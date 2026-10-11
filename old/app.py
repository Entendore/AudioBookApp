#!/usr/bin/env python3
"""
Advanced Audiobook Studio - Kivy Edition
Single-file application for Desktop and Android
Includes Advanced Effects, Chapter Splitting, Loudness Norm, Preview, and Player.

Required: pip install kivy edge-tts
Optional: pip install pypdf python-docx beautifulsoup4 EbookLib plyer
FFmpeg: Required for WAV output, Audio Effects, Pauses, and Chapter Splitting.
"""

import os
import sys
import re
import json
import asyncio
import threading
import subprocess
import tempfile
import shutil
import heapq
from dataclasses import dataclass, field

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.slider import Slider
from kivy.uix.checkbox import CheckBox
from kivy.uix.progressbar import ProgressBar
from kivy.uix.scrollview import ScrollView
from kivy.uix.popup import Popup
from kivy.uix.togglebutton import ToggleButton
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp, sp
from kivy.lang import Builder
from kivy.utils import platform as kivy_platform
from kivy.core.audio import SoundLoader

# ──────────────────── Optional Dependencies ────────────────────
try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False

try:
    from pypdf import PdfReader
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False

try:
    from docx import Document
    DOCX_SUPPORT = True
except ImportError:
    DOCX_SUPPORT = False

try:
    from bs4 import BeautifulSoup
    HTML_MD_SUPPORT = True
except ImportError:
    HTML_MD_SUPPORT = False

try:
    import ebooklib
    from ebooklib import epub
    EPUB_SUPPORT = True
except ImportError:
    EPUB_SUPPORT = False

try:
    from plyer import filechooser
    PLYER_AVAILABLE = True
except ImportError:
    PLYER_AVAILABLE = False


# ──────────────────── Config ────────────────────
CONFIG_FILENAME = "audiobook_config.json"

DEFAULT_CONFIG = {
    "voice": "en-US-AvaNeural",
    "rate": "+0%",
    "volume": "+0%",
    "pitch": "+0Hz",
    "concurrency": 15,
    "chunk_size": 500,
    "output_format": "both",
    "output_dir": "",
    "last_file": "",
    "para_pause": 0.5,
    "fx_highpass": False, "fx_highpass_f": 80,
    "fx_clarity": False, "fx_clarity_g": 5.0,
    "fx_compressor": False,
    "fx_loudnorm": True,
    "fx_reverb": False, "fx_reverb_room": 50,
    "fx_chorus": False,
    "fx_radio": False,
    "fx_vibrato": False, "fx_vibrato_freq": 5.0, "fx_vibrato_depth": 0.5,
    "fx_bass": False, "fx_bass_gain": 5.0,
    "split_chapters": False,
    "chapter_regex": r"^Chapter\s+\d+",
}

def _config_path():
    if kivy_platform == "android":
        try:
            from android.storage import app_storage_path
            return os.path.join(app_storage_path(), CONFIG_FILENAME)
        except Exception:
            pass
    return os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), CONFIG_FILENAME)

def load_config():
    cp = _config_path()
    if os.path.exists(cp):
        try:
            with open(cp, "r", encoding="utf-8") as f:
                data = json.load(f)
                for k, v in DEFAULT_CONFIG.items():
                    data.setdefault(k, v)
                return data
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()

def save_config(cfg):
    try:
        with open(_config_path(), "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4)
    except Exception as e:
        print(f"Config save error: {e}")


# ──────────────────── Text Processor ────────────────────
class TextProcessor:
    @staticmethod
    def _clean_stream(text_stream):
        for chunk in text_stream:
            chunk = re.sub(r"https?://\S+|www\.\S+|[\w\.-]+@[\w\.-]+", "", chunk)
            chunk = re.sub(r"-\s*\n\s*", "", chunk)
            chunk = re.sub(r"\s+", " ", chunk)
            if chunk.strip():
                yield chunk

    @staticmethod
    def _read_raw_file(filepath):
        ext = os.path.splitext(filepath)[1].lower()
        if ext == ".txt":
            with open(filepath, "r", encoding="utf-8") as f:
                while True:
                    block = f.read(65536)
                    if not block: break
                    yield block
        elif ext == ".pdf":
            if not PDF_SUPPORT: raise ImportError("pypdf missing")
            reader = PdfReader(filepath)
            for page in reader.pages:
                t = page.extract_text()
                if t: yield t + "\n"
        elif ext == ".docx":
            if not DOCX_SUPPORT: raise ImportError("python-docx missing")
            doc = Document(filepath)
            for para in doc.paragraphs: yield para.text + "\n"
        elif ext in (".md", ".html", ".htm"):
            if not HTML_MD_SUPPORT: raise ImportError("beautifulsoup4 missing")
            with open(filepath, "r", encoding="utf-8") as f: content = f.read()
            if ext != ".md":
                soup = BeautifulSoup(content, "html.parser")
                for s in soup(["script", "style"]): s.decompose()
                yield soup.get_text(separator="\n")
            else: yield content
        elif ext == ".epub":
            if not EPUB_SUPPORT: raise ImportError("EbookLib missing")
            if not HTML_MD_SUPPORT: raise ImportError("beautifulsoup4 missing")
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
    def _read_raw_text(raw_text):
        block_size = 5000
        for i in range(0, len(raw_text), block_size):
            yield raw_text[i : i + block_size]

    @staticmethod
    def chunk_generator(source, max_chars=500, is_raw_text=False, split_chapters=False, chapter_regex=r"^Chapter\s+\d+"):
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
                            for out_chunk in TextProcessor._drain_buffer(buf, max_chars, sentence_endings):
                                yield chapter_id, out_chunk
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
        if buf.strip():
            yield buf.strip()


# ──────────────────── Audio Engine ────────────────────
@dataclass(order=True)
class ChunkResult:
    index: int
    filepath: str = field(compare=False)
    chapter_id: int = field(compare=False)

class AudioEngine(threading.Thread):
    def __init__(self, source, output_path, config, is_raw_text=False):
        super().__init__(daemon=True)
        self.source = source
        self.output_path = output_path
        self.is_raw_text = is_raw_text
        self.voice = config.get("voice")
        self.rate = config.get("rate")
        self.volume = config.get("volume")
        self.pitch = str(config.get("pitch", "+0Hz"))
        self.concurrency = config.get("concurrency", 10)
        self.chunk_size = config.get("chunk_size", 500)
        self.out_format = config.get("output_format", "both")
        self.effects = config.get("effects", {})
        self.para_pause = config.get("para_pause", 0.0)
        self.split_chapters = config.get("split_chapters", False)
        self.chapter_regex = config.get("chapter_regex", r"^Chapter\s+\d+")

        self.is_cancelled = False
        self.heap: list[ChunkResult] = []
        self.total_tasks = 0
        self.completed_tasks = 0
        self.temp_dir = tempfile.mkdtemp()

        self.on_progress = None
        self.on_log = None
        self.on_finished = None

    def _emit_progress(self, pct, msg):
        if self.on_progress: Clock.schedule_once(lambda _dt: self.on_progress(pct, msg), 0)

    def _emit_log(self, msg):
        if self.on_log: Clock.schedule_once(lambda _dt: self.on_log(msg), 0)

    def _emit_finished(self, ok, msg):
        if self.on_finished: Clock.schedule_once(lambda _dt: self.on_finished(ok, msg), 0)

    async def _producer(self, queue):
        try:
            idx = 0
            gen = TextProcessor.chunk_generator(self.source, self.chunk_size, self.is_raw_text, self.split_chapters, self.chapter_regex)
            for chap_id, chunk in gen:
                if self.is_cancelled: break
                if not chunk: continue
                await queue.put((idx, chap_id, chunk))
                self.total_tasks = idx + 1
                if idx % 20 == 0: self._emit_log(f"Reading chunk {idx + 1}…")
                idx += 1
            self._emit_log(f"Text processing complete. Total chunks: {idx}")
        except Exception as e:
            self._emit_log(f"Producer Error: {e}")
        finally:
            for _ in range(self.concurrency): await queue.put(None)

    async def _consumer(self, queue, wid):
        while True:
            if self.is_cancelled: break
            try:
                item = await asyncio.wait_for(queue.get(), timeout=1.0)
            except asyncio.TimeoutError: continue
            if item is None:
                queue.task_done(); break
            
            idx, chap_id, text = item
            tmp = os.path.join(self.temp_dir, f"chunk_{chap_id}_{idx}.mp3")
            try:
                comm = edge_tts.Communicate(text, self.voice, rate=self.rate, volume=self.volume, pitch=self.pitch)
                await asyncio.wait_for(comm.save(tmp), timeout=60.0)
                heapq.heappush(self.heap, ChunkResult(index=idx, filepath=tmp, chapter_id=chap_id))
                self.completed_tasks += 1
                pct = int(10 + (self.completed_tasks / max(1, self.total_tasks)) * 70)
                self._emit_progress(pct, f"Generated {self.completed_tasks}/{self.total_tasks}")
            except asyncio.TimeoutError:
                self._emit_log(f"[WARNING] Chunk {idx} timed out.")
            except Exception as e:
                self._emit_log(f"[ERROR] Chunk {idx}: {str(e)[:80]}")
            finally:
                queue.task_done()

    def _build_audio_filter(self):
        filters = []
        fx = self.effects

        if fx.get("highpass"):
            freq = fx.get("highpass_f", 80)
            filters.append(f"highpass=f={freq}")
        if fx.get("clarity"):
            gain = fx.get("clarity_g", 5.0)
            filters.append(f"treble=g={gain}:f=3000:w=0.5")
        if fx.get("bass"):
            gain = fx.get("bass_gain", 5.0)
            filters.append(f"bass=g={gain}:f=100:w=0.5")
        if fx.get("compressor"):
            filters.append("acompressor=threshold=-20dB:ratio=4:attack=5:release=50:makeup=1")
        if fx.get("loudnorm"):
            filters.append("loudnorm=I=-16:TP=-1.5:LRA=11")
        if fx.get("chorus"):
            filters.append("chorus=0.5:0.9:50|60:0.4|0.8:0.25|0.4:2|1.5")
        if fx.get("vibrato"):
            freq = fx.get("vibrato_freq", 5.0)
            depth = fx.get("vibrato_depth", 0.5)
            filters.append(f"vibrato=f={freq:.1f}:d={depth:.2f}")
        if fx.get("reverb"):
            room = fx.get("reverb_room", 50) / 100.0
            delay, decay = int(20 + room * 130), 0.2 + room * 0.5
            filters.append(f"aecho=0.8:0.88:{delay}:{decay:.2f}")
        if fx.get("radio"):
            filters.append("equalizer=f=1000:t=q:w=1:g=15,equalizer=f=3000:t=q:w=1:g=15,highpass=f=300,lowpass=f=3400")

        return ",".join(filters)

    async def _run_async(self):
        self._emit_progress(0, "Starting pipeline…")
        queue = asyncio.Queue(maxsize=self.concurrency * 2)
        consumers = [asyncio.create_task(self._consumer(queue, i)) for i in range(self.concurrency)]
        producer = asyncio.create_task(self._producer(queue))
        await producer; await asyncio.gather(*consumers)

        if self.is_cancelled: raise RuntimeError("Cancelled by user.")
        self._emit_progress(85, "Assembling audio…")
        
        has_ffmpeg = self._has_ffmpeg()
        af = self._build_audio_filter()
        
        silence_path = None
        if self.para_pause > 0 and has_ffmpeg:
            silence_path = os.path.join(self.temp_dir, "silence.mp3")
            subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", str(self.para_pause), "-q:a", "9", silence_path], capture_output=True)

        chapters = {}
        while self.heap:
            item = heapq.heappop(self.heap)
            chapters.setdefault(item.chapter_id, []).append(item)

        output_files = []
        is_multi_chapter = len(chapters) > 1
        
        if self.split_chapters and is_multi_chapter:
            base_dir = self.output_path
            os.makedirs(base_dir, exist_ok=True)
        else:
            base_dir = os.path.dirname(self.output_path)

        for chap_id, items in chapters.items():
            chap_name = f"Chapter_{chap_id}" if (self.split_chapters and is_multi_chapter) else os.path.basename(self.output_path)
            out_path = os.path.join(base_dir, chap_name)
            raw_concat = os.path.join(self.temp_dir, f"raw_{chap_id}.mp3")
            
            if has_ffmpeg:
                list_file = os.path.join(self.temp_dir, f"list_{chap_id}.txt")
                with open(list_file, "w", encoding="utf-8") as f:
                    for i, item in enumerate(items):
                        p = item.filepath.replace("\\", "/").replace("'", "'\\''")
                        f.write(f"file '{p}'\n")
                        if silence_path and i < len(items) - 1:
                            sp = silence_path.replace("\\", "/").replace("'", "'\\''")
                            f.write(f"file '{sp}'\n")
                subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file, "-c", "copy", raw_concat], capture_output=True)
            else:
                self._raw_concat_mp3(items, raw_concat)

            if not os.path.exists(raw_concat): continue

            mp3_file = f"{out_path}.mp3"
            wav_file = f"{out_path}.wav"
            
            if has_ffmpeg and af:
                self._emit_progress(90, f"Applying FX to {chap_name}…")
                if self.out_format in ("mp3", "both"):
                    subprocess.run(["ffmpeg", "-y", "-i", raw_concat, "-af", af, "-c:a", "libmp3lame", "-q:a", "2", mp3_file], capture_output=True)
                if self.out_format in ("wav", "both"):
                    src = mp3_file if os.path.exists(mp3_file) else raw_concat
                    subprocess.run(["ffmpeg", "-y", "-i", src, "-af", af, "-acodec", "pcm_s16le", "-ar", "44100", wav_file], capture_output=True)
            else:
                if self.out_format in ("mp3", "both"):
                    try: shutil.move(raw_concat, mp3_file)
                    except: self._raw_concat_mp3(items, mp3_file)
                if self.out_format in ("wav", "both") and has_ffmpeg:
                    src = mp3_file if os.path.exists(mp3_file) else raw_concat
                    subprocess.run(["ffmpeg", "-y", "-i", src, "-acodec", "pcm_s16le", "-ar", "44100", wav_file], capture_output=True)

            if os.path.exists(mp3_file): output_files.append(mp3_file)
            if os.path.exists(wav_file): output_files.append(wav_file)

        return output_files

    @staticmethod
    def _has_ffmpeg():
        try:
            r = subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
            return r.returncode == 0
        except: return False

    @staticmethod
    def _raw_concat_mp3(items, out_path):
        try:
            with open(out_path, "wb") as out:
                for item in items:
                    if os.path.exists(item.filepath):
                        with open(item.filepath, "rb") as inp: out.write(inp.read())
        except Exception as e: raise RuntimeError(f"Raw concat failed: {e}")

    def run(self):
        loop = None
        try:
            self._emit_progress(5, "Initializing…")
            loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
            files = loop.run_until_complete(self._run_async())
            msg = "Success!\nFiles saved:\n" + "\n".join(files)
            self._emit_finished(True, msg)
        except Exception as e:
            self._emit_finished(False, str(e))
        finally:
            try: shutil.rmtree(self.temp_dir, ignore_errors=True)
            except: pass
            if loop and not loop.is_closed(): loop.close()

    def cancel(self): self.is_cancelled = True


# ──────────────────── Voice Preview ────────────────────
class VoicePreviewEngine(threading.Thread):
    def __init__(self, voice, rate, volume, pitch, on_finished):
        super().__init__(daemon=True)
        self.voice = voice; self.rate = rate; self.volume = volume; self.pitch = pitch
        self.on_finished = on_finished

    def run(self):
        try:
            loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
            text = "Hello! This is a preview of the selected voice settings."
            tmp = tempfile.mktemp(suffix=".mp3")
            comm = edge_tts.Communicate(text, self.voice, rate=self.rate, volume=self.volume, pitch=self.pitch)
            loop.run_until_complete(comm.save(tmp))
            loop.close()
            if self.on_finished: Clock.schedule_once(lambda _dt: self.on_finished(tmp), 0)
        except Exception as e:
            print(f"Preview error: {e}")


# ──────────────────── KV UI Definition ────────────────────
KV = """
#:import dp kivy.metrics.dp
#:import sp kivy.metrics.sp

<SectionLabel@Label>:
    bold: True
    font_size: sp(14)
    size_hint_y: None
    height: dp(24)
    halign: 'left'
    valign: 'middle'
    text_size: self.width, None
    color: 0.25, 0.65, 1, 1

<RowLabel@Label>:
    font_size: sp(12)
    size_hint_x: None
    width: dp(64)
    valign: 'center'

<AudiobookStudio>:
    orientation: 'vertical'
    padding: dp(4)
    spacing: dp(2)

    TabbedPanel:
        id: main_tabs
        size_hint_y: 1
        tab_pos: 'top_left'
        tab_height: dp(40)
        do_default_tab: False

        # ── TAB 1: Source & Output ──
        TabbedPanelItem:
            text: 'I/O'
            ScrollView:
                bar_width: dp(4)
                BoxLayout:
                    orientation: 'vertical'
                    size_hint_y: None
                    height: self.minimum_height
                    spacing: dp(6)
                    padding: dp(8)

                    SectionLabel:
                        text: '1. Input Source'
                    TabbedPanel:
                        id: input_tabs
                        size_hint_y: None
                        height: dp(160)
                        tab_pos: 'top_left'
                        tab_height: dp(30)
                        do_default_tab: False
                        TabbedPanelItem:
                            text: 'File'
                            BoxLayout:
                                spacing: dp(4)
                                padding: dp(4)
                                TextInput:
                                    id: file_edit
                                    hint_text: 'Select PDF, TXT, EPUB...'
                                    multiline: False
                                Button:
                                    text: 'Browse'
                                    size_hint_x: None
                                    width: dp(70)
                                    on_press: root.browse_file()
                        TabbedPanelItem:
                            text: 'Text'
                            TextInput:
                                id: raw_text_edit
                                hint_text: 'Paste text here...'
                                multiline: True

                    SectionLabel:
                        text: '2. Output & Chapters'
                    BoxLayout:
                        size_hint_y: None
                        height: dp(36)
                        spacing: dp(4)
                        RowLabel:
                            text: 'Name:'
                        TextInput:
                            id: out_name_edit
                            hint_text: 'Auto-filled'
                            multiline: False

                    BoxLayout:
                        size_hint_y: None
                        height: dp(36)
                        spacing: dp(4)
                        RowLabel:
                            text: 'Folder:'
                        TextInput:
                            id: out_dir_edit
                            hint_text: 'Auto: ./output'
                            multiline: False
                        Button:
                            text: 'Pick'
                            size_hint_x: None
                            width: dp(54)
                            on_press: root.browse_dir()

                    BoxLayout:
                        size_hint_y: None
                        height: dp(30)
                        spacing: dp(8)
                        RowLabel:
                            text: 'Format:'
                        CheckBox:
                            id: chk_mp3
                            active: True
                        Label:
                            text: 'MP3'
                            size_hint_x: None
                            width: dp(34)
                            font_size: sp(11)
                        CheckBox:
                            id: chk_wav
                            active: True
                        Label:
                            text: 'WAV'
                            font_size: sp(11)

                    BoxLayout:
                        size_hint_y: None
                        height: dp(30)
                        spacing: dp(4)
                        CheckBox:
                            id: split_chapters
                            size_hint_x: None
                            width: dp(24)
                        RowLabel:
                            text: 'Split Ch:'
                        TextInput:
                            id: chapter_regex
                            hint_text: 'Regex (e.g. ^Chapter \\d+)'
                            multiline: False

        # ── TAB 2: Voice & Pacing ──
        TabbedPanelItem:
            text: 'Voice'
            ScrollView:
                bar_width: dp(4)
                BoxLayout:
                    orientation: 'vertical'
                    size_hint_y: None
                    height: self.minimum_height
                    spacing: dp(6)
                    padding: dp(8)

                    SectionLabel:
                        text: '1. Voice & Speech'
                    BoxLayout:
                        size_hint_y: None
                        height: dp(36)
                        spacing: dp(4)
                        RowLabel:
                            text: 'Voice:'
                        TextInput:
                            id: voice_input
                            hint_text: 'Voice name'
                            multiline: False
                        Button:
                            text: 'Search'
                            size_hint_x: None
                            width: dp(64)
                            on_press: root.open_voice_search()
                        Button:
                            text: 'Test'
                            size_hint_x: None
                            width: dp(58)
                            background_color: 0.2, 0.6, 0.2, 1
                            on_press: root.preview_voice()

                    BoxLayout:
                        size_hint_y: None
                        height: dp(30)
                        spacing: dp(4)
                        RowLabel:
                            text: 'Speed:'
                        Slider:
                            id: rate_slider
                            min: -50
                            max: 50
                            value: 0
                        Label:
                            id: rate_lbl
                            text: '0%'
                            size_hint_x: None
                            width: dp(36)
                            font_size: sp(11)

                    BoxLayout:
                        size_hint_y: None
                        height: dp(30)
                        spacing: dp(4)
                        RowLabel:
                            text: 'Volume:'
                        Slider:
                            id: vol_slider
                            min: -50
                            max: 50
                            value: 0
                        Label:
                            id: vol_lbl
                            text: '0%'
                            size_hint_x: None
                            width: dp(36)
                            font_size: sp(11)

                    BoxLayout:
                        size_hint_y: None
                        height: dp(30)
                        spacing: dp(4)
                        RowLabel:
                            text: 'Pitch:'
                        Slider:
                            id: pitch_slider
                            min: -50
                            max: 50
                            value: 0
                        Label:
                            id: pitch_lbl
                            text: '0Hz'
                            size_hint_x: None
                            width: dp(36)
                            font_size: sp(11)

                    SectionLabel:
                        text: '2. Pacing & Performance'
                    BoxLayout:
                        size_hint_y: None
                        height: dp(30)
                        spacing: dp(4)
                        RowLabel:
                            text: 'Pause:'
                        Slider:
                            id: pause_slider
                            min: 0
                            max: 3
                            value: 0.5
                            step: 0.1
                        Label:
                            id: pause_lbl
                            text: '0.5s'
                            size_hint_x: None
                            width: dp(36)
                            font_size: sp(11)

                    BoxLayout:
                        size_hint_y: None
                        height: dp(30)
                        spacing: dp(4)
                        RowLabel:
                            text: 'Workers:'
                        Slider:
                            id: workers_slider
                            min: 1
                            max: 50
                            value: 15
                            step: 1
                        Label:
                            id: workers_lbl
                            text: '15'
                            size_hint_x: None
                            width: dp(30)
                            font_size: sp(11)

                    BoxLayout:
                        size_hint_y: None
                        height: dp(30)
                        spacing: dp(4)
                        RowLabel:
                            text: 'Chunk:'
                        Slider:
                            id: chunk_slider
                            min: 100
                            max: 2000
                            value: 500
                            step: 50
                        Label:
                            id: chunk_lbl
                            text: '500'
                            size_hint_x: None
                            width: dp(36)
                            font_size: sp(11)

        # ── TAB 3: Audio Effects ──
        TabbedPanelItem:
            text: 'Effects'
            ScrollView:
                bar_width: dp(4)
                BoxLayout:
                    orientation: 'vertical'
                    size_hint_y: None
                    height: self.minimum_height
                    spacing: dp(6)
                    padding: dp(8)

                    SectionLabel:
                        text: '1. Clean & Dynamics'
                    BoxLayout:
                        size_hint_y: None
                        height: dp(30)
                        spacing: dp(4)
                        CheckBox:
                            id: fx_highpass
                            size_hint_x: None
                            width: dp(24)
                        RowLabel:
                            text: 'HPF:'
                        Slider:
                            id: highpass_f_slider
                            min: 50
                            max: 200
                            value: 80
                        Label:
                            id: highpass_f_lbl
                            text: '80Hz'
                            size_hint_x: None
                            width: dp(44)
                            font_size: sp(11)

                    BoxLayout:
                        size_hint_y: None
                        height: dp(30)
                        spacing: dp(4)
                        CheckBox:
                            id: fx_clarity
                            size_hint_x: None
                            width: dp(24)
                        RowLabel:
                            text: 'Clarity:'
                        Slider:
                            id: clarity_g_slider
                            min: 1.0
                            max: 15.0
                            value: 5.0
                        Label:
                            id: clarity_g_lbl
                            text: '5 dB'
                            size_hint_x: None
                            width: dp(44)
                            font_size: sp(11)

                    BoxLayout:
                        size_hint_y: None
                        height: dp(30)
                        spacing: dp(4)
                        CheckBox:
                            id: fx_compressor
                            size_hint_x: None
                            width: dp(24)
                        RowLabel:
                            text: 'Compress:'
                        Label:
                            text: 'Smooths volume peaks'
                            font_size: sp(11)
                            color: 0.6, 0.6, 0.6, 1

                    BoxLayout:
                        size_hint_y: None
                        height: dp(30)
                        spacing: dp(4)
                        CheckBox:
                            id: fx_loudnorm
                            size_hint_x: None
                            width: dp(24)
                            active: True
                        RowLabel:
                            text: 'Loudnorm'
                        Label:
                            text: 'Audiobook Standard'
                            font_size: sp(11)
                            color: 0.6, 0.6, 0.6, 1

                    SectionLabel:
                        text: '2. Creative Effects'
                    BoxLayout:
                        size_hint_y: None
                        height: dp(30)
                        spacing: dp(4)
                        CheckBox:
                            id: fx_bass
                            size_hint_x: None
                            width: dp(24)
                        RowLabel:
                            text: 'Bass+:'
                        Slider:
                            id: bass_gain_slider
                            min: 1.0
                            max: 15.0
                            value: 5.0
                        Label:
                            id: bass_gain_lbl
                            text: '5 dB'
                            size_hint_x: None
                            width: dp(44)
                            font_size: sp(11)

                    BoxLayout:
                        size_hint_y: None
                        height: dp(30)
                        spacing: dp(4)
                        CheckBox:
                            id: fx_reverb
                            size_hint_x: None
                            width: dp(24)
                        RowLabel:
                            text: 'Reverb:'
                        Slider:
                            id: reverb_room_slider
                            min: 0
                            max: 100
                            value: 50
                        Label:
                            id: reverb_room_lbl
                            text: '50%'
                            size_hint_x: None
                            width: dp(36)
                            font_size: sp(11)

                    BoxLayout:
                        size_hint_y: None
                        height: dp(30)
                        spacing: dp(4)
                        CheckBox:
                            id: fx_chorus
                            size_hint_x: None
                            width: dp(24)
                        RowLabel:
                            text: 'Chorus:'
                        Label:
                            text: 'Vocal doubling effect'
                            font_size: sp(11)
                            color: 0.6, 0.6, 0.6, 1

                    BoxLayout:
                        size_hint_y: None
                        height: dp(30)
                        spacing: dp(4)
                        CheckBox:
                            id: fx_vibrato
                            size_hint_x: None
                            width: dp(24)
                        RowLabel:
                            text: 'Vibrato:'
                        Slider:
                            id: vibrato_freq_slider
                            min: 0.1
                            max: 10.0
                            value: 5.0
                        Label:
                            id: vibrato_freq_lbl
                            text: '5.0Hz'
                            size_hint_x: None
                            width: dp(44)
                            font_size: sp(11)

                    BoxLayout:
                        size_hint_y: None
                        height: dp(30)
                        spacing: dp(4)
                        Label:
                            text: 'Depth:'
                            size_hint_x: None
                            width: dp(88)
                        Slider:
                            id: vibrato_depth_slider
                            min: 0.1
                            max: 1.0
                            value: 0.5
                        Label:
                            id: vibrato_depth_lbl
                            text: '0.50'
                            size_hint_x: None
                            width: dp(44)
                            font_size: sp(11)

                    BoxLayout:
                        size_hint_y: None
                        height: dp(30)
                        spacing: dp(4)
                        CheckBox:
                            id: fx_radio
                            size_hint_x: None
                            width: dp(24)
                        RowLabel:
                            text: 'Radio/TEL:'
                        Label:
                            text: 'Phone call effect'
                            font_size: sp(11)
                            color: 0.6, 0.6, 0.6, 1

    # ── FIXED BOTTOM AREA ──
    BoxLayout:
        size_hint_y: None
        height: dp(185)
        orientation: 'vertical'
        spacing: dp(2)

        Button:
            id: btn_start
            text: '🚀  Start Production'
            size_hint_y: None
            height: dp(42)
            font_size: sp(14)
            background_color: 0.30, 0.69, 0.31, 1
            color: 1, 1, 1, 1
            on_press: root.on_start_button()

        ProgressBar:
            id: pbar
            max: 100
            value: 0
            size_hint_y: None
            height: dp(14)

        Label:
            id: status_lbl
            text: 'Ready'
            size_hint_y: None
            height: dp(18)
            font_size: sp(11)
            halign: 'left'
            valign: 'middle'
            text_size: self.width, None

        TextInput:
            id: log_console
            readonly: True
            multiline: True
            font_size: sp(10)
            background_color: 0.12, 0.12, 0.12, 1
            foreground_color: 0.8, 0.8, 0.8, 1
            size_hint_y: None
            height: dp(55)

        BoxLayout:
            size_hint_y: None
            height: dp(36)
            spacing: dp(4)
            Button:
                id: btn_play
                text: '▶ Play Output'
                disabled: True
                on_press: root.play_audio()
            Button:
                id: btn_stop
                text: '■ Stop'
                disabled: True
                on_press: root.stop_audio()
            Label:
                id: player_lbl
                text: 'No file loaded'
                font_size: sp(10)
                halign: 'left'
                valign: 'middle'
                text_size: self.width, None
"""


# ──────────────────── Voice Search Popup ────────────────────
class VoiceSearchPopup(Popup):
    def __init__(self, on_select, **kw):
        super().__init__(**kw)
        self.on_select = on_select; self.all_voices = []; self.selected_voice = None
        self.title = "Search Voices"; self.size_hint = (0.92, 0.92)
        root = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(8))
        self.search_input = TextInput(hint_text="Filter…", multiline=False, size_hint_y=None, height=dp(36))
        self.search_input.bind(text=self._on_filter); root.add_widget(self.search_input)
        self.status_lbl = Label(text="Loading…", size_hint_y=None, height=dp(20), font_size=sp(11))
        root.add_widget(self.status_lbl)
        self.scroll = ScrollView()
        self.list_layout = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(2))
        self.list_layout.bind(minimum_height=self.list_layout.setter("height"))
        self.scroll.add_widget(self.list_layout); root.add_widget(self.scroll)
        btn_row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(6))
        btn_ok = Button(text="OK"); btn_cancel = Button(text="Cancel")
        btn_ok.bind(on_press=self._on_ok); btn_cancel.bind(on_press=self.dismiss)
        btn_row.add_widget(btn_ok); btn_row.add_widget(btn_cancel); root.add_widget(btn_row)
        self.content = root
        threading.Thread(target=self._load_voices, daemon=True).start()

    def _load_voices(self):
        try:
            loop = asyncio.new_event_loop(); voices = loop.run_until_complete(edge_tts.list_voices()); loop.close()
            self.all_voices = [(v["ShortName"], v["Gender"], v["Locale"]) for v in voices]
            Clock.schedule_once(lambda _dt: self._populate(""), 0)
        except Exception as e:
            Clock.schedule_once(lambda _dt: setattr(self.status_lbl, "text", f"Error: {e}"), 0)

    def _populate(self, ft):
        self.list_layout.clear_widgets(); ft = ft.lower(); count = 0
        for name, gender, locale in self.all_voices:
            if ft and ft not in name.lower() and ft not in locale.lower(): continue
            btn = ToggleButton(text=f"{name} ({gender}, {locale})", size_hint_y=None, height=dp(32), group="vs", font_size=sp(11))
            vn = name
            btn.bind(on_press=lambda i, n=vn: setattr(self, 'selected_voice', n))
            self.list_layout.add_widget(btn); count += 1
        self.status_lbl.text = f"{count} / {len(self.all_voices)}"

    def _on_filter(self, _i, v): self._populate(v)
    def _on_ok(self, _i):
        if self.selected_voice: self.on_select(self.selected_voice)
        self.dismiss()


# ──────────────────── Main Widget ────────────────────
class AudiobookStudio(BoxLayout):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.engine = None; self._running = False; self._sound = None
        Clock.schedule_once(self._apply_config, 0)
        Clock.schedule_once(self._bind_sliders, 0)

    def _default_output_dir(self):
        if kivy_platform == "android":
            try: from android.storage import app_storage_path; return os.path.join(app_storage_path(), "output")
            except: pass
        return os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "output")

    def _output_dir(self):
        return self.ids.out_dir_edit.text.strip() or self._default_output_dir()

    def _unique_name(self, d, b):
        s = re.sub(r'[\\/*?:"<>|]', "", b)[:50]; n = s; c = 1
        while os.path.exists(os.path.join(d, f"{n}.mp3")): n = f"{s}_{c}"; c += 1
        return n

    def _is_raw_text(self):
        try: return self.ids.input_tabs.current_tab.text == "Text"
        except: return False

    def _fmt_str(self):
        m, w = self.ids.chk_mp3.active, self.ids.chk_wav.active
        return "both" if m and w else ("mp3" if m else ("wav" if w else "both"))

    def _apply_config(self, _dt):
        c = load_config()
        self.ids.file_edit.text = c.get("last_file", "")
        self.ids.voice_input.text = c.get("voice", "en-US-AvaNeural")
        def p(s, d=0):
            try: return int(str(s).replace("%","").replace("+",""))
            except: return d
        self.ids.rate_slider.value = p(c.get("rate", "+0%"))
        self.ids.vol_slider.value = p(c.get("volume", "+0%"))
        self.ids.pitch_slider.value = p(c.get("pitch", "+0Hz"))
        self.ids.out_dir_edit.text = c.get("output_dir", "")
        fmt = c.get("output_format", "both")
        self.ids.chk_mp3.active = fmt in ("mp3", "both")
        self.ids.chk_wav.active = fmt in ("wav", "both")
        self.ids.pause_slider.value = c.get("para_pause", 0.5)
        self.ids.workers_slider.value = c.get("concurrency", 15)
        self.ids.chunk_slider.value = c.get("chunk_size", 500)
        
        self.ids.fx_highpass.active = c.get("fx_highpass", False)
        self.ids.highpass_f_slider.value = c.get("fx_highpass_f", 80)
        self.ids.fx_clarity.active = c.get("fx_clarity", False)
        self.ids.clarity_g_slider.value = c.get("fx_clarity_g", 5.0)
        self.ids.fx_compressor.active = c.get("fx_compressor", False)
        self.ids.fx_loudnorm.active = c.get("fx_loudnorm", True)
        
        self.ids.fx_bass.active = c.get("fx_bass", False)
        self.ids.bass_gain_slider.value = c.get("fx_bass_gain", 5.0)
        self.ids.fx_reverb.active = c.get("fx_reverb", False)
        self.ids.reverb_room_slider.value = c.get("fx_reverb_room", 50)
        self.ids.fx_chorus.active = c.get("fx_chorus", False)
        self.ids.fx_vibrato.active = c.get("fx_vibrato", False)
        self.ids.vibrato_freq_slider.value = c.get("fx_vibrato_freq", 5.0)
        self.ids.vibrato_depth_slider.value = c.get("fx_vibrato_depth", 0.5)
        self.ids.fx_radio.active = c.get("fx_radio", False)
        
        self.ids.split_chapters.active = c.get("split_chapters", False)
        self.ids.chapter_regex.text = c.get("chapter_regex", r"^Chapter\s+\d+")
        self._update_auto_name()

    def _bind_sliders(self, _dt):
        binds = [
            (self.ids.rate_slider, self.ids.rate_lbl, lambda v: f"{int(v)}%"),
            (self.ids.vol_slider, self.ids.vol_lbl, lambda v: f"{int(v)}%"),
            (self.ids.pitch_slider, self.ids.pitch_lbl, lambda v: f"{int(v)}Hz"),
            (self.ids.pause_slider, self.ids.pause_lbl, lambda v: f"{v:.1f}s"),
            (self.ids.workers_slider, self.ids.workers_lbl, lambda v: str(int(v))),
            (self.ids.chunk_slider, self.ids.chunk_lbl, lambda v: str(int(v))),
            (self.ids.highpass_f_slider, self.ids.highpass_f_lbl, lambda v: f"{int(v)}Hz"),
            (self.ids.clarity_g_slider, self.ids.clarity_g_lbl, lambda v: f"{v:.1f}dB"),
            (self.ids.bass_gain_slider, self.ids.bass_gain_lbl, lambda v: f"{v:.1f}dB"),
            (self.ids.reverb_room_slider, self.ids.reverb_room_lbl, lambda v: f"{int(v)}%"),
            (self.ids.vibrato_freq_slider, self.ids.vibrato_freq_lbl, lambda v: f"{v:.1f}Hz"),
            (self.ids.vibrato_depth_slider, self.ids.vibrato_depth_lbl, lambda v: f"D:{v:.2f}"),
        ]
        for slider, lbl, fmt in binds:
            slider.bind(value=lambda i, v, l=lbl, f=fmt: setattr(l, 'text', f(v)))
        self.ids.file_edit.bind(text=lambda *_: self._update_auto_name())
        self.ids.raw_text_edit.bind(text=lambda *_: self._update_auto_name())

    def _update_auto_name(self, *_):
        od = self._output_dir(); raw = self.ids.raw_text_edit.text.strip(); fp = self.ids.file_edit.text.strip()
        if self._is_raw_text() and raw:
            s = re.sub(r'[\\/*?:"<>|]', "", raw.split("\n")[0])[:40]
            self.ids.out_name_edit.text = self._unique_name(od, s) if s else "New_Text"
        elif fp: self.ids.out_name_edit.text = os.path.splitext(os.path.basename(fp))[0]
        else: self.ids.out_name_edit.text = "Audiobook"

    # ── Browsing ──
    def browse_file(self):
        if PLYER_AVAILABLE:
            try: filechooser.open_file(on_selection=lambda s: setattr(self.ids.file_edit, 'text', s[0] if s else '')); return
            except: pass
        self._kivy_chooser(False)

    def browse_dir(self):
        if PLYER_AVAILABLE:
            try: filechooser.choose_dir(on_selection=lambda s: setattr(self.ids.out_dir_edit, 'text', s[0] if s else '')); return
            except: pass
        self._kivy_chooser(True)

    def _kivy_chooser(self, is_dir):
        from kivy.uix.filechooser import FileChooserListView
        c = BoxLayout(orientation="vertical", spacing=dp(4), padding=dp(4))
        fc = FileChooserListView(path=os.path.expanduser("~"), dirselect=is_dir)
        c.add_widget(fc)
        br = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(4)); bs = Button(text="Select"); bc = Button(text="Cancel")
        br.add_widget(bs); br.add_widget(bc); c.add_widget(br)
        p = Popup(title="Select" + (" Folder" if is_dir else " File"), content=c, size_hint=(0.9, 0.9))
        def sel(i):
            if fc.selection:
                if is_dir: self.ids.out_dir_edit.text = fc.selection[0]
                else: self.ids.file_edit.text = fc.selection[0]
            p.dismiss()
        bs.bind(on_press=sel); bc.bind(on_press=p.dismiss); p.open()

    def open_voice_search(self):
        if not EDGE_TTS_AVAILABLE: self._popup("Error", "edge-tts missing"); return
        VoiceSearchPopup(on_select=lambda n: setattr(self.ids.voice_input, 'text', n)).open()

    # ── Voice Preview ──
    def preview_voice(self):
        if not EDGE_TTS_AVAILABLE: return
        self.ids.status_lbl.text = "Generating preview…"
        rv, vv, pv = int(self.ids.rate_slider.value), int(self.ids.vol_slider.value), int(self.ids.pitch_slider.value)
        VoicePreviewEngine(
            self.ids.voice_input.text.strip() or "en-US-AvaNeural",
            f"{rv:+d}%", f"{vv:+d}%", f"{pv:+d}Hz",
            self._on_preview_done
        ).start()

    def _on_preview_done(self, filepath):
        self.ids.status_lbl.text = "Playing preview…"
        self._play_file(filepath)

    # ── Audio Player ──
    def _play_file(self, filepath):
        self.stop_audio()
        if not os.path.exists(filepath): return
        self._sound = SoundLoader.load(filepath)
        if self._sound:
            self._sound.play()
            self.ids.btn_play.disabled = True; self.ids.btn_stop.disabled = False
            self.ids.player_lbl.text = os.path.basename(filepath)

    def play_audio(self):
        od = self._output_dir(); name = self.ids.out_name_edit.text.strip() or "Audiobook"
        if self.ids.split_chapters.active:
            mp3 = os.path.join(od, name, "Chapter_0.mp3")
        else:
            mp3 = os.path.join(od, f"{name}.mp3")
        if os.path.exists(mp3): self._play_file(mp3)
        else: self._popup("Not Found", "Generate the audiobook first!")

    def stop_audio(self):
        if self._sound:
            self._sound.stop(); self._sound = None
        self.ids.btn_play.disabled = False; self.ids.btn_stop.disabled = True
        self.ids.player_lbl.text = "Stopped"

    # ── Engine Control ──
    def on_start_button(self):
        if self._running and self.engine and self.engine.is_alive(): self.engine.cancel(); self._log("Cancelling…"); return
        self._start_production()

    def _start_production(self):
        if not EDGE_TTS_AVAILABLE: self._popup("Error", "pip install edge-tts"); return
        is_raw = self._is_raw_text(); source = None
        if is_raw:
            source = self.ids.raw_text_edit.text.strip()
            if not source: self._popup("Warning", "Enter text."); return
        else:
            source = self.ids.file_edit.text.strip()
            if not source or not os.path.exists(source): self._popup("Warning", "Select valid file."); return

        out_dir = self._output_dir()
        try: os.makedirs(out_dir, exist_ok=True)
        except Exception as e: self._popup("Error", f"Bad output dir:\n{e}"); return

        out_name = self.ids.out_name_edit.text.strip() or "Audiobook"
        full_out = os.path.join(out_dir, out_name)
        rv, vv, pv = int(self.ids.rate_slider.value), int(self.ids.vol_slider.value), int(self.ids.pitch_slider.value)

        job = {
            "voice": self.ids.voice_input.text.strip() or "en-US-AvaNeural",
            "rate": f"{rv:+d}%", "volume": f"{vv:+d}%", "pitch": f"{pv:+d}Hz",
            "concurrency": int(self.ids.workers_slider.value),
            "chunk_size": int(self.ids.chunk_slider.value),
            "output_format": self._fmt_str(),
            "para_pause": self.ids.pause_slider.value,
            "split_chapters": self.ids.split_chapters.active,
            "chapter_regex": self.ids.chapter_regex.text.strip() or r"^Chapter\s+\d+",
            "effects": {
                "highpass": self.ids.fx_highpass.active, "highpass_f": self.ids.highpass_f_slider.value,
                "clarity": self.ids.fx_clarity.active, "clarity_g": self.ids.clarity_g_slider.value,
                "compressor": self.ids.fx_compressor.active,
                "loudnorm": self.ids.fx_loudnorm.active,
                "bass": self.ids.fx_bass.active, "bass_gain": self.ids.bass_gain_slider.value,
                "reverb": self.ids.fx_reverb.active, "reverb_room": self.ids.reverb_room_slider.value,
                "chorus": self.ids.fx_chorus.active,
                "vibrato": self.ids.fx_vibrato.active, "vibrato_freq": self.ids.vibrato_freq_slider.value, "vibrato_depth": self.ids.vibrato_depth_slider.value,
                "radio": self.ids.fx_radio.active,
            }
        }

        save_config({**job, "output_dir": self.ids.out_dir_edit.text, "last_file": self.ids.file_edit.text})
        self.ids.log_console.text = ""; self._running = True
        self.ids.btn_start.text = "✖  Cancel"; self.ids.btn_start.background_color = (0.9, 0.2, 0.2, 1)

        self.engine = AudioEngine(source, full_out, job, is_raw_text=is_raw)
        self.engine.on_progress = self._on_progress
        self.engine.on_log = self._log
        self.engine.on_finished = self._on_finished
        self.engine.start()

    def _on_progress(self, pct, msg): self.ids.pbar.value = pct; self.ids.status_lbl.text = msg
    def _log(self, msg):
        self.ids.log_console.text += re.sub(r"\[/?[a-zA-Z=]+\]", "", str(msg)) + "\n"
        self.ids.log_console.cursor = (0, len(self.ids.log_console.text))

    def _on_finished(self, success, msg):
        self._running = False; self.ids.btn_start.text = "🚀  Start Production"; self.ids.btn_start.background_color = (0.30, 0.69, 0.31, 1)
        if success:
            self.ids.pbar.value = 100; self._popup("Done!", msg); self._update_auto_name()
            self.ids.btn_play.disabled = False
        else: self._popup("Error", msg)

    def _popup(self, title, message):
        c = BoxLayout(orientation="vertical", spacing=dp(10), padding=dp(12))
        c.add_widget(Label(text=message, halign="left", valign="top", text_size=(Window.width*0.72, None)))
        b = Button(text="OK", size_hint_y=None, height=dp(38)); c.add_widget(b)
        p = Popup(title=title, content=c, size_hint=(0.82, 0.52)); b.bind(on_press=p.dismiss); p.open()


# ──────────────────── App ────────────────────
class AudiobookApp(App):
    def build(self):
        Builder.load_string(KV)
        self.title = "Audiobook Studio"
        return AudiobookStudio()

    def on_start(self):
        if kivy_platform == "android":
            try:
                from android.permissions import request_permissions, Permission
                request_permissions([Permission.READ_EXTERNAL_STORAGE, Permission.WRITE_EXTERNAL_STORAGE])
            except: pass

    def on_pause(self): return True

if __name__ == "__main__":
    AudiobookApp().run()