"""SQLite schema and helpers for the support memory layer."""
import sqlite3
import json
import hashlib
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "memory.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_events (
    event_id            TEXT PRIMARY KEY,
    idempotency_key     TEXT NOT NULL,
    body_hash           TEXT NOT NULL,
    occurred_at         TEXT NOT NULL,
    source              TEXT NOT NULL,
    actor               TEXT,
    entity_type         TEXT NOT NULL,
    entity_id           TEXT NOT NULL,
    related_entity_ids  TEXT,
    reliability         TEXT NOT NULL,
    text                TEXT,
    payload             TEXT,
    ingested_at         TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS idempotency_log (
    idempotency_key TEXT PRIMARY KEY,
    body_hash       TEXT NOT NULL,
    first_event_id  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS idempotency_conflicts (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    idempotency_key     TEXT NOT NULL,
    existing_event_id   TEXT NOT NULL,
    rejected_event_id   TEXT NOT NULL,
    reason              TEXT NOT NULL,
    detected_at         TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS facts (
    fact_id             TEXT PRIMARY KEY,
    subject_type        TEXT NOT NULL,
    subject_id          TEXT NOT NULL,
    predicate           TEXT NOT NULL,
    value               TEXT NOT NULL,
    confidence          REAL NOT NULL,
    status              TEXT NOT NULL DEFAULT 'active',
    source_event_ids    TEXT NOT NULL,
    superseded_by       TEXT,
    created_at          TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_facts_subject
    ON facts(subject_type, subject_id, predicate);

CREATE TABLE IF NOT EXISTS warnings (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type         TEXT NOT NULL,
    entity_id           TEXT NOT NULL,
    kind                TEXT NOT NULL,
    message             TEXT NOT NULL,
    source_event_ids    TEXT NOT NULL,
    created_at          TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(entity_type, entity_id, kind, message)
);
"""


def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    return c


def init():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with conn() as c:
        c.executescript(SCHEMA)


def reset():
    """Drop all tables. Used by tests."""
    if DB_PATH.exists():
        DB_PATH.unlink()
    init()


def body_hash(event: dict) -> str:
    """Hash the meaningful body of an event so we can detect identical retries."""
    relevant = {
        "source": event.get("source"),
        "actor": event.get("actor"),
        "entity_type": event.get("entity_type"),
        "entity_id": event.get("entity_id"),
        "text": event.get("text"),
        "payload": event.get("payload"),
    }
    return hashlib.sha256(
        json.dumps(relevant, sort_keys=True, default=str).encode()
    ).hexdigest()
