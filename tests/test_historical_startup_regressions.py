from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class HistoricalStartupRegressionTests(unittest.TestCase):
    def test_lyrics_dialog_does_not_use_reserved_synchronized_identifier(self):
        qml = (ROOT / "ums" / "qml" / "LyricsDialog.qml").read_text(encoding="utf-8")
        self.assertNotRegex(
            qml,
            r"\bproperty\s+(?:bool|var|string|int|real)\s+synchronized\b",
        )
        self.assertIn("lyricsSynchronized", qml)

    def test_main_qml_does_not_reference_python_path_type(self):
        qml = (ROOT / "ums" / "qml" / "Main.qml").read_text(encoding="utf-8")
        self.assertNotRegex(qml, r"\bPath\s*(?:\.|\()")

    def test_status_refresh_does_not_capture_an_undefined_request_token(self):
        bridge = (ROOT / "ums" / "qml_bridge.py").read_text(encoding="utf-8")
        start = bridge.index("    def refresh_status(")
        end = bridge.index("    def _on_status_ready(", start)
        refresh_method = bridge[start:end]
        self.assertNotIn("request_token", refresh_method)
        self.assertIn("worker.done.connect(self._on_status_ready)", refresh_method)


if __name__ == "__main__":
    unittest.main()
