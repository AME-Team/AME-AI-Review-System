// OpenCode SDK (TypeScript) サイドカー。
// stdin: プロンプト / stdout: レビュー結果テキスト / stderr: ログ。
// ame-review init が .ame-review/engines-ts/ へこのファイルと package.json を配置し
// npm ci で @opencode-ai/sdk を導入する (ESM 解決のため隣接 node_modules が必要)。
// モデルは provider/model 形式 (例: anthropic/claude-sonnet-4) を指定すること。

import { createOpencode } from "@opencode-ai/sdk";

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

async function main() {
  const prompt = await readStdin();
  if (!prompt.trim()) {
    console.error("[opencode.mjs] empty prompt on stdin");
    process.exit(1);
  }
  const opts = parseArgs();
  // opencode SDK の Config は reasoning を boolean で扱う (minimal/medium/high には非対応)。
  // minimal (= thinking low) 以外は reasoning を有効にして、設定契約が黙殺されないようにする。
  const config = {};
  if (opts.model) config.model = opts.model;
  if (opts.variant) config.reasoning = opts.variant !== "minimal";

  const { client } = await createOpencode({ config });
  const session = await client.session.create({ body: { title: "ame-review" } });
  const result = await client.session.prompt({
    path: { id: session.id },
    body: { parts: [{ type: "text", text: prompt }] },
  });

  const text = extractText(result && result.data);
  if (!text.trim()) {
    console.error("[opencode.mjs] could not extract text from response");
    process.exit(1);
  }
  process.stdout.write(text);
}

main().catch((err) => {
  console.error("[opencode.mjs]", err);
  process.exit(1);
});
