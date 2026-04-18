from pathlib import Path

from rate_table_repair.llm.client import OpenAICompatibleClient
from rate_table_repair.llm.json_parser import normalize_review_json, parse_json_object
from rate_table_repair.schemas.evidence import EvidencePackage
from rate_table_repair.schemas.review import ReviewResult


PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts" / "primary_review.txt"


class PrimaryReviewer:
    def __init__(self, model_config, dry_run: bool = False) -> None:
        self.model_config = model_config
        self.dry_run = dry_run
        self.client = OpenAICompatibleClient(model_config) if not dry_run else None

    def review(self, evidence: EvidencePackage) -> ReviewResult:
        if self.dry_run:
            return ReviewResult(
                role="primary_reviewer",
                model_name=str(self.model_config["name"]),
                confidence="dry-run",
                reason="Dry run: primary reviewer not executed.",
            )
        assert self.client is not None
        prompt = self.client.build_prompt(PROMPT_PATH, evidence)
        raw_text = ""
        raw_json = {}
        for attempt in range(2):
            attempt_prompt = prompt
            if attempt > 0:
                attempt_prompt += "\n\n上一条回答没有返回完整 JSON。现在只返回一个完整 JSON 对象，不要 markdown 代码块，不要额外解释。"
            raw_text = self.client.chat_json(
                str(self.model_config["model_id"]),
                attempt_prompt,
                evidence,
            )
            raw_json = normalize_review_json(parse_json_object(raw_text))
            if raw_json:
                break
        return ReviewResult(
            role="primary_reviewer",
            model_name=str(self.model_config["name"]),
            raw_text=raw_text,
            raw_json=raw_json,
            **raw_json,
        )
