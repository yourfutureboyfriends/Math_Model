// Account security UI: change password (forced on first sign-in with a default or
// admin-issued temporary password), and the admin user-management panel.
//
// Backend: /api/auth/change-password, /api/auth/status, /api/admin/users*.

import { useCallback, useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { KeyRound, Terminal, Users, X } from 'lucide-react';
import { useAuth } from '@/context/AuthContext';

interface Policy { min_length: number; rules: string[] }

function usePolicy(): Policy | null {
  const [policy, setPolicy] = useState<Policy | null>(null);
  useEffect(() => {
    fetch('/api/auth/status').then((r) => r.json()).then((j) => setPolicy(j.password_policy ?? null))
      .catch(() => setPolicy(null));
  }, []);
  return policy;
}

const input = 'w-full bg-bg border border-border rounded px-3 py-2 text-sm text-text-primary ' +
  'focus:border-bloomberg focus:outline-none transition-colors';
const label = 'block text-xs text-text-tertiary uppercase tracking-wider mb-1.5';

export function ChangePasswordForm({ onDone }: { onDone?: () => void }) {
  const { changePassword } = useAuth();
  const policy = usePolicy();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState(false);

  const mismatch = confirm.length > 0 && next !== confirm;
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (next !== confirm) return;
    setBusy(true);
    setError(null);
    try {
      await changePassword(current, next);
      setOk(true);
      setCurrent(''); setNext(''); setConfirm('');
      onDone?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Password change failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-3">
      <div>
        <label className={label} htmlFor="pw-current">Current password</label>
        <input id="pw-current" type="password" autoComplete="current-password" className={input}
          value={current} onChange={(e) => setCurrent(e.target.value)} disabled={busy} />
      </div>
      <div>
        <label className={label} htmlFor="pw-new">New password</label>
        <input id="pw-new" type="password" autoComplete="new-password" className={input}
          value={next} onChange={(e) => setNext(e.target.value)} disabled={busy} />
      </div>
      <div>
        <label className={label} htmlFor="pw-confirm">Confirm new password</label>
        <input id="pw-confirm" type="password" autoComplete="new-password" className={input}
          value={confirm} onChange={(e) => setConfirm(e.target.value)} disabled={busy} />
        {mismatch && <div className="mt-1 text-2xs text-red">Passwords don't match</div>}
      </div>
      {policy && (
        <ul className="text-2xs text-text-tertiary space-y-0.5 list-disc pl-4">
          <li>at least {policy.min_length} characters</li>
          {policy.rules.map((r) => <li key={r}>{r}</li>)}
        </ul>
      )}
      {error && <div className="p-2 bg-red-dim border border-red rounded text-red text-xs">{error}</div>}
      {ok && <div className="p-2 border border-green/40 rounded text-green text-xs">Password changed. Other sessions were signed out.</div>}
      <button type="submit" disabled={busy || !current || !next || next !== confirm}
        className="w-full bg-bloomberg text-bg font-medium py-2 rounded text-sm hover:bg-bloomberg/90
                   disabled:opacity-50 disabled:cursor-not-allowed transition-colors">
        {busy ? 'Saving…' : 'Change password'}
      </button>
    </form>
  );
}

/** Blocking screen shown while the account must set a new password. */
export function ChangePasswordScreen() {
  const { user, logout } = useAuth();
  return (
    <div className="min-h-screen bg-bg flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="flex items-center justify-center gap-3 mb-6">
          <Terminal className="w-7 h-7 text-bloomberg" />
          <h1 className="text-xl font-bold text-text-primary tracking-tight">MACRO TERMINAL</h1>
        </div>
        <div className="bg-surface-1 border border-border rounded-lg p-6">
          <div className="flex items-center gap-2 mb-1">
            <KeyRound className="w-4 h-4 text-amber" />
            <h2 className="text-sm font-semibold text-text-primary">Set a new password</h2>
          </div>
          <p className="text-xs text-text-secondary mb-4">
            {user?.display_name ?? user?.username} is signed in with a default or temporary password.
            Choose a new one to continue — nothing else is available until you do.
          </p>
          <ChangePasswordForm />
          <button onClick={() => logout()} className="mt-3 w-full text-xs text-text-tertiary hover:text-text-primary">
            Sign out instead
          </button>
        </div>
      </div>
    </div>
  );
}

interface AdminUser {
  username: string; role: string; display_name: string; last_login: string | null;
  disabled: boolean; must_change_password: boolean; locked: boolean;
}

async function call(url: string, init?: RequestInit) {
  const r = await fetch(url, { ...init, headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) } });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : `HTTP ${r.status}`);
  return j;
}

export function UserAdminPanel() {
  const { user: me } = useAuth();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [roles, setRoles] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [secret, setSecret] = useState<{ username: string; password: string } | null>(null);
  const [form, setForm] = useState({ username: '', role: 'analyst', display_name: '' });

  const load = useCallback(async () => {
    try {
      const j = await call('/api/admin/users');
      setUsers(j.users); setRoles(j.roles); setError(null);
    } catch (e) { setError((e as Error).message); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const act = async (fn: () => Promise<any>) => {
    setError(null);
    try {
      const j = await fn();
      if (j?.temporary_password) setSecret({ username: j.username, password: j.temporary_password });
      await load();
    } catch (e) { setError((e as Error).message); }
  };

  return (
    <div className="space-y-3">
      {secret && (
        <div className="p-2 border border-amber/50 rounded text-xs">
          <div className="text-amber font-medium">Temporary password for {secret.username} — shown once</div>
          <div className="font-mono text-text-primary select-all mt-1">{secret.password}</div>
          <div className="text-text-tertiary mt-1">Send it over a secure channel; they must change it at sign-in.</div>
          <button className="mt-1 text-text-tertiary hover:text-text-primary" onClick={() => setSecret(null)}>Dismiss</button>
        </div>
      )}
      {error && <div className="p-2 bg-red-dim border border-red rounded text-red text-xs">{error}</div>}
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-text-tertiary text-left border-b border-border">
              <th className="py-1 pr-2">User</th><th className="pr-2">Role</th><th className="pr-2">Status</th>
              <th className="pr-2">Last login</th><th />
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.username} className="border-b border-border-subtle">
                <td className="py-1.5 pr-2">
                  <div className="text-text-primary font-mono">{u.username}</div>
                  <div className="text-text-tertiary">{u.display_name}</div>
                </td>
                <td className="pr-2">
                  <select aria-label={`Role for ${u.username}`} value={u.role}
                    className="bg-bg border border-border rounded px-1 py-0.5 text-text-primary"
                    onChange={(e) => act(() => call(`/api/admin/users/${u.username}`,
                      { method: 'PUT', body: JSON.stringify({ role: e.target.value }) }))}>
                    {roles.map((r) => <option key={r} value={r}>{r}</option>)}
                  </select>
                </td>
                <td className="pr-2 whitespace-nowrap">
                  {u.disabled ? <span className="text-red">disabled</span>
                    : u.locked ? <span className="text-red">locked</span>
                    : u.must_change_password ? <span className="text-amber">must change pw</span>
                    : <span className="text-green">active</span>}
                </td>
                <td className="pr-2 text-text-tertiary whitespace-nowrap">{u.last_login ?? '—'}</td>
                <td className="text-right whitespace-nowrap space-x-2">
                  {u.locked && (
                    <button className="text-bloomberg hover:underline"
                      onClick={() => act(() => call(`/api/admin/users/${u.username}/unlock`, { method: 'POST' }))}>Unlock</button>
                  )}
                  <button className="text-bloomberg hover:underline"
                    onClick={() => act(() => call(`/api/admin/users/${u.username}/reset-password`, { method: 'POST' }))}>Reset pw</button>
                  {u.username !== me?.username && (
                    <button className={u.disabled ? 'text-green hover:underline' : 'text-red hover:underline'}
                      onClick={() => act(() => call(`/api/admin/users/${u.username}`,
                        { method: 'PUT', body: JSON.stringify({ disabled: !u.disabled }) }))}>
                      {u.disabled ? 'Enable' : 'Disable'}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <form className="flex flex-wrap gap-2 items-end pt-2 border-t border-border"
        onSubmit={(e) => {
          e.preventDefault();
          act(() => call('/api/admin/users', { method: 'POST', body: JSON.stringify(form) }))
            .then(() => setForm({ username: '', role: 'analyst', display_name: '' }));
        }}>
        <div className="flex-1 min-w-[7rem]">
          <label className={label} htmlFor="nu-username">New user</label>
          <input id="nu-username" className={input} placeholder="username" value={form.username}
            onChange={(e) => setForm({ ...form, username: e.target.value })} />
        </div>
        <div className="flex-1 min-w-[7rem]">
          <label className={label} htmlFor="nu-name">Display name</label>
          <input id="nu-name" className={input} placeholder="Full name" value={form.display_name}
            onChange={(e) => setForm({ ...form, display_name: e.target.value })} />
        </div>
        <div>
          <label className={label} htmlFor="nu-role">Role</label>
          <select id="nu-role" className={input} value={form.role}
            onChange={(e) => setForm({ ...form, role: e.target.value })}>
            {roles.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </div>
        <button type="submit" disabled={!form.username}
          className="bg-bloomberg text-bg text-sm font-medium px-3 py-2 rounded disabled:opacity-50">Create</button>
      </form>
    </div>
  );
}

/** Modal with the user's account settings (and user management for admins). Rendered into
 *  document.body: inside the sidebar a transformed ancestor would trap `position: fixed`. */
export function AccountDialog({ onClose }: { onClose: () => void }) {
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const [tab, setTab] = useState<'password' | 'users'>('password');
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return createPortal(
    <div className="fixed inset-0 z-[100] bg-black/60 flex items-center justify-center p-4" onClick={onClose}>
      <div role="dialog" aria-label="Account" className="w-full max-w-2xl max-h-[90vh] overflow-y-auto bg-surface-1 border border-border rounded-lg"
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-4 py-2 border-b border-border">
          <div className="flex gap-3 text-xs">
            <button onClick={() => setTab('password')}
              className={`flex items-center gap-1 ${tab === 'password' ? 'text-bloomberg' : 'text-text-secondary hover:text-text-primary'}`}>
              <KeyRound className="w-3.5 h-3.5" /> Password
            </button>
            {isAdmin && (
              <button onClick={() => setTab('users')}
                className={`flex items-center gap-1 ${tab === 'users' ? 'text-bloomberg' : 'text-text-secondary hover:text-text-primary'}`}>
                <Users className="w-3.5 h-3.5" /> Users
              </button>
            )}
          </div>
          <button onClick={onClose} title="Close" className="text-text-tertiary hover:text-text-primary">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="p-4">
          {tab === 'users' && isAdmin ? <UserAdminPanel /> : (
            <div className="max-w-sm"><ChangePasswordForm /></div>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}
