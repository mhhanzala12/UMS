"""Launch the original full-featured PySide6 Widgets interface."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase, QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from ums.ui import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Universal Media Studio")
    app.setOrganizationName("Universal Media Studio")

    root = Path(__file__).resolve().parent
    icon_path = root / "output.ico"
    if icon_path.is_file():
        app.setWindowIcon(QIcon(str(icon_path)))

    font_path = root / "ums" / "fonts" / "Inter-Variable.ttf"
    if font_path.is_file():
        QFontDatabase.addApplicationFont(str(font_path))
    app.setFont(QFont("Inter", 10))

    try:
        window = MainWindow()
        window.show()
        return app.exec()
    except Exception as exc:
        logging.exception("The legacy Universal Media Studio interface failed to start")
        QMessageBox.critical(
            None,
            "Universal Media Studio could not start",
            f"{type(exc).__name__}: {exc}\n\n"
            "Check the console output for the full diagnostic details.",
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
