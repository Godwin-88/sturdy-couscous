export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`skeleton ${className}`} />;
}

export function MetricSkeleton() {
  return (
    <div className="metric">
      <Skeleton className="skeleton-text" />
      <Skeleton className="skeleton-text" />
    </div>
  );
}

export function CardSkeleton() {
  return (
    <div className="card">
      <Skeleton className="skeleton-title" />
      <div className="metric-grid">
        {Array.from({ length: 4 }).map((_, i) => (
          <MetricSkeleton key={i} />
        ))}
      </div>
    </div>
  );
}
