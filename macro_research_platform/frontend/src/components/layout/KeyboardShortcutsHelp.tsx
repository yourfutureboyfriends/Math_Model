// UPGRADE-6: Keyboard Shortcuts Help Overlay
// Shows all available keyboard shortcuts for analyst workflow

import { X, Command, CornerDownLeft, ArrowUpDown } from 'lucide-react';
import { cn } from '@/lib/utils';

interface KeyboardShortcutsHelpProps {
  isOpen: boolean;
  onClose: () => void;
}

const SHORTCUT_CATEGORIES = [
  {
    name: 'Navigation',
    shortcuts: [
      { key: 'M', description: 'Morning Brief', context: '' },
      { key: 'G', description: 'Master Signal', context: '' },
      { key: 'K', description: 'Key Metrics', context: '' },
      { key: 'R', description: 'Regime Engine', context: '' },
      { key: 'P', description: 'Regime Playbook', context: '' },
      { key: 'S', description: 'ML Signals', context: '' },
      { key: 'E', description: 'Ensemble', context: '' },
      { key: 'T', description: 'Trade Ideas', context: '' },
      { key: 'F', description: 'Factor Rotation', context: '' },
      { key: 'V', description: 'Risk Indicators', context: 'V for Volatility' },
      { key: 'A', description: 'Risk Analytics', context: '' },
      { key: 'D', description: 'Debt Cycle', context: '' },
      { key: 'N', description: 'GDP Nowcast', context: '' },
      { key: 'L', description: 'Liquidity', context: '' },
      { key: 'I', description: 'Sentiment', context: '' },
      { key: 'Y', description: 'GMO Forecasts', context: '' },
      { key: 'U', description: 'Valuation', context: '' },
      { key: 'X', description: 'Expected Returns', context: '' },
      { key: 'O', description: 'Portfolio', context: '' },
      { key: 'H', description: 'Horizon Tension', context: '' },
      { key: 'W', description: 'News Sentiment', context: '' },
      { key: 'Q', description: 'Model Agreement', context: '' },
      { key: 'J', description: 'Econ Calendar', context: '' },
      { key: 'Z', description: 'System Health', context: '' },
    ],
  },
  {
    name: 'Quick Access',
    shortcuts: [
      { key: '1', description: 'Morning Brief', context: '' },
      { key: '2', description: 'Master Signal', context: '' },
      { key: '3', description: 'Regime Engine', context: '' },
      { key: '4', description: 'ML Signals', context: '' },
      { key: '5', description: 'Risk Analytics', context: '' },
      { key: '6', description: 'Trade Ideas', context: '' },
      { key: '7', description: 'GDP Nowcast', context: '' },
      { key: '8', description: 'Expected Returns', context: '' },
      { key: '9', description: 'System Health', context: '' },
    ],
  },
  {
    name: 'Global Commands',
    shortcuts: [
      { key: '⌘/Ctrl + K', description: 'Command Palette', context: 'Toggle on/off' },
      { key: '⌘/Ctrl + R', description: 'Refresh Data', context: 'Reload dashboard' },
      { key: '⌘/Ctrl + B', description: 'Toggle Sidebar', context: 'Collapse/expand' },
      { key: '⌘/Ctrl + D', description: 'Toggle Detail Panel', context: 'Show/hide right panel' },
      { key: '⌘/Ctrl + E', description: 'Export Data', context: 'CSV export' },
      { key: '⌘/Ctrl + S', description: 'Save Snapshot', context: 'Save current state' },
      { key: '?', description: 'Show Shortcuts', context: 'This help panel' },
      { key: 'Esc', description: 'Close Panels', context: 'Close any open modal' },
    ],
  },
  {
    name: 'Navigation',
    shortcuts: [
      { key: '↑', description: 'Previous Section', context: 'Scroll up' },
      { key: '↓', description: 'Next Section', context: 'Scroll down' },
    ],
  },
];

export function KeyboardShortcutsHelp({ isOpen, onClose }: KeyboardShortcutsHelpProps) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-4xl max-h-[90vh] bg-surface-1 border border-border shadow-2xl flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-bloomberg/10 rounded">
              <Command className="w-5 h-5 text-bloomberg" />
            </div>
            <div>
              <h2 className="text-lg font-medium text-text-primary">Keyboard Shortcuts</h2>
              <p className="text-xs text-text-tertiary">Analyst Workflow Navigation</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 text-text-tertiary hover:text-text-primary hover:bg-surface-2 rounded transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          <div className="grid grid-cols-2 gap-8">
            {SHORTCUT_CATEGORIES.map((category) => (
              <div
                key={category.name}
                className={cn(
                  'space-y-3',
                  category.name === 'Navigation' ? 'col-span-2' : ''
                )}
              >
                <h3 className="text-xs font-medium text-text-tertiary uppercase tracking-wider border-b border-border-subtle pb-2">
                  {category.name}
                </h3>
                <div
                  className={cn(
                    'grid gap-2',
                    category.name === 'Navigation' ? 'grid-cols-3' : 'grid-cols-1'
                  )}
                >
                  {category.shortcuts.map((shortcut) => (
                    <div
                      key={shortcut.key}
                      className="flex items-center justify-between p-2 bg-surface-2 border border-border-subtle"
                    >
                      <div className="flex items-center gap-2">
                        <kbd className="px-2 py-1 font-mono text-xs bg-surface-3 text-text-primary border border-border rounded min-w-[32px] text-center">
                          {shortcut.key}
                        </kbd>
                        {shortcut.context && (
                          <span className="text-2xs text-text-tertiary">
                            {shortcut.context}
                          </span>
                        )}
                      </div>
                      <span className="text-sm text-text-secondary">
                        {shortcut.description}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>

          {/* Tips */}
          <div className="mt-8 p-4 border border-amber bg-amber-dim">
            <h4 className="text-sm font-medium text-amber mb-2">Pro Tips</h4>
            <ul className="space-y-1 text-sm text-text-secondary">
              <li className="flex items-center gap-2">
                <span className="text-amber">•</span>
                Press a letter key to instantly jump to that section
              </li>
              <li className="flex items-center gap-2">
                <span className="text-amber">•</span>
                Use number keys 1-9 for the most important sections
              </li>
              <li className="flex items-center gap-2">
                <span className="text-amber">•</span>
                Arrow keys navigate between sections sequentially
              </li>
              <li className="flex items-center gap-2">
                <span className="text-amber">•</span>
                Shortcuts are disabled when typing in input fields
              </li>
            </ul>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-3 border-t border-border bg-surface-2">
          <div className="flex items-center gap-2 text-2xs text-text-tertiary">
            <CornerDownLeft className="w-3 h-3" />
            <span>Press Esc to close</span>
          </div>
          <div className="flex items-center gap-2 text-2xs text-text-tertiary">
            <ArrowUpDown className="w-3 h-3" />
            <span>MACRO TERMINAL v8.0</span>
          </div>
        </div>
      </div>
    </div>
  );
}
