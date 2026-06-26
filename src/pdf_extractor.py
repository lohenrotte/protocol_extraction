import fitz
import pdfplumber


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


def extract_tables_from_pdf(pdf_path: str, pages: list[int] = None) -> list[dict]:
    """
    Extract tables from a PDF using pdfplumber's native table detection
    """
    found_tables = []
 
    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        target_pages = pages if pages is not None else range(1, total_pages + 1)
 
        for page_num in target_pages:
            page = pdf.pages[page_num - 1]
            tables = page.extract_tables()
 
            for table in tables:

                found_tables.append(
                    {
                        "page": page_num,
                        "rows": table,
                    }
                )
 
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
            t["rows"] and current["rows"]
            and t["rows"][0] == current["rows"][0]          
            and t["page"] == current["pages"][-1] + 1        
        )
        if same_header:
            current["rows"].extend(t["rows"][1:])      
            current["pages"].append(t["page"])
        else:
            merged.append(current)
            current = dict(t)
            current["pages"] = [current.pop("page")]

    merged.append(current)
    return merged


def attach_table_titles(tables: list[dict], table_toc: list[dict]) -> list[dict]:
    """
    Attach TOC-based titles to extracted tables based on page matching.
    """
    print(table_toc)
    for t in tables:
        print(t.get("pages"))
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

 
def table_to_text(rows: list[list]) -> str:
    """
    Flatten a pdfplumber table (list of row lists) into a simple text block
    """
    lines = []
    for row in rows:
        cells = [cell.strip() if cell else "" for cell in row]
        lines.append(" | ".join(cells))
    return "\n".join(lines)