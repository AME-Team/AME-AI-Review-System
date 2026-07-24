import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import type { UserConfig } from "vite";
import type { InlineConfig } from "vitest/node";

interface ViteConfig extends UserConfig {
  test?: InlineConfig;
}

// GitHub Pages のプロジェクトサイト (https://tarminjapan.github.io/AME-AI-Review-System/)
// にデプロイするため、本番ビルド (vite build) 時は base path にリポジトリ名を付与する。
// 開発サーバー (vite dev) とテスト (vitest) ではルート "/" を使用する。
const config = ({ command }: { command: string }): ViteConfig => ({
  plugins: [tailwindcss(), react()],
  base: command === "build" ? "/AME-AI-Review-System/" : "/",
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: "./src/setupTests.ts",
  },
});

// https://vite.dev/config/
export default defineConfig(config);
