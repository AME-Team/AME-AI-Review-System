# セットアップガイド

本ガイドは、静的解析とAIレビューを組み合わせた二重ゲートのレビューシステムを別のリポジトリへ導入するための手順です。

## 1. 前提条件

| 項目         | 要件                                                                                                                                                                                                                                                                                            |
| ------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Gitea**    | セルフホスト、Gitea Actions 有効化済みであること。                                                                                                                                                                                                                                              |
| **ランナー** | `ubuntu-latest` ラベルが割り当てられた Act ランナーであること。Docker ベース（推奨）または host モードのいずれかで動作。host モードで運用する場合は Python 3.12 / Node.js 22 / shellcheck / actionlint / gitleaks をホスト上に事前インストールすること（ci.yml では自動インストールされない）。 |
| **LLM CLI**  | 使用するエンジンの CLI（既定: `claude`）がランナー上にインストールされ、認証済みであること。`opencode` / `agy`(Antigravity) に切り替える場合はそれぞれの CLI が必要（[アーキテクチャ](architecture.md)参照）。                                                                                  |
| **Python**   | Python 3.10 以上（外部依存ライブラリは不要、標準ライブラリのみで動作）。                                                                                                                                                                                                                        |

### 1-1. Docker ランナーのセットアップ（推奨）

本リポジトリの `Dockerfile` で CI ツールをプリインストールしたジョブ実行イメージをビルドする。
`docker-compose.yml` で `gitea/act_runner` 公式イメージによるランナーデーモンを起動する。

プリインストールされるツール（ジョブ実行イメージ）は以下の通り。

- Python 3.12
- Node.js 22
- shellcheck
- actionlint
- gitleaks
- Claude CLI
- OpenCode CLI
- headroom (コンテキスト圧縮プロキシ)

> [!NOTE] **CI/セキュリティツールのバージョン管理** shellcheck / actionlint /
> gitleaks は既知脆弱性回避のため GitHub Releases から latest を取得する。GitHub API rate
> limit により取得失敗時は FALLBACK バージョンを使用する。FALLBACK バージョンは Dockerfile にハードコードされているため、四半期を目安に見直すことを推奨する。

#### Step 1: ジョブ実行イメージのビルド

```bash
docker build -t ame-ai-review-runner:latest .
```

#### Step 2: 登録トークンの取得

Gitea の Web UI でランナー登録トークンを取得する。

- **インスタンス管理者**: Site Administration → Actions → Runners → "Create new Runner"
- **リポジトリ管理者**: Settings → Actions → Runners → "Create new Runner"

#### Step 3: .env ファイルの作成

リポジトリルートに `.env` ファイル（Git 管理対象外）を作成し、取得したトークンを記述する。

```bash
echo 'RUNNER_REGISTRATION_TOKEN=<トークン>' > .env
```

#### Step 4: ランナーの起動

**手動起動（確認用）:**

```bash
./start-runner.sh
```

`start-runner.sh` は WSL2 IP を自動検出し、`GITEA_INSTANCE_URL` を設定して `docker compose up -d`
を実行する。Gitea UI の Runners 一覧に "local-runner" が **online**
で表示されれば成功。2 回目以降はトークン不要（登録情報は Docker volume に永続化）。

#### Step 5: systemd サービス化（推奨）

WSL2 起動時にランナーが自動起動するよう systemd サービスを登録する。
`scripts/linux/act-runner.service` の `User` と `WorkingDirectory` を環境に合わせて編集する。

```bash
# サービスファイルをインストール
sudo cp scripts/linux/act-runner.service /etc/systemd/system/

# ユーザ・パスを環境に合わせて編集
sudo vi /etc/systemd/system/act-runner.service

# サービス有効化・起動
sudo systemctl daemon-reload
sudo systemctl enable --now act-runner
```

サービスは Docker Desktop 起動を待機してから `docker compose up` （foreground）を実行する。Docker
Desktop 再起動時も自動復旧する。

```bash
# 状態確認
systemctl status act-runner

# ログ確認
journalctl -u act-runner -f

# 停止・再起動
sudo systemctl stop act-runner
sudo systemctl restart act-runner
```

#### セキュリティ Sandbox（任意）

ジョブ実行コンテナのセキュリティを強化するオプション。以下の施策を `runner-config.yaml` の
`container.options` で有効化できる。

| #   | 施策             | 設定方法                                                                         | 優先度 |
| --- | ---------------- | -------------------------------------------------------------------------------- | ------ |
| 1   | 非 root ユーザー | `Dockerfile` 内 `USER gitea-runner`（デフォルトで有効）                          | HIGH   |
| 2   | cap-drop=ALL     | `container.options: "--cap-drop=ALL"`                                            | HIGH   |
| 3   | Read-only rootfs | `container.options: "--read-only"`                                               | MEDIUM |
| 4   | seccomp          | `container.options: "--security-opt seccomp=/abs/path/to/.seccomp/profile.json"` | MEDIUM |
| 5   | cgroups 制限     | `container.options: "--memory=2g --cpus=1.0"`                                    | LOW    |

有効化する場合は `runner-config.yaml` の `container` セクションに `options` を追記する。

```yaml
container:
  network: "runner-net"
  options:
    "--cap-drop=ALL --security-opt seccomp=/abs/path/to/.seccomp/profile.json --memory=2g --cpus=1.0"
```

`.seccomp/profile.json`
は Docker のデフォルトプロファイルをベースにしている。以下のシステムコールを追加で禁止する。

- `mount`
- `umount2`
- `ptrace`
- `setns`
- `unshare`
- `reboot`

### 1-2. 開発端末（ローカル環境）の準備

リポジトリ自体の Linter や型チェック（pre-commit）を動作させるための前提ツールと依存関係のセットアップ手順です。

#### エンジン認証トークンの生成

各 LLM エンジンの長期トークンを生成します。使用するエンジンのみ実行してください。

**Claude（Anthropic）の場合:**

```bash
claude setup-token
```

> 生成されたトークンは `~/.claude/.credentials.json` に保存されます。

**OpenCode の場合:**

```bash
opencode providers login
```

> プロバイダーを選択し、API キーを入力します。認証情報は `~/.local/share/opencode/auth.json`
> に保存されます。

**OpenCode + OpenRouter の場合（API Key 認証）:**

OpenCode は OpenRouter を公式プロバイダーとしてサポートしている。OpenRouter 経由で外部モデル（例:
`Tencent/Hy3`）を使う場合、以下の手順で API Key を登録する。

1. [OpenRouter Dashboard](https://openrouter.ai/settings/keys) で "Create API Key" をクリックし、API
   Key をコピーする。
2. OpenCode の認証コマンドを実行し、**OpenRouter** を選択して API Key を貼り付ける。TUI の
   `/connect` または CLI の `opencode providers login` のいずれでも登録可能であり、どちらも
   `~/.local/share/opencode/auth.json` に保存される。

   ```bash
   opencode providers login   # CLI で認証（プロンプトに従って OpenRouter を選択）
   ```

   > OpenRouter 経由のモデル名は `openrouter/<org>/<model>` 形式で指定する。例:
   > `openrouter/tencent/hy3:free`。`/models` コマンドで利用可能なモデルを確認できる。

3. **ローカル（Gate 1）で使う場合**: `ame_ai_review_system/config.user.json`
   を作成し、モデル名を指定する。

   ```json
   {
     "precommit_engine": "opencode",
     "precommit_model": "openrouter/tencent/hy3:free",
     "precommit_thinking": "medium"
   }
   ```

4. **CI（Gate 2）で使う場合**: 認証ファイルを Base64 化して Gitea
   Secret に登録する。Variables にエンジン・モデルを設定する（[カスタマイズガイド §6](customization.md#6-ci-gate-2-のカスタマイズ)参照）。

**Antigravity（Google Gemini）の場合:**

```bash
agy --login
```

> ブラウザで Google アカウントの OAuth 認証が開始されます。認証後、refresh トークンが
> `~/.gemini/antigravity-cli/antigravity-oauth-token` に自動保存されます。

#### 前提ツールのインストール

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
pre-commit install --install-hooks -t pre-commit -t commit-msg -t pre-push -t post-commit
```

> [!IMPORTANT] **pre-commit AI レビューを使う場合は `-t post-commit` が必須**
> です。post-commit フックが無いと、コミット成功時の streak リセットが走りません。

---

## 2. 移植手順

別のリポジトリに本システムを導入する手順は以下の通りです。

### Step 1: ファイルのコピー

本リポジトリの以下のディレクトリおよびファイルを、導入先のリポジトリのルートに丸ごとコピーします。

- `.gitea/`
- `ame_ai_review_system/`
- `Dockerfile`
- `.seccomp/`

```bash
cp -r .gitea/ <your-repo>/
cp -r ame_ai_review_system/ <your-repo>/
cp Dockerfile <your-repo>/
cp -r .seccomp/ <your-repo>/
```

### Step 2: レビュアー用アカウントの作成とトークンの登録

1. Gitea 管理画面にて、AIレビュアー専用の Gitea アカウント（例: `ame-ai-reviewer`）を作成する。
2. 作成したアカウントでログインし、**[Settings] -> [Applications] -> [Generate Token]** より Access
   Token を生成する。
   - スコープ: `repository` (read + write)
3. 導入先のリポジトリの設定画面で Secret を追加する。
   - **[Settings] -> [Secrets] -> [Add Secret]**
   - 名前: `AME_AI_REVIEWER_TOKEN`
   - 値: 生成した Access Token

> [!NOTE] 本リポジトリのワークフロー（`review_command.yml` / `review.yml` / `review_reply.yml`）は
> `AME_AI_REVIEWER_TOKEN` という Secret 名を参照します。別のレビュアーを追加する場合は
> `<REVIEWER_NAME>_TOKEN`
> のような命名規則で Secret を追加してください（[カスタマイズガイド](customization.md)参照）。

### Step 3: ワークフローの設定確認と修正

`.gitea/workflows/review_command.yml` および `review_reply.yml` を開き、環境変数を変更します。

```yaml
env:
  REVIEWER_NAME: ame-ai-reviewer # 作成したレビュアーのアカウント名と一致させる
```

### Step 4: 動作設定（`config.json`）

`ame_ai_review_system/config.json` でレビューの動作を制御します。

```json
{
  "precommit_review_enabled": true,
  "precommit_require_static_checks": true,
  "precommit_engine": "auto"
}
```

| キー                              | デフォルト | 説明                                                                                                                                     |
| --------------------------------- | ---------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `precommit_review_enabled`        | `true`     | `true` にすると `git commit` 時にローカルで AI レビューが走り、指摘があればコミットをブロックする。                                      |
| `precommit_require_static_checks` | `true`     | `true` の場合、AI レビュー実行前に ruff / mypy を staged ファイルに対して実行し、全て pass した場合のみ AI レビューを実行する。          |
| `precommit_engine`                | `"auto"`   | pre-commit レビューのエンジン。`"auto"` で実装に使っているツールを自動検出。`"claude"` / `"opencode"` / `"antigravity"` で明示指定も可。 |
| `precommit_model`                 | (なし)     | pre-commit レビューのモデルを明示指定。省略時はエンジン既定値 (opencode なら実装で使っているモデル)。                                    |
| `precommit_thinking`              | (なし)     | pre-commit レビューの思考量。省略時は PR の `thinking` を継承。                                                                          |
| `precommit_review_budget_usd`     | (なし)     | pre-commit レビュー専用の予算 (Claude のみ効果)。省略時は PR の `review_budget_usd` を継承。                                             |

> [!NOTE] **push 時の自動レビュー**は Gitea のリポジトリ変数で制御します。 **[Settings] → [Actions]
> → [Variables]** で `PUSH_REVIEW_ENABLED` を作成し、有効化したい場合のみ値を `true`
> にしてください（未設定 = OFF がデフォルトのまま維持される）。

> [!NOTE] **pre-commit AI レビューのエンジン自動検出** `precommit_engine: "auto"`
> (既定) の場合、pre-commit フックが自身のプロセスツリーを親方向へたどり、`opencode` / `claude` /
> `agy` (Antigravity) のいずれかを検出します。例えば OpenCode セッション内で `git commit`
> すると、自動的に OpenCode とその既定モデル (= 実装に使っているモデル) でレビューが走ります。PR レビューとは独立して環境変数
> `PRECOMMIT_REVIEW_ENGINE` / `PRECOMMIT_REVIEW_MODEL` でも上書き可能です。
>
> **無限ループ回避**:
> LOW レベルの指摘のみが 2 回連続で続いた場合は、コミットを通す仕様。コミット成功時に streak カウンタは 0 にリセットされる（post-commit フック）。エンジン失敗時は fail-closed でコミットをブロックする。
>
> **前段の静的解析が必須** `precommit_require_static_checks: true`
> (既定) の場合、AI レビュー実行前に ruff check / ruff format --check /
> mypy を staged された Python ファイルに対して実行し、全て pass した場合のみ AI レビューを実行します。LLM
> API コストの節約と、フォーマット違反などの単純な指摘の AI レビューへの回送を防ぐための仕組みです。

### Step 5: ユーザー固有設定（`config.user.json`・任意）

環境依存の設定（エンジン・モデル・思考量など）は `ame_ai_review_system/config.user.json`
に記述できます。このファイルは **Git 管理対象外**（`.gitignore` に登録済み）で、`config.json`
より優先されます。存在しない場合は無視されます。

```json
{
  "precommit_engine": "claude",
  "precommit_model": "sonnet",
  "precommit_thinking": "medium"
}
```

> [!TIP] 環境変数 `AME_REVIEW_USER_CONFIG` で `config.user.json` のパスを変更できます。

---

## 3. 動作確認

### 3-1. ローカルでの動作確認（Gate 1: pre-commit ゲート）

1. **静的解析の検証**
   - Pythonファイル等に適当なフォーマット崩れや構文エラーを意図的に含め、`git add` してから
     `git commit -m "test"` を実行する。
   - `ruff check` や `mypy`
     などの前段の静的解析でコミットがブロックされ、AIレビューが実行されないことを確認する。
2. **AIレビューの検証**
   - 静的解析エラーを修正して `git commit` を実行する。
   - 静的解析がすべて PASS し、`AI Code Review (pre-commit)`
     フックが実行され、LLMによるコードレビューが走ることを確認する。
   - 指摘事項がある場合、コミットがブロックされ、指摘内容が表示されることを確認する。
3. **streak機能の検証**
   - コミットがブロックされた後、コードを微修正して再度コミットを繰り返す。
   - `LOW`
     レベル以下の軽微な指摘のみが 2 回連続した（streak が 2 に達した）場合に、無限ループを回避するエスケープハッチによりコミットが通ることを確認する。

### 3-2. CI/CD環境での動作確認（Gate 2: PR ゲート）

1. **静的解析 Circuit Breaker の検証**
   - 静的解析エラー（Linter警告や型エラー）を含んだコードを、`SKIP`
     変数を用いてコミットし、プッシュして PR を作成する。

     ```bash
     # 静的解析フック（ruff/mypy/semgrep）のみをスキップしてコミット
     SKIP=ruff,mypy,semgrep-custom git commit -m "test: verify circuit breaker"
     ```

     > [!WARNING] この `SKIP` 指定コミットは Circuit
     > Breaker 動作確認専用である。通常の開発では使用しない。

   - PR コメントで `/request-review` を入力する。
   - PR に静的解析エラーが存在する場合、`static_precheck.py`（Circuit
     Breaker）がそれを検知し、AI レビューをスキップすることを確認する。
2. **AIレビューと対話サイクルの検証**
   - PR上のすべての静的解析エラーを解消してプッシュする。
   - 再度 PR コメントで `/request-review`（または `/review`）を入力する。
   - `AI Code Review (Command)`
     ジョブが起動し、PR にインラインコメント（レビュー）が投稿されることを確認する。
3. **返信とResolveの検証**
   - 投稿されたコメントのスレッドに対して、修正を加えた後に `@ame-ai-reviewer 修正しました`
     のように返信する。
   - `AI Review Reply` ジョブが起動し、自動的に `LGTM` または追加指摘が返答されることを確認する。
   - `LGTM` が届いたスレッドを「Resolve（解決済み）」に変更し、全スレッド Resolve 後に再度
     `/request-review` で再レビューを依頼する。

### 3-3. ランディングページの起動確認

本リポジトリに同梱されている Vite ベースのランディングページ（紹介サイト）の起動・動作確認手順です。

1. **開発用サーバーの起動** リポジトリのルートディレクトリで以下を実行する。

   ```bash
   npm run dev --workspace=landing-page
   ```

2. **ブラウザでの確認** ブラウザで `http://localhost:5173`
   を開き、インタラクティブなコミットシミュレーターや各種設定スニペットの切り替え表示が正しく動作することを確認する。
3. **本番用ビルドとプレビュー（任意）**
   本番用にコンパイルしてローカルでプレビューする場合は、以下を実行する。

   ```bash
   # ビルドを実行
   npm run build --workspace=landing-page
   # ビルド成果物をプレビュー (http://localhost:4173)
   npm run preview --workspace=landing-page
   ```

   詳細な起動・開発手順については、[landing-page/README.md](../../landing-page/README.md)
   も参照すること。
