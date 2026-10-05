"""OpenCode sidecar のリトライ方針を検証する (Issue #154).

配布物 (``ame_ai_review_system/engines/ts/retry.mjs``) を Node のハーネスで直接読み、
一時的な接続エラーの許可リストと、最深段での同一 variant 再試行を実測する。
"""

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
HARNESS = REPO_ROOT / "scripts" / "verify-opencode-retry.mjs"
POLICY = REPO_ROOT / "ame_ai_review_system" / "engines" / "ts" / "retry.mjs"


def test_opencode_retry_policy() -> None:
    """Sidecar のリトライ方針を実測する (Node が無い環境では省略する)."""
    assert HARNESS.is_file()
    assert POLICY.is_file()
    node = shutil.which("node")
    if node is None:
        pytest.skip("node が見つからないため sidecar の検証を省略する")
    completed = subprocess.run(
        [node, str(HARNESS)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
