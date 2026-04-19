from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
import json

from rate_table_repair.config.loader import load_model_roles
from rate_table_repair.decision.rules import build_patch_plan
from rate_table_repair.evidence.builder import EvidenceBuilder
from rate_table_repair.html.patcher import HtmlPatcher
from rate_table_repair.llm.final_judge import FinalJudge
from rate_table_repair.llm.linked_patch_resolver import LinkedPatchResolver
from rate_table_repair.llm.peer_reviewer import PeerReviewer
from rate_table_repair.llm.primary_reviewer import PrimaryReviewer
from rate_table_repair.mineru.adapter import MineruAdapter
from rate_table_repair.reports.audit_writer import AuditWriter
from rate_table_repair.scanners.issue_selector import build_issue, select_issues
from rate_table_repair.scanners.project_scanner import scan_cases
from rate_table_repair.scanners.report_loader import load_verification_summary
from rate_table_repair.schemas.patch import FalsePositiveItem, NeedsReviewItem, PatchResult
from rate_table_repair.schemas.review import FinalJudgeResult, ReviewResult


class RepairPipeline:
    def __init__(
        self,
        dataset_root: Path,
        output_root: Path,
        dry_run: bool = False,
        limit: int = 0,
        selection_file: Optional[Path] = None,
    ) -> None:
        self.dataset_root = dataset_root
        self.output_root = output_root
        self.dry_run = dry_run
        self.limit = limit
        self.selection = self._load_selection(selection_file)
        roles = load_model_roles()
        self.primary_reviewer = PrimaryReviewer(roles["primary_reviewer"], dry_run=dry_run)
        self.peer_reviewer = PeerReviewer(roles["peer_reviewer"], dry_run=dry_run)
        self.final_judge = FinalJudge(roles["final_judge"], dry_run=dry_run)
        self.linked_patch_resolver = LinkedPatchResolver(roles["final_judge"], dry_run=dry_run)
        self.html_patcher = HtmlPatcher()
        self.audit_writer = AuditWriter(output_root)
        self.evidence_builder = EvidenceBuilder(
            MineruAdapter(),
            self.audit_writer.evidence_dir / "rendered_pages",
            self.audit_writer.evidence_dir / "table_crops",
            self.audit_writer.evidence_dir / "row_crops",
        )

    def _load_selection(self, selection_file: Optional[Path]) -> Optional[Set[Tuple[str, int]]]:
        if selection_file is None:
            return None
        data = json.loads(selection_file.read_text(encoding="utf-8"))
        result: Set[Tuple[str, int]] = set()
        for item in data:
            result.add((item["case_name"], int(item["page_number"])))
        return result

    def run(self) -> Dict[str, object]:
        cases = scan_cases(self.dataset_root)
        issue_count = 0
        patch_results: List[PatchResult] = []
        needs_review_items: List[NeedsReviewItem] = []
        false_positive_items: List[FalsePositiveItem] = []

        for case in cases:
            case.summary = load_verification_summary(case.verification_summary_path)
            selected_pages_for_case = None
            if self.selection is not None:
                selected_pages_for_case = sorted(
                    page_number
                    for case_name, page_number in self.selection
                    if case_name == case.name
                )
                if not selected_pages_for_case:
                    continue
            if not case.summary.has_issues and not selected_pages_for_case:
                continue
            issues = (
                [build_issue(case, page_number) for page_number in selected_pages_for_case]
                if selected_pages_for_case
                else select_issues(case)
            )
            for issue in issues:
                if self.limit and issue_count >= self.limit:
                    break
                issue_count += 1

                evidence = self.evidence_builder.build(issue)
                linked_patch = None
                try:
                    primary = self.primary_reviewer.review(evidence)
                    evidence = self.evidence_builder.enrich_with_review_crops(evidence, [primary])
                    peer = self.peer_reviewer.review(evidence, primary)
                    evidence = self.evidence_builder.enrich_with_review_crops(evidence, [primary, peer])
                    final_judge = self.final_judge.review(evidence, primary, peer)
                    patch_plan = build_patch_plan(issue, final_judge)
                    if (
                        not patch_plan.should_modify
                        and final_judge.final_decision != "false_positive"
                        and primary.is_real_error
                        and peer.is_real_error
                    ):
                        linked_patch = self.linked_patch_resolver.review(evidence, primary, peer, final_judge)
                        patch_plan = build_patch_plan(
                            issue,
                            final_judge,
                            primary=primary,
                            peer=peer,
                            linked_patch=linked_patch,
                        )
                except Exception as exc:
                    primary = ReviewResult(
                        role="primary_reviewer",
                        model_name=str(self.primary_reviewer.model_config["name"]),
                        reason="模型调用失败，未完成主审",
                    )
                    peer = ReviewResult(
                        role="peer_reviewer",
                        model_name=str(self.peer_reviewer.model_config["name"]),
                        reason="模型调用失败，未完成互评",
                    )
                    final_judge = FinalJudgeResult(
                        role="final_judge",
                        model_name=str(self.final_judge.model_config["name"]),
                        final_decision="needs_review",
                        should_modify_html=False,
                        reason=f"模型调用失败：{exc}",
                    )
                    patch_plan = build_patch_plan(issue, final_judge)

                output_html_path = self.audit_writer.corrected_dir / issue.case_name / issue.html_path.name
                patch_result = self.html_patcher.apply(patch_plan, output_html_path)
                patch_results.append(patch_result)

                if not patch_result.modified:
                    if final_judge.final_decision == "false_positive":
                        false_positive_items.append(
                            FalsePositiveItem(
                                case_name=issue.case_name,
                                page_number=issue.page_number,
                                reason=final_judge.reason or patch_result.message or "旧报告误报",
                            )
                        )
                    else:
                        needs_review_items.append(
                            NeedsReviewItem(
                                case_name=issue.case_name,
                                page_number=issue.page_number,
                                reason=patch_result.message or patch_plan.reason or "未自动修正",
                            )
                        )

                self.audit_writer.write_case_audit(
                    case_name=issue.case_name,
                    page_number=issue.page_number,
                    primary=primary,
                    peer=peer,
                    final_judge=final_judge,
                    linked_patch=linked_patch,
                    patch_plan=patch_plan,
                    patch_result=patch_result,
                )

            if self.limit and issue_count >= self.limit:
                break

        self.audit_writer.write_summary(patch_results, needs_review_items, false_positive_items)
        return {
            "dataset_root": str(self.dataset_root),
            "output_root": str(self.output_root),
            "dry_run": self.dry_run,
            "cases_scanned": len(cases),
            "issues_processed": issue_count,
            "patches_written": len([item for item in patch_results if item.modified]),
            "needs_review": len(needs_review_items),
            "false_positive": len(false_positive_items),
        }
