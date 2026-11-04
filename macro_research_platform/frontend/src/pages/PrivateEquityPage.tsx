/**
 * PE — the private-equity area (top-bar mode 'pe'): the LBO workbench (a buyout modelled from a company's filings
 * and live credit markets), the deal pipeline (this fund's saved deals by stage), the carry waterfall and fund
 * performance with public-market equivalents. Modelled returns are analysis, never a track record.
 */
import { WorkspaceHeader } from '@/components/layout/WorkspaceHeader';
import { PageSections } from '@/components/markets/PageSections';
import { Workbench } from '@/components/pe/Workbench';
import { Pipeline } from '@/components/pe/Pipeline';
import { Precedents } from '@/components/pe/Comparables';
import { Performance, Waterfall } from '@/components/pe/FundTools';
import { PE_TABS, setPeTab, usePeTab } from '@/components/pe/peShared';

// Where each tool sits in the area's workflow (Underwrite → Compare → Review), shown above its name
const STAGE: Record<string, string> = { workbench: 'Underwrite', pipeline: 'Compare', precedents: 'Compare', waterfall: 'Review', performance: 'Review' };

export function PrivateEquityPage() {
  const tab = usePeTab();
  const t = PE_TABS.find((x) => x.id === tab) ?? PE_TABS[0];
  return (
    <div className="pe-workspace workspace-page p-4 space-y-3">
      <WorkspaceHeader area="pe" context={STAGE[t.id]} title={t.label} description={`${t.desc}.`} items={PE_TABS.map(x=>({id:x.id,label:x.label}))} onPick={id=>{const target=PE_TABS.find(x=>x.id===id);if(target)setPeTab(target.id);}}/>
      <div className="pe-tool-navigation">
        <div className="seg" role="tablist" aria-label="Private equity tools">
          {PE_TABS.map((x) => <button key={x.id} role="tab" aria-selected={tab === x.id} onClick={() => setPeTab(x.id)} className="seg-item">{x.label}</button>)}
        </div>
      </div>
      <div className="pe-tool-body"><PageSections page={`pe-${tab}`}/>
      {tab === 'workbench' && <Workbench />}
      {tab === 'pipeline' && <Pipeline />}
      {tab === 'precedents' && <Precedents />}
      {tab === 'waterfall' && <Waterfall />}
      {tab === 'performance' && <Performance />}
      </div>
    </div>
  );
}
