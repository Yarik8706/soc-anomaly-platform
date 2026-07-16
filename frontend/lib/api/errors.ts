export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly detail: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function errorMessage(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => (typeof item === "object" && item && "msg" in item ? String(item.msg) : null))
      .filter(Boolean);
    if (messages.length) return messages.join(". ");
  }
  if (typeof detail === "object" && detail) {
    if ("errors" in detail && Array.isArray(detail.errors)) {
      return detail.errors.map(String).join(". ");
    }
    if ("detail" in detail) return errorMessage(detail.detail);
  }
  return "Не удалось выполнить запрос";
}
