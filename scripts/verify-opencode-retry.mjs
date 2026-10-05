// opencode sidecar のリトライ挙動を検証する (Issue #154)。
//
// 配布物そのもの (ame_ai_review_system/engines/ts/retry.mjs) を import し、実際の実行ループ
// (runWithRetries) を差し替え可能な依存で駆動する。SDK もネットワークも使わないため、
// CI でもそのまま動く。
//
// 使い方: node scripts/verify-opencode-retry.mjs
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  MAX_LENGTH_RETRIES,
  MAX_PROMPT_ATTEMPTS,
  RETRY_BASE_DELAY_MS,
  isRetryableError,
  runWithRetries,
} from "../ame_ai_review_system/engines/ts/retry.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const sidecarPath = join(here, "..", "ame_ai_review_system", "engines", "ts", "opencode.mjs");

let checks = 0;
function ok(label) {
  checks++;
  console.log(`ok ${checks} - ${label}`);
}

// --- 接続系: cause.code の許可リストだけで再試行する -------------------------------
const TRANSIENT = [
  "ECONNREFUSED",
  "ECONNRESET",
  "ETIMEDOUT",
  "EPIPE",
  "EAI_AGAIN",
  "UND_ERR_CONNECT_TIMEOUT",
  "UND_ERR_HEADERS_TIMEOUT",
  "UND_ERR_SOCKET",
];
for (const code of TRANSIENT) {
  assert.equal(isRetryableError({ cause: { code } }), true, `cause.code=${code}`);
  assert.equal(isRetryableError({ code }), true, `code=${code}`);
}
ok(`一時的なコード ${TRANSIENT.length} 種を再試行対象にする`);

// 恒久エラーは再試行しない。文言 "fetch failed" だけでは再試行しない (Issue #154)。
assert.equal(
  isRetryableError({ message: "fetch failed", cause: { code: "CERT_HAS_EXPIRED" } }),
  false
);
assert.equal(isRetryableError({ message: "fetch failed" }), false);
assert.equal(isRetryableError({ cause: { code: "ENOTFOUND" } }), false);
assert.equal(isRetryableError({ message: "length limit reached" }), false);
assert.equal(isRetryableError(undefined), false);
ok("恒久エラー (証明書・名前解決失敗) と素の fetch failed は再試行しない");

// コードが取れない場合の保険は、一時的と分かる文言だけ。
assert.equal(isRetryableError({ message: "Headers Timeout Error" }), true);
assert.equal(isRetryableError({ message: "connect ECONNREFUSED 127.0.0.1:4096" }), true);
ok("コードが無い場合も一時的な文言だけを拾う");

// localhost のように接続先が複数あると undici は AggregateError を返し、cause.code は
// undefined になる (個々の失敗は cause.errors[])。ここを取りこぼすと Issue #113 の
// サーバー未起動回復が退行する。
const AGGREGATE_REFUSED = Object.assign(new Error("fetch failed"), {
  cause: Object.assign(new AggregateError([], "all failed"), {
    errors: [
      Object.assign(new Error("connect ECONNREFUSED ::1:4096"), {
        code: "ECONNREFUSED",
      }),
      Object.assign(new Error("connect ECONNREFUSED 127.0.0.1:4096"), {
        code: "ECONNREFUSED",
      }),
    ],
  }),
});
assert.equal(isRetryableError(AGGREGATE_REFUSED), true, "AggregateError の各失敗");
assert.equal(isRetryableError({ cause: { cause: { code: "ECONNRESET" } } }), true);
ok("AggregateError と入れ子の cause も走査する");

// 逆に、恒久エラーが混ざっていれば再試行しない (回復しない失敗を繰り返さない)。
assert.equal(
  isRetryableError({
    code: "UND_ERR_SOCKET",
    cause: { code: "CERT_HAS_EXPIRED" },
  }),
  false
);
assert.equal(
  isRetryableError({
    cause: { errors: [{ code: "ECONNREFUSED" }, { code: "CERT_HAS_EXPIRED" }] },
  }),
  false
);
ok("恒久エラーが混ざるチェーンは再試行しない");

// 深さ上限 (4 段) の境界を両側から押さえる。
function nest(code, levels) {
  let node = { code };
  for (let i = 0; i < levels; i++) node = { cause: node };
  return node;
}

// ちょうど 4 段 (実形状と同じ深さ) のコードは判定に使う。
assert.equal(isRetryableError(nest("ECONNRESET", 4)), true, "4 段目は判定に使う");
ok("ちょうど上限 (4 段) のコードは判定に使う");

// 上限を超える分は判定に使わず、再試行しない (実形状では起きない病的な入れ子)。
assert.equal(isRetryableError(nest("ECONNRESET", 5)), false, "5 段目は判定に使わない");
ok("深さ上限を超える入れ子は再試行しない (上限の根拠は実形状の 4 段)");

// --- 長さ系: 実際のループを駆動して、試された variant を観測する -------------------
const LENGTH_EXHAUSTED = new Error("length exhausted");

async function driveLengthFailure(initialVariant) {
  const tried = [];
  const logs = [];
  let raised = null;
  try {
    await runWithRetries({
      initialVariant,
      runOnce: (variant) => {
        tried.push(variant);
        throw LENGTH_EXHAUSTED;
      },
      isLengthExhausted: (err) => err === LENGTH_EXHAUSTED,
      sleepFn: () => Promise.resolve(),
      log: (message) => logs.push(String(message)),
    });
  } catch (err) {
    raised = err;
  }
  return { tried, logs, raised };
}

const LADDER_CASES = [
  ["high", ["high", "medium", "low", "low"]],
  ["medium", ["medium", "low", "low", "low"]],
  ["low", ["low", "low", "low", "low"]],
  [undefined, [undefined, undefined, undefined, undefined]],
];
for (const [initial, expected] of LADDER_CASES) {
  const { tried, logs, raised } = await driveLengthFailure(initial);
  assert.deepEqual(tried, expected, `起点 ${String(initial)} の試行順`);
  assert.equal(raised, LENGTH_EXHAUSTED, "使い切ったら業務エラーとして送出する");
  assert.equal(logs.length, MAX_LENGTH_RETRIES, "再試行のたびに理由を 1 行出す");
}
ok("起点に関わらず最深段で同一 variant を再試行し、使い切ったら送出する");
ok("high 起点の試行順は high→medium→low→low (Issue #154 の再現条件)");

// --- 接続系: 実際のループで再試行と打ち切りを観測する -----------------------------
const TRANSIENT_ERROR = Object.assign(new Error("connect ECONNREFUSED"), {
  cause: { code: "ECONNREFUSED" },
});
const PERMANENT_ERROR = Object.assign(new Error("fetch failed"), {
  cause: { code: "CERT_HAS_EXPIRED" },
});

async function driveConnection({ failures, error }) {
  const delays = [];
  let calls = 0;
  let raised = null;
  let result = null;
  try {
    result = await runWithRetries({
      initialVariant: "low",
      runOnce: () => {
        calls++;
        if (calls <= failures) throw error;
        return "review text";
      },
      sleepFn: (ms) => {
        delays.push(ms);
        return Promise.resolve();
      },
      log: () => {},
    });
  } catch (err) {
    raised = err;
  }
  return { calls, delays, raised, result };
}

const recovered = await driveConnection({ failures: 2, error: TRANSIENT_ERROR });
assert.equal(recovered.calls, 3);
assert.deepEqual(recovered.delays, [RETRY_BASE_DELAY_MS, RETRY_BASE_DELAY_MS * 2]);
assert.equal(recovered.result.text, "review text");
ok("一時的な接続エラーはバックオフ付きで再試行して成功する");

const exhausted = await driveConnection({ failures: 99, error: TRANSIENT_ERROR });
assert.equal(exhausted.calls, MAX_PROMPT_ATTEMPTS);
assert.equal(exhausted.raised, TRANSIENT_ERROR);
ok(`一時的な失敗が続く場合は ${MAX_PROMPT_ATTEMPTS} 回で打ち切る`);

const permanent = await driveConnection({ failures: 1, error: PERMANENT_ERROR });
assert.equal(permanent.calls, 1, "恒久エラーは 1 回で諦める");
assert.equal(permanent.raised, PERMANENT_ERROR);
ok("恒久エラーは再試行せず即座に送出する");

// サーバー未起動 (AggregateError) でもループが再試行し、起動後に回復すること。
const aggregateRecovered = await driveConnection({
  failures: 1,
  error: AGGREGATE_REFUSED,
});
assert.equal(aggregateRecovered.calls, 2);
assert.equal(aggregateRecovered.result.text, "review text");
ok("サーバー未起動 (AggregateError) から回復する");

// --- 配線: sidecar 本体が方針モジュールのループを使っている (最小限のスモークチェック) ---
const sidecar = await readFile(sidecarPath, "utf8");
assert.match(sidecar, /runWithRetries\(\{/);
assert.doesNotMatch(sidecar, /message\.includes\("fetch failed"\)/);
ok("sidecar 本体が retry.mjs のループを呼んでいる");

assert.ok(MAX_LENGTH_RETRIES > 2, "梯子 (2 段) では最深段の再試行に到達しない");
ok(`長さリトライの予算は ${MAX_LENGTH_RETRIES} 回`);

console.log(`\n1..${checks}`);
console.log("opencode sidecar のリトライ挙動は期待どおりです。");
