import json
from pathlib import Path

from rate_table_repair.llm.client import OpenAICompatibleClient
from rate_table_repair.llm.json_parser import normalize_review_json, parse_json_object
from rate_table_repair.schemas.evidence import EvidencePackage
from rate_table_repair.schemas.review import ReviewResult


PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts" / "peer_review.txt"


def _compact_review_payload(result: ReviewResult) -> dict:
    payload = {
        "is_real_error": result.is_real_error,
        "confidence": result.confidence,
        "reason": result.reason,
        "target_location": result.target_location.model_dump(exclude_none=True),
        "correction": result.correction.model_dump(by_alias=True, exclude_none=True),
        "concerns": result.concerns[:3],
    }
    return {key: value for key, value in payload.items() if value not in (None, "", [], {})}


def _is_glm_model(model_name: str) -> bool:
    return model_name.lower().startswith("glm-")


def _normalize_consistency(result: ReviewResult) -> ReviewResult:
    reason = result.reason or ""
    from_value = result.correction.from_value
    to_value = result.correction.to_value
    no_error_markers = ("一致", "无错误", "误报", "完全一致")
    if from_value is not None and to_value is not None and from_value == to_value:
        result.is_real_error = False
    if any(marker in reason for marker in no_error_markers):
        result.is_real_error = False
    return result


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
        primary_payload = _compact_review_payload(primary_result)
        extra = "主审模型输出如下：\n%s" % json.dumps(primary_payload, ensure_ascii=False, indent=2)
        prompt = self.client.build_prompt(
            PROMPT_PATH,
            evidence,
            extra_text=extra,
            html_limit=8000,
            table_limit=3000,
            max_tables=2,
        )
        raw_text = ""
        raw_json = {}
        last_error: Exception | None = None
        attempts = [
            {
                "prompt": prompt,
                "image_first": False,
            },
            {
                "prompt": prompt
                + (
                    "\n\n上一条回答没有返回完整 JSON。"
                    "现在只返回最小必要字段的完整 JSON："
                    "is_real_error、confidence、reason、target_location、correction、concerns。"
                    "不要 markdown，不要额外解释，reason 不超过 25 个汉字。"
                ),
                "image_first": False,
            },
        ]
        if _is_glm_model(str(self.model_config["model_id"])):
            fallback_prompt = self.client.build_prompt(
                PROMPT_PATH,
                evidence,
                extra_text=(
                    "你将看到 PDF 页图。以页图为主，主审只作参考。\n"
                    + json.dumps(primary_payload, ensure_ascii=False)
                    + "\n如果 HTML 片段不含目标行，不要长篇分析，直接给最短 JSON。"
                ),
                html_limit=2500,
                table_limit=1200,
                max_tables=1,
            )
            attempts.append(
                {
                    "prompt": fallback_prompt,
                    "image_first": True,
                }
            )
        for attempt in attempts:
            try:
                raw_text = self.client.chat_json(
                    str(self.model_config["model_id"]),
                    attempt["prompt"],
                    evidence,
                    image_first=bool(attempt["image_first"]),
                )
            except Exception as exc:
                last_error = exc
                raw_text = ""
                raw_json = {}
                continue
            raw_json = normalize_review_json(parse_json_object(raw_text))
            if raw_json and any(
                [
                    raw_json.get("is_real_error") is not None,
                    raw_json.get("reason"),
                    raw_json.get("correction"),
                    raw_json.get("target_location"),
                ]
            ):
                break
        if not raw_json and last_error is not None:
            return ReviewResult(
                role="peer_reviewer",
                model_name=str(self.model_config["name"]),
                confidence="unknown",
                reason=f"互评模型未返回最终内容：{last_error}",
                raw_text=raw_text,
                raw_json={},
            )
        result = ReviewResult(
            role="peer_reviewer",
            model_name=str(self.model_config["name"]),
            raw_text=raw_text,
            raw_json=raw_json,
            **raw_json,
        )
        return _normalize_consistency(result)
