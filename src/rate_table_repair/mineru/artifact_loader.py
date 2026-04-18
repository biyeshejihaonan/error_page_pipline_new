import json
from pathlib import Path
from typing import List

from rate_table_repair.schemas.evidence import MineruTableEvidence


def load_content_list(mineru_page_dir: Path) -> List[dict]:
    content_path = mineru_page_dir / "page_0001_content_list.json"
    if not content_path.exists():
        return []
    with content_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_table_evidence(mineru_page_dir: Path) -> List[MineruTableEvidence]:
    table_items: List[MineruTableEvidence] = []
    for idx, item in enumerate(load_content_list(mineru_page_dir)):
        if item.get("type") != "table":
            continue
        table_items.append(
            MineruTableEvidence(
                table_index=idx,
                page_idx=int(item.get("page_idx", 0)),
                caption=list(item.get("table_caption", [])),
                footnote=list(item.get("table_footnote", [])),
                table_html=item.get("table_body", ""),
                bbox=list(item.get("bbox", [])),
                image_path=item.get("img_path"),
            )
        )
    return table_items
