#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from rate_table_repair.html.patcher import HtmlPatcher
from rate_table_repair.schemas.patch import PatchPlan


SUCCESS_MARKER = "【最终状态】✅ 已自动修正"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="根据修正 txt 报告重建 corrected_html")
    parser.add_argument(
        "--output-root",
        default="output/full_batch_run_v3",
        help="包含 evidence/reports/corrected_html 的输出目录",
    )
    return parser.parse_args()


def load_modified_audits(evidence_root: Path) -> dict[str, list[Path]]:
    grouped: dict[str, list[Path]] = defaultdict(list)
    for report_path in sorted(evidence_root.rglob("page_*_repair_report.txt")):
        report_text = report_path.read_text(encoding="utf-8")
        if SUCCESS_MARKER not in report_text:
            continue
        audit_path = report_path.with_name(report_path.name.replace("_repair_report.txt", "_audit.json"))
        if not audit_path.exists():
            continue
        grouped[report_path.parent.name].append(audit_path)
    return grouped


def rebuild_case(case_name: str, audit_paths: list[Path], corrected_root: Path) -> tuple[int, Path]:
    patcher = HtmlPatcher()
    output_html_path: Path | None = None
    applied = 0

    for audit_path in sorted(audit_paths):
        payload = json.loads(audit_path.read_text(encoding="utf-8"))
        patch_result = payload.get("patch_result") or {}
        if not patch_result.get("modified"):
            continue
        plan = PatchPlan.model_validate(payload["patch_plan"])
        if output_html_path is None:
            output_html_path = corrected_root / case_name / plan.html_path.name
            if output_html_path.exists():
                output_html_path.unlink()
        result = patcher.apply(plan, output_html_path)
        if not result.modified:
            raise RuntimeError(f"{case_name} / {audit_path.name} 重放失败: {result.message}")
        applied += 1

    if output_html_path is None:
        raise RuntimeError(f"{case_name} 没有可重放的修改页")
    return applied, output_html_path


def main() -> int:
    args = parse_args()
    output_root = Path(args.output_root)
    evidence_root = output_root / "evidence"
    corrected_root = output_root / "corrected_html"
    if not evidence_root.exists():
        raise SystemExit(f"evidence 目录不存在: {evidence_root}")

    grouped = load_modified_audits(evidence_root)
    total_cases = 0
    total_pages = 0
    for case_name, audit_paths in sorted(grouped.items()):
        applied, output_html_path = rebuild_case(case_name, audit_paths, corrected_root)
        total_cases += 1
        total_pages += applied
        print(f"{case_name}: replayed_pages={applied} -> {output_html_path}")

    print(
        json.dumps(
            {
                "output_root": str(output_root),
                "cases_rebuilt": total_cases,
                "modified_pages_replayed": total_pages,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
