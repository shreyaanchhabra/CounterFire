"""Gemini and Voiskey endpoints, mounted into the Grok desk app (backend/main.py)."""
import asyncio
import logging

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from . import config
from .agents import draft_ask, editor
from .analyze import analyze, evidence_packet
from .schemas import AnalyzeOut, AskOut, EditorOut, Framing

log = logging.getLogger("firebreak.gemini")
router = APIRouter(prefix="/api")

MAX_UPLOAD = 15 * 1024 * 1024
FRAMING_NAMES = {"A": "Fact check", "B": "Action first", "C": "Neighbor voice"}


@router.get("/gemini/health")
def health():
    return {"gemini_key": bool(config.GEMINI_API_KEY), "model": config.GEMINI_MODEL or "auto",
            "fallbacks": config.GEMINI_FALLBACK_MODELS, "demo_mode": config.DEMO_MODE}


@router.post("/gemini/episodes/{identifier}/evidence")
async def verify_scenario(identifier: str, request: Request):
    """Run Gemini on the scenario image and import the result as the episode's evidence."""
    controller = request.app.state.controller
    controller.view(identifier)  # 404 before spending any quota
    sc = config.scenario()
    image = (config.DATA / sc["image"]).read_bytes()
    try:
        (pro, s1), (dfn, _), (jdg, s3), h = await asyncio.wait_for(
            analyze(image, "image/png", sc["claim"], sc["context"], live=False), config.TIMEOUTS["analyze"])
    except Exception as e:  # noqa: BLE001
        log.warning("scenario verification failed: %s", e)
        raise HTTPException(502, f"Gemini verification failed: {e}")
    status = "fallback" if "fallback" in (s1, s3) else s3
    packet = evidence_packet(pro, dfn, jdg, h=h, status=status, sc=sc)
    view = controller.evidence(identifier, packet)
    return {"view": view, "image_url": f"/data/{sc['image']}", "status": status}


async def _read_upload(f: UploadFile, kind: str) -> tuple[bytes, str]:
    data = await f.read()
    if not data:
        raise HTTPException(400, f"Empty {kind} file")
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, f"{kind.capitalize()} is too large (15 MB max)")
    mime = (f.content_type or "").split(";")[0]
    if not mime.startswith(kind + "/"):
        raise HTTPException(415, f"Expected an {kind} file, got {mime or 'unknown type'}")
    return data, mime


@router.post("/analyze", response_model=AnalyzeOut)
async def analyze_upload(image: UploadFile = File(...), claim: str = Form(...)):
    """Bring your own image: the full Gemini debate, live. Display only; it doesn't change the episode."""
    data, mime = await _read_upload(image, "image")
    sc = config.scenario()
    ctx = sc["context"] if claim.strip() == sc["claim"] else {"date": sc["context"]["date"]}
    ctx = {k: v for k, v in ctx.items() if k != "image_note"}  # an uploaded image is a real image
    try:
        (pro, _), (dfn, _), (jdg, _), h = await asyncio.wait_for(
            analyze(data, mime, claim.strip(), ctx, live=True), config.TIMEOUTS["analyze"])
    except Exception as e:  # noqa: BLE001
        log.warning("analyze failed: %s", e)
        raise HTTPException(502, f"Gemini couldn't analyze that image: {e}")
    return AnalyzeOut(prosecutor=pro, defender=dfn, judge=jdg, image_hash=h)


class VoiceOut(EditorOut):
    target_groups: list[int]


@router.post("/voice", response_model=VoiceOut)
async def voice(audio: UploadFile | None = File(None), text: str | None = Form(None),
                framing_key: str = Form("B"), text_en: str = Form(""), text_es: str = Form(""),
                es: bool = Form(True), source: str = Form("")):
    """A voice note from Voiskey (typed text, source="voiskey") or the mic (WAV audio).

    text_en/text_es are the editor's current copy for the selected framing; the note rewrites it."""
    if audio is None and not (text and text.strip()):
        raise HTTPException(400, "Send audio or text")
    if not text_en.strip():
        raise HTTPException(409, "Draft corrections first so there's copy to edit")
    data, mime = (await _read_upload(audio, "audio")) if audio is not None else (None, None)
    key = framing_key if framing_key in FRAMING_NAMES else "B"
    framing = Framing(key=key, name=FRAMING_NAMES[key], text_en=text_en, text_es=text_es or text_en)
    try:
        out = await asyncio.wait_for(
            editor.run(framing, config.scenario()["claim"], audio=data, mime=mime, text=text, want_es=es,
                       voiskey_clean=source == "voiskey"),
            config.TIMEOUTS["editor"])
    except Exception as e:  # noqa: BLE001
        log.warning("voice failed: %s", e)
        raise HTTPException(502, f"Couldn't process the voice note: {e}")
    groups = sorted({g for g in out.intent.target_groups if 0 <= g <= 5})
    return VoiceOut(**out.model_dump(), target_groups=groups)


class AskIn(BaseModel):
    item: str
    ask_target: str


@router.post("/draft_ask", response_model=AskOut)
async def ask(body: AskIn):
    try:
        return await asyncio.wait_for(draft_ask.run(body.item, body.ask_target, config.scenario()["claim"]),
                                      config.TIMEOUTS["draft_ask"])
    except Exception as e:  # noqa: BLE001
        log.warning("draft_ask failed: %s", e)
        return draft_ask.template(body.item, body.ask_target)
