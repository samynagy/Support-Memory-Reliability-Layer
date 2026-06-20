"""Idempotency-safe event ingestion."""
import json
from pathlib import Path
from .db import conn, body_hash


def ingest_event(e: dict) -> dict:
    """Insert one event. Returns a status dict describing what happened."""
    bh = body_hash(e)
    with conn() as c:
        existing = c.execute(
            "SELECT * FROM idempotency_log WHERE idempotency_key = ?",
            (e["idempotency_key"],),
        ).fetchone()

        if existing:
            if existing["body_hash"] == bh:
                return {
                    "status": "duplicate_ignored",
                    "event_id": e["event_id"],
                    "first_event_id": existing["first_event_id"],
                }
            c.execute(
                """INSERT INTO idempotency_conflicts
                   (idempotency_key, existing_event_id, rejected_event_id, reason)
                   VALUES (?,?,?,?)""",
                (
                    e["idempotency_key"],
                    existing["first_event_id"],
                    e["event_id"],
                    "same_key_different_body",
                ),
            )
            return {
                "status": "idempotency_conflict",
                "event_id": e["event_id"],
                "conflicts_with": existing["first_event_id"],
            }

        c.execute(
            """INSERT INTO raw_events
               (event_id, idempotency_key, body_hash, occurred_at, source, actor,
                entity_type, entity_id, related_entity_ids, reliability, text, payload)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                e["event_id"],
                e["idempotency_key"],
                bh,
                e["occurred_at"],
                e["source"],
                e.get("actor"),
                e["entity_type"],
                e["entity_id"],
                json.dumps(e.get("related_entity_ids", [])),
                e["reliability"],
                e.get("text"),
                json.dumps(e.get("payload", {})),
            ),
        )
        c.execute(
            "INSERT INTO idempotency_log(idempotency_key, body_hash, first_event_id) VALUES (?,?,?)",
            (e["idempotency_key"], bh, e["event_id"]),
        )

    return {"status": "ingested", "event_id": e["event_id"]}


def load_seed(path: str | Path = "seed_data.json") -> list[dict]:
    """Ingest every event in the seed file."""
    path = Path(path)
    if not path.is_absolute():
        path = Path(__file__).resolve().parent.parent / path
    with open(path, encoding="utf-8") as f:
        events = json.load(f)
    return [ingest_event(e) for e in events]
