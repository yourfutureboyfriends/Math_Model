
// Skeleton Loading Components — Phase 8 UI Polish
// Shimmer loading states for all data panels


import { cn } from '@/lib/utils'

// Base skeleton block
interface SkeletonProps {
  className?: string
  width?: string | number
  height?: string | number
}

export function Skeleton({ className, width, height }: SkeletonProps) {
  return (
    <div
      className={cn('skeleton', className)}
      style={{ width, height }}
    />
  )
}

// Skeleton text line
export function SkeletonText({ className, width = '100%' }: SkeletonProps) {
  return <Skeleton className={cn('skeleton-text', className)} width={width} />
}

// Skeleton value (for metrics)
export function SkeletonValue({ className }: { className?: string }) {
  return <Skeleton className={cn('skeleton-value', className)} />
}

// Skeleton KPI card
interface SkeletonKPIProps {
  count?: number
}

export function SkeletonKPI({ count = 4 }: SkeletonKPIProps) {
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="terminal-card">
          <SkeletonText width="60%" />
          <div className="mt-2">
            <SkeletonValue />
          </div>
          <SkeletonText width="40%" className="mt-2" />
        </div>
      ))}
    </div>
  )
}

// Skeleton table row
interface SkeletonRowProps {
  cols?: number
}

export function SkeletonRow({ cols = 4 }: SkeletonRowProps) {
  return (
    <div className="flex gap-3 py-2">
      {Array.from({ length: cols }).map((_, i) => (
        <Skeleton
          key={i}
          className="skeleton-text"
          width={i === 0 ? '40%' : `${60 / (cols - 1)}%`}
        />
      ))}
    </div>
  )
}

// Skeleton table
interface SkeletonTableProps {
  rows?: number
  cols?: number
  showHeader?: boolean
}

export function SkeletonTable({
  rows = 5,
  cols = 4,
  showHeader = true,
}: SkeletonTableProps) {
  return (
    <div className="w-full">
      {showHeader && (
        <div className="flex gap-3 py-2 border-b border-border">
          {Array.from({ length: cols }).map((_, i) => (
            <Skeleton
              key={i}
              className="skeleton-text"
              width={i === 0 ? '40%' : `${60 / (cols - 1)}%`}
            />
          ))}
        </div>
      )}
      {Array.from({ length: rows }).map((_, i) => (
        <SkeletonRow key={i} cols={cols} />
      ))}
    </div>
  )
}

// Skeleton signal stack
interface SkeletonSignalStackProps {
  rows?: number
}

export function SkeletonSignalStack({ rows = 10 }: SkeletonSignalStackProps) {
  return (
    <div className="space-y-1">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-3 py-2">
          <Skeleton className="skeleton-text" width="30%" />
          <Skeleton className="skeleton-text flex-1" />
          <Skeleton className="skeleton-text" width="60px" />
        </div>
      ))}
    </div>
  )
}

// Skeleton chart
export function SkeletonChart({ className }: { className?: string }) {
  return <Skeleton className={cn('skeleton-chart', className)} />
}

// Skeleton card
export function SkeletonCard({ className }: { className?: string }) {
  return (
    <div className={cn('terminal-card', className)}>
      <SkeletonText width="40%" />
      <Skeleton className="skeleton-chart mt-4" />
      <div className="flex gap-3 mt-4">
        <Skeleton className="skeleton-text flex-1" />
        <Skeleton className="skeleton-text flex-1" />
      </div>
    </div>
  )
}

// Full page skeleton for section loading
export function SkeletonSection({ title: _title }: { title?: string }) {
  return (
    <div className="terminal-section animate-pulse">
      <div className="section-header">
        <div className="section-header-left">
          <Skeleton className="skeleton-text" width="24px" />
          <Skeleton className="skeleton-text" width="150px" />
        </div>
      </div>
      <div className="p-4">
        <SkeletonTable rows={6} cols={4} />
      </div>
    </div>
  )
}

// Simple section skeleton with label
export function SectionSkeleton({ label }: { label: string }) {
  return (
    <section className="terminal-section">
      <div className="section-header mb-3">
        <div className="section-header-left">
          <Skeleton className="skeleton-text" width="32px" />
          <h2 className="section-title">{label}</h2>
        </div>
      </div>
      <div className="p-4 bg-surface-1 border border-border">
        <SkeletonTable rows={4} cols={3} />
      </div>
    </section>
  )
}
