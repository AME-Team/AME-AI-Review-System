"""`gh api --paginate repos/{repo}/tags` の出力からリリースタグを選ぶ."""

from __future__ import annotations

import json
import sys
from typing import Any, cast

_SEMVER_PARTS = 3
_ARGC_WITH_SCRIPT = 2

Tag = dict[str, Any]


def _iter_tags(text: str) -> list[Tag]:
    """連結された複数の JSON 配列 (ページ単位) を平坦化する."""
    decoder = json.JSONDecoder()
    tags: list[Tag] = []
    pos = 0
    while pos < len(text):
        chunk = text[pos:].lstrip()
        if not chunk:
            break
        pos = len(text) - len(chunk)
        data, pos = decoder.raw_decode(text, pos)
        if isinstance(data, list):
            tags.extend(
                cast("Tag", item)
                for item in cast("list[Any]", data)
                if isinstance(item, dict)
            )
    return tags


def _is_release_tag(name: str) -> bool:
    """完全な vX.Y.Z だけを対象にする (移動タグ v0 / v0.2 を除外する)."""
    if not name.startswith("v"):
        return False
    parts = name[1:].split(".")
    return len(parts) == _SEMVER_PARTS and all(part.isdigit() for part in parts)


def resolve(text: str, head_sha: str) -> str:
    """head_sha を指すリリースタグを 1 つ返す (無ければ空文字)."""
    for tag in _iter_tags(text):
        commit = tag.get("commit")
        name = tag.get("name")
        if not isinstance(commit, dict) or not isinstance(name, str):
            continue
        if cast("dict[str, Any]", commit).get("sha") == head_sha and _is_release_tag(
            name
        ):
            return name
    return ""


def main(argv: list[str]) -> int:
    if len(argv) != _ARGC_WITH_SCRIPT:
        print("usage: resolve_release_tag.py <head-sha>", file=sys.stderr)
        return 2
    print(resolve(sys.stdin.read(), argv[1]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
