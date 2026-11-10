import { describe, expect, it } from "vitest";
import { MAX_CHARS, splitText } from "./chunking";

describe("splitText", () => {
  it("ignores empty documents", () => expect(splitText(" \n ")).toEqual([]));
  it("keeps paragraphs and bounds large chunks", () => {
    const chunks = splitText(`intro\n\n${"x".repeat(2200)}`);
    expect(chunks[0]).toBe("intro");
    expect(chunks.every((chunk) => chunk.length <= MAX_CHARS)).toBe(true);
    expect(chunks.length).toBeGreaterThan(2);
  });
});
