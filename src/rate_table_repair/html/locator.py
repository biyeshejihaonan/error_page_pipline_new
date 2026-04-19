import re
from typing import Optional, Tuple

from bs4 import BeautifulSoup, Tag

from rate_table_repair.schemas.review import CellLocation


def find_page_section(soup: BeautifulSoup, page_number: int) -> Optional[Tag]:
    sections = soup.select("div.page-section")
    index = page_number - 1
    if index < 0 or index >= len(sections):
        return None
    return sections[index]


def normalize_cell_text(text: Optional[str]) -> str:
    return (text or "").strip().replace("\xa0", " ")


def _tokenize_row_context(text: Optional[str]) -> list[str]:
    if text is None:
        return []
    normalized = normalize_cell_text(text)
    normalized = re.sub(r"</?t[rdh]>", " ", normalized)
    normalized = normalized.replace("、", " ").replace(",", " ").replace("，", " ")
    tokens = [token.strip() for token in re.split(r"\s+", normalized) if token.strip()]
    return tokens


def _row_matches_signature(cells: list[str], tokens: list[str]) -> bool:
    if not tokens:
        return False
    if len(tokens) == 1:
        return cells and cells[0] == tokens[0]
    if len(tokens) <= len(cells) and cells[: len(tokens)] == tokens:
        return True
    joined = " ".join(cells)
    return all(token in joined for token in tokens)


def _find_row_indices(table: Tag, row_context: Optional[str]) -> list[int]:
    if row_context is None:
        return []
    tokens = _tokenize_row_context(row_context)
    needle = normalize_cell_text(row_context)
    matches = []
    for row_index, row in enumerate(table.find_all("tr")):
        cells = [normalize_cell_text(cell.get_text()) for cell in row.find_all(["td", "th"])]
        if not cells:
            continue
        if cells[0] == needle or _row_matches_signature(cells, tokens):
            matches.append(row_index)
    return matches


def _extract_explicit_column_index(text: Optional[str]) -> Optional[int]:
    if text is None:
        return None
    for pattern in (r"第(\d+)列", r"第(\d+)个单元格", r"第(\d+)单元格"):
        match = re.search(pattern, text)
        if match:
            return max(int(match.group(1)) - 1, 0)
    return None


def _find_column_index(table: Tag, column_context: Optional[str]) -> Optional[int]:
    if column_context is None:
        return None
    explicit_index = _extract_explicit_column_index(column_context)
    if explicit_index is not None:
        return explicit_index
    needle = normalize_cell_text(column_context)
    max_columns = 0
    for row in table.find_all("tr"):
        max_columns = max(max_columns, len(row.find_all(["td", "th"])))
    for row in table.find_all("tr")[:3]:
        cells = row.find_all(["td", "th"])
        offset = max(0, max_columns - len(cells))
        for column_index, cell in enumerate(cells):
            if normalize_cell_text(cell.get_text()) == needle:
                return column_index + offset
    return None


def resolve_cell_location(
    section: Tag,
    target_location: CellLocation,
) -> Tuple[Optional[int], Optional[int], Optional[int], Optional[Tag]]:
    tables = section.find_all("table")
    if not tables:
        return None, None, None, None

    table_index = target_location.table_index if target_location.table_index is not None else 0
    if table_index < 0 or table_index >= len(tables):
        return None, None, None, None

    table = tables[table_index]
    row_matches = _find_row_indices(table, target_location.row_context)
    if len(row_matches) == 1:
        row_index = row_matches[0]
    elif target_location.row_index is not None and target_location.row_index in row_matches:
        row_index = target_location.row_index
    else:
        row_index = target_location.row_index

    column_index = _find_column_index(table, target_location.column_context)
    if column_index is None:
        column_index = target_location.column_index

    if row_index is None or column_index is None:
        return table_index, row_index, column_index, None

    rows = table.find_all("tr")
    if row_index < 0 or row_index >= len(rows):
        return table_index, row_index, column_index, None

    cells = rows[row_index].find_all(["td", "th"])
    if column_index < 0 or column_index >= len(cells):
        return table_index, row_index, column_index, None

    return table_index, row_index, column_index, cells[column_index]
