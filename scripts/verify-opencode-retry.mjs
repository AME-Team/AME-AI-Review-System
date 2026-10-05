// opencode sidecar のリトライ方針を検証する (Issue #154)。
//
// 配布物そのもの (ame_ai_review_system/engines/ts/retry.mjs) を import して検証するため、
// 「方針は直ったが sidecar が使っていない」という取り違えも検出する (配線は本文の検査で確認)。
// Node だけで完結し、ネットワークにも依存しない (SDK を読み込まない純粋モジュールのため)。
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
  planLengthRetry,
} from "../ame_ai_review_system/engines/ts/retry.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const sidecarPath = join(here, "..", "ame_ai_review_system", "engines", "ts", "opencode.mjs");
const policyPath = join(here, "..", "ame_ai_review_system", "engines", "ts", "retry.mjs");

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

// コードが取れない場合の保険は、一時的と分かる文言だけ (headers timeout / econnrefused)。
assert.equal(isRetryableError({ message: "Headers Timeout Error" }), true);
assert.equal(isRetryableError({ message: "connect ECONNREFUSED 127.0.0.1:4096" }), true);
ok("コードが無い場合も一時的な文言だけを拾う");

// --- 長さ系: 起点に関わらず最深段で同一 variant を試す -----------------------------
function simulate(initialVariant) {
  const tried = [];
  let variant = initialVariant;
  let used = 0;
  for (;;) {
    tried.push(variant);
    const plan = planLengthRetry(variant, used);
    if (plan.action === "give-up") break;
    if (plan.action === "step-down") variant = plan.variant;
    used++;
    assert.ok(used <= MAX_LENGTH_RETRIES, "予算を超えて再試行している");
  }
  return tried;
}

// high 起点: high→medium→low と下げたあと、最深段 (low) を同一 variant で再試行する。
assert.deepEqual(simulate("high"), ["high", "medium", "low", "low"]);
ok("high 起点でも最深段 (low) の同一 variant 再試行に到達する");

// medium 起点: 1 段下げたあと、最深段で 2 回再試行する (残余を同一 variant に使う)。
assert.deepEqual(simulate("medium"), ["medium", "low", "low", "low"]);
ok("medium 起点は最深段で残余を同一 variant に使う");

// 最深段・variant 未指定 (サーバー既定) は variant を変えずに予算を使い切る。
assert.deepEqual(simulate("low"), ["low", "low", "low", "low"]);
assert.deepEqual(simulate(undefined), [undefined, undefined, undefined, undefined]);
ok("low 起点 / サーバー既定は variant を変えない");

// 未知の variant は step down せず同一 variant で再試行する。
assert.deepEqual(simulate("xhigh"), ["xhigh", "xhigh", "xhigh", "xhigh"]);
ok("未知の variant は step down しない");

// 打ち切りは give-up を返す (呼び出し側は業務エラーとして送出する)。
assert.equal(planLengthRetry("low", MAX_LENGTH_RETRIES).action, "give-up");
assert.ok(MAX_LENGTH_RETRIES > 2, "梯子 (2 段) では最深段の再試行に到達しない");
ok(`予算 ${MAX_LENGTH_RETRIES} 回で打ち切る`);

// --- 配線: sidecar 本体が方針を使っている ---------------------------------------
const sidecar = await readFile(sidecarPath, "utf8");
assert.match(sidecar, /from "\.\/retry\.mjs"/);
assert.match(sidecar, /planLengthRetry\(variant, lengthRetries\)/);
assert.match(sidecar, /isRetryableError\(err\) && attempt < MAX_PROMPT_ATTEMPTS/);
assert.doesNotMatch(sidecar, /message\.includes\("fetch failed"\)/);
ok("sidecar 本体が retry.mjs の方針を使っている");

const policy = await readFile(policyPath, "utf8");
assert.doesNotMatch(policy, /includes\("fetch failed"\)/);
assert.match(policy, /RETRYABLE_CODES/);
ok("方針側に文言一致の fetch failed が残っていない");

// --- 既存の予算が壊れていない ---------------------------------------------------
assert.equal(MAX_PROMPT_ATTEMPTS, 3);
assert.equal(RETRY_BASE_DELAY_MS, 5000);
ok("接続リトライの予算とバックオフは据え置き");

console.log(`\n1..${checks}`);
console.log("opencode sidecar のリトライ方針は期待どおりです。");
