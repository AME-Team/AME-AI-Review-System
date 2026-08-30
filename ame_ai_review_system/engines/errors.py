"""エンジンアダプタ共通の例外定義。."""

from __future__ import annotations


class FatalEngineError(Exception):
    """エンジンの起動・接続など、回復不能な致命的エラー.

    アダプタ固有の例外はこれを継承する。engine.py が基底で捕捉し、明示メッセージで
    子プロセスを終了させる (Issue #113)。``except Exception`` でも捕捉できる。
    """
