"""Tests for ytget_gui.workers.log_buffer.

Covers the bounded-memory guarantees and the non-ASCII byte accounting fix.
Note that drain() returns *coalesced* entries: consecutive lines sharing a
colour are merged into one newline-joined entry, so these tests count lines
rather than entries where the distinction matters.
"""

import unittest

from ytget_gui.workers.log_buffer import LogBuffer, coalesce

# Six characters, twelve UTF-8 bytes (Arabic). Built from code points so this
# file stays pure ASCII.
MULTIBYTE = "".join(chr(c) for c in (0x062F, 0x0627, 0x0646, 0x0644, 0x0648, 0x062F))


def drained_lines(buf):
    """All log lines a single drain() returned, flattened."""
    lines = []
    for text, _colour in buf.drain():
        lines.extend(text.split("\n"))
    return lines


class LogBufferTests(unittest.TestCase):
    def test_drain_returns_lines_then_empties(self):
        buf = LogBuffer()
        buf.add("one", "#fff")
        buf.add("two", "#fff")
        self.assertEqual(drained_lines(buf), ["one", "two"])
        self.assertEqual(buf.drain(), [])

    def test_distinct_colours_stay_separate(self):
        buf = LogBuffer()
        buf.add("a", "#fff")
        buf.add("b", "#000")
        entries = buf.drain()
        self.assertEqual(entries, [("a", "#fff"), ("b", "#000")])

    def test_ignores_empty_text(self):
        buf = LogBuffer()
        buf.add("", "#fff")
        self.assertEqual(buf.drain(), [])

    def test_len_and_bool(self):
        buf = LogBuffer()
        self.assertFalse(buf)
        self.assertEqual(len(buf), 0)
        buf.add("x", "#fff")
        self.assertTrue(buf)
        self.assertEqual(len(buf), 1)

    def test_caps_total_entries_dropping_oldest(self):
        buf = LogBuffer(max_entries=10, trim_to=5)
        for i in range(100):
            buf.add("line %d" % i, "#fff")
        # Trimming keeps the buffer bounded regardless of how much is written.
        self.assertLessEqual(len(buf), 10)
        lines = drained_lines(buf)
        self.assertIn("line 99", lines)
        self.assertNotIn("line 0", lines)

    def test_clear(self):
        buf = LogBuffer()
        buf.add("x", "#fff")
        buf.clear()
        self.assertEqual(buf.drain(), [])
        self.assertEqual(len(buf), 0)

    def test_drain_respects_flush_entry_budget(self):
        buf = LogBuffer(max_entries=1000, trim_to=900, max_flush_entries=5)
        for i in range(20):
            buf.add("line %d" % i, "#fff")
        self.assertEqual(len(drained_lines(buf)), 5)
        # The remainder stays queued rather than being lost.
        self.assertTrue(buf.drain())

    def test_oversized_line_is_truncated_not_dropped(self):
        buf = LogBuffer(max_flush_bytes=256)
        buf.add("x" * 10_000, "#fff")
        lines = drained_lines(buf)
        self.assertEqual(len(lines), 1)
        self.assertLessEqual(len(lines[0].encode("utf-8")), 256)

    def test_multibyte_budget_counts_bytes_not_characters(self):
        # Regression: size was measured with len(text), so a 3-4 byte per
        # character line under-reported its cost and the byte budget could be
        # overshot several times over. Same character count, more bytes, so
        # strictly fewer lines must fit in an identical budget.
        ascii_buf = LogBuffer(max_entries=1000, trim_to=900, max_flush_bytes=60)
        wide_buf = LogBuffer(max_entries=1000, trim_to=900, max_flush_bytes=60)
        for _ in range(30):
            ascii_buf.add("aaaaaa", "#fff")
            wide_buf.add(MULTIBYTE, "#fff")
        self.assertGreater(len(drained_lines(ascii_buf)), len(drained_lines(wide_buf)))

    def test_byte_budget_is_enforced(self):
        buf = LogBuffer(max_entries=1000, trim_to=900, max_flush_bytes=64)
        for _ in range(50):
            buf.add(MULTIBYTE, "#fff")
        drained = buf.drain()
        self.assertTrue(drained)
        total = sum(len(text.encode("utf-8")) for text, _ in drained)
        # One line may always exceed the budget; beyond that it must hold.
        self.assertLessEqual(total, 64 + len(MULTIBYTE.encode("utf-8")))

    def test_flush_threshold_is_exposed(self):
        buf = LogBuffer(max_flush_entries=7)
        self.assertEqual(buf.flush_threshold, 7)

    def test_trim_to_cannot_exceed_max_entries(self):
        buf = LogBuffer(max_entries=5, trim_to=500)
        for i in range(50):
            buf.add("line %d" % i, "#fff")
        self.assertLessEqual(len(buf), 5)


class CoalesceTests(unittest.TestCase):
    def test_groups_consecutive_same_colour(self):
        merged = coalesce([("a", "#fff"), ("b", "#fff"), ("c", "#000")])
        self.assertEqual(merged, [("a\nb", "#fff"), ("c", "#000")])

    def test_alternating_colours_are_not_merged(self):
        entries = [("a", "#fff"), ("b", "#000"), ("c", "#fff")]
        self.assertEqual(coalesce(entries), entries)

    def test_empty(self):
        self.assertEqual(coalesce([]), [])

    def test_single(self):
        self.assertEqual(coalesce([("a", "#fff")]), [("a", "#fff")])


if __name__ == "__main__":
    unittest.main()
