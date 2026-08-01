from __future__ import annotations

from ame_ai_review_system.main import SKIP_NOTICE_MARKER, skip_notice_already_posted

_MARKER = f"{SKIP_NOTICE_MARKER}-pr38"
_ISSUE_URL = "https://api.github.com/repos/tarminjapan/AME-AI-Review-System/issues/38"


def testskip_notice_already_posted_false_when_absent() -> None:
    comments = [{"body": "hello", "issue_url": _ISSUE_URL}]
    assert not skip_notice_already_posted(comments, _MARKER, _ISSUE_URL)


def testskip_notice_already_posted_true_when_present() -> None:
    comments = [
        {"body": f"<!-- {_MARKER} -->", "issue_url": _ISSUE_URL},
    ]
    assert skip_notice_already_posted(comments, _MARKER, _ISSUE_URL)


def testskip_notice_already_posted_ignores_other_prs() -> None:
    other_url = "https://api.github.com/repos/tarminjapan/AME-AI-Review-System/issues/1"
    comments = [
        {"body": f"<!-- {_MARKER} -->", "issue_url": other_url},
    ]
    assert not skip_notice_already_posted(comments, _MARKER, _ISSUE_URL)


def testskip_notice_already_posted_tolerates_trailing_slash() -> None:
    comments = [
        {"body": f"<!-- {_MARKER} -->", "issue_url": _ISSUE_URL + "/"},
    ]
    assert skip_notice_already_posted(comments, _MARKER, _ISSUE_URL)


def testskip_notice_already_posted_ignores_missing_fields() -> None:
    assert not skip_notice_already_posted([{}], _MARKER, _ISSUE_URL)
