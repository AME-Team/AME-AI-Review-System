"""``config_sync`` の検証 (サービス化 Phase 2・Issue #147).

配布先の ``.pre-commit-config.yaml`` にある wheel 参照を hub の最新リリースへ
追随させる仕組みを検証する。書き換え対象を絞ること・fail-open であること・
テキスト完全一致で判定することを固定する。HTTP は ``urlopen`` をフェイクして
差し替え、実ネットワークに依存させない。
"""

from __future__ import annotations

import argparse
import http.client
import importlib.metadata
import json
import shutil
import stat
import subprocess
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from ame_ai_review_system import config_sync, init_cmd, paths

if TYPE_CHECKING:
    from typing import Self

_DIGEST = "b" * 64
_OLD_DIGEST = "a" * 64


def _line(version: str, digest: str, *, indent: str = "          ") -> str:
    return f"{indent}- ame_ai_review_system @ {init_cmd.wheel_url(version)}#sha256={digest}"


def _config_text(version: str, digest: str) -> str:
    return (
        "repos:\n"
        "  - repo: local\n"
        "    hooks:\n"
        "      - id: ai-precommit-review\n"
        "        entry: python -m ame_ai_review_system.precommit_review\n"
        "        language: python\n"
        "        additional_dependencies:\n"
        f"{_line(version, digest)}\n"
        "          - claude-agent-sdk\n"
        "      - id: tsc\n"
        "        entry: ./node_modules/.bin/tsc --noEmit\n"
        "        language: system\n"
    )


class _FakeResponse:
    """``urlopen`` の戻り値を最小限で模す."""

    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def _release(
    tag: str,
    *,
    digest: str | None = _DIGEST,
    prerelease: bool = False,
    draft: bool = False,
) -> dict[str, object]:
    version = tag.removeprefix("v")
    asset: dict[str, object] = {
        "name": f"ame_ai_review_system-{version}-py3-none-any.whl",
    }
    if digest is not None:
        asset["digest"] = f"sha256:{digest}"
    release: dict[str, object] = {"tag_name": tag, "assets": [asset]}
    if prerelease:
        release["prerelease"] = True
    if draft:
        release["draft"] = True
    return release


def _patch_releases(
    monkeypatch: pytest.MonkeyPatch,
    payload: object,
    requests: list[str] | None = None,
    headers: list[dict[str, str]] | None = None,
) -> None:
    """リリース一覧 API の応答を差し替える (``requests``/``headers`` で要求内容を記録する)."""
    body = json.dumps(payload).encode("utf-8")

    def _fake_urlopen(
        url: object, _data: bytes | None = None, *, timeout: float | None = None
    ) -> _FakeResponse:
        if requests is not None:
            # Request オブジェクトの repr では URL が分からないので full_url を記録する。
            requests.append(str(getattr(url, "full_url", url)))
        if headers is not None:
            headers.append({
                k.lower(): v for k, v in getattr(url, "headers", {}).items()
            })
        return _FakeResponse(body)

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)


def _patch_offline(
    monkeypatch: pytest.MonkeyPatch, requests: list[str] | None = None
) -> None:
    """ネットワーク不可を再現する (``requests`` を渡すと試行回数を数える)."""

    def _boom(
        url: object, _data: bytes | None = None, *, timeout: float | None = None
    ) -> _FakeResponse:
        if requests is not None:
            requests.append(str(getattr(url, "full_url", url)))
        message = "offline"
        raise OSError(message)

    monkeypatch.setattr(urllib.request, "urlopen", _boom)


def _forbid_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """呼ばれたら失敗させる (ネットワーク無しで完結すべき経路の検証用)."""

    def _unexpected(
        _url: object, _data: bytes | None = None, *, timeout: float | None = None
    ) -> _FakeResponse:
        message = "この経路で API を引いてはいけない"
        pytest.fail(message)

    monkeypatch.setattr(urllib.request, "urlopen", _unexpected)


def _patch_cache_dir(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    """解決結果キャッシュを一時ディレクトリへ逃がす (実ホームを汚さない)."""

    def _dir() -> Path:
        return root / "config"

    monkeypatch.setattr(paths, "global_config_dir", _dir)


def _patch_project_root(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    """``paths.project_root`` を検証用ディレクトリへ差し替える."""

    def _root() -> Path:
        return root

    monkeypatch.setattr(paths, "project_root", _root)


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / ".pre-commit-config.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_inspect_targets_latest_in_the_installed_series(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # 別メジャー (v1.x) と sha256 を解決できないリリースは候補にしない。
    # 除外しないと配布先が意図しないメジャーへ飛ぶ / 内容固定が崩れる。
    _patch_releases(
        monkeypatch,
        [
            _release("v0.2.16", digest=None),
            _release("v0.2.15"),
            _release("v0.2.14"),
            _release("v1.0.0"),
        ],
    )
    result = config_sync.inspect(_write(tmp_path, _config_text("0.2.14", _DIGEST)))
    assert result.status is config_sync.SyncStatus.DRIFT
    assert result.target_version == "0.2.15"
    assert result.pinned_versions == ("0.2.14",)


def test_inspect_skips_prerelease_and_draft_releases(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # pre-release チェック付きの素のタグ (v0.2.16) と draft は配布対象ではない。
    # 除外しないと、配布先が prerelease へ黙って追随する。
    _patch_releases(
        monkeypatch,
        [
            _release("v0.2.17", draft=True),
            _release("v0.2.16", prerelease=True),
            _release("v0.2.15"),
            _release("v0.2.14"),
        ],
    )
    result = config_sync.inspect(_write(tmp_path, _config_text("0.2.14", _DIGEST)))
    assert result.status is config_sync.SyncStatus.DRIFT
    assert result.target_version == "0.2.15"


def test_inspect_does_not_downgrade_newer_pin(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # 固定版が解決結果より新しい場合は書き換えない。黙ってダウングレードしないため。
    _patch_releases(monkeypatch, [_release("v0.2.15")])
    text = _config_text("0.2.16", _DIGEST)
    path = _write(tmp_path, text)
    result = config_sync.inspect(path)
    # 「参照行が無い (ABSENT)」とは区別する。無言で見逃さないため。
    assert result.status is config_sync.SyncStatus.AHEAD
    assert result.pinned_versions == ("0.2.16",)
    assert config_sync.sync(path, write=True).status is config_sync.SyncStatus.AHEAD
    assert path.read_text(encoding="utf-8") == text


def test_inspect_leaves_uncomparable_pin_alone(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # 比較できない版 (prerelease 固定など) も触らない。大小が判定できない以上、書き換えは危険。
    _patch_releases(monkeypatch, [_release("v0.2.15")])
    text = _config_text("0.3.0-rc1", _DIGEST)
    path = _write(tmp_path, text)
    assert config_sync.inspect(path).status is config_sync.SyncStatus.AHEAD
    assert path.read_text(encoding="utf-8") == text


def test_cmd_sync_reports_ahead_with_notice(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # 対象外でも理由を stderr に出し、黙って見逃さない (exit は 0)。
    _patch_project_root(monkeypatch, tmp_path)
    _patch_releases(monkeypatch, [_release("v0.2.15")])
    _write(tmp_path, _config_text("0.2.16", _DIGEST))
    assert config_sync.cmd_sync(argparse.Namespace(check=True)) == 0
    assert "より新しい" in capsys.readouterr().err


def test_request_headers_use_token_file_first(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # 既存規約の優先順位 (トークンファイル → GITHUB_PAT_TOKEN → GITHUB_TOKEN) に従う。
    # 独自に GITHUB_TOKEN だけを見ると、この repo の CI/ローカルでは拾えない。
    headers: list[dict[str, str]] = []
    _patch_cache_dir(monkeypatch, tmp_path)
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "github.token").write_text("file-token\n", encoding="utf-8")
    monkeypatch.setenv("GITHUB_PAT_TOKEN", "pat-token")
    _patch_releases(monkeypatch, [_release("v0.2.15")], None, headers)
    config_sync.inspect(_write(tmp_path, _config_text("0.2.7", _OLD_DIGEST)))
    assert headers[0]["authorization"] == "Bearer file-token"


def test_request_headers_use_actions_env_when_configured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Actions が渡すのは GITHUB_PAT_TOKEN。これを見ないと CI では未認証のままになる。
    headers: list[dict[str, str]] = []
    _patch_cache_dir(monkeypatch, tmp_path)
    monkeypatch.setenv("GITHUB_PAT_TOKEN", "pat-token")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    _patch_releases(monkeypatch, [_release("v0.2.15")], None, headers)
    config_sync.inspect(_write(tmp_path, _config_text("0.2.7", _OLD_DIGEST)))
    assert headers[0]["authorization"] == "Bearer pat-token"


def test_request_headers_fall_back_to_github_token(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    headers: list[dict[str, str]] = []
    _patch_cache_dir(monkeypatch, tmp_path)
    monkeypatch.delenv("GITHUB_PAT_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", "actions-token")
    _patch_releases(monkeypatch, [_release("v0.2.15")], None, headers)
    config_sync.inspect(_write(tmp_path, _config_text("0.2.7", _OLD_DIGEST)))
    assert headers[0]["authorization"] == "Bearer actions-token"


def test_request_headers_are_anonymous_without_token(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # トークンが無くても同期は成立する (fail-open)。
    headers: list[dict[str, str]] = []
    _patch_cache_dir(monkeypatch, tmp_path)
    monkeypatch.delenv("GITHUB_PAT_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    _patch_releases(monkeypatch, [_release("v0.2.15")], None, headers)
    config_sync.inspect(_write(tmp_path, _config_text("0.2.7", _OLD_DIGEST)))
    assert "authorization" not in headers[0]


def test_inspect_reports_in_sync(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_releases(monkeypatch, [_release("v0.2.15")])
    result = config_sync.inspect(_write(tmp_path, _config_text("0.2.15", _DIGEST)))
    assert result.status is config_sync.SyncStatus.IN_SYNC
    assert result.target_version == "0.2.15"


def test_inspect_detects_digest_only_drift(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # バージョンが同じでも sha256 が違えば DRIFT。判定をバージョン比較にすると
    # 内容固定の書き換えを取りこぼす。
    _patch_releases(monkeypatch, [_release("v0.2.15")])
    result = config_sync.inspect(_write(tmp_path, _config_text("0.2.15", _OLD_DIGEST)))
    assert result.status is config_sync.SyncStatus.DRIFT


def test_inspect_detects_missing_digest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # #sha256= なしの生成物 (sha256 を解決できなかったケース) も DRIFT として拾う。
    _patch_releases(monkeypatch, [_release("v0.2.15")])
    text = _config_text("0.2.15", _DIGEST).replace(
        _line("0.2.15", _DIGEST),
        f"          - ame_ai_review_system @ {init_cmd.wheel_url('0.2.15')}",
    )
    result = config_sync.inspect(_write(tmp_path, text))
    assert result.status is config_sync.SyncStatus.DRIFT


def test_inspect_absent_without_wheel_reference(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # language: system 方式の配布先は同期対象が無い。API も引かない。
    _forbid_network(monkeypatch)
    text = (
        "repos:\n"
        "  - repo: local\n"
        "    hooks:\n"
        "      - id: ai-precommit-review\n"
        "        entry: python -m ame_ai_review_system.precommit_review\n"
        "        language: system\n"
    )
    result = config_sync.inspect(_write(tmp_path, text))
    assert result.status is config_sync.SyncStatus.ABSENT


def test_foreign_major_pin_is_out_of_scope(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # 配布先が別メジャーを意図的に固定している場合は巻き戻さない。書き換えず、API も引かない。
    _forbid_network(monkeypatch)
    text = _config_text("1.0.0", _DIGEST)
    path = _write(tmp_path, text)
    assert config_sync.inspect(path).status is config_sync.SyncStatus.ABSENT
    assert config_sync.sync(path, write=True).status is config_sync.SyncStatus.ABSENT
    assert path.read_text(encoding="utf-8") == text


def test_releases_api_requests_max_page_size(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # per_page=30 (既定) だと、別系列の新しいリリースが 30 件あると対象系列が 1 ページ目から
    # 消えて解決不能になる。上限まで要求しておく。
    requests: list[str] = []
    _patch_releases(monkeypatch, [_release("v0.2.15")], requests)
    config_sync.inspect(_write(tmp_path, _config_text("0.2.7", _OLD_DIGEST)))
    assert len(requests) == 1
    assert "per_page=100" in requests[0]


def test_inspect_is_fail_open_when_offline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # 解決できない場合は UNKNOWN を返し、例外を投げない (コミット可否に影響させない)。
    _patch_offline(monkeypatch)
    result = config_sync.inspect(_write(tmp_path, _config_text("0.2.7", _OLD_DIGEST)))
    assert result.status is config_sync.SyncStatus.UNKNOWN


def test_inspect_reports_absent_without_config(tmp_path: Path) -> None:
    # ファイルが無いのは「対象なし」。判定不能にすると、pyproject だけに参照を持つ構成で
    # sync が exit 2 (要調査) を返してしまう。
    result = config_sync.inspect(tmp_path / "missing.yaml")
    assert result.status is config_sync.SyncStatus.ABSENT


def test_inspect_is_fail_open_on_unreadable_config(tmp_path: Path) -> None:
    # 読めない (存在するが読めない) 場合は判定不能として返す (fail-open で例外は出さない)。
    directory = tmp_path / "as-directory.yaml"
    directory.mkdir()
    result = config_sync.inspect(directory)
    assert result.status is config_sync.SyncStatus.UNKNOWN


def test_inspect_is_fail_open_on_http_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # HTTPException (IncompleteRead 等) は OSError のサブクラスではない。捕捉しないと
    # fail-open が破れ、Gate 1 のコミットが失敗する。
    def _boom(
        _url: object, _data: bytes | None = None, *, timeout: float | None = None
    ) -> _FakeResponse:
        partial = b""
        raise http.client.IncompleteRead(partial)

    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    result = config_sync.inspect(_write(tmp_path, _config_text("0.2.7", _OLD_DIGEST)))
    assert result.status is config_sync.SyncStatus.UNKNOWN


def test_sync_resolves_the_release_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # 取得は 1 回で済ませる。2 回引くとレート制限に響き、判定と書き換え先が食い違い得る。
    requests: list[str] = []
    _patch_releases(monkeypatch, [_release("v0.2.15")], requests)
    path = _write(tmp_path, _config_text("0.2.7", _OLD_DIGEST))
    result = config_sync.sync(path, write=True)
    assert result.status is config_sync.SyncStatus.IN_SYNC
    assert len(requests) == 1
    assert _line("0.2.15", _DIGEST) in path.read_text(encoding="utf-8")


def test_sync_rewrites_only_the_managed_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_releases(monkeypatch, [_release("v0.2.15")])
    path = _write(tmp_path, _config_text("0.2.7", _OLD_DIGEST))
    result = config_sync.sync(path, write=True)
    assert result.status is config_sync.SyncStatus.IN_SYNC
    rewritten = path.read_text(encoding="utf-8")
    assert _line("0.2.15", _DIGEST) in rewritten
    assert "0.2.7" not in rewritten
    # 他の行 (engine SDK の依存・別フック・インデント) は 1 バイトも変えない。
    expected = _config_text("0.2.7", _OLD_DIGEST).replace(
        _line("0.2.7", _OLD_DIGEST), _line("0.2.15", _DIGEST)
    )
    assert rewritten == expected


def test_sync_keeps_foreign_major_line_in_mixed_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # 対象系列 (v0.x) と別メジャー (v1.x) が併存し、対象系列だけが DRIFT のケース。
    # 書き換えが判定と同じ選別を使わないと、固定した v1.x 行まで潰れて契約が破れる。
    _patch_releases(monkeypatch, [_release("v0.2.15")])
    foreign = _line("1.0.0", _DIGEST)
    text = _config_text("0.2.7", _OLD_DIGEST).replace(
        "          - claude-agent-sdk\n", f"          - claude-agent-sdk\n{foreign}\n"
    )
    path = _write(tmp_path, text)
    assert config_sync.inspect(path).status is config_sync.SyncStatus.DRIFT
    result = config_sync.sync(path, write=True)
    assert result.status is config_sync.SyncStatus.IN_SYNC
    rewritten = path.read_text(encoding="utf-8")
    assert _line("0.2.15", _DIGEST) in rewritten
    assert foreign in rewritten  # 別メジャーの意図的固定は 1 バイトも変えない
    assert _line("1.0.0", _DIGEST) in rewritten


def test_sync_without_write_keeps_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_releases(monkeypatch, [_release("v0.2.15")])
    text = _config_text("0.2.7", _OLD_DIGEST)
    path = _write(tmp_path, text)
    result = config_sync.sync(path, write=False)
    assert result.status is config_sync.SyncStatus.DRIFT
    assert path.read_text(encoding="utf-8") == text


def test_cmd_sync_check_exit_codes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_project_root(monkeypatch, tmp_path)
    _patch_releases(monkeypatch, [_release("v0.2.15")])
    path = _write(tmp_path, _config_text("0.2.7", _OLD_DIGEST))
    assert config_sync.cmd_sync(argparse.Namespace(check=True)) == 1
    assert path.read_text(encoding="utf-8") == _config_text("0.2.7", _OLD_DIGEST)
    assert "ame-ai-reviewer sync" in capsys.readouterr().err

    # --check を外すと書き換えて 0 を返す。
    assert config_sync.cmd_sync(argparse.Namespace(check=False)) == 0
    assert _line("0.2.15", _DIGEST) in path.read_text(encoding="utf-8")


def test_cmd_sync_reports_unresolved_with_exit_2(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # 解決不能 (UNKNOWN) は drift (exit 1) と別のコードにする。同じ 1 だと CI のゲートが
    # 一時的なネットワーク障害を「参照が古い」と誤検知する。
    _patch_project_root(monkeypatch, tmp_path)
    _patch_offline(monkeypatch)
    _write(tmp_path, _config_text("0.2.7", _OLD_DIGEST))
    assert config_sync.cmd_sync(argparse.Namespace(check=True)) == 2
    assert "判定できません" in capsys.readouterr().err


def test_cmd_sync_absent_is_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_project_root(monkeypatch, tmp_path)
    (tmp_path / ".pre-commit-config.yaml").write_text(
        "repos:\n  - repo: local\n    hooks: []\n", encoding="utf-8"
    )
    assert config_sync.cmd_sync(argparse.Namespace(check=False)) == 0


def test_warn_skips_in_ci(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # CI では書き換える相手が無いため、判定も API 呼び出しもせず即戻る。
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    _patch_project_root(monkeypatch, tmp_path)
    _forbid_network(monkeypatch)
    config_sync.warn_if_out_of_sync()
    assert not capsys.readouterr().err


def test_hook_uses_cached_target_within_ttl(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # コミットごとに API を引くとレイテンシが残る (fail-open でも待ち時間は消えない)。
    # TTL 内はキャッシュで判定する。
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    _patch_project_root(monkeypatch, tmp_path)
    _patch_cache_dir(monkeypatch, tmp_path)
    requests: list[str] = []
    _patch_releases(monkeypatch, [_release("v0.2.15")], requests)
    _write(tmp_path, _config_text("0.2.7", _OLD_DIGEST))
    config_sync.warn_if_out_of_sync()
    config_sync.warn_if_out_of_sync()
    assert len(requests) == 1
    # 警告自体はキャッシュからでも毎回出す (古い参照を見逃さない)。
    assert capsys.readouterr().err.count("ame-ai-reviewer sync") == 2


def test_hook_does_not_retry_immediately_after_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # 失敗も記録する。記録しないと、オフラインではコミットごとにタイムアウトを待ち直す
    # (レイテンシ対策が失敗ケースで効かない)。
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    _patch_project_root(monkeypatch, tmp_path)
    _patch_cache_dir(monkeypatch, tmp_path)
    requests: list[str] = []
    _patch_offline(monkeypatch, requests)
    _write(tmp_path, _config_text("0.2.7", _OLD_DIGEST))
    config_sync.warn_if_out_of_sync()
    config_sync.warn_if_out_of_sync()
    assert len(requests) == 1
    assert not capsys.readouterr().err


def test_hook_retries_after_failure_ttl(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # 失敗の記録も TTL で失効させ、いつまでも再試行しない状態にしない。
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    _patch_project_root(monkeypatch, tmp_path)
    _patch_cache_dir(monkeypatch, tmp_path)
    requests: list[str] = []
    _patch_offline(monkeypatch, requests)
    _write(tmp_path, _config_text("0.2.7", _OLD_DIGEST))
    config_sync.warn_if_out_of_sync()
    cache = tmp_path / "config" / "config_sync_cache.json"
    data = json.loads(cache.read_text(encoding="utf-8"))
    assert "failed_at" in data
    data["failed_at"] = 0  # 1970 年。どんな TTL でも失効している。
    cache.write_text(json.dumps(data), encoding="utf-8")
    config_sync.warn_if_out_of_sync()
    assert len(requests) == 2


def test_hook_refreshes_expired_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # TTL を過ぎたら解決し直す (キャッシュが古いまま固定されない)。
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    _patch_project_root(monkeypatch, tmp_path)
    _patch_cache_dir(monkeypatch, tmp_path)
    requests: list[str] = []
    _patch_releases(monkeypatch, [_release("v0.2.15")], requests)
    _write(tmp_path, _config_text("0.2.7", _OLD_DIGEST))
    config_sync.warn_if_out_of_sync()
    cache = tmp_path / "config" / "config_sync_cache.json"
    data = json.loads(cache.read_text(encoding="utf-8"))
    data["resolved_at"] = 0  # 1970 年。どんな TTL でも期限切れになる。
    cache.write_text(json.dumps(data), encoding="utf-8")
    config_sync.warn_if_out_of_sync()
    assert len(requests) == 2


def test_warn_prints_on_drift(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    _patch_project_root(monkeypatch, tmp_path)
    _patch_cache_dir(monkeypatch, tmp_path)
    _patch_releases(monkeypatch, [_release("v0.2.15")])
    _write(tmp_path, _config_text("0.2.7", _OLD_DIGEST))
    config_sync.warn_if_out_of_sync()
    assert "ame-ai-reviewer sync" in capsys.readouterr().err


def test_warn_is_silent_when_in_sync(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    _patch_project_root(monkeypatch, tmp_path)
    _patch_cache_dir(monkeypatch, tmp_path)
    _patch_releases(monkeypatch, [_release("v0.2.15")])
    _write(tmp_path, _config_text("0.2.15", _DIGEST))
    config_sync.warn_if_out_of_sync()
    assert not capsys.readouterr().err


def test_warn_is_fail_open_when_offline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # fail-open: 判定できない場合も例外を出さず、警告も出さない。
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    _patch_project_root(monkeypatch, tmp_path)
    _patch_cache_dir(monkeypatch, tmp_path)
    _patch_offline(monkeypatch)
    _write(tmp_path, _config_text("0.2.7", _OLD_DIGEST))
    config_sync.warn_if_out_of_sync()
    assert not capsys.readouterr().err


def _pyproject_text(version: str, *, indent: str = "    ", comma: bool = True) -> str:
    """System 構成の導入先の pyproject.toml を模する (wheel を直接参照する)."""
    comma_text = "," if comma else ""
    return (
        "[project]\n"
        'name = "x"\n'
        "dependencies = [\n"
        f'{indent}"ame-ai-review-system @ {init_cmd.wheel_url(version)}"{comma_text}\n'
        "]\n"
    )


def _write_pyproject(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "pyproject.toml"
    path.write_text(text, encoding="utf-8")
    return path


def _patch_uv(
    monkeypatch: pytest.MonkeyPatch,
    *,
    available: bool = True,
    returncode: int = 0,
    stderr: str = "",
) -> list[dict[str, object]]:
    """``uv lock`` の実行を差し替え、呼び出された引数を記録する."""

    def _which(_name: str) -> str | None:
        return "/usr/bin/uv" if available else None

    monkeypatch.setattr(shutil, "which", _which)
    calls: list[dict[str, object]] = []

    def _fake_run(
        args: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append({"args": list(args), **kwargs})
        return subprocess.CompletedProcess(args, returncode, "", stderr)

    monkeypatch.setattr(subprocess, "run", _fake_run)
    return calls


def _patch_installed_version(monkeypatch: pytest.MonkeyPatch, version: str) -> None:
    """``importlib.metadata.version`` を差し替える (実環境の導入状況に依存しない)."""

    def _fake_version(_name: str) -> str:
        return version

    monkeypatch.setattr(importlib.metadata, "version", _fake_version)


def test_inspect_pyproject_reports_in_sync(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_releases(monkeypatch, [_release("v0.2.15")])
    result = config_sync.inspect_pyproject(
        _write_pyproject(tmp_path, _pyproject_text("0.2.15"))
    )
    assert result.status is config_sync.SyncStatus.IN_SYNC
    assert result.target_version == "0.2.15"


def test_inspect_pyproject_reports_drift(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_releases(monkeypatch, [_release("v0.2.15")])
    result = config_sync.inspect_pyproject(
        _write_pyproject(tmp_path, _pyproject_text("0.2.7"))
    )
    assert result.status is config_sync.SyncStatus.DRIFT
    assert result.target_version == "0.2.15"


def test_sync_pyproject_rewrites_and_runs_uv_lock(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # 参照 URL だけ書き換えると uv.lock の hash が古いまま残るため、uv lock まで走らせる。
    _patch_project_root(monkeypatch, tmp_path)
    _patch_releases(monkeypatch, [_release("v0.2.15")])
    calls = _patch_uv(monkeypatch)
    path = _write_pyproject(tmp_path, _pyproject_text("0.2.7"))
    result = config_sync.sync_pyproject(path, write=True)
    assert result.status is config_sync.SyncStatus.IN_SYNC
    assert "uv.lock" in result.detail
    assert init_cmd.wheel_url("0.2.15") in path.read_text(encoding="utf-8")
    assert init_cmd.wheel_url("0.2.7") not in path.read_text(encoding="utf-8")
    assert [call["args"] for call in calls] == [["/usr/bin/uv", "lock"]]
    # uv は pyproject.toml のあるディレクトリで実行する (project_root と一致しない構成も)。
    assert calls[0]["cwd"] == tmp_path


def test_sync_pyproject_check_does_not_write_or_lock(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_project_root(monkeypatch, tmp_path)
    _patch_releases(monkeypatch, [_release("v0.2.15")])
    calls = _patch_uv(monkeypatch)
    text = _pyproject_text("0.2.7")
    path = _write_pyproject(tmp_path, text)
    assert (
        config_sync.sync_pyproject(path, write=False).status
        is config_sync.SyncStatus.DRIFT
    )
    assert path.read_text(encoding="utf-8") == text
    assert calls == []


def test_sync_pyproject_reports_when_uv_is_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # uv が無い環境では「書き換えたがロックが追随していない」ことを黙らせない (要対応)。
    _patch_project_root(monkeypatch, tmp_path)
    _patch_releases(monkeypatch, [_release("v0.2.15")])
    _patch_uv(monkeypatch, available=False)
    text = _pyproject_text("0.2.7")
    path = _write_pyproject(tmp_path, text)
    result = config_sync.sync_pyproject(path, write=True)
    assert result.status is config_sync.SyncStatus.UNKNOWN
    assert "uv" in result.detail
    # 参照だけ書き換わってロックが古いまま残ると uv sync が壊れるため、書き戻す。
    assert path.read_text(encoding="utf-8") == text
    # 書き戻した結果は「変化なし」なので、到達目標の版は載せない (結果の形を揃える)。
    assert result.target_version is None


def test_sync_pyproject_reports_when_uv_lock_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_project_root(monkeypatch, tmp_path)
    _patch_releases(monkeypatch, [_release("v0.2.15")])
    _patch_uv(monkeypatch, returncode=1, stderr="error: no solution found\n")
    text = _pyproject_text("0.2.7")
    path = _write_pyproject(tmp_path, text)
    result = config_sync.sync_pyproject(path, write=True)
    assert result.status is config_sync.SyncStatus.UNKNOWN
    assert "no solution found" in result.detail
    assert "書き戻" in result.detail
    assert path.read_text(encoding="utf-8") == text


def test_inspect_pyproject_leaves_other_series_alone(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # 意図的な別メジャー固定 (v1.x) は対象外。書き換えても 1 バイト変えない。
    _patch_releases(monkeypatch, [_release("v0.2.15"), _release("v1.2.3")])
    text = _pyproject_text("1.2.3")
    path = _write_pyproject(tmp_path, text)
    assert config_sync.inspect_pyproject(path).status is config_sync.SyncStatus.ABSENT
    assert (
        config_sync.sync_pyproject(path, write=True).status
        is config_sync.SyncStatus.ABSENT
    )
    assert path.read_text(encoding="utf-8") == text


def test_inspect_pyproject_absent_without_reference(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _forbid_network(monkeypatch)
    path = _write_pyproject(tmp_path, '[project]\nname = "x"\ndependencies = []\n')
    result = config_sync.inspect_pyproject(path)
    assert result.status is config_sync.SyncStatus.ABSENT
    assert config_sync.inspect_pyproject(
        tmp_path / "pyproject.toml.missing"
    ).status is (config_sync.SyncStatus.ABSENT)


def test_cmd_sync_reports_both_locations(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_project_root(monkeypatch, tmp_path)
    _patch_releases(monkeypatch, [_release("v0.2.15")])
    _write(tmp_path, _config_text("0.2.15", _DIGEST))
    _write_pyproject(tmp_path, _pyproject_text("0.2.7"))
    assert config_sync.cmd_sync(argparse.Namespace(check=True)) == 1
    captured = capsys.readouterr()
    assert "pre-commit: 同期済み" in captured.out
    assert "pyproject: 差分あり" in captured.err


def test_hook_warns_when_installed_version_is_behind(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # 参照を git 管理しない導入先 (wheel を venv へ直接入れる構成) は、インストール済みの版で
    # 古さを判定しないと「対象なし」のまま無言で古い実装を使い続ける。
    _patch_project_root(monkeypatch, tmp_path)
    _patch_releases(monkeypatch, [_release("v0.2.15")])
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    _patch_installed_version(monkeypatch, "0.2.1")
    _write(tmp_path, "repos: []\n")
    config_sync.warn_if_out_of_sync()
    assert "より古い" in capsys.readouterr().err


def test_hook_silent_when_installed_version_is_current(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_project_root(monkeypatch, tmp_path)
    _patch_releases(monkeypatch, [_release("v0.2.15")])
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    _patch_installed_version(monkeypatch, "0.2.15")
    _write(tmp_path, "repos: []\n")
    config_sync.warn_if_out_of_sync()
    assert not capsys.readouterr().err


def test_hook_prefers_git_reference_over_installed_version(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # git 上の参照が同期済みなら、インストール済みの版が古くても警告しない (参照が正)。
    _patch_project_root(monkeypatch, tmp_path)
    _patch_releases(monkeypatch, [_release("v0.2.15")])
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    _patch_installed_version(monkeypatch, "0.2.1")
    _write(tmp_path, _config_text("0.2.15", _DIGEST))
    config_sync.warn_if_out_of_sync()
    assert not capsys.readouterr().err


def test_hook_warns_for_pyproject_drift(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_project_root(monkeypatch, tmp_path)
    _patch_releases(monkeypatch, [_release("v0.2.15")])
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    _write(tmp_path, "repos: []\n")
    _write_pyproject(tmp_path, _pyproject_text("0.2.7"))
    config_sync.warn_if_out_of_sync()
    err = capsys.readouterr().err
    assert "pyproject.toml" in err
    assert "ame-ai-reviewer sync" in err


def test_inspect_absent_when_config_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # ファイルが無い構成 (pyproject だけに参照を持つ等) を「判定不能 (要調査)」にしない。
    _forbid_network(monkeypatch)
    result = config_sync.inspect(tmp_path / ".pre-commit-config.yaml")
    assert result.status is config_sync.SyncStatus.ABSENT


def test_cmd_sync_only_pyproject_location(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_project_root(monkeypatch, tmp_path)
    _patch_releases(monkeypatch, [_release("v0.2.15")])
    _patch_uv(monkeypatch)
    _write_pyproject(tmp_path, _pyproject_text("0.2.7"))
    assert config_sync.cmd_sync(argparse.Namespace(check=True)) == 1
    captured = capsys.readouterr()
    assert ".pre-commit-config.yaml がありません" in captured.out
    assert "pyproject: 差分あり" in captured.err


def _pyproject_line(
    version: str,
    *,
    name: str = "ame-ai-review-system",
    fragment: str | None = None,
    trailing: str = "",
) -> str:
    """1 行の依存記述を組み立てる (表記揺れ・フラグメント・末尾空白の検証用)."""
    url = init_cmd.wheel_url(version) + (f"#sha256={fragment}" if fragment else "")
    return f'    "{name} @ {url}",{trailing}\n'


def _wrap_pyproject(line: str) -> str:
    return f'[project]\nname = "x"\ndependencies = [\n{line}]\n'


def test_inspect_pyproject_accepts_underscore_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # 依存名は PEP 503 の正規化で同一視する (ame_ai_review_system と書く導入先がある)。
    _patch_releases(monkeypatch, [_release("v0.2.15")])
    path = _write_pyproject(
        tmp_path, _wrap_pyproject(_pyproject_line("0.2.7", name="ame_ai_review_system"))
    )
    _patch_uv(monkeypatch)
    assert config_sync.sync_pyproject(path, write=True).status is (
        config_sync.SyncStatus.IN_SYNC
    )
    # 書き換え後も元の表記 (アンダースコア) を保つ。
    text = path.read_text(encoding="utf-8")
    assert "ame_ai_review_system @ " in text
    assert init_cmd.wheel_url("0.2.15") in text


def test_inspect_pyproject_updates_pinned_fragment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # URL に #sha256= を書く導入先は、書き換えでフラグメントを落とさず新しい digest にする。
    _patch_releases(monkeypatch, [_release("v0.2.15", digest=_DIGEST)])
    path = _write_pyproject(
        tmp_path, _wrap_pyproject(_pyproject_line("0.2.7", fragment=_OLD_DIGEST))
    )
    _patch_uv(monkeypatch)
    assert config_sync.sync_pyproject(path, write=True).status is (
        config_sync.SyncStatus.IN_SYNC
    )
    text = path.read_text(encoding="utf-8")
    assert f"{init_cmd.wheel_url('0.2.15')}#sha256={_DIGEST}" in text
    assert _OLD_DIGEST not in text


def test_inspect_pyproject_in_sync_ignores_unrelated_lines(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_releases(monkeypatch, [_release("v0.2.15")])
    path = _write_pyproject(
        tmp_path,
        '[project]\nname = "x"\ndependencies = [\n'
        '    "ame-ai-review-system @ ' + init_cmd.wheel_url("0.2.15") + '",\n'
        '    "ame-ai-review-system-extra @ https://example.invalid/x.whl",\n'
        '    "other @ ' + init_cmd.wheel_url("0.2.7") + '",\n'
        "]\n",
    )
    # 名前が違う / 別 URL の行は管理対象にしない。
    assert config_sync.inspect_pyproject(path).status is config_sync.SyncStatus.IN_SYNC


def test_sync_pyproject_runs_uv_in_pyproject_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # project_root と pyproject.toml の位置が違っても、uv lock は pyproject の隣で走らせる。
    repo = tmp_path / "repo"
    repo.mkdir()
    _patch_project_root(monkeypatch, repo)
    _patch_releases(monkeypatch, [_release("v0.2.15")])
    calls = _patch_uv(monkeypatch)
    path = _write_pyproject(tmp_path, _pyproject_text("0.2.7"))
    assert config_sync.sync_pyproject(path, write=True).status is (
        config_sync.SyncStatus.IN_SYNC
    )
    assert calls[0]["cwd"] == tmp_path


def test_inspect_pyproject_keeps_other_fragment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # sha256 以外のフラグメント (egg= 等) は落とさず、sha256 だけ差し替える。
    _patch_releases(monkeypatch, [_release("v0.2.15")])
    line = (
        f'    "ame-ai-review-system @ {init_cmd.wheel_url("0.2.7")}'
        f'#egg=ame_ai_review_system&sha256={_OLD_DIGEST}",\n'
    )
    path = _write_pyproject(tmp_path, _wrap_pyproject(line))
    _patch_uv(monkeypatch)
    assert config_sync.sync_pyproject(path, write=True).status is (
        config_sync.SyncStatus.IN_SYNC
    )
    text = path.read_text(encoding="utf-8")
    assert "egg=ame_ai_review_system" in text
    assert f"sha256={_DIGEST}" in text
    assert _OLD_DIGEST not in text


def test_sync_pyproject_keeps_trailing_whitespace(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # 行末の空白は書き換えで落とさない (無関係な差分を作らない)。
    _patch_project_root(monkeypatch, tmp_path)
    _patch_releases(monkeypatch, [_release("v0.2.15")])
    _patch_uv(monkeypatch)
    path = _write_pyproject(
        tmp_path, _wrap_pyproject(_pyproject_line("0.2.7", trailing="  "))
    )
    config_sync.sync_pyproject(path, write=True)
    assert path.read_text(encoding="utf-8").splitlines()[3].endswith('",  ')


def test_sync_pyproject_keeps_reference_when_write_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # 書き込みが途中で失敗しても、参照を壊さない (一時ファイル + 置換)。
    _patch_project_root(monkeypatch, tmp_path)
    _patch_releases(monkeypatch, [_release("v0.2.15")])
    _patch_uv(monkeypatch)
    text = _pyproject_text("0.2.7")
    path = _write_pyproject(tmp_path, text)

    message = "disk full"

    def _boom(*_args: object, **_kwargs: object) -> object:
        raise OSError(message)

    monkeypatch.setattr(Path, "replace", _boom)
    result = config_sync.sync_pyproject(path, write=True)
    assert result.status is config_sync.SyncStatus.UNKNOWN
    assert path.read_text(encoding="utf-8") == text
    # 一時ファイルを残さない。
    assert [entry.name for entry in tmp_path.iterdir()] == ["pyproject.toml"]


def test_sync_pyproject_preserves_file_mode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # 置換で権限を変えない (mkstemp 方式だと 0600 に落ちる)。
    _patch_project_root(monkeypatch, tmp_path)
    _patch_releases(monkeypatch, [_release("v0.2.15")])
    _patch_uv(monkeypatch)
    path = _write_pyproject(tmp_path, _pyproject_text("0.2.7"))
    path.chmod(0o640)
    assert config_sync.sync_pyproject(path, write=True).status is (
        config_sync.SyncStatus.IN_SYNC
    )
    assert stat.S_IMODE(path.stat().st_mode) == 0o640


def test_sync_pyproject_rolls_back_on_unexpected_lock_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # uv 側が想定外の例外を出しても、参照だけ書き換わった状態を残さない。
    _patch_project_root(monkeypatch, tmp_path)
    _patch_releases(monkeypatch, [_release("v0.2.15")])
    _patch_uv(monkeypatch)
    text = _pyproject_text("0.2.7")
    path = _write_pyproject(tmp_path, text)

    message = "unexpected"

    def _boom(*_args: object, **_kwargs: object) -> object:
        raise ValueError(message)

    monkeypatch.setattr(subprocess, "run", _boom)
    result = config_sync.sync_pyproject(path, write=True)
    assert result.status is config_sync.SyncStatus.UNKNOWN
    assert "uv lock" in result.detail
    assert path.read_text(encoding="utf-8") == text
