
// Error State Component — Phase 8 UI Polish
// Shows when data fetching fails


import { AlertTriangle, RefreshCw } from 'lucide-react'

interface ErrorStateProps {
  message?: string
  retry?: () => void
}

// Map technical errors to user-friendly messages
function getUserMessage(message?: string): string {
  if (!message) return 'Something went wrong'

  if (message.includes('Failed to fetch')) {
    return 'Data source unavailable — retrying'
  }
  if (message.includes('401') || message.includes('Unauthorized')) {
    return 'Session expired — please log in'
  }
  if (message.includes('500')) {
    return 'Server error — check system health'
  }
  if (message.includes('Network')) {
    return 'Network error — check your connection'
  }
  if (message.includes('timeout')) {
    return 'Request timed out — try again'
  }
  return message
}

export function ErrorState({ message, retry }: ErrorStateProps) {
  const userMessage = getUserMessage(message)

  return (
    <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
      <div className="p-3 bg-red-dim rounded-lg mb-4">
        <AlertTriangle className="w-8 h-8 text-red" />
      </div>
      <h3 className="text-sm font-semibold text-text-primary mb-1">
        Error loading data
      </h3>
      <p className="text-xs text-text-secondary max-w-xs mb-4">
        {userMessage}
      </p>
      {retry && (
        <button
          onClick={retry}
          className="terminal-btn flex items-center gap-2 px-4 py-2 text-xs"
        >
          <RefreshCw className="w-3 h-3" />
          Retry
        </button>
      )}
    </div>
  )
}
