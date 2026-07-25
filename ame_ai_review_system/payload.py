"""JSON review payload builder for pr_review.sh."""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
from typing import Any, cast

_FALLBACK: dict[str, Any] = {
    "summary": "AIレビューの出力をJSONとして解析できませんでした。",
    "comments": [],
}


def parse_review_json_with_flag(path: str) -> tuple[dict[str, Any], bool]:
    raw = pathlib.Path(path).read_text(encoding="utf-8").strip()

    # 出力形式が旧エンベロープ({"type":"result","result":"..."})に戻った場合でも
    # レビューが壊れないよう、result 文字列を取り出して下流へ渡す。
    try:
        outer = json.loads(raw)
        if isinstance(outer, dict) and outer.get("type") == "result":
            result_val = outer.get("result")
            if not isinstance(result_val, str):
                print(
                    f"[parse_review_json] result field is not a string: {type(result_val).__name__}",
                    file=sys.stderr,
                )
                return _FALLBACK, True
            raw = result_val
    except json.JSONDecodeError:
        pass

    # Try ```json or plain ``` code fence (Claude may or may not include language tag)
    m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
    if m:
        candidate = m.group(1).strip()
        try:
            return cast("dict[str, Any]", json.loads(candidate)), False
        except json.JSONDecodeError:
            pass

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
                    return (
                        cast("dict[str, Any]", json.loads(raw[start_idx : i + 1])),
                        False,
                    )
                except json.JSONDecodeError:
                    start_idx = -1

    preview = raw[:500]
    print(
        f"[parse_review_json] JSON extraction failed. Raw preview (500 chars):\n{preview}",
        file=sys.stderr,
    )
    return _FALLBACK, True


def parse_review_json(path: str) -> dict[str, Any]:
    review, _is_fallback = parse_review_json_with_flag(path)
    return review


def build_valid_lines_map(base_ref: str) -> dict[str, set[int]]:
    """Diff に含まれる実ファイル行番号を集計する（GitHub review API の line 検証用）."""
    try:
        diff_text = subprocess.check_output(
            ["git", "diff", f"origin/{base_ref}...HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        return {}

    result: dict[str, set[int]] = {}
    current_file: str | None = None
    new_line_num = 0

    for line in diff_text.splitlines():
        m = re.match(r"^\+\+\+ b/(.+)$", line)
        if m:
            current_file = str(m.group(1))
            result[current_file] = set()
            new_line_num = 0
            continue
        if current_file is None:
            continue
        if line.startswith(("diff ", "index ", "--- ")):
            continue
        if line.startswith("@@"):
            m2 = re.search(r"\+(\d+)", line)
            if m2:
                new_line_num = int(m2.group(1)) - 1
            continue
        if line.startswith("-"):
            continue
        new_line_num += 1
        result[current_file].add(new_line_num)

    return result


_REQUIRED_ARGS = 2


def build_review_payloads(
    review: dict[str, Any],
    valid_lines: dict[str, set[int]],
    head_sha: str,
) -> list[dict[str, Any]]:
    """レビューコメントから GitHub review API のペイロード一覧を構築する."""
    severity_icon = {
        "CRITICAL": "🔴",
        "HIGH": "🟠",
        "MIDDLE": "🟡",
        "LOW": "🟢",
        "WARNING": "🟡",
        "INFO": "🟢",
    }
    individual_payloads: list[dict[str, Any]] = []
    inline_count = 0
    body_only_count = 0
    for c in review.get("comments", []):
        path = c.get("path", "")
        line = int(c.get("line", 1))
        icon = severity_icon.get(c.get("severity", "INFO"), "🟢")
        body = f"**{icon} {c.get('severity', 'INFO')}: {c.get('title', '')}**\n\n{c.get('body', '')}"

        if path not in valid_lines:
            body = f"📍 **指摘対象: `{path}` L{line}（diff 外のファイル）**\n\n{body}"
            individual_payloads.append(
                {
                    "event": "COMMENT",
                    "body": body,
                    "commit_id": head_sha,
                    "comments": [],
                },
            )
            body_only_count += 1
            continue

        lines = valid_lines[path]
        if not lines:
            body = f"📍 **指摘対象: `{path}` L{line}（追加行なし）**\n\n{body}"
            individual_payloads.append(
                {
                    "event": "COMMENT",
                    "body": body,
                    "commit_id": head_sha,
                    "comments": [],
                },
            )
            body_only_count += 1
            continue
        target_line = line if line in lines else None
        if target_line is None:
            body = f"📍 **指摘対象: `{path}` L{line}（diff 外の行）**\n\n{body}"
            target_line = min(lines, key=lambda x: abs(x - line))

        individual_payloads.append(
            {
                "event": "COMMENT",
                "body": "",
                "commit_id": head_sha,
                "comments": [
                    {"path": path, "line": target_line, "side": "RIGHT", "body": body}
                ],
            },
        )
        inline_count += 1

    parts = []
    if inline_count:
        parts.append(f"*{inline_count} 件のインラインコメントを添付しています。*")
    if body_only_count:
        parts.append(
            f"*{body_only_count} 件は diff 外または追加行なしのためレビューボディに記載。*"
        )
    joined = "\n".join(parts)
    summary_body = (
        f"### 総評\n{review.get('summary', '')}\n\n"
        f"---\n{joined}\n"
        f"<!-- reviewed-sha: {head_sha} -->"
    )
    summary_payload = {
        "event": "COMMENT",
        "body": summary_body,
        "commit_id": head_sha,
        "comments": [],
    }

    return [summary_payload, *individual_payloads]


def main() -> None:
    if len(sys.argv) < _REQUIRED_ARGS:
        sys.exit("Usage: build_review_payload.py <review_file>")
    review_file = sys.argv[1]
    base_ref = os.environ.get("BASE_REF", "main")

    review = parse_review_json(review_file)
    valid_lines = build_valid_lines_map(base_ref)

    try:
        head_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        sys.exit("[build_review_payload] ERROR: Failed to get HEAD SHA.")

    payloads = build_review_payloads(review, valid_lines, head_sha)
    print(json.dumps(payloads))


if __name__ == "__main__":
    main()
