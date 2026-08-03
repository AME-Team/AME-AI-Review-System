"""プロジェクトローカル設定とパッケージ同梱デフォルトのリソースパス解決.

vendored 運用 (ame_ai_review_system/ をリポジトリへコピー) でリポジトリ非依存に
動くよう、各リソースは以下の優先順位で解決する:

1. 環境変数による明示上書き (``AME_REVIEW_CONFIG`` 等)
2. プロジェクトルートの ``.ame-review/`` 配下
3. パッケージ同梱のデフォルト (vendored 運用の後方互換)

プロジェクトルートは cwd から上方向へ ``.ame-review/`` → ``.git/`` の順で探索する。
"""

from __future__ import annotations

import filecmp
import os
import shutil
import subprocess
from pathlib import Path

_AME_REVIEW_DIR_NAME = ".ame-review"


def package_dir() -> Path:
    return Path(__file__).resolve().parent


def project_root() -> Path:
    override = os.environ.get("AME_REVIEW_PROJECT_ROOT")
    if override:
        return Path(override)

    cwd = Path.cwd()
    for candidate in (cwd, *cwd.parents):
        if (candidate / _AME_REVIEW_DIR_NAME).is_dir():
            return candidate
        if (candidate / ".git").exists():
            return candidate
    return cwd


def ame_review_dir() -> Path:
    return project_root() / _AME_REVIEW_DIR_NAME


def _first_existing(*candidates: Path) -> Path | None:
    for path in candidates:
        if path.exists():
            return path
    return None


def config_path() -> Path:
    override = os.environ.get("AME_REVIEW_CONFIG")
    if override:
        return Path(override)
    found = _first_existing(
        ame_review_dir() / "config.json",
        package_dir() / "config.json",
    )
    return found if found is not None else package_dir() / "config.json"


def user_config_path() -> Path:
    override = os.environ.get("AME_REVIEW_USER_CONFIG")
    if override:
        return Path(override)
    found = _first_existing(
        ame_review_dir() / "config.user.json",
        package_dir() / "config.user.json",
    )
    return found if found is not None else ame_review_dir() / "config.user.json"


def tracked_config_path() -> Path:
    # skip_guard 用: 環境変数や user 上書きを無視し版管理対象の config.json のみ参照する。
    found = _first_existing(
        ame_review_dir() / "config.json",
        package_dir() / "config.json",
    )
    return found if found is not None else package_dir() / "config.json"


def prompt_path() -> Path:
    found = _first_existing(
        ame_review_dir() / "review_prompt.txt",
        package_dir() / "review_prompt.txt",
    )
    return found if found is not None else package_dir() / "review_prompt.txt"


def semgrep_rules_path() -> Path:
    found = _first_existing(
        ame_review_dir() / ".semgrep" / "rules.yml",
        package_dir() / ".semgrep" / "rules.yml",
    )
    return found if found is not None else package_dir() / ".semgrep" / "rules.yml"


def state_dir() -> Path:
    return ame_review_dir() / "state"


def ensure_engines_ts() -> Path:
    """TypeScript SDK サイドカーをプロジェクトローカルへ展開し npm install する.

    pip install (site-packages 配下) では書き込み権限や更新の永続性が保証されないため、
    初回実行時に ``.ame-review/engines-ts/`` へコピーし、そこで依存を npm install する。
    ts_runner は ``.ame-review/engines-ts/`` を優先解決するため、既存の vendored 運用とも
    共存する (ts_runner._sidecar_path 参照)。
    """
    src = package_dir() / "engines" / "ts"
    dst_dir = ame_review_dir()
    dst = dst_dir / "engines-ts"

    if not dst.is_dir():
        if not src.is_dir():
            msg = f"TS sidecar source not found: {src}"
            raise SystemExit(msg)
        dst_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst)
    elif not _engines_ts_up_to_date(dst, src):
        # パッケージ更新で engines/ts が新しくなった場合は再展開する。
        # 古い .ame-review/engines-ts が残ると新エンジンと乖離するため。
        shutil.rmtree(dst)
        shutil.copytree(src, dst)

    if not (dst / "node_modules").is_dir():
        if shutil.which("npm") is None:
            msg = (
                "npm not found on PATH. TS SDK engines (opencode / claude-ts) "
                "require Node.js. Install Node.js first."
            )
            raise SystemExit(msg)
        try:
            subprocess.run(["npm", "install"], cwd=dst, check=True)
        except subprocess.CalledProcessError as exc:
            msg = f"npm install failed for TS sidecar: {exc}"
            raise SystemExit(msg) from exc

    return dst


def _engines_ts_up_to_date(dst: Path, src: Path) -> bool:
    """展開先がパッケージ同梱のサイドカーと一致するか判定する.

    ファイル群を再帰比較し、1 つでも差分があれば False。バージョン更新で古い
    ``.ame-review/engines-ts`` が残り、新エンジンと乖離するのを防ぐ。
    ``node_modules`` は npm 依存のローカル成果物のため比較対象から除外する。
    """
    return _dircmp_equal(src, dst, _excluded_subdirs={"node_modules"})


def _dircmp_equal(left: Path, right: Path, *, _excluded_subdirs: set[str]) -> bool:
    """2 ディレクトリを再帰的にバイト比較する."""
    comparison = filecmp.dircmp(left, right)
    left_only = [f for f in comparison.left_only if f not in _excluded_subdirs]
    right_only = [f for f in comparison.right_only if f not in _excluded_subdirs]
    if left_only or right_only or comparison.diff_files:
        return False
    return all(
        _dircmp_equal(
            Path(sub.left),
            Path(sub.right),
            _excluded_subdirs=_excluded_subdirs,
        )
        for name, sub in comparison.subdirs.items()
        if name not in _excluded_subdirs
    )
