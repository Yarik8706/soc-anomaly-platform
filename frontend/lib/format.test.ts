import { describe, expect, it } from "vitest";
import { formatBytes, shortId } from "./format";

describe("format helpers", () => {
  it("formats binary sizes and identifiers", () => {
    expect(formatBytes(1024)).toBe("1.00 КиБ");
    expect(shortId("12345678-1234-1234")).toBe("12345678…");
  });
});
