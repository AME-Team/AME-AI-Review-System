# pyright: basic
from __future__ import annotations

import json
from pathlib import Path

import pytest
from ame_ai_review_system import paths


@pytest.fixture(autouse=True)
def _clean_path_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "AME_REVIEW_PROJECT_ROOT",
        "AME_REVIEW_CONFIG",
        "AME_REVIEW_USER_CONFIG",
    ):
        monkeypatch.delenv(key, raising=False)


def test_project_root_ame_review_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "proj"
    (root / ".ame-review").mkdir(parents=True)
    sub = root / "src" / "deep"
    sub.mkdir(parents=True)
    monkeypatch.chdir(sub)
    assert paths.project_root() == root.resolve()


def test_project_root_git_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".git").mkdir()
    monkeypatch.chdir(root)
    assert paths.project_root() == root.resolve()


def test_project_root_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "pinned"
    root.mkdir()
    monkeypatch.setenv("AME_REVIEW_PROJECT_ROOT", str(root))
    monkeypatch.chdir(tmp_path)
    assert paths.project_root() == root.resolve()


def test_config_path_prefers_project_local(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "proj"
    (root / ".ame-review").mkdir(parents=True)
    proj_config = root / ".ame-review" / "config.json"
    proj_config.write_text(json.dumps({"engine": "opencode"}), encoding="utf-8")
    monkeypatch.setenv("AME_REVIEW_PROJECT_ROOT", str(root))
    assert paths.config_path() == proj_config
    assert paths.config_path().read_text(encoding="utf-8") == json.dumps({
        "engine": "opencode"
    })


def test_config_path_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    custom = tmp_path / "custom.json"
    custom.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("AME_REVIEW_CONFIG", str(custom))
    assert paths.config_path() == custom


def test_config_path_falls_back_to_package_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # .ame-review も .git も無い空ディレクトリ → パッケージ同梱デフォルト。
    monkeypatch.chdir(tmp_path)
    resolved = paths.config_path()
    assert resolved.read_text(encoding="utf-8").strip().startswith("{")


def test_user_config_path_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    custom = tmp_path / "user.json"
    custom.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("AME_REVIEW_USER_CONFIG", str(custom))
    assert paths.user_config_path() == custom


def test_prompt_path_prefers_project_local(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "proj"
    ame = root / ".ame-review"
    ame.mkdir(parents=True)
    (ame / "review_prompt.txt").write_text("CUSTOM PROMPT", encoding="utf-8")
    monkeypatch.setenv("AME_REVIEW_PROJECT_ROOT", str(root))
    assert paths.prompt_path().read_text(encoding="utf-8") == "CUSTOM PROMPT"


def test_semgrep_rules_path_prefers_project_local(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "proj"
    ame = root / ".ame-review"
    (ame / ".semgrep").mkdir(parents=True)
    (ame / ".semgrep" / "rules.yml").write_text("rules: []", encoding="utf-8")
    monkeypatch.setenv("AME_REVIEW_PROJECT_ROOT", str(root))
    assert paths.semgrep_rules_path().read_text(encoding="utf-8") == "rules: []"


def test_tracked_config_path_ignores_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # tracked_config_path はセキュリティ上 env 上書きを無視する (Issue #26)。
    root = tmp_path / "proj"
    ame = root / ".ame-review"
    ame.mkdir(parents=True)
    (ame / "config.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("AME_REVIEW_PROJECT_ROOT", str(root))
    monkeypatch.setenv("AME_REVIEW_CONFIG", str(tmp_path / "evil.json"))
    assert paths.tracked_config_path() == (ame / "config.json").resolve()


def test_state_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "proj"
    (root / ".ame-review").mkdir(parents=True)
    monkeypatch.setenv("AME_REVIEW_PROJECT_ROOT", str(root))
    assert paths.state_dir() == (root / ".ame-review" / "state").resolve()
