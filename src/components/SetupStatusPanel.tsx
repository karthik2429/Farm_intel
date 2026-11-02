import * as React from 'react';
import { CheckCircle2, CircleDashed, ExternalLink, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { env, frontendSetupChecklist } from '@/lib/env';

interface BackendStatus {
  env: string;
  configured: Record<string, boolean>;
  llm_providers: Record<string, boolean>;
  speech_provider: string;
  missing: { var: string; signup: string }[];
}

/**
 * Development-only setup panel: shows which services are configured (booleans
 * only, never values) and links to the free signup page for each missing key.
 * Renders nothing in a production build.
 */
export function SetupStatusPanel() {
  const [open, setOpen] = React.useState(false);
  const [status, setStatus] = React.useState<BackendStatus | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!open || status) return;
    let alive = true;
    fetch(`${env.apiBaseUrl}/config/status`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d) => alive && setStatus(d))
      .catch(() => alive && setError('Backend not reachable — is ./start.sh running?'));
    return () => {
      alive = false;
    };
  }, [open, status]);

  if (!env.isDev) return null;

  const missingFrontend = frontendSetupChecklist.filter((c) => !c.done);
  const missingBackend = status?.missing ?? [];

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="press fixed bottom-24 left-3 z-40 hidden items-center gap-1.5 rounded-full border border-border bg-surface/90 px-3 py-1.5 text-[11px] font-600 text-ink-muted shadow-md backdrop-blur md:flex"
        title="Development setup status"
      >
        <CircleDashed className="h-3 w-3" strokeWidth={2.2} />
        Setup status
        {missingFrontend.length + missingBackend.length > 0 && (
          <span className="rounded-full bg-harvest px-1.5 text-[10px] font-800 text-forest">
            {missingFrontend.length + missingBackend.length}
          </span>
        )}
      </button>

      {open && (
        <div className="fixed inset-0 z-[60] flex items-end justify-center bg-black/40 p-3 backdrop-blur-sm sm:items-center">
          <div className="max-h-[80vh] w-full max-w-lg animate-slide-up-sheet overflow-y-auto rounded-md border border-border bg-surface p-4 shadow-lg">
            <div className="mb-3 flex items-start justify-between gap-3">
              <div>
                <h2 className="font-display text-[16px] font-800">Setup status</h2>
                <p className="mt-0.5 text-[11.5px] text-ink-muted">
                  Booleans only — no key value is ever sent to the browser.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label="Close"
                className="press grid h-9 w-9 place-items-center rounded-full border border-border hover:bg-surface-2"
              >
                <X className="h-4 w-4" strokeWidth={2} />
              </button>
            </div>

            <h3 className="mb-1.5 mt-3 text-[11px] font-700 uppercase tracking-[0.1em] text-ink-muted">
              Frontend
            </h3>
            <div className="space-y-1.5">
              {frontendSetupChecklist.map((c) => (
                <Row key={c.key} done={c.done} label={c.label} detail={c.what} href={c.signup} />
              ))}
            </div>

            <h3 className="mb-1.5 mt-4 text-[11px] font-700 uppercase tracking-[0.1em] text-ink-muted">
              Backend
            </h3>
            {error && <p className="text-[12px] text-destructive">{error}</p>}
            {!error && !status && <p className="text-[12px] text-ink-muted">Checking…</p>}
            {status && (
              <div className="space-y-1.5">
                {Object.entries(status.configured).map(([k, done]) => (
                  <Row key={k} done={done} label={k.replace(/_/g, ' ')} />
                ))}
              </div>
            )}

            {missingBackend.length > 0 && (
              <>
                <h3 className="mb-1.5 mt-4 text-[11px] font-700 uppercase tracking-[0.1em] text-ink-muted">
                  Missing keys ({missingBackend.length})
                </h3>
                <div className="flex flex-wrap gap-1.5">
                  {missingBackend.map((m) => (
                    <a
                      key={m.var}
                      href={m.signup || '#'}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="inline-flex items-center gap-1 rounded-full border border-border bg-surface-2 px-2 py-1 text-[10.5px] font-600 text-ink-muted hover:border-primary/40 hover:text-ink"
                    >
                      {m.var}
                      <ExternalLink className="h-2.5 w-2.5" strokeWidth={2} />
                    </a>
                  ))}
                </div>
                <p className="mt-2 text-[10.5px] leading-relaxed text-ink-muted">
                  Every feature still works without these — it shows an honest
                  setup state instead of fake data.
                </p>
              </>
            )}
          </div>
        </div>
      )}
    </>
  );
}

function Row({
  done,
  label,
  detail,
  href,
}: {
  done: boolean;
  label: string;
  detail?: string;
  href?: string;
}) {
  return (
    <div className="flex items-center gap-2 rounded-sm border border-border bg-surface-2/60 px-2.5 py-1.5">
      {done ? (
        <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-leaf" strokeWidth={2.2} />
      ) : (
        <CircleDashed className={cn('h-3.5 w-3.5 shrink-0 text-ink-muted')} strokeWidth={2.2} />
      )}
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[12px] font-600 capitalize">{label}</span>
        {detail && <span className="block truncate text-[10.5px] text-ink-muted">{detail}</span>}
      </span>
      {href && !done && (
        <a
          href={href}
          target="_blank"
          rel="noreferrer noopener"
          className="shrink-0 text-[10.5px] font-600 text-primary hover:underline"
        >
          Get key
        </a>
      )}
    </div>
  );
}
