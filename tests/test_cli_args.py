"""Tests for ytget_gui.utils.cli_args argument parsing and blocklisting.

Both helpers signal rejection by raising ValueError so the GUI can surface the
reason to the user; they do not silently drop tokens.
"""

import unittest

from ytget_gui.utils import cli_args


class SplitArgumentsTests(unittest.TestCase):
    def test_splits_on_whitespace(self):
        parsed = cli_args.split_arguments("--a 1 --b 2")
        self.assertEqual(parsed, ["--a", "1", "--b", "2"])

    def test_respects_quotes(self):
        parsed = cli_args.split_arguments('--output "my file.mp4"')
        self.assertEqual(parsed, ["--output", "my file.mp4"])

    def test_empty_input(self):
        self.assertEqual(cli_args.split_arguments(""), [])
        self.assertEqual(cli_args.split_arguments("   "), [])

    def test_unbalanced_quote_is_rejected_clearly(self):
        with self.assertRaises(ValueError) as ctx:
            cli_args.split_arguments('--output "unclosed')
        self.assertIn("quote", str(ctx.exception).lower())

    def test_control_characters_are_rejected(self):
        for raw in ("--a\n--exec evil", "--a\rb", "--a\0b"):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    cli_args.split_arguments(raw)

    def test_windows_mode_keeps_backslashes(self):
        # Backslash is a path separator on Windows, not an escape character.
        parsed = cli_args.split_arguments(r"--paths C:\Users\me", windows=True)
        self.assertEqual(parsed, ["--paths", r"C:\Users\me"])


class ParseYtdlpArgsTests(unittest.TestCase):
    def test_keeps_safe_arguments(self):
        parsed = cli_args.parse_ytdlp_args("--sleep-interval 15")
        self.assertEqual(parsed, ["--sleep-interval", "15"])

    def test_blocked_flags_are_rejected(self):
        for flag in ("--exec", "--batch-file", "--simulate", "--print", "--update"):
            with self.subTest(flag=flag):
                with self.assertRaises(ValueError):
                    cli_args.parse_ytdlp_args(flag)

    def test_blocked_flag_with_attached_value_is_rejected(self):
        with self.assertRaises(ValueError):
            cli_args.parse_ytdlp_args("--exec=rm -rf /")

    def test_short_aliases_are_rejected(self):
        for flag in ("-s", "-j", "-g", "-U"):
            with self.subTest(flag=flag):
                with self.assertRaises(ValueError):
                    cli_args.parse_ytdlp_args(flag)

    def test_clustered_short_aliases_are_rejected(self):
        # "-qj" hides -q and -j; a naive membership test would miss it.
        with self.assertRaises(ValueError):
            cli_args.parse_ytdlp_args("-qj")

    def test_unique_prefix_abbreviations_are_rejected(self):
        # yt-dlp's optparse accepts unambiguous prefixes, so "--exe" still
        # reaches --exec.
        with self.assertRaises(ValueError):
            cli_args.parse_ytdlp_args("--exe")

    def test_bare_double_dash_is_rejected(self):
        with self.assertRaises(ValueError):
            cli_args.parse_ytdlp_args("--")

    def test_progress_template_is_rejected(self):
        # The worker owns --progress-template; overriding it breaks progress
        # reporting for the whole queue.
        with self.assertRaises(ValueError):
            cli_args.parse_ytdlp_args("--progress-template foo")

    def test_blocklist_is_not_empty(self):
        self.assertTrue(cli_args.BLOCKED)

    def test_empty_input(self):
        self.assertEqual(cli_args.parse_ytdlp_args(""), [])


if __name__ == "__main__":
    unittest.main()
