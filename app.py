"""Launch the QML desktop interface for Universal Media Studio."""
import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication

from ums.qml_bridge import AppBridge


def main():
    # The native Windows style ignores custom backgrounds/handles; Basic honours them.
    QQuickStyle.setStyle("Basic")
    app = QApplication(sys.argv)
    app.setApplicationName("Universal Media Studio")
    app.setOrganizationName("Universal Media Studio")
    resource_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    font_path = resource_root / "ums" / "fonts" / "Inter-Variable.ttf"
    if font_path.is_file():
        QFontDatabase.addApplicationFont(str(font_path))
    app.setFont(QFont("Inter", 10))
    bridge = AppBridge()
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("appBridge", bridge)
    qml_file = resource_root / "ums" / "qml" / "Main.qml"
    engine.load(QUrl.fromLocalFile(str(qml_file)))
    if not engine.rootObjects():
        raise SystemExit("Could not load the Universal Media Studio QML interface.")
    app.aboutToQuit.connect(bridge.quit)
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
