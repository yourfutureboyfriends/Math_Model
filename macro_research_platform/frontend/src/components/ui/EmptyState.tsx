
// Empty State Component — Phase 8 UI Polish
// Shows when there's no data to display


import { LucideIcon } from 'lucide-react'

interface EmptyStateProps {
  icon: LucideIcon
  title: string
  description: string
  action?: {
    label: string
    onClick: () => void
  }
}

export function EmptyState({ icon: Icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
      <div className="p-3 bg-surface-2 rounded-lg mb-4">
        <Icon className="w-8 h-8 text-text-secondary" />
      </div>
      <h3 className="text-sm font-semibold text-text-primary mb-1">{title}</h3>
      <p className="text-xs text-text-secondary max-w-xs mb-4">{description}</p>
      {action && (
        <button
          onClick={action.onClick}
          className="terminal-btn-primary px-4 py-2 text-xs"
        >
          {action.label}
        </button>
      )}
    </div>
  )
}
