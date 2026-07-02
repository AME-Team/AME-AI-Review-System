from __future__ import annotations

from reply import _extract_json


def test_extract_json_plain() -> None:
    raw = '{"lgtm": true, "reply": "Looks clean!"}'
    res = _extract_json(raw)
    assert res is not None
    assert res.get("lgtm") is True
    assert res.get("reply") == "Looks clean!"


def test_extract_json_with_code_fence() -> None:
    raw = """Here is the result:
```json
{"lgtm": false, "reply": "Please fix line 10"}
```"""
    res = _extract_json(raw)
    assert res is not None
    assert res.get("lgtm") is False
    assert res.get("reply") == "Please fix line 10"
