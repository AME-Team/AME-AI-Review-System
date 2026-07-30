"""OpenCode SDK (TypeScript) サイドカーアダプタ。."""

from __future__ import annotations

from typing import Any

from . import ts_runner

_OPENCODE_VARIANT: dict[str, str] = {
    "low": "minimal",
    "medium": "medium",
    "high": "high",
}


class OpencodeTsAdapter:
    """バンドル ``engines/ts/opencode.mjs`` 経由で ``@opencode-ai/sdk`` を呼ぶアダプタ。."""

    @staticmethod
    def run(prompt: str, settings: dict[str, Any]) -> str:
        """プロンプトを opencode.mjs サイドカーへ渡し、結果テキストを返す。."""
        variant = _OPENCODE_VARIANT.get(str(settings["thinking"]), "high")
        args: list[str] = ["--variant", variant]
        if settings.get("model"):
            args.extend(["--model", str(settings["model"])])
        return ts_runner.run_sidecar(
            "opencode.mjs", prompt, args, float(settings["timeout"])
        )
