import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { getStaticHeaderImageSvgFile } from "../src/assets/headerImage.ts";

// README.md / landing-page/README.md embed this file directly via GitHub's Markdown
// image syntax, so it must exist as a static file — but its content is generated
// from the same template as the live app to guarantee the two never drift apart.
// Regenerate with: node scripts/generate-header-image.mjs
const outPath = fileURLToPath(new URL("../src/assets/header-image.svg", import.meta.url));
writeFileSync(outPath, getStaticHeaderImageSvgFile());
console.log(`Wrote ${outPath}`);
