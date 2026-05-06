// Section Skeleton — Phase 5A Loading Fallback
// Shimmer placeholder for lazy-loaded sections

export function SectionSkeleton() {
  return (
    <div className="bg-surface-1 border border-border p-4 animate-pulse">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="h-5 w-32 bg-surface-2 rounded" />
        <div className="h-4 w-16 bg-surface-2 rounded" />
      </div>

      {/* Content blocks */}
      <div className="space-y-3">
        <div className="h-4 w-full bg-surface-2 rounded" />
        <div className="h-4 w-3/4 bg-surface-2 rounded" />
        <div className="h-4 w-5/6 bg-surface-2 rounded" />
      </div>

      {/* Grid placeholder */}
      <div className="grid grid-cols-3 gap-3 mt-4">
        <div className="h-16 bg-surface-2 rounded" />
        <div className="h-16 bg-surface-2 rounded" />
        <div className="h-16 bg-surface-2 rounded" />
      </div>
    </div>
  );
}

// Compact skeleton for smaller sections
export function CompactSkeleton() {
  return (
    <div className="bg-surface-1 border border-border p-3 animate-pulse">
      <div className="h-4 w-24 bg-surface-2 rounded mb-3" />
      <div className="h-12 bg-surface-2 rounded" />
    </div>
  );
}
