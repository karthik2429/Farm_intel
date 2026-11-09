/**
 * Core UI kit primitives for FarmIntel.
 *
 * These replace every "plain white box" in the app: cards, headers, stats,
 * badges, rings, sparklines, skeletons and empty states all share the design
 * tokens in src/styles/tokens.css.
 */
import * as React from 'react';
import { ArrowDownRight, ArrowUpRight, ChevronLeft, Minus, RefreshCw } from 'lucide-react';
import { cn } from '@/lib/utils';

/* ------------------------------------------------------------------ Card -- */

type CardVariant = 'plain' | 'glass' | 'gradient' | 'gold' | 'flat';

const cardVariants: Record<CardVariant, string> = {
  plain:
    'bg-surface border border-border shadow-sm hover:shadow-md',
  flat: 'bg-surface border border-border',
  glass:
    'surface-glass shadow-md',
  gradient:
    'text-white border border-white/10 shadow-lg hero-gradient grain',
  gold:
    'text-forest border border-harvest/30 shadow-md bg-gold',
};

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: CardVariant;
  interactive?: boolean;
  padded?: boolean;
}

export const Card = React.forwardRef<HTMLDivElement, CardProps>(
  ({ className, variant = 'plain', interactive, padded = true, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        'relative rounded-md transition-all duration-200 ease-out',
        cardVariants[variant],
        padded && 'p-4 sm:p-5',
        interactive && 'cursor-pointer press hover:-translate-y-0.5 hover:shadow-lg',
        className,
      )}
      {...props}
    />
  ),
);
Card.displayName = 'Card';

export function CardTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return <h3 className={cn('font-display text-[15px] font-700 leading-tight', className)} {...props} />;
}

export function CardLabel({ className, ...props }: React.HTMLAttributes<HTMLParagraphElement>) {
  return (
    <p
      className={cn('text-[11px] font-600 uppercase tracking-[0.09em] text-ink-muted', className)}
      {...props}
    />
  );
}

/* --------------------------------------------------------------- Section -- */

export function SectionHeader({
  title,
  action,
  className,
}: {
  title: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn('mb-3 flex items-end justify-between gap-3', className)}>
      <h2 className="font-display text-[17px] font-700 tracking-tight">{title}</h2>
      {action}
    </div>
  );
}

/* ------------------------------------------------------------ PageHeader -- */

export function PageHeader({
  title,
  subtitle,
  onBack,
  right,
  className,
  children,
}: {
  title: string;
  subtitle?: string;
  onBack?: () => void;
  right?: React.ReactNode;
  className?: string;
  children?: React.ReactNode;
}) {
  return (
    <header className={cn('mb-4 flex items-start gap-3', className)}>
      {onBack && (
        <button
          type="button"
          onClick={onBack}
          aria-label="Go back"
          className="press mt-0.5 grid h-11 w-11 shrink-0 place-items-center rounded-full border border-border bg-surface text-ink shadow-sm hover:bg-surface-2"
        >
          <ChevronLeft className="h-5 w-5" strokeWidth={1.75} />
        </button>
      )}
      <div className="min-w-0 flex-1">
        <h1 className="fluid-h1 font-display font-800 leading-tight tracking-tight">{title}</h1>
        {subtitle && <p className="mt-1 text-[13px] leading-snug text-ink-muted">{subtitle}</p>}
        {children}
      </div>
      {right && <div className="shrink-0">{right}</div>}
    </header>
  );
}

/* --------------------------------------------------------------- Badge ---- */

type BadgeTone = 'live' | 'cached' | 'unavailable' | 'gold' | 'neutral' | 'danger' | 'info';

const badgeTones: Record<BadgeTone, string> = {
  live: 'bg-leaf/12 text-leaf border-leaf/30',
  cached: 'bg-harvest/15 text-[hsl(33,94%,32%)] border-harvest/35 dark:text-harvest',
  unavailable: 'bg-ink/8 text-ink-muted border-border',
  gold: 'bg-harvest text-forest border-harvest',
  neutral: 'bg-surface-2 text-ink-muted border-border',
  danger: 'bg-destructive/12 text-destructive border-destructive/30',
  info: 'bg-[hsl(var(--info))]/12 text-[hsl(var(--info))] border-[hsl(var(--info))]/30',
};

const badgeLabels: Record<string, string> = {
  live: 'Live',
  cache: 'Cached',
  cached: 'Cached',
  agmarknet_live: 'Live',
  agmarknet_backfill: 'AGMARKNET',
  msp_reference: 'MSP ref',
  unavailable: 'Unavailable',
  agmarknet_monthly: 'Monthly average',
  monthly: 'Monthly average',
};

export function Badge({
  tone = 'neutral',
  children,
  dot,
  className,
}: {
  tone?: BadgeTone;
  children: React.ReactNode;
  dot?: boolean;
  className?: string;
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-600 leading-none',
        badgeTones[tone],
        className,
      )}
    >
      {dot && (
        <span className="relative flex h-1.5 w-1.5">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-current opacity-60" />
          <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-current" />
        </span>
      )}
      {children}
    </span>
  );
}

/**
 * Provenance badge for a mandi price. `source`/`is_real`/`badge` come straight
 * from the backend; nothing is inferred, so "Unavailable" always means there
 * really is no real row.
 */
export function PriceSourceBadge({
  source,
  isReal,
  updatedAt,
  badge,
}: {
  source?: string | null;
  isReal?: boolean | null;
  updatedAt?: string | null;
  /** The backend's own verdict (live | cached | monthly | msp | unavailable).
   *  When present it wins over guessing from the source string. */
  badge?: string | null;
}) {
  const key = (source || 'unavailable').toLowerCase();
  if (badge === 'unavailable' || key === 'unavailable' || !key) {
    return <Badge tone="unavailable">Unavailable</Badge>;
  }
  if (badge === 'msp' || key === 'msp_reference') {
    return <Badge tone="info">MSP reference</Badge>;
  }
  if (badge === 'monthly' || key.includes('monthly')) {
    return <Badge tone="gold">Monthly average</Badge>;
  }
  if (badge === 'stale') {
    return (
      <Badge tone="neutral">
        Older record{updatedAt ? ` · ${shortDate(updatedAt)}` : ''}
      </Badge>
    );
  }
  const isCached = badge ? badge === 'cached' : key.startsWith('cache');
  const label = isCached
    ? updatedAt
      ? `Cached · ${shortDate(updatedAt)}`
      : 'Cached'
    : badge === 'live'
      ? 'Live'
      : badgeLabels[key] || (isReal ? 'Live' : 'Market');
  return (
    <Badge tone={isCached ? 'cached' : 'live'} dot={!isCached}>
      {label}
    </Badge>
  );
}

export function shortDate(value?: string | null): string {
  if (!value) return '';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' });
}

/* ------------------------------------------------------------- CountUp ---- */

export function useCountUp(target: number, duration = 700) {
  const [value, setValue] = React.useState(target);
  const from = React.useRef(target);
  const raf = React.useRef<number>();

  React.useEffect(() => {
    const reduced =
      typeof window !== 'undefined' &&
      window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    if (reduced || !Number.isFinite(target)) {
      setValue(target);
      return;
    }
    const start = performance.now();
    const origin = from.current;
    const delta = target - origin;
    const tick = (now: number) => {
      const p = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - p, 3);
      setValue(origin + delta * eased);
      if (p < 1) raf.current = requestAnimationFrame(tick);
      else from.current = target;
    };
    raf.current = requestAnimationFrame(tick);
    return () => {
      if (raf.current) cancelAnimationFrame(raf.current);
      from.current = target;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target, duration]);

  return value;
}

export function CountUp({
  value,
  decimals = 0,
  prefix = '',
  suffix = '',
  className,
}: {
  value: number;
  decimals?: number;
  prefix?: string;
  suffix?: string;
  className?: string;
}) {
  const shown = useCountUp(value);
  return (
    <span className={cn('tnum', className)}>
      {prefix}
      {shown.toLocaleString('en-IN', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      })}
      {suffix}
    </span>
  );
}

/* ------------------------------------------------------------ StatTile ---- */

export function StatTile({
  label,
  value,
  deltaPct,
  icon,
  hint,
  className,
}: {
  label: string;
  value: React.ReactNode;
  deltaPct?: number | null;
  icon?: React.ReactNode;
  hint?: string;
  className?: string;
}) {
  const up = (deltaPct ?? 0) >= 0;
  return (
    <Card className={cn('flex flex-col gap-1.5', className)}>
      <div className="flex items-center justify-between gap-2">
        <CardLabel>{label}</CardLabel>
        {icon && <span className="text-ink-muted">{icon}</span>}
      </div>
      <div className="flex items-baseline gap-2">
        <span className="font-display text-[22px] font-800 leading-none tnum">{value}</span>
        {deltaPct != null && Number.isFinite(deltaPct) && (
          <span
            className={cn(
              'inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 text-[11px] font-700 tnum',
              up ? 'bg-leaf/12 text-leaf' : 'bg-destructive/12 text-destructive',
            )}
          >
            {deltaPct === 0 ? (
              <Minus className="h-3 w-3" strokeWidth={2.2} />
            ) : up ? (
              <ArrowUpRight className="h-3 w-3" strokeWidth={2.2} />
            ) : (
              <ArrowDownRight className="h-3 w-3" strokeWidth={2.2} />
            )}
            {Math.abs(deltaPct).toFixed(1)}%
          </span>
        )}
      </div>
      {hint && <p className="text-[11px] leading-snug text-ink-muted">{hint}</p>}
    </Card>
  );
}

/* --------------------------------------------------------- ProgressRing --- */

export function ProgressRing({
  value,
  size = 64,
  stroke = 6,
  label,
  sublabel,
  className,
}: {
  value: number; // 0..100
  size?: number;
  stroke?: number;
  label?: React.ReactNode;
  sublabel?: string;
  className?: string;
}) {
  const clamped = Math.max(0, Math.min(100, Number.isFinite(value) ? value : 0));
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const offset = c - (clamped / 100) * c;
  const gid = React.useId().replace(/:/g, '');

  return (
    <div className={cn('relative grid place-items-center', className)} style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90" aria-hidden>
        <defs>
          <linearGradient id={`ring-${gid}`} x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="hsl(var(--forest))" />
            <stop offset="60%" stopColor="hsl(var(--primary))" />
            <stop offset="100%" stopColor="hsl(var(--leaf))" />
          </linearGradient>
        </defs>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="hsl(var(--surface-2))"
          strokeWidth={stroke}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={`url(#ring-${gid})`}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={offset}
          style={{ transition: 'stroke-dashoffset 700ms cubic-bezier(0.22,1,0.36,1)' }}
        />
      </svg>
      <div className="absolute inset-0 grid place-items-center text-center leading-none">
        <div>
          <div className="tnum font-display text-[13px] font-800">
            {label ?? `${Math.round(clamped)}`}
          </div>
          {sublabel && <div className="mt-0.5 text-[9px] uppercase tracking-wide text-ink-muted">{sublabel}</div>}
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------ Sparkline --- */

export function Sparkline({
  points,
  width = 96,
  height = 28,
  className,
  positive,
}: {
  points: number[];
  width?: number;
  height?: number;
  className?: string;
  positive?: boolean;
}) {
  const gid = React.useId().replace(/:/g, '');
  const clean = (points || []).filter((n) => Number.isFinite(n));
  if (clean.length < 2) {
    return <div className={cn('h-7 w-24 rounded bg-surface-2/60', className)} aria-hidden />;
  }
  const min = Math.min(...clean);
  const max = Math.max(...clean);
  const span = max - min || 1;
  const step = width / (clean.length - 1);
  const coords = clean.map((v, i) => [i * step, height - ((v - min) / span) * (height - 4) - 2]);
  const line = coords.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  const area = `${line} L${width},${height} L0,${height} Z`;
  const rising = positive ?? clean[clean.length - 1] >= clean[0];
  const stroke = rising ? 'hsl(var(--leaf))' : 'hsl(var(--danger))';

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={cn('block', className)}
      aria-hidden
    >
      <defs>
        <linearGradient id={`spark-${gid}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={stroke} stopOpacity="0.28" />
          <stop offset="100%" stopColor={stroke} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#spark-${gid})`} />
      <path d={line} fill="none" stroke={stroke} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/* ------------------------------------------------------------- Skeleton --- */

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('shimmer rounded-sm', className)} aria-hidden />;
}

export function PriceCardSkeleton() {
  return (
    <div className="flex items-center gap-3 rounded-md border border-border bg-surface p-3">
      <Skeleton className="h-12 w-12 rounded-sm" />
      <div className="flex-1 space-y-2">
        <Skeleton className="h-3.5 w-32" />
        <Skeleton className="h-3 w-24" />
      </div>
      <div className="space-y-2 text-right">
        <Skeleton className="ml-auto h-5 w-16" />
        <Skeleton className="ml-auto h-3 w-10" />
      </div>
    </div>
  );
}

/* ------------------------------------------------------------ Empty/Broken -- */

export function EmptyState({
  title,
  description,
  action,
  icon,
  className,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
  icon?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center rounded-md border border-dashed border-border bg-surface/60 px-5 py-10 text-center',
        className,
      )}
    >
      <div className="mb-3 grid h-14 w-14 place-items-center rounded-full bg-surface-2 text-primary">
        {icon || (
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" aria-hidden>
            <path
              d="M12 21c5-2 8-6 8-11V5l-8 3-8-3v5c0 5 3 9 8 11Z"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinejoin="round"
            />
            <path d="M12 21V8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
        )}
      </div>
      <p className="font-display text-[15px] font-700">{title}</p>
      {description && (
        <p className="mt-1 max-w-[34ch] text-[12.5px] leading-relaxed text-ink-muted">{description}</p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({
  title = 'Something went wrong',
  description,
  onRetry,
}: {
  title?: string;
  description?: string;
  onRetry?: () => void;
}) {
  return (
    <EmptyState
      title={title}
      description={description}
      icon={<span className="text-[22px] font-800">!</span>}
      action={
        onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="press inline-flex items-center gap-1.5 rounded-full border border-border bg-surface px-4 py-2 text-[12.5px] font-600 hover:bg-surface-2"
          >
            <RefreshCw className="h-3.5 w-3.5" strokeWidth={2} /> Try again
          </button>
        )
      }
    />
  );
}

/* ---------------------------------------------------------- SegmentedTabs -- */

export function SegmentedTabs<T extends string>({
  tabs,
  value,
  onChange,
  className,
  size = 'md',
}: {
  tabs: { value: T; label: string; icon?: React.ReactNode }[];
  value: T;
  onChange: (v: T) => void;
  className?: string;
  size?: 'sm' | 'md';
}) {
  const index = Math.max(0, tabs.findIndex((t) => t.value === value));
  return (
    <div
      role="tablist"
      className={cn(
        'relative grid rounded-full border border-border bg-surface-2 p-1',
        size === 'sm' ? 'h-9' : 'h-11',
        className,
      )}
      style={{ gridTemplateColumns: `repeat(${tabs.length}, minmax(0, 1fr))` }}
    >
      <span
        aria-hidden
        className="absolute inset-y-1 rounded-full bg-surface shadow-sm transition-transform duration-300 ease-out"
        style={{
          width: `calc((100% - 0.5rem) / ${tabs.length})`,
          transform: `translateX(calc(${index} * 100%))`,
          left: '0.25rem',
        }}
      />
      {tabs.map((t) => (
        <button
          key={t.value}
          role="tab"
          aria-selected={t.value === value}
          type="button"
          onClick={() => onChange(t.value)}
          className={cn(
            'relative z-10 inline-flex items-center justify-center gap-1.5 rounded-full text-[12.5px] font-600 transition-colors',
            t.value === value ? 'text-ink' : 'text-ink-muted hover:text-ink',
          )}
        >
          {t.icon}
          {t.label}
        </button>
      ))}
    </div>
  );
}

/* ---------------------------------------------------------------- Chip ---- */

export function Chip({
  active,
  children,
  onClick,
  icon,
  className,
}: {
  active?: boolean;
  children: React.ReactNode;
  onClick?: () => void;
  icon?: React.ReactNode;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        'press inline-flex h-9 shrink-0 items-center gap-1.5 rounded-full border px-3.5 text-[12.5px] font-600 transition-all',
        active
          ? 'border-primary bg-primary text-primary-foreground shadow-glow'
          : 'border-border bg-surface text-ink-muted hover:border-primary/40 hover:text-ink',
        className,
      )}
    >
      {icon}
      {children}
    </button>
  );
}

/* ---------------------------------------------------------------- Avatar -- */

export function Avatar({ name, size = 36 }: { name?: string | null; size?: number }) {
  const initials =
    (name || '')
      .split(' ')
      .filter(Boolean)
      .slice(0, 2)
      .map((w) => w[0]?.toUpperCase())
      .join('') || 'A';
  return (
    <span
      className="grid shrink-0 place-items-center rounded-full font-display font-800 text-white shadow-sm"
      style={{
        width: size,
        height: size,
        fontSize: size * 0.36,
        background: 'linear-gradient(135deg, hsl(var(--forest)), hsl(var(--leaf)))',
      }}
      aria-hidden
    >
      {initials}
    </span>
  );
}
