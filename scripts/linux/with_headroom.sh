#!/usr/bin/env bash
# AI レビューコマンドを headroom プロキシ経由で実行する。
#
# WHY: コンテナ内の claude/opencode/agy の LLM API トラフィックを headroom プロキシへ
# ルーティングし、入力 (diff 中心) と出力 (レビュー JSON) のトークンを圧縮する。
# config.json の headroom_proxy_enabled が無効ならプロキシなしでそのまま実行する。
# 共有プロキシを1つ起動し env HEADROOM_ENABLED を介して engine.py 側が wrap 経由で
# 再利用する (ネストした複数 engine.py 呼び出しでプロキシ起動オーバーヘッドを避ける)。
set -euo pipefail

PROXY_PID=""
PROXY_LOG=""
MANAGED_PROXY="no"

_cleanup() {
    if [ "$MANAGED_PROXY" = "yes" ] && [ -n "$PROXY_PID" ] \
        && kill -0 "$PROXY_PID" 2>/dev/null; then
        # CLAUDE.md §8: 変数展開での直接シグナル送信は禁止。xargs 経由で送る。
        printf '%s\n' "$PROXY_PID" | xargs -r kill -15
    fi
    if [ -n "$PROXY_LOG" ]; then
        rm -f "$PROXY_LOG"
    fi
    return 0
}

_cfg() {
    # review_config 経由で設定値を読む。失敗時は第2引数のデフォルトを返す。
    local key="$1" default="$2"
    python3 -m ame_ai_review_system.review_config get "$key" 2>/dev/null \
        || printf '%s' "$default"
}

_is_healthy() {
    # doctor は 0=healthy / 1=warnings(動作中) / 2=failure。0/1 を健全とみなす。
    # 0: プロキシが健全に動作中
    # 1: プロキシが動作中だが警告あり（例: モデル未ダウンロード）
    # 2: プロキシが異常（未起動または接続失敗）
    local drc
    if headroom doctor --port "$PORT" >/dev/null 2>&1; then
        drc=0
    else
        drc=$?
    fi
    [ "$drc" -le 1 ]
}

# --- 設定ゲート: 無効ならプロキシなしで実行 ---
ENABLED="$(_cfg headroom_proxy_enabled false)"
if [ "$ENABLED" != "true" ]; then
    exec "$@"
fi

if ! command -v headroom >/dev/null 2>&1; then
    echo "[headroom] 'headroom' が見つかりません。プロキシなしで実行します。" >&2
    exec "$@"
fi

PORT="$(_cfg headroom_proxy_port 8787)"
case "$PORT" in
    '' | *[!0-9]*)
        echo "[headroom] 無効な port 値: ${PORT}。プロキシなしで実行します。" >&2
        exec "$@"
        ;;
esac
if [ "$PORT" -lt 1 ] || [ "$PORT" -gt 65535 ]; then
    echo "[headroom] port は 1-65535 の範囲で指定してください: ${PORT}。プロキシなしで実行します。" >&2
    exec "$@"
fi
export HEADROOM_PORT="$PORT"

# 出力トークン削減 (verbosity steering / effort routing)
SHAPER="$(_cfg headroom_output_shaper true)"
if [ "$SHAPER" = "true" ]; then
    export HEADROOM_OUTPUT_SHAPER=1
fi

trap _cleanup EXIT

healthy="no"
# 既存プロキシが健在なら再利用し、新規起動しない。
if _is_healthy; then
    echo "[headroom] 既存プロキシ (port ${PORT}) を再利用します。" >&2
    healthy="yes"
else
    PROXY_LOG="$(mktemp)"
    # HF_HOME は headroom プロキシ起動時のみ必要 (モデルキャッシュ先)。
    # Docker 以外の環境ではディレクトリが存在しない場合があるため確認する。
    HF_HOME_PREFIX=""
    if [ -d /opt/headroom/hf-cache ]; then
        HF_HOME_PREFIX="HF_HOME=/opt/headroom/hf-cache"
    fi
    env $HF_HOME_PREFIX headroom proxy --port "$PORT" >"$PROXY_LOG" 2>&1 &
    PROXY_PID=$!
    MANAGED_PROXY="yes"

    # ヘルスチェック (最大約15秒待つ)
    for _ in $(seq 1 30); do
        if _is_healthy; then
            healthy="yes"
            break
        fi
        sleep 0.5
    done

    if [ "$healthy" != "yes" ]; then
        echo "[headroom] プロキシが起動しませんでした。プロキシなしで実行します。" >&2
        if [ -n "$PROXY_LOG" ]; then
            echo "[headroom] プロキシログ:" >&2
            cat "$PROXY_LOG" >&2 2>/dev/null || true
        fi
        # 起動したが不健全なプロセスを孤立させポートを占有しないよう終了させる。
        if [ -n "$PROXY_PID" ] && kill -0 "$PROXY_PID" 2>/dev/null; then
            printf '%s\n' "$PROXY_PID" | xargs -r kill -15
        fi
        MANAGED_PROXY="no"
        PROXY_PID=""
    else
        echo "[headroom] プロキシ起動完了 (port ${PORT}, pid ${PROXY_PID})。" >&2
    fi
fi

# engine.py が wrap 経由でプロキシを利用するかを env で通知する。
if [ "$healthy" = "yes" ]; then
    export HEADROOM_ENABLED=1
    echo "[headroom] プロキシ利用を有効化しました。" >&2
else
    # プロキシ非健全時は HEADROOM_* を全て未設定にする（engine.py は未設定で無効と判定）
    unset HEADROOM_ENABLED HEADROOM_PORT HEADROOM_OUTPUT_SHAPER
    echo "[headroom] プロキシ非健全のため直接実行します。" >&2
fi

# コマンド実行 (終了コードを保持するため set -e を一時解除)
set +e
"$@"
rc=$?
set -e
exit "$rc"
