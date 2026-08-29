import { useEffect, type ReactNode } from 'react';
import { useAppSelector, useAppDispatch } from './store';
import { toggleTheme } from './store';

type Theme = 'dark' | 'light';

interface ThemeContextType {
  theme: Theme;
  toggle: () => void;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const theme = useAppSelector((s) => s.theme.theme);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
  }, [theme]);

  return <>{children}</>;
}

export function useTheme(): ThemeContextType {
  const dispatch = useAppDispatch();
  const theme = useAppSelector((s) => s.theme.theme);
  return { theme, toggle: () => dispatch(toggleTheme()) };
}
