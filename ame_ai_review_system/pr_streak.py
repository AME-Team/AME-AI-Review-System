from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any

from . import payload

_STREAK_THRESHOLD = 2
_COMMENT_MARKER = "<!-- ai-review-streak -->"
_STREAK_RE = re.compile(r"streak:\s*(\d+)")
_HEAD_RE = re.compile(r"head:\s*([0-9a-fA-F]+)")
_MIN_ARGS_GET = 3
_MIN_ARGS_SET = 4
_MIN_ARGS_EVALUATE = 4
_PR_NUMBER_ARG_INDEX = 2
_COMMENTS_PAGE_LIMIT = 50
_GIT_TIMEOUT_SECONDS = 5


def _current_head_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=_GIT_TIMEOUT_SECONDS,
            encoding="utf-8",
            errors="replace",
        )
    except (subprocess.SubprocessError, OSError):
        return ""
    return result.stdout.strip()


def _pr_comments_url(pr_number: int, gitea_url: str, repo: str) -> str:
    return (
        f"{gitea_url}/api/v1/repos/{repo}/issues/{pr_number}/comments"
        f"?limit={_COMMENTS_PAGE_LIMIT}"
    )


def _single_comment_url(comment_id: int, gitea_url: str, repo: str) -> str:
    return f"{gitea_url}/api/v1/repos/{repo}/issues/comments/{comment_id}"


def _token() -> str:
    token_file = (
        pathlib.Path.home() / ".config" / "ame-ai-review-system" / "gitea.token"
    )
    if token_file.exists():
        content = token_file.read_text(encoding="utf-8").strip()
        if content:
            return content
    gitea = os.environ.get("GITEA_TOKEN")
    if gitea:
        return gitea
    return os.environ.get("REVIEWER_TOKEN") or ""


def _gitea_env() -> tuple[str, str]:
    gitea_url = os.environ.get("GITEA_URL", "http://localhost:3000")
    repo = os.environ.get("GITHUB_REPOSITORY", "AME-Team/AME-AI-Review-System")
    return gitea_url, repo


def _request(
    url: str,
    token: str,
    data: bytes | None = None,
    method: str | None = None,
) -> bytes:
    headers = {"Authorization": f"token {token}"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=10) as resp:
        result: bytes = resp.read()
        return result


def _find_streak_comment(
    comments: list[dict[str, Any]],
) -> tuple[int, int, str] | None:
    """Return (comment_id, streak, head_sha) for the latest streak marker, or None."""
    for comment in reversed(comments):
        body = str(comment.get("body", ""))
        if _COMMENT_MARKER in body:
            m = _STREAK_RE.search(body)
            streak = int(m.group(1)) if m else 0
            h = _HEAD_RE.search(body)
            head = h.group(1) if h else ""
            cid = comment.get("id")
            if cid is None:
                continue
            return int(cid), streak, head
    return None


def _read_pr_comments(
    pr_number: int,
    gitea_url: str,
    repo: str,
    token: str,
) -> list[dict[str, Any]]:
    url = _pr_comments_url(pr_number, gitea_url, repo)
    try:
        data = _request(url, token)
        comments = json.loads(data)
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        print(f"[pr_streak] failed to read PR comments: {exc}", file=sys.stderr)
        return []
    return comments if isinstance(comments, list) else []


def cmd_get(pr_number: int) -> int:
    gitea_url, repo = _gitea_env()
    token = _token()
    if not token:
        print("0")
        return 1
    comments = _read_pr_comments(pr_number, gitea_url, repo, token)
    result = _find_streak_comment(comments)
    print(result[1] if result else "0")
    return 0


def cmd_set(pr_number: int, streak: int) -> int:
    """Set or update streak. Updates existing marker comment if one exists, else posts new.

    This avoids accumulating multiple streak comments on the PR over time.
    """
    gitea_url, repo = _gitea_env()
    token = _token()
    if not token:
        return 1
    head = _current_head_sha()
    body = f"{_COMMENT_MARKER}\nstreak: {streak}"
    if head:
        body += f"\nhead: {head}"
    body_data = json.dumps({"body": body}).encode("utf-8")

    # Find existing streak comment to update rather than creating a new one.
    comments = _read_pr_comments(pr_number, gitea_url, repo, token)
    existing = _find_streak_comment(comments)

    try:
        if existing:
            cid = existing[0]
            url = _single_comment_url(cid, gitea_url, repo)
            _request(url, token, body_data, method="PATCH")
        else:
            url = _pr_comments_url(pr_number, gitea_url, repo)
            _request(url, token, body_data)
    except (urllib.error.URLError, urllib.error.HTTPError) as exc:
        print(f"[pr_streak] set failed: {exc}", file=sys.stderr)
        return 1
    return 0


def cmd_check(pr_number: int) -> int:
    """Exit 0 if approved (streak >= 3 AND no new push since approval), exit 1 otherwise."""
    gitea_url, repo = _gitea_env()
    token = _token()
    if not token:
        return 1
    comments = _read_pr_comments(pr_number, gitea_url, repo, token)
    result = _find_streak_comment(comments)
    if result and result[1] >= _STREAK_THRESHOLD:
        # streak 到達後に新たな push があった場合はレビューを再実行する。
        stored_head = result[2]
        current_head = _current_head_sha()
        if stored_head and current_head and stored_head != current_head:
            return 1
        return 0
    return 1


def cmd_evaluate(pr_number: int, review_path: str) -> int:
    """Parse review JSON, compute new streak, update, and print result JSON."""
    review, is_fallback = payload.parse_review_json_with_flag(review_path)
    if is_fallback:
        result = {
            "allow": False,
            "streak": 0,
            "reason": "JSON パース失敗のため継続 (fail-closed)",
            "total": 0,
        }
        print(json.dumps(result, ensure_ascii=False))
        print(f"[pr_streak] {result['reason']}", file=sys.stderr)
        return 0

    comments = review.get("comments", [])
    if not isinstance(comments, list):
        comments = []
    clean = [c for c in comments if isinstance(c, dict)]

    blocking = [c for c in clean if _is_blocking(c)]
    total = len(clean)

    current = 0
    gitea_url, repo = _gitea_env()
    token = _token()
    if token:
        pr_comments = _read_pr_comments(pr_number, gitea_url, repo, token)
        found = _find_streak_comment(pr_comments)
        if found:
            current = found[1]

    if total == 0:
        new = 0
        allow = True
        reason = "指摘 0 件のため PASS"
    elif not blocking:
        new = current + 1
        if new >= _STREAK_THRESHOLD:
            allow = True
            reason = f"LOW のみ連続 {new} 回目のため PASS (終了条件達成)"
        else:
            allow = False
            reason = f"LOW 指摘のみ (streak {new}/{_STREAK_THRESHOLD})"
    else:
        new = 0
        allow = False
        reason = f"blocking 指摘 {len(blocking)} 件のため継続"

    if token:
        set_result = cmd_set(pr_number, new)
        if set_result != 0:
            print(
                f"[pr_streak] warning: streak persistence failed (exit={set_result})",
                file=sys.stderr,
            )
    else:
        set_result = 0

    result = {
        "allow": allow,
        "streak": new,
        "reason": reason,
        "total": total,
        "streak_saved": set_result == 0,
    }
    print(json.dumps(result, ensure_ascii=False))
    print(f"[pr_streak] {reason}", file=sys.stderr)
    return 0


def _is_blocking(comment: dict[str, Any]) -> bool:
    severity = str(comment.get("severity", "")).upper().strip()
    return severity not in {"LOW", "INFO"}


def main(argv: list[str]) -> int:
    if len(argv) < _MIN_ARGS_GET:
        print(
            f"Usage: {argv[0]} <get|set|check|evaluate> <pr_number> [args]",
            file=sys.stderr,
        )
        return 2
    cmd = argv[1]
    try:
        pr_number = int(argv[_PR_NUMBER_ARG_INDEX])
    except (ValueError, IndexError):
        print(
            f"Invalid PR number: {argv[_PR_NUMBER_ARG_INDEX] if len(argv) > _PR_NUMBER_ARG_INDEX else '?'}",
            file=sys.stderr,
        )
        return 2

    if cmd == "get":
        return cmd_get(pr_number)
    if cmd == "set":
        if len(argv) < _MIN_ARGS_SET:
            print("Usage: set <pr_number> <streak>", file=sys.stderr)
            return 2
        return cmd_set(pr_number, int(argv[3]))
    if cmd == "check":
        return cmd_check(pr_number)
    if cmd == "evaluate":
        if len(argv) < _MIN_ARGS_EVALUATE:
            print("Usage: evaluate <pr_number> <review_json_path>", file=sys.stderr)
            return 2
        return cmd_evaluate(pr_number, argv[3])
    print(f"Unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
