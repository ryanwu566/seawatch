"""Describe a folder/file of historic AIS so we know how to use it.

    python scripts/inspect_history.py D:/path/to/ais

Prints file count, columns, the auto-detected column mapping, the area and time
covered, and a few sample rows. Paste the output to whoever is wiring it in.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from seawatch.detection import history  # noqa: E402

if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    print(json.dumps(history.inspect(sys.argv[1]), indent=1, default=str))
