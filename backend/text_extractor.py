"""
Text extraction utilities for policy documents.
Supports: PDF, DOCX, TXT, XLSX
"""
from pathlib import Path


def extract_text(file_path: Path, file_ext: str) -> str:
    """
    Extract all text from a file based on its extension.
    Returns extracted text as a string (empty string on failure).
    """
    ext = file_ext.lower().lstrip(".")
    try:
        if ext == "pdf":
            return _extract_pdf(file_path)
        elif ext == "docx":
            return _extract_docx(file_path)
        elif ext == "txt":
            return _extract_txt(file_path)
        elif ext in ("xlsx", "xls"):
            return _extract_xlsx(file_path)
    except Exception as e:
        # Return a note so content_preview is not blank but error is visible
        return f"[Text extraction failed: {e}]"
    return ""


def _extract_pdf(file_path: Path) -> str:
    """Extract text from PDF using PyMuPDF (handles both text-based and complex PDFs)."""
    import fitz  # PyMuPDF

    text_parts = []
    with fitz.open(str(file_path)) as doc:
        for page_num, page in enumerate(doc, start=1):
            page_text = page.get_text("text")
            if page_text.strip():
                text_parts.append(f"--- Page {page_num} ---\n{page_text.strip()}")

    return "\n\n".join(text_parts)


def _extract_docx(file_path: Path) -> str:
    """Extract text from DOCX including paragraphs and tables."""
    from docx import Document

    doc = Document(str(file_path))
    parts = []

    # Extract paragraphs
    for para in doc.paragraphs:
        if para.text.strip():
            parts.append(para.text.strip())

    # Extract tables
    for table_idx, table in enumerate(doc.tables, start=1):
        parts.append(f"\n[Table {table_idx}]")
        for row in table.rows:
            row_cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if row_cells:
                parts.append(" | ".join(row_cells))

    return "\n".join(parts)


def _extract_txt(file_path: Path) -> str:
    """Extract text from TXT files, handling multiple encodings."""
    import chardet

    raw = file_path.read_bytes()
    detected = chardet.detect(raw)
    encoding = detected.get("encoding") or "utf-8"

    try:
        return raw.decode(encoding)
    except (UnicodeDecodeError, LookupError):
        # Fallback: try utf-8 with replacement, then latin-1
        try:
            return raw.decode("utf-8", errors="replace")
        except Exception:
            return raw.decode("latin-1", errors="replace")


def _extract_xlsx(file_path: Path) -> str:
    """Extract data from all sheets of an Excel file."""
    import openpyxl

    wb = openpyxl.load_workbook(str(file_path), read_only=True, data_only=True)
    parts = []

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        sheet_parts = [f"\n[Sheet: {sheet_name}]"]
        row_count = 0
        for row in ws.iter_rows(values_only=True):
            cells = [str(cell) for cell in row if cell is not None]
            if cells:
                sheet_parts.append(" | ".join(cells))
                row_count += 1
        if row_count > 0:
            parts.extend(sheet_parts)

    wb.close()
    return "\n".join(parts)
