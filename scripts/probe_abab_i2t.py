#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import sys
import traceback
from pathlib import Path
from typing import Any

import httpx
from openai import OpenAI


def load_model_config(model_name: str) -> dict[str, Any]:
    namespace: dict[str, Any] = {}
    config_path = Path("model_config.py")
    exec(config_path.read_text(encoding="utf-8"), namespace)
    models = namespace["MODELS"]
    for model in models:
        if model["name"] == model_name and model.get("enabled", True):
            return model
    raise SystemExit(f"model not found or disabled: {model_name}")


def build_message(prompt: str, image_path: Path | None) -> list[dict[str, Any]] | str:
    if image_path is None:
        return prompt
    image_data = base64.b64encode(image_path.read_bytes()).decode("utf-8")
    return [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_data}"}},
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--image", type=Path)
    parser.add_argument(
        "--prompt",
        default="请只回复 OK。如果看到了图片，也请说明你看到了图片。",
    )
    parser.add_argument("--max-tokens", type=int, default=300)
    args = parser.parse_args()

    cfg = load_model_config(args.model)
    client = OpenAI(
        api_key=str(cfg["api_key"]),
        base_url=str(cfg["base_url"]),
        timeout=120,
        http_client=httpx.Client(trust_env=False, timeout=120),
    )

    message_content = build_message(args.prompt, args.image)
    print(
        json.dumps(
            {
                "model": cfg["model_id"],
                "base_url": cfg["base_url"],
                "image": str(args.image) if args.image else None,
                "image_bytes": args.image.stat().st_size if args.image else 0,
                "content_type": "multimodal" if args.image else "text",
            },
            ensure_ascii=False,
        )
    )

    try:
        response = client.chat.completions.create(
            model=str(cfg["model_id"]),
            messages=[{"role": "user", "content": message_content}],
            max_tokens=args.max_tokens,
            stream=False,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR {exc.__class__.__name__}: {exc}", file=sys.stderr)
        if getattr(exc, "__cause__", None) is not None:
            print(f"CAUSE {exc.__cause__.__class__.__name__}: {exc.__cause__}", file=sys.stderr)
        if getattr(exc, "__context__", None) is not None:
            print(f"CONTEXT {exc.__context__.__class__.__name__}: {exc.__context__}", file=sys.stderr)
        traceback.print_exc()
        return 1

    choices = getattr(response, "choices", None)
    if choices:
        content = choices[0].message.content
        if isinstance(content, str):
            print(content.strip())
        else:
            print(json.dumps(content, ensure_ascii=False, indent=2))
        return 0

    if hasattr(response, "model_dump_json"):
        print(response.model_dump_json(indent=2))
    else:
        print(repr(response))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
