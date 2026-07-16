import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";

interface FieldShellProps {
  label: string;
  htmlFor: string;
  hint?: string;
  error?: string;
  children: ReactNode;
}

function FieldShell({ label, htmlFor, hint, error, children }: FieldShellProps) {
  const messageId = `${htmlFor}-message`;
  return (
    <div className="field">
      <label htmlFor={htmlFor}>{label}</label>
      {children}
      {error ? (
        <p id={messageId} className="field-error">
          {error}
        </p>
      ) : hint ? (
        <p id={messageId} className="field-hint">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

export function Input({
  label,
  hint,
  error,
  id,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  hint?: string;
  error?: string;
  id: string;
}) {
  return (
    <FieldShell label={label} htmlFor={id} hint={hint} error={error}>
      <input
        id={id}
        className="control"
        aria-invalid={Boolean(error)}
        aria-describedby={error || hint ? `${id}-message` : undefined}
        {...props}
      />
    </FieldShell>
  );
}

export function Select({
  label,
  hint,
  error,
  id,
  children,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement> & {
  label: string;
  hint?: string;
  error?: string;
  id: string;
}) {
  return (
    <FieldShell label={label} htmlFor={id} hint={hint} error={error}>
      <select
        id={id}
        className="control"
        aria-invalid={Boolean(error)}
        aria-describedby={error || hint ? `${id}-message` : undefined}
        {...props}
      >
        {children}
      </select>
    </FieldShell>
  );
}
