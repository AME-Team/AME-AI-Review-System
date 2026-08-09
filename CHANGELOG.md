# Changelog

本プロジェクトの主な変更点。形式は [Keep a Changelog](https://keepachangelog.com/)、バージョンは
[Semantic Versioning](https://semver.org/) に準拠。

## [Unreleased]

## [0.2.4] - 2026-08-10

### Fixed

- `ame-ai-reviewer init` が生成する `.pre-commit-config.yaml`
  に開発者固有の Python 絶対パスが埋め込まれていた。生成物の共有・コミット時に他環境/CI で失敗する問題を解消。既定を
  `language: python` + `additional_dependencies` に変更し、wheel URL と `#sha256=`
  固定で参照する方式とした。pre-commit が各環境で venv を自動作成する。 `--python` /
  `AME_INIT_PYTHON` 指定時のみオフライン向けの `language: system` で生成 (Issue #79)。
- init が wheel の `#sha256=` をピン留めしない供給チェーンリスク。生成時に GitHub Release
  API から sha256 ダイジェストを解決して URL へ固定。解決できない場合は警告して `#sha256=`
  なしで生成 (Issue #84)。
- codespell exclude から `.ame-review/engines-ts/` の除外が脱落した回帰 (Issue #80)。
- `review_command` wrapper の if と `is-review-command`
  パーサーが不整合だった。改行区切りコマンド（`/request-review\n<理由>`）が静かに skipped される問題を解消。wrapper を軽量な前置フィルタに変更した。厳密判定は reusable ワークフローのパーサーへ一本化 (Issue
  #81)。
- 生成する pre-commit config に `default_install_hook_types` が無い問題。 `pre-commit install`
  だけでは post-commit フック（streak リセット）が導入されなかった。 `[pre-commit, post-commit]`
  を明示し、既存クローン向けの再実行手順を README に追記 (Issue #82)。
- 返信判定モデルが diff に無いファイルの存在を捏造し、同じ指摘を繰り返す stale-loop。返信プロンプトに「diff から確認できないファイルの存在・非存在は断定しない」指示を追加。同一スレッドの連続 non-LGTM 返信（既定 3 回）でも強制 LGTM する判定を追加 (Issue
  #83)。

### Changed

- README / セットアップガイドのクイックスタートに、`uv tool install`
  での導入手順を追加（pipx と同等の CLI ツール管理）(Issue #85)。

## [0.2.3] - 2026-08-09

### Added

- `ame-ai-reviewer init` に TypeScript 向け preset (`ts`) と `--preset auto` を追加。
  `package.json` + `.ts`/`.tsx` ソースの有無で `ts` / `full` を自動選択し、Python 主体で
  `package.json` が付随するリポジトリでも Python ゲート (ruff/mypy) を消さない (Issue #69)。
- 生成する `.pre-commit-config.yaml` で lockfile を codespell / yamllint /
  prettier から自動除外 (Issue #69)。

### Fixed

- `workflow_dispatch` 時に `command` が空になり手動実行でレビュー判定が通らない問題。
  `command: comment.body || '/request-review'` でフォールバック (Issue #71)。
- `review_command` ラッパが `/request-review`
  以外のスラッシュコメントでも発火する問題。コマンド判定を完全一致 / 空白区切りの引数付きに限定 (Issue
  #70)。
- Issue へのコメントで `review_command`
  が発火し skipped ランがノイズになる問題。concurrency グループ化で抑制 (Issue #68)。
- PEP 668 (externally-managed) 環境で Gate 1 の pre-commit AI フックが動作しない問題。 `--python` /
  `AME_INIT_PYTHON` / `sys.executable` の順でインタープリタを自動検出して `entry:`
  に埋め込み、import 可能性を検証 (Issue #66)。
- AI レビュー出力の JSON パース失敗でラウンド全体が失敗する問題。修復試行回数をパラメータ化 (`review_repair_attempts`) し、パース失敗時は
  `reviewed-sha` マーカーを付与せず再レビュー可能にした。プロンプトでも JSON 出力を強制 (Issue
  #65)。
- 修正済み指摘の再投稿で stale-loop 検出が発火しない問題。`path`/`line`/`title` のアンカー一致 +
  severity ガードで再投稿を検出しつつ、HIGH/CRITICAL の過降格を防止 (Issue #67)。

### Changed

- `init` が生成する Gate 1 フックの `entry:`
  を実インタープリタパス埋め込み方式へ変更。パスに空白が含まれる場合は警告 (Issue #66)。

## [0.2.2] - 2026-08-06

### Fixed

- Gate 1 (pre-commit)・Gate 2 (PRレビュー) ともに差分が 4000 行を超えると前方のみを保持し、
  `index.css` / `types/` / `views/` / `tests/`
  等の後方ファイルがレビュー対象から消失して「定義が見当たらない」MIDDLE/HIGH 誤指摘が連発する問題を、優先度付き切り捨てで恒久対応 (Issue
  #62)。
  - 共通モジュール `diff_truncate.py`
    を新設。`priority`（優先セクション全行保持 + コンテキスト末尾保持）/
    `front`（従来）の 2 戦略と、フェンス補完・消失セクションの注記化を実装。
  - ステージ済み差分（当該コミットのレビュー対象）を全行保持し、ブランチ差分末尾（後方ファイル）を可視化。PRレビュー（優先サブセット無し）は head+tail 保持で後方ファイルを可視化。
  - 切り捨て上限・戦略・最低保証行数を `config.json` で設定化。(`max_diff_lines` /
    `diff_truncation_strategy` / `diff_truncation_context_lines`)。
  - `main.py` / `reply.py`
    の重複切り捨てロジック（3箇所）を共通モジュールへ統一し、フェンス補完漏れも修正。

### Changed

- ランディングページと同梱ドキュメントをソースコードと突き合わせて修正。
  - バージョンバッジを v0.2.1 に更新（`__version__` と整合）。
  - Semgrep カスタムルール数を 7 → 8 に修正（`.semgrep/rules.yml` と整合）。
  - デモの既定モデル表記を sonnet に修正。
  - `static_precheck.py` のサーキットブレーカー説明を実装に合わせて修正。
  - README から削除済みの `VERSION` ファイル参照を除去。
  - LOW エスケープ条件の表記を「LOW/INFO のみが 2 回連続」に統一。

## [0.2.1] - 2026-08-05

### Fixed

- pre-commit の AI レビューで false
  positive が連続しても無限ループしないよう、直近 2 回の返信の類似度による stale 検出（強制 LGTM）を導入。
- 最大ラウンド制限とコメント単位の stale 降格も追加 (Issue #55)。
- opencode エンジンで claude 系モデル既定名の解決漏れを防止し、stale 降格を全エンジンで共通化 (Issue
  #55)。
- PR 差分が空の場合に pre-commit 全体をスキップし、base 側で検証済みの内容を再スキャンしないようにした (Issue
  #49 / #55)。
- CI のパッケージビルド検証で、uv /
  npm キャッシュ（`.cache/`）が sdist に混入して毎回約 15 分かかっていた問題を修正。`.gitignore`
  と hatchling の sdist `exclude` の両方で除外 (Issue #57)。

## [0.2.0] - 2026-08-04

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
