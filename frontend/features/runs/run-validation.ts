import type { AnalysisScope } from "@/lib/api/types";

export interface RunFormValues {
  scope: AnalysisScope;
  targetDate: string;
  startDate: string;
  endDate: string;
  uploadIds: string[];
  mode: "report" | "metrics" | "report+metrics" | "full" | "dry-run";
  nEstimators: number;
  topN: number;
  contamination: number;
  nNeighbors: number;
  randomState: number;
  maxSamples: string;
  topFeatures: number;
  topPct: number;
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
  if (values.contamination <= 0 || values.contamination > 0.5)
    errors.contamination = "Допустимо значение больше 0 и не больше 0.5";
  if (values.nNeighbors < 1 || values.nNeighbors > 10000)
    errors.nNeighbors = "Допустимо от 1 до 10000 соседей";
  if (!Number.isInteger(values.randomState)) errors.randomState = "Укажите целое число";
  const maxSamplesNumber = Number(values.maxSamples);
  if (
    values.maxSamples.trim().toLowerCase() !== "auto" &&
    (!Number.isFinite(maxSamplesNumber) ||
      maxSamplesNumber <= 0 ||
      (maxSamplesNumber > 1 && !Number.isInteger(maxSamplesNumber)))
  )
    errors.maxSamples = "Укажите auto, положительное целое или долю от 0 до 1";
  if (values.topFeatures < 1 || values.topFeatures > 100)
    errors.topFeatures = "Допустимо от 1 до 100 признаков";
  if (values.topPct <= 0 || values.topPct > 1)
    errors.topPct = "Допустима доля больше 0 и не больше 1";
  return errors;
}
