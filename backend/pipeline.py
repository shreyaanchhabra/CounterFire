"""Orchestrator. Runs agents in dependency order and pushes SSE events to a queue.

Each event carries sim_t, the sim minute it should appear at (plan 6.12 timeline).
The backend sends events as soon as results are ready. The frontend holds each one
until the map clock reaches its minute, and pauses the clock if a result is late.
"""
import asyncio
import json
import logging
import uuid

from . import config
from .agents import defender, drafter, judge, prosecutor, scout, society
from .agents._util import image_hash
from .cache import fixture, get_or_run
from .schemas import (DefenderOut, DrafterOut, EditorOut, Incident, JudgeOut, ProsecutorOut, SocietyAll)

log = logging.getLogger("firebreak.pipeline")

# agent -> (start minute, done minute). The frontend has the same table.
TIMELINE = {
    "scout": (0, 2), "prosecutor": (6, 12), "defender": (6, 12), "judge": (12, 15),
    "drafter": (15, 18), "society": (18, 22), "editor": (22, 23), "broadcaster": (24, 24),
}

RUNS: dict[str, asyncio.Queue] = {}


def velocity(posts: list[dict]) -> float:
    """Posts per minute over the last 5 minutes of the batch."""
    if not posts:
        return 0.0
    end = max(p["t"] for p in posts)
    recent = [p for p in posts if p["t"] > end - 5]
    return round(len(recent) / 5, 1)


def eval_suffix() -> str:
    p = config.CACHE / "eval.json"
    if not p.exists():
        return ""
    e = json.loads(p.read_text(encoding="utf-8"))
    return f" · eval {e['correct']}/{e['total']}"


def context_line(ctx: dict) -> str:
    return (f"Posted {ctx.get('post_time', 'unknown')} at {ctx.get('location', 'unknown')}. "
            f"{ctx.get('known_facts', '')}").strip()


def judge_targets(ctx: dict) -> list[str]:
    return [t for t in [ctx.get("poster")] + ctx.get("agencies", []) if t]


async def analyze(image: bytes, mime: str, claim: str, ctx: dict, live: bool):
    """Prosecutor + Defender in parallel, then Judge. Shared by the pipeline and /api/analyze."""
    h = image_hash(image)
    fx = (lambda n: n) if not live else (lambda n: None)  # never show scripted findings for a new image
    t = config.TIMEOUTS
    (pro, s1), (dfn, s2) = await asyncio.gather(
        get_or_run(f"prosecutor_{h}", lambda: prosecutor.run(image, mime, claim, ctx), ProsecutorOut,
                   t["prosecutor"], live=live, fixture_name=fx("prosecutor")),
        get_or_run(f"defender_{h}", lambda: defender.run(claim, context_line(ctx), image, mime), DefenderOut,
                   t["defender"], live=live, fixture_name=fx("defender")),
    )
    jdg, s3 = await get_or_run(f"judge_{h}", lambda: judge.run(claim, pro, dfn, judge_targets(ctx)), JudgeOut,
                               t["judge"], live=live, fixture_name=fx("judge"))
    return (pro, s1), (dfn, s2), (jdg, s3), h


async def _run(q: asyncio.Queue):
    sc = config.scenario()
    ctx = sc["context"]
    t = config.TIMEOUTS

    async def emit(agent, status, summary, payload):
        await q.put({"agent": agent, "status": status, "sim_t": TIMELINE[agent][1], "summary": summary,
                     "payload": payload.model_dump() if hasattr(payload, "model_dump") else payload})

    try:
        posts = sc["posts"] + sc.get("extra_posts", [])
        inc, st = await get_or_run("scout", lambda: scout.run(posts, sc["incident_id"]), Incident,
                                   t["scout"], fixture_name="scout")
        if st == "done":
            inc.velocity_per_min = velocity(posts)
        await emit("scout", st, f"{inc.post_count} posts → 1 incident", inc)

        image = (config.DATA / sc["image"]).read_bytes()
        (pro, s1), (dfn, s2), (jdg, s3), _ = await analyze(image, "image/png", inc.claim, ctx, live=False)
        await emit("prosecutor", s1, f"{len(pro.findings)} red flags in image", pro)
        await emit("defender", s2, f"{len(dfn.bullets)} supporting points", dfn)
        await emit("judge", s3, f"{jdg.verdict} · {jdg.confidence}% confident{eval_suffix()}", jdg)

        drf, st = await get_or_run("drafter", lambda: drafter.run(inc, jdg), DrafterOut, t["drafter"],
                                   fixture_name="drafter")
        await emit("drafter", st, f"{len(drf.framings)} framings · EN + ES", drf)

        soc, st = await get_or_run("society", lambda: society.run(drf.framings, inc.claim), SocietyAll,
                                   t["society"], fixture_name="society")
        await emit("society", st, f"20 personas × {len(soc.framings)} framings", soc)

        # The pipeline's editor step is the cached demo voice note. Live voice goes through /api/voice.
        # A recorded note saved to cache/editor_demo.json wins over the scripted fixture.
        p = config.CACHE / "editor_demo.json"
        ed = EditorOut.model_validate_json(p.read_text(encoding="utf-8")) if p.exists() else fixture("editor_demo", EditorOut)
        await emit("editor", "cached", f"{1 + bool(ed.post_es)} posts from voice", ed)

        await emit("broadcaster", "running", "Waiting for approval", {"replies": sc.get("scripted_replies", [])})
    except Exception as e:  # noqa: BLE001
        log.exception("pipeline failed")
        await q.put({"agent": "pipeline", "status": "error", "sim_t": 0, "summary": str(e), "payload": {}})
    finally:
        await q.put(None)


def start() -> str:
    run_id = uuid.uuid4().hex[:8]
    q: asyncio.Queue = asyncio.Queue()
    RUNS[run_id] = q
    asyncio.get_running_loop().create_task(_run(q))
    return run_id
