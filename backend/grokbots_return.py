"""Callback-only receiver and durable, task-scoped Grokbots action inbox."""

import hashlib
import hmac
import json
import secrets
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from uuid import uuid4
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from backend.config import ROOT


class RoundTask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    episode_id: str = Field(min_length=1, max_length=120)
    round_id: int = Field(ge=0)
    group_id: int = Field(ge=0, le=5)
    observation: dict
    task_type: Literal["action", "community", "scout", "draft", "broadcast"] = "action"


class ActionPacket(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    request_id: str = Field(min_length=1, max_length=120)
    episode_id: str = Field(min_length=1, max_length=120)
    round_id: int = Field(ge=0)
    group_id: int = Field(ge=0, le=5)
    observation_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    action: Literal["share", "question", "verify", "reply", "retract", "wait"]
    belief: float = Field(ge=0, le=1)
    message: str | None = Field(max_length=280)
    reason: str = Field(min_length=1, max_length=500)


@dataclass(frozen=True)
class PendingJob:
    request_id: str
    observation_hash: str
    expires_at: float
    callback_token: str = field(repr=False)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def callback_observation(task: RoundTask, job: PendingJob, callback_base: str) -> dict:
    from backend.bot_contracts import result_schema
    origin = urlsplit(callback_base)
    if (origin.scheme != "https" or not origin.hostname or origin.username or origin.password
            or origin.query or origin.fragment or origin.path not in {"", "/"}):
        raise ValueError("Callback base must be an HTTPS origin without credentials, path, query, or fragment")
    return {"task": task.model_dump(mode="json"), "observation_hash": job.observation_hash,
            "callback": {"url": callback_base.rstrip("/") + "/api/results/" + job.request_id,
                         "token": job.callback_token}, "result_schema": result_schema(task.task_type).model_json_schema()}


class JobStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS jobs (
                request_id TEXT PRIMARY KEY, task TEXT NOT NULL, observation_hash TEXT NOT NULL,
                token_hash TEXT NOT NULL, expires_at REAL NOT NULL, status TEXT NOT NULL,
                result TEXT, completed_at REAL)""")
        self.path.chmod(0o600)

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def create(self, task: RoundTask, *, ttl: float = 600, now: float | None = None) -> PendingJob:
        if not 0 < ttl <= 3600:
            raise ValueError("Task TTL must be positive and at most one hour")
        encoded = canonical(task.model_dump(mode="json"))
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        token = secrets.token_urlsafe(32)
        job = PendingJob(str(uuid4()), digest, (time.time() if now is None else now) + ttl, token)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            # A new task replaces an unfinished task for the same episode/community.
            pending = connection.execute("SELECT request_id, task FROM jobs WHERE status='pending'").fetchall()
            for row in pending:
                previous = json.loads(row["task"])
                if (previous["episode_id"] == task.episode_id and previous["group_id"] == task.group_id
                        and previous.get("task_type", "action") == task.task_type):
                    connection.execute("UPDATE jobs SET status='superseded' WHERE request_id=?", (row["request_id"],))
            connection.execute("INSERT INTO jobs VALUES (?, ?, ?, ?, ?, 'pending', NULL, NULL)",
                (job.request_id, encoded, digest, hashlib.sha256(token.encode()).hexdigest(), job.expires_at))
        return job

    def get(self, request_id: str):
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE request_id=?", (request_id,)).fetchone()
        if row is None:
            return None
        # Never expose even the token hash through local result reads.
        return {"request_id": row["request_id"], "status": row["status"],
                "expires_at": row["expires_at"], "task": json.loads(row["task"]),
                "result": json.loads(row["result"]) if row["result"] else None}

    def authorize(self, request_id: str, token: str):
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE request_id=?", (request_id,)).fetchone()
        if row is None or not hmac.compare_digest(row["token_hash"], hashlib.sha256(token.encode()).hexdigest()):
            raise HTTPException(401, "Invalid task capability")
        return row

    def accept(self, request_id: str, token: str, packet: ActionPacket):
        # Authorization is checked again inside the transaction, avoiding stale acceptance.
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM jobs WHERE request_id=?", (request_id,)).fetchone()
            if row is None or not hmac.compare_digest(row["token_hash"], hashlib.sha256(token.encode()).hexdigest()):
                raise HTTPException(401, "Invalid task capability")
            if row["expires_at"] < time.time():
                raise HTTPException(410, "Task expired")
            if row["status"] not in {"pending", "completed"}:
                raise HTTPException(409, "Task was superseded")
            task = json.loads(row["task"])
            if (packet.request_id != request_id or packet.observation_hash != row["observation_hash"] or
                    any(getattr(packet, key) != task[key] for key in ("episode_id", "round_id", "group_id"))):
                raise HTTPException(409, "Result does not match the task observation")
            if task.get('task_type')=='community' and packet.payload.group_id!=packet.group_id:
                raise HTTPException(409,'Community payload does not match its task group')
            encoded = canonical(packet.model_dump(mode="json"))
            if row["status"] == "completed":
                if encoded != row["result"]:
                    raise HTTPException(409, "A different result already completed this task")
                return {"status": "completed", "request_id": request_id, "duplicate": True}
            connection.execute("UPDATE jobs SET status='completed', result=?, completed_at=? WHERE request_id=?",
                               (encoded, time.time(), request_id))
        return {"status": "completed", "request_id": request_id, "duplicate": False}


def create_app(store: JobStore) -> FastAPI:
    app = FastAPI(title="Firebreak task result receiver", docs_url=None, redoc_url=None,
                  openapi_url=None, redirect_slashes=False)

    @app.get('/api/tasks/{request_id}')
    def task(request_id: str, request: Request):
        from fastapi.responses import JSONResponse
        from backend.bot_contracts import result_schema
        auth=request.headers.get('authorization','')
        if not auth.startswith('Bearer '):raise HTTPException(401,'Task capability required')
        row=store.authorize(request_id,auth[7:])
        if row['expires_at'] < time.time():raise HTTPException(410,'Task expired')
        if row['status']!='pending':raise HTTPException(409,'Task is no longer pending')
        task=json.loads(row['task'])
        return JSONResponse({'request_id':request_id,'task':task,'observation_hash':row['observation_hash'],
                             'result_schema':result_schema(task.get('task_type','action')).model_json_schema()},
                            headers={'Cache-Control':'no-store'})

    @app.post("/api/results/{request_id}")
    async def receive(request_id: str, request: Request):
        from backend.bot_contracts import result_schema
        authorization = request.headers.get("authorization", "")
        if not authorization.startswith("Bearer "):
            raise HTTPException(401, "Task capability required")
        token = authorization[7:]
        row = store.authorize(request_id, token)
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 65536:
                raise HTTPException(413, "Result exceeds 64 KiB")
        try:
            kind = json.loads(row["task"]).get("task_type", "action")
            packet = result_schema(kind).model_validate_json(bytes(body))
        except ValidationError:
            # Pydantic's default error includes input values. Do not echo them publicly.
            raise HTTPException(422, "Result does not match the action schema") from None
        return store.accept(request_id, token, packet)

    return app


def app_factory():
    return create_app(JobStore(ROOT / "cache/grokbots/jobs.sqlite3"))
