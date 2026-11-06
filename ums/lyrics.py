"""Helpers for parsing LRCLIB synchronized lyrics without Qt dependencies."""
from __future__ import annotations

import re

_TIMESTAMP = re.compile(r"\[(\d{1,3}):(\d{2})(?:[.:](\d{1,3}))?\]")
_OFFSET = re.compile(r"\[offset:([+-]?\d+)\]", re.IGNORECASE)


def parse_lrc(source: str) -> list[dict]:
    """Convert LRC text into sorted dictionaries containing time_ms and text.

    Multiple timestamps on one line are expanded into separate rows, and
    LRCLIB's optional offset tag is applied to every timestamp.
    """
    if not source:
        return []
    offset_ms = 0
    rows: list[tuple[int, int, dict]] = []
    sequence = 0
    for raw_line in str(source).replace("\r", "").splitlines():
        offset_match = _OFFSET.search(raw_line)
        if offset_match:
            try:
                offset_ms = int(offset_match.group(1))
            except ValueError:
                offset_ms = 0
            raw_line = _OFFSET.sub("", raw_line)
        matches = list(_TIMESTAMP.finditer(raw_line))
        if not matches:
            continue
        text = _TIMESTAMP.sub("", raw_line).strip()
        if not text:
            continue
        for match in matches:
            minutes = int(match.group(1))
            seconds = int(match.group(2))
            if seconds >= 60:
                continue
            fraction = (match.group(3) or "0").ljust(3, "0")[:3]
            milliseconds = (minutes * 60 + seconds) * 1000 + int(fraction) + offset_ms
            milliseconds = max(0, milliseconds)
            rows.append((milliseconds, sequence, {
                "time_ms": milliseconds,
                "text": text,
            }))
            sequence += 1
    rows.sort(key=lambda item: (item[0], item[1]))
    return [row for _time, _sequence, row in rows]
