/**
 * Price presentation: a big tabular number, the market and date it came from,
 * an honest provenance badge and a sparkline. Nothing here invents a price —
 * when `price` is null the card renders "--" plus the reason.
 */
import * as React from 'react';
import { MapPin, TrendingDown, TrendingUp } from 'lucide-react';
import { cn } from '@/lib/utils';
import { cropImage, cropTint } from '@/lib/cropImages';
import { Badge, PriceSourceBadge, Sparkline, shortDate } from './core';

export function CropThumb({
  crop,
  size = 48,
  className,
}: {
  crop: string;
  size?: number;
  className?: string;
}) {
  const src = cropImage(crop);
  const [broken, setBroken] = React.useState(false);
  const tint = cropTint(crop);
  const showPhoto = src && !broken;

  return (
    <div
      className={cn('relative shrink-0 overflow-hidden rounded-sm', className)}
      style={{ width: size, height: size }}
    >
      {showPhoto ? (
        <img
          src={src}
          alt=""
          loading="lazy"
          decoding="async"
          width={size}
          height={size}
          onError={() => setBroken(true)}
          className="h-full w-full object-cover"
        />
      ) : (
        <div
          className="grid h-full w-full place-items-center"
          style={{ background: `linear-gradient(135deg, ${tint.from}, ${tint.to})` }}
          aria-hidden
        >
          <svg width={size * 0.5} height={size * 0.5} viewBox="0 0 24 24" fill="none">
            <path
              d="M20 4c0 8-5 12-11 12H5c0-8 5-12 11-12h4Z"
              stroke="rgba(255,255,255,0.92)"
              strokeWidth="1.4"
              strokeLinejoin="round"
            />
            <path d="M4 20c3-5 7-8 12-9" stroke="rgba(255,255,255,0.75)" strokeWidth="1.4" strokeLinecap="round" />
          </svg>
        </div>
      )}
    </div>
  );
}

export interface PriceData {
  commodity: string;
  district?: string | null;
  state?: string | null;
  market?: string | null;
  price: number | null;
  min_price?: number | null;
  max_price?: number | null;
  unit?: string;
  date?: string | null;
  source?: string | null;
  is_real?: boolean | null;
  badge?: string | null;
  detail?: string | null;
}

function rangePct(d: PriceData): number | null {
  if (d.price == null || d.min_price == null || d.max_price == null) return null;
  const span = d.max_price - d.min_price;
  if (span <= 0) return 50;
  return Math.max(4, Math.min(96, ((d.price - d.min_price) / span) * 100));
}

export function PriceCard({
  data,
  spark,
  deltaPct,
  onClick,
  className,
  compact,
}: {
  data: PriceData;
  spark?: number[];
  deltaPct?: number | null;
  onClick?: () => void;
  className?: string;
  compact?: boolean;
}) {
  const pct = rangePct(data);
  const hasPrice = data.price != null;
  const up = (deltaPct ?? 0) >= 0;

  return (
    <div
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onClick={onClick}
      onKeyDown={(e) => {
        if (onClick && (e.key === 'Enter' || e.key === ' ')) {
          e.preventDefault();
          onClick();
        }
      }}
      className={cn(
        'group flex items-center gap-3 rounded-md border border-border bg-surface p-3 transition-all duration-200',
        onClick && 'cursor-pointer press hover:-translate-y-0.5 hover:border-primary/35 hover:shadow-md',
        !hasPrice && 'opacity-95',
        className,
      )}
    >
      <CropThumb crop={data.commodity} size={compact ? 44 : 52} />

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <p className="truncate font-display text-[14px] font-700 leading-tight">{data.commodity}</p>
          {deltaPct != null && Number.isFinite(deltaPct) && (
            <span
              className={cn(
                'inline-flex shrink-0 items-center gap-0.5 text-[11px] font-700 tnum',
                up ? 'text-leaf' : 'text-destructive',
              )}
            >
              {up ? (
                <TrendingUp className="h-3 w-3" strokeWidth={2.4} />
              ) : (
                <TrendingDown className="h-3 w-3" strokeWidth={2.4} />
              )}
              {Math.abs(deltaPct).toFixed(1)}%
            </span>
          )}
        </div>
        <p className="mt-0.5 flex items-center gap-1 text-[11.5px] text-ink-muted">
          <MapPin className="h-3 w-3 shrink-0" strokeWidth={2} />
          <span className="truncate">
            {[data.market || data.district || 'Market unknown', data.date ? shortDate(data.date) : '']
              .filter(Boolean)
              .join(' · ')}
          </span>
        </p>
        {pct != null && (
          <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-surface-2">
            <span
              className="block h-full rounded-full"
              style={{
                width: `${pct}%`,
                background: 'linear-gradient(90deg, hsl(var(--leaf)), hsl(var(--primary)))',
              }}
            />
          </div>
        )}
        {!hasPrice && data.detail && (
          <p className="mt-1 line-clamp-1 text-[11px] text-ink-muted">{data.detail}</p>
        )}
      </div>

      <div className="shrink-0 text-right">
        <div className="flex items-baseline justify-end gap-0.5">
          {hasPrice ? (
            <>
              <span className="text-[15px] font-600 text-ink-muted">₹</span>
              <span className="font-display text-[22px] font-800 leading-none tnum">
                {Number(data.price).toLocaleString('en-IN')}
              </span>
            </>
          ) : (
            <span className="font-display text-[22px] font-800 leading-none text-ink-muted">--</span>
          )}
        </div>
        <p className="mt-0.5 text-[10px] uppercase tracking-wide text-ink-muted">per quintal</p>
        {spark && spark.length > 1 && (
          <div className="mt-1 flex justify-end">
            <Sparkline points={spark} width={64} height={20} positive={up} />
          </div>
        )}
        <div className="mt-1.5 flex justify-end">
          <PriceSourceBadge source={data.source} isReal={data.is_real} updatedAt={data.date} />
        </div>
      </div>
    </div>
  );
}

export function PriceRow({
  label,
  value,
  unit,
  tone,
}: {
  label: string;
  value: React.ReactNode;
  unit?: string;
  tone?: 'up' | 'down' | 'flat';
}) {
  return (
    <div className="flex items-center justify-between border-b border-border py-2 last:border-0">
      <span className="text-[12.5px] text-ink-muted">{label}</span>
      <span
        className={cn(
          'tnum text-[13px] font-700',
          tone === 'up' && 'text-leaf',
          tone === 'down' && 'text-destructive',
        )}
      >
        {value}
        {unit && <span className="ml-0.5 text-[11px] font-500 text-ink-muted">{unit}</span>}
      </span>
    </div>
  );
}

export function MarketBadge({ market, date }: { market?: string | null; date?: string | null }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-border bg-surface-2 px-2 py-0.5 text-[10.5px] font-600 text-ink-muted">
      <MapPin className="h-2.5 w-2.5" strokeWidth={2.4} />
      {market || '—'}
      {date && <Badge tone="neutral" className="border-0 bg-transparent px-1 py-0">{shortDate(date)}</Badge>}
    </span>
  );
}
