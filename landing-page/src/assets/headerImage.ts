export type Locale = "ja" | "en";
export type FontStyle = "sans" | "serif";

interface HeaderImageTexts {
  subtitle: string;
  badgeShiftLeft: string;
  badgeStaticTools: string;
  badgeLlmCost: string;
  gate1Title: string;
  stagedLabel: string;
  circuitTitle: string;
  circuitBlock: string;
  aiReviewTitle: string;
  commitPass: string;
  gate2Title: string;
  prComment: string;
  diffCheck: string;
  ciReviewTitle: string;
  diffEval: string;
  inlineFeedback: string;
  mergeReady: string;
}

const FONT_FAMILIES: Record<Locale, Record<FontStyle, string>> = {
  ja: {
    sans: "'Noto Sans JP', 'Hiragino Sans', 'Hiragino Kaku Gothic ProN', 'Meiryo', 'Yu Gothic', sans-serif",
    serif: "'Noto Serif JP', 'Yu Mincho', 'YuMincho', 'Hiragino Mincho ProN', serif",
  },
  en: {
    sans: "'Noto Sans', 'Helvetica Neue', Arial, sans-serif",
    serif: "'Noto Serif', 'Georgia', 'Times New Roman', serif",
  },
};

const TEXTS: Record<Locale, HeaderImageTexts> = {
  ja: {
    subtitle: "静的解析 Circuit Breaker × AIコードレビューによる二重品質ガード",
    badgeShiftLeft: "⚡ Shift-Left 検知",
    badgeStaticTools: "⚙️ 25+ 静的解析連携",
    badgeLlmCost: "🤖 LLM コスト最小化",
    gate1Title: "ローカル開発 (pre-commit)",
    stagedLabel: "Staged 変更",
    circuitTitle: "⚙️ 静的解析 (Circuit)",
    circuitBlock: "エラー時 AI 呼び出し前遮断",
    aiReviewTitle: "🤖 ローカル AI レビュー",
    commitPass: "Pass 時にコミット完了",
    gate2Title: "CI / CD 環境 (Pull Request)",
    prComment: "GitHub PR コメント",
    diffCheck: "全累積差分検証",
    ciReviewTitle: "🚀 CI AI レビュー",
    diffEval: "origin/main...HEAD 評価",
    inlineFeedback: "インライン指摘・対話返信",
    mergeReady: "マージ可能な高精度コード",
  },
  en: {
    subtitle: "Static Analysis Circuit Breaker × AI Code Review — Dual-Gate Quality Guard",
    badgeShiftLeft: "⚡ Shift-Left Check",
    badgeStaticTools: "⚙️ 25+ Static Tools",
    badgeLlmCost: "🤖 Min. LLM Cost",
    gate1Title: "Local Dev (pre-commit)",
    stagedLabel: "Staged Changes",
    circuitTitle: "⚙️ Circuit Check",
    circuitBlock: "Blocks AI call on error",
    aiReviewTitle: "🤖 Local AI Review",
    commitPass: "Commit on pass",
    gate2Title: "CI / CD Environment (PR)",
    prComment: "GitHub PR Comment",
    diffCheck: "Full diff check",
    ciReviewTitle: "🚀 CI AI Review",
    diffEval: "origin/main...HEAD diff",
    inlineFeedback: "Inline feedback & replies",
    mergeReady: "Merge-ready code",
  },
};

function escapeXmlText(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function escapeTexts(texts: HeaderImageTexts): HeaderImageTexts {
  const escaped = Object.fromEntries(
    Object.entries(texts).map(([key, value]) => [key, escapeXmlText(value as string)])
  ) as unknown as HeaderImageTexts;
  return escaped;
}

// Single source of truth for the hero banner's structure/colors; only the TEXTS
// table above varies per locale/fontStyle. Selectors are scoped to #${rootId} because this
// markup is injected via dangerouslySetInnerHTML directly into the page DOM (not
// a sandboxed <img>), so unscoped `text {...}` rules would otherwise leak onto
// any other SVG <text> on the page (e.g. the ReactFlow diagram below).
export function getHeaderImageSvg(locale: Locale = "ja", fontStyle: FontStyle = "sans"): string {
  const t = escapeTexts(TEXTS[locale]);
  const fontFamily = FONT_FAMILIES[locale][fontStyle];
  const rootId = `header-image-${locale}-${fontStyle}`;

  return `<svg id="${rootId}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 420" width="100%" height="100%" style="background-color: #0b0f19;">
  <title>AME AI Review</title>
  <defs>
    <style>
      #${rootId} text {
        font-family: ${fontFamily};
      }

      #${rootId} .brand-title {
        font-family: ${fontFamily};
        font-weight: 900;
        font-size: 44px;
        letter-spacing: -0.5px;
      }

      #${rootId} .brand-subtitle {
        font-family: ${fontFamily};
        font-weight: 500;
        font-size: 16px;
        fill: #94a3b8;
      }

      #${rootId} .badge-label {
        font-family: ${fontFamily};
        font-weight: 700;
        font-size: 11px;
        letter-spacing: 0.5px;
      }

      #${rootId} .code-font {
        font-family: 'Noto Sans Mono', 'Consolas', 'Courier New', monospace;
      }
    </style>

    <linearGradient id="${rootId}-bgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#0b0f19"/>
      <stop offset="50%" stop-color="#0f172a"/>
      <stop offset="100%" stop-color="#070a12"/>
    </linearGradient>

    <radialGradient id="${rootId}-cyanGlow" cx="15%" cy="25%" r="55%">
      <stop offset="0%" stop-color="#0284c7" stop-opacity="0.25"/>
      <stop offset="100%" stop-color="#0b0f19" stop-opacity="0"/>
    </radialGradient>

    <radialGradient id="${rootId}-purpleGlow" cx="85%" cy="75%" r="55%">
      <stop offset="0%" stop-color="#7e22ce" stop-opacity="0.2"/>
      <stop offset="100%" stop-color="#0b0f19" stop-opacity="0"/>
    </radialGradient>

    <linearGradient id="${rootId}-titleGrad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#38bdf8"/>
      <stop offset="50%" stop-color="#818cf8"/>
      <stop offset="100%" stop-color="#c084fc"/>
    </linearGradient>

    <linearGradient id="${rootId}-gate1Grad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#1e293b" stop-opacity="0.8"/>
      <stop offset="100%" stop-color="#0f172a" stop-opacity="0.9"/>
    </linearGradient>

    <linearGradient id="${rootId}-gate2Grad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#2e1065" stop-opacity="0.6"/>
      <stop offset="100%" stop-color="#0f172a" stop-opacity="0.9"/>
    </linearGradient>

    <filter id="${rootId}-shadow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="12" stdDeviation="16" flood-color="#000000" flood-opacity="0.6"/>
    </filter>
  </defs>

  <rect width="100%" height="100%" fill="url(#${rootId}-bgGrad)"/>
  <rect width="100%" height="100%" fill="url(#${rootId}-cyanGlow)"/>
  <rect width="100%" height="100%" fill="url(#${rootId}-purpleGlow)"/>

  <g opacity="0.05" stroke="#ffffff" stroke-width="1">
    <path d="M 0 60 L 1200 60 M 0 120 L 1200 120 M 0 180 L 1200 180 M 0 240 L 1200 240 M 0 300 L 1200 300 M 0 360 L 1200 360"/>
    <path d="M 100 0 L 100 420 M 200 0 L 200 420 M 300 0 L 300 420 M 400 0 L 400 420 M 500 0 L 500 420 M 600 0 L 600 420 M 700 0 L 700 420 M 800 0 L 800 420 M 900 0 L 900 420 M 1000 0 L 1000 420 M 1100 0 L 1100 420"/>
  </g>

  <path d="M 50 20 L 200 20 L 240 60" fill="none" stroke="#0284c7" stroke-width="1.5" opacity="0.3"/>
  <circle cx="50" cy="20" r="3" fill="#38bdf8"/>
  <path d="M 1150 400 L 1000 400 L 960 360" fill="none" stroke="#7e22ce" stroke-width="1.5" opacity="0.3"/>
  <circle cx="1150" cy="400" r="3" fill="#c084fc"/>

  <g transform="translate(60, 48)">
    <rect x="0" y="0" width="225" height="26" rx="13" fill="#1e293b" stroke="#0369a1" stroke-width="1"/>
    <circle cx="14" cy="13" r="4" fill="#38bdf8"/>
    <text x="26" y="17" class="badge-label" fill="#38bdf8">DUAL-GATE QUALITY ENGINE</text>

    <text x="0" y="66" class="brand-title">
      <tspan fill="url(#${rootId}-titleGrad)">AME AI Review System</tspan>
    </text>

    <text x="0" y="96" class="brand-subtitle" fill="#94a3b8">
      ${t.subtitle}
    </text>

    <g transform="translate(0, 114)">
      <rect x="0" y="0" width="130" height="24" rx="6" fill="#0f172a" stroke="#334155" stroke-width="1"/>
      <text x="12" y="16" font-size="11" font-weight="700" fill="#38bdf8">${t.badgeShiftLeft}</text>

      <rect x="140" y="0" width="150" height="24" rx="6" fill="#0f172a" stroke="#334155" stroke-width="1"/>
      <text x="152" y="16" font-size="11" font-weight="700" fill="#f59e0b">${t.badgeStaticTools}</text>

      <rect x="300" y="0" width="140" height="24" rx="6" fill="#0f172a" stroke="#334155" stroke-width="1"/>
      <text x="312" y="16" font-size="11" font-weight="700" fill="#c084fc">${t.badgeLlmCost}</text>
    </g>
  </g>

  <g transform="translate(60, 205)" filter="url(#${rootId}-shadow)">
    <g transform="translate(0, 0)">
      <rect x="0" y="0" width="510" height="150" rx="14" fill="url(#${rootId}-gate1Grad)" stroke="#0284c7" stroke-width="1.5" stroke-opacity="0.8"/>

      <rect x="16" y="14" width="68" height="20" rx="10" fill="#0369a1"/>
      <text x="50" y="28" font-size="10" font-weight="700" fill="#ffffff" text-anchor="middle">GATE 1</text>
      <text x="94" y="29" font-size="14" font-weight="700" fill="#f8fafc">${t.gate1Title}</text>

      <g transform="translate(16, 48)">
        <rect x="0" y="0" width="105" height="78" rx="8" fill="#0f172a" stroke="#334155" stroke-width="1"/>
        <text x="12" y="24" font-size="12" font-weight="700" fill="#f8fafc">git commit</text>
        <text x="12" y="44" font-size="10" fill="#94a3b8">${t.stagedLabel}</text>
        <rect x="12" y="52" width="60" height="16" rx="4" fill="#1e293b"/>
        <text x="42" y="63" font-size="9" fill="#38bdf8" class="code-font" text-anchor="middle">Git Hook</text>
      </g>

      <path d="M 121 87 L 138 87" stroke="#38bdf8" stroke-width="2"/>
      <polygon points="138,82 145,87 138,92" fill="#38bdf8"/>

      <g transform="translate(145, 48)">
        <rect x="0" y="0" width="165" height="78" rx="8" fill="#0f172a" stroke="#f59e0b" stroke-width="1.2"/>
        <text x="12" y="22" font-size="11" font-weight="700" fill="#fef3c7">${t.circuitTitle}</text>
        <text x="12" y="38" font-size="9" fill="#94a3b8">ruff / mypy / eslint / semgrep</text>

        <rect x="12" y="48" width="141" height="20" rx="4" fill="#451a03"/>
        <text x="82" y="61" font-size="9" font-weight="700" fill="#fde047" text-anchor="middle">${t.circuitBlock}</text>
      </g>

      <path d="M 310 87 L 327 87" stroke="#34d399" stroke-width="2"/>
      <polygon points="327,82 334,87 327,92" fill="#34d399"/>

      <g transform="translate(334, 48)">
        <rect x="0" y="0" width="160" height="78" rx="8" fill="#0f172a" stroke="#818cf8" stroke-width="1.2"/>
        <text x="12" y="22" font-size="11" font-weight="700" fill="#e0e7ff">${t.aiReviewTitle}</text>
        <text x="12" y="38" font-size="9" fill="#94a3b8">precommit_review.py</text>

        <rect x="12" y="48" width="136" height="20" rx="4" fill="#064e3b"/>
        <text x="80" y="61" font-size="9" font-weight="700" fill="#6ee7b7" text-anchor="middle">${t.commitPass}</text>
      </g>
    </g>

    <g transform="translate(515, 65)">
      <path d="M 0 10 L 40 10" stroke="#38bdf8" stroke-width="2.5" stroke-dasharray="4"/>
      <polygon points="40,5 48,10 40,15" fill="#38bdf8"/>
      <text x="22" y="0" font-size="10" font-weight="700" fill="#38bdf8" text-anchor="middle">git push</text>
    </g>

    <g transform="translate(570, 0)">
      <rect x="0" y="0" width="510" height="150" rx="14" fill="url(#${rootId}-gate2Grad)" stroke="#a855f7" stroke-width="1.5" stroke-opacity="0.8"/>

      <rect x="16" y="14" width="68" height="20" rx="10" fill="#6b21a8"/>
      <text x="50" y="28" font-size="10" font-weight="700" fill="#ffffff" text-anchor="middle">GATE 2</text>
      <text x="94" y="29" font-size="14" font-weight="700" fill="#f8fafc">${t.gate2Title}</text>

      <g transform="translate(16, 48)">
        <rect x="0" y="0" width="130" height="78" rx="8" fill="#0f172a" stroke="#334155" stroke-width="1"/>
        <rect x="10" y="12" width="110" height="20" rx="4" fill="#1e293b"/>
        <text x="65" y="26" font-size="10" font-weight="700" fill="#a5f3fc" class="code-font" text-anchor="middle">/request-review</text>
        <text x="10" y="48" font-size="9" fill="#94a3b8">${t.prComment}</text>
        <text x="10" y="62" font-size="9" fill="#94a3b8">${t.diffCheck}</text>
      </g>

      <path d="M 146 87 L 163 87" stroke="#c084fc" stroke-width="2"/>
      <polygon points="163,82 170,87 163,92" fill="#c084fc"/>

      <g transform="translate(170, 48)">
        <rect x="0" y="0" width="170" height="78" rx="8" fill="#0f172a" stroke="#c084fc" stroke-width="1.2"/>
        <text x="12" y="22" font-size="11" font-weight="700" fill="#f3e8ff">${t.ciReviewTitle}</text>
        <text x="12" y="38" font-size="9" fill="#94a3b8">${t.diffEval}</text>

        <rect x="12" y="48" width="146" height="20" rx="4" fill="#3b0764"/>
        <text x="85" y="61" font-size="9" font-weight="700" fill="#e9d5ff" text-anchor="middle">${t.inlineFeedback}</text>
      </g>

      <path d="M 340 87 L 357 87" stroke="#34d399" stroke-width="2"/>
      <polygon points="357,82 364,87 357,92" fill="#34d399"/>

      <g transform="translate(364, 48)">
        <rect x="0" y="0" width="130" height="78" rx="8" fill="#0f172a" stroke="#34d399" stroke-width="1.2"/>
        <circle cx="28" cy="28" r="12" fill="#10b981"/>
        <path d="M 22 28 L 26 33 L 34 22" fill="none" stroke="#ffffff" stroke-width="2.5" stroke-linecap="round"/>
        <text x="46" y="32" font-size="12" font-weight="700" fill="#ecfdf5">Approved</text>
        <text x="12" y="58" font-size="9" fill="#a7f3d0">${t.mergeReady}</text>
      </g>
    </g>
  </g>

  <g transform="translate(60, 380)">
    <line x1="0" y1="0" x2="1080" y2="0" stroke="#334155" stroke-width="1" opacity="0.6"/>
    <text x="0" y="18" font-size="11" font-weight="500" fill="#64748b">
      AME-AI-Review-System — Portable IP Asset for High-Quality Code Management
    </text>
    <text x="1080" y="18" font-size="11" font-weight="700" fill="#38bdf8" text-anchor="end">
      Claude Code / OpenCode / Antigravity CLI Ready
    </text>
  </g>
</svg>`;
}

// README.md / landing-page/README.md embed a static file (GitHub's Markdown image
// syntax) rather than this live template, so this generates that file's exact
// content — see scripts/generate-header-image.ts — keeping the two from drifting.
export function getStaticHeaderImageSvgFile(): string {
  const banner = `<!-- GENERATED FILE — do not edit by hand.
     Source of truth: src/assets/headerImage.ts (getStaticHeaderImageSvgFile).
     Regenerate with: npm run generate:header-image -->\n`;
  return `${banner}${getHeaderImageSvg("ja")}\n`;
}
