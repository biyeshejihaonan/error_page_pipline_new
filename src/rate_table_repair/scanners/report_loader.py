import json
import re
from pathlib import Path
from typing import Optional

from rate_table_repair.schemas.report import OldIssueHint, VerificationSummary

_HEADER_PATTERNS = ("【验证结论】", "【问题详情】", "【问题分析】")
_LOCATION_PATTERNS = (
    "行内容为",
    "该行数据为",
    "第1列值为",
    "第1列",
    "第5列值为",
    "第",
    "年龄",
    "缴费期",
    "列标题为",
    "行标题为",
    "百分比列",
    "比例列",
)
_VALUE_PATTERNS = ("正确值应为", "正确值为", "图片中应为", "PDF显示", "HTML中为", "当前值", "HTML值为")
_UNSAFE_VALUE_ONLY_PATTERNS = (
    "推测",
    "左右",
    "相近",
    "合理递增",
    "合理数值",
    "应大于",
    "应小于",
    "需以图片",
    "需以PDF",
    "根据前后行",
    "结合前后行",
    "结合前序",
)


def load_verification_summary(path: Path) -> VerificationSummary:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return VerificationSummary(**data)


def _clean_detail_text(text: str) -> str:
    lines = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if any(line.startswith(prefix) for prefix in _HEADER_PATTERNS):
            continue
        line = re.sub(r"^\d+\.\s*", "", line)
        line = re.sub(r"^[-*]\s*", "", line)
        if line:
            lines.append(line)
    return "\n".join(lines)


def _split_detail_items(text: str) -> list[str]:
    cleaned = _clean_detail_text(text)
    if not cleaned:
        return []
    items = []
    for line in cleaned.splitlines():
        line = line.strip()
        if not line:
            continue
        items.append(line)
    return items


def _has_location_clue(text: str) -> bool:
    if "第" in text and ("列" in text or "行" in text or "单元格" in text):
        return True
    return any(pattern in text for pattern in _LOCATION_PATTERNS)


def _has_value_clue(text: str) -> bool:
    return any(pattern in text for pattern in _VALUE_PATTERNS)


def _is_unsafe_value_only_item(text: str) -> bool:
    if not _has_value_clue(text):
        return False
    if _has_location_clue(text):
        return False
    return any(pattern in text for pattern in _UNSAFE_VALUE_ONLY_PATTERNS) or "正确值" in text


def _strip_quotes(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip().strip("*").strip()
    if len(value) >= 2 and value[0] in "“\"" and value[-1] in "”\"":
        value = value[1:-1].strip()
    return value or None


def _extract_row_context(text: str) -> Optional[str]:
    patterns = [
        r"行内容为[“\"]([^”\"]+)[”\"]",
        r"该行数据为[“\"]([^”\"]+)[”\"]",
        r"行内容为`([^`]+)`",
        r"内容为`([^`]+)`",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return _strip_quotes(match.group(1))
    match = re.search(r"年龄(?:为)?(\d+)", text)
    if match:
        return match.group(1)
    match = re.search(r"第1列值为[“\"]?([^，。；”\"]+)", text)
    if match:
        return _strip_quotes(match.group(1))
    return None


def _extract_column_index(text: str) -> Optional[int]:
    patterns = [
        r"第(\d+)列",
        r"第(\d+)个单元格",
        r"第(\d+)单元格",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return max(int(match.group(1)) - 1, 0)
    return None


def _extract_column_context(text: str) -> Optional[str]:
    patterns = [
        r"（([^（）]*百分比列)）",
        r"（([^（）]*比例列)）",
        r"（([^（）]*年龄列)）",
        r"（([^（）]*金额列)）",
        r"列标题为[“\"]([^”\"]+)[”\"]",
        r"对应([^\s，。；）]{1,12}列)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return _strip_quotes(match.group(1))
    for name in ("百分比列", "比例列", "年龄列", "金额列", "数值列"):
        if name in text:
            return name
    return None


def _extract_correct_value(text: str) -> Optional[str]:
    patterns = [
        r"图片中应为[“\"]?([^，。；”\"\s]+)",
        r"PDF显示[^，。；]*应为[“\"]?([^，。；”\"\s]+)",
        r"正确值应为[“\"]?([^，。；”\"]+)",
        r"正确值为[“\"]?([^，。；”\"]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            value = _strip_quotes(match.group(1))
            return value.strip("*") if value else None
    return None


def _extract_current_value(text: str) -> Optional[str]:
    patterns = [
        r"HTML中(?:值为|为|数据值为)?[“\"]?([^，。；”\"]+)",
        r"当前(?:值|为)[“\"]?([^，。；”\"]+)",
        r"原HTML中[^，。；]*为[“\"]?([^，。；”\"]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return _strip_quotes(match.group(1))
    return None


def _build_hint(text: str) -> Optional[OldIssueHint]:
    if not _has_location_clue(text) or not _has_value_clue(text):
        return None
    return OldIssueHint(
        text=text,
        row_context=_extract_row_context(text),
        column_index=_extract_column_index(text),
        column_context=_extract_column_context(text),
        current_value=_extract_current_value(text),
        correct_value=_extract_correct_value(text),
    )


def _extract_detail_items_from_result_json(result_json_path: Optional[Path]) -> list[str]:
    if result_json_path is None or not result_json_path.exists():
        return []
    with result_json_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    model1 = (data.get("model1_result") or {}).get("details", "")
    model2 = (data.get("model2_result") or {}).get("details", "")
    items = []
    for text in (model1, model2):
        items.extend(_split_detail_items(text))
    return items


def load_old_issue_hints(result_json_path: Optional[Path]) -> list[OldIssueHint]:
    hints = []
    seen = set()
    for item in _extract_detail_items_from_result_json(result_json_path):
        if _is_unsafe_value_only_item(item):
            continue
        hint = _build_hint(item)
        if hint is None:
            continue
        key = hint.model_dump_json(exclude_none=True, ensure_ascii=False)
        if key in seen:
            continue
        seen.add(key)
        hints.append(hint)
    return hints


def load_old_issue_summary(result_json_path: Optional[Path]) -> Optional[str]:
    hint_texts = [hint.text for hint in load_old_issue_hints(result_json_path)]
    if hint_texts:
        return "\n".join(hint_texts)
    return None
