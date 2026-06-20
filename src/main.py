"""FastAPI entry point for the support memory layer."""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException

from . import db, ingest, facts, conflicts, context


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init()
    yield


app = FastAPI(
    title="Support Memory Reliability Layer",
    description="Ingest events, derive facts, return evidence-linked context.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/load-seed")
def load_seed():
    """Reset memory and ingest seed_data.json. Returns a per-event status list."""
    db.reset()
    ingestion = ingest.load_seed()
    extracted = facts.extract_facts()
    detection = conflicts.run_all()
    return {
        "ingestion": ingestion,
        "facts_extracted": extracted,
        "detection": detection,
    }


@app.get("/context/{entity_type}/{entity_id}")
def get_ctx(entity_type: str, entity_id: str):
    return context.get_context(entity_type, entity_id)


@app.get("/explain/{fact_id}")
def explain(fact_id: str):
    out = context.explain_fact(fact_id)
    if "error" in out:
        raise HTTPException(404, out["error"])
    return out


@app.get("/idempotency-conflicts")
def idempotency_conflicts():
    return context.list_idempotency_conflicts()
