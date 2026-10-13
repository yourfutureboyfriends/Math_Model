/**
 * ModelInfoPanel — auditable model documentation ("Model Info").
 *
 * Fetches /api/v1/methodology and shows each core model's formula, inputs, output
 * units + range, and citation, so an institutional user can audit model logic before
 * trusting it with capital.
 */
import { useEffect, useState } from 'react';
import { X, FunctionSquare } from 'lucide-react';

interface ModelInfoPanelProps {
  isOpen: boolean;
  onClose: () => void;
}

interface ModelDoc {
  id: string;
  name: string;
  formula: string;
  inputs?: Record<string, string>;
  output?: { units?: string; range?: [number, number] };
  reference_points?: Record<string, string>;
  citation?: string;
}

export function ModelInfoPanel({ isOpen, onClose }: ModelInfoPanelProps) {
  const [models, setModels] = useState<ModelDoc[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    let cancelled = false;
    setError(null);
    fetch('/api/v1/methodology')
      .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then((j) => { if (!cancelled) setModels(j.models || []); })
      .catch((e) => { if (!cancelled) setError(String(e.message || e)); });
    return () => { cancelled = true; };
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-3xl max-h-[90vh] bg-surface-1 border border-border shadow-2xl flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-bloomberg/10 rounded">
              <FunctionSquare className="w-5 h-5 text-bloomberg" />
            </div>
            <div>
              <h2 className="text-lg font-medium text-text-primary">Model Info &amp; Methodology</h2>
              <p className="text-xs text-text-tertiary">Formula · inputs · output range · citation for every core model</p>
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
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {error && (
            <div className="p-3 border border-red bg-red-dim text-red text-sm">
              Methodology unavailable: {error}
            </div>
          )}
          {!models && !error && (
            <div className="text-text-tertiary text-sm">Loading model documentation…</div>
          )}
          {models && models.map((m) => (
            <div key={m.id} className="border border-border-subtle bg-surface-2">
              <div className="px-4 py-2 border-b border-border-subtle flex items-center justify-between gap-2">
                <span className="text-sm font-medium text-text-primary">{m.name}</span>
                {m.output?.range && (
                  <span className="text-2xs font-mono text-text-tertiary">
                    output ∈ [{m.output.range[0]}, {m.output.range[1]}]
                    {m.output.units ? ` ${m.output.units}` : ''}
                  </span>
                )}
              </div>
              <div className="p-4 space-y-2">
                <div>
                  <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-1">Formula</div>
                  <code className="block text-xs font-mono text-bloomberg bg-surface-3 px-2 py-1 rounded overflow-x-auto">
                    {m.formula}
                  </code>
                </div>
                {m.inputs && Object.keys(m.inputs).length > 0 && (
                  <div>
                    <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-1">Inputs</div>
                    <ul className="text-xs text-text-secondary space-y-0.5">
                      {Object.entries(m.inputs).map(([k, v]) => (
                        <li key={k}>
                          <span className="font-mono text-text-primary">{k}</span>
                          <span className="text-text-tertiary"> — {v}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {m.reference_points && Object.keys(m.reference_points).length > 0 && (
                  <div className="text-2xs text-text-tertiary">
                    Reference: {Object.entries(m.reference_points).map(([k, v]) => `${k} → ${v}`).join(' · ')}
                  </div>
                )}
                {m.citation && (
                  <div className="text-2xs text-text-tertiary italic">Source: {m.citation}</div>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-3 border-t border-border bg-surface-2 text-2xs text-text-tertiary">
          <span>Press Esc to close</span>
          <span>MACRO TERMINAL v8.0 · /api/v1/methodology</span>
        </div>
      </div>
    </div>
  );
}
