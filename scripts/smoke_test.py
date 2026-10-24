"""Discover xAI models or make one tiny structured-output request."""

import argparse
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.clients.grok_client import GrokClient
from backend.config import Settings


class SmokeAnswer(BaseModel):
    ok: Literal[True]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list-models", action="store_true")
    args = parser.parse_args()
    client = GrokClient(Settings.from_env())
    try:
        if args.list_models:
            for model in client.list_models():
                print(model)
        else:
            model = client.settings.model
            available = client.list_models()
            if model not in available:
                print("FAIL: Set GROK_MODEL to an ID returned by --list-models", file=sys.stderr)
                return 1
            client.generate('Return {"ok": true}.', "This is a connectivity test.", SmokeAnswer)
            print(f"OK: Grok structured JSON with {model}")
            fast = client.settings.fast_model
            if fast and fast != model:
                if fast not in available:
                    print("FAIL: GROK_FAST_MODEL is not in the available model list", file=sys.stderr)
                    return 1
                client.generate('Return {"ok": true}.', "This is a connectivity test.", SmokeAnswer, model=fast)
                print(f"OK: Grok structured JSON with {fast}")
        return 0
    except ValueError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"FAIL: {type(exc).__name__}. Check xAI access and model configuration.", file=sys.stderr)
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
