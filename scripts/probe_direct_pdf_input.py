from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
import sys

from openai import OpenAI
import httpx

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rate_table_repair.config.loader import load_models


PROMPT = """你现在只做一件事：读取这页费率表，返回一个简短 JSON。

要求：
1. 不要解释，不要 markdown。
2. 只返回一个 JSON 对象。
3. 字段固定为:
{
  "page_readable": true/false,
  "table_present": true/false,
  "sample_text": "你在页内读到的一小段关键文本"
}
"""


def _make_client(model: dict) -> OpenAI:
    return OpenAI(
        api_key=str(model["api_key"]),
        base_url=str(model["base_url"]),
        timeout=120,
        http_client=httpx.Client(trust_env=False, timeout=120),
    )


def _png_item(path: Path) -> dict:
    data = base64.b64encode(path.read_bytes()).decode("utf-8")
    return {
        "type": "image_url",
        "image_url": {"url": f"data:image/png;base64,{data}"},
    }


def _pdf_item_variant_a(path: Path) -> dict:
    data = base64.b64encode(path.read_bytes()).decode("utf-8")
    return {
        "type": "file",
        "file": {
            "filename": path.name,
            "file_data": f"data:application/pdf;base64,{data}",
        },
    }


def _pdf_item_variant_b(path: Path) -> dict:
    data = base64.b64encode(path.read_bytes()).decode("utf-8")
    return {
        "type": "file",
        "file": {
            "filename": path.name,
            "data": f"data:application/pdf;base64,{data}",
        },
    }


def _run_once(model: dict, content: list[dict], max_tokens: int = 2000) -> dict:
    client = _make_client(model)
    try:
        response = client.chat.completions.create(
            model=str(model["model_id"]),
            messages=[{"role": "user", "content": content}],
            stream=False,
            max_tokens=max_tokens,
            temperature=0,
        )
        message = response.choices[0].message
        return {
            "ok": True,
            "content": message.content,
            "finish_reason": response.choices[0].finish_reason,
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": type(exc).__name__,
            "message": str(exc),
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--png")
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    png_path = Path(args.png) if args.png else None
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    models = {item["name"]: item for item in load_models()}
    if args.model not in models:
        raise KeyError(f"模型不存在: {args.model}")
    model = models[args.model]

    trials: dict[str, dict] = {}

    if png_path and png_path.exists():
        trials["png_only"] = _run_once(
            model,
            [_png_item(png_path), {"type": "text", "text": PROMPT}],
        )

    trials["pdf_variant_a"] = _run_once(
        model,
        [_pdf_item_variant_a(pdf_path), {"type": "text", "text": PROMPT}],
    )
    trials["pdf_variant_b"] = _run_once(
        model,
        [_pdf_item_variant_b(pdf_path), {"type": "text", "text": PROMPT}],
    )

    output_path.write_text(
        json.dumps(
            {
                "model": args.model,
                "pdf": str(pdf_path),
                "png": str(png_path) if png_path else None,
                "trials": trials,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
