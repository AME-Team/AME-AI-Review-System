from __future__ import annotations

from pathlib import Path

import pytest
from ame_ai_review_system.mermaid_check import (
    _check_line as check_line,
)
from ame_ai_review_system.mermaid_check import (
    check_file,
    check_files,
    format_issues,
    main,
)

# -------------------------------------------------------
# _check_line unit tests
# -------------------------------------------------------


def test_empty_line_no_issues() -> None:
    assert check_line("test.md", 1, "") == []


def test_plain_text_no_issues() -> None:
    assert check_line("test.md", 1, "A --> B") == []
    assert check_line("test.md", 1, "    C[hello]") == []


def test_subgraph_parens_detected() -> None:
    issues = check_line("test.md", 1, "    subgraph S1 [Gate 1 (pre-commit)]")
    assert len(issues) == 1
    assert "Subgraph title contains" in issues[0].message
    assert "subgraph S1" in issues[0].message


def test_subgraph_braces_detected() -> None:
    issues = check_line("test.md", 1, "    subgraph S1 [Gate {braced}]")
    assert len(issues) == 1


def test_subgraph_brackets_detected() -> None:
    issues = check_line("test.md", 1, "    subgraph S1 [Gate [inner]]")
    assert len(issues) == 1


def test_subgraph_simple_no_issue() -> None:
    assert check_line("test.md", 1, "    subgraph S1 [Simple Title]") == []


def test_subgraph_bare_quote_detected() -> None:
    issues = check_line("test.md", 1, '    subgraph S1 "Gate (with parens)"')
    assert len(issues) == 1
    assert "bare quote" in issues[0].message.lower()
    assert "subgraph S1" in issues[0].message


def test_subgraph_angle_bracket_quoted_no_issue() -> None:
    assert check_line("test.md", 1, '    subgraph S1 ["Gate (with parens)"]') == []


def test_node_square_parens_detected() -> None:
    issues = check_line("test.md", 1, "    A[hello (world)]")
    assert len(issues) == 1
    assert "Node label" in issues[0].message


def test_node_square_no_parens_ok() -> None:
    assert check_line("test.md", 1, "    A[hello world]") == []


def test_node_brace_braces_detected() -> None:
    issues = check_line("test.md", 1, "    A{hello {inner}}")
    assert len(issues) == 1
    assert "Rhombus node" in issues[0].message or "braces" in issues[0].message.lower()


def test_node_brace_simple_ok() -> None:
    assert check_line("test.md", 1, "    A{decision}") == []


# -------------------------------------------------------
# check_file integration tests
# -------------------------------------------------------


def test_check_file_no_mermaid_blocks(tmp_path: Path) -> None:
    md = tmp_path / "no_mermaid.md"
    md.write_text("# Header\n\nPlain text.\n", encoding="utf-8")
    assert check_file(str(md)) == []


def test_check_file_valid_mermaid(tmp_path: Path) -> None:
    md = tmp_path / "valid.md"
    md.write_text(
        "```mermaid\ngraph TD\n    A[hello] --> B[world]\n```\n",
        encoding="utf-8",
    )
    assert check_file(str(md)) == []


def test_check_file_subgraph_error(tmp_path: Path) -> None:
    md = tmp_path / "bad.md"
    md.write_text(
        "```mermaid\ngraph TD\n    subgraph S1 [Gate (bad)]\n        A --> B\n    end\n```\n",
        encoding="utf-8",
    )
    issues = check_file(str(md))
    assert len(issues) == 1
    assert "bad.md" in issues[0].path
    assert issues[0].line == 3


def test_check_file_bare_quote_subgraph_error(tmp_path: Path) -> None:
    md = tmp_path / "bare_quote.md"
    md.write_text(
        '```mermaid\ngraph TD\n    subgraph S1 "Gate (bad)"\n        A --> B\n    end\n```\n',
        encoding="utf-8",
    )
    issues = check_file(str(md))
    assert len(issues) == 1
    assert "bare_quote.md" in issues[0].path
    assert issues[0].line == 3
    assert "bare quote" in issues[0].message.lower()


def test_check_file_multiple_blocks(tmp_path: Path) -> None:
    md = tmp_path / "multi.md"
    md.write_text(
        "```mermaid\ngraph TD\n    A[ok]\n```\n\n"
        "```mermaid\nflowchart LR\n    subgraph S1 [Bad (oops)]\n    end\n```\n",
        encoding="utf-8",
    )
    issues = check_file(str(md))
    assert len(issues) == 1


def test_check_file_nonexistent_file() -> None:
    assert check_file("/nonexistent/path.md") == []


# -------------------------------------------------------
# check_files / format_issues
# -------------------------------------------------------


def test_check_files_filters_non_md(tmp_path: Path) -> None:
    bad = tmp_path / "bad.md"
    bad.write_text(
        "```mermaid\ngraph TD\n    subgraph S1 [Bad (oops)]\n    end\n```\n",
        encoding="utf-8",
    )
    issues = check_files([
        str(bad),
        str(tmp_path / "script.py"),
        str(tmp_path / "doc.txt"),
    ])
    assert len(issues) == 1


def test_format_issues_single() -> None:
    from ame_ai_review_system.mermaid_check import Issue

    issues = [Issue("f.md", 42, "msg")]
    formatted = format_issues(issues)
    assert "f.md:42" in formatted
    assert "msg" in formatted


def test_format_issues_multi() -> None:
    from ame_ai_review_system.mermaid_check import Issue

    issues = [Issue("a.md", 1, "e1"), Issue("b.md", 2, "e2")]
    formatted = format_issues(issues)
    lines = formatted.split("\n")
    assert len(lines) == 2
    assert "a.md:1" in lines[0]
    assert "b.md:2" in lines[1]


# -------------------------------------------------------
# CLI main
# -------------------------------------------------------


def test_main_no_args() -> None:
    assert main([]) == 0


def test_main_clean_file(tmp_path: Path) -> None:
    md = tmp_path / "clean.md"
    md.write_text("```mermaid\ngraph TD\n    A --> B\n```\n", encoding="utf-8")
    assert main([str(md)]) == 0


def test_main_error_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    md = tmp_path / "bad.md"
    md.write_text(
        "```mermaid\ngraph TD\n    subgraph S1 [Bad (parens)]\n    end\n```\n",
        encoding="utf-8",
    )
    rc = main([str(md)])
    assert rc == 1
    captured = capsys.readouterr()
    assert "bad.md" in captured.err


def test_main_files_from_stdin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import io

    md = tmp_path / "bad.md"
    md.write_text(
        "```mermaid\ngraph TD\n    subgraph S1 [Bad (parens)]\n    end\n```\n",
        encoding="utf-8",
    )
    import sys

    stdin_data = f"{md}\n"
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin_data))
    rc = main(["--files-from-stdin"])
    assert rc == 1


def test_main_non_md_skipped(tmp_path: Path) -> None:
    py = tmp_path / "script.py"
    py.write_text('print("hello")', encoding="utf-8")
    assert main([str(py)]) == 0


# -------------------------------------------------------
# check_files with issue object correctness
# -------------------------------------------------------


def test_issue_namedtuple_fields() -> None:
    from ame_ai_review_system.mermaid_check import Issue

    issue = Issue("path.md", 10, "message")
    assert issue.path == "path.md"
    assert issue.line == 10
    assert issue.message == "message"
