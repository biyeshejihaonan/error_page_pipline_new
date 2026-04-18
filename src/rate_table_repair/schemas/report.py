from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel


class VerificationSummary(BaseModel):
    pdf_name: str
    total_pages: int
    pages_with_tables: int
    pages_with_issues: List[int]
    pages_without_issues: List[int]
    has_issues: bool


class DocumentCase(BaseModel):
    name: str
    case_dir: Path
    html_path: Path
    verification_summary_path: Path
    verification_dir: Path
    mineru_pages_dir: Path
    split_pages_dir: Path
    summary: Optional[VerificationSummary] = None

    class Config:
        arbitrary_types_allowed = True


class PageIssue(BaseModel):
    case_name: str
    case_dir: Path
    html_path: Path
    page_number: int
    verification_result_path: Optional[Path] = None
    verification_report_path: Optional[Path] = None
    mineru_page_dir: Optional[Path] = None
    split_page_pdf: Optional[Path] = None
    old_issue_summary: Optional[str] = None

    class Config:
        arbitrary_types_allowed = True
