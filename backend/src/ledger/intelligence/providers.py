"""Intelligence provider adapters.

* ``api``   -- cloud models through LiteLLM (Anthropic, OpenAI, Gemini, ...), BYO keys.
* ``local`` -- local inference servers (Ollama, MLX, any OpenAI-compatible endpoint), also
               through LiteLLM, but flagged local so privacy routing can allow them.
* ``cli``   -- user-installed official agent CLIs (Claude Code, Codex) invoked in their
               non-interactive mode. Credentials stay inside the CLI; we never read them.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

KEYRING_SERVICE = "personal-ledger"


class ProviderError(Exception):
    pass


@dataclass
class ProviderConfig:
    id: str
    kind: str  # api|local|cli
    model: str | None = None
    label: str | None = None
    api_base: str | None = None
    cli: str | None = None  # claude|codex
    executable: str | None = None
    extra_args: list[str] = field(default_factory=list)
    timeout_s: int = 120
    max_tokens: int = 4096
    temperature: float = 0.0
    enabled: bool = True

    @property
    def is_local(self) -> bool:
        return self.kind == "local"

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ProviderConfig:
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**known)


@dataclass
class ProviderResult:
    data: Any
    text: str
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    latency_ms: int | None = None


def extract_json(text: str) -> Any:
    """Parse the first JSON object/array in a model response (tolerates code fences)."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        if start < 0:
            continue
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break
    raise ProviderError("Model response did not contain valid JSON")


# --------------------------------------------------------------------------------------
# Secrets: OS keychain via ``keyring``; never stored in the database or logs.
# --------------------------------------------------------------------------------------


def get_api_key(provider_id: str) -> str | None:
    env = os.environ.get(f"LEDGER_KEY_{re.sub(r'[^A-Z0-9]', '_', provider_id.upper())}")
    if env:
        return env
    try:
        import keyring

        return keyring.get_password(KEYRING_SERVICE, provider_id)
    except Exception:
        return None


def set_api_key(provider_id: str, key: str | None) -> None:
    import keyring

    if key:
        keyring.set_password(KEYRING_SERVICE, provider_id, key)
    else:
        try:
            keyring.delete_password(KEYRING_SERVICE, provider_id)
        except Exception:
            pass


def has_api_key(provider_id: str) -> bool:
    return bool(get_api_key(provider_id))


# --------------------------------------------------------------------------------------
# Providers
# --------------------------------------------------------------------------------------


class Provider(ABC):
    def __init__(self, cfg: ProviderConfig):
        self.cfg = cfg

    @abstractmethod
    def complete_json(
        self, system: str, user: str, images: list[Path] | None = None
    ) -> ProviderResult:
        """``images``: optional page images (PNG) for multimodal models."""


class LiteLLMProvider(Provider):
    """API and local models through LiteLLM's unified completion interface."""

    def complete_json(
        self, system: str, user: str, images: list[Path] | None = None
    ) -> ProviderResult:
        import base64

        import litellm

        if not self.cfg.model:
            raise ProviderError(f"Provider {self.cfg.id} has no model configured")
        content: Any = user
        if images:
            try:
                if not litellm.supports_vision(model=self.cfg.model):
                    raise ProviderError(f"{self.cfg.model} does not accept images")
            except ProviderError:
                raise
            except Exception:
                pass  # unknown to LiteLLM's catalogue (e.g. local models): just try
            content = [{"type": "text", "text": user}] + [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()
                    },
                }
                for p in images
            ]
        kwargs: dict[str, Any] = {
            "model": self.cfg.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": content},
            ],
            "timeout": self.cfg.timeout_s,
            "max_tokens": self.cfg.max_tokens,
            "temperature": self.cfg.temperature,
        }
        if self.cfg.api_base:
            kwargs["api_base"] = self.cfg.api_base
        key = get_api_key(self.cfg.id)
        if key:
            kwargs["api_key"] = key
        elif self.cfg.kind == "api":
            raise ProviderError(f"No API key stored for provider {self.cfg.id}")
        try:
            if litellm.supports_response_schema(model=self.cfg.model) or self.cfg.kind == "local":
                kwargs["response_format"] = {"type": "json_object"}
        except Exception:
            pass
        t0 = time.monotonic()
        try:
            resp = litellm.completion(**kwargs)
        except Exception as e:  # litellm raises provider-specific subclasses
            raise ProviderError(f"{type(e).__name__}: {e}") from e
        latency = int((time.monotonic() - t0) * 1000)
        text = resp.choices[0].message.content or ""
        usage = getattr(resp, "usage", None)
        cost = None
        try:
            cost = float(litellm.completion_cost(completion_response=resp))
        except Exception:
            pass
        return ProviderResult(
            data=extract_json(text),
            text=text,
            model=getattr(resp, "model", self.cfg.model),
            input_tokens=getattr(usage, "prompt_tokens", None),
            output_tokens=getattr(usage, "completion_tokens", None),
            cost_usd=cost,
            latency_ms=latency,
        )


CLI_DEFAULTS: dict[str, dict[str, Any]] = {
    # Prompt is passed on stdin. Output is a JSON envelope whose "result" holds the reply.
    # --restricted confines file tools to the working directory and drops tools that run
    # code; --strict-mcp-config skips the user's MCP servers. Statement content is
    # untrusted, so the model gets no tools at all for text, and only Read for page images.
    "claude": {
        "executable": "claude",
        "args": ["-p", "--output-format", "json", "--restricted", "--strict-mcp-config"],
        "output": "claude_json",
    },
    # Codex non-interactive mode; "-" reads the prompt from stdin, the final message is
    # written to a file we provide.
    "codex": {
        "executable": "codex",
        "args": ["exec", "--skip-git-repo-check", "--sandbox", "read-only"],
        "output": "last_message_file",
    },
}


def detect_cli(name: str, executable: str | None = None) -> dict[str, Any]:
    exe = executable or CLI_DEFAULTS[name]["executable"]
    path = shutil.which(exe)
    info: dict[str, Any] = {"cli": name, "executable": exe, "found": bool(path), "path": path}
    if path:
        try:
            out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=15)
            info["version"] = (out.stdout or out.stderr).strip().splitlines()[0][:200]
        except Exception as e:  # pragma: no cover
            info["version_error"] = str(e)
    return info


class CLIProvider(Provider):
    """Runs an official, user-installed agent CLI in non-interactive mode.

    The CLI is executed in an empty temporary working directory so it has no access to the
    ledger's files; all data it sees is in the prompt.
    """

    def complete_json(
        self, system: str, user: str, images: list[Path] | None = None
    ) -> ProviderResult:
        import shutil as _sh

        name = self.cfg.cli or ""
        if name not in CLI_DEFAULTS:
            raise ProviderError(f"Unknown CLI adapter '{name}'")
        spec = CLI_DEFAULTS[name]
        exe = shutil.which(self.cfg.executable or spec["executable"])
        if not exe:
            raise ProviderError(f"{name} CLI not found on PATH; install and log in first")
        prompt = f"{system}\n\n{user}\n\nRespond with a single JSON value only, no prose."
        args = [exe, *spec["args"], *self.cfg.extra_args]
        if self.cfg.model:
            args += ["--model", self.cfg.model]
        # Reading page images takes the CLI roughly 15-20 s a page; allow for it.
        timeout = max(self.cfg.timeout_s, 60 + 45 * len(images)) if images else self.cfg.timeout_s
        t0 = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="ledger-cli-") as tmp:
            out_file = Path(tmp) / "last_message.txt"
            if images:
                # Copy the pages into the CLI's otherwise empty working directory.
                names = []
                for i, src in enumerate(images, start=1):
                    dst = Path(tmp) / f"page-{i}.png"
                    _sh.copyfile(src, dst)
                    names.append(dst.name)
                if name == "claude":
                    # Read is the only tool, and --restricted keeps it inside this directory.
                    args += ["--tools", "Read"]
                    prompt = (
                        f"The statement pages are image files in the current directory: "
                        f"{', '.join(names)}. Read every one of them, in order.\n\n{prompt}"
                    )
                else:
                    args += [f"--image={Path(tmp) / n}" for n in names]
            elif name == "claude":
                args += ["--tools", ""]
            if spec["output"] == "last_message_file":
                args += ["--output-last-message", str(out_file), "-"]
            try:
                proc = subprocess.run(
                    args,
                    input=prompt,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=tmp,
                )
            except subprocess.TimeoutExpired as e:
                raise ProviderError(f"{name} CLI timed out after {timeout}s") from e
            if proc.returncode != 0:
                raise ProviderError(
                    f"{name} CLI exited {proc.returncode}: {(proc.stderr or '')[-500:]}"
                )
            latency = int((time.monotonic() - t0) * 1000)
            cost = None
            in_tok = out_tok = None
            actual_model = None
            if spec["output"] == "claude_json":
                try:
                    env = json.loads(proc.stdout)
                except json.JSONDecodeError as e:
                    raise ProviderError("claude CLI did not return a JSON envelope") from e
                if env.get("is_error"):
                    raise ProviderError(f"claude CLI error: {str(env.get('result'))[:300]}")
                text = str(env.get("result", ""))
                actual_model = _primary_model(env.get("modelUsage"))
                cost = env.get("total_cost_usd")
                usage = env.get("usage") or {}
                in_tok, out_tok = usage.get("input_tokens"), usage.get("output_tokens")
            else:
                text = out_file.read_text() if out_file.exists() else proc.stdout
        return ProviderResult(
            data=extract_json(text),
            text=text,
            model=actual_model or self.cfg.model or f"{name} (CLI default)",
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=cost,
            latency_ms=latency,
        )


def _primary_model(usage: Any) -> str | None:
    """The model that did most of the work, from Claude Code's ``modelUsage`` envelope."""
    if not isinstance(usage, dict) or not usage:
        return None

    def weight(item: tuple[str, Any]) -> float:
        u = item[1] if isinstance(item[1], dict) else {}
        return float(u.get("outputTokens") or 0) + float(u.get("inputTokens") or 0)

    return max(usage.items(), key=weight)[0]


# --------------------------------------------------------------------------------------
# Model discovery for the settings UI
# --------------------------------------------------------------------------------------

# Aliases accepted by `claude --model`; each resolves to the latest model of that family.
CLAUDE_CLI_ALIASES = ["opus", "sonnet", "haiku", "fable"]
_DATED = re.compile(r"-\d{8}$|-\d{4}-\d{2}-\d{2}$")
_NOT_CHAT = re.compile(
    r"audio|realtime|tts|transcribe|image|search|embedding|moderation|dall-e|whisper"
)


def _catalog(provider: str) -> list[str]:
    """LiteLLM's bundled (offline) model list for a provider, newest-looking first."""
    try:
        import litellm

        names = list(litellm.models_by_provider.get(provider, []))
    except Exception:
        return []
    names = [n.split("/", 1)[1] if n.startswith(provider + "/") else n for n in names]
    names = [n for n in names if not _DATED.search(n) and not _NOT_CHAT.search(n)]
    return sorted(set(names), reverse=True)


def _http_json(url: str, headers: dict[str, str] | None = None, timeout: float = 4) -> Any:
    import urllib.request

    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - user-configured URL
        return json.loads(r.read())


def list_models(cfg: ProviderConfig) -> dict[str, Any]:
    """Models to offer for a provider.

    CLIs have no "list models" command, so they get their documented aliases plus LiteLLM's
    catalog for that vendor. Local servers are asked directly (Ollama ``/api/tags``, or an
    OpenAI-compatible ``/models``). Cloud APIs are asked via LiteLLM when a key is stored,
    falling back to LiteLLM's bundled catalog.
    """
    if cfg.kind == "cli":
        if cfg.cli == "claude":
            return {"models": CLAUDE_CLI_ALIASES + _catalog("anthropic"), "source": "catalog"}
        if cfg.cli == "codex":
            gpt = [m for m in _catalog("openai") if m.startswith(("gpt-5", "o3", "o4"))]
            return {"models": gpt, "source": "catalog"}
        return {"models": [], "source": "none"}

    prefix = (cfg.model or "").split("/", 1)[0] if "/" in (cfg.model or "") else ""
    if cfg.kind == "local":
        try:
            if prefix.startswith("ollama"):
                base = (cfg.api_base or "http://127.0.0.1:11434").rstrip("/")
                tags = _http_json(f"{base}/api/tags")
                names = [f"{prefix}/{m['name']}" for m in tags.get("models", [])]
            else:
                base = (cfg.api_base or "").rstrip("/")
                data = _http_json(f"{base}/models")
                names = [f"{prefix or 'openai'}/{m['id']}" for m in data.get("data", [])]
            return {"models": names, "source": "server"}
        except Exception as e:
            return {"models": [], "source": "server", "error": f"Server not reachable: {e}"}

    if not prefix:
        return {"models": [], "source": "none"}
    key = get_api_key(cfg.id)
    if key:
        try:
            from litellm import get_valid_models

            live = get_valid_models(
                check_provider_endpoint=True, custom_llm_provider=prefix, api_key=key
            )
            if live:
                names = [m if m.startswith(prefix + "/") else f"{prefix}/{m}" for m in live]
                return {"models": sorted(set(names), reverse=True), "source": "provider"}
        except Exception:
            pass
    return {"models": [f"{prefix}/{m}" for m in _catalog(prefix)], "source": "catalog"}


def build_provider(cfg: ProviderConfig) -> Provider:
    if cfg.kind in ("api", "local"):
        return LiteLLMProvider(cfg)
    if cfg.kind == "cli":
        return CLIProvider(cfg)
    raise ProviderError(f"Unknown provider kind '{cfg.kind}'")
