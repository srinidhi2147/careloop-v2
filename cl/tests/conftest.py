from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from careloop.database import Database
from careloop.repositories import (
    AlertRepository,
    AppointmentRepository,
    DoseRepository,
    MedicationRepository,
)
from careloop.services import CareService

TZ = ZoneInfo("Asia/Kolkata")


class FakeClock:
    """A controllable clock so time-based rules are tested without sleeping."""

    def __init__(self, start: str = "2026-10-10 08:05") -> None:
        self.now = datetime.strptime(start, "%Y-%m-%d %H:%M").replace(tzinfo=TZ)

    def __call__(self) -> datetime:
        return self.now

    def set(self, value: str) -> None:
        self.now = datetime.strptime(value, "%Y-%m-%d %H:%M").replace(tzinfo=TZ)

    def advance(self, **kwargs: int) -> None:
        self.now += timedelta(**kwargs)


class FakeText:
    """Stands in for Bedrock text generation."""

    def __init__(self, reply: str | None) -> None:
        self.reply = reply
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str | None:
        self.prompts.append(prompt)
        return self.reply


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


def make_service(tmp_path, clock, text_generator=None, grace_minutes=60) -> CareService:
    db = Database(str(tmp_path / "test.db"))
    db.init_schema()
    return CareService(
        MedicationRepository(db), DoseRepository(db), AlertRepository(db), AppointmentRepository(db),
        clock=clock, grace_minutes=grace_minutes, text_generator=text_generator,
    )


@pytest.fixture
def service(tmp_path, clock) -> CareService:
    return make_service(tmp_path, clock)


@pytest.fixture
def seeded(service) -> CareService:
    service.seed_demo_data()
    return service
