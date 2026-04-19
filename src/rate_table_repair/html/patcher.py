from copy import deepcopy
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup

from rate_table_repair.html.locator import find_page_section, resolve_cell_location
from rate_table_repair.schemas.patch import PatchPlan, PatchResult
from rate_table_repair.schemas.review import PatchInstruction


class HtmlPatcher:
    def _resolve_patch(
        self,
        section,
        patch: PatchInstruction,
    ):
        table_index, row_index, column_index, cell = resolve_cell_location(section, patch.target_location)
        return table_index, row_index, column_index, cell

    def _relocate_by_expected_value(
        self,
        section,
        table_index: Optional[int],
        row_index: Optional[int],
        expected: str,
    ):
        if table_index is None or row_index is None:
            return table_index, row_index, None, None

        tables = section.find_all("table")
        if table_index < 0 or table_index >= len(tables):
            return table_index, row_index, None, None

        rows = tables[table_index].find_all("tr")
        if row_index < 0 or row_index >= len(rows):
            return table_index, row_index, None, None

        matches = []
        for column_index, cell in enumerate(rows[row_index].find_all(["td", "th"])):
            if cell.get_text(strip=True) == expected:
                matches.append((column_index, cell))

        if len(matches) != 1:
            return table_index, row_index, None, None

        column_index, cell = matches[0]
        return table_index, row_index, column_index, cell

    @staticmethod
    def _has_explicit_target(patch: PatchInstruction) -> bool:
        location = patch.target_location
        return any(
            value is not None and value != ""
            for value in (
                location.row_index,
                location.column_index,
                location.row_context,
                location.column_context,
            )
        )

    def apply(self, plan: PatchPlan, output_html_path: Path) -> PatchResult:
        if not plan.should_modify:
            reason = plan.reason or "未生成可执行 patch"
            return PatchResult(case_name=plan.case_name, modified=False, message="不允许自动修改：%s" % reason)

        source_html_path = output_html_path if output_html_path.exists() else plan.html_path
        html_text = source_html_path.read_text(encoding="utf-8")
        soup = BeautifulSoup(html_text, "html.parser")
        section = find_page_section(soup, plan.page_number)
        if section is None:
            return PatchResult(case_name=plan.case_name, modified=False, message="未找到目标页。")

        source_patches = plan.patches or [
            PatchInstruction(
                target_location=deepcopy(plan.target_location),
                correction=deepcopy(plan.correction),
                reason=plan.reason,
            )
        ]
        patches = [deepcopy(patch) for patch in source_patches]
        resolved = []
        for patch in patches:
            table_index, row_index, column_index, cell = self._resolve_patch(section, patch)
            if cell is None:
                return PatchResult(case_name=plan.case_name, modified=False, message="无法根据索引或上下文唯一定位目标单元格。")

            current_value = cell.get_text(strip=True)
            expected = patch.correction.from_value
            if expected is not None and current_value != expected and not self._has_explicit_target(patch):
                relocated_table_index, relocated_row_index, relocated_column_index, relocated_cell = self._relocate_by_expected_value(
                    section,
                    table_index,
                    row_index,
                    expected,
                )
                if relocated_cell is not None:
                    table_index = relocated_table_index
                    row_index = relocated_row_index
                    column_index = relocated_column_index
                    cell = relocated_cell
                    current_value = cell.get_text(strip=True)

            if expected is not None and current_value != expected:
                if self._has_explicit_target(patch):
                    # 模型已明确定位目标单元格时，优先修改该格子，避免仅因 from 值偏差而重定位到错误位置。
                    patch.correction.from_value = current_value
                else:
                    return PatchResult(
                        case_name=plan.case_name,
                        modified=False,
                        message="当前值 %s 与预期旧值 %s 不一致，拒绝修改。" % (current_value, expected),
                    )
            resolved.append((patch, table_index, row_index, column_index, cell, current_value))

        for patch, table_index, row_index, column_index, cell, current_value in resolved:
            cell.string = patch.correction.to_value or current_value
            patch.target_location.table_index = table_index
            patch.target_location.row_index = row_index
            patch.target_location.column_index = column_index

        output_html_path.parent.mkdir(parents=True, exist_ok=True)
        output_html_path.write_text(str(soup), encoding="utf-8")
        return PatchResult(
            case_name=plan.case_name,
            output_html_path=output_html_path,
            modified=True,
            modified_cells=len(resolved),
            message="HTML patch 已写入，共修改 %s 个单元格。" % len(resolved),
        )
