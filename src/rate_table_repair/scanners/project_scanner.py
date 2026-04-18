from pathlib import Path
from typing import List

from rate_table_repair.schemas.report import DocumentCase


def scan_cases(dataset_root: Path) -> List[DocumentCase]:
    if not dataset_root.exists():
        raise FileNotFoundError("数据目录不存在: %s" % dataset_root)

    cases: List[DocumentCase] = []
    for case_dir in sorted(path for path in dataset_root.iterdir() if path.is_dir()):
        verification_summary = case_dir / "_verification" / "_verification_summary.json"
        if not verification_summary.exists():
            continue
        html_candidates = sorted(case_dir.glob("*.html"))
        if not html_candidates:
            continue
        cases.append(
            DocumentCase(
                name=case_dir.name,
                case_dir=case_dir,
                html_path=html_candidates[0],
                verification_summary_path=verification_summary,
                verification_dir=case_dir / "_verification",
                mineru_pages_dir=case_dir / "_mineru_pages",
                split_pages_dir=case_dir / "_pages",
            )
        )
    return cases
