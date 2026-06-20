"""Tests for the deliberate landmines in the seed data.

Each test maps to one of the brief's starter questions:
- idempotency conflicts
- stale/superseded facts (Helios plan)
- WhatsApp -> email preference change for Mona
- 42 -> 48 affected seats correction
- identity ambiguity (shared phone)
- Nova policy must not leak to Delta
- every active fact must cite source events
"""
from pathlib import Path
import pytest

from src import db, ingest, facts, conflicts, context

SEED = Path(__file__).resolve().parent.parent / "seed_data.json"


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test.db"
    monkeypatch.setattr(db, "DB_PATH", test_db)
    db.reset()
    ingest.load_seed(SEED)
    facts.extract_facts()
    conflicts.run_all()
    yield


def test_idempotency_conflict_for_evt_1009_is_logged():
    confs = context.list_idempotency_conflicts()
    assert any(c["rejected_event_id"] == "evt-1009" for c in confs), \
        "evt-1009 reuses idem-1008 with a different body and must be rejected"


def test_evt_1008_same_body_retry_is_ignored_not_conflicted():
    # evt-1008 has the same idempotency key (idem-1008) used for its retry simulation.
    # Because evt-1008 ITSELF is the first event under idem-1008, it should be ingested
    # and only evt-1009 should be the conflict (different body, same key).
    with db.conn() as c:
        row = c.execute(
            "SELECT * FROM raw_events WHERE event_id='evt-1008'"
        ).fetchone()
    assert row is not None


def test_helios_plan_active_is_enterprise_and_starter_is_historical():
    ctx = context.get_context("account", "acct_helios_141")
    active_plans = [f for f in ctx["active_facts"] if f["predicate"] == "plan"]
    assert len(active_plans) == 1
    assert active_plans[0]["value"] == "Enterprise Support"

    historical_plans = [f for f in ctx["historical_facts"] if f["predicate"] == "plan"]
    starter_values = [h["value"] for h in historical_plans]
    assert "Starter" in starter_values


def test_old_starter_note_is_marked_stale_not_just_superseded():
    """evt-1018 is low reliability vs evt-1003 high reliability -> stale."""
    ctx = context.get_context("account", "acct_helios_141")
    stale = [
        f for f in ctx["historical_facts"]
        if f["predicate"] == "plan" and f["status"] == "stale"
    ]
    assert stale, "the low-reliability old Starter note must be stale"
    assert any("evt-1018" in s["sources"] for s in stale)


def test_mona_preference_updated_from_whatsapp_to_email_only():
    ctx = context.get_context("contact", "contact_mona_141")
    active_pref = [f for f in ctx["active_facts"] if f["predicate"] == "contact_preference"]
    assert len(active_pref) == 1
    assert active_pref[0]["value"] == "email_only_except_p1"

    historical_pref = [f for f in ctx["historical_facts"] if f["predicate"] == "contact_preference"]
    assert any(h["value"] == "WhatsApp" for h in historical_pref)


def test_affected_seats_correction_picks_48_over_42():
    ctx = context.get_context("ticket", "ticket_h_141_p1")
    seats = [f for f in ctx["active_facts"] if f["predicate"] == "affected_seats"]
    assert len(seats) == 1
    assert seats[0]["value"] == 48


def test_identity_ambiguity_warns_on_shared_phone():
    ctx_m = context.get_context("contact", "contact_m_salem_141")
    ctx_o = context.get_context("contact", "contact_omar_141")
    assert any(w["kind"] == "identity_ambiguous" for w in ctx_m["warnings"])
    assert any(w["kind"] == "identity_ambiguous" for w in ctx_o["warnings"])


def test_nova_policy_does_not_leak_to_delta():
    delta = context.get_context("account", "acct_delta_141")
    leaked = [
        f for f in delta["active_facts"]
        if f["predicate"].startswith("policy_")
    ]
    assert leaked == [], f"Delta must not inherit Nova policies, got {leaked}"

    assert any(
        w["kind"] == "policy_unverified" for w in delta["warnings"]
    ), "Delta's unverified policy guess must be flagged"


def test_nova_policy_facts_are_scoped_to_nova():
    nova_policy_ctx = context.get_context("policy", "policy_nova_141_privacy")
    scope = [
        f for f in nova_policy_ctx["active_facts"]
        if f["predicate"] == "policy_scope_account_id"
    ]
    assert scope and scope[0]["value"] == "acct_nova_141"


def test_every_active_fact_carries_at_least_one_source_event():
    for entity_type, entity_id in [
        ("account", "acct_helios_141"),
        ("contact", "contact_mona_141"),
        ("ticket", "ticket_h_141_p1"),
        ("account", "acct_nova_141"),
    ]:
        ctx = context.get_context(entity_type, entity_id)
        for f in ctx["active_facts"]:
            assert len(f["sources"]) >= 1, f"{entity_id} fact {f} has no source"


def test_explain_returns_supporting_events():
    ctx = context.get_context("account", "acct_helios_141")
    plan_fact = next(f for f in ctx["active_facts"] if f["predicate"] == "plan")
    exp = context.explain_fact(plan_fact["fact_id"])
    assert exp["fact"]["value"] == "Enterprise Support"
    assert exp["supporting_events"]
    assert any(e["event_id"] == "evt-1003" for e in exp["supporting_events"])


def test_helios_resolved_ticket_shows_root_cause():
    ctx = context.get_context("ticket", "ticket_h_141_p1")
    status_facts = [f for f in ctx["active_facts"] if f["predicate"] == "status"]
    assert any(s["value"] == "resolved" for s in status_facts)
    root_cause = [f for f in ctx["active_facts"] if f["predicate"] == "root_cause"]
    assert root_cause and root_cause[0]["value"] == "cache_invalidation"


def test_helios_context_lists_related_entities():
    ctx = context.get_context("account", "acct_helios_141")
    related_ids = {r["id"] for r in ctx["related_entities"]}
    assert "contact_mona_141" in related_ids
    assert "ticket_h_141_p1" in related_ids
