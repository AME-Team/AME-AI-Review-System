"""Gate 1 フックの wheel 参照を hub の最新リリースへ追随させる (Issue #147・サービス化 Phase 2).

導入先の ``.pre-commit-config.yaml`` は Gate 1 の AI フックで wheel を
``ame_ai_review_system @ <release-url>#sha256=<digest>`` の形で参照する。供給チェーン保護
(Issue #84) のため内容の固定は維持しつつ hub のリリースへ追随させるには、この参照を
書き換える必要があり、配布先ごとの手作業更新が保守負担になっていた。参照行を機械的に
解決して同期する。

方針 (Penguin-AI-Review-System の config_sync から継承):

1. fail-open — 同期の失敗で Gate 1 のコミット可否を変えない。
2. ``load_config()`` より先に CI を判定してスキップする。
3. バージョン一致ではなく**テキスト完全一致**で IN_SYNC を判定する。

書き換えるのは明示コマンド ``ame-ai-reviewer sync`` だけにする。フック実行中に自身の設定を
書き換えると、実行中の pre-commit と設定ファイルの内容が食い違うため、フック側は警告に留める。
"""

from __future__ import annotations

import http.client
import json
import os
import re
import sys
import time
import urllib.request
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    import argparse
    from pathlib import Path

from . import github_client, init_cmd, paths

# 管理対象の参照行。``additional_dependencies`` のリスト項目のうち hub のリリース URL を指す
# ``ame_ai_review_system @ ...`` だけを対象にする (engine SDK 等の他項目は触らない)。
_MANAGED_LINE_RE = re.compile(
    r"^(?P<indent>\s*)-\s+ame_ai_review_system @ (?P<url>\S+?)"
    r"(?:#sha256=(?P<digest>[0-9a-f]{64}))?\s*$",
)

# リリース URL からバージョンを取り出す (``.../download/v0.2.15/<name>``)。
_URL_VERSION_RE = re.compile(r"/download/v(?P<version>[^/]+)/")

# 対象系列の抽出。``v<major>.<minor>.<patch>`` のリリースタグのみを候補にする。
_RELEASE_TAG_TEMPLATE = r"^v{major}\.(\d+)\.(\d+)$"

# 版の比較用。``x.y.z`` 以外 (prerelease 等) は比較しない。
_VERSION_RE = re.compile(r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$")

# hub のリリース一覧 API。系列で絞って最新を選ぶだけなので 1 ページで足りる。
# per_page は上限 (100) にする。既定の 30 件では、別系列の新しいリリースが 30 件以上
# あると対象系列が 1 ページ目に現れず、解決できないまま無言で機能しなくなる。
_RELEASES_API = (
    f"https://api.github.com/repos/{init_cmd.repo_fqn()}/releases?per_page=100"
)

_TIMEOUT_SECONDS = 10
# フック経由の判定はコミットを待たせるため、タイムアウトを短くし結果をキャッシュする。
# fail-open でも待ち時間は消えないため、レイテンシは別に潰す必要がある。
_HOOK_TIMEOUT_SECONDS = 3
_CACHE_TTL_SECONDS = 3600
# 解決に失敗した場合も短い TTL で記録する。記録しないと、オフライン環境ではコミットごとに
# タイムアウトを待ち直す (レイテンシ対策が失敗ケースで効かない)。
_FAILURE_CACHE_TTL_SECONDS = 300

# ``sync --check`` の終了コード。更新すべき状態 (drift) と、判定できなかった状態
# (解決不能・設定読取不能) を区別する。同じ 1 にすると、CI のゲートが一時的な
# ネットワーク障害を「参照が古い」と誤検知する。
_EXIT_DRIFT = 1
_EXIT_UNRESOLVED = 2


class SyncStatus(StrEnum):
    """同期状態."""

    IN_SYNC = "in-sync"
    DRIFT = "drift"
    # 固定版が hub の最新より新しい (棚上げ)。対象外だが「参照行が無い」ABSENT とは区別する。
    AHEAD = "ahead"
    ABSENT = "absent"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SyncResult:
    """同期の判定結果 (``detail`` は人向けの説明)."""

    status: SyncStatus
    path: Path
    target_version: str | None = None
    target_digest: str | None = None
    pinned_versions: tuple[str, ...] = ()
    detail: str = ""


def _version_order(version: str) -> tuple[int, int, int] | None:
    """``x.y.z`` を比較可能なタプルにする (解釈できない版は ``None``)."""
    match = _VERSION_RE.match(version)
    if match is None:
        return None
    return (
        int(match.group("major")),
        int(match.group("minor")),
        int(match.group("patch")),
    )


def _optional_token() -> str:
    """トークンを既存規約の優先順位で解決する (見つからなければ空文字).

    優先順位は ``github_client.get_token`` (トークンファイル → ``GITHUB_PAT_TOKEN``) をそのまま
    使う。独自に ``GITHUB_TOKEN`` だけを見ると、この repo のローカル設定や CI (Actions が渡す
    のは ``GITHUB_PAT_TOKEN``) ではトークンを拾えず、未認証 (60 req/時/IP) のままになる。
    未認証でも同期は成立するため、解決失敗は空文字にして最後に Actions の ``GITHUB_TOKEN`` /
    ``GH_TOKEN`` を見る。トークンの値はログにも例外メッセージにも出さない。
    """
    token_file = str(paths.global_config_dir() / "github.token")
    try:
        token = github_client.get_token(token_file).strip()
    except RuntimeError:
        # トークンが無いことは異常ではない (未認証でも読める公開リポジトリのリリース API)。
        token = ""
    if token:
        return token
    # 例外だけに頼らない。空文字を返す実装へ変わった場合もフォールバックが効くようにする。
    fallback = os.environ.get("GITHUB_TOKEN", "").strip()
    return fallback or os.environ.get("GH_TOKEN", "").strip()


def _request_headers() -> dict[str, str]:
    """リリース一覧 API のヘッダーを返す (トークンがあれば認証する)."""
    headers = {"Accept": "application/vnd.github+json"}
    token = _optional_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _is_target_series(url: str, major: str) -> bool:
    """参照 URL が追随対象のメジャー系列か (別メジャーの意図的固定は False).

    判定 (``inspect``) と書き換え (``_rewrite``) の双方でこれを使う。片方だけに適用すると、
    対象系列と別メジャーが併存する設定で、判定は「対象系列だけ DRIFT」と言いながら書き換えが
    別メジャー行まで潰す (意図した固定を黙って破壊する)。
    """
    version = _pinned_version(url)
    return version is None or version.startswith(f"{major}.")


def _target_major() -> str:
    """追随先のメジャー系列 (``DEFAULT_REF`` から導出する)."""
    return init_cmd.DEFAULT_REF.removeprefix("v")


def _managed_matches(text: str, major: str) -> list[re.Match[str]]:
    """管理対象の参照行を出現順に列挙する.

    別メジャーを意図的に固定している参照 (例: 配布先が ``v1.x`` を選んでいる) は対象外に
    する。``sync`` が新しいメジャーから既定系列へ巻き戻すのを防ぐためである。バージョンを
    取り出せない壊れた URL は、修復対象として管理下に残す。
    """
    matches: list[re.Match[str]] = []
    for line in text.splitlines():
        match = _MANAGED_LINE_RE.match(line)
        if match is None:
            continue
        if not _is_target_series(match.group("url"), major):
            continue
        matches.append(match)
    return matches


def _desired_line(indent: str, version: str, digest: str) -> str:
    """``version`` に対応する参照行を生成する (``init`` の生成物と同じ表記)."""
    return f"{indent}- ame_ai_review_system @ {init_cmd.wheel_url(version)}#sha256={digest}"


def _pinned_version(url: str) -> str | None:
    """参照 URL が指すバージョンを返す."""
    match = _URL_VERSION_RE.search(url)
    return match.group("version") if match is not None else None


def _latest_release(
    major: str, *, timeout: int = _TIMEOUT_SECONDS
) -> tuple[str, str] | None:
    """対象メジャー系列の最新リリースの ``(version, sha256)`` を返す.

    リリース一覧を 1 回取得し、``v<major>.x.y`` のタグを持つ最新版を選ぶ。移動メジャータグ
    (``v0``) 自体には Release オブジェクトが無いため (付け替えはタグのみを動かす)、タグでは
    解決できない。系列で絞るのは、hub が別メジャーを並行リリースしても配布先が意図しない
    メジャーへ飛ばないようにするため。sha256 を解決できないリリースは候補から外し、内容固定を
    崩さない。解決できない場合は ``None`` を返す (呼び出し側は fail-open)。
    """
    try:
        # API URL は固定の HTTPS ホストのみ。file:// 等のスキームは指定されない。
        req = urllib.request.Request(_RELEASES_API, headers=_request_headers())
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data: Any = json.loads(resp.read().decode("utf-8"))
    except (OSError, ValueError, http.client.HTTPException):
        # HTTPException (IncompleteRead 等) は OSError のサブクラスではないため、
        # 捕捉しないと fail-open が破れて Gate 1 のコミットが失敗する。
        return None
    if not isinstance(data, list):
        return None
    tag_re = re.compile(_RELEASE_TAG_TEMPLATE.format(major=re.escape(major)))
    candidates: list[tuple[tuple[int, int], str, str]] = []
    for release in cast("list[dict[str, Any]]", data):
        if release.get("prerelease") is True or release.get("draft") is True:
            # prerelease は配布先へ配る対象ではない (素の ``v0.3.0`` タグでも pre-release に
            # できるため、タグの形だけでは弾けない)。draft は未認証 API では見えないが、
            # トークン付きの取得に切り替えると混ざる。
            continue
        tag = release.get("tag_name")
        if not isinstance(tag, str):
            continue
        match = tag_re.match(tag)
        if match is None:
            continue
        version = tag.removeprefix("v")
        digest = init_cmd.wheel_asset_digest(release, version)
        if digest is None:
            continue
        order = (int(match.group(1)), int(match.group(2)))
        candidates.append((order, version, digest))
    if not candidates:
        return None
    _, version, digest = max(candidates)
    return version, digest


def _cache_path() -> Path:
    """解決結果のキャッシュ先 (プロジェクト非依存なのでグローバル 1 箇所)."""
    return paths.global_config_dir() / "config_sync_cache.json"


def _read_cached_target(major: str) -> tuple[bool, tuple[str, str] | None]:
    """キャッシュの ``(有効な記録があるか, 解決結果)`` を返す.

    ``(True, None)`` は「TTL 内に解決へ失敗した」ことを表す。失敗も記録するのは、記録しないと
    オフライン環境でコミットごとにタイムアウトを待ち直す (レイテンシ対策が失敗ケースで効かない)
    ためである。
    """
    try:
        raw = json.loads(_cache_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False, None
    if not isinstance(raw, dict):
        return False, None
    data = cast("dict[str, Any]", raw)
    if data.get("major") != major:
        return False, None
    now = time.time()
    failed_at = data.get("failed_at")
    if isinstance(failed_at, int | float):
        return now - failed_at <= _FAILURE_CACHE_TTL_SECONDS, None
    resolved_at = data.get("resolved_at")
    if (
        isinstance(data.get("version"), str)
        and isinstance(data.get("digest"), str)
        and isinstance(resolved_at, int | float)
        and now - resolved_at <= _CACHE_TTL_SECONDS
    ):
        return True, (cast("str", data["version"]), cast("str", data["digest"]))
    return False, None


def _write_cached_target(major: str, target: tuple[str, str] | None) -> None:
    """解決結果をキャッシュへ書く (``None`` は失敗の記録・失敗しても無視する)."""
    payload: dict[str, Any]
    if target is None:
        payload = {"major": major, "failed_at": time.time()}
    else:
        version, digest = target
        payload = {
            "major": major,
            "version": version,
            "digest": digest,
            "resolved_at": time.time(),
        }
    try:
        cache = _cache_path()
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(payload), encoding="utf-8")
    except OSError:
        # キャッシュできないことは警告を止める理由にならない。
        return


def _resolve_target(
    major: str, *, use_cache: bool, timeout: int
) -> tuple[str, str] | None:
    """追随先の ``(version, sha256)`` を解決する.

    ``use_cache`` はフック経由の判定用。コミットごとに API を引くとレイテンシが残るため
    (fail-open でも待ち時間は消えない)、TTL 内はキャッシュを使う。解決に失敗した場合も
    短い TTL で記録し、オフライン時に毎コミット待ち直さないようにする。
    """
    if use_cache:
        found, cached = _read_cached_target(major)
        if found:
            return cached
    target = _latest_release(major, timeout=timeout)
    if use_cache:
        _write_cached_target(major, target)
    return target


def inspect(
    config_path: Path, *, use_cache: bool = False, timeout: int = _TIMEOUT_SECONDS
) -> SyncResult:
    """``.pre-commit-config.yaml`` の wheel 参照を検査する (書き換えない).

    ``use_cache`` / ``timeout`` はフック経由の判定でレイテンシを抑えるために使う
    (``sync`` と ``--check`` は常に解決し直す)。
    """
    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        return SyncResult(
            SyncStatus.UNKNOWN, config_path, detail=f"設定を読めません: {exc}"
        )
    major = _target_major()
    matches = _managed_matches(text, major)
    if not matches:
        # ``language: system`` 方式・未導入・別メジャーの意図的固定。対象が無いのは異常ではない。
        return SyncResult(
            SyncStatus.ABSENT,
            config_path,
            detail="管理対象の wheel 参照がありません (別メジャー固定は対象外)",
        )
    pinned = tuple(
        version
        for match in matches
        if (version := _pinned_version(match.group("url"))) is not None
    )
    target = _resolve_target(major, use_cache=use_cache, timeout=timeout)
    if target is None:
        return SyncResult(
            SyncStatus.UNKNOWN,
            config_path,
            pinned_versions=pinned,
            detail=f"v{major} 系列の最新リリースを解決できません",
        )
    version, digest = target
    target_order = _version_order(version)
    if target_order is not None and any(
        (order := _version_order(pinned_version)) is None or order > target_order
        for pinned_version in pinned
    ):
        # 固定版が解決結果より新しい (存在しない版・意図的な prerelease 固定など)。書き換えると
        # 黙ってダウングレードするため対象外にする。
        return SyncResult(
            SyncStatus.AHEAD,
            config_path,
            pinned_versions=pinned,
            detail=f"固定版が hub の最新 (v{version}) より新しいため対象外です",
        )
    actual = [match.group(0) for match in matches]
    # 判定はバージョン比較ではなくテキスト完全一致にする (URL 表記や sha256 の差異を
    # 見逃さないため)。sha256 なしの生成物もここで DRIFT として拾える。
    desired = [
        _desired_line(match.group("indent"), version, digest) for match in matches
    ]
    if actual == desired:
        return SyncResult(
            SyncStatus.IN_SYNC,
            config_path,
            target_version=version,
            target_digest=digest,
            pinned_versions=pinned,
        )
    return SyncResult(
        SyncStatus.DRIFT,
        config_path,
        target_version=version,
        target_digest=digest,
        pinned_versions=pinned,
        detail=f"参照 {', '.join(pinned) or '不明'} → v{version} へ更新できます",
    )


def _rewrite(text: str, version: str, digest: str, major: str) -> str:
    """管理対象行だけを書き換え、改行と他の行を保つ.

    対象メジャーの判定は ``inspect`` と同じ ``_is_target_series`` を使う。別メジャーを固定した
    参照は、判定で対象外としている以上ここでも触らない。
    """
    out: list[str] = []
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        ending = line[len(body) :]
        match = _MANAGED_LINE_RE.match(body)
        if match is None or not _is_target_series(match.group("url"), major):
            out.append(line)
            continue
        desired = _desired_line(match.group("indent"), version, digest)
        out.append(f"{desired}{ending}")
    return "".join(out)


def sync(config_path: Path, *, write: bool) -> SyncResult:
    """``.pre-commit-config.yaml`` の wheel 参照を hub の最新リリースへ同期する.

    ``write=False`` (``--check``) では判定のみ行い、書き換えない。
    """
    result = inspect(config_path)
    if result.status is not SyncStatus.DRIFT or not write:
        return result
    version, digest = result.target_version, result.target_digest
    if version is None or digest is None:
        # 解決済みの値を再利用する。再取得すると API を 2 回引くうえ、判定と書き換え先が
        # 食い違い得る (参照行の表記は同じ値の組でのみ正しい)。
        return SyncResult(
            SyncStatus.UNKNOWN,
            config_path,
            pinned_versions=result.pinned_versions,
            detail="hub の最新リリースを解決できません",
        )
    try:
        text = config_path.read_text(encoding="utf-8")
        config_path.write_text(
            _rewrite(text, version, digest, _target_major()), encoding="utf-8"
        )
    except OSError as exc:
        return SyncResult(
            SyncStatus.UNKNOWN, config_path, detail=f"設定を書けません: {exc}"
        )
    return SyncResult(
        SyncStatus.IN_SYNC,
        config_path,
        target_version=version,
        target_digest=digest,
        pinned_versions=result.pinned_versions,
        detail=f"v{version} へ更新しました",
    )


def warn_if_out_of_sync() -> None:
    """Gate 1 フックの先頭で wheel 参照のドリフトを警告する (fail-open・Issue #147).

    CI では書き換える相手が無いため、``load_config()`` より先にここで判定して戻る。
    設定は書き換えない (実行中の pre-commit と食い違うため)。失敗しても例外を出さず
    コミット可否に影響させない。待ち時間も開発体験を損なうため、タイムアウトを短くし
    解決結果を TTL 付きでキャッシュする。
    """
    if os.environ.get("GITHUB_ACTIONS") == "true":
        return
    # AHEAD (固定版が最新より新しい) は書き換えも警告も不要なため黙って戻る。
    result = inspect(
        paths.project_root() / ".pre-commit-config.yaml",
        use_cache=True,
        timeout=_HOOK_TIMEOUT_SECONDS,
    )
    if result.status is not SyncStatus.DRIFT:
        return
    print(
        f"[config-sync] Gate 1 の wheel 参照が hub の最新リリースではありません "
        f"({result.detail})。`ame-ai-reviewer sync` で更新できます (Issue #147)。",
        file=sys.stderr,
    )


def cmd_sync(args: argparse.Namespace) -> int:
    """``ame-ai-reviewer sync`` のエントリポイント (Issue #147).

    終了コードは drift (更新すべき) と解決不能 (要調査) を区別する。``--check`` は検出のみで、
    ドリフトがあれば exit 1、判定できなければ exit 2 を返す (CI のゲートで誤検知しないため)。
    固定版が hub の最新より新しい場合は書き換えず、理由を stderr に出して exit 0 を返す。
    """
    config_path = paths.project_root() / ".pre-commit-config.yaml"
    result = sync(config_path, write=not args.check)
    prefix = "[config-sync]"
    if result.status is SyncStatus.IN_SYNC:
        print(f"{prefix} 同期済み ({result.detail or f'v{result.target_version}'})")
        return 0
    if result.status is SyncStatus.ABSENT:
        print(f"{prefix} 同期対象なし ({result.detail})")
        return 0
    if result.status is SyncStatus.AHEAD:
        # 更新も不要だが、黙って見逃さないよう理由を出す (存在しない版の固定など)。
        print(f"{prefix} 対象外: {result.detail}", file=sys.stderr)
        return 0
    if result.status is SyncStatus.DRIFT:
        print(f"{prefix} 差分あり: {result.path} — {result.detail}", file=sys.stderr)
        print(
            f"{prefix} `ame-ai-reviewer sync` で更新してください (--check は書き換えません)。",
            file=sys.stderr,
        )
        return _EXIT_DRIFT
    print(f"{prefix} 判定できません: {result.detail}", file=sys.stderr)
    return _EXIT_UNRESOLVED
