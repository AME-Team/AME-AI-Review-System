# pyright: basic
from __future__ import annotations

from typing import Any

import pytest
from ame_ai_review_system import diff_base


def _fake_run_git(
    monkeypatch: pytest.MonkeyPatch, table: dict[tuple[str, ...], str]
) -> None:
    def fake(args: list[str]) -> str:
        return table.get(tuple(args), "")

    monkeypatch.setattr(diff_base, "_run_git", fake)


def test_resolve_uses_upstream_when_different(monkeypatch: pytest.MonkeyPatch) -> None:
    # Issue #55 I1: スタックブランチは上流追跡 (origin/feature) を優先する。
    _fake_run_git(
        monkeypatch,
        {
            (
                "rev-parse",
                "--abbrev-ref",
                "--symbolic-full-name",
                "@{u}",
            ): "origin/feature"
        },
    )
    assert diff_base.resolve_diff_base("main") == "origin/feature"


def test_resolve_uses_fork_point_when_different(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # @{u} が origin/main と同値なら fork-point による分岐点検出を試す。
    _fake_run_git(
        monkeypatch,
        {
            (
                "rev-parse",
                "--abbrev-ref",
                "--symbolic-full-name",
                "@{u}",
            ): "origin/main",
            ("merge-base", "origin/main", "HEAD"): "aaaa",
            ("merge-base", "--fork-point", "origin/main", "HEAD"): "bbbb",
        },
    )
    assert diff_base.resolve_diff_base("main") == "bbbb"


def test_resolve_falls_back_when_fork_point_equals_merge_base(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_run_git(
        monkeypatch,
        {
            (
                "rev-parse",
                "--abbrev-ref",
                "--symbolic-full-name",
                "@{u}",
            ): "origin/main",
            ("merge-base", "origin/main", "HEAD"): "aaaa",
            ("merge-base", "--fork-point", "origin/main", "HEAD"): "aaaa",
        },
    )
    assert diff_base.resolve_diff_base("main") == "origin/main"


def test_resolve_falls_back_without_upstream(monkeypatch: pytest.MonkeyPatch) -> None:
    # 上流なし・fork-point 失敗時は従来どおり origin/{base}。
    _fake_run_git(
        monkeypatch,
        {
            ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"): "",
            ("merge-base", "origin/main", "HEAD"): "aaaa",
            ("merge-base", "--fork-point", "origin/main", "HEAD"): "",
        },
    )
    assert diff_base.resolve_diff_base("main") == "origin/main"


def test_diff_and_commit_ranges(monkeypatch: pytest.MonkeyPatch) -> None:
    # レンジ表記は resolve_diff_base に従う (上流なしの場合は origin/{base} に落ちる)。
    _fake_run_git(
        monkeypatch,
        {
            (
                "rev-parse",
                "--abbrev-ref",
                "--symbolic-full-name",
                "@{u}",
            ): "origin/main",
            ("merge-base", "origin/main", "HEAD"): "aaaa",
            ("merge-base", "--fork-point", "origin/main", "HEAD"): "aaaa",
        },
    )
    assert diff_base.diff_range("main") == "origin/main...HEAD"
    assert diff_base.commit_range("main") == "origin/main..HEAD"


def test_run_git_failure_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess
    from types import SimpleNamespace

    def fake_run(*_a: Any, **_kw: Any) -> SimpleNamespace:
        return SimpleNamespace(returncode=1, stdout="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert not diff_base._run_git(["merge-base", "origin/main", "HEAD"])
