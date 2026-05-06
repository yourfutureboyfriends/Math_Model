// Standardized Loading State Component
// Use this for all section loading states

import { Loader2 } from 'lucide-react';

interface LoadingStateProps {
  message?: string;
  className?: string;
}

export function LoadingState({ message = 'Loading...', className = '' }: LoadingStateProps) {
  return (
    <div className={`h-64 bg-surface-1 border border-border flex flex-col items-center justify-center gap-3 ${className}`}>
      <Loader2 className="w-6 h-6 text-bloomberg animate-spin" />
      <span className="text-text-secondary font-mono text-sm">{message}</span>
    </div>
  );
}

// Compact version for inline loading
export function LoadingSpinner({ className = '' }: { className?: string }) {
  return (
    <div className={`flex items-center justify-center gap-2 ${className}`}>
      <Loader2 className="w-4 h-4 text-bloomberg animate-spin" />
      <span className="text-text-secondary font-mono text-xs">Loading</span>
    </div>
  );
}
