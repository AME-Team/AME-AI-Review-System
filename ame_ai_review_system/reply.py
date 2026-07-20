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
  stale-check <pr_number> <thread_id>  スレッドが stale-loop 状態か判定 (stale/ok)
  run <pr_number>                  全保留スレッドに返信を投稿するオーケストレーション
"""

from __future__ import annotations

import contextlib
import http.client
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
from typing import Any, cast
from urllib.parse import urlparse

_DEFAULT_LGTM = "対応確認しました。LGTM ✅ Resolve してください。"

_HTTP_OK_MIN = 200
_HTTP_OK_MAX = 300

_REVIEWS_PAGE_SIZE = 50

_STALE_JACCARD_THRESHOLD = 0.80
_STALE_MIN_NGRAMS = 4
_TRIGRAM_SIZE = 3
_MIN_COMMENTS_FOR_STALE = 2

_REQUIRED_ARGS_BUILD = 4
_REQUIRED_ARGS_PARSE = 3
_REQUIRED_ARGS_PENDING = 3
_REQUIRED_ARGS_STALE_CHECK = 4
_REQUIRED_ARGS_RUN = 3
_MIN_ARGS = 2


# ============================================================================
# HTTP helpers
# ============================================================================


def _http_request(
    url: str,
    token: str,
    method: str = "GET",
    body: dict[str, Any] | None = None,
) -> tuple[int, Any]:
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

    headers = {"Authorization": f"token {token}"}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    conn.request(method, path, body=data, headers=headers)
    resp = conn.getresponse()
    resp_body = resp.read()
    if not (_HTTP_OK_MIN <= resp.status < _HTTP_OK_MAX):
        msg = f"HTTP {resp.status}: {resp_body[:200]!r}"
        raise OSError(msg)

    try:
        return resp.status, json.loads(resp_body)
    except (json.JSONDecodeError, TypeError):
        return resp.status, resp_body.decode("utf-8", errors="replace")


def _get_json(url: str, token: str) -> Any:
    _, data = _http_request(url, token, "GET")
    return data


# ============================================================================
# Thread comment fetching
# ============================================================================


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


def _get_pr_diff(
    base_ref: str,
    gitea_url: str = "",
    repo: str = "",
    pr: str = "",
    token: str = "",
) -> str:
    """Get PR diff from Gitea .diff endpoint or git diff."""
    from . import diff_utils

    max_diff_lines = 4000

    if gitea_url and repo and pr and token:
        try:
            parsed = urlparse(f"{gitea_url}/api/v1/repos/{repo}/pulls/{pr}.diff")
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
            raw = resp.read().decode("utf-8", errors="replace")
            if raw:
                raw = diff_utils.compact_diff(raw)
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
    result = diff_utils.compact_diff(result)
    all_lines = result.splitlines()
    if len(all_lines) > max_diff_lines:
        return (
            "\n".join(all_lines[:max_diff_lines])
            + f"\n... (truncated, {len(all_lines)} lines total)"
        )
    return result


# ============================================================================
# Stale loop detection
# ============================================================================


def _trigrams(text: str) -> set[str]:
    text = text.lower().strip()
    if len(text) < _TRIGRAM_SIZE:
        return {text} if text else set()
    return {text[i : i + _TRIGRAM_SIZE] for i in range(len(text) - (_TRIGRAM_SIZE - 1))}


def is_stale_loop(comment_bodies: list[str]) -> bool:
    """Detect stale-loop: reviewer repeating the same feedback with slight variations.

    直近2件のコメントの文字トリグラム Jaccard 類似度が閾値以上の場合に True を返す。
    日本語テキストに対応するため単語分割ではなくトリグラムを使用する。
    トリグラム数が 4 未満の短いコメントは完全一致で判定する。
    """
    if len(comment_bodies) < _MIN_COMMENTS_FOR_STALE:
        return False

    g1 = _trigrams(comment_bodies[-2])
    g2 = _trigrams(comment_bodies[-1])

    if not g1 or not g2:
        return False

    if len(g1) < _STALE_MIN_NGRAMS or len(g2) < _STALE_MIN_NGRAMS:
        return g1 == g2

    jaccard = len(g1 & g2) / len(g1 | g2)
    return jaccard >= _STALE_JACCARD_THRESHOLD


# ============================================================================
# Pending threads
# ============================================================================


def _get_pending_threads(
    gitea_url: str,
    repo: str,
    pr: str,
    token: str,
    reviewer_name: str,
) -> list[int]:
    """Return list of pending thread IDs (parent comment IDs)."""
    comments = _get_thread_comments(gitea_url, repo, pr, token)

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
        thread_sorted = sorted(thread, key=lambda x: x.get("created_at", ""))
        if not thread_sorted:
            continue
        parent = thread_sorted[0]
        replies = thread_sorted[1:]

        if parent.get("resolved"):
            continue

        mention_replies = [
            r for r in replies if f"@{reviewer_name}" in r.get("body", "")
        ]
        if not mention_replies:
            continue

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

    return pending


# ============================================================================
# Commands: build, parse, pending, stale-check
# ============================================================================


def _cmd_build(pr: str, thread_id_str: str) -> None:
    gitea_url = os.environ.get("GITEA_URL", "http://localhost:3000")
    repo = os.environ.get("REPO", "AME-Team/AME-AI-Review-System")
    token = os.environ.get("REVIEWER_TOKEN", "")
    reviewer_name = os.environ.get("REVIEWER_NAME", "ame-ai-reviewer")
    base_ref = os.environ.get("BASE_REF", "main")

    thread_id = int(thread_id_str)
    comments = _get_thread_comments(gitea_url, repo, pr, token)

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
        "",
        "=== 以下、動的コンテキスト（プロンプトキャッシュ境界） ===",
        "## 元のレビューコメント（あなたの指摘）",
        f"ファイル: {parent.get('path', '')}",
        parent.get("body", ""),
        "",
        "## 開発者の返信",
        latest_reply.get("body", ""),
    ]

    if diff:
        prompt_lines += [
            "",
            "## PR の diff（修正内容）",
            "```diff",
            diff,
            "```",
        ]

    print("\n".join(prompt_lines))


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


def _cmd_pending(pr: str) -> None:
    gitea_url = os.environ.get("GITEA_URL", "http://localhost:3000")
    repo = os.environ.get("REPO", "AME-Team/AME-AI-Review-System")
    token = os.environ.get("REVIEWER_TOKEN", "")
    reviewer_name = os.environ.get("REVIEWER_NAME", "ame-ai-reviewer")

    pending = _get_pending_threads(gitea_url, repo, pr, token, reviewer_name)
    print(json.dumps(pending))


def _cmd_stale_check(pr: str, thread_id_str: str) -> None:
    gitea_url = os.environ.get("GITEA_URL", "http://localhost:3000")
    repo = os.environ.get("REPO", "AME-Team/AME-AI-Review-System")
    token = os.environ.get("REVIEWER_TOKEN", "")
    reviewer_name = os.environ.get("REVIEWER_NAME", "ame-ai-reviewer")

    thread_id = int(thread_id_str)
    comments = _get_thread_comments(gitea_url, repo, pr, token)

    parent = next((c for c in comments if c.get("id") == thread_id), None)
    if parent is None:
        print("ok")
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

    reviewer_replies = [
        str(c.get("body", ""))
        for c in thread_sorted[1:]
        if c.get("user", {}).get("login") == reviewer_name
    ]

    if is_stale_loop(reviewer_replies):
        print("stale")
    else:
        print("ok")


# ============================================================================
# JSON extraction
# ============================================================================


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


# ============================================================================
# Run command (orchestration from pr_review_reply.sh)
# ============================================================================


def _post_reply(
    gitea_url: str,
    repo: str,
    pr_number: int,
    thread_id: int,
    token: str,
    body: str,
) -> int:
    """Post a reply to a review thread. Returns HTTP status code."""
    url = f"{gitea_url}/api/v1/repos/{repo}/pulls/{pr_number}/comments/{thread_id}/replies"
    try:
        status, _ = _http_request(url, token, "POST", {"body": body})
    except OSError as e:
        print(f"[reply] Failed to post reply: {e}", file=sys.stderr)
        return 0
    else:
        return status


def _resolve_thread(
    gitea_url: str,
    repo: str,
    thread_id: int,
    token: str,
) -> int:
    """Resolve a review thread. Returns HTTP status code."""
    url = f"{gitea_url}/api/v1/repos/{repo}/pulls/comments/{thread_id}/resolve"
    try:
        status, _ = _http_request(url, token, "POST", {})
    except OSError as e:
        print(f"[reply] Failed to resolve thread: {e}", file=sys.stderr)
        return 0
    else:
        return status


def _run_engine(prompt: str) -> tuple[int, str]:
    """Run engine.py with prompt, return (exit_code, stdout)."""
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix="_prompt.txt",
        delete=False,
        encoding="utf-8",
    ) as pf:
        pf.write(prompt)
        prompt_file = pf.name

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix="_out.txt",
        delete=False,
        encoding="utf-8",
    ) as of:
        out_file = of.name

    err_file = out_file + ".err"

    try:
        with (
            pathlib.Path(prompt_file).open("r", encoding="utf-8") as pfi,
            pathlib.Path(out_file).open("w", encoding="utf-8") as fout,
            pathlib.Path(err_file).open("w", encoding="utf-8") as efi,
        ):
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ame_ai_review_system.engine",
                    "--role",
                    "reply",
                ],
                stdin=pfi,
                stdout=fout,
                stderr=efi,
                timeout=600,
                check=False,
            )
        engine_exit = proc.returncode

        stdout = pathlib.Path(out_file).read_text(encoding="utf-8")
        stderr = pathlib.Path(err_file).read_text(encoding="utf-8")

        if stderr:
            print(f"[reply] Engine stderr: {stderr}", file=sys.stderr)

        return engine_exit, stdout
    finally:
        for f in (prompt_file, out_file, err_file):
            with contextlib.suppress(OSError):
                pathlib.Path(f).unlink()


def _check_stale(
    gitea_url: str,
    repo: str,
    pr: str,
    thread_id_str: str,
    token: str,
    reviewer_name: str,
) -> str:
    thread_id = int(thread_id_str)
    comments = _get_thread_comments(gitea_url, repo, pr, token)

    parent = next((c for c in comments if c.get("id") == thread_id), None)
    if parent is None:
        return "ok"

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

    reviewer_replies = [
        str(c.get("body", ""))
        for c in thread_sorted[1:]
        if c.get("user", {}).get("login") == reviewer_name
    ]

    if is_stale_loop(reviewer_replies):
        return "stale"
    return "ok"


def _build_prompt_for_thread(
    gitea_url: str,
    repo: str,
    pr: str,
    thread_id_str: str,
    token: str,
    reviewer_name: str,
    base_ref: str,
) -> str:
    thread_id = int(thread_id_str)
    comments = _get_thread_comments(gitea_url, repo, pr, token)

    parent = next((c for c in comments if c.get("id") == thread_id), None)
    if parent is None:
        print(f"[reply] thread {thread_id} not found", file=sys.stderr)
        return ""

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

    mention_replies = [r for r in replies if f"@{reviewer_name}" in r.get("body", "")]
    if not mention_replies:
        return ""
    latest_reply = mention_replies[-1]

    diff = _get_pr_diff(base_ref, gitea_url=gitea_url, repo=repo, pr=pr, token=token)

    prompt_lines = [
        f"あなたは厳格なコードレビュアー ({reviewer_name}) です。",
        "開発者があなたのレビューコメントに返信しました。",
        "実際の diff と返信内容を確認し、指摘した問題が本当に修正されているか判断してください。",
        "",
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
        "",
        "=== 以下、動的コンテキスト（プロンプトキャッシュ境界） ===",
        "## 元のレビューコメント（あなたの指摘）",
        f"ファイル: {parent.get('path', '')}",
        parent.get("body", ""),
        "",
        "## 開発者の返信",
        latest_reply.get("body", ""),
    ]

    if diff:
        prompt_lines += [
            "",
            "## PR の diff（修正内容）",
            "```diff",
            diff,
            "```",
        ]

    return "\n".join(prompt_lines)


def _cmd_run(pr_number_str: str) -> None:
    gitea_url = os.environ.get("GITEA_URL", "http://localhost:3000")
    repo = os.environ.get("REPO", "AME-Team/AME-AI-Review-System")
    token = os.environ.get("REVIEWER_TOKEN", "")
    reviewer_name = os.environ.get("REVIEWER_NAME", "ame-ai-reviewer")
    base_ref = os.environ.get("BASE_REF", "main")
    pr_number = int(pr_number_str)

    if not token:
        print("[reply] ERROR: REVIEWER_TOKEN not set", file=sys.stderr)
        return

    print(f"[reply] Scanning PR #{pr_number} for pending reply threads...")
    pending = _get_pending_threads(
        gitea_url,
        repo,
        str(pr_number),
        token,
        reviewer_name,
    )
    pending_count = len(pending)

    if pending_count == 0:
        print("[reply] No pending threads, done.")
        return

    print(f"[reply] {pending_count} thread(s) need reply.")

    for thread_id in pending:
        if not str(thread_id).isdigit():
            print(f"[reply] WARNING: Invalid THREAD_ID '{thread_id}', skip.")
            continue

        print(f"[reply] Processing thread {thread_id}...")

        # Stale-loop detection
        stale_status = _check_stale(
            gitea_url,
            repo,
            str(pr_number),
            str(thread_id),
            token,
            reviewer_name,
        )
        if stale_status == "stale":
            print(f"[reply] Thread {thread_id} is in stale-loop. Forcing LGTM.")
            body = _DEFAULT_LGTM
            status = _post_reply(gitea_url, repo, pr_number, thread_id, token, body)
            print(f"[reply] Thread {thread_id} (stale-loop LGTM) → HTTP {status}.")
            continue

        # Build prompt
        prompt = _build_prompt_for_thread(
            gitea_url,
            repo,
            str(pr_number),
            str(thread_id),
            token,
            reviewer_name,
            base_ref,
        )

        if not prompt:
            print(f"[reply] Prompt empty for thread {thread_id}, skip.")
            continue

        # Run engine
        engine_exit, engine_out = _run_engine(prompt)

        if engine_exit != 0 or not engine_out.strip():
            print("[reply] Engine failed, using default LGTM.")
            body = (
                "⚠️ エンジンエラーにより自動 LGTM しています。内容を確認してください。"
            )
        else:
            # Parse output
            parsed = _extract_json(engine_out)
            if parsed:
                body = str(parsed.get("reply", _DEFAULT_LGTM))
            else:
                print(
                    f"[reply] JSON extraction failed: {engine_out[:300]}",
                    file=sys.stderr,
                )
                body = _DEFAULT_LGTM

        # Post reply
        status = _post_reply(gitea_url, repo, pr_number, thread_id, token, body)
        print(f"[reply] Thread {thread_id} → HTTP {status}.")

    print("[reply] Done.")


# ============================================================================
# Main entrypoint
# ============================================================================


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv

    if len(argv) < _MIN_ARGS:
        sys.exit("Usage: reply.py build|parse|pending|stale-check|run ...")

    cmd = argv[1]
    if cmd == "build":
        if len(argv) < _REQUIRED_ARGS_BUILD:
            sys.exit("Usage: reply.py build <pr_number> <thread_id>")
        _cmd_build(argv[2], argv[3])
    elif cmd == "parse":
        if len(argv) < _REQUIRED_ARGS_PARSE:
            sys.exit("Usage: reply.py parse <claude_out_path>")
        _cmd_parse(argv[2])
    elif cmd == "pending":
        if len(argv) < _REQUIRED_ARGS_PENDING:
            sys.exit("Usage: reply.py pending <pr_number>")
        _cmd_pending(argv[2])
    elif cmd == "stale-check":
        if len(argv) < _REQUIRED_ARGS_STALE_CHECK:
            sys.exit("Usage: reply.py stale-check <pr_number> <thread_id>")
        _cmd_stale_check(argv[2], argv[3])
    elif cmd == "run":
        if len(argv) < _REQUIRED_ARGS_RUN:
            sys.exit("Usage: reply.py run <pr_number>")
        _cmd_run(argv[2])
    else:
        sys.exit(f"Unknown command: {cmd}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
