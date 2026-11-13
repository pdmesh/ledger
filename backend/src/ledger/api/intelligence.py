"""Intelligence provider configuration, routing, credentials and execution records."""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ledger.api.deps import bad_request, get_session
from ledger.config import get_setting, put_setting
from ledger.intelligence.providers import (
    CLI_DEFAULTS,
    ProviderConfig,
    ProviderError,
    build_provider,
    detect_cli,
    has_api_key,
    list_models,
    set_api_key,
)
from ledger.intelligence.router import TASKS
from ledger.models import AIExecution

router = APIRouter(prefix="/intelligence", tags=["intelligence"])

# Suggested starting points shown in the UI; nothing is enabled until the user saves it.
PROVIDER_TEMPLATES = [
    {
        "kind": "local",
        "label": "Ollama (local)",
        "model": "ollama_chat/llama3.1",
        "api_base": "http://127.0.0.1:11434",
    },
    {
        "kind": "local",
        "label": "OpenAI-compatible local server (MLX, LM Studio, vLLM)",
        "model": "openai/local-model",
        "api_base": "http://127.0.0.1:8080/v1",
    },
    {"kind": "api", "label": "Anthropic", "model": "anthropic/claude-haiku-5-5"},
    {"kind": "api", "label": "OpenAI", "model": "openai/gpt-5-mini"},
    {"kind": "api", "label": "Google Gemini", "model": "gemini/gemini-2.5-flash"},
    {"kind": "cli", "label": "Claude Code CLI", "cli": "claude"},
    {"kind": "cli", "label": "OpenAI Codex CLI", "cli": "codex"},
]


def _public(intel: dict[str, Any]) -> dict[str, Any]:
    providers = []
    for p in intel.get("providers", []):
        providers.append({**p, "has_key": has_api_key(p["id"]) if p.get("kind") != "cli" else None})
    return {**intel, "providers": providers}


@router.get("")
def get_config(s: Session = Depends(get_session)) -> dict[str, Any]:
    return {
        **_public(get_setting(s, "intelligence")),
        "tasks": TASKS,
        "templates": PROVIDER_TEMPLATES,
    }


class ProviderBody(BaseModel):
    id: str
    kind: str
    label: str | None = None
    model: str | None = None
    api_base: str | None = None
    cli: str | None = None
    executable: str | None = None
    extra_args: list[str] = []
    timeout_s: int = 120
    max_tokens: int = 4096
    temperature: float = 0.0
    enabled: bool = True


class IntelligenceBody(BaseModel):
    providers: list[ProviderBody]
    routing: dict[str, list[str]] = {}
    allow_cloud: bool = False
    share_identity_names: bool = False
    batch_size: int = 40


@router.put("")
def put_config(body: IntelligenceBody, s: Session = Depends(get_session)) -> dict[str, Any]:
    ids = set()
    for p in body.providers:
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", p.id):
            raise bad_request(f"provider id '{p.id}' must be lowercase letters/digits/-/_")
        if p.id in ids:
            raise bad_request(f"duplicate provider id '{p.id}'")
        ids.add(p.id)
        if p.kind not in ("api", "local", "cli"):
            raise bad_request("kind must be api, local or cli")
        if p.kind == "cli" and p.cli not in CLI_DEFAULTS:
            raise bad_request(f"cli must be one of {', '.join(CLI_DEFAULTS)}")
        if p.kind != "cli" and not p.model:
            raise bad_request(f"provider '{p.id}' needs a model")
    for task, chain in body.routing.items():
        if task != "default" and task not in TASKS:
            raise bad_request(f"unknown task '{task}'")
        missing = [c for c in chain if c not in ids]
        if missing:
            raise bad_request(f"routing for '{task}' references unknown providers {missing}")
    # replace (not merge) providers/routing so deletions stick
    data = body.model_dump()
    from ledger.models import Setting

    row = s.get(Setting, "intelligence")
    if row:
        row.value = data
        s.flush()
    merged = put_setting(s, "intelligence", data, summary="Intelligence providers updated")
    return _public(merged)


class KeyBody(BaseModel):
    api_key: str | None = None


@router.put("/providers/{provider_id}/key")
def store_key(provider_id: str, body: KeyBody) -> dict[str, Any]:
    """Store/remove an API key in the OS keychain. Keys never touch the database."""
    try:
        set_api_key(provider_id, body.api_key)
    except Exception as e:  # keyring backend unavailable
        raise bad_request(f"Could not access the OS keychain: {type(e).__name__}") from e
    return {"has_key": has_api_key(provider_id)}


@router.post("/models")
def models(body: ProviderBody) -> dict[str, Any]:
    """Model suggestions for a (possibly unsaved) provider configuration."""
    return list_models(ProviderConfig.from_dict(body.model_dump()))


@router.get("/cli/{name}")
def cli_status(name: str, executable: str | None = None) -> dict[str, Any]:
    if name not in CLI_DEFAULTS:
        raise bad_request("unknown cli")
    return detect_cli(name, executable)


@router.post("/providers/{provider_id}/test")
def test_provider(provider_id: str, s: Session = Depends(get_session)) -> dict[str, Any]:
    intel = get_setting(s, "intelligence")
    cfg = next((p for p in intel.get("providers", []) if p["id"] == provider_id), None)
    if cfg is None:
        raise bad_request("unknown provider")
    provider = build_provider(ProviderConfig.from_dict(cfg))
    try:
        res = provider.complete_json(
            "Reply with JSON only.", 'Return {"ok": true} and nothing else.'
        )
    except ProviderError as e:
        return {"ok": False, "error": str(e)}
    return {
        "ok": bool(isinstance(res.data, dict) and res.data.get("ok")),
        "model": res.model,
        "latency_ms": res.latency_ms,
    }


@router.get("/executions")
def executions(limit: int = 100, s: Session = Depends(get_session)) -> dict[str, Any]:
    rows = s.scalars(select(AIExecution).order_by(AIExecution.id.desc()).limit(limit)).all()
    totals = s.execute(
        select(
            AIExecution.task,
            AIExecution.provider_id,
            func.count(),
            func.sum(AIExecution.cost_usd),
            func.sum(AIExecution.input_tokens),
            func.sum(AIExecution.output_tokens),
        ).group_by(AIExecution.task, AIExecution.provider_id)
    ).all()
    return {
        "items": [
            {
                "id": e.id,
                "task": e.task,
                "provider_id": e.provider_id,
                "kind": e.provider_kind,
                "model": e.model,
                "status": e.status,
                "error": e.error,
                "input_tokens": e.input_tokens,
                "output_tokens": e.output_tokens,
                "cost_usd": e.cost_usd,
                "latency_ms": e.latency_ms,
                "item_count": e.item_count,
                "config_version": e.config_version,
                "created_at": e.created_at,
            }
            for e in rows
        ],
        "totals": [
            {
                "task": t,
                "provider_id": p,
                "calls": n,
                "cost_usd": c,
                "input_tokens": i,
                "output_tokens": o,
            }
            for t, p, n, c, i, o in totals
        ],
    }
