#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx


def load_first_enabled_model() -> dict[str, Any]:
    namespace: dict[str, Any] = {}
    exec(Path("model_config.py").read_text(encoding="utf-8"), namespace)
    for model in namespace["MODELS"]:
        if model.get("enabled", True):
            return model
    raise SystemExit("no enabled model found")


def main() -> int:
    model = load_first_enabled_model()
    url = str(model["base_url"]).rstrip("/") + "/models"
    headers = {
        "Authorization": f"Bearer {model['api_key']}",
        "Accept": "application/json",
    }
    print(json.dumps({"url": url}, ensure_ascii=False))
    with httpx.Client(timeout=30, trust_env=False) as client:
        response = client.get(url, headers=headers)
    print(f"status={response.status_code}")
    print(response.text[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
