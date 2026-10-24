"""Firebreak API. Run: uvicorn backend.main:app --reload --port 8000"""
import asyncio
import json
import logging

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, pipeline
from .agents import broadcaster, draft_ask, editor
from .cache import fixture, get_or_run
from .clients import gemini_client
from .schemas import AnalyzeOut, AskOut, BroadcastOut, DrafterOut, EditorOut, Framing

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("firebreak")

app = FastAPI(title="Firebreak")
app.mount("/static", StaticFiles(directory=config.FRONTEND), name="static")
app.mount("/data", StaticFiles(directory=config.DATA), name="data")

MAX_UPLOAD = 15 * 1024 * 1024


@app.get("/")
def index():
    return FileResponse(config.FRONTEND / "index.html")


@app.get("/api/health")
async def health(check: bool = False):
    out = {"demo_mode": config.DEMO_MODE, "gemini_key": bool(config.GEMINI_API_KEY),
           "xai_key": bool(config.XAI_API_KEY), "voiskey": bool(config.VOISKEY_API_KEY or config.VOISKEY_BASE_URL)}
    if check and config.GEMINI_API_KEY:
        try:
            out["gemini_model"] = await asyncio.to_thread(gemini_client.model)
            out["gemini_ok"] = True
        except Exception as e:  # noqa: BLE001
            out["gemini_ok"], out["gemini_error"] = False, str(e)
    return out


@app.get("/api/scenario")
def get_scenario():
    sc = config.scenario()
    p = config.CACHE / "eval.json"
    ev = json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    return {
        "incident_id": sc["incident_id"], "claim": sc["claim"], "image_url": f"/data/{sc['image']}",
        "posts": sc["posts"], "scripted_replies": sc.get("scripted_replies", []),
        "timeline": pipeline.TIMELINE,
        "eval": {"correct": ev["correct"], "total": ev["total"]} if ev else None,
    }


@app.post("/api/pipeline/start")
async def pipeline_start():
    return {"run_id": pipeline.start()}


@app.get("/api/stream")
async def stream(run_id: str):
    q = pipeline.RUNS.get(run_id)
    if q is None:
        raise HTTPException(404, "Unknown run_id")

    async def gen():
        try:
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), 15)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                if ev is None:
                    yield "event: end\ndata: {}\n\n"
                    return
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        finally:
            pipeline.RUNS.pop(run_id, None)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


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


@app.post("/api/analyze", response_model=AnalyzeOut)
async def analyze(image: UploadFile = File(...), claim: str = Form(...)):
    data, mime = await _read_upload(image, "image")
    sc = config.scenario()
    # The scenario's time and place only apply if it's still the scenario's claim.
    ctx = sc["context"] if claim.strip() == sc["claim"] else {"date": sc["context"]["date"]}
    ctx = {k: v for k, v in ctx.items() if k != "image_note"}  # an uploaded image is a real image
    try:
        (pro, _), (dfn, _), (jdg, _), h = await asyncio.wait_for(
            pipeline.analyze(data, mime, claim.strip(), ctx, live=True), config.TIMEOUTS["analyze"])
    except Exception as e:  # noqa: BLE001
        log.warning("analyze failed: %s", e)
        raise HTTPException(502, f"Gemini couldn't analyze that image: {e}")
    return AnalyzeOut(prosecutor=pro, defender=dfn, judge=jdg, image_hash=h)


def _framing(key: str) -> Framing:
    p = config.CACHE / "drafter.json"
    drf = DrafterOut.model_validate_json(p.read_text(encoding="utf-8")) if p.exists() else fixture("drafter", DrafterOut)
    return next((f for f in drf.framings if f.key == key), drf.framings[0])


@app.post("/api/voice", response_model=EditorOut)
async def voice(audio: UploadFile | None = File(None), text: str | None = Form(None),
                framing_key: str = Form("B"), es: bool = Form(True), source: str = Form("")):
    """Audio from the mic, or `text` typed by the Voiskey desktop app (source="voiskey")."""
    if audio is None and not (text and text.strip()):
        raise HTTPException(400, "Send audio or text")
    data, mime = (await _read_upload(audio, "audio")) if audio is not None else (None, None)
    claim = config.scenario()["claim"]
    try:
        return await asyncio.wait_for(
            editor.run(_framing(framing_key), claim, audio=data, mime=mime, text=text, want_es=es,
                       voiskey_clean=source == "voiskey"),
            config.TIMEOUTS["editor"])
    except Exception as e:  # noqa: BLE001
        log.warning("voice failed: %s", e)
        raise HTTPException(502, f"Couldn't process the voice note: {e}")


class BroadcastIn(BaseModel):
    framing_key: str
    post_en: str
    post_es: str | None = None


@app.post("/api/broadcast", response_model=BroadcastOut)
async def broadcast(body: BroadcastIn):
    replies = config.scenario().get("scripted_replies", [])
    out, _ = await get_or_run(f"broadcast_{body.framing_key}",
                              lambda: broadcaster.run(body.framing_key, body.post_en, body.post_es, replies),
                              BroadcastOut, config.TIMEOUTS["broadcast"], live=True, fixture_name="broadcast")
    return out


class AskIn(BaseModel):
    item: str
    ask_target: str


@app.post("/api/draft_ask", response_model=AskOut)
async def ask(body: AskIn):
    claim = config.scenario()["claim"]
    try:
        return await asyncio.wait_for(draft_ask.run(body.item, body.ask_target, claim), config.TIMEOUTS["draft_ask"])
    except Exception as e:  # noqa: BLE001
        log.warning("draft_ask failed: %s", e)
        return draft_ask.template(body.item, body.ask_target)
