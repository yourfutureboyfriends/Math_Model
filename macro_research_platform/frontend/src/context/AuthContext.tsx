// AuthContext — JWT-based role authentication
// Provides: user, token, login, logout, hasPermission
//
// * Login fails closed: anything but a 2xx with success !== false is an error. (The old
//   check only looked at response.ok, and the backend answered bad credentials with
//   200 {success:false}, so any username/password got in.)
// * The signed token is attached to every API request by a single fetch wrapper, so all
//   panels authenticate without each one handling headers. A 401 from a protected call
//   ends the session.
// * The session survives a page reload (sessionStorage — cleared when the tab closes) until
//   the token expires.

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';

interface User {
  username: string;
  role: string;
  display_name: string;
  permissions: string[];
}

interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
}

interface AuthContextType extends AuthState {
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  hasPermission: (permission: string) => boolean;
}

const AuthContext = createContext<AuthContextType | null>(null);
const SESSION_KEY = 'macro_session';
const EMPTY: AuthState = { user: null, token: null, isAuthenticated: false };

function tokenExpiry(token: string): number | null {
  try {
    const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
    return typeof payload.exp === 'number' ? payload.exp * 1000 : null;
  } catch {
    return null;
  }
}

function loadSession(): AuthState {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    if (!raw) return EMPTY;
    const s = JSON.parse(raw) as AuthState;
    const exp = s.token ? tokenExpiry(s.token) : null;
    if (!s.token || !s.user || (exp !== null && exp <= Date.now())) return EMPTY;
    return { ...s, isAuthenticated: true };
  } catch {
    return EMPTY;
  }
}

// Current token for the fetch wrapper (module-level so the wrapper is installed once).
let currentToken: string | null = null;
let onUnauthorized: (() => void) | null = null;

function isApiUrl(url: string): boolean {
  try {
    const u = new URL(url, window.location.origin);
    return u.pathname.startsWith('/api/') &&
      (u.origin === window.location.origin || u.hostname === 'localhost' || u.hostname === '127.0.0.1');
  } catch {
    return false;
  }
}

let wrapped = false;
function installFetchWrapper() {
  if (wrapped || typeof window === 'undefined') return;
  wrapped = true;
  const original = window.fetch.bind(window);
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    if (!currentToken || !isApiUrl(url)) return original(input, init);
    const headers = new Headers(init?.headers ?? (input instanceof Request ? input.headers : undefined));
    if (!headers.has('Authorization')) headers.set('Authorization', `Bearer ${currentToken}`);
    const res = await original(input, { ...init, headers });
    if (res.status === 401 && !url.includes('/api/auth/login') && onUnauthorized) onUnauthorized();
    return res;
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [auth, setAuth] = useState<AuthState>(() => {
    const s = loadSession();
    currentToken = s.token;
    return s;
  });

  useEffect(() => { installFetchWrapper(); }, []);

  const endSession = useCallback(() => {
    currentToken = null;
    try {
      sessionStorage.removeItem(SESSION_KEY);
      localStorage.removeItem('macro_user');
      localStorage.removeItem('macro_role');
    } catch { /* storage unavailable */ }
    setAuth(EMPTY);
  }, []);

  useEffect(() => {
    onUnauthorized = endSession;
    // Expire the session when the token does.
    const exp = auth.token ? tokenExpiry(auth.token) : null;
    if (!exp) return;
    const t = setTimeout(endSession, Math.max(0, exp - Date.now()));
    return () => clearTimeout(t);
  }, [auth.token, endSession]);

  const login = useCallback(async (username: string, password: string) => {
    installFetchWrapper();
    const formData = new URLSearchParams();
    formData.append('username', username);
    formData.append('password', password);

    const response = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: formData.toString(),
    });
    const data = await response.json().catch(() => ({}));
    const token: string | undefined = data.access_token || data.token;
    if (!response.ok || data.success === false || !token) {
      throw new Error(data.error || data.detail || 'Invalid username or password');
    }

    const resolvedUser: User = {
      username: data.user?.username || username,
      role: data.role || data.user?.role,
      display_name: data.display_name || data.user?.display_name || username,
      permissions: data.permissions || data.user?.permissions || [],
    };
    const next: AuthState = { user: resolvedUser, token, isAuthenticated: true };
    currentToken = token;
    try {
      sessionStorage.setItem(SESSION_KEY, JSON.stringify(next));
      // Display-only hints for non-React code; the server never trusts these.
      localStorage.setItem('macro_user', resolvedUser.username);
      localStorage.setItem('macro_role', resolvedUser.role);
    } catch { /* storage unavailable */ }
    setAuth(next);
  }, []);

  const logout = useCallback(async () => {
    if (auth.token) {
      try {
        await fetch('/api/auth/logout', { method: 'POST', headers: { Authorization: `Bearer ${auth.token}` } });
      } catch { /* ignore */ }
    }
    endSession();
  }, [auth.token, endSession]);

  const hasPermission = useCallback((permission: string) => {
    if (!auth.user) return false;
    if (auth.user.permissions.includes('*')) return true;
    return auth.user.permissions.includes(permission);
  }, [auth.user]);

  return (
    <AuthContext.Provider value={{ ...auth, login, logout, hasPermission }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
