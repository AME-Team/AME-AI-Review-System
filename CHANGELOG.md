# Changelog

本プロジェクトの主な変更点。形式は [Keep a Changelog](https://keepachangelog.com/)、バージョンは
[Semantic Versioning](https://semver.org/) に準拠。

## [Unreleased]

### Added

- `ame-review init` サブコマンドを追加。 `.ame-review/`
  設定・ワークフロー・pre-commit・TS 依存を足場展開する。
- pip インストール可能化 (`ame-ai-review-system`)。オプション extras で `[claude]` / `[antigravity]`
  / `[all]` の SDK 依存を導入できる。
- エンジン SDK アダプタ層を追加。Claude /
  Antigravity は SDK 直駆動、OpenCode は SDK で起動済みサーバへ接続 (`createOpencodeClient` +
  `OPENCODE_URL`。サーバは `opencode serve`
  または親opencode セッション)。実完了(テキスト抽出)まで検証済み。
- プロジェクトローカル設定 `.ame-review/` による repo 非依存パス解決。
- PyPI 公開ワークフロー (`.github/workflows/release.yml`, Trusted Publishing/OIDC)。

### Changed

- 認証モデルを API キーへ移行。(Claude: `ANTHROPIC_API_KEY`, Antigravity: `GEMINI_API_KEY`,
  OpenCode: `auth.json`)

### Removed

- LLM CLI バイナリ (`claude`/`opencode`/`agy`) のサブプロセス呼び出し。
- 未参照の `ame_ai_review_system/VERSION` ファイル。
