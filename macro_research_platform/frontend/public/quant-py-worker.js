/* Quant Lab code runner: Python (Pyodide) in a Web Worker, so user strategy code runs in the
 * browser — never on the server. The engine (api/quant/codelab.py) and the price data are fetched by
 * the page (it holds the sign-in token) and posted here.
 * Messages in:  {type:'init', engine}, {type:'prepare', id, code}, {type:'run', id, code, data, costs}
 * Messages out: {type:'ready'|'status'|'stdout'|'result'|'error', ...}
 */
const PYODIDE = 'https://cdn.jsdelivr.net/pyodide/v314.0.5/full/';
let py = null;

async function init(engine, qcalgo) {
  postMessage({ type: 'status', text: 'Loading Python (first time ≈10 s)…' });
  const { loadPyodide } = await import(PYODIDE + 'pyodide.mjs');   // module worker (importScripts is blocked in some embedded browsers)
  py = await loadPyodide({ indexURL: PYODIDE });
  py.setStdout({ batched: (s) => postMessage({ type: 'stdout', text: s }) });
  py.setStderr({ batched: (s) => postMessage({ type: 'stdout', text: s }) });
  postMessage({ type: 'status', text: 'Loading numpy and pandas…' });
  await py.loadPackage(['numpy', 'pandas']);
  if (qcalgo) py.FS.writeFile('/home/pyodide/qcalgo.py', qcalgo);   // the QuantConnect-style API, imported by the engine
  py.FS.writeFile('/home/pyodide/codelab.py', engine);
  await py.runPythonAsync(`
import sys, json, base64
sys.path.insert(0, '/home/pyodide')
import numpy as np, pandas as pd
import codelab

def _arr(b64, shape):
    a = np.frombuffer(base64.b64decode(b64), dtype=np.float32).astype(np.float64)
    return a.reshape(shape) if shape else a

def _prepare(code):
    st = codelab.load_strategy(code)
    return json.dumps({k: st[k] for k in ("universe", "start", "params", "benchmark", "holdout", "code_hash", "account", "tradable", "fx_hedge", "options", "fundamentals", "custom")})

def _run(code, payload, costs):
    p = json.loads(payload)
    idx = pd.DatetimeIndex(pd.to_datetime(p["dates"]))
    T, cols = len(idx), p["tickers"]
    fr = {f: pd.DataFrame(_arr(p[f], (T, len(cols))), index=idx, columns=cols) for f in ("close", "open", "high", "low", "volume")}
    obs = np.frombuffer(base64.b64decode(p["observed"]), dtype=np.uint8).reshape(T, len(cols)).astype(bool) if p.get("observed") else None
    data = codelab.Data(fr["close"], fr["open"], fr["high"], fr["low"], fr["volume"],
                        rf=pd.Series(_arr(p["rf"], None), index=idx) if p.get("rf_known", True) else None,
                        vix=pd.Series(_arr(p["vix"], None), index=idx),
                        observed=pd.DataFrame(obs, index=idx, columns=cols) if obs is not None else None,
                        rf_known=p.get("rf_known", True), provenance=p.get("provenance"),
                        instruments=p.get("instruments"), account_currency=p.get("account_currency") or "USD",
                        usd_per_unit=pd.Series(_arr(p["usd_per_unit"], None), index=idx) if p.get("usd_per_unit") else None,
                        options={k[4:]: pd.DataFrame(_arr(p["m_" + k], (T, len(c))), index=idx, columns=c)
                                 for k, c in (p.get("micro_cols") or {}).items() if k.startswith("opt_")} or None,
                        **{k: pd.DataFrame(_arr(p["m_" + k], (T, len(c))), index=idx, columns=c)
                           for k, c in (p.get("micro_cols") or {}).items() if not k.startswith(("opt_", "fund_", "cust_"))},
                        custom={k[5:]: pd.DataFrame(_arr(p["m_" + k], (T, len(c))), index=idx, columns=c)
                                for k, c in (p.get("micro_cols") or {}).items() if k.startswith("cust_")} or None,
                        fundamentals={k[5:]: pd.DataFrame(_arr(p["m_" + k], (T, len(c))), index=idx, columns=c)
                                      for k, c in (p.get("micro_cols") or {}).items() if k.startswith("fund_")} or None)
    if "roll" in data.opt:
        data.opt["roll"] = data.opt["roll"].fillna(0).astype(bool)
    bm = pd.Series(_arr(p["benchmark"], None), index=idx) if p.get("benchmark") else None
    st = codelab.load_strategy(code)
    # the result first; research_checks() adds the slower checks right after (message 'checks')
    out = codelab.evaluate(st["strategy"], data, st["params"], st["start"], codelab.run_costs(st, json.loads(costs)) or None, bm,
                           st["holdout"], st["code_hash"], signal=st.get("signal"), on_bar=st.get("on_bar"), setup=st.get("setup"),
                           checks=False)
    out["provenance"]["runtime"] = "browser (Pyodide) — pandas " + pd.__version__ + ", numpy " + np.__version__
    if p.get("engine_version") and p["engine_version"] != codelab.ENGINE_VERSION:
        out["provenance"]["engine_mismatch"] = f"server data prepared for engine {p['engine_version']}, browser ran {codelab.ENGINE_VERSION}"
    return json.dumps(out)

def _checks():
    return json.dumps(codelab.research_checks())
`);
  postMessage({ type: 'ready' });
}

async function withPackages(code) {
  // Optional extra libraries the code imports (scipy, scikit-learn, statsmodels…) are fetched on demand.
  try { await py.loadPackagesFromImports(code); } catch (e) { /* unknown imports surface as errors when run */ }
}

function pyError(e) {
  const msg = String(e && e.message ? e.message : e);
  const lines = msg.trim().split('\n');
  const strat = lines.filter((l) => l.includes('"<strategy>"'));
  const last = lines[lines.length - 1];
  const where = strat.length ? strat[strat.length - 1].trim().replace(/^File "<strategy>", /, '') : '';
  return where ? `${last}  (${where})` : last;
}

onmessage = async (ev) => {
  const m = ev.data;
  try {
    if (m.type === 'init') { if (!py) await init(m.engine, m.qcalgo); else postMessage({ type: 'ready' }); return; }
    if (!py) throw new Error('Python is not loaded yet.');
    if (m.type === 'prepare') {
      await withPackages(m.code);
      const r = py.globals.get('_prepare')(m.code);
      postMessage({ type: 'prepared', id: m.id, header: JSON.parse(r) });
    } else if (m.type === 'run') {
      postMessage({ type: 'status', text: 'Running your strategy…' });
      const r = py.globals.get('_run')(m.code, JSON.stringify(m.data), JSON.stringify(m.costs || {}));
      postMessage({ type: 'result', id: m.id, result: JSON.parse(r) });
    } else if (m.type === 'checks') {
      postMessage({ type: 'status', text: 'Checking for look-ahead, capacity and factor risk…' });
      const r = py.globals.get('_checks')();
      postMessage({ type: 'checked', id: m.id, checks: JSON.parse(r) });
    }
  } catch (e) {
    postMessage({ type: 'error', id: m.id, error: pyError(e) });
  }
};
