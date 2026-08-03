#!/usr/bin/env bash
# wheel の必須アセット同梱を検証する。ci.yml / release.yml から共通利用。
# アセットリストの二重管理を防ぐため、このスクリプトを正とする。
#
# Python の zipfile で検証し、unzip 出力形式の環境差を排除する。
# missing 時は wheel の全内容を出力して原因特定を容易にする。
#
# 使い方: check_wheel_assets.sh <wheel-path>
set -euo pipefail

WHL="${1:?usage: check_wheel_assets.sh <wheel-path>}"

python3 - "$WHL" <<'PYEOF'
import sys
import zipfile

whl = sys.argv[1]
assets = [
    "ame_ai_review_system/.semgrep/rules.yml",
    "ame_ai_review_system/config.json",
    "ame_ai_review_system/review_prompt.txt",
    "ame_ai_review_system/engines/ts/package.json",
    "ame_ai_review_system/templates/precommit/python.yaml",
]
names = zipfile.ZipFile(whl).namelist()
print(f"Inspecting {whl}...")
missing = False
for asset in assets:
    if asset in names:
        print(f"  OK: {asset}")
    else:
        print(f"::error::Missing in wheel: {asset}")
        missing = True
if missing:
    print("--- wheel contents ---")
    for n in sorted(names):
        print(f"  {n}")
    sys.exit(1)
PYEOF
