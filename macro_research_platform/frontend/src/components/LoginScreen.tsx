// Fund selection lives before authentication. Credentials and membership are verified by the server.
import { useEffect, useState, type CSSProperties } from 'react';
import { ArrowRight, BarChart3, Eye, EyeOff, Layers, Lock, ShieldCheck, Terminal } from 'lucide-react';
import { useAuth } from '@/context/AuthContext';
import { currentFund } from '@/lib/fund';
import { applyBrand, cachedFunds, type FundInfo } from '@/lib/fundBrand';

// The markets as they stand — real public data, so the first screen is already useful. Hidden if it can't load.
const STRIP: [string, string, (v: number) => string][] = [
  ['^GSPC', 'S&P 500', (v) => v.toLocaleString(undefined, { maximumFractionDigits: 0 })],
  ['^NDX', 'Nasdaq 100', (v) => v.toLocaleString(undefined, { maximumFractionDigits: 0 })],
  ['^TNX', 'US 10Y', (v) => `${v.toFixed(2)}%`],
  ['EURUSD=X', 'EUR/USD', (v) => v.toFixed(4)],
  ['GC=F', 'Gold', (v) => v.toLocaleString(undefined, { maximumFractionDigits: 0 })],
  ['BTC-USD', 'Bitcoin', (v) => v.toLocaleString(undefined, { maximumFractionDigits: 0 })],
];
type StripRow = { symbol: string; price: number; date?: string; change_1d?: number | null; spark?: number[] };

function Spark({ values, up }: { values: number[]; up: boolean }) {
  if (values.length < 2) return null;
  const lo = Math.min(...values), hi = Math.max(...values), W = 64, H = 18;
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * W},${H - 2 - ((v - lo) / (hi - lo || 1)) * (H - 4)}`).join(' ');
  return <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} aria-hidden><polyline points={pts} fill="none" stroke={up ? '#3fbf8f' : '#e66767'} strokeWidth="1.4" strokeLinejoin="round" strokeLinecap="round" /></svg>;
}

function MarketsStrip() {
  const [rows, setRows] = useState<StripRow[] | null>(null);
  useEffect(() => {
    let live = true;
    const c = new AbortController();
    const t = setTimeout(() => c.abort(), 12000);
    fetch('/api/v1/mkt/overview', { signal: c.signal }).then((r) => (r.ok ? r.json() : null)).then((j) => {
      if (!live || !j?.groups) return;
      const all: Record<string, StripRow> = Object.fromEntries(j.groups.flatMap((g: { rows: StripRow[] }) => g.rows).map((r: StripRow) => [r.symbol, r]));
      setRows(STRIP.map(([s]) => all[s]).filter((r): r is StripRow => !!r && typeof r.price === 'number'));
    }).catch(() => {}).finally(() => clearTimeout(t));
    return () => { live = false; clearTimeout(t); c.abort(); };
  }, []);
  if (!rows?.length) return null;
  const day = rows.find((r) => r.symbol === '^GSPC')?.date;        // the equity session (crypto trades at weekends)
  return (
    <div className="login-markets" aria-label="Markets snapshot">
      <div className="login-markets-head"><span>MARKETS</span>{day && <span>close {new Date(`${day}T12:00:00`).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' })}</span>}</div>
      <div className="login-markets-grid">
        {rows.map((r) => {
          const [, label, fmt] = STRIP.find(([s]) => s === r.symbol)!;
          const sp = r.spark ?? [];
          // yields: the day's change in basis points, from the last two closes
          const bpChg = r.symbol === '^TNX' && sp.length > 1 ? (sp[sp.length - 1] - sp[sp.length - 2]) * 100 : null;
          const ch = r.change_1d ?? null, up = (bpChg ?? ch ?? 0) >= 0;
          return (
            <div key={r.symbol} className="login-market">
              <div className="login-market-top"><span>{label}</span><Spark values={(r.spark ?? []).slice(-30)} up={up} /></div>
              <div className="login-market-val">{fmt(r.price)}</div>
              <div className={up ? 'login-up' : 'login-down'}>{r.symbol === '^TNX' ? (bpChg == null ? '—' : `${bpChg >= 0 ? '+' : ''}${bpChg.toFixed(1)} bp`) : ch == null ? '—' : `${up ? '+' : ''}${(ch * 100).toFixed(2)}%`}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** US session state and New York time, refreshed each minute. */
function useMarketClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => { const t = setInterval(() => setNow(new Date()), 30000); return () => clearInterval(t); }, []);
  const ny = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }));
  const mins = ny.getHours() * 60 + ny.getMinutes(), wd = ny.getDay();
  const open = wd >= 1 && wd <= 5 && mins >= 570 && mins < 960;
  const pre = wd >= 1 && wd <= 5 && mins >= 240 && mins < 570;
  const state = open ? 'US markets open' : pre ? 'US pre-market' : 'US markets closed';
  return { open, state, time: ny.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' }) };
}

export function LoginScreen() {
  const { login }=useAuth();
  const [funds,setFunds]=useState<FundInfo[]>(cachedFunds);
  const [fundId,setFundId]=useState(currentFund);
  const [brandingError,setBrandingError]=useState(false);
  const [brandingAttempt,setBrandingAttempt]=useState(0);
  const [logoError,setLogoError]=useState(false);
  const selectedFund=funds.find(f=>f.id===fundId);
  const [username,setUsername]=useState(()=>{try{return localStorage.getItem('terminal.rememberedUsername')??'';}catch{return '';}});
  const [rememberUsername,setRememberUsername]=useState(()=>{try{return !!localStorage.getItem('terminal.rememberedUsername');}catch{return false;}});
  const [password,setPassword]=useState('');
  const [passwordVisible,setPasswordVisible]=useState(false);
  const [capsLock,setCapsLock]=useState(false);
  const [otp,setOtp]=useState('');
  const [needOtp,setNeedOtp]=useState(false);
  const [loading,setLoading]=useState(false);
  const [error,setError]=useState<string|null>(null);
  const [showDemo,setShowDemo]=useState(false);
  const [defaultAccounts,setDefaultAccounts]=useState<string[]|null>(null);

  useEffect(()=>{
    let live=true;const controller=new AbortController();
    const timeout=setTimeout(()=>controller.abort(),15000);
    setBrandingError(false);
    fetch('/api/auth/funds',{signal:controller.signal}).then(async r=>{if(!r.ok)throw new Error('Branding unavailable');return r.json();}).then(j=>{
      if(!live)return;
      const rows:FundInfo[]=Array.isArray(j.funds)?j.funds.filter((f:FundInfo)=>f&&typeof f.id==='string'&&typeof f.name==='string'):[];
      setFunds(rows);
      try{localStorage.setItem('macro.funds.cache',JSON.stringify(rows));}catch{/* optional storage */}
      setFundId(id=>rows.some(f=>f.id===id)?id:rows[0]?.id??id);
    }).catch(()=>{if(live)setBrandingError(true);}).finally(()=>clearTimeout(timeout));
    return()=>{live=false;clearTimeout(timeout);controller.abort();};
  },[brandingAttempt]);
  useEffect(()=>{setLogoError(false);applyBrand(selectedFund?.brand);},[fundId,selectedFund]);
  useEffect(()=>{
    if(!import.meta.env.DEV)return;
    let live=true;
    fetch('/api/auth/status').then(r=>r.json()).then(j=>{if(!live)return;setShowDemo(Boolean(j.default_credentials_active));setDefaultAccounts(Array.isArray(j.default_credential_accounts)?j.default_credential_accounts:null);}).catch(()=>{if(live)setShowDemo(false);});
    return()=>{live=false;};
  },[]);

  const handleSubmit=async(e:React.FormEvent)=>{
    e.preventDefault();setLoading(true);setError(null);
    try{
      await login(username.trim(),password,needOtp?otp:undefined,fundId);
      try{if(rememberUsername)localStorage.setItem('terminal.rememberedUsername',username.trim());else localStorage.removeItem('terminal.rememberedUsername');}catch{/* optional storage */}
    }catch(err){if((err as {mfaRequired?:boolean})?.mfaRequired)setNeedOtp(true);setError(err instanceof Error?err.message:'Login failed');}
    finally{setLoading(false);}
  };
  const demoCredentials=[
    {role:'admin',user:'admin',pass:'admin123',desc:'Administrator'},
    {role:'pm',user:'pm',pass:'pm123',desc:'Portfolio Manager'},
    {role:'analyst',user:'analyst',pass:'analyst123',desc:'Macro Analyst'},
    {role:'risk',user:'risk',pass:'risk123',desc:'Risk Officer'},
    {role:'quant',user:'quant',pass:'quant123',desc:'Quant Researcher'},
  ];
  const band=selectedFund?.brand?.band??'15 35 62';
  const clock=useMarketClock();
  return <main className="login-stage login-redesign" style={{'--login-brand-band':band} as CSSProperties}>
    <div className="login-topline"><span className="inline-flex items-center gap-2"><Terminal size={15}/>MACRO TERMINAL</span><span className="login-clock"><i className={clock.open?'on':''}/>{clock.state} · New York {clock.time}</span></div>
    <div className="login-layout">
      <section className="login-story" aria-label="Fund identity and platform overview">
        <div className="login-logo-plaque">
          {selectedFund?.logo&&!logoError?<img src={`/api/auth/funds/${encodeURIComponent(fundId)}/logo?v=${selectedFund.logo_version??0}`} alt={`${selectedFund.name} logo`} onError={()=>setLogoError(true)}/>:<div className="login-logo-fallback"><Terminal size={32}/><span>{selectedFund?.brand?.short_name??'Macro Terminal'}</span></div>}
        </div>
        <div className="login-fund-caption">YOUR INVESTMENT WORKSPACE</div>
        <h1>{selectedFund?.name??'Macro Terminal'}</h1>
        <h2>From market context<br/>to investment decisions.</h2>
        <p className="login-story-copy">Connect macro research, company valuation and portfolio risk in one working environment.</p>
        <MarketsStrip/>
        <div className="login-capabilities">
          {[{Icon:BarChart3,title:'Macro & markets',sub:'Understand the environment'},{Icon:Layers,title:'Valuation & PE',sub:'Inspect the assumptions'},{Icon:Lock,title:'Portfolio & risk',sub:'Review exposures and decisions'}].map(({Icon,title,sub})=><div key={title}><Icon size={17}/><span><strong>{title}</strong><small>{sub}</small></span></div>)}
        </div>
      </section>
      <section className="login-access" aria-label="Sign in">
        <div className="login-card login-access-card">
          <span className="login-eyebrow">MEMBER ACCESS</span>
          <h2>Welcome back</h2>
          <p className="login-access-copy">Choose your fund — or your personal workspace — and sign in.</p>
          <form onSubmit={handleSubmit} className="login-form">
            <div>
              <label htmlFor="login-fund">Workspace</label>
              <select id="login-fund" aria-label="Workspace" value={fundId} disabled={loading||!funds.length} onChange={e=>{setFundId(e.target.value);setNeedOtp(false);setOtp('');setError(null);}}>
                {!funds.length&&<option value={fundId}>{brandingError?'Fund list unavailable':'Loading funds…'}</option>}
                {funds.map(f=><option key={f.id} value={f.id}>{f.name}</option>)}
              </select>
              {brandingError&&<p className="login-inline-note" role="status">Could not refresh fund details. <button type="button" onClick={()=>setBrandingAttempt(x=>x+1)}>Try again</button></p>}
            </div>
            <div><label htmlFor="login-username">Username</label><input id="login-username" aria-label="Username" autoComplete="username" value={username} onChange={e=>setUsername(e.target.value)} placeholder="Your username" disabled={loading} required/></div>
            <div>
              <label htmlFor="login-password">Password</label>
              <div className="login-password-field"><input id="login-password" aria-label="Password" type={passwordVisible?'text':'password'} autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} onKeyUp={e=>setCapsLock(e.getModifierState('CapsLock'))} onKeyDown={e=>setCapsLock(e.getModifierState('CapsLock'))} onBlur={()=>setCapsLock(false)} placeholder="Your password" disabled={loading} required/>
                <button type="button" aria-label={passwordVisible?'Hide password':'Show password'} aria-pressed={passwordVisible} onClick={()=>setPasswordVisible(v=>!v)} disabled={loading}>{passwordVisible?<EyeOff size={17}/>:<Eye size={17}/>}</button>
              </div>
              {capsLock&&<p className="login-inline-note" role="status">Caps Lock is on.</p>}
            </div>
            <label className="login-remember"><input type="checkbox" checked={rememberUsername} onChange={e=>setRememberUsername(e.target.checked)} disabled={loading}/>Remember username on this device</label>
            {needOtp&&<div><label htmlFor="login-otp">Two-factor code</label><input id="login-otp" aria-label="Two-factor code" value={otp} onChange={e=>setOtp(e.target.value)} autoComplete="one-time-code" inputMode="numeric" autoFocus placeholder="Code or recovery code" disabled={loading}/></div>}
            {error&&<div className="login-error" role="alert">{error}</div>}
            <button type="submit" disabled={loading||!username.trim()||!password} className="login-cta login-submit">{loading?'Signing in…':'Sign In'}{!loading&&<ArrowRight size={17}/>}</button>
          </form>
          <div className="login-access-note"><ShieldCheck size={13}/><span>Access is verified for the selected fund · two-factor supported</span></div>
          {showDemo&&<details className="login-development"><summary>Development accounts</summary><p>Default accounts require a new password at first sign-in.</p><div className="grid grid-cols-2 gap-2">{demoCredentials.filter(c=>!defaultAccounts||defaultAccounts.includes(c.user)).map(c=><button type="button" key={c.role} onClick={()=>{setUsername(c.user);setPassword(c.pass);}}><strong>{c.desc}</strong><small>{c.user} / {c.pass}</small></button>)}</div></details>}
        </div>
        <p className="login-support-note">Need access? Contact your fund administrator.</p>
      </section>
    </div>
    <footer className="login-footer"><span>Macro Terminal <b>v8.0</b></span><span>Sessions expire after 8 hours · Account lockout after 5 failed attempts</span></footer>
  </main>;
}
