# pyright: basic
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from ame_ai_review_system import (
    paths,
    post_commit_reset,
    precommit_review,
    precommit_state,
    review_config,
)
from ame_ai_review_system.precommit_review import (
    _build_prompt as build_prompt,
)
from ame_ai_review_system.precommit_review import (
    _decide as decide,
)
from ame_ai_review_system.precommit_review import (
    _format_issue as format_issue,
)
from ame_ai_review_system.precommit_review import (
    _is_blocking as is_blocking,
)
from ame_ai_review_system.precommit_review import (
    _run_static_checks as run_static_checks,
)
from ame_ai_review_system.precommit_review import (
    _truncate_diff as truncate_diff,
)

# ---------------------------
# decide / is_blocking / truncate_diff (pure functions)
# ---------------------------


def test_decide_zero_issues_passes_and_resets() -> None:
    allow, new_streak, reason = decide([], 2)
    assert allow is True
    assert new_streak == 0
    assert "0 件" in reason


def test_decide_blocking_resets_streak() -> None:
    comments = [{"severity": "HIGH"}]
    allow, new_streak, reason = decide(comments, 2)
    assert allow is False
    assert new_streak == 0
    assert "blocking" in reason


def test_decide_low_only_streak_0_fails() -> None:
    comments = [{"severity": "LOW"}]
    allow, new_streak, _ = decide(comments, 0)
    assert allow is False
    assert new_streak == 1


def test_decide_low_only_streak_1_passes() -> None:
    comments = [{"severity": "LOW"}]
    allow, new_streak, reason = decide(comments, 1)
    assert allow is True
    assert new_streak == 2
    assert "無限ループ回避" in reason


def test_decide_low_only_streak_2_passes() -> None:
    comments = [{"severity": "LOW"}]
    allow, new_streak, reason = decide(comments, 2)
    assert allow is True
    assert new_streak == 3
    assert "無限ループ回避" in reason


def test_decide_mixed_severity_blocks_and_resets() -> None:
    comments = [{"severity": "LOW"}, {"severity": "CRITICAL"}]
    allow, new_streak, _ = decide(comments, 1)
    assert allow is False
    assert new_streak == 0


def test_decide_multiple_blocking() -> None:
    comments = [{"severity": "HIGH"}, {"severity": "MIDDLE"}]
    allow, new_streak, reason = decide(comments, 0)
    assert allow is False
    assert new_streak == 0
    assert "2 件" in reason


def test_is_blocking_case_insensitive() -> None:
    # fail-closed: LOW/INFO 以外は unknown も含めて blocking 扱い。
    assert is_blocking({"severity": "critical"})
    assert is_blocking({"severity": "High"})
    assert is_blocking({"severity": "MIDDLE"})
    assert is_blocking({"severity": "WARNING"})
    assert is_blocking({"severity": "weird-unknown"})
    assert is_blocking({"severity": ""})
    assert is_blocking({})
    assert not is_blocking({"severity": "LOW"})
    assert not is_blocking({"severity": "INFO"})
    assert not is_blocking({"severity": "low"})


def test_is_blocking_whitespace_tolerant() -> None:
    assert is_blocking({"severity": "  HIGH  "})


def test_truncate_diff_short_unchanged() -> None:
    diff = "line1\nline2\n"
    assert truncate_diff(diff) == diff


def test_truncate_diff_empty_unchanged() -> None:
    assert not truncate_diff("")


def test_truncate_diff_long_gets_capped() -> None:
    diff = "\n".join(f"line{i}" for i in range(5000))
    truncated = truncate_diff(diff)
    assert "truncated from 5000 to 4000 lines" in truncated
    assert truncated.count("\n") < diff.count("\n")


def test_truncate_diff_closes_unmatched_code_fence() -> None:
    # 開いた ``` が切詰めで閉じられない場合、閉じタグを補完すること。
    diff = "```diff\n" + "\n".join(f"line{i}" for i in range(5000))
    truncated = truncate_diff(diff)
    # ``` が偶数個 (開く+閉じる) になっていること
    assert truncated.count("```") % 2 == 0


def test_truncate_diff_keeps_balanced_fence() -> None:
    # 既に閉じているフェンスは補完しないこと。
    diff = "```diff\nline1\n```\n" + "\n".join(f"line{i}" for i in range(5000))
    truncated = truncate_diff(diff)
    # 開始(```diff) + 終了(```) の 2 個のみで、補完されないこと。
    assert truncated.count("```") == 2


def test_truncate_diff_ignores_inline_backticks() -> None:
    # diff 内のバックティック (行頭以外) はフェンス判定に使われないこと。
    diff = "```diff\n+let x = `inline`\n" + "\n".join(f"line{i}" for i in range(5000))
    truncated = truncate_diff(diff)
    # 行頭 ``` は 1 個 (````diff`) のみ → 開いたまま → 補完で閉じタグ追加 → 2 個
    assert truncated.count("```") == 2


def test_truncate_diff_at_boundary_unchanged() -> None:
    diff = "\n".join(f"line{i}" for i in range(4000))
    assert truncate_diff(diff) == diff


# ---------------------------
# format_issue / build_prompt
# ---------------------------


def test_format_issue_renders_fields() -> None:
    out = format_issue(
        {
            "severity": "high",
            "path": "src/app.py",
            "line": 42,
            "title": "bug",
            "body": "fix me",
        },
    )
    assert "[HIGH]" in out
    assert "src/app.py:42" in out
    assert "bug" in out
    assert "fix me" in out


def test_format_issue_missing_fields_safe() -> None:
    out = format_issue({})
    assert "[?]" in out
    assert "?:?" in out


def test_build_prompt_contains_required_sections() -> None:
    prompt = build_prompt(
        "main",
        "feature/x",
        ["src/a.py", "src/b.py"],
        "diff content",
        "BASE PROMPT",
    )
    assert prompt.startswith("BASE PROMPT")
    assert "feature/x" in prompt
    assert "src/a.py" in prompt
    assert "src/b.py" in prompt
    assert "diff content" in prompt


def test_build_prompt_adds_reference_note_for_excluded_package(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Issue #47: 除外した vendored パッケージが差分から参照されるとプロンプトへ注記される。
    root = tmp_path / "repo"
    pkg = root / "ame_ai_review_system"
    pkg.mkdir(parents=True)
    monkeypatch.setattr(paths, "package_dir", lambda: pkg)
    monkeypatch.setattr(paths, "project_root", lambda: root)
    monkeypatch.setattr(
        review_config,
        "load_config",
        lambda: {"review_include_package_dir": False},
    )
    monkeypatch.setattr(review_config, "_package_exists_in_repo", lambda _rel: True)
    monkeypatch.setattr(
        review_config,
        "_package_subpaths_exist",
        lambda _rel, _subpaths: True,
    )
    prompt = build_prompt(
        "main",
        "feature/x",
        [".pre-commit-config.yaml"],
        "python3 -m ame_ai_review_system.skip_guard を追加",
        "BASE PROMPT",
    )
    assert "注記: vendored パッケージの参照" in prompt
    assert "存在" in prompt


def test_build_prompt_omits_reference_note_without_reference(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    pkg = root / "ame_ai_review_system"
    pkg.mkdir(parents=True)
    monkeypatch.setattr(paths, "package_dir", lambda: pkg)
    monkeypatch.setattr(paths, "project_root", lambda: root)
    monkeypatch.setattr(
        review_config,
        "load_config",
        lambda: {"review_include_package_dir": False},
    )
    monkeypatch.setattr(review_config, "_package_exists_in_repo", lambda _rel: True)
    prompt = build_prompt(
        "main",
        "feature/x",
        ["src/app.py"],
        "diff content without reference",
        "BASE PROMPT",
    )
    assert "注記: vendored パッケージの参照" not in prompt


# ---------------------------
# main() end-to-end with mocked I/O
# ---------------------------


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Any]:
    """Set up common stubs for git/engine I/O and isolate under tmp_path."""
    monkeypatch.setattr(
        review_config,
        "load_config",
        lambda: {
            "precommit_review_enabled": True,
            "precommit_require_static_checks": True,
        },
    )
    monkeypatch.setattr(precommit_state, "current_branch", lambda: "feature")
    monkeypatch.setattr(precommit_state, "is_valid_branch", lambda _: True)
    monkeypatch.setattr(precommit_review, "_staged_files", lambda: ["foo.py"])
    monkeypatch.setattr(
        precommit_review,
        "_run_static_checks",
        lambda _f: (True, ""),
    )
    monkeypatch.setattr(precommit_review, "_build_diff", lambda _: "FAKE DIFF")
    monkeypatch.setattr(precommit_review, "_truncate_diff", lambda d: d)

    fake_proj = tmp_path / "proj"
    ame_dir = fake_proj / "ame-ai-review-system"
    ame_dir.mkdir(parents=True)
    (ame_dir / "review_prompt.txt").write_text("PROMPT", encoding="utf-8")
    monkeypatch.setattr(
        precommit_review,
        "_resolve_paths",
        lambda: (ame_dir / "review_prompt.txt", ame_dir / "engine.py"),
    )

    state_path = tmp_path / "state.json"
    monkeypatch.setattr(precommit_state, "state_file_path", lambda: state_path)
    return {"state_path": state_path, "ame_dir": ame_dir}


def _engine_returning(
    monkeypatch: pytest.MonkeyPatch,
    payload_dict: dict[str, Any],
) -> None:
    output = json.dumps(payload_dict)
    monkeypatch.setattr(
        precommit_review,
        "_run_engine",
        lambda _p, _e, _s: (0, output, ""),
    )


def test_main_skips_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        review_config,
        "load_config",
        lambda: {"precommit_review_enabled": False},
    )
    rc = precommit_review.main([])
    assert rc == 0


# ---------------------------
# _run_static_checks
# ---------------------------


def test_run_static_checks_no_python_files(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _: None)
    passed, detail = run_static_checks(["README.md", "config.yaml"])
    assert passed is True
    assert not detail


def _fake_subprocess_ok(
    _cmd: list[str],
    **_kw: Any,
) -> SimpleNamespace:
    return SimpleNamespace(returncode=0, stdout="", stderr="")


def test_run_static_checks_all_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(precommit_state, "run_git", lambda _: "/proj\n")
    monkeypatch.setattr(subprocess, "run", _fake_subprocess_ok)
    passed, detail = run_static_checks(["foo.py", "bar.py"])
    assert passed is True
    assert not detail


def test_run_static_checks_ruff_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(cmd: list[str], **_kw: Any) -> SimpleNamespace:
        if cmd[0] == "ruff" and cmd[1] == "check":
            return SimpleNamespace(returncode=1, stdout="E501 line too long", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(precommit_state, "run_git", lambda _: "/proj\n")
    monkeypatch.setattr(subprocess, "run", fake_run)
    passed, detail = run_static_checks(["foo.py"])
    assert passed is False
    assert "ruff check" in detail
    assert "E501" in detail


def test_run_static_checks_mypy_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(cmd: list[str], **_kw: Any) -> SimpleNamespace:
        if cmd[0] == "mypy":
            return SimpleNamespace(returncode=1, stdout="error: bad type", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(precommit_state, "run_git", lambda _: "/proj\n")
    monkeypatch.setattr(subprocess, "run", fake_run)
    passed, detail = run_static_checks(["foo.py"])
    assert passed is False
    assert "mypy" in detail


def test_run_static_checks_skips_missing_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(cmd: list[str], **_kw: Any) -> SimpleNamespace:
        if cmd[0] == "ruff":
            msg = "ruff not found"
            raise FileNotFoundError(msg)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(precommit_state, "run_git", lambda _: "/proj\n")
    monkeypatch.setattr(subprocess, "run", fake_run)
    passed, detail = run_static_checks(["foo.py"])
    assert passed is True
    assert not detail


def test_run_static_checks_ts_all_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(precommit_state, "run_git", lambda _: "/proj\n")
    monkeypatch.setattr(subprocess, "run", _fake_subprocess_ok)
    monkeypatch.setattr(
        review_config, "load_config", lambda: {"tsconfig_path": "tsconfig.json"}
    )
    passed, detail = run_static_checks(["app.ts", "component.tsx"])
    assert passed is True
    assert not detail


def test_run_static_checks_tsc_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(cmd: list[str], **_kw: Any) -> SimpleNamespace:
        if "tsc" in cmd[0] or (len(cmd) > 1 and "tsc" in cmd[1]):
            return SimpleNamespace(
                returncode=2,
                stdout="Type error: parameter has any type",
                stderr="",
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(precommit_state, "run_git", lambda _: "/proj\n")
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(
        review_config, "load_config", lambda: {"tsconfig_path": "tsconfig.json"}
    )
    passed, detail = run_static_checks(["app.ts"])
    assert passed is False
    assert "tsc" in detail
    assert "Type error" in detail


def test_run_static_checks_tsc_skipped_without_tsconfig(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(cmd: list[str], **_kw: Any) -> SimpleNamespace:
        if "tsc" in cmd[0]:
            return SimpleNamespace(returncode=2, stdout="should not run", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(precommit_state, "run_git", lambda _: "/proj\n")
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(review_config, "load_config", dict)
    passed, detail = run_static_checks(["app.ts"])
    assert passed is True
    assert not detail


def test_run_static_checks_eslint_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(cmd: list[str], **_kw: Any) -> SimpleNamespace:
        if "eslint" in cmd[0] or (len(cmd) > 1 and "eslint" in cmd[1]):
            return SimpleNamespace(
                returncode=1,
                stdout="eslint error: unexpected var",
                stderr="",
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(precommit_state, "run_git", lambda _: "/proj\n")
    monkeypatch.setattr(subprocess, "run", fake_run)
    passed, detail = run_static_checks(["app.ts"])
    assert passed is False
    assert "eslint" in detail
    assert "eslint error" in detail


# ---------------------------
# main() — static checks integration
# ---------------------------


@pytest.mark.usefixtures("env")
def test_main_blocks_when_static_checks_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        precommit_review,
        "_run_static_checks",
        lambda _f: (False, "ruff check:\nE501 line too long"),
    )
    monkeypatch.setattr(
        precommit_review,
        "_run_engine",
        lambda _p, _e, _s: (0, '{"summary":"ok","comments":[]}', ""),
    )
    rc = precommit_review.main([])
    assert rc == 1


@pytest.mark.usefixtures("env")
def test_main_hides_engine_banner_when_gate1_false(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Issue #40: show_engine_info_gate1=false でエンジン情報バナーを抑止する。
    monkeypatch.setattr(
        review_config,
        "load_config",
        lambda: {
            "precommit_review_enabled": True,
            "precommit_require_static_checks": False,
            "show_engine_info_gate1": False,
        },
    )
    _engine_returning(monkeypatch, {"summary": "ok", "comments": []})
    rc = precommit_review.main([])
    assert rc == 0
    err = capsys.readouterr().err
    assert "running AI review" not in err


@pytest.mark.usefixtures("env")
def test_main_shows_engine_banner_by_default(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Issue #40: 既定 (gate1 未設定) ではエンジン情報バナーを表示する。
    _engine_returning(monkeypatch, {"summary": "ok", "comments": []})
    rc = precommit_review.main([])
    assert rc == 0
    err = capsys.readouterr().err
    assert "running AI review" in err


@pytest.mark.usefixtures("env")
def test_main_dry_run_static_checks_fail_returns_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        precommit_review,
        "_run_static_checks",
        lambda _f: (False, "ruff check:\nE501"),
    )
    rc = precommit_review.main(["--dry-run"])
    assert rc == 0


@pytest.mark.usefixtures("env")
def test_main_skips_static_checks_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        review_config,
        "load_config",
        lambda: {
            "precommit_review_enabled": True,
            "precommit_require_static_checks": False,
        },
    )
    called: list[str] = []

    def _fake_static_checks(_f: list[str]) -> tuple[bool, str]:
        called.append("checked")
        return (True, "")

    monkeypatch.setattr(
        precommit_review,
        "_run_static_checks",
        _fake_static_checks,
    )
    _engine_returning(monkeypatch, {"summary": "ok", "comments": []})
    rc = precommit_review.main([])
    assert rc == 0
    assert called == []


@pytest.mark.usefixtures("env")
def test_main_skips_when_no_staged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(precommit_review, "_staged_files", list)
    rc = precommit_review.main([])
    assert rc == 0


@pytest.mark.usefixtures("env")
def test_main_skips_when_detached_head(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(precommit_state, "current_branch", lambda: "HEAD")
    rc = precommit_review.main([])
    assert rc == 0


@pytest.mark.usefixtures("env")
def test_main_skips_when_invalid_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(precommit_state, "current_branch", lambda: "bad branch")
    monkeypatch.setattr(precommit_state, "is_valid_branch", lambda _: False)
    rc = precommit_review.main([])
    assert rc == 0


@pytest.mark.usefixtures("env")
def test_main_blocks_when_engine_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        precommit_review,
        "_run_engine",
        lambda _p, _e, _s: (1, "", "boom"),
    )
    rc = precommit_review.main([])
    assert rc == 1


@pytest.mark.usefixtures("env")
def test_main_dry_run_engine_failure_returns_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        precommit_review,
        "_run_engine",
        lambda _p, _e, _s: (1, "", "boom"),
    )
    rc = precommit_review.main(["--dry-run"])
    assert rc == 0


def test_main_engine_failure_escape_hatch_after_three(
    monkeypatch: pytest.MonkeyPatch,
    env: dict[str, Any],
) -> None:
    # エンジン失敗が3回連続したら escape hatch で PASS する (LLM API 一時障害対策)。
    # engine_failure_streak は low_only_streak とは独立カウンタ。
    precommit_state.write_state(
        env["state_path"],
        {"branches": {"feature": {"engine_failure_streak": 2}}},
    )
    monkeypatch.setattr(
        precommit_review,
        "_run_engine",
        lambda _p, _e, _s: (1, "", "boom"),
    )
    rc = precommit_review.main([])
    assert rc == 0
    state = precommit_state.read_state(env["state_path"])
    assert state["branches"]["feature"]["engine_failure_streak"] == 3


@pytest.mark.usefixtures("env")
def test_main_blocks_when_engine_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        precommit_review,
        "_run_engine",
        lambda _p, _e, _s: (0, "   ", ""),
    )
    rc = precommit_review.main([])
    assert rc == 1


def test_main_blocks_on_blocking_issue_and_resets_streak(
    monkeypatch: pytest.MonkeyPatch,
    env: dict[str, Any],
) -> None:
    precommit_state.write_state(
        env["state_path"],
        {"branches": {"feature": {"low_only_streak": 2}}},
    )
    _engine_returning(
        monkeypatch,
        {
            "summary": "blocking",
            "comments": [
                {
                    "path": "foo.py",
                    "line": 1,
                    "severity": "HIGH",
                    "title": "T",
                    "body": "B",
                },
            ],
        },
    )
    rc = precommit_review.main([])
    assert rc == 1
    state = precommit_state.read_state(env["state_path"])
    assert state["branches"]["feature"]["low_only_streak"] == 0


def test_main_passes_on_zero_issues(
    monkeypatch: pytest.MonkeyPatch,
    env: dict[str, Any],
) -> None:
    _engine_returning(monkeypatch, {"summary": "ok", "comments": []})
    rc = precommit_review.main([])
    assert rc == 0
    state = precommit_state.read_state(env["state_path"])
    assert state["branches"]["feature"]["low_only_streak"] == 0


def test_main_low_only_streak_increments(
    monkeypatch: pytest.MonkeyPatch,
    env: dict[str, Any],
) -> None:
    _engine_returning(
        monkeypatch,
        {
            "summary": "low only",
            "comments": [
                {
                    "path": "f",
                    "line": 1,
                    "severity": "LOW",
                    "title": "t",
                    "body": "b",
                },
            ],
        },
    )
    rc = precommit_review.main([])
    assert rc == 1
    state = precommit_state.read_state(env["state_path"])
    assert state["branches"]["feature"]["low_only_streak"] == 1


def test_main_low_only_at_threshold_passes(
    monkeypatch: pytest.MonkeyPatch,
    env: dict[str, Any],
) -> None:
    precommit_state.write_state(
        env["state_path"],
        {"branches": {"feature": {"low_only_streak": 1}}},
    )
    _engine_returning(
        monkeypatch,
        {
            "summary": "low only 2nd",
            "comments": [
                {
                    "path": "f",
                    "line": 1,
                    "severity": "LOW",
                    "title": "t",
                    "body": "b",
                },
            ],
        },
    )
    rc = precommit_review.main([])
    assert rc == 0
    state = precommit_state.read_state(env["state_path"])
    assert state["branches"]["feature"]["low_only_streak"] == 2


def test_main_dry_run_does_not_write_state(
    monkeypatch: pytest.MonkeyPatch,
    env: dict[str, Any],
) -> None:
    _engine_returning(
        monkeypatch,
        {
            "summary": "low",
            "comments": [
                {
                    "path": "f",
                    "line": 1,
                    "severity": "LOW",
                    "title": "t",
                    "body": "b",
                },
            ],
        },
    )
    rc = precommit_review.main(["--dry-run"])
    assert rc == 0
    assert not env["state_path"].exists()


def test_main_blocks_when_prompt_file_missing(
    monkeypatch: pytest.MonkeyPatch,
    env: dict[str, Any],
) -> None:
    env["ame_dir"].joinpath("review_prompt.txt").unlink()
    _engine_returning(monkeypatch, {"summary": "", "comments": []})
    rc = precommit_review.main([])
    assert rc == 1


@pytest.mark.usefixtures("env")
def test_main_blocks_on_malformed_engine_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # parse_review_json が fallback した場合は fail-closed でブロックする。
    monkeypatch.setattr(
        precommit_review,
        "_run_engine",
        lambda _p, _e, _s: (0, "not json at all", ""),
    )
    rc = precommit_review.main([])
    assert rc == 1


@pytest.mark.usefixtures("env")
def test_main_blocks_when_comments_key_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # comments キー自体が無い場合は不正出力としてブロックする (fail-closed)。
    _engine_returning(monkeypatch, {"summary": "LGTM"})
    rc = precommit_review.main([])
    assert rc == 1


@pytest.mark.usefixtures("env")
def test_main_blocks_when_comments_not_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # comments が list でない場合もブロックする。
    _engine_returning(monkeypatch, {"summary": "x", "comments": "not-a-list"})
    rc = precommit_review.main([])
    assert rc == 1


@pytest.mark.usefixtures("env")
def test_main_blocks_on_unknown_severity(monkeypatch: pytest.MonkeyPatch) -> None:
    # 未知 severity (WARNING 等) は fail-closed で blocking 扱い。
    _engine_returning(
        monkeypatch,
        {
            "summary": "warn",
            "comments": [
                {
                    "path": "f",
                    "line": 1,
                    "severity": "WARNING",
                    "title": "t",
                    "body": "b",
                },
            ],
        },
    )
    rc = precommit_review.main([])
    assert rc == 1


# ---------------------------
# post_commit_reset.main()
# ---------------------------


def _enable_post_commit_reset(monkeypatch: pytest.MonkeyPatch) -> None:
    """post_commit_reset は起動時に config を参照するため、テスト毎に有効化する."""
    monkeypatch.setattr(
        review_config,
        "load_config",
        lambda: {"precommit_review_enabled": True},
    )


def test_post_commit_reset_clears_streak(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _enable_post_commit_reset(monkeypatch)
    state_path = tmp_path / "state.json"
    precommit_state.write_state(
        state_path,
        {"branches": {"feature": {"low_only_streak": 2}}},
    )
    monkeypatch.setattr(precommit_state, "current_branch", lambda: "feature")
    monkeypatch.setattr(precommit_state, "is_valid_branch", lambda _: True)
    monkeypatch.setattr(precommit_state, "state_file_path", lambda: state_path)

    rc = post_commit_reset.main()
    assert rc == 0
    state = precommit_state.read_state(state_path)
    assert state["branches"]["feature"]["low_only_streak"] == 0


def test_post_commit_reset_noop_when_invalid_branch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _enable_post_commit_reset(monkeypatch)
    state_path = tmp_path / "state.json"
    precommit_state.write_state(
        state_path,
        {"branches": {"bad name": {"low_only_streak": 2}}},
    )
    monkeypatch.setattr(precommit_state, "current_branch", lambda: "bad name")
    monkeypatch.setattr(precommit_state, "is_valid_branch", lambda _: False)
    monkeypatch.setattr(precommit_state, "state_file_path", lambda: state_path)

    rc = post_commit_reset.main()
    assert rc == 0
    state = precommit_state.read_state(state_path)
    assert state["branches"]["bad name"]["low_only_streak"] == 2


def test_post_commit_reset_noop_when_detached_head(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _enable_post_commit_reset(monkeypatch)
    # detached HEAD (branch == "HEAD") はスキップし、state を書き換えない。
    state_path = tmp_path / "state.json"
    precommit_state.write_state(
        state_path,
        {"branches": {"feature": {"low_only_streak": 2}}},
    )
    monkeypatch.setattr(precommit_state, "current_branch", lambda: "HEAD")
    # is_valid_branch("HEAD") は True になるため、明示的な HEAD チェックが必須。
    monkeypatch.setattr(precommit_state, "is_valid_branch", lambda _: True)
    monkeypatch.setattr(precommit_state, "state_file_path", lambda: state_path)

    rc = post_commit_reset.main()
    assert rc == 0
    state = precommit_state.read_state(state_path)
    # 書き換えられていないこと
    assert state["branches"]["feature"]["low_only_streak"] == 2
    assert "HEAD" not in state["branches"]


def test_post_commit_reset_noop_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # precommit_review_enabled=false なら state を触らない。
    monkeypatch.setattr(
        review_config,
        "load_config",
        lambda: {"precommit_review_enabled": False},
    )
    state_path = tmp_path / "state.json"
    precommit_state.write_state(
        state_path,
        {"branches": {"feature": {"low_only_streak": 2}}},
    )
    monkeypatch.setattr(precommit_state, "current_branch", lambda: "feature")
    monkeypatch.setattr(precommit_state, "is_valid_branch", lambda _: True)
    monkeypatch.setattr(precommit_state, "state_file_path", lambda: state_path)

    rc = post_commit_reset.main()
    assert rc == 0
    state = precommit_state.read_state(state_path)
    assert state["branches"]["feature"]["low_only_streak"] == 2


def test_post_commit_reset_creates_state_if_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _enable_post_commit_reset(monkeypatch)
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(precommit_state, "current_branch", lambda: "feature")
    monkeypatch.setattr(precommit_state, "is_valid_branch", lambda _: True)
    monkeypatch.setattr(precommit_state, "state_file_path", lambda: state_path)

    rc = post_commit_reset.main()
    assert rc == 0
    state = precommit_state.read_state(state_path)
    assert state["branches"]["feature"]["low_only_streak"] == 0
