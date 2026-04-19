from copy import deepcopy
from typing import Optional

from rate_table_repair.schemas.patch import PatchPlan
from rate_table_repair.schemas.report import OldIssueHint, PageIssue
from rate_table_repair.schemas.review import FinalJudgeResult, LinkedPatchResult, PatchInstruction, ReviewResult


_MULTI_CELL_HINTS = (
    "数据错位",
    "多处",
    "多个单元格",
    "同一行",
    "联动",
    "顺序",
    "整行",
    "相邻",
)


def _normalize_patches(final_judge: FinalJudgeResult) -> list[PatchInstruction]:
    if final_judge.patches:
        return [
            deepcopy(patch)
            for patch in final_judge.patches
            if not (
                patch.correction.from_value is not None
                and patch.correction.to_value is not None
                and patch.correction.from_value == patch.correction.to_value
            )
        ]
    if (
        final_judge.target_location_confirmed
        and final_judge.correction.from_value is not None
        and final_judge.correction.to_value is not None
        and final_judge.correction.from_value != final_judge.correction.to_value
    ):
        return [
            PatchInstruction(
                target_location=deepcopy(final_judge.target_location),
                correction=deepcopy(final_judge.correction),
                reason=final_judge.reason,
            )
        ]
    return []


def _patches_complete(patches: list[PatchInstruction]) -> bool:
    return bool(patches) and all(
        item.correction.from_value is not None and item.correction.to_value is not None
        for item in patches
    )


def _same_location(left: ReviewResult, right: ReviewResult) -> bool:
    return (
        left.target_location.table_index == right.target_location.table_index
        and left.target_location.row_context == right.target_location.row_context
        and left.target_location.column_context == right.target_location.column_context
    )


def _weak_row_context(review: ReviewResult) -> bool:
    row_context = (review.target_location.row_context or "").strip()
    if not row_context:
        return True
    tokens = [token for token in row_context.replace("，", ",").split(",") if token.strip()]
    return len(tokens) <= 1


def _looks_like_multi_cell_issue(*texts: str) -> bool:
    joined = "\n".join(text for text in texts if text)
    return any(token in joined for token in _MULTI_CELL_HINTS)


def _consensus_patches(
    final_judge: FinalJudgeResult,
    primary: Optional[ReviewResult],
    peer: Optional[ReviewResult],
    linked_patch: Optional[LinkedPatchResult] = None,
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
    if _weak_row_context(primary) or _weak_row_context(peer):
        return []
    if _looks_like_multi_cell_issue(
        primary.reason,
        peer.reason,
        final_judge.reason,
        primary.raw_text,
        peer.raw_text,
        final_judge.raw_text,
        linked_patch.raw_text if linked_patch is not None else "",
    ):
        return []
    raw_text = final_judge.raw_text or ""
    if "\"final_decision\": \"modify\"" not in raw_text or "\"should_modify_html\": true" not in raw_text:
        return []
    return [
        PatchInstruction(
            target_location=deepcopy(primary.target_location),
            correction=deepcopy(primary.correction),
            reason="final_judge JSON 不完整，采用主审与互评一致结论",
        )
    ]


def _raw_text_indicates_modify(raw_text: str) -> bool:
    return "\"should_modify_html\": true" in raw_text and (
        "\"final_decision\": \"modify\"" in raw_text or "\"patches\": [" in raw_text
    )


def _hint_matches_patch(hint: OldIssueHint, patch: PatchInstruction) -> bool:
    expected_to = patch.correction.to_value
    expected_from = patch.correction.from_value
    if expected_to and hint.correct_value and expected_to == hint.correct_value:
        return True
    if expected_from and hint.current_value and expected_from == hint.current_value:
        return True
    if expected_to and hint.text and expected_to in hint.text:
        return True
    if expected_from and hint.text and expected_from in hint.text:
        return True
    return False


def _enrich_patch_from_hints(patch: PatchInstruction, hints: list[OldIssueHint]) -> PatchInstruction:
    if not hints:
        return patch

    matches = [hint for hint in hints if _hint_matches_patch(hint, patch)]
    if len(matches) != 1 and len(hints) == 1:
        matches = hints
    if len(matches) != 1:
        return patch

    hint = matches[0]
    if patch.target_location.row_context is None and hint.row_context is not None:
        patch.target_location.row_context = hint.row_context
    if patch.target_location.column_index is None and hint.column_index is not None:
        patch.target_location.column_index = hint.column_index
    if patch.target_location.column_context is None and hint.column_context is not None:
        patch.target_location.column_context = hint.column_context
    if patch.correction.from_value is None and hint.current_value is not None:
        patch.correction.from_value = hint.current_value
    if patch.correction.to_value is None and hint.correct_value is not None:
        patch.correction.to_value = hint.correct_value
    return patch


def _patch_plan_reason(
    final_judge: FinalJudgeResult,
    patches: list[PatchInstruction],
    linked_patch: Optional[LinkedPatchResult],
) -> str:
    if linked_patch is not None and linked_patch.reason:
        return linked_patch.reason
    if final_judge.final_decision == "false_positive":
        return final_judge.reason or "旧报告误报"
    if not patches:
        if final_judge.should_modify_html:
            return final_judge.reason or "模型认为有问题，但没有生成可执行 patch"
        return final_judge.reason or "最终裁决未放行自动修改"
    if not all(item.correction.from_value is not None and item.correction.to_value is not None for item in patches):
        return final_judge.reason or "patch 缺少旧值或新值"
    return final_judge.reason or patches[0].reason or "已生成 patch"


def build_patch_plan(
    issue: PageIssue,
    final_judge: FinalJudgeResult,
    primary: Optional[ReviewResult] = None,
    peer: Optional[ReviewResult] = None,
    linked_patch: Optional[LinkedPatchResult] = None,
) -> PatchPlan:
    patches = _normalize_patches(final_judge)
    if (
        linked_patch is not None
        and linked_patch.should_modify_html
        and linked_patch.patches
        and not _patches_complete(patches)
    ):
        patches = [deepcopy(item) for item in linked_patch.patches]
    if not patches:
        patches = _consensus_patches(final_judge, primary, peer, linked_patch)
    patches = [_enrich_patch_from_hints(item, issue.old_issue_hints) for item in patches]
    decision_allows_modify = final_judge.final_decision == "modify" or (
        linked_patch is not None and linked_patch.should_modify_html and final_judge.final_decision != "false_positive"
    )
    if not decision_allows_modify and _raw_text_indicates_modify(final_judge.raw_text or ""):
        decision_allows_modify = True
    if not decision_allows_modify and linked_patch is not None and _raw_text_indicates_modify(linked_patch.raw_text or ""):
        decision_allows_modify = True
    should_modify = (
        decision_allows_modify
        and len(patches) > 0
        and _patches_complete(patches)
    )
    first_patch = deepcopy(patches[0]) if patches else PatchInstruction()
    reason = _patch_plan_reason(final_judge, patches, linked_patch)
    return PatchPlan(
        case_name=issue.case_name,
        html_path=issue.html_path,
        page_number=issue.page_number,
        should_modify=should_modify,
        target_location=deepcopy(first_patch.target_location),
        correction=deepcopy(first_patch.correction),
        patches=patches,
        reason=reason,
    )
