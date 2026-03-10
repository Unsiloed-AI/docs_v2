"""Tests for doc_sync.mdx.writer."""
from __future__ import annotations

from pathlib import Path

import pytest

from doc_sync.mdx.writer import FileResult, _count_changes, _unified_diff, write_results


class TestCountChanges:
    def test_no_changes(self):
        added, removed = _count_changes("hello\nworld", "hello\nworld")
        assert added == 0
        assert removed == 0

    def test_added_line(self):
        added, removed = _count_changes("line1", "line1\nline2")
        assert added == 1
        assert removed == 0

    def test_removed_line(self):
        added, removed = _count_changes("line1\nline2", "line1")
        assert added == 0
        assert removed == 1

    def test_changed_line(self):
        added, removed = _count_changes("old line", "new line")
        assert added == 1
        assert removed == 1


class TestUnifiedDiff:
    def test_empty_diff_when_identical(self, tmp_path):
        path = tmp_path / "test.mdx"
        diff = _unified_diff("same\ncontent\n", "same\ncontent\n", path)
        assert diff == ""

    def test_diff_shows_changes(self, tmp_path):
        path = tmp_path / "test.mdx"
        diff = _unified_diff("old content\n", "new content\n", path)
        assert "-old content" in diff
        assert "+new content" in diff

    def test_diff_includes_filename(self, tmp_path):
        path = tmp_path / "myfile.mdx"
        diff = _unified_diff("a\n", "b\n", path)
        assert "myfile.mdx" in diff


class TestWriteResults:
    def _make_result(self, tmp_path: Path, original: str, updated: str) -> FileResult:
        path = tmp_path / "api-reference" / "test.mdx"
        path.parent.mkdir(parents=True)
        path.write_text(original, encoding="utf-8")
        return FileResult(
            path=path,
            original=original,
            updated=updated,
            operation_key="POST /test",
        )

    def test_writes_file_when_changed(self, tmp_path):
        result = self._make_result(tmp_path, "old content", "new content")
        write_results([result], dry_run=False, show_diff=False)
        assert result.path.read_text() == "new content"

    def test_dry_run_does_not_write(self, tmp_path):
        result = self._make_result(tmp_path, "original", "updated")
        write_results([result], dry_run=True, show_diff=False)
        assert result.path.read_text() == "original"

    def test_unchanged_file_not_rewritten(self, tmp_path):
        result = self._make_result(tmp_path, "same content", "same content")
        mtime_before = result.path.stat().st_mtime
        write_results([result], dry_run=False, show_diff=False)
        mtime_after = result.path.stat().st_mtime
        assert mtime_before == mtime_after

    def test_multiple_results(self, tmp_path):
        r1 = self._make_result(tmp_path, "a", "b")
        # Create second file in a different subdir
        path2 = tmp_path / "api-reference" / "other.mdx"
        path2.write_text("x", encoding="utf-8")
        r2 = FileResult(path=path2, original="x", updated="y", operation_key="GET /other")

        write_results([r1, r2], dry_run=False, show_diff=False)

        assert r1.path.read_text() == "b"
        assert r2.path.read_text() == "y"
