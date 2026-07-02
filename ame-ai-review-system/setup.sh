#!/usr/bin/env bash
# AME-AI-Review-System setup script.
# Installs pre-commit and static analysis tools globally, then registers hooks.
set -euo pipefail

# ---------------------------------------------------------------------------
# Python static analysis tools (global install)
# ---------------------------------------------------------------------------
pip install \
    ruff \
    mypy \
    codespell \
    yamllint \
    sqlfluff \
    pre-commit \
    pyright \
    pytest

# ---------------------------------------------------------------------------
# Node.js dev tools (markdownlint-cli2, prettier, commitlint, textlint, etc.)
# ---------------------------------------------------------------------------
npm ci

# ---------------------------------------------------------------------------
# Install shellcheck via OS package manager (recommended)
#   Debian/Ubuntu: apt install shellcheck
#   macOS:         brew install shellcheck
#   fallback:      pip install shellcheck-py
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# actionlint: install via go (if available)
#   go install github.com/rhysd/actionlint/cmd/actionlint@v1.7.7
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# gitleaks: install via OS package manager (recommended)
#   Debian/Ubuntu: apt install gitleaks
#   macOS:         brew install gitleaks
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Register pre-commit hooks (pre-commit / commit-msg / pre-push)
# ---------------------------------------------------------------------------
pre-commit install --install-hooks -t pre-commit -t commit-msg -t pre-push

echo "setup complete. Run: pre-commit run --all-files"
