"""Per-site / per-recording-type filename rules (2.8.3)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ytget_gui import filename_rules as fr

YT = "https://www.youtube.com/watch?v=AAAAAAAAAAA"
YTM = "https://music.youtube.com/watch?v=AAAAAAAAAAA"
OTHER = "https://soundcloud.com/artist/track"


class _S:
    def __init__(self, fmt="default", custom="", rules=None):
        self.FILENAME_FORMAT = fmt
        self.CUSTOM_FILENAME_TEMPLATE = custom
        self.FILENAME_RULES = fr.normalise_rules(rules)


class RuleTableTests(unittest.TestCase):
    def test_every_slot_defaults_to_the_general_setting(self):
        rules = fr.default_rules()
        self.assertEqual(set(rules), set(fr.RULE_KEYS))
        self.assertEqual(len(fr.RULE_KEYS), 6)
        self.assertTrue(all(r["format"] == fr.GLOBAL_CHOICE for r in rules.values()))
        self.assertFalse(fr.has_overrides(rules))

    def test_normalise_drops_junk_and_fills_missing(self):
        rules = fr.normalise_rules({
            "youtube_video": {"format": "nope"},
            "ytmusic_audio": "artist_track_title",
            "bogus": {"format": "title_only"},
        })
        self.assertEqual(rules["youtube_video"]["format"], fr.GLOBAL_CHOICE)
        self.assertEqual(rules["ytmusic_audio"]["format"], "artist_track_title")
        self.assertNotIn("bogus", rules)
        self.assertEqual(fr.normalise_rules(None), fr.default_rules())
        self.assertEqual(fr.normalise_rules([1, 2]), fr.default_rules())

    def test_source_detection(self):
        self.assertEqual(fr.source_for(YT), "youtube")
        self.assertEqual(fr.source_for("https://youtu.be/AAAAAAAAAAA"), "youtube")
        self.assertEqual(fr.source_for(YTM), "ytmusic")
        self.assertEqual(fr.source_for(OTHER), "other")
        self.assertEqual(fr.source_for(""), "other")


class ResolutionTests(unittest.TestCase):
    def test_unchanged_behaviour_without_overrides(self):
        s = _S()
        for url in (YT, YTM, OTHER):
            for audio in (False, True):
                self.assertEqual(
                    fr.resolve_template(s, url, audio, "%(title)s"),
                    ("%(title)s", "default"),
                )

    def test_general_setting_still_applies_to_untouched_slots(self):
        s = _S(fmt="uploader_title", rules={"ytmusic_audio": {"format": "artist_title"}})
        self.assertEqual(fr.resolve_template(s, YT, False, "%(title)s")[0],
                         "%(uploader)s - %(title)s")
        self.assertEqual(fr.resolve_template(s, YTM, True, "%(title)s")[0],
                         "%(artist)s - %(title)s")

    def test_music_and_video_templates_are_independent(self):
        # The GitHub request: music as "artist - track# title", video as
        # "uploader - title", set once.
        s = _S(rules={
            "ytmusic_audio": {"format": "artist_track_title"},
            "youtube_audio": {"format": "artist_track_title"},
            "youtube_video": {"format": "uploader_title"},
        })
        self.assertEqual(
            fr.resolve_template(s, YTM, True, "%(title)s")[0],
            fr.FILENAME_FORMAT_PRESETS["artist_track_title"],
        )
        self.assertEqual(
            fr.resolve_template(s, YT, False, "%(title)s")[0],
            "%(uploader)s - %(title)s",
        )
        self.assertEqual(fr.resolve_template(s, OTHER, False, "%(title)s")[0], "%(title)s")

    def test_custom_rule_and_empty_custom_fallback(self):
        s = _S(rules={
            "other_audio": {"format": "custom", "custom": "%(uploader)s ~ %(title)s"},
            "other_video": {"format": "custom", "custom": ""},
        })
        self.assertEqual(fr.resolve_template(s, OTHER, True, "%(title)s"),
                         ("%(uploader)s ~ %(title)s", "custom"))
        self.assertEqual(fr.resolve_template(s, OTHER, False, "%(title)s"),
                         ("%(title)s", "default"))

    def test_explicit_default_overrides_a_general_preset(self):
        s = _S(fmt="id_title", rules={"youtube_video": {"format": "default"}})
        self.assertEqual(fr.resolve_template(s, YT, False, "%(title)s"),
                         ("%(title)s", "default"))
        self.assertEqual(fr.resolve_template(s, YT, True, "%(title)s")[0],
                         "%(id)s - %(title)s")

    def test_settings_without_rules_attribute(self):
        class Bare:
            FILENAME_FORMAT = "title_only"
        self.assertEqual(fr.resolve_template(Bare(), YT, False, "x")[0], "%(title)s")


class TemplateValidationTests(unittest.TestCase):
    def test_every_preset_is_valid(self):
        for key, template in fr.FILENAME_FORMAT_PRESETS.items():
            with self.subTest(key=key):
                self.assertEqual(fr.validate_template(template), (True, ""))

    def test_rejections(self):
        for bad in ("", "a/b %(title)s", "%(nope)s", "%(title", ".%(title)s", "plain"):
            with self.subTest(bad=bad):
                self.assertFalse(fr.validate_template(bad)[0])

    def test_track_number_detection_handles_alternatives(self):
        self.assertTrue(fr.uses_track_number("%(track_number)s - %(title)s"))
        self.assertTrue(fr.uses_track_number("%(track_number,playlist_index)s"))
        self.assertTrue(fr.uses_track_number("%(playlist_index,track_number)s"))
        self.assertFalse(fr.uses_track_number("%(title)s"))
        self.assertFalse(fr.uses_track_number(""))


class PersistenceTests(unittest.TestCase):
    def test_rules_round_trip_and_survive_bad_config(self):
        import json
        from ytget_gui.settings import AppSettings

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            s = AppSettings(DATA_DIR=root / "data", DOWNLOADS_DIR=root / "dl")
            self.assertEqual(s.FILENAME_RULES, fr.default_rules())
            s.apply({"FILENAME_RULES": {"ytmusic_audio": {"format": "artist_track_title"}}})
            s.save_config()
            again = AppSettings(DATA_DIR=root / "data", DOWNLOADS_DIR=root / "dl")
            self.assertEqual(again.FILENAME_RULES["ytmusic_audio"]["format"], "artist_track_title")
            self.assertEqual(again.FILENAME_RULES["youtube_video"]["format"], fr.GLOBAL_CHOICE)

            cfg = root / "data" / "config.json"
            data = json.loads(cfg.read_text(encoding="utf-8"))
            data["FILENAME_RULES"] = "garbage"
            cfg.write_text(json.dumps(data), encoding="utf-8")
            broken = AppSettings(DATA_DIR=root / "data", DOWNLOADS_DIR=root / "dl")
            self.assertEqual(broken.FILENAME_RULES, fr.default_rules())


class WorkerIntegrationTests(unittest.TestCase):
    def _flags(self, url, fmt, rules=None, general="default"):
        from ytget_gui.settings import AppSettings
        from ytget_gui.workers import download_worker as dw

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            s = AppSettings(DATA_DIR=root / "data", DOWNLOADS_DIR=root / "dl")
            s.FILENAME_FORMAT = general
            s.FILENAME_RULES = fr.normalise_rules(rules)
            s.COOKIES_FROM_BROWSER = "firefox"  # no forced-title path
            worker = dw.DownloadWorker({"url": url, "title": "T", "format_code": fmt}, s)
            flags = worker._output_flags(
                is_playlist=False, is_audio=fmt == "bestaudio",
                is_yt_music="music.youtube" in url, is_flat=False,
            )
            return Path(flags[flags.index("-o") + 1]).name

    def test_worker_uses_the_matching_slot(self):
        rules = {
            "ytmusic_audio": {"format": "artist_track_title"},
            "youtube_video": {"format": "uploader_title"},
        }
        self.assertEqual(
            self._flags(YTM, "bestaudio", rules),
            fr.FILENAME_FORMAT_PRESETS["artist_track_title"] + ".%(ext)s",
        )
        self.assertEqual(self._flags(YT, "bv*+ba/b", rules), "%(uploader)s - %(title)s.%(ext)s")
        self.assertEqual(self._flags(YT, "bestaudio", rules), "%(title)s.%(ext)s")

    def test_forced_title_follows_the_effective_choice(self):
        from ytget_gui.settings import AppSettings
        from ytget_gui.workers import download_worker as dw

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            s = AppSettings(DATA_DIR=root / "data", DOWNLOADS_DIR=root / "dl")
            s.COOKIES_FROM_BROWSER = ""
            s.FILENAME_RULES = fr.normalise_rules({"youtube_video": {"format": "uploader_title"}})
            worker = dw.DownloadWorker({"url": YT, "title": "Shown", "format_code": "bv*+ba/b"}, s)
            flags = worker._output_flags(is_playlist=False, is_audio=False,
                                         is_yt_music=False, is_flat=False)
            # An overridden slot must not be replaced by the queue title.
            self.assertTrue(flags[flags.index("-o") + 1].endswith("%(uploader)s - %(title)s.%(ext)s"))
            worker2 = dw.DownloadWorker({"url": OTHER, "title": "Shown", "format_code": "bv*+ba/b"}, s)
            flags2 = worker2._output_flags(is_playlist=False, is_audio=False,
                                           is_yt_music=False, is_flat=False)
            self.assertTrue(flags2[flags2.index("-o") + 1].endswith("Shown.%(ext)s"))


if __name__ == "__main__":
    unittest.main()
