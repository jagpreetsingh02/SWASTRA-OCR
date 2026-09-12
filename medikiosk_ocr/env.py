"""Minimal .env support, so local settings (HF_TOKEN) do not have to be exported by hand.

Deliberately not a configuration framework: `KEY=VALUE` lines from the project's `.env` are copied
into the environment, and anything already exported wins, so `HF_TOKEN=... uvicorn ...`, systemd
units and CI secrets keep working unchanged. Values are never logged or returned.
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def load_env(path: Path | str | None = None) -> list[str]:
    """Copy KEY=VALUE lines from `.env` into os.environ. Returns the NAMES set (never the values)."""
    env_file = Path(path) if path is not None else ENV_FILE
    try:
        lines = env_file.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return []
    applied = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key and key not in os.environ:      # an exported variable always wins
            os.environ[key] = value
            applied.append(key)
    return applied


def huggingface_token_configured() -> bool:
    """True if a token is available for gated/private models. The value itself is never exposed."""
    return bool(os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN") or os.environ.get("HUGGINGFACEHUB_API_TOKEN"))
