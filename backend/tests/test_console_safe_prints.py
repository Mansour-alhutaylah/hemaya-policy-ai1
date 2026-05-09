"""Lock the analyzer print() statements to ASCII-encodable strings.

Why: Windows default console is cp1252. When the analyzer's stdout is piped
(through `tee`, redirection, or a subprocess wrapper that doesn't force
UTF-8), Python's TextIOWrapper raises UnicodeEncodeError on glyphs like
`-` (U+2013, en-dash) or `->` (U+2192, right-arrow). The exception
propagates out of the analyzer and rolls back the caller's transaction,
masquerading as a real failure. The Phase 10 live smoke hit this on
ecc2_analyzer.py's post-analysis confidence-distribution print.

This test scans the backend for `print(...)` statements containing common
non-cp1252 glyphs. It only flags print calls (not comments or docstrings)
because the cp1252 problem is exclusive to stdout encoding.

Run from repo root:
  python -m pytest backend/tests/test_console_safe_prints.py -v
"""
import re
from pathlib import Path

# Glyphs that have bitten us before. Add to the set when new ones surface.
DISALLOWED_GLYPHS = ["–", "—", "→"]  # en-dash, em-dash, right-arrow

# Files in scope: the analyzers and the FastAPI entry point. Tests, scripts,
# and frontend are out of scope. The plan file lives outside this tree.
BACKEND_FILES = [
    "backend/checkpoint_analyzer.py",
    "backend/ecc2_analyzer.py",
    "backend/sacs002_analyzer.py",
    "backend/framework_loader.py",
    "backend/main.py",
]


def _print_lines_with_glyphs(file_path):
    """Return list of (lineno, line) for print() statements containing
    any disallowed glyph. Uses a forgiving regex that matches `print(`
    on the same line; multi-line print() calls are uncommon here."""
    src = Path(file_path).read_text(encoding="utf-8")
    flagged = []
    for i, line in enumerate(src.splitlines(), start=1):
        if "print(" not in line:
            continue
        if any(g in line for g in DISALLOWED_GLYPHS):
            flagged.append((i, line.rstrip()))
    return flagged


def test_no_disallowed_glyphs_in_backend_print_calls():
    """Every print() in the backend must encode under cp1252."""
    failures = []
    for f in BACKEND_FILES:
        for lineno, line in _print_lines_with_glyphs(f):
            failures.append(f"{f}:{lineno}: {line}")
    assert not failures, (
        "These print() statements contain glyphs that crash on Windows "
        "cp1252 consoles. Replace en-dash/em-dash with '-' and right-arrow "
        "with '->'. Crashing here propagates out of the analyzer and rolls "
        "back the caller's transaction.\n  " + "\n  ".join(failures)
    )
