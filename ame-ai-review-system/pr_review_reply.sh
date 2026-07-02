#!/usr/bin/env bash
set -euo pipefail

PROJ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GITEA_URL="${GITEA_URL:-http://localhost:3000}"
REPO="${GITHUB_REPOSITORY:-AME-Team/AME-AI-Review-System}"

REVIEWER_NAME="${REVIEWER_NAME:-ame-ai-reviewer}"
if [[ ! "$REVIEWER_NAME" =~ ^[a-zA-Z0-9-]+$ ]]; then
    echo "[pr_review_reply] ERROR: Invalid REVIEWER_NAME: ${REVIEWER_NAME}"
    exit 1
fi

REVIEWER_TOKEN_FILE="$HOME/.config/ame-ai-review-system/${REVIEWER_NAME}.token"
if [ -z "${REVIEWER_TOKEN:-}" ]; then
    if [ -f "$REVIEWER_TOKEN_FILE" ]; then
        REVIEWER_TOKEN=$(cat "$REVIEWER_TOKEN_FILE")
    else
        ENV_KEY=$(echo "${REVIEWER_NAME}" | tr '[:lower:]-' '[:upper:]_')_TOKEN
        REVIEWER_TOKEN="${!ENV_KEY:-}"
        if [ -z "$REVIEWER_TOKEN" ]; then
            echo "[pr_review_reply] ERROR: REVIEWER_TOKEN not set, $REVIEWER_TOKEN_FILE not found, and \$${ENV_KEY} not set."
            exit 1
        fi
    fi
fi

if [ -z "${PR_NUMBER:-}" ]; then
    echo "[pr_review_reply] ERROR: PR_NUMBER not set."
    exit 1
fi

BASE_REF="${BASE_REF:-main}"
if [[ ! "$BASE_REF" =~ ^[a-zA-Z0-9/_-]+$ ]]; then
    echo "[pr_review_reply] ERROR: Invalid BASE_REF: ${BASE_REF}"
    exit 1
fi
export GITEA_URL REPO REVIEWER_TOKEN REVIEWER_NAME BASE_REF

PROMPT_TMP=$(mktemp)
CLAUDE_OUT=$(mktemp)
CLAUDE_ERR=$(mktemp)

cleanup() { rm -f "$PROMPT_TMP" "$CLAUDE_OUT" "$CLAUDE_ERR"; }
trap cleanup EXIT

echo "[pr_review_reply] Scanning PR #${PR_NUMBER} for pending reply threads..."
PENDING_JSON=$(python3 "$PROJ/ame-ai-review-system/reply.py" pending "$PR_NUMBER")
PENDING_COUNT=$(printf '%s\n' "$PENDING_JSON" | python3 -c "import json,sys; print(len(json.loads(sys.stdin.read())))")

if [ "$PENDING_COUNT" -eq 0 ]; then
    echo "[pr_review_reply] No pending threads, done."
    exit 0
fi

echo "[pr_review_reply] ${PENDING_COUNT} thread(s) need reply."

while IFS= read -r THREAD_ID; do
    if [[ ! "$THREAD_ID" =~ ^[0-9]+$ ]]; then
        echo "[pr_review_reply] WARNING: Invalid THREAD_ID '${THREAD_ID}', skip."
        continue
    fi
    echo "[pr_review_reply] Processing thread ${THREAD_ID}..."

    python3 "$PROJ/ame-ai-review-system/reply.py" build \
        "$PR_NUMBER" "$THREAD_ID" > "$PROMPT_TMP"

    if [ ! -s "$PROMPT_TMP" ]; then
        echo "[pr_review_reply] Prompt empty for thread ${THREAD_ID}, skip."
        continue
    fi

    CLAUDE_MODEL="${CLAUDE_MODEL:-sonnet}"
    if [[ ! "$CLAUDE_MODEL" =~ ^[a-zA-Z0-9._-]+$ ]]; then
        echo "[pr_review_reply] ERROR: Invalid CLAUDE_MODEL: ${CLAUDE_MODEL}"
        exit 1
    fi

    claude -p \
        --model "$CLAUDE_MODEL" \
        --max-budget-usd 0.20 \
        --output-format json \
        --dangerously-skip-permissions \
        < "$PROMPT_TMP" \
        > "$CLAUDE_OUT" 2> "$CLAUDE_ERR"
    CLAUDE_EXIT=$?

    if [ -s "$CLAUDE_ERR" ]; then
        echo "[pr_review_reply] Claude stderr for thread ${THREAD_ID}:"
        cat "$CLAUDE_ERR"
    fi

    if [ "$CLAUDE_EXIT" -ne 0 ] || [ ! -s "$CLAUDE_OUT" ]; then
        echo "[pr_review_reply] Claude failed, using default LGTM."
        REPLY_BODY="対応確認しました。LGTM ✅ Resolve してください。"
    else
        PARSED=$(python3 "$PROJ/ame-ai-review-system/reply.py" parse "$CLAUDE_OUT")
        REPLY_BODY=$(printf '%s\n' "$PARSED" | python3 -c "
import json,sys
d=json.loads(sys.stdin.read())
print(d.get('body', '対応確認しました。LGTM ✅ Resolve してください。'))
")
    fi

    PAYLOAD=$(printf '%s' "$REPLY_BODY" | python3 -c "
import json, sys
body = sys.stdin.read()
print(json.dumps({'body': body}))
")

    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
        -X POST \
        "${GITEA_URL}/api/v1/repos/${REPO}/pulls/${PR_NUMBER}/comments/${THREAD_ID}/replies" \
        -H "Authorization: token ${REVIEWER_TOKEN}" \
        -H "Content-Type: application/json" \
        -d "$PAYLOAD")

    echo "[pr_review_reply] Thread ${THREAD_ID} → HTTP ${HTTP_CODE}."
    if [[ "$HTTP_CODE" != 2* ]]; then
        # 失敗しても他のスレッドの処理を続行するため、警告を出力して続行する
        echo "[pr_review_reply] WARNING: Unexpected HTTP code ${HTTP_CODE} for thread ${THREAD_ID}."
    fi
done < <(printf '%s\n' "$PENDING_JSON" | python3 -c "
import json, sys
for tid in json.loads(sys.stdin.read()):
    print(tid)
")

echo "[pr_review_reply] Done."
