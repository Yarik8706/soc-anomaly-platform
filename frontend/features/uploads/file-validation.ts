export const MAX_FILE_SIZE = 50 * 1024 * 1024;
export const MAX_BATCH_SIZE = 10;
const allowedExtensions = new Set(["csv", "tsv", "txt"]);

export function validateUploadFile(file: File): string | null {
  const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
  if (!allowedExtensions.has(extension)) return "Поддерживаются только CSV, TSV и TXT";
  if (file.size === 0) return "Файл пуст";
  if (file.size > MAX_FILE_SIZE) return "Файл превышает лимит 50 МиБ";
  return null;
}

export function mergeUploadFiles(current: File[], incoming: File[]): File[] {
  const keyed = new Map(
    current.map((file) => [`${file.name}:${file.size}:${file.lastModified}`, file]),
  );
  incoming.forEach((file) => keyed.set(`${file.name}:${file.size}:${file.lastModified}`, file));
  return [...keyed.values()].slice(0, MAX_BATCH_SIZE);
}
