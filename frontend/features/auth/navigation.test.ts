import { describe, expect, it } from "vitest";
import { safeReturnTo } from "./navigation";

describe("safeReturnTo", () => {
  it("keeps local application paths", () => {
    expect(safeReturnTo("/anomalies?severity=high")).toBe("/anomalies?severity=high");
  });
  it("rejects external and protocol-relative redirects", () => {
    expect(safeReturnTo("https://evil.example")).toBe("/");
    expect(safeReturnTo("//evil.example")).toBe("/");
  });
});
