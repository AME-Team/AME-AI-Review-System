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

``language: system`` で動かす導入先 (``init --python`` 方式・``uv run`` 方式) は wheel を
``pyproject.toml`` に参照し、sha256 は ``uv.lock`` が持つ。この形も ``sync`` の対象にし、
書き換え後は ``uv lock`` を実行してロックを追随させる (Issue #153)。参照を git 管理せず
仮想環境へ入れるだけの導入先には、インストール済みの版と hub の最新を突き合わせて警告する。
"""

from __future__ import annotations

import http.client
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    import argparse
    from pathlib import Path

from itertools import starmap

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

# ``language: system`` の導入先は wheel を pyproject.toml に参照する (sha256 は uv.lock 側)。
# ロックは ``uv lock`` で追随させる。解決に時間がかかり得るためタイムアウトを長めに取る。
# 依存名は PEP 503 で正規化して比較する (`ame_ai_review_system` 等の表記揺れを許す)。
_PACKAGE_NAME = "ame-ai-review-system"
_NAME_SEPARATORS_RE = re.compile(r"[-_.]+")
# TOML の文字列は二重引用符と単一引用符の両方が有効なので、どちらも受けて表記を保つ。
_PYPROJECT_LINE_RE = re.compile(
    r'^(?P<indent>\s*)(?P<quote>["\'])(?P<name>[A-Za-z0-9._-]+)\s*@\s*(?P<url>\S+?)'
    r"(?P=quote)(?P<comma>,?)(?P<trailing>\s*)$"
)
_UV_LOCK_TIMEOUT_SECONDS = 120

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


def _pyproject_path() -> Path:
    """``language: system`` の導入先が wheel を参照する ``pyproject.toml`` (Issue #153)."""
    return paths.project_root() / "pyproject.toml"


def _pyproject_matches(text: str, major: str) -> list[re.Match[str]]:
    """pyproject.toml の管理対象行 (対象メジャーのリリース URL を指す行のみ).

    依存の書き方は ``"ame-ai-review-system @ https://.../download/vX.Y.Z/<name>"`` (TOML なので
    単一引用符でもよい)。名前は ``-``/``_``/``.`` の揺れを許し (PEP 503)、引用符・末尾のカンマと
    空白は元の表記のまま保つ。
    """
    matches: list[re.Match[str]] = []
    for line in text.splitlines():
        match = _PYPROJECT_LINE_RE.match(line)
        if match is None or not _is_managed_package(match.group("name")):
            continue
        if not _is_target_series(match.group("url"), major):
            continue
        matches.append(match)
    return matches


def _normalize_package_name(name: str) -> str:
    """PEP 503 の依存名正規化 (``-``/``_``/``.`` を同一視し小文字化する)."""
    return _NAME_SEPARATORS_RE.sub("-", name).lower()


def _is_managed_package(name: str) -> bool:
    """依存名がこのパッケージを指すか (``ame_ai_review_system`` 等の揺れを許す)."""
    return _normalize_package_name(name) == _PACKAGE_NAME


def _desired_pyproject_line(match: re.Match[str], version: str, digest: str) -> str:
    """pyproject.toml の管理対象行の期待値 (名前・カンマ・空白は元の表記のまま).

    ``#sha256=`` を URL に書いている導入先は、その digest も新しいリリースのものへ更新する
    (書き換えでフラグメントを落としたり、古い hash を残したりしない)。
    """
    url = _desired_pyproject_url(match, version, digest)
    quote = match.group("quote")
    return (
        f"{match.group('indent')}{quote}{match.group('name')} @ {url}{quote}"
        f"{match.group('comma')}{match.group('trailing')}"
    )


def _desired_pyproject_url(match: re.Match[str], version: str, digest: str) -> str:
    """参照 URL の期待値 (フラグメントは ``sha256=`` だけ差し替え、他はそのまま残す)."""
    url = init_cmd.wheel_url(version)
    fragment = match.group("url").partition("#")[2]
    if not fragment:
        return url
    others = [part for part in fragment.split("&") if not part.startswith("sha256=")]
    if digest:
        others.insert(0, f"sha256={digest}")
    return f"{url}#{'&'.join(others)}" if others else url


def _write_text_atomic(path: Path, text: str) -> None:
    """同一ディレクトリへ書いてから置換する (部分書きで参照を壊さない).

    一時ファイル名は ``secrets`` で作る (予測できない)。権限は 0600 で作り、書いた直後に
    元ファイルと同じ権限へ広げる。最初から緩い権限で置かないため、書き込み中の内容が
    読まれることがない。置換は ``Path.replace`` なので、途中で落ちても元の参照はそのまま残る。
    """
    try:
        mode: int | None = stat.S_IMODE(path.stat().st_mode)
    except OSError:
        # 元ファイルの権限が読めない場合 (sync は既存ファイルだけを書き換えるため通常は
        # 起きない) は、緩めずに 0600 のまま置換する。
        mode = None
    temporary_path = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    handle = os.open(temporary_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        try:
            stream = os.fdopen(handle, "w", encoding="utf-8")
        except OSError:
            # fdopen に入れなかった場合だけ fd が残るため、ここで閉じる。
            os.close(handle)
            raise
        with stream:
            stream.write(text)
            if mode is not None:
                # umask の影響を受けずに元の権限へ合わせる。
                os.fchmod(stream.fileno(), mode)
        temporary_path.replace(path)
    finally:
        # 置換に成功していれば一時ファイルは残っていない (失敗時だけ残骸を消す)。
        temporary_path.unlink(missing_ok=True)


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
    except FileNotFoundError:
        # ファイルが無いのは異常ではない (pyproject 側だけに参照を持つ導入先など)。
        return SyncResult(
            SyncStatus.ABSENT,
            config_path,
            detail=".pre-commit-config.yaml がありません",
        )
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
        _write_text_atomic(
            config_path, _rewrite(text, version, digest, _target_major())
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


def _installed_version() -> str | None:
    """この環境にインストールされている review system の版 (無ければ ``None``).

    参照を git 管理しない導入先 (wheel を仮想環境へ直接入れる構成) では、git 上の参照を
    突き合わせても古さが分からない。インストール済みの版で判定する (Issue #153)。
    """
    try:
        from importlib.metadata import PackageNotFoundError, version
    except ImportError:  # pragma: no cover - 標準ライブラリなので通常は起きない
        return None
    try:
        return version("ame-ai-review-system")
    except PackageNotFoundError:
        return None


def _run_uv_lock(pyproject_path: Path) -> tuple[bool, str]:
    """pyproject.toml の書き換え後に ``uv lock`` を実行してロックを追随させる (Issue #153).

    参照 URL だけを書き換えると ``uv.lock`` の hash が古いまま残り、``uv sync`` が失敗する。
    実行ファイルは ``shutil.which`` で解決する (存在しない場合は理由を返す)。作業ディレクトリは
    ``pyproject.toml`` の親にする (project_root と一致しない構成でも正しいロックを更新する)。
    """
    uv = shutil.which("uv")
    if uv is None:
        return False, "`uv` が見つかりません。手動で `uv lock` を実行してください"
    try:
        completed = subprocess.run(
            [uv, "lock"],
            cwd=pyproject_path.parent,
            capture_output=True,
            text=True,
            timeout=_UV_LOCK_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"`uv lock` を実行できません: {exc}"
    if completed.returncode != 0:
        lines = (completed.stderr or completed.stdout or "").strip().splitlines()
        why = lines[-1] if lines else f"exit={completed.returncode}"
        return False, f"`uv lock` が失敗しました: {why}"
    return True, "uv.lock を更新しました"


def inspect_pyproject(
    pyproject_path: Path, *, use_cache: bool = False, timeout: int = _TIMEOUT_SECONDS
) -> SyncResult:
    """``pyproject.toml`` の wheel 参照を検査する (書き換えない・system 構成向け).

    供給チェーン保護のため参照 URL はテキスト完全一致で判定する。``uv.lock`` の hash は
    ``sync`` が実行する ``uv lock`` が追随させる。
    """
    try:
        text = pyproject_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return SyncResult(
            SyncStatus.ABSENT, pyproject_path, detail="pyproject.toml がありません"
        )
    except OSError as exc:
        return SyncResult(
            SyncStatus.UNKNOWN, pyproject_path, detail=f"設定を読めません: {exc}"
        )
    major = _target_major()
    matches = _pyproject_matches(text, major)
    if not matches:
        return SyncResult(
            SyncStatus.ABSENT,
            pyproject_path,
            detail="pyproject.toml に管理対象の wheel 参照がありません (別メジャー固定は対象外)",
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
            pyproject_path,
            pinned_versions=pinned,
            detail=f"v{major} 系列の最新リリースを解決できません",
        )
    version, digest = target
    target_order = _version_order(version)
    if target_order is not None and any(
        (order := _version_order(pinned_version)) is None or order > target_order
        for pinned_version in pinned
    ):
        return SyncResult(
            SyncStatus.AHEAD,
            pyproject_path,
            pinned_versions=pinned,
            detail=f"固定版が hub の最新 (v{version}) より新しいため対象外です",
        )
    actual = [match.group(0) for match in matches]
    desired = [_desired_pyproject_line(match, version, digest) for match in matches]
    if actual == desired:
        return SyncResult(
            SyncStatus.IN_SYNC,
            pyproject_path,
            target_version=version,
            target_digest=digest,
            pinned_versions=pinned,
        )
    return SyncResult(
        SyncStatus.DRIFT,
        pyproject_path,
        target_version=version,
        target_digest=digest,
        pinned_versions=pinned,
        detail=f"参照 {', '.join(pinned) or '不明'} → v{version} へ更新できます",
    )


def _rewrite_pyproject(text: str, version: str, digest: str, major: str) -> str:
    """pyproject.toml の管理対象行だけを書き換える (別メジャー固定は触らない)."""
    out: list[str] = []
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        ending = line[len(body) :]
        match = _PYPROJECT_LINE_RE.match(body)
        if match is None or not _is_managed_package(match.group("name")):
            out.append(line)
            continue
        if not _is_target_series(match.group("url"), major):
            out.append(line)
            continue
        out.append(f"{_desired_pyproject_line(match, version, digest)}{ending}")
    return "".join(out)


def sync_pyproject(pyproject_path: Path, *, write: bool) -> SyncResult:
    """``pyproject.toml`` の wheel 参照を hub の最新リリースへ同期する (system 構成向け).

    書き換えた場合は ``uv lock`` を実行し、ロックの hash も追随させる。``--check`` は
    判定のみで書き換えも ``uv lock`` も行わない。
    """
    result = inspect_pyproject(pyproject_path)
    if result.status is not SyncStatus.DRIFT or not write:
        return result
    version, digest = result.target_version, result.target_digest
    if version is None or digest is None:
        return SyncResult(
            SyncStatus.UNKNOWN,
            pyproject_path,
            pinned_versions=result.pinned_versions,
            detail="hub の最新リリースを解決できません",
        )
    try:
        text = pyproject_path.read_text(encoding="utf-8")
        _write_text_atomic(
            pyproject_path, _rewrite_pyproject(text, version, digest, _target_major())
        )
    except OSError as exc:
        return SyncResult(
            SyncStatus.UNKNOWN, pyproject_path, detail=f"設定を書けません: {exc}"
        )
    try:
        locked, lock_detail = _run_uv_lock(pyproject_path)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        # uv 側の想定外の失敗でも、参照だけ書き換わった状態を残さない。
        locked, lock_detail = False, f"`uv lock` を実行できません: {exc}"
    if not locked:
        # 参照だけ書き換わってロックが古いままだと uv sync が失敗するため、書き戻して揃える。
        try:
            _write_text_atomic(pyproject_path, text)
        except OSError as exc:
            return SyncResult(
                SyncStatus.UNKNOWN,
                pyproject_path,
                pinned_versions=result.pinned_versions,
                detail=f"v{version} への更新後 {lock_detail} (書き戻しにも失敗しました: {exc})",
            )
        return SyncResult(
            SyncStatus.UNKNOWN,
            pyproject_path,
            pinned_versions=result.pinned_versions,
            detail=f"{lock_detail}。整合を保つため参照を書き戻しました",
        )
    return SyncResult(
        SyncStatus.IN_SYNC,
        pyproject_path,
        target_version=version,
        target_digest=digest,
        pinned_versions=result.pinned_versions,
        detail=f"v{version} へ更新しました ({lock_detail})",
    )


def warn_if_out_of_sync() -> None:
    """Gate 1 フックの先頭で wheel 参照のドリフトを警告する (fail-open・Issue #147).

    CI では書き換える相手が無いため、``load_config()`` より先にここで判定して戻る。
    設定は書き換えない (実行中の pre-commit と食い違うため)。失敗しても例外を出さず
    コミット可否に影響させない。待ち時間も開発体験を損なうため、タイムアウトを短くし
    解決結果を TTL 付きでキャッシュする。

    ``language: system`` の導入先は ``pyproject.toml`` の参照も見る。参照を git 管理せず
    仮想環境へ入れるだけの導入先では、インストール済みの版で古さを判定する (Issue #153)。
    AHEAD (固定版が最新より新しい) は書き換えも警告も不要なため黙って戻る。
    """
    if os.environ.get("GITHUB_ACTIONS") == "true":
        return
    root = paths.project_root()
    results = (
        inspect(
            root / ".pre-commit-config.yaml",
            use_cache=True,
            timeout=_HOOK_TIMEOUT_SECONDS,
        ),
        inspect_pyproject(
            _pyproject_path(), use_cache=True, timeout=_HOOK_TIMEOUT_SECONDS
        ),
    )
    drifts = [result for result in results if result.status is SyncStatus.DRIFT]
    if drifts:
        for result in drifts:
            print(
                f"[config-sync] {result.path.name} の wheel 参照が hub の最新リリースでは"
                f"ありません ({result.detail})。`ame-ai-reviewer sync` で更新できます "
                "(Issue #147)。",
                file=sys.stderr,
            )
        return
    if any(result.status is SyncStatus.IN_SYNC for result in results):
        return
    installed = _installed_version()
    target = _resolve_target(
        _target_major(), use_cache=True, timeout=_HOOK_TIMEOUT_SECONDS
    )
    if installed is None or target is None:
        return
    installed_order = _version_order(installed)
    target_order = _version_order(target[0])
    if (
        installed_order is None
        or target_order is None
        or installed_order >= target_order
    ):
        return
    print(
        f"[config-sync] インストール済みの review system (v{installed}) が hub の最新 "
        f"(v{target[0]}) より古いです。環境を更新してください (Issue #153)。",
        file=sys.stderr,
    )


def _report(label: str, result: SyncResult) -> int:
    """1 つの参照先の判定を表示し、その終了コードを返す."""
    prefix = "[config-sync]"
    if result.status is SyncStatus.IN_SYNC:
        print(
            f"{prefix} {label}: 同期済み ({result.detail or f'v{result.target_version}'})"
        )
        return 0
    if result.status is SyncStatus.ABSENT:
        print(f"{prefix} {label}: 同期対象なし ({result.detail})")
        return 0
    if result.status is SyncStatus.AHEAD:
        # 更新も不要だが、黙って見逃さないよう理由を出す (存在しない版の固定など)。
        print(f"{prefix} {label}: 対象外: {result.detail}", file=sys.stderr)
        return 0
    if result.status is SyncStatus.DRIFT:
        print(
            f"{prefix} {label}: 差分あり: {result.path} — {result.detail}",
            file=sys.stderr,
        )
        print(
            f"{prefix} `ame-ai-reviewer sync` で更新してください (--check は書き換えません)。",
            file=sys.stderr,
        )
        return _EXIT_DRIFT
    print(f"{prefix} {label}: 判定できません: {result.detail}", file=sys.stderr)
    return _EXIT_UNRESOLVED


def cmd_sync(args: argparse.Namespace) -> int:
    """``ame-ai-reviewer sync`` のエントリポイント (Issue #147・#153).

    参照先は 2 つある。``.pre-commit-config.yaml`` の AI フックと、``language: system`` の
    導入先が wheel を指す ``pyproject.toml`` である。両方を同期し、終了コードは悪い方に
    合わせる (drift = 1 / 判定不能 = 2)。``--check`` は検出のみで書き換えない。
    ``pyproject.toml`` を書き換えた場合は ``uv lock`` でロックも追随させる。
    固定版が hub の最新より新しい場合は書き換えず、理由を stderr に出して exit 0 を返す。
    """
    root = paths.project_root()
    write = not args.check
    results = (
        ("pre-commit", sync(root / ".pre-commit-config.yaml", write=write)),
        ("pyproject", sync_pyproject(_pyproject_path(), write=write)),
    )
    return max(starmap(_report, results))
