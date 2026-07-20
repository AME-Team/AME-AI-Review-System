# AME AI Review System - Landing Page

本プロジェクトは、静的解析とAIレビューを組み合わせた「AME AI Review
System」のランディングページ（紹介サイト）です。プロダクトの設計概要、Gate
1（ローカルコミット）および Gate
2（プルリクエスト）における二重の品質チェックフローをインタラクティブに体験・シミュレーションできます。

## 技術スタック

- **フレームワーク**: React (v19)
- **言語**: TypeScript (型安全かつ厳格なコンパイラ設定)
- **ビルドツール**: Vite
- **スタイリング**: Tailwind CSS v4
- **国際化 (i18n)**: 日本語 (ja) / 英語 (en) 対応とユーザー設定の永続化
- **テスト**: Vitest / Testing Library によるユニットテスト
- **リンター・フォーマッタ**: ESLint / Prettier / Stylelint / Oxlint

---

## 起動・開発手順

### 1. 依存関係のインストール

プロジェクトのルートディレクトリで実行し、必要なパッケージをすべてインストールします（npm
workspaces機能により、サブディレクトリの依存関係も解決されます）。

```bash
npm install
```

### 2. 開発用サーバーの起動

開発サーバーを起動して、ブラウザでリアルタイムにプレビューします。

```bash
# プロジェクトのルートディレクトリから実行する場合
npm run dev --workspace=landing-page

# または、landing-page ディレクトリに移動して実行する場合
cd landing-page
npm run dev
```

起動後、ターミナルに表示されるURL（標準では `http://localhost:5173`）にブラウザでアクセスします。

---

## 本番ビルドとプレビュー

### 1. ビルドの実行

本番環境向けの配布用アセットをビルドします。厳格な TypeScript 型検査（tsc）と Vite ビルドが実行されます。

```bash
# プロジェクトのルートディレクトリから実行する場合
npm run build --workspace=landing-page

# または、landing-page ディレクトリに移動して実行する場合
cd landing-page
npm run build
```

ビルド成果物は `landing-page/dist/` ディレクトリに生成されます。

### 2. ビルド成果物のプレビュー

ローカル環境で本番用ビルドの表示・動作テストを行います。

```bash
# プロジェクトのルートディレクトリから実行する場合
npm run preview --workspace=landing-page

# または、landing-page ディレクトリに移動して実行する場合
cd landing-page
npm run preview
```

起動後、ブラウザで `http://localhost:4173` を開いて動作を確認します。

---

## テストの実行

Vitest によるユニットテストを実行します。

```bash
# プロジェクトのルートディレクトリから実行する場合
npm test

# または、landing-page ディレクトリに移動して実行する場合
cd landing-page
npm run test
```
