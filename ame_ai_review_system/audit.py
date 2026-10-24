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
# ``permissions`` の書き方は YAML のブロック記法とフロー記法、``read-all`` / ``write-all``
# の短縮形がある。``checks: write`` は read を含む上位権限なので許容する。
_PERMISSIONS_RE = re.compile(r"^(?P<indent>\s*)permissions:\s*(?P<rest>.*)$")
# ``run: |`` などのブロックスカラーは中身が YAML ではないため、その範囲を読み飛ばす。
# chomping indicator (``-``/``+``) と明示インデント (``|2``, ``>2-``) は任意順で付く。
_BLOCK_SCALAR_RE = re.compile(r":\s*[|>][-+\d]*\s*$")
_CHECKS_ENTRY_RE = re.compile(r"^\s*checks:\s*(?P<value>\S+)\s*$")
_CHECKS_VALUES = frozenset({"read", "write"})
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


def _fetch_error(check: str, exc: BaseException) -> Finding:
    """取得失敗を ``UNKNOWN`` の Finding にする."""
    if isinstance(exc, github_client.HttpError):
        return Finding(
            check,
            CheckStatus.UNKNOWN,
            f"GitHub API を読めません (HTTP {exc.status_code})",
        )
    return Finding(check, CheckStatus.UNKNOWN, f"取得に失敗: {exc}")


def _strip_comment(line: str) -> str:
    """行末コメントを落とす (``#`` の直前が空白のときだけ。URL の ``#`` は残す)."""
    for index, char in enumerate(line):
        if char == "#" and (index == 0 or line[index - 1] in " \t"):
            return line[:index]
    return line


def _significant_lines(lines: list[str]) -> list[str | None]:
    """ブロックスカラー (``run: |``) の内側を ``None`` にした一覧 (行番号は保つ).

    内側は YAML ではないため、``permissions:`` や ``uses:`` を本物の宣言として読んでは
    いけない。
    """
    result: list[str | None] = []
    scalar_indent: int | None = None
    for raw in lines:
        line = _strip_comment(raw)
        indent = len(line) - len(line.lstrip())
        if scalar_indent is not None:
            if not line.strip() or indent > scalar_indent:
                result.append(None)
                continue
            scalar_indent = None
        result.append(line)
        if _BLOCK_SCALAR_RE.search(line):
            scalar_indent = indent
    return result


def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip())


def _flow_permissions_have_checks(
    lines: list[str | None], start: int, rest: str
) -> bool:
    """フロー記法 (``permissions: {...}``) に ``checks: read|write`` があるか."""
    collected = [rest]
    for raw in lines[start + 1 :]:
        if raw is None:
            continue
        collected.append(raw)
        if "}" in raw:
            break
    body = " ".join(collected)
    opened = body.find("{")
    if opened < 0:
        return False
    closed = body.find("}", opened)
    body = body[opened + 1 : closed] if closed >= 0 else body[opened + 1 :]
    for entry in body.split(","):
        key, _, value = entry.partition(":")
        if key.strip().strip("'\"") == "checks" and value.strip().strip("'\"") in (
            _CHECKS_VALUES
        ):
            return True
    return False


def _block_permissions_have_checks(
    lines: list[str | None], start: int, indent: int
) -> bool:
    """ブロック記法の ``permissions:`` 配下に ``checks: read|write`` があるか."""
    for raw in lines[start + 1 :]:
        if raw is None or not raw.strip():
            continue
        if _indent_of(raw) <= indent:
            # permissions ブロックの終わり (同レベル以上のキーが来た)。
            return False
        match = _CHECKS_ENTRY_RE.match(raw)
        # YAML では値の引用符が有効 (``checks: "read"``) なので、比較前に落とす。
        if match is not None and match.group("value").strip("'\"") in _CHECKS_VALUES:
            return True
    return False


def _grant_at(lines: list[str | None], index: int, indent: int) -> bool:
    """``permissions:`` の行が checks を許可しているか."""
    line = lines[index]
    match = _PERMISSIONS_RE.match(line) if line is not None else None
    if match is None:
        return False
    rest = match.group("rest").strip().strip("'\"")
    if rest in {"read-all", "write-all"}:
        # 全権限の短縮形は checks も含む。
        return True
    if rest.startswith("{"):
        return _flow_permissions_have_checks(lines, index, rest)
    return _block_permissions_have_checks(lines, index, indent)


def _job_grant(lines: list[str | None], index: int, indent: int) -> bool | None:
    """ラッパを呼ぶジョブの ``permissions:`` を評価する (無ければ ``None``).

    ジョブレベルの ``permissions`` はトップレベルをマージせず丸ごと上書きするため、
    ラッパを呼ぶジョブに宣言があればそちらが正になる。
    """
    start = index
    while start > 0:
        previous = lines[start - 1]
        if previous is not None and previous.strip() and _indent_of(previous) < indent:
            break
        start -= 1
    end = index + 1
    while end < len(lines):
        line = lines[end]
        if line is not None and line.strip() and _indent_of(line) < indent:
            break
        end += 1
    for position in range(start, end):
        candidate = lines[position]
        if candidate is None or not candidate.strip():
            continue
        if _indent_of(candidate) != indent:
            continue
        if _PERMISSIONS_RE.match(candidate) is not None:
            return _grant_at(lines, position, indent)
    return None


def _has_checks_permission(text: str) -> bool:
    """Gate 2 が外部 CI を見るための ``checks`` 権限があるか.

    PyYAML を依存に加えない方針 (既定は依存ゼロ) のため、``permissions`` と ``uses``
    だけを読む最小のパーサで判定する。コメント行・行末コメントとブロックスカラーの内側は
    無視し、``checks: read-only`` のような別の値を権限と誤認しない。ラッパを呼ぶジョブに
    ジョブレベルの ``permissions`` があればそれを優先し、無ければトップレベルを見る。
    """
    lines = _significant_lines(text.splitlines())
    top: bool | None = None
    for index, line in enumerate(lines):
        if line is None or _indent_of(line) != 0:
            continue
        if _PERMISSIONS_RE.match(line) is not None:
            top = _grant_at(lines, index, 0)
            break
    usages = [
        (index, _indent_of(line))
        for index, line in enumerate(lines)
        if line is not None and _WORKFLOW_REF_RE.match(line) is not None
    ]
    if not usages:
        # ラッパの参照が無い場合は、呼び出し側が「参照が不明」として DRIFT にする。
        return top is True
    for index, indent in usages:
        job = _job_grant(lines, index, indent)
        effective = top if job is None else job
        if effective is not True:
            return False
    return True


def _workflow_findings(repo: str, token: str) -> list[Finding]:
    """Gate 2 のラッパ 2 件を検査する (移動メジャータグ参照と ``checks: read``)."""
    expected = init_cmd.DEFAULT_REF
    findings: list[Finding] = []
    for filename in _WORKFLOW_FILES:
        check = f"gate2:{filename}"
        try:
            text = _fetch_file(repo, f".github/workflows/{filename}", token)
        except (
            github_client.HttpError,
            OSError,
            ValueError,
            _UnreadableFileError,
        ) as exc:
            # 1 ファイルの失敗で、他の検査で確定した結果を捨てない。
            findings.append(_fetch_error(check, exc))
            continue
        if text is None:
            findings.append(
                Finding(check, CheckStatus.DRIFT, "ラッパがありません (未移行の可能性)")
            )
            continue
        # 参照の抽出も ``_significant_lines`` を通す。ブロックスカラー (``run: |``) の
        # 内側に書かれただけの ``uses:`` を参照と誤認しないため (checks 判定と揃える)。
        refs = [
            match.group("ref").strip("'\"")
            for line in _significant_lines(text.splitlines())
            if line is not None and (match := _WORKFLOW_REF_RE.match(line)) is not None
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
        if filename == "review_command.yml" and not _has_checks_permission(text):
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


def _gate1_finding(repo: str, token: str, *, latest: tuple[str, str] | None) -> Finding:
    """Gate 1 の wheel 参照を検査する (pre-commit / pyproject の両方を見る).

    移行途中のリポジトリは両方に参照を持つ。片方だけ見て return すると、もう片方の古い
    参照を見逃すため、見つかった参照をすべて突き合わせて結果をまとめる。バージョンが
    最新でも ``sha256`` が最新リリースと違えば壊れた参照なので、digest も検証する。
    """
    check = "gate1:wheel"
    found: list[tuple[str, tuple[config_sync.Reference, ...]]] = []
    failures: list[Finding] = []
    for path, extract in (
        (".pre-commit-config.yaml", config_sync.precommit_references),
        ("pyproject.toml", config_sync.pyproject_references),
    ):
        try:
            text = _fetch_file(repo, path, token)
        except (
            github_client.HttpError,
            OSError,
            ValueError,
            _UnreadableFileError,
        ) as exc:
            # 片方の取得失敗で、もう片方の参照評価 (特に DRIFT) を失わない。
            failures.append(_fetch_error(check, exc))
            continue
        if text is None:
            continue
        references = extract(text)
        if references:
            found.append((path, references))
    if not found:
        if failures:
            return failures[0]
        return Finding(
            check,
            CheckStatus.NOT_TRACKED,
            "git 管理下に wheel 参照がありません (ローカルの `sync --check` で検査)",
        )
    if latest is None:
        listed = ", ".join(
            f"{path} の {', '.join(f'v{ref.version}' for ref in references)}"
            for path, references in found
        )
        return Finding(check, CheckStatus.UNKNOWN, f"{listed} (最新版を解決できません)")
    latest_version, latest_digest = latest
    target = config_sync.version_order(latest_version)
    if target is None:
        return Finding(
            check,
            CheckStatus.UNKNOWN,
            f"最新リリース v{latest_version} の版を解釈できません",
        )
    behind: list[str] = []
    stale_digest: list[str] = []
    unorderable: list[str] = []
    ahead: list[str] = []
    for path, references in found:
        for reference in references:
            version = reference.version
            order = config_sync.version_order(version) if version else None
            if order is None:
                unorderable.append(f"{path} の v{version or '不明'}")
            elif order < target:
                behind.append(f"{path} の v{version}")
            elif order > target:
                ahead.append(f"{path} の v{version}")
            elif reference.digest is not None and reference.digest != latest_digest:
                # 同じ版でも digest が違えば内容が違う (改ざん・古い固定)。
                stale_digest.append(f"{path} の v{version}")
    if behind:
        return Finding(
            check,
            CheckStatus.DRIFT,
            f"{', '.join(behind)} → v{latest_version} へ更新できます",
        )
    if stale_digest:
        return Finding(
            check,
            CheckStatus.DRIFT,
            f"{', '.join(stale_digest)} の sha256 が最新リリース "
            f"(v{latest_version}) と一致しません",
        )
    if unorderable:
        # prerelease 等は「古い」とも「同じ」とも言えないため追随済みと断定しない。
        return Finding(
            check,
            CheckStatus.UNKNOWN,
            f"{', '.join(unorderable)} の版を解釈できません (最新 v{latest_version})",
        )
    if failures:
        # 読めた参照は問題ないが、もう片方のファイルを確認できていない。追随済みと
        # 断定せず判定不能にする (ahead でも同じ。読めない側に DRIFT が隠れ得る)。
        return failures[0]
    if ahead:
        # ``sync`` の AHEAD と同じ扱い (意図的な新しい固定は書き換え対象外)。
        return Finding(
            check,
            CheckStatus.OK,
            f"固定版が最新 (v{latest_version}) より新しいため対象外: "
            f"{', '.join(ahead)}",
        )
    return Finding(
        check,
        CheckStatus.OK,
        f"v{latest_version} ({', '.join(path for path, _ in found)})",
    )


def audit_repo(repo: str, *, token: str, latest: tuple[str, str] | None) -> RepoAudit:
    """1 リポジトリを監査する (検査ごとに失敗を隔離し、確定した結果は残す)."""
    try:
        blocked = _repo_access(repo, token)
    except (github_client.HttpError, OSError, ValueError) as exc:
        return RepoAudit(repo, (_fetch_error("repo", exc),))
    if blocked is not None:
        return RepoAudit(repo, (blocked,))
    findings: list[Finding] = []
    try:
        findings.extend(_workflow_findings(repo, token))
    except (github_client.HttpError, OSError, ValueError) as exc:
        # 取得だけでなくパース時の例外も、その検査の UNKNOWN に落として残りを続ける。
        findings.append(_fetch_error("gate2", exc))
    try:
        findings.append(_gate1_finding(repo, token, latest=latest))
    except (github_client.HttpError, OSError, ValueError) as exc:
        findings.append(_fetch_error("gate1:wheel", exc))
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
    audits = [audit_repo(repo, token=token, latest=latest) for repo in repos]
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
