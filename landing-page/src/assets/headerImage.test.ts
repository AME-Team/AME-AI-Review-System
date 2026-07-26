import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, it, expect } from "vitest";
import { getStaticHeaderImageSvgFile } from "./headerImage";

describe("header-image.svg (static README asset)", () => {
  it("matches the generator output, so it can't silently drift from the live hero", () => {
    const filePath = path.resolve(process.cwd(), "src/assets/header-image.svg");
    const onDisk = readFileSync(filePath, "utf-8");
    expect(onDisk).toBe(getStaticHeaderImageSvgFile());
  });
});
