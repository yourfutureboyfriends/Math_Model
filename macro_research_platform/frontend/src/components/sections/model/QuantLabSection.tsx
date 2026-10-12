/**
 * Quant Lab — write strategy code and test it (in your browser), with every cost, walk-forward
 * optimisation, Monte Carlo sizing and a deep analysis; start from the institutional strategy library;
 * save and deploy to the paper traders (Portfolios → Quant Trader). Relative value (pairs, market
 * making) lives alongside. Reads /api/v1/quant/* (api/routers/quant.py).
 */
import { useCallback, useEffect, useState } from 'react';
import { ArrowLeftRight, BookOpen, Code2, FlaskConical, Library as LibraryIcon, Save, Trash2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useAuth } from '@/context/AuthContext';
import { CodeLab, STARTER } from './quant/CodeLab';
import { Library } from './quant/Library';
import { RelValue } from './quant/RelValue';
import { api, ErrorNote } from './quant/shared';

const TABS = [
  ['code', 'Code & test', Code2], ['library', 'Strategy library', LibraryIcon], ['mine', 'My strategies', Save],
  ['relval', 'Arb & market making', ArrowLeftRight], ['research', 'Research', BookOpen],
] as const;
type Tab = (typeof TABS)[number][0];

function loadDraft(): { code: string; name: string; id: number | null } {
  try {
    const d = JSON.parse(localStorage.getItem('quantlab.code') || 'null');
    if (d?.code) return { code: d.code, name: d.name ?? '', id: d.id ?? null };
  } catch { /* storage unavailable */ }
  return { code: STARTER, name: 'Trend-filtered risk parity', id: null };
}

export function QuantLabSection() {
  const { user } = useAuth();
  const canSave = ['admin', 'pm', 'quant', 'analyst'].includes(user?.role ?? '');
  const canDeploy = ['admin', 'pm', 'quant'].includes(user?.role ?? '');
  const [tab, setTab] = useState<Tab>('code');
  const [draft] = useState(loadDraft);
  const [code, setCode] = useState(draft.code);
  const [name, setName] = useState(draft.name);
  const [strategyId, setStrategyId] = useState<number | null>(draft.id);
  const [mine, setMine] = useState<any[]>([]);
  const [meta, setMeta] = useState<any>(null);

  useEffect(() => { try { localStorage.setItem('quantlab.code', JSON.stringify({ code, name, id: strategyId })); } catch { /* storage unavailable */ } }, [code, name, strategyId]);
  const loadMine = useCallback(() => { api('/api/v1/quant/strategies').then((j) => setMine(j.strategies)).catch(() => {}); }, []);
  useEffect(loadMine, [loadMine]);
  useEffect(() => { if (tab === 'relval' && !meta) api('/api/v1/quant/meta').then(setMeta).catch(() => {}); }, [tab, meta]);

  const openCode = (c: string, n: string, id: number | null = null) => { setCode(c); setName(n); setStrategyId(id); setTab('code'); };

  return (
    <div className="terminal-section">
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag"><FlaskConical className="w-3 h-3" /></span>
          <h2 className="section-title">Quant Lab</h2>
          <span className="text-2xs text-text-tertiary">write it in Python · test net of every cost · Monte Carlo · deploy</span>
        </div>
      </div>
      <div className="flex flex-wrap border border-border mb-3 w-fit" role="tablist" aria-label="Quant Lab">
        {TABS.map(([k, l, Icon]) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}
            className={cn('inline-flex items-center gap-1 px-3 py-1 text-2xs', tab === k ? 'bg-bloomberg text-bg' : 'text-text-secondary hover:text-text-primary')}>
            <Icon className="w-3 h-3" />{l}
          </button>
        ))}
      </div>
      {tab === 'code' && <CodeLab code={code} setCode={setCode} name={name} setName={setName} strategyId={strategyId} setStrategyId={setStrategyId}
        canSave={canSave} canDeploy={canDeploy} onSaved={loadMine} />}
      {tab === 'library' && <Library onOpenCode={(c, n) => openCode(c, n)} canDeploy={canDeploy} />}
      {tab === 'mine' && <Mine rows={mine} me={user?.username} isAdmin={user?.role === 'admin'} onOpen={(s) => openCode(s.spec.code, s.name, s.id)} onChanged={loadMine} />}
      {tab === 'relval' && (meta ? <RelValue meta={meta} /> : <div className="text-2xs text-text-tertiary">Loading…</div>)}
      {tab === 'research' && <Research />}
    </div>
  );
}

function Mine({ rows, me, isAdmin, onOpen, onChanged }: { rows: any[]; me?: string; isAdmin: boolean; onOpen: (s: any) => void; onChanged: () => void }) {
  const [err, setErr] = useState<string | null>(null);
  const del = async (s: any) => {
    if (!window.confirm(`Delete “${s.name}”?`)) return;
    try { await api(`/api/v1/quant/strategies/${s.id}`, { method: 'DELETE' }); onChanged(); } catch (e: any) { setErr(e.message); }
  };
  const code = rows.filter((s) => s.spec?.kind === 'code');
  const legacy = rows.filter((s) => s.spec?.kind !== 'code');
  return (
    <div className="space-y-2">
      <ErrorNote msg={err} />
      {!code.length && <div className="text-2xs text-text-tertiary">No saved code strategies yet — write one in Code & test and press Save.</div>}
      {code.map((s) => (
        <div key={s.id} className="flex items-center gap-3 p-2 bg-surface-1 border border-border text-2xs">
          <button className="text-text-primary font-semibold hover:underline" onClick={() => onOpen(s)}>{s.name}</button>
          <span className="text-text-tertiary">{s.owner} · updated {String(s.updated_at || '').slice(0, 10)}</span>
          {(s.owner === me || isAdmin) && <button onClick={() => del(s)} className="ml-auto text-text-tertiary hover:text-red" aria-label={`Delete ${s.name}`}><Trash2 className="w-3 h-3" /></button>}
        </div>))}
      {legacy.length > 0 && (
        <details className="text-2xs text-text-tertiary">
          <summary className="cursor-pointer">{legacy.length} older formula-builder strateg{legacy.length > 1 ? 'ies' : 'y'} (still paper-trading if deployed)</summary>
          <ul className="mt-1 space-y-0.5 pl-4 list-disc">{legacy.map((s) => (
            <li key={s.id}>{s.name} <span className="font-mono">{s.spec?.signal}</span>
              {(s.owner === me || isAdmin) && <button onClick={() => del(s)} className="ml-2 underline">delete</button>}</li>))}</ul>
        </details>)}
    </div>
  );
}

function Research() {
  const notes: [string, string][] = [
    ['Costs are modelled, not assumed', 'Every trade pays commission (0.35 bp ≈ $0.0035/share), half the bid-ask spread (from each asset\'s volatility and dollar volume — ≈0.1 bp for SPY, 2–3 bp for a $50m/day stock, 15 bp for a $2m/day small cap), square-root market impact calibrated on $1.7tn of AQR live trades (11.2 bp × √% of daily volume; Frazzini, Israel & Moskowitz 2018), the SEC fee on sales, a borrow fee on shorts and margin interest above 100% long. Cash earns T-bills. Impact grows with capital, so test at the size you would trade.'],
    ['Walk-forward, not best-fit', 'A PARAMS grid is not searched for the best backtest. Each January the parameter set with the highest long-run growth on data up to then is used for that year, so the stitched record is out-of-sample. The gap to the hindsight-best set is shown — it is the overfitting a single backtest hides (Bailey & López de Prado 2014). Keep grids small and economically motivated.'],
    ['Maximum money = maximum growth, not maximum leverage', 'Wealth compounds at the average log return, which peaks at the Kelly leverage (excess return ÷ variance) and falls beyond it — more leverage eventually means less money. Because the edge is estimated with error, the lab recommends at most half-Kelly and the largest leverage keeping P(drawdown beyond your limit) ≤ 5%, capped at your margin limit (Thorp 2006; MacLean, Thorp & Ziemba 2010).'],
    ['Monte Carlo that respects regimes', 'Futures are simulated by a stationary block bootstrap of the strategy\'s own daily net returns (blocks averaging a month), which keeps volatility clustering and crash dynamics that an independent-day simulation erases (Politis & Romano 1994). It cannot invent regimes the history never saw — a strategy tested only since 2010 has never met a 2008.'],
    ['What the institutions publish', 'Trend (AQR: positive in every decade since 1880; Man AHL: EWMA crossovers for ~30 years), risk parity (Bridgewater All Weather; AQR leverage aversion), low risk (Robeco Conservative Formula; AQR Betting Against Beta), volatility management (Moreira & Muir 2017), seasonality (McConnell & Xu 2008). Their real edge is mostly breadth (hundreds of futures and stocks), execution and cost control — ETF-only versions are weaker by construction.'],
    ['Biases that remain', 'Today\'s large caps (survivorship), Yahoo adjusted prices (small errors around corporate actions), signals at the close traded at the next open (no intraday), no taxes, and publication decay — published anomalies lose about half their return afterwards (McLean & Pontiff 2016).'],
  ];
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-2">
      {notes.map(([t, x]) => (
        <div key={t} className="p-3 bg-surface-1 border border-border">
          <div className="text-xs font-semibold text-text-primary mb-1">{t}</div>
          <div className="text-2xs text-text-secondary leading-relaxed">{x}</div>
        </div>))}
    </div>
  );
}
