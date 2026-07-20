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
