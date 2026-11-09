import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from ums.engine import (
    MediaError,
    _ffmpeg_args,
    _finalize,
    _normalise_webm_options,
    _download_thumbnail_candidates,
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

    def test_muxer_recovery_forces_webm_compatible_encoding(self):
        with (
            patch("ums.engine._source_stream_codecs", return_value={"video": "vp9", "audio": "opus"}),
            patch("ums.engine.list_encoders", return_value=["libvpx-vp9", "libopus"]),
        ):
            options = _normalise_webm_options(
                Path("input.webm"),
                {"container": "webm", "video_codec": "copy", "audio_codec": "copy"},
                "ffprobe", "ffmpeg", force_reencode=True,
            )

        self.assertEqual(options["video_codec"], "vp9")
        self.assertEqual(options["audio_codec"], "opus")
        self.assertEqual(options["rate_control"], "CRF")
        self.assertEqual(options["crf"], "32")
        self.assertEqual(options["pixel_format"], "yuv420p")
        self.assertFalse(options["_webm_video_copy_safe"])
        self.assertFalse(options["_webm_audio_copy_safe"])

    def test_thumbnail_helpers_try_next_size_variant(self):
        with patch(
            "ums.engine._download_thumbnail_data",
            side_effect=[b"", b"valid-preview"],
        ) as download:
            data = _download_thumbnail_candidates([
                "https://example.com/large.jpg",
                "https://example.com/fallback.jpg",
            ])

        self.assertEqual(data, b"valid-preview")
        self.assertEqual(download.call_count, 2)

    def test_webm_muxer_failure_is_retried_without_copy(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "input.webm"
            output_dir = root / "output"
            source.write_bytes(b"source")
            ffmpeg_calls = []

            def fake_ffmpeg(_source, target, options, *_args):
                ffmpeg_calls.append(dict(options))
                if len(ffmpeg_calls) == 1:
                    raise MediaError(
                        "FFmpeg failed (exit -22): Only VP8 or VP9 or AV1 video "
                        "and Vorbis or Opus audio and WebVTT subtitles are supported for WebM. "
                        "Could not write header: Invalid argument"
                    )
                target.write_bytes(b"valid-webm")

            with (
                patch("ums.engine._which", side_effect=lambda name, configured=None: name),
                patch("ums.engine._source_stream_codecs", return_value={"video": "vp9", "audio": "opus"}),
                patch("ums.engine.list_encoders", return_value=["libvpx-vp9", "libopus"]),
                patch("ums.engine._run_ffmpeg", side_effect=fake_ffmpeg),
                patch("ums.engine._probe", return_value={
                    "validated": True,
                    "probe": {"streams": [
                        {"codec_type": "video", "codec_name": "vp9"},
                        {"codec_type": "audio", "codec_name": "opus"},
                    ]},
                    "message": "Output validated with ffprobe.",
                }),
            ):
                result = _finalize(
                    source, output_dir,
                    {"container": "webm", "video_codec": "copy", "audio_codec": "copy"},
                    "webm-retry-test",
                    log_cb=lambda _message: None,
                )

            self.assertTrue(result.is_file())
            self.assertEqual(len(ffmpeg_calls), 2)
            self.assertTrue(ffmpeg_calls[0]["_webm_video_copy_safe"])
            self.assertEqual(ffmpeg_calls[1]["video_codec"], "vp9")
            self.assertEqual(ffmpeg_calls[1]["audio_codec"], "opus")
            self.assertFalse(ffmpeg_calls[1]["_webm_video_copy_safe"])

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

    def test_thumbnail_cdn_failure_does_not_fail_analysis(self):
        from ums.engine import _download_thumbnail_data

        with patch("ums.engine.urllib.request.urlopen", side_effect=OSError("CDN unavailable")):
            self.assertEqual(
                _download_thumbnail_data("https://example.com/preview.jpg"),
                b"",
            )

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
                {"url": "https://example.com/low", "format_id": "low", "width": 426, "height": 240,
                 "fps": 25, "ext": "mp4", "filesize": 500_000, "vcodec": "h264", "acodec": "none"},
                {"url": "https://example.com/high", "format_id": "high", "width": 1920, "height": 1080,
                 "fps": 60, "ext": "mp4", "vcodec": "h264", "acodec": "none"},
                {"url": "https://example.com/audio", "format_id": "audio", "ext": "m4a",
                 "abr": 128, "filesize": 120_000, "vcodec": "none", "acodec": "aac"},
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
        with patch.dict(sys.modules, {"yt_dlp": fake_module}), \
             patch("ums.engine._download_thumbnail_data", return_value=b"preview-bytes"):
            data = analyze_url("https://example.com/watch/abc")

        self.assertEqual(data["formats"][0]["format_id"], "high")
        self.assertEqual(data["thumbnail"], "https://example.com/large.jpg")
        self.assertEqual(data["thumbnail_data"], b"preview-bytes")
        self.assertEqual(data["thumbnails"][0], data["thumbnail"])
        self.assertEqual(data["title"], "Test title")
        self.assertEqual(data["resolution"], "1920x1080")
        self.assertEqual(data["fps"], 60)
        self.assertEqual(data["vcodec"], "h264")
        # There is no progressive format in this fixture, so a single video
        # stream size must not be presented as the total media file size.
        self.assertIsNone(data["filesize"])


if __name__ == "__main__":
    unittest.main()
