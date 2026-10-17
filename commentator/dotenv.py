"""Reads the booth's own .env file into this process's environment only.

Keeps the API key scoped to the booth instead of a user-wide environment variable every
program on the machine can see. Values here override anything set system-wide.
"""

import os
from pathlib import Path


def load_env(path: Path) -> list[str]:
    """Returns the names it set. Lines are KEY=value; # comments and blank lines are skipped."""
    if not path.is_file():
        return []
    names = []
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and value:
            os.environ[key] = value
            names.append(key)
    return names
