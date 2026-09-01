from __future__ import annotations

import os
import pathlib
import subprocess
from typing import TYPE_CHECKING, Any

from . import review_config
from .engine import apply_engine_info_env

if TYPE_CHECKING:
    from collections.abc import Mapping

# ps の comm をエンジン名へ対応付ける。comm は Linux で 15 文字まで切詰められる。
_PROCESS_TO_ENGINE: dict[str, str] = {
    "opencode": "opencode",
    "claude": "claude",
    "agy": "antigravity",
}

# プロセスツリー走査が重くなるのを防ぐための ps タイムアウト。
_PS_TIMEOUT_SECONDS = 3

_PS_REQUIRED_FIELDS = 2


def _process_info(pid: int) -> tuple[int, str] | None:
    try:
        result = subprocess.run(
            ["ps", "-o", "ppid=,comm=", "-p", str(pid)],
            capture_output=True,
            text=True,
            check=False,
            timeout=_PS_TIMEOUT_SECONDS,
            encoding="utf-8",
            errors="replace",
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    # ppid と comm を分離。comm にスペースを含むパス (macOS の "/Applications/My App/...")
    # を保持するため、最初の空白 1 つだけで分割する。
    parts = result.stdout.split(None, 1)
    if len(parts) < _PS_REQUIRED_FIELDS:
        return None
    try:
        comm = pathlib.Path(parts[1].strip()).name.lower()
        return int(parts[0]), comm
    except (ValueError, IndexError):
        return None


def detect_active_engine(start_pid: int | None = None) -> str | None:
    seen: set[int] = set()
    pid = start_pid if start_pid is not None else os.getpid()
    while pid > 1 and pid not in seen:
        seen.add(pid)
        info = _process_info(pid)
        if info is None:
            return None
        ppid, comm = info
        match = _PROCESS_TO_ENGINE.get(comm)
        if match:
            return match
        pid = ppid
    return None


def _str_config(config: Mapping[str, Any], key: str) -> str | None:
    val = config.get(key)
    if val is None:
        return None
    text = str(val).strip()
    return text or None


def _concrete_engine(raw: Any) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip().lower()
    if not text or text == "auto":
        return None
    return text


def _is_auto(raw: Any) -> bool:
    if raw is None:
        return False
    return str(raw).strip().lower() == "auto"


def resolve_engine_settings(
    config: Mapping[str, Any] | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    if config is None:
        config = review_config.load_config()
    if env is None:
        env = dict(os.environ)

    # Issue #126: エンジンは 環境変数 > リポジトリ設定 > グローバル設定 > 自動検出 の順で
    # 解決する。リポジトリの precommit_engine="auto" は「未指定」としてグローバル設定の
    # 具体値を覆わず (従来は検出へ直行し、グローバル由来の precommit_model と分裂した
    # 無効な組み合わせで engine.py へ渡っていた)、どのレイヤにも具体エンジンが無い場合
    # のみプロセスツリー検出へ進む。env の "auto" は最上位レイヤの明示指示として、
    # 下層の具体エンジンを覆って検出する (旧実装と同じ挙動を維持)。
    global_cfg = review_config.load_global_config()
    global_engine = _concrete_engine(
        global_cfg.get("precommit_engine"),
    ) or _concrete_engine(global_cfg.get("engine"))
    env_engine = _concrete_engine(env.get("PRECOMMIT_REVIEW_ENGINE"))
    precommit_engine_conf = _concrete_engine(config.get("precommit_engine"))

    engine: str | None = None
    # env の "auto" は最上位レイヤの明示指示として下層の具体エンジンを覆って検出する。
    # 一方 config の "auto" は「未指定」を意味し、下層 (グローバル設定) の具体値を優先
    # する。この非対称性が Issue #126 の分裂 (repo auto + global model) の対策要件。
    if env_engine is not None:
        engine = env_engine
    elif _is_auto(env.get("PRECOMMIT_REVIEW_ENGINE")):
        engine = detect_active_engine()
    elif precommit_engine_conf is not None:
        engine = precommit_engine_conf
    elif global_engine is not None:
        engine = global_engine
    else:
        engine = detect_active_engine()

    # 検出不能な環境 (プロセスツリーに AI ツールが無い・ps 不可) 向けの既定エンジン。
    if engine is None:
        engine = _concrete_engine(config.get("engine")) or "claude"

    model = env.get("PRECOMMIT_REVIEW_MODEL") or _str_config(
        config,
        "precommit_model",
    )
    # claude は model が必須のため、PR の model 設定をフォールバックする。
    if model is None and engine == "claude":
        model = _str_config(config, "model")

    thinking = (
        env.get("PRECOMMIT_REVIEW_THINKING")
        or _str_config(config, "precommit_thinking")
        or _str_config(config, "thinking")
        # Issue #107: config が空でも reasoning 予算を枯渇させにくい low を既定にする。
        or "low"
    )

    budget = (
        env.get("PRECOMMIT_REVIEW_BUDGET_USD")
        or _str_config(config, "precommit_review_budget_usd")
        or _str_config(config, "review_budget_usd")
    )

    # Issue #40: Gate 1 のエンジン情報表示トグル (既定=表示)。build_env が
    # AME_ENGINE_SHOW_INFO へ変換して子プロセスへ渡す。文字列 "false" にも対応。
    show_info = review_config.config_bool(
        config, "show_engine_info_gate1", default=True
    )

    return {
        "engine": engine,
        "model": model,
        "thinking": thinking,
        "budget": budget,
        "show_info": show_info,
    }


def build_env(
    base_env: Mapping[str, str] | None,
    settings: Mapping[str, Any],
) -> dict[str, str]:
    env = dict(base_env) if base_env is not None else dict(os.environ)
    env["REVIEW_ENGINE"] = str(settings["engine"])
    # None の項目は環境変数を渡さず、stale な既存値があれば掃除する。
    # これにより engine.py が意図せず前回設定を使うのを防ぐ。
    model = settings["model"]
    if model is not None:
        env["REVIEW_MODEL"] = str(model)
    else:
        env.pop("REVIEW_MODEL", None)
    thinking = settings["thinking"]
    if thinking is not None:
        env["REVIEW_THINKING"] = str(thinking)
    else:
        env.pop("REVIEW_THINKING", None)
    budget = settings["budget"]
    if budget is not None:
        env["REVIEW_BUDGET_USD"] = str(budget)
    else:
        env.pop("REVIEW_BUDGET_USD", None)
    # Issue #40: エンジン情報バナー表示フラグ。未指定時は既定で表示 (後方互換)。
    apply_engine_info_env(env, show_info=bool(settings.get("show_info", True)))
    return env
