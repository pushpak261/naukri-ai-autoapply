import { Component, type ErrorInfo, type ReactNode } from 'react';

export default class AppErrorBoundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Dashboard rendering failed', error, info);
  }

  render() {
    if (!this.state.error) return this.props.children;

    return (
      <main className="min-h-screen bg-[#0f172a] text-slate-200 flex items-center justify-center p-6">
        <div className="max-w-lg space-y-4" role="alert">
          <h1 className="text-2xl font-bold">The dashboard couldn’t load</h1>
          <p>Reload to get the latest dashboard files. Your account and saved settings are preserved.</p>
          <p className="text-sm text-slate-400 break-words">{this.state.error.message}</p>
          <button
            className="rounded-lg bg-sky-500 px-4 py-2 text-slate-950 font-semibold"
            onClick={() => window.location.reload()}
          >
            Reload dashboard
          </button>
        </div>
      </main>
    );
  }
}
