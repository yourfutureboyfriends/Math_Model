/**
 * PE — the private-equity area (top-bar mode 'pe'): the LBO workbench (a buyout modelled from a company's filings
 * and live credit markets), the deal pipeline (this fund's saved deals by stage), the carry waterfall and fund
 * performance with public-market equivalents. Modelled returns are analysis, never a track record.
 */
import { Briefcase } from 'lucide-react';
import { Workbench } from '@/components/pe/Workbench';
import { Pipeline } from '@/components/pe/Pipeline';
import { Performance, Waterfall } from '@/components/pe/FundTools';
import { PE_TABS, setPeTab, usePeTab } from '@/components/pe/peShared';

export function PrivateEquityPage() {
  const tab = usePeTab();
  const t = PE_TABS.find((x) => x.id === tab) ?? PE_TABS[0];
  return (
    <div className="p-4 space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <span className="section-tag"><Briefcase className="w-3 h-3" /></span>
        <div>
          <h1 className="text-[17px] font-semibold text-text-primary tracking-[-0.01em]">Private equity</h1>
          <div className="text-[11px] text-text-tertiary">{t.desc}</div>
        </div>
        <div className="seg ml-auto" role="tablist" aria-label="Private equity tools">
          {PE_TABS.map((x) => <button key={x.id} role="tab" aria-selected={tab === x.id} onClick={() => setPeTab(x.id)} className="seg-item">{x.label}</button>)}
        </div>
      </div>
      {tab === 'workbench' && <Workbench />}
      {tab === 'pipeline' && <Pipeline />}
      {tab === 'waterfall' && <Waterfall />}
      {tab === 'performance' && <Performance />}
    </div>
  );
}
