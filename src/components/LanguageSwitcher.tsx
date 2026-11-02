import * as React from 'react';
import { Check, Globe } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useLanguage } from '@/contexts/LanguageContext';
import { coverage, languageEnglishNames, languageNames, type Language } from '@/lib/i18n';

/**
 * Language picker. Applies instantly (context + <html lang>), so fonts and the
 * chatbot switch without a reload.
 */
export function LanguageSwitcher({
  compact,
  className,
}: {
  compact?: boolean;
  className?: string;
}) {
  const { language, setLanguage, languages } = useLanguage();
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <div ref={ref} className={cn('relative', className)}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className={cn(
          'press inline-flex h-9 items-center gap-1.5 rounded-full border border-border bg-surface px-3 text-[12.5px] font-600 text-ink shadow-sm hover:bg-surface-2',
          compact && 'h-8 px-2.5',
        )}
      >
        <Globe className="h-3.5 w-3.5 text-ink-muted" strokeWidth={2} />
        {languageNames[language]}
      </button>

      {open && (
        <div
          role="listbox"
          className="absolute right-0 z-50 mt-2 max-h-[60vh] w-64 animate-scale-in overflow-y-auto rounded-md border border-border bg-surface p-1.5 shadow-lg"
        >
          {languages.map((code: Language) => {
            const pct = coverage(code);
            return (
              <button
                key={code}
                role="option"
                aria-selected={code === language}
                type="button"
                onClick={() => {
                  setLanguage(code);
                  setOpen(false);
                }}
                className={cn(
                  'flex w-full items-center gap-2 rounded-sm px-2.5 py-2 text-left transition-colors',
                  code === language ? 'bg-primary/10' : 'hover:bg-surface-2',
                )}
              >
                <span className="min-w-0 flex-1">
                  <span className="block text-[13.5px] font-600 leading-tight">
                    {languageNames[code]}
                  </span>
                  <span className="block text-[10.5px] text-ink-muted">
                    {languageEnglishNames[code]}
                    {pct < 100 && code !== 'en' ? ` · ${pct}% translated` : ''}
                  </span>
                </span>
                {code === language && <Check className="h-4 w-4 text-primary" strokeWidth={2.5} />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
