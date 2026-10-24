"""Eval the Prosecutor → Defender → Judge chain on 30 labeled PolitiFact claims (LIAR dataset).

Labels: pants-fire / false → False, true / mostly-true → True. Middle labels skipped. 15/15 balanced.
Verdicts: False and Misleading count as False. Unverified counts as wrong (and is reported separately).
No search grounding, so the agents can't just look up the PolitiFact ruling.

Data: downloads the original LIAR zip (1 MB) from UCSB once into data/liar/.
The Hugging Face copy uses a loading script that current `datasets` no longer supports.

Run: .venv/Scripts/python scripts/run_eval.py [--n 30]
Writes cache/eval.json. The Judge pill then shows "eval X/30".
"""
import argparse
import asyncio
import csv
import io
import json
import random
import re
import subprocess
import sys
import zipfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")  # Windows console defaults to cp1252

from backend import config  # noqa: E402
from backend.agents import defender, judge, prosecutor  # noqa: E402

LIAR = config.DATA / "liar"
ZIP_URL = "https://www.cs.ucsb.edu/~william/data/liar_dataset.zip"
GOLD = {"pants-fire": "False", "false": "False", "true": "True", "mostly-true": "True"}


def load_rows() -> list[tuple[str, str]]:
    """(statement, label) from LIAR test.tsv. Columns: id, label, statement, ..."""
    LIAR.mkdir(parents=True, exist_ok=True)
    tsv = LIAR / "test.tsv"
    if not tsv.exists():
        # The UCSB server refuses Python HTTP clients but serves curl (built into Windows 10+).
        data = subprocess.run(["curl", "-sL", ZIP_URL], capture_output=True, check=True, timeout=120).stdout
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            tsv.write_bytes(z.read("test.tsv"))
    with tsv.open(encoding="utf-8") as f:
        return [(r[2], r[1]) for r in csv.reader(f, delimiter="	", quoting=csv.QUOTE_NONE) if len(r) > 2]


async def patient(fn, tries=6):
    """Free tier allows ~5 requests/min per model. On 429, wait the delay Google asks for and retry."""
    for i in range(tries):
        try:
            return await fn()
        except Exception as e:  # noqa: BLE001
            if "429" not in str(e) or i == tries - 1:
                raise
            m = re.search(r"retryDelay': '(\d+)", str(e))
            await asyncio.sleep(int(m.group(1)) + 2 if m else 30)


async def judge_claim(claim: str) -> str:
    pro = await patient(lambda: prosecutor.run_text(claim))
    dfn = await patient(lambda: defender.run(claim, ""))
    j = await patient(lambda: judge.run(claim, pro, dfn, []))
    return j.verdict


async def main(n: int):
    rows = [(s, GOLD[l]) for s, l in load_rows() if l in GOLD]
    rng = random.Random(1024)
    rng.shuffle(rows)
    pick = [r for r in rows if r[1] == "False"][: n // 2] + [r for r in rows if r[1] == "True"][: n - n // 2]

    sem = asyncio.Semaphore(1)  # free tier rate limits

    async def one(i, claim, gold):
        async with sem:
            try:
                v = await judge_claim(claim)
            except Exception as e:  # noqa: BLE001
                v = f"error: {e}"
        pred = "False" if v in ("False", "Misleading") else v
        print(f"{i + 1:>2}. gold={gold:<5} judge={v:<11} {'✓' if pred == gold else '✗'}  {claim[:80]}")
        return {"claim": claim, "gold": gold, "verdict": v, "correct": pred == gold}

    items = await asyncio.gather(*(one(i, c, g) for i, (c, g) in enumerate(pick)))
    done = [x for x in items if not x["verdict"].startswith("error")]
    errors = len(items) - len(done)
    correct = sum(x["correct"] for x in done)
    confusion = Counter(f"{x['gold']}→{x['verdict']}" for x in done)
    out = {"correct": correct, "total": len(done), "errors": errors, "accuracy": round(correct / max(1, len(done)), 3),
           "confusion": dict(confusion), "unverified": sum(x["verdict"] == "Unverified" for x in done), "items": items}
    # Only a clean run feeds the UI's "eval X/30". A run with API errors is saved aside.
    name = "eval.json" if not errors else "eval_partial.json"
    (config.CACHE / name).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nJudge: {correct}/{len(done)} correct, {errors} errors. Confusion: {dict(confusion)}. Saved cache/{name}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    asyncio.run(main(ap.parse_args().n))
