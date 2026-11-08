"""Launch the QML desktop interface for Universal Media Studio."""
import logging
import os
import sys
import time
from pathlib import Path

_T0 = time.perf_counter()

# Qt Multimedia's FFmpeg backend can emit a full codec/MFT diagnostic dump when
# QT_FFMPEG_DEBUG is inherited from a developer shell or IDE. Keep normal app
# launches quiet, but let developers opt in explicitly for troubleshooting.
if os.environ.get("UMS_KEEP_QT_FFMPEG_DEBUG") != "1":
    os.environ.pop("QT_FFMPEG_DEBUG", None)

def _expose_bundled_tools():
    """Expose FFmpeg/ffprobe shipped beside the PyInstaller application.

    In a one-folder build, bundled binaries live below sys._MEIPASS. Adding that
    directory and the executable directory to PATH lets shutil.which() and
    yt-dlp find the tools when the complete application folder is moved.
    """
    if not getattr(sys, "frozen", False):
        return
    bundled = getattr(sys, "_MEIPASS", None)
    extra = [d for d in (bundled, os.path.dirname(sys.executable)) if d]
    current = os.environ.get("PATH", "")
    os.environ["PATH"] = os.pathsep.join(extra + ([current] if current else []))


_expose_bundled_tools()

from PySide6.QtCore import QUrl
from PySide6.QtGui import QFont, QFontDatabase, QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication, QMessageBox

def _stable_qml_root(resource_root: Path) -> Path:
    """Return a folder QML can be loaded from so Qt's compiled-QML cache keeps hitting.

    A single-file (onefile) EXE unpacks itself to a new random temp folder on every
    launch. Qt keys its compiled-QML cache by file path, so loading straight from that
    folder would recompile the 2,500-line interface on every start. The QML files are
    therefore copied once (per content hash) into the user's profile, next to the
    settings file, and loaded from there. Nothing is installed beside the EXE.
    """
    src = resource_root / "ums" / "qml"
    if not hasattr(sys, "_MEIPASS"):
        return src
    try:
        import hashlib
        import shutil

        digest = hashlib.sha1()
        for file in sorted(src.rglob("*")):
            if file.is_file():
                digest.update(file.name.encode("utf-8"))
                digest.update(file.read_bytes())
        key = digest.hexdigest()[:12]
        base = Path.home() / ".universal_media_studio" / "qml"
        dest = base / key
        if not (dest / "Main.qml").is_file():
            base.mkdir(parents=True, exist_ok=True)
            tmp = base / f"{key}.{os.getpid()}.tmp"
            shutil.rmtree(tmp, ignore_errors=True)
            shutil.copytree(src, tmp)
            try:
                os.replace(tmp, dest)
            except OSError:
                shutil.rmtree(tmp, ignore_errors=True)  # another instance won the race
            if not (dest / "Main.qml").is_file():
                return src
        try:
            os.utime(dest, None)
            cutoff = time.time() - 14 * 86400
            for old in base.iterdir():
                if old.is_dir() and old != dest and old.stat().st_mtime < cutoff:
                    shutil.rmtree(old, ignore_errors=True)
        except OSError:
            pass
        return dest
    except Exception:
        logging.exception("Could not prepare the cached QML folder; loading QML from the bundle")
        return src


def _selftest_failure(resource_root: Path, qml_warnings: list) -> int:
    """Checks run by builder.bat against the freshly built EXE. 0 means healthy."""
    fatal = ("is not installed", "File not found", "Cannot open", "is not a type", "No such file")
    broken = [w for w in qml_warnings if any(marker in w for marker in fatal)]
    if broken:
        logging.error("SELFTEST: QML failed to resolve: %s", broken[:3])
        return 3
    from ums.engine import _which
    if not _which("ffmpeg") or not _which("ffprobe"):
        logging.error("SELFTEST: bundled ffmpeg/ffprobe not found")
        return 4
    try:
        import importlib
        importlib.import_module("PySide6.QtMultimedia")
    except Exception:
        logging.exception("SELFTEST: QtMultimedia is not usable")
        return 5
    try:
        importlib.import_module("yt_dlp")
    except Exception:
        logging.exception("SELFTEST: yt-dlp is not usable")
        return 6
    if not (resource_root / "ums" / "fonts" / "Inter-Variable.ttf").is_file():
        logging.error("SELFTEST: bundled font missing")
        return 7
    from PySide6.QtGui import QImageReader
    formats = {bytes(f).lower() for f in QImageReader.supportedImageFormats()}
    if b"svg" not in formats or b"ico" not in formats:
        logging.error("SELFTEST: image plugins missing (have %s)", sorted(formats))
        return 8
    if not (resource_root / "output.ico").is_file():
        logging.error("SELFTEST: bundled icon missing")
        return 9
    return 0


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

        resource_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
        icon_path = resource_root / "output.ico"
        if icon_path.is_file():
            app.setWindowIcon(QIcon(str(icon_path)))

        # Import the Python bridge inside the guarded startup path so import or
        # dependency errors are written to startup.log instead of being silent
        # in a windowed executable.
        from ums.qml_bridge import AppBridge

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
        qml_file = _stable_qml_root(resource_root) / "Main.qml"
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
        if os.environ.get("UMS_SELFTEST") == "1":
            from PySide6.QtCore import QTimer
            QTimer.singleShot(30000, lambda: app.exit(10))  # never hang a build
            QTimer.singleShot(1800, lambda: app.exit(_selftest_failure(resource_root, qml_warnings)))
        logging.info("QML interface loaded successfully in %.0f ms", (time.perf_counter() - _T0) * 1000)
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
