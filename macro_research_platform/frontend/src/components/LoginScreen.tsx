// Fund selection lives before authentication. Credentials and membership are verified by the server.
import { useEffect, useId, useState, type CSSProperties } from 'react';
import { ArrowRight, BarChart3, Eye, EyeOff, Layers, Lock, Terminal } from 'lucide-react';
import { useAuth } from '@/context/AuthContext';
import { currentFund } from '@/lib/fund';
import { applyBrand, cachedFunds, type FundInfo } from '@/lib/fundBrand';

function ResearchGraphic() {
  const id=useId().replace(/:/g,'');
  return <svg className="login-research-graphic" viewBox="0 0 520 180" role="img" aria-label="Illustrative research workflow: market context, valuation and risk review">
    <defs><linearGradient id={id} x1="0" y1="1" x2="1" y2="0"><stop stopColor="currentColor" stopOpacity=".04"/><stop offset="1" stopColor="currentColor" stopOpacity=".24"/></linearGradient></defs>
    <path d="M22 144H498M22 108H498M22 72H498M22 36H498M58 20V158M138 20V158M218 20V158M298 20V158M378 20V158M458 20V158" stroke="currentColor" strokeOpacity=".09"/>
    <path d="M22 144C80 144 78 112 126 112S170 122 208 95S262 110 300 72S354 86 396 47S455 54 498 24V158H22Z" fill={`url(#${id})`}/>
    <path d="M22 144C80 144 78 112 126 112S170 122 208 95S262 110 300 72S354 86 396 47S455 54 498 24" fill="none" stroke="currentColor" strokeOpacity=".7" strokeWidth="2"/>
    {[{x:126,y:112,label:'CONTEXT'},{x:300,y:72,label:'VALUATION'},{x:458,y:40,label:'RISK REVIEW'}].map(p=><g key={p.label}><circle cx={p.x} cy={p.y} r="13" fill="currentColor" fillOpacity=".08"/><circle cx={p.x} cy={p.y} r="4" fill="currentColor"/><text x={p.x} y={p.y+29} textAnchor="middle" fontSize="8" fill="currentColor" opacity=".7" letterSpacing="1.2">{p.label}</text></g>)}
  </svg>;
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
  return <main className="login-stage login-redesign" style={{'--login-brand-band':band} as CSSProperties}>
    <div className="login-topline"><span className="inline-flex items-center gap-2"><Terminal size={15}/>MACRO TERMINAL</span><span>Research & investment workspace</span></div>
    <div className="login-layout">
      <section className="login-story" aria-label="Fund identity and platform overview">
        <div className="login-logo-plaque">
          {selectedFund?.logo&&!logoError?<img src={`/api/auth/funds/${encodeURIComponent(fundId)}/logo?v=${selectedFund.logo_version??0}`} alt={`${selectedFund.name} logo`} onError={()=>setLogoError(true)}/>:<div className="login-logo-fallback"><Terminal size={32}/><span>{selectedFund?.brand?.short_name??'Macro Terminal'}</span></div>}
        </div>
        <div className="login-fund-caption">YOUR INVESTMENT WORKSPACE</div>
        <h1>{selectedFund?.name??'Macro Terminal'}</h1>
        <h2>From market context<br/>to investment decisions.</h2>
        <p className="login-story-copy">Connect macro research, company valuation and portfolio risk in one working environment.</p>
        <ResearchGraphic/>
        <div className="login-capabilities">
          {[{Icon:BarChart3,title:'Macro & markets',sub:'Understand the environment'},{Icon:Layers,title:'Valuation & PE',sub:'Inspect the assumptions'},{Icon:Lock,title:'Portfolio & risk',sub:'Review exposures and decisions'}].map(({Icon,title,sub})=><div key={title}><Icon size={17}/><span><strong>{title}</strong><small>{sub}</small></span></div>)}
        </div>
        <div className="login-graphic-caption">Illustrative research workflow · not market data</div>
      </section>
      <section className="login-access" aria-label="Sign in">
        <div className="login-card login-access-card">
          <span className="login-eyebrow">MEMBER ACCESS</span>
          <h2>Welcome back</h2>
          <p className="login-access-copy">Select your fund and sign in to your workspace.</p>
          <form onSubmit={handleSubmit} className="login-form">
            <div>
              <label htmlFor="login-fund">Fund</label>
              <select id="login-fund" aria-label="Fund" value={fundId} disabled={loading||!funds.length} onChange={e=>{setFundId(e.target.value);setNeedOtp(false);setOtp('');setError(null);}}>
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
          <div className="login-access-note"><Lock size={13}/><span>Account access is verified for your selected fund.</span></div>
          {showDemo&&<details className="login-development"><summary>Development accounts</summary><p>Default accounts require a new password at first sign-in.</p><div className="grid grid-cols-2 gap-2">{demoCredentials.filter(c=>!defaultAccounts||defaultAccounts.includes(c.user)).map(c=><button type="button" key={c.role} onClick={()=>{setUsername(c.user);setPassword(c.pass);}}><strong>{c.desc}</strong><small>{c.user} / {c.pass}</small></button>)}</div></details>}
        </div>
        <p className="login-support-note">Need access? Contact your fund administrator.</p>
      </section>
    </div>
    <footer className="login-footer"><span>Macro Terminal <b>v8.0</b></span><span>Sessions expire after 8 hours · Account lockout after 5 failed attempts</span></footer>
  </main>;
}
