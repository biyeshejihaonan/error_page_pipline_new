import base64
from pathlib import Path
from typing import Dict, List

import httpx
from openai import OpenAI

from rate_table_repair.schemas.evidence import EvidencePackage


class OpenAICompatibleClient:
    def __init__(self, model_config: Dict[str, object]) -> None:
        self.model_config = model_config
        self.client = OpenAI(
            api_key=str(model_config["api_key"]),
            base_url=str(model_config["base_url"]),
            timeout=120,
            http_client=httpx.Client(trust_env=False, timeout=120),
        )

    def _supports_images(self) -> bool:
        return str(self.model_config.get("type", "")).lower() == "vision"

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
        if evidence.old_issue_summary:
            prompt += "\n【旧报告疑点】\n%s\n" % evidence.old_issue_summary
        prompt += "\n【HTML页面片段】\n%s\n" % evidence.html_page_context.html_fragment[:html_limit]
        prompt += "\n【MinerU表格数量】%s\n" % len(evidence.mineru_tables)
        for table in evidence.mineru_tables[:max_tables]:
            prompt += "\n【表格 %s 标题】%s\n" % (table.table_index, " ".join(table.caption))
            prompt += "【表格HTML】\n%s\n" % table.table_html[:table_limit]
        if extra_text:
            prompt += "\n【补充上下文】\n%s\n" % extra_text
        return prompt

    def _build_user_content(self, prompt: str, evidence: EvidencePackage) -> List[Dict[str, object]]:
        content: List[Dict[str, object]] = [{"type": "text", "text": prompt}]
        if self._supports_images() and evidence.rendered_page_image and evidence.rendered_page_image.exists():
            image_data = base64.b64encode(evidence.rendered_page_image.read_bytes()).decode("utf-8")
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,%s" % image_data},
                }
            )
        return content

    @staticmethod
    def _extract_text(response: object) -> str:
        choices = getattr(response, "choices", None)
        if choices:
            content = choices[0].message.content
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                text_chunks = [item.get("text", "") for item in content if isinstance(item, dict)]
                return "\n".join(chunk for chunk in text_chunks if chunk).strip()

        base_resp = getattr(response, "base_resp", None)
        if base_resp is not None:
            status_code = getattr(base_resp, "status_code", None)
            status_msg = getattr(base_resp, "status_msg", None)
            raise RuntimeError(f"model returned no choices: status_code={status_code}, status_msg={status_msg}")

        raise RuntimeError(f"model returned no choices: {response!r}")

    def chat_json(self, model_name: str, prompt: str, evidence: EvidencePackage) -> str:
        response = self.client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": self._build_user_content(prompt, evidence)}],
            stream=False,
            max_tokens=4000,
            temperature=0,
        )
        return self._extract_text(response)
