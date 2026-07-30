# pyright: basic
from __future__ import annotations

import json
from pathlib import Path

import pytest
from ame_ai_review_system import init_project


def _run(
    tmp_path: Path,
    *,
    engine: str = "claude",
    sdk_lang: str = "python",
    profile: str = "python",
    reviewer_name: str = "ame-ai-reviewer",
    force: bool = False,
) -> Path:
    init_project.run_init(
        target_dir=str(tmp_path),
        profile=profile,
        engine=engine,
        sdk_lang=sdk_lang,
        reviewer_name=reviewer_name,
        force=force,
        run_npm=False,
    )
    return tmp_path


def test_init_creates_ame_review_config(tmp_path: Path) -> None:
    root = _run(tmp_path, engine="claude")
    assert (root / ".ame-review" / "config.json").exists()
    assert (root / ".ame-review" / "review_prompt.txt").exists()
    assert (root / ".ame-review" / ".semgrep" / "rules.yml").exists()
    user = json.loads(
        (root / ".ame-review" / "config.user.json").read_text(encoding="utf-8")
    )
    assert user["engine"] == "claude"
    assert user["sdk_lang"] == "python"
    assert user["model"] == "sonnet"


def test_init_opencode_no_ts(tmp_path: Path) -> None:
    root = _run(tmp_path, engine="opencode", sdk_lang="python")
    # opencode は CLI 起動のため TS サイドカーを生成しない
    assert not (root / ".ame-review" / "engines-ts").exists()
    user = json.loads((root / ".ame-review" / "config.user.json").read_text())
    assert user["engine"] == "opencode"
    assert "sdk_lang" not in user


def test_init_antigravity_no_node(tmp_path: Path) -> None:
    root = _run(tmp_path, engine="antigravity")
    assert not (root / ".ame-review" / "engines-ts").exists()
    user = json.loads((root / ".ame-review" / "config.user.json").read_text())
    assert user["engine"] == "antigravity"


def test_init_generates_workflows(tmp_path: Path) -> None:
    root = _run(tmp_path, engine="claude", reviewer_name="my-reviewer")
    cmd = (root / ".github" / "workflows" / "ai-review-command.yml").read_text()
    reply = (root / ".github" / "workflows" / "ai-review-reply.yml").read_text()
    assert "my-reviewer[bot]" in cmd
    assert "MY_REVIEWER_APP_ID" in cmd
    assert "ame-ai-review-system[claude]" in cmd
    assert "ANTHROPIC_API_KEY" in cmd
    assert "my-reviewer" in reply


def test_init_workflow_opencode_cli(tmp_path: Path) -> None:
    root = _run(tmp_path, engine="opencode")
    cmd = (root / ".github" / "workflows" / "ai-review-command.yml").read_text()
    assert "actions/setup-node" in cmd  # node needed for opencode CLI install
    assert "pip install 'ame-ai-review-system'" in cmd  # no python extra for opencode
    assert "OPENCODE_AUTH_B64" in cmd
    assert "npm install -g opencode-ai" in cmd


def test_init_workflow_antigravity_no_node(tmp_path: Path) -> None:
    root = _run(tmp_path, engine="antigravity")
    cmd = (root / ".github" / "workflows" / "ai-review-command.yml").read_text()
    assert "actions/setup-node" not in cmd
    assert "ame-ai-review-system[antigravity]" in cmd
    assert "GEMINI_API_KEY" in cmd


def test_init_precommit_profile(tmp_path: Path) -> None:
    root = _run(tmp_path, profile="minimal")
    pc = (root / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert "ai-precommit-review" in pc
    assert "ai-skip-guard" in pc


def test_init_gitignore_entries(tmp_path: Path) -> None:
    root = _run(tmp_path)
    gi = (root / ".gitignore").read_text(encoding="utf-8")
    assert ".ame-review/config.user.json" in gi
    assert ".ame-review/state/" in gi


def test_init_idempotent_skip(tmp_path: Path) -> None:
    root = _run(tmp_path, engine="claude")
    user_before = (root / ".ame-review" / "config.user.json").read_text()
    # 再実行 (force=False) は既存ファイルを上書きしない。
    _run(tmp_path, engine="opencode", force=False)
    user_after = (root / ".ame-review" / "config.user.json").read_text()
    assert user_before == user_after
    assert json.loads(user_after)["engine"] == "claude"


def test_init_force_overwrites(tmp_path: Path) -> None:
    root = _run(tmp_path, engine="claude")
    _run(tmp_path, engine="opencode", force=True)
    user_after = json.loads((root / ".ame-review" / "config.user.json").read_text())
    assert user_after["engine"] == "opencode"


def test_init_precommit_appends_to_existing(tmp_path: Path) -> None:
    existing = tmp_path / ".pre-commit-config.yaml"
    existing.write_text(
        "minimum_pre_commit_version: '4.0.0'\nrepos:\n  - repo: https://example.com\n"
        "    rev: v1\n    hooks: []\n",
        encoding="utf-8",
    )
    root = _run(tmp_path, profile="minimal")
    content = (root / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert "https://example.com" in content
    assert "ai-precommit-review" in content


def test_init_precommit_skips_when_hooks_present(tmp_path: Path) -> None:
    existing = tmp_path / ".pre-commit-config.yaml"
    existing.write_text(
        "minimum_pre_commit_version: '4.0.0'\nrepos:\n"
        "  # AME AI Review System — Gate 1 AI review hooks\n"
        "  - repo: local\n    hooks: []\n",
        encoding="utf-8",
    )
    _run(tmp_path, profile="minimal")
    content = (tmp_path / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert content.count("ai-precommit-review") == 0


def test_init_invalid_profile(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        init_project.run_init(
            target_dir=str(tmp_path),
            profile="bogus",
            engine="claude",
            sdk_lang="python",
            reviewer_name="r",
            run_npm=False,
        )


def test_engine_meta_claude_python_no_node() -> None:
    meta = init_project.engine_meta("claude", "python")
    assert meta["needs_ts_node"] is False
    assert meta["needs_opencode_cli"] is False
    assert meta["pip_extra"] == "claude"


def test_engine_meta_claude_typescript_needs_node() -> None:
    meta = init_project.engine_meta("claude", "typescript")
    assert meta["needs_ts_node"] is True
    assert meta["needs_opencode_cli"] is False
    assert not meta["pip_extra"]


def test_engine_meta_opencode_needs_cli() -> None:
    meta = init_project.engine_meta("opencode", "typescript")
    assert meta["needs_ts_node"] is False
    assert meta["needs_opencode_cli"] is True
    assert not meta["pip_extra"]
