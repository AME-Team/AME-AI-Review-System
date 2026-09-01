# pyright: basic
from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


@pytest.fixture(autouse=True)
def _isolate_machine_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """開発マシンの設定ファイルをテストへ漏れ出させない (Issue #126).

    resolve_engine_settings が review_config.user_overrides() /
    load_global_config() を直接読むため、実ユーザーのグローバル設定
    (``~/.config/ame-ai-review-system/config.json``) やリポジトリの
    ``.ame-review/config.json`` / ``config.user.json`` に依存してテストが環境依存に
    ならないよう、3 つの設定パスを存在しない一時パスへ差し替える。環境変数名は
    review_config の ``_config_path`` / ``_user_config_path`` / paths の
    ``global_config_path`` が参照するものと一致している (Issue #126)。
    """
    monkeypatch.setenv(
        "AME_REVIEW_GLOBAL_CONFIG",
        str(tmp_path / "nonexistent_global_config.json"),
    )
    monkeypatch.setenv(
        "AME_REVIEW_CONFIG",
        str(tmp_path / "nonexistent_repo_config.json"),
    )
    monkeypatch.setenv(
        "AME_REVIEW_USER_CONFIG",
        str(tmp_path / "nonexistent_user_config.json"),
    )


@pytest.fixture(autouse=True)
def _clear_reviewer_logins_cache() -> Any:
    """reviewer_logins のキャッシュをテスト間でクリアする (Issue #92)."""
    from ame_ai_review_system import github_client

    github_client.clear_reviewer_logins_cache()
    return None


@pytest.fixture
def capture_engine_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """subprocess.run を差し替え、子プロセスへ渡される env を捕捉する (Issue #40)."""
    captured: dict[str, Any] = {}

    def fake_run(_cmd: list[str], **kwargs: Any) -> SimpleNamespace:
        captured["env"] = kwargs.get("env")
        captured["timeout"] = kwargs.get("timeout")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    return captured
