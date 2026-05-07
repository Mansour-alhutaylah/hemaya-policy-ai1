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
    pages = []
    for page in doc:
        try:
            # sort=True asks PyMuPDF to return blocks in reading order,
            # which also corrects Arabic RTL bidi ordering and preserves
            # table-cell boundaries that get lost in flat get_text() mode.
            page_dict = page.get_text("dict", sort=True)
            pages.append(_extract_page_blocks(page_dict))
        except Exception:
            # Per-page fallback: if structured extraction fails for any
            # reason (unusual PDF, corrupt page), degrade to plain text
            # for that page only — the rest of the document is unaffected.
            pages.append(page.get_text())
    return "\n".join(pages)


def _extract_page_blocks(page_dict: dict) -> str:
    """Reconstruct page text from PyMuPDF's block/line/span structure.

    Type-0 blocks are text; type-1 are images (skipped).
    Lines within each block are joined with newlines;
    blocks are separated by blank lines to preserve paragraph boundaries.
    """
    blocks_text = []
    for block in page_dict.get("blocks", []):
        if block.get("type") != 0:  # skip image blocks
            continue
        line_texts = []
        for line in block.get("lines", []):
            span_text = " ".join(
                span["text"]
                for span in line.get("spans", [])
                if span.get("text", "").strip()
            )
            if span_text.strip():
                line_texts.append(span_text.strip())
        if line_texts:
            blocks_text.append("\n".join(line_texts))
    return "\n\n".join(blocks_text)


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
