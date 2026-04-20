from copy import deepcopy
from typing import Any, Optional

from rate_table_repair.schemas.patch import PatchPlan
from rate_table_repair.schemas.report import OldIssueHint, PageIssue
from rate_table_repair.schemas.review import FinalJudgeResult, PatchInstruction, ReviewResult


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

_SOURCE_WEIGHTS = {
    "final_judge": 1,
    "peer": 1,
    "primary": 1,
}

_CONFIDENCE_WEIGHTS = {
    "high": 3,
    "medium": 2,
    "low": 1,
}


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


def _review_to_patches(review: Optional[ReviewResult], source: str) -> list[PatchInstruction]:
    if review is None or review.is_real_error is not True:
        return []
    if review.correction.from_value is None or review.correction.to_value is None:
        return []
    if review.correction.from_value == review.correction.to_value:
        return []
    return [
        PatchInstruction(
            target_location=deepcopy(review.target_location),
            correction=deepcopy(review.correction),
            reason=review.reason or source,
        )
    ]


def _patches_complete(patches: list[PatchInstruction]) -> bool:
    return bool(patches) and all(
        item.correction.from_value is not None and item.correction.to_value is not None
        for item in patches
    )


def _patch_signature(patch: PatchInstruction) -> tuple[Any, ...]:
    return (
        patch.target_location.table_index,
        patch.target_location.row_index,
        patch.target_location.column_index,
        patch.target_location.row_context,
        patch.target_location.column_context,
        patch.correction.from_value,
        patch.correction.to_value,
    )


def _patchset_signature(patches: list[PatchInstruction]) -> tuple[tuple[Any, ...], ...]:
    return tuple(_patch_signature(item) for item in patches)


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


def _candidate_patch_sets(
    final_judge: FinalJudgeResult,
    primary: Optional[ReviewResult],
    peer: Optional[ReviewResult],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []

    final_patches = _normalize_patches(final_judge)
    if final_patches:
        candidates.append(
            {
                "source": "final_judge",
                "patches": final_patches,
                "confidence": final_judge.confidence,
                "reason": final_judge.reason,
            }
        )

    for source, review in (("peer", peer), ("primary", primary)):
        review_patches = _review_to_patches(review, source)
        if review_patches:
            candidates.append(
                {
                    "source": source,
                    "patches": review_patches,
                    "confidence": review.confidence if review is not None else "unknown",
                    "reason": review.reason if review is not None else "",
                }
            )

    return candidates


def _score_candidate(candidate: dict[str, Any], all_candidates: list[dict[str, Any]]) -> int:
    patches = candidate["patches"]
    if not _patches_complete(patches):
        return -100

    score = _SOURCE_WEIGHTS.get(candidate["source"], 0)
    score += _CONFIDENCE_WEIGHTS.get((candidate.get("confidence") or "").lower(), 0)
    score += len(patches) * 2

    for patch in patches:
        if patch.target_location.row_context:
            score += 1
        if patch.target_location.row_index is not None:
            score += 1
        if patch.target_location.column_index is not None or patch.target_location.column_context:
            score += 1

    signature = _patchset_signature(patches)
    first_signature = _patch_signature(patches[0])
    for other in all_candidates:
        if other is candidate or not other["patches"]:
            continue
        other_signature = _patchset_signature(other["patches"])
        if signature == other_signature:
            score += 4
        elif _patch_signature(other["patches"][0]) == first_signature:
            score += 2
    return score


def _vote_score_map(candidate_votes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for vote in candidate_votes:
        voter_model = vote.get("voter_model", "")
        for item in vote.get("scores") or []:
            source = item.get("source")
            if not isinstance(source, str):
                continue
            bucket = result.setdefault(source, {"total": 0, "votes": []})
            score = int(item.get("score", 0))
            bucket["total"] += score
            bucket["votes"].append(
                {
                    "voter_model": voter_model,
                    "score": score,
                    "reason": item.get("reason", ""),
                }
            )
    return result


def _select_best_patches(candidates: list[dict[str, Any]]) -> tuple[list[PatchInstruction], str]:
    if not candidates:
        return [], ""

    best = None
    best_vote_score = -10**9
    best_tie_break = -10**9
    for candidate in candidates:
        vote_score = int(candidate.get("vote_score", candidate.get("score", 0)))
        tie_break = int(candidate.get("tie_break_score", _score_candidate(candidate, candidates)))
        candidate["score"] = vote_score
        candidate["tie_break_score"] = tie_break
        if vote_score > best_vote_score or (vote_score == best_vote_score and tie_break > best_tie_break):
            best_vote_score = vote_score
            best_tie_break = tie_break
            best = candidate
    if best is None or best_vote_score < 0:
        return [], ""
    return [deepcopy(item) for item in best["patches"]], f"{best['source']} 投票最高({best_vote_score})"


def _candidate_score_report(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    report: list[dict[str, Any]] = []
    for candidate in candidates:
        patches = candidate.get("patches") or []
        first_patch = patches[0] if patches else PatchInstruction()
        report.append(
            {
                "source": candidate.get("source", ""),
                "score": candidate.get("score", 0),
                "vote_score": candidate.get("vote_score", 0),
                "tie_break_score": candidate.get("tie_break_score", 0),
                "confidence": candidate.get("confidence", ""),
                "reason": candidate.get("reason", ""),
                "patch_count": len(patches),
                "vote_details": candidate.get("vote_details", []),
                "first_patch": {
                    "target_location": deepcopy(first_patch.target_location).model_dump(by_alias=True),
                    "correction": deepcopy(first_patch.correction).model_dump(by_alias=True),
                },
            }
        )
    report.sort(key=lambda item: item.get("score", 0), reverse=True)
    return report


def _apply_vote_scores(candidates: list[dict[str, Any]], candidate_votes: list[dict[str, Any]]) -> None:
    vote_scores = _vote_score_map(candidate_votes)
    for candidate in candidates:
        source = candidate.get("source", "")
        bucket = vote_scores.get(source, {"total": 0, "votes": []})
        candidate["vote_score"] = bucket["total"]
        candidate["vote_details"] = bucket["votes"]
        candidate["tie_break_score"] = _score_candidate(candidate, candidates)
        candidate["score"] = candidate.get("vote_score", 0)


def _false_positive_votes(
    primary: Optional[ReviewResult],
    peer: Optional[ReviewResult],
) -> int:
    votes = 0
    if primary is not None and primary.is_real_error is False:
        votes += 1
    if peer is not None and peer.is_real_error is False:
        votes += 1
    return votes


def _support_votes_for_source(candidate_scores: list[dict[str, Any]], source: str) -> int:
    for candidate in candidate_scores:
        if candidate.get("source") != source:
            continue
        votes = 0
        for vote in candidate.get("vote_details") or []:
            if int(vote.get("score", 0)) >= 8:
                votes += 1
        return votes
    return 0


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
) -> str:
    if not patches:
        return "模型未生成可执行 patch"
    if not all(item.correction.from_value is not None and item.correction.to_value is not None for item in patches):
        return "patch 缺少旧值或新值"
    return patches[0].reason or "已生成 patch"


def build_patch_plan(
    issue: PageIssue,
    final_judge: FinalJudgeResult,
    primary: Optional[ReviewResult] = None,
    peer: Optional[ReviewResult] = None,
    candidate_votes: Optional[list[dict[str, Any]]] = None,
) -> PatchPlan:
    candidate_sets = _candidate_patch_sets(final_judge, primary, peer)
    if candidate_votes:
        _apply_vote_scores(candidate_sets, candidate_votes)
    patches, selection_reason = _select_best_patches(candidate_sets)
    candidate_scores = _candidate_score_report(candidate_sets)
    patches = [_enrich_patch_from_hints(item, issue.old_issue_hints) for item in patches]
    should_modify = len(patches) > 0 and _patches_complete(patches)
    first_patch = deepcopy(patches[0]) if patches else PatchInstruction()
    reason = selection_reason or _patch_plan_reason(final_judge, patches)
    selection_source = ""
    selection_score = 0
    support_votes = 0
    false_positive_votes = _false_positive_votes(primary, peer)
    if selection_reason:
        selection_source = selection_reason.split(" ", 1)[0]
    if candidate_scores and selection_source:
        for candidate in candidate_scores:
            if candidate.get("source") == selection_source:
                selection_score = candidate.get("score", 0)
                break
        support_votes = _support_votes_for_source(candidate_scores, selection_source)
    classification = "needs_review"
    if false_positive_votes >= 2:
        classification = "false_positive"
        should_modify = False
        reason = "至少两票认为旧报告误报"
    elif should_modify and support_votes >= 2:
        classification = "modify"
    else:
        should_modify = False
        classification = "needs_review"
        if not patches:
            reason = "模型未形成可执行共识"
        elif support_votes < 2:
            reason = "模型未形成足够相似结果"
        else:
            reason = reason or "自动修改失败"
    return PatchPlan(
        case_name=issue.case_name,
        html_path=issue.html_path,
        page_number=issue.page_number,
        should_modify=should_modify,
        target_location=deepcopy(first_patch.target_location),
        correction=deepcopy(first_patch.correction),
        patches=patches,
        reason=reason,
        selection_source=selection_source,
        selection_score=selection_score,
        classification=classification,
        support_votes=support_votes,
        false_positive_votes=false_positive_votes,
        candidate_scores=candidate_scores,
    )
