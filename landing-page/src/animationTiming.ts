// exit アニメーションの所要時間は index.css の CSS 変数と同一ソースで参照する
function cssVarMs(name: string, fallback: number): number {
  if (typeof window === "undefined") return fallback;
  const raw = window.getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const m = /^(\d+(?:\.\d+)?)ms$/.exec(raw);
  return m ? Number(m[1]) : fallback;
}

export const DRAWER_EXIT_MS = cssVarMs("--drawer-exit-ms", 300);
export const SETTINGS_EXIT_MS = cssVarMs("--settings-exit-ms", 150);
