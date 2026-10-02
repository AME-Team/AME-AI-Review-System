"""``config_sync`` の検証 (サービス化 Phase 2・Issue #147).

配布先の ``.pre-commit-config.yaml`` にある wheel 参照を hub の最新リリースへ
追随させる仕組みを検証する。書き換え対象を絞ること・fail-open であること・
テキスト完全一致で判定することを固定する。HTTP は ``urlopen`` をフェイクして
差し替え、実ネットワークに依存させない。
"""

from __future__ import annotations

import argparse
import http.client
import json
import urllib.request
from typing import TYPE_CHECKING

import pytest
from ame_ai_review_system import config_sync, init_cmd, paths

if TYPE_CHECKING:
    from pathlib import Path
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


def test_inspect_is_fail_open_without_config(tmp_path: Path) -> None:
    result = config_sync.inspect(tmp_path / "missing.yaml")
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
