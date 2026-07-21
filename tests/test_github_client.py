"""Unit tests for the shared GitHub REST/GraphQL client module."""

from __future__ import annotations

import urllib.error
import urllib.request
from typing import Any

import pytest
from ame_ai_review_system import github_client

# ============================================================================
# resolve_env
# ============================================================================


def test_resolve_env_uses_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_API_URL", "https://api.github.com")
    monkeypatch.setenv("GITHUB_REPOSITORY", "tarminjapan/AME-AI-Review-System")
    api_url, repo = github_client.resolve_env()
    assert api_url == "https://api.github.com"
    assert repo == "tarminjapan/AME-AI-Review-System"


def test_resolve_env_missing_repo_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    with pytest.raises(RuntimeError, match="GITHUB_REPOSITORY"):
        github_client.resolve_env()


def test_resolve_env_custom_api_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_API_URL", "https://github.enterprise/api/v3")
    monkeypatch.setenv("GITHUB_REPOSITORY", "org/repo")
    api_url, _ = github_client.resolve_env()
    assert api_url == "https://github.enterprise/api/v3"


# ============================================================================
# get_token
# ============================================================================


def test_get_token_from_file(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    token_file = tmp_path / "github.token"
    token_file.write_text("filetoken123", encoding="utf-8")
    monkeypatch.delenv("GITHUB_PAT_TOKEN", raising=False)
    assert github_client.get_token(str(token_file)) == "filetoken123"


def test_get_token_fallback_to_env(
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token_file = tmp_path / "missing.token"
    monkeypatch.setenv("GITHUB_PAT_TOKEN", "envtoken456")
    assert github_client.get_token(str(token_file)) == "envtoken456"


def test_get_token_custom_env_key(
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token_file = tmp_path / "missing.token"
    monkeypatch.delenv("GITHUB_PAT_TOKEN", raising=False)
    monkeypatch.setenv("REVIEWER_BOT_TOKEN", "customtoken789")
    assert (
        github_client.get_token(str(token_file), env_key="REVIEWER_BOT_TOKEN")
        == "customtoken789"
    )


def test_get_token_missing_raises(
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token_file = tmp_path / "missing.token"
    monkeypatch.delenv("GITHUB_PAT_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="GitHub token not found"):
        github_client.get_token(str(token_file))


# ============================================================================
# bot_login
# ============================================================================


def test_bot_login_appends_bot_suffix() -> None:
    """App slug に [bot] サフィックスが付与されることを検証する。."""
    assert github_client.bot_login("ame-ai-reviewer") == "ame-ai-reviewer[bot]"


def test_bot_login_idempotent_for_already_bot_login() -> None:
    """すでに [bot] 付きの名前はそのまま返すことを検証する。."""
    assert github_client.bot_login("ame-ai-reviewer[bot]") == "ame-ai-reviewer[bot]"


def test_bot_login_preserves_hyphenated_slug() -> None:
    """ハイフン入り slug も正しく処理されることを検証する。."""
    assert github_client.bot_login("security-reviewer") == "security-reviewer[bot]"


# ============================================================================
# mentions_reviewer
# ============================================================================


def test_mentions_reviewer_detects_short_form() -> None:
    """@ame-ai-reviewer (旧PAT形式) を検出することを検証する。."""
    assert github_client.mentions_reviewer(
        "@ame-ai-reviewer 修正しました", "ame-ai-reviewer"
    )


def test_mentions_reviewer_detects_bot_form() -> None:
    """@ame-ai-reviewer[bot] (App公式形式) を検出することを検証する。."""
    assert github_client.mentions_reviewer(
        "@ame-ai-reviewer[bot] 修正しました", "ame-ai-reviewer"
    )


def test_mentions_reviewer_negative_no_mention() -> None:
    """メンションがない本文は False となることを検証する。."""
    assert not github_client.mentions_reviewer(
        "修正しました。LGTM お願いします。", "ame-ai-reviewer"
    )


def test_mentions_reviewer_negative_different_user() -> None:
    """別ユーザーへのメンションは False となることを検証する。."""
    assert not github_client.mentions_reviewer(
        "@other-reviewer 修正しました", "ame-ai-reviewer"
    )


def test_mentions_reviewer_substring_safety() -> None:
    """Bot 形式の明確な境界ケースを検証する。.

    本実装では部分一致検出のため、``@ame-ai-reviewer[bot]`` の直後に
    句読点が続くケースも True になることを確認する。
    """
    assert github_client.mentions_reviewer(
        "@ame-ai-reviewer[bot], 修正しました", "ame-ai-reviewer"
    )


# ============================================================================
# http_request
# ============================================================================


class _FakeResponse:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data

    def __enter__(self) -> Any:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


def test_http_request_sets_bearer_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(req: urllib.request.Request) -> _FakeResponse:
        captured["url"] = req.full_url
        captured["method"] = req.method
        captured["headers"] = {k: req.headers[k] for k in req.headers}
        captured["data"] = req.data
        return _FakeResponse(b'{"ok": true}')

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    result = github_client.http_request(
        "GET",
        "https://api.github.com/repos/o/r/pulls/1",
        "tok_ABC",
    )
    assert result == {"ok": True}
    assert captured["method"] == "GET"
    assert captured["headers"]["Authorization"] == "Bearer tok_ABC"
    assert captured["headers"]["Accept"] == "application/vnd.github+json"
    assert captured["headers"]["X-github-api-version"] == "2022-11-28"
    assert captured["data"] is None


def test_http_request_post_with_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(req: urllib.request.Request) -> _FakeResponse:
        captured["method"] = req.method
        captured["data"] = req.data
        captured["headers"] = {k: req.headers[k] for k in req.headers}
        return _FakeResponse(b'{"id": 42}')

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    result = github_client.http_request(
        "POST",
        "https://api.github.com/repos/o/r/pulls/1/comments",
        "tok_X",
        body={"body": "hello"},
    )
    assert result == {"id": 42}
    assert captured["method"] == "POST"
    assert captured["headers"]["Content-type"] == "application/json"
    assert captured["data"] == b'{"body": "hello"}'


def test_http_request_http_error_raises_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from email.message import Message

    def fake_urlopen(_req: urllib.request.Request) -> _FakeResponse:
        raise urllib.error.HTTPError(
            url="https://api.github.com/x",
            code=422,
            msg="Unprocessable",
            hdrs=Message(),
            fp=None,
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(RuntimeError, match="GitHub API error 422"):
        github_client.http_request("GET", "https://api.github.com/x", "tok")


def test_http_request_diff_accept_returns_raw_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(_req: urllib.request.Request) -> _FakeResponse:
        return _FakeResponse(b"diff --git a/x b/x\n+hello\n")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    result = github_client.http_request(
        "GET",
        "https://api.github.com/repos/o/r/pulls/1",
        "tok",
        accept="application/vnd.github.diff",
    )
    assert result == "diff --git a/x b/x\n+hello\n"


def test_http_request_empty_body_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(_req: urllib.request.Request) -> _FakeResponse:
        return _FakeResponse(b"")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert (
        github_client.http_request("DELETE", "https://api.github.com/x", "tok") is None
    )


# ============================================================================
# graphql_request
# ============================================================================


def test_graphql_request_success(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_http_request(
        method: str,
        url: str,
        token: str,
        body: dict[str, Any] | None = None,
        **_kw: Any,
    ) -> dict[str, Any]:
        captured["method"] = method
        captured["url"] = url
        captured["body"] = body
        return {"data": {"viewer": {"login": "octocat"}}}

    monkeypatch.setattr(github_client, "http_request", fake_http_request)
    result = github_client.graphql_request(
        "query { viewer { login } }",
        {},
        "tok_G",
    )
    assert result == {"viewer": {"login": "octocat"}}
    assert captured["method"] == "POST"
    assert captured["url"] == "https://api.github.com/graphql"
    assert captured["body"]["query"] == "query { viewer { login } }"


def test_graphql_request_http200_with_errors_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTP 200 応答でも GraphQL レベルの errors 配列を持つ場合を検出する."""

    def fake_http_request(
        _method: str,
        _url: str,
        _token: str,
        body: dict[str, Any] | None = None,
        **_kw: Any,
    ) -> dict[str, Any]:
        assert body is not None
        return {
            "data": None,
            "errors": [
                {
                    "type": "FORBIDDEN",
                    "message": "Resource not accessible by integration",
                },
            ],
        }

    monkeypatch.setattr(github_client, "http_request", fake_http_request)
    with pytest.raises(RuntimeError, match="GraphQL errors"):
        github_client.graphql_request("query { x }", {}, "tok")


def test_graphql_request_no_data_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_http_request(
        _method: str,
        _url: str,
        _token: str,
        body: dict[str, Any] | None = None,
        **_kw: Any,
    ) -> dict[str, Any]:
        return {"neither": "data nor errors"}

    monkeypatch.setattr(github_client, "http_request", fake_http_request)
    with pytest.raises(TypeError, match="no data"):
        github_client.graphql_request("query { x }", {}, "tok")


def test_graphql_request_non_dict_response_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_http_request(
        _method: str,
        _url: str,
        _token: str,
        body: dict[str, Any] | None = None,
        **_kw: Any,
    ) -> Any:
        return ["unexpected", "list"]

    monkeypatch.setattr(github_client, "http_request", fake_http_request)
    with pytest.raises(TypeError, match="Unexpected GraphQL response"):
        github_client.graphql_request("query { x }", {}, "tok")


# ============================================================================
# list_review_threads / resolve_review_thread
# ============================================================================


def test_list_review_threads_paginates_and_flattens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    calls: list[dict[str, Any]] = []

    def fake_graphql(
        query: str,
        variables: dict[str, Any],
        token: str,
    ) -> dict[str, Any]:
        calls.append({"query": query, "variables": variables})
        after = variables["after"]
        if after is None:
            return {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "pageInfo": {"hasNextPage": True, "endCursor": "cursor1"},
                            "nodes": [
                                {
                                    "id": "T1",
                                    "isResolved": False,
                                    "comments": {"nodes": [{"databaseId": 100}]},
                                },
                            ],
                        },
                    },
                },
            }
        return {
            "repository": {
                "pullRequest": {
                    "reviewThreads": {
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "nodes": [
                            {
                                "id": "T2",
                                "isResolved": True,
                                "comments": {
                                    "nodes": [{"databaseId": 200}, {"databaseId": 201}]
                                },
                            },
                        ],
                    },
                },
            },
        }

    monkeypatch.setattr(github_client, "graphql_request", fake_graphql)
    threads = github_client.list_review_threads(7, "tok")
    assert [t["id"] for t in threads] == ["T1", "T2"]
    assert calls[0]["variables"]["after"] is None
    assert calls[1]["variables"]["after"] == "cursor1"


def test_resolve_review_thread_matches_comment_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """comment_id (REST 数値) を GraphQL thread 内の databaseId と突き合わせる."""
    mutation_calls: list[dict[str, Any]] = []

    def fake_list(pr_number: int, token: str) -> list[dict[str, Any]]:
        return [
            {
                "id": "T1",
                "isResolved": False,
                "comments": {"nodes": [{"databaseId": 100}, {"databaseId": 101}]},
            },
            {
                "id": "T2",
                "isResolved": False,
                "comments": {"nodes": [{"databaseId": 200}]},
            },
        ]

    def fake_graphql(
        query: str,
        variables: dict[str, Any],
        token: str,
    ) -> dict[str, Any]:
        mutation_calls.append({"query": query, "variables": variables})
        return {
            "resolveReviewConversation": {
                "thread": {"id": variables["threadId"], "isResolved": True},
            },
        }

    monkeypatch.setattr(github_client, "list_review_threads", fake_list)
    monkeypatch.setattr(github_client, "graphql_request", fake_graphql)
    github_client.resolve_review_thread(7, 101, "tok")
    assert len(mutation_calls) == 1
    assert mutation_calls[0]["variables"]["threadId"] == "T1"


def test_resolve_review_thread_no_match_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_list(_pr: int, _tok: str) -> list[dict[str, Any]]:
        return [
            {
                "id": "T1",
                "isResolved": False,
                "comments": {"nodes": [{"databaseId": 100}]},
            },
        ]

    monkeypatch.setattr(github_client, "list_review_threads", fake_list)
    with pytest.raises(RuntimeError, match="Review thread not found for comment 999"):
        github_client.resolve_review_thread(7, 999, "tok")
