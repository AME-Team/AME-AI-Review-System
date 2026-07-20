#!/usr/bin/env bash
# act_runner デーモンを docker compose で起動する (systemd サービス用)。
#
# Docker Desktop 起動直後は Docker ソケットが未準備な場合があるため、
# 利用可能になるまで待機してから docker compose up (foreground) を実行する。
# WSL2 IP は再起動のたびに変動するため、起動時に自動検出する。
# foreground 実行により systemd がプロセス寿命を管理し、
# Docker Desktop 再起動時に自動復旧できる。

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_DIR"

DOCKER_WAIT_RETRIES=30
DOCKER_WAIT_INTERVAL=2

echo "[act-runner] Waiting for Docker to become available..."
for i in $(seq 1 "$DOCKER_WAIT_RETRIES"); do
  if docker info >/dev/null 2>&1; then
    echo "[act-runner] Docker is ready (attempt ${i})."
    break
  fi
  if [ "$i" -eq "$DOCKER_WAIT_RETRIES" ]; then
    echo "[act-runner] ERROR: Docker not available after" \
      "$((DOCKER_WAIT_RETRIES * DOCKER_WAIT_INTERVAL))s." >&2
    exit 1
  fi
  sleep "$DOCKER_WAIT_INTERVAL"
done

WSL_IP="$(hostname -I | awk '{print $1}')"
if [ -z "$WSL_IP" ]; then
  echo "[act-runner] ERROR: WSL2 IP not found." >&2
  exit 1
fi
export GITEA_INSTANCE_URL="http://${WSL_IP}:3000"
echo "[act-runner] Gitea URL: ${GITEA_INSTANCE_URL}"
echo "[act-runner] Starting docker compose up (foreground)..."

exec docker compose up
