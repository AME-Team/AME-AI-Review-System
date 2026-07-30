"""Review system configuration loader and slash-command detection.

サブコマンド:
  get <key>                 ``config.json`` から値を読み取り stdout へ出力する。
                            ファイルやキーが存在しない場合は組み込みデフォルトを使う。
  is-review-command <body>  コメント本文がレビュー要求コマンド
                            (``/request-review`` / ``/review``) かを判定し
                            ``true`` / ``false`` を stdout へ出力する。

設定ファイルのパスは環境変数 ``AME_REVIEW_CONFIG`` で上書き可能。
ユーザー固有の上書きは ``config.user.json``（環境変数 ``AME_REVIEW_USER_CONFIG`` でパス変更可能）に記述する。
``config.user.json`` は Git 管理対象外であり、存在しない場合は無視される。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, cast

from . import paths

_DEFAULTS: dict[str, Any] = {
    "precommit_review_enabled": True,
    "precommit_require_static_checks": True,
    "pr_review_require_static_checks": True,
    "ai_review_enforce_no_skip": True,
    "precommit_engine": "auto",
    "precommit_model": None,
    "precommit_thinking": None,
    "precommit_review_budget_usd": None,
    "engine": "claude",
    "model": "sonnet",
    "review_model": "sonnet",
    "reply_model": "haiku",
    "thinking": "high",
    "review_thinking": "high",
    "reply_thinking": "low",
    "review_budget_usd": 2.00,
    "reply_budget_usd": 0.20,
}

_REVIEW_COMMANDS = ("/request-review", "/review")

_MIN_ARGS = 2


def _config_path() -> Path:
    override = os.environ.get("AME_REVIEW_CONFIG")
    if override:
        return Path(override)
    return paths.config_path()


def _user_config_path() -> Path:
    override = os.environ.get("AME_REVIEW_USER_CONFIG")
    if override:
        return Path(override)
    return paths.user_config_path()


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return cast("dict[str, Any]", data) if isinstance(data, dict) else None


def load_config() -> dict[str, Any]:
    config: dict[str, Any] = dict(_DEFAULTS)
    data: dict[str, object] | None = _read_json(_config_path())
    if data is not None:
        config.update(data)
    user_data = _read_json(_user_config_path())
    if user_data is not None:
        config.update(user_data)
    return config


def user_overrides() -> dict[str, Any]:
    """Return keys explicitly set in config.json or config.user.json (user wins)."""
    overrides: dict[str, Any] = {}
    data: dict[str, object] | None = _read_json(_config_path())
    if data is not None:
        overrides.update(data)
    user_data = _read_json(_user_config_path())
    if user_data is not None:
        overrides.update(user_data)
    return overrides


def is_review_command(body: str) -> bool:
    stripped = body.strip()
    if not stripped:
        return False
    first_line = stripped.splitlines()[0].strip()
    return any(
        first_line == cmd or first_line.startswith(cmd + " ")
        for cmd in _REVIEW_COMMANDS
    )


def get_ts_checks(ts_files: list[str]) -> list[tuple[str, list[str]]]:
    """Return command lists for TypeScript compiler and ESLint checks."""
    if not ts_files:
        return []
    checks: list[tuple[str, list[str]]] = []
    tsconfig = load_config().get("tsconfig_path")
    if not tsconfig:
        default_tsconfig = paths.project_root() / "tsconfig.json"
        if default_tsconfig.exists():
            tsconfig = str(default_tsconfig)
    if tsconfig:
        checks.append(
            (
                "tsc",
                [
                    "./node_modules/.bin/tsc",
                    "--noEmit",
                    "-p",
                    str(tsconfig),
                ],
            ),
        )
    checks.append(
        (
            "eslint",
            [
                "./node_modules/.bin/eslint",
                "--max-warnings=0",
                "--no-warn-ignored",
                *ts_files,
            ],
        ),
    )
    return checks


def _emit_value(value: Any) -> None:
    if isinstance(value, bool):
        print("true" if value else "false")
    elif value is None:
        print()
    else:
        print(value)


def _cmd_get(args: list[str]) -> int:
    key = args[0] if args else ""
    _emit_value(load_config().get(key, _DEFAULTS.get(key)))
    return 0


def _cmd_is_review_command(args: list[str]) -> int:
    body = args[0] if args else ""
    print("true" if is_review_command(body) else "false")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < _MIN_ARGS:
        print(
            "Usage: review_config.py get <key> | is-review-command <body>",
            file=sys.stderr,
        )
        return 2
    cmd = argv[1]
    rest = argv[2:]
    if cmd == "get":
        return _cmd_get(rest)
    if cmd == "is-review-command":
        return _cmd_is_review_command(rest)
    print(f"Unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
