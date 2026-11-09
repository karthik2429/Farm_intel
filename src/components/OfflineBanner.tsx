import * as React from 'react';
import { Download, WifiOff, X } from 'lucide-react';
import { cn } from '@/lib/utils';

/** Shows whenever the browser reports itself offline. */
export function OfflineBanner() {
  const [offline, setOffline] = React.useState(
    typeof navigator !== 'undefined' ? !navigator.onLine : false,
  );

  React.useEffect(() => {
    const on = () => setOffline(false);
    const off = () => setOffline(true);
    window.addEventListener('online', on);
    window.addEventListener('offline', off);
    return () => {
      window.removeEventListener('online', on);
      window.removeEventListener('offline', off);
    };
  }, []);

  if (!offline) return null;

  return (
    <div
      role="status"
      className="sticky top-0 z-30 -mx-4 mb-2 flex items-center gap-2 border-b border-harvest/40 bg-harvest/15 px-4 py-2 text-[12px] font-600 text-ink backdrop-blur sm:-mx-6 sm:px-6"
    >
      <WifiOff className="h-3.5 w-3.5 shrink-0" strokeWidth={2.2} />
      Offline — showing the last prices saved on this device.
    </div>
  );
}

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}

/** Small, dismissible "install the app" chip driven by the browser prompt. */
export function InstallPrompt({ className }: { className?: string }) {
  const [event, setEvent] = React.useState<BeforeInstallPromptEvent | null>(null);
  const [dismissed, setDismissed] = React.useState(
    () => localStorage.getItem('agrosmart.install.dismissed') === '1',
  );

  React.useEffect(() => {
    const handler = (e: Event) => {
      e.preventDefault();
      setEvent(e as BeforeInstallPromptEvent);
    };
    window.addEventListener('beforeinstallprompt', handler);
    return () => window.removeEventListener('beforeinstallprompt', handler);
  }, []);

  if (!event || dismissed) return null;

  return (
    <div
      className={cn(
        'flex items-center gap-2 rounded-sm border border-border bg-surface px-3 py-2 shadow-sm',
        className,
      )}
    >
      <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-primary/12 text-primary">
        <Download className="h-4 w-4" strokeWidth={2} />
      </span>
      <p className="min-w-0 flex-1 text-[11.5px] leading-snug text-ink-muted">
        Install FarmIntel for offline prices.
      </p>
      <button
        type="button"
        onClick={async () => {
          await event.prompt();
          const choice = await event.userChoice;
          if (choice.outcome === 'dismissed') {
            localStorage.setItem('agrosmart.install.dismissed', '1');
            setDismissed(true);
          }
          setEvent(null);
        }}
        className="press shrink-0 rounded-full bg-primary px-3 py-1.5 text-[11.5px] font-700 text-primary-foreground"
      >
        Install
      </button>
      <button
        type="button"
        aria-label="Dismiss install prompt"
        onClick={() => {
          localStorage.setItem('agrosmart.install.dismissed', '1');
          setDismissed(true);
        }}
        className="press grid h-6 w-6 shrink-0 place-items-center rounded-full text-ink-muted"
      >
        <X className="h-3 w-3" strokeWidth={2.4} />
      </button>
    </div>
  );
}
