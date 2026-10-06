"""Human semantic judgments, independent of generation execution and Keep.

No mesh classification or generator changes. Request snapshots describe the
output that was actually generated, not the current editable UI inputs.
"""
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import copy
import uuid

REVIEW_STATES = ("UNREVIEWED", "ACCEPTED", "REJECTED")
REJECT_REASONS = ("WRONG_PART", "WHOLE_OBJECT", "BROKEN_MESH", "WRONG_PROPORTION", "OTHER")
REVIEWABLE_EXECUTION_STATES = ("DONE", "KEPT")


@dataclass(frozen=True)
class SemanticReview:
    unit_id: str
    review_state: str = "UNREVIEWED"
    reject_reason: str | None = None
    note: str | None = None
    reviewed_at: str | None = None
    review_id: str | None = None

    def decide(self, state, reason=None, note=None):
        if state not in ("ACCEPTED", "REJECTED"):
            raise ValueError("Choose ACCEPTED or REJECTED.")
        if state == "REJECTED" and reason not in REJECT_REASONS:
            raise ValueError("Rejection requires a valid reason.")
        return replace(self, review_state=state,
                       reject_reason=reason if state == "REJECTED" else None,
                       note=(note or "").strip() or None if state == "REJECTED" else None,
                       reviewed_at=datetime.now(timezone.utc).isoformat(),
                       review_id=uuid.uuid4().hex)


def request_snapshot(request, *, batch_id, unit_kind, entity_type, generator,
                     placement, output_path, final_prompt, diagnostics=None):
    """Plain JSON snapshot; absent metadata stays null rather than being guessed."""
    names = list(request.source_object_names)
    return copy.deepcopy({
        "batch_id": batch_id,
        "run_id": batch_id,
        "generation_unit_id": request.master_id,
        "unit_kind": unit_kind,
        "entity_type": entity_type,
        "semantic_role": request.semantic_type,
        "source_group": placement.get("source_group"),
        "source_guide_name": names[0] if len(names) == 1 else None,
        "source_guide_names": names,
        "instance_count": request.instance_count,
        "style_prompt": request.style_prompt,
        "final_prompt": final_prompt,
        "guide_dimensions": list(request.guide_dimensions),
        "guide_ratio": list(request.guide_ratio),
        "generator": generator,
        "output_path": output_path,
        "request": request.to_dict(),
        "diagnostics": diagnostics or {},
    })


def review_event(snapshot, current_review, execution_status, state, reason=None, note=None):
    if execution_status not in REVIEWABLE_EXECUTION_STATES:
        raise ValueError("Only completed geometry can be reviewed.")
    if snapshot.get("generation_unit_id") != current_review.unit_id:
        raise ValueError("Review identity does not match the generated unit.")
    if not snapshot.get("batch_id") or not snapshot.get("output_path") or not snapshot.get("final_prompt"):
        raise ValueError("The generated request snapshot is incomplete.")
    review = current_review.decide(state, reason, note)
    event = copy.deepcopy(snapshot)
    event.update(schema_version="0.3.1", review_id=review.review_id,
                 reviewed_at=review.reviewed_at, execution_status=execution_status,
                 semantic_review=review.review_state, reject_reason=review.reject_reason,
                 review_note=review.note)
    return review, event