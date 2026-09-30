"""Run the staged, offline Phase 3B behavioral review-ranking workflow."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apps.api.seawatch.review_ranking.pipeline import calibrate, evaluate, report, select_features


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("select-features", "calibrate", "evaluate", "report"):
        command = sub.add_parser(name)
        command.add_argument("--force", action="store_true")
        command.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    functions = {"select-features": select_features, "calibrate": calibrate, "evaluate": evaluate, "report": report}
    try:
        path = functions[args.command](root=root, output=args.output, overwrite=args.force)
    except (FileExistsError, KeyError, OSError, TypeError, ValueError) as error:
        parser.exit(1, f"error: {error}\n")
    print(f"{args.command}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
