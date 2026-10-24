"""CareService: every business rule lives here. The MCP tools, REST API and website all call it."""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Any, Protocol

from .database import current_session
from .frequency import TIME_RE
from .models import (
    AlertLevel,
    Dose,
    DoseStatus,
    PrescriptionItem,
    Reply,
    Summary,
    ValidationError,
)
from .repositories import (
    AlertRepository,
    AppointmentRepository,
    DoseRepository,
    MedicationRepository,
)

log = logging.getLogger("careloop.service")

Clock = Callable[[], datetime]

# Used when a prescription line has no readable frequency (for example "cough syrup").
DEFAULT_DOSE_TIME = "08:00"
# Minutes after the due time before we say "you have not taken this tablet".
REMIND_AFTER_MINUTES = 15


class TextGenerator(Protocol):
    def generate(self, prompt: str) -> str | None: ...


def _clean(value: str | None, field: str, max_len: int, required: bool = False) -> str:
    text = (value or "").strip()
    if required and not text:
        raise ValidationError(f"{field} is required.")
    if len(text) > max_len:
        raise ValidationError(f"{field} must be at most {max_len} characters.")
    return text


def _check_time(value: str | None) -> str:
    if not TIME_RE.fullmatch(value or ""):
        raise ValidationError("Time must be HH:MM in 24-hour format.")
    return str(value)


class CareService:
    def __init__(
        self,
        medications: MedicationRepository,
        doses: DoseRepository,
        alerts: AlertRepository,
        appointments: AppointmentRepository,
        clock: Clock,
        grace_minutes: int = 60,
        text_generator: TextGenerator | None = None,
    ) -> None:
        self._meds = medications
        self._doses = doses
        self._alerts = alerts
        self._appts = appointments
        self._clock = clock
        self._grace = grace_minutes
        self._remind_after = min(REMIND_AFTER_MINUTES, grace_minutes)
        self._text = text_generator
        self._version = 0
        # (browser session, dose id, day) already reminded, so each dose is reminded once a day
        self._reminded: set[tuple[str | None, int, str]] = set()

    # ----- change tracking (drives the live dashboard) -----
    @property
    def version(self) -> int:
        return self._version

    def _touch(self) -> None:
        self._version += 1

    def _day(self) -> str:
        return self._clock().date().isoformat()

    def _hm(self) -> str:
        return self._clock().strftime("%H:%M")

    # ----- medicines -----
    def schedule(self) -> list[Dose]:
        return self._doses.schedule_for(self._day())

    def add_medication(self, name: str, time: str, strength: str = "", instructions: str = "") -> Reply:
        clean = (
            _clean(name, "Medicine name", 100, required=True),
            _check_time(time),
            _clean(strength, "Strength", 50),
            _clean(instructions, "Instructions", 200),
        )
        self._meds.add(clean[0], clean[2], clean[1], clean[3])
        self._touch()
        log.info("medication added: %s at %s", clean[0], clean[1])
        return Reply(True, f"Added {clean[0]} at {clean[1]}.")

    def add_prescription(self, items: list[PrescriptionItem]) -> int:
        """Validate every line first so a bad line never leaves a half-saved prescription.
        A dose already in the care plan (same medicine and time) is skipped, so saving twice
        does not create duplicates. A line with no times is scheduled once a day at DEFAULT_DOSE_TIME."""
        existing = {(d.name.strip().lower(), d.time) for d in self.schedule()}
        rows: list[tuple[str, str, str, str]] = []
        for item in items:
            name = _clean(item.name, "Medicine name", 100, required=True)
            strength = _clean(item.strength, "Strength", 50)
            notes = _clean(item.instructions, "Instructions", 200)
            for t in (item.times or [DEFAULT_DOSE_TIME]):
                time = _check_time(t)
                key = (name.lower(), time)
                if key in existing:
                    continue
                existing.add(key)
                rows.append((name, strength, time, notes))
        for name, strength, time, notes in rows:
            self._meds.add(name, strength, time, notes)
        if rows:
            self._touch()
        log.info("prescription saved: %d new dose times", len(rows))
        return len(rows)

    # ----- doses -----
    def _next_pending(self, name: str = "") -> Dose | None:
        pending = [d for d in self.schedule() if d.status == DoseStatus.PENDING]
        if name.strip():
            needle = name.lower().strip()
            pending = [d for d in pending if needle in d.name.lower()]
        return pending[0] if pending else None

    def _record(self, dose: Dose, status: str) -> None:
        self._doses.log(dose.id, self._day(), status, self._hm())
        self._resolve_reminders(dose)
        self._touch()

    def _resolve_reminders(self, dose: Dose) -> None:
        """Once a dose is taken, skipped or missed, its 'not taken yet' reminder is done."""
        for alert in self._alerts.recent(50):
            if alert.level == AlertLevel.REMINDER and not alert.resolved and dose.label in alert.text:
                self._alerts.resolve(alert.id)

    def _due_at(self, dose: Dose) -> datetime:
        hour, minute = (int(p) for p in dose.time.split(":"))
        return self._clock().replace(hour=hour, minute=minute, second=0, microsecond=0)

    def _is_late(self, dose: Dose) -> bool:
        """True when the dose is past its grace period and still not confirmed."""
        return self._clock() > self._due_at(dose) + timedelta(minutes=self._grace)

    def get_medication_schedule(self, pending_only: bool = True) -> Reply:
        doses = self.schedule()
        pending = [d for d in doses if d.status == DoseStatus.PENDING]
        late = [d for d in pending if self._is_late(d)]
        upcoming = [d for d in pending if not self._is_late(d)]
        if not doses:
            speech = "You have no medicines scheduled."
        elif not pending:
            speech = "You have taken everything for today."
        else:
            parts: list[str] = []
            if late:
                said = f"You missed {late[0].label} at {late[0].time}"
                if len(late) > 1:
                    said += f" and {len(late) - 1} more"
                parts.append(said + ". Please check with your caregiver before taking late doses.")
            if upcoming:
                nxt = upcoming[0]
                text = f"You have {len(upcoming)} left today. Next is {nxt.label} at {nxt.time}."
                if nxt.instructions:
                    text += f" Remember: {nxt.instructions}."
                parts.append(text)
            else:
                parts.append("No more doses are due today.")
            speech = " ".join(parts)
        shown = pending if pending_only else doses
        return Reply(True, speech, {"doses": [d.to_dict() for d in shown]})

    def confirm_dose(self, name: str = "") -> Reply:
        dose = self._next_pending(name)
        if dose is None:
            done = [
                d for d in self.schedule()
                if d.status == DoseStatus.TAKEN and name.strip() and name.lower() in d.name.lower()
            ]
            if done:
                return Reply(False, f"{done[0].label} is already logged at {done[0].at}.")
            return Reply(False, "There is nothing pending to confirm.")
        self._record(dose, DoseStatus.TAKEN)
        log.info("dose taken: %s", dose.name)
        return Reply(True, f"Noted. {dose.label} taken at {self._hm()}.", {"dose": dose.name})

    def skip_dose(self, name: str = "") -> Reply:
        dose = self._next_pending(name)
        if dose is None:
            return Reply(False, "There is nothing left to skip.")
        self._record(dose, DoseStatus.MISSED)
        self._add_alert(AlertLevel.INFO, f"{dose.label} was skipped.")
        return Reply(True, f"Okay. I have told your caregiver about {dose.label}.", {"dose": dose.name})

    def _remind(self, dose: Dose) -> None:
        key = (current_session.get(), dose.id, self._day())
        if key in self._reminded:
            return
        self._reminded.add(key)
        food = dose.instructions.strip().lower()
        tail = f" Take it {food}." if food.startswith(("before", "after", "with")) else ""
        self._add_alert(
            AlertLevel.REMINDER,
            f'You have not taken {dose.label} yet.{tail} Please take it and tap "I took it".',
        )

    def check_overdue(self) -> int:
        """Remind about doses that are late, and mark doses past the grace period as missed.
        The second miss of a day is urgent."""
        now = self._clock()
        marked = 0
        for dose in self.schedule():
            if dose.status != DoseStatus.PENDING:
                continue
            due = self._due_at(dose)
            if now > due + timedelta(minutes=self._grace):
                self._record(dose, DoseStatus.MISSED)
                missed = sum(1 for d in self.schedule() if d.status == DoseStatus.MISSED)
                level = AlertLevel.URGENT if missed >= 2 else AlertLevel.INFO
                self._add_alert(level, f"{dose.label} due at {dose.time} was not confirmed.")
                marked += 1
            elif now > due + timedelta(minutes=self._remind_after):
                self._remind(dose)
        return marked

    # ----- agenda -----
    def get_agenda(self) -> Reply:
        items = self._appts.for_day(self._day())
        if items:
            speech = "Today: " + ". Then ".join(f"{a.time} {a.title}" for a in items) + "."
        else:
            speech = "Nothing is planned today."
        return Reply(True, speech, {"agenda": [asdict(a) for a in items]})

    def add_appointment(self, title: str, time: str, day: str = "") -> Reply:
        self._appts.add(_clean(title, "Title", 100, required=True), _check_time(time), day)
        self._touch()
        return Reply(True, "Appointment added.")

    # ----- alerts -----
    def _add_alert(self, level: str, text: str) -> None:
        self._alerts.add(level, text, self._hm())
        self._touch()
        log.info("alert (%s): %s", level, text)

    def notify_caregiver(self, message: str, urgent: bool = True) -> Reply:
        text = _clean(message, "Message", 300, required=True)
        self._add_alert(AlertLevel.URGENT if urgent else AlertLevel.INFO, text)
        return Reply(True, "I have told your caregiver.")

    def request_help(self) -> Reply:
        self._add_alert(AlertLevel.URGENT, "Help requested by voice. Please call now.")
        return Reply(True, "I have alerted your family right now. Stay where you are.")

    def resolve_alert(self, alert_id: int) -> None:
        self._alerts.resolve(alert_id)
        self._touch()

    # ----- views -----
    def state(self) -> dict[str, Any]:
        doses = self.schedule()
        return {
            "doses": [d.to_dict() for d in doses],
            "alerts": [asdict(a) for a in self._alerts.recent()],
            "agenda": [asdict(a) for a in self._appts.for_day(self._day())],
            "taken": sum(1 for d in doses if d.status == DoseStatus.TAKEN),
            "total": len(doses),
        }

    def summary(self) -> Summary:
        doses = self.schedule()
        taken = [d for d in doses if d.status == DoseStatus.TAKEN]
        missed = [d.label for d in doses if d.status == DoseStatus.MISSED]
        pending = [d for d in doses if d.status == DoseStatus.PENDING]
        urgent = [a for a in self._alerts.recent(50) if a.level == AlertLevel.URGENT]
        facts = (
            f"Doses taken: {len(taken)} of {len(doses)}. Missed: {', '.join(missed) or 'none'}. "
            f"Still pending: {len(pending)}. Urgent help requests: {len(urgent)}."
        )
        if self._text is not None:
            text = self._text.generate(
                "Write 2 or 3 calm, plain sentences for a family caregiver summarising an elder's "
                "medicine day. Do not give medical advice. Facts: " + facts
            )
            if text:
                return Summary(text, "ai")
        text = f"{len(taken)} of {len(doses)} doses taken."
        if missed:
            text += f" Missed: {', '.join(missed)}."
        if pending:
            text += f" {len(pending)} still pending."
        if urgent:
            text += f" Help was requested {len(urgent)} time(s). Worth a call."
        if not missed and not urgent and taken:
            text += " No concerns so far."
        return Summary(text, "template")

    # ----- admin -----
    def reset_today(self) -> None:
        self._doses.clear()
        self._alerts.clear()
        self._reminded.clear()
        self._touch()

    def seed_demo_data(self) -> None:
        if self._meds.count() > 0:
            return
        for name, strength, time, notes in [
            ("Metformin", "500 mg", "08:00", "after food"),
            ("Amlodipine", "5 mg", "09:00", ""),
            ("Vitamin D", "", "13:00", "with lunch"),
            ("Atorvastatin", "10 mg", "21:00", "after dinner"),
        ]:
            self._meds.add(name, strength, time, notes)
        self._appts.add("Video call with Dr. Rao", "10:30")
        self._appts.add("Walk in the garden", "16:00")
        self._touch()