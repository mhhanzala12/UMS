import unittest

from ums.download_options import DEFAULT_DOWNLOAD_OPTIONS, OUTPUT_CONTAINERS, sanitize_download_options
from ums.presets import PRESETS


class DownloadOptionsTests(unittest.TestCase):
    def test_defaults_are_valid_and_include_all_advanced_option_groups(self):
        options = sanitize_download_options({})
        self.assertEqual(options["container"], "original")
        self.assertEqual(options["format"], DEFAULT_DOWNLOAD_OPTIONS["format"])
        for key in (
            "video_codec", "audio_codec", "video_encoder", "rate_control",
            "video_bitrate", "audio_bitrate", "crf", "encoder_preset",
            "fps", "fps_mode", "resolution", "custom_scale", "sample_rate",
            "channels", "pixel_format", "color_space", "color_range",
            "write_subtitles", "write_automatic_subtitles", "embed_subtitles",
            "preserve_metadata", "download_thumbnail",
        ):
            self.assertIn(key, options)

    def test_3gp_feature_phone_preset_passes_the_modern_option_schema(self):
        options = sanitize_download_options(PRESETS["3GP Legacy Mobile"])
        self.assertEqual(options["container"], "3gp")
        self.assertEqual(options["video_codec"], "mpeg4")
        self.assertEqual(options["rate_control"], "CBR")
        self.assertEqual(options["video_bitrate"], "250k")
        self.assertEqual(options["resolution"], "Custom")
        self.assertEqual(options["custom_scale"], "320x240")
        self.assertEqual(options["fps"], "20")
        self.assertEqual(options["pixel_format"], "yuv420p")
        self.assertEqual(options["channels"], "Mono")

    def test_complete_advanced_options_survive_sanitization(self):
        payload = {
            "format": "bestvideo[height<=720]+bestaudio/best",
            "container": "webm",
            "video_codec": "vp9",
            "audio_codec": "opus",
            "video_encoder": "libvpx-vp9",
            "rate_control": "CRF",
            "crf": "31",
            "fps": "29.97",
            "resolution": "720p",
            "pixel_format": "yuv420p",
            "write_subtitles": True,
            "preserve_metadata": False,
            "download_thumbnail": True,
            "not_an_option": "ignore me",
        }
        options = sanitize_download_options(payload)
        for key, value in payload.items():
            if key != "not_an_option":
                self.assertEqual(options[key], value)
        self.assertNotIn("not_an_option", options)

    def test_container_allowlist_is_explicit(self):
        self.assertIn("3gp", OUTPUT_CONTAINERS)
        self.assertIn("webm", OUTPUT_CONTAINERS)
        for container in ("exe", "../mp4", "", "avi;rm -rf"):
            with self.subTest(container=container):
                with self.assertRaises(ValueError):
                    sanitize_download_options({"container": container})

    def test_unknown_codec_and_encoder_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "video codec"):
            sanitize_download_options({"video_codec": "made-up"})
        with self.assertRaisesRegex(ValueError, "video encoder"):
            sanitize_download_options({"video_encoder": "untrusted-encoder"})

    def test_string_and_numeric_fields_are_bounded_and_validated(self):
        with self.assertRaisesRegex(ValueError, "format is too long"):
            sanitize_download_options({"format": "x" * 513})
        with self.assertRaisesRegex(ValueError, "CRF / quality"):
            sanitize_download_options({"crf": "99"})
        with self.assertRaisesRegex(ValueError, "Choose a source"):
            sanitize_download_options({"format": "  "})

    def test_boolean_values_are_normalized_without_truthy_string_pitfall(self):
        options = sanitize_download_options({
            "write_subtitles": "false",
            "preserve_metadata": "true",
            "download_thumbnail": 0,
        })
        self.assertFalse(options["write_subtitles"])
        self.assertTrue(options["preserve_metadata"])
        self.assertFalse(options["download_thumbnail"])

    def test_non_object_payload_is_rejected(self):
        for value in (None, [], "{}", 4):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    sanitize_download_options(value)


if __name__ == "__main__":
    unittest.main()
