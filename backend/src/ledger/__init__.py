"""Personal Ledger: local-first financial ledger backend."""

__version__ = "0.1.0"

import os as _os

# Local-first: LiteLLM otherwise downloads its model price list from GitHub whenever it is
# imported. Use the copy bundled with the package so the app makes no network calls of its
# own; only requests to providers the user configured leave the machine.
_os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
_os.environ.setdefault("LITELLM_TELEMETRY", "False")
