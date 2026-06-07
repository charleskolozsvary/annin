import unittest
from pathlib import Path
from unittest.mock import mock_open, patch

from texpdfedits.sync import build_line_map, _read_balanced

from contextlib import contextmanager, ExitStack

@contextmanager
def make_patch(content: str, exists: bool = True):
    with ExitStack() as stack:
        stack.enter_context(patch("pathlib.Path.exists", return_value=exists))
        stack.enter_context(patch("builtins.open", mock_open(read_data=content)))
        yield

class TestReadBalanced(unittest.TestCase):
    def _test_delim(self, string: str, delimiters: tuple[str, str], expected: str):
        span = _read_balanced(string, delimiters)
        assert string[span[0]:span[1]] == expected
        
    def test_empty_string(self):
        assert _read_balanced('', ('', '')) is None
        
    def test_empty_string_two(self):
        assert _read_balanced('', ('any', 'thing')) is None
        
    def test_single_delim_start_end(self):
        string = '[]'
        delimiters = ('[', ']')
        self._test_delim(string, delimiters, string)
        
    def test_single_delim_mid_end(self):
        string = ' and then there was [ a thing that ]'
        delimiters = ('[', ']')
        self._test_delim(string, delimiters, '[ a thing that ]')
        
    def test_single_delim_start_mid(self):
        string = '[and then there was ] a thing that ]'
        delimiters = ('[', ']')
        self._test_delim(string, delimiters, '[and then there was ]')
        
    def test_multi_delim_start_end(self):
        string = r'\beginwhat\'s up\end'
        delimiters = (r'\begin', r'\end')
        self._test_delim(string, delimiters, string)
        
    def test_multi_delim_mid_end(self):
        string = r'beginwha\begint\'s up\end'
        delimiters = (r'\begin', r'\end')
        self._test_delim(string, delimiters, r'\begint\'s up\end')
        
    def test_multi_delim_start_mid(self):
        string = r'\beginwhat\'s up\end and then there was'
        delimiters = (r'\begin', r'\end')
        self._test_delim(string, delimiters, r'\beginwhat\'s up\end')
        
    def test_multi_delim_mid_mid(self):
        string = r'how are you doing \beginwhat\'s up\end and then there was'
        delimiters = (r'\begin', r'\end')
        self._test_delim(string, delimiters, r'\beginwhat\'s up\end')

    def test_single_more_depth(self):
        string = 'and then [there was [a []] thing that ]'
        delimiters = ('[', ']')
        self._test_delim(string, delimiters, '[there was [a []] thing that ]')

    def test_multi_more_depth(self):
        string = 'and then [[(there was [[(a [[()]])]] thing that )]]'
        delimiters = ('[[(', ')]]')
        self._test_delim(string, delimiters, '[[(there was [[(a [[()]])]] thing that )]]')

    def test_multi_more_depth_runout(self):
        string = 'and then [[(there was [[(a [[()]])]] thing that '
        delimiters = ('[[(', ')]]')
        assert _read_balanced(string, delimiters) is None

    def test_single_more_depth_runout(self):
        string = 'and then [there was [a []] thing that and then there was a place that we could '
        delimiters = ('[', ']')
        assert _read_balanced(string, delimiters) is None

class TestBuildLineMapBasic(unittest.TestCase):
    """Happy-path cases covering typical file contents."""

    def test_single_line_with_newline(self):
        # "hello\n" → line 1 spans [0, 6)
        with make_patch("hello\n"):
            result = build_line_map(Path("fake.txt"))
        self.assertEqual(result, {1: 0})

    def test_two_lines_uniform_length(self):
        # "foo\nbar\n"
        # line 1: [0, 4)   ("foo\n")
        # line 2: [4, 8)   ("bar\n")
        with make_patch("foo\nbar\n"):
            result = build_line_map(Path("fake.txt"))
        self.assertEqual(result, {
            1: 0,
            2: 4,
        })

    def test_three_lines_varying_length(self):
        # "a\nbb\nccc\n"
        # line 1: [0,  2)   ("a\n")
        # line 2: [2,  5)   ("bb\n")
        # line 3: [5, 10)   ("ccc\n")
        with make_patch("a\nbb\nccc\n"):
            result = build_line_map(Path("fake.txt"))
        self.assertEqual(result, {
            1: 0,
            2: 2,
            3: 5,
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
        self.assertEqual(result, {1: 0})

    def test_multiple_lines_no_trailing_newline(self):
        # "foo\nbar" — second line has no \n
        # line 1: [0, 4)   ("foo\n")
        # line 2: [4, 7)   ("bar")
        with make_patch("foo\nbar"):
            result = build_line_map(Path("fake.txt"))
        self.assertEqual(result, {
            1: 0,
            2: 4,
        })

    def test_blank_line_in_middle(self):
        # "a\n\nb\n"
        # line 1: [0, 2)   ("a\n")
        # line 2: [2, 3)   ("\n")
        # line 3: [3, 5)   ("b\n")
        with make_patch("a\n\nb\n"):
            result = build_line_map(Path("fake.txt"))
        self.assertEqual(result, {
            1: 0,
            2: 2,
            3: 3,
        })

    def test_only_newlines(self):
        # "\n\n\n" — three blank lines
        # line 1: [0, 1)
        # line 2: [1, 2)
        # line 3: [2, 3)
        with make_patch("\n\n\n"):
            result = build_line_map(Path("fake.txt"))
        self.assertEqual(result, {
            1: 0,
            2: 1,
            3: 2,
        })

    def test_line_of_only_spaces(self):
        # "   \nfoo\n"
        # line 1: [0, 4)   ("   \n")
        # line 2: [4, 8)   ("foo\n")
        with make_patch("   \nfoo\n"):
            result = build_line_map(Path("fake.txt"))
        self.assertEqual(result, {
            1: 0,
            2: 4,
        })


        

