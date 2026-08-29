import { configureStore, createSlice, createAsyncThunk, type PayloadAction } from '@reduxjs/toolkit';
import { useDispatch, useSelector, type TypedUseSelectorHook } from 'react-redux';
import { api, setAuthToken } from './api';

const USER_KEY = 'naukri_auth_user';
const THEME_KEY = 'theme';

export interface User {
  email: string;
  naukriConfigured: boolean;
}

interface AuthState {
  user: User | null;
  loading: boolean;
}

function loadSavedUser(): User | null {
  if (typeof window === 'undefined') return null;
  const saved = localStorage.getItem(USER_KEY);
  if (!saved) return null;
  try {
    return JSON.parse(saved) as User;
  } catch {
    return null;
  }
}

const initialUser = loadSavedUser();

const initialAuthState: AuthState = {
  user: initialUser,
  loading: !!initialUser,
};

export const loginThunk = createAsyncThunk<
  User,
  { email: string; password: string }
>('auth/login', async ({ email, password }) => {
  const res = await api.auth.login(email, password);
  setAuthToken(res.access_token);
  const userData: User = { email: res.email, naukriConfigured: true };
  if (typeof window !== 'undefined') {
    localStorage.setItem(USER_KEY, JSON.stringify(userData));
  }
  return userData;
});

export const logoutThunk = createAsyncThunk('auth/logout', async () => {
  try {
    await api.auth.logout();
  } catch {
    // ignore
  }
  setAuthToken(null);
  if (typeof window !== 'undefined') {
    localStorage.removeItem(USER_KEY);
  }
});

export const restoreSession = createAsyncThunk<User | null>('auth/restore', async () => {
  try {
    const me = await api.auth.me();
    const userData: User = { email: me.email, naukriConfigured: me.naukri_configured };
    if (typeof window !== 'undefined') {
      localStorage.setItem(USER_KEY, JSON.stringify(userData));
    }
    return userData;
  } catch {
    setAuthToken(null);
    if (typeof window !== 'undefined') {
      localStorage.removeItem(USER_KEY);
    }
    return null;
  }
});

const authSlice = createSlice({
  name: 'auth',
  initialState: initialAuthState,
  reducers: {
    setUser(state, action: PayloadAction<User | null>) {
      state.user = action.payload;
    },
    setLoading(state, action: PayloadAction<boolean>) {
      state.loading = action.payload;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(loginThunk.pending, (state) => {
        state.loading = true;
      })
      .addCase(loginThunk.fulfilled, (state, action) => {
        state.user = action.payload;
        state.loading = false;
      })
      .addCase(loginThunk.rejected, (state) => {
        state.loading = false;
      })
      .addCase(logoutThunk.fulfilled, (state) => {
        state.user = null;
        state.loading = false;
      })
      .addCase(restoreSession.pending, (state) => {
        state.loading = true;
      })
      .addCase(restoreSession.fulfilled, (state, action) => {
        state.user = action.payload;
        state.loading = false;
      })
      .addCase(restoreSession.rejected, (state) => {
        state.user = null;
        state.loading = false;
      });
  },
});

export const { setUser, setLoading } = authSlice.actions;

type Theme = 'dark' | 'light';

function loadSavedTheme(): Theme {
  if (typeof window !== 'undefined') {
    const saved = localStorage.getItem(THEME_KEY);
    if (saved === 'light' || saved === 'dark') return saved;
  }
  return 'dark';
}

interface ThemeState {
  theme: Theme;
}

const initialTheme = loadSavedTheme();

const themeSlice = createSlice({
  name: 'theme',
  initialState: { theme: initialTheme } as ThemeState,
  reducers: {
    toggleTheme(state) {
      state.theme = state.theme === 'dark' ? 'light' : 'dark';
    },
    setTheme(state, action: PayloadAction<Theme>) {
      state.theme = action.payload;
    },
  },
});

export const { toggleTheme, setTheme } = themeSlice.actions;

export const store = configureStore({
  reducer: {
    auth: authSlice.reducer,
    theme: themeSlice.reducer,
  },
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;

export const useAppDispatch = () => useDispatch<AppDispatch>();
export const useAppSelector: TypedUseSelectorHook<RootState> = useSelector;
