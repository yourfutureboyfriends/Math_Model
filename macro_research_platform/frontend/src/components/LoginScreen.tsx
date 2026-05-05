// LoginScreen — Dark terminal-style authentication
// Demo credentials note: "Demo credentials — change before production deployment"

import { useState } from 'react';
import { useAuth } from '@/context/AuthContext';
import { Terminal } from 'lucide-react';

export function LoginScreen() {
  const { login } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      await login(username, password);
    } catch (err) {
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
    <div className="min-h-screen bg-bg flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="flex items-center justify-center gap-3 mb-4">
            <Terminal className="w-8 h-8 text-bloomberg" />
            <h1 className="text-2xl font-bold text-text-primary tracking-tight">
              MACRO TERMINAL
            </h1>
            <span className="text-sm text-text-tertiary">v8.0</span>
          </div>
          <p className="text-text-secondary text-sm">
            Institutional-grade macro research platform
          </p>
        </div>

        {/* Login Form */}
        <div className="bg-surface-1 border border-border rounded-lg p-6">
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs text-text-tertiary uppercase tracking-wider mb-1.5">
                Username
              </label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full bg-bg border border-border rounded px-3 py-2 text-text-primary
                         focus:border-bloomberg focus:outline-none transition-colors"
                placeholder="Enter username"
                disabled={loading}
              />
            </div>

            <div>
              <label className="block text-xs text-text-tertiary uppercase tracking-wider mb-1.5">
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full bg-bg border border-border rounded px-3 py-2 text-text-primary
                         focus:border-bloomberg focus:outline-none transition-colors"
                placeholder="Enter password"
                disabled={loading}
              />
            </div>

            {error && (
              <div className="p-3 bg-red-dim border border-red rounded text-red text-sm">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading || !username || !password}
              className="w-full bg-bloomberg text-bg font-medium py-2.5 rounded
                       hover:bg-bloomberg/90 disabled:opacity-50 disabled:cursor-not-allowed
                       transition-colors"
            >
              {loading ? 'Authenticating...' : 'Sign In'}
            </button>
          </form>

          {/* Demo Credentials */}
          <div className="mt-6 pt-6 border-t border-border">
            <div className="text-xs text-amber mb-3 text-center">
              Demo credentials — change before production deployment
            </div>
            <div className="grid grid-cols-2 gap-2">
              {demoCredentials.map((cred) => (
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
        </div>

        {/* Footer */}
        <div className="mt-6 text-center text-2xs text-text-tertiary">
          Protected by JWT authentication • Token expires in 8 hours
        </div>
      </div>
    </div>
  );
}
