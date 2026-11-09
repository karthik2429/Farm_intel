import * as React from 'react';
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  CalendarDays,
  CloudRain,
  Database,
  Flame,
  Info,
  Minus,
  Sprout,
  Sun,
  Waves,
} from 'lucide-react';
import { Badge, Card, CardLabel, Skeleton } from '@/components/ui-kit/core';
import type { FactorDirection, PriceFactorContext, PriceFactorSignal } from '@/lib/priceApi';
import { cn } from '@/lib/utils';

/**
 * Context factors around a forecast: season, seasonality, supply, weather,
 * flood/heat risk and the festival calendar. Every row carries the evidence it
 * was derived from, and inputs that were unavailable are listed rather than
 * hidden — the numbers themselves come from the backend, nothing here is
 * invented or re-estimated.
 */

const ICONS: Record<string, React.ReactNode> = {
  season: <Sprout className="h-4 w-4" strokeWidth={2.2} />,
  seasonality: <CalendarDays className="h-4 w-4" strokeWidth={2.2} />,
  supply: <Database className="h-4 w-4" strokeWidth={2.2} />,
  flood_risk: <Waves className="h-4 w-4" strokeWidth={2.2} />,
  heavy_rain: <CloudRain className="h-4 w-4" strokeWidth={2.2} />,
  dry_spell: <Sun className="h-4 w-4" strokeWidth={2.2} />,
  weather_normal: <CloudRain className="h-4 w-4" strokeWidth={2.2} />,
  heat_stress: <Flame className="h-4 w-4" strokeWidth={2.2} />,
  festival: <CalendarDays className="h-4 w-4" strokeWidth={2.2} />,
};

const DIRECTION_STYLE: Record<FactorDirection, { icon: React.ReactNode; tone: string; word: string }> = {
  up: { icon: <ArrowUpRight className="h-3 w-3" strokeWidth={2.6} />, tone: 'text-leaf', word: 'firmer' },
  down: { icon: <ArrowDownRight className="h-3 w-3" strokeWidth={2.6} />, tone: 'text-destructive', word: 'softer' },
  neutral: { icon: <Minus className="h-3 w-3" strokeWidth={2.6} />, tone: 'text-ink-muted', word: 'neutral' },
};

const STRENGTH_TONE: Record<string, 'live' | 'cached' | 'neutral'> = {
  high: 'live',
  medium: 'cached',
  low: 'neutral',
};

function FactorRow({ signal }: { signal: PriceFactorSignal }) {
  const dir = DIRECTION_STYLE[signal.direction] ?? DIRECTION_STYLE.neutral;
  return (
    <li className="flex items-start gap-2.5 py-2.5">
      <span className={cn('mt-0.5 shrink-0', dir.tone)}>{ICONS[signal.key] ?? <Sprout className="h-4 w-4" />}</span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[12.5px] font-700 text-ink">{signal.label}</span>
          <span
            className={cn(
              'inline-flex items-center gap-0.5 rounded-full border border-border bg-surface-2 px-1.5 py-0.5 text-[9.5px] font-700 uppercase tracking-wide',
              dir.tone,
            )}
          >
            {dir.icon}
            {dir.word}
          </span>
          <Badge tone={STRENGTH_TONE[signal.strength] ?? 'neutral'}>{signal.strength} confidence</Badge>
        </div>
        <p className="mt-0.5 text-[11.5px] leading-relaxed text-ink-muted">{signal.detail}</p>
        {signal.festivals && signal.festivals.length > 1 && (
          <div className="mt-1.5 flex flex-wrap gap-1">
            {signal.festivals.map((f) => (
              <span
                key={`${f.name}-${f.date}`}
                className="rounded-full border border-border bg-surface-2/70 px-2 py-0.5 text-[10px] text-ink-muted"
                title={f.approx ? 'Lunar date — varies by region' : 'Fixed date'}
              >
                {f.name} · {new Date(f.date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}
                {f.approx ? '*' : ''}
              </span>
            ))}
          </div>
        )}
      </div>
    </li>
  );
}

export function PriceFactorsCard({
  factors,
  loading,
}: {
  factors: PriceFactorContext | null;
  loading?: boolean;
}) {
  if (loading) {
    return (
      <Card>
        <Skeleton className="h-4 w-40" />
        <Skeleton className="mt-2 h-3 w-full" />
        <Skeleton className="mt-1.5 h-3 w-2/3" />
        <div className="mt-3 space-y-2">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </div>
      </Card>
    );
  }
  if (!factors) return null;

  const tiltTone = factors.tilt === 'firm' ? 'live' : factors.tilt === 'soft' ? 'danger' : 'neutral';
  const tiltLabel = factors.tilt === 'firm' ? 'Firm bias' : factors.tilt === 'soft' ? 'Soft bias' : 'Balanced';

  return (
    <Card>
      <div className="flex items-start justify-between gap-2">
        <div>
          <CardLabel>What&apos;s moving this price</CardLabel>
          <p className="mt-0.5 text-[10.5px] text-ink-muted">
            Season, weather, floods, festivals and market supply · {factors.as_of}
          </p>
        </div>
        <Badge tone={tiltTone as 'live' | 'danger' | 'neutral'}>{tiltLabel}</Badge>
      </div>

      <p className="mt-2 text-[12px] leading-relaxed text-ink">{factors.summary}</p>

      {factors.shocks.length > 0 && (
        <div className="mt-2 rounded-sm border border-destructive/25 bg-destructive/6 p-2.5">
          <p className="flex items-center gap-1.5 text-[11px] font-700 text-destructive">
            <AlertTriangle className="h-3.5 w-3.5" strokeWidth={2.4} />
            Unexpected-shock risk
          </p>
          <ul className="mt-1 space-y-1">
            {factors.shocks.map((s) => (
              <li key={s} className="text-[11.5px] leading-relaxed text-ink-muted">
                {s}
              </li>
            ))}
          </ul>
        </div>
      )}

      <ul className="mt-1 divide-y divide-border">
        {factors.signals.map((s) => (
          <FactorRow key={s.key} signal={s} />
        ))}
      </ul>

      {factors.weather && (
        <div className="mt-2 grid grid-cols-3 gap-2">
          <MiniStat label="Rain 7d" value={`${factors.weather.total_rain_7d_mm.toFixed(0)} mm`} />
          <MiniStat label="Heaviest day" value={`${factors.weather.max_day_rain_mm.toFixed(0)} mm`} />
          <MiniStat
            label="Flood risk"
            value={factors.weather.flood_risk ? 'Elevated' : 'Low'}
            danger={factors.weather.flood_risk}
          />
        </div>
      )}

      {factors.unavailable.length > 0 && (
        <p className="mt-2 flex items-start gap-1.5 text-[10.5px] leading-relaxed text-ink-muted">
          <Info className="mt-0.5 h-3 w-3 shrink-0" strokeWidth={2} />
          Not available for this crop/location: {factors.unavailable.join('; ')}. These are omitted rather than
          estimated.
        </p>
      )}

      {factors.sources.length > 0 && (
        <p className="mt-2 text-[10px] leading-relaxed text-ink-muted">
          Sources: {factors.sources.join(' · ')}
        </p>
      )}

      <p className="mt-2 border-t border-border pt-2 text-[10px] leading-relaxed text-ink-muted">
        {factors.disclaimer}
      </p>
    </Card>
  );
}

function MiniStat({ label, value, danger }: { label: string; value: string; danger?: boolean }) {
  return (
    <div className="rounded-sm border border-border bg-surface-2/60 p-2 text-center">
      <p className="text-[9.5px] uppercase tracking-wide text-ink-muted">{label}</p>
      <p className={cn('tnum mt-0.5 text-[12px] font-800', danger ? 'text-destructive' : 'text-ink')}>{value}</p>
    </div>
  );
}
