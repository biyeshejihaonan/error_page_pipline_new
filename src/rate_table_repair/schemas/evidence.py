from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel


class MineruTableEvidence(BaseModel):
    table_index: int
    page_idx: int
    caption: List[str]
    footnote: List[str]
    table_html: str
    bbox: List[int]
    image_path: Optional[str] = None


class HtmlPageContext(BaseModel):
    page_number: int
    page_title: Optional[str]
    table_count: int
    html_fragment: str


class EvidencePackage(BaseModel):
    case_name: str
    page_number: int
    html_path: Path
    split_page_pdf: Optional[Path]
    rendered_page_image: Optional[Path]
    mineru_page_dir: Optional[Path]
    verification_result_path: Optional[Path]
    old_issue_summary: Optional[str]
    html_page_context: HtmlPageContext
    mineru_tables: List[MineruTableEvidence]

    class Config:
        arbitrary_types_allowed = True
