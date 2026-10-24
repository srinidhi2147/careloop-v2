"""Data access, one small class per table. All SQL lives here and nowhere else."""
from __future__ import annotations

from .database import Database
from .models import Alert, Appointment, Dose, DoseStatus


class MedicationRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def add(self, name: str, strength: str, time: str, instructions: str,
            start_day: str = "", days: int = 0) -> int:
        with self._db.connect() as conn:
            cur = conn.execute(
                "INSERT INTO medications(name, strength, time, instructions, start_day, days) "
                "VALUES(?,?,?,?,?,?)",
                (name, strength, time, instructions, start_day, days),
            )
            return int(cur.lastrowid or 0)

    def count(self) -> int:
        with self._db.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM medications").fetchone()[0])


class DoseRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def schedule_for(self, day: str) -> list[Dose]:
        """Doses for one day. A course with days > 0 runs from start_day for that many days."""
        sql = """SELECT m.id, m.name, m.strength, m.time, m.instructions,
                        COALESCE(l.status, ?) AS status, COALESCE(l.at, '') AS at,
                        m.days AS days,
                        CASE WHEN m.start_day = '' THEN 0
                             ELSE CAST(julianday(?) - julianday(m.start_day) AS INTEGER) + 1 END AS day_no
                 FROM medications m
                 LEFT JOIN dose_logs l ON l.med_id = m.id AND l.day = ?
                 WHERE m.active = 1
                   AND (m.start_day = '' OR m.start_day <= ?)
                   AND (m.days = 0 OR m.start_day = ''
                        OR date(m.start_day, '+' || m.days || ' days') > ?)
                 ORDER BY m.time, m.id"""
        with self._db.connect() as conn:
            rows = conn.execute(sql, (DoseStatus.PENDING, day, day, day, day)).fetchall()
        return [Dose(r["id"], r["name"], r["strength"], r["time"], r["instructions"],
                     r["status"], r["at"], r["days"], r["day_no"]) for r in rows]

    def log(self, med_id: int, day: str, status: str, at: str) -> None:
        with self._db.connect() as conn:
            conn.execute("INSERT OR REPLACE INTO dose_logs VALUES(?,?,?,?)", (med_id, day, status, at))

    def clear(self) -> None:
        with self._db.connect() as conn:
            conn.execute("DELETE FROM dose_logs")


class AlertRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def add(self, level: str, text: str, at: str) -> None:
        with self._db.connect() as conn:
            conn.execute("INSERT INTO alerts(level, text, at) VALUES(?,?,?)", (level, text, at))

    def recent(self, limit: int = 20) -> list[Alert]:
        with self._db.connect() as conn:
            rows = conn.execute("SELECT * FROM alerts ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [Alert(r["id"], r["level"], r["text"], r["at"], bool(r["resolved"])) for r in rows]

    def resolve(self, alert_id: int) -> None:
        with self._db.connect() as conn:
            conn.execute("UPDATE alerts SET resolved = 1 WHERE id = ?", (alert_id,))

    def clear(self) -> None:
        with self._db.connect() as conn:
            conn.execute("DELETE FROM alerts")


class AppointmentRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def add(self, title: str, time: str, day: str = "") -> None:
        with self._db.connect() as conn:
            conn.execute("INSERT INTO appointments(day, time, title) VALUES(?,?,?)", (day, time, title))

    def for_day(self, day: str) -> list[Appointment]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT id, time, title FROM appointments WHERE day IN (?, '') ORDER BY time", (day,)
            ).fetchall()
        return [Appointment(r["id"], r["time"], r["title"]) for r in rows]