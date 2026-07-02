# レビュアーとルールのカスタマイズ

本システムでは、レビューの観点（プロンプト）の変更や、役割が異なる複数の AI レビュアーの追加を簡単に行うことができます。

## 1. レビュー観点（プロンプト）の変更

AI が指摘する観点や規約を変更するには、以下のファイルを修正します。

- **`ame-ai-review-system/review_prompt.txt`**

### カスタマイズのヒント

- **プロジェクト固有のルールの追加**: `## レビュー観点` や `## コーディング規約`
  の項目に、開発チーム内で定めたルールや非推奨な記述を記述する。
- **出力フォーマットの維持**: プロンプトの最後にある `## 出力フォーマット（厳守）`
  セクションは**絶対に書き換えない**。この構造が変わると、Giteaへのコメント登録時のパース処理が失敗する。

---

## 2. 複数のレビュアーを追加する手順

例として、コード品質をレビューする `general-reviewer` に加え、セキュリティを厳しくチェックする
`security-reviewer` を追加する手順を示す。

### Step 1: 新しいプロンプトファイルの用意

`ame-ai-review-system/` 内に、新しいプロンプトファイル（例:
`security_review_prompt.txt`）を配置します。

### Step 2: Gitea Secrets の登録

新レビュアーアカウントのトークンを Gitea の Secret に追加します（例: `REVIEWER_TOKEN_SECURITY`）。

### Step 3: `review.yml` にジョブを追加

`.gitea/workflows/review.yml` に、新レビュアー用のジョブを追加します。

```yaml
security-review:
  name: Security Review (security-reviewer)
  runs-on: ubuntu-latest
  timeout-minutes: 10
  steps:
    - name: Checkout
      uses: actions/checkout@v4
      with:
        fetch-depth: 0
    - name: Run Security Review
      env:
        GITEA_URL: ${{ github.server_url }}
        REVIEWER_TOKEN: ${{ secrets.REVIEWER_TOKEN_SECURITY }}
        REVIEWER_NAME: security-reviewer
        REVIEWER_PROMPT_FILE: ame-ai-review-system/security_review_prompt.txt
        PR_NUMBER: ${{ github.event.pull_request.number }}
        PR_TITLE: ${{ github.event.pull_request.title }}
        PR_BODY: ${{ github.event.pull_request.body }}
        BASE_REF: ${{ github.base_ref }}
      run: |
        bash ame-ai-review-system/pr_review.sh
```

### Step 4: `review_reply.yml` の修正（重要）

新レビュアーからの返信も判定対象とするため、`.gitea/workflows/review_reply.yml` へ `if`
条件およびジョブを追加する。

> [!IMPORTANT] 返信ループ（カスケード）を防ぐため、他ジョブの `if`
> 条件にも互いのレビュアーのアカウント名を除外するように設定する必要があります。

```yaml
# 既存の一般レビュアー用ジョブの if 条件
general-review-reply:
  if: >-
    github.event.comment.user.login != 'ame-ai-reviewer' && github.event.comment.user.login !=
    'security-reviewer' && contains(github.event.comment.body, '@ame-ai-reviewer')
```

また、セキュリティレビュアー用の返信ジョブを追加します。

```yaml
security-review-reply:
  name: Security Review Reply (security-reviewer)
  runs-on: ubuntu-latest
  if: >-
    github.event.comment.user.login != 'ame-ai-reviewer' && github.event.comment.user.login !=
    'security-reviewer' && contains(github.event.comment.body, '@security-reviewer')
  steps:
    - name: Checkout
      uses: actions/checkout@v4
      with:
        fetch-depth: 0
    - name: Switch to PR branch
      env:
        GITEA_URL: ${{ github.server_url }}
        REPO: ${{ github.repository }}
        PR_NUMBER: ${{ github.event.issue.number }}
        TOKEN: ${{ secrets.REVIEWER_TOKEN_SECURITY }}
      run: |
        PR_JSON_TMP=$(mktemp)
        cleanup() { rm -f "$PR_JSON_TMP"; }
        trap cleanup EXIT
        HTTP_CODE=$(curl -s -o "$PR_JSON_TMP" -w "%{http_code}" \
          "${GITEA_URL}/api/v1/repos/${REPO}/pulls/${PR_NUMBER}" \
          -H "Authorization: token ${TOKEN}")
        if [ "$HTTP_CODE" -lt 200 ] || [ "$HTTP_CODE" -ge 300 ]; then
          echo "[review_reply] ERROR: Failed to fetch PR info (HTTP ${HTTP_CODE})"
          exit 1
        fi
        PR_JSON=$(cat "$PR_JSON_TMP")
        BRANCH=$(printf '%s\n' "$PR_JSON" | python3 -c "
        import json,sys
        print(json.load(sys.stdin)['head']['ref'])
        ")
        BASE=$(printf '%s\n' "$PR_JSON" | python3 -c "
        import json,sys
        print(json.load(sys.stdin)['base']['ref'])
        ")
        if [[ ! "$BASE" =~ ^[a-zA-Z0-9/_.-]+$ ]]; then
            echo "[review_reply] ERROR: Invalid BASE_REF: ${BASE}"
            exit 1
        fi
        echo "BASE_REF=${BASE}" >> "$GITHUB_ENV"
        git fetch origin "${BRANCH}"
        git checkout "${BRANCH}"
    - name: Run reply handler
      env:
        REVIEWER_TOKEN: ${{ secrets.REVIEWER_TOKEN_SECURITY }}
        REVIEWER_NAME: security-reviewer
        PR_NUMBER: ${{ github.event.issue.number }}
        GITEA_URL: ${{ github.server_url }}
        GITHUB_REPOSITORY: ${{ github.repository }}
      run: |
        bash ame-ai-review-system/pr_review_reply.sh
```

---

## 3. レビュー対象外のファイル設定

画像ファイルやドキュメント、外部ライブラリなどのファイルを AI のレビュー対象から外したい場合、`pr_review.sh`
を直接書き換えるか、あるいは Git のコマンドで除外する。

通常、`git diff` を実行して差分を抽出する際に、パスを指定して除外できる。

例として、`pr_review.sh` の diff 抽出箇所を以下のように変更する。

```bash
DIFF=$(git diff "origin/${BASE_REF}...HEAD" -- . ':(exclude)*.md' ':(exclude)vendor/*' 2>/dev/null || ...)
```

このように記述することで、Markdown ファイルや `vendor/`
ディレクトリ配下の差分が Claude へのプロンプトから除外される。
