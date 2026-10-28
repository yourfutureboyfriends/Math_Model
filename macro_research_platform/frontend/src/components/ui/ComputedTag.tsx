/**
 * ComputedTag — data-trust provenance tag for dashboard-computed panels.
 *
 * Reads the panel's own `lastUpdated` (falling back to the dashboard `timestamp`)
 * out of the store's fullDashboard and renders a SourceTag, so every model-derived
 * panel shows how fresh its inputs are. Defaults to source "Computed" since these
 * values are derived from the live feeds rather than a single raw source.
 */
import React from 'react';
import { useMacroStore } from '@/store/macroStore';
import { SourceTag } from '@/components/ui/SourceTag';

interface ComputedTagProps {
  /** Key of the sub-object in the dashboard response, e.g. "riskIndicators". */
  section?: string;
  source?: string;
  staleAfterSeconds?: number;
}

export function ComputedTag({
  section,
  source = 'Computed',
  staleAfterSeconds = 300,
}: ComputedTagProps): React.ReactElement {
  const timestamp = useMacroStore((s) => {
    const fd = s.fullDashboard as any;
    if (!fd) return undefined;
    const sub = section ? fd[section] : undefined;
    return (sub && sub.lastUpdated) || fd.timestamp || undefined;
  });
  return <SourceTag source={source} timestamp={timestamp} staleAfterSeconds={staleAfterSeconds} />;
}
