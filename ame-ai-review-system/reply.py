"""PR review reply: prompt builder and Claude output parser.

サブコマンド:
  build <pr_number> <thread_id>   スレッドの親コメント + 返信一覧 + diff からプロンプトを
                                   stdout へ出力する。
                                   対応不要なスレッドは空文字を出力して exit 0。
  parse <claude_out_path>          Claude の JSON 出力から {"body": "..."} を
                                   stdout へ出力する。
  pending <pr_number>              返信待ちスレッドの id を JSON 配列で stdout へ。
                                   条件: @<reviewer_name> 宛て最新 mention 後に
                                         reviewer が未返信。
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
from typing import Any, cast

_DEFAULT_LGTM = "対応確認しました。LGTM ✅ Resolve してください。"


_HTTP_OK_MIN = 200
_HTTP_OK_MAX = 300


def _get_json(url: str, token: str) -> Any:
    import http.client
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = parsed.netloc
    path = parsed.path
    if parsed.query:
        path += "?" + parsed.query
    conn = (
        http.client.HTTPSConnection(host)
        if parsed.scheme == "https"
        else http.client.HTTPConnection(host)
    )
    conn.request("GET", path, headers={"Authorization": f"token {token}"})
    resp = conn.getresponse()
    body = resp.read()
    if not (_HTTP_OK_MIN <= resp.status < _HTTP_OK_MAX):
        msg = f"HTTP {resp.status}: {body[:200]!r}"
        raise OSError(msg)
    try:
        return json.loads(body)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError(body[:200]) from exc


_REVIEWS_PAGE_SIZE = 50


def _get_thread_comments(
    gitea_url: str,
    repo: str,
    pr: str,
    token: str,
) -> list[dict[str, Any]]:
    """Return all inline comments across all reviews, flattened."""
    reviews: list[dict[str, Any]] = []
    page = 1
    while True:
        page_reviews: list[dict[str, Any]] = _get_json(
            f"{gitea_url}/api/v1/repos/{repo}/pulls/{pr}"
            f"/reviews?limit={_REVIEWS_PAGE_SIZE}&page={page}",
            token,
        )
        if not page_reviews:
            break
        reviews.extend(page_reviews)
        if len(page_reviews) < _REVIEWS_PAGE_SIZE:
            break
        page += 1
    result: list[dict[str, Any]] = []
    for review in reviews:
        try:
            comments: list[dict[str, Any]] = _get_json(
                f"{gitea_url}/api/v1/repos/{repo}/pulls/{pr}"
                f"/reviews/{review['id']}/comments",
                token,
            )
        except (OSError, ConnectionError):
            continue
        result.extend(comments)
    return result


def _cmd_pending(pr: str) -> None:
    import os

    gitea_url = os.environ.get("GITEA_URL", "http://localhost:3000")
    repo = os.environ.get("REPO", "AME-Team/AME-AI-Review-System")
    token = os.environ.get("REVIEWER_TOKEN", "")
    reviewer_name = os.environ.get("REVIEWER_NAME", "ame-ai-reviewer")

    comments = _get_thread_comments(gitea_url, repo, pr, token)

    # Gitea のスレッドは (pull_request_review_id, path, position) の組み合わせで識別する。
    # 同一 review に複数のコメントが存在するため review_id だけではグループ化できない。
    by_thread: dict[tuple[int, str, int], list[dict[str, Any]]] = {}
    for c in comments:
        key = (
            int(c.get("pull_request_review_id", 0)),
            str(c.get("path", "")),
            int(c.get("position") or c.get("original_position") or 0),
        )
        by_thread.setdefault(key, []).append(c)

    pending: list[int] = []
    for thread in by_thread.values():
        # 時刻順に並べる
        thread_sorted = sorted(thread, key=lambda x: x.get("created_at", ""))
        if not thread_sorted:
            continue
        parent = thread_sorted[0]
        replies = thread_sorted[1:]

        # resolved 済みはスキップ
        if parent.get("resolved"):
            continue

        # @<reviewer_name> 宛て返信があるか
        mention_replies = [
            r for r in replies if f"@{reviewer_name}" in r.get("body", "")
        ]
        if not mention_replies:
            continue

        # 最新の @mention 以降にレビュアーが既に返信済みならスキップ
        # (LGTM でなくても「修正が不十分」返信が来ていれば再処理しない)
        latest_mention_time = max(r.get("created_at", "") for r in mention_replies)
        reviewer_replied_after = any(
            r.get("user", {}).get("login") == reviewer_name
            and r.get("created_at", "") > latest_mention_time
            for r in replies
        )
        if reviewer_replied_after:
            continue

        parent_id = parent.get("id")
        if parent_id is not None:
            pending.append(int(parent_id))

    print(json.dumps(pending))


def _get_raw_text(url: str, token: str) -> str:
    import http.client
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = parsed.netloc
    path = parsed.path
    if parsed.query:
        path += "?" + parsed.query
    conn = (
        http.client.HTTPSConnection(host)
        if parsed.scheme == "https"
        else http.client.HTTPConnection(host)
    )
    conn.request("GET", path, headers={"Authorization": f"token {token}"})
    resp = conn.getresponse()
    body = resp.read()
    if not (_HTTP_OK_MIN <= resp.status < _HTTP_OK_MAX):
        return ""
    return body.decode("utf-8", errors="replace")


def _get_pr_diff(
    base_ref: str,
    gitea_url: str = "",
    repo: str = "",
    pr: str = "",
    token: str = "",
) -> str:
    # Gitea の .diff エンドポイントで PR ブランチの完全な diff を取得する。
    # /files API は patch を返さないため使用しない。
    max_diff_lines = 4000

    if gitea_url and repo and pr and token:
        try:
            raw = _get_raw_text(
                f"{gitea_url}/api/v1/repos/{repo}/pulls/{pr}.diff",
                token,
            )
            if raw:
                all_lines = raw.splitlines()
                if len(all_lines) > max_diff_lines:
                    return (
                        "\n".join(all_lines[:max_diff_lines])
                        + f"\n... (truncated, {len(all_lines)} lines total)"
                    )
                return raw
        except OSError:
            pass

    if not re.match(r"^[a-zA-Z0-9/_-]+$", base_ref):
        print(f"[get_pr_diff] Invalid base_ref: {base_ref!r}", file=sys.stderr)
        return ""
    try:
        result = subprocess.check_output(
            ["git", "diff", f"origin/{base_ref}...HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        try:
            result = subprocess.check_output(
                ["git", "diff", "HEAD~1"],
                text=True,
                stderr=subprocess.DEVNULL,
            )
        except subprocess.CalledProcessError:
            return ""
    all_lines = result.splitlines()
    if len(all_lines) > max_diff_lines:
        return (
            "\n".join(all_lines[:max_diff_lines])
            + f"\n... (truncated, {len(all_lines)} lines total)"
        )
    return result


def _cmd_build(pr: str, thread_id_str: str) -> None:
    import os

    gitea_url = os.environ.get("GITEA_URL", "http://localhost:3000")
    repo = os.environ.get("REPO", "AME-Team/AME-AI-Review-System")
    token = os.environ.get("REVIEWER_TOKEN", "")
    reviewer_name = os.environ.get("REVIEWER_NAME", "ame-ai-reviewer")
    base_ref = os.environ.get("BASE_REF", "main")

    thread_id = int(thread_id_str)
    comments = _get_thread_comments(gitea_url, repo, pr, token)

    # 対象スレッドの親を探す
    parent: dict[str, Any] | None = next(
        (c for c in comments if c.get("id") == thread_id),
        None,
    )
    if parent is None:
        print(f"[build] thread {thread_id} not found", file=sys.stderr)
        return

    thread_key = (
        int(parent.get("pull_request_review_id", 0)),
        str(parent.get("path", "")),
        int(parent.get("position") or parent.get("original_position") or 0),
    )
    thread_sorted = sorted(
        [
            c
            for c in comments
            if (
                int(c.get("pull_request_review_id", 0)),
                str(c.get("path", "")),
                int(c.get("position") or c.get("original_position") or 0),
            )
            == thread_key
        ],
        key=lambda x: x.get("created_at", ""),
    )
    replies = thread_sorted[1:]

    # 直近の @<reviewer_name> メンション返信を取得
    mention_replies = [r for r in replies if f"@{reviewer_name}" in r.get("body", "")]
    if not mention_replies:
        return
    latest_reply = mention_replies[-1]

    diff = _get_pr_diff(base_ref, gitea_url=gitea_url, repo=repo, pr=pr, token=token)

    prompt_lines = [
        f"あなたは厳格なコードレビュアー ({reviewer_name}) です。",
        "開発者があなたのレビューコメントに返信しました。",
        "実際の diff と返信内容を確認し、指摘した問題が本当に修正されているか判断してください。",
        "",
        "## 元のレビューコメント（あなたの指摘）",
        f"ファイル: {parent.get('path', '')}",
        parent.get("body", ""),
        "",
        "## 開発者の返信",
        latest_reply.get("body", ""),
        "",
    ]

    if diff:
        prompt_lines += [
            "## PR の diff（修正内容）",
            "```diff",
            diff,
            "```",
            "",
        ]

    prompt_lines += [
        "## 判断基準",
        "- diff を見て、指摘した問題が実際にコード上で修正されている → LGTM",
        "- diff に修正がなく返信だけ → 修正されているか慎重に確認する",
        "- LOW / INFO (🟢) の指摘は、理由の説明があれば対応不要でも LGTM",
        "- 修正が不十分または的外れ → 具体的に何が不足しているか指摘する",
        "",
        "## 出力フォーマット（JSON のみ。前後に余計な文字は不要）",
        '{"lgtm": true, "reply": "返信本文（日本語）"}',
        "",
        f'LGTM の場合は reply = "{_DEFAULT_LGTM}"',
        "LGTM でない場合は reply に不足点を具体的に記載（どのファイルの何行目を直すべきか）",
    ]
    print("\n".join(prompt_lines))


def _extract_json(raw: str) -> dict[str, Any] | None:
    """Extract first valid JSON object from raw string using multiple strategies."""
    # Strategy 1: ```json or ``` code fence
    m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
    if m:
        try:
            return cast("dict[str, Any]", json.loads(m.group(1).strip()))
        except json.JSONDecodeError:
            pass

    # Strategy 2: brace-depth tracking for outermost {...}
    depth = 0
    start_idx = -1
    for i, ch in enumerate(raw):
        if ch == "{":
            if depth == 0:
                start_idx = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start_idx != -1:
                try:
                    return cast("dict[str, Any]", json.loads(raw[start_idx : i + 1]))
                except json.JSONDecodeError:
                    start_idx = -1
    return None


def _cmd_parse(claude_out_path: str) -> None:
    raw = pathlib.Path(claude_out_path).read_text(encoding="utf-8").strip()

    try:
        outer: Any = json.loads(raw)
        if isinstance(outer, dict) and outer.get("type") == "result":
            result_val = outer.get("result")
            if isinstance(result_val, str):
                raw = result_val
    except json.JSONDecodeError:
        pass

    parsed = _extract_json(raw)
    if parsed is not None:
        reply_body = str(parsed.get("reply", _DEFAULT_LGTM))
    else:
        print(
            f"[parse] JSON extraction failed. Raw preview:\n{raw[:300]}",
            file=sys.stderr,
        )
        reply_body = _DEFAULT_LGTM

    print(json.dumps({"body": reply_body}))


_REQUIRED_ARGS_BUILD = 4
_REQUIRED_ARGS_PARSE = 3
_REQUIRED_ARGS_PENDING = 3
_MIN_ARGS = 2


def main() -> None:
    if len(sys.argv) < _MIN_ARGS:
        sys.exit("Usage: build_review_reply_prompt.py build|parse|pending ...")

    cmd = sys.argv[1]
    if cmd == "build":
        if len(sys.argv) < _REQUIRED_ARGS_BUILD:
            sys.exit(
                "Usage: build_review_reply_prompt.py build <pr_number> <thread_id>",
            )
        _cmd_build(sys.argv[2], sys.argv[3])
    elif cmd == "parse":
        if len(sys.argv) < _REQUIRED_ARGS_PARSE:
            sys.exit("Usage: build_review_reply_prompt.py parse <claude_out_path>")
        _cmd_parse(sys.argv[2])
    elif cmd == "pending":
        if len(sys.argv) < _REQUIRED_ARGS_PENDING:
            sys.exit("Usage: build_review_reply_prompt.py pending <pr_number>")
        _cmd_pending(sys.argv[2])
    else:
        sys.exit(f"Unknown command: {cmd}")


if __name__ == "__main__":
    main()
