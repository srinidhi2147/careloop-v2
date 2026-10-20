import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("multipart")

from fastapi.testclient import TestClient  # noqa: E402

from careloop.ai import MockReader  # noqa: E402
from careloop.api import create_app  # noqa: E402
from careloop.config import Settings  # noqa: E402


class BrokenReader:
    def read(self, data, content_type):
        raise RuntimeError("model unavailable")


@pytest.fixture
def client(seeded):
    app = create_app(seeded, MockReader(), Settings(max_upload_bytes=100))
    return TestClient(app)


def test_health(client):
    assert client.get("/healthz").json()["status"] == "ok"


def test_state_lists_seeded_doses(client):
    body = client.get("/api/state").json()
    assert body["total"] == 4 and body["taken"] == 0


def test_voice_took_updates_state(client):
    reply = client.post("/api/voice/took").json()
    assert reply["ok"] is True
    assert client.get("/api/state").json()["taken"] == 1


def test_voice_help_creates_urgent_alert(client):
    client.post("/api/voice/help")
    assert client.get("/api/state").json()["alerts"][0]["level"] == "urgent"


def test_unknown_voice_intent_is_404(client):
    assert client.post("/api/voice/dance").status_code == 404


def test_add_medication_validates_time_format(client):
    bad = client.post("/api/medications", json={"name": "Aspirin", "time": "25:00"})
    assert bad.status_code == 422
    ok = client.post("/api/medications", json={"name": "Aspirin", "time": "18:00"})
    assert ok.status_code == 200


def test_prescription_upload_returns_review_lines(client):
    r = client.post("/api/prescription", files={"file": ("rx.png", b"x" * 10, "image/png")})
    names = [m["name"] for m in r.json()["medicines"]]
    assert names == ["Metformin", "Amlodipine", "Pantoprazole"]


def test_prescription_rejects_wrong_type(client):
    r = client.post("/api/prescription", files={"file": ("rx.txt", b"hello", "text/plain")})
    assert r.status_code == 400


def test_prescription_rejects_oversized_file(client):
    r = client.post("/api/prescription", files={"file": ("rx.png", b"x" * 101, "image/png")})
    assert r.status_code == 413


def test_prescription_reader_failure_is_503(seeded):
    app = create_app(seeded, BrokenReader(), Settings())
    r = TestClient(app).post("/api/prescription", files={"file": ("rx.png", b"x", "image/png")})
    assert r.status_code == 503


def test_prescription_confirm_saves_and_reports_bad_times(client):
    ok = client.post("/api/prescription/confirm", json=[{"name": "Test", "times": ["07:30"]}])
    assert ok.json() == {"added": 1}
    bad = client.post("/api/prescription/confirm", json=[{"name": "Test", "times": ["99:99"]}])
    assert bad.status_code == 400


def test_summary_endpoint(client):
    body = client.get("/api/summary").json()
    assert body["source"] == "template" and "doses taken" in body["summary"]
