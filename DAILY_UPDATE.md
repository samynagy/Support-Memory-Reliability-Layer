# Daily update — 2026-06-20

**Branch:** `main`
**Repo:** support-memory

## Shipped

- Project scaffolding: `src/`, `tests/`, `samples/`, `scripts/`.
- `src/db.py` — SQLite schema: `raw_events`, `idempotency_log`,
  `idempotency_conflicts`, `facts`, `warnings`. Index on
  `(subject_type, subject_id, predicate)`.
- `src/ingest.py` — idempotency-safe ingestion. `(key, body_hash)`
  decides ignore / accept / conflict. Catches the `evt-1009` retry-bug
  landmine.
- `src/facts.py` — deterministic payload-rule extractor with the
  confidence formula `RELIABILITY × SOURCE_WEIGHT`.
- `src/conflicts.py` — four detectors:
  - `resolve_supersessions` (Helios plan Starter→Enterprise, stale low-reliability note)
  - `detect_duplicates` (events that flag themselves as retries)
  - `detect_identity_ambiguity` (shared phone across contacts)
  - `detect_unverified_policies` (Delta guess, Nova policy hint)
- `src/context.py` — `get_context`, `explain_fact`,
  `list_idempotency_conflicts`. Every active fact carries `sources`.
- `src/main.py` — FastAPI app:
  `POST /load-seed`, `GET /context/{type}/{id}`, `GET /explain/{fact_id}`,
  `GET /idempotency-conflicts`, `GET /health`.
- `tests/test_landmines.py` — 13 tests, one per landmine + one each for
  citations, explain, related entities, root cause.
- `scripts/generate_samples.py` — regenerates the JSON outputs in `samples/`.
- Docs: `README.md`, `ARCHITECTURE.md`, this update, `NEXT.md`.

## Tests

```
pytest -v
13 passed in 2.56s
```

Covered:

| Test | Landmine |
|---|---|
| `test_idempotency_conflict_for_evt_1009_is_logged` | evt-1009 reuses idem-1008 with a different body |
| `test_evt_1008_same_body_retry_is_ignored_not_conflicted` | evt-1008 is the first event under that key |
| `test_helios_plan_active_is_enterprise_and_starter_is_historical` | Starter → Enterprise supersession |
| `test_old_starter_note_is_marked_stale_not_just_superseded` | low-reliability old note vs. high-reliability contract |
| `test_mona_preference_updated_from_whatsapp_to_email_only` | WhatsApp → email-only preference |
| `test_affected_seats_correction_picks_48_over_42` | 42 → 48 correction |
| `test_identity_ambiguity_warns_on_shared_phone` | Mona / Omar shared phone |
| `test_nova_policy_does_not_leak_to_delta` | scoped policies don't project |
| `test_nova_policy_facts_are_scoped_to_nova` | scope predicate set correctly |
| `test_every_active_fact_carries_at_least_one_source_event` | citations |
| `test_explain_returns_supporting_events` | /explain |
| `test_helios_resolved_ticket_shows_root_cause` | status sync |
| `test_helios_context_lists_related_entities` | related entity discovery |

## Sample outputs (in `samples/`)

- `context_helios_account.json`
- `explain_helios_plan.json`
- `context_mona_contact.json`
- `context_delta_account.json` (no leaked Nova policy, has policy_unverified warning)
- `context_nova_account.json`
- `context_helios_p1_ticket.json`
- `idempotency_conflicts.json`
- `ingestion_report.json`

## Blockers

None.

## Next step

If this continued past the time box, the immediate priority is:

1. Implement `/diff/{type}/{id}?since=v` (designed in `ARCHITECTURE.md`).
2. LLM-based fact extractor for free-text claims, with structured-output
   verification + human review queue.
3. Outbox + worker for async fact derivation.
