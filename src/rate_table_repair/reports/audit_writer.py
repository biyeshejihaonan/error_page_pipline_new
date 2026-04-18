import json
from pathlib import Path
from typing import Dict, List, Optional

from rate_table_repair.schemas.patch import FalsePositiveItem, NeedsReviewItem, PatchPlan, PatchResult
from rate_table_repair.schemas.review import FinalJudgeResult, LinkedPatchResult, ReviewResult


class AuditWriter:
    def __init__(self, output_root: Path) -> None:
        self.output_root = output_root
        self.reports_dir = output_root / "reports"
        self.evidence_dir = output_root / "evidence"
        self.corrected_dir = output_root / "corrected_html"
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self.corrected_dir.mkdir(parents=True, exist_ok=True)

    def write_case_audit(
        self,
        case_name: str,
        page_number: int,
        primary: ReviewResult,
        peer: ReviewResult,
        final_judge: FinalJudgeResult,
        linked_patch: Optional[LinkedPatchResult],
        patch_plan: PatchPlan,
        patch_result: PatchResult,
    ) -> None:
        case_dir = self.evidence_dir / case_name
        case_dir.mkdir(parents=True, exist_ok=True)
        audit_path = case_dir / ("page_%04d_audit.json" % page_number)
        payload: Dict[str, object] = {
            "primary": primary.dict(by_alias=True),
            "peer": peer.dict(by_alias=True),
            "final_judge": final_judge.dict(by_alias=True),
            "linked_patch": linked_patch.dict(by_alias=True) if linked_patch is not None else None,
            "patch_plan": patch_plan.dict(by_alias=True),
            "patch_result": patch_result.dict(by_alias=True),
        }
        audit_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    def write_summary(
        self,
        patch_results: List[PatchResult],
        needs_review_items: List[NeedsReviewItem],
        false_positive_items: List[FalsePositiveItem],
    ) -> None:
        correction_summary = [
            item.dict() for item in patch_results
        ]
        needs_review = [
            item.dict() for item in needs_review_items
        ]
        false_positive = [
            item.dict() for item in false_positive_items
        ]
        (self.reports_dir / "correction_report.json").write_text(
            json.dumps(correction_summary, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        (self.reports_dir / "needs_review.json").write_text(
            json.dumps(needs_review, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        (self.reports_dir / "false_positive_report.json").write_text(
            json.dumps(false_positive, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
