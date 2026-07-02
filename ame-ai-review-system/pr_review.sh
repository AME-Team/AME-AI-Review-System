#!/usr/bin/env bash
set -euo pipefail

PROJ="$(cd "$(dirname "$0")/.." && pwd)"
GITEA_URL="${GITEA_URL:-http://localhost:3000}"
REPO="${GITHUB_REPOSITORY:-AME-Team/AME-AI-Review-System}"
REVIEW_OUT="/tmp/pr_review_$$.txt"
PROMPT_IN="/tmp/pr_prompt_$$.txt"
RESPONSE_TMP="/tmp/pr_comment_response_$$.json"
CLAUDE_ERR="/tmp/pr_claude_err_$$.txt"

cleanup() { rm -f "$REVIEW_OUT" "$PROMPT_IN" "$RESPONSE_TMP" "$CLAUDE_ERR"; }
trap cleanup EXIT

REVIEWER_NAME="${REVIEWER_NAME:-ame-ai-reviewer}"
if [[ ! "$REVIEWER_NAME" =~ ^[a-zA-Z0-9-]+$ ]]; then
    echo "[pr_review] ERROR: Invalid REVIEWER_NAME: ${REVIEWER_NAME}"
    exit 1
fi

_RAW_PROMPT="${REVIEWER_PROMPT_FILE:-}"
if [ -z "$_RAW_PROMPT" ]; then
    REVIEWER_PROMPT_FILE="$PROJ/ame-ai-review-system/review_prompt.txt"
elif [ "${_RAW_PROMPT#/}" = "$_RAW_PROMPT" ]; then
    REVIEWER_PROMPT_FILE="$PROJ/$_RAW_PROMPT"
else
    REVIEWER_PROMPT_FILE="$_RAW_PROMPT"
fi
CANONICAL_PROMPT=$(realpath -m "$REVIEWER_PROMPT_FILE")
if [[ "$CANONICAL_PROMPT" != "$PROJ/"* ]]; then
    echo "[pr_review] ERROR: REVIEWER_PROMPT_FILE escapes project root: ${REVIEWER_PROMPT_FILE}"
    exit 1
fi
REVIEWER_PROMPT_FILE="$CANONICAL_PROMPT"

REVIEWER_TOKEN_FILE="$HOME/.config/ame-ai-review-system/${REVIEWER_NAME}.token"
if [ -z "${REVIEWER_TOKEN:-}" ]; then
    if [ -f "$REVIEWER_TOKEN_FILE" ]; then
        REVIEWER_TOKEN=$(cat "$REVIEWER_TOKEN_FILE")
    else
        ENV_KEY=$(echo "${REVIEWER_NAME}" | tr '[:lower:]-' '[:upper:]_')_TOKEN
        REVIEWER_TOKEN="${!ENV_KEY:-}"
        if [ -z "$REVIEWER_TOKEN" ]; then
            echo "[pr_review] ERROR: REVIEWER_TOKEN not set, $REVIEWER_TOKEN_FILE not found, and \$${ENV_KEY} not set."
            exit 1
        fi
    fi
fi

_MAX_REVIEWS=20
git fetch origin "${BASE_REF}" --depth=100 2>/dev/null || true
if ! HEAD_SHA=$(git rev-parse HEAD 2>/dev/null); then
    echo "[pr_review] ERROR: Failed to get HEAD SHA."
    exit 1
fi
REVIEWED_SHAS=$(curl -s \
    "${GITEA_URL}/api/v1/repos/${REPO}/pulls/${PR_NUMBER}/reviews?limit=100" \
    -H "Authorization: token ${REVIEWER_TOKEN}" \
    | REVIEWER_NAME="$REVIEWER_NAME" python3 -c "
import json, sys, os, re
data = json.load(sys.stdin)
name = os.environ.get('REVIEWER_NAME', 'ame-ai-reviewer')
shas = set()
for r in data:
    if r.get('user', {}).get('login') == name:
        m = re.search(r'<!--\s*reviewed-sha:\s*([0-9a-f]{40,64})\s*-->', r.get('body', ''))
        if m:
            shas.add(m.group(1))
print(' '.join(shas))
" 2>/dev/null || echo "")
if echo "$REVIEWED_SHAS" | grep -qw "$HEAD_SHA"; then
    echo "[pr_review] Already reviewed HEAD SHA ${HEAD_SHA::8}, skipping."
    exit 0
fi
REVIEW_COUNT=$(echo "$REVIEWED_SHAS" | wc -w)
if [ "$REVIEW_COUNT" -ge "$_MAX_REVIEWS" ]; then
    echo "[pr_review] Already ${REVIEW_COUNT} push review(s) (max ${_MAX_REVIEWS}), skipping."
    exit 0
fi

DIFF=$(git diff "origin/${BASE_REF}...HEAD" 2>/dev/null || git diff HEAD~1 2>/dev/null || echo "")
CHANGED_FILES=$(git diff --name-only "origin/${BASE_REF}...HEAD" 2>/dev/null | head -50 || echo "")
COMMIT_LOG=$(git log "origin/${BASE_REF}..HEAD" --oneline 2>/dev/null | head -20 || echo "")

if [ -z "$DIFF" ]; then
    echo "[pr_review] No diff found, skipping review."
    exit 0
fi

DIFF_LINES=$(echo "$DIFF" | wc -l)
if [ "$DIFF_LINES" -gt 4000 ]; then
    echo "[pr_review] Diff truncated from ${DIFF_LINES} to 4000 lines."
    DIFF="$(set +o pipefail; printf '%s\n' "$DIFF" | head -4000)
... (truncated, ${DIFF_LINES} lines total)"
fi

cat "$REVIEWER_PROMPT_FILE" > "$PROMPT_IN"
{
    printf '%s\n' "" "## PR 情報"
    printf '%s\n' "- PR #: ${PR_NUMBER}"
    printf '%s\n' "- タイトル: ${PR_TITLE}"
    printf '%s\n' "- マージ先: ${BASE_REF}"
    printf '%s\n' "- 説明: ${PR_BODY:-（なし）}"
    printf '%s\n' "" "## 変更ファイル一覧" '```'
    printf '%s\n' "${CHANGED_FILES}"
    printf '%s\n' '```' "" "## コミット一覧" '```'
    printf '%s\n' "${COMMIT_LOG}"
    printf '%s\n' '```' "" "## diff" '```diff'
    printf '%s\n' "${DIFF}"
    printf '%s\n' '```'
} >> "$PROMPT_IN"

CLAUDE_MODEL="${CLAUDE_MODEL:-sonnet}"
if [[ ! "$CLAUDE_MODEL" =~ ^[a-zA-Z0-9._-]+$ ]]; then
    echo "[pr_review] ERROR: Invalid CLAUDE_MODEL: ${CLAUDE_MODEL}"
    exit 1
fi
echo "[pr_review] Running Claude Code review (model: $CLAUDE_MODEL)..."
claude -p \
    --model "$CLAUDE_MODEL" \
    --max-budget-usd 2.00 \
    --output-format json \
    --dangerously-skip-permissions \
    < "$PROMPT_IN" \
    > "$REVIEW_OUT" 2> "$CLAUDE_ERR"
REVIEW_EXIT=$?

if [ -s "$CLAUDE_ERR" ]; then
    echo "[pr_review] Claude stderr:"
    cat "$CLAUDE_ERR"
fi

if [ "$REVIEW_EXIT" -ne 0 ] || [ ! -s "$REVIEW_OUT" ]; then
    echo "[pr_review] Claude Code failed (exit=$REVIEW_EXIT) or empty output."
    cat "$REVIEW_OUT" || true
    exit 1
fi

echo "[pr_review] Building review payload ($(wc -c < "$REVIEW_OUT") bytes)..."

export BASE_REF PR_NUMBER
PAYLOADS=$(python3 "$PROJ/ame-ai-review-system/payload.py" "$REVIEW_OUT")

if [ -z "$PAYLOADS" ]; then
    echo "[pr_review] Failed to build review payload."
    exit 1
fi

PAYLOAD_COUNT=$(printf '%s' "$PAYLOADS" | python3 -c "import json,sys; print(len(json.load(sys.stdin)))")
echo "[pr_review] Posting ${PAYLOAD_COUNT} review(s) to PR #${PR_NUMBER} as ${REVIEWER_NAME}..."

BLOCKING_COUNT=0
for i in $(seq 0 $((PAYLOAD_COUNT - 1))); do
    PAYLOAD=$(printf '%s' "$PAYLOADS" | python3 -c "import json,sys; print(json.dumps(json.load(sys.stdin)[$i]))" "$i")
    HTTP_CODE=$(curl -s -o "$RESPONSE_TMP" -w "%{http_code}" \
        -X POST \
        "${GITEA_URL}/api/v1/repos/${REPO}/pulls/${PR_NUMBER}/reviews" \
        -H "Authorization: token ${REVIEWER_TOKEN}" \
        -H "Content-Type: application/json" \
        -d "$PAYLOAD")
    if [ "$HTTP_CODE" -ge 200 ] && [ "$HTTP_CODE" -lt 300 ]; then
        REVIEW_ID=$(python3 -c "import json,pathlib; d=json.loads(pathlib.Path('$RESPONSE_TMP').read_text()); print(d.get('id','?'))")
        echo "[pr_review] Review $((i+1))/${PAYLOAD_COUNT} posted (id=${REVIEW_ID}, HTTP ${HTTP_CODE})."
    else
        echo "[pr_review] Failed to post inline review $((i+1))/${PAYLOAD_COUNT} (HTTP ${HTTP_CODE}). Retrying as general comment..."
        # Fallback payload: convert inline comments to a general body review comment
        FALLBACK_PAYLOAD=$(printf '%s' "$PAYLOAD" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    comments = data.get('comments', [])
    if comments:
        bodies = []
        for c in comments:
            severity = c.get('severity', '')
            title = c.get('title', '')
            body_text = c.get('body', '')
            header = f'**[{severity}] {title}**\n\n' if severity or title else ''
            bodies.append(header + body_text)
        data['body'] = '\n\n---\n\n'.join(bodies)
        data['comments'] = []
    print(json.dumps(data))
except (json.JSONDecodeError, KeyError, TypeError):
    print('')
" 2>/dev/null || echo "")
        if [ -n "$FALLBACK_PAYLOAD" ]; then
            HTTP_CODE=$(curl -s -o "$RESPONSE_TMP" -w "%{http_code}" \
                -X POST \
                "${GITEA_URL}/api/v1/repos/${REPO}/pulls/${PR_NUMBER}/reviews" \
                -H "Authorization: token ${REVIEWER_TOKEN}" \
                -H "Content-Type: application/json" \
                -d "$FALLBACK_PAYLOAD")
            if [ "$HTTP_CODE" -ge 200 ] && [ "$HTTP_CODE" -lt 300 ]; then
                REVIEW_ID=$(python3 -c "import json,pathlib; d=json.loads(pathlib.Path('$RESPONSE_TMP').read_text()); print(d.get('id','?'))")
                echo "[pr_review] Review $((i+1))/${PAYLOAD_COUNT} posted as general comment (id=${REVIEW_ID}, HTTP ${HTTP_CODE})."
            else
                echo "[pr_review] Failed to post fallback review $((i+1))/${PAYLOAD_COUNT} (HTTP ${HTTP_CODE}). Skipping."
            fi
        else
            echo "[pr_review] Failed to build fallback payload. Skipping."
        fi
    fi
    # 指摘コメント（index > 0）に CRITICAL / HIGH / MIDDLE が含まれるか確認
    if [ "$i" -gt 0 ]; then
        IS_BLOCKING=$(printf '%s' "$PAYLOAD" | python3 -c "
import json, sys
payload = json.load(sys.stdin)
blocking = [c for c in payload.get('comments', [])
            if any(s in c.get('body', '') for s in ['CRITICAL', 'HIGH', 'MIDDLE'])]
print(len(blocking))
" 2>/dev/null || echo 0)
        BLOCKING_COUNT=$((BLOCKING_COUNT + IS_BLOCKING))
    fi
done

if [ "$BLOCKING_COUNT" -gt 0 ]; then
    echo "[pr_review] ${BLOCKING_COUNT} blocking issue(s) found by ${REVIEWER_NAME}."
else
    echo "[pr_review] No blocking issues found by ${REVIEWER_NAME}."
fi
