# Architecture

## Goals

Lina needs a memory layer that:

- preserves the original evidence (events) so any belief can be re-derived
- never silently merges duplicates, contradictions, or ambiguous identities
- answers a rep question quickly with citations a human can audit
- recovers cleanly from retries and partial failures

This document describes the model, the reliability assumptions, and what
was intentionally left out.

## Four layers

```
                                   +----------------------+
   raw events ────► raw_events ───►│  facts (derived)     │───► entity
   from feeds        append-only   │  (subject, predicate,│     projections
                                   │   value, confidence, │           │
                                   │   status, sources[]) │           ▼
                                   +----------------------+     /context, /explain
```

1. **`raw_events`** — every ingested event, with `body_hash` and timestamps.
   Append-only; nothing in the system mutates a raw event.
2. **`facts`** — derived claims of the form
   `(subject_type, subject_id, predicate, value)`. Every fact carries
   `confidence`, `status`, and a `source_event_ids` array pointing back to
   the events it came from.
3. **Entity projections** — at query time we filter `facts` by
   `(entity_type, entity_id)`; there is no separate "current state" table
   because the facts are the source of truth.
4. **Runtime context** — `/context` assembles
   `{active_facts, historical_facts, warnings, related_entities}` with full
   citations.

Keeping these layers separate means each can be changed in isolation:
a smarter extractor only touches the facts layer; a new context format only
touches the projection layer.

## Reliability decisions

### Idempotency

Each ingested event is identified by `(idempotency_key, body_hash)` where
`body_hash = sha256({source, actor, entity_type, entity_id, text, payload})`.

| Existing key? | Same body hash? | Outcome |
|---|---|---|
| No  | —   | Insert event, record `(key, hash, first_event_id)`. |
| Yes | Yes | **Duplicate retry** — ignore. Return reference to the original. |
| Yes | No  | **Idempotency conflict** — reject, log in `idempotency_conflicts`. |

This catches the `evt-1009` landmine in the seed data: same key as
`evt-1008` but a different body (different ticket, different payload).

### Supersession and staleness

For each `(subject, predicate)` with more than one distinct value:

1. Winner = `max(confidence, occurred_at)`.
2. Losers are tagged:
   - `superseded` for normal updates (preference change, seat correction).
   - `stale` when a low-reliability fact is overruled by a high-reliability
     one (low-reliability old agent note vs. signed contract).

Losers are kept, not deleted, so `/explain` can show "the system once
believed X, now believes Y because Z."

### Identity ambiguity

Contacts that share a phone number across distinct entity IDs (Mona vs Omar
sharing `+20 10 5555 0142`) produce an `identity_ambiguous` warning on each
contact involved. The system never merges contacts automatically — it
asks for a human.

### Unverified policies

Events flagged with `unverified_policy_guess` (or only `policy_hint` without
a contract) produce a `policy_unverified` warning. The high-reliability
contract DPA for Nova produces structured `policy_*` facts scoped by
`policy_scope_account_id`, so Nova's policy cannot leak onto Delta even
when a rep guesses they should be similar.

## Confidence formula

```
confidence(reliability, source)
  = RELIABILITY_WEIGHT[reliability] * SOURCE_WEIGHT[source]
```

| reliability | weight |   | source     | weight |
|---|---:|---|---|---:|
| high   | 1.0 |   | contract   | 1.0 |
| medium | 0.6 |   | system     | 0.9 |
| low    | 0.3 |   | crm        | 0.7 |
|        |     |   | email      | 0.6 |
|        |     |   | chat       | 0.5 |
|        |     |   | agent_note | 0.5 |

The number itself is not magic — what matters is that a signed contract
(1.0) always wins over an old agent note (0.15), and that the multiplication
keeps the score in [0, 1] for easy thresholding ("require >= 0.6 before
acting without review").

## Data model summary

```
raw_events(event_id PK, idempotency_key, body_hash, occurred_at,
           source, actor, entity_type, entity_id, related_entity_ids,
           reliability, text, payload, ingested_at)

idempotency_log(idempotency_key PK, body_hash, first_event_id)

idempotency_conflicts(id PK, idempotency_key, existing_event_id,
                      rejected_event_id, reason, detected_at)

facts(fact_id PK, subject_type, subject_id, predicate, value,
      confidence, status, source_event_ids[], superseded_by, created_at)
  index (subject_type, subject_id, predicate)

warnings(id PK, entity_type, entity_id, kind, message,
         source_event_ids[], created_at)
  unique (entity_type, entity_id, kind, message)
```

## What was intentionally NOT built

- **LLM fact extraction over free text.** Only structured payload keys
  produce facts today (e.g., `payload.plan` → `(account, X, plan, val)`).
  Free-text claims like "Mona prefers WhatsApp" are picked up only because
  the same event carries `payload.preference`. A v2 LLM extractor with
  structured output and human review queue is the next step.
- **`/diff` endpoint for "what changed since last context build."**
  Design: snapshot the set of `fact_id`s for an entity at every context
  request and store a monotonic `context_version`. `/diff?since=v17`
  returns `{added: [...], removed: [...], changed: [...]}` by fact_id.
  Did not build it because the demo budget was spent on landmine coverage;
  every piece needed is already in the facts table.
- **Outbox + worker queue.** Today the API does ingest + extract + detect
  synchronously inside `/load-seed`. Production should write `raw_events`
  in one transaction with an outbox row, then a worker derives facts and
  warnings. That makes retries safe end-to-end.
- **Authentication, multi-tenancy, rate limiting.** Out of scope for a
  local demo. Every query would gain a `tenant_id` filter in production.
- **Vector retrieval and embeddings.** All queries are structured. Free
  text is only there for human reading and as v2 extractor input.
- **Background jobs to re-score stale facts as new contracts arrive.**
  Today the detector runs once per `/load-seed`. Production wants a
  trigger after each ingestion batch.

## Failure model

| Failure | Behavior today | Production fix |
|---|---|---|
| Network retry sends same event again | Body-hash match → ignored | Same |
| Same key, different body (bug) | Rejected + logged for human | Same; plus alert |
| Fact extractor crashes mid-batch | `/load-seed` raises; no partial commit | Outbox + worker retries |
| Two reps file the same fact at once | Both become facts; supersession picks one | Same |
| Contract event missing | No high-reliability fact; medium agent notes win | Same |

## Mid-test scope change ("show what changed since last context")

Design (not implemented):

1. On every `/context` response, snapshot the active `fact_id` set with
   `context_versions(entity_type, entity_id, version, fact_ids_json,
   created_at)`.
2. `/diff/{type}/{id}?since={version}`:
   - Load the snapshot at `since`.
   - Compute current snapshot.
   - Return `{added: [fact_id...], removed: [fact_id...],
     changed: [{predicate, before, after, source_events}]}`.
3. Reps see exactly what's new since the last time they looked.

This is small enough to add in ~30 minutes; it was cut to make room for
broader landmine coverage.
