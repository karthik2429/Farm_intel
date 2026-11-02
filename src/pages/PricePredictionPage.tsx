import * as React from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowDownRight, ArrowUpRight, CalendarDays, Database, Gauge, Info, TrendingUp } from 'lucide-react';
import { AppShell } from '@/components/ui-kit/AppShell';
import {
  Badge,
  Card,
  CardLabel,
  Chip,
  EmptyState,
  ErrorState,
  PageHeader,
  PriceCardSkeleton,
  ProgressRing,
  Skeleton,
} from '@/components/ui-kit/core';
import { ChartLegend, ForecastChart } from '@/components/ui-kit/charts';
import { Select } from '@/components/ui-kit/form';
import { CropThumb } from '@/components/ui-kit/PriceCard';
import { useAuth } from '@/contexts/AuthContext';
import { useLanguage } from '@/contexts/LanguageContext';
import { useProfile, defaultLocation } from '@/lib/profile';
import { getMarketHistory, getMarketPrice } from '@/lib/marketApi';
import { getCommodities } from '@/lib/priceApi';
import { env } from '@/lib/env';
import { cn } from '@/lib/utils';

interface Trajectory {
  day: number;
  date: string;
  predicted_price: number;
  ci_low: number;
  ci_high: number;
  change_from_initial_pct: number;
}

interface Forecast {
  commodity: string;
  district?: string | null;
  state?: string | null;
  market?: string | null;
  scope_level?: string;
  current_price: number;
  predicted_change_pct: number;
  mape: number;
  model?: string;
  backtest_folds?: number;
  history_first: string;
  history_last: string;
  history_obs: number;
  stale_days: number;
  signal?: string;
  trajectory: Trajectory[];
}

const PricePredictionPage: React.FC = () => {
  const { t } = useLanguage();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const { profile } = useProfile(user?.id, user?.email);
  const loc = defaultLocation(profile);

  const [commodities, setCommodities] = React.useState<string[]>([]);
  const [crop, setCrop] = React.useState(params.get('crop') || profile?.crops?.[0] || 'Tomato');
  const [forecast, setForecast] = React.useState<Forecast | null>(null);
  const [history, setHistory] = React.useState<{ date: string; price: number }[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [coverage, setCoverage] = React.useState<{ first: string; last: string; obs: number; markets: number } | null>(null);

  React.useEffect(() => {
    getCommodities()
      .then((list) => setCommodities(list || []))
      .catch(() => setCommodities([]));
  }, []);

  React.useEffect(() => {
    const fromUrl = params.get('crop');
    if (fromUrl && fromUrl !== crop) setCrop(fromUrl);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  React.useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);

    const run = async () => {
      const [hist, live] = await Promise.all([
        getMarketHistory(crop, loc.district, loc.state, 90).catch(() => null),
        getMarketPrice(crop, loc.district, loc.state).catch(() => null),
      ]);
      if (!alive) return;
      setHistory(hist?.points || []);

      const res = await fetch(`${env.apiBaseUrl}/predict/14day`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          district: loc.district || null,
          commodity: crop,
          market: 'All',
          state: loc.state || null,
        }),
      }).catch(() => null);

      if (!alive) return;
      if (!res) {
        setError('The forecast service is not reachable. Start the backend with ./start.sh.');
        setForecast(null);
        setLoading(false);
        return;
      }
      if (res.status === 404) {
        const body = await res.json().catch(() => ({}));
        setError(
          body?.detail ||
            `Not enough real mandi history yet to forecast ${crop}. Daily ingestion keeps accruing history.`,
        );
        setForecast(null);
        setLoading(false);
        return;
      }
      if (!res.ok) {
        setError(`Forecast failed (HTTP ${res.status}).`);
        setForecast(null);
        setLoading(false);
        return;
      }
      const data = await res.json();
      const entry: Forecast | null = Array.isArray(data) ? data[0] : data;
      setForecast(entry);
      if (entry) {
        setCoverage({
          first: entry.history_first,
          last: entry.history_last,
          obs: entry.history_obs,
          markets: 0,
        });
      }
      // live price (may be null) is only used for the "today" figure fallback
      if (live?.modal != null && entry && !entry.current_price) {
        setForecast({ ...entry, current_price: live.modal });
      }
      setLoading(false);
    };

    void run();
    return () => {
      alive = false;
    };
  }, [crop, loc.district, loc.state]);

  const best = React.useMemo(() => {
    if (!forecast?.trajectory?.length) return null;
    return forecast.trajectory.reduce((a, b) =>
      b.predicted_price > a.predicted_price ? b : a,
    );
  }, [forecast]);

  const change = forecast?.predicted_change_pct ?? 0;
  const up = change >= 0;

  return (
    <AppShell>
      <PageHeader
        title={t('pricePrediction')}
        subtitle={`${loc.label || 'All India'} · 14-day Holt-Winters forecast`}
      />

      <div className="mb-3 flex items-center gap-2">
        <CropThumb crop={crop} size={44} />
        <Select
          label="Commodity"
          value={crop}
          onChange={(v) => {
            setCrop(v);
            setParams({ crop: v });
          }}
          options={(commodities.length ? commodities : [crop]).map((c) => ({ value: c, label: c }))}
          placeholder="Pick a commodity"
        />
      </div>

      {loading ? (
        <div className="space-y-3">
          <Card>
            <Skeleton className="h-4 w-24" />
            <Skeleton className="mt-2 h-10 w-40" />
            <Skeleton className="mt-3 h-20 w-full" />
          </Card>
          <PriceCardSkeleton />
        </div>
      ) : error || !forecast ? (
        <EmptyState
          title="No forecast for this crop yet"
          description={error || 'Not enough real mandi history for this commodity and district.'}
          action={
            <div className="flex flex-wrap justify-center gap-2">
              <button
                type="button"
                onClick={() => {
                  setCrop('Tomato');
                  setParams({ crop: 'Tomato' });
                }}
                className="rounded-full bg-primary px-4 py-2 text-[12.5px] font-700 text-primary-foreground"
              >
                Try Tomato
              </button>
              <button
                type="button"
                onClick={() => navigate('/market')}
                className="rounded-full border border-border px-4 py-2 text-[12.5px] font-600"
              >
                Browse market
              </button>
            </div>
          }
        />
      ) : (
        <div className="space-y-3">
          {/* summary */}
          <Card>
            <div className="flex items-start justify-between gap-3">
              <div>
                <CardLabel>Current price</CardLabel>
                <div className="mt-1 flex items-baseline gap-1">
                  <span className="text-[18px] font-600 text-ink-muted">₹</span>
                  <span className="price-xl font-display font-800 tnum">
                    {Math.round(forecast.current_price).toLocaleString('en-IN')}
                  </span>
                  <span className="ml-0.5 text-[12px] text-ink-muted">/quintal</span>
                </div>
                <p className="mt-1 text-[11.5px] text-ink-muted">
                  {forecast.market || loc.district || forecast.state || 'India'} ·{' '}
                  {forecast.history_last}
                </p>
              </div>
              <div className="text-right">
                <Badge tone={up ? 'live' : 'danger'}>
                  {up ? <ArrowUpRight className="h-3 w-3" strokeWidth={2.4} /> : <ArrowDownRight className="h-3 w-3" strokeWidth={2.4} />}
                  {Math.abs(change).toFixed(1)}% in 14d
                </Badge>
                <div className="mt-2 flex items-center justify-end gap-1.5">
                  <Gauge className="h-3.5 w-3.5 text-ink-muted" strokeWidth={2} />
                  <span className="text-[11px] text-ink-muted">MAPE</span>
                  <span className="text-[12px] font-700 tnum">{forecast.mape.toFixed(1)}%</span>
                </div>
              </div>
            </div>

            <div
              className={cn(
                'mt-3 rounded-sm border p-2.5 text-[12px] leading-relaxed',
                up ? 'border-leaf/30 bg-leaf/8' : 'border-destructive/25 bg-destructive/6',
              )}
            >
              <span className="font-700">{up ? 'Prices are trending up. ' : 'Prices are easing. '}</span>
              {up
                ? `Holding ${crop} for the next few days looks better than selling today at the current rate.`
                : `Selling earlier is likely better — the model expects a dip over the next two weeks.`}
              {forecast.stale_days > 0 && (
                <span className="mt-1 block text-ink-muted">
                  Last real mandi record is {forecast.stale_days} day
                  {forecast.stale_days === 1 ? '' : 's'} old.
                </span>
              )}
            </div>
          </Card>

          {/* chart */}
          <Card>
            <div className="mb-1 flex items-center justify-between">
              <CardLabel>Price history + forecast</CardLabel>
              <span className="text-[10.5px] text-ink-muted">{forecast.model || 'Holt-Winters'}</span>
            </div>
            <ForecastChart
              history={history}
              forecast={forecast.trajectory.map((p) => ({
                date: p.date,
                predicted_price: p.predicted_price,
                ci_low: p.ci_low,
                ci_high: p.ci_high,
              }))}
              today={history[history.length - 1]?.date}
              height={230}
            />
            <ChartLegend />
          </Card>

          {/* best day */}
          {best && (
            <Card variant="gold">
              <div className="flex items-center gap-3">
                <span className="grid h-11 w-11 place-items-center rounded-sm bg-forest/10 text-forest">
                  <CalendarDays className="h-5 w-5" strokeWidth={2.2} />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-[10.5px] font-700 uppercase tracking-[0.1em] text-forest/70">
                    {t('bestTimeToSell')}
                  </p>
                  <p className="font-display text-[15px] font-800 text-forest">
                    {new Date(best.date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })} · ₹
                    {Math.round(best.predicted_price).toLocaleString('en-IN')}
                  </p>
                  <p className="text-[11.5px] text-forest/75">
                    Best of the next 14 days (+{best.change_from_initial_pct.toFixed(1)}% vs today)
                  </p>
                </div>
                <ProgressRing
                  value={Math.max(0, Math.min(100, 50 + best.change_from_initial_pct * 4))}
                  size={48}
                  stroke={5}
                  label={<TrendingUp className="mx-auto h-3.5 w-3.5" strokeWidth={2.4} />}
                />
              </div>
            </Card>
          )}

          {/* day by day */}
          <Card className="p-0">
            <div className="flex items-center justify-between px-4 pt-3">
              <CardLabel>Day by day</CardLabel>
              <Badge tone="neutral">14 days</Badge>
            </div>
            <div className="mt-1 divide-y divide-border">
              {forecast.trajectory.map((p) => {
                const d = new Date(p.date);
                return (
                  <div key={p.date} className="flex items-center gap-3 px-4 py-2">
                    <span className="w-16 shrink-0 text-[11.5px] font-600 text-ink-muted">
                      {d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })}
                    </span>
                    <span className="tnum flex-1 text-[13px] font-700">
                      ₹{Math.round(p.predicted_price).toLocaleString('en-IN')}
                    </span>
                    <span className="tnum hidden text-[10.5px] text-ink-muted sm:block">
                      ₹{Math.round(p.ci_low).toLocaleString('en-IN')}–
                      {Math.round(p.ci_high).toLocaleString('en-IN')}
                    </span>
                    <span
                      className={cn(
                        'tnum w-14 text-right text-[11.5px] font-700',
                        p.change_from_initial_pct >= 0 ? 'text-leaf' : 'text-destructive',
                      )}
                    >
                      {p.change_from_initial_pct >= 0 ? '+' : ''}
                      {p.change_from_initial_pct.toFixed(1)}%
                    </span>
                  </div>
                );
              })}
            </div>
          </Card>

          {/* coverage */}
          <Card>
            <div className="mb-2 flex items-center gap-2">
              <Database className="h-4 w-4 text-primary" strokeWidth={2} />
              <h3 className="font-display text-[14px] font-700">{t('dataCoverage')}</h3>
            </div>
            <p className="mb-2.5 text-[11.5px] leading-relaxed text-ink-muted">{t('coverageExplain')}</p>
            <div className="grid grid-cols-3 gap-2">
              <CoverageStat label="Observations" value={coverage?.obs ?? 0} />
              <CoverageStat label="First" value={coverage?.first ?? '—'} small />
              <CoverageStat label="Last" value={coverage?.last ?? '—'} small />
            </div>
            <div className="mt-2.5 flex flex-wrap items-center gap-2">
              <Badge tone={forecast.mape <= 10 ? 'live' : forecast.mape <= 20 ? 'cached' : 'danger'}>
                MAPE {forecast.mape.toFixed(1)}%
              </Badge>
              <Badge tone="neutral">{forecast.backtest_folds || 0} backtest folds</Badge>
              <Badge tone="neutral">scope: {forecast.scope_level || 'district'}</Badge>
            </div>
            <p className="mt-2 flex items-start gap-1.5 text-[10.5px] leading-relaxed text-ink-muted">
              <Info className="mt-0.5 h-3 w-3 shrink-0" strokeWidth={2} />
              MAPE is measured on rolling-origin backtests over this commodity's
              own real history, not on synthetic data.
            </p>
          </Card>
        </div>
      )}
    </AppShell>
  );
};

function CoverageStat({ label, value, small }: { label: string; value: React.ReactNode; small?: boolean }) {
  return (
    <div className="rounded-sm border border-border bg-surface-2/60 p-2 text-center">
      <p className="text-[9.5px] uppercase tracking-wide text-ink-muted">{label}</p>
      <p className={cn('tnum mt-0.5 font-display font-800', small ? 'text-[11.5px]' : 'text-[15px]')}>
        {value}
      </p>
    </div>
  );
}

export default PricePredictionPage;
