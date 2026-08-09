import React, { useState, useEffect } from "react";
import { ReactFlow, Background, Controls, Handle, Position } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { type Locale, type TranslationResource } from "./i18n";

export interface LogMessage {
  type: "cmd" | "info" | "success" | "warning" | "error";
  text: string;
}

interface StaticAnalysisCategory {
  id: string;
  abbr: string;
  nameJa: string;
  nameEn: string;
  tools: string[];
  configFiles: string[];
  colorClasses: string;
}

const staticAnalysisCategories: StaticAnalysisCategory[] = [
  {
    id: "python",
    abbr: "Py",
    nameJa: "Python",
    nameEn: "Python",
    tools: ["ruff (lint, ALL+preview)", "ruff-format", "mypy (strict)", "pyright"],
    configFiles: ["pyproject.toml"],
    colorClasses: "bg-blue-500/10 text-blue-600 dark:text-blue-400",
  },
  {
    id: "security",
    abbr: "Sec",
    nameJa: "セキュリティ",
    nameEn: "Security",
    tools: ["semgrep-custom (8 rules)", "gitleaks", "detect-private-key"],
    configFiles: ["ame_ai_review_system/.semgrep/rules.yml", ".gitleaks.toml"],
    colorClasses: "bg-rose-500/10 text-rose-600 dark:text-rose-400",
  },
  {
    id: "frontend",
    abbr: "FE",
    nameJa: "フロントエンド",
    nameEn: "Frontend",
    tools: ["eslint (--max-warnings=0)", "tsc --noEmit", "stylelint"],
    configFiles: ["eslint.config.mjs", "tsconfig.json"],
    colorClasses: "bg-amber-500/10 text-amber-600 dark:text-amber-400",
  },
  {
    id: "docs",
    abbr: "Doc",
    nameJa: "ドキュメント/文章",
    nameEn: "Docs & Prose",
    tools: ["markdownlint-cli2", "textlint", "codespell", "mermaid-check (custom)"],
    configFiles: [".markdownlint-cli2.jsonc", ".textlintrc"],
    colorClasses: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
  },
  {
    id: "config-data",
    abbr: "Cfg",
    nameJa: "設定/データ",
    nameEn: "Config & Data",
    tools: ["yamllint (strict)", "check-yaml", "check-toml", "check-json", "sqlfluff"],
    configFiles: [".yamllint.yaml", ".sqlfluff"],
    colorClasses: "bg-indigo-500/10 text-indigo-600 dark:text-indigo-400",
  },
  {
    id: "shell-ci",
    abbr: "Sh",
    nameJa: "シェル/CI",
    nameEn: "Shell & CI",
    tools: ["shellcheck", "actionlint"],
    configFiles: [".shellcheckrc", ".actionlint.yaml"],
    colorClasses: "bg-cyan-500/10 text-cyan-600 dark:text-cyan-400",
  },
  {
    id: "git-hygiene",
    abbr: "Git",
    nameJa: "Git衛生",
    nameEn: "Git Hygiene",
    tools: ["commitlint", "check-merge-conflict", "check-case-conflict", "check-added-large-files"],
    configFiles: [".commitlintrc.json", "pre-commit-hooks"],
    colorClasses: "bg-orange-500/10 text-orange-600 dark:text-orange-400",
  },
  {
    id: "format",
    abbr: "Fmt",
    nameJa: "フォーマット",
    nameEn: "Formatting",
    tools: ["prettier-root"],
    configFiles: [".prettierrc"],
    colorClasses: "bg-purple-500/10 text-purple-600 dark:text-purple-400",
  },
  {
    id: "repo-rules",
    abbr: "Rule",
    nameJa: "自作リポジトリ規約",
    nameEn: "Custom Repo Rules",
    tools: ["prohibit-suppression-comments", "repo-hygiene"],
    configFiles: ["scripts/check_suppression_comments.py"],
    colorClasses: "bg-teal-500/10 text-teal-600 dark:text-teal-400",
  },
  {
    id: "test",
    abbr: "Test",
    nameJa: "テスト",
    nameEn: "Testing",
    tools: ["pytest", "vitest (pre-push / pre-merge-commit)"],
    configFiles: ["pyproject.toml", "vitest.config.ts"],
    colorClasses: "bg-lime-500/10 text-lime-600 dark:text-lime-400",
  },
];

export const StaticAnalysisSection: React.FC<{ t: TranslationResource; locale: Locale }> = ({
  t,
  locale,
}) => {
  const isJa = locale === "ja";
  const totalTools = staticAnalysisCategories.reduce((sum, c) => sum + c.tools.length, 0);

  return (
    <section id="static-analysis" className="flex flex-col gap-8 w-full max-w-6xl mx-auto">
      <div className="flex flex-col gap-2">
        <h2 className="text-2xl font-bold text-gray-900 dark:text-white">
          {t.staticAnalysisTitle}
        </h2>
        <p className="text-sm text-gray-500 dark:text-gray-400 max-w-3xl">{t.staticAnalysisDesc}</p>
      </div>

      <div className="flex flex-wrap gap-4">
        <div className="flex items-baseline gap-2 px-4 py-3 rounded-md bg-primary/10 border border-primary/20">
          <span className="text-2xl font-bold text-primary">{staticAnalysisCategories.length}</span>
          <span className="text-xs font-semibold text-primary">
            {t.staticAnalysisStatCategories}
          </span>
        </div>
        <div className="flex items-baseline gap-2 px-4 py-3 rounded-md bg-primary/10 border border-primary/20">
          <span className="text-2xl font-bold text-primary">{totalTools}+</span>
          <span className="text-xs font-semibold text-primary">{t.staticAnalysisStatTools}</span>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {staticAnalysisCategories.map((category) => (
          <div
            key={category.id}
            className="flex flex-col gap-4 p-6 rounded-2xl bg-white dark:bg-gray-800/80 border border-gray-200/80 dark:border-gray-700/80 shadow-sm hover:shadow-md transition-shadow"
          >
            <div
              className={`w-12 h-12 rounded-xl flex items-center justify-center font-bold text-sm ${category.colorClasses}`}
            >
              {category.abbr}
            </div>
            <div className="flex flex-col gap-2.5">
              <h3 className="text-base font-bold text-gray-900 dark:text-white">
                {isJa ? category.nameJa : category.nameEn}
              </h3>
              <div className="flex flex-wrap gap-1.5">
                {category.tools.map((tool) => (
                  <span
                    key={tool}
                    className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 border border-gray-200 dark:border-gray-600 font-mono"
                  >
                    {tool}
                  </span>
                ))}
              </div>
            </div>
            <div className="mt-auto pt-3 border-t border-gray-100 dark:border-gray-700/50 flex flex-col gap-1 text-[11px] text-gray-500 dark:text-gray-400 font-mono">
              <span className="font-sans font-semibold text-gray-400 dark:text-gray-500">
                {t.staticAnalysisConfigLabel}
              </span>
              {category.configFiles.map((file) => (
                <code key={file}>{file}</code>
              ))}
            </div>
          </div>
        ))}
      </div>

      <p className="text-xs text-gray-500 dark:text-gray-400 max-w-3xl">
        {t.staticAnalysisPortabilityNote}
      </p>
    </section>
  );
};

export const EngineComparisonSection: React.FC<{ t: TranslationResource }> = ({ t }) => {
  return (
    <section id="engines" className="flex flex-col gap-8 my-4 w-full max-w-6xl mx-auto">
      <div className="flex flex-col gap-2">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary/10 text-primary text-xs font-semibold w-fit">
          Multi-Engine Integration
        </div>
        <h2 className="text-2xl font-bold text-gray-900 dark:text-white">{t.enginesTitle}</h2>
        <p className="text-sm text-gray-500 dark:text-gray-400">{t.enginesDesc}</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
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
            <code>claude-agent-sdk</code> / Budget limit
          </div>
        </div>

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
            <code>@opencode-ai/sdk</code> / OpenRouter
          </div>
        </div>

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
            <code>google-antigravity</code> / Gemini Reasoning
          </div>
        </div>
      </div>
    </section>
  );
};

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

export const DualGateFlowDiagram: React.FC<{ locale: Locale }> = ({ locale }) => {
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
        sub: isJa ? "品質チェックパス" : "Quality Checked",
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

interface DiagramStep {
  id: number;
  title: string;
  desc: string;
}

function getDiagramSteps(t: TranslationResource): DiagramStep[] {
  return [
    { id: 0, title: t.diagramStepFile, desc: t.diagramStepFileDesc },
    { id: 1, title: t.diagramStepGate1, desc: t.diagramStepGate1Desc },
    { id: 2, title: t.diagramStepCommit, desc: t.diagramStepCommitDesc },
    { id: 3, title: t.diagramStepGate2, desc: t.diagramStepGate2Desc },
  ];
}

function getStepDetail(locale: Locale, step: number): string {
  if (locale === "ja") {
    switch (step) {
      case 0:
        return "【変更監視の対象】TypeScriptやPythonのソースコードに加え、Markdownドキュメント、JSON、YAML等の主要構成ファイルの変更も検知しトラッキングします。変更がないファイルは検証をスキップし、検証を高速化します。";
      case 1:
        return "【静的サーキットブレーカー】コミットフック（pre-commit）が働き、tsc(型チェック)、eslint(スタイル)、mypy/ruff(Python静的解析)を並行して実行します。ここでエラーが出た場合はAI APIの実行を即時中断し、不要なAPI利用と開発者の待機を防ぎます。";
      case 2:
        return "【ローカルコミット許可】すべてのローカル静的検証と、AIローカル事前チェックを通過した場合にのみ、コミットが成功します。開発者はバグが混入していないクリーンな状態で作業を進められます。";
      case 3:
        return "【CI自動レビュー】コードがリモートにプッシュされPR（プルリクエスト）が作成されると、CI上のレビューシステム（ゲート2）が起動。/request-review コメントでAIのディスカッションスレッドが作られ、類似度比較による停滞ループ検知が作動します。";
      default:
        return "";
    }
  }
  switch (step) {
    case 0:
      return "[Change Tracking] Identifies modified files among TS/JS/Python source codes, Markdown docs, JSON, and YAML configuration files. Clean files are skipped dynamically to speed up checkout stages.";
    case 1:
      return "[Static Circuit Breaker] Pre-commit hooks run tsc (strict check), ESLint (linting), and mypy/ruff (Python static analysis) in parallel. Fails immediately to skip downstream AI API calls and save tokens.";
    case 2:
      return "[Commit Approval] Only commits that pass all local static checks and local AI pre-check are permitted. Developers proceed confident that no bugs or type errors have slipped in.";
    case 3:
      return "[CI Automated Review] Upon pushing to remote and initiating a PR, Gate 2 starts. Commenting /request-review triggers deep AI analysis, creating review threads and deploying stagnation loop checks.";
    default:
      return "";
  }
}

export const PipelineDiagram: React.FC<{ t: TranslationResource; locale: Locale }> = ({
  t,
  locale,
}) => {
  const [activeStep, setActiveStep] = useState<number>(0);
  const steps = getDiagramSteps(t);

  return (
    <section
      id="diagram"
      className="bg-white dark:bg-gray-850/40 p-6 rounded-md border border-gray-200/50 dark:border-gray-800 flex flex-col gap-8 w-full max-w-6xl mx-auto"
    >
      <div className="flex flex-col gap-2 items-start text-left">
        <h2 className="text-2xl font-bold text-gray-900 dark:text-white">{t.diagramTitle}</h2>
        <p className="text-sm text-gray-500 dark:text-gray-400">{t.diagramDesc}</p>
      </div>

      <div className="relative py-4">
        <div className="absolute top-9 left-[10%] right-[10%] h-0.5 bg-gray-200 dark:bg-gray-800 z-0 hidden md:block"></div>

        <div className="relative z-10 grid grid-cols-1 md:grid-cols-4 gap-6">
          {steps.map((step) => {
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

      <div className="bg-gray-50 dark:bg-gray-900/60 p-6 rounded-md border border-primary/20 dark:border-primary/10 shadow-inner text-left transition-all duration-150">
        <h5 className="font-semibold text-sm text-primary mb-2.5 flex items-center gap-2">
          <span className="w-1.5 h-3 bg-primary rounded-full"></span>
          {steps[activeStep]?.title ?? ""} — {locale === "ja" ? "技術的詳細" : "Technical Details"}
        </h5>
        <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed font-sans">
          {getStepDetail(locale, activeStep)}
        </p>
      </div>
    </section>
  );
};

export const Simulator: React.FC<{ t: TranslationResource; locale: Locale }> = ({ t, locale }) => {
  const [simulateBug, setSimulateBug] = useState<boolean>(false);
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [terminalLogs, setTerminalLogs] = useState<LogMessage[]>([]);

  const isRunningRef = React.useRef<boolean>(isRunning);

  useEffect(() => {
    isRunningRef.current = isRunning;
  }, [isRunning]);

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
              ? "[precommit-review] AIコードレビューを実行中 (モデル: sonnet)..."
              : "[precommit-review] Running AI code review (Model: sonnet)...",
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
      timers.forEach((t2) => {
        clearTimeout(t2);
      });
    };
  }, [isRunning, simulateBug, locale]);

  return (
    <section
      id="demo"
      className="bg-white dark:bg-gray-850 p-6 rounded-md shadow-sm border border-gray-200/50 dark:border-gray-800 w-full max-w-6xl mx-auto"
    >
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8 items-start">
        <div className="flex flex-col gap-6 items-start text-left">
          <h2 className="text-2xl font-bold text-gray-900 dark:text-white">{t.demoTitle}</h2>
          <p className="text-sm text-gray-600 dark:text-gray-400 leading-relaxed">{t.demoDesc}</p>
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
                {log.type === "cmd" && <span className="text-teal-clarity mr-2 font-bold">$</span>}
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
  );
};

export const ConfigTabs: React.FC<{ t: TranslationResource; locale: Locale }> = ({ t, locale }) => {
  const [activeTab, setActiveTab] = useState<"yaml" | "eslint" | "circuit">("yaml");

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
# PR 差分の変更ファイルに対して静的解析 (ruff/mypy/semgrep 等) を実行し、
# エラーが 1 件でもあれば異常終了して AI レビューをスキップする。
import subprocess
import sys

def run(files):
    checks = [
        ["ruff", "check", *files],
        ["mypy", *files],
        ["semgrep", "--config", "ame_ai_review_system/.semgrep/rules.yml", "--error", *files],
    ]
    for cmd in checks:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            sys.exit(1)  # エラー検出時は異常終了し、AIレビューをスキップ`;
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
# Runs static analysis (ruff/mypy/semgrep, etc.) on the changed files and exits
# non-zero on any error to skip the AI review.
import subprocess
import sys

def run(files):
    checks = [
        ["ruff", "check", *files],
        ["mypy", *files],
        ["semgrep", "--config", "ame_ai_review_system/.semgrep/rules.yml", "--error", *files],
    ]
    for cmd in checks:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            sys.exit(1)  # Fails early if static checks fail, skipping AI review`;
      }
    }
  };

  return (
    <section id="config" className="flex flex-col gap-8 w-full max-w-6xl mx-auto">
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
  );
};
