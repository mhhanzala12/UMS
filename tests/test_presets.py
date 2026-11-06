"""Tests for built-in download profiles and custom label validation."""
import unittest

from ums.presets import DOWNLOAD_PROFILE_NAMES, PRESETS, merged_presets


class DownloadPresetTests(unittest.TestCase):
    def test_required_profiles_are_retained(self):
        profiles = merged_presets()
        for name in (
            "Best Available Quality",
            "Audio Only",
            "Lossless Audio",
            "3GP Legacy Mobile",
            "MP4 Universal Compatibility",
        ):
            self.assertIn(name, profiles)

    def test_malformed_custom_labels_are_filtered(self):
        profiles = merged_presets({
            "gg.": {"container": "ogg"},
            "  Bad name": {"container": "mp4"},
            "My Custom Profile": {"container": "mp4"},
        })
        self.assertNotIn("gg.", profiles)
        self.assertNotIn("  Bad name", profiles)
        self.assertIn("My Custom Profile", profiles)
        self.assertIn("বাংলা প্রোফাইল", merged_presets({
            "বাংলা প্রোফাইল": {"container": "mp4"}
        }))

    def test_download_profile_list_contains_only_requested_profiles(self):
        self.assertEqual(DOWNLOAD_PROFILE_NAMES, (
            "Best Available Quality",
            "Audio Only",
            "Lossless Audio",
            "3GP Legacy Mobile",
            "MP4 Universal Compatibility",
        ))

    def test_built_in_presets_are_not_mutated(self):
        custom = merged_presets()
        self.assertEqual(custom["Audio Only"]["container"], PRESETS["Audio Only"]["container"])


if __name__ == "__main__":
    unittest.main()
