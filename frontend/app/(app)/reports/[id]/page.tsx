import { ReportDetailView } from "@/features/reports/report-detail";

export default async function ReportDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ReportDetailView id={id} />;
}
