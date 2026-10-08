"""Publish reviewed import mappings as an immutable governance mapping set."""
from __future__ import annotations

import hashlib
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ImportJob,
    MappingDefinition,
    MappingImportAuditEvent,
    MappingSet,
    MappingSuggestion,
    MappingSuggestionReview,
    SourceFieldProfile,
)


def publish_reviewed_mapping_set(session: Session, import_job_id: UUID) -> dict[str, object]:
    """Create or return the one immutable mapping set derived from final approved reviews."""
    job = session.get(ImportJob, import_job_id)
    if not job:
        raise LookupError("Import job not found")
    reviews = session.execute(
        select(MappingSuggestionReview, MappingSuggestion, SourceFieldProfile)
        .join(MappingSuggestion, MappingSuggestionReview.mapping_suggestion_id == MappingSuggestion.mapping_suggestion_id)
        .join(SourceFieldProfile, MappingSuggestion.source_field_profile_id == SourceFieldProfile.source_field_profile_id)
        .where(MappingSuggestion.import_job_id == import_job_id, MappingSuggestionReview.action.in_(("approved", "edited")))
    ).all()
    if not reviews:
        raise ValueError("At least one approved or edited review is required")
    scope = f"import-{str(import_job_id)[:8]}"
    version = f"profile-{job.profile_hash[:12]}"
    existing = session.scalar(select(MappingSet).where(MappingSet.scope == scope, MappingSet.version == version))
    if existing:
        definitions = session.scalars(select(MappingDefinition).where(MappingDefinition.mapping_set_id == existing.mapping_set_id)).all()
        return {"id": str(existing.mapping_set_id), "scope": existing.scope, "version": existing.version, "definition_count": len(definitions)}
    mapping_set = MappingSet(scope=scope, version=version, status="draft", description="Human-reviewed external import mappings")
    session.add(mapping_set)
    session.flush()
    definitions = 0
    for review, suggestion, profile in reviews:
        session.add(MappingDefinition(
            mapping_set_id=mapping_set.mapping_set_id,
            source_system="external",
            source_entity=profile.table_name[:32],
            source_field=profile.field_name[:64],
            canonical_entity=review.target_entity or "",
            canonical_field=review.target_field or "",
            rule_key=review.transform,
            confidence=suggestion.confidence,
            evidence={
                "kind": "human_reviewed_import_mapping",
                "profile_hash": job.profile_hash,
                "artifact_hash": job.artifact_hash,
                "review_snapshot": review.snapshot,
                "reviewer": review.reviewer,
                "mapping_policy": "mapping-review@1.0.0",
                "manifest_hash": hashlib.sha256(f"{job.profile_hash}:{review.mapping_suggestion_review_id}".encode()).hexdigest(),
            },
            status="approved",
            reviewer=review.reviewer,
        ))
        definitions += 1
    session.add(MappingImportAuditEvent(import_job_id=import_job_id, mapping_suggestion_id=None, event_type="mapping_set_published", details={"mapping_set_scope": scope, "mapping_set_version": version, "definition_count": definitions, "profile_hash": job.profile_hash}))
    session.commit()
    return {"id": str(mapping_set.mapping_set_id), "scope": scope, "version": version, "definition_count": definitions}
