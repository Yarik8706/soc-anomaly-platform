import { describe, expect, it } from "vitest";
import { histogramPoints, metricValue } from "./histogram";

describe("metrics presentation", () => {
  it("normalizes histogram bars relative to the maximum", () => {
    expect(histogramPoints({ bin_edges: [0, 0.5, 1], counts: [2, 4] })).toEqual([
      { label: "0–0.5", count: 2, height: 50 },
      { label: "0.5–1", count: 4, height: 100 },
    ]);
  });
  it("does not present missing stability as zero", () => {
    expect(metricValue(null)).toBe("Недостаточно данных");
  });
});
