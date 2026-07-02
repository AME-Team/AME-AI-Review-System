#!/usr/bin/env bash
set -euo pipefail

PROJ="$(cd "$(dirname "$0")/.." && pwd)"
GITEA_URL="${GITEA_URL:-http://localhost:3000}"
REPO="${GITHUB_REPOSITORY:-AME-Team/AME-AI-Review-System}"

GITEA_TOKEN_FILE="$HOME/.config/ame-ai-review-system/gitea.token"
if [ -f "$GITEA_TOKEN_FILE" ]; then
    GITEA_TOKEN=$(cat "$GITEA_TOKEN_FILE")
elif [ -n "${GITEA_TOKEN:-}" ]; then
    : # 環境変数から使用
else
    exit 0
fi

COMMAND=$(python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    print(d.get('tool_input', {}).get('command', ''))
except Exception:
    print('')
" 2>/dev/null || true)
if [ -z "$COMMAND" ]; then
    COMMAND="${1:-}"
fi

if ! echo "$COMMAND" | grep -qE 'git push'; then
    exit 0
fi

BRANCH=$(git -C "$PROJ" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
if [ -z "$BRANCH" ] || [ "$BRANCH" = "HEAD" ] || [ "$BRANCH" = "main" ]; then
    exit 0
fi

PR_NUM=$(curl -s \
    "${GITEA_URL}/api/v1/repos/${REPO}/pulls?state=open&limit=20" \
    -H "Authorization: token ${GITEA_TOKEN}" \
    | BRANCH="$BRANCH" python3 -c "
import json, sys, os
data = json.load(sys.stdin)
branch = os.environ.get('BRANCH', '')
for pr in data:
    if pr.get('head', {}).get('ref', '') == branch or pr.get('head', {}).get('label', '') == branch:
        print(pr['number'])
        break
" 2>/dev/null || echo "")

if [ -z "$PR_NUM" ]; then
    exit 0
fi

echo "[post_push_review] PR #${PR_NUM} detected. Waiting for reviewers..."

REVIEWERS=(
    "ame-ai-reviewer"
)

count_all_reviews() {
    local pr="$1"
    local names_json
    names_json=$(printf '%s\n' "${REVIEWERS[@]}" | python3 -c "import sys,json; print(json.dumps([l.strip() for l in sys.stdin]))")
    curl -s \
        "${GITEA_URL}/api/v1/repos/${REPO}/pulls/${pr}/reviews?limit=50" \
        -H "Authorization: token ${GITEA_TOKEN}" \
        | REVIEWER_NAMES="$names_json" python3 -c "
import json, sys, os
data = json.load(sys.stdin)
names = set(json.loads(os.environ['REVIEWER_NAMES']))
print(sum(1 for r in data if r.get('user', {}).get('login') in names))
" 2>/dev/null || echo 0
}

INITIAL_REVIEWS=$(count_all_reviews "$PR_NUM")

WAITED=0
while [ "$WAITED" -lt 90 ]; do
    sleep 10
    WAITED=$((WAITED + 10))
    CURRENT_REVIEWS=$(count_all_reviews "$PR_NUM")
    if [ "$CURRENT_REVIEWS" -gt "$INITIAL_REVIEWS" ]; then
        echo "[post_push_review] New review(s) detected. Running reply handlers..."
        break
    fi
done

if [ "$WAITED" -ge 90 ]; then
    echo "[post_push_review] No new reviews after 90s, skipping."
    exit 0
fi

export PR_NUMBER="$PR_NUM"
BASE_REF="${BASE_REF:-main}"
export BASE_REF

for REVIEWER_NAME in "${REVIEWERS[@]}"; do
    TOKEN_FILE="$HOME/.config/ame-ai-review-system/${REVIEWER_NAME}.token"
    if [ -f "$TOKEN_FILE" ]; then
        REVIEWER_TOKEN=$(cat "$TOKEN_FILE")
    else
        ENV_KEY=$(echo "${REVIEWER_NAME}" | tr '[:lower:]-' '[:upper:]_')_TOKEN
        REVIEWER_TOKEN="${!ENV_KEY:-}"
        if [ -z "$REVIEWER_TOKEN" ]; then
            echo "[post_push_review] Token not found for ${REVIEWER_NAME}, skipping."
            continue
        fi
    fi
    export REVIEWER_TOKEN REVIEWER_NAME

    echo "[post_push_review] Checking pending threads for ${REVIEWER_NAME}..."
    bash "$PROJ/ame-ai-review-system/pr_review_reply.sh"

    PENDING=$(REVIEWER_TOKEN="$REVIEWER_TOKEN" REVIEWER_NAME="$REVIEWER_NAME" \
        python3 "$PROJ/ame-ai-review-system/reply.py" pending "$PR_NUM" \
        2>/dev/null || echo "[]")
    echo "$PENDING" | python3 -c "
import json, sys
for tid in json.loads(sys.stdin.read()):
    print(tid)
" | while IFS= read -r TID; do
        curl -s -o /dev/null -X POST \
            "${GITEA_URL}/api/v1/repos/${REPO}/pulls/comments/${TID}/resolve" \
            -H "Authorization: token ${GITEA_TOKEN}"
        echo "[post_push_review] Resolved thread ${TID} (${REVIEWER_NAME})."
    done
done

echo "[post_push_review] All reviewers processed."
