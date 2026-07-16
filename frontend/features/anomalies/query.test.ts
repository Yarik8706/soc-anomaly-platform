import { describe, expect, it } from "vitest";
import { anomalyFilterQuery, parseAnomalyFilters, statusCommentError } from "./query";

describe("anomaly query", () => {
  it("normalizes unsupported filters and pagination", () => {
    expect(parseAnomalyFilters({ severity: "urgent", offset: "-2", limit: "999" })).toMatchObject({
      severity: "",
      offset: 0,
      limit: 20,
      sort: "rank",
    });
  });

  it("keeps meaningful filters in a shareable query", () => {
    const filters = parseAnomalyFilters({ severity: "high", entity_type: "host", offset: "20" });
    expect(anomalyFilterQuery(filters)).toContain("severity=high");
    expect(anomalyFilterQuery(filters)).toContain("offset=20");
  });

  it("requires an audit comment for terminal decisions", () => {
    expect(statusCommentError("incident", " ")).toBeTruthy();
    expect(statusCommentError("investigating", "")).toBeNull();
  });
});
