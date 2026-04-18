import json
from pathlib import Path
from typing import Optional

from rate_table_repair.schemas.report import VerificationSummary


def load_verification_summary(path: Path) -> VerificationSummary:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return VerificationSummary(**data)


def load_old_issue_summary(result_json_path: Optional[Path]) -> Optional[str]:
    if result_json_path is None or not result_json_path.exists():
        return None
    with result_json_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    model1 = (data.get("model1_result") or {}).get("details", "")
    model2 = (data.get("model2_result") or {}).get("details", "")
    parts = [text.strip() for text in [model1, model2] if text and text.strip()]
    return "\n\n".join(parts) if parts else None
