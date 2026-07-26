# pyright: basic
from __future__ import annotations

from typing import Any

import pytest
from ame_ai_review_system import github_client, reply
from ame_ai_review_system.reply import _extract_json, _group_by_thread, is_stale_loop


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


# --- _group_by_thread (GitHub flat comments API) ---------------------------


def _comment(
    cid: int,
    body: str = "",
    *,
    in_reply_to: int | None = None,
    created_at: str = "2024-01-01T00:00:00Z",
    login: str = "octocat",
    path: str = "src/app.py",
) -> dict[str, Any]:
    return {
        "id": cid,
        "in_reply_to_id": in_reply_to,
        "body": body,
        "created_at": created_at,
        "user": {"login": login},
        "path": path,
    }


def test_group_by_thread_single_root() -> None:
    comments = [_comment(1, "root"), _comment(2, "reply1", in_reply_to=1)]
    grouped = _group_by_thread(comments)
    assert set(grouped.keys()) == {1}
    assert [c["id"] for c in grouped[1]] == [1, 2]


def test_group_by_thread_multiple_threads() -> None:
    comments = [
        _comment(10, "rootA"),
        _comment(20, "rootB"),
        _comment(11, "a1", in_reply_to=10),
        _comment(21, "b1", in_reply_to=20),
        _comment(12, "a2", in_reply_to=10),
    ]
    grouped = _group_by_thread(comments)
    assert set(grouped.keys()) == {10, 20}
    assert [c["id"] for c in grouped[10]] == [10, 11, 12]
    assert [c["id"] for c in grouped[20]] == [20, 21]


def test_group_by_thread_orders_by_created_at() -> None:
    comments = [
        _comment(1, "root", created_at="2024-01-01T00:00:00Z"),
        _comment(3, "late", in_reply_to=1, created_at="2024-01-03T00:00:00Z"),
        _comment(2, "early", in_reply_to=1, created_at="2024-01-02T00:00:00Z"),
    ]
    grouped = _group_by_thread(comments)
    assert [c["id"] for c in grouped[1]] == [1, 2, 3]


def test_group_by_thread_orphan_reply_ignored() -> None:
    """in_reply_to_id が現在のページに無いルートを指す場合は単独スレッドを形成しない."""
    comments = [_comment(99, "orphan reply", in_reply_to=9999)]
    grouped = _group_by_thread(comments)
    # 99 自身は親を持つため root として扱われない。result は空になる。
    assert grouped == {}


# --- _resolved_root_ids (GraphQL isResolved integration) ------------------


def test_resolved_root_ids_collects_resolved_thread_members(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    threads = [
        {
            "id": "T1",
            "isResolved": True,
            "comments": {"nodes": [{"databaseId": 100}, {"databaseId": 101}]},
        },
        {
            "id": "T2",
            "isResolved": False,
            "comments": {"nodes": [{"databaseId": 200}]},
        },
        {
            "id": "T3",
            "isResolved": True,
            "comments": {"nodes": [{"databaseId": 300}]},
        },
    ]
    monkeypatch.setattr(github_client, "list_review_threads", lambda _pr, _tok: threads)
    result = reply._resolved_root_ids(7, "tok")
    assert result == {100, 101, 300}


def test_resolved_root_ids_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(github_client, "list_review_threads", lambda _pr, _tok: [])
    assert reply._resolved_root_ids(7, "tok") == set()


# --- GitHub App [bot] suffix integration ----------------------------------


def test_mention_detection_accepts_bot_form() -> None:
    """reviewer_name='ame-ai-reviewer' でも @ame-ai-reviewer[bot] を検出できることを検証する。."""
    assert github_client.mentions_reviewer(
        "@ame-ai-reviewer[bot] 修正しました", "ame-ai-reviewer"
    )


def test_mention_detection_accepts_short_form() -> None:
    """後方互換のため @ame-ai-reviewer (短縮形) も検出することを検証する。."""
    assert github_client.mentions_reviewer(
        "@ame-ai-reviewer 修正しました", "ame-ai-reviewer"
    )


def test_mention_detection_rejects_unrelated_mention() -> None:
    """無関係なメンションは拒否することを検証する。."""
    assert not github_client.mentions_reviewer(
        "@other-user 修正しました", "ame-ai-reviewer"
    )
