// AuthContext — JWT-based role authentication
// Provides: user, token, login, logout, hasPermission

import { createContext, useContext, useState, useCallback, type ReactNode } from 'react';

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

export function AuthProvider({ children }: { children: ReactNode }) {
  const [auth, setAuth] = useState<AuthState>({
    user: null,
    token: null,
    isAuthenticated: false,
  });

  const login = useCallback(async (username: string, password: string) => {
    const formData = new URLSearchParams();
    formData.append('username', username);
    formData.append('password', password);

    const response = await fetch('/api/auth/login', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: formData.toString(),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Login failed');
    }

    const data = await response.json();

    const resolvedUser = {
      username: data.user?.username || data.username || username,
      role: data.role || data.user?.role || 'user',
      display_name: data.display_name || data.user?.display_name || username,
      permissions: data.permissions || data.user?.permissions || ['read'],
    };
    // Persist identity so non-React fetches (audit log, trade workflow) can attribute actions.
    try {
      localStorage.setItem('macro_user', resolvedUser.username);
      localStorage.setItem('macro_role', resolvedUser.role);
    } catch { /* storage unavailable */ }

    setAuth({
      user: resolvedUser,
      token: data.access_token || data.token,
      isAuthenticated: true,
    });
  }, []);

  const logout = useCallback(async () => {
    if (auth.token) {
      try {
        await fetch('/api/auth/logout', {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${auth.token}`,
          },
        });
      } catch (e) {
        // Ignore logout errors
      }
    }

    try {
      localStorage.removeItem('macro_user');
      localStorage.removeItem('macro_role');
    } catch { /* storage unavailable */ }

    setAuth({
      user: null,
      token: null,
      isAuthenticated: false,
    });
  }, [auth.token]);

  const hasPermission = useCallback((permission: string) => {
    if (!auth.user) return false;
    if (auth.user.permissions.includes('*')) return true;
    return auth.user.permissions.includes(permission);
  }, [auth.user]);

  return (
    <AuthContext.Provider
      value={{
        ...auth,
        login,
        logout,
        hasPermission,
      }}
    >
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
