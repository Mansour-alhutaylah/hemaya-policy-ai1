"""
backend/pdf_export.py

Build a clean, paginated PDF of a stored policy version using PyMuPDF.

Design choices:
  - PyMuPDF (fitz) is already a project dependency (1.27+). No new packages.
  - Text-only output: source content is plain policy text (no markdown / HTML).
  - Word-wrap per paragraph with a fixed-width font for predictable pagination.
  - Header with title + version, footer with page X of Y.
"""
from __future__ import annotations

import textwrap
from datetime import datetime
from typing import Optional

import fitz  # PyMuPDF


# A4 in points (PyMuPDF default). 1 pt = 1/72 inch.
_PAGE_W, _PAGE_H = fitz.paper_size("a4")
_MARGIN = 54                  # ~0.75 inch
_HEADER_H = 36
_FOOTER_H = 28
_FONT_BODY = "helv"           # built-in Helvetica
_FONT_MONO = "cour"           # built-in Courier (used for the "v3" tag etc.)
_FONT_SIZE = 10
_LINE_H = 13.5                # leading for body text
_TITLE_SIZE = 14
_META_SIZE = 9

_DARK = (0.10, 0.10, 0.12)
_GREY = (0.45, 0.45, 0.50)
_ACCENT = (0.06, 0.55, 0.42)  # emerald-600-ish — matches app accent


def _wrap_paragraphs(content: str, width: int = 95) -> list[str]:
    """
    Convert raw policy text into a flat list of display lines, preserving
    blank lines between paragraphs. `width` is roughly the number of
    Helvetica-10 chars that fit between the margins.
    """
    out: list[str] = []
    for para in (content or "").splitlines():
        if not para.strip():
            out.append("")
            continue
        wrapped = textwrap.wrap(
            para,
            width=width,
            replace_whitespace=False,
            drop_whitespace=False,
            break_long_words=True,
            break_on_hyphens=True,
        )
        out.extend(wrapped or [""])
    return out


def _draw_header_footer(
    page: fitz.Page,
    *,
    title: str,
    subtitle: str,
    page_idx: int,
    total_pages: int,
) -> None:
    # Header — title on top-left, subtitle right under it
    page.insert_text(
        (_MARGIN, _MARGIN - 8),
        title,
        fontname=_FONT_BODY,
        fontsize=_TITLE_SIZE,
        color=_DARK,
    )
    page.insert_text(
        (_MARGIN, _MARGIN + 8),
        subtitle,
        fontname=_FONT_BODY,
        fontsize=_META_SIZE,
        color=_GREY,
    )
    # Accent line
    page.draw_line(
        fitz.Point(_MARGIN, _MARGIN + 16),
        fitz.Point(_PAGE_W - _MARGIN, _MARGIN + 16),
        color=_ACCENT,
        width=1.0,
    )
    # Footer — left date, right page number
    footer_y = _PAGE_H - _MARGIN + 8
    page.insert_text(
        (_MARGIN, footer_y),
        f"Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        fontname=_FONT_BODY,
        fontsize=_META_SIZE,
        color=_GREY,
    )
    page.insert_text(
        (_PAGE_W - _MARGIN - 70, footer_y),
        f"Page {page_idx + 1} of {total_pages}",
        fontname=_FONT_BODY,
        fontsize=_META_SIZE,
        color=_GREY,
    )


def build_policy_version_pdf(
    *,
    content: str,
    policy_name: str,
    version_number: int,
    version_type: str,
    change_summary: Optional[str] = None,
    compliance_score: Optional[float] = None,
) -> bytes:
    """Return a finalised PDF as bytes for the given policy version."""
    title = policy_name or "Policy Document"
    subtitle_bits = [f"Version {version_number}", version_type.replace("_", " ").title()]
    if compliance_score is not None:
        subtitle_bits.append(f"Est. compliance {round(compliance_score)}%")
    subtitle = "  ·  ".join(subtitle_bits)

    # Pre-paginate. Reserve top space for header + summary, footer for page no.
    body_top = _MARGIN + _HEADER_H
    body_bottom = _PAGE_H - _MARGIN - _FOOTER_H
    usable_h = body_bottom - body_top

    summary_lines: list[str] = []
    if change_summary:
        summary_lines.extend(_wrap_paragraphs(f"Summary: {change_summary}"))
        summary_lines.append("")  # spacer
    summary_block_h = len(summary_lines) * _LINE_H if summary_lines else 0

    body_lines = _wrap_paragraphs(content)
    if not body_lines:
        body_lines = ["(empty version content)"]

    # First page may have less room because of summary block.
    first_page_lines = max(1, int((usable_h - summary_block_h) / _LINE_H))
    other_page_lines = max(1, int(usable_h / _LINE_H))

    # Distribute lines across pages.
    pages: list[list[str]] = []
    remaining = body_lines[:]
    pages.append(remaining[:first_page_lines])
    remaining = remaining[first_page_lines:]
    while remaining:
        pages.append(remaining[:other_page_lines])
        remaining = remaining[other_page_lines:]

    total_pages = len(pages)
    doc = fitz.open()

    for i, lines in enumerate(pages):
        page = doc.new_page(width=_PAGE_W, height=_PAGE_H)
        _draw_header_footer(
            page,
            title=title,
            subtitle=subtitle,
            page_idx=i,
            total_pages=total_pages,
        )

        y = body_top
        # Summary on the first page only
        if i == 0 and summary_lines:
            for line in summary_lines:
                page.insert_text(
                    (_MARGIN, y),
                    line,
                    fontname=_FONT_BODY,
                    fontsize=_FONT_SIZE,
                    color=_GREY,
                )
                y += _LINE_H

        # Body
        for line in lines:
            page.insert_text(
                (_MARGIN, y),
                line,
                fontname=_FONT_BODY,
                fontsize=_FONT_SIZE,
                color=_DARK,
            )
            y += _LINE_H

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes
