# 配布ガイド（PyPI 公開）

本パッケージの PyPI 公開とリリース手順を説明する。

## 前提

- Python 3.10 以上
- ビルドツール: [uv](https://docs.astral.sh/uv/) / [hatchling](https://hatch.pypa.io/)
- バージョンの正: `ame_ai_review_system/__init__.py` の `__version__`（hatchling が動的読込）

## パッケージ構成

- 配布名: `ame-ai-review-system`（import 名: `ame_ai_review_system`）
- コアは標準ライブラリのみ。LLM エンジン SDK はオプション extras:
  - `[claude]` → `claude-agent-sdk`（Python SDK）。TypeScript
    SDK（`@anthropic-ai/claude-agent-sdk`）サイドカーでも利用可
  - `[antigravity]` → `google-antigravity`
  - `[all]` → 両方
  - OpenCode は TypeScript SDK（`@opencode-ai/sdk`）サイドカー経由のため Python
    extras は不要。Node で `engines/ts/` の依存をインストールする。サーバ起動に `opencode`
    CLI が必要。
- wheel 同梱データ: `review_prompt.txt`, `.semgrep/rules.yml`,
  `templates/`（pre-commit プロファイル／ワークフロー），`engines/ts/claude.mjs`,
  `engines/ts/opencode.mjs`（TypeScript SDK サイドカー）

## ローカルビルド検証

```bash
uv build                           # dist/ へ sdist + wheel を生成
pip install twine && twine check dist/*   # メタデータ検証
```

## PyPI Trusted Publishing（OIDC）設定

API トークン不要。PyPI 側で GitHub Actions からの OIDC 公開を許可する。

1. PyPI で `ame-ai-review-system`
   プロジェクトを作成（初回は手動アップロードまたは publishing 設定のみ）。
2. `Account settings` → `Add publishing publisher`:
   - PyPI Project Name: `ame-ai-review-system`
   - Owner: `tarminjapan`
   - Repository: `AME-AI-Review-System`
   - Workflow name: `release.yml`
   - Environment name: `pypi`

## リリース手順

1. `ame_ai_review_system/__init__.py` の `__version__` を上げる。
2. `CHANGELOG.md` を更新。
3. `main` へマージする PR を作成・マージする（本リポジトリのブランチポリシー: 作業ブランチ →
   `main`）。
4. `main` でタグを打つ:

   ```bash
   git tag v0.1.0
   git push origin v0.1.0
   ```

5. `release.yml` が起動し、ビルド → PyPI 公开を自動実行する。

## コンシューマ（利用側）のクイックスタート

```bash
pip install "ame-ai-review-system[claude]"
cd /path/to/your-repo
ame-review init --profile python --engine claude
```

詳細は README の「クイックスタート（pip インストール）」を参照。
