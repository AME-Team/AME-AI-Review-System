# pyright: basic
from __future__ import annotations

import os
import pathlib
import stat
from types import SimpleNamespace
from typing import Any

import pytest
from ame_ai_review_system import skip_guard

# ---------------------------
# parse_skip_ids
# ---------------------------


def test_parse_skip_ids_comma_separated() -> None:
    assert skip_guard.parse_skip_ids("ai-precommit-review,ruff") == {
        "ai-precommit-review",
        "ruff",
    }


def test_parse_skip_ids_whitespace_separated() -> None:
    assert skip_guard.parse_skip_ids("ai-precommit-review ruff") == {
        "ai-precommit-review",
        "ruff",
    }


def test_parse_skip_ids_mixed_separators() -> None:
    assert skip_guard.parse_skip_ids(
        " ai-precommit-review , mypy  end-of-file-fixer"
    ) == {
        "ai-precommit-review",
        "mypy",
        "end-of-file-fixer",
    }


def test_parse_skip_ids_empty() -> None:
    assert skip_guard.parse_skip_ids("") == set()
    assert skip_guard.parse_skip_ids(" , , ") == set()


def test_parse_skip_ids_strips_whitespace() -> None:
    assert skip_guard.parse_skip_ids("  ai-precommit-review  ") == {
        "ai-precommit-review"
    }


# ---------------------------
# main — guard disabled / no-skip cases (always pass)
# ---------------------------


def test_enforce_enabled_ignores_env_and_user_overrides(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    # tracked な config.json のみを読み、AME_REVIEW_CONFIG / config.user.json 等の
    # 非 root で書き換え可能な上書きを無視すること (Issue #26 HIGH 対策)。
    tracked = tmp_path / "config.json"
    tracked.write_text('{"ai_review_enforce_no_skip": true}', encoding="utf-8")
    evil = tmp_path / "evil.json"
    evil.write_text('{"ai_review_enforce_no_skip": false}', encoding="utf-8")
    user = tmp_path / "config.user.json"
    user.write_text('{"ai_review_enforce_no_skip": false}', encoding="utf-8")
    monkeypatch.setattr(skip_guard, "_tracked_config_path", lambda: tracked)
    monkeypatch.setenv("AME_REVIEW_CONFIG", str(evil))
    monkeypatch.setenv("AME_REVIEW_USER_CONFIG", str(user))
    assert skip_guard._enforce_enabled() is True


def test_enforce_enabled_disabled_via_tracked_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    tracked = tmp_path / "config.json"
    tracked.write_text('{"ai_review_enforce_no_skip": false}', encoding="utf-8")
    monkeypatch.setattr(skip_guard, "_tracked_config_path", lambda: tracked)
    assert skip_guard._enforce_enabled() is False


def test_enforce_enabled_defaults_to_true_when_unreadable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        skip_guard,
        "_tracked_config_path",
        lambda: pathlib.Path("/nonexistent/skip-guard-config.json"),
    )
    assert skip_guard._enforce_enabled() is True


def test_main_no_skip_env_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SKIP", raising=False)
    assert skip_guard.main() == 0


def test_main_skip_other_hook_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKIP", "ruff,mypy")
    assert skip_guard.main() == 0


def test_main_guard_disabled_by_tracked_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKIP", "ai-precommit-review")
    monkeypatch.setattr(skip_guard, "_enforce_enabled", lambda: False)
    assert skip_guard.main() == 0


# ---------------------------
# main — unauthorized skip is blocked
# ---------------------------


def test_main_unauthorized_skip_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKIP", "ai-precommit-review")
    # 非特権実行をシミュレート (geteuid != 0)
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    token = pathlib.Path("/nonexistent/skip-guard-token-test")
    monkeypatch.setattr(skip_guard, "bypass_token_path", lambda: token)
    assert skip_guard.main() == 1


def test_main_blocks_when_guard_id_also_in_skip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # ai-precommit-review が含まれていれば、ai-skip-guard も併記されていても (本フックが
    # 実行された上で) ai-precommit-review のスキップを検知してブロックする。
    monkeypatch.setenv("SKIP", "ai-precommit-review,ai-skip-guard")
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    token = pathlib.Path("/nonexistent/skip-guard-token-test")
    monkeypatch.setattr(skip_guard, "bypass_token_path", lambda: token)
    assert skip_guard.main() == 1


# ---------------------------
# main — authorized skip is allowed
# ---------------------------


def test_main_root_authorized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKIP", "ai-precommit-review")
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    token = pathlib.Path("/nonexistent/skip-guard-token-test")
    monkeypatch.setattr(skip_guard, "bypass_token_path", lambda: token)
    assert skip_guard.main() == 0


def test_main_token_authorized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKIP", "ai-precommit-review")
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    monkeypatch.setattr(skip_guard, "_token_present", lambda: True)
    assert skip_guard.main() == 0


def test_main_token_non_root_owned_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    # トークンファイルが存在しても非 root 所有ならバイパス不可 (AI Agent が無痕跡で
    # 作成したファイルでは迂回できない)。
    monkeypatch.setenv("SKIP", "ai-precommit-review")
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    monkeypatch.setattr(skip_guard, "_token_present", lambda: False)
    assert skip_guard.main() == 1


# ---------------------------
# bypass_token_path
# ---------------------------


def test_bypass_token_path_fixed_under_home(monkeypatch: pytest.MonkeyPatch) -> None:
    # パスは HOME 配下の固定位置。環境変数での上書きは認めない (セキュリティ)。
    monkeypatch.setenv("AME_AI_REVIEW_BYPASS_TOKEN", "/etc/passwd")
    monkeypatch.setenv("HOME", "/u")
    assert skip_guard.bypass_token_path() == (
        pathlib.Path("/u") / ".config" / "ame-ai-review-system" / "allow-skip-ai-review"
    )


# ---------------------------
# is_authorized
# ---------------------------


def _fake_stat(uid: int, *, is_reg: bool = True) -> SimpleNamespace:
    st_mode = stat.S_IFREG if is_reg else stat.S_IFLNK
    return SimpleNamespace(st_uid=uid, st_mode=st_mode)


def _mock_stat(uid: int, *, is_reg: bool = True) -> Any:
    # Path.lstat() は os.lstat(path, *, follow_symlinks=False) を呼ぶため可変長引数を受ける。
    return lambda *_args, **_kwargs: _fake_stat(uid, is_reg=is_reg)


def test_is_authorized_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    token = pathlib.Path("/nonexistent/skip-guard-token-test")
    monkeypatch.setattr(skip_guard, "bypass_token_path", lambda: token)
    authorized, reason = skip_guard.is_authorized()
    assert authorized is True
    assert "sudo" in reason


def test_is_authorized_token_root_owned(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    token = tmp_path / "allow-skip-ai-review"
    token.write_text("ok\n", encoding="utf-8")
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    monkeypatch.setattr(skip_guard, "bypass_token_path", lambda: token)
    monkeypatch.setattr(os, "lstat", _mock_stat(0))
    authorized, reason = skip_guard.is_authorized()
    assert authorized is True
    assert "バイパストークン" in reason


def test_is_authorized_token_non_root_owned_blocks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    token = tmp_path / "allow-skip-ai-review"
    token.write_text("ok\n", encoding="utf-8")
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    monkeypatch.setattr(skip_guard, "bypass_token_path", lambda: token)
    monkeypatch.setattr(os, "lstat", _mock_stat(1000))
    authorized, reason = skip_guard.is_authorized()
    assert authorized is False
    assert not reason


def test_is_authorized_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    token = pathlib.Path("/nonexistent/skip-guard-token-test")
    monkeypatch.setattr(skip_guard, "bypass_token_path", lambda: token)
    authorized, reason = skip_guard.is_authorized()
    assert authorized is False
    assert not reason


# ---------------------------
# _token_present (root ownership check)
# ---------------------------


def test_token_present_root_owned(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    token = tmp_path / "allow-skip-ai-review"
    token.write_text("ok\n", encoding="utf-8")
    monkeypatch.setattr(skip_guard, "bypass_token_path", lambda: token)
    monkeypatch.setattr(os, "lstat", _mock_stat(0))
    assert skip_guard._token_present() is True


def test_token_present_non_root_owned_blocks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    token = tmp_path / "allow-skip-ai-review"
    token.write_text("ok\n", encoding="utf-8")
    monkeypatch.setattr(skip_guard, "bypass_token_path", lambda: token)
    monkeypatch.setattr(os, "lstat", _mock_stat(1000))
    assert skip_guard._token_present() is False


def test_token_present_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        skip_guard,
        "bypass_token_path",
        lambda: pathlib.Path("/nonexistent/skip-guard-token-test"),
    )
    assert skip_guard._token_present() is False


def test_token_present_symlink_blocks_even_if_root_owned(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    # ln -s /etc/passwd <token> のようなシンボリックリンクでリンク先の uid=0 を盗用する
    # 攻撃を防ぐこと。リンク自体が root 所有でも通常ファイルでなければ拒否する。
    token = tmp_path / "allow-skip-ai-review"
    token.write_text("ok\n", encoding="utf-8")
    monkeypatch.setattr(skip_guard, "bypass_token_path", lambda: token)
    monkeypatch.setattr(os, "lstat", _mock_stat(0, is_reg=False))
    assert skip_guard._token_present() is False
