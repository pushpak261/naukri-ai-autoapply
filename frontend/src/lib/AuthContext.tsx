import { createContext, useContext, useCallback, useEffect, useState, type ReactNode } from 'react';
import { api, setAuthToken } from './api';

interface User {
  email: string;
  naukriConfigured: boolean;
}

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const USER_KEY = 'naukri_auth_user';

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem(USER_KEY);
      if (saved) {
        try {
          return JSON.parse(saved);
        } catch {
          return null;
        }
      }
    }
    return null;
  });
  const [loading, setLoading] = useState(!user);

  // Restore session on mount
  useEffect(() => {
    (async () => {
      try {
        const me = await api.auth.me();
        const userData = { email: me.email, naukriConfigured: me.naukri_configured };
        setUser(userData);
        if (typeof window !== 'undefined') {
          localStorage.setItem(USER_KEY, JSON.stringify(userData));
        }
      } catch {
        setUser(null);
        if (typeof window !== 'undefined') {
          localStorage.removeItem(USER_KEY);
        }
        setAuthToken(null);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const res = await api.auth.login(email, password);
    setAuthToken(res.access_token);
    const userData = { email: res.email, naukriConfigured: true };
    setUser(userData);
    if (typeof window !== 'undefined') {
      localStorage.setItem(USER_KEY, JSON.stringify(userData));
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.auth.logout();
    } catch {
      // ignore
    }
    setAuthToken(null);
    setUser(null);
    if (typeof window !== 'undefined') {
      localStorage.removeItem(USER_KEY);
    }
  }, []);


  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
