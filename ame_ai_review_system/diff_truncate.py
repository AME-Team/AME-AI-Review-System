"""Diff truncation utilities (Issue #62).

従来は差分が 4000 行を超えると前方のみを残して切り詰め、後方ファイル
(``index.css`` / ``types/`` / ``views/`` / ``tests/`` 等) がレビュー対象から
完全に消失していた。これにより LLM が「定義が見当たらない」と誤判定し、
MIDDLE/HIGH の誤指摘が連発する問題があった。

本モジュールは以下の戦略でこの問題を緩和する。

strategy="priority" + priority_markers:
  ``priority_markers`` に列挙したヘッダで始まるセクション (例: ステージ済み差分 =
  当該コミットのレビュー対象) を**全行保持**し、残り予算をコンテキストセクション
  (例: ブランチ差分) の**末尾**へ割り当てる。git はパス順に出力するため、末尾に
  配置される後方ファイル (CSS / 型定義 / テスト) が可視になる。
  完全に消失したセクションは本文をトークン化された通知行へ置換し、LLM が
  「見えない」ことと「存在しない」ことを区別できるようにする。

strategy="priority" (markers なし):
  diff 全体を**先頭 + 末尾**で保持する。PR レビューのように優先サブセットが
  無いケースでも後方ファイルを可視化する。末尾長は ``context_floor`` で制御する。

strategy="front":
  従来動作 (前方のみ保持)。脱出ハッチとして残す。

いずれの戦略も、切り詰めで開いたままの ``` フェンスを閉じてプロンプト構造を保つ。
"""

from __future__ import annotations

from typing import Any

_FENCE = "```"

_TRUNCATED_TOTAL_SUFFIX = " (truncated)"


def truncate_diff(
    diff: str,
    *,
    max_lines: int,
    strategy: str = "priority",
    priority_markers: list[str] | None = None,
    context_floor: int = 0,
) -> str:
    """Diff を max_lines 以下へ戦略的に切り詰める.

    既に max_lines 以下の場合は何もしない。それ以外は strategy に従って切り詰め、
    切り詰めを示す注記行を付与する。
    """
    if max_lines <= 0:
        return diff
    lines = diff.splitlines()
    if len(lines) <= max_lines:
        return diff

    markers = [m for m in (priority_markers or []) if m]
    if strategy == "priority" and markers and _has_priority_section(lines, markers):
        kept = _priority_pick(lines, markers, max_lines)
    elif strategy == "priority":
        kept = _head_tail_pick(lines, max_lines, context_floor)
    else:
        kept = _front_pick(lines, max_lines)
    return "\n".join(kept)


# ============================================================================
# 戦略実装
# ============================================================================


def _front_pick(lines: list[str], max_lines: int) -> list[str]:
    """従来動作: 前方 max_lines 行を残す (フェンス補完付き)."""
    kept = list(lines[:max_lines])
    if _fence_parity(kept) == 1:
        kept.append(_FENCE)
    kept.append(f"... (truncated from {len(lines)} to {max_lines} lines)")
    return kept


def _head_tail_pick(
    lines: list[str],
    max_lines: int,
    tail_count: int,
) -> list[str]:
    """先頭 + 末尾を保持し、中間を切り詰める (markers なしの priority 戦略)."""
    safe_tail = max(0, min(tail_count, max_lines - 1))
    head_count = max(1, max_lines - safe_tail)

    head = list(lines[:head_count])
    if _fence_parity(head) == 1:
        head.append(_FENCE)

    tail_start = _advance_to_outside_fence(
        lines, max(head_count, len(lines) - safe_tail)
    )
    tail = list(lines[tail_start:])
    tail = _close_open_fence(tail)

    omitted = max(0, len(lines) - head_count - len(tail))
    if omitted == 0:
        # フェンス整列で尾部が空になった場合は前方のみ返す
        return [
            *head,
            f"... (truncated from {len(lines)} to {max_lines} lines)",
        ]
    note = (
        f"... (truncated, ~{omitted} middle lines omitted; "
        f"{len(lines)} lines total) ..."
    )
    return [*head, note, *tail]


def _priority_pick(
    lines: list[str],
    markers: list[str],
    max_lines: int,
) -> list[str]:
    """優先セクション全行保持 + コンテキスト末尾保持で切り詰める."""
    sections = _split_sections(lines, markers)

    priority_body_len = sum(len(s["body"]) for s in sections if s["is_priority"])
    # 優先セクションが max_lines に収まるなら全行保持し、残りをコンテキスト末尾へ。
    if priority_body_len <= max_lines:
        priority_budget = priority_body_len
        context_budget = max_lines - priority_body_len
    else:
        # 優先セクション自体が溢れる場合は前方から切り詰め、コンテキストは見捨てる。
        priority_budget = max_lines
        context_budget = 0

    kept: list[str] = []
    remaining_priority = priority_budget

    for section in sections:
        if section["is_priority"]:
            kept.extend(
                _emit_priority_section(section, remaining_priority),
            )
            remaining_priority -= min(len(section["body"]), remaining_priority)

    # コンテキストは連結した末尾から予算分だけ残す。後方ファイル (CSS/types/tests)
    # が git のパス順で末尾に来るため、末尾保持がこれらの可視化に直結する。
    context_sections = [s for s in sections if not s["is_priority"]]
    context_total = sum(len(s["body"]) for s in context_sections)
    keep_from = context_total - context_budget

    running = 0
    for section in context_sections:
        body = section["body"]
        start = running
        end = running + len(body)
        running = end
        lo = max(keep_from, start)
        hi = min(context_total, end)
        if lo >= hi:
            kept.extend(_emit_dropped_section(section))
            continue
        kept.extend(_emit_context_tail_section(section, lo - start, hi - start))
    return kept


# ============================================================================
# セクション分割
# ============================================================================


def _split_sections(
    lines: list[str],
    markers: list[str],
) -> list[dict[str, Any]]:
    """``### `` ヘッダでセクション分割し、優先フラグを付ける.

    最初の ``### `` より前の行はヘッダなしのプリアンブルセクション (コンテキスト扱い)。
    """
    sections: list[dict[str, Any]] = []
    header: list[str] = []
    body: list[str] = []
    marker_line = ""

    def flush() -> None:
        if header or body:
            sections.append(
                {
                    "header_lines": list(header),
                    "body": list(body),
                    "marker": marker_line,
                    "is_priority": bool(marker_line)
                    and any(m in marker_line for m in markers),
                },
            )

    for ln in lines:
        if ln.startswith("### "):
            flush()
            header = [ln]
            body = []
            marker_line = ln
        else:
            body.append(ln)
    flush()
    return sections


def _has_priority_section(lines: list[str], markers: list[str]) -> bool:
    return any(section["is_priority"] for section in _split_sections(lines, markers))


# ============================================================================
# セクション出力
# ============================================================================


def _emit_priority_section(
    section: dict[str, Any],
    budget: int,
) -> list[str]:
    body = section["body"]
    if budget <= 0:
        return _emit_dropped_section(section)
    take = min(len(body), budget)
    block = list(body[:take])
    out = [*section["header_lines"]]
    if take < len(body):
        block = _close_open_fence(block)
        out.extend(block)
        out.append(
            f"... (priority section truncated, {len(body) - take} lines omitted) ...",
        )
    else:
        out.extend(_close_open_fence(block))
    return out


def _emit_context_tail_section(
    section: dict[str, Any],
    offset: int,
    end: int,
) -> list[str]:
    body = section["body"]
    block = list(body[offset:end])
    out = [*section["header_lines"]]
    if offset > 0:
        out.append(
            f"... (section head truncated, {offset} lines omitted) ...",
        )
    out.extend(_wrap_partial_diff_block(block))
    if end < len(body):
        out.append(
            f"... (section tail truncated, {len(body) - end} lines omitted) ...",
        )
    return out


def _emit_dropped_section(section: dict[str, Any]) -> list[str]:
    body_len = len(section["body"])
    header = section["header_lines"]
    if not header:
        return [f"... (unnamed section dropped, {body_len} lines omitted) ..."]
    return [
        *header,
        f"... (diff truncated, {body_len} lines omitted in this section) ...",
    ]


# ============================================================================
# フェンス補完
# ============================================================================


def _fence_parity(block: list[str]) -> int:
    return sum(1 for ln in block if ln.startswith(_FENCE)) % 2


def _close_open_fence(block: list[str]) -> list[str]:
    if _fence_parity(block) == 1:
        return [*block, _FENCE]
    return list(block)


def _advance_to_outside_fence(lines: list[str], idx: int) -> int:
    """``idx`` がフェンス内なら、次のフェンス行の直後まで進める."""
    if _fence_parity(lines[:idx]) == 0:
        return idx
    for j in range(idx, len(lines)):
        if lines[j].startswith(_FENCE):
            return j + 1
    return len(lines)


def _wrap_partial_diff_block(block: list[str]) -> list[str]:
    """フェンス境界で切れた diff 断片を綺麗な ```diff ブロックへ包む.

    完全なセクション (先頭がフェンス opener) はそのまま末尾を補完するだけ。
    断片 (opener が無い) は新たに ``diff`` フェンスで囲み、LLM が diff として
    認識できるようにする。
    """
    if not block:
        return []
    if block[0].lstrip().startswith(_FENCE):
        return _close_open_fence(block)
    wrapped = [f"{_FENCE}diff", *block]
    return _close_open_fence(wrapped)
