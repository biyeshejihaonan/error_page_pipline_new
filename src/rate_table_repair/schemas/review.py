from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CellLocation(BaseModel):
    table_index: Optional[int] = None
    row_index: Optional[int] = None
    column_index: Optional[int] = None
    row_context: Optional[str] = None
    column_context: Optional[str] = None


class Correction(BaseModel):
    from_value: Optional[str] = Field(default=None, alias="from")
    to_value: Optional[str] = Field(default=None, alias="to")

    class Config:
        populate_by_name = True


class PatchInstruction(BaseModel):
    target_location: CellLocation = Field(default_factory=CellLocation)
    correction: Correction = Field(default_factory=Correction)
    reason: str = ""


class ReviewResult(BaseModel):
    role: str
    model_name: str
    is_real_error: Optional[bool] = None
    confidence: str = "unknown"
    reason: str = ""
    target_location: CellLocation = Field(default_factory=CellLocation)
    correction: Correction = Field(default_factory=Correction)
    concerns: List[str] = Field(default_factory=list)
    raw_text: str = ""
    raw_json: Dict[str, Any] = Field(default_factory=dict)


class FinalJudgeResult(BaseModel):
    role: str
    model_name: str
    final_decision: str = "needs_review"
    should_modify_html: bool = False
    confidence: str = "unknown"
    reason: str = ""
    target_location_confirmed: bool = False
    target_location: CellLocation = Field(default_factory=CellLocation)
    correction: Correction = Field(default_factory=Correction)
    patches: List[PatchInstruction] = Field(default_factory=list)
    basis: Dict[str, Any] = Field(default_factory=dict)
    raw_text: str = ""
    raw_json: Dict[str, Any] = Field(default_factory=dict)
