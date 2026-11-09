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


def _extract_info_with_cookie_fallback(
    yt_dlp_module,
    options: dict,
    url: str,
    *,
    download: bool = False,
    related_options: tuple[dict, ...] = (),
    log_cb=None,
    fallback_state: dict | None = None,
):
    """Retry once without browser cookies when the browser locks its SQLite DB.

    Public music search/downloads should still work when cookies are optional.
    We never rewrite the user's setting: if a private source needs authentication,
    its subsequent error remains visible with guidance to close the browser.
    """
    def extract():
        with yt_dlp_module.YoutubeDL(options) as ydl:
            return ydl.extract_info(url, download=download)

    try:
        return extract()
    except Exception as exc:
        if "cookiesfrombrowser" not in options or not _is_browser_cookie_access_error(exc):
            raise

        for candidate in (options, *related_options):
            candidate.pop("cookiesfrombrowser", None)
        if fallback_state is not None:
            fallback_state["used"] = True
        if log_cb:
            log_cb(
                "The browser cookie database is locked or unreadable. "
                "Retrying this music request without browser cookies; close the browser "
                "fully if the source requires a signed-in session."
            )
        _LOG.warning(
            "yt-dlp could not read the selected browser cookie database; retrying without browser cookies"
        )
        return extract()
