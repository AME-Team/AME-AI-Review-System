# AME-AI-Review-System

> **「静的解析（Linter/型検査）」と「AIレビュー」を融合し、ローカル（pre-commit）と CI（PR）の二重ゲートでコード品質を担保する、簡単移植可能な開発フィロソフィー（IPアセット）パッケージ。**

## 概要

本システムは、ローカル（pre-commit）と CI（PR）の両方で「静的解析と AI レビュー」を組み合わせる仕組みです。二重の品質ゲートにより、高品質なコード管理（IPアセット）を簡単に導入します。

機械的な「Linterや型検査」を前段で実行し、無駄な LLM コストを削減する Circuit
Breaker を備えています。ローカルで早期に検知する Shift-Left を徹底し、高品質なコードのみが PR に到達するよう強制します。

### 二重の品質ゲート構成

```text
[ ローカル開発 (Git Commit) ]
  └── Gate 1: pre-commit ゲート (静的解析 + AI レビュー)
        └── staged ファイルに対し ruff/mypy/semgrep を実行。パスした場合のみローカル AI レビューを実行。

[ CI/CD 環境 (Pull Request) ]
  └── Gate 2: PR ゲート (Circuit Breaker 静的解析 + AI レビュー)
        └── コメント `/request-review` 時に ruff/mypy/semgrep を実行。エラーが 0 件の場合のみ AI レビューを実行。
```

> [!NOTE]
> **push時の自動レビューはデフォルトでOFF**です。コメントでの依頼を推奨します。有効化はリポジトリ設定
> **[Settings] → [Actions] → [Variables]** で `PUSH_REVIEW_ENABLED` を `true` に設定してください。

本リポジトリは、別のプロジェクトへ `.github/` と `ame_ai_review_system/`
をコピペするだけで、この仕組みを移植可能です。

## 特徴

- **コマンド駆動のレビュー**: PR コメントで `/request-review`
  を入力したタイミングでレビューが走る。push 時の自動実行は GitHub Variables `PUSH_REVIEW_ENABLED`
  で ON/OFF 可能（デフォルト OFF）。
- **pre-commit 時の AI レビュー**: `git commit`
  時にローカルで AI レビューが走り、指摘があればコミットをブロックする（デフォルト ON）。PR レビューと同じプロンプトを使用し、LOW レベル指摘のみ 2 回連続で無限ループ回避の escape
  hatch を用意。前段の静的解析 (ruff / mypy / semgrep) が全て pass した場合のみ AI レビューする。
  `precommit_require_static_checks` で ON/OFF 可能（デフォルト ON）。
- **PR レビューの Circuit Breaker**: `/request-review` 実行時に ruff / mypy /
  semgrep の静的解析を先行実行する。1件でもエラーがあれば AI レビューをスキップしてトークン消費を抑制する。
  `pr_review_require_static_checks` で ON/OFF 可能（デフォルト ON）。
- **Semgrep カスタムルール**: CLAUDE.md §8 のコーディング規約を Semgrep で機械的に検出する。broad
  exception catch 禁止・kill -15 $pids 禁止・echo|python3 -c 禁止 等。ルールは
  `ame_ai_review_system/.semgrep/rules.yml`。
- **プロンプトキャッシュ最適化**: 返信判定プロンプトの固定セクションを先頭に配置する。動的セクション（diff・返信）を末尾に配置し Claude
  API のキャッシュヒット率を最大化。
- **Reasoning Effort の役割別制御**: レビュー時と返信判定時で model /
  thinking を個別設定可能。`review_model`/`reply_model`/
  `review_thinking`/`reply_thinking`。返信判定は haiku/low で推論トークンを削減。
- **Stale-Loop 検出**: レビュアーが同じ指摘を言い換えて繰り返す膠着状態を Jaccard 類似度 (80%閾値) で検出し、強制 LGTM で胶着を打破する。
- **Diff 圧縮**: git
  diff のメタデータ行・バイナリ差分・連続空行を除去し（RTK アプローチ）、LLM 入力トークンを削減。
- **実装エンジンの自動検出**: 実装に使っている AI ツールをプロセスツリーから自動検出する (`precommit_engine="auto"`)。OpenCode +
  GLM-5.2 で実装していれば同じ組合せでレビューする。PR レビューとは独立してエンジン/モデル/思考量を
  `config.json` の `precommit_*` キーや環境変数で上書き可能。
- **ユーザー固有設定オーバーライド**:
  `config.user.json`（Git 管理対象外）で環境依存の設定（エンジン・モデル・思考量など）を上書き可能。`config.json`
  より優先される。
- **超簡単移植**: `.github/` と `ame_ai_review_system/`
  の2つのディレクトリを他リポジトリにコピーするだけで導入完了。GitHub
  Actions と AI レビュー機能が自動で有効化される。
- **対話型の修正サイクル**: 開発者が `@<レビュアー名>`
  で返信すると、AI が最新コードを再評価してスレッドに返答。
- **重大度ラベル**: 指摘を `CRITICAL` / `HIGH` / `MIDDLE` / `LOW` の 4 段階で分類。
- **複数レビュアー対応**: ジョブの追加だけで、役割の異なる複数のレビュアーを追加可能。
- **マルチエンジン**: `config.json` / 環境変数で Claude Code・OpenCode・Antigravity
  CLIを切り替え可能。エンジン・モデル・思考量(high/medium/low)を設定ファイルで指定できる。

## ランディングページ

プロダクトの設計概要や、コミット前（Gate 1）およびプルリクエスト時（Gate
2）の品質チェックフローをブラウザ上でシミュレーションできるインタラクティブな紹介サイトを同梱しています。

### 起動・ビルドコマンド

```bash
# 依存パッケージのインストール
npm install

# 開発サーバーの起動 (http://localhost:5173)
npm run dev --workspace=landing-page

# 本番用ビルドの実行
npm run build --workspace=landing-page

# ビルド成果物のローカルプレビュー
npm run preview --workspace=landing-page
```

## ディレクトリ構成

```text
.github/
  workflows/
    review.yml            # PR作成/プッシュ時にレビューを実行するワークフロー（設定で OFF 可能）
    review_command.yml    # `/request-review` コメントでレビューを実行するワークフロー
    review_reply.yml      # コメント返信時に自動返答を実行するワークフロー
    ci.yml                # 本リポジトリのCI設定（pre-commit / pytest / pyright）

ame_ai_review_system/    # ★他のリポジトリに丸ごとコピーする資材
  main.py                # CLI エントリポイント（review / checkout / post-push / setup サブコマンド）
  reply.py               # 返信プロンプト生成・スレッド解析・stale-loop検出
  github_client.py       # GitHub REST/GraphQL API 共通クライアント（Resolve 等の GraphQL 操作を含む）
  engine.py              # LLM エンジンアダプタ（claude/opencode/antigravity を切替・role別設定）
  payload.py             # モデル出力 -> GitHub API ペイロード変換
  review_config.py       # 設定読み込み・コマンド判定ヘルパ
  static_precheck.py     # PR レビュー前段の静的解析 pre-check（Circuit Breaker）
  diff_utils.py          # diff 圧縮ユーティリティ（RTK アプローチ）
  pr_streak.py           # PR レビューの streak 管理（2回連続LOWで終了）
  precommit_review.py    # pre-commit AI レビュー本体
  precommit_engine.py    # pre-commit レビューのエンジン解決・自動検出
  precommit_state.py     # pre-commit レビューの状態管理モジュール
  post_commit_reset.py   # post-commit で streak カウンタをリセット
  mermaid_check.py       # Mermaid 記法バリデータ
  setup.py               # 開発環境セットアップ補助
  config.json            # 動作設定（push/precommit 自動レビューの ON/OFF、エンジン/モデル/思考量 等）
  review_prompt.txt      # レビュアーへのプロンプト（レビュー観点・静的解析移管後の軽量版）
  .semgrep/rules.yml     # Semgrep カスタムルール（CLAUDE.md §8 コーディング規約の機械的強制）
  VERSION                # バージョン情報

  docs/                   # 同梱ドキュメント
    setup.md              # 移植・セットアップ手順
    architecture.md       # システムアーキテクチャ・処理の流れ
    customization.md      # プロンプトやレビュアーのカスタマイズ
    troubleshooting.md    # よくあるエラーと対処法
    instructions.md       # AIレビューフロー指示書（開発者・AIエージェント向け）

scripts/
  linux/
    with_headroom.sh           # AI レビューコマンドを headroom プロキシ経由で実行するラッパー
    pr_review_reply.sh         # レビュー返信ワークフロー互換のレガシーパス（互換ラッパ）
  precommit_hygiene.py         # pre-commit 関連の補助スクリプト
  check_suppression_comments.py  # 抑制コメント検証スクリプト
```

## クイックスタート

他プロジェクトへの導入は非常にシンプルです。

1. **資材のコピー**: `.github/` と `ame_ai_review_system/` を対象リポジトリのルートにコピーする。
2. **GitHub App の登録と Secret 設定**: レビュー用の GitHub
   App を作成し、対象リポジトリにインストールする。App の Credentials として以下を Secrets に登録する。
   - `AME_AI_REVIEWER_APP_ID` : GitHub App の App ID（数値）
   - `AME_AI_REVIEWER_APP_PRIVATE_KEY` : 生成した Private Key（`.pem` 内容全体）

   必要な App 権限: `Contents: Read` / `Pull requests: Read & Write` /
   `Issues: Read & Write`。CI ワークフローは `actions/create-github-app-token@v2`
   で都度インストールトークンを取得する。

3. **プロンプトの調整**: `ame_ai_review_system/review_prompt.txt`
   をプロジェクトの規約や観点に合わせてカスタマイズする。
4. **レビュー依頼**: PR を作成したら、PR コメントで `/request-review` を入力してレビューを依頼する。

> [!NOTE] **pre-commit 時の AI レビューもデフォルトで有効** です。`git commit`
> 時にローカルで AI レビューが走り、指摘があればコミットをブロックします。PR レビューとは独立して
> `ame_ai_review_system/config.json` の `precommit_review_enabled` で ON/OFF できます。利用には
> `pre-commit install --install-hooks -t pre-commit -t commit-msg -t pre-push -t post-commit`
> で post-commit フックもインストールする必要があります。

ユーザー固有の設定は
`ame_ai_review_system/config.user.json`（Git 管理対象外）で上書き可能です。例えば Gate
1 のエンジンだけ変更したい場合は `{"precommit_engine": "claude", "precommit_model": "sonnet"}`
のように記述します。詳細は[カスタマイズガイド](ame_ai_review_system/docs/customization.md)を参照。

より詳細な手順は、[セットアップガイド](ame_ai_review_system/docs/setup.md) を参照してください。

## 関連ドキュメント

- [セットアップガイド](ame_ai_review_system/docs/setup.md) — 移植手順と初期設定の詳細
- [アーキテクチャ解説](ame_ai_review_system/docs/architecture.md) — システムの処理シーケンスと仕組み
- [カスタマイズガイド](ame_ai_review_system/docs/customization.md)
  — プロンプトの修正、複数レビュアーの追加
- [自動レビュー対応フロー指示書](ame_ai_review_system/docs/instructions.md)
  — 人間・AI がレビューに対応するための手順とルール
- [トラブルシューティング](ame_ai_review_system/docs/troubleshooting.md)
  — 動作しない、無限ループが発生したなどの対応
- [開発フロー (CLAUDE.md)](CLAUDE.md) — 本リポジトリ開発者向けの運用ルール
