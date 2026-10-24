"""Run Gemini verification on the scenario image once, live, and save it to cache/gemini/.

The desk then loads it instantly (and with no quota) when an episode starts.
Run: .venv/Scripts/python scripts/gemini_warm_cache.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")  # Windows console defaults to cp1252

from backend.gemini import config  # noqa: E402
from backend.gemini.analyze import analyze  # noqa: E402

config.DEMO_MODE = "live"


async def main():
    sc = config.scenario()
    image = (config.DATA / sc["image"]).read_bytes()
    (pro, s1), (dfn, s2), (jdg, s3), h = await analyze(image, "image/png", sc["claim"], sc["context"], live=False)
    print(f"prosecutor {s1}")
    for f in pro.findings:
        print(f"    {f.id}. [{f.category}] {f.label}  box={f.box_2d}")
    print(f"defender   {s2}  {dfn.bullets}")
    print(f"judge      {s3}  " + json.dumps(jdg.model_dump(), ensure_ascii=False))
    print(f"\nCache: {sorted(p.name for p in config.CACHE.glob('*.json'))}")


if __name__ == "__main__":
    asyncio.run(main())
