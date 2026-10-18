import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClientProvider } from '@tanstack/react-query'
import { Provider } from 'react-redux'
import { ThemeProvider } from './lib/ThemeContext'
import { store } from './lib/store'
import { queryClient } from './lib/query-client'
import './index.css'
import App from './App.tsx'
import AppErrorBoundary from './components/AppErrorBoundary'

// A tab left open during a rebuild can reference chunks that no longer exist.
// Retry once with the current HTML, without creating an offline reload loop.
window.addEventListener('vite:preloadError', (event) => {
  const key = 'dashboard-chunk-reload';
  try {
    const lastReload = Number(sessionStorage.getItem(key) || 0);
    if (Date.now() - lastReload > 60_000) {
      sessionStorage.setItem(key, String(Date.now()));
      event.preventDefault();
      window.location.reload();
    }
  } catch { /* Let the error boundary handle blocked browser storage. */ }
});

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AppErrorBoundary>
    <Provider store={store}>
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <App />
        </ThemeProvider>
      </QueryClientProvider>
    </Provider>
    </AppErrorBoundary>
  </StrictMode>,
)
