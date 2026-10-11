#!/usr/bin/env python3
"""
Kivy KV language string for the AudiobookStudio root widget.
Embeds voice search and file choosers directly to avoid Popups.
"""

KV = """
#:import dp kivy.metrics.dp
#:import sp kivy.metrics.sp
#:import os os

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
                        height: dp(200)
                        tab_pos: 'top_left'
                        tab_height: dp(30)
                        do_default_tab: False
                        TabbedPanelItem:
                            text: 'File'
                            BoxLayout:
                                orientation: 'vertical'
                                FileChooserListView:
                                    id: file_chooser
                                    dirselect: False
                                    filter: ['*.txt', '*.pdf', '*.docx', '*.md', '*.html', '*.htm', '*.epub']
                                    on_selection: root.on_file_selection(self.selection)
                                BoxLayout:
                                    size_hint_y: None
                                    height: dp(36)
                                    spacing: dp(4)
                                    TextInput:
                                        id: file_edit
                                        hint_text: 'Selected file path'
                                        readonly: True
                                    Button:
                                        text: 'Native'
                                        size_hint_x: None
                                        width: dp(70)
                                        on_press: root.browse_file_native()
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
                            on_press: root.browse_dir_native()

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
                        ToggleButton:
                            id: toggle_voice_search
                            text: 'Search'
                            size_hint_x: None
                            width: dp(64)
                        Button:
                            text: 'Test'
                            size_hint_x: None
                            width: dp(58)
                            background_color: 0.2, 0.6, 0.2, 1
                            on_press: root.preview_voice()

                    # Inline Voice Search Widget (Expands/Collapses)
                    VoiceSearchWidget:
                        id: voice_search_widget
                        size_hint_y: None
                        height: dp(220) if root.ids.toggle_voice_search.state == 'down' else 0
                        opacity: 1 if root.ids.toggle_voice_search.state == 'down' else 0

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
            color: 1, 1, 1, 1

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