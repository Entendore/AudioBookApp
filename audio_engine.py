#!/usr/bin/env python3
"""
Audio generation engine: TTS synthesis, FFmpeg effects, and assembly.
"""

import os
import asyncio
import threading
import subprocess
import tempfile
import shutil
import heapq
from dataclasses import dataclass, field
from typing import List, Optional, Callable

from kivy.clock import Clock
from dependencies import EDGE_TTS_AVAILABLE
from text_processor import TextProcessor

# Import edge_tts at the module level so _consumer can access it
try:
    import edge_tts
except ImportError:
    edge_tts = None


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
        self.heap: List[ChunkResult] = []
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
            try: item = await asyncio.wait_for(queue.get(), timeout=1.0)
            except asyncio.TimeoutError: continue
            if item is None: queue.task_done(); break
            
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
        if fx.get("highpass"): filters.append(f"highpass=f={fx.get('highpass_f', 80)}")
        if fx.get("clarity"): filters.append(f"treble=g={fx.get('clarity_g', 5.0)}:f=3000:w=0.5")
        if fx.get("bass"): filters.append(f"bass=g={fx.get('bass_gain', 5.0)}:f=100:w=0.5")
        if fx.get("compressor"): filters.append("acompressor=threshold=-20dB:ratio=4:attack=5:release=50:makeup=1")
        if fx.get("loudnorm"): filters.append("loudnorm=I=-16:TP=-1.5:LRA=11")
        if fx.get("chorus"): filters.append("chorus=0.5:0.9:50|60:0.4|0.8:0.25|0.4:2|1.5")
        if fx.get("vibrato"):
            filters.append(f"vibrato=f={fx.get('vibrato_freq', 5.0):.1f}:d={fx.get('vibrato_depth', 0.5):.2f}")
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
        
        has_ffmpeg = self.has_ffmpeg()
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
            base_dir = self.output_path; os.makedirs(base_dir, exist_ok=True)
        else:
            base_dir = os.path.dirname(self.output_path); os.makedirs(base_dir, exist_ok=True)

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
    def has_ffmpeg():
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
            if not EDGE_TTS_AVAILABLE or edge_tts is None: 
                raise RuntimeError("edge-tts is not installed. Please install it via: pip install edge-tts")
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