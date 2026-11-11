from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ModernAdvancedDownloaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.panel = (ROOT / "ums" / "qml" / "AdvancedDownloadPanel.qml").read_text(encoding="utf-8")
        cls.main = (ROOT / "ums" / "qml" / "Main.qml").read_text(encoding="utf-8")
        cls.bridge = (ROOT / "ums" / "qml_bridge.py").read_text(encoding="utf-8")

    def test_panel_exposes_legacy_level_stream_and_encoding_controls(self):
        for token in (
            "sourceFormat", "outputContainer", "videoCodec", "audioCodec",
            "videoBitrate", "audioBitrate", "qualityValue", "encoderPreset",
            "frameRate", "frameMode", "resolution", "customScale",
            "sampleRate", "channels", "videoEncoder", "profileName",
            "codecLevel", "pixelFormat", "colorSpace", "colorRange",
            "subtitles", "automaticCaptions", "embedSubtitles",
            "preserveMetadata", "saveThumbnail",
        ):
            with self.subTest(control=token):
                self.assertIn(token, self.panel)

    def test_controls_serialize_every_legacy_advanced_option(self):
        for key in (
            "format", "container", "video_codec", "audio_codec", "video_encoder",
            "profile", "level", "pixel_format", "color_space", "color_range",
            "rate_control", "video_bitrate", "audio_bitrate", "crf",
            "encoder_preset", "fps", "fps_mode", "resolution", "custom_scale",
            "sample_rate", "channels", "write_subtitles",
            "write_automatic_subtitles", "embed_subtitles", "preserve_metadata",
            "download_thumbnail",
        ):
            with self.subTest(option=key):
                self.assertIn(key + ":", self.panel)

    def test_main_download_queue_sends_the_complete_options_payload(self):
        self.assertIn("AdvancedDownloadPanel {", self.main)
        self.assertIn("advancedDownloadPanel.options()", self.main)
        self.assertIn("bridge.enqueueDownloadWithOptions(urls[i], optionsJson)", self.main)
        self.assertNotIn("classic advanced Downloader window", self.main)

    def test_panel_provides_live_output_summary_and_validation(self):
        self.assertIn("readonly property string outputSummary", self.panel)
        self.assertIn("readonly property string validationMessage", self.panel)
        self.assertIn("readonly property string compatibilityNotice", self.panel)
        self.assertIn("root.validationMessage.length === 0", self.panel)
        self.assertIn('"CHECK YOUR SETTINGS"', self.panel)
        self.assertIn("root.outputSummary", self.panel)

    def test_queue_reports_only_items_the_bridge_accepted(self):
        self.assertIn("@Slot(str, str, result=bool)", self.bridge)
        self.assertIn("@Slot(str, result=bool)", self.bridge)
        self.assertIn("return self._enqueue_download(url, options)", self.bridge)
        self.assertIn("var added = 0", self.main)
        self.assertIn("if (accepted)", self.main)
        self.assertIn('"Nothing was added. Check the URLs and downloader settings."', self.main)

    def test_custom_preset_save_action_is_wired_to_the_bridge(self):
        self.assertIn("savePresetRequested", self.panel)
        self.assertIn("bridge.saveCustomPreset(optionsJson)", self.main)
        self.assertIn("def saveCustomPreset(self, options_json)", self.bridge)
        self.assertIn("self.presetsChanged.emit", self.bridge)

    def test_bridge_validates_payload_before_queueing(self):
        self.assertIn("def enqueueDownloadWithOptions(self, url, options_json)", self.bridge)
        self.assertIn("sanitize_download_options(options)", self.bridge)

    def test_local_converter_uses_the_same_complete_advanced_panel(self):
        self.assertIn("id: conversionAdvancedPanel", self.main)
        self.assertIn("showSourceQuality: false", self.main)
        self.assertIn("conversionAdvancedPanel.options()", self.main)
        self.assertIn("bridge.enqueueConversionWithAdvancedOptions", self.main)
        self.assertIn("@Slot(str, str, result=bool)", self.bridge)
        self.assertIn("def enqueueConversionWithAdvancedOptions(self, source, options_json)", self.bridge)
        self.assertIn("if (accepted)", self.main)
        self.assertIn("Conversion added to the queue.", self.main)


if __name__ == "__main__":
    unittest.main()
