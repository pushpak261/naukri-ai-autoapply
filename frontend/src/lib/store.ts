import { configureStore, createSlice, createAsyncThunk, type PayloadAction } from '@reduxjs/toolkit';
import { useDispatch, useSelector, type TypedUseSelectorHook } from 'react-redux';
import { api, APIError, getAuthGeneration, setAuthToken } from './api';
import { clearAccountCache } from './query-client';

const USER_KEY = 'naukri_auth_user';
const THEME_KEY = 'theme';

export interface User {
  email: string;
  naukriConfigured: boolean;
}

interface AuthState {
  user: User | null;
  loading: boolean;
  requestId?: string;
}

function loadSavedUser(): User | null {
  if (typeof window === 'undefined') return null;
  try {
    const saved = localStorage.getItem(USER_KEY);
    if (!saved) return null;
    const value = JSON.parse(saved);
    return value && typeof value.email === 'string' && typeof value.naukriConfigured === 'boolean'
      ? value as User : null;
  } catch {
    return null;
  }
}

function saveUser(user: User | null) {
  try {
    if (typeof window === 'undefined') return;
    if (user) localStorage.setItem(USER_KEY, JSON.stringify(user));
    else localStorage.removeItem(USER_KEY);
  } catch { /* Browsers can deny persistent storage. */ }
}

const initialUser = loadSavedUser();

const initialAuthState: AuthState = {
  user: initialUser,
  loading: true,
};

export const loginThunk = createAsyncThunk<
  User,
  { email: string; password: string }
>('auth/login', async ({ email, password }) => {
  setAuthToken(null);
  const generation = getAuthGeneration();
  await clearAccountCache();
  const res = await api.auth.login(email, password);
  if (generation !== getAuthGeneration()) throw new Error('Your session changed. Please sign in again.');
  setAuthToken(res.access_token);
  const issuedGeneration = getAuthGeneration();
  const me = await api.auth.me();
  if (issuedGeneration !== getAuthGeneration()) throw new Error('Your session changed. Please sign in again.');
  const userData: User = { email: me.email, naukriConfigured: me.naukri_configured };
  saveUser(userData);
  return userData;
});

export const logoutThunk = createAsyncThunk('auth/logout', async () => {
  setAuthToken(null);
  saveUser(null);
  await clearAccountCache();
  try {
    await api.auth.logout();
  } catch {
    // ignore
  }
});

export const restoreSession = createAsyncThunk<User | null>('auth/restore', async () => {
  const generation = getAuthGeneration();
  try {
    const me = await api.auth.me();
    if (generation !== getAuthGeneration()) return null;
    const userData: User = { email: me.email, naukriConfigured: me.naukri_configured };
    saveUser(userData);
    return userData;
  } catch (error) {
    if (generation !== getAuthGeneration()) return null;
    // A temporary outage is not proof that the account was signed out.
    if (!(error instanceof APIError) || error.status !== 401) throw error;
    setAuthToken(null);
    saveUser(null);
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
      .addCase(loginThunk.pending, (state, action) => {
        state.requestId = action.meta.requestId;
        state.user = null;
        state.loading = true;
      })
      .addCase(loginThunk.fulfilled, (state, action) => {
        if (state.requestId !== action.meta.requestId) return;
        state.user = action.payload;
        state.loading = false;
      })
      .addCase(loginThunk.rejected, (state, action) => {
        if (state.requestId !== action.meta.requestId) return;
        state.loading = false;
      })
      .addCase(logoutThunk.pending, (state, action) => {
        state.requestId = action.meta.requestId;
        state.user = null;
        state.loading = false;
      })
      .addCase(restoreSession.pending, (state, action) => {
        state.requestId = action.meta.requestId;
        state.loading = true;
      })
      .addCase(restoreSession.fulfilled, (state, action) => {
        if (state.requestId !== action.meta.requestId) return;
        state.user = action.payload;
        state.loading = false;
      })
      .addCase(restoreSession.rejected, (state, action) => {
        if (state.requestId !== action.meta.requestId) return;
        state.loading = false;
      });
  },
});

export const { setUser, setLoading } = authSlice.actions;

type Theme = 'dark' | 'light';

function loadSavedTheme(): Theme {
  try {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem(THEME_KEY);
      if (saved === 'light' || saved === 'dark') return saved;
    }
  } catch { /* Use the default when storage is disabled. */ }
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
