// Phase 8 Detail Panel (Right side)
// Contextual detail view for active section

import { cn } from '@/lib/utils';
import { X } from 'lucide-react';

interface DetailPanelProps {
  isOpen: boolean;
  onClose: () => void;
  activeSection?: string;
  data?: any;
}

export function DetailPanel({ isOpen, onClose, activeSection, data }: DetailPanelProps) {
  // Default view: Model Breakdown when Master Signal is active
  const renderDefaultContent = () => {
    const modelBreakdown = data?.ensembleSignal?.modelBreakdown || [];

    return (
      <>
        <div className="px-4 py-3 border-b border-border">
          <div className="text-xs font-medium text-text-secondary uppercase tracking-wider">
            Model Breakdown
          </div>
        </div>

        <div className="p-4">
          {modelBreakdown.length === 0 ? (
            <div className="text-sm text-text-tertiary">No model data available</div>
          ) : (
            <div className="space-y-1">
              {modelBreakdown
                .sort((a: any, b: any) =>
                  Math.abs(b.weightedContribution) - Math.abs(a.weightedContribution)
                )
                .map((model: any) => (
                  <div
                    key={model.model}
                    className="flex items-center gap-2 py-1.5 hover:bg-surface-3 px-2 -mx-2 rounded-sm cursor-pointer transition-colors"
                  >
                    <span className="w-24 text-xs text-text-secondary truncate">
                      {model.model}
                    </span>

                    <div className="flex-1 h-1.5 bg-surface-4 rounded-sm overflow-hidden">
                      <div
                        className={cn(
                          'h-full rounded-sm',
                          model.weightedContribution > 0 ? 'bg-accent' : 'bg-red'
                        )}
                        style={{
                          width: `${Math.min(100, Math.abs(model.weightedContribution) * 100)}%`,
                          marginLeft: model.weightedContribution < 0 ? 'auto' : 0,
                          marginRight: model.weightedContribution > 0 ? 'auto' : 0,
                        }}
                      />
                    </div>

                    <span
                      className={cn(
                        'w-12 text-xs font-mono text-right',
                        model.weightedContribution > 0 ? 'text-accent' : 'text-red'
                      )}
                    >
                      {model.weightedContribution > 0 ? '+' : ''}
                      {(model.weightedContribution * 100).toFixed(0)}%
                    </span>
                  </div>
                ))}
            </div>
          )}
        </div>
      </>
    );
  };

  // Render content based on active section
  const renderContent = () => {
    switch (activeSection) {
      case 'sector-allocation':
        return (
          <>
            <div className="px-4 py-3 border-b border-border">
              <div className="text-xs font-medium text-text-secondary uppercase tracking-wider">
                Sector Factor Weights
              </div>
            </div>
            <div className="p-4 text-sm text-text-tertiary">
              Select a sector to view factor decomposition
            </div>
          </>
        );

      case 'factor-rotation':
        return (
          <>
            <div className="px-4 py-3 border-b border-border">
              <div className="text-xs font-medium text-text-secondary uppercase tracking-wider">
                Factor ETF Prices
              </div>
            </div>
            <div className="p-4 text-sm text-text-tertiary">
              Select a factor to view price and 52W range
            </div>
          </>
        );

      case 'risk-indicators':
        return (
          <>
            <div className="px-4 py-3 border-b border-border">
              <div className="text-xs font-medium text-text-secondary uppercase tracking-wider">
                Historical Risk Spread
              </div>
            </div>
            <div className="p-4">
              <div className="h-32 flex items-center justify-center text-sm text-text-tertiary">
                Sparkline chart placeholder
              </div>
            </div>
          </>
        );

      default:
        return renderDefaultContent();
    }
  };

  return (
    <>
      {/* Desktop: Fixed panel */}
      <div
        className={cn(
          'hidden lg:block fixed top-12 right-0 bottom-0 w-72 bg-surface-1 border-l border-border z-30',
          'transform transition-transform duration-200',
          isOpen ? 'translate-x-0' : 'translate-x-full'
        )}
      >
        <div className="h-full overflow-y-auto">{renderContent()}</div>
      </div>

      {/* Mobile: Slide-over */}
      <>
        {isOpen && (
          <div
            className="lg:hidden fixed inset-0 bg-black/50 z-40"
            onClick={onClose}
          />
        )}
        <div
          className={cn(
            'lg:hidden fixed top-12 right-0 bottom-0 w-80 bg-surface-1 border-l border-border z-50',
            'transform transition-transform duration-200',
            isOpen ? 'translate-x-0' : 'translate-x-full'
          )}
        >
          <div className="h-12 flex items-center justify-between px-4 border-b border-border">
            <span className="text-sm font-medium text-text-primary">Details</span>
            <button onClick={onClose} className="p-1 text-text-tertiary hover:text-text-primary">
              <X className="w-4 h-4" />
            </button>
          </div>
          <div className="h-[calc(100%-48px)] overflow-y-auto">{renderContent()}</div>
        </div>
      </>
    </>
  );
}
