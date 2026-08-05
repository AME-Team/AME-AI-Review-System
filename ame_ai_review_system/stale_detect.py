"""Stale-loop 検出 (同一指摘の繰り返し) の共通実装.

返信判定 (reply.py) と pre-commit / PR streak の escape 判定で共用する。
文字トリグラムの Jaccard 類似度で「直近 2 件のコメント本文が実質同じ」を検出する。
日本語テキストに対応するため単語分割ではなくトリグラムを使用する (Issue #55 B2)。
"""

from __future__ import annotations

_TRIGRAM_SIZE = 3
_STALE_JACCARD_THRESHOLD = 0.80
_STALE_MIN_NGRAMS = 4
_MIN_COMMENTS_FOR_STALE = 2


def trigrams(text: str) -> set[str]:
    """本文から文字トリグラム集合を抽出する."""
    text = text.lower().strip()
    if len(text) < _TRIGRAM_SIZE:
        return {text} if text else set()
    return {text[i : i + _TRIGRAM_SIZE] for i in range(len(text) - (_TRIGRAM_SIZE - 1))}


def is_stale_loop(comment_bodies: list[str]) -> bool:
    """直近 2 件の本文が同一指摘の繰り返しか判定する.

    トリグラム数が 4 未満の短いコメントは完全一致で判定する。
    """
    if len(comment_bodies) < _MIN_COMMENTS_FOR_STALE:
        return False

    g1 = trigrams(comment_bodies[-2])
    g2 = trigrams(comment_bodies[-1])

    if not g1 or not g2:
        return False

    if len(g1) < _STALE_MIN_NGRAMS or len(g2) < _STALE_MIN_NGRAMS:
        return g1 == g2

    jaccard = len(g1 & g2) / len(g1 | g2)
    return jaccard >= _STALE_JACCARD_THRESHOLD
