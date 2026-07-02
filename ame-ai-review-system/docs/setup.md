# セットアップガイド

本レビューシステムを別のリポジトリへ導入するためのセットアップ手順です。

## 1. 前提条件

| 項目           | 要件                                                                     |
| -------------- | ------------------------------------------------------------------------ |
| **Gitea**      | セルフホスト、Gitea Actions 有効化済みであること。                       |
| **ランナー**   | `ubuntu-latest` ラベルが割り当てられた Act ランナーであること。          |
| **Claude CLI** | ランナー上に `claude` コマンドがインストールされ、認証済みであること。   |
| **Python**     | Python 3.10 以上（外部依存ライブラリは不要、標準ライブラリのみで動作）。 |

### 1-1. 開発端末（ローカル環境）の準備

リポジトリ自体の Linter や型チェック（pre-commit）を動作させるための前提ツールと依存関係のセットアップ手順です。

```bash
# 前提ツールのインストール
# 1. uv のインストール
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

# 2. shellcheck / gitleaks のインストール
sudo apt update && sudo apt install -y shellcheck gitleaks

# 3. actionlint のインストール (バイナリダウンロードとチェックサム検証)
ACTIONLINT_VER=$(curl -s https://api.github.com/repos/rhysd/actionlint/releases/latest | grep -oP '"tag_name": "v\K[^"]+')
ACTIONLINT_ARCH=$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/')
ACTIONLINT_FILE="actionlint_${ACTIONLINT_VER}_linux_${ACTIONLINT_ARCH}.tar.gz"
curl -sSLO "https://github.com/rhysd/actionlint/releases/download/v${ACTIONLINT_VER}/${ACTIONLINT_FILE}"
curl -sSL "https://github.com/rhysd/actionlint/releases/download/v${ACTIONLINT_VER}/actionlint_${ACTIONLINT_VER}_checksums.txt" | sha256sum --check --ignore-missing
tar -xz -f "${ACTIONLINT_FILE}" -C ~/.local/bin actionlint
rm -f "${ACTIONLINT_FILE}"

# 仮想環境の作成と有効化
uv venv .venv --python 3.12
source .venv/bin/activate

# Python 依存ライブラリのインストール
uv pip install -r requirements-dev.txt

# Node.js 依存パッケージのインストール
npm ci

# Git フックの登録
pre-commit install --install-hooks -t pre-commit -t commit-msg -t pre-push
```

---

## 2. 移植手順

別のリポジトリに本システムを導入する手順は以下の通りです。

### Step 1: ファイルのコピー

本リポジトリの以下の2つのディレクトリを、導入先のリポジトリのルートに丸ごとコピーします。

- `.gitea/`
- `ame-ai-review-system/`

```bash
cp -r .gitea/ <your-repo>/
cp -r ame-ai-review-system/ <your-repo>/
```

### Step 2: レビュアー用アカウントの作成とトークンの登録

1. Gitea 管理画面にて、AIレビュアー専用の Gitea アカウント（例: `ame-ai-reviewer`）を作成する。
2. 作成したアカウントでログインし、**[Settings] -> [Applications] -> [Generate Token]** より Access
   Token を生成する。
   - スコープ: `repository` (read + write)
3. 導入先のリポジトリの設定画面で Secret を追加する。
   - **[Settings] -> [Secrets] -> [Add Secret]**
   - 名前: `REVIEWER_TOKEN`
   - 値: 生成した Access Token

### Step 3: ワークフローの設定確認と修正

`.gitea/workflows/review.yml` および `review_reply.yml` を開き、環境変数を変更します。

```yaml
env:
  REVIEWER_NAME: ame-ai-reviewer # 作成したレビュアーのアカウント名と一致させる
```

---

## 3. 動作確認

1. フィーチャーブランチで変更をコミットし、プッシュする。
2. Gitea 上で PR を作成する。
3. `AI Code Review` ジョブが起動し、PR にインラインコメント（レビュー）が投稿されることを確認する。
4. 投稿されたコメントのスレッドに対して `@ame-ai-reviewer 修正しました` のように返信する。
5. `AI Review Reply` ジョブが起動し、自動的に LGTM または追加指摘が返信されることを確認する。
