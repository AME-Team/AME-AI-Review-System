# pyright: basic
from __future__ import annotations

from typing import Any

import pytest
from ame_ai_review_system import main
from ame_ai_review_system.main import SKIP_NOTICE_MARKER, skip_notice_already_posted

_MARKER = f"{SKIP_NOTICE_MARKER}-pr38"
_ISSUE_URL = "https://api.github.com/repos/tarminjapan/AME-AI-Review-System/issues/38"


def test_skip_notice_already_posted_false_when_absent() -> None:
    comments = [{"body": "hello", "issue_url": _ISSUE_URL}]
    assert not skip_notice_already_posted(comments, _MARKER, _ISSUE_URL)


def test_skip_notice_already_posted_true_when_present() -> None:
    comments = [
        {"body": f"<!-- {_MARKER} -->", "issue_url": _ISSUE_URL},
    ]
    assert skip_notice_already_posted(comments, _MARKER, _ISSUE_URL)


def test_skip_notice_already_posted_ignores_other_prs() -> None:
    other_url = "https://api.github.com/repos/tarminjapan/AME-AI-Review-System/issues/1"
    comments = [
        {"body": f"<!-- {_MARKER} -->", "issue_url": other_url},
    ]
    assert not skip_notice_already_posted(comments, _MARKER, _ISSUE_URL)


def test_skip_notice_already_posted_tolerates_trailing_slash() -> None:
    comments = [
        {"body": f"<!-- {_MARKER} -->", "issue_url": _ISSUE_URL + "/"},
    ]
    assert skip_notice_already_posted(comments, _MARKER, _ISSUE_URL)


def test_skip_notice_already_posted_ignores_missing_fields() -> None:
    assert not skip_notice_already_posted([{}], _MARKER, _ISSUE_URL)


# --- engine info injection sentinel (Issue #40) -----------------------------


def test_run_engine_capture_injects_show_info_by_default(
    capture_engine_env: dict[str, Any],
) -> None:
    # 哨戒テスト: 既定では Gate2 の表示フラグを必ず子プロセスへ注入する (Issue #40)。
    main._run_engine_capture({}, "PROMPT")
    assert capture_engine_env["env"].get("AME_ENGINE_SHOW_INFO") == "1"


def test_run_engine_capture_omits_show_info_when_false(
    capture_engine_env: dict[str, Any],
) -> None:
    main._run_engine_capture({}, "PROMPT", show_info=False)
    assert capture_engine_env["env"].get("AME_ENGINE_SHOW_INFO") == "0"
