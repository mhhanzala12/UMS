from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from PySide6.QtCore import Qt, QSize, QUrl, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QAction, QFont, QDesktopServices, QPixmap
from PySide6.QtWidgets import QGraphicsOpacityEffect
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QFrame, QInputDialog,
    QDialog, QDialogButtonBox,
    QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
    QScrollArea, QSizePolicy, QSpinBox, QStackedWidget, QTableWidget, QTabWidget, QListWidgetItem, QSlider,
    QTableWidgetItem, QVBoxLayout, QWidget, QHeaderView, QSplitter,
)

from .config import DEFAULT_OUTPUT, load_settings, save_settings
from .engine import is_http_url, tool_status
from .presets import PRESETS, _valid_preset_name, merged_presets
from .workers import AnalyzeWorker, FunctionWorker, MediaTaskWorker
from .music import CatalogSearchWorker, LyricsSearchWorker, SpotifyResolveWorker, load_music_playlists, save_music_playlists, scan_audio_library


APP_STYLE = """
QMainWindow, QWidget {
    background: #11161e;
    color: #e8edf4;
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 10pt;
}
QMenuBar {
    background: #171e28;
    color: #dce4ee;
    border-bottom: 1px solid #2a3544;
    padding: 5px 8px;
}
QMenuBar::item { padding: 6px 10px; border-radius: 6px; }
QMenuBar::item:selected { background: #263243; }
QMenu {
    background: #1a222d;
    color: #e8edf4;
    border: 1px solid #344153;
    padding: 5px;
}
QMenu::item { padding: 7px 26px 7px 10px; border-radius: 5px; }
QMenu::item:selected { background: #2b394b; }
QWidget#Sidebar {
    background: #171e28;
    border-right: 1px solid #2a3544;
}
QLabel#Brand {
    font-size: 16pt;
    font-weight: 750;
    color: #f5f7fb;
    padding: 14px 10px;
}
QLabel#Eyebrow {
    color: #8e9bab;
    font-size: 8pt;
    font-weight: 700;
    letter-spacing: 1px;
}
QLabel#PageTitle {
    font-size: 22pt;
    font-weight: 750;
    color: #f5f7fb;
}
QLabel#Muted { color: #9aa7b7; }
QLabel#CardTitle {
    font-size: 11pt;
    font-weight: 700;
    color: #eff3f8;
}
QFrame#Card, QGroupBox {
    background: #19212c;
    border: 1px solid #2d3949;
    border-radius: 13px;
}
QGroupBox {
    margin-top: 14px;
    padding: 15px 13px 12px 13px;
    font-weight: 650;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 6px;
    color: #e1e8f1;
}
QPushButton {
    background: #222c39;
    border: 1px solid #354457;
    border-radius: 9px;
    padding: 9px 14px;
    min-height: 20px;
    color: #e0e7f0;
    font-weight: 600;
}
QPushButton:hover {
    background: #2b394a;
    border-color: #61748c;
}
QPushButton:pressed { background: #18212c; }
QPushButton:disabled {
    background: #1b232d;
    border-color: #293443;
    color: #697789;
}
QPushButton#Primary {
    background: #a3e635;
    border: 1px solid #b8f45a;
    color: #1c290b;
    font-weight: 750;
}
QPushButton#Primary:hover { background: #b5f04e; }
QPushButton#Nav {
    background: transparent;
    border: 0;
    border-left: 3px solid transparent;
    border-radius: 8px;
    text-align: left;
    padding: 11px 12px;
    color: #a0acbb;
    font-weight: 650;
}
QPushButton#Nav:hover {
    background: #202a37;
    color: #f0f4f8;
}
QPushButton#Nav:checked {
    background: #26351d;
    color: #c7f36d;
    border-left: 3px solid #a3e635;
}
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QListWidget, QTableWidget {
    background: #111821;
    border: 1px solid #354356;
    border-radius: 8px;
    padding: 8px;
    color: #e7edf5;
    selection-background-color: #40546c;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus {
    border: 1px solid #a3e635;
}
QComboBox::drop-down { border: 0; width: 26px; }
QComboBox QAbstractItemView {
    background: #1a222d;
    color: #edf3fa;
    selection-background-color: #35485e;
    border: 1px solid #3a4a5e;
    outline: 0;
}
QCheckBox { spacing: 8px; color: #dce4ed; }
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #526176;
    border-radius: 4px;
    background: #111821;
}
QCheckBox::indicator:checked {
    background: #a3e635;
    border-color: #a3e635;
}
QProgressBar {
    background: #111821;
    border: 1px solid #354356;
    border-radius: 7px;
    text-align: center;
    color: #edf3fa;
    height: 16px;
}
QProgressBar::chunk { background: #a3e635; border-radius: 6px; }
QHeaderView::section {
    background: #202a37;
    color: #b9c5d4;
    border: 0;
    border-bottom: 1px solid #354356;
    padding: 9px;
    font-weight: 700;
}
QTableWidget {
    gridline-color: #2d3949;
    alternate-background-color: #171f29;
}
QTableWidget::item { padding: 5px; }
QTableWidget::item:selected { background: #34495f; color: #ffffff; }
QScrollArea { border: 0; background: transparent; }
QScrollBar:vertical {
    background: #151d27;
    width: 11px;
    margin: 2px;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background: #46566a;
    min-height: 28px;
    border-radius: 5px;
}
QScrollBar::handle:vertical:hover { background: #60758f; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal {
    background: #151d27;
    height: 11px;
    margin: 2px;
    border-radius: 5px;
}
QScrollBar::handle:horizontal {
    background: #46566a;
    min-width: 28px;
    border-radius: 5px;
}
QSplitter::handle { background: #2a3544; }
QToolTip {
    background: #202a37;
    color: #f2f6fb;
    border: 1px solid #46566a;
    padding: 6px;
}
"""


def card(title: str, description: str = "") -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("Card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(18, 16, 18, 16)
    layout.setSpacing(10)
    heading = QLabel(title)
    heading.setObjectName("CardTitle")
    layout.addWidget(heading)
    if description:
        desc = QLabel(description)
        desc.setObjectName("Muted")
        desc.setWordWrap(True)
        layout.addWidget(desc)
    return frame, layout


def page_heading(title: str, subtitle: str):
    box = QVBoxLayout()
    box.setSpacing(4)
    title_label = QLabel(title)
    title_label.setObjectName("PageTitle")
    sub = QLabel(subtitle)
    sub.setObjectName("Muted")
    sub.setWordWrap(True)
    box.addWidget(title_label)
    box.addWidget(sub)
    return box


class AdvancedSettingsWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(12)

        encoding = QGroupBox("Video & audio encoding")
        form = QGridLayout(encoding)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)
        self.video_codec = self._combo(["copy", "h264", "hevc", "av1", "vp9", "vp8", "mpeg4", "mpeg2", "theora"])
        self.audio_codec = self._combo(["copy", "aac", "mp3", "opus", "vorbis", "flac", "pcm", "alac"])
        self.rate_control = self._combo(["Source", "CRF", "CBR", "VBR", "CQ"])
        self.video_bitrate = QLineEdit()
        self.video_bitrate.setPlaceholderText("e.g. 4500k")
        self.audio_bitrate = QLineEdit()
        self.audio_bitrate.setPlaceholderText("e.g. 192k")
        self.crf = QSpinBox()
        self.crf.setRange(0, 63)
        self.crf.setValue(23)
        self.encoder_preset = self._combo(["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow", "placebo"])
        self.fps = self._combo(["Source", "VFR", "15", "20", "23.976", "24", "25", "29.97", "30", "48", "50", "59.94", "60", "90", "120"])
        self.fps.setEditable(True)
        self.fps_mode = self._combo(["CFR", "VFR"])
        self.resolution = self._combo(["Source", "2160p", "1440p", "1080p", "720p", "540p", "480p", "360p", "240p", "Custom"])
        self.custom_scale = QLineEdit()
        self.custom_scale.setPlaceholderText("e.g. 1920x1080 (optional)")
        self.sample_rate = self._combo(["Source", "22050", "32000", "44100", "48000", "96000", "192000"])
        self.channels = self._combo(["Source", "Mono", "Stereo"])
        self._field(form, 0, 0, "Video codec", self.video_codec)
        self._field(form, 0, 1, "Audio codec", self.audio_codec)
        self._field(form, 1, 0, "Rate control", self.rate_control)
        self._field(form, 1, 1, "Video bitrate", self.video_bitrate)
        self._field(form, 2, 0, "Audio bitrate", self.audio_bitrate)
        self._field(form, 2, 1, "CRF / quality", self.crf)
        self._field(form, 3, 0, "Encoder preset", self.encoder_preset)
        self._field(form, 3, 1, "Frame rate (FPS)", self.fps)
        self._field(form, 4, 0, "Frame mode", self.fps_mode)
        self._field(form, 4, 1, "Output resolution", self.resolution)
        self._field(form, 5, 0, "Custom resolution", self.custom_scale)
        self._field(form, 5, 1, "Sample rate (Hz)", self.sample_rate)
        self._field(form, 6, 0, "Audio channels", self.channels)
        layout.addWidget(encoding)

        encoder_details = QGroupBox("Encoder details · optional")
        detail_grid = QGridLayout(encoder_details)
        self.video_encoder = self._combo([
            "Auto", "libx264", "h264_nvenc", "h264_qsv", "h264_amf",
            "libx265", "hevc_nvenc", "hevc_qsv", "hevc_amf",
            "libsvtav1", "libaom-av1", "av1_nvenc", "libvpx-vp9", "libvpx",
            "mpeg4", "mpeg2video", "libtheora",
        ])
        self.profile = QLineEdit()
        self.profile.setPlaceholderText("e.g. high (blank = automatic)")
        self.level = QLineEdit()
        self.level.setPlaceholderText("e.g. 4.1 (blank = automatic)")
        self.pixel_format = self._combo(["Auto", "yuv420p", "yuv422p", "yuv444p", "yuv420p10le", "yuv422p10le", "yuv444p10le", "p010le", "rgb24"])
        self.color_space = self._combo(["Auto", "bt709", "bt2020nc", "smpte170m", "bt470bg", "smpte240m"])
        self.color_range = self._combo(["Auto", "tv", "pc"])
        self._field(detail_grid, 0, 0, "Encoder (Auto or explicit)", self.video_encoder)
        self._field(detail_grid, 0, 1, "Profile", self.profile)
        self._field(detail_grid, 0, 2, "Level", self.level)
        self._field(detail_grid, 1, 0, "Pixel format / bit depth", self.pixel_format)
        self._field(detail_grid, 1, 1, "Color space", self.color_space)
        self._field(detail_grid, 1, 2, "Color range", self.color_range)
        layout.addWidget(encoder_details)

        preservation = QGroupBox("Subtitles & metadata")
        p_layout = QGridLayout(preservation)
        self.write_subtitles = QCheckBox("Download available subtitles")
        self.write_automatic = QCheckBox("Include automatic captions")
        self.embed_subtitles = QCheckBox("Embed subtitles into output (when supported)")
        self.preserve_metadata = QCheckBox("Preserve metadata and chapters")
        self.preserve_metadata.setChecked(True)
        self.download_thumbnail = QCheckBox("Download thumbnail / artwork when available")
        p_layout.addWidget(self.write_subtitles, 0, 0)
        p_layout.addWidget(self.write_automatic, 0, 1)
        p_layout.addWidget(self.embed_subtitles, 1, 0, 1, 2)
        p_layout.addWidget(self.preserve_metadata, 2, 0)
        p_layout.addWidget(self.download_thumbnail, 2, 1)
        layout.addWidget(preservation)
        note = QLabel("Auto selects an encoder available in your FFmpeg build (software encoders are preferred). You can explicitly choose NVENC / QSV / AMF when supported by your hardware and drivers. “copy” avoids re-encoding; pixel formats include 10-bit choices. CRF is codec-specific; CBR/VBR require a video bitrate.")
        note.setObjectName("Muted")
        note.setWordWrap(True)
        layout.addWidget(note)

    @staticmethod
    def _combo(items):
        c = QComboBox()
        c.addItems(items)
        return c

    @staticmethod
    def _field(grid, row, col, label, widget):
        wrap = QWidget()
        l = QVBoxLayout(wrap)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(4)
        t = QLabel(label)
        t.setObjectName("Muted")
        l.addWidget(t)
        l.addWidget(widget)
        grid.addWidget(wrap, row, col)

    def options(self) -> dict:
        fps = self.fps.currentText().strip() or "Source"
        return {
            "video_codec": self.video_codec.currentText(),
            "audio_codec": self.audio_codec.currentText(),
            "video_encoder": self.video_encoder.currentText(),
            "profile": self.profile.text().strip(),
            "level": self.level.text().strip(),
            "pixel_format": self.pixel_format.currentText(),
            "color_space": self.color_space.currentText(),
            "color_range": self.color_range.currentText(),
            "rate_control": self.rate_control.currentText(),
            "video_bitrate": self.video_bitrate.text().strip(),
            "audio_bitrate": self.audio_bitrate.text().strip(),
            "crf": str(self.crf.value()),
            "encoder_preset": self.encoder_preset.currentText(),
            "fps": fps,
            "fps_mode": self.fps_mode.currentText(),
            "resolution": self.resolution.currentText(),
            "custom_scale": self.custom_scale.text().strip(),
            "sample_rate": self.sample_rate.currentText(),
            "channels": self.channels.currentText(),
            "write_subtitles": self.write_subtitles.isChecked(),
            "write_automatic_subtitles": self.write_automatic.isChecked(),
            "embed_subtitles": self.embed_subtitles.isChecked(),
            "preserve_metadata": self.preserve_metadata.isChecked(),
            "download_thumbnail": self.download_thumbnail.isChecked(),
        }

    def apply_options(self, options: dict):
        mapping = {
            "video_codec": self.video_codec, "audio_codec": self.audio_codec,
            "video_encoder": self.video_encoder, "pixel_format": self.pixel_format,
            "color_space": self.color_space, "color_range": self.color_range,
            "rate_control": self.rate_control, "encoder_preset": self.encoder_preset,
            "fps_mode": self.fps_mode, "resolution": self.resolution,
            "sample_rate": self.sample_rate, "channels": self.channels,
        }
        combo_defaults = {
            "video_codec": "copy", "audio_codec": "copy", "video_encoder": "Auto",
            "pixel_format": "Auto", "color_space": "Auto", "color_range": "Auto",
            "rate_control": "Source", "encoder_preset": "medium", "fps_mode": "CFR",
            "resolution": "Source", "sample_rate": "Source", "channels": "Source",
        }
        for key, combo in mapping.items():
            value = str(options.get(key, combo_defaults.get(key, "")))
            index = combo.findText(value)
            if index >= 0:
                combo.setCurrentIndex(index)
            else:
                default_index = combo.findText(combo_defaults.get(key, ""))
                if default_index >= 0:
                    combo.setCurrentIndex(default_index)
        self.fps.setCurrentText(str(options.get("fps", "Source")))
        self.video_bitrate.setText(str(options.get("video_bitrate", "")))
        self.audio_bitrate.setText(str(options.get("audio_bitrate", "")))
        try:
            self.crf.setValue(int(options.get("crf", "23")))
        except (ValueError, TypeError):
            self.crf.setValue(23)
        self.custom_scale.setText(str(options.get("custom_scale", "")))
        self.profile.setText(str(options.get("profile", "")))
        self.level.setText(str(options.get("level", "")))
        checkbox_defaults = {
            "write_subtitles": False,
            "write_automatic_subtitles": False,
            "embed_subtitles": False,
            "preserve_metadata": True,
            "download_thumbnail": False,
        }
        for key, widget in {
            "write_subtitles": self.write_subtitles,
            "write_automatic_subtitles": self.write_automatic,
            "embed_subtitles": self.embed_subtitles,
            "preserve_metadata": self.preserve_metadata,
            "download_thumbnail": self.download_thumbnail,
        }.items():
            widget.setChecked(bool(options.get(key, checkbox_defaults[key])))


class AnalysisDialog(QDialog):
    """Compact, readable media-inspection window with thumbnail and source details."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("AnalysisDialog")
        self.setWindowTitle("Analyze URL")
        self.setModal(False)
        self.resize(900, 720)
        self.setMinimumSize(760, 620)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(12)

        header = QHBoxLayout()
        intro = QVBoxLayout()
        eyebrow = QLabel("SOURCE INSPECTION")
        eyebrow.setObjectName("Eyebrow")
        self.heading = QLabel("Analyze URL")
        self.heading.setStyleSheet("font-size: 19pt; font-weight: 750; color: #f5f7fb;")
        self.status = QLabel("Waiting for the source…")
        self.status.setObjectName("Muted")
        intro.addWidget(eyebrow)
        intro.addWidget(self.heading)
        intro.addWidget(self.status)
        header.addLayout(intro, 1)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedWidth(150)
        header.addWidget(self.progress, 0, Qt.AlignVCenter)
        root.addLayout(header)

        self.loading_panel = QFrame()
        self.loading_panel.setObjectName("Card")
        loading_layout = QVBoxLayout(self.loading_panel)
        loading_layout.setContentsMargins(22, 22, 22, 22)
        loading_layout.setSpacing(10)
        self.loading_title = QLabel("Fetching media information")
        self.loading_title.setStyleSheet("font-size: 14pt; font-weight: 700;")
        self.loading_detail = QLabel("yt-dlp is checking the page, available formats, and preview image.")
        self.loading_detail.setObjectName("Muted")
        self.loading_detail.setWordWrap(True)
        loading_layout.addStretch(1)
        loading_layout.addWidget(self.loading_title, 0, Qt.AlignHCenter)
        loading_layout.addWidget(self.loading_detail, 0, Qt.AlignHCenter)
        loading_layout.addStretch(1)
        root.addWidget(self.loading_panel, 1)

        self.error_panel = QFrame()
        self.error_panel.setObjectName("Card")
        error_layout = QVBoxLayout(self.error_panel)
        error_layout.setContentsMargins(18, 18, 18, 18)
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #ff9e9e;")
        error_layout.addWidget(self.error_label)
        self.error_panel.hide()
        root.addWidget(self.error_panel, 1)

        self.result_panel = QWidget()
        result_layout = QVBoxLayout(self.result_panel)
        result_layout.setContentsMargins(0, 0, 0, 0)
        result_layout.setSpacing(12)

        hero = QFrame()
        hero.setObjectName("Card")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(14, 14, 14, 14)
        hero_layout.setSpacing(18)

        self.thumbnail = QLabel("Thumbnail will appear here")
        self.thumbnail.setAlignment(Qt.AlignCenter)
        self.thumbnail.setFixedSize(330, 186)
        self.thumbnail.setWordWrap(True)
        self.thumbnail.setStyleSheet(
            "background: #101720; border: 1px solid #354356; "
            "border-radius: 9px; color: #8e9bab; padding: 8px;"
        )
        hero_layout.addWidget(self.thumbnail, 0, Qt.AlignTop)

        info_column = QVBoxLayout()
        info_column.setSpacing(8)
        self.title_label = QLabel("Untitled media")
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet("font-size: 15pt; font-weight: 750; color: #f5f7fb;")
        info_column.addWidget(self.title_label)

        metadata = QGridLayout()
        metadata.setHorizontalSpacing(14)
        metadata.setVerticalSpacing(8)
        self.metadata_values = {}
        labels = [
            ("Uploader", "uploader"), ("Duration", "duration"),
            ("Views", "views"), ("Published", "published"),
            ("Source", "source"), ("Available formats", "formats"),
            ("Subtitles", "subtitles"), ("Likes", "likes"),
        ]
        for index, (label, key) in enumerate(labels):
            row, col = divmod(index, 2)
            cell = QVBoxLayout()
            cell.setSpacing(2)
            key_label = QLabel(label.upper())
            key_label.setObjectName("Eyebrow")
            value_label = QLabel("—")
            value_label.setWordWrap(True)
            value_label.setStyleSheet("color: #e7edf5; font-weight: 650;")
            cell.addWidget(key_label)
            cell.addWidget(value_label)
            metadata.addLayout(cell, row, col)
            self.metadata_values[key] = value_label
        info_column.addLayout(metadata)
        info_column.addStretch(1)
        hero_layout.addLayout(info_column, 1)
        result_layout.addWidget(hero)

        description_card = QFrame()
        description_card.setObjectName("Card")
        description_layout = QVBoxLayout(description_card)
        description_layout.setContentsMargins(14, 12, 14, 12)
        description_layout.setSpacing(6)
        description_title = QLabel("DESCRIPTION")
        description_title.setObjectName("Eyebrow")
        description_layout.addWidget(description_title)
        self.description = QPlainTextEdit()
        self.description.setReadOnly(True)
        self.description.setMaximumHeight(100)
        self.description.setPlaceholderText("No description provided by the source.")
        description_layout.addWidget(self.description)
        self.tags_label = QLabel()
        self.tags_label.setObjectName("Muted")
        self.tags_label.setWordWrap(True)
        description_layout.addWidget(self.tags_label)
        result_layout.addWidget(description_card)

        formats_card = QFrame()
        formats_card.setObjectName("Card")
        formats_layout = QVBoxLayout(formats_card)
        formats_layout.setContentsMargins(14, 12, 14, 12)
        formats_layout.setSpacing(6)
        formats_title = QLabel("AVAILABLE FORMATS")
        formats_title.setObjectName("Eyebrow")
        formats_layout.addWidget(formats_title)
        self.formats_table = QTableWidget(0, 5)
        self.formats_table.setHorizontalHeaderLabels(
            ["ID", "Container", "Resolution", "FPS", "Video / audio"]
        )
        self.formats_table.verticalHeader().setVisible(False)
        self.formats_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.formats_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.formats_table.setAlternatingRowColors(True)
        self.formats_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.formats_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.formats_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.formats_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.formats_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.formats_table.setMaximumHeight(190)
        formats_layout.addWidget(self.formats_table)
        result_layout.addWidget(formats_card)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(self.result_panel)
        self.result_panel.hide()
        root.addWidget(scroll, 1)

        actions = QHBoxLayout()
        actions.addStretch(1)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        close_button.setMinimumWidth(100)
        actions.addWidget(close_button)
        root.addLayout(actions)

    @staticmethod
    def _number(value):
        try:
            return f"{int(value):,}"
        except (TypeError, ValueError, OverflowError):
            return "—"

    @staticmethod
    def _duration(value):
        try:
            seconds = max(0, int(float(value)))
        except (TypeError, ValueError, OverflowError):
            return "Live / unknown"
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:d}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:d}:{seconds:02d}"

    @staticmethod
    def _date(value):
        value = str(value or "")
        if len(value) == 8 and value.isdigit():
            return f"{value[0:4]}-{value[4:6]}-{value[6:8]}"
        return value or "—"

    def show_loading(self, url):
        self.heading.setText("Analyzing media")
        self.status.setText("Connecting to the source and reading its metadata…")
        self.loading_detail.setText(url)
        self.progress.show()
        self.loading_panel.show()
        self.error_panel.hide()
        self.result_panel.hide()
        self.show()
        self.raise_()
        self.activateWindow()

    def show_error(self, message):
        self.heading.setText("Analysis could not be completed")
        self.status.setText("The source did not return usable media information.")
        self.progress.hide()
        self.loading_panel.hide()
        self.result_panel.hide()
        self.error_label.setText(str(message))
        self.error_panel.show()
        self.show()
        self.raise_()
        self.activateWindow()

    def show_result(self, info):
        self.heading.setText("Media information")
        self.status.setText(
            f"{info.get('extractor') or 'Media source'} · "
            f"{len(info.get('formats') or [])} formats found"
        )
        self.progress.hide()
        self.loading_panel.hide()
        self.error_panel.hide()

        self.title_label.setText(str(info.get("title") or "Untitled media"))
        values = {
            "uploader": info.get("uploader") or info.get("channel") or "—",
            "duration": self._duration(info.get("duration")),
            "views": self._number(info.get("view_count")),
            "published": self._date(info.get("upload_date") or info.get("release_date")),
            "source": info.get("extractor") or "—",
            "formats": self._number(len(info.get("formats") or [])),
            "subtitles": self._number(
                len(info.get("subtitles") or []) + len(info.get("automatic_captions") or [])
            ),
            "likes": self._number(info.get("like_count")),
        }
        for key, label in self.metadata_values.items():
            label.setText(str(values.get(key, "—")))

        self.description.setPlainText(str(info.get("description") or "")[:12000])
        tags = [str(tag) for tag in (info.get("tags") or [])[:12] if tag]
        self.tags_label.setText("Tags: " + ", ".join(tags) if tags else "")

        pixmap = QPixmap()
        image_data = info.get("thumbnail_data")
        if image_data and pixmap.loadFromData(image_data):
            self.thumbnail.setPixmap(
                pixmap.scaled(
                    self.thumbnail.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
            )
            self.thumbnail.setText("")
        else:
            self.thumbnail.setPixmap(QPixmap())
            self.thumbnail.setText("Preview image unavailable")

        formats = info.get("formats") or []
        self.formats_table.setRowCount(0)
        for source_format in formats[:14]:
            row = self.formats_table.rowCount()
            self.formats_table.insertRow(row)
            codecs = " / ".join(
                str(value) for value in (
                    source_format.get("vcodec"),
                    source_format.get("acodec"),
                ) if value and value != "none"
            ) or "—"
            values = [
                source_format.get("format_id", "—"),
                source_format.get("ext", "—"),
                source_format.get("resolution", "—"),
                source_format.get("fps") or "—",
                codecs,
            ]
            for col, value in enumerate(values):
                self.formats_table.setItem(row, col, QTableWidgetItem(str(value)))
        self.result_panel.show()
        self.show()
        self.raise_()
        self.activateWindow()


class DownloadPage(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        self.analysis_worker = None
        self.analysis_dialog = AnalysisDialog(self)
        self.latest_analysis = None
        self.latest_analysis_url = ""
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(18)
        root.addLayout(page_heading("Downloader", "Paste one or more URLs. Inspect source formats, choose an output profile, and send downloads to the queue."))

        top, top_l = card("Add media", "Supports direct media links and compatible public media sources through yt-dlp. Only download media you have permission to save.")
        row = QHBoxLayout()
        self.url = QPlainTextEdit()
        self.url.setPlaceholderText("Paste a media URL… (multiple URLs: one per line)")
        self.url.setFixedHeight(76)
        self.analyze_btn = QPushButton("Analyze URL")
        self.analyze_btn.setMinimumHeight(42)
        self.analyze_btn.clicked.connect(self.analyze)
        row.addWidget(self.url, 1)
        row.addWidget(self.analyze_btn)
        top_l.addLayout(row)
        self.analysis_label = QLabel("No media analyzed yet. You can also add a URL directly to the queue.")
        self.analysis_label.setObjectName("Muted")
        self.analysis_label.setTextFormat(Qt.PlainText)
        self.analysis_label.setWordWrap(True)
        top_l.addWidget(self.analysis_label)
        root.addWidget(top)

        settings_card, settings_l = card("Download setup", "Keep it simple with a ready-made profile, or open Advanced for detailed stream and encoding controls.")
        grid = QGridLayout()
        self.quality = QComboBox()
        self.quality.addItem("Best video + audio", "bestvideo+bestaudio/best")
        self.quality.addItem("Best single file", "best")
        self.quality.addItem("1080p or lower", "bestvideo[height<=1080]+bestaudio/best[height<=1080]")
        self.quality.addItem("720p or lower", "bestvideo[height<=720]+bestaudio/best[height<=720]")
        self.quality.addItem("480p or lower", "bestvideo[height<=480]+bestaudio/best[height<=480]")
        self.quality.addItem("Audio only", "bestaudio/best")
        self.output_format = QComboBox()
        self.output_format.addItems(["Original", "MP4", "MKV", "WebM", "MOV", "AVI", "3GP", "TS", "MPEG", "OGV", "M4V", "MP3", "M4A", "AAC", "Opus", "OGG", "FLAC", "WAV", "AIFF", "WMA"])
        self.preset = QComboBox()
        self.preset.addItems(list(self.main.presets.keys()))
        self.preset.currentTextChanged.connect(self.apply_preset)
        self.save_preset_btn = QPushButton("Save as preset")
        self.save_preset_btn.clicked.connect(lambda: self.save_custom_preset(self.advanced_widget.options(), self.output_format.currentText(), self.quality.currentData()))
        self.advanced_toggle = QCheckBox("Show advanced controls")
        self._grid_field(grid, 0, 0, "Source quality", self.quality)
        self._grid_field(grid, 0, 1, "Output format", self.output_format)
        self._grid_field(grid, 1, 0, "Preset", self.preset)
        grid.addWidget(self.save_preset_btn, 1, 1)
        settings_l.addLayout(grid)
        settings_l.addWidget(self.advanced_toggle)
        self.advanced_widget = AdvancedSettingsWidget()
        self.advanced_widget.setVisible(False)
        self.advanced_toggle.toggled.connect(self.advanced_widget.setVisible)
        settings_l.addWidget(self.advanced_widget)
        row2 = QHBoxLayout()
        self.output_label = QLabel(f"Save to: {self.main.settings['output_dir']}")
        self.output_label.setObjectName("Muted")
        row2.addWidget(self.output_label, 1)
        change_folder = QPushButton("Change folder")
        change_folder.clicked.connect(self.choose_output)
        row2.addWidget(change_folder)
        self.add_btn = QPushButton("Add to download queue")
        self.add_btn.setObjectName("Primary")
        self.add_btn.setMinimumHeight(42)
        self.add_btn.clicked.connect(self.add_to_queue)
        row2.addWidget(self.add_btn)
        settings_l.addLayout(row2)
        root.addWidget(settings_card, 1)

    @staticmethod
    def _grid_field(grid, row, col, title, widget):
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lbl = QLabel(title)
        lbl.setObjectName("Muted")
        lay.addWidget(lbl)
        lay.addWidget(widget)
        grid.addWidget(box, row, col)

    def analyze(self):
        url_text = self.url.toPlainText().strip()
        url = url_text.splitlines()[0] if url_text else ""
        if not url:
            QMessageBox.information(self, "URL required", "Paste a media URL first.")
            return
        if not is_http_url(url):
            QMessageBox.warning(self, "Invalid URL", "Enter a complete http:// or https:// URL.")
            return
        self.analyze_btn.setEnabled(False)
        self.analysis_label.setText("Inspecting available formats…")
        self.analysis_dialog.show_loading(url)
        self.analysis_worker = AnalyzeWorker(url, self, self.main.settings)
        self.analysis_worker.completed.connect(self.analysis_done)
        self.analysis_worker.failed.connect(self.analysis_failed)
        self.analysis_worker.finished.connect(lambda: self.analyze_btn.setEnabled(True))
        self.analysis_worker.start()

    def analysis_done(self, info):
        self.latest_analysis = dict(info)
        self.latest_analysis_url = self.url.toPlainText().strip().splitlines()[0].strip()
        self.analysis_dialog.show_result(info)
        title = info.get("title", "Media")
        duration = info.get("duration")
        duration_text = f" · {int(duration // 60)}:{int(duration % 60):02d}" if isinstance(duration, (int, float)) else ""
        self.analysis_label.setStyleSheet("")
        self.analysis_label.setText(
            f"{title}{duration_text} · {info.get('uploader', '')} · "
            f"{len(info.get('formats', []))} source formats · "
            f"{len(info.get('subtitles', []))} subtitle languages"
        )
        self.quality.clear()
        self.quality.addItem("Best video + audio", "bestvideo+bestaudio/best")
        self.quality.addItem("Best single file", "best")
        self.quality.addItem("Audio only", "bestaudio/best")
        for f in info.get("formats", []):
            h = f.get("height")
            fps = f.get("fps")
            size = f.get("filesize")
            note = f.get("note") or f.get("format") or ""
            label = f"{f.get('format_id')} · {f.get('resolution')} · {f.get('ext')}"
            if fps:
                label += f" · {fps:g} fps"
            if size:
                label += f" · {size / 1024 / 1024:.1f} MB"
            if note:
                label += f" · {note[:48]}"
            # Add best compatible audio when the selected source is video-only.
            fmt = f.get("format_id", "best")
            if f.get("vcodec") not in (None, "none") and f.get("acodec") in (None, "none"):
                fmt = f"{fmt}+bestaudio/best"
            self.quality.addItem(label, fmt)
        # Analysis rebuilds the source-format menu. Re-apply the selected
        # preset's selector so analyzing a URL cannot silently undo the profile.
        selected_preset = self.main.presets.get(self.preset.currentText(), {})
        preset_format = selected_preset.get("format") if isinstance(selected_preset, dict) else None
        if preset_format:
            match = self.quality.findData(preset_format)
            if match < 0:
                self.quality.addItem(
                    f"{self.preset.currentText()} source selection",
                    preset_format,
                )
                match = self.quality.count() - 1
            self.quality.setCurrentIndex(match)
        else:
            self.quality.setCurrentIndex(0)

    def analysis_failed(self, message):
        self.analysis_label.setText(f"Analysis failed: {message}")
        self.analysis_label.setStyleSheet("color: #ff9e9e;")
        self.analysis_dialog.show_error(message)

    def apply_preset(self, name):
        preset = self.main.presets.get(name)
        if not preset:
            return
        fmt = preset.get("container", "original")
        target_fmt = "original" if str(fmt).lower() == "original" else str(fmt).lower()
        for idx in range(self.output_format.count()):
            candidate = "original" if self.output_format.itemText(idx).lower() == "original" else self.output_format.itemText(idx).lower()
            if candidate == target_fmt:
                self.output_format.setCurrentIndex(idx)
                break
        if "format" in preset:
            match = self.quality.findData(preset["format"])
            if match < 0:
                self.quality.addItem(f"Preset source selection · {preset['format']}", preset["format"])
                match = self.quality.count() - 1
            self.quality.setCurrentIndex(match)
        self.advanced_widget.apply_options(preset)

    def save_custom_preset(self, adv, output_format, source_format):
        name, ok = QInputDialog.getText(self, "Save preset", "Preset name (1–48 characters):")
        if not ok:
            return
        name = name.strip()
        if not _valid_preset_name(name):
            QMessageBox.warning(
                self, "Invalid preset name",
                "Use 1–48 characters. Start with a letter or number and avoid trailing punctuation.",
            )
            return
        if name in PRESETS:
            QMessageBox.warning(
                self, "Built-in preset",
                "Built-in presets are protected. Choose a different name for your custom profile.",
            )
            return
        custom = self.main.settings.setdefault("custom_presets", {})
        if name in custom:
            answer = QMessageBox.question(
                self, "Replace custom preset?",
                f"A custom preset named “{name}” already exists. Replace it?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
        data = dict(adv)
        data.update({
            "container": "original" if output_format == "Original" else output_format.lower(),
            "format": source_format or "bestvideo+bestaudio/best",
        })
        custom[name] = data
        self.main.save_settings()
        self.main.refresh_presets()
        self.preset.setCurrentText(name)
        QMessageBox.information(self, "Preset saved", f"Saved “{name}”.")

    def choose_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose output folder", self.main.settings["output_dir"])
        if folder:
            self.main.set_output_folder(folder)

    def add_to_queue(self):
        urls = [x.strip() for x in self.url.toPlainText().splitlines() if x.strip()] if hasattr(self.url, "toPlainText") else [x.strip() for x in self.url.text().splitlines() if x.strip()]
        if not urls:
            QMessageBox.information(self, "URL required", "Paste one or more URLs first.")
            return
        invalid_urls = [url for url in urls if not is_http_url(url)]
        urls = [url for url in urls if is_http_url(url)]
        if invalid_urls:
            preview = "\n".join(invalid_urls[:3])
            suffix = "\n…" if len(invalid_urls) > 3 else ""
            QMessageBox.warning(
                self, "Some URLs were skipped",
                f"{len(invalid_urls)} invalid URL(s) were skipped. Use complete http:// or https:// links.\n\n{preview}{suffix}",
            )
        if not urls:
            return
        options = self.advanced_widget.options()
        options["container"] = "original" if self.output_format.currentText() == "Original" else self.output_format.currentText().lower()
        options["format"] = self.quality.currentData() or "bestvideo+bestaudio/best"
        options["audio_only"] = str(options["format"]).startswith("bestaudio") or options["container"] in {"mp3", "m4a", "aac", "opus", "ogg", "flac", "wav"}
        analysed = (
            self.latest_analysis
            if self.latest_analysis and urls[0] == self.latest_analysis_url
            else None
        )
        self.main.add_download_tasks(urls, options, analyzed_info=analysed)
        self.main.navigate("Queue")


class ConverterPage(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        self.files: list[str] = []
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(18)
        root.addLayout(page_heading("Converter", "Convert local media with FFmpeg. Remux, extract audio, scale resolution, adjust FPS, and configure codecs."))
        pick_card, pick_l = card("Input files", "Select one or several local audio/video files. Each file becomes a queue task.")
        pick_row = QHBoxLayout()
        self.files_label = QLabel("No files selected")
        self.files_label.setObjectName("Muted")
        self.files_label.setWordWrap(True)
        browse = QPushButton("Choose files…")
        browse.clicked.connect(self.choose_files)
        pick_row.addWidget(self.files_label, 1)
        pick_row.addWidget(browse)
        pick_l.addLayout(pick_row)
        root.addWidget(pick_card)

        output_card, output_l = card("Output profile", "Choose the destination container and then customize the exact encoding options below.")
        row = QHBoxLayout()
        self.output_format = QComboBox()
        self.output_format.addItems(["MP4", "MKV", "WebM", "MOV", "AVI", "3GP", "TS", "MPEG", "OGV", "M4V", "MP3", "M4A", "AAC", "Opus", "OGG", "FLAC", "WAV", "AIFF", "WMA"])
        self.output_format.setCurrentText("MP4")
        self.preset = QComboBox()
        self.preset.addItems(list(self.main.presets.keys()))
        self.preset.currentTextChanged.connect(self.apply_preset)
        row.addWidget(QLabel("Output format"))
        row.addWidget(self.output_format)
        row.addSpacing(12)
        row.addWidget(QLabel("Preset"))
        row.addWidget(self.preset, 1)
        output_l.addLayout(row)
        self.advanced = AdvancedSettingsWidget()
        output_l.addWidget(self.advanced)
        root.addWidget(output_card, 1)

        bottom = QHBoxLayout()
        self.dest = QLabel(f"Save to: {self.main.settings['output_dir']}")
        self.dest.setObjectName("Muted")
        change = QPushButton("Change output folder")
        change.clicked.connect(self.choose_output)
        add = QPushButton("Add conversion(s) to queue")
        add.setObjectName("Primary")
        add.clicked.connect(self.add_conversions)
        bottom.addWidget(self.dest, 1)
        bottom.addWidget(change)
        bottom.addWidget(add)
        root.addLayout(bottom)

    def choose_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select media files", str(Path.home()), "Media files (*.mp4 *.mkv *.webm *.mov *.avi *.3gp *.mp3 *.m4a *.aac *.ogg *.opus *.flac *.wav *.aiff *.ts *.mpg *.mpeg);;All files (*)")
        if files:
            self.files = files
            names = [Path(f).name for f in files[:3]]
            text = ", ".join(names) + (f" and {len(files) - 3} more" if len(files) > 3 else "")
            self.files_label.setText(f"{len(files)} file(s): {text}")

    def apply_preset(self, name):
        preset = self.main.presets.get(name)
        if preset:
            fmt = str(preset.get("container", "mp4")).lower()
            for idx in range(self.output_format.count()):
                if self.output_format.itemText(idx).lower() == fmt:
                    self.output_format.setCurrentIndex(idx)
                    break
            self.advanced.apply_options(preset)

    def choose_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose output folder", self.main.settings["output_dir"])
        if folder:
            self.main.set_output_folder(folder)

    def add_conversions(self):
        if not self.files:
            QMessageBox.information(self, "Input required", "Choose at least one media file.")
            return
        options = self.advanced.options()
        options["container"] = self.output_format.currentText().lower()
        self.main.add_conversion_tasks(self.files, options)
        self.main.navigate("Queue")


class QueuePage(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)
        root.addLayout(page_heading("Download & conversion queue", "Monitor active work, inspect logs, cancel running jobs, and retry failed tasks."))
        toolbar = QHBoxLayout()
        self.run_status = QLabel("Queue is idle")
        self.run_status.setObjectName("Muted")
        toolbar.addWidget(self.run_status, 1)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.cancel_selected)
        self.retry_btn = QPushButton("Retry")
        self.retry_btn.clicked.connect(self.retry_selected)
        self.up_btn = QPushButton("Move up")
        self.up_btn.clicked.connect(lambda: self.move_selected(-1))
        self.down_btn = QPushButton("Move down")
        self.down_btn.clicked.connect(lambda: self.move_selected(1))
        self.remove_btn = QPushButton("Remove")
        self.remove_btn.clicked.connect(self.remove_selected)
        self.clear_btn = QPushButton("Clear completed")
        self.clear_btn.clicked.connect(self.clear_completed)
        toolbar.addWidget(self.cancel_btn)
        toolbar.addWidget(self.retry_btn)
        toolbar.addWidget(self.up_btn)
        toolbar.addWidget(self.down_btn)
        toolbar.addWidget(self.remove_btn)
        toolbar.addWidget(self.clear_btn)
        root.addLayout(toolbar)
        splitter = QSplitter(Qt.Vertical)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Task", "Type", "Status", "Progress", "Details", "Output"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        splitter.addWidget(self.table)
        log_frame = QFrame()
        log_frame.setObjectName("Card")
        log_layout = QVBoxLayout(log_frame)
        log_title = QLabel("Activity log")
        log_title.setObjectName("CardTitle")
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(1200)
        log_layout.addWidget(log_title)
        log_layout.addWidget(self.log_view)
        splitter.addWidget(log_frame)
        splitter.setSizes([440, 190])
        root.addWidget(splitter, 1)
        self.table.itemSelectionChanged.connect(self.update_actions)

    def update_actions(self):
        task_id = self.selected_task()
        task = self.main.find_task(task_id) if task_id else None
        selected = bool(task)
        queued = selected and task.get("status") == "Queued"
        retryable = selected and task.get("status") in {"Failed", "Cancelled"}
        removable = selected and task_id != self.main.active_task_id
        self.retry_btn.setEnabled(bool(retryable))
        self.up_btn.setEnabled(bool(queued))
        self.down_btn.setEnabled(bool(queued))
        self.remove_btn.setEnabled(bool(removable))
        cancelable = (selected and task.get("status") in {"Queued", "Starting", "Running"}) or (not selected and bool(self.main.active_task_id))
        self.cancel_btn.setEnabled(bool(cancelable))

    def selected_task(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.data(Qt.UserRole) if item else None

    def cancel_selected(self):
        task_id = self.selected_task()
        if task_id:
            self.main.cancel_task(task_id)
        elif self.main.active_task_id:
            self.main.cancel_task(self.main.active_task_id)

    def retry_selected(self):
        task_id = self.selected_task()
        if task_id:
            self.main.retry_task(task_id)

    def move_selected(self, direction):
        task_id = self.selected_task()
        if task_id:
            self.main.move_task(task_id, direction)

    def remove_selected(self):
        task_id = self.selected_task()
        if task_id:
            self.main.remove_task(task_id)

    def clear_completed(self):
        self.main.clear_completed()

    def append_log(self, task_id: str, message: str):
        self.log_view.appendPlainText(f"[{task_id[:8]}] {message}")

    def refresh(self, tasks: list, active_task_id=None):
        selected_id = self.selected_task() or active_task_id
        self.table.setRowCount(0)
        selected_row = -1
        for task in tasks:
            row = self.table.rowCount()
            self.table.insertRow(row)
            name = QTableWidgetItem(task.get("name", "Media task"))
            name.setData(Qt.UserRole, task["id"])
            typ = {"download": "Download", "convert": "Convert", "music": "Audio"}.get(task["kind"], task["kind"].title())
            values = [name, QTableWidgetItem(typ), QTableWidgetItem(task.get("status", "Queued")),
                      QTableWidgetItem(f"{task.get('progress', 0)}%"),
                      QTableWidgetItem(task.get("detail", "")),
                      QTableWidgetItem(task.get("output", ""))]
            for col, item in enumerate(values):
                self.table.setItem(row, col, item)
            if task["id"] == selected_id:
                selected_row = row
        if selected_row >= 0:
            self.table.selectRow(selected_row)
        queued = sum(1 for t in tasks if t["status"] == "Queued")
        self.run_status.setText(f"{queued} queued · {len(tasks)} total · {'Processing' if active_task_id else 'Idle'}")


class MusicHubPage(QWidget):
    """Native music discovery, local library, and playlist workspace."""

    def __init__(self, main):
        super().__init__()
        self.main = main
        self.search_worker = None
        self.lyrics_worker = None
        self.results: list[dict] = []
        self.library: list[dict] = []
        self.playlists = load_music_playlists()
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)
        root.addLayout(page_heading("Music workspace", "Discover tracks from public music catalogs, match audio with yt-dlp, and organize your local files."))
        section_row = QHBoxLayout()
        section_row.setSpacing(6)
        self.section_buttons = {}
        for section, label in [("Discover", "⌕  Search & Explore"), ("Library", "▤  Library"), ("Playlists", "≡  Playlists")]:
            button = QPushButton(label)
            button.setObjectName("Segment")
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, value=section: self.set_section(value))
            section_row.addWidget(button)
            self.section_buttons[section] = button
        section_row.addStretch(1)
        root.addLayout(section_row)
        self.tabs = QTabWidget()
        self.tabs.tabBar().setObjectName("HiddenTabs")
        self.tabs.tabBar().hide()
        self.tabs_effect = QGraphicsOpacityEffect(self.tabs)
        self.tabs_effect.setOpacity(1.0)
        self.tabs.setGraphicsEffect(self.tabs_effect)
        self.tabs_animation = QPropertyAnimation(self.tabs_effect, b"opacity", self)
        self.tabs_animation.setDuration(240)
        self.tabs_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        root.addWidget(self.tabs, 1)

        # Discover tab
        discover = QWidget()
        droot = QVBoxLayout(discover)
        search_card, search_l = card("Find music", "Catalog search returns public metadata. yt-dlp matches supported public audio sources; Spotify is used only for public track metadata.")
        search_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search artist, track, or album…")
        self.search.returnPressed.connect(self.search_catalog)
        self.provider = QComboBox()
        self.provider.addItems(["All catalogs", "Deezer", "Apple Music", "YouTube", "SoundCloud"])
        self.search_btn = QPushButton("Search")
        self.search_btn.setObjectName("Primary")
        self.search_btn.clicked.connect(self.search_catalog)
        search_row.addWidget(self.search, 1)
        search_row.addWidget(self.provider)
        search_row.addWidget(self.search_btn)
        search_l.addLayout(search_row)
        direct_row = QHBoxLayout()
        self.spotify_url = QLineEdit()
        self.spotify_url.setPlaceholderText("Or paste a Spotify track, album, or playlist URL…")
        self.spotify_download_btn = QPushButton("Download collection")
        self.spotify_download_btn.clicked.connect(self.download_spotify_url)
        direct_row.addWidget(self.spotify_url, 1)
        direct_row.addWidget(self.spotify_download_btn)
        search_l.addLayout(direct_row)
        droot.addWidget(search_card)
        result_card, result_l = card("Search results", "Select a result to download a tagged audio file using yt-dlp.")
        self.result_list = QListWidget()
        self.result_list.setMinimumHeight(240)
        result_l.addWidget(self.result_list, 1)
        actions = QHBoxLayout()
        self.download_result_btn = QPushButton("Download selected track")
        self.download_result_btn.setObjectName("Primary")
        self.download_result_btn.clicked.connect(self.download_selected_result)
        self.open_catalog_btn = QPushButton("Open catalog page")
        self.open_catalog_btn.clicked.connect(self.open_selected_catalog)
        self.preview_result_btn = QPushButton("Preview")
        self.preview_result_btn.clicked.connect(self.preview_selected_result)
        actions.addWidget(self.download_result_btn)
        actions.addWidget(self.open_catalog_btn)
        actions.addWidget(self.preview_result_btn)
        actions.addStretch(1)
        self.lyrics_btn = QPushButton("Find lyrics")
        self.lyrics_btn.clicked.connect(self.find_selected_lyrics)
        actions.addWidget(self.lyrics_btn)
        result_l.addLayout(actions)
        self.lyrics_view = QPlainTextEdit()
        self.lyrics_view.setReadOnly(True)
        self.lyrics_view.setPlaceholderText("Lyrics from LRCLIB will appear here when available.")
        self.lyrics_view.setMaximumHeight(150)
        result_l.addWidget(self.lyrics_view)
        self.search_status = QLabel("Search Deezer, Apple Music, YouTube, and SoundCloud, or paste a Spotify URL.")
        self.search_status.setObjectName("Muted")
        result_l.addWidget(self.search_status)
        droot.addWidget(result_card, 1)
        self.tabs.addTab(discover, "Discover")

        # Local library tab
        library_page = QWidget()
        lroot = QVBoxLayout(library_page)
        library_card, library_l = card("Your audio library", "Scans the configured output folder for local audio files. Open files with your system's default player.")
        lib_toolbar = QHBoxLayout()
        self.library_count = QLabel("No library scan yet")
        self.library_count.setObjectName("Muted")
        refresh_library = QPushButton("Refresh library")
        refresh_library.clicked.connect(self.refresh_library)
        open_audio = QPushButton("Open selected")
        open_audio.clicked.connect(self.open_selected_library_file)
        lib_toolbar.addWidget(self.library_count, 1)
        lib_toolbar.addWidget(refresh_library)
        lib_toolbar.addWidget(open_audio)
        library_l.addLayout(lib_toolbar)
        self.library_list = QListWidget()
        self.library_list.itemDoubleClicked.connect(lambda _item: self.play_selected_library_file())
        library_l.addWidget(self.library_list, 1)
        player_row = QHBoxLayout()
        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(0.75)
        self.player.setAudioOutput(self.audio_output)
        self.play_button = QPushButton("▶ Play")
        self.play_button.clicked.connect(self.toggle_playback)
        stop_button = QPushButton("■ Stop")
        stop_button.clicked.connect(self.player.stop)
        self.position_label = QLabel("0:00 / 0:00")
        self.position_label.setObjectName("Muted")
        self.seek_slider = QSlider(Qt.Horizontal)
        self.seek_slider.setRange(0, 0)
        self.seek_slider.sliderMoved.connect(self.player.setPosition)
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(75)
        self.volume_slider.setMaximumWidth(100)
        self.volume_slider.valueChanged.connect(lambda value: self.audio_output.setVolume(value / 100))
        self.player.playbackStateChanged.connect(self.update_play_button)
        self.player.positionChanged.connect(self.update_player_position)
        self.player.durationChanged.connect(self.update_player_duration)
        self.player.errorOccurred.connect(lambda _error, message: self.position_label.setText(message or "Playback error"))
        player_row.addWidget(self.play_button)
        player_row.addWidget(stop_button)
        player_row.addWidget(self.position_label)
        player_row.addWidget(self.seek_slider, 1)
        player_row.addWidget(QLabel("Volume"))
        player_row.addWidget(self.volume_slider)
        library_l.addLayout(player_row)
        lroot.addWidget(library_card, 1)
        self.tabs.addTab(library_page, "Library")

        # Local playlists tab
        playlists_page = QWidget()
        proot = QVBoxLayout(playlists_page)
        playlist_card, playlist_l = card("Playlists", "Create local playlists that reference audio files already on this device. Playlist changes are saved in your local application settings.")
        playlist_toolbar = QHBoxLayout()
        self.playlist_select = QComboBox()
        self.playlist_select.currentTextChanged.connect(self.refresh_playlist_tracks)
        create_playlist = QPushButton("New playlist")
        create_playlist.clicked.connect(self.create_playlist)
        add_to_playlist = QPushButton("Add library track")
        add_to_playlist.clicked.connect(self.add_library_track_to_playlist)
        playlist_toolbar.addWidget(self.playlist_select, 1)
        playlist_toolbar.addWidget(create_playlist)
        playlist_toolbar.addWidget(add_to_playlist)
        export_playlist = QPushButton("Export .m3u8")
        export_playlist.clicked.connect(self.export_playlist)
        import_playlist = QPushButton("Import .m3u8")
        import_playlist.clicked.connect(self.import_playlist)
        playlist_toolbar.addWidget(export_playlist)
        playlist_toolbar.addWidget(import_playlist)
        playlist_l.addLayout(playlist_toolbar)
        self.playlist_tracks = QListWidget()
        playlist_l.addWidget(self.playlist_tracks, 1)
        pl_actions = QHBoxLayout()
        play_track = QPushButton("Open selected track")
        play_track.clicked.connect(self.open_selected_playlist_track)
        remove_track = QPushButton("Remove from playlist")
        remove_track.clicked.connect(self.remove_playlist_track)
        pl_actions.addWidget(play_track)
        pl_actions.addWidget(remove_track)
        pl_actions.addStretch(1)
        playlist_l.addLayout(pl_actions)
        proot.addWidget(playlist_card, 1)
        self.tabs.addTab(playlists_page, "Playlists")
        self.refresh_playlist_names()
        self.refresh_library()

    def set_section(self, name: str):
        index = {"Music": 0, "Discover": 0, "Library": 1, "Playlists": 2}.get(name, 0)
        if self.tabs.currentIndex() != index:
            self.tabs_animation.stop()
            self.tabs_effect.setOpacity(0.55)
            self.tabs.setCurrentIndex(index)
            self.tabs_animation.setStartValue(0.55)
            self.tabs_animation.setEndValue(1.0)
            self.tabs_animation.start()
        for section, button in self.section_buttons.items():
            button.setChecked(section == ("Discover" if index == 0 else "Library" if index == 1 else "Playlists"))
        if name == "Library":
            self.refresh_library()
        elif name == "Playlists":
            self.refresh_playlist_names()

    def search_catalog(self):
        query = self.search.text().strip()
        if not query:
            QMessageBox.information(self, "Search required", "Enter an artist, track, or album to search.")
            return
        if self.search_worker is not None and self.search_worker.isRunning():
            return
        provider = self.provider.currentText()
        self.search_btn.setEnabled(False)
        self.search_status.setText("Searching public music catalogs…")
        self.search_worker = CatalogSearchWorker(query, provider, self)
        self.search_worker.completed.connect(self.search_completed)
        self.search_worker.failed.connect(self.search_failed)
        self.search_worker.finished.connect(lambda: self.search_btn.setEnabled(True))
        self.search_worker.start()

    def search_completed(self, results):
        self.results = list(results)
        self.result_list.clear()
        for row in self.results:
            duration = row.get("duration")
            duration_text = f"{int(duration) // 60}:{int(duration) % 60:02d}" if isinstance(duration, (int, float)) else ""
            item = QListWidgetItem(f"{row.get('title', 'Track')}  —  {row.get('artist', 'Unknown artist')}\n{row.get('album', '')}  ·  {row.get('provider', '')}  ·  {duration_text}")
            item.setData(Qt.UserRole, row)
            self.result_list.addItem(item)
        self.search_status.setText(f"{len(self.results)} result(s). Select a track to find and download a matching audio source.")
        if not self.results:
            self.search_status.setText("No catalog results. Try a different query or paste a Spotify URL.")

    def search_failed(self, message):
        self.search_status.setText(message)
        QMessageBox.warning(self, "Music search failed", message)

    def download_selected_result(self):
        item = self.result_list.currentItem()
        row = item.data(Qt.UserRole) if item else None
        if not row:
            QMessageBox.information(self, "Select a track", "Choose a search result first.")
            return
        query = row.get("query") or f"{row.get('artist', '')} - {row.get('title', '')}"
        self.main.add_music_tasks([row])
        self.main.navigate("Queue")

    def download_spotify_url(self):
        url = self.spotify_url.text().strip()
        if not url:
            self.spotify_url.setFocus()
            return
        if self.search_worker is not None and self.search_worker.isRunning():
            QMessageBox.information(self, "Please wait", "The current search is still running.")
            return
        if getattr(self, "spotify_worker", None) is not None and self.spotify_worker.isRunning():
            return
        self.spotify_download_btn.setEnabled(False)
        self.spotify_download_btn.setText("Resolving link…")
        self.search_status.setText("Reading public Spotify embed metadata — no API token required.")
        self.spotify_worker = SpotifyResolveWorker(url, self)
        self.spotify_worker.completed.connect(self.spotify_resolved)
        self.spotify_worker.failed.connect(self.spotify_resolve_failed)
        self.spotify_worker.finished.connect(lambda: (self.spotify_download_btn.setEnabled(True), self.spotify_download_btn.setText("Download collection")))
        self.spotify_worker.start()

    def spotify_resolved(self, collection):
        tracks = collection.get("tracks") or []
        tracks = [row for row in tracks if row.get("query", "").strip()]
        if not tracks:
            self.spotify_resolve_failed("No downloadable tracks were found in this public Spotify collection.")
            return
        self.search_status.setText(f"Resolved “{collection.get('name', 'Spotify collection')}” · {len(tracks)} track(s). Adding them to the sequential audio queue…")
        self.main.add_music_tasks(tracks)
        if collection.get("limited"):
            self.search_status.setText(self.search_status.text() + " Spotify's public embed exposed only the first 100 tracks.")
        self.main.navigate("Queue")

    def spotify_resolve_failed(self, message):
        self.search_status.setText(message)
        QMessageBox.warning(self, "Spotify link could not be resolved", message)


    def preview_selected_result(self):
        item = self.result_list.currentItem()
        row = item.data(Qt.UserRole) if item else None
        preview = row.get("preview") if row else ""
        if not preview:
            QMessageBox.information(self, "Preview unavailable", "This catalog result does not provide a playable preview.")
            return
        self.player.setSource(QUrl(preview))
        self.player.play()
        self.tabs.setCurrentIndex(1)
        self.position_label.setText(f"Preview · {row.get('title', 'Track')}")

    def open_selected_catalog(self):
        item = self.result_list.currentItem()
        row = item.data(Qt.UserRole) if item else None
        if row and row.get("url"):
            QDesktopServices.openUrl(QUrl(row["url"]))

    def refresh_library(self):
        self.library = scan_audio_library(self.main.settings.get("output_dir", str(Path.home() / "Downloads")))
        self.library_list.clear()
        for row in self.library:
            item = QListWidgetItem(f"{row['title']}\n{row['path']}")
            item.setData(Qt.UserRole, row["path"])
            self.library_list.addItem(item)
        self.library_count.setText(f"{len(self.library)} audio file(s) · {self.main.settings.get('output_dir', '')}")


    @staticmethod
    def _clock(milliseconds: int) -> str:
        seconds = max(0, int(milliseconds / 1000))
        return f"{seconds // 60}:{seconds % 60:02d}"

    def toggle_playback(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            return
        current = self.player.source().toLocalFile()
        item = self.library_list.currentItem()
        selected = item.data(Qt.UserRole) if item else ""
        if selected and selected != current:
            self.player.setSource(QUrl.fromLocalFile(selected))
        if not self.player.source().isEmpty():
            self.player.play()
        elif selected:
            self.player.setSource(QUrl.fromLocalFile(selected))
            self.player.play()
        else:
            QMessageBox.information(self, "Select audio", "Select an audio file in the library first.")

    def update_play_button(self, state):
        self.play_button.setText("Ⅱ Pause" if state == QMediaPlayer.PlaybackState.PlayingState else "▶ Play")

    def update_player_position(self, position: int):
        if not self.seek_slider.isSliderDown():
            self.seek_slider.setValue(position)
        self.position_label.setText(f"{self._clock(position)} / {self._clock(self.player.duration())}")

    def update_player_duration(self, duration: int):
        self.seek_slider.setRange(0, max(0, duration))
        self.position_label.setText(f"{self._clock(self.player.position())} / {self._clock(duration)}")

    def open_selected_library_file(self):
        item = self.library_list.currentItem()
        path = item.data(Qt.UserRole) if item else None
        if path and Path(path).exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        elif path:
            QMessageBox.warning(self, "File not found", "This file may have been moved or deleted. Refresh the library.")

    def refresh_playlist_names(self):
        current = self.playlist_select.currentText() if hasattr(self, "playlist_select") else ""
        self.playlists = load_music_playlists()
        self.playlist_select.blockSignals(True)
        self.playlist_select.clear()
        self.playlist_select.addItems(sorted(self.playlists.keys(), key=str.casefold))
        if current in self.playlists:
            self.playlist_select.setCurrentText(current)
        self.playlist_select.blockSignals(False)
        self.refresh_playlist_tracks()

    def create_playlist(self):
        name, ok = QInputDialog.getText(self, "Create playlist", "Playlist name:")
        name = name.strip()
        if not ok or not name:
            return
        if name in self.playlists:
            QMessageBox.information(self, "Playlist exists", "Choose a different playlist name.")
            return
        self.playlists[name] = []
        save_music_playlists(self.playlists)
        self.refresh_playlist_names()
        self.playlist_select.setCurrentText(name)

    def add_library_track_to_playlist(self):
        playlist = self.playlist_select.currentText()
        item = self.library_list.currentItem()
        path = item.data(Qt.UserRole) if item else None
        if not playlist:
            QMessageBox.information(self, "Create a playlist", "Create a playlist first.")
            return
        if not path:
            QMessageBox.information(self, "Select a library track", "Open the Library tab and select an audio file first.")
            return
        tracks = self.playlists.setdefault(playlist, [])
        if path not in tracks:
            tracks.append(path)
            save_music_playlists(self.playlists)
        self.refresh_playlist_tracks()

    def refresh_playlist_tracks(self):
        if not hasattr(self, "playlist_tracks"):
            return
        name = self.playlist_select.currentText()
        self.playlist_tracks.clear()
        for path in self.playlists.get(name, []):
            item = QListWidgetItem(f"{Path(path).stem}\n{path}")
            item.setData(Qt.UserRole, path)
            if not Path(path).exists():
                item.setForeground(Qt.gray)
            self.playlist_tracks.addItem(item)

    def open_selected_playlist_track(self):
        item = self.playlist_tracks.currentItem()
        path = item.data(Qt.UserRole) if item else None
        if path and Path(path).exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        elif path:
            QMessageBox.warning(self, "File not found", "This track is no longer in the library.")


    def find_selected_lyrics(self):
        item = self.result_list.currentItem()
        row = item.data(Qt.UserRole) if item else None
        if not row:
            QMessageBox.information(self, "Select a track", "Choose a track before looking up lyrics.")
            return
        if self.lyrics_worker is not None and self.lyrics_worker.isRunning():
            return
        self.lyrics_view.setPlainText("Looking up lyrics…")
        self.lyrics_btn.setEnabled(False)
        self.lyrics_worker = LyricsSearchWorker(row.get("title", ""), row.get("artist", ""), self)
        self.lyrics_worker.completed.connect(self.lyrics_view.setPlainText)
        self.lyrics_worker.failed.connect(self.lyrics_view.setPlainText)
        self.lyrics_worker.finished.connect(lambda: self.lyrics_btn.setEnabled(True))
        self.lyrics_worker.start()

    def export_playlist(self):
        name = self.playlist_select.currentText()
        if not name:
            QMessageBox.information(self, "Select a playlist", "Create or select a playlist first.")
            return
        target, _ = QFileDialog.getSaveFileName(self, "Export playlist", str(Path.home() / f"{name}.m3u8"), "M3U8 playlists (*.m3u8)")
        if not target:
            return
        lines = ["#EXTM3U"]
        for path in self.playlists.get(name, []):
            lines.extend([f"#EXTINF:-1,{Path(path).stem}", path])
        try:
            Path(target).write_text("\n".join(lines) + "\n", encoding="utf-8")
            QMessageBox.information(self, "Playlist exported", f"Exported {len(self.playlists.get(name, []))} track(s).")
        except OSError as exc:
            QMessageBox.warning(self, "Export failed", str(exc))

    def import_playlist(self):
        source, _ = QFileDialog.getOpenFileName(self, "Import playlist", str(Path.home()), "M3U playlists (*.m3u *.m3u8);;All files (*)")
        if not source:
            return
        try:
            lines = Path(source).read_text(encoding="utf-8-sig").splitlines()
        except OSError as exc:
            QMessageBox.warning(self, "Import failed", str(exc))
            return
        root = Path(source).expanduser().parent
        paths = []
        for line in lines:
            value = line.strip()
            if not value or value.startswith("#"):
                continue
            path = Path(value).expanduser()
            if not path.is_absolute():
                path = root / path
            paths.append(str(path.resolve()))
        name = Path(source).stem
        base, index = name, 2
        while name in self.playlists:
            name = f"{base} ({index})"
            index += 1
        self.playlists[name] = paths
        save_music_playlists(self.playlists)
        self.refresh_playlist_names()
        self.playlist_select.setCurrentText(name)
        QMessageBox.information(self, "Playlist imported", f"Imported {len(paths)} track path(s). Missing files remain listed so you can locate them later.")

    def remove_playlist_track(self):
        name = self.playlist_select.currentText()
        item = self.playlist_tracks.currentItem()
        path = item.data(Qt.UserRole) if item else None
        if name and path:
            self.playlists[name] = [value for value in self.playlists.get(name, []) if value != path]
            save_music_playlists(self.playlists)
            self.refresh_playlist_tracks()


class SettingsPage(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        self._tool_status_worker = None
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(18)
        root.addLayout(page_heading("Settings", "Choose folders and local executable paths. Tool locations are saved on this device only."))
        paths, pl = card("Output & tools", "Universal Media Studio does not upload your media URLs or files to a processing server.")
        form = QGridLayout()
        self.output_dir = QLineEdit(self.main.settings["output_dir"])
        self.ffmpeg = QLineEdit(self.main.settings.get("ffmpeg_path", ""))
        self.ffprobe = QLineEdit(self.main.settings.get("ffprobe_path", ""))
        self._path_row(form, 0, "Default output folder", self.output_dir, self.pick_output)
        self._path_row(form, 1, "FFmpeg executable (optional if on PATH)", self.ffmpeg, lambda: self.pick_executable(self.ffmpeg))
        self._path_row(form, 2, "FFprobe executable (optional if on PATH)", self.ffprobe, lambda: self.pick_executable(self.ffprobe))
        pl.addLayout(form)
        root.addWidget(paths)

        limits, ll = card("Transfer limits", "These settings tune yt-dlp retries and HLS/DASH fragment concurrency.")
        row = QHBoxLayout()
        self.retries = QSpinBox()
        self.retries.setRange(0, 20)
        self.retries.setValue(int(self.main.settings.get("max_retries", 3)))
        self.fragments = QSpinBox()
        self.fragments.setRange(1, 16)
        self.fragments.setValue(int(self.main.settings.get("fragment_concurrency", 4)))
        row.addWidget(QLabel("Retries"))
        row.addWidget(self.retries)
        row.addSpacing(18)
        row.addWidget(QLabel("Concurrent fragments"))
        row.addWidget(self.fragments)
        row.addStretch(1)
        ll.addLayout(row)
        root.addWidget(limits)

        status_card, sl = card("Detected tools", "FFmpeg and ffprobe are optional for direct original-file downloads; conversion and stream merging require FFmpeg.")
        self.tools_status = QLabel()
        self.tools_status.setWordWrap(True)
        self.tools_status.setObjectName("Muted")
        sl.addWidget(self.tools_status)
        refresh = QPushButton("Refresh tool status")
        refresh.clicked.connect(self.refresh_tool_status)
        sl.addWidget(refresh, 0, Qt.AlignLeft)
        root.addWidget(status_card)
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        save = QPushButton("Save settings")
        save.setObjectName("Primary")
        save.clicked.connect(self.save)
        bottom.addWidget(save)
        root.addLayout(bottom)
        self.refresh_tool_status()

    @staticmethod
    def _path_row(grid, row, title, edit, callback):
        label = QLabel(title)
        label.setObjectName("Muted")
        grid.addWidget(label, row, 0)
        grid.addWidget(edit, row, 1)
        button = QPushButton("Browse…")
        button.clicked.connect(callback)
        grid.addWidget(button, row, 2)

    def pick_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Select output directory", self.output_dir.text())
        if folder:
            self.output_dir.setText(folder)

    def pick_executable(self, edit):
        path, _ = QFileDialog.getOpenFileName(self, "Select executable", str(Path.home()), "Executable files (*)")
        if path:
            edit.setText(path)

    def refresh_tool_status(self):
        if self._tool_status_worker and self._tool_status_worker.isRunning():
            self.tools_status.setText("A tool check is already running…")
            return
        ffmpeg = self.ffmpeg.text().strip() or None
        ffprobe = self.ffprobe.text().strip() or None
        self.tools_status.setText("Checking local media tools…")
        self._tool_status_worker = FunctionWorker(
            lambda: tool_status(ffmpeg, ffprobe),
            self,
        )
        self._tool_status_worker.done.connect(self._render_tool_status)
        self._tool_status_worker.failed.connect(self._tool_status_failed)
        self._tool_status_worker.start()

    def _render_tool_status(self, status):
        y = status.get("yt_dlp") or "Missing"
        ff = status.get("ffmpeg_version") or "Missing — install FFmpeg and add it to PATH"
        fp = status.get("ffprobe") or "Missing — output checks will be limited"
        encoders = set(status.get("encoders", []))
        relevant = [
            x for x in ["mpeg4", "libx264", "h264_nvenc", "h264_qsv", "h264_amf", "libx265", "hevc_nvenc", "hevc_qsv", "hevc_amf", "libsvtav1", "libaom-av1", "av1_nvenc", "libvpx-vp9", "libvpx", "libmp3lame", "libopus", "libvorbis", "flac", "aac"]
            if x in encoders
        ]
        encoder_text = ", ".join(relevant) if relevant else "Not detected / FFmpeg missing"
        self.tools_status.setText(
            f"yt-dlp: {y}\nFFmpeg: {ff}\nFFprobe: {fp}\n"
            f"Music matching: yt-dlp (no Spotify API token)\n"
            f"Detected common encoders: {encoder_text}"
        )

    def _tool_status_failed(self, message):
        self.tools_status.setText(f"Could not check local tools: {message}")

    def save(self):
        self.main.set_output_folder(self.output_dir.text().strip() or str(DEFAULT_OUTPUT))
        self.main.settings["ffmpeg_path"] = self.ffmpeg.text().strip()
        self.main.settings["ffprobe_path"] = self.ffprobe.text().strip()
        self.main.settings["max_retries"] = self.retries.value()
        self.main.settings["fragment_concurrency"] = self.fragments.value()
        self.main.save_settings()
        # Start tool discovery first so the sidebar can subscribe to its result
        # instead of blocking the GUI with a second synchronous FFmpeg probe.
        self.refresh_tool_status()
        self.main.refresh_global_status()
        QMessageBox.information(self, "Settings saved", "Your settings have been saved locally.")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        self.presets = merged_presets(self.settings.get("custom_presets", {}))
        self.tasks: list[dict] = []
        self.active_task_id = None
        self.active_worker = None
        self._pending_completion = None
        self._close_after_worker = False
        self._global_status_waiting = False
        self.setWindowTitle("Universal Media Studio")
        self.resize(1180, 800)
        self.setMinimumSize(900, 620)
        self.setStyleSheet(APP_STYLE)

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.sidebar = QWidget()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(204)
        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(15, 12, 15, 16)
        side.setSpacing(7)
        brand = QLabel("UMS  /  MEDIA")
        brand.setObjectName("Brand")
        side.addWidget(brand)
        eyebrow = QLabel("WORKSPACE")
        eyebrow.setObjectName("Eyebrow")
        side.addWidget(eyebrow)
        self.nav_buttons = {}
        for name, icon in [("Downloader", "↓"), ("Music", "♫"), ("Library", "▤"), ("Playlists", "≡"), ("Converter", "⇄"), ("Queue", "▣"), ("Settings", "⚙")]:
            btn = QPushButton(f"{icon}    {name}")
            btn.setObjectName("Nav")
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked=False, page=name: self.navigate(page))
            side.addWidget(btn)
            self.nav_buttons[name] = btn
        side.addStretch(1)
        self.global_status = QLabel("Checking local tools…")
        self.global_status.setWordWrap(True)
        self.global_status.setObjectName("Muted")
        side.addWidget(QLabel("LOCAL ENGINE"))
        side.addWidget(self.global_status)
        version = QLabel("Universal Media Studio  ·  1.0.0")
        version.setObjectName("Muted")
        version.setStyleSheet("font-size: 8pt;")
        side.addWidget(version)
        root.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        self.download_page = DownloadPage(self)
        self.converter_page = ConverterPage(self)
        self.queue_page = QueuePage(self)
        self.settings_page = SettingsPage(self)
        self.music_page = MusicHubPage(self)
        self.pages = {
            "Downloader": self.download_page,
            "Converter": self.converter_page,
            "Music": self.music_page,
            "Library": self.music_page,
            "Playlists": self.music_page,
            "Queue": self.queue_page,
            "Settings": self.settings_page,
        }
        page_scrolls = {}
        for page in dict.fromkeys(self.pages.values()):
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.NoFrame)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            scroll.setAlignment(Qt.AlignTop)
            scroll.setWidget(page)
            self.stack.addWidget(scroll)
            page_scrolls[id(page)] = scroll
        self.pages = {
            name: page_scrolls[id(page)]
            for name, page in self.pages.items()
        }
        root.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        menu = self.menuBar()
        file_menu = menu.addMenu("File")
        open_output = QAction("Open output folder", self)
        open_output.triggered.connect(self.open_output_folder)
        file_menu.addAction(open_output)
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)
        help_menu = menu.addMenu("Help")
        about_action = QAction("About", self)
        about_action.triggered.connect(self.about)
        help_menu.addAction(about_action)

        self.navigate("Downloader")
        self.refresh_global_status()

    def set_output_folder(self, folder):
        self.settings["output_dir"] = str(Path(folder).expanduser())
        self.save_settings()
        if hasattr(self, "download_page"):
            self.download_page.output_label.setText(f"Save to: {self.settings['output_dir']}")
        if hasattr(self, "converter_page"):
            self.converter_page.dest.setText(f"Save to: {self.settings['output_dir']}")
        if hasattr(self, "settings_page"):
            self.settings_page.output_dir.setText(self.settings["output_dir"])
        if hasattr(self, "music_page"):
            self.music_page.refresh_library()

    def save_settings(self):
        save_settings(self.settings)
        self.presets = merged_presets(self.settings.get("custom_presets", {}))

    def refresh_presets(self):
        self.presets = merged_presets(self.settings.get("custom_presets", {}))
        for page, combo in [(self.download_page, self.download_page.preset), (self.converter_page, self.converter_page.preset)]:
            current = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(list(self.presets.keys()))
            if current in self.presets:
                combo.setCurrentText(current)
            combo.blockSignals(False)

    def refresh_global_status(self):
        worker = getattr(self.settings_page, "_tool_status_worker", None)
        if worker and worker.isRunning():
            if not self._global_status_waiting:
                self._global_status_waiting = True
                worker.done.connect(self._update_global_status)
                worker.failed.connect(self._global_status_failed)
            return
        try:
            status = tool_status(
                self.settings.get("ffmpeg_path") or None,
                self.settings.get("ffprobe_path") or None,
            )
        except Exception as exc:
            self._global_status_failed(str(exc))
            return
        self._update_global_status(status)

    def _update_global_status(self, status):
        self._global_status_waiting = False
        y = "yt-dlp ready" if status.get("yt_dlp") else "yt-dlp missing"
        f = "FFmpeg ready" if status.get("ffmpeg") else "FFmpeg missing"
        self.global_status.setText(f"{y}\n{f}")

    def _global_status_failed(self, message):
        self._global_status_waiting = False
        self.global_status.setText(f"Tool check unavailable\n{message}")

    def navigate(self, name):
        self.stack.setCurrentWidget(self.pages[name])
        if name in {"Music", "Library", "Playlists"} and hasattr(self, "music_page"):
            self.music_page.set_section(name)
        for key, btn in self.nav_buttons.items():
            btn.setChecked(key == name)

    def add_download_tasks(self, urls: list[str], options: dict, analyzed_info=None):
        analyzed_info = analyzed_info if isinstance(analyzed_info, dict) else {}
        for index, url in enumerate(urls):
            media_info = analyzed_info if index == 0 else {}
            task_id = uuid.uuid4().hex[:12]
            task = {
                "id": task_id, "kind": "download", "url": url,
                "name": str(media_info.get("title") or url[:92]),
                "thumbnail": str(media_info.get("thumbnail") or ""),
                "uploader": str(media_info.get("uploader") or media_info.get("channel") or ""),
                "duration": media_info.get("duration"),
                "view_count": media_info.get("view_count"),
                "upload_date": str(media_info.get("upload_date") or ""),
                "options": dict(options), "output_dir": self.settings["output_dir"],
                "status": "Queued", "progress": 0, "detail": "Waiting in queue", "output": "",
            }
            self.tasks.append(task)
        self.queue_page.refresh(self.tasks, self.active_task_id)
        self.queue_page.log_view.appendPlainText(f"Added {len(urls)} download task(s) to queue.")
        self.process_next()

    def add_music_tasks(self, tracks: list[dict]):
        count = 0
        for track in tracks:
            if isinstance(track, str):
                query = track.strip()
                metadata = {}
            else:
                metadata = dict(track or {})
                query = str(metadata.get("query") or f"{metadata.get('artist', '')} - {metadata.get('title', '')}").strip(" -")
            if not query:
                continue
            task_id = uuid.uuid4().hex[:12]
            task = {
                "id": task_id, "kind": "music", "query": query, "music_track": metadata,
                "name": query[:92], "options": {}, "output_dir": self.settings["output_dir"],
                "status": "Queued", "progress": 0, "detail": "Waiting in music queue", "output": "",
            }
            self.tasks.append(task)
            count += 1
        self.queue_page.refresh(self.tasks, self.active_task_id)
        self.queue_page.log_view.appendPlainText(f"Added {count} music download task(s) to queue.")
        self.process_next()

    def add_conversion_tasks(self, files: list[str], options: dict):
        for file in files:
            task_id = uuid.uuid4().hex[:12]
            task = {
                "id": task_id, "kind": "convert", "source": file, "name": Path(file).name,
                "options": dict(options), "output_dir": self.settings["output_dir"],
                "status": "Queued", "progress": 0, "detail": "Waiting in queue", "output": "",
            }
            self.tasks.append(task)
        self.queue_page.refresh(self.tasks, self.active_task_id)
        self.queue_page.log_view.appendPlainText(f"Added {len(files)} conversion task(s) to queue.")
        self.process_next()

    def process_next(self):
        if self.active_worker is not None:
            return
        task = next((t for t in self.tasks if t["status"] == "Queued"), None)
        if not task:
            self.queue_page.refresh(self.tasks, self.active_task_id)
            return
        task["status"] = "Starting"
        task["detail"] = "Launching local engine…"
        self.active_task_id = task["id"]
        self.queue_page.refresh(self.tasks, self.active_task_id)
        self.active_worker = MediaTaskWorker(task, self.settings, self)
        self.active_worker.progress.connect(self.on_progress)
        self.active_worker.log.connect(self.on_log)
        self.active_worker.completed.connect(self.on_task_completed)
        self.active_worker.finished.connect(self.on_worker_finished)
        self.active_worker.start()

    def on_progress(self, task_id, percent, label):
        task = self.find_task(task_id)
        if task:
            task["progress"] = max(0, min(100, int(percent)))
            task["detail"] = label
            if task["status"] in {"Starting", "Queued"}:
                task["status"] = "Running"
            self.queue_page.refresh(self.tasks, self.active_task_id)

    def on_log(self, task_id, message):
        self.queue_page.append_log(task_id, message)

    def on_task_completed(self, task_id, status, outputs, error):
        task = self.find_task(task_id)
        if task:
            task["status"] = status
            task["progress"] = 100 if status == "Completed" else task.get("progress", 0)
            task["detail"] = error or (f"{len(outputs)} output file(s)" if outputs else status)
            task["output"] = "; ".join(outputs[:2]) + (f" (+{len(outputs)-2})" if len(outputs) > 2 else "")
            if outputs:
                task["outputs"] = outputs
        self._pending_completion = (task_id, status, error)
        self.queue_page.refresh(self.tasks, self.active_task_id)
        if status == "Failed":
            self.queue_page.append_log(task_id, f"FAILED: {error}")
        elif status == "Completed":
            self.queue_page.append_log(task_id, "Task completed successfully.")
        else:
            self.queue_page.append_log(task_id, error or "Task cancelled.")

    def on_worker_finished(self):
        self.active_worker = None
        self.active_task_id = None
        self._pending_completion = None
        self.queue_page.refresh(self.tasks, self.active_task_id)
        if self._close_after_worker:
            self._maybe_close_after_background()
            return
        self.process_next()

    def find_task(self, task_id):
        return next((t for t in self.tasks if t["id"] == task_id), None)

    def cancel_task(self, task_id):
        task = self.find_task(task_id)
        if not task:
            return
        if self.active_task_id == task_id and self.active_worker:
            task["detail"] = "Cancelling…"
            self.active_worker.cancel()
            self.queue_page.refresh(self.tasks, self.active_task_id)
        elif task["status"] == "Queued":
            task["status"] = "Cancelled"
            task["detail"] = "Cancelled before starting"
            self.queue_page.refresh(self.tasks, self.active_task_id)

    def retry_task(self, task_id):
        task = self.find_task(task_id)
        if task and task["status"] in {"Failed", "Cancelled"}:
            task["status"] = "Queued"
            task["progress"] = 0
            task["detail"] = "Queued for retry"
            task["output"] = ""
            task.pop("outputs", None)
            self.queue_page.refresh(self.tasks, self.active_task_id)
            self.process_next()

    def move_task(self, task_id, direction):
        queued_indices = [i for i, task in enumerate(self.tasks) if task.get("status") == "Queued"]
        try:
            position = queued_indices.index(next(i for i, task in enumerate(self.tasks) if task["id"] == task_id))
        except (ValueError, StopIteration):
            return
        target_position = position + int(direction)
        if not (0 <= target_position < len(queued_indices)):
            return
        first, second = queued_indices[position], queued_indices[target_position]
        self.tasks[first], self.tasks[second] = self.tasks[second], self.tasks[first]
        self.queue_page.refresh(self.tasks, self.active_task_id)

    def remove_task(self, task_id):
        task = self.find_task(task_id)
        if not task or task_id == self.active_task_id:
            return
        self.tasks = [t for t in self.tasks if t["id"] != task_id]
        self.queue_page.refresh(self.tasks, self.active_task_id)

    def clear_completed(self):
        self.tasks = [t for t in self.tasks if t["status"] not in {"Completed", "Cancelled"}]
        self.queue_page.refresh(self.tasks, self.active_task_id)

    def open_output_folder(self):
        path = Path(self.settings["output_dir"]).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        import os, subprocess, sys
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(path))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as exc:
            QMessageBox.warning(self, "Could not open folder", str(exc))

    def about(self):
        QMessageBox.about(self, "About Universal Media Studio",
                          "Universal Media Studio 1.0.0\n\nA local-first yt-dlp and FFmpeg GUI for authorized media downloads and conversions.\n\nNo telemetry or remote processing is included. Website availability and output codecs depend on the source and your installed tool builds.")

    def _running_background_workers(self):
        """Return every live QThread owned by the legacy UI."""
        candidates = [
            self.active_worker,
            getattr(self.download_page, "analysis_worker", None),
            getattr(self.music_page, "search_worker", None),
            getattr(self.music_page, "lyrics_worker", None),
            getattr(self.music_page, "spotify_worker", None),
            getattr(self.settings_page, "_tool_status_worker", None),
        ]
        running = []
        seen = set()
        for worker in candidates:
            if worker is None or id(worker) in seen:
                continue
            seen.add(id(worker))
            try:
                if worker.isRunning():
                    running.append(worker)
            except RuntimeError:
                # A completed Qt worker may already have been deleted.
                continue
        return running

    def _maybe_close_after_background(self):
        if not self._close_after_worker:
            return
        if not self._running_background_workers():
            self._close_after_worker = False
            self.close()

    def closeEvent(self, event):
        # Do not destroy a QThread while it is running. Media work can be
        # cancelled; short catalog/analysis/tool workers are allowed to finish.
        if self._close_after_worker:
            event.ignore()
            return
        running_workers = self._running_background_workers()
        media_running = bool(self.active_worker and self.active_worker.isRunning())
        if media_running:
            reply = QMessageBox.question(
                self, "Stop active task?",
                "A media task is still running. Cancel it and exit?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                event.ignore()
                return
            self._close_after_worker = True
            self.active_worker.cancel()
        elif running_workers:
            self._close_after_worker = True

        if self._close_after_worker:
            # Connect all currently running workers. The shared handler checks
            # the full set, so whichever one finishes last closes the window.
            for worker in running_workers:
                try:
                    worker.finished.connect(self._maybe_close_after_background)
                except RuntimeError:
                    continue
            self._maybe_close_after_background()
            event.ignore()
        else:
            event.accept()
