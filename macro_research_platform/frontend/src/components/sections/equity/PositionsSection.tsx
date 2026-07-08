/**
 * PositionsSection — Phase 1 position & portfolio ingestion.
 *
 * Manual entry + CSV upload of held positions, persisted server-side, enriched with
 * live market value / unrealized P&L / weights, and aggregated per book and firm-wide.
 * This is the foundation the risk/attribution/trade features build on.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { Plus, Upload, Trash2, RefreshCw, Briefcase } from 'lucide-react';

interface Position {
  id: number;
  symbol: string;
  asset_class: string;
  quantity: number;
  avg_cost: number;
  book: string;
  strategy_bucket?: string | null;
  entry_date?: string | null;
  current_price: number | null;
  market_value: number | null;
  unrealized_pnl: number | null;
  unrealized_pnl_pct: number | null;
  weight_pct: number | null;
  price_available: boolean;
}
interface Summary {
  position_count: number; priced_count: number; unpriced_count: number;
  long_market_value: number; short_market_value: number;
  gross_exposure: number; net_exposure: number; total_unrealized_pnl: number;
}
interface BookRow extends Summary { book: string; }
interface PortfolioResponse { positions: Position[]; summary: Summary; books: BookRow[]; priced_at: string; }

const usd = (v: number | null | undefined, dp = 0) =>
  v == null ? '—' : `${v < 0 ? '-' : ''}$${Math.abs(v).toLocaleString(undefined, { maximumFractionDigits: dp, minimumFractionDigits: dp })}`;
const pct = (v: number | null | undefined) => (v == null ? '—' : `${(v * 100).toFixed(1)}%`);
const signed = (v: number | null | undefined) => (v == null ? '' : v >= 0 ? 'text-green' : 'text-red');

const EMPTY_FORM = { symbol: '', quantity: '', avg_cost: '', book: 'Macro', asset_class: 'Equity' };

export function PositionsSection() {
  const [data, setData] = useState<PortfolioResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({ ...EMPTY_FORM });
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch('/api/v1/portfolio/positions');
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setData(await r.json());
      setError(null);
    } catch (e: any) {
      setError(e.message || 'failed');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const addPosition = async () => {
    if (!form.symbol || !form.quantity || !form.avg_cost) return;
    setBusy(true);
    try {
      const r = await fetch('/api/v1/portfolio/positions', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol: form.symbol, quantity: Number(form.quantity), avg_cost: Number(form.avg_cost),
          book: form.book || 'Macro', asset_class: form.asset_class || 'Equity',
        }),
      });
      if (r.ok) { setForm({ ...EMPTY_FORM }); await load(); }
    } finally { setBusy(false); }
  };

  const remove = async (id: number) => {
    setBusy(true);
    try { await fetch(`/api/v1/portfolio/positions/${id}`, { method: 'DELETE' }); await load(); }
    finally { setBusy(false); }
  };

  const onCsv = async (file: File) => {
    setBusy(true);
    try {
      const text = await file.text();
      const lines = text.split(/\r?\n/).filter((l) => l.trim());
      if (!lines.length) return;
      const headers = lines[0].split(',').map((h) => h.trim().toLowerCase());
      const idx = (name: string) => headers.indexOf(name);
      const positions = lines.slice(1).map((line) => {
        const c = line.split(',');
        return {
          symbol: c[idx('symbol')]?.trim(),
          quantity: Number(c[idx('quantity')]),
          avg_cost: Number(c[idx('avg_cost')] ?? c[idx('avg cost')]),
          book: (idx('book') >= 0 ? c[idx('book')]?.trim() : '') || 'Macro',
          asset_class: (idx('asset_class') >= 0 ? c[idx('asset_class')]?.trim() : '') || 'Equity',
        };
      }).filter((p) => p.symbol && !isNaN(p.quantity) && !isNaN(p.avg_cost));
      if (positions.length) {
        await fetch('/api/v1/portfolio/positions/bulk', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ positions }),
        });
        await load();
      }
    } finally { setBusy(false); if (fileRef.current) fileRef.current.value = ''; }
  };

  const s = data?.summary;

  return (
    <div id="portfolio-positions" className="terminal-section">
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag"><Briefcase className="w-3 h-3" /></span>
          <h2 className="section-title">Positions & Portfolio</h2>
          {s && <span className="section-meta">{s.position_count} positions</span>}
        </div>
        <button onClick={load} title="Refresh" className="p-1 text-text-tertiary hover:text-bloomberg">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      <div className="space-y-3">
        {/* Firm summary */}
        {s && (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
            {[
              ['Gross Exp.', usd(s.gross_exposure)],
              ['Net Exp.', usd(s.net_exposure)],
              ['Long', usd(s.long_market_value)],
              ['Short', usd(s.short_market_value)],
              ['Unrealized P&L', usd(s.total_unrealized_pnl), signed(s.total_unrealized_pnl)],
            ].map(([label, val, tone]) => (
              <div key={label as string} className="p-2 bg-surface-1 border border-border">
                <div className="text-2xs text-text-tertiary uppercase tracking-wider">{label}</div>
                <div className={`text-sm font-mono font-bold ${tone || 'text-text-primary'}`}>{val}</div>
              </div>
            ))}
          </div>
        )}

        {/* Book breakdown */}
        {data && data.books.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {data.books.map((b) => (
              <div key={b.book} className="px-2 py-1 bg-surface-2 border border-border-subtle text-2xs">
                <span className="text-text-secondary">{b.book}</span>
                <span className="mx-1 text-text-tertiary">·</span>
                <span className="font-mono text-text-primary">net {usd(b.net_exposure)}</span>
                <span className="mx-1 text-text-tertiary">·</span>
                <span className={`font-mono ${signed(b.total_unrealized_pnl)}`}>{usd(b.total_unrealized_pnl)}</span>
              </div>
            ))}
          </div>
        )}

        {/* Add position form */}
        <div className="p-3 bg-surface-1 border border-border">
          <div className="grid grid-cols-2 md:grid-cols-6 gap-2 items-end">
            <div>
              <label className="text-2xs text-text-tertiary uppercase">Symbol</label>
              <input value={form.symbol} onChange={(e) => setForm({ ...form, symbol: e.target.value.toUpperCase() })}
                placeholder="AAPL" className="w-full bg-surface-2 border border-border-subtle px-2 py-1 text-sm font-mono text-text-primary" />
            </div>
            <div>
              <label className="text-2xs text-text-tertiary uppercase">Quantity</label>
              <input value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })}
                placeholder="100 / -50" className="w-full bg-surface-2 border border-border-subtle px-2 py-1 text-sm font-mono text-text-primary" />
            </div>
            <div>
              <label className="text-2xs text-text-tertiary uppercase">Avg Cost</label>
              <input value={form.avg_cost} onChange={(e) => setForm({ ...form, avg_cost: e.target.value })}
                placeholder="180.00" className="w-full bg-surface-2 border border-border-subtle px-2 py-1 text-sm font-mono text-text-primary" />
            </div>
            <div>
              <label className="text-2xs text-text-tertiary uppercase">Book</label>
              <input value={form.book} onChange={(e) => setForm({ ...form, book: e.target.value })}
                className="w-full bg-surface-2 border border-border-subtle px-2 py-1 text-sm text-text-primary" />
            </div>
            <div>
              <label className="text-2xs text-text-tertiary uppercase">Asset Class</label>
              <input value={form.asset_class} onChange={(e) => setForm({ ...form, asset_class: e.target.value })}
                className="w-full bg-surface-2 border border-border-subtle px-2 py-1 text-sm text-text-primary" />
            </div>
            <div className="flex gap-1">
              <button onClick={addPosition} disabled={busy}
                className="flex-1 flex items-center justify-center gap-1 px-2 py-1 border border-green/40 bg-green-dim text-green text-xs hover:bg-green/20">
                <Plus className="w-3 h-3" /> Add
              </button>
              <button onClick={() => fileRef.current?.click()} disabled={busy} title="Upload CSV (symbol,quantity,avg_cost,book)"
                className="px-2 py-1 border border-border bg-surface-2 text-text-secondary hover:text-bloomberg">
                <Upload className="w-3 h-3" />
              </button>
              <input ref={fileRef} type="file" accept=".csv,text/csv" className="hidden"
                onChange={(e) => e.target.files?.[0] && onCsv(e.target.files[0])} />
            </div>
          </div>
        </div>

        {/* Positions table */}
        <div className="border border-border bg-surface-1 overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border bg-surface-2 text-2xs text-text-tertiary uppercase">
                <th className="text-left py-2 px-3 font-medium">Symbol</th>
                <th className="text-left py-2 px-3 font-medium">Book</th>
                <th className="text-right py-2 px-3 font-medium">Qty</th>
                <th className="text-right py-2 px-3 font-medium">Avg Cost</th>
                <th className="text-right py-2 px-3 font-medium">Price</th>
                <th className="text-right py-2 px-3 font-medium">Mkt Value</th>
                <th className="text-right py-2 px-3 font-medium">Unreal. P&L</th>
                <th className="text-right py-2 px-3 font-medium">Weight</th>
                <th className="py-2 px-2"></th>
              </tr>
            </thead>
            <tbody>
              {(data?.positions ?? []).map((p) => (
                <tr key={p.id} className="border-b border-border-subtle last:border-0 hover:bg-surface-3">
                  <td className="py-2 px-3">
                    <span className="text-sm font-medium text-text-primary">{p.symbol}</span>
                    <span className="ml-1 text-2xs text-text-tertiary">{p.asset_class}</span>
                  </td>
                  <td className="py-2 px-3 text-xs text-text-secondary">{p.book}</td>
                  <td className={`py-2 px-3 text-right font-mono text-sm ${p.quantity < 0 ? 'text-red' : 'text-text-primary'}`}>{p.quantity}</td>
                  <td className="py-2 px-3 text-right font-mono text-sm text-text-secondary">{usd(p.avg_cost, 2)}</td>
                  <td className="py-2 px-3 text-right font-mono text-sm text-text-primary">
                    {p.price_available ? usd(p.current_price, 2) : <span className="text-amber text-2xs">no price</span>}
                  </td>
                  <td className="py-2 px-3 text-right font-mono text-sm text-text-primary">{usd(p.market_value)}</td>
                  <td className={`py-2 px-3 text-right font-mono text-sm ${signed(p.unrealized_pnl)}`}>
                    {usd(p.unrealized_pnl)} {p.unrealized_pnl_pct != null && <span className="text-2xs">({pct(p.unrealized_pnl_pct)})</span>}
                  </td>
                  <td className="py-2 px-3 text-right font-mono text-sm text-text-secondary">{pct(p.weight_pct)}</td>
                  <td className="py-2 px-2 text-center">
                    <button onClick={() => remove(p.id)} title="Close position" className="p-1 text-text-tertiary hover:text-red">
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </td>
                </tr>
              ))}
              {!loading && (!data || data.positions.length === 0) && (
                <tr><td colSpan={9} className="py-6 text-center text-sm text-text-secondary">
                  No positions yet. Add one above or upload a CSV (columns: symbol, quantity, avg_cost, book).
                </td></tr>
              )}
            </tbody>
          </table>
        </div>

        {error && <div className="text-2xs text-red">Positions API error: {error}</div>}
        {data && <div className="text-2xs text-text-tertiary text-right">Priced {new Date(data.priced_at).toLocaleTimeString()}</div>}
      </div>
    </div>
  );
}
