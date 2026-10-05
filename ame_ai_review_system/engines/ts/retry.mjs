// opencode sidecar のリトライ方針 (Issue #113 / #137 / #154)。
// 副作用を持たない判定だけをここに置き、sidecar 本体とテストハーネス
// (scripts/verify-opencode-retry.mjs) の双方から同じ実装を使う。
//   - 接続系: 一時的なネットワークエラーだけを許可リストで再試行する
//   - 長さ系: finish=length で空応答したとき variant を下げ、最下段では同一 variant を試す

// Issue #113: 一時的な接続・ヘッダータイムアウトは retry で回復できる。
export const MAX_PROMPT_ATTEMPTS = 3;
export const RETRY_BASE_DELAY_MS = 5000;

// Issue #137: finish=length で空応答した際に variant を順に下げてリトライする。
// high→medium→low と reasoning を減らし、step down 先が無くなったら残余を同じ variant の
// 再試行に使う (非決定性回復)。
// Issue #154: 梯子の段数 (high→medium→low の 2 段) に 1 を足す。段数と同じ上限だと `high` 起点で
// step down が予算を使い切り、最深段の同一 variant 再試行に到達しない。起点に関わらず最下段で
// 最低 1 回は同じ variant を試すため、上限を段数 + 1 にする。
export const MAX_LENGTH_RETRIES = 3;
export const VARIANT_STEP_DOWN = { high: "medium", medium: "low", low: undefined };

// 再試行してよい一時的なエラーコード。恒久エラー (CERT_HAS_EXPIRED 等の証明書・ENOTFOUND 等の
// 名前解決失敗) は含めない。undici は fetch の失敗を包み、本来の原因を cause に入れる。
const RETRYABLE_CODES = new Set([
  "ECONNREFUSED",
  "ECONNRESET",
  "ETIMEDOUT",
  "EPIPE",
  "EAI_AGAIN",
  "UND_ERR_CONNECT_TIMEOUT",
  "UND_ERR_HEADERS_TIMEOUT",
  "UND_ERR_SOCKET",
]);

function errorCode(err) {
  // cause 側のコードを優先する (undici の "fetch failed" は cause に本来の原因を持つ)。
  const cause = err && err.cause;
  if (cause && typeof cause.code === "string" && cause.code) return cause.code;
  if (err && typeof err.code === "string" && err.code) return err.code;
  return "";
}

// Issue #154: コードが取れる場合は許可リストだけで判定する。文言一致の "fetch failed" は
// CERT_HAS_EXPIRED 等の恒久エラーまで拾い、回復しない失敗を繰り返すため使わない。
// コードが取れない場合に限り、一時的と分かる文言だけを保険として見る。
export function isRetryableError(err) {
  if (!err) return false;
  const code = errorCode(err);
  if (code) return RETRYABLE_CODES.has(code);
  const message = String(err.message || "").toLowerCase();
  return message.includes("headers timeout") || message.includes("econnrefused");
}

// finish=length (空応答) の次手を決める。
//   { action: "step-down", variant } — 一段下げて再試行する
//   { action: "same-variant" }       — 同じ variant で再試行する (非決定性回復)
//   { action: "give-up" }            — 予算を使い切った (呼び出し側は業務エラーとして送出する)
export function planLengthRetry(variant, lengthRetriesUsed, maxLengthRetries = MAX_LENGTH_RETRIES) {
  if (lengthRetriesUsed >= maxLengthRetries) return { action: "give-up" };
  const next = VARIANT_STEP_DOWN[variant];
  if (next !== undefined) return { action: "step-down", variant: next };
  return { action: "same-variant" };
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// 接続リトライ (Issue #113) と長さリトライ (Issue #137 / #154) をまとめた実行ループ。
// runOnce / isLengthExhausted / sleepFn / log を差し替えられるようにして、sidecar 本体と
// まったく同じコードをテストから挙動で検証できるようにする (Issue #154)。
// 再試行を使い切った場合は最後のエラーをそのまま送出する (呼び出し側が業務エラーとして扱う)。
export async function runWithRetries({
  runOnce,
  initialVariant,
  isLengthExhausted = () => false,
  maxPromptAttempts = MAX_PROMPT_ATTEMPTS,
  maxLengthRetries = MAX_LENGTH_RETRIES,
  baseDelayMs = RETRY_BASE_DELAY_MS,
  sleepFn = sleep,
  log = console.error,
}) {
  let attempt = 0;
  let variant = initialVariant;
  let lengthRetries = 0;
  for (;;) {
    attempt++;
    try {
      return { text: await runOnce(variant), attempts: attempt };
    } catch (err) {
      if (isLengthExhausted(err)) {
        const plan = planLengthRetry(variant, lengthRetries, maxLengthRetries);
        if (plan.action !== "give-up") {
          if (plan.action === "step-down") {
            // high→medium→low と reasoning を下げて再試行する。
            variant = plan.variant;
            log(
              `[opencode.mjs] finish=length with empty output; retry ` +
                `${lengthRetries + 1}/${maxLengthRetries} with variant=${variant}...`
            );
          } else {
            // 既に最低段 (low / サーバー既定)。server default はむしろ reasoning が高く
            // なり得るため上げず、同じ variant で再試行する (非決定性回復, Issue #137)。
            // Issue #154: 梯子の段数に 1 を足した予算により `high` 起点でもここへ到達する。
            log(
              `[opencode.mjs] finish=length with empty output; retry ` +
                `${lengthRetries + 1}/${maxLengthRetries} (variant stays ` +
                `${variant ?? "server default"})...`
            );
          }
          lengthRetries++;
          attempt = 0; // 接続リトライ回数も振り直す
          continue;
        }
      }
      if (isRetryableError(err) && attempt < maxPromptAttempts) {
        const delay = baseDelayMs * attempt;
        log(
          `[opencode.mjs] attempt ${attempt}/${maxPromptAttempts} failed ` +
            `(${err.message}); retrying in ${delay}ms...`
        );
        await sleepFn(delay);
        continue;
      }
      throw err;
    }
  }
}
