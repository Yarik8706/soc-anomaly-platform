import { AnomalyWorkspace } from "@/features/anomalies/anomaly-workspace";
import { parseAnomalyFilters } from "@/features/anomalies/query";

export default async function AnomaliesPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const filters = parseAnomalyFilters(await searchParams);
  return <AnomalyWorkspace key={JSON.stringify(filters)} initialFilters={filters} />;
}
