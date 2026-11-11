import os
from pathlib import Path
import unittest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine


ROOT = Path(__file__).resolve().parents[1]


class AdvancedDownloaderQmlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])
        cls.engine = QQmlEngine()

    def test_advanced_panel_compiles_and_instantiates_in_qt_quick(self):
        qml_path = ROOT / "ums" / "qml" / "AdvancedDownloadPanel.qml"
        component = QQmlComponent(self.engine, QUrl.fromLocalFile(str(qml_path)))
        self.assertFalse(
            component.isError(),
            "\n".join(error.toString() for error in component.errors()),
        )
        panel = component.create()
        self.assertIsNotNone(
            panel,
            "\n".join(error.toString() for error in component.errors()),
        )
        self.assertEqual(panel.property("selectedPreset"), "Best Available Quality")
        self.assertEqual(panel.property("validationMessage"), "")
        self.assertTrue(panel.property("outputSummary"))
        panel.deleteLater()


if __name__ == "__main__":
    unittest.main()
