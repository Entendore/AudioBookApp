#!/usr/bin/env python3
"""
Advanced Audiobook Studio – Kivy Edition
Entry point.  Run with:  python main.py

Required: pip install kivy edge-tts
Optional: pip install pypdf python-docx beautifulsoup4 EbookLib plyer
FFmpeg:   Required for WAV output, Audio Effects, Pauses, and Chapter Splitting.
"""

import os
import re

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.clock import Clock
from kivy.core.audio import SoundLoader
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.utils import platform as kivy_platform

# ── Local modules ──
from config import load_config, save_config, default_output_dir
from dependencies import EDGE_TTS_AVAILABLE, PLYER_AVAILABLE
from audio_engine import AudioEngine
from voice_preview import VoicePreviewEngine
from kv_layout import KV
from widgets import VoiceSearchWidget


class AudiobookStudio(BoxLayout):
    """Root widget – orchestrates UI, engine, and audio playback."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.engine = None
        self._running = False
        self._sound = None

        Clock.schedule_once(self._apply_config, 0)
        Clock.schedule_once(self._bind_sliders, 0)
        Clock.schedule_once(self._setup_widgets, 0)

    # ── Helpers ─────────────────────────────────────────────────

    def _output_dir(self) -> str:
        return self.ids.out_dir_edit.text.strip() or default_output_dir()

    def _is_raw_text(self) -> bool:
        try:
            return self.ids.input_tabs.current_tab.text == "Text"
        except Exception:
            return False

    def _fmt_str(self) -> str:
        m, w = self.ids.chk_mp3.active, self.ids.chk_wav.active
        if m and w: return "both"
        return "mp3" if m else ("wav" if w else "both")

    @staticmethod
    def _unique_name(directory: str, base: str) -> str:
        safe = re.sub(r'[\\/*?:"<>|]', "", base)[:50]
        name = safe
        counter = 1
        while os.path.exists(os.path.join(directory, f"{name}.mp3")):
            name = f"{safe}_{counter}"
            counter += 1
        return name

    def _update_auto_name(self, *_):
        od = self._output_dir()
        raw = self.ids.raw_text_edit.text.strip()
        fp = self.ids.file_edit.text.strip()
        if self._is_raw_text() and raw:
            first_line = re.sub(r'[\\/*?:"<>|]', "", raw.split("\n")[0])[:40]
            self.ids.out_name_edit.text = self._unique_name(od, first_line) if first_line else "New_Text"
        elif fp:
            self.ids.out_name_edit.text = os.path.splitext(os.path.basename(fp))[0]
        else:
            self.ids.out_name_edit.text = "Audiobook"

    # ── Setup & Config ──────────────────────────────────────────

    def _setup_widgets(self, _dt):
        """Wire up custom inline widgets."""
        # Connect the VoiceSearchWidget callback
        self.ids.voice_search_widget.on_select = self._on_voice_selected
        # Set default path for file chooser
        self.ids.file_chooser.path = os.path.expanduser("~")

    def _on_voice_selected(self, voice_name: str):
        """Callback from the inline VoiceSearchWidget."""
        self.ids.voice_input.text = voice_name

    def _apply_config(self, _dt):
        c = load_config()
        self.ids.file_edit.text = c.get("last_file", "")
        self.ids.voice_input.text = c.get("voice", "en-US-AvaNeural")

        def _pct(s, default=0):
            try: return int(str(s).replace("%", "").replace("+", ""))
            except (ValueError, TypeError): return default

        self.ids.rate_slider.value = _pct(c.get("rate", "+0%"))
        self.ids.vol_slider.value = _pct(c.get("volume", "+0%"))
        self.ids.pitch_slider.value = _pct(c.get("pitch", "+0Hz"))
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

    def _build_effects_dict(self) -> dict:
        return {
            "highpass": self.ids.fx_highpass.active, "highpass_f": int(self.ids.highpass_f_slider.value),
            "clarity": self.ids.fx_clarity.active, "clarity_g": self.ids.clarity_g_slider.value,
            "bass": self.ids.fx_bass.active, "bass_gain": self.ids.bass_gain_slider.value,
            "compressor": self.ids.fx_compressor.active,
            "loudnorm": self.ids.fx_loudnorm.active,
            "reverb": self.ids.fx_reverb.active, "reverb_room": int(self.ids.reverb_room_slider.value),
            "chorus": self.ids.fx_chorus.active,
            "vibrato": self.ids.fx_vibrato.active,
            "vibrato_freq": self.ids.vibrato_freq_slider.value,
            "vibrato_depth": self.ids.vibrato_depth_slider.value,
            "radio": self.ids.fx_radio.active,
        }

    def _build_config(self) -> dict:
        rv = int(self.ids.rate_slider.value)
        vv = int(self.ids.vol_slider.value)
        pv = int(self.ids.pitch_slider.value)
        return {
            "voice": self.ids.voice_input.text.strip() or "en-US-AvaNeural",
            "rate": f"{rv:+d}%", "volume": f"{vv:+d}%", "pitch": f"{pv:+d}Hz",
            "concurrency": int(self.ids.workers_slider.value),
            "chunk_size": int(self.ids.chunk_slider.value),
            "output_format": self._fmt_str(),
            "output_dir": self._output_dir(),
            "para_pause": self.ids.pause_slider.value,
            "effects": self._build_effects_dict(),
            "split_chapters": self.ids.split_chapters.active,
            "chapter_regex": self.ids.chapter_regex.text.strip() or r"^Chapter\s+\d+",
        }

    def _save_current_config(self):
        cfg = self._build_config()
        flat = {
            "voice": cfg["voice"], "rate": cfg["rate"], "volume": cfg["volume"], "pitch": cfg["pitch"],
            "concurrency": cfg["concurrency"], "chunk_size": cfg["chunk_size"], "output_format": cfg["output_format"],
            "output_dir": cfg["output_dir"], "last_file": self.ids.file_edit.text.strip(),
            "para_pause": cfg["para_pause"], "split_chapters": cfg["split_chapters"], "chapter_regex": cfg["chapter_regex"],
        }
        for k, v in cfg["effects"].items(): flat[f"fx_{k}"] = v
        save_config(flat)

    # ── Slider Binding ──────────────────────────────────────────

    def _bind_sliders(self, _dt):
        bindings = [
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
        for slider, lbl, fmt in bindings:
            slider.bind(value=lambda i, v, l=lbl, f=fmt: setattr(l, 'text', f(v)))
        self.ids.file_edit.bind(text=lambda *_: self._update_auto_name())
        self.ids.raw_text_edit.bind(text=lambda *_: self._update_auto_name())

    # ── Inline File Chooser / Native Browsing ───────────────────

    def on_file_selection(self, selection):
        """Callback for the embedded FileChooserListView."""
        if selection:
            self.ids.file_edit.text = selection[0]
            self._update_auto_name()

    def browse_file_native(self):
        """Attempt to use plyer native dialog, otherwise log error in status."""
        if PLYER_AVAILABLE:
            try:
                from plyer import filechooser
                filechooser.open_file(on_selection=lambda s: setattr(self.ids.file_edit, 'text', s[0] if s else ''))
                return
            except Exception:
                pass
        self.ids.status_lbl.text = "Native chooser unavailable. Use inline browser above."

    def browse_dir_native(self):
        if PLYER_AVAILABLE:
            try:
                from plyer import filechooser
                filechooser.choose_dir(on_selection=lambda s: setattr(self.ids.out_dir_edit, 'text', s[0] if s else ''))
                return
            except Exception:
                pass
        self.ids.status_lbl.text = "Native chooser unavailable. Type folder path manually."

    # ── Voice Preview ───────────────────────────────────────────

    def preview_voice(self):
        if not EDGE_TTS_AVAILABLE:
            self.ids.status_lbl.text = "Error: edge-tts not installed"
            return
        self.ids.status_lbl.text = "Generating preview…"
        rv, vv, pv = int(self.ids.rate_slider.value), int(self.ids.vol_slider.value), int(self.ids.pitch_slider.value)
        VoicePreviewEngine(
            self.ids.voice_input.text.strip() or "en-US-AvaNeural",
            f"{rv:+d}%", f"{vv:+d}%", f"{pv:+d}Hz", self._on_preview_done
        ).start()

    def _on_preview_done(self, filepath: str):
        self.ids.status_lbl.text = "Playing preview…"
        self._play_file(filepath)

    # ── Audio Playback ──────────────────────────────────────────

    def _play_file(self, filepath: str):
        self.stop_audio()
        if not os.path.exists(filepath): return
        self._sound = SoundLoader.load(filepath)
        if self._sound:
            self._sound.play()
            self.ids.btn_play.disabled = True
            self.ids.btn_stop.disabled = False
            self.ids.player_lbl.text = os.path.basename(filepath)

    def play_audio(self):
        od = self._output_dir()
        name = self.ids.out_name_edit.text.strip() or "Audiobook"
        if self.ids.split_chapters.active:
            mp3 = os.path.join(od, name, "Chapter_0.mp3")
        else:
            mp3 = os.path.join(od, f"{name}.mp3")
        if os.path.exists(mp3):
            self._play_file(mp3)
        else:
            self.ids.status_lbl.text = f"Output not found: {mp3}"

    def stop_audio(self):
        if self._sound:
            self._sound.stop()
            self._sound.unload()
            self._sound = None
        self.ids.btn_play.disabled = False
        self.ids.btn_stop.disabled = True
        self.ids.player_lbl.text = "Stopped"

    # ── Production Start / Cancel ───────────────────────────────

    def on_start_button(self):
        if self._running:
            if self.engine: self.engine.cancel()
            self.ids.btn_start.text = "Cancelling…"
            return

        # Validate Input (No popups, just status bar updates)
        if self._is_raw_text():
            source = self.ids.raw_text_edit.text.strip()
            if not source:
                self.ids.status_lbl.text = "Error: No text entered. Paste or type text in the Text tab."
                return
        else:
            source = self.ids.file_edit.text.strip()
            if not source or not os.path.exists(source):
                self.ids.status_lbl.text = "Error: No valid file selected. Browse for a file first."
                return

        od = self._output_dir()
        os.makedirs(od, exist_ok=True)
        name = self.ids.out_name_edit.text.strip() or "Audiobook"
        out_path = os.path.join(od, name)

        cfg = self._build_config()
        self.engine = AudioEngine(source, out_path, cfg, self._is_raw_text())
        self.engine.on_progress = self._on_progress
        self.engine.on_log = self._on_log
        self.engine.on_finished = self._on_finished

        self._running = True
        self.ids.btn_start.text = "⏹  Cancel"
        self.ids.btn_start.background_color = (0.8, 0.2, 0.2, 1)
        self.ids.pbar.value = 0
        self.ids.log_console.text = ""
        self.engine.start()

    # ── Engine Callbacks ────────────────────────────────────────

    def _on_progress(self, pct: int, msg: str):
        self.ids.pbar.value = pct
        self.ids.status_lbl.text = msg

    def _on_log(self, msg: str):
        self.ids.log_console.text += msg + "\n"
        log = self.ids.log_console
        log.cursor = (0, len(log._lines) + 1)

    def _on_finished(self, ok: bool, msg: str):
        self._running = False
        self.ids.btn_start.text = "🚀  Start Production"
        self.ids.btn_start.background_color = (0.30, 0.69, 0.31, 1)

        if ok:
            self.ids.pbar.value = 100
            self.ids.status_lbl.text = "✅ Done!"
            self.ids.btn_play.disabled = False
            self._save_current_config()
        else:
            self.ids.status_lbl.text = "❌ Error"
        
        # Log the final summary instead of a popup
        self._on_log(f"\n--- {'SUCCESS' if ok else 'ERROR'} ---\n{msg}\n-------------")


class AudiobookStudioApp(App):
    def build(self):
        Builder.load_string(KV)
        self.title = "Advanced Audiobook Studio"
        return AudiobookStudio()

    def on_stop(self):
        root = self.root
        if root and hasattr(root, "stop_audio"):
            root.stop_audio()


if __name__ == "__main__":
    AudiobookStudioApp().run()