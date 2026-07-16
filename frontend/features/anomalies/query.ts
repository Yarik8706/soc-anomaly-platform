import type { AnomalyStatus, EntityType, Severity } from "@/lib/api/types";

export type AnomalySort = "rank" | "score_desc" | "score_asc" | "date_desc";

export interface AnomalyFilters {
  run_id: string;
  date_from: string;
  date_to: string;
  entity_type: "" | EntityType;
  severity: "" | Severity;
  workflow_status: "" | AnomalyStatus;
  sort: AnomalySort;
  offset: number;
  limit: number;
}

const entities = new Set(["user", "host"]);
const severities = new Set(["critical", "high", "medium", "low"]);
const statuses = new Set(["new", "investigating", "incident", "false_positive", "closed"]);
const sorts = new Set(["rank", "score_desc", "score_asc", "date_desc"]);

function scalar(value: string | string[] | undefined): string {
  return Array.isArray(value) ? (value[0] ?? "") : (value ?? "");
}

function allowed<T extends string>(value: string, values: Set<string>, fallback: T): T {
  return (values.has(value) ? value : fallback) as T;
}

export function parseAnomalyFilters(
  params: Record<string, string | string[] | undefined>,
): AnomalyFilters {
  const rawOffset = Number.parseInt(scalar(params.offset), 10);
  const rawLimit = Number.parseInt(scalar(params.limit), 10);
  return {
    run_id: scalar(params.run_id),
    date_from: scalar(params.date_from),
    date_to: scalar(params.date_to),
    entity_type: allowed(scalar(params.entity_type), entities, ""),
    severity: allowed(scalar(params.severity), severities, ""),
    workflow_status: allowed(scalar(params.workflow_status), statuses, ""),
    sort: allowed(scalar(params.sort), sorts, "rank"),
    offset: Number.isFinite(rawOffset) && rawOffset > 0 ? rawOffset : 0,
    limit: [20, 50, 100].includes(rawLimit) ? rawLimit : 20,
  };
}

export function anomalyFilterQuery(filters: AnomalyFilters): string {
  const query = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (
      value !== "" &&
      !(key === "offset" && value === 0) &&
      !(key === "sort" && value === "rank")
    ) {
      query.set(key, String(value));
    }
  });
  return query.toString();
}

export function statusCommentError(status: AnomalyStatus, comment: string): string | null {
  if (["incident", "false_positive", "closed"].includes(status) && !comment.trim()) {
    return "Добавьте комментарий, чтобы решение осталось проверяемым.";
  }
  return null;
}
