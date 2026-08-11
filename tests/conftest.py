# pyright: basic
from __future__ import annotations

import subprocess
from types import SimpleNamespace
from typing import Any

import pytest


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
