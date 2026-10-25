#!/usr/bin/env bash
# 導入先 (配布先) の一覧を出力する。1 行 1 リポジトリ (owner/name)。
#
# `Release` 後の同期 PR 作成 (Sync Downstream) と Drift Audit の監査対象は、この出力を
# 単一情報源にする。コメント行 (`#` で始まる行) と空行は無視する。行内コメントは不可。
#
# 使い方: scripts/list_downstream_repos.sh [file]
#   file の既定は `.github/downstream-repos.txt`。

set -euo pipefail

file="${1:-.github/downstream-repos.txt}"
if [ ! -f "${file}" ]; then
  echo "error: ${file} not found" >&2
  exit 1
fi

# 該当行が無い場合も正常終了させる (呼び出し側で空判定する)。
grep -vE '^[[:space:]]*($|#)' "${file}" || true
