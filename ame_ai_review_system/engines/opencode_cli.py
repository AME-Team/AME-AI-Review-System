# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false
"""OpenCode CLI (``opencode run``) サブプロセスアダプタ.

OpenCode SDK はサーバ起動型で CI の都度起動すると認証/ポート管理が煩雑になるため、
OpenCode は CLI サブプロセス経由(1プロセス完結)とする。Claude/Antigravity は SDK 直駆動する。
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from typing import Any

_OPENCODE_VARIANT: dict[str, str] = {
    "low": "minimal",
    "medium": "medium",
    "high": "high",
}


class OpencodeCliAdapter:
    """``opencode run --format json`` を呼び、NDJSON の text イベントを結合して返す。."""

    @staticmethod
    def run(prompt: str, settings: dict[str, Any]) -> str:
        """Opencode CLI を実行し、text イベントを結合した出力を返します."""
        binary = shutil.which("opencode")
        if not binary:
            msg = (
                "[engine] opencode CLI not found on PATH. "
                "Install opencode-ai (npm install -g opencode-ai)."
            )
            raise SystemExit(msg)
        variant = _OPENCODE_VARIANT.get(str(settings["thinking"]), "high")
        args = [binary, "run", "--variant", variant, "--format", "json", "--auto"]
        if settings.get("model"):
            args.extend(["-m", str(settings["model"])])
        timeout = float(settings.get("timeout", 600.0))
        try:
            proc = subprocess.run(
                args,
                input=prompt,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            msg = f"[engine] opencode timed out after {timeout:.0f}s"
            raise SystemExit(msg) from exc

        if proc.stderr:
            sys.stderr.write(proc.stderr)
        if proc.returncode != 0:
            msg = f"[engine] opencode exited with code {proc.returncode}."
            raise SystemExit(msg)

        output = _extract_text(proc.stdout)
        if not output.strip():
            msg = (
                "[engine] opencode produced no text output "
                '(expected NDJSON with {"type":"text"} events).'
            )
            raise SystemExit(msg)
        return output


def _extract_text(raw: str) -> str:
    collected: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        text = _event_text(event)
        if text:
            collected.append(text)
    return "".join(collected)


def _event_text(event: dict[str, object]) -> str | None:
    # OpenCode の --format json は SDK と同じイベントプロトコルを出力するが、
    # ラップ形式(data.part / part / 直置き)がバージョンで異なるため複数形に対応する。
    if event.get("type") != "text":
        return None
    for container in ("data", "part"):
        node = event.get(container)
        if isinstance(node, dict):
            part = node.get("part", node)
            if isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str):
                    return text
    text = event.get("text")
    if isinstance(text, str):
        return text
    return None
