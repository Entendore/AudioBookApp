#!/usr/bin/env python3
"""
Optional-dependency detection for Advanced Audiobook Studio.
Each flag is checked once at import time and exposed as a module-level constant.
"""

# ── Core ──
try:
    import edge_tts  # noqa: F401
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False

# ── Document formats ──
try:
    from pypdf import PdfReader  # noqa: F401
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False

try:
    from docx import Document  # noqa: F401
    DOCX_SUPPORT = True
except ImportError:
    DOCX_SUPPORT = False

try:
    from bs4 import BeautifulSoup  # noqa: F401
    HTML_MD_SUPPORT = True
except ImportError:
    HTML_MD_SUPPORT = False

try:
    import ebooklib  # noqa: F401
    from ebooklib import epub  # noqa: F401
    EPUB_SUPPORT = True
except ImportError:
    EPUB_SUPPORT = False

# ── Platform helpers ──
try:
    from plyer import filechooser  # noqa: F401
    PLYER_AVAILABLE = True
except ImportError:
    PLYER_AVAILABLE = False


def format_support_summary() -> str:
    """Return a human-readable summary of available format support."""
    lines = [
        f"edge-tts:  {'✓' if EDGE_TTS_AVAILABLE else '✗'}",
        f"PDF:       {'✓' if PDF_SUPPORT else '✗'} (pypdf)",
        f"DOCX:      {'✓' if DOCX_SUPPORT else '✗'} (python-docx)",
        f"HTML/MD:   {'✓' if HTML_MD_SUPPORT else '✗'} (beautifulsoup4)",
        f"EPUB:      {'✓' if EPUB_SUPPORT else '✗'} (EbookLib)",
        f"Native Chooser: {'✓' if PLYER_AVAILABLE else '✗'} (plyer)",
    ]
    return "\n".join(lines)