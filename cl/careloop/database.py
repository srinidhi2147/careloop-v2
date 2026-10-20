"""SQLite access. One short-lived connection per operation keeps threads and async simple."""
from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

SCHEMA = """
CREATE TABLE IF NOT EXISTS medications(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  strength TEXT NOT NULL DEFAULT '',
  time TEXT NOT NULL,
  instructions TEXT NOT NULL DEFAULT '',
  active INTEGER NOT NULL DEFAULT 1);
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


class Database:
    def __init__(self, path: str) -> None:
        self.path = path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
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
