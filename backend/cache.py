"""Content-addressed, validated disk cache with bounded generation time."""

import hashlib
import json
import os
import tempfile
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from typing import Callable

from pydantic import BaseModel, ValidationError

from backend.schemas import AgentResult, T


class CacheMiss(RuntimeError):
    pass


def _bounded(fn, timeout):
    # A timed-out worker cannot write the cache. Network clients also set timeouts.
    result = Queue(maxsize=1)
    def work():
        try:
            result.put((True, fn()))
        except Exception as exc:
            result.put((False, exc))
    Thread(target=work, daemon=True).start()
    try:
        ok, value = result.get(timeout=timeout)
    except Empty:
        raise TimeoutError("Agent exceeded its time budget") from None
    if not ok:
        raise value
    return value


class DiskCache:
    def __init__(self, directory: Path | str = "cache", timeout: float = 8):
        if timeout <= 0:
            raise ValueError("Timeout must be positive")
        self.directory = Path(directory)
        self.timeout = timeout

    def get_or_run(self, agent: str, inputs: dict, schema: type[T], fn: Callable[[], T],
                   *, mode: str = "hybrid", prefer_cache: bool = True) -> AgentResult[T]:
        if mode not in {"live", "replay", "hybrid"}:
            raise ValueError("Mode must be live, replay, or hybrid")
        identity = {"agent": agent, "inputs": inputs, "schema": schema.model_json_schema()}
        encoded = json.dumps(identity, sort_keys=True, ensure_ascii=False, allow_nan=False)
        key = hashlib.sha256(encoded.encode()).hexdigest()
        path = self.directory / f"{agent}_{key}.json"
        cached = None
        try:
            cached = schema.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValidationError):
            pass
        if mode == "replay" or (mode == "hybrid" and prefer_cache and cached is not None):
            if cached is None:
                raise CacheMiss(f"No valid cached {agent} result for these inputs")
            return AgentResult(payload=cached, status="cached")
        try:
            def generate():
                out = fn()
                return schema.model_validate(out.model_dump() if isinstance(out, BaseModel) else out)
            payload = _bounded(generate, self.timeout)
        except Exception:
            if cached is not None:
                return AgentResult(payload=cached, status="cached")
            raise
        self.directory.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".pending-", dir=self.directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload.model_dump_json(indent=2))
            os.replace(name, path)
        finally:
            if os.path.exists(name):
                os.unlink(name)
        return AgentResult(payload=payload, status="done")
