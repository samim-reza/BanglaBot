import { ReactNode } from "react";

/** Illustrated empty state used inside tables and lists. */
export default function EmptyState({
  art,
  title,
  hint,
  action,
}: {
  art: ReactNode;
  title: string;
  hint?: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      {art}
      <p className="empty-title">{title}</p>
      {hint && <p className="muted">{hint}</p>}
      {action}
    </div>
  );
}
