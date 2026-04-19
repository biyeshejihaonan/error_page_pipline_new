import json
from pathlib import Path

from rate_table_repair.llm.client import OpenAICompatibleClient
from rate_table_repair.llm.json_parser import normalize_final_judge_json, parse_json_object
from rate_table_repair.schemas.evidence import EvidencePackage
from rate_table_repair.schemas.review import FinalJudgeResult, ReviewResult


PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts" / "final_judge.txt"


def _trim_text(text: str, limit: int = 80) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit]


def _compact_review_payload(result: ReviewResult) -> dict:
    payload = {
        "is_real_error": result.is_real_error,
        "confidence": result.confidence,
        "reason": _trim_text(result.reason, 60),
        "target_location": result.target_location.model_dump(exclude_none=True),
        "correction": result.correction.model_dump(by_alias=True, exclude_none=True),
        "concerns": [_trim_text(item, 40) for item in result.concerns[:2]],
    }
    return {key: value for key, value in payload.items() if value not in (None, "", [], {})}


def _is_complete_modify_result(payload: dict) -> bool:
    if not payload:
        return False
    if payload.get("final_decision") != "modify" or payload.get("should_modify_html") is not True:
        return True
    patches = payload.get("patches") or []
    if not patches:
        return False
    for patch in patches:
        correction = patch.get("correction") or {}
        if correction.get("from") is None or correction.get("to") is None:
            return False
    return True


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
        primary_payload = _compact_review_payload(primary_result)
        peer_payload = _compact_review_payload(peer_result)
        extra = "主审结果：\n%s\n\n互评结果：\n%s" % (
            json.dumps(primary_payload, ensure_ascii=False, indent=2),
            json.dumps(peer_payload, ensure_ascii=False, indent=2),
        )
        prompt = self.client.build_prompt(
            PROMPT_PATH,
            evidence,
            extra_text=extra,
            html_limit=4500,
            table_limit=1800,
            max_tables=1,
        )
        raw_text = ""
        raw_json = {}
        for attempt in range(3):
            attempt_prompt = prompt
            if attempt > 0:
                attempt_prompt = (
                    prompt_path_read := PROMPT_PATH.read_text(encoding="utf-8")
                ) + (
                    "\n\n只返回一行完整 JSON。"
                    "\n不要 markdown，不要解释。"
                    "\n如果 final_decision=modify，patches 中每一项都必须同时包含 correction.from 和 correction.to。"
                    "\n如果不能给出完整 from/to，就返回 needs_review。"
                    "\nreason 不超过 16 个汉字。"
                    f"\n\n【案件】{evidence.case_name}\n【页码】{evidence.page_number}\n"
                    f"\n【补充上下文】\n{extra}\n"
                )
            raw_text = self.client.chat_json(
                str(self.model_config["model_id"]),
                attempt_prompt,
                evidence,
                max_tokens=6000,
            )
            raw_json = normalize_final_judge_json(parse_json_object(raw_text))
            if _is_complete_modify_result(raw_json):
                break
        return FinalJudgeResult(
            role="final_judge",
            model_name=str(self.model_config["name"]),
            raw_text=raw_text,
            raw_json=raw_json,
            **raw_json,
        )
