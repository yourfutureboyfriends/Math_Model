// Phase 2 — Terminal Card Component
// Clean panel container with terminal aesthetic

import { cn } from '@/lib/utils';

interface CardProps {
  title?: string;
  /** Optional content rendered on the right of the title bar (e.g. a SourceTag). */
  headerRight?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  loading?: boolean;
}

export function Card({ title, headerRight, children, className, loading }: CardProps) {
  return (
    <div
      className={cn(
        'bg-surface-1 border border-border',
        className
      )}
    >
      {(title || headerRight) && (
        <div className="px-3 py-1.5 bg-surface-2 border-b border-border-subtle flex items-center justify-between gap-2">
          <h3 className="text-2xs font-medium text-text-tertiary uppercase tracking-wider">
            {title}
          </h3>
          {headerRight}
        </div>
      )}
      <div className="p-3">
        {loading ? (
          <div className="space-y-2">
            <div className="h-3 bg-surface-3 animate-pulse" />
            <div className="h-6 bg-surface-3 animate-pulse" />
            <div className="h-3 bg-surface-3 animate-pulse w-2/3" />
          </div>
        ) : (
          children
        )}
      </div>
    </div>
  );
}

// Sub-components for compound pattern
export function CardHeader({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={cn('px-3 py-2 bg-surface-2 border-b border-border-subtle', className)}>
      {children}
    </div>
  );
}

export function CardTitle({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <h3 className={cn('text-2xs font-medium text-text-tertiary uppercase tracking-wider', className)}>
      {children}
    </h3>
  );
}

export function CardContent({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={cn('p-3', className)}>
      {children}
    </div>
  );
}
