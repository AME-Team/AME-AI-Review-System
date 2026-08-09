"""Stale-loop 検出 (同一指摘の繰り返し) の共通実装.

返信判定 (reply.py) と pre-commit / PR streak の escape 判定で共用する。
文字トリグラムの Jaccard 類似度で「直近 2 件のコメント本文が実質同じ」を検出する。
日本語テキストに対応するため単語分割ではなくトリグラムを使用する (Issue #55 B2)。
"""

from __future__ import annotations

import re
from typing import Any

from . import review_config

_TRIGRAM_SIZE = 3
_STALE_MIN_NGRAMS = 4
_MIN_COMMENTS_FOR_STALE = 2


def trigrams(text: str) -> set[str]:
    """本文から文字トリグラム集合を抽出する."""
    text = text.lower().strip()
    if len(text) < _TRIGRAM_SIZE:
        return {text} if text else set()
    return {text[i : i + _TRIGRAM_SIZE] for i in range(len(text) - (_TRIGRAM_SIZE - 1))}


def is_stale_loop(
    comment_bodies: list[str],
    *,
    threshold: float | None = None,
) -> bool:
    """直近 2 件の本文が同一指摘の繰り返しか判定する.

    トリグラム数が 4 未満の短いコメントは完全一致で判定する。
    ``threshold`` で Jaccard しきい値を上書きできる (Issue #67)。
    """
    if len(comment_bodies) < _MIN_COMMENTS_FOR_STALE:
        return False

    g1 = trigrams(comment_bodies[-2])
    g2 = trigrams(comment_bodies[-1])

    if not g1 or not g2:
        return False

    if len(g1) < _STALE_MIN_NGRAMS or len(g2) < _STALE_MIN_NGRAMS:
        return g1 == g2

    cutoff = threshold if threshold is not None else review_config.stale_threshold()
    jaccard = len(g1 & g2) / len(g1 | g2)
    return jaccard >= cutoff


def comment_text(comment: dict[str, Any]) -> str:
    """コメント 1 件の stale-loop 判定用本文を合成する.

    severity は MIDDLE → LOW → MIDDLE と揺れるため比較対象から除外する
    (Issue #55 B2)。

    Issue #67: 指摘の安定識別子である ``path`` / ``line`` / ``title`` を
    ``[path|line|title]`` ヘッダとして先頭に付与し、続けて本文 (body) を保持する。
    同一箇所への再投稿はヘッダで確実に検出しつつ、全文類似度 (同一指摘の再投稿) の
    判定にも使える。ヘッダが実質的に空 (path も title も無い) の場合は本文のみ返す。
    """
    path = str(comment.get("path", "")).strip()
    # キーが欠如している場合と値が null の場合を同一表現 ("") に正規化する。
    line_value = comment.get("line")
    line = "" if line_value is None else str(line_value)
    title = str(comment.get("title", "")).strip()
    body = str(comment.get("body", ""))
    if path or title:
        return f"[{path}|{line}|{title}]\n{body}"
    return body


_ANCHOR_RE = re.compile(r"^\[(.*?)\]")


def _anchor_of(text: str) -> str | None:
    """``comment_text`` 出力からアンカー (path|line|title) を抽出する.

    旧形式 (アンカーなし) の保存済み本文は ``None`` を返し、アンカー一致判定の
    対象外とする。
    """
    m = _ANCHOR_RE.match(text)
    return m.group(1) if m else None


def demote_stale(
    comments: list[dict[str, Any]],
    prev_comment_texts: list[str],
    *,
    threshold: float | None = None,
) -> list[dict[str, Any]]:
    """前回レビューと同一のコメントのみを LOW へ降格する.

    LLM が同じ指摘を MIDDLE → LOW → MIDDLE と severity を揺らすと LOW-only streak が
    進まないため、コメント単位の Jaccard stale-loop 検出で繰り返し指摘だけを LOW 扱いに
    落として escape を機能させる (Issue #55 B2)。

    降格条件は以下の 2 経路の OR (Issue #67):
      1. 全文 Jaccard がしきい値以上 (同一本文の再投稿) → severity 不問で降格。
      2. アンカー (path|line|title) が一致し、かつ severity が LOW/MIDDLE 等の降格
         許容対象 → HIGH/CRITICAL の過降格 (同一箇所へ再発した別種の重大指摘) を防ぐ。

    レビュー全体ではなくコメント単位で突き合わせることで、繰り返し指摘の中に紛れた
    新規の CRITICAL/HIGH 指摘を誤って降格しない。escape 条件自体は変更しない。
    ``threshold`` で Jaccard しきい値を上書きできる (Issue #67)。
    """
    if not prev_comment_texts:
        return comments
    prev_texts = [p for p in prev_comment_texts if p.strip()]
    if not prev_texts:
        return comments
    result: list[dict[str, Any]] = []
    for comment in comments:
        current = comment_text(comment)
        if current.strip() and _matches_any_prev(
            current,
            comment,
            prev_texts,
            threshold=threshold,
        ):
            result.append({**comment, "severity": "LOW"})
            continue
        result.append(comment)
    return result


def _matches_any_prev(
    current: str,
    comment: dict[str, Any],
    prev_texts: list[str],
    *,
    threshold: float | None,
) -> bool:
    """前回のいずれかの本文と ``current`` が stale 関係にあるかを判定する."""
    current_anchor = _anchor_of(current)
    for prev in prev_texts:
        if is_stale_loop([prev, current], threshold=threshold):
            return True
        if (
            current_anchor
            and _anchor_of(prev) == current_anchor
            and _is_demotable(comment)
        ):
            return True
    return False


_DEMOTABLE_SEVERITIES = frozenset({"LOW", "MIDDLE", "WARNING", "INFO"})


def _is_demotable(comment: dict[str, Any]) -> bool:
    """Stale 判定による降格を許容する severity かを返す (HIGH/CRITICAL は除外)."""
    severity = str(comment.get("severity", "")).upper().strip()
    return severity in _DEMOTABLE_SEVERITIES
