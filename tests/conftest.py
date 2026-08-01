# pyright: basic
from __future__ import annotations

import subprocess
from types import SimpleNamespace
from typing import Any

import pytest


@pytest.fixture
def capture_engine_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """subprocess.run を差し替え、子プロセスへ渡される env を捕捉する (Issue #40)."""
    captured: dict[str, Any] = {}

    def fake_run(_cmd: list[str], **kwargs: Any) -> SimpleNamespace:
        captured["env"] = kwargs.get("env")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    return captured
