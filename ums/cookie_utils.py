"""Small yt-dlp helpers that do not depend on the Qt GUI runtime."""
from __future__ import annotations

import logging

_LOG = logging.getLogger(__name__)


def _is_browser_cookie_access_error(exc: BaseException) -> bool:
    """Recognise a locked/unreadable browser cookie DB, not auth failures."""
    fragments = []
    seen = set()
    current = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        fragments.append(str(current).casefold())
        current = current.__cause__ or current.__context__
    message = " ".join(fragments)
    if "cookie" not in message:
        return False
    return any(marker in message for marker in (
        "permission denied",
        "access is denied",
        "could not copy",
        "failed to load cookies",
        "database is locked",
        "unable to open database file",
    ))


def _run_with_cookie_fallback(
    options: dict,
    operation,
    *,
    related_options: tuple[dict, ...] = (),
    log_cb=None,
    fallback_state: dict | None = None,
    task_label: str = "media request",
):
    """Run one yt-dlp operation, retrying once if browser cookies are locked.

    The retry is scoped to this operation only. The user's persisted settings
    remain unchanged; signed-in-only sources will still report their auth error.
    """
    try:
        return operation()
    except Exception as exc:
        if "cookiesfrombrowser" not in options or not _is_browser_cookie_access_error(exc):
            raise

        for candidate in (options, *related_options):
            candidate.pop("cookiesfrombrowser", None)
        if fallback_state is not None:
            fallback_state["used"] = True
        message = (
            "The browser cookie database is locked or unreadable. "
            f"Retrying this {task_label} without browser cookies; close the browser "
            "fully if the source requires a signed-in session."
        )
        if log_cb:
            log_cb(message)
        _LOG.warning(
            "yt-dlp could not read the selected browser cookie database; retrying %s without browser cookies",
            task_label,
        )
        return operation()


def _extract_info_with_cookie_fallback(
    yt_dlp_module,
    options: dict,
    url: str,
    *,
    download: bool = False,
    related_options: tuple[dict, ...] = (),
    log_cb=None,
    fallback_state: dict | None = None,
    task_label: str = "media analysis",
):
    """Call extract_info with the shared, one-time browser-cookie fallback."""
    def extract():
        with yt_dlp_module.YoutubeDL(options) as ydl:
            return ydl.extract_info(url, download=download)

    return _run_with_cookie_fallback(
        options,
        extract,
        related_options=related_options,
        log_cb=log_cb,
        fallback_state=fallback_state,
        task_label=task_label,
    )
