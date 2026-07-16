const statusLabels: Record<string, string> = {
  pending: "Ожидает обработки",
  validated: "Проверен",
  invalid: "Некорректен",
  normalized: "Нормализован",
  queued: "В очереди",
  running: "Выполняется",
  completed: "Завершён",
  failed: "Ошибка",
  new: "Новая",
  investigating: "В проверке",
  incident: "Инцидент",
  false_positive: "Ложное срабатывание",
  closed: "Закрыта",
  critical: "Критическая",
  high: "Высокая",
  medium: "Средняя",
  low: "Низкая",
  ready: "Готов",
  uploading: "Загружается",
  success: "Загружен",
  error: "Ошибка",
  day: "День",
  week: "Неделя",
  month: "Месяц",
  range: "Диапазон",
  all: "Все данные",
  features: "Построение признаков",
  scoring: "ML-скоринг",
  explain: "Объяснения",
  user: "Пользователь",
  host: "Хост",
};

export function statusLabel(value: string): string {
  return statusLabels[value] ?? value;
}

export function statusTone(value: string): string {
  if (["failed", "invalid", "critical"].includes(value)) return "critical";
  if (["high", "incident"].includes(value)) return "warning";
  if (["normalized", "completed", "closed", "low"].includes(value)) return "completed";
  if (["queued", "running", "medium", "investigating"].includes(value)) return "running";
  return "neutral";
}
