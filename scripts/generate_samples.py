"""Generate sample outputs into samples/ for the README and reviewer."""
import json
from pathlib import Path

from src import db, ingest, facts, conflicts, context

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"
SAMPLES.mkdir(exist_ok=True)


def write(name: str, data) -> None:
    path = SAMPLES / name
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"wrote {path.relative_to(ROOT)}")


def main():
    db.reset()
    ingestion = ingest.load_seed(ROOT / "seed_data.json")
    extracted = facts.extract_facts()
    detection = conflicts.run_all()

    write("ingestion_report.json", {
        "ingestion": ingestion,
        "facts_extracted": extracted,
        "detection": detection,
    })

    helios = context.get_context("account", "acct_helios_141")
    write("context_helios_account.json", helios)

    plan_fact = next(f for f in helios["active_facts"] if f["predicate"] == "plan")
    write("explain_helios_plan.json", context.explain_fact(plan_fact["fact_id"]))

    write("context_mona_contact.json",
          context.get_context("contact", "contact_mona_141"))

    write("context_delta_account.json",
          context.get_context("account", "acct_delta_141"))

    write("context_nova_account.json",
          context.get_context("account", "acct_nova_141"))

    write("context_helios_p1_ticket.json",
          context.get_context("ticket", "ticket_h_141_p1"))

    write("idempotency_conflicts.json", context.list_idempotency_conflicts())


if __name__ == "__main__":
    main()
