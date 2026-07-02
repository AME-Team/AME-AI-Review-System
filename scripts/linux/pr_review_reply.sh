#!/usr/bin/env bash
# Giteaの仕様上、コメントトリガー（review_reply.yml）はmainブランチのワークフロー定義を参照して動作します。
# PRマージ前の段階で、新パス（ame-ai-review-system/pr_review_reply.sh）を実行できるようにするため、
# mainブランチのワークフローが期待する旧パス（scripts/linux/pr_review_reply.sh）から新パスを呼び出すラッパーとして機能させています。
# 本PRがmainにマージされた後は、このファイルは削除可能です。
set -euo pipefail
PROJ_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
exec bash "$PROJ_ROOT/ame-ai-review-system/pr_review_reply.sh" "$@"
