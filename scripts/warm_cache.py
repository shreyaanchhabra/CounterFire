"""Warm the Grok-only cache. Pass --fixtures for synthetic offline results."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.run_grok import main


if __name__ == "__main__":
    # Always generate fresh results; all other flags use run_grok's interface.
    raise SystemExit(main([*sys.argv[1:], "--mode", "live"]))
