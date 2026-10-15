import { ChevronDown, ChevronLeft, ChevronRight } from "lucide-react";

import { Button } from "@/components/ui/button";

export function Pagination({
  page,
  pageSize,
  total,
  onChange,
}: {
  page: number;
  pageSize: number;
  total: number;
  onChange: (page: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(total, page * pageSize);
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-muted-foreground">
      <span>
        {total === 0 ? "No results" : `Showing ${from}–${to} of ${total}`}
      </span>
      <div className="flex items-center gap-2">
        <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => onChange(page - 1)}>
          <ChevronLeft className="h-3.5 w-3.5" />
          Previous
        </Button>
        <span className="tabular-nums">
          Page {page} of {pages}
        </span>
        <Button variant="outline" size="sm" disabled={page >= pages} onClick={() => onChange(page + 1)}>
          Next
          <ChevronRight className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  );
}

/** Cursor pagination: how many are shown and a "Load more" button while the server has more. */
export function LoadMore({
  shown,
  hasMore,
  loading,
  onLoadMore,
  noun = "results",
}: {
  shown: number;
  hasMore: boolean;
  loading?: boolean;
  onLoadMore: () => void;
  noun?: string;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-muted-foreground">
      <span className="tabular-nums">
        {shown === 0 ? "No results" : `Showing ${shown.toLocaleString("en-US")} ${noun}${hasMore ? "" : " · end of list"}`}
      </span>
      {hasMore && (
        <Button variant="outline" size="sm" disabled={loading} onClick={onLoadMore} aria-busy={loading}>
          <ChevronDown className="h-3.5 w-3.5" />
          {loading ? "Loading…" : "Load more"}
        </Button>
      )}
    </div>
  );
}
