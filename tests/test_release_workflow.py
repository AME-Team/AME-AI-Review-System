"""リリースワークフローの移動メジャータグ (moving major tag) を機械検証する.

配布先は移動メジャータグを参照して hub のリリースへ自動追随する。付け替えの仕組みが失われると
配布先が更新されなくなる (無言の劣化) ため、ここで回帰を防ぐ。
"""

from __future__ import annotations

import re
from pathlib import Path

from ame_ai_review_system import __version__, init_cmd

_REPO_ROOT = Path(__file__).resolve().parents[1]
_RELEASE_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "release.yml"

# "on:" 配下のタグフィルタ (例: - "v[0-9]+.[0-9]+.[0-9]+")。
_TAG_FILTER = re.compile(r'^\s*-\s*"(?P<pattern>[^"]+)"\s*$', re.MULTILINE)


def _release_text() -> str:
    return _RELEASE_WORKFLOW.read_text(encoding="utf-8")


def test_release_workflow_tag_filter_excludes_moving_major_tag() -> None:
    # 付け替えたメジャータグは "v*" に一致する。フィルタが "v*" のままだと付け替えが
    # release.yml を再トリガーし、タグ名 "1" と __version__ の不一致で毎回失敗する。
    on_block = _release_text().split("permissions:", 1)[0]
    patterns = [m.group("pattern") for m in _TAG_FILTER.finditer(on_block)]
    assert patterns, "release.yml にタグフィルタが見つかりません"
    assert "v*" not in patterns
    assert all(pattern.startswith("v[0-9]") for pattern in patterns)


def test_major_tag_move_runs_after_release_upload() -> None:
    # パッケージが存在しないバージョンへタグが向く事故を防ぐため、付け替えはアセット添付の
    # 成功後にのみ実行される順序であること (先行ステップの失敗でジョブは中断される)。
    text = _release_text()
    upload_index = text.index("softprops/action-gh-release")
    move_index = text.index("Move major tag to this release")
    assert upload_index < move_index


def test_major_tag_move_derives_major_and_force_pushes() -> None:
    # 移動先は push されたタグのメジャー成分 (例: v2.3.4 → v2)。対象は HEAD にする
    # (浅い clone でも確実に解決でき、タグ ref の取得有無に依存しない)。
    text = _release_text()
    assert 'MAJOR_TAG="v$(echo "${GITHUB_REF_NAME#v}" | cut -d. -f1)"' in text
    assert 'git tag -f "$MAJOR_TAG" HEAD' in text
    assert "--force-with-lease=" in text


def test_major_tag_move_is_a_compare_and_swap() -> None:
    # 最新判定と push の間に別 run が先に付け替えても巻き戻さないよう、
    # 観測値を lease にした compare-and-swap で push する (stale なら拒否される)。
    text = _release_text()
    assert (
        'LEASE_RAW=$(git ls-remote --tags --refs origin "refs/tags/${MAJOR_TAG}")'
        in text
    )
    assert "LEASE=$(printf '%s\\n' \"${LEASE_RAW}\" | cut -f1)" in text
    assert '--force-with-lease="refs/tags/${MAJOR_TAG}:${LEASE}"' in text
    # 判定から push までの窓を狭めるため、push のたびに最新を取り直す。
    # 判定材料を取得できない場合は異常として扱う (空を正常終了で返すと誤スキップする)。
    # 注釈はコマンド置換に飲み込まれるため関数内では出さず、呼び出し側で出す。
    assert "if ! LATEST_TAG=$(latest_remote_tag); then" in text
    assert "return 1" in text
    # lease 敗北は有限回の再試行で巻き取る (古い run が先に勝っても最新 run が勝ち直す)。
    assert "MAX_ATTEMPTS=" in text
    assert "failed to move ${MAJOR_TAG} after ${MAX_ATTEMPTS} attempts." in text


def test_latest_tag_pipeline_cannot_abort_the_step() -> None:
    # 既定シェルが -eo pipefail の場合、grep が 0 件のパイプライン失敗で step が異常終了し、
    # 空タグを検知する ::error:: 分岐が到達不能になる。`|| true` で保護し、
    # 失敗時のメッセージを自作のものに一本化する (無言のスキップを残さない)。
    assert "| sort -V | tail -1 || true" in _release_text()


def test_release_workflow_does_not_serialize_runs() -> None:
    # concurrency で group を共有すると、まだ開始していない pending の run が自動キャンセルされ、
    # 中間のタグの Release とアセットが無言で欠落する。各タグの run は独立に保つ。
    assert "concurrency:" not in _release_text()


def test_major_tag_move_is_guarded_to_the_latest_release() -> None:
    # run は並走しうる。古い run の再実行や到着順の逆転で移動タグが巻き戻らないよう、
    # 最新リリース以外は付け替えをスキップする。最新判定は checkout 時点のローカルタグでは
    # なくリモートを直接読む (自 run の開始後に push されたタグを見落とさないため)。
    text = _release_text()
    assert "git ls-remote --tags --refs origin 'refs/tags/v*'" in text
    assert 'if [ "${GITHUB_REF_NAME}" != "${LATEST_TAG}" ]; then' in text
    # 最新タグを解決できない場合は無言でスキップせず失敗させる。
    assert (
        'echo "::error::could not resolve the latest release tag from origin."' in text
    )


def test_release_workflow_keeps_the_move_shallow_clone_safe() -> None:
    # 付け替えは HEAD を対象にし、ls-remote で最新判定するため浅い clone で足りる。
    # fetch-depth: 0 を要求しない (取得量を増やす必要がない)。
    assert "fetch-depth" not in _release_text()


def test_default_ref_matches_version_major_tag() -> None:
    # init が埋め込む既定 ref は、release.yml が付け替えるタグと一致していること。
    # 定数で持つとメジャーが変わった時に配布先が解決不能な ref を参照するため、
    # __version__ からの導出を強制する (ドリフト検知)。
    assert f"v{__version__.split('.')[0]}" == init_cmd.DEFAULT_REF
    assert re.fullmatch(r"v[0-9]+", init_cmd.DEFAULT_REF) is not None


def test_version_is_three_component() -> None:
    # タグフィルタ (vX.Y.Z) と __version__ の形式が対応していること。
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__) is not None
