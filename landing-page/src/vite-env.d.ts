/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_GITEA_URL: string | undefined;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
