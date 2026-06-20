# What I would build next

If this became production, in priority order:

## 1. `/diff/{type}/{id}?since={version}`

Implements Lina's mid-test scope change. Designed in `ARCHITECTURE.md`.
Snapshot the active `fact_id` set on every context call, store with a
monotonic `context_version`. Diff returns
`{added, removed, changed: [{predicate, before, after, source_events}]}`.

Effort: ~30 min on top of the current model.

## 2. LLM-based free-text extractor

The current rule-based extractor only promotes structured payload keys.
Free-text claims like "Mona prefers WhatsApp" only register today because
the same event also carries `payload.preference`.

Plan:

- Pass `text` to an LLM with structured output (Pydantic schema for facts).
- Run on a separate worker; never block ingest.
- Confidence = `extractor_confidence * source_weight * reliability_weight`.
- Any extracted fact below the action threshold lands in a
  `needs_review` queue, not the active set.

## 3. Outbox + worker for async derivation

Today `/load-seed` runs ingest + extract + detect synchronously. In
production this should be:

```
ingest tx -> writes raw_events + outbox row (single sqlite/postgres tx)
worker   -> consumes outbox -> extract_facts + run_all
```

Lets the API stay fast, and retries become safe end-to-end.

## 4. Tenancy + auth

Every table gets `tenant_id`. Every query filters by tenant. Auth
middleware injects tenant from the bearer token. Without this, the
"policy must not leak across accounts" guarantee is only enforced
inside one tenant — cross-tenant leak protection needs the filter.

## 5. Confidence calibration loop

Today the weights are picked by judgment. With production traffic, a
weekly job should:

- pull rep actions ("dismissed fact", "acted on fact", "marked stale")
- fit per-source-type weights to match observed accuracy
- write new weights to a config table, not hard-coded constants.

## 6. PII redaction for scoped accounts

For Nova-style DPAs, run an extra pass on context responses for
accounts under a `policy_no_training` policy to redact free-text fields
that contain patient/customer data before any response touches an LLM
or analytics surface.

## 7. Vector retrieval for free-text questions

Embed `raw_events.text` and free-text fact values. When a rep asks an
open question ("anything weird about Helios billing?"), do hybrid
retrieval: structured facts + top-k semantic events. Citations still
required.

## 8. Observability

- Metrics: events_ingested, idempotency_conflicts_total,
  warnings_total, fact_status_transitions.
- Per-tenant dashboard.
- Alert if `idempotency_conflicts_total` is non-zero in a window — that
  is almost always a producer bug worth paging.
