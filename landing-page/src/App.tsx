import React, { useState, useEffect, useRef } from "react";
import { ReactFlow, Background, Controls, Handle, Position } from "@xyflow/react";
import "@xyflow/react/dist/style.css";

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
  navEngines: string;
  navDemo: string;
  navWorkflow: string;
  navConfig: string;
  githubRepo: string;
  badgeVersion: string;
  heroTitle1: string;
  heroTitleAccent: string;
  heroTitle2: string;
  heroDesc: string;
  tryDemoBtn: string;
  viewConfigBtn: string;
  secFeaturesTitle: string;
  secFeaturesDesc: string;
  featureDiffTitle: string;
  featureDiffDesc: string;
  featureCbTitle: string;
  featureCbDesc: string;
  featureGateTitle: string;
  featureGateDesc: string;
  featureAgentTitle: string;
  featureAgentDesc: string;
  featureCompressTitle: string;
  featureCompressDesc: string;
  featureLoopTitle: string;
  featureLoopDesc: string;
  enginesTitle: string;
  enginesDesc: string;
  engineClaudeTitle: string;
  engineClaudeDesc: string;
  engineOpencodeTitle: string;
  engineOpencodeDesc: string;
  engineAntigravityTitle: string;
  engineAntigravityDesc: string;
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
    navEngines: "Codingエージェント",
    navDemo: "動作デモ",
    navWorkflow: "ワークフロー",
    navConfig: "設定構成",
    githubRepo: "GitHub リポジトリ",
    badgeVersion: "v2.0.0 厳格監視ゲート",
    heroTitle1: "デュアルゲートAIコードレビュー",
    heroTitleAccent: "超厳格な静的解析とAIエージェント",
    heroTitle2: "が品質を徹底保証",
    heroDesc:
      "開発者のローカル環境（Gate 1）とプルリクエスト（Gate 2）の二重ゲート構造。mainブランチとの全累積差分評価、超厳格な静的解析サーキットブレーカー、およびClaude Code / OpenCode / Antigravityなどの各種Codingエージェント連携により、コードとドキュメントの品質を保証します。",
    tryDemoBtn: "シミュレーターを試す",
    viewConfigBtn: "設定ファイルを見る",
    secFeaturesTitle: "厳格さと柔軟性を備えたコアアーキテクチャ",
    secFeaturesDesc:
      "静的解析の超厳格性とAIエージェントの柔軟なコンテキスト評価を融合した品質管理機構",
    featureDiffTitle: "mainブランチ累積差分レビュー",
    featureDiffDesc:
      "Commit単位の局所的な変更点ではなく origin/main...HEAD の全累積差分を評価。複数コミットを含むPRでも変更の全容を漏らさず正確に追跡・レビューします。",
    featureCbTitle: "超厳格な静的サーキットブレーカー",
    featureCbDesc:
      "TypeScript (tsc)、ESLint (--max-warnings=0)、Python (mypy/ruff)、Semgrep を前段で実行。機械的指摘を100%捕捉し、エラー時はAI呼び出しを即時スキップします。",
    featureGateTitle: "Dual-Gate 品質保証",
    featureGateDesc:
      "ローカルコミット時（Gate 1）とCI/CDのPR時（Gate 2）の二段階で静的解析とAIレビューを実行。早期検出（Shift-Left）とPRでの強固なガードを完璧に両立します。",
    featureAgentTitle: "Codingエージェント & 広範コンテキスト検証",
    featureAgentDesc:
      "Claude Code, OpenCode, Antigravity CLIなどのCodingエージェントをエンジンに指定可能。差分外を含む全リポジトリを参照し「コード修正に伴うDocumentsの更新有無」なども自動チェック可能。",
    featureCompressTitle: "headroom トークン圧縮技術",
    featureCompressDesc:
      "Gitメタデータ、バイナリ差分、冗長な空行、構成ファイル内の不要セクションを自動圧縮。AIへの入力トークン量を最小限に抑えプロンプトキャッシュを最適化します。",
    featureLoopTitle: "停滞ループ自動検出",
    featureLoopDesc:
      "指摘内容のJaccard類似度を自動評価。進展のない堂々巡りの議論（無限ループ）を検知すると強制的にLGTMを発行しデリバリー速度の低下を防ぎます。",
    enginesTitle: "対応 Coding エージェント",
    enginesDesc: "開発スタイルや環境に合わせて切り替え可能なマルチエンジン構造",
    engineClaudeTitle: "Claude Code",
    engineClaudeDesc:
      "Anthropic開発のエージェント。リポジトリ全域のコンテキスト参照・プロンプトキャッシュ最適化・予算上限管理に対応。",
    engineOpencodeTitle: "OpenCode",
    engineOpencodeDesc:
      "オープンソースエージェント。Anthropic, OpenRouter, DeepSeek, Tencent など多種多様なLLMプロバイダーを統合利用可能。",
    engineAntigravityTitle: "Antigravity CLI",
    engineAntigravityDesc:
      "Google DeepMind開発の高度なAIエージェント。広範なコンテキスト検証と段階的なReasoning Effort(High/Medium/Low)に対応。",
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
    navEngines: "Coding Agents",
    navDemo: "Interactive Demo",
    navWorkflow: "Workflow",
    navConfig: "Configuration",
    githubRepo: "GitHub Repo",
    badgeVersion: "v2.0.0 Strict Monitoring Gate",
    heroTitle1: "Dual-Gate AI Code Review",
    heroTitleAccent: "Ultra-Strict Static Checks & AI Agents",
    heroTitle2: "Guarantee Complete Quality",
    heroDesc:
      "A dual-gate quality control architecture combining local pre-commit (Gate 1) and pull request reviews (Gate 2). Evaluates cumulative main branch diffs, ultra-strict static circuit breakers, and integrates Coding agents like Claude Code, OpenCode, and Antigravity for code and document assurance.",
    tryDemoBtn: "Try Simulator",
    viewConfigBtn: "View Config Files",
    secFeaturesTitle: "Core Architecture Designed for Rigidity & Flexibility",
    secFeaturesDesc:
      "A quality management system combining ultra-strict static analysis with flexible AI agent context evaluations",
    featureDiffTitle: "Main Branch Cumulative Diff Review",
    featureDiffDesc:
      "Evaluates cumulative diffs (origin/main...HEAD) instead of per-commit fragments, capturing the full scope of multi-commit PRs accurately.",
    featureCbTitle: "Ultra-Strict Static Circuit Breaker",
    featureCbDesc:
      "Executes tsc, ESLint (--max-warnings=0), mypy/ruff, and Semgrep upfront. Catches 100% of static issues early and skips AI calls when errors occur.",
    featureGateTitle: "Dual-Gate Quality Assurance",
    featureGateDesc:
      "Combines local pre-commit verification (Gate 1) with CI pull request reviews (Gate 2), ensuring local Shift-Left and solid CI gating.",
    featureAgentTitle: "Coding Agent & Full Context Analysis",
    featureAgentDesc:
      "Supports Claude Code, OpenCode, and Antigravity CLI. Refers to full repository context to automatically check if documentation updates match code changes.",
    featureCompressTitle: "headroom Token Compression",
    featureCompressDesc:
      "Automatically filters Git metadata and redundant lines, compressing LLM input tokens and maximizing prompt caching efficiency.",
    featureLoopTitle: "Stagnation Loop Detection",
    featureLoopDesc:
      "Evaluates comment Jaccard similarity to catch circular discussions, issuing forced LGTMs to maintain team velocity.",
    enginesTitle: "Supported Coding Agents",
    enginesDesc: "Multi-engine architecture adaptable to your team's workflow and AI stack",
    engineClaudeTitle: "Claude Code",
    engineClaudeDesc:
      "Powered by Anthropic. Features deep repository-wide context, prompt caching, and per-run budget caps.",
    engineOpencodeTitle: "OpenCode",
    engineOpencodeDesc:
      "Open-source agent engine supporting multi-provider models (Anthropic, OpenRouter, DeepSeek, Tencent, etc.).",
    engineAntigravityTitle: "Antigravity CLI",
    engineAntigravityDesc:
      "Next-gen agent by Google DeepMind with deep context reasoning and configurable effort controls.",
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

const GateCustomNode: React.FC<{
  data: { title: string; desc: string; badges: string[]; isGate1?: boolean };
}> = ({ data }) => {
  return (
    <div className="px-4 py-3 rounded-xl bg-white dark:bg-gray-800 border-2 border-primary/40 shadow-lg min-w-[260px] max-w-[300px]">
      <Handle type="target" position={Position.Left} className="!bg-primary !w-3 !h-3" />
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between border-b border-gray-100 dark:border-gray-700 pb-2">
          <span className="font-bold text-sm text-gray-900 dark:text-white flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-primary inline-block"></span>
            {data.title}
          </span>
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-primary/10 text-primary font-semibold">
            {data.isGate1 === true ? "Local" : "CI/CD"}
          </span>
        </div>
        <p className="text-xs text-gray-500 dark:text-gray-400 font-sans">{data.desc}</p>
        <div className="flex flex-wrap gap-1 mt-1">
          {data.badges.map((b, i) => (
            <span
              key={i}
              className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 border border-gray-200 dark:border-gray-600 font-mono"
            >
              {b}
            </span>
          ))}
        </div>
      </div>
      <Handle
        type="source"
        position={Position.Right}
        id="pass"
        className="!bg-emerald-500 !w-3 !h-3"
      />
      <Handle
        type="source"
        position={Position.Bottom}
        id="fail"
        className="!bg-rose-500 !w-3 !h-3"
      />
    </div>
  );
};

const ActionCustomNode: React.FC<{ data: { label: string; sub: string } }> = ({ data }) => {
  return (
    <div className="px-4 py-2.5 rounded-lg bg-gray-900 text-white dark:bg-gray-100 dark:text-gray-900 font-semibold text-xs shadow-md border border-gray-700 dark:border-gray-300 min-w-[130px] text-center">
      <Handle type="target" position={Position.Left} className="!bg-gray-400 !w-2.5 !h-2.5" />
      <div>{data.label}</div>
      <div className="text-[10px] opacity-75 font-normal font-sans mt-0.5">{data.sub}</div>
      <Handle type="source" position={Position.Right} className="!bg-gray-400 !w-2.5 !h-2.5" />
    </div>
  );
};

const FailCustomNode: React.FC<{ data: { label: string; sub: string } }> = ({ data }) => {
  return (
    <div className="px-3 py-2 rounded-lg bg-rose-50 dark:bg-rose-950/50 border border-rose-300 dark:border-rose-800 text-rose-700 dark:text-rose-300 text-xs shadow-sm text-center font-sans">
      <Handle type="target" position={Position.Top} className="!bg-rose-500 !w-2.5 !h-2.5" />
      <div className="font-bold">{data.label}</div>
      <div className="text-[10px] text-rose-500 dark:text-rose-400 mt-0.5">{data.sub}</div>
    </div>
  );
};

const flowNodeTypes = {
  gate: GateCustomNode,
  action: ActionCustomNode,
  fail: FailCustomNode,
};

const DualGateFlowDiagram: React.FC<{ locale: Locale }> = ({ locale }) => {
  const isJa = locale === "ja";

  const nodes = [
    {
      id: "commit",
      type: "action",
      position: { x: 20, y: 110 },
      data: {
        label: "git commit",
        sub: isJa ? "ローカルコミット" : "Local Commit",
      },
    },
    {
      id: "gate1",
      type: "gate",
      position: { x: 200, y: 30 },
      data: {
        title: "Gate 1: pre-commit",
        desc: isJa ? "静的解析 (25+ツール) ＋ AI レビュー" : "Static Check (25+ tools) + AI Review",
        badges: ["Python", "Security", "Frontend", "Docs", "Config", "Shell/CI", "Git", "Test"],
        isGate1: true,
      },
    },
    {
      id: "gate1-fail",
      type: "fail",
      position: { x: 235, y: 240 },
      data: {
        label: isJa ? "コミットブロック ❌" : "Commit Blocked ❌",
        sub: isJa ? "静的解析エラー / 重大指摘" : "Static Error / Major Issue",
      },
    },
    {
      id: "pr",
      type: "action",
      position: { x: 550, y: 110 },
      data: {
        label: "PR / /request-review",
        sub: isJa ? "GitHub Actions 起動" : "Trigger CI Workflow",
      },
    },
    {
      id: "gate2",
      type: "gate",
      position: { x: 770, y: 30 },
      data: {
        title: "Gate 2: PR (CI/CD)",
        desc: isJa
          ? "Circuit Breaker 静的解析 ＋ AI レビュー"
          : "Circuit Breaker Static Check + AI Review",
        badges: ["ruff/mypy/semgrep", "Circuit Breaker", "Multi-Agent", "Reply Sync"],
        isGate1: false,
      },
    },
    {
      id: "gate2-fail",
      type: "fail",
      position: { x: 805, y: 240 },
      data: {
        label: isJa ? "AIレビュー スキップ ⚠️" : "AI Review Skipped ⚠️",
        sub: isJa ? "Circuit Breaker 発動" : "Circuit Breaker Triggered",
      },
    },
    {
      id: "merge",
      type: "action",
      position: { x: 1120, y: 110 },
      data: {
        label: isJa ? "PR マージ 🎉" : "PR Merged 🎉",
        sub: isJa ? "品質保証パス" : "Quality Passed",
      },
    },
  ];

  const edges = [
    {
      id: "e1",
      source: "commit",
      target: "gate1",
      animated: true,
      style: { stroke: "#6366f1", strokeWidth: 2 },
    },
    {
      id: "e-g1-fail",
      source: "gate1",
      sourceHandle: "fail",
      target: "gate1-fail",
      label: "FAIL",
      style: { stroke: "#f43f5e", strokeDasharray: "4,4", strokeWidth: 2 },
    },
    {
      id: "e-g1-pass",
      source: "gate1",
      sourceHandle: "pass",
      target: "pr",
      label: "PASS",
      style: { stroke: "#10b981", strokeWidth: 2 },
    },
    {
      id: "e2",
      source: "pr",
      target: "gate2",
      animated: true,
      style: { stroke: "#6366f1", strokeWidth: 2 },
    },
    {
      id: "e-g2-fail",
      source: "gate2",
      sourceHandle: "fail",
      target: "gate2-fail",
      label: "FAIL (Circuit Breaker)",
      style: { stroke: "#f43f5e", strokeDasharray: "4,4", strokeWidth: 2 },
    },
    {
      id: "e-g2-pass",
      source: "gate2",
      sourceHandle: "pass",
      target: "merge",
      label: "PASS (LGTM)",
      style: { stroke: "#10b981", strokeWidth: 2 },
    },
  ];

  return (
    <div className="w-full h-[360px] rounded-2xl border border-gray-200 dark:border-gray-800 bg-gray-50/50 dark:bg-gray-900/50 overflow-hidden shadow-inner relative">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={flowNodeTypes}
        fitView
        nodesDraggable={false}
        nodesConnectable={false}
        zoomOnScroll={false}
        panOnScroll={false}
        preventScrolling={false}
      >
        <Background color="#888888" gap={16} size={1} style={{ opacity: 0.15 }} />
        <Controls
          showInteractive={false}
          className="!bg-white dark:!bg-gray-800 !border-gray-200 dark:!border-gray-700 shadow-sm"
        />
      </ReactFlow>
    </div>
  );
};

const EngineComparisonSection: React.FC<{ t: TranslationResource }> = ({ t }) => {
  return (
    <section id="engines" className="flex flex-col gap-8 my-4">
      <div className="flex flex-col gap-2">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary/10 text-primary text-xs font-semibold w-fit">
          Multi-Engine Integration
        </div>
        <h2 className="text-2xl font-bold text-gray-900 dark:text-white">{t.enginesTitle}</h2>
        <p className="text-sm text-gray-500 dark:text-gray-400">{t.enginesDesc}</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Claude Code */}
        <div className="flex flex-col gap-4 p-6 rounded-2xl bg-white dark:bg-gray-800/80 border border-gray-200/80 dark:border-gray-700/80 shadow-sm hover:shadow-md transition-shadow">
          <div className="w-12 h-12 rounded-xl bg-amber-500/10 text-amber-600 dark:text-amber-400 flex items-center justify-center font-bold text-xl">
            Cc
          </div>
          <div className="flex flex-col gap-1.5">
            <h3 className="text-lg font-bold text-gray-900 dark:text-white flex items-center justify-between">
              {t.engineClaudeTitle}
              <span className="text-xs px-2 py-0.5 rounded bg-amber-100 dark:bg-amber-950 text-amber-700 dark:text-amber-300 font-normal">
                Anthropic
              </span>
            </h3>
            <p className="text-xs text-gray-600 dark:text-gray-400 leading-relaxed font-sans">
              {t.engineClaudeDesc}
            </p>
          </div>
          <div className="mt-auto pt-3 border-t border-gray-100 dark:border-gray-700/50 flex items-center gap-2 text-[11px] text-gray-500 dark:text-gray-400 font-mono">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
            <code>claude -p</code> / Budget limit
          </div>
        </div>

        {/* OpenCode */}
        <div className="flex flex-col gap-4 p-6 rounded-2xl bg-white dark:bg-gray-800/80 border border-gray-200/80 dark:border-gray-700/80 shadow-sm hover:shadow-md transition-shadow">
          <div className="w-12 h-12 rounded-xl bg-blue-500/10 text-blue-600 dark:text-blue-400 flex items-center justify-center font-bold text-xl">
            Oc
          </div>
          <div className="flex flex-col gap-1.5">
            <h3 className="text-lg font-bold text-gray-900 dark:text-white flex items-center justify-between">
              {t.engineOpencodeTitle}
              <span className="text-xs px-2 py-0.5 rounded bg-blue-100 dark:bg-blue-950 text-blue-700 dark:text-blue-300 font-normal">
                Multi-Provider
              </span>
            </h3>
            <p className="text-xs text-gray-600 dark:text-gray-400 leading-relaxed font-sans">
              {t.engineOpencodeDesc}
            </p>
          </div>
          <div className="mt-auto pt-3 border-t border-gray-100 dark:border-gray-700/50 flex items-center gap-2 text-[11px] text-gray-500 dark:text-gray-400 font-mono">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
            <code>opencode run</code> / OpenRouter
          </div>
        </div>

        {/* Antigravity CLI */}
        <div className="flex flex-col gap-4 p-6 rounded-2xl bg-white dark:bg-gray-800/80 border border-gray-200/80 dark:border-gray-700/80 shadow-sm hover:shadow-md transition-shadow">
          <div className="w-12 h-12 rounded-xl bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 flex items-center justify-center font-bold text-xl">
            Ag
          </div>
          <div className="flex flex-col gap-1.5">
            <h3 className="text-lg font-bold text-gray-900 dark:text-white flex items-center justify-between">
              {t.engineAntigravityTitle}
              <span className="text-xs px-2 py-0.5 rounded bg-indigo-100 dark:bg-indigo-950 text-indigo-700 dark:text-indigo-300 font-normal">
                Google DeepMind
              </span>
            </h3>
            <p className="text-xs text-gray-600 dark:text-gray-400 leading-relaxed font-sans">
              {t.engineAntigravityDesc}
            </p>
          </div>
          <div className="mt-auto pt-3 border-t border-gray-100 dark:border-gray-700/50 flex items-center gap-2 text-[11px] text-gray-500 dark:text-gray-400 font-mono">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
            <code>agy</code> / Gemini Reasoning
          </div>
        </div>
      </div>
    </section>
  );
};

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
              href="#engines"
              className="text-sm font-medium text-gray-500 hover:text-primary dark:text-gray-400 dark:hover:text-primary transition-colors duration-150"
            >
              {t.navEngines}
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
                import.meta.env.VITE_GITHUB_URL ??
                "https://github.com/tarminjapan/AME-AI-Review-System"
              }
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center justify-center bg-gray-900 dark:bg-gray-800 text-white hover:bg-gray-800 dark:hover:bg-gray-700 text-xs font-semibold px-4 py-2 rounded-md transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-primary focus-visible:outline-none"
            >
              {t.githubRepo}
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
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="bg-white dark:bg-gray-850 p-6 rounded-md shadow-sm border border-gray-200/50 dark:border-gray-800 flex flex-col gap-4 items-start text-left">
              <div className="w-10 h-10 rounded-md bg-primary/10 text-primary flex items-center justify-center font-bold text-base shadow-sm">
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
                    d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4"
                  />
                </svg>
              </div>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                {t.featureDiffTitle}
              </h3>
              <p className="text-sm text-gray-600 dark:text-gray-400 leading-relaxed">
                {t.featureDiffDesc}
              </p>
            </div>
            <div className="bg-white dark:bg-gray-850 p-6 rounded-md shadow-sm border border-gray-200/50 dark:border-gray-800 flex flex-col gap-4 items-start text-left">
              <div className="w-10 h-10 rounded-md bg-grounded-orange/10 text-grounded-orange flex items-center justify-center font-bold text-base shadow-sm">
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
                    d="M13 10V3L4 14h7v7l9-11h-7z"
                  />
                </svg>
              </div>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                {t.featureCbTitle}
              </h3>
              <p className="text-sm text-gray-600 dark:text-gray-400 leading-relaxed">
                {t.featureCbDesc}
              </p>
            </div>
            <div className="bg-white dark:bg-gray-850 p-6 rounded-md shadow-sm border border-gray-200/50 dark:border-gray-800 flex flex-col gap-4 items-start text-left">
              <div className="w-10 h-10 rounded-md bg-stable-green/10 text-stable-green flex items-center justify-center font-bold text-base shadow-sm">
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
                    d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"
                  />
                </svg>
              </div>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                {t.featureGateTitle}
              </h3>
              <p className="text-sm text-gray-600 dark:text-gray-400 leading-relaxed">
                {t.featureGateDesc}
              </p>
            </div>
            <div className="bg-white dark:bg-gray-850 p-6 rounded-md shadow-sm border border-gray-200/50 dark:border-gray-800 flex flex-col gap-4 items-start text-left">
              <div className="w-10 h-10 rounded-md bg-indigo-sophisticated/10 text-indigo-sophisticated flex items-center justify-center font-bold text-base shadow-sm">
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
                    d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
                  />
                </svg>
              </div>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                {t.featureAgentTitle}
              </h3>
              <p className="text-sm text-gray-600 dark:text-gray-400 leading-relaxed">
                {t.featureAgentDesc}
              </p>
            </div>
            <div className="bg-white dark:bg-gray-850 p-6 rounded-md shadow-sm border border-gray-200/50 dark:border-gray-800 flex flex-col gap-4 items-start text-left">
              <div className="w-10 h-10 rounded-md bg-teal-clarity/10 text-teal-clarity flex items-center justify-center font-bold text-base shadow-sm">
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
                    d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"
                  />
                </svg>
              </div>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                {t.featureCompressTitle}
              </h3>
              <p className="text-sm text-gray-600 dark:text-gray-400 leading-relaxed">
                {t.featureCompressDesc}
              </p>
            </div>
            <div className="bg-white dark:bg-gray-850 p-6 rounded-md shadow-sm border border-gray-200/50 dark:border-gray-800 flex flex-col gap-4 items-start text-left">
              <div className="w-10 h-10 rounded-md bg-primary/10 text-primary flex items-center justify-center font-bold text-base shadow-sm">
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
                    d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                  />
                </svg>
              </div>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                {t.featureLoopTitle}
              </h3>
              <p className="text-sm text-gray-600 dark:text-gray-400 leading-relaxed">
                {t.featureLoopDesc}
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

        {/* Multi-Engine Comparison Section */}
        <EngineComparisonSection t={t} />

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
          <DualGateFlowDiagram locale={locale} />

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 font-sans">
            <div className="p-5 rounded-xl bg-white dark:bg-gray-800/60 border border-gray-200/80 dark:border-gray-700/80 shadow-sm flex flex-col gap-2">
              <h3 className="font-bold text-base text-gray-900 dark:text-white flex items-center gap-2">
                <span className="w-6 h-6 rounded-full bg-primary/10 text-primary text-xs flex items-center justify-center font-bold">
                  01
                </span>
                {t.workflowStep1Title}
              </h3>
              <p className="text-xs text-gray-600 dark:text-gray-400 leading-relaxed font-sans">
                {t.workflowStep1Desc}
              </p>
            </div>
            <div className="p-5 rounded-xl bg-white dark:bg-gray-800/60 border border-gray-200/80 dark:border-gray-700/80 shadow-sm flex flex-col gap-2">
              <h3 className="font-bold text-base text-gray-900 dark:text-white flex items-center gap-2">
                <span className="w-6 h-6 rounded-full bg-primary/10 text-primary text-xs flex items-center justify-center font-bold">
                  02
                </span>
                {t.workflowStep2Title}
              </h3>
              <p className="text-xs text-gray-600 dark:text-gray-400 leading-relaxed font-sans">
                {t.workflowStep2Desc}
              </p>
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
