"""Deterministic fact extraction from raw event payloads."""
import json
import uuid
from .db import conn

# How much to trust the source of an event.
RELIABILITY_WEIGHT = {"high": 1.0, "medium": 0.6, "low": 0.3}

# How much to trust the channel an event came in on.
SOURCE_WEIGHT = {
    "contract": 1.0,
    "system": 0.9,
    "crm": 0.7,
    "email": 0.6,
    "chat": 0.5,
    "agent_note": 0.5,
}


def confidence(reliability: str, source: str) -> float:
    return round(
        RELIABILITY_WEIGHT.get(reliability, 0.3) * SOURCE_WEIGHT.get(source, 0.5),
        3,
    )


# Payload keys we promote into structured facts. The value goes through as-is.
PAYLOAD_RULES = {
    "plan":                "plan",
    "region":              "region",
    "p1_response_hours":   "p1_response_hours",
    "phone_escalation":    "phone_escalation",
    "preference":          "contact_preference",
    "affected_seats":      "affected_seats",
    "status":              "status",
    "priority":            "priority",
    "no_training":         "policy_no_training",
    "no_cross_account_analytics": "policy_no_cross_account_analytics",
    "scope_account_id":    "policy_scope_account_id",
    "standard_response":   "standard_response",
    "root_cause":          "root_cause",
    "symptom":             "symptom",
    "topic":               "topic",
    "account_name":        "account_name",
    "contact_name":        "contact_name",
}


def _wipe_facts():
    with conn() as c:
        c.execute("DELETE FROM facts")


def extract_facts() -> int:
    """Walk every raw event and emit derived facts. Idempotent: wipes existing facts first."""
    _wipe_facts()
    count = 0
    with conn() as c:
        events = c.execute("SELECT * FROM raw_events ORDER BY occurred_at").fetchall()
        for e in events:
            payload = json.loads(e["payload"]) if e["payload"] else {}
            for key, val in payload.items():
                predicate = PAYLOAD_RULES.get(key)
                if predicate is None:
                    continue
                fact_id = str(uuid.uuid4())
                c.execute(
                    """INSERT INTO facts
                       (fact_id, subject_type, subject_id, predicate, value,
                        confidence, status, source_event_ids)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (
                        fact_id,
                        e["entity_type"],
                        e["entity_id"],
                        predicate,
                        json.dumps(val),
                        confidence(e["reliability"], e["source"]),
                        "active",
                        json.dumps([e["event_id"]]),
                    ),
                )
                count += 1
    return count
