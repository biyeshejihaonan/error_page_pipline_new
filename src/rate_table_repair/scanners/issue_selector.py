from typing import List

from rate_table_repair.schemas.report import DocumentCase, PageIssue
from rate_table_repair.scanners.report_loader import load_old_issue_hints, load_old_issue_summary


def build_issue(document_case: DocumentCase, page_number: int) -> PageIssue:
    result_path = document_case.mineru_pages_dir / "_verification" / (
        "page_%04d_verification_result.json" % page_number
    )
    report_path = document_case.mineru_pages_dir / "_verification" / (
        "page_%04d_verification_report.txt" % page_number
    )
    mineru_page_dir = document_case.mineru_pages_dir / ("page_%04d" % page_number)
    split_pdf = document_case.split_pages_dir / ("page_%04d.pdf" % page_number)
    return PageIssue(
        case_name=document_case.name,
        case_dir=document_case.case_dir,
        html_path=document_case.html_path,
        page_number=page_number,
        verification_result_path=result_path if result_path.exists() else None,
        verification_report_path=report_path if report_path.exists() else None,
        mineru_page_dir=mineru_page_dir if mineru_page_dir.exists() else None,
        split_page_pdf=split_pdf if split_pdf.exists() else None,
        old_issue_summary=load_old_issue_summary(result_path),
        old_issue_hints=load_old_issue_hints(result_path),
    )


def select_issues(document_case: DocumentCase) -> List[PageIssue]:
    if document_case.summary is None:
        raise ValueError("document_case.summary 未加载")

    return [build_issue(document_case, page_number) for page_number in document_case.summary.pages_with_issues]
