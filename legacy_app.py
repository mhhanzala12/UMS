"""Launch the original full-featured PySide6 Widgets interface.

This remains available as a fallback while QML feature parity is expanded.
"""
import sys
from PySide6.QtWidgets import QApplication
from ums.ui import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Universal Media Studio")
    app.setOrganizationName("Universal Media Studio")
    window = MainWindow()
    window.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
