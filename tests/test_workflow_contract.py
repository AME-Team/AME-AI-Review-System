"""配布テンプレートと reusable workflow の契約が乖離していないかを検証する (Issue #164).

導入先は ``templates/workflow/*-wrapper.yml`` から生成した薄いラッパで reusable workflow を
呼ぶ。reusable 側に input / secret を足したのにテンプレートを追随させないと、配布先の
ラッパは未定義の入力を渡せず (または必須入力を渡せず) 実行時に落ちる。``init`` で生成済みの
既存リポジトリはテンプレートを再生成しないため、この乖離は CI でしか検出できない。

YAML パーサは使わない (パッケージは依存ゼロ方針)。``workflow_call`` とラッパの呼び出し
ブロックだけをインデントで読む最小のパーサで判定する。
"""

from __future__ import annotations

from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_WORKFLOWS = _ROOT / ".github" / "workflows"
_TEMPLATES = _ROOT / "ame_ai_review_system" / "templates" / "workflow"


def _key(line: str) -> str:
    """``key: value`` / ``key:`` / ``key: # comment`` からキー名を取る."""
    return line.strip().split(":", 1)[0].strip()


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _significant(lines: list[str]) -> list[str]:
    return [
        line for line in lines if line.strip() and not line.lstrip().startswith("#")
    ]


def _children(lines: list[str], start: int, indent: int) -> dict[str, list[str]]:
    """``start`` 行の直下 (``indent + 2``) のキーと、その配下の行を返す."""
    children: dict[str, list[str]] = {}
    current: str | None = None
    for line in lines[start + 1 :]:
        if _indent(line) <= indent:
            break
        if _indent(line) == indent + 2:
            current = line.strip().split(":", 1)[0].strip()
            children[current] = []
        elif current is not None:
            children[current].append(line.strip())
    return children


def _named_block(
    lines: list[str], start: int, parent_indent: int, name: str
) -> dict[str, list[str]] | None:
    """``parent_indent + 2`` にある ``name:`` ブロックの直下キーを返す (無ければ ``None``)."""
    for index in range(start + 1, len(lines)):
        indent = _indent(lines[index])
        if indent <= parent_indent:
            break
        if indent == parent_indent + 2 and _key(lines[index]) == name:
            return _children(lines, index, indent)
    return None


def _workflow_contract(path: Path) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """ワークフローの ``workflow_call`` 宣言から inputs / secrets を読む."""
    lines = _significant(path.read_text(encoding="utf-8").splitlines())
    for index, line in enumerate(lines):
        if _key(line) != "workflow_call":
            continue
        indent = _indent(line)
        inputs = _named_block(lines, index, indent, "inputs")
        secrets = _named_block(lines, index, indent, "secrets")
        if inputs is None and secrets is None:
            # どちらも読めないまま比較すると、空集合同士で全アサーションが通ってしまう。
            message = f"workflow_call の inputs / secrets を読めません: {path}"
            raise AssertionError(message)
        return inputs or {}, secrets or {}
    message = f"workflow_call が見つかりません: {path}"
    raise AssertionError(message)


def _required(block: dict[str, list[str]]) -> set[str]:
    """Return the names declared as ``required: true`` (省略不可のものだけ)."""
    return {
        name
        for name, body in block.items()
        if any(line.strip() == "required: true" for line in body)
    }


def _wrapper_inherits_secrets(path: Path) -> bool:
    """ラッパが ``secrets: inherit`` を使っているか."""
    return any(
        line.strip() == "secrets: inherit"
        for line in path.read_text(encoding="utf-8").splitlines()
    )


def _wrapper_call(path: Path) -> tuple[str, set[str], set[str]]:
    """ラッパの ``uses:`` 参照先と、渡す ``with`` / ``secrets`` のキーを返す."""
    lines = _significant(path.read_text(encoding="utf-8").splitlines())
    for index, line in enumerate(lines):
        if not line.strip().startswith("uses: __REPO__/"):
            continue
        indent = _indent(line)
        with_keys: set[str] = set()
        secret_keys: set[str] = set()
        current: str | None = None
        for child in lines[index + 1 :]:
            if _indent(child) < indent:
                break
            if _indent(child) == indent:
                # with: / secrets: は uses: と同じインデントで並ぶ。
                name = _key(child)
                current = name if name in {"with", "secrets"} else None
                continue
            if _indent(child) == indent + 2 and current is not None:
                (with_keys if current == "with" else secret_keys).add(_key(child))
        return line.split("uses:", 1)[1].strip(), with_keys, secret_keys
    message = f"uses: __REPO__/... が見つかりません: {path}"
    raise AssertionError(message)


def _pairs() -> list[tuple[Path, Path]]:
    """``templates/workflow/*-wrapper.yml`` と対応する reusable workflow を列挙する.

    新しいラッパを足したら自動で検証対象になる (ハードコードすると追随を忘れる)。
    """
    pairs: list[tuple[Path, Path]] = []
    for template in sorted(_TEMPLATES.glob("*-wrapper.yml")):
        workflow = _WORKFLOWS / template.name.replace("-wrapper.yml", ".yml")
        if not workflow.is_file():
            message = f"対応する reusable workflow がありません: {template.name}"
            raise AssertionError(message)
        pairs.append((template, workflow))
    if not pairs:
        message = "配布テンプレートが見つかりません"
        raise AssertionError(message)
    return pairs


@pytest.mark.parametrize(
    ("template", "workflow"),
    _pairs(),
    ids=lambda path: path.name,
)
def test_wrapper_matches_reusable_workflow_contract(
    template: Path, workflow: Path
) -> None:
    """ラッパが reusable workflow の宣言を満たしていることを固定する.

    必須の入力・秘密はすべて渡すこと、宣言に無い名前は渡さないことを検証する。既定値を持つ
    任意の入力 (``runner_labels`` など) は、ラッパが渡さなくても既定で動くため対象外とする。
    未宣言の入力を渡せば実行時に落ち、必須入力の未追随は生成済みの導入先で気づけない。
    """
    inputs, secrets = _workflow_contract(workflow)
    uses, with_keys, secret_keys = _wrapper_call(template)

    # 呼び出し先が対応する workflow であること。input / secret 名が偶然一致していても、
    # 別の workflow を呼んでいれば契約は満たさない。
    expected = f".github/workflows/{workflow.name}@"
    assert expected in uses, (
        f"{template.name} が {workflow.name} を呼んでいません: {uses}"
    )
    assert not (with_keys - set(inputs)), (
        f"{template.name} が未宣言の入力を渡しています: {sorted(with_keys - set(inputs))}"
    )
    missing_inputs = _required(inputs) - with_keys
    assert not missing_inputs, (
        f"{template.name} が必須の入力を渡していません: {sorted(missing_inputs)}"
    )
    if _wrapper_inherits_secrets(template):
        # `secrets: inherit` は宣言を個別に渡さないため、名前の一致は要求しない。
        return
    assert not (secret_keys - set(secrets)), (
        f"{template.name} が未宣言の secret を渡しています: {sorted(secret_keys - set(secrets))}"
    )
    missing_secrets = _required(secrets) - secret_keys
    assert not missing_secrets, (
        f"{template.name} が必須の secret を渡していません: {sorted(missing_secrets)}"
    )
