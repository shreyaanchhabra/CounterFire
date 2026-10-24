"""Disk cache so the demo never depends on live API latency (plan Section 7).

get_or_run returns (output, status) where status is:
  "done"     ran live just now (and saved to cache)
  "cached"   loaded from cache/<key>.json
  "fallback" live call failed and there was no cache, so data/fixtures/<fixture>.json was used
"""
import asyncio
import json
import logging
import traceback

from pydantic import BaseModel

from . import config

log = logging.getLogger("firebreak.cache")


def _path(key):
    return config.CACHE / f"{key}.json"


def load(key, model: type[BaseModel]):
    return model.model_validate_json(_path(key).read_text(encoding="utf-8"))


def save(key, out: BaseModel):
    _path(key).write_text(out.model_dump_json(indent=2), encoding="utf-8")


def fixture(name, model: type[BaseModel]):
    return model.model_validate_json((config.FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


async def get_or_run(key, fn, model: type[BaseModel], timeout: float, *, live=False, fixture_name=None):
    """fn is an async callable returning `model`.

    live=True means this call is meant to be live even in hybrid mode
    (voice, analyze, broadcast, draft_ask). Pipeline calls use live=False.
    """
    mode = config.DEMO_MODE
    prefer_cache = mode == "replay" or (mode == "hybrid" and not live)
    if prefer_cache and _path(key).exists():
        return load(key, model), "cached"
    try:
        out = await asyncio.wait_for(fn(), timeout)
        save(key, out)
        return out, "done"
    except Exception as e:  # noqa: BLE001 - any failure falls back
        log.warning("%s failed live (%s: %s)", key, type(e).__name__, e)
        log.debug(traceback.format_exc())
        if _path(key).exists():
            return load(key, model), "cached"
        if fixture_name and (config.FIXTURES / f"{fixture_name}.json").exists():
            return fixture(fixture_name, model), "fallback"
        raise
