# pyright: basic
from __future__ import annotations

from typing import TYPE_CHECKING

from ame_ai_review_system import precommit_engine

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


# ---------------------------
# detect_active_engine (process tree inspection)
# ---------------------------


def test_detect_returns_none_when_no_ai_ancestor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        precommit_engine,
        "_process_info",
        lambda _pid: (1, "bash"),
    )
    assert precommit_engine.detect_active_engine(start_pid=100) is None


def test_detect_finds_opencode_in_tree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 親方向: self(bash) -> opencode -> init(1)
    chain = {
        100: (200, "bash"),
        200: (300, "opencode"),
        300: (1, "init"),
    }

    def fake_info(pid: int) -> tuple[int, str] | None:
        return chain.get(pid)

    monkeypatch.setattr(precommit_engine, "_process_info", fake_info)
    assert precommit_engine.detect_active_engine(start_pid=100) == "opencode"


def test_detect_finds_claude_in_tree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chain = {
        100: (200, "bash"),
        200: (300, "zsh"),
        300: (400, "claude"),
        400: (1, "init"),
    }

    def fake_info(pid: int) -> tuple[int, str] | None:
        return chain.get(pid)

    monkeypatch.setattr(precommit_engine, "_process_info", fake_info)
    assert precommit_engine.detect_active_engine(start_pid=100) == "claude"


def test_detect_finds_agy_in_tree(monkeypatch: pytest.MonkeyPatch) -> None:
    chain = {
        100: (200, "agy"),
        200: (1, "init"),
    }

    def fake_info(pid: int) -> tuple[int, str] | None:
        return chain.get(pid)

    monkeypatch.setattr(precommit_engine, "_process_info", fake_info)
    assert precommit_engine.detect_active_engine(start_pid=100) == "antigravity"


def test_detect_immediate_self_match(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        precommit_engine,
        "_process_info",
        lambda pid: (1, "opencode") if pid == 100 else None,
    )
    assert precommit_engine.detect_active_engine(start_pid=100) == "opencode"


def test_detect_stops_at_pid_1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        precommit_engine,
        "_process_info",
        lambda pid: (1, "systemd") if pid == 100 else None,
    )
    assert precommit_engine.detect_active_engine(start_pid=100) is None


def test_detect_breaks_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    # PPID ループ (悪意のある/壊れた ps 出力) でも停止すること。
    monkeypatch.setattr(
        precommit_engine,
        "_process_info",
        lambda _pid: (100, "bash"),  # 親が自分自身を指す
    )
    assert precommit_engine.detect_active_engine(start_pid=100) is None


def test_detect_returns_none_when_ps_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(precommit_engine, "_process_info", lambda _pid: None)
    assert precommit_engine.detect_active_engine(start_pid=100) is None


def test_detect_defaults_to_current_pid(monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    real_pid = os.getpid()
    monkeypatch.setattr(
        precommit_engine,
        "_process_info",
        lambda pid: (1, "opencode") if pid == real_pid else None,
    )
    assert precommit_engine.detect_active_engine() == "opencode"


# ---------------------------
# resolve_engine_settings (precedence)
# ---------------------------


def test_resolve_auto_detects_opencode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        precommit_engine,
        "detect_active_engine",
        lambda **_kw: "opencode",
    )
    settings = precommit_engine.resolve_engine_settings(
        config={"precommit_engine": "auto", "engine": "claude", "model": "sonnet"},
        env={},
    )
    assert settings["engine"] == "opencode"
    # opencode は model=None を許す (ユーザ設定の既定モデルを使う)
    assert settings["model"] is None


def test_resolve_auto_falls_back_to_pr_engine_when_detection_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(precommit_engine, "detect_active_engine", lambda **_kw: None)
    settings = precommit_engine.resolve_engine_settings(
        config={"precommit_engine": "auto", "engine": "claude", "model": "sonnet"},
        env={},
    )
    assert settings["engine"] == "claude"


def test_resolve_explicit_precommit_engine_overrides_auto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # detect が opencode を返しても precommit_engine="claude" ならそれが勝つ
    monkeypatch.setattr(
        precommit_engine,
        "detect_active_engine",
        lambda **_kw: "opencode",
    )
    settings = precommit_engine.resolve_engine_settings(
        config={"precommit_engine": "claude", "model": "sonnet"},
        env={},
    )
    assert settings["engine"] == "claude"


def test_resolve_env_var_overrides_config() -> None:
    settings = precommit_engine.resolve_engine_settings(
        config={"precommit_engine": "claude"},
        env={"PRECOMMIT_REVIEW_ENGINE": "opencode"},
    )
    assert settings["engine"] == "opencode"


def test_resolve_env_model_overrides_config() -> None:
    settings = precommit_engine.resolve_engine_settings(
        config={"precommit_engine": "opencode", "precommit_model": "foo"},
        env={"PRECOMMIT_REVIEW_MODEL": "glm-5.2"},
    )
    assert settings["model"] == "glm-5.2"


def test_resolve_falls_back_to_pr_engine_when_no_precommit_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(precommit_engine, "detect_active_engine", lambda **_kw: None)
    settings = precommit_engine.resolve_engine_settings(
        config={"engine": "claude"},
        env={},
    )
    assert settings["engine"] == "claude"


def test_resolve_claude_inherits_pr_model_when_unspecified() -> None:
    # claude は model が必須なので、未指定時は config の model を使う。
    settings = precommit_engine.resolve_engine_settings(
        config={"precommit_engine": "claude", "model": "sonnet"},
        env={},
    )
    assert settings["engine"] == "claude"
    assert settings["model"] == "sonnet"


def test_resolve_opencode_model_none_passes_through() -> None:
    # opencode は model=None を許す (エンジン既定値を使う)。
    settings = precommit_engine.resolve_engine_settings(
        config={"precommit_engine": "opencode"},
        env={},
    )
    assert settings["engine"] == "opencode"
    assert settings["model"] is None


def test_resolve_antigravity_keeps_model_none() -> None:
    # antigravity は model 必須だが、解決時点では None を返し engine.py でエラーにする。
    settings = precommit_engine.resolve_engine_settings(
        config={"precommit_engine": "antigravity"},
        env={},
    )
    assert settings["engine"] == "antigravity"
    assert settings["model"] is None


def test_resolve_thinking_inheritance() -> None:
    settings = precommit_engine.resolve_engine_settings(
        config={"thinking": "medium"},
        env={},
    )
    assert settings["thinking"] == "medium"


def test_resolve_thinking_override_via_config() -> None:
    settings = precommit_engine.resolve_engine_settings(
        config={"thinking": "high", "precommit_thinking": "low"},
        env={},
    )
    assert settings["thinking"] == "low"


def test_resolve_thinking_override_via_env() -> None:
    settings = precommit_engine.resolve_engine_settings(
        config={"thinking": "high"},
        env={"PRECOMMIT_REVIEW_THINKING": "medium"},
    )
    assert settings["thinking"] == "medium"


def test_resolve_budget_inheritance() -> None:
    settings = precommit_engine.resolve_engine_settings(
        config={"review_budget_usd": 1.5},
        env={},
    )
    assert settings["budget"] == "1.5"


def test_resolve_budget_override_via_env() -> None:
    settings = precommit_engine.resolve_engine_settings(
        config={"review_budget_usd": 1.5},
        env={"PRECOMMIT_REVIEW_BUDGET_USD": "0.5"},
    )
    assert settings["budget"] == "0.5"


def test_resolve_ignores_empty_string_config_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 空文字列は未指定扱い。
    monkeypatch.setattr(precommit_engine, "detect_active_engine", lambda **_kw: None)
    settings = precommit_engine.resolve_engine_settings(
        config={"precommit_engine": "", "engine": "claude"},
        env={},
    )
    assert settings["engine"] == "claude"


def test_resolve_uses_global_config_when_no_repo(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Issue #120: リポジトリ設定が無い場合はグローバル設定が使われ、
    # 継承 (プロセスツリー検出) には倒れない。
    monkeypatch.setenv("AME_REVIEW_GLOBAL_CONFIG", str(tmp_path / "global.json"))
    (tmp_path / "global.json").write_text(
        '{"precommit_engine": "claude", "precommit_model": "sonnet"}',
        encoding="utf-8",
    )
    monkeypatch.setenv("AME_REVIEW_CONFIG", str(tmp_path / "nonexistent.json"))
    monkeypatch.setenv("AME_REVIEW_USER_CONFIG", str(tmp_path / "nonexistent.json"))
    monkeypatch.setattr(
        precommit_engine, "detect_active_engine", lambda **_kw: "opencode"
    )
    settings = precommit_engine.resolve_engine_settings(config=None, env={})
    assert settings["engine"] == "claude"
    assert settings["model"] == "sonnet"


def test_resolve_auto_defers_to_global_engine(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Issue #126: リポジトリの precommit_engine="auto" を config 引数で直接渡し、
    # _concrete_engine が "auto"→None へ変換してグローバル設定の具体エンジン (opencode)
    # へフォールバックする経路を検証する。プロセス検出 (claude) が食い違っても
    # グローバル設定のエンジンが採用される。
    monkeypatch.setenv("AME_REVIEW_GLOBAL_CONFIG", str(tmp_path / "global.json"))
    (tmp_path / "global.json").write_text(
        '{"precommit_engine": "opencode",'
        ' "precommit_model": "opencode-go/deepseek-v4-flash"}',
        encoding="utf-8",
    )
    monkeypatch.setenv("AME_REVIEW_CONFIG", str(tmp_path / "nonexistent.json"))
    monkeypatch.setenv("AME_REVIEW_USER_CONFIG", str(tmp_path / "nonexistent.json"))
    # Claude Code セッションからのコミットを想定 (検出が claude を返す)。
    monkeypatch.setattr(
        precommit_engine, "detect_active_engine", lambda **_kw: "claude"
    )
    settings = precommit_engine.resolve_engine_settings(
        config={"precommit_engine": "auto"},
        env={},
    )
    assert settings["engine"] == "opencode"


def test_resolve_repo_concrete_engine_overrides_global(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Issue #126: リポジトリが具体エンジンを明示すればグローバル設定より優先される。
    monkeypatch.setenv("AME_REVIEW_GLOBAL_CONFIG", str(tmp_path / "global.json"))
    (tmp_path / "global.json").write_text(
        '{"precommit_engine": "opencode",'
        ' "precommit_model": "opencode-go/deepseek-v4-flash"}',
        encoding="utf-8",
    )
    monkeypatch.setenv("AME_REVIEW_CONFIG", str(tmp_path / "repo.json"))
    (tmp_path / "repo.json").write_text(
        '{"precommit_engine": "claude"}',
        encoding="utf-8",
    )
    monkeypatch.setenv("AME_REVIEW_USER_CONFIG", str(tmp_path / "nonexistent.json"))
    monkeypatch.setattr(
        precommit_engine, "detect_active_engine", lambda **_kw: "opencode"
    )
    settings = precommit_engine.resolve_engine_settings(config=None, env={})
    assert settings["engine"] == "claude"


def test_resolve_auto_still_detects_when_global_engine_auto(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Issue #126: グローバル設定の precommit_engine="auto" にも具体エンジンが無ければ
    # 従来どおりプロセスツリー検出へ進む。
    monkeypatch.setenv("AME_REVIEW_GLOBAL_CONFIG", str(tmp_path / "global.json"))
    (tmp_path / "global.json").write_text(
        '{"precommit_engine": "auto"}',
        encoding="utf-8",
    )
    monkeypatch.setenv("AME_REVIEW_CONFIG", str(tmp_path / "repo.json"))
    (tmp_path / "repo.json").write_text(
        '{"precommit_engine": "auto"}',
        encoding="utf-8",
    )
    monkeypatch.setenv("AME_REVIEW_USER_CONFIG", str(tmp_path / "nonexistent.json"))
    monkeypatch.setattr(
        precommit_engine, "detect_active_engine", lambda **_kw: "opencode"
    )
    settings = precommit_engine.resolve_engine_settings(config=None, env={})
    assert settings["engine"] == "opencode"


def test_resolve_env_auto_triggers_detection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Issue #126: env の PRECOMMIT_REVIEW_ENGINE="auto" は最上位レイヤの明示指示として、
    # 下層 (リポジトリ) の具体エンジンを覆って自動検出を優先する (旧実装と同じ挙動)。
    monkeypatch.setattr(
        precommit_engine, "detect_active_engine", lambda **_kw: "opencode"
    )
    settings = precommit_engine.resolve_engine_settings(
        config={"precommit_engine": "claude"},
        env={"PRECOMMIT_REVIEW_ENGINE": "auto"},
    )
    assert settings["engine"] == "opencode"


def test_resolve_global_legacy_engine_key_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Issue #126: グローバル設定がレガシー engine キーで具体エンジンを指定している場合も
    # 尊重し、グローバル由来の precommit_model との不整合を防ぐ。
    monkeypatch.setenv("AME_REVIEW_GLOBAL_CONFIG", str(tmp_path / "global.json"))
    (tmp_path / "global.json").write_text(
        '{"engine": "opencode", "precommit_model": "opencode-go/deepseek-v4-flash"}',
        encoding="utf-8",
    )
    monkeypatch.setenv("AME_REVIEW_CONFIG", str(tmp_path / "repo.json"))
    (tmp_path / "repo.json").write_text(
        '{"precommit_engine": "auto"}',
        encoding="utf-8",
    )
    monkeypatch.setenv("AME_REVIEW_USER_CONFIG", str(tmp_path / "nonexistent.json"))
    monkeypatch.setattr(
        precommit_engine, "detect_active_engine", lambda **_kw: "claude"
    )
    settings = precommit_engine.resolve_engine_settings(config=None, env={})
    assert settings["engine"] == "opencode"
    assert settings["model"] == "opencode-go/deepseek-v4-flash"


def test_resolve_repo_legacy_engine_overrides_detection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Issue #126: リポジトリ設定がレガシー engine キーで具体エンジンを明示していれば、
    # 自動検出 (opencode) より優先される (docs の「リポジトリ設定 > 自動検出」に対応)。
    monkeypatch.setenv("AME_REVIEW_GLOBAL_CONFIG", str(tmp_path / "nonexistent.json"))
    monkeypatch.setenv("AME_REVIEW_CONFIG", str(tmp_path / "repo.json"))
    (tmp_path / "repo.json").write_text(
        '{"engine": "claude"}',
        encoding="utf-8",
    )
    monkeypatch.setenv("AME_REVIEW_USER_CONFIG", str(tmp_path / "nonexistent.json"))
    monkeypatch.setattr(
        precommit_engine, "detect_active_engine", lambda **_kw: "opencode"
    )
    settings = precommit_engine.resolve_engine_settings(config=None, env={})
    assert settings["engine"] == "claude"


# ---------------------------
# build_env (subprocess env construction)
# ---------------------------


def test_build_env_sets_engine() -> None:
    env = precommit_engine.build_env(
        {"PATH": "/usr/bin"},
        {"engine": "opencode", "model": None, "thinking": "high", "budget": "1.0"},
    )
    assert env["REVIEW_ENGINE"] == "opencode"
    assert env["REVIEW_THINKING"] == "high"
    assert env["REVIEW_BUDGET_USD"] == "1.0"
    assert "REVIEW_MODEL" not in env


def test_build_env_sets_model_when_provided() -> None:
    env = precommit_engine.build_env(
        {"PATH": "/usr/bin"},
        {"engine": "claude", "model": "sonnet", "thinking": "high", "budget": "1.0"},
    )
    assert env["REVIEW_MODEL"] == "sonnet"


def test_build_env_removes_existing_review_model_when_none() -> None:
    env = precommit_engine.build_env(
        {"PATH": "/usr/bin", "REVIEW_MODEL": "stale"},
        {"engine": "opencode", "model": None, "thinking": "high", "budget": None},
    )
    assert "REVIEW_MODEL" not in env


def test_build_env_preserves_base_env() -> None:
    env = precommit_engine.build_env(
        {"PATH": "/usr/bin", "HOME": "/home/u"},
        {"engine": "opencode", "model": None, "thinking": "high", "budget": None},
    )
    assert env["PATH"] == "/usr/bin"
    assert env["HOME"] == "/home/u"


def test_build_env_omits_budget_when_none() -> None:
    env = precommit_engine.build_env(
        {"PATH": "/usr/bin"},
        {"engine": "opencode", "model": None, "thinking": "high", "budget": None},
    )
    assert "REVIEW_BUDGET_USD" not in env or env.get("REVIEW_BUDGET_USD") is None


# ---------------------------
# show_engine_info_gate1 / AME_ENGINE_SHOW_INFO (Issue #40)
# ---------------------------


def test_resolve_show_info_defaults_true() -> None:
    settings = precommit_engine.resolve_engine_settings(
        config={"engine": "claude"},
        env={},
    )
    assert settings["show_info"] is True


def test_resolve_show_info_gate1_false() -> None:
    settings = precommit_engine.resolve_engine_settings(
        config={"show_engine_info_gate1": False},
        env={},
    )
    assert settings["show_info"] is False


def test_resolve_show_info_string_false() -> None:
    # config.user.json で "false" が文字列として書かれても false と解釈する (Issue #40)。
    settings = precommit_engine.resolve_engine_settings(
        config={"show_engine_info_gate1": "false"},
        env={},
    )
    assert settings["show_info"] is False


def test_build_env_sets_show_info_when_default() -> None:
    # show_info 未指定 (後方互換) は既定で表示フラグを注入する。
    env = precommit_engine.build_env(
        {"PATH": "/usr/bin"},
        {"engine": "opencode", "model": None, "thinking": "high", "budget": None},
    )
    assert env["AME_ENGINE_SHOW_INFO"] == "1"


def test_build_env_sets_show_info_zero_when_false() -> None:
    env = precommit_engine.build_env(
        {"PATH": "/usr/bin", "AME_ENGINE_SHOW_INFO": "1"},
        {
            "engine": "opencode",
            "model": None,
            "thinking": "high",
            "budget": None,
            "show_info": False,
        },
    )
    assert env["AME_ENGINE_SHOW_INFO"] == "0"
