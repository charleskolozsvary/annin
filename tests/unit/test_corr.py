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

class TestApplySourceOffset:    
    class TestHappyPath:
        def test_zero_offset_returns_unchanged_dict(self):
            boxes = make_boxes(0, 1, 2, 3, 4)
            original_boxes = dict(boxes)
            result, empty = applySourceOffset(0, boxes)
            assert empty is None
            assert result == original_boxes

        def test_basic_offset_shifts_keys(self):
            """source_offset=2, pages 0-4 → pages 0-2 hold what pages 2-4 held."""
            boxes = make_boxes(0, 1, 2, 3, 4)
            old = dict(boxes)
            result, now_empty = applySourceOffset(2, boxes)
            assert result[0] == old[2]
            assert result[1] == old[3]
            assert result[2] == old[4]

        def test_tail_pages_are_discarded(self):
            """Pages 3 and 4 (from the original) must no longer exist."""
            boxes = make_boxes(0, 1, 2, 3, 4)
            result, _ = applySourceOffset(2, boxes)
            assert 3 not in result
            assert 4 not in result

        def test_offset_of_one(self):
            boxes = make_boxes(0, 1, 2)
            old = dict(boxes)
            result, _ = applySourceOffset(1, boxes)
            assert result[0] == old[1]
            assert result[1] == old[2]
            assert 2 not in result

        def test_offset_equals_max_page(self):
            """Only the last page survives, mapped to index 0."""
            boxes = make_boxes(0, 1, 2)
            old = dict(boxes)
            result, _ = applySourceOffset(2, boxes)
            assert result[0] == old[2]
            assert 1 not in result
            assert 2 not in result

        def test_returns_same_dict_object(self):
            """Function mutates and returns the same dict (not a copy)."""
            boxes = make_boxes(0, 1, 2)
            result, _ = applySourceOffset(1, boxes)
            assert result is boxes

    class TestEmptyPageHandling:
        def test_gap_in_source_creates_empty_page_entry(self):
            """Page 3 is missing in source; after offset=2 it becomes page 1."""
            boxes = make_boxes(0, 1, 2, 4)  # page 3 absent
            result, now_empty = applySourceOffset(2, boxes)
            assert 1 not in result          # shifted gap should be absent
            assert 1 in now_empty           # and reported

        def test_now_empty_pages_set_is_returned(self):
            boxes = make_boxes(0, 1, 3)     # page 2 absent
            _, now_empty = applySourceOffset(1, boxes)
            assert isinstance(now_empty, set)

        def test_no_gaps_returns_empty_set(self):
            boxes = make_boxes(0, 1, 2, 3)
            _, now_empty = applySourceOffset(1, boxes)
            assert now_empty == set()

    class TestEdgeCases:
        def test_offset_out_of_range_calls_sys_exit(self):
            boxes = make_boxes(0, 1, 2)
            with patch("sys.exit") as mock_exit:
                applySourceOffset(5, boxes)
                mock_exit.assert_called_once_with(1)

        def test_offset_out_of_range_assertion_error(self):
            """An offset between 0 and max_page that is simply absent triggers
            a different code-path: the assertion fires because offset <= max_page."""
            boxes = {0: {}, 2: {}}   # key 1 deliberately absent
            with pytest.raises(AssertionError):
                applySourceOffset(1, boxes)

        def test_single_page_zero_offset(self):
            boxes = make_boxes(0)
            result, empty = applySourceOffset(0, boxes)
            assert 0 in result
            assert empty is None

        def test_single_page_offset_equals_only_page(self):
            """offset == max_page == 0 would be zero-offset (handled above)."""
            boxes = make_boxes(0, 1)
            old = dict(boxes)
            result, _ = applySourceOffset(1, boxes)
            assert result[0] == old[1]
            assert 1 not in result

        def test_large_offset(self):
            boxes = make_boxes(*range(100))
            old = dict(boxes)
            result, _ = applySourceOffset(50, boxes)
            for i in range(50):
                assert result[i] == old[i + 50]
            for i in range(50, 100):
                assert i not in result
