import json
from pathlib import Path

from bs4 import BeautifulSoup

from rate_table_repair.llm.client import OpenAICompatibleClient
from rate_table_repair.llm.json_parser import normalize_linked_patch_json, parse_json_object
from rate_table_repair.schemas.evidence import EvidencePackage
from rate_table_repair.schemas.review import FinalJudgeResult, LinkedPatchResult, ReviewResult


PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts" / "linked_patch.txt"


class LinkedPatchResolver:
    def __init__(self, model_config, dry_run: bool = False) -> None:
        self.model_config = model_config
        self.dry_run = dry_run
        self.client = OpenAICompatibleClient(model_config) if not dry_run else None

    @staticmethod
    def _build_candidate_rows(evidence: EvidencePackage, row_context: str) -> str:
        soup = BeautifulSoup(evidence.html_page_context.html_fragment, "html.parser")
        rows_text = []
        for table_index, table in enumerate(soup.find_all("table")):
            rows = table.find_all("tr")
            for row_index, row in enumerate(rows):
                cells = [cell.get_text(strip=True) for cell in row.find_all(["td", "th"])]
                if cells and cells[0] == row_context:
                    start = max(0, row_index - 2)
                    end = min(len(rows), row_index + 3)
                    rows_text.append("候选表格 %s / 行 %s" % (table_index, row_index))
                    for ctx_index in range(start, end):
                        ctx_cells = [cell.get_text(strip=True) for cell in rows[ctx_index].find_all(["td", "th"])]
                        rows_text.append("row[%s]=%s" % (ctx_index, ctx_cells))
        return "\n".join(rows_text[:40])

    def review(
        self,
        evidence: EvidencePackage,
        primary_result: ReviewResult,
        peer_result: ReviewResult,
        final_judge: FinalJudgeResult,
    ) -> LinkedPatchResult:
        if self.dry_run:
            return LinkedPatchResult(
                role="linked_patch",
                model_name=str(self.model_config["name"]),
                confidence="dry-run",
                reason="Dry run: linked patch resolver not executed.",
            )

        assert self.client is not None
        row_context = primary_result.target_location.row_context or peer_result.target_location.row_context or ""
        candidate_rows = self._build_candidate_rows(evidence, row_context) if row_context else ""
        extra = "主审结果：\n%s\n\n互评结果：\n%s\n\n最终裁决结果：\n%s" % (
            json.dumps(primary_result.raw_json or {"reason": primary_result.reason}, ensure_ascii=False, indent=2),
            json.dumps(peer_result.raw_json or {"reason": peer_result.reason}, ensure_ascii=False, indent=2),
            json.dumps(final_judge.raw_json or {"reason": final_judge.reason, "raw_text": final_judge.raw_text}, ensure_ascii=False, indent=2),
        )
        if candidate_rows:
            extra += "\n\n【候选行上下文】\n%s" % candidate_rows
        prompt = self.client.build_prompt(
            PROMPT_PATH,
            evidence,
            extra_text=extra,
            html_limit=2500,
            table_limit=0,
            max_tables=0,
        )
        raw_text = ""
        raw_json = {}
        for attempt in range(2):
            attempt_prompt = prompt
            if attempt > 0:
                attempt_prompt += (
                    "\n\n上一条回答没有返回完整 JSON。"
                    "现在只返回一行完整 JSON。"
                    "reason 控制在 20 个汉字内。"
                )
            raw_text = self.client.chat_json(
                str(self.model_config["model_id"]),
                attempt_prompt,
                evidence,
            )
            raw_json = normalize_linked_patch_json(parse_json_object(raw_text))
            if raw_json:
                break

        return LinkedPatchResult(
            role="linked_patch",
            model_name=str(self.model_config["name"]),
            raw_text=raw_text,
            raw_json=raw_json,
            **raw_json,
        )
