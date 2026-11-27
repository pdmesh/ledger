---
title: Use AI providers
---

# Use AI providers

[← User guide](index.md)

Ledger works without any AI. Your rules, merchant mappings and corrections still
categorise transactions, and anything else is left uncategorised for you. An AI provider
adds three things: categorising transactions nothing else recognised, reading statements
with an unusual layout, and reading scanned PDFs.

Set providers up under **Settings → Intelligence providers**. **Add provider** offers three
kinds.

## Local models (stay on your computer)

Run a model with [Ollama](https://ollama.com) or any OpenAI-compatible local server (LM
Studio, MLX, llama.cpp, vLLM) and add it as a local provider. Nothing leaves your
computer. Local providers are always allowed. To read scanned PDFs, the model must accept
images.

## Cloud APIs (your own key)

Anthropic, OpenAI, Google Gemini and others, with your own API key. Enter the key and
choose **Store in keychain**; it's kept in your macOS keychain, never in the ledger
database. Pick the model from the list, or type any model name the provider supports.

## Claude Code or Codex (use your existing subscription)

If you already use [Claude Code](https://claude.com/claude-code) or Codex, Ledger can run
it for you. You don't give Ledger any key or token: the CLI uses the login you already
have.

1. Install the CLI and sign in to it once from Terminal.
2. Add **Claude Code CLI** or **OpenAI Codex CLI** as a provider.
3. Choose **Detect** to check Ledger can find it, then **Test** to make one small request.

**Model.** **CLI default** uses the CLI's built-in default model. Ledger runs Claude Code
in a restricted mode that ignores your personal Claude Code settings, so a default model
you set there isn't used. Choose a model here (for example `sonnet`) to control which
model runs and what it costs. **Other…** lets you type any model name the CLI accepts.

**Safety.** The CLI runs in an empty temporary folder. For Claude Code, text requests get
no tools at all, and when it reads scanned pages its only tool is reading files, limited
to that folder.

## Allowing cloud and CLI providers

Cloud APIs and CLIs are only used after you turn on **Allow cloud and CLI providers**
under **Privacy**. What they receive:

- **Categorising**: transaction descriptions and amounts. With **Share household names**
  off, people's names are replaced by "Person 1", "Person 2".
- **Reading a statement** (unusual layout or scanned PDF): the whole statement as it is,
  as text or page images, including names, account numbers and addresses. Names can't be
  replaced here. To keep statements on your computer, route the **extract** task to a
  local model.

## Task routing and fallbacks

**Task routing** chooses which provider handles each kind of work (categorising, reading
statements, matching, answering questions…). Tasks without their own route use
**default**. After the first provider you can add fallbacks: if a provider fails, times
out or returns something unusable, the next one is tried. A good setup uses a small or
local model for routine categorising and a stronger one for reading statements.

**Recent model calls** at the bottom lists every request: which task, provider and model,
whether it worked, how long it took and its cost when known. The content of requests is
never recorded.
