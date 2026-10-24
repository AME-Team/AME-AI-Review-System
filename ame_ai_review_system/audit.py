"""導入先リポジトリの参照ドリフトを 1 コマンドで監査する (Issue #164).

サービス化 (Issue #147) 以降、導入先は 2 系統の参照を持つ。Gate 2 は reusable workflow を
移動メジャータグ (``@v0``) で参照するため作業ゼロで追随する。Gate 1 は供給チェーン保護の
ため ``#sha256=`` 固定を維持しており、リリースごとに ``ame-ai-reviewer sync`` が要る。
どちらがどれだけ遅れているかを 6 リポジトリ分目視で確認していたため、GitHub API 越しに
列挙して 1 コマンドで差分を出す。

読み取り専用である。書き換えは ``sync`` の役割であり、ここでは行わない。仮想環境へ wheel を
直接入れる導入先 (git 管理下に参照が無い構成) は、この API 監査では版を確認できない
(``.venv`` は git 管理外)。その場合は「参照なし」として報告し、ローカルの
``sync --check`` で検査するよう促す。
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any, cast

from . import config_sync, github_client, init_cmd

if TYPE_CHECKING:
    import argparse

# 導入先のラッパは ``init`` が生成するこの 2 ファイルで、どちらも reusable workflow を
# 移動メジャータグで参照する。
_WORKFLOW_FILES = ("review_command.yml", "review_reply.yml")
_CONTENTS_API = "https://api.github.com/repos/{repo}/contents/{path}"
_REPO_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
# ``checks:`` は Gate 2 (Circuit Breaker) がリポジトリ自身の CI を見るために要る権限。
_CHECKS_READ_RE = re.compile(r"^\s*checks:\s*read\s*$", re.MULTILINE)
# 行頭の ``uses:`` だけを対象にする。コメントアウトされた旧参照 (``# uses: ...@v0.2.13``)
# を拾うと、移行済みのリポジトリをドリフトと誤判定する。値の引用符と、``@ref`` の後ろに
# 空白なしで続くコメント (``@v0#foo``) も吸収する。
_WORKFLOW_REF_RE = re.compile(
    rf"^[ \t]*uses:[ \t]*[\"']?{re.escape(init_cmd.repo_fqn())}/\.github/workflows/"
    r"[A-Za-z0-9._-]+\.yml@(?P<ref>[^\s\"'#]+)[\"']?",
    re.MULTILINE,
)

# ``contents`` API はファイルが無いとき 404 を返す。それ以外の HTTP エラーは判定不能。
_HTTP_NOT_FOUND = 404
# リポジトリ自体を読めない場合 (未認証の private / 名前の誤り) は、ファイルが無いのとは
# 区別する。混同すると「ラッパがありません」= 参照ドリフトと誤判定する。
_HTTP_FORBIDDEN = 403
_REPO_API = "https://api.github.com/repos/{repo}"

_EXIT_DRIFT = 1
_EXIT_UNRESOLVED = 2


class _UnreadableFileError(RuntimeError):
    """``contents`` API からファイル本文を取り出せなかった (存在はする).

    「ファイルが無い」(404) と区別する。混同すると、取得できなかっただけのリポジトリを
    「ラッパがありません」= 参照ドリフトとして報告してしまう。
    """


class CheckStatus(StrEnum):
    """1 つの検査項目の結果."""

    OK = "ok"
    DRIFT = "drift"
    # git 管理下に参照が無い (仮想環境へ直接入れる構成)。API からは版を確認できない。
    NOT_TRACKED = "not-tracked"
    # 取得・解決に失敗して判定できなかった。
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Finding:
    """1 つの検査項目の結果 (``detail`` は人向けの説明)."""

    check: str
    status: CheckStatus
    detail: str = ""


@dataclass(frozen=True)
class RepoAudit:
    """1 リポジトリ分の監査結果."""

    repo: str
    findings: tuple[Finding, ...] = field(default_factory=tuple)

    @property
    def status(self) -> CheckStatus:
        """リポジトリ全体の判定 (drift > unknown > ok の順に悪い方を採る)."""
        statuses = {finding.status for finding in self.findings}
        if CheckStatus.DRIFT in statuses:
            return CheckStatus.DRIFT
        if CheckStatus.UNKNOWN in statuses:
            return CheckStatus.UNKNOWN
        return CheckStatus.OK


def _repo_access(repo: str, token: str) -> Finding | None:
    """リポジトリ自体を読めるかを確認する (読めなければ ``UNKNOWN`` の Finding).

    ``contents`` API の 404 は「ファイルが無い」と「リポジトリに到達できない」の両方を
    意味する。後者を「ラッパがありません」= 参照ドリフトとして扱うと、監査していない
    リポジトリを drift と報告してしまう。
    """
    try:
        github_client.http_request("GET", _REPO_API.format(repo=repo), token)
    except github_client.HttpError as exc:
        if exc.status_code in {_HTTP_FORBIDDEN, _HTTP_NOT_FOUND}:
            return Finding(
                "repo",
                CheckStatus.UNKNOWN,
                f"リポジトリを読めません (HTTP {exc.status_code})",
            )
        raise
    return None


def _fetch_file(repo: str, path: str, token: str) -> str | None:
    """``contents`` API でファイル本文を取り出す (存在しなければ ``None``).

    ``HttpError`` のうち 404 だけを「ファイルが無い」として扱う。それ以外 (403/500 等) は
    判定不能なので呼び出し側へ伝える。
    """
    url = _CONTENTS_API.format(repo=repo, path=path)
    try:
        payload: Any = github_client.http_request("GET", url, token)
    except github_client.HttpError as exc:
        if exc.status_code == _HTTP_NOT_FOUND:
            return None
        raise
    if not isinstance(payload, dict):
        message = f"unexpected contents payload: {path}"
        raise _UnreadableFileError(message)
    data = cast("dict[str, Any]", payload)
    content = data.get("content")
    if data.get("encoding") != "base64" or not isinstance(content, str):
        # 大きいファイルは ``encoding: none`` で返る (本文が入っていない)。
        message = f"contents is not base64: {path}"
        raise _UnreadableFileError(message)
    try:
        return base64.b64decode(content).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        message = f"cannot decode contents: {path}"
        raise _UnreadableFileError(message) from exc


def _workflow_findings(repo: str, token: str) -> list[Finding]:
    """Gate 2 のラッパ 2 件を検査する (移動メジャータグ参照と ``checks: read``)."""
    expected = init_cmd.DEFAULT_REF
    findings: list[Finding] = []
    for filename in _WORKFLOW_FILES:
        text = _fetch_file(repo, f".github/workflows/{filename}", token)
        check = f"gate2:{filename}"
        if text is None:
            findings.append(
                Finding(check, CheckStatus.DRIFT, "ラッパがありません (未移行の可能性)")
            )
            continue
        # グループが増えても壊れないよう、名前付きグループで明示的に取り出す。
        refs = [
            match.group("ref").strip("'\"")
            for match in re.finditer(_WORKFLOW_REF_RE, text)
        ]
        # 期待値が 1 つあれば良いのではない。同じファイルに古い固定参照が残っている
        # (両方が使われている) 場合も移行漏れなので、すべてが期待値であることを要求する。
        if not refs or any(ref != expected for ref in refs):
            findings.append(
                Finding(
                    check,
                    CheckStatus.DRIFT,
                    f"参照が {', '.join(refs) or '不明'} です (期待値 {expected})",
                )
            )
            continue
        if filename == "review_command.yml" and not _CHECKS_READ_RE.search(text):
            # checks: read が無いと Circuit Breaker が外部 CI を見られない。
            findings.append(
                Finding(
                    check,
                    CheckStatus.DRIFT,
                    "permissions に checks: read がありません",
                )
            )
            continue
        findings.append(Finding(check, CheckStatus.OK, f"{expected} 参照"))
    return findings


def _gate1_finding(repo: str, token: str, *, latest: str | None) -> Finding:
    """Gate 1 の wheel 参照の版を検査する (pre-commit / pyproject の両方を見る).

    移行途中のリポジトリは両方に参照を持つ。片方だけ見て return すると、もう片方の古い
    参照を見逃すため、見つかった参照をすべて突き合わせて結果をまとめる。
    """
    check = "gate1:wheel"
    found: list[tuple[str, tuple[str, ...]]] = []
    for path, extract in (
        (".pre-commit-config.yaml", config_sync.precommit_pins),
        ("pyproject.toml", config_sync.pyproject_pins),
    ):
        text = _fetch_file(repo, path, token)
        if text is None:
            continue
        pins = extract(text)
        if pins:
            found.append((path, pins))
    if not found:
        return Finding(
            check,
            CheckStatus.NOT_TRACKED,
            "git 管理下に wheel 参照がありません (ローカルの `sync --check` で検査)",
        )
    if latest is None:
        listed = ", ".join(f"{path} の {', '.join(pins)}" for path, pins in found)
        return Finding(check, CheckStatus.UNKNOWN, f"{listed} (最新版を解決できません)")
    target = config_sync.version_order(latest)
    if target is None:
        return Finding(
            check, CheckStatus.UNKNOWN, f"最新リリース v{latest} の版を解釈できません"
        )
    behind: list[str] = []
    unorderable: list[str] = []
    ahead: list[str] = []
    for path, pins in found:
        for pin in pins:
            order = config_sync.version_order(pin)
            if order is None:
                unorderable.append(f"{path} の v{pin}")
            elif order < target:
                behind.append(f"{path} の v{pin}")
            elif order > target:
                ahead.append(f"{path} の v{pin}")
    if behind:
        # 確定したドリフトは UNKNOWN より優先する。解釈できない参照が 1 つあるだけで
        # 更新すべき参照の通知を落とさない。
        return Finding(
            check,
            CheckStatus.DRIFT,
            f"{', '.join(behind)} → v{latest} へ更新できます",
        )
    if unorderable:
        # prerelease 等は「古い」とも「同じ」とも言えないため追随済みと断定しない。
        return Finding(
            check,
            CheckStatus.UNKNOWN,
            f"{', '.join(unorderable)} の版を解釈できません (最新 v{latest})",
        )
    if ahead:
        # ``sync`` の AHEAD と同じ扱い (意図的な新しい固定は書き換え対象外)。
        return Finding(
            check,
            CheckStatus.OK,
            f"固定版が最新 (v{latest}) より新しいため対象外: {', '.join(ahead)}",
        )
    return Finding(
        check, CheckStatus.OK, f"v{latest} ({', '.join(path for path, _ in found)})"
    )


def audit_repo(repo: str, *, token: str, latest: str | None) -> RepoAudit:
    """1 リポジトリを監査する (ネットワーク失敗は ``UNKNOWN`` へ落とす)."""
    findings: list[Finding] = []
    try:
        blocked = _repo_access(repo, token)
        if blocked is not None:
            return RepoAudit(repo, (blocked,))
        findings.extend(_workflow_findings(repo, token))
        findings.append(_gate1_finding(repo, token, latest=latest))
    except github_client.HttpError as exc:
        return RepoAudit(
            repo,
            (
                Finding(
                    "api",
                    CheckStatus.UNKNOWN,
                    f"GitHub API を読めません (HTTP {exc.status_code})",
                ),
            ),
        )
    except (OSError, ValueError, _UnreadableFileError) as exc:
        return RepoAudit(
            repo, (Finding("api", CheckStatus.UNKNOWN, f"取得に失敗: {exc}"),)
        )
    return RepoAudit(repo, tuple(findings))


def resolve_repos(repos: list[str] | None) -> list[str]:
    """監査対象の ``owner/name`` を解決する (``--repo`` → 環境変数).

    ``--repo`` の値もカンマ区切りを受ける。明示指定がある場合は環境変数を無視する
    (ローカルに ``AME_AUDIT_REPOS`` が残っていても、指定した対象だけを見る)。
    重複は出現順で落とす。形式の検証は ``cmd_audit`` 側で行う。
    """
    explicit = [
        name.strip()
        for chunk in repos or []
        for name in chunk.split(",")
        if name.strip()
    ]
    if explicit:
        return list(dict.fromkeys(explicit))
    raw = (os.environ.get("AME_AUDIT_REPOS") or "").split(",")
    seen: dict[str, None] = {}
    for item in raw:
        name = item.strip()
        if name:
            seen.setdefault(name, None)
    return list(seen)


def cmd_audit(args: argparse.Namespace) -> int:
    """``ame-ai-reviewer audit`` のエントリポイント (Issue #164).

    導入先の Gate 1 / Gate 2 の参照を GitHub API で列挙し、期待値との差分を出す。
    終了コードは ``sync --check`` と同じ (drift = 1 / 判定不能 = 2)。
    """
    repos = resolve_repos(cast("list[str] | None", getattr(args, "repo", None)))
    invalid = [repo for repo in repos if not _REPO_NAME_RE.match(repo)]
    if invalid:
        print(
            "[audit] リポジトリ名が不正です (owner/name 形式で指定してください): "
            f"{', '.join(invalid)}",
            file=sys.stderr,
        )
        return _EXIT_UNRESOLVED
    if not repos:
        print(
            "[audit] 対象がありません。`--repo owner/name` か環境変数 "
            "AME_AUDIT_REPOS を指定してください。",
            file=sys.stderr,
        )
        return _EXIT_UNRESOLVED
    token = config_sync.optional_token()
    latest = config_sync.latest_release(config_sync.target_major())
    target = latest[0] if latest is not None else None
    audits = [audit_repo(repo, token=token, latest=target) for repo in repos]
    if getattr(args, "json", False):
        print(
            json.dumps(
                [_as_dict(audit) for audit in audits], ensure_ascii=False, indent=2
            )
        )
    else:
        for audit in audits:
            _report(audit)
    statuses = {audit.status for audit in audits}
    if CheckStatus.DRIFT in statuses:
        return _EXIT_DRIFT
    if CheckStatus.UNKNOWN in statuses:
        return _EXIT_UNRESOLVED
    return 0


def _report(audit: RepoAudit) -> None:
    """1 リポジトリ分の監査結果を表示する."""
    print(f"[audit] {audit.repo}: {audit.status}")
    for finding in audit.findings:
        if finding.status is CheckStatus.OK:
            print(f"[audit]   {finding.check}: ok ({finding.detail})")
            continue
        if finding.status is CheckStatus.NOT_TRACKED:
            # 失敗ではない (API からは確認できないだけ)。理由付きで見せる。
            print(f"[audit]   {finding.check}: 対象外 ({finding.detail})")
            continue
        print(
            f"[audit]   {finding.check}: {finding.status} — {finding.detail}",
            file=sys.stderr,
        )


def _as_dict(audit: RepoAudit) -> dict[str, Any]:
    """監査結果を JSON 用の辞書にする."""
    return {
        "repo": audit.repo,
        "status": str(audit.status),
        "checks": [
            {
                "name": finding.check,
                "status": str(finding.status),
                "detail": finding.detail,
            }
            for finding in audit.findings
        ],
    }
