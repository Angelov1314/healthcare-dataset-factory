"""Command-line entry points for Milestone 1 developer workflows."""

from __future__ import annotations

import argparse
import json
import logging
from uuid import UUID

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import create_session_factory
from app.ingestion.service import persist_snapshot, run_ingestion
from app.canonical.service import canonicalize
from app.governance.service import run_quality, seed_mapping_set
from app.omop.service import run_omop_mapping
from app.cohort.service import run_cohort, seed_liver_definition
from app.product.service import build_dataset_product
from sqlalchemy import select
from app.db.models import CohortRun, OmopMappingRun, QualityRun
from app.synthetic.generator import generate_snapshot


def main() -> None:
    """Run seed or pipeline commands and emit a JSON summary."""

    parser = argparse.ArgumentParser(prog="healthcare-factory")
    commands = parser.add_subparsers(dest="command", required=True)
    seed_parser = commands.add_parser("seed")
    seed_parser.add_argument("--seed", type=int)
    seed_parser.add_argument("--patients", type=int, choices=range(1, 5001))
    pipeline_parser = commands.add_parser("pipeline")
    pipeline_parser.add_argument("--snapshot-id", type=UUID)
    pipeline_parser.add_argument("--new-run", action="store_true")
    canonical_parser = commands.add_parser("canonicalize")
    canonical_parser.add_argument("--ingestion-run-id", type=UUID)
    quality_parser = commands.add_parser("quality")
    quality_parser.add_argument("--canonicalization-run-id", type=UUID)
    semantics_parser = commands.add_parser("semantics")
    semantics_parser.add_argument("--canonicalization-run-id", type=UUID)
    commands.add_parser("product")
    args = parser.parse_args()
    settings = get_settings()
    configure_logging(settings.log_level)
    session = create_session_factory()()
    try:
        if args.command == "seed":
            snapshot = generate_snapshot(args.seed or settings.synthetic_seed, args.patients or settings.synthetic_patients)
            result = {"source_snapshot_id": str(snapshot.source_snapshot_id), "inserted": persist_snapshot(session, snapshot)}
        elif args.command == "pipeline":
            result = run_ingestion(session, args.snapshot_id, args.new_run)
        elif args.command == "canonicalize":
            mapping = seed_mapping_set(session)
            ingestion_id = args.ingestion_run_id or UUID(run_ingestion(session)["ingestion_run_id"])
            result = canonicalize(session, ingestion_id, mapping.mapping_set_id)
        elif args.command == "quality":
            mapping = seed_mapping_set(session)
            ingestion_id = UUID(run_ingestion(session)["ingestion_run_id"])
            canonical = canonicalize(session, ingestion_id, mapping.mapping_set_id)
            result = run_quality(session, UUID(canonical["id"]))
        elif args.command == "semantics":
            mapping = seed_mapping_set(session)
            ingestion_id = args.canonicalization_run_id
            if ingestion_id is None:
                ingestion = run_ingestion(session)
                canonical = canonicalize(session, UUID(ingestion["ingestion_run_id"]), mapping.mapping_set_id)
                ingestion_id = UUID(canonical["id"])
            omop = run_omop_mapping(session, ingestion_id)
            definition = seed_liver_definition(session)
            result = {"omop": omop, "cohort": run_cohort(session, definition.cohort_definition_id, UUID(omop["id"]))}
        else:
            cohort = quality = None
            for candidate in session.scalars(select(CohortRun).where(CohortRun.status == "completed")).all():
                omop = session.get(OmopMappingRun, candidate.omop_run_id)
                if omop:
                    matching = session.scalar(select(QualityRun).where(QualityRun.status == "completed", QualityRun.canonicalization_run_id == omop.canonicalization_run_id))
                    if matching: cohort, quality = candidate, matching
            if cohort is None: raise ValueError("Compatible completed cohort and quality runs required; run make quality and make semantics first")
            result = build_dataset_product(session, cohort.cohort_run_id, quality.quality_run_id, settings.pseudonymization_secret, settings.pseudonymization_key_id)
        logging.getLogger(__name__).info("command_completed")
        print(json.dumps(result, default=str, sort_keys=True))
    finally:
        session.close()


if __name__ == "__main__":
    main()
