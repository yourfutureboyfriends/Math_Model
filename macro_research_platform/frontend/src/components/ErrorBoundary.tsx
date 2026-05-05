// ErrorBoundary — Prevents section crashes from unmounting the entire dashboard
// Wrap any component that may throw to isolate failures

import React from 'react';

interface State {
  hasError: boolean;
  error?: Error;
}

interface Props {
  children: React.ReactNode;
  fallback?: React.ReactNode;
  sectionName?: string;
}

export class ErrorBoundary extends React.Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error(`[ErrorBoundary] ${this.props.sectionName || 'Component'} crashed:`, error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        this.props.fallback ?? (
          <div
            className="p-4 m-4 border border-dashed border-text-muted rounded"
            style={{
              color: 'var(--color-text-muted)',
              background: 'var(--color-surface-1)',
            }}
          >
            <div className="text-sm font-medium mb-1">
              {this.props.sectionName || 'Section'} failed to load
            </div>
            <div className="text-xs opacity-70">
              {this.state.error?.message || 'Check console for details'}
            </div>
          </div>
        )
      );
    }
    return this.props.children;
  }
}
