# pyright: basic
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pytest
from ame_ai_review_system import __version__, init_cmd


def _make_args(**kwargs: object) -> argparse.Namespace:
    defaults: dict[str, object] = {
        "preset": "full",
        "ref": "main",
        "no_workflow": False,
        "with_engines": False,
        "force": False,
        "python": None,
        "version": None,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def _init_in(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / ".git").mkdir()
    monkeypatch.setenv("AME_REVIEW_PROJECT_ROOT", str(tmp_path))
    return tmp_path


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


def test_init_requires_ref_unless_no_workflow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _init_in(tmp_path, monkeypatch)
    assert init_cmd.cmd_init(_make_args(ref=None)) == 1


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
