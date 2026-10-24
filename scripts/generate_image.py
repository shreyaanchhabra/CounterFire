"""Generate a realistic version of the viral photo with a Gemini image model.

Writes data/viral_candidate.png. Look at it, and if it's good, copy it over data/viral.png
and run scripts/warm_cache.py again (the cache is keyed by image hash).

Run: .venv/Scripts/python scripts/generate_image.py [model]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")  # Windows console defaults to cp1252

from google.genai import types  # noqa: E402

from backend import config  # noqa: E402
from backend.clients.gemini_client import client  # noqa: E402

PROMPT = """A realistic smartphone photo, landscape orientation, taken from a car on a multi-lane desert freeway at dusk.
A wildfire burns on the low hills to the right of the freeway, orange flames and a big plume of brown smoke.
A large green overhead freeway guide sign is clearly readable: top line "101 NORTH", second line "Scottsdale Rd 1 MILE".
Sonoran desert landscape with a few saguaro cacti near the road. A few cars with tail lights on the freeway.
Slight motion blur and phone camera noise. No watermarks, no extra text, no people."""


def main():
    model = sys.argv[1] if len(sys.argv) > 1 else "gemini-3.1-flash-image"
    resp = client().models.generate_content(
        model=model, contents=PROMPT,
        config=types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]))
    for part in resp.candidates[0].content.parts:
        if part.inline_data and part.inline_data.data:
            out = config.DATA / "viral_candidate.png"
            out.write_bytes(part.inline_data.data)
            print(f"Wrote {out} ({len(part.inline_data.data) // 1024} KB, {part.inline_data.mime_type})")
            return
    sys.exit("No image returned: " + (resp.text or ""))


if __name__ == "__main__":
    main()
