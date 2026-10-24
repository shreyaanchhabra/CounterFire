"""Run the full pipeline once in live mode and save every agent output to cache/.

Run it 2 or 3 times and keep the best run (check the Prosecutor caught the sign):
  .venv/Scripts/python scripts/warm_cache.py
Agents that aren't built yet (Grok stubs) fall back to data/fixtures and are not cached.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")  # Windows console defaults to cp1252

from backend import config, pipeline  # noqa: E402

config.DEMO_MODE = "live"


async def main():
    q: asyncio.Queue = asyncio.Queue()
    task = asyncio.create_task(pipeline._run(q))
    while (ev := await q.get()) is not None:
        print(f"{ev['agent']:<12} {ev['status']:<9} {ev['summary']}")
        if ev["agent"] == "prosecutor":
            for f in ev["payload"]["findings"]:
                print(f"    {f['id']}. [{f['category']}] {f['label']}  box={f['box_2d']}")
        if ev["agent"] == "judge":
            print("    " + json.dumps(ev["payload"], ensure_ascii=False))
    await task
    print(f"\nCache files: {sorted(p.name for p in config.CACHE.glob('*.json'))}")


if __name__ == "__main__":
    asyncio.run(main())
