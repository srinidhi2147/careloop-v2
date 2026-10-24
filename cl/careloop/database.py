"""SQLite access. One short-lived connection per operation keeps threads and async simple.

Each browser gets its own database file (see session.py), so visitors never see each other's data.
"""
from __future__ import annotations

import os
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

SCHEMA = """
CREATE TABLE IF NOT EXISTS medications(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  strength TEXT NOT NULL DEFAULT '',
  time TEXT NOT NULL,
  instructions TEXT NOT NULL DEFAULT '',
  active INTEGER NOT NULL DEFAULT 1,
  start_day TEXT NOT NULL DEFAULT '',
  days INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS dose_logs(
  med_id INTEGER NOT NULL REFERENCES medications(id),
  day TEXT NOT NULL,
  status TEXT NOT NULL,
  at TEXT NOT NULL,
  PRIMARY KEY(med_id, day));
CREATE TABLE IF NOT EXISTS appointments(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  day TEXT NOT NULL DEFAULT '',
  time TEXT NOT NULL,
  title TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS alerts(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  level TEXT NOT NULL,
  text TEXT NOT NULL,
  at TEXT NOT NULL,
  resolved INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS idx_medications_time ON medications(time);
"""

# Set per request by SessionMiddleware. None means "use the default database".
current_session: ContextVar[str | None] = ContextVar("current_session", default=None)
SESSION_ID_RE = re.compile(r"^[a-f0-9]{32}$")


def _migrate(conn: sqlite3.Connection) -> None:
    """Add columns that older database files do not have yet."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(medications)")}
    if "start_day" not in cols:
        conn.execute("ALTER TABLE medications ADD COLUMN start_day TEXT NOT NULL DEFAULT ''")
    if "days" not in cols:
        conn.execute("ALTER TABLE medications ADD COLUMN days INTEGER NOT NULL DEFAULT 0")
    conn.commit()


class Database:
    def __init__(self, path: str) -> None:
        self.path = path

    def _path_for_session(self) -> str:
        sid = current_session.get()
        if not sid or not SESSION_ID_RE.fullmatch(sid):
            return self.path
        folder = os.path.join(os.path.dirname(os.path.abspath(self.path)), "sessions")
        os.makedirs(folder, exist_ok=True)
        return os.path.join(folder, f"{sid}.db")

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        path = self._path_for_session()
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        if path != self.path:
            conn.executescript(SCHEMA)  # safe to repeat: every statement is IF NOT EXISTS
            _migrate(conn)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            _migrate(conn)