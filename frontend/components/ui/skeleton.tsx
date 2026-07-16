export function Skeleton({
  width = "100%",
  height = 18,
}: {
  width?: string | number;
  height?: string | number;
}) {
  return <span className="skeleton" aria-hidden="true" style={{ width, height }} />;
}
