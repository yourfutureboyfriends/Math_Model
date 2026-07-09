// Phase 8 — Data Explorer Section (Redesigned)
// All raw data with terminal aesthetic

import { useState } from 'react';
import { ChevronDown, ChevronRight, Database } from 'lucide-react';
import type { DashboardData } from '@/types';
import { useMacroStore } from '@/store/macroStore';

interface DataExplorerSectionProps {
  data?: DashboardData;
}

export function DataExplorerSection({ data: dataProp }: DataExplorerSectionProps) {
  const _fullDash = useMacroStore((s) => s.fullDashboard);
  let data = dataProp;
  if (!data) data = _fullDash as any;
  if (!data) return null;

  const [expanded, setExpanded] = useState<Record<string, boolean>>({
    metadata: true,
    regime: false,
    keyMetrics: false,
    signals: false,
    sectorAllocation: false,
    riskIndicators: false,
    advancedIndicators: false,
    businessLayer: false,
    modelAgreement: false,
    transmissionAnalysis: false,
    investmentMemo: false,
    dataToWatch: false,
  });

  const toggle = (key: string) => {
    setExpanded((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const SectionHeader = ({
    title,
    dataKey,
    count,
  }: {
    title: string;
    dataKey: string;
    count?: number;
  }) => (
    <button
      onClick={() => toggle(dataKey)}
      className="w-full flex items-center justify-between p-2 bg-surface-2 hover:bg-surface-3 transition-colors"
    >
      <div className="flex items-center gap-2">
        {expanded[dataKey] ? (
          <ChevronDown className="w-3 h-3 text-text-tertiary" />
        ) : (
          <ChevronRight className="w-3 h-3 text-text-tertiary" />
        )}
        <span className="text-xs font-medium text-text-primary">{title}</span>
        {count !== undefined && (
          <span className="signal-tag neutral text-2xs">
            {count} items
          </span>
        )}
      </div>
    </button>
  );

  const JsonDisplay = ({ data }: { data: unknown }) => (
    <pre className="text-2xs text-text-secondary overflow-x-auto p-3 bg-surface-3 max-h-96 overflow-y-auto font-mono">
      {JSON.stringify(data, null, 2)}
    </pre>
  );

  return (
    <div id="data-explorer" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">37</span>
          <h2 className="section-title">Data Explorer</h2>
        </div>
      </div>

      <div className="space-y-2">
        {/* Metadata */}
        <div className="border border-border bg-surface-1">
          <SectionHeader title="Metadata" dataKey="metadata" />
          {expanded.metadata && <JsonDisplay data={data.metadata} />}
        </div>

        {/* Regime Data */}
        <div className="border border-border bg-surface-1">
          <SectionHeader title="Regime Data" dataKey="regime" />
          {expanded.regime && <JsonDisplay data={data.regime} />}
        </div>

        {/* Key Metrics */}
        <div className="border border-border bg-surface-1">
          <SectionHeader title="Key Metrics" dataKey="keyMetrics" />
          {expanded.keyMetrics && <JsonDisplay data={data.keyMetrics} />}
        </div>

        {/* Signals */}
        <div className="border border-border bg-surface-1">
          <SectionHeader title="Signals" dataKey="signals" />
          {expanded.signals && <JsonDisplay data={data.signals} />}
        </div>

        {/* Sector Allocation */}
        <div className="border border-border bg-surface-1">
          <SectionHeader
            title="Sector Allocation"
            dataKey="sectorAllocation"
            count={data.sectorAllocation?.sectors?.length}
          />
          {expanded.sectorAllocation && <JsonDisplay data={data.sectorAllocation} />}
        </div>

        {/* Risk Indicators */}
        <div className="border border-border bg-surface-1">
          <SectionHeader
            title="Risk Indicators"
            dataKey="riskIndicators"
            count={data.riskIndicators?.indicators?.length}
          />
          {expanded.riskIndicators && <JsonDisplay data={data.riskIndicators} />}
        </div>

        {/* Advanced Indicators */}
        <div className="border border-border bg-surface-1">
          <SectionHeader title="Advanced Indicators" dataKey="advancedIndicators" />
          {expanded.advancedIndicators && <JsonDisplay data={data.advancedIndicators} />}
        </div>

        {/* Business Layer */}
        <div className="border border-border bg-surface-1">
          <SectionHeader
            title="Business Layer"
            dataKey="businessLayer"
            count={
              (data.businessLayer?.expectedReturns?.length || 0) +
              (data.businessLayer?.positionSizing?.length || 0) +
              (data.businessLayer?.signalScorecard?.length || 0) +
              (data.businessLayer?.decisionLog?.length || 0)
            }
          />
          {expanded.businessLayer && <JsonDisplay data={data.businessLayer} />}
        </div>

        {/* Model Agreement */}
        <div className="border border-border bg-surface-1">
          <SectionHeader
            title="Model Agreement"
            dataKey="modelAgreement"
            count={data.modelAgreement?.items?.length}
          />
          {expanded.modelAgreement && <JsonDisplay data={data.modelAgreement} />}
        </div>

        {/* Transmission Analysis */}
        <div className="border border-border bg-surface-1">
          <SectionHeader
            title="Transmission Analysis"
            dataKey="transmissionAnalysis"
            count={data.transmissionAnalysis?.channels?.length}
          />
          {expanded.transmissionAnalysis && <JsonDisplay data={data.transmissionAnalysis} />}
        </div>

        {/* Investment Memo */}
        <div className="border border-border bg-surface-1">
          <SectionHeader title="Investment Memo" dataKey="investmentMemo" />
          {expanded.investmentMemo && <JsonDisplay data={data.investmentMemo} />}
        </div>

        {/* Data to Watch */}
        <div className="border border-border bg-surface-1">
          <SectionHeader
            title="Data to Watch"
            dataKey="dataToWatch"
            count={data.dataToWatch?.length}
          />
          {expanded.dataToWatch && <JsonDisplay data={data.dataToWatch} />}
        </div>
      </div>

      <div className="mt-3 p-2 bg-surface-1 border border-border">
        <div className="flex items-center gap-2 text-xs text-text-secondary">
          <Database className="w-3 h-3" />
          <span>Raw data from API — verify all fields populated correctly</span>
        </div>
      </div>
    </div>
  );
}
