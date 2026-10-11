#!/usr/bin/env python3
"""
Custom inline widgets for Advanced Audiobook Studio.
No popups - these components embed directly into the UI.
"""

import asyncio
import threading
from typing import List, Tuple

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.scrollview import ScrollView
from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.properties import ObjectProperty


class VoiceSearchWidget(BoxLayout):
    """
    Inline widget that lists all available edge-tts voices
    with a live text filter. Collapses into the UI smoothly.
    """
    # Define on_select as a Kivy ObjectProperty so it can be instantiated by KV without arguments
    on_select = ObjectProperty(None)

    def __init__(self, **kw):
        super().__init__(orientation="vertical", spacing=dp(4), **kw)
        self.all_voices: List[Tuple[str, str, str]] = []

        self.search_input = TextInput(
            hint_text="Filter by name or locale…",
            multiline=False,
            size_hint_y=None,
            height=dp(32),
        )
        self.search_input.bind(text=self._on_filter)
        self.add_widget(self.search_input)

        self.status_lbl = Label(
            text="Loading voices…",
            size_hint_y=None,
            height=dp(18),
            font_size=sp(10),
            halign="left",
            valign="middle",
        )
        self.status_lbl.bind(size=self.status_lbl.setter("text_size"))
        self.add_widget(self.status_lbl)

        self.scroll = ScrollView()
        self.list_layout = BoxLayout(
            orientation="vertical", size_hint_y=None, spacing=dp(1)
        )
        self.list_layout.bind(minimum_height=self.list_layout.setter("height"))
        self.scroll.add_widget(self.list_layout)
        self.add_widget(self.scroll)

        # Load voices in the background
        threading.Thread(target=self._load_voices, daemon=True).start()

    def _load_voices(self):
        try:
            import edge_tts
            loop = asyncio.new_event_loop()
            voices = loop.run_until_complete(edge_tts.list_voices())
            loop.close()
            self.all_voices = [
                (v["ShortName"], v["Gender"], v["Locale"]) for v in voices
            ]
            Clock.schedule_once(lambda _dt: self._populate(""), 0)
        except Exception as exc:
            msg = f"Error: {exc}"
            Clock.schedule_once(
                lambda _dt, m=msg: setattr(self.status_lbl, "text", m), 0
            )

    def _populate(self, filter_text: str):
        self.list_layout.clear_widgets()
        ft = filter_text.lower()
        count = 0
        for name, gender, locale in self.all_voices:
            if ft and ft not in name.lower() and ft not in locale.lower():
                continue
            btn = ToggleButton(
                text=f"{name} ({gender}, {locale})",
                size_hint_y=None,
                height=dp(28),
                group="inline_voice_select",
                font_size=sp(10),
            )
            btn.bind(on_press=lambda i, n=name: self._select_voice(n))
            self.list_layout.add_widget(btn)
            count += 1
        self.status_lbl.text = f"{count} / {len(self.all_voices)}"

    def _on_filter(self, _instance, value: str):
        self._populate(value)

    def _select_voice(self, name: str):
        if self.on_select:
            self.on_select(name)