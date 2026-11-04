// ErrorBoundary — Prevents section crashes from unmounting the entire dashboard
// Wrap any component that may throw to isolate failures

import React from 'react';

interface State {
  hasError: boolean;
  error?: Error;
  copied?: string;
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
            <div role="alert" className="text-xs opacity-70">{this.state.error?.message || 'An unexpected rendering error occurred.'}</div>
            <div className="flex flex-wrap gap-2 mt-3 text-xs">
              <button className="border border-border rounded px-3 py-1.5" onClick={()=>this.setState({hasError:false,error:undefined,copied:undefined})}>Retry this view</button>
              <button className="border border-border rounded px-3 py-1.5" onClick={async()=>{try{await navigator.clipboard.writeText(`${this.props.sectionName||'Application'}: ${this.state.error?.message||'Unknown error'}\n${this.state.error?.stack||''}`);this.setState({copied:'Diagnostic copied to clipboard.'});}catch{this.setState({copied:'Clipboard unavailable; expand details below.'});}}}>Copy diagnostic</button>
            </div>
            <details className="mt-3 text-xs"><summary className="cursor-pointer">Error details</summary><pre className="mt-2 whitespace-pre-wrap break-words max-h-48 overflow-auto">{this.state.error?.stack||this.state.error?.message}</pre></details>
            {this.state.copied&&<p role="status" className="text-xs mt-2">{this.state.copied}</p>}
          </div>
        )
      );
    }
    return this.props.children;
  }
}
