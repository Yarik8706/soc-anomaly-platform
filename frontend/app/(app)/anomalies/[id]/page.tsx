import { AnomalyDetailView } from "@/features/anomalies/anomaly-detail";

export default async function AnomalyDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ back?: string }>;
}) {
  const [{ id }, { back }] = await Promise.all([params, searchParams]);
  return <AnomalyDetailView id={id} back={back} />;
}
