"""``ame-ai-reviewer init`` サブコマンド: 配布先に必要なファイルを生成する.

pip インストールされたパッケージのテンプレート (``templates/``) を基に、
プロジェクトローカルへ以下を配置する:

- ``.ame-review/config.json`` / ``review_prompt.txt`` (プロジェクト固有設定)
- ``.pre-commit-config.yaml`` (preset 選択式の静的解析 + AI レビュー)
- ``.github/workflows/review_command.yml`` / ``review_reply.yml``
  (reusable workflow を呼ぶ薄いラッパ)

Gate 1 の AI フックは既定で ``language: python`` + wheel 参照 (``additional_dependencies``
に URL + ``#sha256=`` を埋め込み) で生成し、絶対パスを排除する (Issue #79/#84)。
``--python`` (または ``AME_INIT_PYTHON``) を指定するとオフライン向けに
``language: system`` で生成する (Issue #66)。

idempotent: 既存ファイルは上書きしない。``--force`` で上書きする。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.request
from typing import TYPE_CHECKING, Any, cast

from . import __version__, paths

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

# Gate 1 の AI フックを 2 方式でレンダリングするためのプレースホルダ (Issue #79)。
#   1. 既定: ``language: python`` + ``additional_dependencies`` (wheel URL + #sha256)。
#      絶対パスを埋め込まず、各環境で pre-commit が venv を自動作成する。
#   2. ``--python`` / ``AME_INIT_PYTHON`` 指定時: ``language: system``。
#      オフライン環境向けに実インタープリタパスを埋め込む (Issue #66 の後継)。
_AI_HOOK_ENTRY = "__AI_HOOK_ENTRY__"
_AI_LANGUAGE = "__AI_LANGUAGE__"
_AI_ADDEPS = "__AI_ADDEPS__"

# 配布元リポジトリの正規オーナー (旧個人アカウントから移転済み, Issue #100)。
_REPO_OWNER = "AME-Team"
_REPO_NAME = "AME-AI-Review-System"

# ワークフローテンプレート内のリポジトリ参照 (Issue #100)。
# オーナー移転時の更新漏れを防ぐため、URL にオーナーを直接書かず
# __REPO__ プレースホルダを init 生成時に _REPO_OWNER/_REPO_NAME で置換する。
_REPO_PLACEHOLDER = "__REPO__"
_REPO_FQN = f"{_REPO_OWNER}/{_REPO_NAME}"

# ``language: system`` 時に additional_dependencies の代わりに置く説明コメント。
_SYSTEM_ADDEPS_COMMENT = (
    "# オフライン: language: system は init --python で指定した"
    " Python の ame_ai_review_system を使用"
)

# Issue #114: エンジン別に追加する Python SDK (additional_dependencies へ)。
# claude のみ pre-commit の隔離 venv (language: python) に SDK が入らず
# ImportError で起動失敗する問題の対策。opencode は TS サイドカーで
# Python 依存が不要なためここには含めない。
_ENGINE_SDK_DEPS: dict[str, str] = {
    "claude": "claude-agent-sdk",
    "antigravity": "google-antigravity",
}

# system 方式で SDK が必要なエンジン向けのコメント注記 (Issue #114)。
_ENGINE_SDK_SYSTEM_COMMENTS: dict[str, str] = {
    "claude": "# 注意: claude エンジン利用時はこの Python に claude-agent-sdk を導入しておくこと",
    "antigravity": (
        "# 注意: antigravity エンジン利用時はこの Python に google-antigravity を"
        " 導入しておくこと"
    ),
}

# Issue #114: 指定可能なエンジンの正本 (main.py の --engine choices と共通)。
ENGINE_CHOICES = ("auto", "claude", "opencode", "antigravity")

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


def _resolve_python_bin(args: argparse.Namespace) -> str:
    """``--python`` / ``AME_INIT_PYTHON`` で指定された Python を解決する (Issue #66).

    優先順位: ``--python`` フラグ → ``AME_INIT_PYTHON`` 環境変数 → ``sys.executable``。
    ``language: system`` 方式 (オフライン向け) のときだけ使う。
    """
    explicit = getattr(args, "python", None)
    if explicit:
        return str(explicit)
    env_python = os.environ.get("AME_INIT_PYTHON")
    if env_python:
        return env_python
    return sys.executable


def _use_system_language(args: argparse.Namespace) -> bool:
    """``language: system`` 方式を使うか (``--python`` / ``AME_INIT_PYTHON`` 指定時)."""
    return bool(getattr(args, "python", None) or os.environ.get("AME_INIT_PYTHON"))


def _resolve_engine(args: argparse.Namespace) -> str:
    """Gate 1 の既定エンジンを解決する (``--engine`` / ``AME_INIT_ENGINE``).

    優先順位: ``--engine`` フラグ → ``AME_INIT_ENGINE`` 環境変数 → ``auto``。
    ``--engine`` の argparse 既定は ``None`` のため、未指定時のみ環境変数を参照する
    (既定を ``"auto"`` にすると環境変数が到達不能になる対策、Issue #114)。
    ``claude`` / ``antigravity`` は SDK 依存を追加する対象。不正値は fail-fast。
    """
    explicit = getattr(args, "engine", None)
    raw = explicit or os.environ.get("AME_INIT_ENGINE") or "auto"
    engine = str(raw).strip().lower()
    if engine not in ENGINE_CHOICES:
        print(
            f"ERROR: invalid engine {engine!r}. Choose from: {list(ENGINE_CHOICES)}",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return engine


def _resolve_version(args: argparse.Namespace) -> str:
    """Gate 1 フックが参照する wheel のバージョンを解決する.

    優先順位: ``--version`` フラグ → インストール済みパッケージの ``__version__``。
    既定は導入中パッケージのバージョン (リリースタグ ``v<version>`` と一致前提)。
    """
    explicit = getattr(args, "version", None)
    if explicit:
        return str(explicit).lstrip("v")
    return __version__


def _wheel_url(version: str) -> str:
    """バージョンに対応する配布 wheel のダウンロード URL を返す (Issue #79/#84)."""
    return (
        f"https://github.com/{_REPO_OWNER}/{_REPO_NAME}/releases/download/"
        f"v{version}/ame_ai_review_system-{version}-py3-none-any.whl"
    )


def _resolve_wheel_sha256(version: str) -> str | None:
    """GitHub API から wheel アセットの sha256 ダイジェストを解決する (Issue #84).

    リリースが未作成 / ネットワーク不可 / アセット不在の場合は ``None`` を返し、
    呼び出し側で ``#sha256=`` なしの URL にフォールバックする。
    """
    api_url = (
        f"https://api.github.com/repos/{_REPO_OWNER}/{_REPO_NAME}/releases/"
        f"tags/v{version}"
    )
    try:
        # API URL は固定の HTTPS ホストのみ。file:// 等のスキームは指定されない。
        req = urllib.request.Request(
            api_url,
            headers={"Accept": "application/vnd.github+json"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data: Any = json.loads(resp.read().decode("utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    release_data = cast("dict[str, Any]", data)
    asset_name = f"ame_ai_review_system-{version}-py3-none-any.whl"
    for asset in cast("list[dict[str, Any]]", release_data.get("assets", [])):
        if asset.get("name") != asset_name:
            continue
        digest = asset.get("digest")
        if isinstance(digest, str) and digest.startswith("sha256:"):
            return digest[len("sha256:") :]
    return None


def _render_preset(
    content: str,
    *,
    language: str,
    entry_prefix: str,
    addeps: str,
) -> str:
    """テンプレートの Gate 1 フック用プレースホルダをレンダリングする (Issue #79)."""
    return (
        content
        .replace(_AI_HOOK_ENTRY, entry_prefix)
        .replace(_AI_LANGUAGE, language)
        .replace(f"additional_dependencies: {_AI_ADDEPS}", addeps)
    )


def _verify_importable(python_bin: str) -> bool:
    """``python_bin`` で ``ame_ai_review_system`` が import 可能か検証する."""
    try:
        result = subprocess.run(
            [python_bin, "-c", "import ame_ai_review_system"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _print_import_help(python_bin: str) -> None:
    """``ame_ai_review_system`` が import できない場合の修正手順を表示する (Issue #66)."""
    print(
        "WARNING: ame_ai_review_system が指定の Python で import できません。\n"
        f"  Python: {python_bin}\n"
        "  Gate 1 (pre-commit AI フック) が動作しません。以下のいずれかで導入してください:\n"
        "    1. venv:  python -m venv .venv && . .venv/bin/activate && pip install <wheel>\n"
        "    2. uv:    uv tool install <wheel>\n"
        "    3. pipx:  pipx install <wheel>\n"
        "  その後、ame-ai-reviewer init --python <そのPythonのパス> を再実行してください。",
        file=sys.stderr,
    )


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
    preset_content = src.read_text(encoding="utf-8")

    if _use_system_language(args):
        # オフライン向け: language: system で実インタープリタパスを埋め込む (Issue #66)。
        python_bin = _resolve_python_bin(args)
        if " " in python_bin:
            print(
                "WARNING: Python パスに空白が含まれます。pre-commit の entry: は shlex "
                "分割するため空白入りパスは正常に起動できません。空白を含まないパス "
                "(シンボリックリンク等) を --python で指定してください (Issue #66)。",
                file=sys.stderr,
            )
        import_ok = _verify_importable(python_bin)
        if not import_ok:
            _print_import_help(python_bin)
            # 明示的な --python 指定で import 不可なら、壊れた Gate 1 設定を書き出さず
            # fail fast する。自動解決 (env/sys.executable) の場合は静的解析設定だけでも
            # 有用なため警告しつつ書き出す (Issue #66)。
            if args.python:
                return 1
        # Issue #114: system 方式でも SDK がエンジンで必要な場合はコメントで注記する。
        gate1_engine = _resolve_engine(args)
        sdk_comment = _ENGINE_SDK_SYSTEM_COMMENTS.get(gate1_engine)
        system_addeps = _SYSTEM_ADDEPS_COMMENT
        if sdk_comment:
            system_addeps = f"{system_addeps}\n    {sdk_comment}"
        preset_content = _render_preset(
            preset_content,
            language="system",
            entry_prefix=f"{python_bin} -m ",
            addeps=system_addeps,
        )
    else:
        # 既定: language: python + wheel (絶対パス非依存、各環境で venv 自動作成)。
        # 供給チェーン対策として wheel は #sha256= で内容を固定する (Issue #79/#84)。
        version = _resolve_version(args)
        dep = f"ame_ai_review_system @ {_wheel_url(version)}"
        sha256 = _resolve_wheel_sha256(version)
        if sha256:
            dep += f"#sha256={sha256}"
        else:
            print(
                f"WARNING: wheel v{version} の sha256 を解決できませんでした。"
                "#sha256= なしで生成します。供給チェーン対策のため、対応する release の"
                " sha256 を確認して .pre-commit-config.yaml を編集するか、"
                "--force で再生成してください (Issue #84)。",
                file=sys.stderr,
            )
        # 指摘対応: フックの削除/並べ替えで YAML アンカー (undefined alias) が破綻しないよう、
        # 各フックに同一の additional_dependencies を直接記述する。
        # Issue #114: engine=claude/antigravity 指定時は SDK を追加し、
        # pre-commit の隔離 venv でエンジンを起動可能にする。
        gate1_engine = _resolve_engine(args)
        sdk_dep = _ENGINE_SDK_DEPS.get(gate1_engine)
        addeps_line = f"          - {dep}"
        if sdk_dep:
            addeps_line += f"\n          - {sdk_dep}"
        preset_content = _render_preset(
            preset_content,
            language="python",
            entry_prefix="python -m ",
            addeps=f"additional_dependencies:\n{addeps_line}",
        )
        if sdk_dep:
            print(
                f"  Gate 1: engine={gate1_engine} → additional_dependencies に {sdk_dep} を追加しました。"
            )
        print(
            f"  Gate 1: language: python + wheel v{version}"
            f"{' (sha256 固定)' if sha256 else ''} で生成しました。"
        )
        print(
            "  (オフライン環境向けには --python <path> を指定すると "
            "language: system で生成します)"
        )
    _write(root / ".pre-commit-config.yaml", preset_content, force=args.force)

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
            content = (
                src
                .read_text(encoding="utf-8")
                .replace("__REF__", args.ref)
                .replace(_REPO_PLACEHOLDER, _REPO_FQN)
            )
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
