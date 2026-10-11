#!/usr/bin/env python3
"""
Text processing pipeline: reading, cleaning, and chunking.
Supports TXT, PDF, DOCX, HTML/MD, EPUB, and raw text input.
"""

import os
import re
from typing import Generator, Tuple

from dependencies import PDF_SUPPORT, DOCX_SUPPORT, HTML_MD_SUPPORT, EPUB_SUPPORT


class TextProcessor:
    """Stateless text-processing utilities for audiobook generation."""

    # ── Streaming file readers ──────────────────────────────────

    @staticmethod
    def _read_raw_file(filepath: str) -> Generator[str, None, None]:
        ext = os.path.splitext(filepath)[1].lower()

        if ext == ".txt":
            with open(filepath, "r", encoding="utf-8") as fh:
                while True:
                    block = fh.read(65536)
                    if not block: break
                    yield block

        elif ext == ".pdf":
            if not PDF_SUPPORT: raise ImportError("pypdf missing")
            from pypdf import PdfReader
            for page in PdfReader(filepath).pages:
                t = page.extract_text()
                if t: yield t + "\n"

        elif ext == ".docx":
            if not DOCX_SUPPORT: raise ImportError("python-docx missing")
            from docx import Document
            for para in Document(filepath).paragraphs: yield para.text + "\n"

        elif ext in (".md", ".html", ".htm"):
            if not HTML_MD_SUPPORT: raise ImportError("beautifulsoup4 missing")
            from bs4 import BeautifulSoup
            with open(filepath, "r", encoding="utf-8") as fh: content = fh.read()
            if ext != ".md":
                soup = BeautifulSoup(content, "html.parser")
                for s in soup(["script", "style"]): s.decompose()
                yield soup.get_text(separator="\n")
            else: yield content

        elif ext == ".epub":
            if not EPUB_SUPPORT: raise ImportError("EbookLib missing")
            if not HTML_MD_SUPPORT: raise ImportError("beautifulsoup4 missing")
            from ebooklib import epub
            from bs4 import BeautifulSoup
            book = epub.read_epub(filepath)
            for item in book.get_items():
                if item.get_type() == 9:
                    try:
                        soup = BeautifulSoup(item.get_content(), "html.parser")
                        for s in soup(["script", "style"]): s.decompose()
                        t = soup.get_text(separator="\n")
                        if t.strip(): yield t + "\n"
                    except Exception: continue
        else:
            raise ValueError(f"Unsupported format: {ext}")

    @staticmethod
    def _read_raw_text(raw_text: str) -> Generator[str, None, None]:
        block_size = 5000
        for i in range(0, len(raw_text), block_size):
            yield raw_text[i: i + block_size]

    # ── Cleaning ────────────────────────────────────────────────

    @staticmethod
    def _clean_stream(text_stream) -> Generator[str, None, None]:
        for chunk in text_stream:
            chunk = re.sub(r"https?://\S+|www\.\S+|[\w\.-]+@[\w\.-]+", "", chunk)
            chunk = re.sub(r"-\s*\n\s*", "", chunk)
            chunk = re.sub(r"\s+", " ", chunk)
            if chunk.strip(): yield chunk

    # ── Chunking ────────────────────────────────────────────────

    @staticmethod
    def chunk_generator(source, max_chars=500, is_raw_text=False, split_chapters=False, chapter_regex=r"^Chapter\s+\d+") -> Generator[Tuple[int, str], None, None]:
        sentence_endings = re.compile(r"(?<=[.!?])\s+")
        buf = ""
        chapter_id = 0
        
        raw_stream = TextProcessor._read_raw_text(source) if is_raw_text else TextProcessor._read_raw_file(source)
        clean_stream = TextProcessor._clean_stream(raw_stream)
        
        for clean_chunk in clean_stream:
            if split_chapters:
                matches = list(re.finditer(chapter_regex, clean_chunk))
                if matches:
                    for match in matches:
                        before = clean_chunk[:match.start()]
                        if before.strip(): buf += before
                        if buf.strip():
                            for out in TextProcessor._drain_buffer(buf, max_chars, sentence_endings):
                                yield chapter_id, out
                            buf = ""
                        chapter_id += 1
                    clean_chunk = clean_chunk[matches[-1].end():]
            
            buf += clean_chunk
            while len(buf) > max_chars:
                m = sentence_endings.search(buf, 0, max_chars + 50)
                cp = m.end() if m else max_chars
                yield chapter_id, buf[:cp].strip()
                buf = buf[cp:].strip()
                
        if buf.strip():
            yield chapter_id, buf.strip()

    @staticmethod
    def _drain_buffer(buf, max_chars, sentence_endings):
        while len(buf) > max_chars:
            m = sentence_endings.search(buf, 0, max_chars + 50)
            cp = m.end() if m else max_chars
            yield buf[:cp].strip()
            buf = buf[cp:].strip()
        if buf.strip(): yield buf.strip()