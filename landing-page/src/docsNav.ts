import { type TranslationResource } from "./i18n";

export type DocPageId =
  | "overview"
  | "features"
  | "static-analysis"
  | "quickstart"
  | "gate1"
  | "gate2"
  | "demo"
  | "config-json"
  | "env-vars"
  | "config-examples"
  | "architecture"
  | "engines"
  | "troubleshooting";

export const DOC_PAGE_ORDER: DocPageId[] = [
  "overview",
  "features",
  "static-analysis",
  "quickstart",
  "gate1",
  "gate2",
  "demo",
  "config-json",
  "env-vars",
  "config-examples",
  "architecture",
  "engines",
  "troubleshooting",
];

export interface DocNavItem {
  id: DocPageId;
  label: string;
}

export interface DocNavCategory {
  id: string;
  label: string;
  items: DocNavItem[];
}

export function getDocNav(t: TranslationResource): DocNavCategory[] {
  return [
    {
      id: "getting-started",
      label: t.catGettingStarted,
      items: [
        { id: "overview", label: t.pageOverview },
        { id: "features", label: t.pageFeatures },
        { id: "static-analysis", label: t.pageStaticAnalysis },
      ],
    },
    {
      id: "usage",
      label: t.catUsage,
      items: [
        { id: "quickstart", label: t.pageQuickStart },
        { id: "gate1", label: t.pageGate1 },
        { id: "gate2", label: t.pageGate2 },
        { id: "demo", label: t.pageDemo },
      ],
    },
    {
      id: "configuration",
      label: t.catConfiguration,
      items: [
        { id: "config-json", label: t.pageConfigJson },
        { id: "env-vars", label: t.pageEnvVars },
        { id: "config-examples", label: t.pageConfigExamples },
      ],
    },
    {
      id: "architecture",
      label: t.catArchitecture,
      items: [
        { id: "architecture", label: t.pageArchitecture },
        { id: "engines", label: t.pageEngines },
      ],
    },
    {
      id: "support",
      label: t.catSupport,
      items: [{ id: "troubleshooting", label: t.pageTroubleshooting }],
    },
  ];
}
