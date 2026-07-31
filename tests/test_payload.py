# pyright: basic
from __future__ import annotations

import json
from pathlib import Path

from ame_ai_review_system.payload import parse_review_json, parse_review_json_with_flag


def test_parse_review_json_plain(tmp_path: Path) -> None:
    data = {
        "summary": "Good progress.",
        "comments": [],
    }
    tmp_file = tmp_path / "review.json"
    tmp_file.write_text(json.dumps(data), encoding="utf-8")

    res = parse_review_json(str(tmp_file))
    assert res["summary"] == "Good progress."
    assert res["comments"] == []


def test_parse_review_json_with_code_fence(tmp_path: Path) -> None:
    raw_content = """Some text before
```json
{
  "summary": "Code fence test",
  "comments": []
}
```
Some text after"""
    tmp_file = tmp_path / "review.json"
    tmp_file.write_text(raw_content, encoding="utf-8")

    res = parse_review_json(str(tmp_file))
    assert res["summary"] == "Code fence test"
    assert res["comments"] == []


def test_parse_review_json_fallback_on_invalid(tmp_path: Path) -> None:
    tmp_file = tmp_path / "broken.json"
    tmp_file.write_text("not a json content at all", encoding="utf-8")

    res, is_fallback = parse_review_json_with_flag(str(tmp_file))
    assert is_fallback is True
    assert res["comments"] == []


def test_parse_review_json_with_flag_false_on_valid(tmp_path: Path) -> None:
    data = {"summary": "LGTM", "comments": []}
    tmp_file = tmp_path / "review.json"
    tmp_file.write_text(json.dumps(data), encoding="utf-8")

    res, is_fallback = parse_review_json_with_flag(str(tmp_file))
    assert is_fallback is False
    assert res["summary"] == "LGTM"


def test_parse_review_json_repair_fixes_broken_output(tmp_path: Path) -> None:
    broken = (
        '<invoke name="bash">\n'
        "git status\n"
        "</invoke>\n"
        '{"summary": "repaired", "comments": []}\n'
        "trailing text"
    )
    tmp_file = tmp_path / "broken.json"
    tmp_file.write_text(broken, encoding="utf-8")

    def _repair(raw: str) -> str | None:
        assert "git status" in raw
        return '{"summary": "repaired", "comments": []}'

    res, is_fallback = parse_review_json_with_flag(str(tmp_file), repair=_repair)
    assert is_fallback is False
    assert res["summary"] == "repaired"


def test_parse_review_json_repair_none_keeps_fallback(tmp_path: Path) -> None:
    tmp_file = tmp_path / "broken.json"
    tmp_file.write_text("not a json content at all", encoding="utf-8")

    res, is_fallback = parse_review_json_with_flag(
        str(tmp_file),
        repair=lambda _raw: None,
    )
    assert is_fallback is True
    assert res["comments"] == []


def test_parse_review_json_structural_repair_without_llm(tmp_path: Path) -> None:
    broken = (
        '<invoke name="bash">\n'
        "git status\n"
        "</invoke>\n"
        "</tool_calls>\n"
        "garbage\n"
        "</tool_calls>\n"
        '{"summary": "structural", "comments": []}\n'
    )
    tmp_file = tmp_path / "broken.json"
    tmp_file.write_text(broken, encoding="utf-8")

    called = {"llm": False}

    def _repair(_raw: str) -> str | None:
        called["llm"] = True
        return None

    res, is_fallback = parse_review_json_with_flag(str(tmp_file), repair=_repair)
    assert is_fallback is False
    assert res["summary"] == "structural"
    assert called["llm"] is False


def test_build_repair_prompt_sanitizes_fence() -> None:
    from ame_ai_review_system.payload import build_repair_prompt

    broken = '前書き\n```json\n{"summary": "x"}\n```\n後書き'
    prompt = build_repair_prompt(broken)
    assert "```json" not in prompt
    assert "\u201e\u201e\u201ejson" in prompt
    assert prompt.count("```") == 2
