"""Composition root: the only place that wires settings, database, service and app together."""
from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI

from .ai import build_ai
from .api import create_app
from .config import Settings
from .database import Database
from .mcp_tools import build_mcp
from .repositories import (
    AlertRepository,
    AppointmentRepository,
    DoseRepository,
    MedicationRepository,
)
from .services import CareService
from .session import SessionMiddleware


def create(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    db = Database(settings.db_path)
    db.init_schema()
    reader, generator = build_ai(settings)
    tz = ZoneInfo(settings.timezone)
    service = CareService(
        MedicationRepository(db), DoseRepository(db), AlertRepository(db), AppointmentRepository(db),
        clock=lambda: datetime.now(tz),
        grace_minutes=settings.grace_minutes,
        text_generator=generator,
    )
    if settings.seed_demo:
        service.seed_demo_data()
    app = create_app(service, reader, settings, mcp=build_mcp(service, settings))
    app.add_middleware(SessionMiddleware)
    return app