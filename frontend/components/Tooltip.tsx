import type { ReactNode } from "react";

export function Tooltip({ label, children }: { label: string; children: ReactNode }) {
  return (
    <span className="tooltip-wrap">
      <span className="tooltip-trigger" tabIndex={0} aria-label={label}>
        {children}
      </span>
      <span className="tooltip-content" role="tooltip">{label}</span>
    </span>
  );
}
