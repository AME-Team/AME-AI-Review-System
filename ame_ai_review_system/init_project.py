"""``ame-review init`` の足場展開を行うモジュール.

対象リポジトリへ ``.ame-review/`` 設定ディレクトリ・Gate 2 ワークフロー・
Gate 1 pre-commit 設定・TS エンジン依存を生成する。エンジンと SDK 言語の組合せで
認証・Node 要否・pip extras を切り替える。
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from . import paths

PROFILES: tuple[str, ...] = ("minimal", "python", "full")
ENGINES: tuple[str, ...] = ("claude", "opencode", "antigravity")

# エンジン既定モデル。配布時の妥当な初期値。
_DEFAULT_MODEL: dict[str, str] = {
    "claude": "sonnet",
    "opencode": "anthropic/claude-sonnet-4",
    "antigravity": "gemini-2.5-pro",
}

_AI_HOOK_MARKER = "# AME AI Review System — Gate 1 AI review hooks"


def engine_meta(engine: str, sdk_lang: str) -> dict[str, Any]:
    """エンジン/SDK 言語から生成に必要なメタ情報を返す。."""
    needs_node = engine == "opencode" or (
        engine == "claude" and sdk_lang == "typescript"
    )
    if engine == "claude" and sdk_lang == "python":
        pip_extra = "claude"
    elif engine == "antigravity":
        pip_extra = "antigravity"
    else:
        pip_extra = ""
    return {
        "needs_node": needs_node,
        "pip_extra": pip_extra,
        "auth_env": _auth_env(engine),
    }


def _auth_env(engine: str) -> dict[str, str]:
    if engine == "claude":
        return {"ANTHROPIC_API_KEY": "${{ secrets.ANTHROPIC_API_KEY }}"}
    if engine == "antigravity":
        return {"GEMINI_API_KEY": "${{ secrets.GEMINI_API_KEY }}"}
    # opencode: SDK サーバが ~/.local/share/opencode/auth.json を読む。
    return {"OPENCODE_AUTH_B64": "${{ secrets.OPENCODE_AUTH_B64 }}"}


def run_init(
    target_dir: str,
    profile: str,
    engine: str,
    sdk_lang: str,
    reviewer_name: str,
    *,
    force: bool = False,
    run_npm: bool = True,
) -> int:
    if profile not in PROFILES:
        msg = f"Invalid profile {profile!r}. Choose from: {', '.join(PROFILES)}"
        raise SystemExit(msg)
    if engine not in ENGINES:
        msg = f"Invalid engine {engine!r}. Choose from: {', '.join(ENGINES)}"
        raise SystemExit(msg)

    target = Path(target_dir).resolve()
    target.mkdir(parents=True, exist_ok=True)
    ame = target / ".ame-review"

    meta = engine_meta(engine, sdk_lang)
    model = _DEFAULT_MODEL[engine]

    _scaffold_config(ame, engine, sdk_lang, model, force=force)
    _generate_workflows(target, reviewer_name, engine, meta, force=force)
    _write_precommit(target, profile, force=force)
    if meta["needs_node"]:
        _setup_ts_engines(ame, engine, sdk_lang, run_npm=run_npm)
    _update_gitignore(target)
    _print_next_steps(target, reviewer_name, engine, sdk_lang, meta, profile)
    return 0


def _write(dest: Path, content: str, *, force: bool) -> None:
    if dest.exists() and not force:
        print(f"  skip (exists): {dest}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")
    print(f"  wrote: {dest}")


def _copy_packaged(rel: str, dest: Path, *, force: bool) -> None:
    src = paths.package_dir() / rel
    if dest.exists() and not force:
        print(f"  skip (exists): {dest}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
    print(f"  wrote: {dest}")


def _scaffold_config(
    ame: Path,
    engine: str,
    sdk_lang: str,
    model: str,
    *,
    force: bool,
) -> None:
    print("[init] .ame-review/ config:")
    _copy_packaged("config.json", ame / "config.json", force=force)
    _copy_packaged("review_prompt.txt", ame / "review_prompt.txt", force=force)
    _copy_packaged(".semgrep/rules.yml", ame / ".semgrep" / "rules.yml", force=force)

    user_cfg: dict[str, Any] = {
        "engine": engine,
        "model": model,
        "sdk_lang": sdk_lang if engine == "claude" else None,
    }
    user_cfg = {k: v for k, v in user_cfg.items() if v is not None}
    _write(
        ame / "config.user.json",
        json.dumps(user_cfg, indent=2, ensure_ascii=False) + "\n",
        force=force,
    )
    (ame / "state").mkdir(parents=True, exist_ok=True)


def _generate_workflows(
    target: Path,
    reviewer_name: str,
    engine: str,
    meta: dict[str, Any],
    *,
    force: bool,
) -> None:
    print("[init] .github/workflows/:")
    wf_dir = target / ".github" / "workflows"
    command = _render_command_workflow(reviewer_name, engine, meta)
    reply = _render_reply_workflow(reviewer_name, engine, meta)
    _write(wf_dir / "ai-review-command.yml", command, force=force)
    _write(wf_dir / "ai-review-reply.yml", reply, force=force)


def _install_block(meta: dict[str, Any]) -> str:
    extra = meta["pip_extra"]
    spec = f"ame-ai-review-system[{extra}]" if extra else "ame-ai-review-system"
    lines = [
        "      - name: Setup Python",
        "        uses: actions/setup-python@v5",
        "        with:",
        '          python-version: "3.12"',
        "      - name: Install ame-ai-review-system",
        f"        run: pip install '{spec}'",
    ]
    if meta["needs_node"]:
        lines += [
            "      - name: Setup Node",
            "        uses: actions/setup-node@v4",
            "        with:",
            '          node-version: "22"',
            "      - name: Install TS engine deps",
            "        run: npm --prefix .ame-review/engines-ts ci",
        ]
    return "\n".join(lines)


def _restore_credentials_block(engine: str) -> str:
    if engine == "opencode":
        return (
            "      - name: Restore OpenCode credentials\n"
            "        run: |\n"
            "          mkdir -p ~/.local/share/opencode\n"
            '          echo "${{ secrets.OPENCODE_AUTH_B64 }}" | base64 -d '
            "> ~/.local/share/opencode/auth.json\n"
            "          chmod 600 ~/.local/share/opencode/auth.json"
        )
    # claude / antigravity は API キーを env 経由で渡すため復元ステップ不要。
    return "      # Credentials are injected via environment secrets."


def _env_block(meta: dict[str, Any], reviewer_name: str, app_token: str) -> str:
    env = {
        f"{reviewer_name.upper().replace('-', '_')}_TOKEN": app_token,
        "REVIEWER_NAME": reviewer_name,
        "GITHUB_REPOSITORY": "${{ github.repository }}",
    }
    env.update(meta["auth_env"])
    return "\n".join(f"          {k}: {v}" for k, v in env.items())


def _reviewer_secret_names(reviewer_name: str) -> tuple[str, str]:
    upper = reviewer_name.upper().replace("-", "_")
    return f"{upper}_APP_ID", f"{upper}_APP_PRIVATE_KEY"


def _render_command_workflow(
    reviewer_name: str,
    engine: str,
    meta: dict[str, Any],
) -> str:
    bot = f"{reviewer_name}[bot]"
    app_id, app_key = _reviewer_secret_names(reviewer_name)
    env_block = _env_block(meta, reviewer_name, "${{ steps.app_token.outputs.token }}")
    return f"""---
name: AI Code Review (Command)

"on":
  issue_comment:
    types: [created]
  workflow_dispatch:
    inputs:
      pr_number:
        description: "Review target PR number (manual run)"
        required: true

permissions:
  contents: read
  pull-requests: write

jobs:
  review:
    name: Review on /request-review ({reviewer_name})
    runs-on: ubuntu-latest
    timeout-minutes: 10
    if: >-
      github.event_name == 'workflow_dispatch' || (github.event.issue.pull_request != null &&
       github.event.comment.user.login != '{bot}' &&
       startsWith(github.event.comment.body, '/'))
    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          fetch-depth: 0
{_restore_credentials_block(engine)}
{_install_block(meta)}
      - name: Determine target PR and whether to run
        id: cmd
        env:
          EVENT_NAME: ${{{{ github.event_name }}}}
          INPUT_PR: ${{{{ inputs.pr_number }}}}
          COMMENT_BODY: ${{{{ github.event.comment.body }}}}
          ISSUE_PR: ${{{{ github.event.issue.number }}}}
        run: |
          if [ "$EVENT_NAME" = "workflow_dispatch" ]; then
            echo "run_review=true" >> "$GITHUB_OUTPUT"
            echo "pr_number=${{INPUT_PR}}" >> "$GITHUB_OUTPUT"
          else
            RUN_REVIEW=$(python -m ame_ai_review_system.review_config is-review-command "${{COMMENT_BODY}}")
            echo "run_review=${{RUN_REVIEW}}" >> "$GITHUB_OUTPUT"
            echo "pr_number=${{ISSUE_PR}}" >> "$GITHUB_OUTPUT"
      - name: Get GitHub App installation token
        id: app_token
        if: steps.cmd.outputs.run_review == 'true'
        uses: actions/create-github-app-token@v2
        with:
          app-id: ${{{{ secrets.{app_id} }}}}
          private-key: ${{{{ secrets.{app_key} }}}}
          permission-contents: read
          permission-pull-requests: write
          permission-issues: write
      - name: Switch to PR branch
        if: steps.cmd.outputs.run_review == 'true'
        env:
          GITHUB_REPOSITORY: ${{{{ github.repository }}}}
          PR_NUMBER: ${{{{ steps.cmd.outputs.pr_number }}}}
          GITHUB_PAT_TOKEN: ${{{{ steps.app_token.outputs.token }}}}
        run: |
          python -m ame_ai_review_system.main checkout "$PR_NUMBER"
      - name: Run General Review
        if: steps.cmd.outputs.run_review == 'true'
        env:
{env_block}
          REVIEW_ENGINE: {engine}
          PR_NUMBER: ${{{{ steps.cmd.outputs.pr_number }}}}
        run: |
          python -m ame_ai_review_system.main review \\
            "$PR_NUMBER" \\
            --prompt-file .ame-review/review_prompt.txt
"""


def _render_reply_workflow(
    reviewer_name: str,
    engine: str,
    meta: dict[str, Any],
) -> str:
    bot = f"{reviewer_name}[bot]"
    app_id, app_key = _reviewer_secret_names(reviewer_name)
    env_block = _env_block(meta, reviewer_name, "${{ steps.app_token.outputs.token }}")
    return f"""---
name: AI Review Reply

"on":
  issue_comment:
    types: [created]
  pull_request_review_comment:
    types: [created]

permissions:
  contents: read
  pull-requests: write

jobs:
  reply:
    name: Reply to @{reviewer_name}
    runs-on: ubuntu-latest
    timeout-minutes: 10
    if: >-
      github.event_name == 'issue_comment' &&
      contains(github.event.comment.body, '@{reviewer_name}') &&
      github.event.comment.user.login != '{bot}' &&
      !startsWith(github.event.comment.body, '/')
    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          fetch-depth: 0
{_restore_credentials_block(engine)}
{_install_block(meta)}
      - name: Get GitHub App installation token
        id: app_token
        uses: actions/create-github-app-token@v2
        with:
          app-id: ${{{{ secrets.{app_id} }}}}
          private-key: ${{{{ secrets.{app_key} }}}}
          permission-contents: read
          permission-pull-requests: write
          permission-issues: write
      - name: Switch to PR branch
        env:
          GITHUB_REPOSITORY: ${{{{ github.repository }}}}
          PR_NUMBER: ${{{{ github.event.issue.number }}}}
          GITHUB_PAT_TOKEN: ${{{{ steps.app_token.outputs.token }}}}
        run: |
          python -m ame_ai_review_system.main checkout "$PR_NUMBER"
      - name: Run Reply
        env:
{env_block}
          REVIEW_ENGINE: {engine}
          PR_NUMBER: ${{{{ github.event.issue.number }}}}
        run: |
          python -m ame_ai_review_system.reply run "$PR_NUMBER"
"""


def _write_precommit(target: Path, profile: str, *, force: bool) -> None:
    print(f"[init] .pre-commit-config.yaml (profile={profile}):")
    dest = target / ".pre-commit-config.yaml"
    src = paths.package_dir() / "templates" / "precommit" / f"{profile}.yaml"
    fragment = src.read_text(encoding="utf-8")
    if dest.exists() and not force:
        existing = dest.read_text(encoding="utf-8")
        if _AI_HOOK_MARKER in existing:
            print("  skip (AI hooks already present)")
            return
        with dest.open("a", encoding="utf-8") as fh:
            if not existing.endswith("\n"):
                fh.write("\n")
            fh.write(
                "\n" + fragment.split("repos:", 1)[1]
                if "repos:" in fragment
                else fragment
            )
        print(f"  appended AI hooks: {dest}")
        return
    dest.write_text(fragment, encoding="utf-8")
    print(f"  wrote: {dest}")


def _setup_ts_engines(ame: Path, engine: str, sdk_lang: str, *, run_npm: bool) -> None:
    print("[init] TS engine sidecar:")
    ts_dir = ame / "engines-ts"
    ts_dir.mkdir(parents=True, exist_ok=True)
    deps: dict[str, str] = {}
    if engine == "opencode":
        deps["@opencode-ai/sdk"] = "*"
    if engine == "claude" and sdk_lang == "typescript":
        deps["@anthropic-ai/claude-agent-sdk"] = "*"
    pkg = {
        "name": "ame-review-engines-ts",
        "version": "1.0.0",
        "private": True,
        "type": "module",
        "dependencies": deps,
    }
    (ts_dir / "package.json").write_text(
        json.dumps(pkg, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"  wrote: {ts_dir / 'package.json'}")
    for script in ("claude.mjs", "opencode.mjs"):
        src = paths.package_dir() / "engines" / "ts" / script
        if src.exists():
            shutil.copyfile(src, ts_dir / script)
            print(f"  wrote: {ts_dir / script}")
    if run_npm:
        npm = shutil.which("npm")
        if npm:
            print("  running npm install ...")
            subprocess.run([npm, "install", "--prefix", str(ts_dir)], check=False)
        else:
            print(
                "  npm not found; run manually: npm --prefix .ame-review/engines-ts install"
            )


def _update_gitignore(target: Path) -> None:
    print("[init] .gitignore:")
    gi = target / ".gitignore"
    entries = [
        ".ame-review/config.user.json",
        ".ame-review/state/",
        ".ame-review/engines-ts/node_modules/",
    ]
    existing = gi.read_text(encoding="utf-8") if gi.exists() else ""
    new = [e for e in entries if e not in existing]
    if not new:
        print("  skip (entries already present)")
        return
    with gi.open("a", encoding="utf-8") as fh:
        if existing and not existing.endswith("\n"):
            fh.write("\n")
        fh.write("\n# AME AI Review System\n")
        for e in new:
            fh.write(e + "\n")
    print(f"  appended {len(new)} entr(ies): {gi}")


def _print_next_steps(
    target: Path,
    reviewer_name: str,
    engine: str,
    sdk_lang: str,
    meta: dict[str, Any],
    profile: str,
) -> None:
    app_id, app_key = _reviewer_secret_names(reviewer_name)
    extra = meta["pip_extra"]
    install_cmd = (
        f"pip install 'ame-ai-review-system[{extra}]'"
        if extra
        else "pip install ame-ai-review-system"
    )
    print("\n=== Next steps ===")
    print(f"1. Install the package (local dev): {install_cmd}")
    print("2. Create a GitHub App for the reviewer and install it on the repo.")
    print(
        "   Required permissions: Contents: Read, Pull requests: Read&Write, Issues: Read&Write."
    )
    print("3. Add repository Actions Secrets:")
    print(f"   - {app_id}  (GitHub App ID)")
    print(f"   - {app_key}  (.pem private key)")
    if engine == "claude":
        print("   - ANTHROPIC_API_KEY  (Anthropic API key for the SDK)")
    elif engine == "antigravity":
        print("   - GEMINI_API_KEY  (Google AI API key)")
    elif engine == "opencode":
        print("   - OPENCODE_AUTH_B64  (base64 of ~/.local/share/opencode/auth.json)")
    print("4. Install pre-commit hooks locally:")
    print(
        "   pre-commit install --install-hooks -t pre-commit -t commit-msg -t pre-push -t post-commit"
    )
    if meta["needs_node"]:
        print("5. TS engine: npm --prefix .ame-review/engines-ts install")
    print(
        f"\nEngine: {engine} (sdk={sdk_lang}), profile: {profile}, reviewer: {reviewer_name}"
    )
    print(f"Target: {target}")
