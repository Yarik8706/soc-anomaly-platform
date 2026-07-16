import { describe, expect, it } from "vitest";
import { validateRun, type RunFormValues } from "./run-validation";

const base: RunFormValues = {
  scope: "day",
  targetDate: "2026-07-15",
  startDate: "",
  endDate: "",
  uploadIds: ["id"],
  nEstimators: 100,
  topN: 20,
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
});
