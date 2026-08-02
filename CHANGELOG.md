# Changelog

本プロジェクトの主な変更点。形式は [Keep a Changelog](https://keepachangelog.com/)、バージョンは
[Semantic Versioning](https://semver.org/) に準拠。

## [Unreleased]

### Added

- エンジン SDK アダプタ層を追加。Claude /
  Antigravity は SDK 直駆動、OpenCode は CLI サブプロセス経由（SDK はサーバ起動型で CI 都度起動が煩雑なため）。
- プロジェクトローカル設定 `.ame-review/` による repo 非依存パス解決。
- 移植先で vendored した `ame_ai_review_system/` 配下を既定でレビュー対象外にする設定を追加 (Issue
  #37)。`review_include_package_dir` で切替可能。
- このリポジトリ自身は `.ame-review/config.json` で `true` に設定し、配下をレビュー対象として運用。

### Changed

- 認証モデルを API キーへ移行。(Claude: `ANTHROPIC_API_KEY`, Antigravity: `GEMINI_API_KEY`,
  OpenCode: `auth.json`)
- 返信判定 (`review_reply.yml` /
  `reply run`) を**インライン返信のみ**トリガーに変更し、トリガーとなったスレッド 1 件だけに LGTM
  / 追加指摘を返信するようにした。投稿直前の保留再チェックも追加し、並走実行による重複 LGTM を防止 (Issue
  #39)。`TRIGGER_COMMENT_ID` 未設定時は従来の全スレッド走査へフォールバック。

### Removed

- PyPI 公開・pip インストール経路を廃止。配布はソースコードコピー方式（`.github/` と
  `ame_ai_review_system/` のコピー）に一本化 (Issue #45)。これに伴い `ame-review init`
  サブコマンド、`.github/workflows/release.yml`、`pyproject.toml` の `[project.scripts]` /
  `[project.optional-dependencies]` / hatchling ビルド設定、 `docs/distribution.md` を削除。
- LLM CLI バイナリ (`claude`/`opencode`/`agy`) のサブプロセス呼び出し。
- 未参照の `ame_ai_review_system/VERSION` ファイル。
