# pyright: basic
from __future__ import annotations

import io
import json
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from ame_ai_review_system import engine
from ame_ai_review_system.engine import resolve_settings, run_engine

_ENV_KEYS = (
    "REVIEW_ENGINE",
    "REVIEW_MODEL",
    "REPLY_MODEL",
    "REVIEW_THINKING",
    "REPLY_THINKING",
    "REVIEW_BUDGET_USD",
    "REPLY_BUDGET_USD",
    "REVIEW_TIMEOUT_SECONDS",
    "REVIEW_SDK_LANG",
    "CLAUDE_MODEL",
    "CLAUDE_SDK_LANG",
    "AME_REVIEW_CONFIG",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    # 開発者ローカルの config.user.json (Git 管理対象外) がテストに漏れ込むのを防ぐ。
    monkeypatch.setenv(
        "AME_REVIEW_USER_CONFIG", str(tmp_path / "unused_user_config.json")
    )


def _write_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    data: dict[str, Any],
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setenv("AME_REVIEW_CONFIG", str(config_path))


class _FakeAdapter:
    def __init__(self, result: str = "OK") -> None:
        self.result = result
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def run(self, prompt: str, settings: dict[str, Any]) -> str:
        self.calls.append((prompt, settings))
        return self.result


def _patch_adapter(
    monkeypatch: pytest.MonkeyPatch,
    result: str = "OK",
) -> _FakeAdapter:
    adapter = _FakeAdapter(result=result)
    monkeypatch.setattr(engine, "get_adapter", lambda _engine, _lang=None: adapter)
    return adapter


# --- resolve_settings ------------------------------------------------------


def test_resolve_settings_defaults(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _write_config(monkeypatch, tmp_path, {})
    settings = resolve_settings("review")
    assert settings["engine"] == "claude"
    assert settings["model"] == "sonnet"
    assert settings["thinking"] == "high"
    assert settings["budget"] == pytest.approx(2.0)
    assert settings["sdk_lang"] == "python"
    assert settings["timeout"] == pytest.approx(600.0)
    assert settings["role"] == "review"


def test_resolve_settings_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REVIEW_ENGINE", "opencode")
    monkeypatch.setenv("REVIEW_MODEL", "anthropic/claude-sonnet-4-5")
    monkeypatch.setenv("REVIEW_THINKING", "low")
    monkeypatch.setenv("REVIEW_BUDGET_USD", "0.5")
    settings = resolve_settings("review")
    assert settings["engine"] == "opencode"
    assert settings["model"] == "anthropic/claude-sonnet-4-5"
    assert settings["thinking"] == "low"
    assert settings["budget"] == pytest.approx(0.5)
    assert settings["sdk_lang"] == "typescript"


def test_resolve_settings_claude_sdk_lang_selectable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _write_config(monkeypatch, tmp_path, {"engine": "claude", "sdk_lang": "typescript"})
    assert resolve_settings("review")["sdk_lang"] == "typescript"


def test_resolve_settings_claude_sdk_lang_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _write_config(monkeypatch, tmp_path, {"engine": "claude"})
    monkeypatch.setenv("CLAUDE_SDK_LANG", "typescript")
    assert resolve_settings("review")["sdk_lang"] == "typescript"


def test_resolve_settings_opencode_forces_typescript(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _write_config(monkeypatch, tmp_path, {"engine": "opencode", "sdk_lang": "python"})
    # OpenCode は TS SDK しかないため python 指定は拒否される。
    with pytest.raises(SystemExit):
        resolve_settings("review")


def test_resolve_settings_claude_model_backward_compat(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _write_config(monkeypatch, tmp_path, {"engine": "claude"})
    monkeypatch.setenv("CLAUDE_MODEL", "opus")
    settings = resolve_settings("review")
    assert settings["model"] == "opus"


def test_resolve_settings_claude_model_default(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _write_config(monkeypatch, tmp_path, {})
    settings = resolve_settings("review")
    assert settings["model"] == "sonnet"


def test_resolve_settings_config_model_override(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _write_config(monkeypatch, tmp_path, {"engine": "claude", "model": "opus"})
    settings = resolve_settings("review")
    assert settings["engine"] == "claude"
    assert settings["model"] == "opus"


def test_resolve_settings_opencode_uses_config_model(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _write_config(monkeypatch, tmp_path, {"engine": "opencode", "model": "zai/glm"})
    settings = resolve_settings("review")
    assert settings["engine"] == "opencode"
    assert settings["model"] == "zai/glm"


def test_resolve_settings_opencode_ignores_claude_model(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # CLAUDE_MODEL は Claude 専用名の可能性があるため claude 以外では参照しない。
    _write_config(monkeypatch, tmp_path, {"engine": "opencode", "model": "zai/glm"})
    monkeypatch.setenv("CLAUDE_MODEL", "sonnet")
    settings = resolve_settings("review")
    assert settings["model"] == "zai/glm"


def test_resolve_settings_env_model_for_opencode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REVIEW_ENGINE", "opencode")
    monkeypatch.setenv("REVIEW_MODEL", "zai-coding-plan/glm-5.2")
    settings = resolve_settings("review")
    assert settings["model"] == "zai-coding-plan/glm-5.2"


def test_resolve_settings_role_budget(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _write_config(
        monkeypatch,
        tmp_path,
        {"review_budget_usd": 3.0, "reply_budget_usd": 0.1},
    )
    assert resolve_settings("review")["budget"] == pytest.approx(3.0)
    assert resolve_settings("reply")["budget"] == pytest.approx(0.1)


def test_resolve_settings_role_specific_model(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _write_config(
        monkeypatch,
        tmp_path,
        {"engine": "claude", "review_model": "opus", "reply_model": "haiku"},
    )
    assert resolve_settings("review")["model"] == "opus"
    assert resolve_settings("reply")["model"] == "haiku"


def test_resolve_settings_role_specific_thinking(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _write_config(
        monkeypatch,
        tmp_path,
        {"engine": "claude", "review_thinking": "high", "reply_thinking": "low"},
    )
    assert resolve_settings("review")["thinking"] == "high"
    assert resolve_settings("reply")["thinking"] == "low"


def test_resolve_settings_reply_model_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REPLY_MODEL", "haiku")
    assert resolve_settings("reply")["model"] == "haiku"


def test_resolve_settings_reply_thinking_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REPLY_THINKING", "low")
    assert resolve_settings("reply")["thinking"] == "low"


def test_resolve_settings_role_model_falls_back_to_generic(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _write_config(monkeypatch, tmp_path, {"engine": "claude", "model": "opus"})
    assert resolve_settings("review")["model"] == "opus"
    assert resolve_settings("reply")["model"] == "opus"


def test_resolve_settings_reply_budget_env_priority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REPLY_BUDGET_USD", "0.25")
    monkeypatch.setenv("REVIEW_BUDGET_USD", "9.0")
    assert resolve_settings("reply")["budget"] == pytest.approx(0.25)
    assert resolve_settings("review")["budget"] == pytest.approx(9.0)


def test_resolve_settings_reply_falls_back_to_review_budget_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REVIEW_BUDGET_USD", "9.0")
    assert resolve_settings("reply")["budget"] == pytest.approx(9.0)


def test_resolve_settings_invalid_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REVIEW_ENGINE", "gemini")
    with pytest.raises(SystemExit):
        resolve_settings("review")


def test_resolve_settings_invalid_thinking(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REVIEW_THINKING", "ultra")
    with pytest.raises(SystemExit):
        resolve_settings("review")


def test_resolve_settings_invalid_budget(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _write_config(monkeypatch, tmp_path, {"review_budget_usd": "not-a-number"})
    with pytest.raises(SystemExit):
        resolve_settings("review")


def test_resolve_settings_nonpositive_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REVIEW_BUDGET_USD", "0")
    with pytest.raises(SystemExit):
        resolve_settings("review")


def test_resolve_settings_invalid_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REVIEW_MODEL", "bad;model")
    with pytest.raises(SystemExit):
        resolve_settings("review")


def test_resolve_settings_timeout_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REVIEW_TIMEOUT_SECONDS", "120")
    assert resolve_settings("review")["timeout"] == pytest.approx(120.0)


def test_resolve_settings_invalid_timeout_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REVIEW_TIMEOUT_SECONDS", "abc")
    with pytest.raises(SystemExit):
        resolve_settings("review")


# --- adapters --------------------------------------------------------------


def test_claude_ts_adapter_args(monkeypatch: pytest.MonkeyPatch) -> None:
    from ame_ai_review_system.engines import claude_ts, ts_runner

    captured: dict[str, Any] = {}

    def fake_sidecar(script: str, prompt: str, args: list[str], timeout: float) -> str:
        captured["script"] = script
        captured["args"] = args
        captured["timeout"] = timeout
        return "RESULT"

    monkeypatch.setattr(ts_runner, "run_sidecar", fake_sidecar)
    out = claude_ts.ClaudeTsAdapter.run(
        "PROMPT",
        {
            "engine": "claude",
            "model": "sonnet",
            "thinking": "high",
            "budget": 2.0,
            "timeout": 600.0,
        },
    )
    assert out == "RESULT"
    assert captured["script"] == "claude.mjs"
    assert "--model" in captured["args"]
    assert captured["args"][captured["args"].index("--model") + 1] == "sonnet"
    assert captured["args"][captured["args"].index("--effort") + 1] == "high"


def test_opencode_ts_adapter_args(monkeypatch: pytest.MonkeyPatch) -> None:
    from ame_ai_review_system.engines import opencode_ts, ts_runner

    captured: dict[str, Any] = {}

    def fake_sidecar(script: str, prompt: str, args: list[str], timeout: float) -> str:
        captured["script"] = script
        captured["args"] = args
        return "RESULT"

    monkeypatch.setattr(ts_runner, "run_sidecar", fake_sidecar)
    opencode_ts.OpencodeTsAdapter.run(
        "PROMPT",
        {
            "engine": "opencode",
            "model": "anthropic/claude-sonnet-4",
            "thinking": "low",
            "budget": 1.0,
            "timeout": 600.0,
        },
    )
    assert captured["script"] == "opencode.mjs"
    assert (
        captured["args"][captured["args"].index("--model") + 1]
        == "anthropic/claude-sonnet-4"
    )


def test_claude_python_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    from ame_ai_review_system.engines import claude_python

    class _FakeResult:
        is_error = False
        result = "## 総評\nLGTM"

    async def _fake_query(prompt: str, options: object) -> AsyncIterator[Any]:
        yield _FakeResult()

    monkeypatch.setattr(
        claude_python,
        "_import_sdk",
        lambda: (_fake_query, lambda **kw: kw, _FakeResult),
    )
    out = claude_python.ClaudePythonAdapter.run(
        "PROMPT",
        {"model": "sonnet", "thinking": "high", "budget": 2.0, "timeout": 600.0},
    )
    assert out == "## 総評\nLGTM"


def test_claude_python_missing_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    from ame_ai_review_system.engines import claude_python

    def _raise() -> Any:
        msg = "no sdk"
        raise SystemExit(msg)

    monkeypatch.setattr(claude_python, "_import_sdk", _raise)
    with pytest.raises(SystemExit):
        claude_python.ClaudePythonAdapter.run(
            "PROMPT",
            {"model": "sonnet", "thinking": "high", "budget": 2.0, "timeout": 600.0},
        )


def test_registry_unknown_engine() -> None:
    from ame_ai_review_system.engines import registry

    with pytest.raises(ValueError, match="Unknown engine"):
        registry.get_adapter("gemini")


def test_registry_unsupported_sdk_lang() -> None:
    from ame_ai_review_system.engines import registry

    with pytest.raises(ValueError, match="not available"):
        registry.get_adapter("antigravity", "typescript")


# --- run_engine ------------------------------------------------------------


def test_run_engine_dispatches_to_adapter(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    adapter = _patch_adapter(monkeypatch, result="REVIEW BODY")
    rc = run_engine(
        {
            "engine": "claude",
            "model": "sonnet",
            "thinking": "high",
            "budget": 2.0,
            "sdk_lang": "python",
            "timeout": 600.0,
            "role": "review",
        },
        "PROMPT",
    )
    assert rc == 0
    assert adapter.calls[0][0] == "PROMPT"
    out = capsys.readouterr()
    assert out.out.strip() == "REVIEW BODY"


def test_run_engine_rejects_empty_output(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_adapter(monkeypatch, result="   ")
    with pytest.raises(SystemExit):
        run_engine(
            {
                "engine": "claude",
                "model": "sonnet",
                "thinking": "high",
                "budget": 2.0,
                "sdk_lang": "python",
                "timeout": 600.0,
                "role": "review",
            },
            "PROMPT",
        )


def test_run_engine_warns_non_claude_budget(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_adapter(monkeypatch, result="ok")
    run_engine(
        {
            "engine": "opencode",
            "model": "zai/glm",
            "thinking": "high",
            "budget": 1.0,
            "sdk_lang": "typescript",
            "timeout": 600.0,
            "role": "review",
        },
        "PROMPT",
    )
    err = capsys.readouterr()
    assert "budget limit is not enforced" in err.err


# --- main ------------------------------------------------------------------


def test_main_reads_stdin_and_dispatches(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_config(monkeypatch, tmp_path, {})
    monkeypatch.setattr(sys, "stdin", io.StringIO("STDIN PROMPT"))
    adapter = _patch_adapter(monkeypatch, result="RESULT")
    assert engine.main(["--role", "review"]) == 0
    assert adapter.calls[0][0] == "STDIN PROMPT"
    out = capsys.readouterr()
    assert out.out.strip() == "RESULT"


def test_main_rejects_empty_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    with pytest.raises(SystemExit):
        engine.main(["--role", "review"])
