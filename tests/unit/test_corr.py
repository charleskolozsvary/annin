import sys
import pytest
import pymupdf
from unittest.mock import patch, MagicMock

from texpdfedits.corr import applySourceOffset
from texpdfedits.corr import groupOverlappingCorrections

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_correction(index, start, end, latex_snippet):
    corr = MagicMock()
    corr.index = index
    corr.snippet_source_positions = (start, end)
    corr.latex_snippet = latex_snippet
    corr.group = None
    return corr

def make_boxes(*page_nos):
    """Return a tex_word_boxes dict with a distinct sentinel per page."""
    return {p: {"word": pymupdf.Rect(0, 0, p, p)} for p in page_nos}

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGroupOverlappingCorrections:
    class TestHappyPath:
        def test_empty_corrections_returns_empty(self):
            groups = groupOverlappingCorrections([], "anything")
            assert groups == ([], [])

        def test_no_overlaps_returns_empty_groups(self):
            tex = "hello world foo bar"
            c0 = make_correction(0, 0, 5, "hello")   # "hello"
            c1 = make_correction(1, 6, 11, "world")  # "world"
            groups = groupOverlappingCorrections([c0, c1], tex)
            assert groups == []

        def test_two_overlapping_corrections_grouped(self):
            tex = "hello world"
            c0 = make_correction(0, 0, 7, "hello w")   # overlaps with c1
            c1 = make_correction(1, 5, 11, "world")
            groups = groupOverlappingCorrections([c0, c1], tex)
            assert [0, 1] in groups

        def test_group_assigned_to_corrections(self):
            tex = "hello world"
            c0 = make_correction(0, 0, 7, "hello w")
            c1 = make_correction(1, 5, 11, "world")
            groupOverlappingCorrections([c0, c1], tex)
            assert c0.group == [0, 1]
            assert c1.group == [0, 1]

        def test_three_corrections_all_overlapping(self):
            tex = "abcdefghij"
            c0 = make_correction(0, 0, 5, "abcde")
            c1 = make_correction(1, 3, 7, "defg")
            c2 = make_correction(2, 6, 10, "ghij")
            groups = groupOverlappingCorrections([c0, c1, c2], tex)
            assert len(groups) == 1
            assert set(groups[0]) == {0, 1, 2}

        def test_two_separate_overlap_groups(self):
            tex = "abcde     vwxyz"
            c0 = make_correction(0, 0, 3, "abc")
            c1 = make_correction(1, 2, 5, "cde")
            c2 = make_correction(2, 10, 13, "vwx")
            c3 = make_correction(3, 12, 15, "xyz")
            groups = groupOverlappingCorrections([c0, c1, c2, c3], tex)
            assert len(groups) == 2
            assert set(groups[0]) == {0, 1}
            assert set(groups[1]) == {2, 3}

    class TestUpdateSnippet:
        def test_update_snippet_called_with_union_span(self):
            tex = "hello world"
            c0 = make_correction(0, 0, 7, "hello w")
            c1 = make_correction(1, 5, 11, "world")
            groupOverlappingCorrections([c0, c1], tex)
            c0.updateSnippet.assert_called_once_with((0, 11), "hello world")
            c1.updateSnippet.assert_called_once_with((0, 11), "hello world")

        def test_update_snippet_not_called_when_disabled(self):
            tex = "hello world"
            c0 = make_correction(0, 0, 7, "hello w")
            c1 = make_correction(1, 5, 11, "world")
            groupOverlappingCorrections([c0, c1], tex, merge_overlapping_snippets=False)
            c0.updateSnippet.assert_not_called()
            c1.updateSnippet.assert_not_called()

        def test_no_overlap_update_snippet_not_called(self):
            tex = "hello world foo"
            c0 = make_correction(0, 0, 5, "hello")
            c1 = make_correction(1, 6, 11, "world")
            groupOverlappingCorrections([c0, c1], tex)
            c0.updateSnippet.assert_not_called()
            c1.updateSnippet.assert_not_called()

    class TestEdgeCases:
        def test_single_correction_no_group(self):
            tex = "hello world"
            c0 = make_correction(0, 0, 5, "hello")
            groups = groupOverlappingCorrections([c0], tex)
            assert groups == []

        def test_snippet_not_in_span_calls_sys_exit(self):
            tex = "hello world"
            # latex_snippet is something that won't appear in the spanning text
            c0 = make_correction(0, 0, 7, "hello w")
            c1 = make_correction(1, 5, 11, "ZZZZZZ")  # not in "hello world"
            with patch("sys.exit") as mock_exit:
                groupOverlappingCorrections([c0, c1], tex)
            mock_exit.assert_called_once_with(1)

        def test_touching_spans_are_grouped(self):
            """Touching spans (end == next start) are intentionally grouped
            to prevent comments from being inserted at the same character."""
            tex = "helloworld"
            c0 = make_correction(0, 0, 5, "hello")
            c1 = make_correction(1, 5, 10, "world")
            groups = groupOverlappingCorrections([c0, c1], tex)
            assert [0, 1] in groups
