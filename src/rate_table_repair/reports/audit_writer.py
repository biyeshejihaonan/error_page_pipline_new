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

    @staticmethod
    def _effective_final_decision(final_judge: FinalJudgeResult, patch_result: PatchResult) -> str:
        if patch_result.modified:
            return "modify"
        if final_judge.final_decision == "false_positive":
            return "false_positive"
        return "needs_review"

    @staticmethod
    def _review_status_text(review: ReviewResult) -> str:
        if review.is_real_error is True:
            return "⚠️ 有问题"
        if review.is_real_error is False:
            return "✅ 无问题"
        return "❓ 不确定"

    @staticmethod
    def _final_status_text(final_judge: FinalJudgeResult, patch_result: PatchResult) -> str:
        effective = AuditWriter._effective_final_decision(final_judge, patch_result)
        if effective == "modify":
            return "✅ 已自动修正"
        if effective == "false_positive":
            return "ℹ️ 旧报告误报"
        return "⚠️ 待人工复核"

    @staticmethod
    def _format_review_detail(review: ReviewResult) -> str:
        detail_lines = [
            "【复核结论】%s" % AuditWriter._review_status_text(review),
            "【说明】%s" % (review.reason or "无"),
        ]
        if review.target_location and any(
            value is not None and value != ""
            for value in (
                review.target_location.table_index,
                review.target_location.row_index,
                review.target_location.column_index,
                review.target_location.row_context,
                review.target_location.column_context,
            )
        ):
            detail_lines.append(
                "【定位】table=%s row=%s col=%s row_context=%s column_context=%s"
                % (
                    review.target_location.table_index,
                    review.target_location.row_index,
                    review.target_location.column_index,
                    review.target_location.row_context,
                    review.target_location.column_context,
                )
            )
        if review.correction and (review.correction.from_value is not None or review.correction.to_value is not None):
            detail_lines.append(
                "【候选修正】from=%s -> to=%s"
                % (review.correction.from_value, review.correction.to_value)
            )
        if review.concerns:
            detail_lines.append("【疑虑】%s" % "；".join(review.concerns))
        return "\n".join(detail_lines)

    @staticmethod
    def _format_final_detail(
        final_judge: FinalJudgeResult,
        linked_patch: Optional[LinkedPatchResult],
        patch_plan: PatchPlan,
        patch_result: PatchResult,
    ) -> str:
        effective = AuditWriter._effective_final_decision(final_judge, patch_result)
        lines = [
            "【最终状态】%s" % AuditWriter._final_status_text(final_judge, patch_result),
            "【有效结论】%s" % effective,
            "【模型裁决】%s" % final_judge.final_decision,
            "【裁决说明】%s" % (patch_plan.reason or final_judge.reason or "无"),
        ]
        if patch_plan.patches:
            lines.append("【修正项】")
            for index, patch in enumerate(patch_plan.patches, start=1):
                lines.append(
                    "  %s. table=%s row=%s col=%s row_context=%s column_context=%s | %s -> %s | %s"
                    % (
                        index,
                        patch.target_location.table_index,
                        patch.target_location.row_index,
                        patch.target_location.column_index,
                        patch.target_location.row_context,
                        patch.target_location.column_context,
                        patch.correction.from_value,
                        patch.correction.to_value,
                        patch.reason or "无",
                    )
                )
        elif (
            AuditWriter._is_meaningful_location(patch_plan.target_location.model_dump())
            or patch_plan.correction.from_value is not None
            or patch_plan.correction.to_value is not None
        ):
            lines.append("【候选修正】")
            lines.append(
                "  table=%s row=%s col=%s row_context=%s column_context=%s | %s -> %s"
                % (
                    patch_plan.target_location.table_index,
                    patch_plan.target_location.row_index,
                    patch_plan.target_location.column_index,
                    patch_plan.target_location.row_context,
                    patch_plan.target_location.column_context,
                    patch_plan.correction.from_value,
                    patch_plan.correction.to_value,
                )
            )
        if linked_patch is not None and linked_patch.reason:
            lines.append("【联动修正说明】%s" % linked_patch.reason)
        lines.append("【执行结果】%s" % patch_result.message)
        return "\n".join(lines)

    def _write_case_text_report(
        self,
        case_dir: Path,
        page_number: int,
        primary: ReviewResult,
        peer: ReviewResult,
        final_judge: FinalJudgeResult,
        linked_patch: Optional[LinkedPatchResult],
        patch_plan: PatchPlan,
        patch_result: PatchResult,
    ) -> None:
        report_path = case_dir / ("page_%04d_repair_report.txt" % page_number)
        lines = [
            "【修正复核报告 — 第 %s 页】" % page_number,
            self._final_status_text(final_judge, patch_result),
            "",
            "============================================================",
            "【主审模型: %s】" % primary.model_name,
            "============================================================",
            self._format_review_detail(primary),
            "",
            "============================================================",
            "【互评模型: %s】" % peer.model_name,
            "============================================================",
            self._format_review_detail(peer),
            "",
            "============================================================",
            "【最终裁决 / 修正执行】",
            "============================================================",
            self._format_final_detail(final_judge, linked_patch, patch_plan, patch_result),
            "",
        ]
        report_path.write_text("\n".join(lines), encoding="utf-8")

    def _write_summary_text(
        self,
        patch_results: List[PatchResult],
        needs_review_items: List[NeedsReviewItem],
        false_positive_items: List[FalsePositiveItem],
    ) -> None:
        entries = []
        for audit_path in sorted(self.evidence_dir.rglob("page_*_audit.json")):
            payload = json.loads(audit_path.read_text(encoding="utf-8"))
            entries.append(self._detailed_entry(payload))
        modified_entries = [item for item in entries if item["effective_final_decision"] == "modify"]
        false_positive_entries = [item for item in entries if item["effective_final_decision"] == "false_positive"]
        needs_review_entries = [item for item in entries if item["effective_final_decision"] == "needs_review"]
        all_pages = len(entries)
        modified_pages = len(modified_entries)
        false_positive_pages = len(false_positive_entries)
        needs_review_pages = len(needs_review_entries)
        summary_path = self.reports_dir / "repair_summary.txt"
        lines = [
            "======================================================================",
            "HTML 定向修正汇总报告",
            "======================================================================",
            "总问题页数: %s" % all_pages,
            "自动修正成功页数: %s" % modified_pages,
            "旧报告误报页数: %s" % false_positive_pages,
            "待人工复核页数: %s" % needs_review_pages,
            "",
            "【✅ 已自动修正的页面】",
        ]
        if modified_entries:
            for item in modified_entries:
                location = item.get("location") or {}
                lines.append(
                    "  - %s 第 %s 页: table=%s row=%s col=%s row_context=%s column_context=%s | %s -> %s | %s"
                    % (
                        item["case_name"],
                        item["page_number"],
                        location.get("table_index"),
                        location.get("row_index"),
                        location.get("column_index"),
                        location.get("row_context"),
                        location.get("column_context"),
                        item.get("original_value"),
                        item.get("corrected_value"),
                        item["reason"],
                    )
                )
        else:
            lines.append("  - 无")
        lines.extend(["", "【ℹ️ 旧报告误报的页面】"])
        if false_positive_entries:
            for item in false_positive_entries:
                location = item.get("location") or {}
                lines.append(
                    "  - %s 第 %s 页: table=%s row=%s col=%s row_context=%s column_context=%s | 当前值=%s | 误报原因=%s"
                    % (
                        item["case_name"],
                        item["page_number"],
                        location.get("table_index"),
                        location.get("row_index"),
                        location.get("column_index"),
                        location.get("row_context"),
                        location.get("column_context"),
                        item.get("original_value"),
                        item["reason"],
                    )
                )
        else:
            lines.append("  - 无")
        lines.extend(["", "【⚠️ 待人工复核的页面】"])
        if needs_review_entries:
            for item in needs_review_entries:
                location = item.get("location") or {}
                lines.append(
                    "  - %s 第 %s 页: table=%s row=%s col=%s row_context=%s column_context=%s | 候选值=%s -> %s | 未修原因=%s"
                    % (
                        item["case_name"],
                        item["page_number"],
                        location.get("table_index"),
                        location.get("row_index"),
                        location.get("column_index"),
                        location.get("row_context"),
                        location.get("column_context"),
                        item.get("original_value"),
                        item.get("corrected_value"),
                        item["reason"],
                    )
                )
        else:
            lines.append("  - 无")
        summary_path.write_text("\n".join(lines), encoding="utf-8")

    @staticmethod
    def _is_meaningful_location(location: Dict[str, object]) -> bool:
        return any(location.get(key) not in (None, "") for key in ("table_index", "row_index", "column_index", "row_context", "column_context"))

    @staticmethod
    def _pick_location(payload: Dict[str, object]) -> Dict[str, object]:
        candidates = []
        patch_plan = payload.get("patch_plan") or {}
        patches = patch_plan.get("patches") or []
        if patches:
            candidates.append((patches[0].get("target_location") or {}))
        candidates.append(patch_plan.get("target_location") or {})
        for key in ("final_judge", "primary", "peer"):
            item = payload.get(key) or {}
            candidates.append(item.get("target_location") or {})
        for candidate in candidates:
            if AuditWriter._is_meaningful_location(candidate):
                return candidate
        return {}

    @staticmethod
    def _pick_correction(payload: Dict[str, object]) -> Dict[str, object]:
        candidates = []
        patch_plan = payload.get("patch_plan") or {}
        patches = patch_plan.get("patches") or []
        if patches:
            candidates.append((patches[0].get("correction") or {}))
        candidates.append(patch_plan.get("correction") or {})
        for key in ("final_judge", "primary", "peer"):
            item = payload.get(key) or {}
            candidates.append(item.get("correction") or {})
        for candidate in candidates:
            if candidate.get("from") is not None or candidate.get("to") is not None:
                return candidate
        return {}

    @staticmethod
    def _build_patch_items(payload: Dict[str, object]) -> List[Dict[str, object]]:
        patch_plan = payload.get("patch_plan") or {}
        patches = patch_plan.get("patches") or []
        items = []
        for patch in patches:
            items.append(
                {
                    "location": patch.get("target_location") or {},
                    "original_value": (patch.get("correction") or {}).get("from"),
                    "corrected_value": (patch.get("correction") or {}).get("to"),
                    "reason": patch.get("reason") or "",
                }
            )
        if items:
            return items
        correction = AuditWriter._pick_correction(payload)
        location = AuditWriter._pick_location(payload)
        if correction or location:
            return [
                {
                    "location": location,
                    "original_value": correction.get("from"),
                    "corrected_value": correction.get("to"),
                    "reason": (patch_plan.get("reason") or ""),
                }
            ]
        return []

    @staticmethod
    def _detailed_entry(payload: Dict[str, object]) -> Dict[str, object]:
        patch_plan = payload.get("patch_plan") or {}
        patch_result = payload.get("patch_result") or {}
        effective = payload.get("effective_final_decision") or "needs_review"
        patches = AuditWriter._build_patch_items(payload)
        location = AuditWriter._pick_location(payload)
        correction = AuditWriter._pick_correction(payload)
        return {
            "case_name": patch_plan.get("case_name"),
            "page_number": patch_plan.get("page_number"),
            "effective_final_decision": effective,
            "model_final_decision": (payload.get("final_judge") or {}).get("final_decision"),
            "modified": patch_result.get("modified", False),
            "modified_cells": patch_result.get("modified_cells", 0),
            "output_html_path": patch_result.get("output_html_path"),
            "location": location,
            "original_value": correction.get("from"),
            "corrected_value": correction.get("to"),
            "patches": patches,
            "reason": patch_result.get("message") or patch_plan.get("reason") or "",
        }

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
            "effective_final_decision": self._effective_final_decision(final_judge, patch_result),
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
        self._write_case_text_report(
            case_dir=case_dir,
            page_number=page_number,
            primary=primary,
            peer=peer,
            final_judge=final_judge,
            linked_patch=linked_patch,
            patch_plan=patch_plan,
            patch_result=patch_result,
        )

    def write_summary(
        self,
        patch_results: List[PatchResult],
        needs_review_items: List[NeedsReviewItem],
        false_positive_items: List[FalsePositiveItem],
    ) -> None:
        correction_summary = []
        needs_review = []
        false_positive = []
        for audit_path in sorted(self.evidence_dir.rglob("page_*_audit.json")):
            payload = json.loads(audit_path.read_text(encoding="utf-8"))
            entry = self._detailed_entry(payload)
            effective = entry["effective_final_decision"]
            if effective == "modify":
                correction_summary.append(entry)
            elif effective == "false_positive":
                false_positive.append(entry)
            else:
                needs_review.append(entry)
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
        self._write_summary_text(patch_results, needs_review_items, false_positive_items)
