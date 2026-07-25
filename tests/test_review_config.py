from __future__ import annotations

import io
import os
import tempfile
from collections.abc import Callable
from contextlib import redirect_stdout
from pathlib import Path

import pytest
from ame_ai_review_system import review_config
from ame_ai_review_system.review_config import (
    is_review_command,
    load_config,
    user_overrides,
)


def test_is_review_command_exact() -> None:
    assert is_review_command("/request-review")
    assert is_review_command("/review")


def test_is_review_command_with_args() -> None:
    assert is_review_command("/request-review @ame-ai-reviewer")
    assert is_review_command("/review please")


def test_is_review_command_multiline() -> None:
    assert is_review_command("  /request-review\n\nレビューお願いします")


def test_is_review_command_negative() -> None:
    assert not is_review_command("/requestreview")
    assert not is_review_command("request-review")
    assert not is_review_command("")
    assert not is_review_command("   ")
    assert not is_review_command("通常の返信コメントです")


def test_load_config_default_disabled() -> None:
    os.environ.pop("AME_REVIEW_CONFIG", None)
    cfg = load_config()
    assert "push_review_enabled" not in cfg
    assert cfg["engine"] == "claude"
    assert cfg["model"] == "sonnet"
    assert cfg["thinking"] == "high"
    assert cfg["review_budget_usd"] == pytest.approx(2.0)
    assert cfg["reply_budget_usd"] == pytest.approx(0.2)


def test_load_config_reads_file() -> None:
    old = os.environ.get("AME_REVIEW_CONFIG")
    old_user = os.environ.get("AME_REVIEW_USER_CONFIG")
    fd, name = tempfile.mkstemp(suffix=".json")
    nonexistent = Path(tempfile.gettempdir()) / "nonexistent_user_config.json"
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write('{"precommit_engine": "claude"}')
        os.environ["AME_REVIEW_CONFIG"] = name
        os.environ["AME_REVIEW_USER_CONFIG"] = str(nonexistent)
        cfg = load_config()
    finally:
        _restore_env("AME_REVIEW_CONFIG", old)
        _restore_env("AME_REVIEW_USER_CONFIG", old_user)
        Path(name).unlink(missing_ok=True)
    assert cfg["precommit_engine"] == "claude"


def test_cli_get_prints_default() -> None:
    nonexistent = Path(tempfile.gettempdir()) / "nonexistent_cli_config.json"
    old = os.environ.get("AME_REVIEW_CONFIG")
    try:
        os.environ["AME_REVIEW_CONFIG"] = str(nonexistent)
        output = _capture(
            lambda: review_config.main(
                ["review_config.py", "get", "engine"],
            ),
        )
    finally:
        _restore_env("AME_REVIEW_CONFIG", old)
    assert output.strip() == "claude"


def test_cli_is_review_command() -> None:
    output = _capture(
        lambda: review_config.main(
            ["review_config.py", "is-review-command", "/request-review"],
        ),
    )
    assert output.strip() == "true"


def test_user_config_overrides_default_config() -> None:
    old_conf = os.environ.get("AME_REVIEW_CONFIG")
    old_user = os.environ.get("AME_REVIEW_USER_CONFIG")
    fd_conf, name_conf = tempfile.mkstemp(suffix=".json")
    fd_user, name_user = tempfile.mkstemp(suffix=".json")
    try:
        with os.fdopen(fd_conf, "w", encoding="utf-8") as fh:
            fh.write('{"engine": "opencode", "thinking": "medium"}')
        with os.fdopen(fd_user, "w", encoding="utf-8") as fh:
            fh.write('{"thinking": "high", "review_budget_usd": 3.0}')
        os.environ["AME_REVIEW_CONFIG"] = name_conf
        os.environ["AME_REVIEW_USER_CONFIG"] = name_user
        cfg = load_config()
    finally:
        _restore_env("AME_REVIEW_CONFIG", old_conf)
        _restore_env("AME_REVIEW_USER_CONFIG", old_user)
        Path(name_conf).unlink(missing_ok=True)
        Path(name_user).unlink(missing_ok=True)
    assert cfg["engine"] == "opencode"
    assert cfg["thinking"] == "high"
    assert cfg["review_budget_usd"] == pytest.approx(3.0)


def test_user_overrides_includes_user_config() -> None:
    old_conf = os.environ.get("AME_REVIEW_CONFIG")
    old_user = os.environ.get("AME_REVIEW_USER_CONFIG")
    fd_conf, name_conf = tempfile.mkstemp(suffix=".json")
    fd_user, name_user = tempfile.mkstemp(suffix=".json")
    try:
        with os.fdopen(fd_conf, "w", encoding="utf-8") as fh:
            fh.write('{"engine": "opencode"}')
        with os.fdopen(fd_user, "w", encoding="utf-8") as fh:
            fh.write('{"thinking": "low"}')
        os.environ["AME_REVIEW_CONFIG"] = name_conf
        os.environ["AME_REVIEW_USER_CONFIG"] = name_user
        overrides = user_overrides()
    finally:
        _restore_env("AME_REVIEW_CONFIG", old_conf)
        _restore_env("AME_REVIEW_USER_CONFIG", old_user)
        Path(name_conf).unlink(missing_ok=True)
        Path(name_user).unlink(missing_ok=True)
    assert overrides["engine"] == "opencode"
    assert overrides["thinking"] == "low"


def test_missing_user_config_does_not_break() -> None:
    old = os.environ.get("AME_REVIEW_CONFIG")
    old_user = os.environ.get("AME_REVIEW_USER_CONFIG")
    fd, name = tempfile.mkstemp(suffix=".json")
    nonexistent = Path(tempfile.gettempdir()) / "nonexistent_user_config.json"
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write('{"engine": "claude"}')
        os.environ["AME_REVIEW_CONFIG"] = name
        os.environ.pop("AME_REVIEW_USER_CONFIG", None)
        # Point to a non-existent user config
        os.environ["AME_REVIEW_USER_CONFIG"] = str(nonexistent)
        cfg = load_config()
    finally:
        _restore_env("AME_REVIEW_CONFIG", old)
        _restore_env("AME_REVIEW_USER_CONFIG", old_user)
        Path(name).unlink(missing_ok=True)
    assert cfg["engine"] == "claude"


def _restore_env(key: str, old: str | None) -> None:
    if old is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = old


def _capture(fn: Callable[[], int]) -> str:
    buf = io.StringIO()
    with redirect_stdout(buf):
        fn()
    return buf.getvalue()
