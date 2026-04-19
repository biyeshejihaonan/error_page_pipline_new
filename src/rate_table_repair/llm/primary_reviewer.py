from pathlib import Path
import json

from rate_table_repair.llm.client import OpenAICompatibleClient
from rate_table_repair.llm.json_parser import normalize_review_json, parse_json_object
from rate_table_repair.schemas.evidence import EvidencePackage
from rate_table_repair.schemas.review import ReviewResult


PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts" / "primary_review.txt"


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


def _is_glm_model(model_name: str) -> bool:
    return model_name.lower().startswith("glm-")


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
        attempts = [
            {
                "prompt": prompt,
                "image_first": False,
                "max_tokens": None,
            },
            {
                "prompt": prompt
                + "\n\n上一条回答没有返回完整 JSON。现在只返回一个完整 JSON 对象，不要 markdown 代码块，不要额外解释。",
                "image_first": False,
                "max_tokens": None,
            },
        ]
        if _is_glm_model(str(self.model_config["model_id"])):
            minimal_prompt = (
                PROMPT_PATH.read_text(encoding="utf-8")
                + "\n\n只根据附图和少量HTML做判断。"
                + "\n优先看图片，不要声称缺少图像。"
                + "\n如果图里看得到，就直接给 JSON。"
                + "\n看不清再返回 uncertain。"
                + f"\n\n【案件】{evidence.case_name}\n【页码】{evidence.page_number}\n"
                + "\n【HTML页面片段】\n"
                + evidence.html_page_context.html_fragment[:2500]
                + "\n【旧报告疑点】\n"
                + (evidence.old_issue_summary or "无")
            )
            attempts.append(
                {
                    "prompt": minimal_prompt,
                    "image_first": True,
                    "max_tokens": 2500,
                }
            )
        for attempt in attempts:
            raw_text = self.client.chat_json(
                str(self.model_config["model_id"]),
                attempt["prompt"],
                evidence,
                image_first=bool(attempt["image_first"]),
                max_tokens=attempt["max_tokens"],
            )
            raw_json = normalize_review_json(parse_json_object(raw_text))
            if raw_json and not (
                evidence.rendered_page_image is not None
                and (
                    "未提供PDF图像证据" in (raw_json.get("reason") or "")
                    or "缺少PDF页面图像" in "\n".join(raw_json.get("concerns") or [])
                )
            ):
                break
        result = ReviewResult(
            role="primary_reviewer",
            model_name=str(self.model_config["name"]),
            raw_text=raw_text,
            raw_json=raw_json,
            **raw_json,
        )
        return _normalize_consistency(result)
