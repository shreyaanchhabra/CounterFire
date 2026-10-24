"""One tiny call per Gemini capability. Prints OK/FAIL and the models your key can use.

Run: .venv/Scripts/python scripts/smoke_test.py
"""
import asyncio
import io
import struct
import sys
import time
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import config  # noqa: E402
from backend.clients import gemini_client as gc  # noqa: E402
from backend.schemas import Transcript, VisionOut  # noqa: E402


def silent_wav(seconds=1.0, rate=16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack("<h", 0) * int(rate * seconds))
    return buf.getvalue()


async def check(name, coro):
    t = time.perf_counter()
    try:
        out = await coro
        print(f"OK   {name} ({time.perf_counter() - t:.1f}s): {str(out)[:150]}")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"FAIL {name} ({time.perf_counter() - t:.1f}s): {type(e).__name__}: {e}")
        return False


async def main():
    if not config.GEMINI_API_KEY:
        sys.exit("GEMINI_API_KEY is not set. Copy .env.example to .env and add it.")
    names = gc.list_text_models()
    print("Models with generateContent:")
    for n in sorted(n for n in names if n.startswith("gemini")):
        print("  ", n)
    print(f"\nUsing GEMINI_MODEL={gc.model()}  (auto-picked)" if not config.GEMINI_MODEL else f"\nUsing GEMINI_MODEL={gc.model()}")
    print(f"Judge model: {gc.judge_model()}\n")

    image = (config.DATA / "viral.png").read_bytes()
    results = [
        await check("text", gc.gemini_text("Reply with the single word: ready")),
        await check("image + JSON + box_2d", gc.gemini_json(
            "Find the road sign. One finding with box_2d [ymin,xmin,ymax,xmax] 0-1000, category location. "
            "bullets: one short point. image_description: one sentence.", VisionOut, image, "image/png")),
        await check("Google Search grounding", gc.gemini_grounded_text("What is the date today? Answer in one line.")),
        await check("audio (WAV) transcription", gc.gemini_json(
            "Transcribe this audio. If silent, return an empty string.", Transcript, silent_wav(), "audio/wav")),
    ]
    print(f"\n{sum(results)}/{len(results)} passed")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    asyncio.run(main())
