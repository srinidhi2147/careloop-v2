import pytest

from careloop.models import AlertLevel, DoseStatus, PrescriptionItem, ValidationError

from .conftest import FakeText, make_service


def statuses(service):
    return {d.name: d.status for d in service.schedule()}


# ---------- schedule and voice replies ----------
def test_empty_schedule_has_friendly_speech(service):
    reply = service.get_medication_schedule()
    assert reply.ok
    assert reply.speech == "You have no medicines scheduled."
    assert reply.data["doses"] == []


def test_schedule_announces_next_dose_with_instructions(seeded):
    reply = seeded.get_medication_schedule()
    assert "4 left today" in reply.speech
    assert "Metformin 500 mg at 08:00" in reply.speech
    assert "after food" in reply.speech


def test_pending_only_false_returns_every_dose(seeded):
    seeded.confirm_dose()
    assert len(seeded.get_medication_schedule(pending_only=True).data["doses"]) == 3
    assert len(seeded.get_medication_schedule(pending_only=False).data["doses"]) == 4


# ---------- confirming and skipping ----------
def test_confirm_marks_earliest_pending_dose(seeded):
    reply = seeded.confirm_dose()
    assert reply.ok
    assert "Metformin 500 mg taken at 08:05" in reply.speech
    assert statuses(seeded)["Metformin"] == DoseStatus.TAKEN
    assert statuses(seeded)["Amlodipine"] == DoseStatus.PENDING


def test_confirm_by_name_is_case_insensitive_and_partial(seeded):
    assert seeded.confirm_dose("ATORVA").ok
    assert statuses(seeded)["Atorvastatin"] == DoseStatus.TAKEN
    assert statuses(seeded)["Metformin"] == DoseStatus.PENDING


def test_confirming_same_medicine_twice_reports_already_logged(seeded):
    seeded.confirm_dose("metformin")
    reply = seeded.confirm_dose("metformin")
    assert not reply.ok
    assert "already logged at 08:05" in reply.speech


def test_confirm_with_nothing_pending(service):
    reply = service.confirm_dose()
    assert not reply.ok
    assert "nothing pending" in reply.speech


def test_skip_marks_missed_and_alerts_caregiver(seeded):
    reply = seeded.skip_dose()
    assert reply.ok
    assert statuses(seeded)["Metformin"] == DoseStatus.MISSED
    alert = seeded.state()["alerts"][0]
    assert alert["level"] == AlertLevel.INFO
    assert "Metformin 500 mg was skipped" in alert["text"]


def test_skip_with_nothing_left(service):
    assert not service.skip_dose().ok


def test_doses_reset_each_day(seeded, clock):
    seeded.confirm_dose()
    assert statuses(seeded)["Metformin"] == DoseStatus.TAKEN
    clock.set("2026-10-11 07:00")
    assert statuses(seeded)["Metformin"] == DoseStatus.PENDING


# ---------- overdue rule ----------
def test_dose_is_not_overdue_inside_grace_period(seeded, clock):
    clock.set("2026-10-10 08:59")  # Metformin due 08:00, grace 60 minutes
    assert seeded.check_overdue() == 0


def test_dose_becomes_missed_after_grace_period(seeded, clock):
    clock.set("2026-10-10 09:01")
    assert seeded.check_overdue() == 1  # Metformin only; Amlodipine is due 09:00 plus grace
    assert statuses(seeded)["Metformin"] == DoseStatus.MISSED
    assert seeded.state()["alerts"][0]["level"] == AlertLevel.INFO


def test_second_missed_dose_is_urgent(seeded, clock):
    clock.set("2026-10-10 10:30")
    assert seeded.check_overdue() == 2
    levels = [a["level"] for a in seeded.state()["alerts"]]
    assert AlertLevel.URGENT in levels


def test_check_overdue_ignores_taken_doses(seeded, clock):
    seeded.confirm_dose()
    clock.set("2026-10-10 09:30")
    assert seeded.check_overdue() == 0


def test_check_overdue_is_idempotent(seeded, clock):
    clock.set("2026-10-10 09:01")
    seeded.check_overdue()
    assert seeded.check_overdue() == 0


# ---------- adding medicines ----------
def test_add_medication_appears_in_schedule(service):
    service.add_medication("Aspirin", "18:30", "75 mg", "with water")
    dose = service.schedule()[0]
    assert (dose.name, dose.strength, dose.time, dose.instructions) == ("Aspirin", "75 mg", "18:30", "with water")


@pytest.mark.parametrize("bad_time", ["25:00", "8:00", "08:60", "", "noon", "08:00 "])
def test_add_medication_rejects_bad_time(service, bad_time):
    with pytest.raises(ValidationError, match="HH:MM"):
        service.add_medication("Aspirin", bad_time)
    assert service.schedule() == []


def test_add_medication_requires_name(service):
    with pytest.raises(ValidationError, match="required"):
        service.add_medication("   ", "08:00")


def test_add_medication_limits_length(service):
    with pytest.raises(ValidationError, match="at most 100"):
        service.add_medication("x" * 101, "08:00")


def test_add_medication_trims_whitespace(service):
    service.add_medication("  Aspirin  ", "08:00")
    assert service.schedule()[0].name == "Aspirin"


# ---------- prescription saving ----------
def test_prescription_adds_one_dose_per_time(service):
    count = service.add_prescription([PrescriptionItem("Metformin", ["08:00", "21:00"], "500 mg")])
    assert count == 2
    assert [d.time for d in service.schedule()] == ["08:00", "21:00"]


def test_prescription_is_all_or_nothing(service):
    items = [PrescriptionItem("Good", ["08:00"]), PrescriptionItem("Bad", ["99:99"])]
    with pytest.raises(ValidationError):
        service.add_prescription(items)
    assert service.schedule() == []


def test_prescription_line_without_times_is_rejected(service):
    with pytest.raises(ValidationError, match="at least one dose time"):
        service.add_prescription([PrescriptionItem("Pantoprazole", [])])


# ---------- agenda and alerts ----------
def test_agenda_lists_recurring_items_in_time_order(seeded):
    reply = seeded.get_agenda()
    assert reply.speech.startswith("Today: 10:30 Video call with Dr. Rao")
    assert [a["time"] for a in reply.data["agenda"]] == ["10:30", "16:00"]


def test_dated_appointment_only_shows_on_its_day(service, clock):
    service.add_appointment("Eye test", "11:00", day="2026-10-11")
    assert service.get_agenda().data["agenda"] == []
    clock.set("2026-10-11 08:00")
    assert service.get_agenda().data["agenda"][0]["title"] == "Eye test"


def test_empty_agenda_speech(service):
    assert service.get_agenda().speech == "Nothing is planned today."


def test_help_request_raises_urgent_alert(service):
    reply = service.request_help()
    assert reply.ok
    alert = service.state()["alerts"][0]
    assert alert["level"] == AlertLevel.URGENT
    assert not alert["resolved"]


def test_notify_caregiver_levels_and_validation(service):
    service.notify_caregiver("Low on stock", urgent=False)
    assert service.state()["alerts"][0]["level"] == AlertLevel.INFO
    with pytest.raises(ValidationError):
        service.notify_caregiver("  ")


def test_resolving_an_alert(service):
    service.request_help()
    alert_id = service.state()["alerts"][0]["id"]
    service.resolve_alert(alert_id)
    assert service.state()["alerts"][0]["resolved"] is True


# ---------- state, version, summary, reset ----------
def test_state_counts_taken_doses(seeded):
    seeded.confirm_dose()
    state = seeded.state()
    assert (state["taken"], state["total"]) == (1, 4)


def test_version_increases_on_writes_only(seeded):
    start = seeded.version
    seeded.schedule()
    seeded.state()
    assert seeded.version == start
    seeded.confirm_dose()
    assert seeded.version > start


def test_template_summary_without_ai(seeded):
    seeded.confirm_dose()
    seeded.skip_dose()
    summary = seeded.summary()
    assert summary.source == "template"
    assert "1 of 4 doses taken" in summary.text
    assert "Missed: Amlodipine 5 mg" in summary.text


def test_summary_uses_ai_text_and_sends_facts(tmp_path, clock):
    fake = FakeText("Mom had a good day.")
    service = make_service(tmp_path, clock, text_generator=fake)
    service.seed_demo_data()
    service.confirm_dose()
    summary = service.summary()
    assert (summary.text, summary.source) == ("Mom had a good day.", "ai")
    assert "Doses taken: 1 of 4" in fake.prompts[0]


def test_summary_falls_back_when_ai_returns_nothing(tmp_path, clock):
    service = make_service(tmp_path, clock, text_generator=FakeText(None))
    service.seed_demo_data()
    assert service.summary().source == "template"


def test_reset_clears_logs_and_alerts_but_keeps_medicines(seeded):
    seeded.confirm_dose()
    seeded.request_help()
    seeded.reset_today()
    assert all(d.status == DoseStatus.PENDING for d in seeded.schedule())
    assert seeded.state()["alerts"] == []
    assert len(seeded.schedule()) == 4


def test_seeding_twice_does_not_duplicate(seeded):
    seeded.seed_demo_data()
    assert len(seeded.schedule()) == 4
