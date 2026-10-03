"""Backend-only secrets for the optional language-model reviewers. Keys are read from the environment or a local .env file and never logged."""

from __future__ import annotations

import os
import re
from pathlib import Path

_CANDIDATES = [os.environ.get("SEAWATCH_ENV_FILE", ""), ".env", "../.env"]


def _from_files(name: str) -> str:
    for c in _CANDIDATES:
        if not c:
            continue
        p = Path(c)
        if not p.is_file():
            continue
        for line in p.read_text(encoding="utf8", errors="ignore").splitlines():
            m = re.match(r"\s*([A-Za-z0-9_]+)\s*[:=]\s*(.+?)\s*$", line)
            if m and m.group(1).upper() in (name.upper(), name.upper() + "_KEY"):
                return m.group(2).strip().strip('"').strip("'")
    return ""


def secret(name: str) -> str:
    """Value of ``name`` (also tries NAME_KEY) from the environment, then from the .env files listed in SEAWATCH_ENV_FILE, ./.env, ../.env."""

    return os.environ.get(name) or os.environ.get(name + "_KEY") or _from_files(name)
