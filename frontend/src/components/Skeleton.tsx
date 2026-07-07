export function Skeleton({ className = '', style }: { className?: string; style?: React.CSSProperties }) {
  return (
    <div
      className={`animate-pulse rounded bg-surface-hover ${className}`}
      style={style}
    />
  );
}

export function CardSkeleton() {
  return (
    <div className="card p-4 space-y-3">
      <Skeleton className="h-3 w-24" />
      <Skeleton className="h-8 w-16" />
      <Skeleton className="h-3 w-32" />
    </div>
  );
}

export function TableRowSkeleton() {
  return (
    <div className="flex items-center justify-between p-3 rounded-lg border bg-bg border-border">
      <div className="space-y-2 flex-1">
        <Skeleton className="h-4 w-3/5" />
        <Skeleton className="h-3 w-2/5" />
      </div>
      <div className="flex items-center gap-3 ml-3">
        <Skeleton className="h-4 w-8" />
        <Skeleton className="h-5 w-16 rounded-full" />
      </div>
    </div>
  );
}

export function ChartSkeleton({ height = 250 }: { height?: number }) {
  return (
    <div className="card p-5">
      <Skeleton className="h-5 w-48 mb-4" />
      <Skeleton className="w-full rounded" style={{ height }} />
    </div>
  );
}
