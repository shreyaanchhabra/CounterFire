"""Editor: the comms officer's voice note becomes clean posts and app commands.

Voiskey is a desktop speak-to-type app with no API. The officer holds Right Alt and Voiskey
types a cleaned note (fillers and grammar slips removed) into the Editor's dictation box,
which sends it here as text. Gemini then parses the commands and rewrites the chosen framing.
The hold-to-talk mic is the backup: Gemini transcribes the audio itself.
"""
import re

from ..clients.gemini_client import gemini_json
from ..clients.voiskey_client import VoiskeyClient
from ..schemas import EditorOut, Framing, Transcript, VoiceParse
from ._util import short

TRANSCRIBE = """Transcribe this voice note word for word, exactly as spoken.
Keep filler words (um, uh, like, okay so) and false starts. No speaker labels. No punctuation cleanup beyond commas."""

PARSE = """You help a county emergency comms officer during a wildfire rumor. They dictated this voice note:
RAW: "{raw}"
{clean_line}
The rumor: "{claim}"
The selected correction draft (framing {key}, {name}):
EN: "{en}"
ES: "{es}"

Return:
- clean: the note as clean, well punctuated text with filler removed.{keep_clean}
- filler_words: filler words or phrases exactly as they appear in RAW (like "um", "uh", "like").
- command_phrases: phrases copied exactly from RAW that are instructions or facts to act on
  (like "kill it", "approve", "do Spanish too", "stay off the roads").
- intent.action: approve, kill, edit or none. "kill it" about the rumor means publish the correction, so it is "approve".
  "kill" only means the officer wants to scrap the correction itself.
- intent.languages: languages to publish in, like ["en"] or ["en","es"]. Spanish requested means include "es".
- intent.facts: facts the officer stated, short.
- intent.framing_hint: "A" (fact check), "B" (action first) or "C" (neighbor voice) only if they asked for that style, else null.
- post_en: rewrite the EN draft to include the officer's facts and instructions. Under 280 characters, plain language, 6th grade level, no em dashes.
- post_es: natural Spanish version for North County San Diego parents, under 280 characters, or null if Spanish wasn't requested."""


def _spans(raw: str, phrases: list[str], all_hits: bool) -> list[list[int]]:
    out = []
    low = raw.lower()
    for p in phrases:
        p = p.strip().lower()
        if not p:
            continue
        if all_hits:
            for m in re.finditer(r"(?<!\w)" + re.escape(p) + r"(?!\w)", low):
                out.append([m.start(), m.end()])
        else:
            i = low.find(p)
            if i >= 0:
                out.append([i, i + len(p)])
    return sorted(out)


def _overlaps(a, spans):
    return any(a[0] < b[1] and b[0] < a[1] for b in spans)


async def run(framing: Framing, claim: str, audio: bytes | None = None, mime: str | None = None,
              text: str | None = None, want_es: bool = True, voiskey_clean: bool = False) -> EditorOut:
    """voiskey_clean: `text` was typed by Voiskey, which already removed fillers and fixed grammar."""
    clean = None
    if text:
        raw = text.strip()
        if voiskey_clean:
            clean = raw
    else:
        try:
            raw, clean = await VoiskeyClient().transcribe_and_clean(audio, mime)
        except NotImplementedError:
            raw = (await gemini_json(TRANSCRIBE, Transcript, audio, mime, temperature=0)).raw.strip()
    if not raw:
        raise ValueError("Didn't catch any speech")

    p = await gemini_json(PARSE.format(
        raw=raw, claim=claim, key=framing.key, name=framing.name, en=framing.text_en, es=framing.text_es,
        clean_line=f'CLEAN (from Voiskey): "{clean}"' if clean else "",
        keep_clean=" If CLEAN is given, return it unchanged." if clean else ""), VoiceParse, temperature=0.3)

    commands = _spans(raw, p.command_phrases, all_hits=False)
    fillers = [s for s in _spans(raw, p.filler_words, all_hits=True) if not _overlaps(s, commands)]
    langs = p.intent.languages or ["en"]
    if want_es and "es" not in langs:
        langs = langs + ["es"]
    p.intent.languages = langs
    post_es = p.post_es if "es" in langs else None
    if "es" in langs and not post_es:
        post_es = framing.text_es
    return EditorOut(raw=raw, clean=clean or p.clean, filler_spans=fillers, command_spans=commands, intent=p.intent,
                     post_en=short(p.post_en, 280), post_es=short(post_es, 280) if post_es else None)
