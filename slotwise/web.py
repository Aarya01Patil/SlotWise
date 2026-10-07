"""Synthetic demo server with explicit local and protected public configurations."""

import json
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from slotwise.agent import Agent
from slotwise.clinic import Clinic
from slotwise.domain import Session
from slotwise.evaluation import load_policy, run_loop
from slotwise.hosting import DemoBudget, Hosting
from slotwise.providers import live_settings, provider_for


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=2000)
    confirm_slot: str | None = Field(default=None, max_length=100)
    select_slot: str | None = Field(default=None, max_length=100)


class EvalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    repeats: int = Field(default=1, ge=1, le=3)


def create_app(root: Path | None = None, mode: str = "live"):
    if mode not in {"live", "offline"}:
        raise ValueError("Mode must be live or offline.")
    root = Path(root or ".slotwise")
    hosting = Hosting.from_env()
    budget = DemoBudget()
    realm = root / mode
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()
    clinic = Clinic(realm / f"chat-{today}.sqlite", today)
    provider_holder = []
    provider_lock = threading.Lock()

    @asynccontextmanager
    async def lifespan(app):
        yield
        if provider_holder and hasattr(provider_holder[0], "close"):
            provider_holder[0].close()

    app = FastAPI(
        title="SlotWise", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan
    )
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["localhost", "127.0.0.1"] + ([hosting.hostname] if hosting.public else []),
    )
    sessions: dict[str, tuple[Session, threading.Lock, float]] = {}
    registry_lock = threading.Lock()
    eval_lock = threading.Lock()
    job = {"status": "idle", "progress": "No evaluation running", "error": None}
    assets = Path(__file__).with_name("static")

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        if request.method not in {"GET", "HEAD"}:
            origin = request.headers.get("origin")
            source = urlsplit(origin) if origin else None
            if source and (
                source.scheme != ("https" if hosting.public else request.url.scheme)
                or source.netloc != request.headers.get("host")
            ):
                from fastapi.responses import JSONResponse

                return JSONResponse(
                    {"detail": "Cross-origin writes are not allowed."}, status_code=403
                )
            if hosting.public and request.url.path in {"/api/session", "/api/message"}:
                address = request.client.host if request.client else "unknown"
                if not budget.allow(address, request.url.path):
                    from fastapi.responses import JSONResponse

                    return JSONResponse(
                        {"detail": "Synthetic demo request limit reached. Please try later."},
                        status_code=429,
                        headers={"Retry-After": "60"},
                    )
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        if hosting.public:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    @app.get("/")
    def home():
        return FileResponse(assets / "index.html")

    @app.get("/healthz")
    def health():
        return {"status": "ok", "synthetic": True}

    @app.get("/api/config")
    def config():
        return {
            "mode": mode,
            "public_demo": hosting.public,
            "eval_requires_token": hosting.public,
            "eval_enabled": not hosting.public or bool(hosting.operator_token),
            **(
                live_settings()
                if mode == "live"
                else {
                    "ready": True,
                    "provider": "offline",
                    "provider_label": "Scripted",
                    "model": "scripted-test-double-v1",
                }
            ),
            "today": today,
            "timezone": "Asia/Kolkata",
            "policy": load_policy(realm).model_dump(),
        }

    @app.post("/api/session")
    def new_session(request: Request, response: Response):
        with registry_lock:
            expired = [key for key, value in sessions.items() if time.monotonic() - value[2] > 3600]
            for key in expired:
                sessions.pop(key)
            previous = request.cookies.get("slotwise_session")
            if previous:
                sessions.pop(previous, None)
            if len(sessions) >= 100:
                raise HTTPException(429, "Demo session limit reached. Try again later.")
            session = Session(
                patient_id="synthetic-" + uuid4().hex, today=today, policy=load_policy(realm)
            )
            session.messages.append(
                {
                    "role": "assistant",
                    "kind": "message",
                    "text": "Hi, I'm SlotWise. Which specialty, date, and time of day "
                    "would you prefer? Please use synthetic details only.",
                }
            )
            sessions[session.id] = (session, threading.Lock(), time.monotonic())
        response.set_cookie(
            "slotwise_session",
            session.id,
            httponly=True,
            samesite="strict",
            max_age=3600,
            secure=hosting.public,
        )
        return session.public()

    @app.post("/api/message")
    def message(body: Message, request: Request):
        key = request.cookies.get("slotwise_session", "")
        with registry_lock:
            entry = sessions.get(key)
            if not entry or time.monotonic() - entry[2] > 3600:
                sessions.pop(key, None)
                raise HTTPException(401, "Conversation expired. Start a new conversation.")
        if mode == "live" and not live_settings()["ready"]:
            raise HTTPException(
                503, f"API key missing. Add {live_settings()['key_name']} to .env and restart."
            )
        session, lock, _ = entry
        if not lock.acquire(blocking=False):
            raise HTTPException(409, "A reply is already in progress. Please wait.")
        try:
            try:
                with provider_lock:
                    if not provider_holder:
                        provider_holder.append(provider_for(mode))
                agent = Agent(clinic, provider_holder[0], session.policy)
                return agent.turn(session, body.text, body.confirm_slot, body.select_slot)
            except ValueError as error:
                # Do not expose SDK, credential, or database exception contents.
                if not body.text.strip():
                    raise HTTPException(422, "Message cannot be blank.") from error
                raise HTTPException(
                    503, "Scheduling provider unavailable. Check local configuration."
                ) from error
        finally:
            lock.release()

    @app.post("/api/evals")
    def start_eval(body: EvalRequest, request: Request):
        if not hosting.authorize_operator(request.headers.get("x-slotwise-operator", "")):
            raise HTTPException(403, "Evaluation runs require operator access.")
        if mode == "live" and not live_settings()["ready"]:
            raise HTTPException(
                503, f"API key missing. Add {live_settings()['key_name']} to .env and restart."
            )
        if not eval_lock.acquire(blocking=False):
            raise HTTPException(409, "An evaluation is already running.")
        job.update(status="running", progress="Starting evaluation", error=None)

        def worker():
            try:
                run_loop(
                    realm, mode, body.repeats, progress=lambda message: job.update(progress=message)
                )
                job.update(status="complete")
            except Exception:  # noqa: BLE001 - background job must release lock on any failure
                job.update(
                    status="failed",
                    error="Evaluation failed. Check local configuration or "
                    "provider quota. No fallback or successful promotion was fabricated.",
                )
            finally:
                eval_lock.release()

        threading.Thread(target=worker, daemon=True).start()
        return dict(job)

    @app.get("/api/evals")
    def evaluations():
        path = realm / "latest.json"
        if hosting.public and not path.exists():
            # Read-only captured evidence survives ephemeral service restarts.
            saved = Path(__file__).resolve().parent.parent / "examples" / f"{mode}-report.json"
            if saved.exists():
                path = saved
        return {
            "job": dict(job),
            "saved_evidence": path != realm / "latest.json",
            "report": json.loads(path.read_text(encoding="utf-8")) if path.exists() else None,
        }

    app.mount("/static", StaticFiles(directory=assets), name="static")
    return app
