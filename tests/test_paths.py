# pyright: basic
from __future__ import annotations

import json
import shutil
import subprocess
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


class _FakeShutil:
    """paths モジュール内の ``shutil`` を差し替えるための stub."""

    def __init__(self, which_result: str | None) -> None:
        self._which_result = which_result

    def which(self, _cmd: str) -> str | None:
        return self._which_result

    @staticmethod
    def copytree(src: Path, dst: Path) -> None:
        shutil.copytree(src, dst)

    @staticmethod
    def rmtree(dst: Path) -> None:
        shutil.rmtree(dst)


class _FakeSubprocess:
    """paths モジュール内の ``subprocess.run`` を記録用に差し替えるための stub."""

    def __init__(self, calls: list[list[str]]) -> None:
        self._calls = calls

    def run(
        self,
        args: list[str],
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        self._calls.append(list(args))
        return subprocess.CompletedProcess(args=args, returncode=0)


def _stub_engines_ts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> list[list[str]]:
    """package_dir / ame_review_dir を差し替え、npm install を記録する stub を仕込む."""
    pkg = tmp_path / "pkg"
    (pkg / "engines" / "ts").mkdir(parents=True)
    (pkg / "engines" / "ts" / "package.json").write_text("{}", encoding="utf-8")
    (pkg / "engines" / "ts" / "claude.mjs").write_text("module", encoding="utf-8")
    (pkg / "engines" / "ts" / "opencode.mjs").write_text("module", encoding="utf-8")
    monkeypatch.setattr(paths, "package_dir", lambda: pkg)
    monkeypatch.setattr(paths, "ame_review_dir", lambda: tmp_path / ".ame-review")
    monkeypatch.setattr(paths, "shutil", _FakeShutil("/usr/bin/npm"))
    calls: list[list[str]] = []
    monkeypatch.setattr(paths, "subprocess", _FakeSubprocess(calls))
    return calls


def test_ensure_engines_ts_copies_and_installs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _stub_engines_ts(tmp_path, monkeypatch)
    dst = paths.ensure_engines_ts()
    assert (dst / "package.json").exists()
    assert calls == [["npm", "install"]]


def test_ensure_engines_ts_skips_install_when_node_modules_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _stub_engines_ts(tmp_path, monkeypatch)
    dst = paths.ensure_engines_ts()
    (dst / "node_modules").mkdir()
    paths.ensure_engines_ts()
    assert calls == [["npm", "install"]]


def test_ensure_engines_ts_raises_without_npm(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pkg = tmp_path / "pkg"
    (pkg / "engines" / "ts").mkdir(parents=True)
    (pkg / "engines" / "ts" / "package.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(paths, "package_dir", lambda: pkg)
    monkeypatch.setattr(paths, "ame_review_dir", lambda: tmp_path / ".ame-review")
    monkeypatch.setattr(paths, "shutil", _FakeShutil(None))
    with pytest.raises(SystemExit):
        paths.ensure_engines_ts()


def test_ensure_engines_ts_redeploys_when_source_changed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _stub_engines_ts(tmp_path, monkeypatch)
    dst = paths.ensure_engines_ts()
    (dst / "node_modules").mkdir()
    # ソースが更新されると再展開され、node_modules が失われるため npm install も再実行。
    pkg = tmp_path / "pkg"
    (pkg / "engines" / "ts" / "opencode.mjs").write_text("UPDATED", encoding="utf-8")
    paths.ensure_engines_ts()
    assert (dst / "opencode.mjs").read_text(encoding="utf-8") == "UPDATED"
    assert calls == [["npm", "install"], ["npm", "install"]]


def test_ensure_engines_ts_redeploys_when_new_file_added(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _stub_engines_ts(tmp_path, monkeypatch)
    dst = paths.ensure_engines_ts()
    (dst / "node_modules").mkdir()
    # ソースに新規ファイルが追加されても再帰比較で差分検知して再展開する。
    pkg = tmp_path / "pkg"
    (pkg / "engines" / "ts" / "new-file.mjs").write_text("NEW", encoding="utf-8")
    paths.ensure_engines_ts()
    assert (dst / "new-file.mjs").read_text(encoding="utf-8") == "NEW"
    assert calls == [["npm", "install"], ["npm", "install"]]


def test_ensure_engines_ts_reuses_existing_dest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _stub_engines_ts(tmp_path, monkeypatch)
    # 初回展開後に node_modules を置くと、再実行で npm install が走らない。
    dst = paths.ensure_engines_ts()
    (dst / "node_modules").mkdir()
    assert paths.ensure_engines_ts() == dst
    assert calls == [["npm", "install"]]
