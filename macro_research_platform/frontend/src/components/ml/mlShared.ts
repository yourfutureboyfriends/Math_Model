/** ML area (top-bar mode 'ml'): tab and selected-task state shared by the page and its sidebar, plus the data hooks
 *  and the in-browser forward pass the visualizer uses. */
import { useEffect, useState } from 'react';

export type MlTab = 'overview' | 'lab' | 'visualizer' | 'explain' | 'monitoring' | 'registry' | 'knowledge' | 'method';
export const ML_TABS: { id: MlTab; label: string; desc: string }[] = [
  { id: 'overview', label: 'Overview', desc: 'Every task × every model, the served signals and the platform’s health' },
  { id: 'lab', label: 'Model lab', desc: 'Leaderboard and head-to-head comparison: forecasts over time, ROC, calibration, skill by era' },
  { id: 'visualizer', label: 'Network visualizer', desc: 'The neural networks drawn and run in your browser; the deep sequence and regime models' },
  { id: 'explain', label: 'Explainability', desc: 'What drives each forecast: attributions, importance by series and data group, coefficients' },
  { id: 'monitoring', label: 'Monitoring', desc: 'Input drift and range checks, retraining log, feature store and panel coverage' },
  { id: 'registry', label: 'Registry', desc: 'Stages (production / shadow), promotions with approvals, the forecast audit log' },
  { id: 'knowledge', label: 'Knowledge scanner', desc: 'New indicators the models test each month; a person approves additions' },
  { id: 'method', label: 'Method & research', desc: 'How it works and the research it follows' },
];
const TAB_KEY = 'ml_tab', TASK_KEY = 'ml_task', TAB_EVT = 'ml-tab', TASK_EVT = 'ml-task';

function sticky<T extends string>(key: string, evt: string, valid: (v: string | null) => v is T, fallback: T) {
  const get = (): T => { try { const v = localStorage.getItem(key); return valid(v) ? v : fallback; } catch { return fallback; } };
  const set = (v: T) => { try { localStorage.setItem(key, v); } catch { /* storage unavailable */ } window.dispatchEvent(new CustomEvent(evt, { detail: v })); };
  const use = (): T => {
    const [v, setV] = useState<T>(get);
    useEffect(() => { const h = (e: Event) => setV((e as CustomEvent).detail as T); window.addEventListener(evt, h); return () => window.removeEventListener(evt, h); }, []);
    return v;
  };
  return { get, set, use };
}
const tab = sticky<MlTab>(TAB_KEY, TAB_EVT, (v): v is MlTab => ML_TABS.some((t) => t.id === v), 'overview');
const task = sticky<string>(TASK_KEY, TASK_EVT, (v): v is string => !!v && /^[a-z0-9_]+$/.test(v), 'recession_12m');
export const useMlTab = tab.use, setMlTab = tab.set, useMlTask = task.use, setMlTask = task.set;

/** The engine's tasks, known before the server answers (so pickers and the sidebar are never empty). */
export const KNOWN_TASKS: { task: string; title: string }[] = [
  { task: 'recession_12m', title: 'US recession within 12 months' },
  { task: 'spx_drawdown_6m', title: 'S&P 500 falls 10%+ within 6 months' },
  { task: 'yields_up_3m', title: '10Y yield higher in 3 months' },
  { task: 'inflation_up_3m', title: 'CPI inflation higher in 3 months' },
  { task: 'oil_up_3m', title: 'Oil higher in 3 months' },
  { task: 'unemployment_up_6m', title: 'Unemployment higher in 6 months' },
];

async function getJSON(url: string): Promise<any> {
  const r = await fetch(url);
  const j = await r.json().catch(() => null);
  if (!r.ok) throw new Error(j?.detail ? String(j.detail) : r.status === 404 ? 'The server does not have the ML engine yet — restart the backend' : `HTTP ${r.status}`);
  return j;
}

/** All tasks (summary, no weights). Retries while the server is unreachable or restarting; refreshes every minute
 *  while any task is still training, so cards fill in as they finish. */
export function useTasks(tick = 0) {
  const [d, setD] = useState<any[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true, timer = 0, tries = 0;
    const load = () => getJSON('/api/v1/ml/tasks').then((j) => {
      if (!live) return;
      setD(j?.tasks ?? []); setError(null);
      const pending = (j?.tasks ?? []).filter((t: any) => !t.ready);
      if (pending.length) timer = window.setTimeout(load, pending.some((t: any) => t.training) ? 10_000 : 60_000);
    }).catch((e) => {
      if (!live) return;
      setError(e.message);
      if (tries++ < 20) timer = window.setTimeout(load, 5_000);
    });
    load();
    return () => { live = false; clearTimeout(timer); };
  }, [tick]);
  return { tasks: d, error };
}

/** One task in full (trains on its first request of the month — up to a few minutes). undefined = loading;
 *  {available:false, reason} on failure. Retries a few times while the server restarts. */
export function useTask(name: string, tick = 0) {
  const [d, setD] = useState<any>(undefined);
  const [n, setN] = useState(0);
  const [progress, setProgress] = useState(0);
  useEffect(() => {
    let live = true, timer = 0, tries = 0;
    setD(undefined);
    const load = () => getJSON(`/api/v1/ml/tasks/${name}`).then((j) => {
      if (!live) return;
      if (j?.training) { setD(undefined); setProgress(j.elapsed_s ?? 0); timer = window.setTimeout(load, 4_000); return; }   // poll until trained
      setD(j);
    }).catch((e) => {
      if (!live) return;
      if (tries++ < 6) timer = window.setTimeout(load, 5_000);
      else setD({ available: false, reason: e.message });
    });
    load();
    return () => { live = false; clearTimeout(timer); };
  }, [name, tick, n]);
  return { d, retry: () => setN((v) => v + 1), progress };
}

// ── the network, run in the browser from its exported weights ──────────────────
export type Net = { W1: number[][]; b1: number[]; W2: number[]; b2: number };
export type Weights = { mu: number[]; sd: number[]; nets: Net[] };
export const sigmoid = (z: number) => 1 / (1 + Math.exp(-Math.max(-35, Math.min(35, z))));
const logit = (p: number) => { const q = Math.min(1 - 1e-4, Math.max(1e-4, p)); return Math.log(q / (1 - q)); };

/** One network: tanh hidden layer, logistic output. */
export function forward(net: Net, w: Weights, x: number[]) {
  const z = x.map((v, i) => (v - w.mu[i]) / w.sd[i]);
  const h = net.b1.map((b, j) => Math.tanh(b + z.reduce((s, zi, i) => s + zi * net.W1[i][j], 0)));
  return { z, h, p: sigmoid(net.b2 + h.reduce((s, hj, j) => s + hj * net.W2[j], 0)) };
}

/** The ensemble: averaged, then recalibrated (Platt); the range across the individual networks. */
export function ensemble(w: Weights, cal: number[] | null | undefined, x: number[]) {
  const raws = w.nets.map((n) => forward(n, w, x).p);
  const platt = (r: number) => (cal ? sigmoid(cal[0] + cal[1] * logit(r)) : r);
  const each = raws.map(platt);
  return { p: platt(raws.reduce((a, b) => a + b, 0) / raws.length), lo: Math.min(...each), hi: Math.max(...each), each };
}

export const skillText = (s: number | null | undefined) => (s == null ? '—' : `${s > 0 ? '+' : ''}${(s * 100).toFixed(0)}%`);

/** Any ML endpoint as JSON, with retries while the server restarts. */
export function useJSON(url: string | null, tick = 0) {
  const [d, setD] = useState<any>(undefined);
  useEffect(() => {
    if (!url) return;
    let live = true, timer = 0, tries = 0;
    setD(undefined);
    const load = () => getJSON(url).then((j) => live && setD(j)).catch((e) => { if (!live) return; if (tries++ < 4) timer = window.setTimeout(load, 4000); else setD({ error: e.message }); });
    load();
    return () => { live = false; clearTimeout(timer); };
  }, [url, tick]);
  return d;
}


/** Reject incomplete or incompatible exported models before drawing a forward pass. */
export function validWeights(w:any,inputs:number):w is Weights {
 const finite=(v:any)=>typeof v==='number'&&Number.isFinite(v);
 return !!w&&inputs>0&&Array.isArray(w.mu)&&w.mu.length===inputs&&w.mu.every(finite)&&Array.isArray(w.sd)&&w.sd.length===inputs&&w.sd.every((v:any)=>finite(v)&&v>0)&&Array.isArray(w.nets)&&w.nets.length>0&&w.nets.every((n:any)=>Array.isArray(n.b1)&&n.b1.length>0&&n.b1.every(finite)&&finite(n.b2)&&Array.isArray(n.W2)&&n.W2.length===n.b1.length&&n.W2.every(finite)&&Array.isArray(n.W1)&&n.W1.length===inputs&&n.W1.every((row:any)=>Array.isArray(row)&&row.length===n.b1.length&&row.every(finite)));
}

export function connectionSignals(net:Net,w:Weights,x:number[]) {
 const f=forward(net,w,x);
 return {input:net.W1.map((row,i)=>row.map(weight=>weight*f.z[i])),output:net.W2.map((weight,j)=>weight*f.h[j])};
}


export function selectedPrediction(net:Net,w:Weights,x:number[],cal:number[]|null|undefined) {
 const raw=forward(net,w,x).p;
 return {raw,p:cal?sigmoid(cal[0]+cal[1]*logit(raw)):raw};
}
