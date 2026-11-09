/**
 * Error boundary.
 *
 * A single throwing screen used to unmount the entire tree and leave a blank
 * white page with no way back. This catches the error, keeps the shell usable
 * and offers a reload plus a link home.
 */
import * as React from 'react';
import { AlertTriangle, RotateCw } from 'lucide-react';

interface State {
  error: Error | null;
}

export class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  State
> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    // Keep the detail in the console for debugging; never hide it from devs.
    console.error('Screen crashed:', error, info.componentStack);
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    return (
      <div className="grid min-h-dvh place-items-center bg-bg px-5">
        <div className="w-full max-w-md rounded-md border border-border bg-surface p-6 shadow-lg">
          <div className="mb-3 grid h-11 w-11 place-items-center rounded-full bg-destructive/10">
            <AlertTriangle className="h-5 w-5 text-destructive" strokeWidth={2} />
          </div>
          <h1 className="font-display text-[20px] font-800 text-ink">This screen hit an error</h1>
          <p className="mt-1.5 text-[13px] leading-relaxed text-ink-muted">
            The rest of the app still works. Reload to try again — if it keeps happening, the
            message below is the cause.
          </p>
          <pre className="mt-3 max-h-32 overflow-auto rounded-sm bg-surface-2 p-2.5 text-[11px] leading-relaxed text-ink-muted">
            {error.message}
          </pre>
          <div className="mt-4 flex gap-2">
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="press inline-flex h-11 flex-1 items-center justify-center gap-2 rounded-sm text-[13.5px] font-700 text-white"
              style={{ background: 'var(--grad-leaf)' }}
            >
              <RotateCw className="h-4 w-4" strokeWidth={2.2} />
              Reload
            </button>
            <a
              href="/home"
              className="press inline-flex h-11 flex-1 items-center justify-center rounded-sm border border-border bg-surface text-[13.5px] font-700 text-ink"
            >
              Go to Home
            </a>
          </div>
        </div>
      </div>
    );
  }
}
