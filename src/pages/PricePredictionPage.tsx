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
import {
  getCommodities,
  getPriceFactors,
  getScopedCommodities,
  type PriceFactorContext,
} from '@/lib/priceApi';
import { allStates, getDistricts } from '@/lib/indian-locations';
import { PriceFactorsCard } from '@/components/PriceFactorsCard';
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
  /** Human-readable name of the model the backtest selected for this series. */
  model_label?: string;
  /** Factors that were allowed to move this forecast, each with its evidence. */
  events?: {
    applied?: Array<{ key: string; label: string; shift_pct: number; evidence: string }>;
    notes?: string[];
    shift_total_pct?: number;
  };
  /** Rows repaired before fitting (unit errors) and how many were used. */
  data_quality?: { repaired_rows: number; rows_used: number };
  backtest_folds?: number | { fold: number; cut: string; mape: number }[];
  history_first: string;
  history_last: string;
  history_obs: number;
  stale_days: number;
  signal?: string;
  /** "daily" = mandi transaction records, "monthly" = AGMARKNET district
   *  monthly averages (the 2-year report). */
  history_basis?: 'daily' | 'monthly';
  history_months?: number;
  season?: {
    month: string;
    index: number;
    raw_index?: number;
    months_used: number;
    years_used: number;
  } | null;
  festivals?: Array<{ name: string; date: string; days_until: number; approx: boolean }>;
  shocks?: string[];
  adjustment?: number;
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
  const [factors, setFactors] = React.useState<PriceFactorContext | null>(null);
  const [factorsLoading, setFactorsLoading] = React.useState(false);

  // Forecast scope. The profile supplies the default, but a state can be
  // switched here so the same crop can be compared across states — every state
  // carries its own AGMARKNET monthly history.
  const [scopeState, setScopeState] = React.useState(loc.state || '');
  const [scopeDistrict, setScopeDistrict] = React.useState(loc.district || '');

  React.useEffect(() => {
    // Adopt the saved profile location once it arrives, without overriding a
    // state the farmer already picked on this page.
    setScopeState((s) => s || loc.state || '');
    setScopeDistrict((d) => d || loc.district || '');
  }, [loc.state, loc.district]);

  // A district only makes sense inside its own state.
  const districts = React.useMemo(() => getDistricts(scopeState), [scopeState]);
  const district = React.useMemo(
    () => (scopeDistrict && districts.includes(scopeDistrict) ? scopeDistrict : ''),
    [districts, scopeDistrict],
  );

  React.useEffect(() => {
    let alive = true;
    // Scoped list: only crops that state actually reports prices for.
    getScopedCommodities({
      state: scopeState || undefined,
      district: district || undefined,
      predictable: true,
    })
      .then((res) => {
        const list = (res.commodities || []).filter(Boolean);
        if (!alive) return;
        // A crop the URL explicitly asked for (e.g. the chat's "14-day
        // forecast" action) must stay selected even when the state's
        // predictable list does not include it — otherwise the page silently
        // shows a different crop's forecast. Keep it in the picker and let the
        // honest "not enough history" message explain the gap.
        // The crop the farmer actually asked for — from the URL, or the crop
        // saved on their profile — must stay selected. Silently swapping it for
        // whatever the state can forecast hides their own crop.
        const requested = params.get('crop') || profile?.crops?.[0] || null;
        if (requested && !list.includes(requested)) {
          setCommodities([requested, ...list]);
        } else {
          setCommodities(list);
          if (!requested && list.length && !list.includes(crop)) setCrop(list[0]);
        }
      })
      .catch(() => {
        if (!alive) return;
        getCommodities()
          .then((list) => alive && setCommodities(list || []))
          .catch(() => alive && setCommodities([]));
      });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scopeState, district]);

  // With no explicit crop (and no saved profile crop), default to the
  // commodity with the most REAL history so the first view is never a
  // "not enough data" dead end.
  React.useEffect(() => {
    if (params.get('crop') || profile?.crops?.length) return;
    let alive = true;
    fetch(`${env.apiBaseUrl}/market/coverage?limit=15`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        const first = d?.rows?.[0]?.commodity;
        if (alive && first) setCrop(first);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
      const live = await getMarketPrice(crop, district, scopeState).catch(() => null);
      if (!alive) return;

      const res = await fetch(`${env.apiBaseUrl}/predict/14day`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          district: district || null,
          commodity: crop,
          market: 'All',
          state: scopeState || null,
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

        // Plot history at the SAME scope the forecast resolved to, so the
        // solid line and the dashed forecast line meet instead of showing two
        // different geographic aggregates.
        const hist = await getMarketHistory(
          crop,
          entry.district || district,
          90,
          entry.state || scopeState,
        ).catch(() => null);
        if (alive) setHistory((hist?.points || []).slice(-45));
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
  }, [crop, scopeState, district]);

  // Context factors (season, weather, flood risk, festivals, supply, market
  // breadth). Loaded separately so a slow weather call never blocks the chart.
  React.useEffect(() => {
    let alive = true;
    setFactorsLoading(true);
    getPriceFactors({ commodity: crop, district: district || null, state: scopeState || null })
      .then((ctx) => {
        if (alive) setFactors(ctx);
      })
      .catch(() => {
        if (alive) setFactors(null);
      })
      .finally(() => {
        if (alive) setFactorsLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [crop, scopeState, district]);

  const best = React.useMemo(() => {
    if (!forecast?.trajectory?.length) return null;
    return forecast.trajectory.reduce((a, b) =>
      b.predicted_price > a.predicted_price ? b : a,
    );
  }, [forecast]);

  /** "2026-11" (a monthly series) reads as "Nov 2026", not a raw key. */
  const periodLabel = (value?: string | null) => {
    if (!value) return '—';
    if (/^\d{4}-\d{2}$/.test(value)) {
      const [y, m] = value.split('-').map(Number);
      return new Date(y, m - 1, 1).toLocaleDateString('en-IN', {
        month: 'short',
        year: 'numeric',
      });
    }
    return value;
  };

  const change = forecast?.predicted_change_pct ?? 0;
  // A +/-0.5% move is noise on a mandi price; calling it "trending up" would
  // send a farmer to market on nothing.
  const flat = Math.abs(change) < 0.5;
  const up = change >= 0;

  return (
    <AppShell>
      <PageHeader
        title={t('pricePrediction')}
        subtitle={`${[district, scopeState].filter(Boolean).join(', ') || 'All India'} · 14-day forecast`}
      />

      <div className="mb-3 flex items-start gap-2">
        <CropThumb crop={crop} size={44} />
        <div className="flex-1 space-y-2">
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
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <Select
              label="State"
              value={scopeState}
              onChange={(v) => {
                setScopeState(v);
                setScopeDistrict('');
              }}
              options={allStates.map((s) => ({ value: s, label: s }))}
              placeholder="All India"
            />
            <Select
              label="District"
              value={district}
              onChange={setScopeDistrict}
              options={districts.map((d) => ({ value: d, label: d }))}
              placeholder="Whole state"
              disabled={!scopeState}
              helper={scopeState ? undefined : 'Pick a state first'}
            />
          </div>
        </div>
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
                  {[forecast.district, forecast.state].filter(Boolean).join(', ') ||
                    [district, scopeState].filter(Boolean).join(', ') ||
                    'All India'}{' '}
                  · {periodLabel(forecast.history_last)}
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
              <span className="font-700">
                {flat ? 'Prices look steady. ' : up ? 'Prices are trending up. ' : 'Prices are easing. '}
              </span>
              {flat
                ? `The model expects little change for ${crop} over the next two weeks — sell when it suits your harvest and storage, not on this forecast alone.`
                : up
                  ? `Holding ${crop} for the next few days looks better than selling today at the current rate.`
                  : `Selling earlier is likely better — the model expects a dip over the next two weeks.`}
              {district && forecast.scope_level && forecast.scope_level !== 'district' && (
                <span className="mt-1 block text-ink-muted">
                  No published history for {district} yet — this is the{' '}
                  {forecast.state || scopeState || 'state'} state estimate.
                </span>
              )}
              {forecast.stale_days > 0 && (
                <span className="mt-1 block text-ink-muted">
                  Last real mandi record is {forecast.stale_days} day
                  {forecast.stale_days === 1 ? '' : 's'} old.
                </span>
              )}
            </div>
          </Card>

          {/* what the numbers are made of: AGMARKNET monthly averages, the
              annual season index, festivals inside the horizon, and observed
              supply shocks (the footprint of a flood/drought/strike) */}
          <Card>
            <div className="flex items-center justify-between gap-2">
              <CardLabel>What this forecast is built on</CardLabel>
              <Badge tone={forecast.history_basis === 'monthly' ? 'cached' : 'live'}>
                {forecast.history_basis === 'monthly' ? 'Monthly averages' : 'Daily mandi data'}
              </Badge>
            </div>
            <p className="mt-1.5 flex items-start gap-1.5 text-[11.5px] leading-relaxed text-ink-muted">
              <Database className="mt-0.5 h-3.5 w-3.5 shrink-0" strokeWidth={2} />
              {forecast.history_basis === 'monthly'
                ? `AGMARKNET district monthly analysis — ${forecast.history_months ?? 0} published monthly averages covering ${forecast.history_first} to ${forecast.history_last}, averaged across the districts in this scope.`
                : `Daily mandi records from ${forecast.history_first} to ${forecast.history_last} (${forecast.history_obs ?? 0} observations).`}
            </p>

            <div className="mt-2.5 grid grid-cols-1 gap-2 sm:grid-cols-2">
              {forecast.season && (
                <div className="rounded-sm border border-border bg-surface-2/60 p-2.5">
                  <p className="flex items-center gap-1.5 text-[10px] font-700 uppercase tracking-wide text-ink-muted">
                    <CalendarDays className="h-3 w-3" strokeWidth={2.4} /> Season
                  </p>
                  <p className="mt-1 text-[12.5px] font-700">
                    {forecast.season.month} ·{' '}
                    {forecast.season.index >= 1 ? '+' : ''}
                    {((forecast.season.index - 1) * 100).toFixed(1)}% vs yearly average
                  </p>
                  <p className="text-[10.5px] leading-snug text-ink-muted">
                    Measured from {forecast.season.months_used} monthly averages over{' '}
                    {forecast.season.years_used} year(s) in this scope.
                  </p>
                </div>
              )}
              {(forecast.festivals?.length ?? 0) > 0 && (
                <div className="rounded-sm border border-border bg-surface-2/60 p-2.5">
                  <p className="flex items-center gap-1.5 text-[10px] font-700 uppercase tracking-wide text-ink-muted">
                    <CalendarDays className="h-3 w-3" strokeWidth={2.4} /> Festivals ahead
                  </p>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {forecast.festivals?.slice(0, 3).map((f) => (
                      <span
                        key={`${f.name}-${f.date}`}
                        className="rounded-full border border-border px-2 py-0.5 text-[10.5px] text-ink"
                        title={f.approx ? 'Lunar date — varies by region' : 'Fixed date'}
                      >
                        {f.name} · {new Date(f.date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}
                        {f.approx ? '*' : ''}
                      </span>
                    ))}
                  </div>
                  <p className="mt-1 text-[10.5px] leading-snug text-ink-muted">
                    Each festival is checked against this crop's own past prices.
                    An uplift is only applied when the measured effect is larger
                    than the series' normal week-to-week noise.
                  </p>
                </div>
              )}
            </div>

            {(forecast.shocks?.length ?? 0) > 0 && (
              <div className="mt-2 rounded-sm border border-destructive/25 bg-destructive/6 p-2.5">
                <p className="text-[11px] font-700 text-destructive">
                  Supply shocks in the recent record
                </p>
                <ul className="mt-1 space-y-0.5">
                  {forecast.shocks?.map((s) => (
                    <li key={s} className="text-[11.5px] leading-relaxed text-ink-muted">
                      {s}
                    </li>
                  ))}
                </ul>
                <p className="mt-1 text-[10.5px] leading-snug text-ink-muted">
                  Moves that large usually follow unseasonal rain, flood or a transport disruption. The
                  forecast widens its range instead of guessing the cause.
                </p>
              </div>
            )}
          </Card>

          {(factorsLoading || factors) && <PriceFactorsCard factors={factors} loading={factorsLoading} />}

          {/* chart */}
          <Card>
            <div className="mb-1 flex items-center justify-between">
              <CardLabel>Price history + forecast</CardLabel>
              <span className="text-[10.5px] text-ink-muted">
                {forecast.model_label || forecast.model || 'Mandi forecast'}
              </span>
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
                    {best.change_from_initial_pct > 0.5
                      ? `Best of the next 14 days (+${best.change_from_initial_pct.toFixed(1)}% vs today)`
                      : `No better day ahead — today's ₹${Math.round(forecast.current_price).toLocaleString('en-IN')} is the highest of the next two weeks`}
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
            <p className="mb-2.5 text-[11.5px] leading-relaxed text-ink-muted">
              {forecast.history_basis === 'monthly'
                ? 'Published AGMARKNET monthly averages for this state and crop. Daily mandi records are used whenever they run deeper.'
                : t('coverageExplain')}
            </p>
            <div className="grid grid-cols-3 gap-2">
              <CoverageStat
                label={forecast.history_basis === 'monthly' ? 'Months' : 'Observations'}
                value={
                  forecast.history_basis === 'monthly'
                    ? forecast.history_months ?? coverage?.obs ?? 0
                    : coverage?.obs ?? 0
                }
              />
              <CoverageStat label="First" value={coverage?.first ?? '—'} small />
              <CoverageStat label="Last" value={coverage?.last ?? '—'} small />
            </div>
            {(forecast.events?.applied?.length ? true : false) && (
              <div className="mt-2.5 space-y-1.5 rounded-sm border border-leaf/25 bg-leaf/6 p-2.5">
                <p className="text-[10.5px] font-700 uppercase tracking-[0.1em] text-forest/70">
                  Adjusted for
                </p>
                {forecast.events!.applied!.map((ev) => (
                  <div key={ev.key} className="text-[11.5px] leading-relaxed">
                    <span className="font-700">
                      {ev.label} {ev.shift_pct >= 0 ? '+' : ''}{ev.shift_pct.toFixed(1)}%
                    </span>
                    <span className="mt-0.5 block text-[10.5px] text-ink-muted">{ev.evidence}</span>
                  </div>
                ))}
              </div>
            )}
            <div className="mt-2.5 flex flex-wrap items-center gap-2">
              <Badge tone={forecast.mape <= 10 ? 'live' : forecast.mape <= 20 ? 'cached' : 'danger'}>
                MAPE {forecast.mape.toFixed(1)}%
              </Badge>
              <Badge tone="neutral">
                {Array.isArray(forecast.backtest_folds)
                  ? forecast.backtest_folds.length
                  : forecast.backtest_folds || 0}{' '}
                backtest folds
              </Badge>
              <Badge tone="neutral">scope: {forecast.scope_level || 'district'}</Badge>
            </div>
            <p className="mt-2 flex items-start gap-1.5 text-[10.5px] leading-relaxed text-ink-muted">
              <Info className="mt-0.5 h-3 w-3 shrink-0" strokeWidth={2} />
              MAPE is measured on rolling-origin backtests over this commodity's
              own real history, not on synthetic data. The model is picked by
              that backtest from several candidates, including simply repeating
              today's price.
              {forecast.data_quality?.repaired_rows
                ? ` ${forecast.data_quality.repaired_rows} bad unit row(s) were repaired before fitting.`
                : ''}
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
