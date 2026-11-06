"""Launch the QML desktop interface for Universal Media Studio."""
import logging
import os
import sys
from pathlib import Path

# Qt Multimedia's FFmpeg backend can emit a full codec/MFT diagnostic dump when
# QT_FFMPEG_DEBUG is inherited from a developer shell or IDE. Keep normal app
# launches quiet, but let developers opt in explicitly for troubleshooting.
if os.environ.get("UMS_KEEP_QT_FFMPEG_DEBUG") != "1":
    os.environ.pop("QT_FFMPEG_DEBUG", None)

from PySide6.QtCore import QUrl
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication, QMessageBox

def _configure_startup_logging():
    log_path = Path.home() / ".universal_media_studio" / "startup.log"
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            filename=str(log_path),
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s",
            encoding="utf-8",
            force=True,
        )
        logging.info("Starting Universal Media Studio")
        return log_path
    except Exception:
        logging.basicConfig(level=logging.INFO, force=True)
        logging.exception("Could not initialize the startup log file")
        return None


def main():
    log_path = _configure_startup_logging()
    app = None
    try:
        # The native Windows style ignores custom backgrounds/handles; Basic honours them.
        QQuickStyle.setStyle("Basic")
        app = QApplication(sys.argv)
        app.setApplicationName("Universal Media Studio")
        app.setOrganizationName("Universal Media Studio")

        # Import the Python bridge inside the guarded startup path so import or
        # dependency errors are written to startup.log instead of being silent
        # in a windowed executable.
        from ums.qml_bridge import AppBridge

        resource_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
        font_path = resource_root / "ums" / "fonts" / "Inter-Variable.ttf"
        if font_path.is_file():
            QFontDatabase.addApplicationFont(str(font_path))
        app.setFont(QFont("Inter", 10))

        bridge = AppBridge()
        engine = QQmlApplicationEngine()
        qml_warnings = []

        def record_qml_warnings(warnings):
            for warning in warnings:
                message = warning.toString() if hasattr(warning, "toString") else str(warning)
                qml_warnings.append(message)
                logging.error("QML: %s", message)

        engine.warnings.connect(record_qml_warnings)
        engine.rootContext().setContextProperty("appBridge", bridge)
        qml_file = resource_root / "ums" / "qml" / "Main.qml"
        if not qml_file.is_file():
            raise FileNotFoundError(f"The QML entry point was not found: {qml_file}")

        logging.info("Loading QML entry point: %s", qml_file)
        engine.load(QUrl.fromLocalFile(str(qml_file)))
        if not engine.rootObjects():
            details = "\n".join(qml_warnings[-12:])
            if not details:
                details = "Qt did not create a root QML window. Check the startup log for details."
            logging.error("QML startup failed:\n%s", details)
            QMessageBox.critical(
                None,
                "Universal Media Studio could not start",
                f"The interface failed to load.\n\n{details}\n\nStartup log: {log_path or 'unavailable'}",
            )
            return 1

        app.aboutToQuit.connect(bridge.quit)
        logging.info("QML interface loaded successfully")
        return app.exec()

    except Exception as exc:
        logging.exception("Universal Media Studio startup failed")
        message = (
            f"{type(exc).__name__}: {exc}\n\n"
            f"Startup log: {log_path or 'unavailable'}"
        )
        if app is not None:
            QMessageBox.critical(None, "Universal Media Studio could not start", message)
        else:
            print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
