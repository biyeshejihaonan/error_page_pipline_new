import base64
from pathlib import Path
import time
from typing import Dict, List, Optional

import httpx
from openai import OpenAI

from rate_table_repair.schemas.evidence import EvidencePackage


class OpenAICompatibleClient:
    def __init__(self, model_config: Dict[str, object]) -> None:
        self.model_config = model_config
        self.max_retries = 3
        self.client = OpenAI(
            api_key=str(model_config["api_key"]),
            base_url=str(model_config["base_url"]),
            timeout=120,
            http_client=httpx.Client(trust_env=False, timeout=120),
        )

    def _supports_images(self) -> bool:
        return str(self.model_config.get("type", "")).lower() == "vision"

    def _extra_body(self, model_name: str) -> Dict[str, object]:
        lower_name = model_name.lower()
        if lower_name.startswith("glm-"):
            return {
                "thinking": {"type": "disabled"},
                "do_sample": False,
            }
        return {}

    @staticmethod
    def _default_max_tokens(model_name: str) -> int:
        lower_name = model_name.lower()
        if "gemini" in lower_name:
            return 6000
        return 4000

    def build_prompt(
        self,
        prompt_path: Path,
        evidence: EvidencePackage,
        extra_text: str = "",
        html_limit: int = 12000,
        table_limit: int = 8000,
        max_tables: int = 3,
    ) -> str:
        prompt = prompt_path.read_text(encoding="utf-8")
        prompt += "\n\n【案件】%s\n【页码】%s\n" % (evidence.case_name, evidence.page_number)
        prompt += "\n【附图说明】仅提供当前页整页图。\n"
        if evidence.old_issue_summary:
            prompt += "\n【旧报告疑点】\n%s\n" % evidence.old_issue_summary
        if evidence.old_issue_hints:
            prompt += "\n【旧报告定位线索】\n"
            for hint in evidence.old_issue_hints[:8]:
                prompt += "- %s\n" % hint.model_dump_json(exclude_none=True, ensure_ascii=False)
        prompt += "\n【HTML页面片段】\n%s\n" % evidence.html_page_context.html_fragment[:html_limit]
        prompt += "\n【MinerU表格数量】%s\n" % len(evidence.mineru_tables)
        for table in evidence.mineru_tables[:max_tables]:
            prompt += "\n【表格 %s 标题】%s\n" % (table.table_index, " ".join(table.caption))
            prompt += "【表格HTML】\n%s\n" % table.table_html[:table_limit]
        if extra_text:
            prompt += "\n【补充上下文】\n%s\n" % extra_text
        return prompt

    def _build_user_content(
        self,
        prompt: str,
        evidence: EvidencePackage,
        image_first: bool = False,
    ) -> List[Dict[str, object]]:
        text_item: Dict[str, object] = {"type": "text", "text": prompt}
        image_items: List[Dict[str, object]] = []
        image_paths: List[Path] = []
        if evidence.rendered_page_image and evidence.rendered_page_image.exists():
            image_paths.append(evidence.rendered_page_image)
        if self._supports_images():
            for image_path in image_paths:
                image_data = base64.b64encode(image_path.read_bytes()).decode("utf-8")
                image_items.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/png;base64,%s" % image_data},
                    }
                )
        content: List[Dict[str, object]] = []
        if image_first and image_items:
            content.extend(image_items)
        content.append(text_item)
        if not image_first and image_items:
            content.extend(image_items)
        return content

    @staticmethod
    def _extract_text(response: object) -> str:
        choices = getattr(response, "choices", None)
        if choices:
            message = choices[0].message
            content = message.content
            if isinstance(content, str):
                if content.strip():
                    return content
            if isinstance(content, list):
                text_chunks = [item.get("text", "") for item in content if isinstance(item, dict)]
                joined = "\n".join(chunk for chunk in text_chunks if chunk).strip()
                if joined:
                    return joined

            reasoning_content = getattr(message, "reasoning_content", None)
            if reasoning_content:
                finish_reason = getattr(choices[0], "finish_reason", None)
                raise RuntimeError(
                    "model returned reasoning only without final content: "
                    f"finish_reason={finish_reason}"
                )

        base_resp = getattr(response, "base_resp", None)
        if base_resp is not None:
            status_code = getattr(base_resp, "status_code", None)
            status_msg = getattr(base_resp, "status_msg", None)
            raise RuntimeError(f"model returned no choices: status_code={status_code}, status_msg={status_msg}")

        raise RuntimeError(f"model returned no choices: {response!r}")

    def chat_json(
        self,
        model_name: str,
        prompt: str,
        evidence: EvidencePackage,
        image_first: bool = False,
        max_tokens: Optional[int] = None,
    ) -> str:
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.client.chat.completions.create(
                    model=model_name,
                    messages=[{"role": "user", "content": self._build_user_content(prompt, evidence, image_first=image_first)}],
                    stream=False,
                    max_tokens=max_tokens or self._default_max_tokens(model_name),
                    temperature=0,
                    extra_body=self._extra_body(model_name),
                )
                return self._extract_text(response)
            except Exception as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                time.sleep(min(2 * attempt, 5))
        assert last_error is not None
        raise last_error
