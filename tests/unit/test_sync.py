import unittest
from pathlib import Path
from unittest.mock import mock_open, patch

from texpdfedits.sync import build_line_map

from contextlib import contextmanager, ExitStack

@contextmanager
def make_patch(content: str, exists: bool = True):
    with ExitStack() as stack:
        stack.enter_context(patch("pathlib.Path.exists", return_value=exists))
        stack.enter_context(patch("builtins.open", mock_open(read_data=content)))
        yield

class TestBuildLineMapBasic(unittest.TestCase):
    """Happy-path cases covering typical file contents."""

    def test_single_line_with_newline(self):
        # "hello\n" → line 1 spans [0, 6)
        with make_patch("hello\n"):
            result = build_line_map(Path("fake.txt"))
        self.assertEqual(result, {1: (0, 6)})

    def test_two_lines_uniform_length(self):
        # "foo\nbar\n"
        # line 1: [0, 4)   ("foo\n")
        # line 2: [4, 8)   ("bar\n")
        with make_patch("foo\nbar\n"):
            result = build_line_map(Path("fake.txt"))
        self.assertEqual(result, {
            1: (0, 4),
            2: (4, 8),
        })

    def test_three_lines_varying_length(self):
        # "a\nbb\nccc\n"
        # line 1: [0,  2)   ("a\n")
        # line 2: [2,  5)   ("bb\n")
        # line 3: [5, 10)   ("ccc\n")
        with make_patch("a\nbb\nccc\n"):
            result = build_line_map(Path("fake.txt"))
        self.assertEqual(result, {
            1: (0, 2),
            2: (2, 5),
            3: (5, 9),
        })

    def test_keys_are_one_indexed(self):
        with make_patch("x\ny\n"):
            result = build_line_map(Path("fake.txt"))
        self.assertIn(1, result)
        self.assertIn(2, result)
        self.assertNotIn(0, result)


class TestBuildLineMapEdgeCases(unittest.TestCase):
    """Edge cases: empty files, missing trailing newline, whitespace lines."""

    def test_empty_file(self):
        with make_patch(""):
            result = build_line_map(Path("fake.txt"))
        self.assertEqual(result, {})

    def test_single_line_no_trailing_newline(self):
        # "hello" (no \n) → line 1 spans [0, 5)
        with make_patch("hello"):
            result = build_line_map(Path("fake.txt"))
        self.assertEqual(result, {1: (0, 5)})

    def test_multiple_lines_no_trailing_newline(self):
        # "foo\nbar" — second line has no \n
        # line 1: [0, 4)   ("foo\n")
        # line 2: [4, 7)   ("bar")
        with make_patch("foo\nbar"):
            result = build_line_map(Path("fake.txt"))
        self.assertEqual(result, {
            1: (0, 4),
            2: (4, 7),
        })

    def test_blank_line_in_middle(self):
        # "a\n\nb\n"
        # line 1: [0, 2)   ("a\n")
        # line 2: [2, 3)   ("\n")
        # line 3: [3, 5)   ("b\n")
        with make_patch("a\n\nb\n"):
            result = build_line_map(Path("fake.txt"))
        self.assertEqual(result, {
            1: (0, 2),
            2: (2, 3),
            3: (3, 5),
        })

    def test_only_newlines(self):
        # "\n\n\n" — three blank lines
        # line 1: [0, 1)
        # line 2: [1, 2)
        # line 3: [2, 3)
        with make_patch("\n\n\n"):
            result = build_line_map(Path("fake.txt"))
        self.assertEqual(result, {
            1: (0, 1),
            2: (1, 2),
            3: (2, 3),
        })

    def test_line_of_only_spaces(self):
        # "   \nfoo\n"
        # line 1: [0, 4)   ("   \n")
        # line 2: [4, 8)   ("foo\n")
        with make_patch("   \nfoo\n"):
            result = build_line_map(Path("fake.txt"))
        self.assertEqual(result, {
            1: (0, 4),
            2: (4, 8),
        })


class TestBuildLineMapSpanProperties(unittest.TestCase):
    """Invariants that must hold for any valid output."""

    def _spans_are_valid(self, content: str):
        with make_patch(content):
            return build_line_map(Path("fake.txt"))

    def test_spans_are_contiguous(self):
        """End of line N must equal start of line N+1."""
        result = self._spans_are_valid("one\ntwo\nthree\n")
        line_numbers = sorted(result)
        for i in range(len(line_numbers) - 1):
            cur  = line_numbers[i]
            nxt  = line_numbers[i + 1]
            self.assertEqual(result[cur][1], result[nxt][0],
                             f"Gap between line {cur} and {nxt}")

    def test_spans_are_non_empty(self):
        """Every span must cover at least one character."""
        result = self._spans_are_valid("a\nbb\nccc\n")
        for line_no, (start, end) in result.items():
            self.assertGreater(end, start,
                               f"Line {line_no} has empty span")

    def test_first_span_starts_at_zero(self):
        result = self._spans_are_valid("anything\n")
        self.assertEqual(result[1][0], 0)

    def test_last_span_ends_at_total_length(self):
        content = "foo\nbar\nbaz\n"
        result = self._spans_are_valid(content)
        last_line = max(result)
        self.assertEqual(result[last_line][1], len(content))

    def test_span_length_matches_line_length(self):
        """Each span's width must equal the length of the raw line string."""
        content = "short\nmedium line\nx\n"
        result = self._spans_are_valid(content)
        lines = content.splitlines(keepends=True)
        for i, line in enumerate(lines, start=1):
            start, end = result[i]
            self.assertEqual(end - start, len(line),
                             f"Line {i}: span width {end - start} != len {len(line)}")


        

