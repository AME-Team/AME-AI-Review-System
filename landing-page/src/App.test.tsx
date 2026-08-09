import { render, screen, fireEvent, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import App from "./App";

const openPage = (label: string): void => {
  const matches = screen.getAllByRole("button", { name: label });
  if (matches[0]) {
    fireEvent.click(matches[0]);
  }
};

describe("App Component", () => {
  beforeEach(() => {
    localStorage.clear();
    window.location.hash = "";
  });

  it("renders the Japanese titles and documentation navigation", () => {
    render(<App />);
    expect(screen.getAllByText(/AME AI Review/)[0]).toBeInTheDocument();
    expect(screen.getByText(/デュアルゲートAIコードレビュー/)).toBeInTheDocument();
    expect(screen.getByText(/厳格な静的解析とAIエージェント/)).toBeInTheDocument();
    expect(screen.getByText("ドキュメント")).toBeInTheDocument();
  });

  it("shows the current version badge", () => {
    render(<App />);
    expect(screen.getAllByText("v0.2.4").length).toBeGreaterThan(0);
  });

  it("renders the hero header image on the overview page", () => {
    render(<App />);
    expect(screen.getByRole("img", { name: "AME AI Review" })).toBeInTheDocument();
  });

  it("renders the static analysis suite section via sidebar navigation", () => {
    render(<App />);
    openPage("静的解析プリセット");
    expect(screen.getByRole("heading", { name: "静的解析プリセット" })).toBeInTheDocument();
    expect(screen.getByText("ruff (lint, ALL+preview)")).toBeInTheDocument();
    expect(screen.getByText("semgrep-custom (8 rules)")).toBeInTheDocument();
  });

  it("renders detailed documentation pages via sidebar navigation", () => {
    render(<App />);
    openPage("インストールと初期設定");
    expect(screen.getByRole("heading", { name: "インストールと初期設定" })).toBeInTheDocument();
    expect(screen.getAllByText(/ame-ai-reviewer init/).length).toBeGreaterThan(0);

    openPage("config.json");
    expect(screen.getByRole("heading", { name: "config.json" })).toBeInTheDocument();
    expect(screen.getByText("precommit_review_enabled")).toBeInTheDocument();
  });

  it("toggles the simulated bug checkbox on the demo page", () => {
    render(<App />);
    openPage("動作デモ");
    const checkbox = screen.getByLabelText(
      "高重要度のバグコードをシミュレートする (AIレビューでの指摘を擬似発生)"
    );
    expect(checkbox).not.toBeChecked();
    fireEvent.click(checkbox);
    expect(checkbox).toBeChecked();
  });

  it("runs the simulator sequence successfully", () => {
    vi.useFakeTimers();
    render(<App />);
    openPage("動作デモ");

    // Initial logs check
    expect(
      screen.getByText("--- AME AI Review System インタラクティブ・シミュレーター ---")
    ).toBeInTheDocument();

    const runBtn = screen.getByRole("button", { name: "コミット検証を実行" });
    fireEvent.click(runBtn);

    // After clicking, verify initial logs are printed
    expect(screen.getByText("git add .")).toBeInTheDocument();
    expect(
      screen.getByText(
        "検証対象ファイルをステージング中: landing-page/src/App.tsx, pyproject.toml, README.md"
      )
    ).toBeInTheDocument();

    // Fast-forward through timers
    act(() => {
      vi.advanceTimersByTime(1000); // pre-commit run
    });
    expect(screen.getByText("pre-commit run")).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(1000); // static precheck
    });
    expect(screen.getByText("[static-precheck] 静的解析を実行中...")).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(6000); // remaining steps to complete
    });
    expect(
      screen.getByText("[git] 1ファイル変更、24行挿入(+)。コミットが成功しました！")
    ).toBeInTheDocument();

    vi.useRealTimers();
  });

  it("runs the simulator sequence with simulated bug and blocks commit", () => {
    vi.useFakeTimers();
    render(<App />);
    openPage("動作デモ");

    const checkbox = screen.getByLabelText(
      "高重要度のバグコードをシミュレートする (AIレビューでの指摘を擬似発生)"
    );
    fireEvent.click(checkbox);

    const runBtn = screen.getByRole("button", { name: "コミット検証を実行" });
    fireEvent.click(runBtn);

    // Fast-forward through timers
    act(() => {
      vi.advanceTimersByTime(8000);
    });
    expect(screen.getByText(/コミットがブロックされました。/)).toBeInTheDocument();

    vi.useRealTimers();
  });

  it("opens and closes the mobile sidebar drawer with Escape", () => {
    render(<App />);
    const menuBtn = screen.getByRole("button", { name: "メニューを開く" });
    fireEvent.click(menuBtn);
    const dialog = screen.getByRole("dialog", { name: "ドキュメント" });
    expect(dialog).toBeInTheDocument();
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("changes theme mode setting (light/dark/system)", () => {
    render(<App />);
    const settingsBtn = screen.getByRole("button", { name: "表示設定" });
    fireEvent.click(settingsBtn);

    expect(screen.getByText("テーマ (Theme)")).toBeInTheDocument();
    const lightBtn = screen.getByRole("button", { name: "ライト" });
    fireEvent.click(lightBtn);

    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(document.documentElement).not.toHaveClass("dark");

    const darkBtn = screen.getByRole("button", { name: "ダーク" });
    fireEvent.click(darkBtn);

    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(document.documentElement).toHaveClass("dark");
  });
});
