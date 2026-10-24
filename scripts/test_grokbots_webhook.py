"""Trigger the official connectivity routine once. No automatic retries."""

import argparse
import json
import sys
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.clients.grokbots_webhook import GrokBotsWebhookClient, WebhookSettings
from backend.config import ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request-id", default=None)
    args = parser.parse_args()
    load_dotenv(ROOT / ".env", override=False)
    try:
        client = GrokBotsWebhookClient(WebhookSettings.from_env())
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    try:
        result = client.send({"test": "FIREBREAK_WEBHOOK_OK", "synthetic": True},
                             request_id=args.request_id or f"firebreak-smoke-{uuid4()}")
        print(json.dumps(result.model_dump()))
        print("A receipt is not a completed Bot response. Verify the matching request_id in Trial's chat.", file=sys.stderr)
        return 0 if result.delivery == "accepted" else 1
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
