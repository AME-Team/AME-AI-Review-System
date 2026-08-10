import React, { useState, useEffect, useLayoutEffect, useRef } from "react";
import { translations, type TranslationResource, type Locale } from "./i18n";
import { type FontStyle } from "./assets/headerImage";
import { DocPage } from "./docs";
import { getDocNav, DOC_PAGE_ORDER, type DocPageId } from "./docsNav";

type PrimaryColor = "blue" | "green" | "orange" | "indigo" | "teal";
type ThemeMode = "light" | "dark" | "system";

interface AppSettings {
  locale: Locale;
  fontStyle: FontStyle;
  primaryColor: PrimaryColor;
  theme: ThemeMode;
}

function loadSavedSettings(): AppSettings {
  const defaults: AppSettings = {
    locale: "ja",
    fontStyle: "sans",
    primaryColor: "blue",
    theme: "system",
  };
  try {
    const saved = localStorage.getItem("app_settings");
    if (saved === null) return defaults;
    const parsed = JSON.parse(saved) as {
      locale?: unknown;
      fontStyle?: unknown;
      primaryColor?: unknown;
      theme?: unknown;
    };
    const validLocales: Locale[] = ["ja", "en"];
    const validFonts: FontStyle[] = ["sans", "serif"];
    const validColors: PrimaryColor[] = ["blue", "green", "orange", "indigo", "teal"];
    const validThemes: ThemeMode[] = ["light", "dark", "system"];
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
      theme: validThemes.includes(parsed.theme as ThemeMode)
        ? (parsed.theme as ThemeMode)
        : defaults.theme,
    };
  } catch (e) {
    console.warn("Failed to parse app_settings, using defaults:", e);
    return defaults;
  }
}

function parseHash(): DocPageId | null {
  if (typeof window === "undefined") return null;
  const m = /^#\/docs\/([a-z0-9-]+)/.exec(window.location.hash);
  const id = m?.[1];
  if (id !== undefined && (DOC_PAGE_ORDER as string[]).includes(id)) {
    return id as DocPageId;
  }
  return null;
}

function getPageLabel(t: TranslationResource, id: DocPageId): { category: string; label: string } {
  for (const cat of getDocNav(t)) {
    const item = cat.items.find((i) => i.id === id);
    if (item) {
      return { category: cat.label, label: item.label };
    }
  }
  return { category: "", label: id };
}

import { DRAWER_EXIT_MS, SETTINGS_EXIT_MS } from "./animationTiming";

// 開閉の mount → visible → unmount と終了所要時間を 1 箇所で管理し、CSS とのズレを防ぐ
function useOpenAnimation(open: boolean, exitMs: number): { rendered: boolean; visible: boolean } {
  const [rendered, setRendered] = useState<boolean>(false);
  const [visible, setVisible] = useState<boolean>(false);

  useEffect(() => {
    if (open) {
      setRendered(true);
    }
  }, [open]);

  useEffect(() => {
    if (rendered) {
      setVisible(open);
    }
  }, [rendered, open]);

  useEffect(() => {
    if (!open && rendered) {
      const t = setTimeout(() => {
        setRendered(false);
      }, exitMs);
      return (): void => {
        clearTimeout(t);
      };
    }
  }, [open, rendered, exitMs]);

  return { rendered, visible };
}

export default function App(): React.JSX.Element {
  const [settings, setSettings] = useState<AppSettings>(loadSavedSettings);
  const [showSettings, setShowSettings] = useState<boolean>(false);
  const [sidebarOpen, setSidebarOpen] = useState<boolean>(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState<boolean>(false);
  const [isDesktop, setIsDesktop] = useState<boolean>(
    () => typeof window !== "undefined" && window.matchMedia("(min-width: 1024px)").matches
  );
  const [activePage, setActivePage] = useState<DocPageId>(() => parseHash() ?? "overview");
  const drawer = useOpenAnimation(sidebarOpen, DRAWER_EXIT_MS);
  const settingsDropdown = useOpenAnimation(showSettings, SETTINGS_EXIT_MS);

  const { locale, fontStyle, primaryColor, theme } = settings;

  const settingsRef = useRef<HTMLDivElement>(null);
  const docPageRef = useRef<HTMLDivElement>(null);
  const isFirstPageRender = useRef<boolean>(true);

  const navigate = (id: DocPageId): void => {
    setActivePage(id);
    setSidebarOpen(false);
    if (typeof window !== "undefined") {
      window.location.hash = `/docs/${id}`;
      try {
        window.scrollTo({ top: 0 });
      } catch {
        // jsdom and some environments do not implement window.scrollTo
      }
    }
  };

  // Support browser back/forward through hash changes
  useEffect(() => {
    const onHashChange = (): void => {
      const id = parseHash();
      setActivePage(id ?? "overview");
    };
    window.addEventListener("hashchange", onHashChange);
    return (): void => {
      window.removeEventListener("hashchange", onHashChange);
    };
  }, []);

  // Focus management for the mobile sidebar drawer (a11y)
  const sidebarToggleRef = useRef<HTMLButtonElement>(null);
  const mobileDrawerRef = useRef<HTMLDivElement>(null);
  const wasDrawerOpenRef = useRef<boolean>(false);

  useEffect(() => {
    if (drawer.visible) {
      wasDrawerOpenRef.current = true;
      const firstButton = mobileDrawerRef.current?.querySelector<HTMLButtonElement>("button");
      firstButton?.focus();
    } else if (wasDrawerOpenRef.current) {
      wasDrawerOpenRef.current = false;
      sidebarToggleRef.current?.focus();
    }
  }, [drawer.visible]);

  const handleDrawerKeyDown = (e: React.KeyboardEvent<HTMLDivElement>): void => {
    if (e.key === "Escape") {
      setSidebarOpen(false);
      return;
    }
    if (e.key !== "Tab") return;
    const container = mobileDrawerRef.current;
    if (!container) return;
    const focusables = Array.from(
      container.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])'
      )
    );
    if (focusables.length === 0) return;
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    if (first === undefined || last === undefined) return;
    const active = document.activeElement;
    const activeInside = active !== null && container.contains(active);
    if (e.shiftKey) {
      if (active === first || !activeInside) {
        e.preventDefault();
        last.focus();
      }
    } else if (active === last || !activeInside) {
      e.preventDefault();
      first.focus();
    }
  };

  // Track desktop viewport so the sidebar toggle switches between
  // the desktop collapse and the mobile drawer behavior
  useEffect(() => {
    const mq = window.matchMedia("(min-width: 1024px)");
    const update = (): void => {
      const matches = mq.matches;
      setIsDesktop(matches);
      if (matches) {
        setSidebarOpen(false);
      }
    };
    update();
    mq.addEventListener("change", update);
    return (): void => {
      mq.removeEventListener("change", update);
    };
  }, []);

  // Re-trigger the page transition animation on navigation without remounting the
  // DocPage subtree (preserves its internal state). The first render is skipped so
  // the animation never overlaps with the drawer opening on the initial paint.
  useLayoutEffect(() => {
    if (isFirstPageRender.current) {
      isFirstPageRender.current = false;
      return;
    }
    const el = docPageRef.current;
    if (el === null) return;
    el.classList.remove("doc-page-enter");
    void el.getBoundingClientRect();
    el.classList.add("doc-page-enter");
  }, [activePage]);

  const toggleSidebar = (): void => {
    if (isDesktop) {
      setSidebarCollapsed((prev) => !prev);
    } else {
      setSidebarOpen((prev) => !prev);
    }
  };

  // Sync settings with DOM attributes and localStorage
  useEffect(() => {
    document.documentElement.setAttribute("data-locale", locale);
    document.documentElement.setAttribute("data-font-style", fontStyle);
    document.documentElement.setAttribute("data-theme-color", primaryColor);
    document.documentElement.setAttribute("data-theme", theme);

    const applyTheme = (): void => {
      const supportsMatchMedia =
        typeof window !== "undefined" && typeof window.matchMedia === "function";
      const isDark =
        theme === "dark" ||
        (theme === "system" &&
          supportsMatchMedia &&
          window.matchMedia("(prefers-color-scheme: dark)").matches);

      if (isDark) {
        document.documentElement.classList.add("dark");
      } else {
        document.documentElement.classList.remove("dark");
      }
    };

    applyTheme();

    localStorage.setItem(
      "app_settings",
      JSON.stringify({ locale, fontStyle, primaryColor, theme })
    );

    if (
      theme === "system" &&
      typeof window !== "undefined" &&
      typeof window.matchMedia === "function"
    ) {
      const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
      const handleChange = (): void => {
        applyTheme();
      };
      mediaQuery.addEventListener("change", handleChange);
      return (): void => {
        mediaQuery.removeEventListener("change", handleChange);
      };
    }
  }, [locale, fontStyle, primaryColor, theme]);

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

  const t = translations[locale];
  const nav = getDocNav(t);

  const currentIdx = DOC_PAGE_ORDER.indexOf(activePage);
  const prevPage = currentIdx > 0 ? DOC_PAGE_ORDER[currentIdx - 1] : null;
  const nextPage = currentIdx < DOC_PAGE_ORDER.length - 1 ? DOC_PAGE_ORDER[currentIdx + 1] : null;
  const currentLabel = getPageLabel(t, activePage);

  const sidebarIconPath = isDesktop
    ? sidebarCollapsed
      ? "M9 5l7 7-7 7"
      : "M15 19l-7-7 7-7"
    : sidebarOpen
      ? "M6 18L18 6M6 6l12 12"
      : "M4 6h16M4 12h16M4 18h16";

  const renderNavItems = (): React.ReactNode => (
    <nav className="flex flex-col gap-6" aria-label={t.sidebarTitle}>
      {nav.map((cat) => (
        <div key={cat.id} className="flex flex-col gap-1.5">
          <div className="text-[11px] font-bold uppercase tracking-wider text-gray-400 dark:text-gray-500">
            {cat.label}
          </div>
          <div className="flex flex-col gap-0.5">
            {cat.items.map((item) => {
              const isActive = activePage === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => {
                    navigate(item.id);
                  }}
                  aria-current={isActive ? "page" : undefined}
                  className={`text-left text-sm px-3 py-1.5 rounded-md transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-primary focus-visible:outline-none ${
                    isActive
                      ? "bg-primary/10 text-primary font-semibold"
                      : "text-gray-500 dark:text-gray-400 hover:text-primary dark:hover:text-primary hover:bg-gray-100 dark:hover:bg-gray-800"
                  }`}
                >
                  {item.label}
                </button>
              );
            })}
          </div>
        </div>
      ))}
    </nav>
  );

  return (
    <div className="min-h-screen bg-gray-50 text-gray-600 dark:bg-gray-900 dark:text-gray-400 font-sans antialiased">
      {/* Navigation Header */}
      <header className="sticky top-0 z-50 bg-white/80 dark:bg-gray-900/80 backdrop-blur-md border-b border-gray-200/50 dark:border-gray-800/50 transition-colors duration-150">
        <div className="max-w-[1400px] mx-auto px-4 h-16 flex items-center justify-between relative">
          <div className="flex items-center gap-3 min-w-0">
            <button
              type="button"
              ref={sidebarToggleRef}
              onClick={toggleSidebar}
              aria-label={
                isDesktop
                  ? sidebarCollapsed
                    ? t.sidebarOpen
                    : t.sidebarClose
                  : sidebarOpen
                    ? t.menuClose
                    : t.menuOpen
              }
              aria-expanded={isDesktop ? !sidebarCollapsed : sidebarOpen}
              aria-controls={isDesktop ? "desktop-sidebar" : undefined}
              className="p-2 rounded-md hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-500 dark:text-gray-400 transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-primary focus-visible:outline-none"
            >
              <svg
                className="w-5 h-5"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" d={sidebarIconPath} />
              </svg>
            </button>
            <button
              type="button"
              onClick={() => {
                navigate("overview");
              }}
              className="flex items-center gap-3 min-w-0 focus-visible:ring-2 focus-visible:ring-primary focus-visible:outline-none rounded-md"
            >
              <div className="w-8 h-8 bg-primary rounded-md shadow-sm flex items-center justify-center text-white font-bold text-sm shrink-0">
                AR
              </div>
              <span className="text-lg font-bold text-gray-900 dark:text-white tracking-wide truncate">
                {t.title}
              </span>
            </button>
          </div>

          <div className="flex items-center gap-3">
            <span className="hidden md:inline-flex items-center gap-1.5 text-xs font-semibold text-primary bg-primary/10 border border-primary/20 px-2.5 py-1 rounded-md">
              <span className="w-1.5 h-1.5 bg-primary rounded-full"></span>
              {t.badgeVersion}
            </span>

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
              {settingsDropdown.rendered && (
                <div
                  aria-hidden={!settingsDropdown.visible}
                  inert={!settingsDropdown.visible}
                  className={`absolute right-0 mt-2 w-80 bg-white dark:bg-gray-850 border border-gray-200 dark:border-gray-800 rounded-md shadow-md p-4 flex flex-col gap-4 z-50 transition-all duration-[var(--settings-exit-ms)] ease-out ${settingsDropdown.visible ? "opacity-100 translate-y-0" : "pointer-events-none opacity-0 -translate-y-1"}`}
                >
                  <h3 className="font-bold text-sm text-gray-900 dark:text-white border-b border-gray-100 dark:border-gray-800 pb-2">
                    {t.settingsTitle}
                  </h3>

                  {/* Theme Mode Selector */}
                  <div className="flex flex-col gap-1.5">
                    <label className="text-xs font-semibold text-gray-500 dark:text-gray-400">
                      {t.settingsTheme}
                    </label>
                    <div className="grid grid-cols-3 gap-1.5 bg-gray-50 dark:bg-gray-900 p-1 rounded-md">
                      <button
                        type="button"
                        onClick={() => {
                          setSettings((prev) => ({ ...prev, theme: "light" }));
                        }}
                        className={`text-xs py-1.5 rounded-md font-medium transition-all ${theme === "light" ? "bg-white dark:bg-gray-800 text-primary shadow-sm" : "text-gray-500 hover:text-gray-900 dark:hover:text-white"}`}
                      >
                        {t.settingsThemeLight}
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setSettings((prev) => ({ ...prev, theme: "dark" }));
                        }}
                        className={`text-xs py-1.5 rounded-md font-medium transition-all ${theme === "dark" ? "bg-white dark:bg-gray-800 text-primary shadow-sm" : "text-gray-500 hover:text-gray-900 dark:hover:text-white"}`}
                      >
                        {t.settingsThemeDark}
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setSettings((prev) => ({ ...prev, theme: "system" }));
                        }}
                        className={`text-xs py-1.5 rounded-md font-medium transition-all ${theme === "system" ? "bg-white dark:bg-gray-800 text-primary shadow-sm" : "text-gray-500 hover:text-gray-900 dark:hover:text-white"}`}
                      >
                        {t.settingsThemeSystem}
                      </button>
                    </div>
                  </div>

                  {/* Language Selector */}
                  <div className="flex flex-col gap-1.5">
                    <label className="text-xs font-semibold text-gray-500 dark:text-gray-400">
                      {t.settingsLang}
                    </label>
                    <div className="grid grid-cols-2 gap-2 bg-gray-50 dark:bg-gray-900 p-1 rounded-md">
                      <button
                        type="button"
                        onClick={() => {
                          setSettings((prev) => ({ ...prev, locale: "ja" }));
                        }}
                        className={`text-xs py-1.5 rounded-md font-medium transition-all ${locale === "ja" ? "bg-white dark:bg-gray-800 text-primary shadow-sm" : "text-gray-500 hover:text-gray-900 dark:hover:text-white"}`}
                      >
                        日本語
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setSettings((prev) => ({ ...prev, locale: "en" }));
                        }}
                        className={`text-xs py-1.5 rounded-md font-medium transition-all ${locale === "en" ? "bg-white dark:bg-gray-800 text-primary shadow-sm" : "text-gray-500 hover:text-gray-900 dark:hover:text-white"}`}
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

      <div className="flex">
        {/* Desktop Sidebar */}
        <aside
          id="desktop-sidebar"
          data-testid="desktop-sidebar"
          className={`hidden w-64 shrink-0 border-r border-gray-200/50 dark:border-gray-800/50 ${sidebarCollapsed ? "lg:hidden" : "lg:block"}`}
        >
          <div className="sticky top-16 max-h-[calc(100vh-4rem)] overflow-y-auto p-4">
            <div className="text-[11px] font-bold uppercase tracking-wider text-gray-400 dark:text-gray-500 mb-4">
              {t.sidebarTitle}
            </div>
            {renderNavItems()}
          </div>
        </aside>

        {/* Mobile Sidebar Drawer */}
        {drawer.rendered && (
          <div
            className="lg:hidden fixed inset-0 z-40"
            role="dialog"
            aria-modal="true"
            aria-label={t.sidebarTitle}
            aria-hidden={!drawer.visible}
            inert={!drawer.visible}
            ref={mobileDrawerRef}
            onKeyDown={handleDrawerKeyDown}
          >
            {/* パネル退出と同じ duration に揃え、退出後半にパネルだけが残って見えるチラつきを防ぐ */}
            <div
              className={`absolute inset-0 bg-black/40 transition-opacity duration-[var(--drawer-exit-ms)] ease-in-out ${drawer.visible ? "opacity-100" : "pointer-events-none opacity-0"}`}
              onClick={() => {
                setSidebarOpen(false);
              }}
            ></div>
            <div
              className={`absolute left-0 top-0 bottom-0 w-72 bg-white dark:bg-gray-900 shadow-xl overflow-y-auto p-4 pt-20 transition-transform duration-[var(--drawer-exit-ms)] ease-in-out ${drawer.visible ? "translate-x-0" : "-translate-x-full"}`}
            >
              <div className="text-[11px] font-bold uppercase tracking-wider text-gray-400 dark:text-gray-500 mb-4">
                {t.sidebarTitle}
              </div>
              {renderNavItems()}
            </div>
          </div>
        )}

        {/* Main Content */}
        <main className="flex-1 min-w-0">
          <div className="max-w-4xl mx-auto px-6 py-10 flex flex-col gap-10">
            <div className="flex flex-col gap-2">
              <div className="text-xs text-gray-400 dark:text-gray-500">
                {t.sidebarTitle} / {currentLabel.category} / {currentLabel.label}
              </div>
            </div>

            <div ref={docPageRef}>
              <DocPage
                id={activePage}
                t={t}
                locale={locale}
                fontStyle={fontStyle}
                onNavigate={navigate}
              />
            </div>

            {/* Prev / Next navigation */}
            <nav
              className="flex items-center justify-between gap-4 border-t border-gray-200/50 dark:border-gray-800/50 pt-6"
              aria-label="pagination"
            >
              {prevPage ? (
                <button
                  type="button"
                  onClick={() => {
                    navigate(prevPage);
                  }}
                  className="flex flex-col gap-1 items-start text-left px-4 py-3 rounded-md border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-850 hover:border-primary/50 transition-colors duration-150 max-w-[45%]"
                >
                  <span className="text-[11px] text-gray-400">← {t.pagePrev}</span>
                  <span className="text-sm font-semibold text-gray-900 dark:text-white">
                    {getPageLabel(t, prevPage).label}
                  </span>
                </button>
              ) : (
                <span></span>
              )}
              {nextPage ? (
                <button
                  type="button"
                  onClick={() => {
                    navigate(nextPage);
                  }}
                  className="flex flex-col gap-1 items-end text-right px-4 py-3 rounded-md border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-850 hover:border-primary/50 transition-colors duration-150 max-w-[45%]"
                >
                  <span className="text-[11px] text-gray-400">{t.pageNext} →</span>
                  <span className="text-sm font-semibold text-gray-900 dark:text-white">
                    {getPageLabel(t, nextPage).label}
                  </span>
                </button>
              ) : (
                <span></span>
              )}
            </nav>
          </div>
        </main>
      </div>

      <footer className="border-t border-gray-200/50 dark:border-gray-800/50 py-8 mt-12 transition-colors duration-150">
        <div className="max-w-[1400px] mx-auto px-6 flex flex-col md:flex-row items-center justify-between gap-4">
          <span className="text-sm font-bold text-gray-900 dark:text-white">
            AME-AI-Review-System
          </span>
          <div className="flex flex-col md:flex-row items-center gap-2 text-xs text-gray-500">
            <a
              href="https://github.com/tarminjapan/AME-AI-Review-System/blob/main/ame_ai_review_system/docs/instructions.md"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-primary transition-colors duration-150"
            >
              instructions.md
            </a>
            <span className="hidden md:inline">·</span>
            <a
              href="https://github.com/tarminjapan/AME-AI-Review-System/blob/main/ame_ai_review_system/docs/troubleshooting.md"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-primary transition-colors duration-150"
            >
              troubleshooting.md
            </a>
          </div>
          <p className="text-xs text-gray-500">© 2026 AME Team. All rights reserved.</p>
        </div>
      </footer>
    </div>
  );
}
