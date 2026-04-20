import json
import re
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


def _extract_string(text: str, key: str) -> Optional[str]:
    pattern = rf'"{re.escape(key)}"\s*:\s*"((?:[^"\\]|\\.)*)"'
    match = re.search(pattern, text)
    if not match:
        return None
    try:
        return json.loads(f'"{match.group(1)}"')
    except json.JSONDecodeError:
        return match.group(1)


def _extract_bool(text: str, key: str) -> Optional[bool]:
    pattern = rf'"{re.escape(key)}"\s*:\s*(true|false)'
    match = re.search(pattern, text)
    if not match:
        return None
    return match.group(1) == "true"


def _extract_int(text: str, key: str) -> Optional[int]:
    pattern = rf'"{re.escape(key)}"\s*:\s*(-?\d+)'
    match = re.search(pattern, text)
    if not match:
        return None
    return int(match.group(1))


def _extract_object_slice(text: str, key: str) -> Optional[str]:
    key_match = re.search(rf'"{re.escape(key)}"\s*:\s*\{{', text)
    if not key_match:
        return None
    start = text.find("{", key_match.start())
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
    return text[start:]


def _salvage_location(text: str) -> Dict[str, Any]:
    location_text = _extract_object_slice(text, "target_location") or text
    location: Dict[str, Any] = {}
    for key in ("table_index", "row_index", "column_index"):
        value = _extract_int(location_text, key)
        if value is not None:
            location[key] = value
    for key in ("row_context", "column_context"):
        value = _extract_string(location_text, key)
        if value is not None:
            location[key] = value
    return location


def _salvage_correction(text: str) -> Dict[str, Any]:
    correction_text = _extract_object_slice(text, "correction") or text
    correction: Dict[str, Any] = {}
    for key in ("from", "to"):
        value = _extract_string(correction_text, key)
        if value is not None:
            correction[key] = value
    return correction


def _salvage_patch_instruction(text: str) -> Optional[Dict[str, Any]]:
    patch_text = _extract_object_slice(text, "target_location")
    correction_text = _extract_object_slice(text, "correction")
    if patch_text is None and correction_text is None:
        return None
    patch: Dict[str, Any] = {}
    location = _salvage_location(text)
    correction = _salvage_correction(text)
    if location:
        patch["target_location"] = location
    if correction:
        patch["correction"] = correction
    reason = _extract_string(text, "reason")
    if reason:
        patch["reason"] = reason
    return patch if patch else None


def _salvage_partial_object(text: str) -> Dict[str, Any]:
    salvaged: Dict[str, Any] = {}
    for key in ("final_decision", "confidence", "reason"):
        value = _extract_string(text, key)
        if value is not None:
            salvaged[key] = value
    for key in ("is_real_error", "should_modify_html", "target_location_confirmed"):
        value = _extract_bool(text, key)
        if value is not None:
            salvaged[key] = value

    location = _salvage_location(text)
    if location:
        salvaged["target_location"] = location
    correction = _salvage_correction(text)
    if correction:
        salvaged["correction"] = correction

    patch = _salvage_patch_instruction(text)
    if patch and (
        "final_decision" in salvaged or "should_modify_html" in salvaged or '"patches"' in text
    ):
        salvaged["patches"] = [patch]
    return salvaged


def parse_json_object(text: str) -> Dict[str, Any]:
    if not text.strip():
        return {}
    candidate = _extract_balanced_json(text)
    if candidate is not None:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            value = None
        if isinstance(value, dict):
            return value
    return _salvage_partial_object(text)


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
