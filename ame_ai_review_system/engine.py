from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from typing import TYPE_CHECKING, Any

from . import review_config

if TYPE_CHECKING:
    from collections.abc import Callable

ENGINES: tuple[str, ...] = ("claude", "opencode", "antigravity")
THINKING_LEVELS: tuple[str, ...] = ("low", "medium", "high")

_OPENCODE_VARIANT: dict[str, str] = {
    "low": "minimal",
    "medium": "medium",
    "high": "high",
}

# agy は --effort 相当の独立フラグを持たないため思考量をモデル名に埋め込む。
_ANTIGRAVITY_LABEL: dict[str, str] = {
    "low": "Low",
    "medium": "Medium",
    "high": "High",
}

_ROLE_BUDGET_KEY: dict[str, str] = {
    "review": "review_budget_usd",
    "reply": "reply_budget_usd",
}

_ROLE_MODEL_KEY: dict[str, str] = {
    "review": "review_model",
    "reply": "reply_model",
}

_ROLE_THINKING_KEY: dict[str, str] = {
    "review": "review_thinking",
    "reply": "reply_thinking",
}

_ROLE_MODEL_ENV: dict[str, str] = {
    "review": "REVIEW_MODEL",
    "reply": "REPLY_MODEL",
}

_ROLE_THINKING_ENV: dict[str, str] = {
    "review": "REVIEW_THINKING",
    "reply": "REPLY_THINKING",
}

# LLM CLI がハングしたときに CI が無限待ちしないよう、実行に上限を設ける。
_DEFAULT_TIMEOUT_SECONDS = 600.0

# agy は stdin 非対応でプロンプトを --print の引数に渡すため、1 引数のサイズ上限
# (Linux MAX_ARG_STRLEN = 128KB)に収まるよう切詰める。
_AGY_MAX_PROMPT_BYTES = 100_000

_BINARY: dict[str, str] = {
    "claude": "claude",
    "opencode": "opencode",
    "antigravity": "agy",
}

# opencode は org/model 形式、antigravity は "Gemini 3.5 Pro" のように空白を含むため、
# 許容文字は英数字・記号(./:@-)・空白に限定し、シェルメタ文字を弾く。
_MODEL_RE = re.compile(r"^[-\w./:@ ]+$")


def _first_nonempty(*values: str | None) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def resolve_settings(role: str) -> dict[str, Any]:
    config = review_config.load_config()

    engine_raw = _first_nonempty(
        os.environ.get("REVIEW_ENGINE"),
        config.get("engine"),
    )
    if not engine_raw:
        sys.exit("[engine] engine is not configured.")
    engine = engine_raw.lower()
    if engine not in ENGINES:
        choices = ", ".join(ENGINES)
        sys.exit(f"[engine] Invalid engine: {engine!r}. Choose from: {choices}")

    model_env_key = _ROLE_MODEL_ENV[role]
    model_config_key = _ROLE_MODEL_KEY[role]
    model = _first_nonempty(os.environ.get(model_env_key))
    if model is None and engine == "claude":
        # CLAUDE_MODEL と config の role別 model / model は claude 専用のため他エンジンには渡さない。
        # role別キーは user_overrides (明示的設定のみ) で確認し、未設定なら汎用 model (デフォルト含む) にフォールバック。
        model = _first_nonempty(
            os.environ.get("CLAUDE_MODEL"),
            review_config.user_overrides().get(model_config_key),
            config.get("model"),
        )
        if not model:
            sys.exit("[engine] model is not configured for the claude engine.")
    if model is None and engine in {"opencode", "antigravity"}:
        # opencode/antigravity は config からモデルを読み取る
        model = _first_nonempty(
            review_config.user_overrides().get(model_config_key),
            config.get("model"),
        )
    if model is not None and not _MODEL_RE.match(model):
        sys.exit(f"[engine] Invalid {model_env_key} value: {model!r}")

    thinking_env_key = _ROLE_THINKING_ENV[role]
    thinking_config_key = _ROLE_THINKING_KEY[role]
    thinking_raw = _first_nonempty(
        os.environ.get(thinking_env_key),
        review_config.user_overrides().get(thinking_config_key),
        config.get("thinking"),
    )
    if not thinking_raw:
        sys.exit("[engine] thinking is not configured.")
    thinking = thinking_raw.lower()
    if thinking not in THINKING_LEVELS:
        choices = ", ".join(THINKING_LEVELS)
        sys.exit(
            f"[engine] Invalid thinking: {thinking!r}. Choose from: {choices}",
        )

    budget_key = _ROLE_BUDGET_KEY[role]
    config_budget = config.get(budget_key)
    config_budget_str = str(config_budget) if config_budget is not None else None
    if role == "reply":
        budget_raw = _first_nonempty(
            os.environ.get("REPLY_BUDGET_USD"),
            os.environ.get("REVIEW_BUDGET_USD"),
            config_budget_str,
        )
    else:
        budget_raw = _first_nonempty(
            os.environ.get("REVIEW_BUDGET_USD"),
            config_budget_str,
        )
    if budget_raw is None:
        sys.exit(
            f"[engine] {budget_key} is not set (config.json or env). "
            "Set a positive value.",
        )
    try:
        budget = float(budget_raw)
    except ValueError:
        sys.exit(f"[engine] Invalid budget value: {budget_raw!r}")
    if budget <= 0:
        sys.exit(f"[engine] budget must be positive, got {budget}")

    return {
        "engine": engine,
        "model": model,
        "thinking": thinking,
        "budget": budget,
        "role": role,
    }


def build_command(
    settings: dict[str, Any],
    prompt: str,
) -> tuple[list[str], str | None]:
    engine = settings["engine"]
    model = settings["model"]
    thinking = str(settings["thinking"])
    budget = float(settings["budget"])

    if engine == "claude":
        if model is None:
            sys.exit("[engine] internal error: claude model is None")
        args = [
            "claude",
            "-p",
            "--model",
            str(model),
            "--effort",
            thinking,
            "--max-budget-usd",
            f"{budget:.2f}",
            "--output-format",
            "text",
            "--dangerously-skip-permissions",
        ]
        return args, prompt

    if engine == "opencode":
        # --auto は非インタラクティブ実行で権限プロンプトによりブロックしないため必須。
        args = [
            "opencode",
            "run",
            "--variant",
            _OPENCODE_VARIANT[thinking],
            "--format",
            "json",
            "--auto",
        ]
        if model:
            args.extend(["-m", str(model)])
        return args, prompt

    assert engine == "antigravity", f"Unhandled engine: {engine}"
    if not model:
        sys.exit("[engine] antigravity requires a base model (set REVIEW_MODEL).")
    safe_prompt = _truncate_for_arg(prompt)
    args = [
        "agy",
        "--print",
        safe_prompt,
        "--model",
        f"{model} ({_ANTIGRAVITY_LABEL[thinking]})",
    ]
    return args, None


def _truncate_for_arg(prompt: str) -> str:
    encoded = prompt.encode("utf-8")
    if len(encoded) <= _AGY_MAX_PROMPT_BYTES:
        return prompt
    print(
        f"[engine] WARNING: agy prompt truncated from {len(encoded)} bytes "
        f"to {_AGY_MAX_PROMPT_BYTES} (diff の後半が欠落する可能性があります)",
        file=sys.stderr,
    )
    truncated = encoded[:_AGY_MAX_PROMPT_BYTES].decode("utf-8", errors="ignore")
    return (
        truncated
        + "\n\n... (agy は引数でプロンプトを受け取るため、サイズ上限により切詰めました)"
    )


def _check_binary(engine: str) -> None:
    binary = _BINARY[engine]
    if not shutil.which(binary):
        sys.exit(
            f"[engine] {binary!r} not found on PATH (engine={engine!r}). "
            "Install the CLI or change the 'engine' setting.",
        )


def _normalize_claude(raw: str) -> str:
    return raw.strip()


def _normalize_opencode(raw: str) -> str:
    # 形式変更時はここでテキストが取れなくなり下のフォールバックへ落ちる。
    collected: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("type") == "text":
            part = event.get("part")
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                collected.append(part["text"])
    result = "".join(collected)
    if result.strip():
        return result
    # テキストイベントがない・または空文字列のみの場合は出力形式が変わった可能性が高い。
    # 生データを下流へ流すと payload.py が破損するため、呼び出し側で失敗させる。
    msg = (
        "[engine] opencode: no text events found, aborting. "
        'Expected NDJSON with {"type":"text"} events from '
        "`opencode run --format json` (flag name may differ by version; "
        "verify with `opencode run --help`)."
    )
    raise ValueError(msg)


def _normalize_antigravity(raw: str) -> str:
    return raw.strip()


_NORMALIZE: dict[str, Callable[[str], str]] = {
    "claude": _normalize_claude,
    "opencode": _normalize_opencode,
    "antigravity": _normalize_antigravity,
}


def run_engine(settings: dict[str, Any], prompt: str) -> int:
    engine = settings["engine"]
    _check_binary(engine)

    args, stdin_data = build_command(settings, prompt)
    proc_env = os.environ.copy()
    timeout_raw = os.environ.get("REVIEW_TIMEOUT_SECONDS")
    if timeout_raw:
        try:
            timeout = float(timeout_raw)
        except ValueError:
            sys.exit(f"[engine] Invalid REVIEW_TIMEOUT_SECONDS: {timeout_raw!r}")
    else:
        timeout = _DEFAULT_TIMEOUT_SECONDS
    if timeout <= 0:
        sys.exit(f"[engine] REVIEW_TIMEOUT_SECONDS must be positive, got {timeout}")
    model_display = settings["model"] or "<engine-default>"
    print(
        f"[engine] {engine} starting "
        f"(model={model_display}, thinking={settings['thinking']}, "
        f"role={settings['role']})",
        file=sys.stderr,
    )
    try:
        proc = subprocess.run(
            args,
            input=stdin_data,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            env=proc_env,
        )
    except subprocess.TimeoutExpired as exc:
        msg = f"[engine] {engine} timed out after {timeout:.0f}s"
        raise SystemExit(msg) from exc
    except FileNotFoundError as exc:
        msg = f"[engine] {engine} binary failed to start: {exc}"
        raise SystemExit(msg) from exc

    if proc.stderr:
        sys.stderr.write(proc.stderr)

    if proc.returncode != 0:
        sys.exit(f"[engine] {engine} exited with code {proc.returncode}.")

    try:
        output = _NORMALIZE[engine](proc.stdout)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    if not output.strip():
        sys.exit(f"[engine] {engine} produced empty output.")
    sys.stdout.write(output)
    if not output.endswith("\n"):
        sys.stdout.write("\n")
    sys.stdout.flush()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="LLM engine adapter for the review pipeline.",
    )
    parser.add_argument(
        "--role",
        choices=["review", "reply"],
        default="review",
    )
    namespace = parser.parse_args(argv)
    prompt = sys.stdin.read()
    if not prompt.strip():
        sys.exit("[engine] stdin prompt is empty.")
    settings = resolve_settings(str(namespace.role))
    if settings["engine"] != "claude":
        print(
            f"[engine] WARNING: budget limit is not enforced for {settings['engine']}",
            file=sys.stderr,
        )
    return run_engine(settings, prompt)


if __name__ == "__main__":
    sys.exit(main())
