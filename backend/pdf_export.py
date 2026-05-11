"""
backend/pdf_export.py

Premium PDF export for Himaya AI Compliance policy versions.

  ai_remediated  →  enterprise cover page, executive summary, before/after
                    comparison, and annotated AI-additions content.
  all other types →  clean paginated plain-text document (original behaviour).
"""
from __future__ import annotations

import functools
import re
import textwrap
from datetime import datetime, timezone
from typing import Optional

import fitz  # PyMuPDF


# ── Page geometry ─────────────────────────────────────────────────────────────
_W, _H = fitz.paper_size("a4")   # 595 × 842 pt
_M  = 52    # outer margin (used by simple PDF and legacy helpers)
_HH = 38    # legacy: used only by _build_simple_pdf
_FH = 28    # legacy: used only by _build_simple_pdf

# policyReport.js-matched layout constants (1 mm ≈ 2.835 pt)
_HDR_H    = 79   # dark header bar height (≈28 mm)
_STR_H    = 6    # emerald accent stripe height (≈2 mm)
_BODY_TOP = 108  # body content start y — matches jsPDF ctx.y=38 mm (107.7 pt)
_BODY_BOT = 794  # body content end y — matches jsPDF ensureRoom PAGE_H-18 mm (790 pt)

# ── Built-in PDF base-14 font shortnames ─────────────────────────────────────
_F  = "helv"   # Helvetica
_FB = "hebo"   # Helvetica-Bold
_FI = "heit"   # Helvetica-Oblique

# ── Colour palette (matches app Tailwind theme) ───────────────────────────────
_COVER_BG  = (0.059, 0.090, 0.165)   # slate-900  #0F172A  — cover background
_CARD_DARK = (0.114, 0.141, 0.196)   # slate-800  #1E293B  — dark card
_BODY_TEXT = (0.200, 0.255, 0.333)   # slate-700  #334155  — body copy
_MUTED     = (0.392, 0.455, 0.545)   # slate-500  #64748B  — secondary text
_DIM       = (0.573, 0.631, 0.722)   # slate-400  #94A3B8  — tertiary / meta
_BORDER    = (0.820, 0.855, 0.886)   # slate-300  #CBD5E1  — subtle borders
_CARD_LT   = (0.973, 0.984, 0.996)   # slate-50   #F8FAFC  — light card bg
_TEXT_DARK = (0.059, 0.090, 0.165)   # slate-900  — headings on white pages
_ACCENT    = (0.063, 0.725, 0.506)   # emerald-500  #10B981
_ACCENT_D  = (0.024, 0.573, 0.376)   # emerald-600  #059669
_AMBER     = (0.851, 0.467, 0.024)   # amber-600
_RED       = (0.753, 0.122, 0.122)   # red-600
_WHITE     = (1.000, 1.000, 1.000)

# Pre-computed layout constant (avoids repeated arithmetic per call)
_CW = 491.0  # content width = _W − 2×_M = 595 − 104 (set after _M is known)


# ── Font cache + text-width measurement ───────────────────────────────────────
# fitz.Font() is expensive to construct. Cache one instance per font name and
# use functools.lru_cache on _tw() so repeated identical measurements are free.

_FONT_CACHE: dict[str, fitz.Font] = {}


def _get_font(name: str) -> fitz.Font:
    if name not in _FONT_CACHE:
        _FONT_CACHE[name] = fitz.Font(name)
    return _FONT_CACHE[name]


@functools.lru_cache(maxsize=2048)
def _tw(text: str, font: str = _F, size: float = 10.0) -> float:
    """Return the rendered width of *text* in points (cached per (text,font,size))."""
    try:
        return _get_font(font).text_length(text, fontsize=size)
    except Exception:
        return len(text) * size * 0.52   # rough fallback


def _t(page: fitz.Page, x: float, y: float, text: str, *,
       font: str = _F, size: float = 10.0, color=_TEXT_DARK) -> None:
    page.insert_text(fitz.Point(x, y), text, fontname=font, fontsize=size, color=color)


def _ct(page: fitz.Page, y: float, text: str, *,
        font: str = _F, size: float = 10.0, color=_TEXT_DARK) -> None:
    """Centre text horizontally on the page."""
    _t(page, (_W - _tw(text, font, size)) / 2, y, text, font=font, size=size, color=color)


def _ct_in(page: fitz.Page, x0: float, x1: float, y: float, text: str, *,
           font: str = _F, size: float = 10.0, color=_TEXT_DARK) -> None:
    """Centre text within the band [x0, x1]."""
    w = _tw(text, font, size)
    _t(page, x0 + (x1 - x0 - w) / 2, y, text, font=font, size=size, color=color)


def _hline(page: fitz.Page, y: float, *,
           x0: float = _M, x1: float = 0.0,
           color=_BORDER, width: float = 0.8) -> None:
    page.draw_line(fitz.Point(x0, y), fitz.Point(x1 or _W - _M, y),
                   color=color, width=width)


def _vline(page: fitz.Page, x: float, y0: float, y1: float, *,
           color=_BORDER, width: float = 0.8) -> None:
    page.draw_line(fitz.Point(x, y0), fitz.Point(x, y1), color=color, width=width)


def _safe_radius(radius: float, x0: float, y0: float, x1: float, y1: float) -> float:
    """Clamp radius so it never exceeds half the shorter rect side."""
    if radius <= 0:
        return 0.0
    w = abs(x1 - x0)
    h = abs(y1 - y0)
    if w <= 0 or h <= 0:
        return 0.0
    # Must be strictly less than half the shorter side; subtract a small margin
    # to stay clear of the boundary across PyMuPDF versions.
    return max(0.0, min(float(radius), w / 2.0 - 0.1, h / 2.0 - 0.1))


def _box(page: fitz.Page, x0: float, y0: float, x1: float, y1: float, *,
         fill=None, stroke=None, width: float = 0.8, radius: float = 0) -> None:
    r = fitz.Rect(x0, y0, x1, y1)
    kw: dict = {"color": stroke, "fill": fill, "width": width}
    safe_r = _safe_radius(radius, x0, y0, x1, y1)
    if safe_r > 0:
        kw["radius"] = safe_r
    try:
        page.draw_rect(r, **kw)
    except (ValueError, TypeError):
        # Radius still rejected (e.g. older PyMuPDF version or unexpected
        # constraint); fall back to a sharp-cornered rectangle.
        kw.pop("radius", None)
        try:
            page.draw_rect(r, **kw)
        except Exception:
            pass  # skip rather than crash the entire PDF


# ── Running header / footer — matches policyReport.js drawHeader / drawFooter ──

def _header(page: fitz.Page, policy_name: str) -> None:
    """Dark slate-900 header bar + emerald stripe, matching policyReport.js."""
    # Dark bar
    _box(page, 0, 0, _W, _HDR_H, fill=_TEXT_DARK)
    # Emerald accent stripe beneath bar
    _box(page, 0, _HDR_H, _W, _HDR_H + _STR_H, fill=_ACCENT)
    # Logo block (rounded square with "H" — mirrors Sidebar/Home logo)
    # Position matches jsPDF: logo at (MARGIN=16mm, 8mm), size 12mm → (22.7, 22.7) 34pt
    _box(page, _M, 23, _M + 34, 57, fill=_ACCENT_D, radius=5)
    _t(page, _M + 10, 48, "H", font=_FB, size=16, color=_WHITE)
    # Brand name + tagline — jsPDF y=13.5mm=38pt and y=18mm=51pt
    _t(page, _M + 40, 38, "Himaya",       font=_FB, size=14, color=_WHITE)
    _t(page, _M + 40, 51, "AI COMPLIANCE", font=_F,  size=8,  color=_DIM)
    # Right side — same y positions as brand text
    title = "AI REMEDIATED POLICY"
    _t(page, _W - _M - _tw(title, _FB, 10), 38, title, font=_FB, size=10, color=_WHITE)
    label = (policy_name[:44] + "…") if len(policy_name) > 44 else policy_name
    _t(page, _W - _M - _tw(label, _F, 8), 51, label, font=_F, size=8, color=_DIM)


def _footer(page: fitz.Page, page_n: int, total: int) -> None:
    """Three-item footer: date left, brand center, page right — matches policyReport.js."""
    line_y = _H - 34
    _hline(page, line_y, color=_BORDER, width=0.2)
    ty = line_y + 17   # jsPDF: PAGE_H-6mm = 291mm = 825pt; line at 808, so +17
    date_s = datetime.now(timezone.utc).strftime("%B %d, %Y")
    _t(page, _M, ty, f"Generated {date_s}", font=_F, size=8, color=_MUTED)
    pg = f"Page {page_n} of {total}"
    _t(page, _W - _M - _tw(pg, _F, 8), ty, pg, font=_F, size=8, color=_MUTED)
    brand = "Himaya · AI Compliance Platform"
    _ct(page, ty, brand, font=_F, size=8, color=_MUTED)


# ── Parse helpers ─────────────────────────────────────────────────────────────

def _parse_stats(summary: str, compliance_score: Optional[float]) -> dict:
    s: dict = {
        "total_fixed":    0,
        "total_targeted": 0,
        "original_score": 0.0,
        "new_score":      compliance_score or 0.0,
        "delta":          0.0,
    }
    m = re.search(r"(\d+)/(\d+)\s+targeted", summary)
    if m:
        s["total_fixed"]    = int(m.group(1))
        s["total_targeted"] = int(m.group(2))
    m = re.search(r"Score:\s*([\d.]+)%\s*[→>]\s*([\d.]+)%", summary)
    if m:
        s["original_score"] = float(m.group(1))
        s["new_score"]      = float(m.group(2))
    s["delta"] = round(s["new_score"] - s["original_score"], 1)
    return s


def _split_content(content: str) -> tuple[str, str]:
    """Split merged policy text into (original_text, ai_additions_text)."""
    SEP = "================================================================"
    idx = content.find(SEP)
    if idx == -1:
        return content.strip(), ""
    original = content[:idx].strip()
    rest     = content[idx:].splitlines()
    # Skip the 3-line separator block: ====, label, ====
    skip, eq = 0, 0
    for i, ln in enumerate(rest):
        if ln.startswith("==="):
            eq += 1
            if eq == 2:
                skip = i + 1
                break
    ai_part = "\n".join(rest[skip:]).strip()
    return original, ai_part


_HEADING_RE = re.compile(
    r"^(\d+\.)+\d*\s+\w"                         # 1.2.3 Numbered heading
    r"|^[A-Z][A-Z\s\-&:,()/\d]{5,}$"             # ALL CAPS HEADING
    r"|^(Section|SECTION|Chapter|CHAPTER"
    r"|Article|ARTICLE|Annex|ANNEX)\s+\d"
    r"|^#{1,3}\s+"                                # Markdown
    r"|^[IVX]+\.\s+\w"                            # Roman numerals
)


def _is_heading(line: str) -> bool:
    s = line.strip()
    return bool(s and len(s) <= 100 and _HEADING_RE.match(s))


# ── Line heights for original-policy content pages (pt) ──────────────────────
# orig_label uses _section_title style: 28pt total (bar 17pt + 11pt gap below)
_LH: dict[str, float] = {
    "orig_label": 28,
    "h1":         20,
    "h2":         18,
    "body":       14,
    "blank":       7,
}


def _dedupe_lines(text: str) -> list[str]:
    """Return splitlines with consecutive duplicate non-empty lines removed.

    Policy chunks overlap by ~100 chars. Reassembling them produces repeated
    sentences/headings at every boundary. A sliding window of 8 recent
    non-empty lines catches all such artifacts without touching legitimate
    repeated phrases that are far apart.
    """
    seen: list[str] = []  # ring of last 8 non-empty lines
    out: list[str] = []
    for raw in text.splitlines():
        s = raw.strip()
        if s:
            if s in seen:
                continue  # duplicate from chunk overlap — skip
            seen.append(s)
            if len(seen) > 8:
                seen.pop(0)
        out.append(raw)
    return out


def _build_lines(original: str) -> list[tuple[str, str]]:
    """Convert original policy text into a flat (kind, text) line list for pagination."""
    out: list[tuple[str, str]] = []

    def add(k: str, t: str = "") -> None:
        out.append((k, t))

    add("orig_label", "ORIGINAL POLICY DOCUMENT")
    add("blank")

    prev_blank = True
    for raw in _dedupe_lines(original):
        s = raw.strip()
        if not s:
            if not prev_blank:
                add("blank")
            prev_blank = True
            continue
        prev_blank = False
        if _is_heading(s):
            if not prev_blank:
                add("blank")
            kind = "h1" if (len(s) <= 60 or re.match(r"^[A-Z\s]{5,}$|^(\d+\.)+", s)) else "h2"
            add(kind, s)
            prev_blank = False
        else:
            for wl in textwrap.wrap(s, width=88, break_long_words=True) or ["—"]:
                add("body", wl)

    return out


def _paginate(lines: list[tuple[str, str]]) -> list[list[tuple[str, str]]]:
    """Distribute lines across pages; return a list of per-page line lists."""
    usable = _BODY_BOT - _BODY_TOP

    pages: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []
    y_used = 0.0

    for kind, text in lines:
        lh = _LH.get(kind, 14)
        # Never start a page with blank lines
        if kind == "blank" and y_used == 0:
            continue
        if y_used + lh > usable:
            if current:
                pages.append(current)
            current = []
            y_used  = 0.0
            if kind == "blank":
                continue
        current.append((kind, text))
        y_used += lh

    if current:
        pages.append(current)

    return pages or [[("body", "(no content)")]]


def _render_line(page: fitz.Page, kind: str, text: str, y: float) -> None:
    """Draw one content line at baseline y."""
    x = _M

    if kind == "orig_label":
        # Section title style — matches _section_title helper exactly
        _box(page, x, y, x + 8.5, y + 17, fill=_ACCENT)
        _t(page, x + 11, y + 14, text, font=_FB, size=13, color=_TEXT_DARK)

    elif kind == "h1":
        _t(page, x, y, text, font=_FB, size=12, color=_TEXT_DARK)

    elif kind == "h2":
        _t(page, x, y, text, font=_FB, size=10.5, color=_TEXT_DARK)

    elif kind == "body":
        _t(page, x, y, text, font=_F, size=10, color=_BODY_TEXT)

    elif kind == "blank":
        pass  # vertical whitespace only


def _render_content_pages(
    doc: fitz.Document,
    pages_data: list[list[tuple[str, str]]],
    policy_name: str,
    version_number: int,
    page_offset: int,
    total_pages: int,
) -> None:
    body_top = float(_BODY_TOP)
    for ci, page_lines in enumerate(pages_data):
        page = doc.new_page(width=_W, height=_H)
        _header(page, policy_name)
        _footer(page, page_offset + ci, total_pages)
        y = body_top
        for kind, text in page_lines:
            _render_line(page, kind, text, y)
            y += _LH.get(kind, 14)


# ── AI finding-block rendering — matches policyReport.js drawGapsList exactly ──

# Finding-block constants — all converted from jsPDF drawGapsList mm values
# jsPDF blockH = 14mm + n*4mm; gap = 3mm; accent 2mm w / 1mm r; card r = 2mm
_BLK_HDR     = 39.7   # header area (14mm = 39.7pt)
_BLK_LINE    = 11.3   # body line-height (4mm = 11.3pt) — matches jsPDF descLines * 4
_BLK_PAD     = 6.0    # bottom padding inside card
_BLK_GAP     = 8.5    # gap between blocks (3mm = 8.5pt)
_ACC_W       = 5.7    # left accent strip width (2mm = 5.7pt)
_BADGE_H     = 14.2   # badge height (5mm = 14.2pt)
_PAGE_USABLE = _BODY_BOT - _BODY_TOP


def _block_height(n_body: int) -> float:
    """Total card height — mirrors jsPDF: 14mm + n*4mm."""
    return _BLK_HDR + n_body * _BLK_LINE + _BLK_PAD


_AI_SEP_RE  = re.compile(r"^={6,}$")
_AI_META_RE = re.compile(
    r"^(AI-REMEDIATED ADDITIONS|Targets:|ECC reference coverage:|"
    r"AI-Generated Additi|Himaya AI Additi)",
    re.IGNORECASE,
)
# Matches a first "word" that is clearly the tail of a split word
# e.g. "cording", "ness need", "ss need", "or internet-facing"
_AI_FRAGMENT_RE = re.compile(r"^[a-z]{1,6}[a-z\s]")


def _normalize_ai_text(text: str) -> str:
    """Remove corruption artifacts from AI additions text before PDF rendering.

    Handles: embedded separator lines, metadata headers, mid-word fragment
    lines, and consecutive duplicate paragraphs that arise when AI text was
    concatenated from multiple generation passes or chunk-overlap reassembly.
    """
    if not text or not text.strip():
        return ""

    # ── Pass 1: line-level filtering ──────────────────────────────────────
    clean: list[str] = []
    seen_norm: list[str] = []   # sliding window — last 20 non-empty lines

    for raw in text.splitlines():
        s = raw.strip()

        # Drop separator lines
        if _AI_SEP_RE.match(s):
            continue

        # Drop metadata header lines (separator label + targets list)
        if s and _AI_META_RE.match(s):
            continue

        # Drop fragment lines: start with a lowercase char sequence that is
        # NOT a normal sentence opener. These are mid-word remnants from
        # chunk-overlap concatenation, e.g. "cording to risk", "ss need."
        if s and _AI_FRAGMENT_RE.match(s) and len(s) < 60:
            first_word = s.split()[0]
            # Allow known lowercase sentence starters
            _SENTENCE_STARTS = {
                "the", "a", "an", "all", "any", "each", "in", "if",
                "when", "where", "while", "which", "who", "this", "that",
                "these", "those", "it", "its", "such", "for", "on", "at",
                "by", "with", "without", "no", "not", "one", "two", "three",
            }
            if first_word.rstrip(".,;:") not in _SENTENCE_STARTS:
                continue

        # Exact duplicate in sliding window
        if s:
            norm = " ".join(s.split()).lower()
            if norm in seen_norm:
                continue
            seen_norm.append(norm)
            if len(seen_norm) > 20:
                seen_norm.pop(0)

        clean.append(raw)

    # ── Pass 2: paragraph-level duplicate detection ───────────────────────
    # Group consecutive non-blank lines into paragraph units, hash each.
    result: list[str] = []
    seen_para: set[int] = set()
    buf: list[str] = []

    def _flush_buf() -> None:
        if not buf:
            return
        norm = " ".join(" ".join(ln.split()) for ln in buf).lower()
        h = hash(norm)
        if h not in seen_para:
            seen_para.add(h)
            result.extend(buf)
        buf.clear()

    for line in clean:
        if line.strip():
            buf.append(line)
        else:
            _flush_buf()
            result.append(line)
    _flush_buf()

    joined = "\n".join(result)
    # Collapse 3+ blank lines → 1 blank line
    return re.sub(r"\n{3,}", "\n\n", joined).strip()


def _build_ai_blocks(ai_text: str) -> list[dict]:
    """Group AI additions text into finding-block dicts: {title, body: [lines]}."""
    blocks: list[dict] = []
    current_title: Optional[str] = None
    current_body: list[str] = []
    seen_headings: set[str] = set()   # heading-level dedup across the full doc
    skip_until_heading = False        # True when we're inside a duplicate-heading section

    max_body_w = 84  # chars — slightly narrower than content to stay inside card padding

    def flush() -> None:
        # Only keep blocks that have at least 2 body lines — single-line and
        # empty blocks are corruption fragments, not real AI additions.
        if current_title is not None and len(current_body) >= 2:
            blocks.append({"title": current_title, "body": current_body[:]})

    for raw in _normalize_ai_text(ai_text).splitlines():
        s = raw.strip()
        if not s:
            continue
        if _is_heading(s):
            flush()
            norm_h = " ".join(s.split()).lower()
            if norm_h in seen_headings:
                # Duplicate heading — skip until the next unique heading
                current_title = None
                current_body = []
                skip_until_heading = True
            else:
                seen_headings.add(norm_h)
                current_title = s
                current_body = []
                skip_until_heading = False
        else:
            if skip_until_heading:
                continue
            if current_title is None:
                current_title = "AI Remediation Addition"
                current_body = []
            for wl in textwrap.wrap(s, width=max_body_w, break_long_words=True) or ["—"]:
                current_body.append(wl)

    flush()
    return blocks


def _paginate_blocks(blocks: list[dict]) -> list[list[dict]]:
    """Distribute finding blocks across pages without splitting a block mid-card."""
    # First AI page reserves space for section title + intro line
    first_reserved = 60.0
    usable_first   = _PAGE_USABLE - first_reserved
    usable_other   = _PAGE_USABLE

    pages: list[list[dict]] = []
    current: list[dict] = []
    y_used = 0.0
    usable = usable_first

    for block in blocks:
        bh = _block_height(len(block["body"])) + _BLK_GAP
        # Clamp oversized single blocks so they never overflow a page
        if bh > usable_other:
            max_lines = max(1, int((usable_other - _BLK_HDR - _BLK_PAD - _BLK_GAP) / _BLK_LINE))
            block = {"title": block["title"], "body": block["body"][:max_lines]}
            bh = _block_height(len(block["body"])) + _BLK_GAP

        if y_used > 0 and y_used + bh > usable:
            pages.append(current)
            current = []
            y_used  = 0.0
            usable  = usable_other

        current.append(block)
        y_used += bh

    if current:
        pages.append(current)

    return pages or [[]]


def _render_finding_block(page: fitz.Page, y: float, block: dict) -> float:
    """Render one finding block — policyReport.js drawGapsList exact replica.

    jsPDF: roundedRect(MARGIN, y, pageW-2M, blockH, 2, 2); accent roundedRect(MARGIN, y, 2, blockH, 1, 1);
    title at MARGIN+5mm=14pt, y+6mm=17pt; badge at top-right, h=5mm=14pt;
    desc at MARGIN+5mm=14pt, y+11mm=31pt; line spacing 4mm=11.3pt; gap ctx.y+=3mm=8.5pt.
    """
    title  = block["title"]
    body   = block["body"]
    bh     = _block_height(len(body))

    # Card: 2mm radius — matches jsPDF roundedRect(..., 2, 2, "FD")
    _box(page, _M, y, _W - _M, y + bh, fill=_CARD_LT, stroke=_BORDER, width=0.5, radius=5.7)
    # Left accent: 2mm wide, 1mm radius
    _box(page, _M, y, _M + _ACC_W, y + bh, fill=_ACCENT, radius=2.8)

    # Title — 9pt bold slate-900 at MARGIN+5mm=14pt, y+6mm=17pt
    title_trim = (title[:68] + "…") if len(title) > 68 else title
    _t(page, _M + 14, y + 17, title_trim, font=_FB, size=9, color=_TEXT_DARK)

    # Badge — top-right pill; jsPDF: y+2mm=5.7pt top, h=5mm=14.2pt, text at y+5.5mm=15.6pt
    badge  = "AI ADDITION"
    pill_w = _tw(badge, _FB, 7.5) + 8
    _box(page, _W - _M - pill_w - 5.7, y + 5.7, _W - _M - 5.7, y + 5.7 + _BADGE_H,
         fill=_ACCENT, radius=2.8)
    _t(page, _W - _M - pill_w - 1.7, y + 15.6, badge, font=_FB, size=7.5, color=_WHITE)

    # Body — 9pt slate-700 at MARGIN+5mm=14pt, y+11mm=31pt, spacing 4mm=11.3pt
    for i, ln in enumerate(body):
        _t(page, _M + 14, y + 31 + i * _BLK_LINE, ln, font=_F, size=9, color=_BODY_TEXT)

    return y + bh + _BLK_GAP


def _render_ai_pages(
    doc: fitz.Document,
    ai_pages: list[list[dict]],
    policy_name: str,
    page_offset: int,
    total_pages: int,
) -> None:
    """Render AI finding blocks — one card per AI addition, matching the gaps list style."""
    for ci, blocks in enumerate(ai_pages):
        page = doc.new_page(width=_W, height=_H)
        _header(page, policy_name)
        _footer(page, page_offset + ci, total_pages)
        y = float(_BODY_TOP)

        if ci == 0:
            y = _section_title(page, y, "AI-Generated Remediation Additions")
            intro = (
                "The following additions were generated by Himaya AI to address compliance "
                "gaps identified during policy analysis. They do not alter existing content."
            )
            _t(page, _M, y, intro[:90], font=_FI, size=9, color=_MUTED)
            y += 16

        for block in blocks:
            y = _render_finding_block(page, y, block)


# ── Shared drawing helpers — match policyReport.js primitives exactly ─────────

def _section_title(page: fitz.Page, y: float, title: str) -> float:
    """Emerald left-bar + bold title — policyReport.js drawSectionTitle exact replica.

    jsPDF: rect(MARGIN, y, 3mm=8.5pt, 6mm=17pt); text at MARGIN+6mm=17pt, y+5mm=14pt.
    Advances ctx.y by 10mm = 28pt.
    """
    _box(page, _M, y, _M + 8.5, y + 17, fill=_ACCENT)
    _t(page, _M + 11, y + 14, title, font=_FB, size=13, color=_TEXT_DARK)
    return y + 28


def _metric_cards(page: fitz.Page, y: float, cards: list) -> float:
    """Four equal metric cards — policyReport.js drawSummaryCards exact replica.

    jsPDF: gap=3mm=8.5pt; card h=22mm=62pt, r=2mm=5.7pt; accent r=1mm=2.8pt;
    label at x+5mm=14pt, y+7mm=20pt; value at x+5mm, y+16mm=45pt.
    Advances ctx.y by 28mm = 79pt.
    """
    gap    = 8.5   # 3mm — matches jsPDF gap between cards
    card_w = (_W - 2 * _M - 3 * gap) / 4
    for i, (label, val, accent) in enumerate(cards):
        cx = _M + i * (card_w + gap)
        # Card: 22mm tall, 2mm radius
        _box(page, cx, y, cx + card_w, y + 62,
             fill=_CARD_LT, stroke=_BORDER, width=0.5, radius=5.7)
        # Left accent strip: 2mm wide, 1mm radius
        _box(page, cx, y, cx + 5.7, y + 62, fill=accent, radius=2.8)
        # Label — 8pt uppercase slate-500 at x+5mm, y+7mm
        ll = label.split("\n")
        _t(page, cx + 14, y + 20, ll[0].upper(), font=_F, size=8, color=_MUTED)
        if len(ll) > 1:
            _t(page, cx + 14, y + 29, ll[1].upper(), font=_F, size=8, color=_MUTED)
        # Value — 15pt bold slate-900 at x+5mm, y+16mm
        _t(page, cx + 14, y + 46, val, font=_FB, size=15, color=_TEXT_DARK)
    return y + 79   # 22mm card + 6mm gap = 28mm = 79pt


def _kv_grid(page: fitz.Page, y: float, pairs: list) -> float:
    """Two-column key/value grid — policyReport.js drawKeyValueGrid exact replica.

    jsPDF: ctx.y+=2mm=6pt before first row; label at ctx.y, 8pt; value at ctx.y+5mm=14pt;
    advances ctx.y by 12mm=34pt per row.
    """
    col_w = (_W - 2 * _M) / 2
    y += 6   # 2mm initial gap — matches jsPDF ctx.y += 2
    for i in range(0, len(pairs), 2):
        row = pairs[i:i + 2]
        for j, (label, val) in enumerate(row):
            px = _M + j * col_w
            _t(page, px, y, label.upper(), font=_F, size=8, color=_MUTED)
            v_str   = str(val or "—")
            v_lines = textwrap.wrap(v_str, width=38) or ["—"]
            _t(page, px, y + 14, v_lines[0], font=_FB, size=10, color=_TEXT_DARK)
        y += 34   # 12mm row height
    return y


# ── Summary page — matches policyReport.js section structure exactly ──────────

def _make_report_summary(
    doc: fitz.Document,
    policy_name: str,
    version_number: int,
    stats: dict,
    change_summary: str,
    total_pages: int,
) -> None:
    page = doc.new_page(width=_W, height=_H)
    _header(page, policy_name)
    _footer(page, 1, total_pages)

    y = float(_BODY_TOP)

    # ── Policy overview (drawKeyValueGrid style) ──────────────────────────────
    y = _section_title(page, y, "Policy overview")
    y = _kv_grid(page, y, [
        ("Policy",           policy_name),
        ("Version",          str(version_number)),
        ("Type",             "AI Remediated"),
        ("Compliance score", f"{stats['new_score']:.1f}%"),
    ])
    y += 10

    # ── Remediation statistics (drawSummaryCards style) ───────────────────────
    y = _section_title(page, y, "Remediation statistics")
    remaining = max(0, stats["total_targeted"] - stats["total_fixed"])
    rate      = (round(stats["total_fixed"] / stats["total_targeted"] * 100, 1)
                 if stats["total_targeted"] else 0.0)
    y = _metric_cards(page, y, [
        ("Controls\ntargeted", str(stats["total_targeted"]), _MUTED),
        ("Controls\nfixed",    str(stats["total_fixed"]),    _ACCENT),
        ("Remaining\ngaps",    str(remaining),               _AMBER if remaining else _MUTED),
        ("Remediation\nrate",  f"{rate:.0f}%",               _ACCENT if rate >= 80 else _AMBER),
    ])
    y += 10

    # ── Compliance improvement (drawKeyValueGrid style) ───────────────────────
    y = _section_title(page, y, "Compliance improvement")
    sign = "+" if stats["delta"] >= 0 else ""
    y = _kv_grid(page, y, [
        ("Score before", f"{stats['original_score']:.1f}%"),
        ("Score after",  f"{stats['new_score']:.1f}%"),
        ("Improvement",  f"{sign}{stats['delta']:.1f}%"),
        ("Gaps targeted", str(stats["total_targeted"])),
    ])
    y += 10

    # ── Remediation overview (plain text body) ────────────────────────────────
    y = _section_title(page, y, "Remediation overview")
    summary_clean = re.sub(r"AI-remediated version:\s*", "", change_summary)
    for ln in textwrap.wrap(summary_clean, width=90) or [summary_clean]:
        if y + 14 > _BODY_BOT - 60:
            break
        _t(page, _M, y, ln, font=_F, size=9.5, color=_BODY_TEXT)
        y += 14

    # ── Advisory notice (gap-block style, amber left accent) ─────────────────
    notice_top = max(y + 10, _BODY_BOT - 52)
    if notice_top + 48 <= _BODY_BOT:
        _box(page, _M, notice_top, _W - _M, notice_top + 48,
             fill=_CARD_LT, stroke=_BORDER, width=0.5, radius=5.7)
        _box(page, _M, notice_top, _M + 5.7, notice_top + 48, fill=_AMBER, radius=2.8)
        _t(page, _M + 10, notice_top + 15, "Advisory Notice",
           font=_FB, size=9, color=_TEXT_DARK)
        notice = (
            "AI-generated remediation is advisory only. "
            "Review with a qualified compliance officer before incorporating into official documents."
        )
        for i, wl in enumerate(textwrap.wrap(notice, width=86)):
            _t(page, _M + 10, notice_top + 28 + i * 13, wl, font=_FI, size=8.5, color=_MUTED)


# ── AI Remediated PDF builder ─────────────────────────────────────────────────

def _build_ai_remediated_pdf(
    content: str,
    policy_name: str,
    version_number: int,
    change_summary: Optional[str],
    compliance_score: Optional[float],
) -> bytes:
    stats            = _parse_stats(change_summary or "", compliance_score)
    original, ai     = _split_content(content)

    # Original section — line-by-line pagination (same renderer as any policy PDF)
    orig_lines       = _build_lines(original)
    orig_pages       = _paginate(orig_lines)

    # AI additions — finding-block pagination (matches policyReport.js drawGapsList)
    ai_blocks        = _build_ai_blocks(ai) if ai else []
    ai_pages         = _paginate_blocks(ai_blocks) if ai_blocks else []

    total_pages      = 1 + len(orig_pages) + len(ai_pages)   # summary + orig + ai
    ai_page_offset   = 2 + len(orig_pages)                   # page number of first AI page

    doc = fitz.open()
    _make_report_summary(doc, policy_name, version_number, stats,
                         change_summary or "", total_pages)
    _render_content_pages(doc, orig_pages, policy_name, version_number,
                          2, total_pages)
    if ai_pages:
        _render_ai_pages(doc, ai_pages, policy_name, ai_page_offset, total_pages)

    # deflate=True produces a ~30-40% smaller file and opens faster in viewers
    pdf_bytes = doc.tobytes(garbage=3, deflate=True, deflate_images=True)
    doc.close()
    return pdf_bytes


# ── Plain paginated builder (original types) ──────────────────────────────────

def _wrap_paragraphs(content: str, width: int = 95) -> list[str]:
    out: list[str] = []
    for para in (content or "").splitlines():
        if not para.strip():
            out.append("")
            continue
        wrapped = textwrap.wrap(
            para, width=width,
            replace_whitespace=False, drop_whitespace=False,
            break_long_words=True, break_on_hyphens=True,
        )
        out.extend(wrapped or [""])
    return out


_PLAIN_DARK   = (0.10, 0.10, 0.12)
_PLAIN_GREY   = (0.45, 0.45, 0.50)
_PLAIN_ACCENT = (0.06, 0.55, 0.42)
_LINE_H       = 13.5
_FONT_SIZE    = 10
_TITLE_SIZE   = 14
_META_SIZE    = 9


def _plain_header_footer(
    page: fitz.Page, title: str, subtitle: str, page_idx: int, total: int,
) -> None:
    page.insert_text((_M, _M - 8), title,
                     fontname=_F, fontsize=_TITLE_SIZE, color=_PLAIN_DARK)
    page.insert_text((_M, _M + 8), subtitle,
                     fontname=_F, fontsize=_META_SIZE, color=_PLAIN_GREY)
    page.draw_line(fitz.Point(_M, _M + 16), fitz.Point(_W - _M, _M + 16),
                   color=_PLAIN_ACCENT, width=1.0)
    fy = _H - _M + 8
    page.insert_text(
        (_M, fy),
        f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        fontname=_F, fontsize=_META_SIZE, color=_PLAIN_GREY,
    )
    page.insert_text(
        (_W - _M - 70, fy),
        f"Page {page_idx + 1} of {total}",
        fontname=_F, fontsize=_META_SIZE, color=_PLAIN_GREY,
    )


def _build_simple_pdf(
    content: str,
    policy_name: str,
    version_number: int,
    version_type: str,
    change_summary: Optional[str],
    compliance_score: Optional[float],
) -> bytes:
    title = policy_name or "Policy Document"
    bits  = [f"Version {version_number}", version_type.replace("_", " ").title()]
    if compliance_score is not None:
        bits.append(f"Est. compliance {round(compliance_score)}%")
    subtitle = "  ·  ".join(bits)

    body_top    = _M + 36
    body_bottom = _H - _M - 28
    usable_h    = body_bottom - body_top

    summary_lines: list[str] = []
    if change_summary:
        summary_lines.extend(_wrap_paragraphs(f"Summary: {change_summary}"))
        summary_lines.append("")
    summary_block_h = len(summary_lines) * _LINE_H if summary_lines else 0

    body_lines = _wrap_paragraphs(content)
    if not body_lines:
        body_lines = ["(empty version content)"]

    first_cap = max(1, int((usable_h - summary_block_h) / _LINE_H))
    other_cap = max(1, int(usable_h / _LINE_H))

    pages: list[list[str]] = []
    rem = body_lines[:]
    pages.append(rem[:first_cap])
    rem = rem[first_cap:]
    while rem:
        pages.append(rem[:other_cap])
        rem = rem[other_cap:]

    total = len(pages)
    doc   = fitz.open()

    for i, lines in enumerate(pages):
        pg = doc.new_page(width=_W, height=_H)
        _plain_header_footer(pg, title, subtitle, i, total)
        y = float(body_top)
        if i == 0 and summary_lines:
            for ln in summary_lines:
                pg.insert_text((_M, y), ln, fontname=_F,
                                fontsize=_FONT_SIZE, color=_PLAIN_GREY)
                y += _LINE_H
        for ln in lines:
            pg.insert_text((_M, y), ln, fontname=_F,
                            fontsize=_FONT_SIZE, color=_PLAIN_DARK)
            y += _LINE_H

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


# ── Public API — signature unchanged ─────────────────────────────────────────

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
    if version_type == "ai_remediated":
        return _build_ai_remediated_pdf(
            content=content,
            policy_name=policy_name,
            version_number=version_number,
            change_summary=change_summary,
            compliance_score=compliance_score,
        )
    return _build_simple_pdf(
        content=content,
        policy_name=policy_name,
        version_number=version_number,
        version_type=version_type,
        change_summary=change_summary,
        compliance_score=compliance_score,
    )
