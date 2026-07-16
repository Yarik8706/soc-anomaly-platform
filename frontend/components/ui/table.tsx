import type { HTMLAttributes, TableHTMLAttributes } from "react";

export function Table({ className = "", ...props }: TableHTMLAttributes<HTMLTableElement>) {
  return (
    <div className="table-scroll" tabIndex={0}>
      <table className={`data-table ${className}`.trim()} {...props} />
    </div>
  );
}

export function TableToolbar({ className = "", ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={`table-toolbar ${className}`.trim()} {...props} />;
}
