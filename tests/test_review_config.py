from __future__ import annotations

import io
import os
import tempfile
from collections.abc import Callable
from contextlib import redirect_stdout
from pathlib import Path

import pytest
from ame_ai_review_system import paths, review_config
from ame_ai_review_system.review_config import (
    apply_repair_model,
    filter_review_diff,
    filter_review_targets,
    is_review_command,
    load_config,
    package_dir_rel,
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


# ============================================================================
# Issue #37: vendored ame_ai_review_system 配下のレビュー除外
# ============================================================================


def _exclude_package(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
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


def test_package_dir_rel_returns_top_level_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _exclude_package(monkeypatch, tmp_path)
    assert package_dir_rel() == "ame_ai_review_system"


def test_package_dir_rel_returns_nested_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    pkg = root / "vendor" / "ame_ai_review_system"
    pkg.mkdir(parents=True)
    monkeypatch.setattr(paths, "package_dir", lambda: pkg)
    monkeypatch.setattr(paths, "project_root", lambda: root)
    monkeypatch.setattr(
        review_config,
        "load_config",
        lambda: {"review_include_package_dir": False},
    )
    assert package_dir_rel() == "vendor/ame_ai_review_system"
    files = [
        "vendor/ame_ai_review_system/main.py",
        "vendor/other.py",
        "src/app.py",
    ]
    assert filter_review_targets(files) == ["vendor/other.py", "src/app.py"]


def test_package_dir_rel_none_when_not_vendored(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir(parents=True)
    pkg = tmp_path / "site-packages" / "ame_ai_review_system"
    pkg.mkdir(parents=True)
    monkeypatch.setattr(paths, "package_dir", lambda: pkg)
    monkeypatch.setattr(paths, "project_root", lambda: root)
    assert package_dir_rel() is None


def test_apply_repair_model_overrides_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        review_config,
        "load_config",
        lambda: {"review_repair_model": "opencode-go/gpt-5.6-luna"},
    )
    settings = {"model": "opencode-go/deepseek-v4-flash"}
    assert apply_repair_model(settings) == {
        "model": "opencode-go/gpt-5.6-luna",
    }


def test_apply_repair_model_passthrough_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        review_config,
        "load_config",
        lambda: {"review_repair_model": None},
    )
    settings = {"model": "opencode-go/deepseek-v4-flash"}
    assert apply_repair_model(settings) == settings


def test_filter_review_targets_keeps_all_when_include_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        review_config,
        "load_config",
        lambda: {"review_include_package_dir": True},
    )
    files = ["ame_ai_review_system/main.py", "src/app.py"]
    assert filter_review_targets(files) == files


def test_filter_review_targets_excludes_package_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _exclude_package(monkeypatch, tmp_path)
    files = [
        "ame_ai_review_system/main.py",
        "ame_ai_review_system/sub/foo.py",
        "src/app.py",
        "tests/test_main.py",
    ]
    assert filter_review_targets(files) == ["src/app.py", "tests/test_main.py"]


_DIFF = (
    "diff --git a/ame_ai_review_system/main.py b/ame_ai_review_system/main.py\n"
    "index 1234567..abcdefg 100644\n"
    "--- a/ame_ai_review_system/main.py\n"
    "+++ b/ame_ai_review_system/main.py\n"
    "@@ -1,1 +1,1 @@\n"
    "-x\n"
    "+y\n"
    "diff --git a/src/app.py b/src/app.py\n"
    "index 1234567..abcdefg 100644\n"
    "--- a/src/app.py\n"
    "+++ b/src/app.py\n"
    "@@ -1,1 +1,1 @@\n"
    "-x\n"
    "+y\n"
)


def test_filter_review_diff_keeps_all_when_include_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        review_config,
        "load_config",
        lambda: {"review_include_package_dir": True},
    )
    assert filter_review_diff(_DIFF) == _DIFF


def test_filter_review_diff_excludes_package_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _exclude_package(monkeypatch, tmp_path)
    result = filter_review_diff(_DIFF)
    assert "ame_ai_review_system/main.py" not in result
    assert "src/app.py" in result
    assert "-x" in result
    assert "+y" in result


def test_filter_review_diff_excludes_rename_under_package_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _exclude_package(monkeypatch, tmp_path)
    rename_diff = (
        "diff --git a/ame_ai_review_system/old.py b/ame_ai_review_system/new.py\n"
        "similarity index 90%\n"
        "rename from ame_ai_review_system/old.py\n"
        "rename to ame_ai_review_system/new.py\n"
        "--- a/ame_ai_review_system/old.py\n"
        "+++ b/ame_ai_review_system/new.py\n"
        "@@ -1,1 +1,1 @@\n"
        "-x\n"
        "+y\n"
    )
    assert not filter_review_diff(rename_diff)


def test_filter_review_diff_excludes_binary_diff_under_package_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _exclude_package(monkeypatch, tmp_path)
    binary_diff = (
        "diff --git a/ame_ai_review_system/data.bin b/ame_ai_review_system/data.bin\n"
        "index 1234567..abcdefg 100644\n"
        "Binary files a/ame_ai_review_system/data.bin and b/ame_ai_review_system/data.bin differ\n"
    )
    assert not filter_review_diff(binary_diff)


def test_filter_review_diff_excludes_mode_change_under_package_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _exclude_package(monkeypatch, tmp_path)
    mode_diff = (
        "diff --git a/ame_ai_review_system/run.sh b/ame_ai_review_system/run.sh\n"
        "old mode 100644\n"
        "new mode 100755\n"
    )
    assert not filter_review_diff(mode_diff)


def test_filter_review_diff_excludes_quoted_binary_path_under_package_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _exclude_package(monkeypatch, tmp_path)
    quoted_diff = (
        'diff --git "a/ame_ai_review_system/my file.bin" '
        '"b/ame_ai_review_system/my file.bin"\n'
        "index 1234567..abcdefg 100644\n"
        'Binary files "a/ame_ai_review_system/my file.bin" and '
        '"b/ame_ai_review_system/my file.bin" differ\n'
    )
    assert not filter_review_diff(quoted_diff)


def test_filter_review_diff_keeps_quoted_path_outside_package_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _exclude_package(monkeypatch, tmp_path)
    quoted_diff = (
        'diff --git "a/src/my file.txt" "b/src/my file.txt"\n'
        "index 1234567..abcdefg 100644\n"
        'Binary files "a/src/my file.txt" and "b/src/my file.txt" differ\n'
    )
    result = filter_review_diff(quoted_diff)
    assert 'diff --git "a/src/my file.txt"' in result
    assert "Binary files" in result


def test_filter_review_diff_keeps_cross_boundary_rename(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _exclude_package(monkeypatch, tmp_path)
    rename_diff = (
        "diff --git a/src/old.py b/ame_ai_review_system/new.py\n"
        "similarity index 80%\n"
        "rename from src/old.py\n"
        "rename to ame_ai_review_system/new.py\n"
        "--- a/src/old.py\n"
        "+++ b/ame_ai_review_system/new.py\n"
        "@@ -1,1 +1,1 @@\n"
        "-x\n"
        "+y\n"
    )
    result = filter_review_diff(rename_diff)
    assert "src/old.py" in result


def test_filter_review_diff_excludes_add_under_package_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _exclude_package(monkeypatch, tmp_path)
    add_diff = (
        "diff --git a/ame_ai_review_system/new.py b/ame_ai_review_system/new.py\n"
        "new file mode 100644\n"
        "index 0000000..1234567\n"
        "--- /dev/null\n"
        "+++ b/ame_ai_review_system/new.py\n"
        "@@ -0,0 +1 @@\n"
        "+print('hi')\n"
    )
    assert not filter_review_diff(add_diff)


def test_filter_review_diff_excludes_delete_under_package_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _exclude_package(monkeypatch, tmp_path)
    delete_diff = (
        "diff --git a/ame_ai_review_system/old.py b/ame_ai_review_system/old.py\n"
        "deleted file mode 100644\n"
        "index 1234567..0000000\n"
        "--- a/ame_ai_review_system/old.py\n"
        "+++ /dev/null\n"
        "@@ -1 +0,0 @@\n"
        "-x\n"
    )
    assert not filter_review_diff(delete_diff)


def test_filter_review_diff_empty_input() -> None:
    assert not filter_review_diff("")


def test_filter_review_diff_after_compact_diff(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from ame_ai_review_system.diff_utils import compact_diff

    _exclude_package(monkeypatch, tmp_path)
    diff = (
        "diff --git a/ame_ai_review_system/main.py b/ame_ai_review_system/main.py\n"
        "index 1234567..abcdefg 100644\n"
        "--- a/ame_ai_review_system/main.py\n"
        "+++ b/ame_ai_review_system/main.py\n"
        "@@ -1,1 +1,1 @@\n"
        "-x\n"
        "+y\n"
        "diff --git a/src/app.py b/src/app.py\n"
        "index 1234567..abcdefg 100644\n"
        "--- a/src/app.py\n"
        "+++ b/src/app.py\n"
        "@@ -1,1 +1,1 @@\n"
        "-x\n"
        "+y\n"
    )
    result = filter_review_diff(compact_diff(diff))
    assert "ame_ai_review_system/main.py" not in result
    assert "src/app.py" in result


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
