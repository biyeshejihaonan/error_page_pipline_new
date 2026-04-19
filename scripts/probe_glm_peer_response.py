from pathlib import Path
import json
import sys

import httpx
from openai import OpenAI


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rate_table_repair.config.loader import load_model_roles
from rate_table_repair.evidence.builder import EvidenceBuilder
from rate_table_repair.mineru.adapter import MineruAdapter
from rate_table_repair.scanners.issue_selector import build_issue
from rate_table_repair.scanners.project_scanner import scan_cases
from rate_table_repair.scanners.report_loader import load_verification_summary


PROMPT_PATH = ROOT / "prompts" / "peer_review.txt"
DATASET_ROOT = ROOT / "第一批采集结果（源于重疾险1.zip）"
CASE_NAME = "中信保诚「康爱保」恶性肿瘤疾病保险_78aebf56-a419-4c60-b7ee-0e959e6aa23e_费率文件"
PAGE_NUMBER = 1


def main() -> None:
    roles = load_model_roles()
    cfg = roles["peer_reviewer"]
    cases = scan_cases(DATASET_ROOT)
    case = next(item for item in cases if item.name == CASE_NAME)
    case.summary = load_verification_summary(case.verification_summary_path)
    issue = build_issue(case, PAGE_NUMBER)
    evidence = EvidenceBuilder(MineruAdapter(), ROOT / "output" / "api_probe" / "rendered_pages").build(issue)

    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    prompt += "\n\n【案件】%s\n【页码】%s\n" % (evidence.case_name, evidence.page_number)
    prompt += "\n【HTML页面片段】\n%s\n" % evidence.html_page_context.html_fragment[:3000]
    if evidence.mineru_tables:
        table = evidence.mineru_tables[0]
        prompt += "\n【表格HTML】\n%s\n" % table.table_html[:1500]
    prompt += "\n【补充上下文】\n%s\n" % json.dumps(
        {
            "is_real_error": True,
            "confidence": "high",
            "reason": "PDF与HTML在26岁5年缴费期处不一致",
            "target_location": {
                "table_index": 0,
                "row_index": 26,
                "column_index": 3,
                "row_context": "26",
                "column_context": "5年",
            },
            "correction": {"from": "36.95", "to": "34.18"},
        },
        ensure_ascii=False,
    )

    image_data = None
    if evidence.rendered_page_image and evidence.rendered_page_image.exists():
        import base64

        image_data = base64.b64encode(evidence.rendered_page_image.read_bytes()).decode("utf-8")

    client = OpenAI(
        api_key=str(cfg["api_key"]),
        base_url=str(cfg["base_url"]),
        timeout=120,
        http_client=httpx.Client(trust_env=False, timeout=120),
    )
    content = [{"type": "text", "text": prompt}]
    if image_data:
        content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_data}"}})

    response = client.chat.completions.create(
        model=str(cfg["model_id"]),
        messages=[{"role": "user", "content": content}],
        stream=False,
        max_tokens=2000,
        temperature=0,
    )

    out = {
        "model": cfg["name"],
        "response_type": type(response).__name__,
        "choices_type": type(getattr(response, "choices", None)).__name__,
        "choices_len": len(getattr(response, "choices", []) or []),
        "raw_repr": repr(response)[:4000],
    }
    if getattr(response, "choices", None):
        message = response.choices[0].message
        out["message_content_type"] = type(message.content).__name__
        out["message_content_repr"] = repr(message.content)[:4000]
        out["message_dict"] = message.model_dump() if hasattr(message, "model_dump") else str(message)
    if getattr(response, "base_resp", None) is not None:
        base_resp = response.base_resp
        out["base_resp"] = {
            "status_code": getattr(base_resp, "status_code", None),
            "status_msg": getattr(base_resp, "status_msg", None),
        }
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
