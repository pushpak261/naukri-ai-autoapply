import { useEffect, type ReactNode } from 'react';
import { useAppDispatch, useAppSelector } from './store';
import { loginThunk, logoutThunk, restoreSession, type User } from './store';

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const dispatch = useAppDispatch();
  useEffect(() => {
    dispatch(restoreSession());
  }, [dispatch]);
  return <>{children}</>;
}

export function useAuth(): AuthContextValue {
  const dispatch = useAppDispatch();
  const user = useAppSelector((s) => s.auth.user);
  const loading = useAppSelector((s) => s.auth.loading);

  const login = (email: string, password: string) =>
    dispatch(loginThunk({ email, password })).then(() => undefined);
  const logout = () => dispatch(logoutThunk()).then(() => undefined);

  return { user, loading, login, logout };
}
