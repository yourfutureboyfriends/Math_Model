/**
 * Team & positions — the fund's organisation by tier: each position's purpose, the platform role it acts as, the
 * capabilities it grants and its workspace; who holds it; and "My access" for the signed-in person.
 * Managers (capability manage_positions) assign people and create or edit positions. Backend: /api/v1/positions*.
 */
import { useCallback, useEffect, useState } from 'react';
import { Check, Minus, Users } from 'lucide-react';
import { cn } from '@/lib/utils';
import { panelLabel } from '@/lib/panels';

async function call(url: string, method = 'GET', body?: any) {
  const r = await fetch(url, { method, headers: body ? { 'Content-Type': 'application/json' } : undefined, body: body ? JSON.stringify(body) : undefined });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : `HTTP ${r.status}`);
  return j;
}
const inputCls = 'bg-surface-1 border border-border px-2 py-1 text-xs text-text-primary focus:border-bloomberg outline-none';
const btn = 'px-2 py-0.5 border border-border hover:border-bloomberg text-2xs disabled:opacity-40';
const ROLE_LABEL: Record<string, string> = { pm: 'portfolio manager', risk: 'risk', analyst: 'analyst', quant: 'quant', viewer: 'read-only' };
const TIER_TONE: Record<number, string> = { 1: 'border-bloomberg text-bloomberg', 2: 'border-nav text-nav', 3: 'border-border-strong text-text-secondary', 4: 'border-border text-text-tertiary' };

export function MyAccess() {
  const [me, setMe] = useState<any>(null);
  useEffect(() => { call('/api/v1/positions/me').then(setMe).catch(() => setMe(null)); }, []);
  if (!me) return null;
  const caps = Object.entries(me.capability_labels) as [string, string][];
  return (
    <div className="border border-border bg-surface-2 p-2 text-xs">
      <div className="flex items-center gap-2 flex-wrap mb-1">
        <span className="text-2xs text-text-tertiary uppercase tracking-wider">My access</span>
        {me.position ? <>
          <span className="text-text-primary font-medium">{me.position.title}</span>
          <span className={cn('text-[10px] px-1.5 border rounded-sm', TIER_TONE[me.position.tier])}>Tier {me.position.tier} · {me.position.tier_label}</span>
        </> : <span className="text-text-secondary">no position in this fund — your account role applies ({ROLE_LABEL[me.role] ?? me.role})</span>}
        {me.read_only && <span className="text-amber text-[10px]">read-only</span>}
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-x-3">
        {caps.map(([k, label]) => (
          <div key={k} className={cn('flex items-center gap-1 text-[11px] py-0.5', me.capabilities[k] ? 'text-text-secondary' : 'text-text-tertiary/60')}>
            {me.capabilities[k] ? <Check className="w-3 h-3 text-green shrink-0" /> : <Minus className="w-3 h-3 shrink-0" />}{label}
          </div>))}
      </div>
    </div>
  );
}

const EMPTY = { key: '', title: '', tier: 3, base_role: 'analyst', capabilities: [] as string[], panels: [] as string[], description: '', seats: 1 };

export function TeamPositions() {
  const [d, setD] = useState<any>(null);
  const [people, setPeople] = useState<any[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [edit, setEdit] = useState<any>(null);
  const load = useCallback(() => {
    call('/api/v1/positions').then((j) => { setD(j); if (j.can_manage) call('/api/v1/positions/people').then((p) => setPeople(p.people)).catch(() => {}); })
      .catch((e) => setErr(e.message));
  }, []);
  useEffect(load, [load]);
  const act = async (fn: () => Promise<any>) => { setErr(null); try { await fn(); load(); } catch (e: any) { setErr(e.message); } };
  if (!d) return <div className="text-2xs text-text-tertiary">{err ?? 'Loading…'}</div>;
  const holderOf = new Map<string, string>();
  d.positions.forEach((p: any) => p.holders.forEach((h: string) => holderOf.set(h, p.title)));
  return (
    <div className="space-y-3 text-xs">
      <MyAccess />
      {err && <div className="text-amber text-2xs">{err}</div>}
      {[1, 2, 3, 4].map((tier) => {
        const ps = d.positions.filter((p: any) => p.tier === tier);
        if (!ps.length) return null;
        return (
          <div key={tier}>
            <div className="text-2xs uppercase tracking-wider text-text-tertiary mb-1">Tier {tier} · {d.tiers[tier]}</div>
            <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-2">
              {ps.map((p: any) => (
                <div key={p.key} className={cn('border bg-surface-2 p-2 space-y-1', tier === 1 ? 'border-bloomberg/40' : 'border-border')}>
                  <div className="flex items-start gap-2">
                    <div className="flex-1 min-w-0">
                      <div className="text-text-primary font-medium">{p.title}</div>
                      <div className="text-[10px] text-text-tertiary">acts as {ROLE_LABEL[p.base_role]} · {p.holders.length}/{p.seats} seat{p.seats > 1 ? 's' : ''}</div>
                    </div>
                    {d.can_manage && <button className={btn} onClick={() => setEdit({ ...p })}>Edit</button>}
                  </div>
                  <div className="text-[11px] text-text-secondary leading-snug">{p.description}</div>
                  <div className="flex flex-wrap gap-1">
                    {p.capabilities.filter((c: string) => c !== 'view_book').map((c: string) => (
                      <span key={c} title={d.capabilities[c]} className="text-[9.5px] px-1 border border-border-subtle text-text-secondary">{d.capabilities[c]}</span>))}
                  </div>
                  <div className="text-[10px] text-text-tertiary">Workspace: {p.panels.map((x: string) => panelLabel(x)).join(' · ')}</div>
                  <div className="flex flex-wrap gap-1 items-center pt-1 border-t border-border-subtle">
                    <Users className="w-3 h-3 text-text-tertiary" />
                    {p.holders.length ? p.holders.map((h: string) => (
                      <span key={h} className="text-[10px] px-1.5 bg-surface-3 rounded-sm">{h}
                        {d.can_manage && <button className="ml-1 text-text-tertiary hover:text-red" title="Remove from position"
                          onClick={() => act(() => call('/api/v1/positions/assign', 'POST', { username: h, position_key: null }))}>×</button>}</span>))
                      : <span className="text-[10px] text-text-tertiary">vacant</span>}
                    {d.can_manage && p.holders.length < p.seats && (
                      <select className={cn(inputCls, 'text-[10px] py-0 ml-auto')} value="" onChange={(e) => e.target.value && act(() => call('/api/v1/positions/assign', 'POST', { username: e.target.value, position_key: p.key }))}>
                        <option value="">assign…</option>
                        {people.filter((x) => !x.disabled && !p.holders.includes(x.username)).map((x) => (
                          <option key={x.username} value={x.username}>{x.username}{holderOf.get(x.username) ? ` (now ${holderOf.get(x.username)})` : ''}</option>))}
                      </select>)}
                  </div>
                </div>))}
            </div>
          </div>);
      })}
      {d.can_manage && (
        <div className="flex gap-2 flex-wrap items-center">
          <button className={btn} onClick={() => setEdit({ ...EMPTY })}>New position</button>
          {d.templates.map((t: string) => <button key={t} className={btn} onClick={() => act(() => call(`/api/v1/positions/templates/${t}`, 'POST'))}>Add missing {t} positions</button>)}
        </div>)}
      {edit && (
        <div className="border border-bloomberg/40 bg-surface-2 p-2 space-y-2">
          <div className="text-2xs uppercase text-text-tertiary">{edit.created_at ? `Edit ${edit.title}` : 'New position'}</div>
          <div className="grid md:grid-cols-3 gap-1">
            <input className={inputCls} placeholder="key (e.g. head_of_macro)" value={edit.key} disabled={!!edit.created_at} onChange={(e) => setEdit({ ...edit, key: e.target.value })} />
            <input className={inputCls} placeholder="title" value={edit.title} onChange={(e) => setEdit({ ...edit, title: e.target.value })} />
            <div className="flex gap-1">
              <select className={inputCls} value={edit.tier} onChange={(e) => setEdit({ ...edit, tier: Number(e.target.value) })}>{[1, 2, 3, 4].map((t) => <option key={t} value={t}>Tier {t} · {d.tiers[t]}</option>)}</select>
              <select className={inputCls} value={edit.base_role} onChange={(e) => setEdit({ ...edit, base_role: e.target.value })}>{d.base_roles.map((r: string) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}</select>
              <input className={cn(inputCls, 'w-16')} type="number" min={1} value={edit.seats} onChange={(e) => setEdit({ ...edit, seats: Number(e.target.value) })} title="seats" />
            </div>
          </div>
          <input className={cn(inputCls, 'w-full')} placeholder="what this position does" value={edit.description} onChange={(e) => setEdit({ ...edit, description: e.target.value })} />
          <div className="grid grid-cols-2 md:grid-cols-3 gap-x-3">
            {Object.entries(d.capabilities).map(([k, label]: any) => (
              <label key={k} className="flex items-center gap-1 text-[11px]"><input type="checkbox" checked={edit.capabilities.includes(k)}
                onChange={(e) => setEdit({ ...edit, capabilities: e.target.checked ? [...edit.capabilities, k] : edit.capabilities.filter((x: string) => x !== k) })} />{label}</label>))}
          </div>
          <input className={cn(inputCls, 'w-full')} placeholder="workspace panels, comma-separated ids (e.g. pretrade-desk, trade-lifecycle)" value={edit.panels.join(', ')}
            onChange={(e) => setEdit({ ...edit, panels: e.target.value.split(',').map((x) => x.trim()).filter(Boolean) })} />
          <div className="flex gap-1">
            <button className={btn} onClick={() => act(async () => { await call('/api/v1/positions', 'POST', edit); setEdit(null); })}>Save</button>
            {edit.created_at && <button className={btn} onClick={() => act(async () => { await call(`/api/v1/positions/${edit.key}`, 'DELETE'); setEdit(null); })}>Delete</button>}
            <button className={btn} onClick={() => setEdit(null)}>Cancel</button>
            {edit.base_role === 'viewer' && <span className="text-[10px] text-text-tertiary">Read-only positions keep only finance and control capabilities.</span>}
          </div>
        </div>)}
    </div>
  );
}
