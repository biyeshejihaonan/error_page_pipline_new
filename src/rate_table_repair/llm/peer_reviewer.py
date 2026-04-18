import json
from pathlib import Path

from rate_table_repair.llm.client import OpenAICompatibleClient
from rate_table_repair.llm.json_parser import normalize_review_json, parse_json_object
from rate_table_repair.schemas.evidence import EvidencePackage
from rate_table_repair.schemas.review import ReviewResult


PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts" / "peer_review.txt"


class PeerReviewer:
    def __init__(self, model_config, dry_run: bool = False) -> None:
        self.model_config = model_config
        self.dry_run = dry_run
        self.client = OpenAICompatibleClient(model_config) if not dry_run else None

    def review(self, evidence: EvidencePackage, primary_result: ReviewResult) -> ReviewResult:
        if self.dry_run:
            return ReviewResult(
                role="peer_reviewer",
                model_name=str(self.model_config["name"]),
                confidence="dry-run",
                reason="Dry run: peer reviewer not executed.",
            )
        assert self.client is not None
        primary_payload = primary_result.raw_json or {"reason": primary_result.reason, "raw_text": primary_result.raw_text}
        extra = "主审模型输出如下：\n%s" % json.dumps(primary_payload, ensure_ascii=False, indent=2)
        prompt = self.client.build_prompt(PROMPT_PATH, evidence, extra_text=extra)
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
            role="peer_reviewer",
            model_name=str(self.model_config["name"]),
            raw_text=raw_text,
            raw_json=raw_json,
            **raw_json,
        )
