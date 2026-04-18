from pathlib import Path
from typing import Dict, List, Optional

from rate_table_repair.mineru.artifact_loader import load_table_evidence
from rate_table_repair.schemas.evidence import MineruTableEvidence


class MineruAdapter:
    def __init__(self) -> None:
        self._cache: Dict[Path, List[MineruTableEvidence]] = {}

    def get_page_tables(self, mineru_page_dir: Optional[Path]) -> List[MineruTableEvidence]:
        if mineru_page_dir is None:
            return []
        if mineru_page_dir not in self._cache:
            self._cache[mineru_page_dir] = load_table_evidence(mineru_page_dir)
        return self._cache[mineru_page_dir]
