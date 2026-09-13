"""Filename disambiguation for several formats of one link."""
import unittest

from ytget_gui import naming


class _Settings:
    def __init__(self, container=".mkv"):
        self.VIDEO_FORMAT = container


class ContainerKeyTests(unittest.TestCase):
    def test_video_presets_share_the_configured_container(self):
        s = _Settings(".mkv")
        self.assertEqual(
            naming.container_key("bv*[height<=1080]+ba/b", s),
            naming.container_key("bv*[height<=2160]+ba/b", s),
        )

    def test_audio_presets_do_not_collide_with_video(self):
        s = _Settings(".mkv")
        self.assertNotEqual(
            naming.container_key("bestaudio", s),
            naming.container_key("bv*[height<=1080]+ba/b", s),
        )

    def test_audio_codecs_are_distinct(self):
        self.assertNotEqual(
            naming.container_key("audio_flac"), naming.container_key("bestaudio")
        )

    def test_spotify_is_its_own_container(self):
        self.assertEqual(naming.container_key("spotify"), "spotify")

    def test_missing_settings_default_to_mkv(self):
        self.assertEqual(naming.container_key("bv*+ba/b"), "mkv")


class SuffixTests(unittest.TestCase):
    def test_parenthesised_label_tag_wins(self):
        self.assertEqual(
            naming.suffix_for("\U0001f3ac YouTube 1440p (QHD)", "bv*+ba"), "QHD"
        )
        self.assertEqual(
            naming.suffix_for("\U0001f3ac YouTube 2160p (4K)", "bv*+ba"), "4K"
        )

    def test_height_is_used_when_there_is_no_tag(self):
        self.assertEqual(naming.suffix_for("Universal 720p", "bv*+ba"), "720p")

    def test_audio_presets_use_their_codec(self):
        self.assertEqual(naming.suffix_for("Single Audio", "audio_flac"), "FLAC")

    def test_taken_suffixes_are_never_reused(self):
        first = naming.suffix_for("YouTube 1440p (QHD)", "bv*+ba", [""])
        second = naming.suffix_for("YouTube 1440p (QHD)", "bv*+ba", ["", first])
        self.assertEqual(first, "QHD")
        self.assertNotEqual(second, first)
        self.assertTrue(second)

    def test_a_suffix_is_always_produced(self):
        self.assertTrue(naming.suffix_for("", "", [""]))

    def test_suffix_has_no_path_separators(self):
        suffix = naming.suffix_for("Weird /\\: label", "", [""])
        for bad in "/\\:*?\"<>|":
            self.assertNotIn(bad, suffix)


if __name__ == "__main__":
    unittest.main()
