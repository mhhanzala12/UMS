"""Tests for synchronized lyric timestamp parsing."""
import unittest

from ums.lyrics import parse_lrc


class ParseLrcTests(unittest.TestCase):
    def test_parses_fractional_timestamps(self):
        rows = parse_lrc("[00:01.25]First line\n[01:02.345]Second line")
        self.assertEqual(rows, [
            {"time_ms": 1250, "text": "First line"},
            {"time_ms": 62345, "text": "Second line"},
        ])

    def test_expands_multiple_timestamps_and_sorts(self):
        rows = parse_lrc("[00:04.00][00:02.00]Repeated")
        self.assertEqual([row["time_ms"] for row in rows], [2000, 4000])
        self.assertEqual([row["text"] for row in rows], ["Repeated", "Repeated"])

    def test_applies_offset_and_ignores_metadata(self):
        rows = parse_lrc("[ar:Artist]\n[offset:+500]\n[00:01.00]Line")
        self.assertEqual(rows, [{"time_ms": 1500, "text": "Line"}])

    def test_ignores_invalid_seconds_and_empty_lines(self):
        self.assertEqual(parse_lrc("[00:75.00]Bad\n[00:02.00]"), [])

    def test_empty_input(self):
        self.assertEqual(parse_lrc(""), [])


if __name__ == "__main__":
    unittest.main()
