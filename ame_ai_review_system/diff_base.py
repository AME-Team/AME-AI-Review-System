"""Diff 比較元 (ベース) の自動解決.

スタックブランチ (feature → feature2) では origin/{base} との 3-dot diff が
累積しすぎて無関係な変更までレビュー対象になるため、分岐元を自動判定して
レビュー範囲を狭める (Issue #55 I1)。

解決順:
  1. ``@{upstream}`` が設定されており origin/{base} と異なる場合はそれを使用。
  2. ``git merge-base --fork-point origin/{base} HEAD`` が通常の merge-base と
     異なる場合はその SHA を使用 (ローカルの分岐履歴に基づくフォーク点)。
  3. フォールバックは従来どおり ``origin/{base}`` (3-dot で merge-base 解決)。
"""

from __future__ import annotations

import subprocess

_GIT_TIMEOUT_SECONDS = 10


def _run_git(args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=_GIT_TIMEOUT_SECONDS,
            encoding="utf-8",
            errors="replace",
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _upstream_ref() -> str:
    """カレントブランチの上流追跡 ref (例: ``origin/feature``) を返す."""
    return _run_git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])


def resolve_diff_base(base_ref: str) -> str:
    """レビュー diff の比較元 ref を返す (詳細はモジュール docstring)."""
    upstream = _upstream_ref()
    if upstream and upstream != f"origin/{base_ref}":
        return upstream

    plain_base = _run_git(["merge-base", f"origin/{base_ref}", "HEAD"])
    fork_point = _run_git(["merge-base", "--fork-point", f"origin/{base_ref}", "HEAD"])
    if fork_point and plain_base and fork_point != plain_base:
        return fork_point

    return f"origin/{base_ref}"


def diff_range(base_ref: str) -> str:
    """``git diff`` へ渡す 3-dot レンジ表記 (``<base>...HEAD``) を返す."""
    return f"{resolve_diff_base(base_ref)}...HEAD"


def commit_range(base_ref: str) -> str:
    """``git log`` へ渡す 2-dot レンジ表記 (``<base>..HEAD``) を返す."""
    return f"{resolve_diff_base(base_ref)}..HEAD"
