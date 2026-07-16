import type { AnalysisScope } from "@/lib/api/types";

export interface RunFormValues {
  scope: AnalysisScope;
  targetDate: string;
  startDate: string;
  endDate: string;
  uploadIds: string[];
  nEstimators: number;
  topN: number;
}

export function validateRun(values: RunFormValues): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!values.uploadIds.length) errors.uploadIds = "Выберите минимум один нормализованный файл";
  if (["day", "week", "month"].includes(values.scope) && !values.targetDate)
    errors.targetDate = "Укажите опорную дату";
  if (values.scope === "range") {
    if (!values.startDate) errors.startDate = "Укажите начало диапазона";
    if (!values.endDate) errors.endDate = "Укажите конец диапазона";
    if (values.startDate && values.endDate && values.startDate > values.endDate)
      errors.endDate = "Конец диапазона должен быть не раньше начала";
  }
  if (values.nEstimators < 10 || values.nEstimators > 1000)
    errors.nEstimators = "Допустимо от 10 до 1000 деревьев";
  if (values.topN < 1 || values.topN > 500) errors.topN = "Допустимо от 1 до 500 результатов";
  return errors;
}
