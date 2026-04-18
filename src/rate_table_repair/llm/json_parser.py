import json
from typing import Any, Dict, Optional


def _extract_balanced_json(text: str) -> Optional[str]:
    start = text.find("{")
    if start < 0:
        return None

    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def parse_json_object(text: str) -> Dict[str, Any]:
    if not text.strip():
        return {}
    candidate = _extract_balanced_json(text)
    if candidate is None:
        return {}
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def normalize_review_json(payload: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(payload)
    if normalized.get("target_location") is None:
        normalized["target_location"] = {}
    if normalized.get("correction") is None:
        normalized["correction"] = {}
    if normalized.get("concerns") is None:
        normalized["concerns"] = []
    return normalized


def normalize_final_judge_json(payload: Dict[str, Any]) -> Dict[str, Any]:
    normalized = normalize_review_json(payload)
    if normalized.get("patches") is None:
        normalized["patches"] = []
    if normalized.get("basis") is None:
        normalized["basis"] = {}
    return normalized


def normalize_linked_patch_json(payload: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(payload)
    if normalized.get("patches") is None:
        normalized["patches"] = []
    return normalized
