import * as React from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  ArrowRight,
  Droplets,
  FlaskConical,
  MapPin,
  Mic,
  RefreshCw,
  Repeat2,
  Sparkles,
  Sprout,
  Store,
  TrendingUp,
  Wind,
} from 'lucide-react';
import { AppShell } from '@/components/ui-kit/AppShell';
import { HeroChip, HeroHeader } from '@/components/ui-kit/HeroHeader';
import {
  Badge,
  Card,
  CardLabel,
  EmptyState,
  PriceCardSkeleton,
  ProgressRing,
  Skeleton,
  StatTile,
} from '@/components/ui-kit/core';
import { CropThumb, PriceCard, type PriceData } from '@/components/ui-kit/PriceCard';
import { useAuth } from '@/contexts/AuthContext';
import { useLanguage } from '@/contexts/LanguageContext';
import { useProfile, defaultLocation } from '@/lib/profile';
import { InstallPrompt } from '@/components/OfflineBanner';
import { getCropRecommendations } from '@/lib/api';
import { getMarketHistory, getMarketPrice, getWeather } from '@/lib/marketApi';
import { cn } from '@/lib/utils';

interface Weather {
  temperature: number;
  humidity: number;
  rainfall: number;
}

const QUICK_ACTIONS = [
  { to: '/crops', label: 'Crops', icon: Sprout, tint: 'from-[#16A34A] to-[#22C55E]' },
  { to: '/market', label: 'Market', icon: Store, tint: 'from-[#0B3D2E] to-[#14764A]' },
  { to: '/predict', label: 'Predict', icon: TrendingUp, tint: 'from-[#F4B942] to-[#F59E0B]' },
  { to: '/rotation', label: 'Rotation', icon: Repeat2, tint: 'from-[#0E7490] to-[#22D3EE]' },
  { to: '/fertilizer', label: 'Fertiliser', icon: FlaskConical, tint: 'from-[#7C3AED] to-[#A78BFA]' },
];

const HomeDashboard: React.FC = () => {
  const { t } = useLanguage();
  const { user } = useAuth();
  const navigate = useNavigate();
  const { profile } = useProfile(user?.id, user?.email);
  const loc = defaultLocation(profile);

  const [weather, setWeather] = React.useState<Weather | null>(null);
  const [weatherFailed, setWeatherFailed] = React.useState(false);
  const [crops, setCrops] = React.useState<{ crop: string; price: PriceData | null; spark: number[] }[]>([]);
  const [loadingCrops, setLoadingCrops] = React.useState(true);
  const [recs, setRecs] = React.useState<{ crop: string; confidence: number }[]>([]);

  const watchCrops = React.useMemo(
    () => (profile?.crops?.length ? profile.crops.slice(0, 5) : ['Tomato', 'Onion', 'Cotton', 'Potato']),
    [profile?.crops],
  );

  React.useEffect(() => {
    let alive = true;
    getWeather({ district: loc.district, state: loc.state, lat: loc.lat ?? undefined, lon: loc.lon ?? undefined })
      .then((w) => {
        if (!alive) return;
        if (w) setWeather(w);
        else setWeatherFailed(true);
      })
      .catch(() => alive && setWeatherFailed(true));
    return () => {
      alive = false;
    };
  }, [loc.district, loc.state, loc.lat, loc.lon]);

  const loadCrops = React.useCallback(() => {
    let alive = true;
    setLoadingCrops(true);
    Promise.all(
      watchCrops.map(async (crop) => {
        const [p, hist] = await Promise.all([
          getMarketPrice(crop, loc.district, loc.state),
          getMarketHistory(crop, loc.district, 30, loc.state).catch(() => null),
        ]);
        const spark = (hist?.points || []).slice(-14).map((h) => h.price);
        const data: PriceData | null = p
          ? {
              commodity: crop,
              district: loc.district,
              state: loc.state,
              market: p.market,
              price: p.modal,
              min_price: p.min,
              max_price: p.max,
              date: p.date,
              source: p.source,
              is_real: p.is_real,
              badge: p.badge,
              detail: p.detail,
            }
          : null;
        return { crop, price: data, spark };
      }),
    ).then((res) => {
      if (!alive) return;
      setCrops(res);
      setLoadingCrops(false);
    });
    return () => {
      alive = false;
    };
  }, [watchCrops, loc.district, loc.state]);

  React.useEffect(() => {
    const cleanup = loadCrops();
    return cleanup;
  }, [loadCrops]);

  React.useEffect(() => {
    let alive = true;
    getCropRecommendations({
      district: loc.district || undefined,
      state: loc.state || undefined,
      season: profile?.season_focus || 'kharif',
    })
      .then((res) => {
        if (!alive || !res) return;
        const alts = (res.alternatives || []).slice(0, 3);
        setRecs(alts.map((a: { crop: string; confidence: number }) => ({ crop: a.crop, confidence: a.confidence })));
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [loc.district, loc.state, profile?.season_focus]);

  const bestPrice = React.useMemo(() => {
    const priced = crops.filter((c) => c.price?.price != null);
    if (!priced.length) return null;
    return priced.reduce((a, b) => ((a.price!.price || 0) > (b.price!.price || 0) ? a : b));
  }, [crops]);

  const hour = new Date().getHours();
  const greeting = hour < 12 ? 'Suprabhat' : hour < 17 ? 'Namaste' : 'Namaste';
  const displayName = profile?.name?.split(' ')[0] || user?.email?.split('@')[0] || '';

  return (
    <AppShell>
      <HeroHeader>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-[11.5px] font-600 uppercase tracking-[0.14em] text-white/65">
              {greeting}
            </p>
            <h1 className="mt-0.5 truncate font-display text-[24px] font-800 leading-tight tracking-tight">
              {displayName || t('welcome')}
            </h1>
            <div className="mt-2.5 flex flex-wrap gap-1.5">
              <HeroChip
                icon={<MapPin className="h-3 w-3" strokeWidth={2.2} />}
                onClick={() => navigate('/profile')}
              >
                {loc.label || 'Set your district'}
              </HeroChip>
              <HeroChip icon={<Sparkles className="h-3 w-3" strokeWidth={2.2} />}>
                {profile?.season_focus ? profile.season_focus : 'Kharif'} season
              </HeroChip>
            </div>
          </div>

          <div className="shrink-0 text-right">
            {weather ? (
              <>
                <p className="font-display text-[38px] font-800 leading-none tnum">
                  {Math.round(weather.temperature)}°
                </p>
                <p className="mt-0.5 text-[11px] text-white/70">Live now</p>
              </>
            ) : weatherFailed ? (
              <p className="text-[11px] text-white/70">Weather unavailable</p>
            ) : (
              <Skeleton className="h-10 w-16 bg-white/20" />
            )}
          </div>
        </div>

        {weather && (
          <div className="mt-3.5 flex gap-1.5">
            <HeroChip icon={<Droplets className="h-3 w-3" strokeWidth={2.2} />}>
              {Math.round(weather.humidity)}% humidity
            </HeroChip>
            <HeroChip icon={<Wind className="h-3 w-3" strokeWidth={2.2} />}>
              {weather.rainfall.toFixed(1)} mm rain
            </HeroChip>
          </div>
        )}
      </HeroHeader>

      {/* overlapping content */}
      <div className="relative z-10 -mt-12 space-y-5">
        <InstallPrompt />
        <button
          type="button"
          onClick={() => navigate('/chat')}
          className="press flex w-full items-center gap-3 rounded-md border border-border bg-surface p-3 text-left shadow-md hover:shadow-lg"
        >
          <span className="grid h-9 w-9 place-items-center rounded-full bg-primary/12 text-primary">
            <Sparkles className="h-4 w-4" strokeWidth={2} />
          </span>
          <span className="min-w-0 flex-1 truncate text-[13.5px] text-ink-muted">
            {t('askInLanguage')}
          </span>
          <span className="grid h-9 w-9 place-items-center rounded-full bg-gold text-forest">
            <Mic className="h-4 w-4" strokeWidth={2.2} />
          </span>
        </button>

        {/* quick actions */}
        <section>
          <div className="grid grid-cols-5 gap-2">
            {QUICK_ACTIONS.map((a) => (
              <Link
                key={a.to}
                to={a.to}
                className="press group flex flex-col items-center gap-1.5 rounded-sm border border-border bg-surface p-2.5 text-center shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md"
              >
                <span
                  className={cn(
                    'grid h-9 w-9 place-items-center rounded-sm bg-gradient-to-br text-white shadow-sm',
                    a.tint,
                  )}
                >
                  <a.icon className="h-[18px] w-[18px]" strokeWidth={2} />
                </span>
                <span className="text-[10.5px] font-600 leading-tight text-ink">{a.label}</span>
              </Link>
            ))}
          </div>
        </section>

        {/* my crops */}
        <section>
          <div className="mb-2.5 flex items-end justify-between">
            <h2 className="font-display text-[17px] font-700 tracking-tight">{t('myCrops')}</h2>
            <Link to="/market" className="inline-flex items-center gap-1 text-[12px] font-600 text-primary">
              {t('viewAll')} <ArrowRight className="h-3 w-3" strokeWidth={2.4} />
            </Link>
          </div>

          {loadingCrops ? (
            <div className="space-y-2">
              <PriceCardSkeleton />
              <PriceCardSkeleton />
            </div>
          ) : crops.length ? (
            <div className="space-y-2 stagger">
              {crops.map(({ crop, price, spark }) =>
                price ? (
                  <PriceCard
                    key={crop}
                    data={price}
                    spark={spark}
                    onClick={() => navigate(`/predict?crop=${encodeURIComponent(crop)}`)}
                  />
                ) : (
                  <Card key={crop} className="flex items-center gap-3">
                    <CropThumb crop={crop} size={44} />
                    <div className="min-w-0 flex-1">
                      <p className="font-display text-[13.5px] font-700">{crop}</p>
                      <p className="text-[11.5px] text-ink-muted">No mandi record for your district yet</p>
                    </div>
                    <Badge tone="unavailable">Unavailable</Badge>
                  </Card>
                ),
              )}
            </div>
          ) : (
            <EmptyState
              title="No crops watched yet"
              description="Add the crops you grow in your profile to see their mandi prices here."
              action={
                <button
                  type="button"
                  onClick={() => navigate('/profile')}
                  className="rounded-full bg-primary px-4 py-2 text-[12.5px] font-700 text-primary-foreground"
                >
                  Add my crops
                </button>
              }
            />
          )}
        </section>

        {/* best time to sell */}
        {bestPrice?.price?.price != null && (
          <Card variant="gold" className="flex items-center gap-3">
            <span className="grid h-11 w-11 shrink-0 place-items-center rounded-sm bg-forest/10 text-forest">
              <TrendingUp className="h-5 w-5" strokeWidth={2.2} />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-[10.5px] font-700 uppercase tracking-[0.1em] text-forest/70">
                {t('bestTimeToSell')}
              </p>
              <p className="mt-0.5 font-display text-[15px] font-800 leading-tight text-forest">
                {bestPrice.crop} · ₹{bestPrice.price!.price!.toLocaleString('en-IN')}/q
              </p>
              <p className="text-[11.5px] text-forest/75">
                Highest of your crops in {loc.district || 'your district'} today
              </p>
            </div>
            <button
              type="button"
              onClick={() => navigate(`/predict?crop=${encodeURIComponent(bestPrice.crop)}`)}
              className="press shrink-0 rounded-full bg-forest px-3 py-2 text-[11.5px] font-700 text-white"
            >
              Forecast
            </button>
          </Card>
        )}

        {/* recommendations */}
        <section>
          <div className="mb-2.5 flex items-end justify-between">
            <div>
              <h2 className="font-display text-[17px] font-700 tracking-tight">
                {t('topRecommendations')}
              </h2>
              <p className="text-[11.5px] text-ink-muted">{t('aiBasedSelection')}</p>
            </div>
            <Link to="/crops" className="text-[12px] font-600 text-primary">
              {t('viewAll')}
            </Link>
          </div>

          {recs.length ? (
            <div className="grid gap-2 sm:grid-cols-3">
              {recs.map((r) => (
                <Card key={r.crop} interactive onClick={() => navigate(`/crop-detail?crop=${encodeURIComponent(r.crop)}`)}>
                  <div className="flex items-center gap-3">
                    <CropThumb crop={r.crop} size={44} />
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-display text-[13.5px] font-700">{r.crop}</p>
                      <p className="text-[11px] text-ink-muted">{t('matchScore')}</p>
                    </div>
                    <ProgressRing value={Math.round(r.confidence * 100)} size={46} stroke={5} />
                  </div>
                </Card>
              ))}
            </div>
          ) : (
            <Card className="flex items-center justify-between gap-3">
              <p className="text-[12.5px] text-ink-muted">
                Recommendations need your district and soil — set them once and this fills in.
              </p>
              <button
                type="button"
                onClick={() => navigate('/profile')}
                className="shrink-0 rounded-full border border-border px-3 py-1.5 text-[11.5px] font-600"
              >
                Set up
              </button>
            </Card>
          )}
        </section>

        {/* mandi movers */}
        <section>
          <div className="mb-2.5 flex items-center justify-between">
            <h2 className="font-display text-[17px] font-700 tracking-tight">{t('mandiMovers')}</h2>
            <button
              type="button"
              onClick={() => loadCrops()}
              className="press inline-flex items-center gap-1 rounded-full border border-border px-2.5 py-1 text-[11px] font-600 text-ink-muted"
            >
              <RefreshCw className="h-3 w-3" strokeWidth={2.2} /> Refresh
            </button>
          </div>
          <Card className="divide-y divide-border p-0">
            {crops.slice(0, 4).map(({ crop, price, spark }) => (
              <div key={crop} className="flex items-center gap-3 px-3 py-2.5">
                <CropThumb crop={crop} size={32} />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[12.5px] font-600">{crop}</p>
                  <p className="truncate text-[10.5px] text-ink-muted">
                    {price?.market || 'Market unknown'}
                  </p>
                </div>
                <span className="tnum text-[13px] font-700">
                  {price?.price != null ? `₹${price.price.toLocaleString('en-IN')}` : '--'}
                </span>
              </div>
            ))}
            {!crops.length && (
              <div className="px-3 py-6 text-center text-[12px] text-ink-muted">No prices yet</div>
            )}
          </Card>
        </section>

        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <StatTile label="Crops watched" value={crops.length} icon={<Sprout className="h-4 w-4" />} />
          <StatTile
            label="With live price"
            value={crops.filter((c) => c.price?.price != null).length}
            icon={<TrendingUp className="h-4 w-4" />}
          />
          <StatTile
            label="District"
            value={<span className="text-[15px]">{loc.district || '—'}</span>}
            icon={<MapPin className="h-4 w-4" />}
          />
          <StatTile
            label="Season"
            value={<span className="text-[15px] capitalize">{profile?.season_focus || 'kharif'}</span>}
            icon={<Sparkles className="h-4 w-4" />}
          />
        </div>
      </div>
    </AppShell>
  );
};

export default HomeDashboard;
