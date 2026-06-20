"""Detect supersession, duplicates, identity ambiguity, and unverified policies."""
import json
from .db import conn


def _wipe_warnings():
    with conn() as c:
        c.execute("DELETE FROM warnings")


def resolve_supersessions() -> int:
    """Where multiple facts cover the same (subject, predicate) with different values,
    pick the highest-confidence/most-recent as winner and mark losers superseded or stale."""
    changes = 0
    with conn() as c:
        groups = c.execute(
            """SELECT subject_type, subject_id, predicate
               FROM facts WHERE status='active'
               GROUP BY subject_type, subject_id, predicate
               HAVING COUNT(*) > 1"""
        ).fetchall()

        for g in groups:
            facts = c.execute(
                """SELECT f.fact_id, f.value, f.confidence,
                          e.occurred_at, e.reliability
                   FROM facts f
                   JOIN raw_events e
                     ON e.event_id = json_extract(f.source_event_ids,'$[0]')
                   WHERE f.subject_type=? AND f.subject_id=? AND f.predicate=?
                   ORDER BY e.occurred_at DESC""",
                (g["subject_type"], g["subject_id"], g["predicate"]),
            ).fetchall()

            distinct_values = {f["value"] for f in facts}
            if len(distinct_values) <= 1:
                # All agree, no conflict. Collapse into a single "active" fact set.
                continue

            winner = max(
                facts, key=lambda f: (f["confidence"], f["occurred_at"])
            )
            for f in facts:
                if f["fact_id"] == winner["fact_id"]:
                    continue
                # Low reliability fact overruled by high reliability fact = stale.
                if f["reliability"] == "low" and winner["reliability"] == "high":
                    new_status = "stale"
                else:
                    new_status = "superseded"
                c.execute(
                    "UPDATE facts SET status=?, superseded_by=? WHERE fact_id=?",
                    (new_status, winner["fact_id"], f["fact_id"]),
                )
                changes += 1
    return changes


def detect_duplicates() -> int:
    """Surface events that flag themselves as retries or possible duplicates."""
    added = 0
    with conn() as c:
        rows = c.execute(
            """SELECT event_id, entity_type, entity_id, payload
               FROM raw_events
               WHERE json_extract(payload,'$.possible_duplicate_of') IS NOT NULL
                  OR json_extract(payload,'$.retry_of') IS NOT NULL"""
        ).fetchall()
        for r in rows:
            p = json.loads(r["payload"])
            ref = p.get("possible_duplicate_of") or p.get("retry_of")
            msg = f"Event {r['event_id']} flagged as duplicate of {ref}"
            try:
                c.execute(
                    """INSERT INTO warnings
                       (entity_type, entity_id, kind, message, source_event_ids)
                       VALUES (?,?,?,?,?)""",
                    (
                        r["entity_type"],
                        r["entity_id"],
                        "duplicate_suspect",
                        msg,
                        json.dumps([r["event_id"], ref]),
                    ),
                )
                added += 1
            except Exception:
                pass  # UNIQUE constraint, already warned
    return added


def detect_identity_ambiguity() -> int:
    """Different contact entities sharing the same phone are an identity warning."""
    added = 0
    with conn() as c:
        rows = c.execute(
            """SELECT event_id, entity_id, payload FROM raw_events
               WHERE entity_type='contact'
                 AND json_extract(payload,'$.phone') IS NOT NULL"""
        ).fetchall()
        by_phone: dict[str, list] = {}
        for e in rows:
            phone = json.loads(e["payload"]).get("phone")
            if not phone:
                continue
            by_phone.setdefault(phone, []).append(e)

        for phone, evs in by_phone.items():
            entity_ids = sorted({e["entity_id"] for e in evs})
            if len(entity_ids) <= 1:
                continue
            msg = (
                f"Shared phone {phone} across distinct contact entities "
                f"{entity_ids}. Do not merge without human review."
            )
            source_event_ids = [e["event_id"] for e in evs]
            for eid in entity_ids:
                try:
                    c.execute(
                        """INSERT INTO warnings
                           (entity_type, entity_id, kind, message, source_event_ids)
                           VALUES (?,?,?,?,?)""",
                        (
                            "contact",
                            eid,
                            "identity_ambiguous",
                            msg,
                            json.dumps(source_event_ids),
                        ),
                    )
                    added += 1
                except Exception:
                    pass
    return added


def detect_unverified_policies() -> int:
    """Flag policy guesses that lack a contract source as unsafe to enforce."""
    added = 0
    with conn() as c:
        rows = c.execute(
            """SELECT event_id, entity_type, entity_id, text
               FROM raw_events
               WHERE json_extract(payload,'$.unverified_policy_guess') = 1
                  OR json_extract(payload,'$.policy_hint') IS NOT NULL"""
        ).fetchall()
        for r in rows:
            try:
                c.execute(
                    """INSERT INTO warnings
                       (entity_type, entity_id, kind, message, source_event_ids)
                       VALUES (?,?,?,?,?)""",
                    (
                        r["entity_type"],
                        r["entity_id"],
                        "policy_unverified",
                        f"Policy claim without contract evidence: {r['text']}",
                        json.dumps([r["event_id"]]),
                    ),
                )
                added += 1
            except Exception:
                pass
    return added


def run_all() -> dict:
    _wipe_warnings()
    return {
        "supersessions": resolve_supersessions(),
        "duplicates": detect_duplicates(),
        "identity_warnings": detect_identity_ambiguity(),
        "policy_warnings": detect_unverified_policies(),
    }
