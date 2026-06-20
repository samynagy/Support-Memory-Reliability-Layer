"""Assemble compact, evidence-linked context for a support rep."""
import json
from .db import conn


def _row_to_fact(row) -> dict:
    return {
        "fact_id": row["fact_id"],
        "predicate": row["predicate"],
        "value": json.loads(row["value"]),
        "confidence": row["confidence"],
        "status": row["status"],
        "sources": json.loads(row["source_event_ids"]),
    }


def get_context(entity_type: str, entity_id: str) -> dict:
    """Return the active belief set + historical losers + warnings + related entities."""
    with conn() as c:
        active = c.execute(
            """SELECT * FROM facts
               WHERE subject_type=? AND subject_id=? AND status='active'""",
            (entity_type, entity_id),
        ).fetchall()

        historical = c.execute(
            """SELECT * FROM facts
               WHERE subject_type=? AND subject_id=? AND status IN ('superseded','stale')""",
            (entity_type, entity_id),
        ).fetchall()

        warnings = c.execute(
            """SELECT kind, message, source_event_ids FROM warnings
               WHERE entity_id = ?""",
            (entity_id,),
        ).fetchall()

        related = []
        if entity_type == "account":
            rows = c.execute(
                """SELECT DISTINCT entity_id, entity_type FROM raw_events
                   WHERE entity_id != ? AND related_entity_ids LIKE ?""",
                (entity_id, f"%{entity_id}%"),
            ).fetchall()
            related = [{"id": r["entity_id"], "type": r["entity_type"]} for r in rows]

    return {
        "entity": {"type": entity_type, "id": entity_id},
        "active_facts": [_row_to_fact(r) for r in active],
        "historical_facts": [_row_to_fact(r) for r in historical],
        "warnings": [
            {
                "kind": w["kind"],
                "message": w["message"],
                "sources": json.loads(w["source_event_ids"]),
            }
            for w in warnings
        ],
        "related_entities": related,
    }


def explain_fact(fact_id: str) -> dict:
    """Show why the system believes a specific fact: the supporting raw events."""
    with conn() as c:
        f = c.execute("SELECT * FROM facts WHERE fact_id=?", (fact_id,)).fetchone()
        if not f:
            return {"error": "fact not found", "fact_id": fact_id}
        source_ids = json.loads(f["source_event_ids"])
        placeholders = ",".join("?" * len(source_ids))
        events = c.execute(
            f"SELECT * FROM raw_events WHERE event_id IN ({placeholders})",
            source_ids,
        ).fetchall()

    return {
        "fact": {
            "fact_id": f["fact_id"],
            "subject": {"type": f["subject_type"], "id": f["subject_id"]},
            "predicate": f["predicate"],
            "value": json.loads(f["value"]),
            "confidence": f["confidence"],
            "status": f["status"],
            "superseded_by": f["superseded_by"],
        },
        "supporting_events": [
            {
                "event_id": e["event_id"],
                "occurred_at": e["occurred_at"],
                "source": e["source"],
                "actor": e["actor"],
                "reliability": e["reliability"],
                "text": e["text"],
                "payload": json.loads(e["payload"]) if e["payload"] else {},
            }
            for e in events
        ],
        "explanation": (
            f"Belief '{f['predicate']}={json.loads(f['value'])}' for "
            f"{f['subject_type']}/{f['subject_id']} is supported by "
            f"{len(source_ids)} event(s). Confidence={f['confidence']}. "
            f"Status={f['status']}."
        ),
    }


def list_idempotency_conflicts() -> list[dict]:
    with conn() as c:
        rows = c.execute(
            "SELECT * FROM idempotency_conflicts ORDER BY id"
        ).fetchall()
    return [dict(r) for r in rows]


def list_warnings_for(entity_id: str) -> list[dict]:
    with conn() as c:
        rows = c.execute(
            "SELECT * FROM warnings WHERE entity_id = ?", (entity_id,)
        ).fetchall()
    return [dict(r) for r in rows]
