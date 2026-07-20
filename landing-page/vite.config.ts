import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import type { UserConfig } from "vite";
import type { InlineConfig } from "vitest/node";

interface ViteConfig extends UserConfig {
  test?: InlineConfig;
}

const config: ViteConfig = {
  plugins: [tailwindcss(), react()],
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: "./src/setupTests.ts",
  },
};

// https://vite.dev/config/
export default defineConfig(config);
