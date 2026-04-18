from rate_table_repair.schemas.patch import PatchPlan
from rate_table_repair.schemas.review import FinalJudgeResult, LinkedPatchResult, PatchInstruction, ReviewResult
from rate_table_repair.schemas.report import PageIssue
from typing import Optional


def _normalize_patches(final_judge: FinalJudgeResult) -> list[PatchInstruction]:
    if final_judge.patches:
        return final_judge.patches
    if (
        final_judge.target_location_confirmed
        and final_judge.correction.from_value is not None
        and final_judge.correction.to_value is not None
    ):
        return [
            PatchInstruction(
                target_location=final_judge.target_location,
                correction=final_judge.correction,
                reason=final_judge.reason,
            )
        ]
    return []


def _same_location(left: ReviewResult, right: ReviewResult) -> bool:
    return (
        left.target_location.table_index == right.target_location.table_index
        and left.target_location.row_context == right.target_location.row_context
        and left.target_location.column_context == right.target_location.column_context
    )


def _consensus_patches(
    final_judge: FinalJudgeResult,
    primary: Optional[ReviewResult],
    peer: Optional[ReviewResult],
) -> list[PatchInstruction]:
    if primary is None or peer is None:
        return []
    if not (primary.is_real_error and peer.is_real_error):
        return []
    if primary.correction.from_value is None or primary.correction.to_value is None:
        return []
    if peer.correction.from_value is None or peer.correction.to_value is None:
        return []
    if primary.correction.from_value != peer.correction.from_value:
        return []
    if primary.correction.to_value != peer.correction.to_value:
        return []
    if not _same_location(primary, peer):
        return []
    raw_text = final_judge.raw_text or ""
    if "\"final_decision\": \"modify\"" not in raw_text or "\"should_modify_html\": true" not in raw_text:
        return []
    return [
        PatchInstruction(
            target_location=primary.target_location,
            correction=primary.correction,
            reason="final_judge JSON 不完整，采用主审与互评一致结论",
        )
    ]


def build_patch_plan(
    issue: PageIssue,
    final_judge: FinalJudgeResult,
    primary: Optional[ReviewResult] = None,
    peer: Optional[ReviewResult] = None,
    linked_patch: Optional[LinkedPatchResult] = None,
) -> PatchPlan:
    patches = _normalize_patches(final_judge)
    if not patches and linked_patch is not None and linked_patch.should_modify_html and linked_patch.patches:
        patches = linked_patch.patches
    if not patches:
        patches = _consensus_patches(final_judge, primary, peer)
    should_modify = (
        (final_judge.should_modify_html or len(patches) > 0)
        and len(patches) > 0
        and all(item.correction.from_value is not None and item.correction.to_value is not None for item in patches)
    )
    first_patch = patches[0] if patches else PatchInstruction()
    return PatchPlan(
        case_name=issue.case_name,
        html_path=issue.html_path,
        page_number=issue.page_number,
        should_modify=should_modify,
        target_location=first_patch.target_location,
        correction=first_patch.correction,
        patches=patches,
        reason=(linked_patch.reason if linked_patch is not None and linked_patch.reason else final_judge.reason) or first_patch.reason,
    )
