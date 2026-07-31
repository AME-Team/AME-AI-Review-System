// OpenCode SDK (TypeScript) サイドカー。起動済み OpenCode サーバへ SDK で接続する。
// stdin: プロンプト / stdout: レビュー結果テキスト / stderr: ログ。
// サーバは別プロセスで起動されていること (ame-review は接続のみ; 認証は OPENCODE_URL で指定)。
//   OPENCODE_URL : 接続先 (既定 http://127.0.0.1:4096)。`opencode serve` 等で起動済みであること。
//   OPENCODE_PASSWORD / OPENCODE_SERVER_PASSWORD : Basic 認証パスワード (serve 無認証時は不要)。
// ame-review init が .ame-review/engines-ts/ へこのファイルと package.json を配置し
// npm ci で @opencode-ai/sdk を導入する (ESM 解決のため隣接 node_modules が必要)。
// モデルは provider/model 形式 (例: anthropic/claude-sonnet-4) を指定すること。

import { createOpencodeClient } from "@opencode-ai/sdk";

function parseArgs() {
  const args = process.argv.slice(2);
  const opts = {};
  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--model") opts.model = args[++i];
    else if (args[i] === "--variant") opts.variant = args[++i];
  }
  return opts;
}

async function readStdin() {
  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(chunk);
  return Buffer.concat(chunks).toString("utf8");
}

function extractText(data) {
  if (!data) return "";
  if (typeof data === "string") return data;
  const parts = data.parts || (data.info && data.info.parts);
  if (Array.isArray(parts)) {
    const text = parts
      .filter((p) => p && p.type === "text" && typeof p.text === "string")
      .map((p) => p.text)
      .join("");
    if (text) return text;
  }
  const structured = data.info && data.info.structured_output;
  if (structured) return typeof structured === "string" ? structured : JSON.stringify(structured);
  return "";
}

function splitModel(model) {
  if (!model || !model.includes("/")) return undefined;
  const idx = model.indexOf("/");
  return { providerID: model.slice(0, idx), modelID: model.slice(idx + 1) };
}

async function main() {
  const prompt = await readStdin();
  if (!prompt.trim()) {
    console.error("[opencode.mjs] empty prompt on stdin");
    process.exit(1);
  }
  const opts = parseArgs();

  const url = process.env.OPENCODE_URL || "http://127.0.0.1:4096";
  const password = process.env.OPENCODE_PASSWORD || process.env.OPENCODE_SERVER_PASSWORD;
  const headers = {};
  if (password) {
    const token = Buffer.from(`opencode:${password}`).toString("base64");
    headers["authorization"] = `Basic ${token}`;
  }

  const client = createOpencodeClient({
    baseUrl: url,
    headers,
    directory: process.cwd(),
  });

  const session = await client.session.create({ body: { title: "ame-review" } });
  // session.create は { data: {...} } を返す (SDK 1.18.x)。id は data 配下にある。
  const sessionId = session?.data?.id;
  if (!sessionId) {
    console.error("[opencode.mjs] failed to obtain session id from create response");
    process.exit(1);
  }
  const model = splitModel(opts.model);
  // レビューは diff がプロンプトに埋め込まれているためツールは不要。
  // build agent が bash / 外部ディレクトリ読取等で権限確認 (external_directory: ask) に
  // ハングするのを防ぐため、ツールを明示的に全て無効化する。
  const toolsOff = {
    bash: false,
    edit: false,
    write: false,
    read: false,
    glob: false,
    grep: false,
    patch: false,
    webfetch: false,
    task: false,
    todowrite: false,
    application_launcher: false,
    question: false,
    skill: false,
  };
  const result = await client.session.prompt({
    path: { id: sessionId },
    body: {
      parts: [{ type: "text", text: prompt }],
      tools: toolsOff,
      ...(model ? { model } : {}),
    },
  });

  if (result && result.error) {
    console.error("[opencode.mjs] server error:", JSON.stringify(result.error));
    process.exit(1);
  }

  const text = extractText(result && result.data);
  if (!text.trim()) {
    console.error("[opencode.mjs] could not extract text from response");
    process.exit(1);
  }
  process.stdout.write(text);
}

main().catch((err) => {
  console.error(
    "[opencode.mjs] failed to connect to OpenCode server at",
    process.env.OPENCODE_URL || "http://127.0.0.1:4096"
  );
  console.error(err);
  process.exit(1);
});
