from __future__ import annotations

import json
from pathlib import Path

from payload import parse_review_json


def test_parse_review_json_plain(tmp_path: Path) -> None:
    data = {
        "summary": "Good progress.",
        "comments": [],
        "checklist": {"no_bugs": True},
    }
    tmp_file = tmp_path / "review.json"
    tmp_file.write_text(json.dumps(data), encoding="utf-8")

    res = parse_review_json(str(tmp_file))
    assert res["summary"] == "Good progress."
    assert res["checklist"]["no_bugs"] is True


def test_parse_review_json_with_code_fence(tmp_path: Path) -> None:
    raw_content = """Some text before
```json
{
  "summary": "Code fence test",
  "comments": [],
  "checklist": {"no_bugs": false}
}
```
Some text after"""
    tmp_file = tmp_path / "review.json"
    tmp_file.write_text(raw_content, encoding="utf-8")

    res = parse_review_json(str(tmp_file))
    assert res["summary"] == "Code fence test"
    assert res["checklist"]["no_bugs"] is False
