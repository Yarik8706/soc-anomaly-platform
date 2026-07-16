import type { Histogram } from "@/lib/api/types";

export interface HistogramPoint {
  label: string;
  count: number;
  height: number;
}

export function histogramPoints(histogram: Histogram): HistogramPoint[] {
  const max = Math.max(...histogram.counts, 0);
  return histogram.counts.map((count, index) => ({
    label: `${formatEdge(histogram.bin_edges[index])}–${formatEdge(histogram.bin_edges[index + 1])}`,
    count,
    height: max ? (count / max) * 100 : 0,
  }));
}

function formatEdge(value: number | undefined): string {
  return value === undefined ? "?" : Number(value.toFixed(3)).toString();
}

export function metricValue(value: number | null): string {
  return value === null ? "Недостаточно данных" : value.toFixed(3);
}
