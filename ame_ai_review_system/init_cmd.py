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

生成する CI ラッパは ``--ref`` (既定 :data:`DEFAULT_REF` = 現行バージョンの移動メジャータグ)
を参照する。移動タグは hub のリリースへ自動追随するため、配布先での更新作業は
不要である。

idempotent: 既存ファイルは上書きしない。``--force`` で上書きする。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple, cast

from . import __version__, paths

if TYPE_CHECKING:
    import argparse

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

# 配布先ラッパが参照する既定 ref。移動メジャータグ (moving major tag) を __version__ から
# 導出することで、リリース時に実際に付け替えられるタグと常に一致させる。
#   - `.github/workflows/release.yml` は push されたタグのメジャー成分を付け替える。
#   - ここを定数で持つと、メジャーが変わった時に配布先が解決不能な ref を参照する。
# 特定バージョンへ固定したい場合のみ ``--ref vX.Y.Z`` を明示する。
DEFAULT_REF = f"v{__version__.split('.')[0]}"

# ``language: system`` 時に additional_dependencies の代わりに置く説明コメント。
_SYSTEM_ADDEPS_COMMENT = (
    "# オフライン: language: system は init --python で指定した"
    " Python の ame_ai_review_system を使用"
)

# Issue #114: エンジン別に追加する Python SDK (additional_dependencies へ)。
# pre-commit の隔離 venv (language: python) には wheel のみが入るため、
# SDK を個別に追加しておかないと claude / antigravity は ImportError で
# 起動失敗する。opencode は TS サイドカーで Python 依存が不要なためここには含めない。
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

# Issue #114: 指定可能なエンジン一覧の単一情報源 (main.py の --engine choices と共通)。
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


def _resolve_engine(args: argparse.Namespace) -> str | None:
    """Gate 1 の既定エンジンを解決する (``--engine`` / ``AME_INIT_ENGINE``).

    優先順位: ``--engine`` フラグ → ``AME_INIT_ENGINE`` 環境変数 → ``auto``。
    ``--engine`` の argparse 既定は ``None`` のため、未指定時のみ環境変数を参照する
    (既定を ``"auto"`` にすると環境変数が到達不能になる対策、Issue #114)。
    ``claude`` / ``antigravity`` は SDK 依存を追加する対象。不正値は ``None`` を返し、
    呼び出し側 (cmd_init) が ``return 1`` で fail-fast する (他の検証と同一方針)。
    """
    explicit = getattr(args, "engine", None)
    raw = explicit or os.environ.get("AME_INIT_ENGINE") or "auto"
    engine = str(raw).strip().lower()
    if engine not in ENGINE_CHOICES:
        print(
            f"ERROR: invalid engine {engine!r}. Choose from: {list(ENGINE_CHOICES)}",
            file=sys.stderr,
        )
        return None
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


def repo_fqn() -> str:
    """Hub の ``owner/name`` を返す (workflow の uses: と URL の単一情報源)."""
    return _REPO_FQN


def wheel_url(version: str) -> str:
    """バージョンに対応する配布 wheel のダウンロード URL を返す (Issue #79/#84).

    ``config_sync`` も同じ URL を生成するため公開する (表記が 2 箇所で分岐すると
    同期判定が常に DRIFT になる)。
    """
    return (
        f"https://github.com/{_REPO_OWNER}/{_REPO_NAME}/releases/download/"
        f"v{version}/ame_ai_review_system-{version}-py3-none-any.whl"
    )


def wheel_asset_digest(release: dict[str, Any], version: str) -> str | None:
    """Release のアセット一覧から wheel の sha256 ダイジェストを取り出す (Issue #84).

    ``config_sync`` はリリース一覧 API の応答をそのまま渡すため、抽出だけを切り出して
    単一情報源にする。
    """
    asset_name = f"ame_ai_review_system-{version}-py3-none-any.whl"
    for asset in cast("list[dict[str, Any]]", release.get("assets", [])):
        if asset.get("name") != asset_name:
            continue
        digest = asset.get("digest")
        if isinstance(digest, str) and digest.startswith("sha256:"):
            return digest[len("sha256:") :]
    return None


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
    return wheel_asset_digest(cast("dict[str, Any]", data), version)


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

# Issue #142: 既存ファイル走査専用の除外集合。``_SKIP_DIRS`` を拡張して共有すると、
# プリセット自動判定 (``_repo_has_suffix``) の判定結果まで変わるため別集合にする。
#   - ``.ame-review`` は init 自身が直前に生成するため、config.json を「JSON あり」と
#     誤検出しないよう除外する。
#   - キャッシュ / ビルド生成物は git 管理外のことが多く、``.gitignore`` 済みの
#     ファイルを種別として数えないための保険 (git が無い環境のフォールバック用)。
_SCAN_SKIP_DIRS = _SKIP_DIRS | frozenset(
    {
        ".ame-review",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        ".tox",
        ".nox",
        ".eggs",
        ".cache",
        "htmlcov",
        "coverage",
        "target",
        ".next",
        ".nuxt",
        ".turbo",
        "site",
    },
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


# Issue #142: init 時にリポジトリ内の既存ファイル構成を走査し、言語プリセットが
# 持たない共通衛生フック (Markdown / YAML / JSON 等) を補う。拡張子 → 種別の対応を
# 単一情報源にし、検出と追加判定の両方から参照する。
_SUFFIX_KINDS: dict[str, str] = {
    ".md": "markdown",
    ".markdown": "markdown",
    # .mdx は JSX 構文を含み markdownlint が失敗するため対象外 (レビュー指摘対応)。
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
}

# ロックファイルと TS エンジンサイドカーは生成物 (手で整形しない) のため、
# 行末空白 / EOF 修正の対象から外す。codespell の exclude と同じ並びに揃える。
# 値は素の正規表現で持ち、YAML へ書くときにバックスラッシュを二重化する
# (_yaml_quote)。テストからそのまま re で検証できるよう単一情報源にする。
_BASE_HOOKS_EXCLUDE = (
    r"(pnpm-lock\.yaml|package-lock\.json|yarn\.lock)$|^\.ame-review/engines-ts/"
)

# check-json は json.load による厳密検査のため、コメント / 末尾カンマを含む JSONC
# (tsconfig.json, .vscode/*.json, devcontainer.json) があると初回から失敗する。
# 既存リポジトリへ後付けするフックなので、既知の JSONC は除外する (レビュー指摘対応)。
_JSONC_EXCLUDE = (
    r"(^|/)(tsconfig|jsconfig)(\.[^/]*)?\.json$|(^|/)\.vscode/"
    r"|(^|/)devcontainer\.json$"
)

# check-yaml は 1 ドキュメント前提のため、`---` 区切りの複数ドキュメントや Helm /
# Ansible / Jinja のテンプレートで初回から失敗する。複数ドキュメントを許可し、
# テンプレート系のパスは除外する (レビュー指摘対応)。
_YAML_TEMPLATE_EXCLUDE = r"(^|/)(charts|templates)/|\.(j2|jinja2?)$"


def _yaml_quote(text: str) -> str:
    """正規表現を YAML の double-quoted scalar として安全に埋め込む."""
    return '"' + text.replace("\\", "\\\\") + '"'


_BASE_HOOKS_HEADER = """\
  # =========================================================================
  # Issue #142: init がリポジトリ内の既存ファイルを走査して追加した共通衛生フック
  #   検出したファイル種別: {kinds}
  # 言語プリセットに含まれない種別だけを追加する。行末空白 / 末尾改行 / 大容量 /
  # コンフリクトマーカーは種別に依らず追加する。YAML は構文検査のみのため、
  # actionlint 等が必要なら手動で追加すること。JSON は既知の JSONC (tsconfig 等) を
  # 除外して検査する。
  # 不要な場合は `ame-ai-reviewer init --no-base-hooks` で生成し直すこと。
  # =========================================================================
"""


class _BaseHook(NamedTuple):
    """共通衛生フック 1 件の定義 (Issue #142)."""

    hook_id: str
    # この種別が検出されたときだけ追加する (空集合 = 常に追加)。
    requires: frozenset[str] = frozenset()
    # これらのフック id がプリセットに含まれていれば追加しない (同等以上とみなす)。
    satisfied_by: frozenset[str] = frozenset()
    # args は YAML フロー配列の本文 (例: "[--fix]")、exclude は正規表現本文。
    args: str = ""
    exclude: str = ""

    def render(self) -> str:
        """1 件の hook エントリを ``.pre-commit-config.yaml`` の断片へ整形する."""
        lines = [f"      - id: {self.hook_id}"]
        if self.args:
            lines.append(f"        args: {self.args}")
        if self.exclude:
            lines.append(f"        exclude: {_yaml_quote(self.exclude)}")
        return "\n".join(lines) + "\n"


class _BaseRepo(NamedTuple):
    """共通衛生フックを提供する pre-commit リポジトリ 1 件 (Issue #142)."""

    repo: str
    rev: str
    hooks: tuple[_BaseHook, ...]


# 追加するフックの並び (順序 = 生成物での並び)。pre-commit-hooks は
# `language: python` のため追加ツール無しで動く。markdownlint は `language: node`
# で、hook 用 env は pre-commit が作るため npm install は不要 (node のみ必要)。
_BASE_HOOK_REPOS: tuple[_BaseRepo, ...] = (
    _BaseRepo(
        "https://github.com/pre-commit/pre-commit-hooks",
        "v6.0.0",
        (
            _BaseHook("check-added-large-files"),
            _BaseHook("check-merge-conflict"),
            _BaseHook("trailing-whitespace", exclude=_BASE_HOOKS_EXCLUDE),
            _BaseHook("end-of-file-fixer", exclude=_BASE_HOOKS_EXCLUDE),
            _BaseHook(
                "check-yaml",
                requires=frozenset({"yaml"}),
                # yamllint は YAML を構文 + スタイルで検査する上位互換。
                satisfied_by=frozenset({"yamllint"}),
                args="[--allow-multiple-documents]",
                exclude=_YAML_TEMPLATE_EXCLUDE,
            ),
            _BaseHook(
                "check-json",
                requires=frozenset({"json"}),
                # prettier は types_or に json を含み、構文不正なら失敗する。
                satisfied_by=frozenset({"prettier"}),
                exclude=_JSONC_EXCLUDE,
            ),
        ),
    ),
    _BaseRepo(
        "https://github.com/igorshubovych/markdownlint-cli",
        "v0.49.1",
        (
            _BaseHook(
                "markdownlint",
                requires=frozenset({"markdown"}),
                # 既存の Markdown リンタがあれば重複させない。
                satisfied_by=frozenset(
                    {"markdownlint", "markdownlint-cli2", "textlint"},
                ),
                args="[--fix]",
            ),
        ),
    ),
)


def _git_listed_files(root: Path) -> list[str] | None:
    """Git 管理下のファイル一覧を返す (追跡済み + 未追跡・非 ignore).

    ``.gitignore`` を尊重することで、キャッシュやビルド生成物に含まれる ``.json`` を
    「JSON ファイルあり」と誤検出しない (Issue #142 レビュー指摘対応)。git リポジトリ
    でない / git が無い場合は ``None`` を返し、呼び出し側が os.walk へフォールバックする。
    """
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=root,
            capture_output=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    # 非 UTF-8 のファイル名 (Shift-JIS 等) でも UnicodeDecodeError で init 全体を
    # 落とさないよう surrogateescape で復号する (レビュー指摘対応)。
    decoded = result.stdout.decode("utf-8", errors="surrogateescape")
    return [name for name in decoded.split("\0") if name]


def _iter_repo_files(root: Path) -> list[str]:
    """走査対象のファイル名一覧を返す (Issue #142).

    git 管理下では ``git ls-files`` を使う (``.gitignore`` 済みの生成物を拾わない)。
    使えない場合のみ ``_SCAN_SKIP_DIRS`` で間引いた os.walk にフォールバックする。
    どちらの経路でも ``_SCAN_SKIP_DIRS`` 配下は除外する。``.ame-review`` は init 自身が
    直前に生成するため、git 未追跡でも種別として数えない。
    """
    listed: list[str] | None = _git_listed_files(root)
    if listed is None:
        walked: list[str] = []
        for _dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in _SCAN_SKIP_DIRS]
            walked.extend(filenames)
        listed = walked
    return [
        name
        for name in listed
        if not _SCAN_SKIP_DIRS.intersection(Path(name).parts[:-1])
    ]


def _detect_file_kinds(root: Path) -> frozenset[str]:
    """リポジトリ内の既存ファイルから静的解析対象のファイル種別を検出する (Issue #142).

    拡張子は小文字化して比較する。
    """
    kinds = {
        kind
        for name in _iter_repo_files(root)
        if (kind := _SUFFIX_KINDS.get(Path(name).suffix.lower())) is not None
    }
    return frozenset(kinds)


def _render_base_hooks(
    kinds: frozenset[str],
    preset_content: str,
) -> tuple[str, tuple[str, ...]]:
    """検出した種別に応じた共通衛生フックの YAML ブロックを組み立てる (Issue #142).

    プリセットが既に同等以上のフックを持つ場合は追加しない (``satisfied_by``)。
    ``(ブロック, 追加した hook id の並び)`` を返す。追加が無ければブロックは空文字。
    """
    existing = set(re.findall(r"^\s*- id: (\S+)", preset_content, flags=re.MULTILINE))
    # プリセットが同じ repo を別 rev で持つ場合、同一 URL を二重に並べない
    # (hook env の二重インストール / rev 不整合を避ける。レビュー指摘対応)。
    existing_repos = set(
        re.findall(r"^\s*- repo: (\S+)\s*$", preset_content, flags=re.MULTILINE),
    )
    group_blocks: list[str] = []
    added: list[str] = []
    for group in _BASE_HOOK_REPOS:
        if group.repo in existing_repos:
            continue
        selected = [
            hook
            for hook in group.hooks
            if (not hook.requires or hook.requires <= kinds)
            and hook.hook_id not in existing
            and not hook.satisfied_by & existing
        ]
        if not selected:
            continue
        group_blocks.append(
            f"  - repo: {group.repo}\n    rev: {group.rev}\n    hooks:\n"
            + "".join(hook.render() for hook in selected)
            + "\n"
        )
        added.extend(hook.hook_id for hook in selected)
    if not group_blocks:
        return "", ()
    header = _BASE_HOOKS_HEADER.format(kinds=", ".join(sorted(kinds)) or "なし")
    return header + "".join(group_blocks), tuple(added)


def _insert_base_hooks(content: str, block: str) -> str | None:
    """``repos:`` の直後へ共通衛生フックのブロックを挿入する (Issue #142).

    言語プリセットのフックより先に評価させるため先頭へ置く。``fail_fast: true``
    のため、安価な衛生フックを先に走らせる方が無駄な実行を減らせる。
    挿入位置 (``repos:``) がテンプレートに無い場合は ``None`` を返す。フックが実際には
    入っていないのに「追加しました」と表示しないよう、成否を呼び出し側へ返す。
    """
    if not block:
        return content
    # 行頭一致で探す。`# repos:` のようなコメントや値の中の "repos:" にヒットすると
    # 不正な YAML を生成するため (レビュー指摘対応)。
    match = re.search(r"^repos:[ \t]*$", content, flags=re.MULTILINE)
    if match is None:
        return None
    line_end = content.find("\n", match.end())
    if line_end < 0:
        return f"{content}\n{block}"
    return content[: line_end + 1] + block + content[line_end + 1 :]


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
    # Issue #111: パッケージデータ同梱の欠落 (wheel ビルド設定の変更等) で生成物が
    # 無言でスキップされ、弱いプロンプトのまま運用されるのを防ぐ。コピー開始前に
    # 存在を検証して fail-fast する。空ディレクトリを含む部分的な init 状態を残さない
    # ため、mkdir は検証の後に行う。
    prompt_src = paths.package_dir() / "review_prompt.txt"
    if not prompt_src.exists():
        print(
            f"ERROR: {prompt_src} が存在しません。wheel ビルドで review_prompt.txt が"
            " パッケージデータとして同梱されているか確認してください (Issue #111)。",
            file=sys.stderr,
        )
        return 1
    ame_dir.mkdir(parents=True, exist_ok=True)
    for name in _AME_REVIEW_FILES:
        if name == "review_prompt.txt":
            # Issue #111: プロンプトはパッケージ同梱の review_prompt.txt を単一情報源とする。
            # templates/ame-review/ に旧版を持たせると init 生成物が弱い出力契約になり、
            # paths.prompt_path() が .ame-review/ を優先するため Gate 1/2 が弱い
            # プロンプトで実行される。生成物と既定のドリフトを防ぐためテンプレートは持たない。
            src = prompt_src
        else:
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

    # Issue #142: リポジトリ内の既存ファイルを走査し、プリセットが持たない共通衛生
    # フックを補う。走査は .ame-review 配下を除外するため、上で生成した config.json は
    # 検出対象にならない。minimal は「静的解析フックを持たない」明示的な選択のため
    # 対象外とし、--no-base-hooks で全プリセットから外せるようにする。
    if getattr(args, "no_base_hooks", False):
        print("  base hooks: 指定なし (--no-base-hooks)")
    elif _use_system_language(args):
        # --python / AME_INIT_PYTHON はオフライン前提の指定なので、remote リポジトリの
        # hook env を初回に取得する共通衛生フックは足さない (Issue #142 レビュー指摘対応)。
        print(
            "  base hooks: 追加しない (--python / AME_INIT_PYTHON はオフライン前提のため、"
            "リモート hook リポジトリを取得できません)"
        )
    elif preset_name == "minimal":
        print(
            "  base hooks: 追加しない (preset=minimal は静的解析フックを持たない選択)"
        )
    else:
        detected = _detect_file_kinds(root)
        base_block, base_added = _render_base_hooks(detected, preset_content)
        inserted = _insert_base_hooks(preset_content, base_block)
        detected_text = ", ".join(sorted(detected)) or "なし"
        if inserted is None:
            # テンプレートの書式が変わって repos: が見つからない場合。実際には何も
            # 入っていないので成功表示にしない (レビュー指摘対応)。
            print(
                "WARNING: .pre-commit-config.yaml のテンプレートに `repos:` が無いため、"
                f"共通衛生フック ({', '.join(base_added)}) を挿入できませんでした "
                "(Issue #142)。",
                file=sys.stderr,
            )
        else:
            preset_content = inserted
            if base_added:
                print(
                    f"  base hooks: 既存ファイルから検出 ({detected_text}) "
                    f"→ {', '.join(base_added)} を追加しました。"
                )
            else:
                print(
                    f"  base hooks: 追加なし (検出: {detected_text} / プリセットが既に網羅)"
                )

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
        if gate1_engine is None:
            return 1
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
        dep = f"ame_ai_review_system @ {wheel_url(version)}"
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
        if gate1_engine is None:
            return 1
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
                "ERROR: --ref が空です。移動メジャータグ (既定: "
                f"{DEFAULT_REF}) かリリースタグ (例: v0.2.15) を指定してください。",
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
