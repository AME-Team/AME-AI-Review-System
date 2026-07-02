# AME-AI-Review-System

> Gitea Actions と Claude (Sonnet) を組み合わせた、簡単移植可能な AI コードレビューシステム。

## 概要

Pull Request を作成・更新すると、Claude
(Sonnet) が自動でコードレビューし、Gitea の PR にインラインコメントを投稿します。開発者がコメントに
`@<レビュアー名>`
で返信すると、Claude が PR の最新 diff を再読込して LGTM か追加指摘かを判断し、スレッドへ自動返信します。

本リポジトリは、AI レビューを簡単に導入したいプロジェクト向けの、**コピペだけで移行可能なテンプレート**として構成されています。

## 特徴

- **超簡単移植**: `.gitea/` と `ame-ai-review-system/`
  の2つのディレクトリを他リポジトリにコピーするだけで導入完了。
- **対話型の修正サイクル**: 開発者が `@<レビュアー名>`
  で返信すると、AI が最新コードを再評価してスレッドに返答。
- **重大度ラベル**: 指摘を `CRITICAL` / `HIGH` / `MIDDLE` / `LOW` の 4 段階で分類。
- **複数レビュアー対応**: ジョブの追加だけで、役割の異なる複数のレビュアーを追加可能。

## ディレクトリ構成

```text
.gitea/
  workflows/
    review.yml            # PR作成/プッシュ時にレビューを実行するワークフロー
    review_reply.yml      # コメント返信時に自動返答を実行するワークフロー
    ci.yml                # 本リポジトリのCI設定

ame-ai-review-system/    # ★他のリポジトリに丸ごとコピーする資材
  pr_review.sh            # レビュー処理本体
  pr_review_reply.sh      # 返信・LGTM判定処理本体
  post_push_review.sh     # ローカルプッシュ後のトリガー用フック（任意）
  setup.sh                # 開発環境セットアップ補助
  payload.py              # Claude 出力 -> Gitea API ペイロード変換
  reply.py                # 返信プロンプト生成・スレッド解析
  review_prompt.txt       # レビュアーへのプロンプト（レビュー観点）
  VERSION                 # バージョン情報

  docs/                   # 同梱ドキュメント
    setup.md              # 移植・セットアップ手順
    architecture.md       # システムアーキテクチャ・処理の流れ
    customization.md      # プロンプトやレビュアーのカスタマイズ
    troubleshooting.md    # よくあるエラーと対処法
    instructions.md       # AIレビューフロー指示書（開発者・AIエージェント向け）
```

## クイックスタート

他プロジェクトへの導入は非常にシンプルです。

1. **資材のコピー**: `.gitea/` と `ame-ai-review-system/` を対象リポジトリのルートにコピーする。
2. **トークンの登録**: レビュアー用の Gitea トークンを生成し、対象リポジトリの Secrets に
   `REVIEWER_TOKEN` として登録する。
3. **プロンプトの調整**: `ame-ai-review-system/review_prompt.txt`
   をプロジェクトの規約や観点に合わせてカスタマイズする。

より詳細な手順は、[セットアップガイド](ame-ai-review-system/docs/setup.md) を参照してください。

## 関連ドキュメント

- [セットアップガイド](ame-ai-review-system/docs/setup.md) — 移植手順と初期設定の詳細
- [アーキテクチャ解説](ame-ai-review-system/docs/architecture.md) — システムの処理シーケンスと仕組み
- [カスタマイズガイド](ame-ai-review-system/docs/customization.md)
  — プロンプトの修正、複数レビュアーの追加
- [自動レビュー対応フロー指示書](ame-ai-review-system/docs/instructions.md)
  — 人間・AI がレビューに対応するための手順とルール
- [トラブルシューティング](ame-ai-review-system/docs/troubleshooting.md)
  — 動作しない、無限ループが発生したなどの対応
- [開発フロー (CLAUDE.md)](CLAUDE.md) — 本リポジトリ開発者向けの運用ルール
