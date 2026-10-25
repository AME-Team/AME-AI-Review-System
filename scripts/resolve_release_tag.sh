#!/usr/bin/env bash
# Release ワークフローの head SHA から、そのリビジョンに付いたリリースタグを特定する。
#
# 移動メジャータグ (`v0` / `v0.2`) も同じ SHA を指すため、完全な `vX.Y.Z` 形式だけに絞ってから
# 選ぶ。絞らずに先頭を取ると `v0` を拾い、後段のタグ検証で必ず失敗する。
# タグは多いのでページングして全件を見る。
#
# 使い方: scripts/resolve_release_tag.sh <head-sha> [repo]
#   出力: タグ名 (見つからなければ空)。API 失敗・解析失敗は非 0 で終了する
#   (呼び出し側が ::error:: を出して中断する)。

set -euo pipefail

head_sha="${1:?head sha required}"
repo="${2:-${GITHUB_REPOSITORY:?repo required}}"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# `gh api --paginate` はページごとに JSON 配列を連結して返す。semver の絞り込みと
# ページ連結の扱いは Python 側 (resolve_release_tag.py) に寄せてテスト可能にする。
gh api --paginate "repos/${repo}/tags?per_page=100" |
  python3 "${script_dir}/resolve_release_tag.py" "${head_sha}"
