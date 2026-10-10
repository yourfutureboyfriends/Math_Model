/**
 * Section-level error boundary for graceful degradation
 * Wraps individual dashboard sections so one failure doesn't crash entire page
 */

import { Component, type ReactNode, type ErrorInfo } from 'react';

interface Props {
  sectionName: string;
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class SectionErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error(`[SectionErrorBoundary] ${this.props.sectionName} crashed:`, error, errorInfo);

    // Could log to monitoring service here
    // reportSectionError(this.props.sectionName, error);
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div className="p-4 border border-red-500/20 rounded bg-red-500/5">
          <h3 className="text-sm font-medium text-red-500 mb-2">
            {this.props.sectionName} Unavailable
          </h3>
          <p className="text-xs text-red-500/70">
            This section encountered an error. Other sections are still available.
          </p>
          <button
            onClick={() => this.setState({ hasError: false, error: null })}
            className="mt-2 text-xs text-red-500 underline hover:text-red-400"
          >
            Retry
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
