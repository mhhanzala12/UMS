"""Tests for synchronized lyric timestamp parsing."""
import unittest

from ums.lyrics import format_lrc, lyric_match_score, parse_lrc, parse_ttml


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

    def test_parses_ttml_line_timestamps_and_nested_spans(self):
        source = """<?xml version="1.0"?>
        <tt xmlns="http://www.w3.org/ns/ttml">
          <body><div>
            <p begin="00:00:01.250" end="00:00:02.500"><span>First </span><span>line</span></p>
            <p begin="3.5s" end="4.5s">Second line</p>
          </div></body>
        </tt>"""
        self.assertEqual(parse_ttml(source), [
            {"time_ms": 1250, "text": "First line"},
            {"time_ms": 3500, "text": "Second line"},
        ])

    def test_ttml_uses_first_timed_child_when_paragraph_has_no_start(self):
        source = '<tt><body><div><p><span begin="00:00:02.10">Timed line</span></p></div></body></tt>'
        self.assertEqual(parse_ttml(source), [{"time_ms": 2100, "text": "Timed line"}])

    def test_ttml_ignores_invalid_xml_and_untimed_lines(self):
        self.assertEqual(parse_ttml("<tt><p>Untimed</p></tt>"), [])
        self.assertEqual(parse_ttml("<tt>"), [])

    def test_formats_timestamped_lines_as_lrc_with_metadata(self):
        source = format_lrc(
            [
                {"time_ms": 1250, "text": "First line"},
                {"time_ms": 62345, "text": "Second line"},
                {"time_ms": -1, "text": "Untimed text"},
            ],
            title="Song",
            artist="Artist",
            album="Album",
        )
        self.assertEqual(source, (
            "[ti:Song]\n[ar:Artist]\n[al:Album]\n"
            "[00:01.25]First line\n[01:02.35]Second line\n"
        ))
        self.assertEqual(parse_lrc(source), [
            {"time_ms": 1250, "text": "First line"},
            {"time_ms": 62350, "text": "Second line"},
        ])

    def test_lrc_formatter_returns_empty_for_plain_lyrics(self):
        self.assertEqual(format_lrc([{"time_ms": -1, "text": "Plain lyric"}]), "")

    def test_match_score_preserves_non_latin_track_metadata(self):
        score = lyric_match_score(
            "আমার সোনার বাংলা",
            "রবীন্দ্রনাথ ঠাকুর",
            "আমার সোনার বাংলা",
            "রবীন্দ্রনাথ ঠাকুর",
        )
        self.assertGreaterEqual(score, 0.99)

    def test_match_score_prefers_correct_artist_and_duration(self):
        exact = lyric_match_score("Song Name", "Correct Artist", "Song Name", "Correct Artist", 210, 211)
        wrong_artist = lyric_match_score("Song Name", "Correct Artist", "Song Name", "Other Artist", 210, 211)
        wrong_duration = lyric_match_score("Song Name", "Correct Artist", "Song Name", "Correct Artist", 210, 260)
        self.assertGreater(exact, wrong_artist)
        self.assertGreater(exact, wrong_duration)
        self.assertEqual(wrong_artist, 0.0)


if __name__ == "__main__":
    unittest.main()
