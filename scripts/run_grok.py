"""Run the Grok-only demo. Offline fixtures always require an explicit flag."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.agents.runner import AgentRunner
from backend.cache import CacheMiss, DiskCache
from backend.clients.grok_client import GrokClient
from backend.config import Settings
from backend.demo import DemoFixtureProvider, run_demo


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", action="store_true", help="Use labeled synthetic outputs, with no API calls")
    parser.add_argument("--mode", choices=["live", "hybrid", "replay"])
    parser.add_argument("--approve", action="store_true", help="Approve the recommended framing for the in-app feed only")
    parser.add_argument("--cache-dir", type=Path)
    args = parser.parse_args(argv)
    settings = Settings.from_env()
    provider = DemoFixtureProvider() if args.fixtures else GrokClient(settings)
    directory = args.cache_dir or settings.cache_dir / ("fixtures" if args.fixtures else "grok")
    runner = AgentRunner(provider, DiskCache(directory, settings.timeout),
        model="synthetic-fixture-v1" if args.fixtures else settings.model,
        fast_model="" if args.fixtures else settings.fast_model, mode=args.mode or settings.mode)
    try:
        print(json.dumps(run_demo(runner, approved=args.approve), ensure_ascii=False, indent=2))
        return 0
    except (CacheMiss, ValueError, TimeoutError) as exc:
        print(f"Grok demo could not finish: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        # Do not dump upstream response bodies or configuration that might contain keys.
        print(f"Grok demo could not finish ({type(exc).__name__}). Check API access and model configuration.", file=sys.stderr)
        return 1
    finally:
        if isinstance(provider, GrokClient):
            provider.close()


if __name__ == "__main__":
    raise SystemExit(main())
