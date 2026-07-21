/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_GITHUB_URL: string | undefined;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
