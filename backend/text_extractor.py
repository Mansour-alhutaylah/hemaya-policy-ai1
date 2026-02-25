"""Text extraction helpers for uploaded policy files."""
from pathlib import Path


def extract_text(file_path: Path, file_ext: str) -> str:
    ext = file_ext.lower().lstrip(".")
    try:
        if ext == "pdf":
            return _extract_pdf(file_path)
        elif ext == "docx":
            return _extract_docx(file_path)
        elif ext in ("xlsx", "xls"):
            return _extract_xlsx(file_path)
        elif ext == "txt":
            return _extract_txt(file_path)
        else:
            return ""
    except Exception as e:
        return f"[Extraction error: {e}]"


def _extract_pdf(file_path: Path) -> str:
    import fitz  # PyMuPDF
    doc = fitz.open(str(file_path))
    return "\n".join(page.get_text() for page in doc)


def _extract_docx(file_path: Path) -> str:
    from docx import Document
    doc = Document(str(file_path))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def _extract_xlsx(file_path: Path) -> str:
    from openpyxl import load_workbook
    wb = load_workbook(str(file_path), read_only=True, data_only=True)
    lines = []
    for sheet in wb.worksheets:
        for row in sheet.iter_rows(values_only=True):
            row_text = "\t".join(str(c) if c is not None else "" for c in row)
            if row_text.strip():
                lines.append(row_text)
    return "\n".join(lines)


def _extract_txt(file_path: Path) -> str:
    import chardet
    raw = file_path.read_bytes()
    detected = chardet.detect(raw)
    encoding = detected.get("encoding") or "utf-8"
    return raw.decode(encoding, errors="replace")
