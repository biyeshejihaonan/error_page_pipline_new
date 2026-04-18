import argparse
import json
from pathlib import Path

from rate_table_repair.pipeline.repair_pipeline import RepairPipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Targeted HTML repair framework")
    parser.add_argument(
        "--root",
        default="第一批采集结果（源于重疾险1.zip）",
        help="包含费率文件目录的根目录",
    )
    parser.add_argument(
        "--output",
        default="output/framework_run",
        help="输出目录",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="仅处理前 N 个存在问题的案例，0 表示不限制",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只跑框架，不实际调用模型或修改 HTML",
    )
    parser.add_argument(
        "--selection-file",
        default="",
        help="JSON 文件，内容为 [{\"case_name\":...,\"page_number\":...}]",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    pipeline = RepairPipeline(
        dataset_root=Path(args.root),
        output_root=Path(args.output),
        dry_run=args.dry_run,
        limit=args.limit,
        selection_file=Path(args.selection_file) if args.selection_file else None,
    )
    result = pipeline.run()
    print(json.dumps(result, ensure_ascii=False, indent=2))
