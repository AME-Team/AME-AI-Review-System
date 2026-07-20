from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from ame_ai_review_system import engine
from ame_ai_review_system.engine import (
    _AGY_MAX_PROMPT_BYTES,
    build_command,
    resolve_settings,
    run_engine,
)

_ENV_KEYS = (
    "REVIEW_ENGINE",
    "REVIEW_MODEL",
    "REPLY_MODEL",
    "REVIEW_THINKING",
    "REPLY_THINKING",
    "REVIEW_BUDGET_USD",
    "REPLY_BUDGET_USD",
    "REVIEW_TIMEOUT_SECONDS",
    "CLAUDE_MODEL",
    "AME_REVIEW_CONFIG",
    "HEADROOM_ENABLED",
    "HEADROOM_PORT",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def _write_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    data: dict[str, Any],
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setenv("AME_REVIEW_CONFIG", str(config_path))


@dataclass
class _FakeCompleted:
    stdout: str = ""
    returncode: int = 0
    stderr: str = ""


def _patch_engine(
    monkeypatch: pytest.MonkeyPatch,
    stdout: str = "",
    returncode: int = 0,
    stderr: str = "",
    binary: str = "/usr/bin/fake",
) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    monkeypatch.setattr(shutil, "which", lambda _name: binary)

    def fake_run(args: list[str], **kwargs: object) -> _FakeCompleted:
        captured["args"] = args
        captured["input"] = kwargs.get("input")
        captured["env"] = kwargs.get("env")
        return _FakeCompleted(stdout=stdout, returncode=returncode, stderr=stderr)

    monkeypatch.setattr(subprocess, "run", fake_run)
    return captured


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


def test_resolve_settings_opencode_ignores_config_model(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _write_config(monkeypatch, tmp_path, {"engine": "opencode", "model": "sonnet"})
    settings = resolve_settings("review")
    assert settings["engine"] == "opencode"
    assert settings["model"] is None


def test_resolve_settings_opencode_ignores_claude_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # CLAUDE_MODEL は Claude 専用名の可能性があるため claude 以外では参照しない。
    monkeypatch.setenv("REVIEW_ENGINE", "opencode")
    monkeypatch.setenv("CLAUDE_MODEL", "sonnet")
    settings = resolve_settings("review")
    assert settings["model"] is None


def test_resolve_settings_warns_on_ignored_config_model(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_config(monkeypatch, tmp_path, {"engine": "opencode", "model": "some-model"})
    resolve_settings("review")
    err = capsys.readouterr().err
    assert "ignored" in err
    assert "opencode" in err


def test_resolve_settings_no_warning_without_explicit_model(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_config(monkeypatch, tmp_path, {"engine": "opencode"})
    resolve_settings("review")
    assert "ignored" not in capsys.readouterr().err


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


# --- build_command ---------------------------------------------------------


def test_build_command_claude_uses_stdin_and_effort() -> None:
    args, stdin_data = build_command(
        {
            "engine": "claude",
            "model": "sonnet",
            "thinking": "high",
            "budget": 2.0,
            "role": "review",
        },
        "PROMPT",
    )
    assert args[0] == "claude"
    assert "--effort" in args
    assert args[args.index("--effort") + 1] == "high"
    assert "--output-format" in args
    assert args[args.index("--output-format") + 1] == "text"
    assert stdin_data == "PROMPT"


def test_build_command_opencode_maps_variant() -> None:
    args, stdin_data = build_command(
        {
            "engine": "opencode",
            "model": "zai-coding-plan/glm-5.2",
            "thinking": "low",
            "budget": 1.0,
            "role": "review",
        },
        "PROMPT",
    )
    assert args[0] == "opencode"
    assert "-m" in args
    assert args[args.index("-m") + 1] == "zai-coding-plan/glm-5.2"
    assert args[args.index("--variant") + 1] == "minimal"
    assert "--format" in args
    assert "--auto" in args
    assert stdin_data == "PROMPT"


def test_build_command_opencode_omits_model_when_unset() -> None:
    args, stdin_data = build_command(
        {
            "engine": "opencode",
            "model": None,
            "thinking": "high",
            "budget": 1.0,
            "role": "review",
        },
        "PROMPT",
    )
    assert "-m" not in args
    assert args[args.index("--variant") + 1] == "high"
    assert stdin_data == "PROMPT"


def test_build_command_claude_requires_model() -> None:
    with pytest.raises(SystemExit):
        build_command(
            {
                "engine": "claude",
                "model": None,
                "thinking": "high",
                "budget": 1.0,
                "role": "review",
            },
            "PROMPT",
        )


def test_build_command_claude_wraps_with_headroom(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HEADROOM_ENABLED", "1")
    args, stdin_data = build_command(
        {
            "engine": "claude",
            "model": "sonnet",
            "thinking": "high",
            "budget": 2.0,
            "role": "review",
        },
        "PROMPT",
    )
    assert args[:3] == ["headroom", "wrap", "claude"]
    # -- で wrap 独自フラグと対象 CLI のフラグを分離する
    sep = args.index("--")
    assert "--no-proxy" in args[:sep]
    assert "--no-mcp" in args[:sep]
    # -- の後ろは元の claude 引数 (バイナリ名は headroom wrap 側で解決されるため除外)
    assert args[sep + 1] == "-p"
    assert "--output-format" in args[sep + 1 :]
    assert stdin_data == "PROMPT"


def test_build_command_opencode_wraps_with_headroom(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HEADROOM_ENABLED", "true")
    args, _ = build_command(
        {
            "engine": "opencode",
            "model": "zai-coding-plan/glm-5.2",
            "thinking": "low",
            "budget": 1.0,
            "role": "review",
        },
        "PROMPT",
    )
    assert args[:3] == ["headroom", "wrap", "opencode"]
    sep = args.index("--")
    assert "--no-proxy" in args[:sep]
    # バイナリ名は headroom wrap 側で解決されるため除外、run が先頭
    assert args[sep + 1] == "run"


def test_build_command_headroom_injects_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # headroom wrap は HEADROOM_PORT 環境変数を読まないため、
    # -p <port> をフラグ領域へ明示的に注入する。
    monkeypatch.setenv("HEADROOM_ENABLED", "1")
    monkeypatch.setenv("HEADROOM_PORT", "9999")
    args, _ = build_command(
        {
            "engine": "claude",
            "model": "sonnet",
            "thinking": "high",
            "budget": 2.0,
            "role": "review",
        },
        "PROMPT",
    )
    sep = args.index("--")
    pre_sep = args[:sep]
    assert "-p" in pre_sep
    port_idx = pre_sep.index("-p")
    assert pre_sep[port_idx + 1] == "9999"


def test_build_command_antigravity_not_wrapped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # antigravity は wrap 非対応: HEADROOM_ENABLED でも引数はそのまま。
    monkeypatch.setenv("HEADROOM_ENABLED", "1")
    args, _ = build_command(
        {
            "engine": "antigravity",
            "model": "Gemini 3.5 Pro",
            "thinking": "high",
            "budget": 1.0,
            "role": "review",
        },
        "PROMPT",
    )
    assert args[0] == "agy"
    assert "headroom" not in args


def test_build_command_antigravity_requires_model() -> None:
    with pytest.raises(SystemExit):
        build_command(
            {
                "engine": "antigravity",
                "model": None,
                "thinking": "high",
                "budget": 1.0,
                "role": "review",
            },
            "PROMPT",
        )


def test_build_command_antigravity_embeds_thinking_in_model() -> None:
    args, stdin_data = build_command(
        {
            "engine": "antigravity",
            "model": "Gemini 3.5 Pro",
            "thinking": "medium",
            "budget": 1.0,
            "role": "review",
        },
        "PROMPT",
    )
    assert args[0] == "agy"
    assert args[args.index("--model") + 1] == "Gemini 3.5 Pro (Medium)"
    # agy は stdin 非対応のためプロンプトを --print 引数で渡す。
    assert args[args.index("--print") + 1] == "PROMPT"
    assert stdin_data is None


def test_build_command_antigravity_truncates_large_prompt() -> None:
    big = "x" * (_AGY_MAX_PROMPT_BYTES + 5000)
    args, _ = build_command(
        {
            "engine": "antigravity",
            "model": "Gemini 3.5 Pro",
            "thinking": "high",
            "budget": 1.0,
            "role": "review",
        },
        big,
    )
    prompt_arg = args[args.index("--print") + 1]
    assert "切詰めました" in prompt_arg
    assert len(prompt_arg.encode("utf-8")) <= _AGY_MAX_PROMPT_BYTES + 200


# --- run_engine ------------------------------------------------------------


def test_run_engine_missing_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    with pytest.raises(SystemExit):
        run_engine(
            {
                "engine": "antigravity",
                "model": "Gemini 3.5 Pro",
                "thinking": "high",
                "budget": 1.0,
                "role": "review",
            },
            "PROMPT",
        )


def test_run_engine_claude_passes_text_through(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # claude は --output-format text でプレーンテキストを出力するためそのまま通す。
    payload = "## 総評\n問題ありません。LGTM。"
    captured = _patch_engine(monkeypatch, stdout=payload)
    rc = run_engine(
        {
            "engine": "claude",
            "model": "sonnet",
            "thinking": "high",
            "budget": 2.0,
            "role": "review",
        },
        "PROMPT",
    )
    assert rc == 0
    assert captured["input"] == "PROMPT"
    out = capsys.readouterr()
    assert out.out.strip() == payload


def test_run_engine_claude_plain_text_passthrough(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_engine(monkeypatch, stdout='{"summary":"plain review"}')
    run_engine(
        {
            "engine": "claude",
            "model": "sonnet",
            "thinking": "high",
            "budget": 2.0,
            "role": "review",
        },
        "PROMPT",
    )
    out = capsys.readouterr()
    assert out.out.strip() == '{"summary":"plain review"}'


def test_run_engine_opencode_parses_ndjson(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    events = "\n".join(
        [
            json.dumps({"type": "step_start", "part": {"type": "step-start"}}),
            json.dumps({"type": "text", "part": {"type": "text", "text": "Hello "}}),
            json.dumps({"type": "text", "part": {"type": "text", "text": "World"}}),
            json.dumps({"type": "step_finish", "part": {"type": "step-finish"}}),
        ],
    )
    captured = _patch_engine(monkeypatch, stdout=events)
    run_engine(
        {
            "engine": "opencode",
            "model": "anthropic/claude-sonnet-4-5",
            "thinking": "high",
            "budget": 1.0,
            "role": "review",
        },
        "PROMPT",
    )
    assert captured["input"] == "PROMPT"
    out = capsys.readouterr()
    assert out.out.strip() == "Hello World"


def test_run_engine_opencode_aborts_without_text_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # テキストイベントがない(出力形式変化など)場合は生データを流さず明示的に失敗する。
    _patch_engine(monkeypatch, stdout="not json at all")
    with pytest.raises(SystemExit):
        run_engine(
            {
                "engine": "opencode",
                "model": "zai-coding-plan/glm-5.2",
                "thinking": "high",
                "budget": 1.0,
                "role": "review",
            },
            "PROMPT",
        )


def test_run_engine_opencode_aborts_with_empty_text_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # テキストイベントは存在するが内容が全て空文字の場合も失敗させる。
    events = json.dumps({"type": "text", "part": {"type": "text", "text": ""}})
    _patch_engine(monkeypatch, stdout=events)
    with pytest.raises(SystemExit):
        run_engine(
            {
                "engine": "opencode",
                "model": "zai-coding-plan/glm-5.2",
                "thinking": "high",
                "budget": 1.0,
                "role": "review",
            },
            "PROMPT",
        )


def test_run_engine_nonzero_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_engine(monkeypatch, stdout="", returncode=2, stderr="boom")
    with pytest.raises(SystemExit):
        run_engine(
            {
                "engine": "claude",
                "model": "sonnet",
                "thinking": "high",
                "budget": 2.0,
                "role": "review",
            },
            "PROMPT",
        )


def test_run_engine_rejects_empty_output(monkeypatch: pytest.MonkeyPatch) -> None:
    # exit 0 でも空文字列ならシェルの -s チェックに頼らず明示的に失敗させる。
    _patch_engine(monkeypatch, stdout="", returncode=0)
    with pytest.raises(SystemExit):
        run_engine(
            {
                "engine": "claude",
                "model": "sonnet",
                "thinking": "high",
                "budget": 2.0,
                "role": "review",
            },
            "PROMPT",
        )


def test_run_engine_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/fake")

    def fake_run(
        *_args: object,
        **_kwargs: object,
    ) -> Any:
        raise subprocess.TimeoutExpired(cmd=["fake"], timeout=600)

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(SystemExit):
        run_engine(
            {
                "engine": "claude",
                "model": "sonnet",
                "thinking": "high",
                "budget": 2.0,
                "role": "review",
            },
            "PROMPT",
        )


def test_run_engine_invalid_timeout_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/fake")
    monkeypatch.setenv("REVIEW_TIMEOUT_SECONDS", "abc")
    with pytest.raises(SystemExit):
        run_engine(
            {
                "engine": "claude",
                "model": "sonnet",
                "thinking": "high",
                "budget": 2.0,
                "role": "review",
            },
            "PROMPT",
        )


def test_run_engine_nonpositive_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/fake")
    monkeypatch.setenv("REVIEW_TIMEOUT_SECONDS", "0")
    with pytest.raises(SystemExit):
        run_engine(
            {
                "engine": "claude",
                "model": "sonnet",
                "thinking": "high",
                "budget": 2.0,
                "role": "review",
            },
            "PROMPT",
        )


def test_run_engine_antigravity_strips_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_engine(monkeypatch, stdout="  raw antigravity text\n")
    run_engine(
        {
            "engine": "antigravity",
            "model": "Gemini 3.5 Pro",
            "thinking": "high",
            "budget": 1.0,
            "role": "review",
        },
        "PROMPT",
    )
    out = capsys.readouterr()
    assert out.out.strip() == "raw antigravity text"


def test_run_engine_antigravity_no_proxy_env_when_headroom(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # antigravity は headroom 非対応 (wrap 不可・経路未検証) のため、
    # HEADROOM_ENABLED=1 でもプロキシ env を注入せず親 env を継承する。
    # proc_env から HEADROOM_* を除去した env が渡されることを確認。
    monkeypatch.setenv("HEADROOM_ENABLED", "1")
    monkeypatch.setenv("HEADROOM_PORT", "8787")
    captured = _patch_engine(monkeypatch, stdout="ok")
    run_engine(
        {
            "engine": "antigravity",
            "model": "Gemini 3.5 Pro",
            "thinking": "high",
            "budget": 1.0,
            "role": "review",
        },
        "PROMPT",
    )
    assert captured["env"] is not None
    assert "HEADROOM_ENABLED" not in captured["env"]
    assert "HEADROOM_PORT" not in captured["env"]
    assert "HEADROOM_OUTPUT_SHAPER" not in captured["env"]


def test_run_engine_no_env_override_without_headroom(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # headroom 無効時は親プロセスの環境変数をそのまま継承する
    # (proc_env をコピーして渡すが、HEADROOM_* は除去されない)
    captured = _patch_engine(monkeypatch, stdout="ok")
    run_engine(
        {
            "engine": "claude",
            "model": "sonnet",
            "thinking": "high",
            "budget": 1.0,
            "role": "review",
        },
        "PROMPT",
    )
    assert captured["env"] is not None
    assert "PATH" in captured["env"]


# --- main ------------------------------------------------------------------


def test_main_reads_stdin_and_role(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_config(monkeypatch, tmp_path, {})
    monkeypatch.setattr(sys, "stdin", io.StringIO("STDIN PROMPT"))
    captured = _patch_engine(monkeypatch, stdout="RESULT")
    assert engine.main(["--role", "review"]) == 0
    assert captured["input"] == "STDIN PROMPT"
    out = capsys.readouterr()
    assert out.out.strip() == "RESULT"


def test_main_rejects_empty_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    with pytest.raises(SystemExit):
        engine.main(["--role", "review"])
