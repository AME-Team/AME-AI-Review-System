"""Main CLI entrypoint for AME AI Review System.

Replaces: pr_review.sh, checkout_pr.sh

Subcommands:
  review       Run AI review on PR (replaces pr_review.sh)
  checkout     Checkout PR branch (replaces checkout_pr.sh)
  setup        Install dependencies (replaces setup.sh)
"""

from __future__ import annotations

import argparse
import contextlib
import os
import pathlib
import re
import subprocess
import sys
import tempfile
from typing import Any

from . import github_client, pr_streak, review_config, static_precheck
from . import payload as payload_module
from .engine import resolve_settings, run_engine

# ============================================================================
# Common utilities
# ============================================================================

PROJ_ROOT = pathlib.Path(__file__).resolve().parent.parent
STALE_ROUND_THRESHOLD = 3
MAX_REVIEWS = 10
MAX_DIFF_LINES = 4000
HTTP_STATUS_OK = 200


def _get_env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def _run_git(args: list[str], cwd: pathlib.Path | None = None) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd or PROJ_ROOT,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return ""


# ============================================================================
# checkout command (replaces checkout_pr.sh)
# ============================================================================


def cmd_checkout(args: argparse.Namespace) -> int:
    api_url, repo = github_client.resolve_env()
    pr_number = args.pr_number
    try:
        token = args.token or github_client.get_token(
            str(
                pathlib.Path.home()
                / ".config"
                / "ame-ai-review-system"
                / "github.token"
            ),
        )
    except RuntimeError:
        token = ""

    if not token:
        print("[checkout] ERROR: Token required", file=sys.stderr)
        return 1

    # Fetch PR info
    pr_url = f"{api_url}/repos/{repo}/pulls/{pr_number}"
    try:
        pr_data = github_client.http_request("GET", pr_url, token)
    except RuntimeError as e:
        print(f"[checkout] ERROR: Failed to fetch PR info: {e}", file=sys.stderr)
        return 1

    if not isinstance(pr_data, dict):
        print(
            f"[checkout] ERROR: Unexpected PR data type: {type(pr_data)}",
            file=sys.stderr,
        )
        return 1

    base_ref = str(pr_data.get("base", {}).get("ref", ""))
    if not re.fullmatch(r"[A-Za-z0-9/_.-]+", base_ref):
        print(f"[checkout] ERROR: Invalid BASE_REF: {base_ref!r}", file=sys.stderr)
        return 1

    title = str(pr_data.get("title", ""))
    body = str(pr_data.get("body", ""))
    head_branch = str(pr_data.get("head", {}).get("ref", ""))

    if not head_branch or head_branch == "HEAD":
        print(
            f"[checkout] ERROR: Could not determine head branch for PR #{pr_number}",
            file=sys.stderr,
        )
        return 1

    # Write metadata to GITHUB_ENV if available
    github_env = os.environ.get("GITHUB_ENV")
    if github_env:
        delim = "ame_review_meta"
        with pathlib.Path(github_env).open("a", encoding="utf-8") as f:
            f.writelines(
                f"{key}<<{delim}\n{value}\n{delim}\n"
                for key, value in (
                    ("BASE_REF", base_ref),
                    ("PR_TITLE", title),
                    ("PR_BODY", body),
                )
            )

    # Fetch and checkout
    _run_git(["fetch", "origin", head_branch])
    _run_git(["checkout", head_branch])

    print(
        f"[checkout] Checked out PR #{pr_number} branch '{head_branch}' (base: {base_ref})",
    )
    return 0


# ============================================================================
# review command (replaces pr_review.sh)
# ============================================================================


def _build_review_prompt(
    pr_number: int,
    pr_title: str,
    base_ref: str,
    pr_body: str,
    changed_files: str,
    commit_log: str,
    diff: str,
    review_count: int,
    reviewer_prompt_file: pathlib.Path,
) -> str:
    """Build the review prompt for the AI engine."""
    prompt = reviewer_prompt_file.read_text(encoding="utf-8")
    prompt += "\n\n## PR 情報\n"
    prompt += f"- PR #: {pr_number}\n"
    prompt += f"- タイトル: {pr_title}\n"
    prompt += f"- マージ先: {base_ref}\n"
    prompt += f"- 説明: {pr_body or '（なし）'}\n"

    if review_count >= STALE_ROUND_THRESHOLD:
        prompt += f"\n## ⚠️ 収束シグナル（ラウンド {review_count + 1}）\n"
        prompt += f"この PR は既に {review_count} 回レビュー済みです。\n"
        prompt += "新規機能追加の指摘や些末な改善提案は抑制し、\n"
        prompt += "既存指摘への対応確認と CRITICAL/HIGH のみに集中してください。\n"

    prompt += "\n## 変更ファイル一覧\n```\n"
    prompt += changed_files + "\n```\n\n"
    prompt += "## コミット一覧\n```\n"
    prompt += commit_log + "\n```\n\n"
    prompt += "## diff\n```diff\n"
    prompt += diff + "\n```\n"

    return prompt


def _run_engine_capture(_settings: dict[str, Any], prompt: str) -> tuple[int, str, str]:
    """Run engine.py with prompt, return (exit_code, stdout, stderr)."""
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix="_prompt.txt",
        delete=False,
        encoding="utf-8",
    ) as pf:
        pf.write(prompt)
        prompt_file = pf.name

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix="_out.txt",
        delete=False,
        encoding="utf-8",
    ) as of:
        out_file = of.name

    err_file = out_file + ".err"

    try:
        with (
            pathlib.Path(prompt_file).open(encoding="utf-8") as pfi,
            pathlib.Path(out_file).open("w", encoding="utf-8") as fout,
            pathlib.Path(err_file).open("w", encoding="utf-8") as efi,
        ):
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ame_ai_review_system.engine",
                    "--role",
                    "review",
                ],
                stdin=pfi,
                stdout=fout,
                stderr=efi,
                timeout=600,
                check=False,
            )
        engine_exit = proc.returncode

        stdout = pathlib.Path(out_file).read_text(encoding="utf-8")
        stderr = pathlib.Path(err_file).read_text(encoding="utf-8")

        return engine_exit, stdout, stderr
    finally:
        for f in (prompt_file, out_file, err_file):
            with contextlib.suppress(OSError):
                pathlib.Path(f).unlink()


def _post_review(
    api_url: str,
    repo: str,
    pr_number: int,
    token: str,
    payload_data: dict[str, Any],
) -> tuple[int, dict[str, Any] | list[Any]]:
    """Post a review to GitHub. Returns (status_code, response_json)."""
    url = f"{api_url}/repos/{repo}/pulls/{pr_number}/reviews"
    try:
        resp = github_client.http_request("POST", url, token, body=payload_data)
    except github_client.HttpError as e:
        print(
            f"[review] Failed to post review (HTTP {e.status_code}): {e}",
            file=sys.stderr,
        )
        return e.status_code, {}
    except RuntimeError as e:
        print(f"[review] Failed to post review: {e}", file=sys.stderr)
        return 0, {}
    else:
        return 200, resp


def _build_review_payloads(
    review_json: str,
    base_ref: str,
    head_sha: str,
) -> list[dict[str, Any]]:
    """Parse review JSON and build GitHub review payloads."""
    review, _ = payload_module.parse_review_json_with_flag(review_json)
    valid_lines = payload_module.build_valid_lines_map(base_ref)
    return payload_module.build_review_payloads(review, valid_lines, head_sha)


def cmd_review(args: argparse.Namespace) -> int:
    api_url, repo = github_client.resolve_env()
    pr_number = args.pr_number
    base_ref = args.base_ref
    pr_title = args.pr_title or ""
    pr_body = args.pr_body or ""
    reviewer_name = _get_env("REVIEWER_NAME", "ame-ai-reviewer")
    reviewer_prompt_file = args.prompt_file or (
        PROJ_ROOT / "ame-ai-review-system" / "review_prompt.txt"
    )

    # Token resolution
    try:
        token = args.token or github_client.get_token(
            str(
                pathlib.Path.home()
                / ".config"
                / "ame-ai-review-system"
                / f"{reviewer_name}.token",
            ),
            reviewer_name.upper().replace("-", "_") + "_TOKEN",
        )
    except RuntimeError:
        token = ""
    if not token:
        print("[review] ERROR: REVIEWER_TOKEN not found", file=sys.stderr)
        return 1

    # PR streak check
    if pr_streak.cmd_check(pr_number) == 0:
        print(
            f"[review] PR #{pr_number} already approved (streak threshold). Skipping review.",
        )
        return 0

    # Get HEAD SHA
    head_sha = _run_git(["rev-parse", "HEAD"])
    if not head_sha:
        print("[review] ERROR: Failed to get HEAD SHA.", file=sys.stderr)
        return 1

    # Check already reviewed SHAs
    reviews_url = f"{api_url}/repos/{repo}/pulls/{pr_number}/reviews?per_page=100"
    try:
        reviews_data = github_client.http_request("GET", reviews_url, token)
    except RuntimeError:
        reviews_data = []

    if not isinstance(reviews_data, list):
        reviews_data = []

    reviewed_shas = set()
    for r in reviews_data:
        if r.get("user", {}).get("login") == github_client.bot_login(reviewer_name):
            body = r.get("body", "")
            m = re.search(r"<!--\s*reviewed-sha:\s*([0-9a-f]{40,64})\s*-->", body)
            if m:
                reviewed_shas.add(m.group(1))

    if head_sha in reviewed_shas:
        print(f"[review] Already reviewed HEAD SHA {head_sha[:8]}, skipping.")
        return 0

    if len(reviewed_shas) >= MAX_REVIEWS:
        print(
            f"[review] Already {len(reviewed_shas)} push review(s) (max 10), skipping.",
        )
        return 0

    # Get diff and changed files
    diff = _run_git(["diff", f"origin/{base_ref}...HEAD"])
    if not diff:
        diff = _run_git(["diff", "HEAD~1"])
    if not diff:
        print("[review] No diff found, skipping review.")
        return 0

    # Diff compression via diff_utils
    try:
        from . import diff_utils

        diff = diff_utils.compact_diff(diff)
    except ImportError:
        pass

    diff_lines = diff.count("\n")
    if diff_lines > MAX_DIFF_LINES:
        print(f"[review] Diff truncated from {diff_lines} to 4000 lines.")
        diff = (
            "\n".join(diff.splitlines()[:4000])
            + f"\n... (truncated, {diff_lines} lines total)"
        )

    changed_files = _run_git(["diff", "--name-only", f"origin/{base_ref}...HEAD"])
    if not changed_files:
        changed_files = _run_git(["diff", "--name-only", "HEAD~1"])
    changed_files = changed_files[:50]  # limit

    commit_log = _run_git(["log", f"origin/{base_ref}..HEAD", "--oneline"])
    if not commit_log:
        commit_log = _run_git(["log", "HEAD~20..HEAD", "--oneline"])

    # Circuit breaker: static analysis pre-check
    if review_config.load_config().get("pr_review_require_static_checks", True):
        print("[review] Running static analysis pre-check (ruff/mypy/semgrep)...")
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ame_ai_review_system.static_precheck",
                    "--files-from-stdin",
                ],
                input=changed_files.encode(),
                capture_output=True,
                check=False,
            )
            if result.returncode != 0:
                print("[review] Static analysis failed. Skipping AI review.")
                print(
                    "[review] 静的解析エラーを解消してから /request-review を再実行してください。",
                )
                return 0
        except (subprocess.SubprocessError, OSError) as e:
            print(f"[review] Static precheck error: {e}", file=sys.stderr)
            return 1
        print("[review] Static analysis passed. Proceeding to AI review.")

    # Build prompt
    prompt = _build_review_prompt(
        pr_number=pr_number,
        pr_title=pr_title,
        base_ref=base_ref,
        pr_body=pr_body,
        changed_files=changed_files,
        commit_log=commit_log,
        diff=diff,
        review_count=len(reviewed_shas),
        reviewer_prompt_file=pathlib.Path(reviewer_prompt_file),
    )

    # Run engine
    print("[review] Running review via engine.py...")
    settings = resolve_settings("review")
    if settings["engine"] != "claude":
        print(
            f"[review] WARNING: budget limit not enforced for {settings['engine']}",
            file=sys.stderr,
        )

    engine_exit, engine_out, engine_err = _run_engine_capture(settings, prompt)

    if engine_err:
        print(f"[review] Engine stderr: {engine_err}", file=sys.stderr)

    if engine_exit != 0 or not engine_out.strip():
        print("[review] Engine failed.", file=sys.stderr)
        return 1

    print(f"[review] Engine output captured ({len(engine_out)} bytes)")

    # Write engine output to temp file for payload parser
    review_file: pathlib.Path | None = None
    try:
        fd, review_path = tempfile.mkstemp(suffix=".json", prefix="review_")
        os.close(fd)
        review_file = pathlib.Path(review_path)
        review_file.write_text(engine_out, encoding="utf-8")
        payloads = _build_review_payloads(str(review_file), base_ref, head_sha)
    except (ValueError, KeyError, TypeError, OSError) as e:
        print(f"[review] Failed to build payload: {e}", file=sys.stderr)
        return 1
    finally:
        if review_file is not None:
            review_file.unlink(missing_ok=True)

    if not payloads:
        print("[review] No payloads built.")
        return 0

    # Post reviews
    print(
        f"[review] Posting {len(payloads)} review(s) to PR #{pr_number} as {reviewer_name}...",
    )

    for i, pl in enumerate(payloads):
        status, resp = _post_review(api_url, repo, pr_number, token, pl)
        review_id = resp.get("id", "?") if isinstance(resp, dict) else "?"
        if status == HTTP_STATUS_OK:
            print(
                f"[review] Review {i + 1}/{len(payloads)} posted (id={review_id}, HTTP {status}).",
            )
        else:
            print(
                f"[review] Failed to post review {i + 1}/{len(payloads)} (HTTP {status}).",
            )
            # Try fallback as general comment
            if pl.get("comments"):
                fallback = pl.copy()
                bodies = [c.get("body", "") for c in pl["comments"]]
                fallback["body"] = "\n\n---\n\n".join(bodies)
                fallback["comments"] = []
                fb_status, _ = _post_review(api_url, repo, pr_number, token, fallback)
                if fb_status == HTTP_STATUS_OK:
                    print(
                        f"[review] Review {i + 1} posted as general comment (HTTP {fb_status}).",
                    )
                else:
                    print(f"[review] Fallback also failed (HTTP {fb_status}).")

    return 0


# ============================================================================
# setup command (replaces setup.sh)
# ============================================================================


def cmd_setup(_args: argparse.Namespace) -> int:
    """Install dependencies and configure pre-commit hooks."""
    import subprocess

    print("[setup] Installing Python static analysis tools...")
    py_tools = [
        "ruff",
        "mypy",
        "codespell",
        "yamllint",
        "sqlfluff",
        "pre-commit",
        "pyright",
        "pytest",
    ]
    subprocess.run([sys.executable, "-m", "pip", "install", *py_tools], check=False)

    print("[setup] Installing Node.js dev tools...")
    subprocess.run(["npm", "ci"], check=False)

    print("[setup] Installing pre-commit hooks...")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pre_commit",
            "install",
            "--install-hooks",
            "-t",
            "pre-commit",
            "-t",
            "commit-msg",
            "-t",
            "pre-push",
        ],
        check=False,
    )

    print("[setup] Done. Run: pre-commit run --all-files")
    return 0


# ============================================================================
# Main entrypoint
# ============================================================================


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="AME AI Review System CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # checkout
    p_checkout = subparsers.add_parser("checkout", help="Checkout PR branch")
    p_checkout.add_argument("pr_number", type=int)
    p_checkout.add_argument("--token", help="GitHub token (or use token file/env)")

    # review
    p_review = subparsers.add_parser("review", help="Run AI review on PR")
    p_review.add_argument("pr_number", type=int)
    p_review.add_argument(
        "--base-ref",
        default=os.environ.get("BASE_REF", "main"),
    )
    p_review.add_argument("--pr-title", default="")
    p_review.add_argument("--pr-body", default="")
    p_review.add_argument(
        "--prompt-file",
        type=pathlib.Path,
        help="Reviewer prompt file",
    )
    p_review.add_argument("--token", help="Reviewer token (or use token file/env)")

    # setup
    subparsers.add_parser("setup", help="Install dependencies and configure hooks")

    args = parser.parse_args(argv)

    if args.command == "checkout":
        return cmd_checkout(args)
    if args.command == "review":
        return cmd_review(args)
    if args.command == "setup":
        return cmd_setup(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
