from pathlib import Path
import unittest

from ums.config import APP_DIR, LOG_BACKUP_COUNT, LOG_FILE, LOG_MAX_BYTES


ROOT = Path(__file__).resolve().parents[1]


class LoggingOutputTests(unittest.TestCase):
    def test_log_file_uses_the_application_data_directory(self):
        self.assertEqual(LOG_FILE, APP_DIR / "startup.log")
        self.assertGreater(LOG_MAX_BYTES, 0)
        self.assertEqual(LOG_MAX_BYTES, 2 * 1024 * 1024)
        self.assertEqual(LOG_BACKUP_COUNT, 3)

    def test_application_logging_uses_a_bounded_rotating_handler(self):
        config = (ROOT / "ums" / "config.py").read_text(encoding="utf-8")
        self.assertIn("RotatingFileHandler", config)
        self.assertIn("maxBytes=LOG_MAX_BYTES", config)
        self.assertIn("backupCount=LOG_BACKUP_COUNT", config)
        self.assertIn('encoding="utf-8"', config)

    def test_task_output_is_written_to_the_application_log(self):
        bridge = (ROOT / "ums" / "qml_bridge.py").read_text(encoding="utf-8")
        self.assertIn('logging.getLogger("ums.tasks").info', bridge)
        self.assertIn("def readLog(self)", bridge)
        self.assertIn("def exportLog(self)", bridge)
        self.assertIn("def openLogFile(self)", bridge)
        self.assertIn("LOG_FILE.name + f\".{index}\"", bridge)

    def test_qml_settings_exposes_view_export_and_open_actions(self):
        qml = (ROOT / "ums" / "qml" / "Main.qml").read_text(encoding="utf-8")
        self.assertIn('title: "Application logs"', qml)
        self.assertIn('text: "View logs"', qml)
        self.assertIn('text: "Export log"', qml)
        self.assertIn('text: "Open file"', qml)
        self.assertIn("function onLogUpdated()", qml)
        self.assertIn("id: logDialog", qml)

    def test_log_viewer_scroll_content_has_a_bounded_viewport_width(self):
        qml = (ROOT / "ums" / "qml" / "Main.qml").read_text(encoding="utf-8")
        self.assertIn("id: logScroll", qml)
        self.assertIn("contentWidth: availableWidth", qml)
        self.assertIn("width: logScroll.availableWidth", qml)

    def test_legacy_queue_has_activity_log_export(self):
        ui = (ROOT / "ums" / "ui.py").read_text(encoding="utf-8")
        self.assertIn("Export activity log", ui)
        self.assertIn("def export_activity_log(self)", ui)
        self.assertIn("def open_application_log(self)", ui)


if __name__ == "__main__":
    unittest.main()
