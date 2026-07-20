# ジョブ実行イメージ — CI ジョブが実際に走る環境 (ubuntu-latest label で参照される)。
# act_runner デーモン自体は docker-compose.yml の gitea/act_runner 公式イメージを使用。
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN useradd --create-home --shell /bin/bash gitea-runner \
  && mkdir -p /workspace && chown gitea-runner:gitea-runner /workspace

RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl ca-certificates xz-utils jq \
  && rm -rf /var/lib/apt/lists/*

ENV UV_INSTALL_DIR=/usr/local/bin \
    UV_PYTHON_INSTALL_DIR=/usr/local/share/uv-python

RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
  && uv python install 3.12 \
  && chmod -R a+rX /usr/local/share/uv-python

# Node.js — LTS 22 を使用する。claude-code@2.1.214 / opencode-ai@1.18.3 は
# Node 22 で動作確認済み。メジャーアップ時は互換性を再確認すること。
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
  && apt-get install -y nodejs && rm -rf /var/lib/apt/lists/*

# =============================================================================
# ビルド方針: 再現性とセキュリティのバランス
# =============================================================================
# - Node.js / claude-code / opencode-ai / headroom: バージョン固定（再現性優先）
# - shellcheck / actionlint / gitleaks: latest 取得 + フォールバック（セキュリティ優先）
#   CI/セキュリティツールは既知脆弱性回避のため最新版を優先する。
#   GitHub API rate limit (60 req/h 未認証) により latest 取得が失敗する場合は
#   FALLBACK 版を使用する。USE_LATEST=0 で latest 取得をスキップ可能。
# =============================================================================
# shellcheck / actionlint / gitleaks — ビルド時に GitHub Releases の latest を取得する。
# jq は apt-get で導入済み (line 11)。tag_name は "vX.Y.Z" 形式。
# shellcheck / actionlint: URL 側で "v" を付与する（例: v0.10.0）。
# gitleaks: アセット名に "v" なし（例: gitleaks_8.21.2_linux_x64.tar.gz）。
# 全ツール統一: sed で "v" を除去して VER を統一。
# フォールバック判定: API_RESPONSE が空、または tag_name が空/"null" の場合に FALLBACK を適用する。
# 各ステップ (curl / jq / sed) を分離し、エラー捕捉を明確化している。
RUN set -euo pipefail && \
    FALLBACK="0.10.0" && \
    USE_LATEST="${USE_LATEST:-1}" && \
    if [ "$USE_LATEST" = "1" ]; then \
      API_RESPONSE=$(curl -sf https://api.github.com/repos/koalaman/shellcheck/releases/latest || true) && \
      VER=$(echo "$API_RESPONSE" | jq -e -r '.tag_name' 2>/dev/null || true) && \
      if [ -z "$API_RESPONSE" ] || [ -z "$VER" ] || [ "$VER" = "null" ]; then VER="$FALLBACK" && echo "shellcheck: using fallback ${FALLBACK}" >&2; fi; \
    else \
      VER="$FALLBACK" && echo "shellcheck: USE_LATEST=0, using fallback ${FALLBACK}" >&2; \
    fi && \
    VER=$(echo "$VER" | sed 's/^v//') && \
    [ -n "$VER" ] || { echo "shellcheck: VER is empty" >&2; exit 1; } && \
    echo "shellcheck version: ${VER}" >&2 && \
    mkdir -p /tmp/sc && \
    curl -sSfL "https://github.com/koalaman/shellcheck/releases/download/v${VER}/shellcheck-v${VER}.linux.x86_64.tar.xz" | tar -xJ -C /tmp/sc && \
    mv /tmp/sc/shellcheck-v${VER}/shellcheck /usr/local/bin/ && \
    rm -rf /tmp/sc

RUN set -euo pipefail && \
    FALLBACK="1.7.7" && \
    USE_LATEST="${USE_LATEST:-1}" && \
    if [ "$USE_LATEST" = "1" ]; then \
      API_RESPONSE=$(curl -sf https://api.github.com/repos/rhysd/actionlint/releases/latest || true) && \
      VER=$(echo "$API_RESPONSE" | jq -e -r '.tag_name' 2>/dev/null || true) && \
      if [ -z "$API_RESPONSE" ] || [ -z "$VER" ] || [ "$VER" = "null" ]; then VER="$FALLBACK" && echo "actionlint: using fallback ${FALLBACK}" >&2; fi; \
    else \
      VER="$FALLBACK" && echo "actionlint: USE_LATEST=0, using fallback ${FALLBACK}" >&2; \
    fi && \
    VER=$(echo "$VER" | sed 's/^v//') && \
    [ -n "$VER" ] || { echo "actionlint: VER is empty" >&2; exit 1; } && \
    echo "actionlint version: ${VER}" >&2 && \
    mkdir -p /tmp/al && \
    curl -sSfL "https://github.com/rhysd/actionlint/releases/download/v${VER}/actionlint_${VER}_linux_amd64.tar.gz" | tar -xz -C /tmp/al && \
    mv /tmp/al/actionlint /usr/local/bin/ && \
    rm -rf /tmp/al

RUN set -euo pipefail && \
    FALLBACK="8.21.2" && \
    USE_LATEST="${USE_LATEST:-1}" && \
    if [ "$USE_LATEST" = "1" ]; then \
      API_RESPONSE=$(curl -sf https://api.github.com/repos/gitleaks/gitleaks/releases/latest || true) && \
      VER=$(echo "$API_RESPONSE" | jq -e -r '.tag_name' 2>/dev/null || true) && \
      if [ -z "$API_RESPONSE" ] || [ -z "$VER" ] || [ "$VER" = "null" ]; then VER="$FALLBACK" && echo "gitleaks: using fallback ${FALLBACK}" >&2; fi; \
    else \
      VER="$FALLBACK" && echo "gitleaks: USE_LATEST=0, using fallback ${FALLBACK}" >&2; \
    fi && \
    VER=$(echo "$VER" | sed 's/^v//') && \
    [ -n "$VER" ] || { echo "gitleaks: VER is empty" >&2; exit 1; } && \
    echo "gitleaks version: ${VER}" >&2 && \
    mkdir -p /tmp/gl && \
    curl -sSfL "https://github.com/gitleaks/gitleaks/releases/download/v${VER}/gitleaks_${VER}_linux_x64.tar.gz" | tar -xz -C /tmp/gl && \
    mv /tmp/gl/gitleaks /usr/local/bin/ && \
    rm -rf /tmp/gl

# claude-code / opencode-ai — AI コーディング支援ツール。
# Gitea CI 上の AI コードレビュー (pre-commit / PR) で使用する。
# ビルド再現性のためバージョンを固定する。
RUN npm install -g @anthropic-ai/claude-code@2.1.214 opencode-ai@1.18.3

# headroom (コンテキスト圧縮プロキシ) — AI レビューの LLM トラフィックを圧縮する。
# 専用 venv に headroom-ai[all] を導入し /usr/local/bin へ symlink することで
# gitea-runner の PATH から呼べるようにする (shellcheck/actionlint と同じ配置)。
# ビルド再現性のためバージョンを固定する。
RUN uv venv /opt/headroom --python 3.12 \
  && uv pip install --python /opt/headroom/bin/python "headroom-ai[all]==0.31.0" \
  && chmod -R a+rX /opt/headroom \
  && ln -s /opt/headroom/bin/headroom /usr/local/bin/headroom

# Kompress ML モデルと ONNX をビルド時に事前取得し、コンテナ実行時の
# 初回ダウンロード遅延を回避する (失敗してもビルドは継続、診断のため stderr は残す)。
RUN HF_HOME=/opt/headroom/hf-cache /opt/headroom/bin/python -c "from headroom import compress; \
      compress([{'role':'user','content':'warmup'}])" \
    || (echo "[warning] headroom model warmup failed; first run may be slow" >&2 && true)

# 実行ユーザ (gitea-runner) がキャッシュへ読み取れるよう、ディレクトリ存在を保証して所有権を移譲する。
# warmup 失敗で hf-cache が未作成の場合もあるため mkdir -p で確実に作る。
# 書き込みは gitea-runner が行うためキャッシュディレクトリは chown のみ。
RUN mkdir -p /opt/headroom/hf-cache \
  && chown -R gitea-runner:gitea-runner /opt/headroom/hf-cache

USER gitea-runner
WORKDIR /workspace
