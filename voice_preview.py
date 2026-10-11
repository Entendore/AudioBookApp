#!/usr/bin/env python3
"""
Voice preview engine – generates a short TTS sample in a background thread.
"""

import asyncio
import tempfile
import threading
from typing import Optional, Callable

from kivy.clock import Clock


class VoicePreviewEngine(threading.Thread):
    PREVIEW_TEXT = "Hello! This is a preview of the selected voice settings. Adjust speed, pitch, and volume, then test again."

    def __init__(self, voice: str, rate: str, volume: str, pitch: str, on_finished: Optional[Callable[[str], None]] = None):
        super().__init__(daemon=True)
        self.voice = voice; self.rate = rate; self.volume = volume; self.pitch = pitch
        self.on_finished = on_finished

    def run(self):
        try:
            import edge_tts
            loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
            tmp = tempfile.mktemp(suffix=".mp3")
            comm = edge_tts.Communicate(self.PREVIEW_TEXT, self.voice, rate=self.rate, volume=self.volume, pitch=self.pitch)
            loop.run_until_complete(comm.save(tmp))
            loop.close()
            if self.on_finished: Clock.schedule_once(lambda _dt: self.on_finished(tmp), 0)
        except Exception as exc:
            print(f"[VoicePreview] Error: {exc}")