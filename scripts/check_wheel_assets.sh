#!/usr/bin/env bash
# wheel の必須アセット同梱を検証する。ci.yml / release.yml から共通利用。
# アセットリストの二重管理を防ぐため、このスクリプトを正とする。
#
# 使い方: check_wheel_assets.sh <wheel-path>
set -euo pipefail

WHL="${1:?usage: check_wheel_assets.sh <wheel-path>}"

# wheel に同梱されているべき必須アセット。
# 新規アセット追加時はこのリストを更新する（ci.yml / release.yml 側は触らない）。
assets=(
  "ame_ai_review_system/.semgrep/rules.yml"
  "ame_ai_review_system/config.json"
  "ame_ai_review_system/review_prompt.txt"
  "ame_ai_review_system/engines/ts/package.json"
  "ame_ai_review_system/templates/precommit/python.yaml"
)

echo "Inspecting ${WHL}..."
for asset in "${assets[@]}"; do
  if unzip -l "$WHL" | grep -q "$asset"; then
    echo "  OK: $asset"
  else
    echo "::error::Missing in wheel: $asset"
    exit 1
  fi
done
