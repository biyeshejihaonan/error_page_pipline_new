from pathlib import Path

from rate_table_repair.evidence.html_context import extract_html_page_context
from rate_table_repair.mineru.adapter import MineruAdapter
from rate_table_repair.mineru.page_assets import render_split_pdf_to_png
from rate_table_repair.schemas.evidence import EvidencePackage
from rate_table_repair.schemas.report import PageIssue


class EvidenceBuilder:
    def __init__(
        self,
        mineru_adapter: MineruAdapter,
        rendered_pages_dir: Path,
        table_crops_dir: Path,
        row_crops_dir: Path,
    ) -> None:
        self.mineru_adapter = mineru_adapter
        self.rendered_pages_dir = rendered_pages_dir
        self.table_crops_dir = table_crops_dir
        self.row_crops_dir = row_crops_dir

    def build(self, issue: PageIssue) -> EvidencePackage:
        html_text = issue.html_path.read_text(encoding="utf-8")
        html_context = extract_html_page_context(html_text, issue.page_number)
        mineru_tables = self.mineru_adapter.get_page_tables(issue.mineru_page_dir)
        rendered_page_image = render_split_pdf_to_png(
            issue.split_page_pdf,
            self.rendered_pages_dir / issue.case_name,
        )
        return EvidencePackage(
            case_name=issue.case_name,
            page_number=issue.page_number,
            html_path=issue.html_path,
            split_page_pdf=issue.split_page_pdf,
            rendered_page_image=rendered_page_image,
            table_crop_images=[],
            row_crop_images=[],
            mineru_page_dir=issue.mineru_page_dir,
            verification_result_path=issue.verification_result_path,
            old_issue_summary=issue.old_issue_summary,
            old_issue_hints=issue.old_issue_hints,
            html_page_context=html_context,
            mineru_tables=mineru_tables,
        )

    def enrich_with_review_crops(
        self,
        evidence: EvidencePackage,
        reviews,
    ) -> EvidencePackage:
        return evidence
