"""``audit`` の検証 (Issue #164).

導入先 6 リポジトリの参照を GitHub API 越しに列挙する監査を検証する。HTTP は
``github_client.http_request`` をフェイクして差し替え、実ネットワークに依存させない。
"""

from __future__ import annotations

import argparse
import base64
import json

import pytest
from ame_ai_review_system import audit, config_sync, github_client, init_cmd

_DIGEST = "b" * 64
_LATEST = "0.2.20"
_LATEST_RELEASE = (_LATEST, _DIGEST)


def _contents(text: str) -> dict[str, object]:
    """``contents`` API の応答を模す."""
    return {
        "encoding": "base64",
        "content": base64.b64encode(text.encode("utf-8")).decode("ascii"),
    }


def _wrapper(ref: str, *, checks_read: bool = True) -> str:
    permissions = "permissions:\n  contents: read\n"
    if checks_read:
        permissions += "  checks: read\n"
    return f"name: x\n{permissions}jobs:\n  r:\n    uses: {init_cmd.repo_fqn()}/.github/workflows/review-command.yml@{ref}\n"


def _precommit(version: str) -> str:
    return (
        "repos:\n"
        "  - repo: local\n"
        "    hooks:\n"
        "      - id: ai-precommit-review\n"
        "        additional_dependencies:\n"
        f"          - ame_ai_review_system @ {init_cmd.wheel_url(version)}#sha256={_DIGEST}\n"
    )


def _patch_files(monkeypatch: pytest.MonkeyPatch, files: dict[str, str]) -> list[str]:
    """``contents`` API を ``files`` (path -> 本文) で差し替え、要求パスを記録する."""
    requests: list[str] = []

    def _fake(
        method: str,
        url: str,
        token: str,
        body: object = None,
        accept: str = "application/vnd.github+json",
    ) -> object:
        assert method == "GET"
        if "/contents/" not in url:
            # リポジトリ到達性の確認 (``GET /repos/{repo}``)。
            return {"full_name": "AME-Team/demo"}
        prefix = "https://api.github.com/repos/AME-Team/demo/contents/"
        path = url.removeprefix(prefix)
        requests.append(path)
        if path not in files:
            message = f"not found: {path}"
            raise github_client.HttpError(404, message)
        return _contents(files[path])

    monkeypatch.setattr(github_client, "http_request", _fake)
    return requests


def _check(repo_audit: audit.RepoAudit, name: str) -> audit.Finding:
    for finding in repo_audit.findings:
        if finding.check == name:
            return finding
    message = f"no finding named {name}"
    raise AssertionError(message)


def test_audit_repo_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_files(
        monkeypatch,
        {
            ".github/workflows/review_command.yml": _wrapper(init_cmd.DEFAULT_REF),
            ".github/workflows/review_reply.yml": _wrapper(init_cmd.DEFAULT_REF),
            ".pre-commit-config.yaml": _precommit(_LATEST),
        },
    )
    result = audit.audit_repo("AME-Team/demo", token="", latest=_LATEST_RELEASE)
    assert result.status is audit.CheckStatus.OK
    assert {finding.status for finding in result.findings} == {audit.CheckStatus.OK}


def test_audit_repo_detects_stale_workflow_ref(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 版固定のままのラッパは移行漏れ。移動メジャータグ参照を期待する。
    _patch_files(
        monkeypatch,
        {
            ".github/workflows/review_command.yml": _wrapper("v0.2.13"),
            ".github/workflows/review_reply.yml": _wrapper(init_cmd.DEFAULT_REF),
            ".pre-commit-config.yaml": _precommit(_LATEST),
        },
    )
    result = audit.audit_repo("AME-Team/demo", token="", latest=_LATEST_RELEASE)
    assert result.status is audit.CheckStatus.DRIFT
    finding = _check(result, "gate2:review_command.yml")
    assert finding.status is audit.CheckStatus.DRIFT
    assert "v0.2.13" in finding.detail


def test_audit_repo_ignores_trailing_comment_in_ref(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # ``@v0#foo`` のようにコメントが空白なしで続いても参照は v0 として読む。
    wrapper = _wrapper(init_cmd.DEFAULT_REF).replace(
        f"@{init_cmd.DEFAULT_REF}", f"@{init_cmd.DEFAULT_REF}#foo"
    )
    _patch_files(
        monkeypatch,
        {
            ".github/workflows/review_command.yml": wrapper,
            ".github/workflows/review_reply.yml": _wrapper(init_cmd.DEFAULT_REF),
            ".pre-commit-config.yaml": _precommit(_LATEST),
        },
    )
    result = audit.audit_repo("AME-Team/demo", token="", latest=_LATEST_RELEASE)
    assert result.status is audit.CheckStatus.OK


def test_audit_repo_detects_missing_checks_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # checks: read が無いと Circuit Breaker が外部 CI を見られない。
    _patch_files(
        monkeypatch,
        {
            ".github/workflows/review_command.yml": _wrapper(
                init_cmd.DEFAULT_REF, checks_read=False
            ),
            ".github/workflows/review_reply.yml": _wrapper(init_cmd.DEFAULT_REF),
            ".pre-commit-config.yaml": _precommit(_LATEST),
        },
    )
    result = audit.audit_repo("AME-Team/demo", token="", latest=_LATEST_RELEASE)
    assert result.status is audit.CheckStatus.DRIFT
    assert "checks: read" in _check(result, "gate2:review_command.yml").detail


def test_audit_repo_detects_behind_wheel(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_files(
        monkeypatch,
        {
            ".github/workflows/review_command.yml": _wrapper(init_cmd.DEFAULT_REF),
            ".github/workflows/review_reply.yml": _wrapper(init_cmd.DEFAULT_REF),
            ".pre-commit-config.yaml": _precommit("0.2.16"),
        },
    )
    result = audit.audit_repo("AME-Team/demo", token="", latest=_LATEST_RELEASE)
    assert result.status is audit.CheckStatus.DRIFT
    assert "0.2.16" in _check(result, "gate1:wheel").detail


def test_audit_repo_reads_pyproject_pin(monkeypatch: pytest.MonkeyPatch) -> None:
    # language: system 構成は pyproject.toml に参照を持つ。
    _patch_files(
        monkeypatch,
        {
            ".github/workflows/review_command.yml": _wrapper(init_cmd.DEFAULT_REF),
            ".github/workflows/review_reply.yml": _wrapper(init_cmd.DEFAULT_REF),
            "pyproject.toml": (
                "[project]\ndependencies = [\n"
                f'  "ame-ai-review-system @ {init_cmd.wheel_url("0.2.16")}",\n]\n'
            ),
        },
    )
    result = audit.audit_repo("AME-Team/demo", token="", latest=_LATEST_RELEASE)
    assert _check(result, "gate1:wheel").status is audit.CheckStatus.DRIFT


def test_audit_repo_checks_both_managed_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 移行途中は pre-commit と pyproject の両方に参照がある。片方だけ見て return すると
    # もう片方の古い参照を見逃す。
    _patch_files(
        monkeypatch,
        {
            ".github/workflows/review_command.yml": _wrapper(init_cmd.DEFAULT_REF),
            ".github/workflows/review_reply.yml": _wrapper(init_cmd.DEFAULT_REF),
            ".pre-commit-config.yaml": _precommit(_LATEST),
            "pyproject.toml": (
                "[project]\ndependencies = [\n"
                f'  "ame-ai-review-system @ {init_cmd.wheel_url("0.2.16")}",\n]\n'
            ),
        },
    )
    result = audit.audit_repo("AME-Team/demo", token="", latest=_LATEST_RELEASE)
    finding = _check(result, "gate1:wheel")
    assert finding.status is audit.CheckStatus.DRIFT
    assert "pyproject.toml" in finding.detail


def test_audit_repo_reports_unreadable_file_as_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # contents API は大きいファイルで encoding: none を返す。取得できなかっただけなのに
    # 「ラッパがありません」= ドリフトとして報告しない。
    def _fake(
        method: str,
        url: str,
        token: str,
        body: object = None,
        accept: str = "application/vnd.github+json",
    ) -> object:
        assert method == "GET"
        if "/contents/" not in url:
            return {"full_name": "AME-Team/demo"}
        return {"encoding": "none", "content": ""}

    monkeypatch.setattr(github_client, "http_request", _fake)
    result = audit.audit_repo("AME-Team/demo", token="", latest=_LATEST_RELEASE)
    assert result.status is audit.CheckStatus.UNKNOWN
    # 取得できなかったファイルは「ラッパがありません」(DRIFT) ではなく判定不能。
    assert _check(result, "gate2:review_command.yml").status is (
        audit.CheckStatus.UNKNOWN
    )


def test_audit_repo_detects_mixed_refs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 同じファイルに @v0 と古い固定参照が併存する場合も移行漏れ。
    wrapper = _wrapper(init_cmd.DEFAULT_REF) + (
        "  old:\n"
        f"    uses: {init_cmd.repo_fqn()}/.github/workflows/review-command.yml@v0.2.13\n"
    )
    _patch_files(
        monkeypatch,
        {
            ".github/workflows/review_command.yml": wrapper,
            ".github/workflows/review_reply.yml": _wrapper(init_cmd.DEFAULT_REF),
            ".pre-commit-config.yaml": _precommit(_LATEST),
        },
    )
    result = audit.audit_repo("AME-Team/demo", token="", latest=_LATEST_RELEASE)
    assert result.status is audit.CheckStatus.DRIFT
    assert "v0.2.13" in _check(result, "gate2:review_command.yml").detail


def test_audit_repo_reports_unorderable_pin_as_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # prerelease の固定は「追随済み」と断定できない。
    _patch_files(
        monkeypatch,
        {
            ".github/workflows/review_command.yml": _wrapper(init_cmd.DEFAULT_REF),
            ".github/workflows/review_reply.yml": _wrapper(init_cmd.DEFAULT_REF),
            ".pre-commit-config.yaml": _precommit("0.3.0rc1"),
        },
    )
    result = audit.audit_repo("AME-Team/demo", token="", latest=_LATEST_RELEASE)
    assert result.status is audit.CheckStatus.UNKNOWN
    assert _check(result, "gate1:wheel").status is audit.CheckStatus.UNKNOWN


def test_audit_repo_treats_ahead_pin_as_ok(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 固定版が最新より新しい場合は sync と同じく対象外 (書き換えない)。
    _patch_files(
        monkeypatch,
        {
            ".github/workflows/review_command.yml": _wrapper(init_cmd.DEFAULT_REF),
            ".github/workflows/review_reply.yml": _wrapper(init_cmd.DEFAULT_REF),
            ".pre-commit-config.yaml": _precommit("0.2.21"),
        },
    )
    result = audit.audit_repo("AME-Team/demo", token="", latest=_LATEST_RELEASE)
    finding = _check(result, "gate1:wheel")
    assert finding.status is audit.CheckStatus.OK
    assert "対象外" in finding.detail


def test_audit_repo_ignores_commented_out_ref(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # コメントアウトされた旧参照を拾うと、移行済みのリポジトリをドリフトと誤判定する。
    wrapper = _wrapper(init_cmd.DEFAULT_REF).replace(
        "jobs:",
        f"# uses: {init_cmd.repo_fqn()}/.github/workflows/review-command.yml@v0.2.13\njobs:",
    )
    _patch_files(
        monkeypatch,
        {
            ".github/workflows/review_command.yml": wrapper,
            ".github/workflows/review_reply.yml": _wrapper(init_cmd.DEFAULT_REF),
            ".pre-commit-config.yaml": _precommit(_LATEST),
        },
    )
    result = audit.audit_repo("AME-Team/demo", token="", latest=_LATEST_RELEASE)
    assert result.status is audit.CheckStatus.OK


def test_audit_repo_accepts_quoted_ref(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # YAML では値の引用符が有効。引用されていても参照として読む。
    wrapper = (
        _wrapper(init_cmd.DEFAULT_REF)
        .replace(f"@{init_cmd.DEFAULT_REF}", f'@{init_cmd.DEFAULT_REF}"')
        .replace("uses: ", 'uses: "')
    )
    _patch_files(
        monkeypatch,
        {
            ".github/workflows/review_command.yml": wrapper,
            ".github/workflows/review_reply.yml": _wrapper(init_cmd.DEFAULT_REF),
            ".pre-commit-config.yaml": _precommit(_LATEST),
        },
    )
    result = audit.audit_repo("AME-Team/demo", token="", latest=_LATEST_RELEASE)
    assert result.status is audit.CheckStatus.OK


def test_audit_repo_prefers_confirmed_drift_over_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 解釈できない参照が 1 つあっても、確定した古い参照の通知は落とさない。
    _patch_files(
        monkeypatch,
        {
            ".github/workflows/review_command.yml": _wrapper(init_cmd.DEFAULT_REF),
            ".github/workflows/review_reply.yml": _wrapper(init_cmd.DEFAULT_REF),
            ".pre-commit-config.yaml": _precommit("0.2.16"),
            "pyproject.toml": (
                "[project]\ndependencies = [\n"
                f'  "ame-ai-review-system @ {init_cmd.wheel_url("0.3.0rc1")}",\n]\n'
            ),
        },
    )
    result = audit.audit_repo("AME-Team/demo", token="", latest=_LATEST_RELEASE)
    finding = _check(result, "gate1:wheel")
    assert finding.status is audit.CheckStatus.DRIFT
    assert "0.2.16" in finding.detail


def test_audit_repo_detects_stale_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 版が最新でも sha256 が違えば内容が違う (古い固定 / 改ざん)。sync --check は
    # テキスト完全一致で判定するため、監査も digest を見る。
    stale = "c" * 64
    text = _precommit(_LATEST).replace(_DIGEST, stale)
    _patch_files(
        monkeypatch,
        {
            ".github/workflows/review_command.yml": _wrapper(init_cmd.DEFAULT_REF),
            ".github/workflows/review_reply.yml": _wrapper(init_cmd.DEFAULT_REF),
            ".pre-commit-config.yaml": text,
        },
    )
    result = audit.audit_repo("AME-Team/demo", token="", latest=_LATEST_RELEASE)
    finding = _check(result, "gate1:wheel")
    assert finding.status is audit.CheckStatus.DRIFT
    assert "sha256" in finding.detail


def test_audit_repo_isolates_parse_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 取得だけでなくパース時の例外も、その検査の UNKNOWN に落として監査を続ける。
    def _extract(_text: str) -> tuple[config_sync.Reference, ...]:
        message = "broken"
        raise ValueError(message)

    monkeypatch.setattr(config_sync, "precommit_references", _extract)
    _patch_files(
        monkeypatch,
        {
            ".github/workflows/review_command.yml": _wrapper(init_cmd.DEFAULT_REF),
            ".github/workflows/review_reply.yml": _wrapper(init_cmd.DEFAULT_REF),
            ".pre-commit-config.yaml": _precommit(_LATEST),
        },
    )
    result = audit.audit_repo("AME-Team/demo", token="", latest=_LATEST_RELEASE)
    assert result.status is audit.CheckStatus.UNKNOWN
    assert _check(result, "gate1:wheel").status is audit.CheckStatus.UNKNOWN
    # Gate 2 の検査結果は失われない。
    assert _check(result, "gate2:review_command.yml").status is audit.CheckStatus.OK


def test_audit_repo_reports_untracked_wheel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 仮想環境へ直接入れる構成は API から版を確認できない。失敗ではなく「対象外」。
    _patch_files(
        monkeypatch,
        {
            ".github/workflows/review_command.yml": _wrapper(init_cmd.DEFAULT_REF),
            ".github/workflows/review_reply.yml": _wrapper(init_cmd.DEFAULT_REF),
        },
    )
    result = audit.audit_repo("AME-Team/demo", token="", latest=_LATEST_RELEASE)
    assert result.status is audit.CheckStatus.OK
    assert _check(result, "gate1:wheel").status is audit.CheckStatus.NOT_TRACKED


def test_audit_repo_reports_missing_wrapper(monkeypatch: pytest.MonkeyPatch) -> None:
    # ラッパが無い = 未導入。移行漏れとして drift にする。
    _patch_files(
        monkeypatch,
        {".pre-commit-config.yaml": _precommit(_LATEST)},
    )
    result = audit.audit_repo("AME-Team/demo", token="", latest=_LATEST_RELEASE)
    assert result.status is audit.CheckStatus.DRIFT
    assert "ありません" in _check(result, "gate2:review_command.yml").detail


def test_audit_repo_reports_unreachable_repository(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # private / 名前の誤りは contents API も 404 になる。「ラッパがありません」=
    # 参照ドリフトではなく「判定不能」として扱う。
    def _fake(
        method: str,
        url: str,
        token: str,
        body: object = None,
        accept: str = "application/vnd.github+json",
    ) -> object:
        assert method == "GET"
        message = "not found"
        raise github_client.HttpError(404, message)

    monkeypatch.setattr(github_client, "http_request", _fake)
    result = audit.audit_repo("AME-Team/demo", token="", latest=_LATEST_RELEASE)
    assert result.status is audit.CheckStatus.UNKNOWN
    assert "読めません" in _check(result, "repo").detail


def test_audit_repo_reports_api_error(monkeypatch: pytest.MonkeyPatch) -> None:
    # 403/500 は「参照が古い」ではなく「判定不能」。
    def _boom(*_args: object, **_kwargs: object) -> object:
        message = "boom"
        raise github_client.HttpError(500, message)

    monkeypatch.setattr(github_client, "http_request", _boom)
    result = audit.audit_repo("AME-Team/demo", token="", latest=_LATEST_RELEASE)
    assert result.status is audit.CheckStatus.UNKNOWN
    assert _check(result, "repo").status is audit.CheckStatus.UNKNOWN


def test_resolve_repos_dedupes_and_splits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 明示指定があるときは環境変数を無視する (ローカルの設定で対象が増えない)。
    monkeypatch.setenv("AME_AUDIT_REPOS", "AME-Team/c, AME-Team/a")
    repos = audit.resolve_repos(["AME-Team/a,AME-Team/b", "AME-Team/a"])
    assert repos == ["AME-Team/a", "AME-Team/b"]


def test_resolve_repos_falls_back_to_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AME_AUDIT_REPOS", "AME-Team/c, AME-Team/a")
    assert audit.resolve_repos(None) == ["AME-Team/c", "AME-Team/a"]


def _args(**kwargs: object) -> argparse.Namespace:
    base: dict[str, object] = {"repo": ["AME-Team/demo"], "json": False}
    base.update(kwargs)
    return argparse.Namespace(**base)


def _patch_latest(monkeypatch: pytest.MonkeyPatch, version: str | None) -> None:
    def _latest(_major: str, *, timeout: int | None = None) -> tuple[str, str] | None:
        return (version, _DIGEST) if version is not None else None

    monkeypatch.setattr(config_sync, "latest_release", _latest)


def test_cmd_audit_exit_codes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_latest(monkeypatch, _LATEST)
    files = {
        ".github/workflows/review_command.yml": _wrapper(init_cmd.DEFAULT_REF),
        ".github/workflows/review_reply.yml": _wrapper(init_cmd.DEFAULT_REF),
        ".pre-commit-config.yaml": _precommit(_LATEST),
    }
    _patch_files(monkeypatch, files)
    assert audit.cmd_audit(_args()) == 0
    assert "ok" in capsys.readouterr().out

    files[".pre-commit-config.yaml"] = _precommit("0.2.16")
    assert audit.cmd_audit(_args()) == 1
    assert "gate1:wheel" in capsys.readouterr().err


def test_cmd_audit_treats_unresolved_release_as_unknown(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # 最新版を解決できないだけで「参照が古い」と断定しない。
    _patch_latest(monkeypatch, None)
    _patch_files(
        monkeypatch,
        {
            ".github/workflows/review_command.yml": _wrapper(init_cmd.DEFAULT_REF),
            ".github/workflows/review_reply.yml": _wrapper(init_cmd.DEFAULT_REF),
            ".pre-commit-config.yaml": _precommit("0.2.16"),
        },
    )
    assert audit.cmd_audit(_args()) == 2
    assert "最新版を解決できません" in capsys.readouterr().err


def test_cmd_audit_json_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_latest(monkeypatch, _LATEST)
    _patch_files(
        monkeypatch,
        {
            ".github/workflows/review_command.yml": _wrapper(init_cmd.DEFAULT_REF),
            ".github/workflows/review_reply.yml": _wrapper(init_cmd.DEFAULT_REF),
            ".pre-commit-config.yaml": _precommit(_LATEST),
        },
    )
    assert audit.cmd_audit(_args(json=True)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["repo"] == "AME-Team/demo"
    assert payload[0]["status"] == "ok"
    assert {check["name"] for check in payload[0]["checks"]} == {
        "gate2:review_command.yml",
        "gate2:review_reply.yml",
        "gate1:wheel",
    }


def test_cmd_audit_rejects_invalid_repo_name(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # 不正な値を黙って捨てると、監査したつもりで 1 件も見ていない状態になる。
    _patch_latest(monkeypatch, _LATEST)
    assert audit.cmd_audit(_args(repo=["not-a-repo"])) == 2
    assert "不正" in capsys.readouterr().err


def test_cmd_audit_requires_a_target(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_latest(monkeypatch, _LATEST)
    monkeypatch.delenv("AME_AUDIT_REPOS", raising=False)
    assert audit.cmd_audit(_args(repo=[])) == 2
    assert "対象がありません" in capsys.readouterr().err
