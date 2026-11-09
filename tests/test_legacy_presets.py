import unittest
from pathlib import Path

from ums.engine import _ffmpeg_args
from ums.presets import PRESETS, merged_presets


class LegacyPresetTests(unittest.TestCase):
    def test_3gp_profile_uses_feature_phone_target(self):
        preset = PRESETS["3GP Legacy Mobile"]

        self.assertEqual(preset["container"], "3gp")
        self.assertEqual(preset["video_codec"], "mpeg4")
        self.assertEqual(preset["rate_control"], "CBR")
        self.assertEqual(preset["video_bitrate"], "250k")
        self.assertEqual(preset["resolution"], "Custom")
        self.assertEqual(preset["custom_scale"], "320x240")
        self.assertEqual(preset["fps"], "20")
        self.assertEqual(preset["pixel_format"], "yuv420p")

    def test_3gp_profile_builds_matching_ffmpeg_arguments(self):
        preset = dict(PRESETS["3GP Legacy Mobile"])
        args = _ffmpeg_args(Path("input.mp4"), Path("output.3gp"), preset)

        self.assertEqual(args[args.index("-c:v") + 1], "mpeg4")
        self.assertEqual(args[args.index("-b:v") + 1], "250k")
        self.assertEqual(args[args.index("-minrate") + 1], "250k")
        self.assertEqual(args[args.index("-maxrate") + 1], "250k")
        self.assertEqual(args[args.index("-bufsize") + 1], "250k")
        self.assertEqual(args[args.index("-r") + 1], "20")
        self.assertEqual(
            args[args.index("-vf") + 1],
            "scale=320:240:force_original_aspect_ratio=decrease,"
            "pad=320:240:(ow-iw)/2:(oh-ih)/2",
        )
        self.assertEqual(args[args.index("-pix_fmt") + 1], "yuv420p")

    def test_custom_preset_cannot_override_a_builtin_profile(self):
        merged = merged_presets({
            "3GP Legacy Mobile": {"video_codec": "h264"},
            "My QVGA profile": {"container": "3gp", "video_codec": "mpeg4"},
        })

        self.assertEqual(merged["3GP Legacy Mobile"]["video_codec"], "mpeg4")
        self.assertIn("My QVGA profile", merged)


if __name__ == "__main__":
    unittest.main()
