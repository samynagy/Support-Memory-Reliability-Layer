# Support Memory Reliability Layer

A small local service that ingests Aster Support events, derives evidence-linked
facts, and returns compact context for a support rep — without silently flattening
duplicates, conflicts, stale facts, or ambiguous identities.

Built for the Aster Support work sample. 3-hour time-boxed.

## What it does

- **Ingest** raw events with idempotency keys + body-hash conflict detection.
- **Derive** structured facts from event payloads with a confidence score.
- **Resolve** same-subject/same-predicate disagreements into a winner, with
  losers kept as `superseded` or `stale` (never silently deleted).
- **Surface** identity ambiguity, duplicate retries, and unverified policy
  guesses as warnings — never auto-merge contacts, never enforce a policy
  without a contract.
- **Answer** "what should the rep know about Helios?" with citations to the
  source event IDs.
- **Explain** any fact by returning the events that support it.

## Run

```bash
python -m venv .venv
source .venv/Scripts/activate          # Windows bash
# or: .venv\Scripts\activate           # Windows cmd/powershell
pip install -r requirements.txt

uvicorn src.main:app --reload
```

Then in another terminal:

```bash
  curl -X POST http://localhost:8000/load-seed
curl http://localhost:8000/context/account/acct_helios_141
curl http://localhost:8000/idempotency-conflicts
```

## Test

```bash
pytest -v
```

13 tests cover every landmine in the seed data:
idempotency conflict, plan supersession, stale low-reliability note,
preference change, seat-count correction, identity ambiguity,
policy non-leak, source citations, explain view, related entities.

## Generate sample outputs

```bash
PYTHONPATH=. python scripts/generate_samples.py
ls samples/
```

Pre-generated samples are checked in under `samples/`.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/load-seed` | Reset DB, ingest `seed_data.json`, run extraction + detectors. |
| `GET`  | `/context/{type}/{id}` | Compact context for an entity, with citations + warnings. |
| `GET`  | `/explain/{fact_id}` | The raw events that support one fact. |
| `GET`  | `/idempotency-conflicts` | Events rejected because a key was reused with a different body. |
| `GET`  | `/health` | Liveness check. |

## Design summary

Four layers, kept separate so each can be reasoned about and replaced:

1. **`raw_events`** — append-only. Original evidence, never mutated.
2. **`facts`** — `(subject_type, subject_id, predicate, value)` triples
   derived deterministically from payload keys, with confidence and status.
3. **Entity projections** — facts filtered by `(entity_type, entity_id)`.
4. **Runtime context** — `/context` assembles active facts + historical losers
   + warnings + related entities, every fact citing its source event IDs.

### Confidence

```
confidence = RELIABILITY_WEIGHT[reliability] * SOURCE_WEIGHT[source]
```

| reliability | weight | | source     | weight |
|---|---:|---|---|---:|
| high   | 1.0  | | contract   | 1.0 |
| medium | 0.6  | | system     | 0.9 |
| low    | 0.3  | | crm        | 0.7 |
|        |      | | email      | 0.6 |
|        |      | | chat       | 0.5 |
|        |      | | agent_note | 0.5 |

### Conflict resolution

When two facts share `(subject_type, subject_id, predicate)` with different values:

1. Highest confidence wins; recency breaks ties.
2. Losers become `superseded` (kept for audit).
3. If a low-reliability fact loses to a high-reliability one, it is marked
   `stale` so the rep can see "this was once believed but is overruled."

### Idempotency

Each event has an `idempotency_key`. The ingest path stores a
`(key, body_hash)` row on first sight:

- Same key + same body → **silent duplicate**, ignored.
- Same key + different body → **conflict**, rejected and logged in
  `idempotency_conflicts`. Visible at `GET /idempotency-conflicts`. This is
  the `evt-1009` landmine in the seed data.

### Identity ambiguity

Two different contact entities that share a phone number raise an
`identity_ambiguous` warning on **both** contacts. The system never merges
contacts automatically — that is a human decision.

### Policy scope

Policies attach to their own entity (e.g. `policy_nova_141_privacy`) and
carry a `policy_scope_account_id` fact pointing at the scoped account.
Queries are filtered by `subject_id`, so Nova's DPA cannot project onto
Delta even if a rep guesses they are similar.

## Tradeoffs (intentional cuts)

- **Rule-based extractor, not LLM.** Deterministic, testable, free. v2 step
  is an LLM extractor for free-text claims with a human review queue.
- **SQLite, single process.** Easy to run locally; a production version
  would use an outbox + queue for async fact extraction.
- **No auth, no tenancy.** Single-tenant local service. Production would
  filter every query by `tenant_id`.
- **No vector retrieval.** All queries are structured. Free-text matching
  is left to v2.
- **`/diff` endpoint not implemented.** Designed in `ARCHITECTURE.md`
  under the mid-test scope change. Snapshot fact-id sets per entity with a
  monotonic `context_version`; `/diff` returns `{added, removed, changed}`.

## AI tooling used

I used Claude and Gemini Pro as my partners for thinking and coding. They helped me to:

Break down the task into small parts.

Build the basic four-layer system.

Write the math for the confidence scores.

Think of the tricky test cases.

I checked all their work carefully. I ran the tests (pytest) on the 20 starting events and read the final results from start to finish to make sure everything was exactly right

## Layout

```
support-memory/
├── README.md            you are here
├── ARCHITECTURE.md      model, reliability assumptions, what was skipped
├── DAILY_UPDATE.md      end-of-day status
├── NEXT.md              production roadmap
├── requirements.txt
├── seed_data.json       20 seed events
├── src/
│   ├── db.py            schema + helpers
│   ├── ingest.py        idempotent ingestion
│   ├── facts.py         deterministic fact extraction + confidence
│   ├── conflicts.py     supersession, dupes, identity, policy detectors
│   ├── context.py       compact context + explain
│   └── main.py          FastAPI app
├── tests/
│   └── test_landmines.py
├── samples/             pre-generated JSON outputs
└── scripts/
    └── generate_samples.py
```
