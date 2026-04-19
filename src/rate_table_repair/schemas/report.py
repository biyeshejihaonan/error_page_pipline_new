from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field


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


class OldIssueHint(BaseModel):
    text: str
    row_context: Optional[str] = None
    column_index: Optional[int] = None
    column_context: Optional[str] = None
    current_value: Optional[str] = None
    correct_value: Optional[str] = None


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
    old_issue_hints: List[OldIssueHint] = Field(default_factory=list)

    class Config:
        arbitrary_types_allowed = True
