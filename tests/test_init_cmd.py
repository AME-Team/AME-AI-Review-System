# pyright: basic
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

import pytest
from ame_ai_review_system import __version__, init_cmd, paths
from ame_ai_review_system import main as cli


def _make_args(**kwargs: object) -> argparse.Namespace:
    defaults: dict[str, object] = {
        "preset": "full",
        "ref": "main",
        "no_workflow": False,
        "with_engines": False,
        "force": False,
        "python": None,
        "version": None,
        "engine": "auto",
        "no_base_hooks": False,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def _init_in(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / ".git").mkdir()
    monkeypatch.setenv("AME_REVIEW_PROJECT_ROOT", str(tmp_path))
    return tmp_path


def _touch(root: Path, rel: str) -> None:
    """走査対象のダミーファイルを置く (Issue #142 の検出テスト用)."""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}" if rel.endswith(".json") else "# x\n", encoding="utf-8")


def _read_config(root: Path) -> str:
    return (root / ".pre-commit-config.yaml").read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    # 既定 (language: python) 方式のテストが GitHub API に依存しないよう固定ハッシュを返す。
    monkeypatch.setattr(init_cmd, "_resolve_wheel_sha256", lambda _version: "a" * 64)


def test_init_creates_expected_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _init_in(tmp_path, monkeypatch)
    assert init_cmd.cmd_init(_make_args()) == 0
    assert (root / ".ame-review" / "config.json").exists()
    assert (root / ".ame-review" / "review_prompt.txt").exists()
    assert (root / ".pre-commit-config.yaml").exists()
    assert (root / ".github" / "workflows" / "review_command.yml").exists()
    assert (root / ".github" / "workflows" / "review_reply.yml").exists()


def test_init_review_prompt_matches_package_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Issue #111: init が生成する .ame-review/review_prompt.txt はパッケージ同梱の
    # review_prompt.txt と同一であること。templates/ に旧版が残ると
    # paths.prompt_path() が .ame-review/ を優先するため、弱い出力契約で
    # Gate 1/2 が実行されてしまう。生成物と既定のドリフトを防ぐ。
    root = _init_in(tmp_path, monkeypatch)
    assert init_cmd.cmd_init(_make_args(no_workflow=True)) == 0
    generated = (root / ".ame-review" / "review_prompt.txt").read_text(
        encoding="utf-8",
    )
    package_default = (
        paths
        .package_dir()
        .joinpath("review_prompt.txt")
        .read_text(
            encoding="utf-8",
        )
    )
    assert generated == package_default
    assert "JSON オブジェクト 1 つのみ" in generated


def test_init_review_prompt_fails_fast_when_package_data_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Issue #111: パッケージデータとして review_prompt.txt が同梱されていない場合、
    # 無言でスキップせず fail-fast する。弱いプロンプトのまま運用されるのを防ぐ。
    root = _init_in(tmp_path, monkeypatch)
    empty_pkg = tmp_path / "empty-pkg"
    empty_pkg.mkdir()
    monkeypatch.setattr(paths, "package_dir", lambda: empty_pkg)
    assert init_cmd.cmd_init(_make_args(no_workflow=True)) == 1
    assert not (root / ".ame-review" / "review_prompt.txt").exists()


def test_init_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _init_in(tmp_path, monkeypatch)
    assert init_cmd.cmd_init(_make_args()) == 0
    cfg = root / ".ame-review" / "config.json"
    cfg.write_text("CUSTOM", encoding="utf-8")
    assert init_cmd.cmd_init(_make_args()) == 0
    assert cfg.read_text(encoding="utf-8") == "CUSTOM"


def test_init_force_overwrites(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _init_in(tmp_path, monkeypatch)
    assert init_cmd.cmd_init(_make_args()) == 0
    cfg = root / ".ame-review" / "config.json"
    cfg.write_text("CUSTOM", encoding="utf-8")
    assert init_cmd.cmd_init(_make_args(force=True)) == 0
    assert cfg.read_text(encoding="utf-8") != "CUSTOM"


def test_init_ref_replacement(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _init_in(tmp_path, monkeypatch)
    assert init_cmd.cmd_init(_make_args(ref="v1.2.3")) == 0
    wf = (root / ".github" / "workflows" / "review_command.yml").read_text(
        encoding="utf-8",
    )
    assert "@v1.2.3" in wf
    assert "system_ref: v1.2.3" in wf
    assert "__REF__" not in wf


def test_init_workflow_repo_placeholder_replaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Issue #100: __REPO__ が正規オーナー FQN に置換され、残らないこと。
    root = _init_in(tmp_path, monkeypatch)
    assert init_cmd.cmd_init(_make_args(ref="v1.2.3")) == 0
    for name in ("review_command.yml", "review_reply.yml"):
        wf = (root / ".github" / "workflows" / name).read_text(encoding="utf-8")
        assert "__REPO__" not in wf
        assert init_cmd._REPO_FQN in wf


def test_init_no_workflow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _init_in(tmp_path, monkeypatch)
    assert init_cmd.cmd_init(_make_args(no_workflow=True)) == 0
    assert not (root / ".github").exists()


def test_init_auto_preset_picks_ts_when_package_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Issue #69: package.json + .ts があれば auto は ts を選ぶ。
    root = _init_in(tmp_path, monkeypatch)
    (root / "package.json").write_text("{}", encoding="utf-8")
    (root / "src").mkdir()
    (root / "src" / "index.ts").write_text("export const x = 1;\n", encoding="utf-8")
    assert init_cmd.cmd_init(_make_args(preset="auto", no_workflow=True)) == 0
    cfg = (root / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert "eslint" in cfg


def test_init_auto_preset_keeps_python_for_py_repo_with_package_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Issue #69: Python 主体で package.json が付随しても .ts/.tsx が無ければ full
    # (ruff/mypy 等の Python ゲート) を選び、静かに ts へ置き換わらない。
    root = _init_in(tmp_path, monkeypatch)
    (root / "package.json").write_text("{}", encoding="utf-8")
    (root / "main.py").write_text("print(1)\n", encoding="utf-8")
    assert init_cmd.cmd_init(_make_args(preset="auto", no_workflow=True)) == 0
    cfg = (root / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert "ruff-pre-commit" in cfg
    assert "eslint" not in cfg


def test_init_auto_preset_picks_full_without_package_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _init_in(tmp_path, monkeypatch)
    assert init_cmd.cmd_init(_make_args(preset="auto", no_workflow=True)) == 0
    cfg = (root / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert "ruff-pre-commit" in cfg


def test_init_ts_preset_generates_ts_hooks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _init_in(tmp_path, monkeypatch)
    assert init_cmd.cmd_init(_make_args(preset="ts", no_workflow=True)) == 0
    cfg = (root / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert "eslint" in cfg
    assert "prettier" in cfg
    assert "pnpm-lock" in cfg


def test_init_empty_ref_fails_unless_no_workflow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # --ref の既定は移動メジャータグ (init_cmd.DEFAULT_REF)。空文字は明示的な指定ミス
    # として扱い、ref の無い (動かない) ラッパを書き出さず fail-fast する。
    _init_in(tmp_path, monkeypatch)
    assert init_cmd.cmd_init(_make_args(ref=None)) == 1
    assert init_cmd.cmd_init(_make_args(ref="")) == 1
    assert init_cmd.cmd_init(_make_args(ref=None, no_workflow=True)) == 0


def test_init_default_ref_generates_moving_major_tag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 既定 ref は移動メジャータグ。配布先は ref を書き換えずに hub のリリースへ追随する。
    root = _init_in(tmp_path, monkeypatch)
    assert init_cmd.cmd_init(_make_args(ref=init_cmd.DEFAULT_REF)) == 0
    cases = (
        ("review_command.yml", "review-command.yml"),
        ("review_reply.yml", "review-reply.yml"),
    )
    for out_name, template_name in cases:
        wf = (root / ".github" / "workflows" / out_name).read_text(encoding="utf-8")
        assert (
            f"uses: {init_cmd._REPO_FQN}/.github/workflows/{template_name}"
            f"@{init_cmd.DEFAULT_REF}" in wf
        )
        assert f"system_ref: {init_cmd.DEFAULT_REF}" in wf


def test_init_cli_ref_default_is_the_moving_major_tag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # CLI (main.py) の --ref 既定が単一情報源 init_cmd.DEFAULT_REF と一致し、
    # 既定でラッパが生成される (--ref は必須ではない) こと。
    captured: dict[str, object] = {}

    def fake_cmd_init(args: argparse.Namespace) -> int:
        captured["ref"] = args.ref
        return 0

    monkeypatch.setattr(init_cmd, "cmd_init", fake_cmd_init)
    assert cli.main(["init", "--no-workflow"]) == 0
    assert captured["ref"] == init_cmd.DEFAULT_REF


def test_init_embeds_python_bin_in_preset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # --python 指定時は language: system で実インタープリタを埋め込む (Issue #66/#79)。
    root = _init_in(tmp_path, monkeypatch)
    monkeypatch.setattr(init_cmd, "_verify_importable", lambda _p: True)
    custom = "/custom/venv/bin/python"
    assert init_cmd.cmd_init(_make_args(python=custom)) == 0
    cfg = (root / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert f"entry: {custom} -m ame_ai_review_system." in cfg
    assert "language: system" in cfg
    assert "__PYTHON_BIN__" not in cfg
    assert "__AI_HOOK_ENTRY__" not in cfg
    assert "__AI_LANGUAGE__" not in cfg


def test_init_python_bin_from_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # AME_INIT_PYTHON 指定時も language: system で生成する (Issue #66/#79)。
    root = _init_in(tmp_path, monkeypatch)
    monkeypatch.setenv("AME_INIT_PYTHON", "/env/python")
    monkeypatch.setattr(init_cmd, "_verify_importable", lambda _p: True)
    assert init_cmd.cmd_init(_make_args(python=None)) == 0
    cfg = (root / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert "entry: /env/python -m ame_ai_review_system." in cfg
    assert "language: system" in cfg


def test_init_falls_back_to_sys_executable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # --python / AME_INIT_PYTHON が無い場合は既定の language: python (wheel) 方式で
    # 生成され、絶対パス (sys.executable) を埋め込まない (Issue #79)。
    root = _init_in(tmp_path, monkeypatch)
    monkeypatch.delenv("AME_INIT_PYTHON", raising=False)
    assert init_cmd.cmd_init(_make_args(python=None)) == 0
    cfg = (root / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert "language: python" in cfg
    assert "entry: python -m ame_ai_review_system." in cfg
    assert sys.executable not in cfg


def test_init_default_python_mode_embeds_pinned_wheel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Issue #79/#84: 既定方式は wheel URL + #sha256= を各フックの
    # additional_dependencies に埋め込み、絶対パスを含まない。
    root = _init_in(tmp_path, monkeypatch)
    assert init_cmd.cmd_init(_make_args(python=None)) == 0
    cfg = (root / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    wheel = f"ame_ai_review_system-{__version__}-py3-none-any.whl"
    assert f"{wheel}#sha256=aaaaaaaaaaaaaaaa" in cfg
    assert "ame-wheel-dep" not in cfg


def test_init_engine_claude_adds_claude_sdk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Issue #114: --engine claude 時は additional_dependencies へ claude-agent-sdk を追加し、
    # pre-commit の隔離 venv で claude エンジンを起動可能にする。
    root = _init_in(tmp_path, monkeypatch)
    assert init_cmd.cmd_init(_make_args(engine="claude")) == 0
    cfg = (root / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert cfg.count("claude-agent-sdk") == 3  # 3 フックすべてに追加
    assert "google-antigravity" not in cfg


def test_init_engine_antigravity_adds_sdk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Issue #114: --engine antigravity 時は google-antigravity を追加する。
    root = _init_in(tmp_path, monkeypatch)
    assert init_cmd.cmd_init(_make_args(engine="antigravity")) == 0
    cfg = (root / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert cfg.count("google-antigravity") == 3
    assert "claude-agent-sdk" not in cfg


def test_init_engine_auto_and_opencode_no_python_sdk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Issue #114: auto/opencode は Python SDK を追加しない (opencode は TS サイドカー)。
    for i, engine in enumerate(("auto", "opencode")):
        root = tmp_path / f"case{i}"
        root.mkdir()
        _init_in(root, monkeypatch)
        assert init_cmd.cmd_init(_make_args(engine=engine)) == 0
        cfg = (root / ".pre-commit-config.yaml").read_text(encoding="utf-8")
        assert "claude-agent-sdk" not in cfg
        assert "google-antigravity" not in cfg


def test_init_engine_from_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Issue #114: AME_INIT_ENGINE 環境変数でも engine を指定できる。
    monkeypatch.setenv("AME_INIT_ENGINE", "claude")
    root = _init_in(tmp_path, monkeypatch)
    assert init_cmd.cmd_init(_make_args(engine=None)) == 0
    cfg = (root / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert cfg.count("claude-agent-sdk") == 3


def test_init_invalid_engine_fails_fast(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Issue #114: 不正な engine は fail-fast する (return 1)。
    root = _init_in(tmp_path, monkeypatch)
    assert init_cmd.cmd_init(_make_args(engine="gemini")) == 1
    assert not (root / ".pre-commit-config.yaml").exists()


def test_init_default_python_mode_all_hooks_self_contained(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 指摘対応: YAML アンカーに依存せず、3 フックそれぞれに直接 wheel を記述する。
    # これによりフック削除・並べ替えでも .pre-commit-config.yaml のロードが破綻しない。
    root = _init_in(tmp_path, monkeypatch)
    assert init_cmd.cmd_init(_make_args(python=None)) == 0
    cfg = (root / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert cfg.count("ame_ai_review_system @ https://github.com/") == 3


def test_init_version_flag_controls_wheel_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # --version で参照する wheel バージョンを上書きできる (Issue #84)。
    root = _init_in(tmp_path, monkeypatch)
    assert init_cmd.cmd_init(_make_args(python=None, version="v9.9.9")) == 0
    cfg = (root / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert "ame_ai_review_system-9.9.9-py3-none-any.whl#sha256=" in cfg


def test_init_wheel_sha256_unresolvable_omits_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # sha256 解決に失敗したら #sha256= なしで生成し、警告する (Issue #84)。
    root = _init_in(tmp_path, monkeypatch)
    monkeypatch.setattr(init_cmd, "_resolve_wheel_sha256", lambda _version: None)
    assert init_cmd.cmd_init(_make_args(python=None)) == 0
    cfg = (root / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    wheel = f"ame_ai_review_system-{__version__}-py3-none-any.whl"
    assert wheel in cfg
    assert "whl#sha256=" not in cfg


def test_init_system_mode_does_not_require_import_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 既定 (language: python) 方式は import 検証を必要としない。
    root = _init_in(tmp_path, monkeypatch)
    monkeypatch.delenv("AME_INIT_PYTHON", raising=False)
    monkeypatch.setattr(init_cmd, "_verify_importable", lambda _p: False)
    assert init_cmd.cmd_init(_make_args(python=None, no_workflow=True)) == 0
    assert (root / ".pre-commit-config.yaml").exists()


def test_init_explicit_python_unimportable_fails_fast(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Issue #66: 明示 --python で import 不可なら壊れた Gate 1 設定を書き出さず非ゼロ終了。
    root = _init_in(tmp_path, monkeypatch)
    monkeypatch.setattr(init_cmd, "_verify_importable", lambda _p: False)
    assert init_cmd.cmd_init(_make_args(python="/missing/python")) == 1
    assert not (root / ".pre-commit-config.yaml").exists()


def test_init_auto_python_unimportable_warns_but_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # system 方式で自動解決 (env) の Python が import 不可なら警告しつつ書き出す。
    root = _init_in(tmp_path, monkeypatch)
    monkeypatch.setenv("AME_INIT_PYTHON", "/missing/python")
    monkeypatch.setattr(init_cmd, "_verify_importable", lambda _p: False)
    assert init_cmd.cmd_init(_make_args(python=None, no_workflow=True)) == 0
    assert (root / ".pre-commit-config.yaml").exists()


def _read_lines(rel: str) -> list[str]:
    # プロジェクトルート (tests/ の親) からの相対パスでワークフローを読む。
    root = Path(__file__).resolve().parent.parent
    return (root / rel).read_text(encoding="utf-8").splitlines()


def _comment_match_lines(lines: list[str]) -> list[str]:
    """ワークフローからコメント本文判定 (github.event.comment.body) の行を抽出する.

    ラッパと配布テンプレートでコマンド発火条件が常に一致することを機械的に検証し、
    片方だけ更新されるドリフトを検知する (Issue #68/#70/#71)。
    """
    return [ln.strip() for ln in lines if "github.event.comment.body" in ln]


def _command_lines(lines: list[str]) -> list[str]:
    return [ln.strip() for ln in lines if "command:" in ln and "comment.body" in ln]


def test_workflow_and_template_command_conditions_match() -> None:
    real = _read_lines(".github/workflows/review_command.yml")
    tmpl = _read_lines(
        "ame_ai_review_system/templates/workflow/review-command-wrapper.yml"
    )
    assert _comment_match_lines(real) == _comment_match_lines(tmpl)
    assert _command_lines(real) == _command_lines(tmpl)


def _input_type(lines: list[str], name: str) -> str:
    """Reusable workflow の inputs 宣言から指定入力の type を抽出する (Issue #104)."""
    start = next(i for i, ln in enumerate(lines) if ln.strip() == f"{name}:")
    for ln in lines[start + 1 :]:
        stripped = ln.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("type:"):
            return stripped.split(":", 1)[1].strip()
        if stripped.startswith(("required:", "default:")):
            continue
    msg = f"input '{name}' に type が見つかりません"
    raise AssertionError(msg)


def test_reusable_workflows_accept_string_pr_number() -> None:
    # Issue #104: workflow_dispatch の inputs は常に文字列のため、reusable workflow の
    # pr_number / comment_id は type: string で受け取る。type: number だと配布先
    # ラッパが fromJSON() に依存しないと「Unexpected value '9'」で失敗する。
    for rel in (
        ".github/workflows/review-command.yml",
        ".github/workflows/review-reply.yml",
    ):
        lines = _read_lines(rel)
        assert _input_type(lines, "pr_number") == "string"
    assert (
        _input_type(_read_lines(".github/workflows/review-reply.yml"), "comment_id")
        == "string"
    )


def test_wrappers_pass_pr_number_without_fromjson() -> None:
    # Issue #104: 配布先ラッパ (テンプレート) と本リポジトリのラッパは pr_number を
    # そのまま渡す。fromJSON() に依存させないことで workflow_dispatch / issue_comment
    # の両経路で同一の渡し方になる (reusable 側が string で受けるため不要)。
    # 式の書式ではなく契約 (fromJSON 不使用 + 両経路のフォールバック由来) を検証する。
    sources = ("inputs.pr_number", "github.event.issue.number")
    for rel in (
        "ame_ai_review_system/templates/workflow/review-command-wrapper.yml",
        ".github/workflows/review_command.yml",
    ):
        expr = next(
            ln.strip() for ln in _read_lines(rel) if "pr_number:" in ln and "${{" in ln
        )
        assert "fromJSON" not in expr
        assert all(src in expr for src in sources)


def test_reply_wrappers_pass_ids_without_fromjson() -> None:
    # Issue #104: review-reply.yml の pr_number / comment_id が string 化された
    # ことを踏まえ、本リポジトリと配布先テンプレートの reply ラッパが各 ID を
    # fromJSON 非依存でそのまま渡すことを検証する。式の書式ではなく契約
    # (fromJSON 不使用 + 正しいイベント由来) に着目してドリフトを防ぐ。
    sources = {
        "pr_number": "github.event.pull_request.number",
        "comment_id": "github.event.comment.id",
    }
    for rel in (
        "ame_ai_review_system/templates/workflow/review-reply-wrapper.yml",
        ".github/workflows/review_reply.yml",
    ):
        lines = _read_lines(rel)
        for name, src in sources.items():
            expr = next(ln.strip() for ln in lines if f"{name}:" in ln and "${{" in ln)
            assert "fromJSON" not in expr
            assert src in expr


def test_ci_template_skip_matches_ai_hook_ids() -> None:
    # ci.yml (配布先向け静的解析 CI) の SKIP 一覧が precommit テンプレートの
    # AI レビューフック ID と一致することを機械的に検証する (Issue #101)。
    # 手動同期の更新漏れを防ぐための回帰テスト。
    skip_line = next(
        ln.strip()
        for ln in _read_lines("ame_ai_review_system/templates/workflow/ci.yml")
        if ln.strip().startswith("SKIP:")
    )
    skip_ids = set(skip_line.split("SKIP:")[1].strip().split(","))

    ai_ids: set[str] = set()
    for preset in ("full", "minimal", "python", "text", "ts"):
        for ln in _read_lines(
            f"ame_ai_review_system/templates/precommit/{preset}.yaml"
        ):
            line = ln.strip()
            if line.startswith("- id: ai-"):
                ai_ids.add(line.split(":", 1)[1].strip())
    assert ai_ids, "AI フック ID が precommit テンプレートから検出できません"
    assert skip_ids == ai_ids


# ---------------------------------------------------------------------------
# Issue #142: init 時の既存ファイル走査による共通衛生フックの補完
# ---------------------------------------------------------------------------


def test_detect_file_kinds_skips_vendor_and_generated_dirs(tmp_path: Path) -> None:
    # node_modules / .ame-review / キャッシュ配下は走査しない (生成物を種別として数えない)。
    _touch(tmp_path, "node_modules/pkg/index.json")
    _touch(tmp_path, ".ame-review/config.json")
    _touch(tmp_path, ".pytest_cache/v/cache/nodeids.json")
    _touch(tmp_path, "docs/guide.md")
    assert init_cmd._detect_file_kinds(tmp_path) == frozenset({"markdown"})


def test_detect_file_kinds_ignores_gitignored_paths(tmp_path: Path) -> None:
    # git 管理下では git ls-files が .gitignore を尊重し、キャッシュを種別と誤検出しない。
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".gitignore").write_text(".cache/\n", encoding="utf-8")
    _touch(tmp_path, ".cache/settings.json")
    _touch(tmp_path, "README.md")
    assert init_cmd._detect_file_kinds(tmp_path) == frozenset({"markdown"})


def test_detect_file_kinds_ignores_mdx(tmp_path: Path) -> None:
    # .mdx は JSX 構文を含み markdownlint が失敗するため対象外とする (レビュー指摘対応)。
    _touch(tmp_path, "docs/page.mdx")
    assert init_cmd._detect_file_kinds(tmp_path) == frozenset()


def test_insert_base_hooks_reports_missing_anchor() -> None:
    # repos: が無いテンプレートでは挿入できたことにしない (成功表示の防止)。
    assert init_cmd._insert_base_hooks("a: 1\n", "  x\n") is None
    assert init_cmd._insert_base_hooks("repos:\n  - repo: a\n", "  # b\n") == (
        "repos:\n  # b\n  - repo: a\n"
    )
    assert init_cmd._insert_base_hooks("repos:\n", "") == "repos:\n"


def test_jsonc_exclude_covers_commented_json() -> None:
    # check-json は厳密 JSON 検査のため、JSONC (コメント/末尾カンマ) を除外する。
    pattern = re.compile(init_cmd._JSONC_EXCLUDE)
    jsonc = (
        "tsconfig.json",
        "tsconfig.build.json",
        "jsconfig.json",
        ".vscode/settings.json",
        ".devcontainer/devcontainer.json",
    )
    for path in jsonc:
        assert pattern.search(path), path
    for path in ("package.json", "src/config.json", "tsconfig.md"):
        assert not pattern.search(path), path


def test_yaml_quote_escapes_backslashes_for_double_quoted_scalar() -> None:
    # 素の正規表現を YAML の double-quoted scalar へ入れると \. が不正エスケープになる。
    assert init_cmd._yaml_quote(r"a\.b") == r'"a\\.b"'
    assert init_cmd._yaml_quote("plain") == '"plain"'
    # ダブルクォートを含む exclude でも YAML を壊さない。
    assert init_cmd._yaml_quote('a"b') == r'"a\"b"'


def test_init_reports_skip_when_config_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # 既存の .pre-commit-config.yaml は既定でスキップされる。書き込まないのに
    # 「追加しました」と表示しない (レビュー指摘対応)。
    root = _init_in(tmp_path, monkeypatch)
    _touch(root, "README.md")
    assert init_cmd.cmd_init(_make_args(preset="python", no_workflow=True)) == 0
    capsys.readouterr()
    assert init_cmd.cmd_init(_make_args(preset="python", no_workflow=True)) == 0
    out = capsys.readouterr().out
    assert "追加しました" not in out
    assert "--force で反映" in out


def test_scan_skip_dirs_does_not_change_preset_detection(tmp_path: Path) -> None:
    # 走査専用の除外集合をプリセット自動判定と共有すると判定結果が変わるため分けている。
    assert init_cmd._SKIP_DIRS < init_cmd._SCAN_SKIP_DIRS
    _touch(tmp_path, "site/assets/app.ts")
    # site/ 配下の .ts は自動判定では従来どおり検出される (挙動を変えない)。
    assert init_cmd._repo_has_suffix(tmp_path, frozenset({".ts"})) is True
    assert init_cmd._detect_file_kinds(tmp_path) == frozenset()


def test_init_adds_markdownlint_when_markdown_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Issue #142: 既存の README.md を検出し、python プリセットへ Markdown リンタを補う。
    root = _init_in(tmp_path, monkeypatch)
    _touch(root, "README.md")
    assert init_cmd.cmd_init(_make_args(preset="python", no_workflow=True)) == 0
    cfg = _read_config(root)
    assert "https://github.com/igorshubovych/markdownlint-cli" in cfg
    assert "- id: markdownlint" in cfg


def test_init_skips_kind_hooks_when_kind_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # .md / .yaml / .json が無ければ種別フックは足さない (常時フックのみ)。
    root = _init_in(tmp_path, monkeypatch)
    (root / "main.py").write_text("print(1)\n", encoding="utf-8")
    assert init_cmd.cmd_init(_make_args(preset="python", no_workflow=True)) == 0
    cfg = _read_config(root)
    assert "- id: end-of-file-fixer" in cfg
    assert "- id: check-yaml" not in cfg
    assert "- id: check-json" not in cfg
    assert "markdownlint" not in cfg


def test_init_adds_yaml_and_json_hooks_when_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # ワークフロー定義 (.yml) と JSON があるリポジトリでは該当フックを補う。
    root = _init_in(tmp_path, monkeypatch)
    _touch(root, ".github/workflows/ci.yml")
    _touch(root, "settings.json")
    assert init_cmd.cmd_init(_make_args(preset="python", no_workflow=True)) == 0
    cfg = _read_config(root)
    assert "- id: check-yaml" in cfg
    assert "- id: check-json" in cfg


def test_init_base_hooks_do_not_duplicate_preset_coverage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # full は yamllint を持つため check-yaml を重複追加しない。
    root = _init_in(tmp_path, monkeypatch)
    _touch(root, ".github/workflows/ci.yml")
    assert init_cmd.cmd_init(_make_args(preset="full", no_workflow=True)) == 0
    cfg = _read_config(root)
    assert "- id: yamllint" in cfg
    assert "- id: check-yaml" not in cfg


def test_init_ts_preset_prettier_supersedes_check_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # ts は prettier が json を検査するため check-json を重複追加しない。
    root = _init_in(tmp_path, monkeypatch)
    (root / "package.json").write_text("{}", encoding="utf-8")
    assert init_cmd.cmd_init(_make_args(preset="ts", no_workflow=True)) == 0
    cfg = _read_config(root)
    assert "- id: prettier" in cfg
    assert "- id: check-json" not in cfg


def test_init_text_preset_existing_markdown_linter_supersedes_markdownlint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # text は markdownlint-cli2 / textlint を持つため markdownlint を足さない。
    root = _init_in(tmp_path, monkeypatch)
    _touch(root, "README.md")
    assert init_cmd.cmd_init(_make_args(preset="text", no_workflow=True)) == 0
    cfg = _read_config(root)
    assert "- id: markdownlint-cli2" in cfg
    assert "repo: https://github.com/igorshubovych/markdownlint-cli" not in cfg


def test_init_no_base_hooks_flag_skips_detection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # --no-base-hooks は走査結果を一切足さない (既存リポジトリの段階導入向け)。
    root = _init_in(tmp_path, monkeypatch)
    _touch(root, "README.md")
    _touch(root, "settings.json")
    args = _make_args(preset="python", no_workflow=True, no_base_hooks=True)
    assert init_cmd.cmd_init(args) == 0
    cfg = _read_config(root)
    assert "https://github.com/pre-commit/pre-commit-hooks" not in cfg
    assert "markdownlint" not in cfg
    assert "- id: check-json" not in cfg


def test_init_minimal_preset_never_adds_base_hooks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # minimal は「静的解析フックを持たない」明示的な選択のため走査結果を足さない。
    root = _init_in(tmp_path, monkeypatch)
    _touch(root, "README.md")
    _touch(root, "settings.json")
    assert init_cmd.cmd_init(_make_args(preset="minimal", no_workflow=True)) == 0
    cfg = _read_config(root)
    assert "- id: check-added-large-files" not in cfg
    assert "- id: check-json" not in cfg
    assert "markdownlint" not in cfg


def test_init_detection_ignores_generated_ame_review_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # init が直前に置いた .ame-review/config.json を「JSON あり」と誤検出しない。
    root = _init_in(tmp_path, monkeypatch)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    (root / "main.py").write_text("print(1)\n", encoding="utf-8")
    assert init_cmd.cmd_init(_make_args(preset="python", no_workflow=True)) == 0
    assert (root / ".ame-review" / "config.json").exists()
    assert "- id: check-json" not in _read_config(root)


def test_init_generated_configs_parse_as_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 断片を文字列連結で組み立てるため、生成物が YAML として妥当であることを機械的に確認する。
    yaml = pytest.importorskip("yaml")
    for preset in ("full", "minimal", "python", "text", "ts"):
        root = tmp_path / preset
        root.mkdir()
        _init_in(root, monkeypatch)
        _touch(root, "README.md")
        _touch(root, "config.yaml")
        assert init_cmd.cmd_init(_make_args(preset=preset, no_workflow=True)) == 0
        parsed = yaml.safe_load(_read_config(root))
        assert "local" in [repo["repo"] for repo in parsed["repos"]]
        for repo in parsed["repos"]:
            assert repo["repo"]
            assert "rev" in repo or repo["repo"] == "local"
            assert all(hook["id"] for hook in repo["hooks"])


def test_init_cli_no_base_hooks_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    # CLI から --no-base-hooks が init_cmd まで届く。
    captured: dict[str, object] = {}

    def fake_cmd_init(args: argparse.Namespace) -> int:
        captured["no_base_hooks"] = args.no_base_hooks
        return 0

    monkeypatch.setattr(init_cmd, "cmd_init", fake_cmd_init)
    assert cli.main(["init", "--no-base-hooks", "--no-workflow"]) == 0
    assert captured["no_base_hooks"] is True


def test_init_system_mode_skips_base_hooks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # --python はオフライン前提の指定。remote リポジトリの hook env を初回に取得する
    # 共通衛生フックを足すと、その前提を壊す (Issue #142 レビュー指摘対応)。
    root = _init_in(tmp_path, monkeypatch)
    _touch(root, "README.md")
    _touch(root, "settings.json")
    monkeypatch.setattr(init_cmd, "_verify_importable", lambda _p: True)
    args = _make_args(
        preset="python", no_workflow=True, python="/custom/venv/bin/python"
    )
    assert init_cmd.cmd_init(args) == 0
    cfg = _read_config(root)
    assert "https://github.com/pre-commit/pre-commit-hooks" not in cfg
    assert "markdownlint" not in cfg
    assert "- id: check-json" not in cfg
    assert "- id: ruff" in cfg


def test_yaml_template_exclude_and_multi_document_args() -> None:
    # Helm / Ansible 等のテンプレートや複数ドキュメントで初回から失敗しないようにする。
    pattern = re.compile(init_cmd._YAML_TEMPLATE_EXCLUDE)
    for path in ("charts/app/values.yaml", "ansible/templates/site.yml", "x/config.j2"):
        assert pattern.search(path), path
    for path in ("config/app.yaml", "template.yml", "src/charts.md"):
        assert pattern.search(path) is None, path
    yaml_hook = next(
        hook
        for group in init_cmd._BASE_HOOK_REPOS
        for hook in group.hooks
        if hook.hook_id == "check-yaml"
    )
    assert yaml_hook.args == "[--allow-multiple-documents]"
    assert yaml_hook.exclude == init_cmd._YAML_TEMPLATE_EXCLUDE


def test_render_base_hooks_skips_existing_repo(tmp_path: Path) -> None:
    # プリセットが同じ repo を別 rev で持つ場合は二重に並べない。
    preset = "repos:\n  - repo: https://github.com/pre-commit/pre-commit-hooks\n    rev: v4.0.0\n    hooks:\n      - id: trailing-whitespace\n"
    block, added = init_cmd._render_base_hooks(frozenset({"markdown"}), preset)
    assert "https://github.com/pre-commit/pre-commit-hooks" not in block
    assert "trailing-whitespace" not in added
    assert "markdownlint" in added


def test_insert_base_hooks_ignores_comment_anchor() -> None:
    # コメント行の "# repos:" を挿入位置と誤認しない。
    content = "# repos: の下に並べる\nrepos:\n  - repo: a\n"
    inserted = init_cmd._insert_base_hooks(content, "  # base\n")
    assert inserted == "# repos: の下に並べる\nrepos:\n  # base\n  - repo: a\n"
