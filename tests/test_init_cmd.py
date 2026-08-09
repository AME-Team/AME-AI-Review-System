# pyright: basic
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pytest
from ame_ai_review_system import init_cmd


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
    assert "ame_ai_review_system-0.2.3-py3-none-any.whl#sha256=aaaaaaaaaaaaaaaa" in cfg
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
    assert "ame_ai_review_system-0.2.3-py3-none-any.whl" in cfg
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
