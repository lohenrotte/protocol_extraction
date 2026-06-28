import json
import os
import pdf_extractor
import pandas as pd

pdf_path = "input/protocol_covid_19_AstraZeneca.pdf"

if not os.path.exists("output/sections.json"):

    section_dict = pdf_extractor.build_section_ranges(pdf_path)

    page_text = pdf_extractor.extract_text_from_pdf(pdf_path)

    section_dict = pdf_extractor.build_section_text(page_text, section_dict)

    # Extract every table 
    tables = pdf_extractor.extract_tables_from_pdf(pdf_path)

    # Merge tables spanning multiple pages
    tables = pdf_extractor.merge_continued_tables(tables)

    # Attach table titles to the extracted tables
    tables_toc = pdf_extractor.extract_table_toc(pdf_path)
    tables = pdf_extractor.attach_table_titles(tables, tables_toc)

    # Attach tables to the correct section
    section_dict = pdf_extractor.attach_tables_to_sections(section_dict, tables)

    with open("output/sections.json", "w", encoding="utf-8") as f:
        json.dump(section_dict, f, indent=4, ensure_ascii=False)
else:
    with open("output/sections.json", "r", encoding="utf-8") as f:
        section_dict = json.load(f)