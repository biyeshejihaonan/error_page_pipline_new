from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from rate_table_repair.schemas.review import CellLocation, Correction, PatchInstruction


class PatchPlan(BaseModel):
    case_name: str
    html_path: Path
    page_number: int
    should_modify: bool
    target_location: CellLocation
    correction: Correction
    patches: List[PatchInstruction]
    reason: str
    selection_source: str = ""
    selection_score: int = 0
    classification: str = "needs_review"
    support_votes: int = 0
    false_positive_votes: int = 0
    candidate_scores: List[Dict[str, Any]] = []

    class Config:
        arbitrary_types_allowed = True


class PatchResult(BaseModel):
    case_name: str
    output_html_path: Optional[Path] = None
    modified: bool = False
    modified_cells: int = 0
    message: str = ""

    class Config:
        arbitrary_types_allowed = True


class NeedsReviewItem(BaseModel):
    case_name: str
    page_number: int
    reason: str


class FalsePositiveItem(BaseModel):
    case_name: str
    page_number: int
    reason: str
