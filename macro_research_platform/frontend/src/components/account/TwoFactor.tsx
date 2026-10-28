// Two-factor sign-in (TOTP authenticator app + one-time recovery codes): enrol, confirm, turn off; administrators can
// require it for every account and reset a user's device. Backend: /api/auth/mfa*, /api/admin/security/mfa.
import { useCallback, useEffect, useState } from 'react';
import { ShieldCheck } from 'lucide-react';
import { useAuth } from '@/context/AuthContext';
import { apiCall } from '@/lib/http';

const call = apiCall;
const input = 'w-full bg-bg border border-border rounded px-3 py-2 text-text-primary font-mono focus:border-bloomberg focus:outline-none';
const btn = 'px-3 py-1.5 text-xs border border-border rounded hover:border-bloomberg disabled:opacity-40';

export function TwoFactorPanel({ onEnrolled }: { onEnrolled?: () => void }) {
  const { user } = useAuth();
  const [st, setSt] = useState<any>(null);
  const [setup, setSetup] = useState<any>(null);
  const [code, setCode] = useState('');
  const [codes, setCodes] = useState<string[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [policy, setPolicy] = useState<any>(null);
  const load = useCallback(() => {
    call('/api/auth/mfa').then(setSt).catch((e) => setErr(e.message));
    if (user?.role === 'admin') call('/api/admin/security/mfa').then(setPolicy).catch(() => setPolicy(null));
  }, [user?.role]);
  useEffect(load, [load]);
  const act = async (fn: () => Promise<any>) => { setErr(null); try { await fn(); } catch (e: any) { setErr(e.message); } };
  if (!st) return <div className="text-xs text-text-tertiary">{err ?? 'Loading…'}</div>;
  return (
    <div className="space-y-3 text-xs">
      <div className="flex items-center gap-2"><ShieldCheck className={st.enabled ? 'w-4 h-4 text-green' : 'w-4 h-4 text-text-tertiary'} />
        Two-factor sign-in is <b className={st.enabled ? 'text-green' : 'text-amber'}>{st.enabled ? 'on' : 'off'}</b>
        {st.enabled && <span className="text-text-tertiary">· {st.recovery_codes_left} recovery codes left</span>}
        {st.required && <span className="text-text-tertiary">· required for every account</span>}</div>
      {err && <div className="text-amber">{err}</div>}
      {codes && (
        <div className="p-3 border border-amber/50 rounded space-y-1">
          <div className="text-amber font-medium">Save these recovery codes now — they are shown once. Each works once if you lose your device.</div>
          <div className="grid grid-cols-2 gap-1 font-mono">{codes.map((c) => <span key={c}>{c}</span>)}</div>
          <button className={btn} onClick={() => { setCodes(null); onEnrolled?.(); }}>I have saved them</button>
        </div>)}
      {!st.enabled && !setup && <button className={btn} onClick={() => act(async () => setSetup(await call('/api/auth/mfa/setup', 'POST')))}>Set up an authenticator app</button>}
      {!st.enabled && setup && (
        <div className="space-y-2">
          <div>1. In your authenticator app (Google / Microsoft Authenticator, 1Password, Authy…) add an account with this key:</div>
          <div className="p-2 bg-surface-2 border border-border rounded font-mono break-all select-all">{setup.secret.replace(/(.{4})/g, '$1 ').trim()}</div>
          <div className="text-text-tertiary">Account: {setup.account} · issuer: {setup.issuer} · time-based, 6 digits, 30 s. Or paste this link into an app that accepts it:
            <div className="font-mono break-all select-all text-[10px]">{setup.otpauth_uri}</div></div>
          <div>2. Enter the 6-digit code it shows:</div>
          <div className="flex gap-2"><input className={input} value={code} onChange={(e) => setCode(e.target.value)} inputMode="numeric" autoComplete="one-time-code" placeholder="123456" />
            <button className={btn} disabled={code.length < 6} onClick={() => act(async () => { const r = await call('/api/auth/mfa/enable', 'POST', { code }); setCodes(r.recovery_codes); setSetup(null); setCode(''); load(); })}>Turn on</button></div>
        </div>)}
      {st.enabled && !st.required && (
        <div className="flex gap-2"><input className={input} value={code} onChange={(e) => setCode(e.target.value)} placeholder="current code to turn off" />
          <button className={btn} onClick={() => act(async () => { await call('/api/auth/mfa/disable', 'POST', { code }); setCode(''); load(); })}>Turn off</button></div>)}
      {policy && (
        <div className="pt-3 border-t border-border space-y-2">
          <div className="text-2xs text-text-tertiary uppercase">Administrator</div>
          <label className="flex items-center gap-2"><input type="checkbox" checked={policy.required}
            onChange={(e) => act(async () => { await call('/api/admin/security/mfa', 'PUT', { required: e.target.checked }); load(); })} />
            Require two-factor for every account (users without it can only enrol until they do)</label>
          <table className="w-full"><tbody>{Object.entries(policy.users).map(([u, on]: any) => (
            <tr key={u} className="border-b border-border-subtle"><td className="py-1 font-mono">{u}</td><td className={on ? 'text-green' : 'text-text-tertiary'}>{on ? 'on' : 'off'}</td>
              <td className="text-right">{on && u !== user?.username && <button className="text-2xs underline text-text-tertiary hover:text-text-primary"
                onClick={() => act(async () => { await call(`/api/admin/users/${encodeURIComponent(u)}/mfa/reset`, 'POST'); load(); })}>reset (lost device)</button>}</td></tr>))}</tbody></table>
        </div>)}
    </div>
  );
}

export function MfaEnrollScreen() {
  const { mfaEnrolled, logout } = useAuth();
  return (
    <div className="min-h-screen bg-bg flex items-center justify-center p-4">
      <div className="w-full max-w-md bg-surface-1 border border-border rounded-lg p-5 space-y-3">
        <div className="text-sm text-text-primary font-medium">Set up two-factor sign-in</div>
        <div className="text-xs text-text-secondary">Your administrator requires an authenticator app for every account. Set it up to continue.</div>
        <TwoFactorPanel onEnrolled={mfaEnrolled} />
        <button className="text-2xs text-text-tertiary underline" onClick={() => logout()}>Sign out</button>
      </div>
    </div>
  );
}
