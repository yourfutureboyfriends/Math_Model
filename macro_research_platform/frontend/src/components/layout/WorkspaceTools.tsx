/** Shared navigation and accessibility tools for every terminal area. Local view history contains no API data. */
import { useEffect, useState } from 'react';
import { ArrowUp, Bookmark, PanelLeft, Search } from 'lucide-react';
import { useAuth } from '@/context/AuthContext';
import { TableExplorer } from './TableExplorer';
import { preference, savedViews, type SavedView } from '@/lib/workspaceState';
import { currentFund } from '@/lib/fund';
import { setWorkspace, useWorkspace } from '@/lib/focusMode';
import { HUB_MODES, isDashboardMode, setHubMode, useHubMode } from '@/lib/hubMode';
import { PE_TABS, setPeTab, usePeTab } from '@/components/pe/peShared';

function decodeHash(hash: string) { try { return decodeURIComponent(hash); } catch { return hash; } }
type View = SavedView;
function read<T>(key: string, fallback: T): T { try { return JSON.parse(localStorage.getItem(key) ?? 'null') ?? fallback; } catch { return fallback; } }
function write(key: string, value: unknown) { try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* optional browser storage */ } }
export function WorkspaceTools({ onCommand, onHelp, onSidebar, refreshing }: {
  onCommand: () => void; onHelp: () => void; onSidebar: () => void; refreshing?: boolean;
}) {
  const mode = useHubMode(), workspace = useWorkspace(), pe = usePeTab();
  const { user } = useAuth();
  const scope = `terminal.views:${user?.username ?? 'local'}:${currentFund()}`;
  const [hash, setHash] = useState(window.location.hash);
  const [recent, setRecent] = useState<View[]>(() => savedViews(read(`${scope}:recent`, [])));
  const [pins, setPins] = useState<View[]>(() => savedViews(read(`${scope}:pins`, [])));
  const [tableOpen,setTableOpen] = useState(false);
  const [message,setMessage] = useState('');
  const [online, setOnline] = useState(navigator.onLine);
  const [comfortable, setComfortable] = useState(() => preference(read('terminal.readable', false)));
  const [quietMotion, setQuietMotion] = useState(() => preference(read('terminal.reduceMotion', false)));
  useEffect(() => {
    const h = () => setHash(window.location.hash);
    const network = () => setOnline(navigator.onLine);
    window.addEventListener('hashchange', h); window.addEventListener('online', network); window.addEventListener('offline', network);
    return () => { window.removeEventListener('hashchange', h); window.removeEventListener('online', network); window.removeEventListener('offline', network); };
  }, []);
  useEffect(() => { setRecent(savedViews(read(`${scope}:recent`, []))); setPins(savedViews(read(`${scope}:pins`, []))); }, [scope]);
  const area = HUB_MODES.find(m => m.id === mode)?.label ?? mode;
  const suffix = mode === 'markets' ? decodeHash(hash.replace(/^#mkt\/?/, '')).replace(/\//g, ' · ')
    : mode === 'pe' ? PE_TABS.find(t => t.id === pe)?.label : workspace === 'all' ? 'All panels' : workspace === 'focus' ? 'My focus' : workspace;
  const view: View = { id: `${mode}:${isDashboardMode(mode) ? workspace : mode === 'pe' ? pe : hash}`,
    mode, label: `${area} · ${suffix || 'Workspace'}`, workspace, hash: mode === 'markets' ? hash : undefined, pe };
  useEffect(() => {
    setRecent(previous => { const next = [view, ...previous.filter(v => v.id !== view.id)].slice(0, 12); write(`${scope}:recent`, next); return next; });
  }, [view.id, scope]);
  useEffect(() => {
    document.documentElement.classList.toggle('terminal-readable', comfortable);
    document.documentElement.classList.toggle('terminal-reduce-motion', quietMotion);
    write('terminal.readable', comfortable); write('terminal.reduceMotion', quietMotion);
  }, [comfortable, quietMotion]);
  const open = (id: string) => {
    const v = [...pins, ...recent].find(v => v.id === id); if (!v) return;
    if (v.mode === 'markets' && v.hash?.startsWith('#mkt/')) window.location.hash = v.hash;
    setHubMode(v.mode);
    if (isDashboardMode(v.mode) && v.workspace) setWorkspace(v.workspace, v.mode);
    if (v.mode === 'pe' && v.pe) setPeTab(v.pe);
  };
  const pinned = pins.some(v => v.id === view.id);
  return <>
    <div className="workspace-tools flex flex-wrap items-center gap-2 px-4 py-2 border-b border-border-subtle bg-surface-1 text-[11px]" aria-label="Workspace tools">
      <button onClick={onSidebar} aria-label="Toggle navigation sidebar" title="Toggle sidebar · Ctrl/⌘ B" className="p-1.5 rounded border border-border"><PanelLeft className="w-3.5 h-3.5" /></button>
      <span className="font-medium text-text-primary max-w-[240px] truncate" title={view.label}>{view.label}</span>
      <button onClick={() => { const next = pinned ? pins.filter(v => v.id !== view.id) : [...pins, view].slice(-20); setPins(next); write(`${scope}:pins`, next); }}
        aria-pressed={pinned} title={pinned ? 'Unpin this workspace' : 'Pin this workspace'} className="p-1.5 rounded border border-border"><Bookmark className={`w-3.5 h-3.5 ${pinned ? 'fill-current text-bloomberg' : ''}`} /></button>
      <select aria-label="Pinned workspaces" value="" onChange={e => open(e.target.value)} className="bg-bg border border-border rounded px-2 py-1 max-w-[190px]">
        <option value="">Pinned ({pins.length})</option>{pins.map(v => <option key={v.id} value={v.id}>{v.label}</option>)}
      </select>
      <select aria-label="Recent workspaces" value="" onChange={e => open(e.target.value)} className="bg-bg border border-border rounded px-2 py-1 max-w-[190px]">
        <option value="">Recent views</option>{recent.filter(v => v.id !== view.id).map(v => <option key={v.id} value={v.id}>{v.label}</option>)}
      </select>
      <button onClick={onCommand} className="inline-flex gap-1 items-center text-text-secondary"><Search className="w-3.5 h-3.5" />Find anything <kbd className="text-text-tertiary">⌘K</kbd></button>
      <button onClick={()=>setTableOpen(true)} className="px-2 py-1 border border-border rounded text-text-secondary">Tables & export</button>
      <details className="relative text-text-secondary"><summary className="cursor-pointer">Saved views</summary><div className="absolute top-6 left-0 z-50 w-72 max-h-72 overflow-auto rounded-lg border border-border bg-surface-1 p-3 shadow-xl">
        <div className="font-medium mb-2">Manage pinned workspaces</div>
        {!pins.length&&<p className="text-text-tertiary">Pin a workspace using the bookmark button.</p>}
        {pins.map(v=><div key={v.id} className="flex gap-2 items-center py-1"><button className="flex-1 text-left truncate" onClick={()=>open(v.id)}>{v.label}</button><button aria-label={`Unpin ${v.label}`} className="text-red" onClick={()=>{const next=pins.filter(p=>p.id!==v.id);setPins(next);write(`${scope}:pins`,next);}}>Remove</button></div>)}
        <button className="underline mt-3" onClick={()=>{setRecent([]);write(`${scope}:recent`,[]);setMessage('Recent workspace history cleared for this user and fund.');}}>Clear recent history</button>
      </div></details>
      <div className="flex gap-3 items-center ml-auto text-text-secondary">
        <label className="inline-flex gap-1 items-center"><input type="checkbox" checked={comfortable} onChange={e => setComfortable(e.target.checked)} />Readable tables</label>
        <label className="inline-flex gap-1 items-center"><input type="checkbox" checked={quietMotion} onChange={e => setQuietMotion(e.target.checked)} />Less motion</label>
        <button onClick={onHelp} className="underline underline-offset-2">Shortcuts</button>
        <button aria-label="Back to top" title="Back to top" onClick={() => window.scrollTo({top: 0, behavior: quietMotion ? 'instant' : 'smooth'})}><ArrowUp className="w-3.5 h-3.5" /></button>
      </div>
    </div>
    {tableOpen&&<TableExplorer onClose={()=>setTableOpen(false)}/>}
    {message&&<div role="status" className="px-4 py-1 text-xs text-text-secondary">{message}<button className="underline ml-3" onClick={()=>setMessage('')}>Dismiss</button></div>}
    {!online && <div role="status" className="px-4 py-2 text-xs text-amber bg-amber/10">You’re offline. Displayed data may be out of date; reconnect before relying on live results.</div>}
    {refreshing && <div role="status" className="px-4 py-1 text-[10px] text-text-tertiary">Refreshing macro data · your workspace remains available</div>}
  </>;
}
