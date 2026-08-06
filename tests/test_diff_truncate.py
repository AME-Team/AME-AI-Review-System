# pyright: basic
from __future__ import annotations

from ame_ai_review_system.diff_truncate import truncate_diff

_STAGED_HEADER = "### ステージ済み差分"
_BRANCH_HEADER = "### ブランチ差分"
_STAGED_TAG = "STAGED"
_BRANCH_TAG = "BRANCH"


def _section(header: str, tag: str, body_lines: int) -> str:
    body = "\n".join(f"{tag}-line{i}" for i in range(body_lines))
    return f"{header}\n\n```diff\n{body}\n```"


# ============================================================================
# 共通: 切り捨て不要
# ============================================================================


def test_no_truncation_when_under_limit() -> None:
    diff = "\n".join(f"line{i}" for i in range(100))
    assert truncate_diff(diff, max_lines=4000) == diff


def test_no_truncation_at_boundary() -> None:
    diff = "\n".join(f"line{i}" for i in range(4000))
    assert truncate_diff(diff, max_lines=4000) == diff


def test_empty_diff_unchanged() -> None:
    assert not truncate_diff("", max_lines=4000)


def test_max_lines_zero_returns_unchanged() -> None:
    diff = "\n".join(f"line{i}" for i in range(10))
    assert truncate_diff(diff, max_lines=0) == diff


# ============================================================================
# front 戦略 (従来動作)
# ============================================================================


def test_front_strategy_keeps_head_only() -> None:
    diff = "\n".join(f"line{i}" for i in range(5000))
    out = truncate_diff(diff, max_lines=100, strategy="front")
    assert "line0" in out
    assert "line99" in out
    assert "line100" not in out
    assert "line4999" not in out
    assert "truncated from 5000 to 100 lines" in out


def test_front_strategy_closes_open_fence() -> None:
    diff = "```diff\n" + "\n".join(f"line{i}" for i in range(5000))
    out = truncate_diff(diff, max_lines=50, strategy="front")
    assert out.count("```") % 2 == 0


def test_front_strategy_keeps_balanced_fence_unclosed() -> None:
    # 既に閉じたフェンス + 余分行。front で切った後にフェンスが開いたままになら
    # なければ補完しない。ここではフェンスは先頭付近で完結している。
    diff = "```diff\nline1\n```\n" + "\n".join(f"line{i}" for i in range(5000))
    out = truncate_diff(diff, max_lines=10, strategy="front")
    assert out.count("```") % 2 == 0


# ============================================================================
# priority 戦略: markers なし = head + tail
# ============================================================================


def test_priority_no_markers_keeps_head_and_tail() -> None:
    diff = "\n".join(f"line{i}" for i in range(5000))
    out = truncate_diff(diff, max_lines=1000, strategy="priority", context_floor=200)
    assert "line0" in out
    assert "line4999" in out
    # 中間は切り捨てられる
    assert "line2500" not in out
    assert "truncated" in out


def test_priority_no_markers_tail_size_equals_context_floor() -> None:
    diff = "\n".join(f"line{i}" for i in range(5000))
    out = truncate_diff(diff, max_lines=1000, strategy="priority", context_floor=300)
    # 末尾 300 行分が残る (後方ファイル可視化)
    assert "line4700" in out
    assert "line4699" not in out


def test_priority_no_markers_fence_balance() -> None:
    diff = "```diff\n" + "\n".join(f"line{i}" for i in range(5000)) + "\n```"
    out = truncate_diff(diff, max_lines=1000, strategy="priority", context_floor=200)
    assert out.count("```") % 2 == 0


def test_priority_no_markers_clamps_oversized_floor() -> None:
    # context_floor が max_lines を超える場合はクランプされ、head ≥ 1 を残す。
    diff = "\n".join(f"line{i}" for i in range(5000))
    out = truncate_diff(
        diff,
        max_lines=100,
        strategy="priority",
        context_floor=10_000,
    )
    assert "line0" in out
    assert "line4999" in out
    assert "truncated" in out


# ============================================================================
# priority 戦略: markers あり = 優先セクション全行 + コンテキスト末尾
# ============================================================================


def test_priority_markers_keeps_full_priority_section() -> None:
    staged = _section(_STAGED_HEADER, _STAGED_TAG, 50)
    branch = _section(_BRANCH_HEADER, _BRANCH_TAG, 5000)
    diff = f"{staged}\n\n{branch}"
    out = truncate_diff(
        diff,
        max_lines=1000,
        strategy="priority",
        priority_markers=[_STAGED_HEADER],
    )
    # 優先セクションは全行保持
    for i in (0, 25, 49):
        assert f"{_STAGED_TAG}-line{i}" in out
    # コンテキスト末尾 (後方ファイル) も可視
    assert f"{_BRANCH_TAG}-line4999" in out
    # コンテキスト冒頭は切り捨て
    assert f"{_BRANCH_TAG}-line0" not in out
    assert "truncated" in out


def test_priority_markers_drops_no_priority_section_silently() -> None:
    # 該当ヘッダが無ければ markers ありでも head+tail へフォールバック。
    diff = "\n".join(f"line{i}" for i in range(5000))
    out = truncate_diff(
        diff,
        max_lines=1000,
        strategy="priority",
        priority_markers=[_STAGED_HEADER],
        context_floor=200,
    )
    assert "line0" in out
    assert "line4999" in out
    assert "line2500" not in out


def test_priority_markers_truncates_priority_when_it_overflows() -> None:
    # 優先セクション単体で max_lines を超える場合は前方から切り詰め、コンテキストは
    # 完全にドロップされるが、セクションヘッダは残り「切り捨て」注記が付く。
    staged = _section(_STAGED_HEADER, _STAGED_TAG, 5000)
    branch = _section(_BRANCH_HEADER, _BRANCH_TAG, 100)
    diff = f"{staged}\n\n{branch}"
    out = truncate_diff(
        diff,
        max_lines=1000,
        strategy="priority",
        priority_markers=[_STAGED_HEADER],
    )
    assert f"{_STAGED_TAG}-line0" in out
    assert f"{_STAGED_TAG}-line997" in out
    assert f"{_STAGED_TAG}-line998" not in out
    assert f"{_STAGED_TAG}-line4999" not in out
    # ブランチセクションはヘッダ + 切り捨て注記として残る (存在は明示)
    assert _BRANCH_HEADER in out
    assert "truncated" in out


def test_priority_markers_fence_balance_in_kept_blocks() -> None:
    staged = _section(_STAGED_HEADER, _STAGED_TAG, 50)
    branch_body = "\n".join(f"b{i}" for i in range(5000))
    branch = f"{_BRANCH_HEADER}\n\n```diff\n{branch_body}\n```"
    diff = f"{staged}\n\n{branch}"
    out = truncate_diff(
        diff,
        max_lines=1000,
        strategy="priority",
        priority_markers=[_STAGED_HEADER],
    )
    assert out.count("```") % 2 == 0


def test_priority_markers_keeps_small_context_section_fully() -> None:
    # コンテキスト予算内に収まる小さなセクションは末尾保持で実質全行残存する。
    staged = _section(_STAGED_HEADER, _STAGED_TAG, 50)
    branch = _section(_BRANCH_HEADER, _BRANCH_TAG, 200)
    diff = f"{staged}\n\n{branch}"
    out = truncate_diff(
        diff,
        max_lines=1000,
        strategy="priority",
        priority_markers=[_STAGED_HEADER],
    )
    # 全体が 1000 行未満なので切り捨て不要
    assert "truncated" not in out
    assert f"{_BRANCH_TAG}-line0" in out
    assert f"{_BRANCH_TAG}-line199" in out


# ============================================================================
# フェンス整形の詳細
# ============================================================================


def test_partial_context_block_wrapped_in_diff_fence() -> None:
    # コンテキスト末尾がフェンス途中から始まる場合、```diff で包まれて整形される。
    staged = _section(_STAGED_HEADER, _STAGED_TAG, 10)
    # ブランチ部はフェンスを開いたまま大量行を置き、末尾で閉じない構造
    branch_body = "\n".join(f"b{i}" for i in range(5000))
    branch = f"{_BRANCH_HEADER}\n\n```diff\n{branch_body}\n```"
    diff = f"{staged}\n\n{branch}"
    out = truncate_diff(
        diff,
        max_lines=500,
        strategy="priority",
        priority_markers=[_STAGED_HEADER],
    )
    assert out.count("```") % 2 == 0
    # 末尾の後方ファイル行が残っていること
    assert "b4999" in out
