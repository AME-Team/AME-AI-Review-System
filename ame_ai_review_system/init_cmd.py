"""``ame-ai-reviewer init`` サブコマンド: 配布先に必要なファイルを生成する.

pip インストールされたパッケージのテンプレート (``templates/``) を基に、
プロジェクトローカルへ以下を配置する:

- ``.ame-review/config.json`` / ``review_prompt.txt`` (プロジェクト固有設定)
- ``.pre-commit-config.yaml`` (preset 選択式の静的解析 + AI レビュー)
- ``.github/workflows/review_command.yml`` / ``review_reply.yml``
  (reusable workflow を呼ぶ薄いラッパ)

idempotent: 既存ファイルは上書きしない。``--force`` で上書きする。
"""

from __future__ import annotations

import os
import shutil
import sys
from typing import TYPE_CHECKING

from . import paths

if TYPE_CHECKING:
    import argparse
    from pathlib import Path

# preset 名 → templates/precommit/ のファイル名。
_PRESETS: dict[str, str] = {
    "full": "full.yaml",
    "minimal": "minimal.yaml",
    "python": "python.yaml",
    "text": "text.yaml",
    "ts": "ts.yaml",
}

# .ame-review/ へ配置する既定ファイル (存在するテンプレートのみ)。
_AME_REVIEW_FILES = (
    "config.json",
    "review_prompt.txt",
)

# ワークフローテンプレート → 生成先ファイル名。
_WORKFLOW_FILES = (
    ("review-command-wrapper.yml", "review_command.yml"),
    ("review-reply-wrapper.yml", "review_reply.yml"),
)


def _templates_dir() -> Path:
    return paths.package_dir() / "templates"


_SKIP_DIRS = frozenset(
    {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build"},
)


def _repo_has_suffix(root: Path, suffixes: frozenset[str]) -> bool:
    """リポジトリ内に指定の拡張子のファイルが存在するかを判定する.

    node_modules / .git / venv 等をスキップして走査し、見つけたら即返す。
    """
    for _dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        if any(name.endswith(suffix) for name in filenames for suffix in suffixes):
            return True
    return False


def _resolve_preset(preset: str, root: Path) -> str:
    """Preset 名を解決する (Issue #69).

    ``auto`` (既定) のときは package.json と .ts/.tsx ソースの有無で判定する:
      - package.json があり .ts/.tsx があり .py が無い → ``ts``
      - それ以外 (Python 主体 / 混在 / どちらも無い) → ``full``
    Python 主体のリポジトリに package.json が付随していても Python ゲート (ruff/mypy)
    が消えないよう、.ts/.tsx の存在も併せて判定する (Issue #69)。
    明示指定された preset はそのまま返す。
    """
    if preset != "auto":
        return preset
    has_package_json = (root / "package.json").exists()
    has_ts = _repo_has_suffix(root, frozenset({".ts", ".tsx"}))
    has_py = _repo_has_suffix(root, frozenset({".py"}))
    if has_package_json and has_ts and not has_py:
        print("  package.json + .ts/.tsx detected; preset = ts")
        return "ts"
    if has_package_json and not has_ts:
        print("  package.json but no .ts/.tsx; preset = full (Python hooks kept)")
    else:
        print("  no .ts/.tsx; preset = full")
    return "full"


def _write(dst: Path, content: str, *, force: bool) -> bool:
    if dst.exists() and not force:
        print(f"  skip (exists): {dst}")
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(content, encoding="utf-8")
    print(f"  write: {dst}")
    return True


def _copy_template(src: Path, dst: Path, *, force: bool) -> bool:
    if dst.exists() and not force:
        print(f"  skip (exists): {dst}")
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"  write: {dst}")
    return True


def cmd_init(args: argparse.Namespace) -> int:
    root = paths.project_root()
    print(f"Initializing AME AI Review System in {root}")

    # .ame-review/ へ既定ファイルを配置 (ユーザー固有設定は config.user.json で上書き)。
    ame_dir = paths.ame_review_dir()
    ame_dir.mkdir(parents=True, exist_ok=True)
    for name in _AME_REVIEW_FILES:
        src = _templates_dir() / "ame-review" / name
        if not src.exists():
            continue
        _copy_template(src, ame_dir / name, force=args.force)

    # .pre-commit-config.yaml を preset から生成。
    preset_name = _resolve_preset(args.preset, root)
    preset_file = _PRESETS.get(preset_name, _PRESETS["full"])
    src = _templates_dir() / "precommit" / preset_file
    if not src.exists():
        print(f"ERROR: preset template not found: {src}", file=sys.stderr)
        return 1
    _copy_template(src, root / ".pre-commit-config.yaml", force=args.force)

    # CI ラッパワークフローを生成 (reusable workflow 呼び出し)。
    if not args.no_workflow:
        if not args.ref:
            print(
                "ERROR: --ref is required unless --no-workflow "
                "(use a release tag, e.g. --ref v1.0.0)",
                file=sys.stderr,
            )
            return 1
        workflows_dir = root / ".github" / "workflows"
        for tmpl_name, out_name in _WORKFLOW_FILES:
            src = _templates_dir() / "workflow" / tmpl_name
            if not src.exists():
                print(f"ERROR: workflow template not found: {src}", file=sys.stderr)
                return 1
            content = src.read_text(encoding="utf-8").replace("__REF__", args.ref)
            _write(workflows_dir / out_name, content, force=args.force)

    # engines-ts の展開 + npm install (オプション)。
    if args.with_engines:
        print("Installing TypeScript SDK sidecar (engines-ts)...")
        try:
            dst = paths.ensure_engines_ts()
        except SystemExit as exc:
            print(f"  ERROR: {exc}", file=sys.stderr)
            return 1
        print(f"  OK: {dst}")

    print("Done. Next steps:")
    print("  1. レビュー用 GitHub App をリポジトリにインストールし Secrets を設定する")
    print("  2. 必要な静的解析ツールを導入する (preset は .pre-commit-config.yaml)")
    print("  3. pre-commit フックを登録する: pre-commit install")
    return 0
