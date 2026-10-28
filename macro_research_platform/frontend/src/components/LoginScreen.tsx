// LoginScreen — Dark terminal-style authentication
// The seeded demo accounts are offered only in a dev build AND only while the server
// reports their default passwords still work; signing in with one forces a password change.

import { useEffect, useState } from 'react';
import { useAuth } from '@/context/AuthContext';
import { Terminal } from 'lucide-react';

export function LoginScreen() {
  const { login } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [otp, setOtp] = useState('');
  const [needOtp, setNeedOtp] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showDemo, setShowDemo] = useState(false);
  const [defaultAccounts, setDefaultAccounts] = useState<string[] | null>(null);

  useEffect(() => {
    if (!import.meta.env.DEV) return;
    fetch('/api/auth/status').then((r) => r.json())
      .then((j) => {
        setShowDemo(Boolean(j.default_credentials_active));
        setDefaultAccounts(Array.isArray(j.default_credential_accounts) ? j.default_credential_accounts : null);
      })
      .catch(() => setShowDemo(false));
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      await login(username, password, needOtp ? otp : undefined);
    } catch (err) {
      if ((err as { mfaRequired?: boolean })?.mfaRequired) setNeedOtp(true);
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  const demoCredentials = [
    { role: 'admin', user: 'admin', pass: 'admin123', desc: 'Administrator' },
    { role: 'pm', user: 'pm', pass: 'pm123', desc: 'Portfolio Manager' },
    { role: 'analyst', user: 'analyst', pass: 'analyst123', desc: 'Macro Analyst' },
    { role: 'risk', user: 'risk', pass: 'risk123', desc: 'Risk Officer' },
    { role: 'quant', user: 'quant', pass: 'quant123', desc: 'Quant Researcher' },
  ];

  const fillCredentials = (user: string, pass: string) => {
    setUsername(user);
    setPassword(pass);
  };

  return (
    <div className="login-stage min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-md relative">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="flex items-center justify-center gap-3 mb-4">
            <span className="login-mark"><Terminal className="w-5 h-5" /></span>
            <h1 className="text-[26px] font-semibold text-text-primary tracking-[-0.02em]">
              Macro Terminal
            </h1>
            <span className="px-1.5 py-0.5 rounded-full text-[10px] font-medium text-text-tertiary bg-text-primary/5 ring-1 ring-border">v8.0</span>
          </div>
          <p className="text-text-secondary text-sm">
            Macro research and portfolio management
          </p>
        </div>

        {/* Login Form */}
        <div className="login-card p-7">
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-[11px] font-medium text-text-secondary mb-1.5">
                Username
              </label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full bg-bg/60 border border-border rounded-lg px-3 py-2.5 text-text-primary
                         focus:border-bloomberg focus:outline-none transition-colors"
                placeholder="Enter username"
                disabled={loading}
              />
            </div>

            <div>
              <label className="block text-[11px] font-medium text-text-secondary mb-1.5">
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full bg-bg/60 border border-border rounded-lg px-3 py-2.5 text-text-primary
                         focus:border-bloomberg focus:outline-none transition-colors"
                placeholder="Enter password"
                disabled={loading}
              />
            </div>

            {needOtp && (
              <div>
                <label className="block text-[11px] font-medium text-text-secondary mb-1.5">
                  Two-factor code
                </label>
                <input
                  value={otp}
                  onChange={(e) => setOtp(e.target.value)}
                  autoComplete="one-time-code"
                  inputMode="numeric"
                  autoFocus
                  className="w-full bg-bg/60 border border-border rounded-lg px-3 py-2.5 text-text-primary font-mono tracking-widest
                           focus:border-bloomberg focus:outline-none transition-colors"
                  placeholder="6-digit code or a recovery code"
                  disabled={loading}
                />
              </div>
            )}

            {error && (
              <div className="p-3 bg-red-dim border border-red rounded text-red text-sm">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading || !username || !password}
              className="login-cta w-full font-medium py-2.5 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? 'Authenticating...' : 'Sign In'}
            </button>
          </form>

          {/* Demo Credentials (dev build, defaults still active) */}
          {showDemo && (
          <div className="mt-6 pt-6 border-t border-border">
            <div className="text-xs text-amber mb-3 text-center">
              Development accounts — a new password is required at first sign-in
            </div>
            <div className="grid grid-cols-2 gap-2">
              {demoCredentials.filter((c) => !defaultAccounts || defaultAccounts.includes(c.user)).map((cred) => (
                <button
                  key={cred.role}
                  onClick={() => fillCredentials(cred.user, cred.pass)}
                  className="text-left px-3 py-2 bg-surface-2 hover:bg-surface-3
                           border border-border hover:border-bloomberg
                           rounded transition-all text-xs"
                >
                  <div className="text-text-primary font-medium">{cred.desc}</div>
                  <div className="text-text-tertiary">{cred.user} / {cred.pass}</div>
                </button>
              ))}
            </div>
          </div>
          )}
        </div>

        {/* Footer */}
        <div className="mt-6 text-center text-2xs text-text-tertiary">
          Signed sessions expire after 8 hours • 5 failed attempts lock the account for 15 min
        </div>
      </div>
    </div>
  );
}
