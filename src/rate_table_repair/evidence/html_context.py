from typing import Optional

from bs4 import BeautifulSoup

from rate_table_repair.schemas.evidence import HtmlPageContext


def extract_html_page_context(html_text: str, page_number: int) -> HtmlPageContext:
    soup = BeautifulSoup(html_text, "html.parser")
    sections = soup.select("div.page-section")
    section_index = page_number - 1
    if section_index < 0 or section_index >= len(sections):
        return HtmlPageContext(
            page_number=page_number,
            page_title=None,
            table_count=0,
            html_fragment="",
        )
    section = sections[section_index]
    title_tag = section.find(["h1", "h2", "h3", "p"])
    title: Optional[str] = title_tag.get_text(strip=True) if title_tag else None
    tables = section.find_all("table")
    return HtmlPageContext(
        page_number=page_number,
        page_title=title,
        table_count=len(tables),
        html_fragment=str(section),
    )
