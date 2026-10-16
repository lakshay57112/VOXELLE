import sqlite3
from contextlib import contextmanager
from datetime import datetime

from .config import DB_PATH, TZ

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS schedule_items (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    medicine   TEXT NOT NULL,
    time       TEXT NOT NULL,              -- HH:MM, 24h, local time
    slot       TEXT NOT NULL,              -- subah | dopahar | shaam | raat
    food       TEXT NOT NULL DEFAULT 'any',-- before | after | any
    active     INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dose_events (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id          INTEGER,
    medicine         TEXT NOT NULL,
    slot             TEXT NOT NULL,
    food             TEXT NOT NULL DEFAULT 'any',
    due_date         TEXT NOT NULL,
    due_time         TEXT NOT NULL,
    status           TEXT NOT NULL,        -- due | snoozed | taken | missed | escalated
    remind_count     INTEGER NOT NULL DEFAULT 0,
    last_reminded_at TEXT,
    snooze_until     TEXT,
    responded_at     TEXT,
    last_reply       TEXT,
    missed_after_sec INTEGER,
    is_demo          INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL,
    UNIQUE (item_id, due_date, due_time)
);

CREATE TABLE IF NOT EXISTS push_subs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    role       TEXT NOT NULL,              -- parent | family
    endpoint   TEXT NOT NULL UNIQUE,
    sub_json   TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    kind       TEXT NOT NULL,              -- missed | symptom | confused
    message    TEXT NOT NULL,
    event_id   INTEGER,
    created_at TEXT NOT NULL,
    seen       INTEGER NOT NULL DEFAULT 0
);
"""


def now_iso(now: datetime | None = None) -> str:
    return (now or datetime.now(TZ)).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


@contextmanager
def db():
    con = connect()
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init_db() -> None:
    with db() as con:
        con.executescript(SCHEMA)


def get_setting(con: sqlite3.Connection, key: str, default: str = "") -> str:
    row = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row and row["value"] is not None else default


def set_setting(con: sqlite3.Connection, key: str, value: str) -> None:
    con.execute(
        "INSERT INTO settings(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
