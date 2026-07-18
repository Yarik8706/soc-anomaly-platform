import { describe, expect, it } from "vitest";
import {
  MAX_BATCH_SIZE,
  MAX_FILE_SIZE,
  mergeUploadFiles,
  validateUploadFile,
} from "./file-validation";

describe("upload file validation", () => {
  it("accepts supported files and rejects unsupported or empty files", () => {
    expect(validateUploadFile(new File(["a,b\n1,2"], "events.csv"))).toBeNull();
    expect(validateUploadFile(new File(["value"], "events.json"))).toContain("CSV");
    expect(validateUploadFile(new File([], "empty.tsv"))).toBe("Файл пуст");
  });

  it("accepts files up to 200 MiB", () => {
    expect(MAX_FILE_SIZE).toBe(200 * 1024 * 1024);
    expect(validateUploadFile({ name: "events.csv", size: MAX_FILE_SIZE } as File)).toBeNull();
    expect(
      validateUploadFile({ name: "events.csv", size: MAX_FILE_SIZE + 1 } as File),
    ).toBe("Файл превышает лимит 200 МиБ");
  });

  it("deduplicates and limits a batch", () => {
    const files = Array.from(
      { length: MAX_BATCH_SIZE + 2 },
      (_, index) => new File([String(index)], `file-${index}.csv`, { lastModified: index }),
    );
    expect(mergeUploadFiles([files[0]], files)).toHaveLength(MAX_BATCH_SIZE);
  });
});
