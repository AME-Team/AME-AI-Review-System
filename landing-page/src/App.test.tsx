import { render, screen, fireEvent, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import App from "./App";

describe("App Component", () => {
  beforeEach(() => {
    localStorage.clear();
  });
  it("renders the Japanese titles and navigation elements", () => {
    render(<App />);
    expect(screen.getAllByText(/AME AI Review/)[0]).toBeInTheDocument();
    expect(screen.getByText(/デュアルゲートAIコードレビュー/)).toBeInTheDocument();
    expect(screen.getByText(/超厳格な静的解析とAIエージェント/)).toBeInTheDocument();
  });

  it("toggles the simulated bug checkbox", () => {
    render(<App />);
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
});
