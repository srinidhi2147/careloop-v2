"""HTTP layer: REST + live events for the website, and the MCP endpoint for Alexa+."""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from . import __version__
from .ai import PrescriptionReader
from .config import Settings
from .models import PrescriptionItem, ValidationError
from .services import CareService

log = logging.getLogger("careloop.api")

INDEX = Path(__file__).parent / "static" / "index.html"
ALLOWED_UPLOADS = {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif", "application/pdf"}
TIME_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"
OVERDUE_CHECK_SECONDS = 30


class MedicationIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    time: str = Field(pattern=TIME_PATTERN)
    strength: str = Field("", max_length=50)
    instructions: str = Field("", max_length=200)
    days: int = Field(0, ge=0, le=365)  # 0 = no end date


class PrescriptionLineIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    times: list[str] = Field(default_factory=list, max_length=6)  # empty = service default time
    strength: str = Field("", max_length=50)
    instructions: str = Field("", max_length=200)
    days: int = Field(0, ge=0, le=365)  # 0 = no end date


class AppointmentIn(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    time: str = Field(pattern=TIME_PATTERN)


async def _watch_overdue(service: CareService) -> None:
    while True:
        await asyncio.sleep(60)
        try:
            service.check_overdue()
        except Exception:
            log.exception("overdue check failed")


def create_app(
    service: CareService,
    reader: PrescriptionReader,
    settings: Settings,
    mcp: Any = None,
) -> FastAPI:
    mcp_app = mcp.streamable_http_app() if mcp is not None else None  # must precede lifespan

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        async with contextlib.AsyncExitStack() as stack:
            if mcp is not None:
                await stack.enter_async_context(mcp.session_manager.run())
            task = asyncio.create_task(_watch_overdue(service)) if settings.auto_missed else None
            try:
                yield
            finally:
                if task:
                    task.cancel()

    app = FastAPI(title="CareLoop", version=__version__, lifespan=lifespan)

    @app.exception_handler(ValidationError)
    async def on_validation_error(_: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/")
    def home() -> FileResponse:
        return FileResponse(INDEX)

    @app.get("/api/state")
    def get_state() -> dict[str, Any]:
        return service.state()

    @app.get("/api/events")
    async def events() -> StreamingResponse:
        async def stream() -> AsyncIterator[str]:
            last = -1
            next_check = 0.0
            while True:
                # Runs inside this browser's own session, so each browser's doses are checked.
                if settings.auto_missed and time.monotonic() >= next_check:
                    next_check = time.monotonic() + OVERDUE_CHECK_SECONDS
                    try:
                        await asyncio.to_thread(service.check_overdue)
                    except Exception:
                        log.exception("overdue check failed")
                if service.version != last:
                    last = service.version
                    yield f"data: {json.dumps(service.state())}\n\n"
                await asyncio.sleep(1)

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache"})

    @app.post("/api/voice/{intent}")
    def voice(intent: str) -> dict[str, Any]:
        """Website simulation of what Alexa+ does through the MCP tools."""
        actions = {
            "schedule": service.get_medication_schedule, "took": service.confirm_dose,
            "skip": service.skip_dose, "agenda": service.get_agenda, "help": service.request_help,
        }
        if intent not in actions:
            raise HTTPException(404, "Unknown intent")
        return actions[intent]().to_dict()

    @app.post("/api/medications")
    def add_medication(body: MedicationIn) -> dict[str, Any]:
        return service.add_medication(
            body.name, body.time, body.strength, body.instructions, body.days
        ).to_dict()

    @app.post("/api/appointments")
    def add_appointment(body: AppointmentIn) -> dict[str, Any]:
        return service.add_appointment(body.title, body.time).to_dict()

    @app.post("/api/alerts/{alert_id}/resolve")
    def resolve_alert(alert_id: int) -> dict[str, bool]:
        service.resolve_alert(alert_id)
        return {"ok": True}

    @app.get("/api/summary")
    def get_summary() -> dict[str, str]:
        s = service.summary()
        return {"summary": s.text, "source": s.source}

    @app.post("/api/check-overdue")
    def check_overdue() -> dict[str, int]:
        return {"marked": service.check_overdue()}

    @app.post("/api/reset")
    def reset() -> dict[str, bool]:
        service.reset_today()
        return {"ok": True}

    @app.post("/api/prescription")
    async def read_prescription(file: UploadFile = File(...)) -> dict[str, Any]:
        content_type = file.content_type or ""
        if content_type not in ALLOWED_UPLOADS:
            raise HTTPException(400, "Upload a PNG, JPEG, WEBP or PDF file.")
        data = await file.read(settings.max_upload_bytes + 1)
        if len(data) > settings.max_upload_bytes:
            raise HTTPException(413, f"File is too large. The limit is {settings.max_upload_bytes // 1_000_000} MB.")
        try:
            medicines = await asyncio.to_thread(reader.read, data, content_type)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except Exception as exc:
            log.exception("prescription reading failed")
            raise HTTPException(503, f"Could not read the prescription: {exc}") from exc
        return {"medicines": [m.to_dict() for m in medicines]}

    @app.post("/api/prescription/confirm")
    def confirm_prescription(lines: list[PrescriptionLineIn]) -> dict[str, int]:
        items = [PrescriptionItem(ln.name, ln.times, ln.strength, ln.instructions, ln.days) for ln in lines]
        return {"added": service.add_prescription(items)}

    if mcp_app is not None:
        app.mount("/", mcp_app)  # last, so it only serves /mcp
    return app