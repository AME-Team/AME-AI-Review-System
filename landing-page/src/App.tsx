import React, { useState, useEffect, useRef } from "react";

interface LogMessage {
  type: "cmd" | "info" | "success" | "warning" | "error";
  text: string;
}

type Locale = "ja" | "en";
type FontStyle = "sans" | "serif";
type PrimaryColor = "blue" | "green" | "orange" | "indigo" | "teal";

interface AppSettings {
  locale: Locale;
  fontStyle: FontStyle;
  primaryColor: PrimaryColor;
}

interface TranslationResource {
  title: string;
  navFeatures: string;
  navDemo: string;
  navWorkflow: string;
  navConfig: string;
  giteaRepo: string;
  badgeVersion: string;
  heroTitle1: string;
  heroTitleAccent: string;
  heroTitle2: string;
  heroDesc: string;
  tryDemoBtn: string;
  viewConfigBtn: string;
  secFeaturesTitle: string;
  secFeaturesDesc: string;
  featureCbTitle: string;
  featureCbDesc: string;
  featureCompressTitle: string;
  featureCompressDesc: string;
  featureLoopTitle: string;
  featureLoopDesc: string;
  featureScopeTitle: string;
  featureScopeDesc: string;
  demoTitle: string;
  demoDesc: string;
  demoCheckbox: string;
  demoButtonRunning: string;
  demoButtonRun: string;
  demoHeader: string;
  workflowTitle: string;
  workflowDesc: string;
  workflowStep1Title: string;
  workflowStep1Desc: string;
  workflowStep2Title: string;
  workflowStep2Desc: string;
  diagramTitle: string;
  diagramDesc: string;
  diagramStepFile: string;
  diagramStepFileDesc: string;
  diagramStepGate1: string;
  diagramStepGate1Desc: string;
  diagramStepHeadroom: string;
  diagramStepHeadroomDesc: string;
  diagramStepCommit: string;
  diagramStepCommitDesc: string;
  diagramStepGate2: string;
  diagramStepGate2Desc: string;
  configTitle: string;
  configDesc: string;
  configTabPrecommit: string;
  configTabEslint: string;
  configTabCircuit: string;
  settingsTitle: string;
  settingsLang: string;
  settingsColor: string;
  settingsFont: string;
  settingsFontSans: string;
  settingsFontSerif: string;
  colorBlue: string;
  colorGreen: string;
  colorOrange: string;
  colorIndigo: string;
  colorTeal: string;
}

const translations: Record<Locale, TranslationResource> = {
  ja: {
    title: "AME AI Review",
    navFeatures: "主要機能",
    navDemo: "動作デモ",
    navWorkflow: "ワークフロー",
    navConfig: "設定構成",
    giteaRepo: "Gitea リポジトリ",
    badgeVersion: "v2.0.0 厳格監視ゲート",
    heroTitle1: "デュアルゲートAIコードレビュー",
    heroTitleAccent: "厳格なマルチ言語品質",
    heroTitle2: "を保証する自動レビュー",
    heroDesc:
      "開発者のローカル環境におけるコミット前の検証（ゲート1）と、プルリクエスト時の自動レビュー（ゲート2）を組み合わせた品質管理システム。TypeScript、Python、および主要なテキストファイル（Markdown、JSON、YAMLなど）の品質を静的解析とAIで保証し、レビューコストを大幅に削減します。",
    tryDemoBtn: "シミュレーターを試す",
    viewConfigBtn: "設定ファイルを見る",
    secFeaturesTitle: "厳格さと速度を両立する設計",
    secFeaturesDesc: "プロジェクトの品質と開発効率を高めるためのコアメカニズム",
    featureCbTitle: "静的サーキットブレーカー",
    featureCbDesc:
      "TypeScript(tsc)、ESLint、Python(mypy/ruff) などの解析を事前に実行。エラー検出時はAIレビューを即時スキップし、不要なAPIトークン消費と開発者の待ち時間を徹底的に削減します。",
    featureCompressTitle: "headroom トークン圧縮技術",
    featureCompressDesc:
      "Gitメタデータ、バイナリ差分、冗長な空行、markdown/json/yaml等の構成ファイル内の不要セクションを自動でフィルタリングおよび圧縮。AIへの入力トークン量を最小限に抑え、プロンプトキャッシュを最適化します。",
    featureLoopTitle: "停滞ループ検出",
    featureLoopDesc:
      "直近の指摘内容のJaccard類似度を自動評価。進展のない堂々巡りの議論（無限ループ）を検知すると強制的にLGTMを発行し、チーム全体のデリバリー速度の低下を防ぎます。",
    featureScopeTitle: "広範なファイル品質保証",
    featureScopeDesc:
      "ソースコード(TS, Python)だけでなく、主要な設定ファイル(JSON, YAML)やプロジェクトドキュメント(Markdown)までカバー。あらゆる構成ファイルの書き込み品質を一定に保ちます。",
    demoTitle: "ローカル検証の体験",
    demoDesc:
      "コミット時におけるローカル検証（ゲート1）が、どのようにコードや設定の欠陥を検知してコミットをブロックするかをシミュレートできます。以下のチェックを切り替えて、シミュレーションを実行してください。",
    demoCheckbox: "高重要度のバグコードをシミュレートする (AIレビューでの指摘を擬似発生)",
    demoButtonRunning: "検証プロセスを実行中...",
    demoButtonRun: "コミット検証を実行",
    demoHeader: "git-gate@bash: ~",
    workflowTitle: "ダブルゲート・ワークフロー",
    workflowDesc: "コード品質を保つための2段階のチェックポイント",
    workflowStep1Title: "ローカル検証 (ゲート1)",
    workflowStep1Desc:
      "開発者が git commit を実行した際、ローカルの pre-commit フックが動作。コードフォーマット、構文、型定義、主要設定ファイルの整合性を検証し、軽量なAIレビューをローカルで実施。問題検出時はコミットを自動でブロックします。",
    workflowStep2Title: "プルリクエスト自動レビュー (ゲート2)",
    workflowStep2Desc:
      "コードがリモートにプッシュされると、CIランナーが総合検証を起動。PRのコメントで /request-review と投稿するだけで、対話型のAIレビューコメントとディスカッションスレッドを自動生成します。",
    diagramTitle: "デュアルゲート & headroom 処理フロー",
    diagramDesc:
      "コード変更からコミット、PRレビューまでの最適化パイプライン（いずれかのノードを選択して詳細情報を表示）",
    diagramStepFile: "1. ファイル変更検知",
    diagramStepFileDesc: "TS / Python / MD / JSON / YAML 等",
    diagramStepGate1: "2. ゲート1 (静的解析)",
    diagramStepGate1Desc: "並行静的チェッカー実行",
    diagramStepHeadroom: "3. headroom 圧縮",
    diagramStepHeadroomDesc: "メタデータ除去・差分最適化",
    diagramStepCommit: "4. コミット実行",
    diagramStepCommitDesc: "検証通過でのみコミットを許可",
    diagramStepGate2: "5. ゲート2 (PRレビュー)",
    diagramStepGate2Desc: "/request-review による指摘",
    configTitle: "品質保証の設定構成",
    configDesc: "チーム全体で共有され、高い品質を維持するための標準設定ファイル",
    configTabPrecommit: "pre-commit 設定",
    configTabEslint: "ESLint 設定",
    configTabCircuit: "サーキットブレーカー (Python)",
    settingsTitle: "表示設定",
    settingsLang: "言語 (Language)",
    settingsColor: "ポイントカラー (Color)",
    settingsFont: "フォント (Font)",
    settingsFontSans: "Sans-Serif (ゴシック体)",
    settingsFontSerif: "Serif (明朝体)",
    colorBlue: "Trust Blue (青)",
    colorGreen: "Stable Green (緑)",
    colorOrange: "Grounded Orange (橙)",
    colorIndigo: "Sophisticated Indigo (藍)",
    colorTeal: "Clarity Teal (青緑)",
  },
  en: {
    title: "AME AI Review",
    navFeatures: "Features",
    navDemo: "Interactive Demo",
    navWorkflow: "Workflow",
    navConfig: "Configuration",
    giteaRepo: "Gitea Repo",
    badgeVersion: "v2.0.0 Strict Monitoring Gate",
    heroTitle1: "Dual-Gate AI Code Review",
    heroTitleAccent: "Strict Multi-Language Quality",
    heroTitle2: "Guaranteed by Automated Reviews",
    heroDesc:
      "A quality management system combining pre-commit verification in the developer's local environment (Gate 1) and automated review during pull requests (Gate 2). It guarantees the quality of TypeScript, Python, and major text files (Markdown, JSON, YAML, etc.) using static analysis and AI, significantly reducing review costs.",
    tryDemoBtn: "Try Simulator",
    viewConfigBtn: "View Config Files",
    secFeaturesTitle: "Designed for Both Rigidity and Speed",
    secFeaturesDesc: "Core mechanisms for elevating project quality and development efficiency",
    featureCbTitle: "Static Circuit Breaker",
    featureCbDesc:
      "Executes static analysis (tsc, ESLint, mypy, ruff) beforehand. Skips AI review immediately if errors are detected, minimizing API token consumption and developer wait time.",
    featureCompressTitle: "headroom Token Compression",
    featureCompressDesc:
      "Automatically filters and compresses Git metadata, binary diffs, redundant empty lines, and unnecessary sections in configuration files (JSON, YAML, Markdown), maximizing Claude's prompt caching efficiency.",
    featureLoopTitle: "Stagnation Loop Detection",
    featureLoopDesc:
      "Automatically evaluates the Jaccard similarity of the last review comments. Emits a forced LGTM when progress-less circular discussions (infinite loops) are detected, ensuring team velocity.",
    featureScopeTitle: "Broad File Quality Assurance",
    featureScopeDesc:
      "Guarantees quality not only for source code (TS, Python) but also for major configuration files (JSON, YAML) and documentation (Markdown). Keeps standard formatting consistent.",
    demoTitle: "Experience Local Verification",
    demoDesc:
      "Simulate how Gate 1 (pre-commit hook) catches flaws in code or configurations and blocks commits. Toggle the option below and start the verification.",
    demoCheckbox: "Simulate high-priority bug code (triggers AI review warnings)",
    demoButtonRunning: "Running verification...",
    demoButtonRun: "Run Commit Verification",
    demoHeader: "git-gate@bash: ~",
    workflowTitle: "Dual-Gate Workflow",
    workflowDesc: "Two-stage checkpoint for preserving code quality",
    workflowStep1Title: "Local Verification (Gate 1)",
    workflowStep1Desc:
      "When a developer runs git commit, the local pre-commit hook runs to check code formatting, syntax, typescript definitions, and major configurations. If issues are found, the commit is blocked.",
    workflowStep2Title: "Pull Request Auto-Review (Gate 2)",
    workflowStep2Desc:
      "Once pushed, CI runners trigger comprehensive tests. Developers can simply type /request-review in the PR comments to instantly generate interactive AI reviews and discussion threads.",
    diagramTitle: "Dual-Gate & headroom Pipeline Flow",
    diagramDesc:
      "Optimized pipeline from code modifications to commit and PR reviews (Select a node to view technical details)",
    diagramStepFile: "1. File Change Detect",
    diagramStepFileDesc: "TS / Python / MD / JSON / YAML etc.",
    diagramStepGate1: "2. Gate 1 (Static Check)",
    diagramStepGate1Desc: "Parallel static checkers execution",
    diagramStepHeadroom: "3. headroom Compression",
    diagramStepHeadroomDesc: "Strips metadata, optimizes diffs to save tokens",
    diagramStepCommit: "4. Execute Commit",
    diagramStepCommitDesc: "Allows commit execution only when local checks pass",
    diagramStepGate2: "5. Gate 2 (PR Review)",
    diagramStepGate2Desc: "Triggers AI feedback on CI via /request-review",
    configTitle: "Quality Assurance Settings",
    configDesc: "Shared, standard configuration files maintaining code and review policies",
    configTabPrecommit: "pre-commit Config",
    configTabEslint: "ESLint Config",
    configTabCircuit: "Circuit Breaker (Python)",
    settingsTitle: "Display Settings",
    settingsLang: "Language",
    settingsColor: "Point Color",
    settingsFont: "Font",
    settingsFontSans: "Sans-Serif",
    settingsFontSerif: "Serif",
    colorBlue: "Trust Blue",
    colorGreen: "Stable Green",
    colorOrange: "Grounded Orange",
    colorIndigo: "Sophisticated Indigo",
    colorTeal: "Clarity Teal",
  },
};

function loadSavedSettings(): AppSettings {
  const defaults: AppSettings = { locale: "ja", fontStyle: "sans", primaryColor: "blue" };
  try {
    const saved = localStorage.getItem("app_settings");
    if (saved === null) return defaults;
    const parsed = JSON.parse(saved) as {
      locale?: unknown;
      fontStyle?: unknown;
      primaryColor?: unknown;
    };
    const validLocales: Locale[] = ["ja", "en"];
    const validFonts: FontStyle[] = ["sans", "serif"];
    const validColors: PrimaryColor[] = ["blue", "green", "orange", "indigo", "teal"];
    return {
      locale: validLocales.includes(parsed.locale as Locale)
        ? (parsed.locale as Locale)
        : defaults.locale,
      fontStyle: validFonts.includes(parsed.fontStyle as FontStyle)
        ? (parsed.fontStyle as FontStyle)
        : defaults.fontStyle,
      primaryColor: validColors.includes(parsed.primaryColor as PrimaryColor)
        ? (parsed.primaryColor as PrimaryColor)
        : defaults.primaryColor,
    };
  } catch (e) {
    console.warn("Failed to parse app_settings, using defaults:", e);
    return defaults;
  }
}

export default function App(): React.JSX.Element {
  const [simulateBug, setSimulateBug] = useState<boolean>(false);
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [settings, setSettings] = useState<AppSettings>(loadSavedSettings);
  const [showSettings, setShowSettings] = useState<boolean>(false);
  const [activeStep, setActiveStep] = useState<number>(2); // Default to headroom token compression detail

  const [terminalLogs, setTerminalLogs] = useState<LogMessage[]>([]);
  const [activeTab, setActiveTab] = useState<"yaml" | "eslint" | "circuit">("yaml");

  const { locale, fontStyle, primaryColor } = settings;

  const settingsRef = useRef<HTMLDivElement>(null);
  const isRunningRef = useRef<boolean>(isRunning);

  useEffect(() => {
    isRunningRef.current = isRunning;
  }, [isRunning]);

  // Initialize terminal logs on locale change
  useEffect(() => {
    if (isRunningRef.current) return;
    setTerminalLogs([
      {
        type: "info",
        text:
          locale === "ja"
            ? "--- AME AI Review System インタラクティブ・シミュレーター ---"
            : "--- AME AI Review System Interactive Simulator ---",
      },
      {
        type: "info",
        text:
          locale === "ja"
            ? "「高重要度のバグコードをシミュレートする」を有効にしてシミュレーションを実行すると、ゲート1の検証をテストできます。"
            : "Enable 'Simulate high-priority bug code' and click run to test Gate 1 verification.",
      },
    ]);
  }, [locale]);

  // Sync settings with DOM attributes and localStorage
  useEffect(() => {
    document.documentElement.setAttribute("data-locale", locale);
    document.documentElement.setAttribute("data-font-style", fontStyle);
    document.documentElement.setAttribute("data-theme-color", primaryColor);

    localStorage.setItem("app_settings", JSON.stringify({ locale, fontStyle, primaryColor }));
  }, [locale, fontStyle, primaryColor]);

  // Close settings panel when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent): void {
      if (settingsRef.current && !settingsRef.current.contains(event.target as Node)) {
        setShowSettings(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return (): void => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  // Simulated terminal sequence
  const runSimulation = (): void => {
    setIsRunning(true);
    setTerminalLogs([
      { type: "cmd", text: "git add ." },
      {
        type: "info",
        text:
          locale === "ja"
            ? "検証対象ファイルをステージング中: landing-page/src/App.tsx, pyproject.toml, README.md"
            : "Staging target files for verification: landing-page/src/App.tsx, pyproject.toml, README.md",
      },
    ]);
  };

  useEffect(() => {
    if (!isRunning) {
      return;
    }

    const steps: { delay: number; log: LogMessage }[] = [
      { delay: 1000, log: { type: "cmd", text: "pre-commit run" } },
      {
        delay: 1800,
        log: {
          type: "info",
          text:
            locale === "ja"
              ? "[static-precheck] 静的解析を実行中..."
              : "[static-precheck] Running static checks...",
        },
      },
      { delay: 2500, log: { type: "info", text: "tsc --noEmit .................. [PASS]" } },
      { delay: 3200, log: { type: "info", text: "eslint --max-warnings=0 ........ [PASS]" } },
      { delay: 3800, log: { type: "info", text: "mypy & ruff (Python) .......... [PASS]" } },
      {
        delay: 4500,
        log: {
          type: "info",
          text:
            locale === "ja"
              ? "[precommit-review] AIコードレビューを実行中 (モデル: Claude 3.5)..."
              : "[precommit-review] Running AI code review (Model: Claude 3.5)...",
        },
      },
    ];

    if (simulateBug) {
      steps.push(
        {
          delay: 5800,
          log: {
            type: "error",
            text:
              locale === "ja"
                ? "[precommit-review] 失敗: [HIGH] landing-page/src/App.tsx:L12\n  - バグ: クリックハンドラー内での状態遷移処理に不備があります。古いステートを参照している可能性があります。\n  - 推奨対策: ステートの更新にはコールバック関数形式を使用してください。"
                : "[precommit-review] FAILED: [HIGH] landing-page/src/App.tsx:L12\n  - Bug: Incomplete state transition in click handler. Might be referencing an outdated state.\n  - Recommendation: Use callback form for updating state variables.",
          },
        },
        {
          delay: 6500,
          log: {
            type: "error",
            text:
              locale === "ja"
                ? "コミットがブロックされました。上記の指摘事項を修正してください。"
                : "Commit blocked. Please resolve the issues described above.",
          },
        }
      );
    } else {
      steps.push(
        {
          delay: 5800,
          log: {
            type: "success",
            text:
              locale === "ja"
                ? "[precommit-review] AIレビュー結果: 指摘事項は検出されませんでした。[PASS]"
                : "[precommit-review] AI review result: No issues detected. [PASS]",
          },
        },
        {
          delay: 6500,
          log: {
            type: "cmd",
            text: 'git commit -m "feat: implement strict typescript gates"',
          },
        },
        {
          delay: 7200,
          log: {
            type: "success",
            text:
              locale === "ja"
                ? "[git] 1ファイル変更、24行挿入(+)。コミットが成功しました！"
                : "[git] 1 file changed, 24 insertions(+). Commit successful!",
          },
        }
      );
    }

    const timers = steps.map((step) =>
      setTimeout(() => {
        setTerminalLogs((prev) => [...prev, step.log]);
        if (
          step.log.text.includes("ブロック") ||
          step.log.text.includes("blocked") ||
          step.log.text.includes("成功") ||
          step.log.text.includes("successful")
        ) {
          setIsRunning(false);
        }
      }, step.delay)
    );

    return (): void => {
      timers.forEach((t) => {
        clearTimeout(t);
      });
    };
  }, [isRunning, simulateBug, locale]);

  const getCodeSnippet = (): string => {
    if (locale === "ja") {
      switch (activeTab) {
        case "yaml":
          return `# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: eslint
        name: eslint (--max-warnings=0)
        entry: ./node_modules/.bin/eslint --max-warnings=0 --no-warn-ignored
        language: system
        files: '\\.(js|mjs|cjs|ts|tsx)$'

      - id: tsc
        name: tsc (厳密な型チェック)
        entry: ./node_modules/.bin/tsc --noEmit -p landing-page/tsconfig.app.json
        language: system
        files: '\\.(ts|tsx)$'
        pass_filenames: false`;
        case "eslint":
          return `// eslint.config.mjs
import eslint from "@eslint/js";
import tseslint from "typescript-eslint";

export default tseslint.config(
  eslint.configs.recommended,
  ...tseslint.configs.strictTypeChecked,
  ...tseslint.configs.stylisticTypeChecked,
  {
    files: ["**/*.ts", "**/*.tsx"],
    rules: {
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/explicit-function-return-type": "error",
      "@typescript-eslint/strict-boolean-expressions": "error",
      "@typescript-eslint/no-floating-promises": "error"
    }
  }
);`;
        case "circuit":
          return `# static_precheck.py (サーキットブレーカー)
ts_files = [f for f in files if f.endswith((".ts", ".tsx", ".js"))]
if ts_files:
    ts_checks = [
        ("tsc", ["./node_modules/.bin/tsc", "--noEmit"]),
        ("eslint", ["./node_modules/.bin/eslint", "--max-warnings=0", *ts_files])
    ]
    for name, cmd in ts_checks:
        passed, detail = _run_check(name, cmd, cwd)
        if not passed:
            sys.exit(1) # 解析エラー検出時はここで異常終了し、AIレビューをスキップ`;
      }
    } else {
      switch (activeTab) {
        case "yaml":
          return `# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: eslint
        name: eslint (--max-warnings=0)
        entry: ./node_modules/.bin/eslint --max-warnings=0 --no-warn-ignored
        language: system
        files: '\\.(js|mjs|cjs|ts|tsx)$'

      - id: tsc
        name: tsc (strict type check)
        entry: ./node_modules/.bin/tsc --noEmit -p landing-page/tsconfig.app.json
        language: system
        files: '\\.(ts|tsx)$'
        pass_filenames: false`;
        case "eslint":
          return `// eslint.config.mjs
import eslint from "@eslint/js";
import tseslint from "typescript-eslint";

export default tseslint.config(
  eslint.configs.recommended,
  ...tseslint.configs.strictTypeChecked,
  ...tseslint.configs.stylisticTypeChecked,
  {
    files: ["**/*.ts", "**/*.tsx"],
    rules: {
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/explicit-function-return-type": "error",
      "@typescript-eslint/strict-boolean-expressions": "error",
      "@typescript-eslint/no-floating-promises": "error"
    }
  }
);`;
        case "circuit":
          return `# static_precheck.py (Circuit Breaker)
ts_files = [f for f in files if f.endswith((".ts", ".tsx", ".js"))]
if ts_files:
    ts_checks = [
        ("tsc", ["./node_modules/.bin/tsc", "--noEmit"]),
        ("eslint", ["./node_modules/.bin/eslint", "--max-warnings=0", *ts_files])
    ]
    for name, cmd in ts_checks:
        passed, detail = _run_check(name, cmd, cwd)
        if not passed:
            sys.exit(1) # Fails early if static checks fail, skipping AI review`;
      }
    }
  };

  const getDiagramSteps = (lang: Locale): { id: number; title: string; desc: string }[] => {
    const tDict = translations[lang];
    return [
      { id: 0, title: tDict.diagramStepFile, desc: tDict.diagramStepFileDesc },
      { id: 1, title: tDict.diagramStepGate1, desc: tDict.diagramStepGate1Desc },
      { id: 2, title: tDict.diagramStepHeadroom, desc: tDict.diagramStepHeadroomDesc },
      { id: 3, title: tDict.diagramStepCommit, desc: tDict.diagramStepCommitDesc },
      { id: 4, title: tDict.diagramStepGate2, desc: tDict.diagramStepGate2Desc },
    ];
  };

  const getStepDetail = (lang: Locale, step: number): string => {
    if (lang === "ja") {
      switch (step) {
        case 0:
          return "【変更監視の対象】TypeScriptやPythonのソースコードに加え、Markdownドキュメント、JSON、YAML等の主要構成ファイルの変更も検知しトラッキングします。変更がないファイルは検証をスキップし、検証を高速化します。";
        case 1:
          return "【静的サーキットブレーカー】コミットフック（pre-commit）が働き、tsc(型チェック)、eslint(スタイル)、mypy/ruff(Python静的解析)を並行して実行します。ここでエラーが出た場合はAI APIの実行を即時中断し、不要なAPI利用と開発者の待機を防ぎます。";
        case 2:
          return "【headroom による差分圧縮】git diff から余分なメタデータや長い連続改行、構成ファイル(json, yaml, md)内の冗長なブロックを自動除外。プロンプトサイズを圧縮し、Claude 3.5 へのトークン量を抑えることで、APIの応答速度とプロンプトキャッシュ効率を最大化します。";
        case 3:
          return "【ローカルコミット許可】すべてのローカル静的検証と、トークン圧縮されたコンテキストに基づくAIローカル事前チェックを通過した場合にのみ、コミットが成功します。開発者はバグが混入していないクリーンな状態で作業を進められます。";
        case 4:
          return "【CI自動レビュー】コードがリモートにプッシュされPR（プルリクエスト）が作成されると、CI上のレビューシステム（ゲート2）が起動。/request-review コメントでAIのディスカッションスレッドが作られ、類似度比較による停滞ループ検知が作動します。";
        default:
          return "";
      }
    } else {
      switch (step) {
        case 0:
          return "[Change Tracking] Identifies modified files among TS/JS/Python source codes, Markdown docs, JSON, and YAML configuration files. Clean files are skipped dynamically to speed up checkout stages.";
        case 1:
          return "[Static Circuit Breaker] Pre-commit hooks run tsc (strict check), ESLint (linting), and mypy/ruff (Python static analysis) in parallel. Fails immediately to skip downstream AI API calls and save tokens.";
        case 2:
          return "[headroom Token Compression] Automatically filters redundant metadata, excess blank lines, and boilerplate comments from configuration files (JSON/YAML/MD). Compresses input size to optimize Claude 3.5 caching.";
        case 3:
          return "[Commit Approval] Only commits that pass all local static checks and local AI pre-check are permitted. Developers proceed confident that no bugs or type errors have slipped in.";
        case 4:
          return "[CI Automated Review] Upon pushing to remote and initiating a PR, Gate 2 starts. Commenting /request-review triggers deep AI analysis, creating review threads and deploying stagnation loop checks.";
        default:
          return "";
      }
    }
  };

  const t = translations[locale];

  return (
    <div className="min-h-screen bg-gray-50 text-gray-600 dark:bg-gray-900 dark:text-gray-400 font-sans antialiased">
      {/* Navigation Header */}
      <header className="sticky top-0 z-50 bg-white/80 dark:bg-gray-900/80 backdrop-blur-md border-b border-gray-200/50 dark:border-gray-800/50 transition-colors duration-150">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between relative">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-primary rounded-md shadow-sm flex items-center justify-center text-white font-bold text-sm">
              AR
            </div>
            <span className="text-lg font-bold text-gray-900 dark:text-white tracking-wide">
              {t.title}
            </span>
          </div>
          <nav className="hidden md:flex items-center gap-6">
            <a
              href="#features"
              className="text-sm font-medium text-gray-500 hover:text-primary dark:text-gray-400 dark:hover:text-primary transition-colors duration-150"
            >
              {t.navFeatures}
            </a>
            <a
              href="#demo"
              className="text-sm font-medium text-gray-500 hover:text-primary dark:text-gray-400 dark:hover:text-primary transition-colors duration-150"
            >
              {t.navDemo}
            </a>
            <a
              href="#workflow"
              className="text-sm font-medium text-gray-500 hover:text-primary dark:text-gray-400 dark:hover:text-primary transition-colors duration-150"
            >
              {t.navWorkflow}
            </a>
            <a
              href="#config"
              className="text-sm font-medium text-gray-500 hover:text-primary dark:text-gray-400 dark:hover:text-primary transition-colors duration-150"
            >
              {t.navConfig}
            </a>
          </nav>

          <div className="flex items-center gap-4">
            {/* Settings Dropdown Container */}
            <div className="relative" ref={settingsRef}>
              <button
                type="button"
                onClick={() => {
                  setShowSettings(!showSettings);
                }}
                className="p-2 rounded-md hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-500 hover:text-primary dark:text-gray-400 dark:hover:text-primary transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-primary focus-visible:outline-none"
                aria-label={t.settingsTitle}
              >
                <svg
                  className="w-5 h-5"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"
                  />
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
                  />
                </svg>
              </button>

              {/* Floating Settings Card */}
              {showSettings && (
                <div className="absolute right-0 mt-2 w-80 bg-white dark:bg-gray-850 border border-gray-200 dark:border-gray-800 rounded-md shadow-md p-4 flex flex-col gap-4 z-50 transition-all duration-150 animate-in fade-in slide-in-from-top-2">
                  <h3 className="font-bold text-sm text-gray-900 dark:text-white border-b border-gray-100 dark:border-gray-800 pb-2">
                    {t.settingsTitle}
                  </h3>

                  {/* Language Selector */}
                  <div className="flex flex-col gap-1.5">
                    <label className="text-xs font-semibold text-gray-500 dark:text-gray-400">
                      {t.settingsLang}
                    </label>
                    <div className="grid grid-cols-2 gap-2 bg-gray-50 dark:bg-gray-900 p-1 rounded-md">
                      <button
                        type="button"
                        disabled={isRunning}
                        onClick={() => {
                          setSettings((prev) => ({ ...prev, locale: "ja" }));
                        }}
                        className={`text-xs py-1.5 rounded-md font-medium transition-all ${locale === "ja" ? "bg-white dark:bg-gray-800 text-primary shadow-sm" : "text-gray-500 hover:text-gray-900 dark:hover:text-white"} ${isRunning ? "opacity-50 cursor-not-allowed" : ""}`}
                      >
                        日本語
                      </button>
                      <button
                        type="button"
                        disabled={isRunning}
                        onClick={() => {
                          setSettings((prev) => ({ ...prev, locale: "en" }));
                        }}
                        className={`text-xs py-1.5 rounded-md font-medium transition-all ${locale === "en" ? "bg-white dark:bg-gray-800 text-primary shadow-sm" : "text-gray-500 hover:text-gray-900 dark:hover:text-white"} ${isRunning ? "opacity-50 cursor-not-allowed" : ""}`}
                      >
                        English
                      </button>
                    </div>
                  </div>

                  {/* Font Style Selector */}
                  <div className="flex flex-col gap-1.5">
                    <label className="text-xs font-semibold text-gray-500 dark:text-gray-400">
                      {t.settingsFont}
                    </label>
                    <div className="grid grid-cols-2 gap-2 bg-gray-50 dark:bg-gray-900 p-1 rounded-md">
                      <button
                        type="button"
                        onClick={() => {
                          setSettings((prev) => ({ ...prev, fontStyle: "sans" }));
                        }}
                        className={`text-xs py-1.5 rounded-md font-medium transition-all ${fontStyle === "sans" ? "bg-white dark:bg-gray-800 text-primary shadow-sm" : "text-gray-500 hover:text-gray-900 dark:hover:text-white"}`}
                      >
                        {t.settingsFontSans}
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setSettings((prev) => ({ ...prev, fontStyle: "serif" }));
                        }}
                        className={`text-xs py-1.5 rounded-md font-medium transition-all ${fontStyle === "serif" ? "bg-white dark:bg-gray-800 text-primary shadow-sm" : "text-gray-500 hover:text-gray-900 dark:hover:text-white"}`}
                      >
                        {t.settingsFontSerif}
                      </button>
                    </div>
                  </div>

                  {/* Point Color Presets Selector */}
                  <div className="flex flex-col gap-1.5">
                    <label className="text-xs font-semibold text-gray-500 dark:text-gray-400">
                      {t.settingsColor}
                    </label>
                    <div className="flex gap-2.5 items-center justify-between px-1">
                      {(["blue", "green", "orange", "indigo", "teal"] as PrimaryColor[]).map(
                        (color) => {
                          const bgClasses: Record<PrimaryColor, string> = {
                            blue: "bg-[#005B99] dark:bg-[#3B82C4]",
                            green: "bg-[#2D6A4F] dark:bg-[#4F8A6E]",
                            orange: "bg-[#C2410C] dark:bg-[#DD6B3D]",
                            indigo: "bg-[#4338CA] dark:bg-[#7C79E8]",
                            teal: "bg-[#0F766E] dark:bg-[#2FA39A]",
                          };
                          return (
                            <button
                              key={color}
                              type="button"
                              onClick={() => {
                                setSettings((prev) => ({ ...prev, primaryColor: color }));
                              }}
                              className={`w-6 h-6 rounded-full ${bgClasses[color]} transition-transform duration-150 relative focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary ${primaryColor === color ? "scale-125 ring-2 ring-offset-2 ring-primary" : "hover:scale-110"}`}
                              title={
                                t[
                                  `color${color.charAt(0).toUpperCase() + color.slice(1)}` as keyof TranslationResource
                                ]
                              }
                            >
                              {primaryColor === color && (
                                <span className="absolute inset-0 flex items-center justify-center text-white text-[10px] font-bold">
                                  ✓
                                </span>
                              )}
                            </button>
                          );
                        }
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>

            <a
              href={
                import.meta.env.VITE_GITEA_URL ??
                "http://localhost:3000/AME-Team/AME-AI-Review-System"
              }
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center justify-center bg-gray-900 dark:bg-gray-800 text-white hover:bg-gray-800 dark:hover:bg-gray-700 text-xs font-semibold px-4 py-2 rounded-md transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-primary focus-visible:outline-none"
            >
              {t.giteaRepo}
            </a>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-12 flex flex-col gap-16">
        {/* Hero Section */}
        <section className="flex flex-col items-start text-left gap-6 max-w-3xl">
          <div className="inline-flex items-center gap-2 bg-primary/10 border border-primary/20 text-primary px-3 py-1 rounded-md text-xs font-semibold">
            <span className="w-1.5 h-1.5 bg-primary rounded-full animate-pulse"></span>
            <span>{t.badgeVersion}</span>
          </div>
          <h1 className="text-3xl md:text-4xl font-bold text-gray-900 dark:text-white tracking-tight leading-tight">
            {t.heroTitle1}
            <br />
            <span className="text-primary">{t.heroTitleAccent}</span>
            {t.heroTitle2}
          </h1>
          <p className="text-sm md:text-base text-gray-600 dark:text-gray-400 leading-relaxed max-w-2xl">
            {t.heroDesc}
          </p>
          <div className="flex items-center gap-4 mt-2">
            <a
              href="#demo"
              className="inline-flex items-center justify-center bg-primary hover:bg-primary-hover text-white text-sm font-semibold px-5 py-3 rounded-md transition-colors duration-150 shadow-sm focus-visible:ring-2 focus-visible:ring-primary focus-visible:outline-none"
            >
              {t.tryDemoBtn}
            </a>
            <a
              href="#config"
              className="inline-flex items-center justify-center border border-gray-300 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 text-sm font-semibold px-5 py-3 rounded-md transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-primary focus-visible:outline-none"
            >
              {t.viewConfigBtn}
            </a>
          </div>
        </section>

        {/* Grid Features */}
        <section id="features" className="flex flex-col gap-8">
          <div className="flex flex-col gap-2">
            <h2 className="text-2xl font-bold text-gray-900 dark:text-white">
              {t.secFeaturesTitle}
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400">{t.secFeaturesDesc}</p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
            <div className="bg-white dark:bg-gray-850 p-6 rounded-md shadow-sm border border-gray-200/50 dark:border-gray-800 flex flex-col gap-4 items-start text-left">
              <div className="w-10 h-10 rounded-md bg-primary/10 text-primary flex items-center justify-center font-bold text-lg shadow-sm">
                ✓
              </div>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                {t.featureCbTitle}
              </h3>
              <p className="text-sm text-gray-600 dark:text-gray-400 leading-relaxed">
                {t.featureCbDesc}
              </p>
            </div>
            <div className="bg-white dark:bg-gray-850 p-6 rounded-md shadow-sm border border-gray-200/50 dark:border-gray-800 flex flex-col gap-4 items-start text-left">
              <div className="w-10 h-10 rounded-md bg-stable-green/10 text-stable-green flex items-center justify-center font-bold text-lg shadow-sm">
                ⚡
              </div>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                {t.featureCompressTitle}
              </h3>
              <p className="text-sm text-gray-600 dark:text-gray-400 leading-relaxed">
                {t.featureCompressDesc}
              </p>
            </div>
            <div className="bg-white dark:bg-gray-850 p-6 rounded-md shadow-sm border border-gray-200/50 dark:border-gray-800 flex flex-col gap-4 items-start text-left">
              <div className="w-10 h-10 rounded-md bg-indigo-sophisticated/10 text-indigo-sophisticated flex items-center justify-center font-bold text-lg shadow-sm">
                ∞
              </div>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                {t.featureLoopTitle}
              </h3>
              <p className="text-sm text-gray-600 dark:text-gray-400 leading-relaxed">
                {t.featureLoopDesc}
              </p>
            </div>
            <div className="bg-white dark:bg-gray-850 p-6 rounded-md shadow-sm border border-gray-200/50 dark:border-gray-800 flex flex-col gap-4 items-start text-left">
              <div className="w-10 h-10 rounded-md bg-teal-clarity/10 text-teal-clarity flex items-center justify-center font-bold text-lg shadow-sm">
                📁
              </div>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                {t.featureScopeTitle}
              </h3>
              <p className="text-sm text-gray-600 dark:text-gray-400 leading-relaxed">
                {t.featureScopeDesc}
              </p>
            </div>
          </div>
        </section>

        {/* Visual Pipeline Connection Flow Diagram Section */}
        <section
          id="diagram"
          className="bg-white dark:bg-gray-850/40 p-6 rounded-md border border-gray-200/50 dark:border-gray-800 flex flex-col gap-8"
        >
          <div className="flex flex-col gap-2 items-start text-left">
            <h2 className="text-2xl font-bold text-gray-900 dark:text-white">{t.diagramTitle}</h2>
            <p className="text-sm text-gray-500 dark:text-gray-400">{t.diagramDesc}</p>
          </div>

          <div className="relative py-4">
            {/* Background connection line */}
            <div className="absolute top-9 left-[10%] right-[10%] h-0.5 bg-gray-200 dark:bg-gray-800 z-0 hidden md:block"></div>

            <div className="relative z-10 grid grid-cols-1 md:grid-cols-5 gap-6">
              {getDiagramSteps(locale).map((step) => {
                const isActive = activeStep === step.id;
                return (
                  <button
                    key={step.id}
                    type="button"
                    onClick={() => {
                      setActiveStep(step.id);
                    }}
                    className={`bg-white dark:bg-gray-850 p-4 rounded-md border text-left flex flex-col items-start gap-3 hover:-translate-y-0.5 transition-all duration-150 cursor-pointer shadow-sm focus:outline-none focus:ring-2 focus:ring-primary ${isActive ? "border-primary ring-1 ring-primary shadow-md" : "border-gray-200 dark:border-gray-800"}`}
                  >
                    <div
                      className={`w-8 h-8 rounded-full flex items-center justify-center font-bold text-sm transition-colors ${isActive ? "bg-primary text-white" : "bg-gray-100 dark:bg-gray-800 text-gray-500"}`}
                    >
                      {step.id + 1}
                    </div>
                    <div className="flex flex-col gap-1">
                      <h4 className="font-bold text-sm text-gray-900 dark:text-white leading-tight">
                        {step.title}
                      </h4>
                      <p className="text-xs text-gray-500 dark:text-gray-400">{step.desc}</p>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Detailed step description block */}
          <div className="bg-gray-50 dark:bg-gray-900/60 p-6 rounded-md border border-primary/20 dark:border-primary/10 shadow-inner text-left transition-all duration-150">
            <h5 className="font-semibold text-sm text-primary mb-2.5 flex items-center gap-2">
              <span className="w-1.5 h-3 bg-primary rounded-full"></span>
              {getDiagramSteps(locale)[activeStep]?.title ?? ""} —{" "}
              {locale === "ja" ? "技術的詳細" : "Technical Details"}
            </h5>
            <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed font-sans">
              {getStepDetail(locale, activeStep)}
            </p>
          </div>
        </section>

        {/* Interactive Simulator Sandbox */}
        <section
          id="demo"
          className="bg-white dark:bg-gray-850 p-6 rounded-md shadow-sm border border-gray-200/50 dark:border-gray-800"
        >
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8 items-start">
            <div className="flex flex-col gap-6 items-start text-left">
              <h2 className="text-2xl font-bold text-gray-900 dark:text-white">{t.demoTitle}</h2>
              <p className="text-sm text-gray-600 dark:text-gray-400 leading-relaxed">
                {t.demoDesc}
              </p>
              <div className="flex items-center gap-3">
                <input
                  id="simulate-bug-checkbox"
                  type="checkbox"
                  className="w-4 h-4 text-primary bg-gray-100 border-gray-300 rounded-md focus:ring-primary dark:focus:ring-primary dark:ring-offset-gray-800 focus:ring-2 dark:bg-gray-700 dark:border-gray-600"
                  checked={simulateBug}
                  onChange={(e) => {
                    setSimulateBug(e.target.checked);
                  }}
                  disabled={isRunning}
                />
                <label
                  htmlFor="simulate-bug-checkbox"
                  className="text-sm font-medium text-gray-700 dark:text-gray-300 cursor-pointer"
                >
                  {t.demoCheckbox}
                </label>
              </div>
              <button
                type="button"
                className="inline-flex items-center justify-center bg-primary hover:bg-primary-hover disabled:bg-gray-400 dark:disabled:bg-gray-700 text-white font-bold text-sm px-6 py-3 rounded-md transition-colors duration-150 w-full focus-visible:ring-2 focus-visible:ring-primary focus-visible:outline-none"
                onClick={runSimulation}
                disabled={isRunning}
              >
                {isRunning && (
                  <span className="w-4 h-4 mr-2 border-2 border-white/20 border-t-white rounded-full animate-spin"></span>
                )}
                <span>{isRunning ? t.demoButtonRunning : t.demoButtonRun}</span>
              </button>
            </div>

            <div className="bg-gray-950 text-gray-200 font-mono text-xs rounded-md shadow-sm border border-gray-900 overflow-hidden flex flex-col">
              <div className="bg-gray-900/60 px-4 py-3 border-b border-gray-900 flex items-center justify-between">
                <div className="flex gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-full bg-red-500"></span>
                  <span className="w-2.5 h-2.5 rounded-full bg-yellow-500"></span>
                  <span className="w-2.5 h-2.5 rounded-full bg-green-500"></span>
                </div>
                <span className="text-gray-500">{t.demoHeader}</span>
              </div>
              <div
                className="p-4 min-h-[280px] max-h-[380px] overflow-y-auto flex flex-col gap-2 text-left"
                aria-live="polite"
              >
                {terminalLogs.map((log, index) => (
                  <div key={index} className="leading-relaxed whitespace-pre-wrap">
                    {log.type === "cmd" && (
                      <span className="text-teal-clarity mr-2 font-bold">$</span>
                    )}
                    <span
                      className={
                        log.type === "success"
                          ? "text-stable-green"
                          : log.type === "error"
                            ? "text-red-500"
                            : log.type === "warning"
                              ? "text-grounded-orange"
                              : log.type === "info"
                                ? "text-gray-400"
                                : "text-gray-200"
                      }
                    >
                      {log.text}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* Double Gate Workflow Section */}
        <section id="workflow" className="flex flex-col gap-8">
          <div className="flex flex-col gap-2">
            <h2 className="text-2xl font-bold text-gray-900 dark:text-white">{t.workflowTitle}</h2>
            <p className="text-sm text-gray-500 dark:text-gray-400">{t.workflowDesc}</p>
          </div>
          <div className="flex flex-col gap-6 max-w-3xl">
            <div className="flex gap-6 items-start text-left">
              <div className="w-10 h-10 rounded-full bg-primary/10 text-primary flex items-center justify-center font-bold text-lg flex-shrink-0 border border-primary/20 shadow-sm">
                01
              </div>
              <div className="flex flex-col gap-1">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                  {t.workflowStep1Title}
                </h3>
                <p className="text-sm text-gray-600 dark:text-gray-400 leading-relaxed font-sans">
                  {t.workflowStep1Desc}
                </p>
              </div>
            </div>
            <div className="w-0.5 h-8 bg-gray-200 dark:bg-gray-800 ml-5"></div>
            <div className="flex gap-6 items-start text-left">
              <div className="w-10 h-10 rounded-full bg-primary/10 text-primary flex items-center justify-center font-bold text-lg flex-shrink-0 border border-primary/20 shadow-sm">
                02
              </div>
              <div className="flex flex-col gap-1">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                  {t.workflowStep2Title}
                </h3>
                <p className="text-sm text-gray-600 dark:text-gray-400 leading-relaxed font-sans">
                  {t.workflowStep2Desc}
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* Configurations Tabs */}
        <section id="config" className="flex flex-col gap-8">
          <div className="flex flex-col gap-2 font-sans">
            <h2 className="text-2xl font-bold text-gray-900 dark:text-white">{t.configTitle}</h2>
            <p className="text-sm text-gray-500 dark:text-gray-400 font-sans">{t.configDesc}</p>
          </div>
          <div className="flex flex-col gap-4">
            <div className="flex items-center gap-2 border-b border-gray-200 dark:border-gray-800">
              <button
                type="button"
                className={`text-sm font-semibold pb-3 px-4 border-b-2 transition-colors duration-150 focus-visible:outline-none ${activeTab === "yaml" ? "border-primary text-primary" : "border-transparent text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"}`}
                onClick={() => {
                  setActiveTab("yaml");
                }}
              >
                {t.configTabPrecommit}
              </button>
              <button
                type="button"
                className={`text-sm font-semibold pb-3 px-4 border-b-2 transition-colors duration-150 focus-visible:outline-none ${activeTab === "eslint" ? "border-primary text-primary" : "border-transparent text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"}`}
                onClick={() => {
                  setActiveTab("eslint");
                }}
              >
                {t.configTabEslint}
              </button>
              <button
                type="button"
                className={`text-sm font-semibold pb-3 px-4 border-b-2 transition-colors duration-150 focus-visible:outline-none ${activeTab === "circuit" ? "border-primary text-primary" : "border-transparent text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"}`}
                onClick={() => {
                  setActiveTab("circuit");
                }}
              >
                {t.configTabCircuit}
              </button>
            </div>
            <div className="bg-gray-950 rounded-md border border-gray-900 overflow-hidden shadow-sm text-left">
              <pre className="p-5 font-mono text-xs overflow-x-auto text-gray-300 leading-relaxed whitespace-pre">
                <code>{getCodeSnippet()}</code>
              </pre>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-gray-200/50 dark:border-gray-800/50 py-8 mt-12 transition-colors duration-150">
        <div className="max-w-6xl mx-auto px-6 flex flex-col md:flex-row items-center justify-between gap-4">
          <span className="text-sm font-bold text-gray-900 dark:text-white">
            AME AI Review System
          </span>
          <p className="text-xs text-gray-500">© 2026 AME Team. All rights reserved.</p>
        </div>
      </footer>
    </div>
  );
}
