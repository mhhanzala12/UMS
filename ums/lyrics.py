"""Helpers for parsing LRCLIB synchronized lyrics without Qt dependencies."""
from __future__ import annotations

import re
import unicodedata
import xml.etree.ElementTree as ET
from difflib import SequenceMatcher

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


def _parse_ttml_time(value: str | None) -> int | None:
    """Convert common TTML clock/offset expressions to milliseconds."""
    value = str(value or "").strip()
    if not value:
        return None
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(ms|s)", value, re.IGNORECASE)
    if match:
        amount = float(match.group(1))
        return max(0, round(amount if match.group(2).lower() == "ms" else amount * 1000))
    match = re.fullmatch(r"(?:(\d+):)?(\d{1,2}):(\d+(?:\.\d+)?)", value)
    if not match:
        return None
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2))
    seconds = float(match.group(3))
    if minutes >= 60 or seconds >= 60:
        return None
    return max(0, round((hours * 3600 + minutes * 60 + seconds) * 1000))


def parse_ttml(source: str) -> list[dict]:
    """Extract line start times and text from TTML documents.

    Better Lyrics and other providers often supply syllable-timed spans inside
    a paragraph. The current player highlights whole lines, so the paragraph
    start is preferred; the earliest timed child is used when a paragraph has
    no explicit begin attribute.
    """
    if not source:
        return []
    try:
        root = ET.fromstring(str(source).strip())
    except (ET.ParseError, ValueError, TypeError):
        return []

    rows: list[tuple[int, int, dict]] = []
    sequence = 0
    for paragraph in root.iter():
        if paragraph.tag.rsplit("}", 1)[-1].lower() != "p":
            continue
        start_ms = _parse_ttml_time(paragraph.attrib.get("begin") or paragraph.attrib.get("start"))
        if start_ms is None:
            child_times = [
                value for child in paragraph.iter()
                if child is not paragraph
                for value in [_parse_ttml_time(child.attrib.get("begin") or child.attrib.get("start"))]
                if value is not None
            ]
            if child_times:
                start_ms = min(child_times)
        if start_ms is None:
            continue
        text = re.sub(r"\s+", " ", "".join(paragraph.itertext())).strip()
        if not text:
            continue
        rows.append((start_ms, sequence, {"time_ms": start_ms, "text": text}))
        sequence += 1
    rows.sort(key=lambda item: (item[0], item[1]))
    result: list[dict] = []
    seen: set[tuple[int, str]] = set()
    for _time, _sequence, row in rows:
        key = (row["time_ms"], row["text"])
        if key not in seen:
            result.append(row)
            seen.add(key)
    return result


def _normalise_track_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", str(value or "").casefold())
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = re.sub(r"\b(?:feat|ft|featuring)\b.*$", " ", value)
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value).split())


def _text_similarity(left: str, right: str) -> float:
    left = _normalise_track_text(left)
    right = _normalise_track_text(right)
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    overlap = len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))
    return max(SequenceMatcher(None, left, right).ratio(), overlap)


def _artist_similarity(left: str, right: str) -> float:
    left_tokens = set(_normalise_track_text(left).split())
    right_tokens = set(_normalise_track_text(right).split())
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))


def lyric_match_score(
    requested_title: str,
    requested_artist: str,
    candidate_title: str,
    candidate_artist: str,
    requested_duration: float | None = None,
    candidate_duration: float | None = None,
) -> float:
    """Score a lyric candidate against track metadata; incompatible artists are rejected."""
    title_score = _text_similarity(requested_title, candidate_title)
    if title_score < 0.42:
        return 0.0

    if requested_artist and candidate_artist:
        artist_score = _artist_similarity(requested_artist, candidate_artist)
        if artist_score < 0.35:
            return 0.0
    else:
        artist_score = 0.72

    score = title_score * 0.76 + artist_score * 0.24
    try:
        requested_seconds = float(requested_duration or 0)
        candidate_seconds = float(candidate_duration or 0)
    except (TypeError, ValueError):
        requested_seconds = candidate_seconds = 0.0
    if requested_seconds > 0 and candidate_seconds > 0:
        difference = abs(requested_seconds - candidate_seconds)
        if difference <= 4:
            score += 0.08
        elif difference <= 10:
            score += 0.04
        elif difference > 30:
            score -= 0.15
        elif difference > 15:
            score -= 0.08
    return max(0.0, min(1.0, score))
