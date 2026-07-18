import { describe, expect, it } from "vitest";
import { validateRun, type RunFormValues } from "./run-validation";

const base: RunFormValues = {
  scope: "day",
  targetDate: "2026-07-15",
  startDate: "",
  endDate: "",
  uploadIds: ["id"],
  mode: "full",
  nEstimators: 100,
  topN: 20,
  contamination: 0.05,
  nNeighbors: 20,
  randomState: 42,
  maxSamples: "auto",
  topFeatures: 5,
  topPct: 0.05,
};

describe("run validation", () => {
  it("validates scope dates and upload selection", () => {
    expect(validateRun(base)).toEqual({});
    expect(validateRun({ ...base, uploadIds: [], targetDate: "" })).toMatchObject({
      uploadIds: expect.any(String),
      targetDate: expect.any(String),
    });
    expect(
      validateRun({ ...base, scope: "range", startDate: "2026-07-20", endDate: "2026-07-10" }),
    ).toHaveProperty("endDate");
  });

  it("validates the extended model configuration", () => {
    expect(
      validateRun({
        ...base,
        contamination: 0,
        nNeighbors: 0,
        maxSamples: "1.5",
        topFeatures: 0,
        topPct: 2,
      }),
    ).toMatchObject({
      contamination: expect.any(String),
      nNeighbors: expect.any(String),
      maxSamples: expect.any(String),
      topFeatures: expect.any(String),
      topPct: expect.any(String),
    });
  });
});
