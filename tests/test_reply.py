from __future__ import annotations

from ame_ai_review_system.reply import _extract_json, is_stale_loop


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


# --- is_stale_loop --------------------------------------------------------


def test_stale_loop_empty_list() -> None:
    assert is_stale_loop([]) is False


def test_stale_loop_single_comment() -> None:
    assert is_stale_loop(["one comment"]) is False


def test_stale_loop_identical_long_comments() -> None:
    body = "この関数は例外をキャッチしていません 修正してください"
    assert is_stale_loop([body, body]) is True


def test_stale_loop_high_similarity() -> None:
    c1 = "この関数は例外をキャッチしていません 修正してください"
    c2 = "この関数は例外をキャッチしていません 修正してください。"
    assert is_stale_loop([c1, c2]) is True


def test_stale_loop_low_similarity() -> None:
    c1 = "この関数は例外をキャッチしていません 修正してください"
    c2 = "変数名が不適切です snake_case を使ってください"
    assert is_stale_loop([c1, c2]) is False


def test_stale_loop_short_exact_match() -> None:
    assert is_stale_loop(["LGTM", "LGTM"]) is True


def test_stale_loop_short_different() -> None:
    assert is_stale_loop(["LGTM", "Fix it"]) is False


def test_stale_loop_empty_bodies() -> None:
    assert is_stale_loop(["", ""]) is False
