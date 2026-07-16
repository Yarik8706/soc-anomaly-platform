import { MetricsWorkspace } from "@/features/metrics/metrics-workspace";

export default async function MetricsPage({
  searchParams,
}: {
  searchParams: Promise<{ run_id?: string }>;
}) {
  const { run_id } = await searchParams;
  return <MetricsWorkspace key={run_id ?? "none"} selectedRun={run_id ?? ""} />;
}
