#!/usr/bin/env bash
# act_runner デーモンを Docker Compose で起動する。
#
# WSL2 上の Gitea に接続するため、WSL2 IP を自動検出して GITEA_INSTANCE_URL に設定する。
# 初回起動時は RUNNER_REGISTRATION_TOKEN が必要 (Gitea UI で取得)。
#
# 使い方:
#   初回:  RUNNER_REGISTRATION_TOKEN=<トークン> ./start-runner.sh
#   2回目: ./start-runner.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

WSL_IP="$(hostname -I | awk '{print $1}')"

if [ -z "$WSL_IP" ]; then
  echo "[error] WSL2 IP を取得できませんでした。" >&2
  exit 1
fi

export GITEA_INSTANCE_URL="http://${WSL_IP}:3000"
echo "[runner] Gitea URL: ${GITEA_INSTANCE_URL}"

if [ -n "${RUNNER_REGISTRATION_TOKEN:-}" ]; then
  echo "[runner] 登録トークンが設定されています。初回登録を実行します。"
else
  echo "[runner] 登録トークン未設定 (既存登録があればそれを使用)。"
fi

echo "[runner] docker compose up を開始..."
exec docker compose up -d
