// Phase 2 — Terminal Badge Component
// Signal tag style badges matching terminal aesthetic

import { cn } from '@/lib/utils';

interface BadgeProps {
  children: React.ReactNode;
  variant?: 'success' | 'warning' | 'danger' | 'info' | 'neutral';
  className?: string;
}

const variantStyles = {
  success: 'bg-green-dim text-green border-green',
  warning: 'bg-amber-dim text-amber border-amber',
  danger: 'bg-red-dim text-red border-red',
  info: 'bg-blue-dim text-blue border-blue',
  neutral: 'bg-surface-3 text-text-secondary border-border-subtle',
};

export function Badge({ children, variant = 'neutral', className }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center px-1.5 py-0.5 text-2xs font-medium',
        'uppercase tracking-wider border',
        variantStyles[variant],
        className
      )}
    >
      {children}
    </span>
  );
}
