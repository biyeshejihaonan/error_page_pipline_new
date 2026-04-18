import json
from pathlib import Path

from rate_table_repair.llm.client import OpenAICompatibleClient
from rate_table_repair.llm.json_parser import normalize_final_judge_json, parse_json_object
from rate_table_repair.schemas.evidence import EvidencePackage
from rate_table_repair.schemas.review import FinalJudgeResult, ReviewResult


PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts" / "final_judge.txt"


class FinalJudge:
    def __init__(self, model_config, dry_run: bool = False) -> None:
        self.model_config = model_config
        self.dry_run = dry_run
        self.client = OpenAICompatibleClient(model_config) if not dry_run else None

    def review(
        self,
        evidence: EvidencePackage,
        primary_result: ReviewResult,
        peer_result: ReviewResult,
    ) -> FinalJudgeResult:
        if self.dry_run:
            return FinalJudgeResult(
                role="final_judge",
                model_name=str(self.model_config["name"]),
                final_decision="needs_review",
                should_modify_html=False,
                confidence="dry-run",
                reason="Dry run: final judge not executed.",
            )
        assert self.client is not None
        primary_payload = primary_result.raw_json or {"reason": primary_result.reason, "raw_text": primary_result.raw_text}
        peer_payload = peer_result.raw_json or {"reason": peer_result.reason, "raw_text": peer_result.raw_text}
        extra = "主审结果：\n%s\n\n互评结果：\n%s" % (
            json.dumps(primary_payload, ensure_ascii=False, indent=2),
            json.dumps(peer_payload, ensure_ascii=False, indent=2),
        )
        prompt = self.client.build_prompt(
            PROMPT_PATH,
            evidence,
            extra_text=extra,
            html_limit=5000,
            table_limit=3500,
            max_tables=1,
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
                    "如果可自动修改，只返回必要字段："
                    "final_decision、should_modify_html、confidence、reason、target_location_confirmed、patches、basis。"
                    "不要 markdown，不要重复 top-level target_location/correction。"
                )
            raw_text = self.client.chat_json(
                str(self.model_config["model_id"]),
                attempt_prompt,
                evidence,
            )
            raw_json = normalize_final_judge_json(parse_json_object(raw_text))
            if raw_json:
                break
        return FinalJudgeResult(
            role="final_judge",
            model_name=str(self.model_config["name"]),
            raw_text=raw_text,
            raw_json=raw_json,
            **raw_json,
        )
