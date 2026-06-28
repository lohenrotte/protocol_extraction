import fitz
import pdfplumber
import pandas as pd
import numpy as np


def build_section_ranges(pdf_path: str) -> dict:
    """
    Build a dictionary of section titles and their corresponding page ranges 
    """
    def is_excluded(title: str) -> bool:
        t = title.lower().strip()
        return (
            t.startswith("figure") or
            t.startswith("list of figures") or
            t.startswith("table") or
            t.startswith("list of tables") 
        )
    section_dict = {}

    doc = fitz.open(pdf_path)
    toc = doc.get_toc()
    doc.close()

    toc_filtered = [(lvl, title, page) for lvl, title, page in toc
                    if not is_excluded(title)]

    for i, (_, title, start_page) in enumerate(toc_filtered):
        if i < len(toc_filtered) - 1:
            end_page = toc_filtered[i + 1][2] 
        else:
            end_page = None

        section_dict[title] = {}
        section_dict[title]["pages"] = [start_page, end_page]

    return section_dict


def extract_text_from_pdf(pdf_path: str, pages: list[int] = None) -> dict[int, str]:
    """
    Extract plain text from a PDF, page by page.
    """
    results = {}
    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        target_pages = pages if pages is not None else range(1, total_pages + 1)
 
        for page_num in target_pages:
            page = pdf.pages[page_num - 1]
            results[page_num] = (page.extract_text() or "").strip()
 
    return results


# def extract_text_from_pdf(pdf_path: str, pages: list[int] = None) -> dict[int, str]:
#     results = {}

#     doc = fitz.open(pdf_path)
#     total_pages = doc.page_count

#     target_pages = pages if pages is not None else range(1, total_pages + 1)

#     for page_num in target_pages:
#         page = doc.load_page(page_num - 1)
#         text = page.get_text("text") 
#         results[page_num] = text.strip()

#     doc.close()
#     return results

 
def build_section_text(page_text: dict, section_dict: dict) -> dict[str, str]:
    """
    Build section-level text by concatenating page-level text using TOC.
    """

    if not section_dict:
        return {}
    
    for _, data in section_dict.items():
        start, end = data["pages"]

        if end is None:
            data["pages"][1] = max(page_text.keys())
            end = data["pages"][1]

        data["text"] = "\n".join(
            page_text.get(p, "")
            for p in range(start, end + 1)
        ).strip()

    return section_dict


def _cluster_edges(values: list[float], tol: float = 2.0) -> list[float]:
    """
    Collapse near-duplicate coordinates (e.g. 100.01 vs 100.03 due to
    floating point / rendering noise) into single canonical edges.
    Returns sorted unique edges.
    """
    values = sorted(values)
    clustered = []
    for v in values:
        if not clustered or v - clustered[-1] > tol:
            clustered.append(v)
        # else: close enough to previous edge, treat as same line
    return clustered
 
 
def _index_of(edge: float, edges: list[float], tol: float = 2.0) -> int:
    """Find which canonical edge index a coordinate corresponds to."""
    for i, e in enumerate(edges):
        if abs(edge - e) <= tol:
            return i
    # fallback: nearest edge (handles minor cropping/rounding mismatches)
    return min(range(len(edges)), key=lambda i: abs(edges[i] - edge))
 

def _process_table(page, table, page_num: int, edge_tol: float) -> dict :
    cells = table.cells  # list of (x0, top, x1, bottom) bboxes
    if not cells:
        return None
 
    # Canonical column/row boundaries from every cell edge actually seen.
    x_edges = _cluster_edges(
        [c[0] for c in cells] + [c[2] for c in cells], tol=edge_tol
    )
    y_edges = _cluster_edges(
        [c[1] for c in cells] + [c[3] for c in cells], tol=edge_tol
    )
 
    n_cols = len(x_edges) - 1
    n_rows = len(y_edges) - 1
    if n_cols <= 0 or n_rows <= 0:
        return None
 
    grid = [[None] * n_cols for _ in range(n_rows)]
 
    for bbox in cells:
        x0, top, x1, bottom = bbox
 
        col_start = _index_of(x0, x_edges, edge_tol)
        col_end = _index_of(x1, x_edges, edge_tol)
        row_start = _index_of(top, y_edges, edge_tol)
        row_end = _index_of(bottom, y_edges, edge_tol)
 
        col_span = max(1, col_end - col_start)
        row_span = max(1, row_end - row_start)
 
        text = page.crop(bbox).extract_text()
        text = text.strip() if text else ""
 
        # Fill every grid slot this cell actually covers.
        for r in range(row_start, row_start + row_span):
            for c in range(col_start, col_start + col_span):
                if 0 <= r < n_rows and 0 <= c < n_cols:
                    grid[r][c] = text
 
    return {
        "page": page_num,
        "grid": grid,
    }

 
def extract_tables_from_pdf(
    pdf_path: str,
    pages: list[int] = None,
    edge_tol: float = 2.0,
) -> list[dict]:
    """
    Extract tables from a PDF, reconstructing merged cells (row-span and
    col-span) using actual ruling-line geometry instead of a flat text grid.
    """

    found_tables = []
 
    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        target_pages = pages if pages is not None else range(1, total_pages + 1)
 
        for page_num in target_pages:
            page = pdf.pages[page_num - 1]
            tables = page.find_tables()
 
            for table in tables:
                table_dict = _process_table(page, table, page_num, edge_tol)
                if table_dict is not None:
                    found_tables.append(table_dict)
 
    return found_tables


def merge_continued_tables(found_tables: list[dict]) -> list[dict]:
    """
    Merge tables across consecutive pages when they share the same header row
    """
    if not found_tables:
        return []

    merged = []
    current = dict(found_tables[0])
    current["pages"] = [current.pop("page")]

    for t in found_tables[1:]:
        same_header = (
            t["grid"] and current["grid"]
            and t["grid"][0] == current["grid"][0]          
            and t["page"] == current["pages"][-1] + 1        
        )
        if same_header:
            current["grid"].extend(t["grid"][1:])      
            current["pages"].append(t["page"])
        else:
            merged.append(current)
            current = dict(t)
            current["pages"] = [current.pop("page")]

    merged.append(current)
    return merged


def extract_table_toc(pdf_path: str):
    doc = fitz.open(pdf_path)
    toc = doc.get_toc()
    doc.close()

    def is_table(title: str) -> bool:
        t = title.lower().strip()
        return t.startswith("table") or "table" in t

    return [
        {"title": title, "page": page}
        for lvl, title, page in toc
        if is_table(title)
    ]


def attach_table_titles(tables: list[dict], table_toc: list[dict]) -> list[dict]:
    """
    Attach TOC-based titles to extracted tables based on page matching.
    """

    for t in tables:
        match = next(
            (x for x in table_toc if x["page"] == t.get("pages")[0]),
            None
        )
        t["title"] = match["title"] if match else "Unknown Table"

    return tables


def attach_tables_to_sections(section_dict: dict, tables: list[dict]) -> dict:
    """
    Attach extracted tables to their corresponding section based on page ranges.
    """
    for data in section_dict.values():
        data["tables"] = []

    for table in tables:

        table_pages = table["pages"]
        first_page = table_pages[0]

        for data in section_dict.values():
            start, end = data["pages"]

            if start <= first_page <= end:
                data["tables"].append(table)
                break

    return section_dict