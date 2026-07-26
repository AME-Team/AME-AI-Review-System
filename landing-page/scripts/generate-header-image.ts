import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { getStaticHeaderImageSvgFile } from "../src/assets/headerImage.ts";

// README.md / landing-page/README.md embed this file directly via GitHub's Markdown
// image syntax, so it must exist as a static file — but its content is generated
// from the same template as the live app to guarantee the two never drift apart.
// Run via tsx (not plain `node`): CI/dev pins Node 22, which can't import a .ts
// module without a flag, so a plain Node script would fail for anyone running it.
// Regenerate with: npm run generate:header-image
const outPath = fileURLToPath(new URL("../src/assets/header-image.svg", import.meta.url));
writeFileSync(outPath, getStaticHeaderImageSvgFile());
console.log(`Wrote ${outPath}`);
