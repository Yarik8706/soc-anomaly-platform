import { describe, expect, it } from "vitest";
import { MAX_BATCH_SIZE, mergeUploadFiles, validateUploadFile } from "./file-validation";

describe("upload file validation", () => {
  it("accepts supported files and rejects unsupported or empty files", () => {
    expect(validateUploadFile(new File(["a,b\n1,2"], "events.csv"))).toBeNull();
    expect(validateUploadFile(new File(["value"], "events.json"))).toContain("CSV");
    expect(validateUploadFile(new File([], "empty.tsv"))).toBe("Файл пуст");
  });

  it("deduplicates and limits a batch", () => {
    const files = Array.from(
      { length: MAX_BATCH_SIZE + 2 },
      (_, index) => new File([String(index)], `file-${index}.csv`, { lastModified: index }),
    );
    expect(mergeUploadFiles([files[0]], files)).toHaveLength(MAX_BATCH_SIZE);
  });
});
