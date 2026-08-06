---
name: ame-ui-philosophy
description:
  AME-AI-Review-System (および共通コンポーネント) の UI・UX デザイン基準と実装ルールを規定する
  Skill。React + TypeScript + Tailwind CSS
  を使用したコンポーネント生成・リファクタリング時に適用する。
---

# AME-AI-Review-System UI Philosophy Skill

本 Skill は、AME-AI-Review-System のデザイン・UX 統一基準を AI
Agent が実行可能なガイドラインとして定義したものです。React + TypeScript + Tailwind
CSS でコンポーネント生成・修正・リファクタリングを行う際は、必ず本ドキュメントを適用してください。

## 1. 核心哲学 (Core Philosophy)

すべての UI 設計は、以下の 3 原則を起点に判断すること。

- **引き算のデザイン**: 装飾は情報伝達を助ける場合のみ許可。自己主張する装飾は排除する。
- **余白による構造**: 構造は「線（border/hr）」より「余白」で作る。線は最後の手段。
- **真面目感（フォーマルさ）**: 開発ツールとして厳格で落ち着いたトーンを維持する。

## 2. デザイン4大原則 (Design Principles)

Tailwind クラス適用時は次を厳守する。

| 原則                        | 適用ルール (Tailwind)                                                                                                          |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| **近接 (Proximity)**        | 関連情報は近づける (`gap-2`, `gap-4`)。無関係情報は離す (`mt-8`, `p-6`)。区切りは安易な `border-b` / `hr` ではなく余白を優先。 |
| **整列 (Alignment)**        | 原則 **左揃え** (`text-left`, `items-start`)。中央揃えはロゴや短いコピー等の限定用途のみ。                                     |
| **反復 (Repetition)**       | **8px グリッド**（4, 8, 16, 24, 32...）を厳守。任意値 (`p-[13px]`) 禁止。角丸は `rounded-md` / `rounded-lg` のみ。             |
| **コントラスト (Contrast)** | サイズ・太さ・色濃さに明確な差をつける。中途半端な差（`text-base` と `text-sm` のみ等）を禁止。                                |

## 3. タイポグラフィ (Typography)

### 3.1 言語別フォント定義（Default / Serif / Mono）

フォントは「日本語」と「英語」を明示的に分けて定義する。Mono は両言語共通。表示差異を避けるため、フォントは各端末のローカルフォントに依存せず、**Google
Fonts（Webフォント）を必須利用**とする。

- 必須方針: UI/コード表示で使用する Noto 系フォントは Google Fonts から配信する。
- 禁止方針: OS 依存のローカルフォントのみで完結する実装（環境差で見た目が変わるため）。
- 実装例: `@import` または `<link rel="preconnect">` +
  `<link href="https://fonts.googleapis.com/...">` で読み込む。

#### 日本語 (ja)

| セット             | デフォルトフォント | Monoフォント（コード用） |
| ------------------ | ------------------ | ------------------------ |
| **Default (Sans)** | `Noto Sans JP`     | `Noto Sans Mono`         |
| **Serif**          | `Noto Serif JP`    | `Noto Sans Mono`         |

#### 英語 (en)

| セット             | デフォルトフォント | Monoフォント（コード用） |
| ------------------ | ------------------ | ------------------------ |
| **Default (Sans)** | `Noto Sans`        | `Noto Sans Mono`         |
| **Serif**          | `Noto Serif`       | `Noto Sans Mono`         |

実装では以下の CSS 変数を使い、言語とフォントセットで切り替えること。

- `--font-ui-ja-sans: 'Noto Sans JP', sans-serif;`
- `--font-ui-ja-serif: 'Noto Serif JP', serif;`
- `--font-ui-en-sans: 'Noto Sans', sans-serif;`
- `--font-ui-en-serif: 'Noto Serif', serif;`
- `--font-mono: 'Noto Sans Mono', 'Noto Sans JP', monospace;`

### 3.2 コード表示時のフォント適用ルール

コードブロック・インラインコードでは、文字種に応じて表示フォントが切り替わる設計にする。

| 文字種別                            | 適用フォント             | 例                               |
| ----------------------------------- | ------------------------ | -------------------------------- |
| **1バイト文字**（半角英数字・記号） | `Noto Sans Mono`         | `const x = 1;`                   |
| **2バイト文字**（日本語コメント等） | 言語別デフォルトフォント | `// 日本語コメント` の日本語部分 |

`font-family: var(--font-mono);`
をコード要素に適用し、Mono にないグリフは各言語の UI フォントへフォールバックさせる。

### 3.3 フォント選択機能（ユーザー設定）

ユーザーは設定 UI で以下を選べること。

- `Default`（Sans）
- `Serif`
- `User Settings`（UI フォント/Mono フォントのユーザー指定）

選択状態は `app_settings` に永続化し、再起動後も維持すること。

### 3.4 読みやすさ基準

- 日本語は `tracking-[0.05em]` または `tracking-wide`。
- 行間は `leading-relaxed` (1.625) または `leading-loose` (1.75)。
- 長文は `max-w-prose` (65ch) または `max-w-2xl`。
- `text-justify` は禁止。

### 3.5 見出し階層（規定値）

| レベル   | Tailwind 規定 (Light / Dark)                                                                          |
| -------- | ----------------------------------------------------------------------------------------------------- |
| **h1**   | `text-2xl font-bold text-gray-900 dark:text-gray-100`（※ヒーロー等の特例は `text-3xl`/`text-4xl` 可） |
| **h2**   | `text-xl font-bold text-gray-900 dark:text-gray-100`                                                  |
| **h3**   | `text-lg font-semibold text-gray-700 dark:text-gray-300`                                              |
| **本文** | `text-sm font-normal text-gray-600 dark:text-gray-400`                                                |

## 4. 配色システムとダークモード (Color + Dark Mode)

### 4.1 ベース配色

- **ライトモード**: 背景 `bg-white` / `bg-gray-50`、テキスト `text-gray-900/700/500`
- **ダークモード**: 背景 `bg-gray-900`（純黒 `#000` を避ける）、テキスト `text-gray-100/300/400`

テーマ切替は `light` / `dark` / `system` をサポートし、`app_settings` へ永続化する。

### 4.2 1ポイントカラー（5プリセット）

`--color-primary` を切り替えて利用する。ライト・ダークで別値を持つこと。

| 名称                 | Light     | Dark Variant | 意味             |
| -------------------- | --------- | ------------ | ---------------- |
| Trust Blue           | `#005B99` | `#3B82C4`    | 信頼・技術       |
| Stable Green         | `#2D6A4F` | `#4F8A6E`    | 安定・成長       |
| Grounded Orange      | `#C2410C` | `#DD6B3D`    | 注意・アクション |
| Sophisticated Indigo | `#4338CA` | `#7C79E8`    | 高級感・モダン   |
| Clarity Teal         | `#0F766E` | `#2FA39A`    | 明瞭・冷静       |

通常テキストのコントラスト比は最低 4.5:1（WCAG AA）を満たすこと。

## 5. スペーシング・レイアウト (Spacing & Layout)

- **8px グリッド厳守**: 4 / 8 / 16 / 24 / 32 / 48 / 64px（`gap-1/2/4/6/8/12/16`）
- **任意値禁止**: `p-[13px]` 等を使用しない
- **角丸**: `rounded-md` / `rounded-lg`
  のみ。ただし、アイコン、バッジ、アバター、スウォッチ等の円形UIは `rounded-full` を許容する。
- **境界線**: `border` / `border-b` / `divide-y` / `hr`
  は最終手段。先に余白で解決する（※ヘッダーやタブ等の下線は許容）

## 6. アニメーション (Animation)

### 6.1 規定値（duration / easing）

| 用途                     | duration       | easing        | Tailwind 例                                   |
| ------------------------ | -------------- | ------------- | --------------------------------------------- |
| マイクロインタラクション | 150ms          | `ease-out`    | `transition-all duration-150 ease-out`        |
| 状態変化（色・背景）     | 200ms          | `ease-out`    | `transition-colors duration-200 ease-out`     |
| 要素の出現・消失         | 200-300ms      | `ease-in-out` | `transition-opacity duration-300 ease-in-out` |
| ページ切替               | 200-300ms      | `ease-in-out` | ルーティング遷移                              |
| チャットテキスト描画     | ストリーミング | -             | 文字/ブロック単位フェード（`duration-150`）   |

### 6.2 制約

- 300ms 超のアニメーション禁止
- 装飾目的のアニメーション（回転・バウンス・パララックス）禁止（※稼働状態やロードを示すパルス・スピン等は例外）
- `prefers-reduced-motion: reduce` 時は `motion-reduce:*` で無効化

## 7. アクセシビリティ (Accessibility: WCAG 2.1 AA)

- 通常テキスト 4.5:1 以上、大テキスト 3:1 以上
- 色だけに依存せず、ラベル・アイコン・形状差を併用
- 全機能キーボード操作可能、`focus-visible:` で明確なフォーカス表示
- セマンティック HTML と正しい見出し階層を維持
- フォームは `label` を関連付け、エラーはテキストで明示
- 動的更新（チャット追加など）は `aria-live` で通知

## 8. 多言語対応 (i18n)

### 8.1 対応言語

- 初期リリースは `ja` / `en`
- 将来言語を追加可能な i18n 構造を前提に設計

### 8.2 実装要件

- UI 文字列はすべて翻訳リソース経由（ハードコード禁止）
- 言語切替は設定 UI から実行可能にする
- 選択言語は `app_settings` に永続化する
- 日付・時刻・数値は `Intl` API 等でロケール準拠にする
- ラベル長が増えても崩れないレイアウト（折返し・最小幅・余白）を確保する

### 8.3 フォントと i18n の接続ルール

- `locale=ja` のとき UI フォントは `Noto Sans JP` / `Noto Serif JP`
- `locale=en` のとき UI フォントは `Noto Sans` / `Noto Serif`
- コード表示の Mono は常に `Noto Sans Mono` を優先し、未収録グリフのみ UI フォントへフォールバック

## 9. 禁止事項 (Negative Constraints)

1. 過度なドロップシャドウ（`shadow-lg`, `shadow-xl`）
2. グラデーション背景（`bg-gradient-to-*`）
3. 余白で解決可能な区切り線（`border-b`, `hr`）
4. 8px グリッド外の任意値（`p-[13px]` 等）
5. `text-justify`
6. `rounded-xl` 以上
7. テキストのハードコード（翻訳リソースを通さない UI 文言）

## 10. AI 実行ワークフロー (Execution Workflow)

コンポーネント生成・修正時は、以下 Step 1〜5 を必ず実行すること。

### Step 1: 要件分析と情報設計

- コンポーネントの目的、画面内コンテキスト、利用ロケール（`ja/en`）を確認する
- 情報優先順位とセマンティック構造（`main/section/article/nav`）を決定する

### Step 2: レイアウト設計（引き算 + 余白）

- 8px グリッドで要素を配置し、余白で情報構造を分離する
- 関連要素は `gap-*` で近接、非関連要素は `mt-*`/`p-*` で分離する
- 線ではなく余白を優先し、角丸は `rounded-md/lg` に限定する

### Step 3: スタイル適用（Typography / Color / i18n）

- 見出し階層、行間、字間、行長を規定値で適用する
- `locale` とフォントセット（Default/Serif/User Settings）に応じて UI フォントを適用する
- Google Fonts（Webフォント）の読み込みを前提にし、ローカルフォント依存の実装を避ける
- `--color-primary` と `dark:` を使い、ライト/ダーク双方でコントラストを満たす
- 文字列を翻訳キー経由へ統一し、日時/数値をロケール形式にする

### Step 4: アクセシビリティとモーション検証

- `focus-visible`、`label`、`aria-*`、`aria-live` を確認する
- アニメーションは規定 duration/easing 内に収める
- `motion-reduce:*` を適用し、色だけに依存した状態表現を排除する

### Step 5: 禁止事項と品質ゲート最終確認

- 禁止事項（シャドウ、グラデーション、任意値、過剰角丸、ハードコード文言）を全点検する
- `ja/en` の表示崩れと読みやすさを確認し、問題なければ最終コードを出力する
