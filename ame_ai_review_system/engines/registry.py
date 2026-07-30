"""エンジンアダプタのレジストリ。."""

from __future__ import annotations

from typing import Any

ENGINES: tuple[str, ...] = ("claude", "opencode", "antigravity")
SDK_LANGS: tuple[str, ...] = ("python", "typescript")

# Claude は Python/TypeScript SDK、Antigravity は Python SDK、OpenCode は CLI のみ。
# OpenCode は SDK 言語を持たないため空タプルとする。
_ENGINE_SDK_LANG: dict[str, tuple[str, ...]] = {
    "claude": ("python", "typescript"),
    "opencode": (),
    "antigravity": ("python",),
}


def available_sdk_langs(engine: str) -> tuple[str, ...]:
    """エンジンがサポートする SDK 言語の一覧を返す(CLI エンジンは空)。."""
    return _ENGINE_SDK_LANG.get(engine, ())


def is_cli_engine(engine: str) -> bool:
    """CLI サブプロセスで動くエンジン(opencode)か。."""
    return engine == "opencode"


def get_adapter(engine: str, sdk_lang: str | None = None) -> Any:
    """エンジンと SDK 言語から適切なアダプタインスタンスを返す(遅延 import)。."""
    if engine not in ENGINES:
        choices = ", ".join(ENGINES)
        msg = f"Unknown engine: {engine!r}. Choose from: {choices}"
        raise ValueError(msg)

    if engine == "opencode":
        from .opencode_cli import OpencodeCliAdapter

        return OpencodeCliAdapter()

    available = available_sdk_langs(engine)
    lang = (sdk_lang or available[0]).lower()
    if lang not in available:
        msg = (
            f"sdk_lang {lang!r} not available for engine {engine!r}. "
            f"Available: {', '.join(available)}"
        )
        raise ValueError(msg)

    if engine == "claude":
        if lang == "typescript":
            from .claude_ts import ClaudeTsAdapter

            return ClaudeTsAdapter()
        from .claude_python import ClaudePythonAdapter

        return ClaudePythonAdapter()
    from .antigravity import AntigravityAdapter

    return AntigravityAdapter()
