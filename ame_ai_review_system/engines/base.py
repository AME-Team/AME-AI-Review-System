"""エンジンアダプタの共通例外。."""

from __future__ import annotations


class EngineError(Exception):
    """SDK 呼び出し失敗など、エンジン層の回復不能エラー。."""
