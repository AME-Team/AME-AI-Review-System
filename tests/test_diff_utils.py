from __future__ import annotations

from ame_ai_review_system.diff_utils import compact_diff


def test_compact_diff_removes_index_metadata() -> None:
    diff = (
        "diff --git a/foo.py b/foo.py\n"
        "index 1234567..abcdefg 100644\n"
        "--- a/foo.py\n"
        "+++ b/foo.py\n"
        "@@ -1,3 +1,4 @@\n"
        " import os\n"
        "+import sys\n"
        " x = 1\n"
    )
    result = compact_diff(diff)
    assert "index 1234567..abcdefg 100644" not in result
    assert "diff --git" in result
    assert "+++ b/foo.py" in result
    assert "+import sys" in result


def test_compact_diff_removes_binary_files_marker() -> None:
    diff = (
        "diff --git a/data.bin b/data.bin\n"
        "Binary files a/data.bin and b/data.bin differ\n"
        "--- a/data.bin\n"
        "+++ b/data.bin\n"
    )
    result = compact_diff(diff)
    assert "Binary files" not in result
    assert "differ" not in result


def test_compact_diff_removes_rename_metadata() -> None:
    diff = (
        "diff --git a/old.py b/new.py\n"
        "similarity index 90%\n"
        "rename from old.py\n"
        "rename to new.py\n"
        "@@ -1,3 +1,3 @@\n"
        " x = 1\n"
    )
    result = compact_diff(diff)
    assert "similarity index" not in result
    assert "rename from" not in result
    assert "rename to" not in result


def test_compact_diff_preserves_semantic_structure() -> None:
    diff = (
        "--- a/foo.py\n+++ b/foo.py\n@@ -1,3 +1,4 @@\n import os\n+import sys\n x = 1\n"
    )
    result = compact_diff(diff)
    assert "--- a/foo.py" in result
    assert "+++ b/foo.py" in result
    assert "@@ -1,3 +1,4 @@" in result
    assert "+import sys" in result


def test_compact_diff_collapses_blank_lines() -> None:
    diff = "line1\n\n\n\nline2\n"
    result = compact_diff(diff)
    lines = result.splitlines()
    blank_count = sum(1 for line in lines if not line.strip())
    assert blank_count <= 1


def test_compact_diff_empty_input() -> None:
    assert not compact_diff("")


def test_compact_diff_no_metadata() -> None:
    diff = "--- a/foo.py\n+++ b/foo.py\n@@ -1,1 +1,1 @@\n-x\n+y\n"
    result = compact_diff(diff)
    assert result.strip() == diff.strip()
