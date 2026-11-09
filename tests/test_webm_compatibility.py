import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from ums.engine import (
    MediaError,
    _ffmpeg_args,
    _normalise_webm_options,
    _validate_webm_streams,
    analyze_url,
)


class WebMCompatibilityTests(unittest.TestCase):
    def test_h264_aac_copy_is_rewritten_for_webm(self):
        with patch("ums.engine._source_stream_codecs", return_value={"video": "h264", "audio": "aac"}), \
             patch("ums.engine.list_encoders", return_value=["libvpx-vp9", "libopus"]):
            options = _normalise_webm_options(
                Path("input.mp4"),
                {"container": "webm", "video_codec": "copy", "audio_codec": "copy",
                 "rate_control": "Source", "embed_subtitles": True},
                "ffprobe", "ffmpeg",
            )

        self.assertEqual(options["video_codec"], "vp9")
        self.assertEqual(options["audio_codec"], "opus")
        self.assertEqual(options["rate_control"], "CRF")
        self.assertFalse(options["embed_subtitles"])
        self.assertFalse(options["_webm_video_copy_safe"])
        self.assertFalse(options["_webm_audio_copy_safe"])

    def test_unknown_probe_codec_is_not_treated_as_safe_to_copy(self):
        with patch("ums.engine._source_stream_codecs", return_value={"video": "", "audio": ""}), \
             patch("ums.engine.list_encoders", return_value=["libvpx", "libvorbis"]):
            options = _normalise_webm_options(
                Path("input.bin"),
                {"container": "webm", "video_codec": "copy", "audio_codec": "copy"},
                "ffprobe", "ffmpeg",
            )

        self.assertEqual(options["video_codec"], "vp8")
        self.assertEqual(options["audio_codec"], "vorbis")
        self.assertFalse(options["_webm_video_copy_safe"])
        self.assertFalse(options["_webm_audio_copy_safe"])

    def test_valid_webm_source_streams_can_be_copied_after_probe(self):
        with patch("ums.engine._source_stream_codecs", return_value={"video": "vp9", "audio": "opus"}), \
             patch("ums.engine.list_encoders", return_value=["libvpx-vp9", "libopus"]):
            options = _normalise_webm_options(
                Path("input.webm"),
                {"container": "webm", "video_codec": "copy", "audio_codec": "copy"},
                "ffprobe", "ffmpeg",
            )

        self.assertEqual(options["video_codec"], "copy")
        self.assertEqual(options["audio_codec"], "copy")
        self.assertTrue(options["_webm_video_copy_safe"])
        self.assertTrue(options["_webm_audio_copy_safe"])

    def test_webm_arguments_reject_unchecked_or_forbidden_streams(self):
        with self.assertRaises(MediaError):
            _ffmpeg_args(
                Path("input.mp4"), Path("output.webm"),
                {"container": "webm", "video_codec": "h264", "audio_codec": "aac"},
            )

        with self.assertRaises(MediaError):
            _ffmpeg_args(
                Path("input.webm"), Path("output.webm"),
                {"container": "webm", "video_codec": "copy", "audio_codec": "copy"},
            )

    def test_post_mux_validation_rejects_h264_in_webm(self):
        with self.assertRaises(MediaError):
            _validate_webm_streams({
                "validated": True,
                "probe": {"streams": [
                    {"codec_type": "video", "codec_name": "h264"},
                    {"codec_type": "audio", "codec_name": "opus"},
                ]},
            })

    def test_analysis_prefers_best_formats_and_thumbnail_fallbacks(self):
        info = {
            "id": "abc",
            "title": "Test title",
            "extractor_key": "Test",
            "webpage_url": "https://example.com/watch/abc",
            "thumbnails": [
                {"url": "https://example.com/small.jpg", "width": 320, "height": 180},
                {"url": "https://example.com/large.jpg", "width": 1280, "height": 720},
            ],
            "formats": [
                {"url": "https://example.com/low", "format_id": "low", "height": 240,
                 "fps": 25, "ext": "mp4", "vcodec": "h264", "acodec": "aac"},
                {"url": "https://example.com/high", "format_id": "high", "height": 1080,
                 "fps": 60, "ext": "mp4", "vcodec": "h264", "acodec": "none"},
            ],
        }

        class FakeYoutubeDL:
            def __init__(self, options):
                self.options = options
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def extract_info(self, url, download=False):
                return info

        fake_module = types.SimpleNamespace(YoutubeDL=FakeYoutubeDL)
        with patch.dict(sys.modules, {"yt_dlp": fake_module}):
            data = analyze_url("https://example.com/watch/abc")

        self.assertEqual(data["formats"][0]["format_id"], "high")
        self.assertEqual(data["thumbnail"], "https://example.com/large.jpg")
        self.assertEqual(data["thumbnails"][0], data["thumbnail"])
        self.assertEqual(data["title"], "Test title")


if __name__ == "__main__":
    unittest.main()
