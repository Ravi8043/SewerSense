import { Component, type ErrorInfo, type ReactNode } from 'react';

interface State {
  error: Error | null;
}

/** Last-resort fallback so a rendering bug never leaves a blank screen without the demo notice. */
export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('SewerSense UI error', error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div role="alert" className="flex h-screen w-screen flex-col items-center justify-center gap-4 bg-ss-bg text-center">
        <div className="flex items-center gap-2">
          <span className="text-[18px] font-bold text-white">
            Sewer<span className="text-ss-accent">Sense</span>
          </span>
          <span className="rounded border border-amber-400/60 bg-amber-400/10 px-1.5 py-px text-[10px] font-bold uppercase tracking-wider text-amber-300">Demo data</span>
        </div>
        <p className="max-w-md text-[13px] text-ss-textmuted">The command center hit an unexpected display error. Your data is safe on the server.</p>
        <button onClick={() => window.location.reload()} className="rounded bg-ss-accent px-4 py-1.5 text-[13px] font-semibold text-ss-bg hover:bg-ss-accent/90">
          Reload
        </button>
      </div>
    );
  }
}
