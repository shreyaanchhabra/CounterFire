"""Send one official Bot task and wait for its authenticated local callback."""

import argparse
import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.clients.grokbots_webhook import GrokBotsWebhookClient, WebhookSettings
from backend.config import ROOT
from backend.grokbots_return import JobStore, RoundTask, callback_observation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--callback-base-url", required=True)
    parser.add_argument("--wait-seconds", type=int, default=180)
    args = parser.parse_args()
    if not 1 <= args.wait_seconds <= 600:
        parser.error("--wait-seconds must be between 1 and 600")
    load_dotenv(ROOT / ".env", override=False)
    store = JobStore(ROOT / "cache/grokbots/jobs.sqlite3")
    task = RoundTask(episode_id="official-webhook-spike", round_id=1, group_id=0, observation={
        "synthetic": True, "persona": "A fictional resident who checks sources before sharing.",
        "messages": [{"id": "message-1", "text": "A neighbor says the fire crossed I-15. No source is provided."}],
        "prior_belief": 0.5, "instruction": "Choose one social action using only the delivered information."})
    client = GrokBotsWebhookClient(WebhookSettings.from_env())
    try:
        job = store.create(task, ttl=args.wait_seconds + 30)
        observation = callback_observation(task, job, args.callback_base_url)
        receipt = client.send(observation, request_id=job.request_id)
        print(json.dumps({"request_id": job.request_id, "delivery": receipt.delivery,
                          "http_status": receipt.http_status}), flush=True)
        if receipt.delivery == "rejected":
            return 1
        deadline = time.monotonic() + args.wait_seconds
        while time.monotonic() < deadline:
            state = store.get(job.request_id)
            if state["status"] == "completed":
                print(json.dumps({"status": "completed", "result": state["result"]}, ensure_ascii=False), flush=True)
                return 0
            if state["status"] != "pending":
                print("Task was superseded; no resend attempted.", file=sys.stderr)
                return 1
            time.sleep(1)
        print("No validated callback arrived before the deadline. Do not blindly resend.", file=sys.stderr)
        return 2
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
