import * as React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  ChevronDown,
  ChevronLeft,
  ChevronUp,
  Clock,
  Droplets,
  IndianRupee,
  Layers,
  Sprout,
  Thermometer,
  TrendingUp,
} from 'lucide-react';
import { AppShell } from '@/components/ui-kit/AppShell';
import {
  Card,
  CardLabel,
  EmptyState,
  PageHeader,
  ProgressRing,
  Sparkline,
  shortDate,
} from '@/components/ui-kit/core';
import { CropThumb } from '@/components/ui-kit/PriceCard';
import { Button } from '@/components/ui-kit/form';
import { getCropInfo, getMarketHistory, type CropInfo, type MarketHistory } from '@/lib/marketApi';
import type { CropEntry } from '@/lib/apiTypes';
import { cn } from '@/lib/utils';

/**
 * Recommendation detail.
 *
 * Every number is either real or absent. A crop with no confidence from the
 * model shows "--" rather than an invented 80%, and a crop without a photo gets
 * its own tinted leaf tile instead of borrowing another crop's picture.
 */
const pct = (v: number | null) => (v == null ? '--' : `${Math.round(v * 100)}%`);

const CropDetailPage: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();

  const cropsData: CropEntry[] = (location.state?.crops as CropEntry[]) || [];
  const district: string | undefined = location.state?.district;

  const [open, setOpen] = React.useState<string | null>(null);
  const [infoByCrop, setInfoByCrop] = React.useState<Record<string, CropInfo | null>>({});
  const [historyByCrop, setHistoryByCrop] = React.useState<Record<string, MarketHistory | null>>({});

  const names = React.useMemo(
    () => cropsData.map((c) => String(c.name || '')).filter(Boolean),
    [cropsData],
  );

  React.useEffect(() => {
    if (!names.length) return;
    let cancelled = false;

    getCropInfo(names)
      .then((res) => {
        if (cancelled) return;
        setInfoByCrop(res?.crops || Object.fromEntries(names.map((n) => [n, null])));
      })
      .catch(() => !cancelled && setInfoByCrop(Object.fromEntries(names.map((n) => [n, null]))));

    Promise.all(
      names.map(async (n) => {
        const mapped = n.toLowerCase() === 'rice' ? 'Paddy' : n;
        const h = await getMarketHistory(mapped, district, 60).catch(() => null);
        return [n, h] as const;
      }),
    )
      .then((entries) => !cancelled && setHistoryByCrop(Object.fromEntries(entries)))
      .catch(() => {});

    return () => {
      cancelled = true;
    };
  }, [names, district]);

  const periodText = (info?: CropInfo | null) => {
    const d = info?.duration_days;
    if (d && d[0] > 0 && d[1] > 0) {
      if (info?.perennial && info?.maturity_note) return info.maturity_note;
      const m1 = Math.round(d[0] / 30.4);
      const m2 = Math.round(d[1] / 30.4);
      return m1 === m2 ? `${m1} months` : `${m1}–${m2} months`;
    }
    return info?.maturity_note || null;
  };

  const yieldText = (info?: CropInfo | null) => {
    const y = info?.yield_t_ha;
    if (y && y[0] > 0 && y[1] > 0) {
      const f = (v: number) => (v % 1 === 0 ? v : v.toFixed(1));
      return y[0] === y[1] ? `${f(y[0])} t/ha` : `${f(y[0])}–${f(y[1])} t/ha`;
    }
    return null;
  };

  /** Real yield band × real mandi price. Labelled an estimate in the UI. */
  const revenuePerAcre = (info?: CropInfo | null, price?: number | null) => {
    const y = info?.yield_t_ha;
    if (!y || !price || y[1] <= 0) return null;
    const q = (tHa: number) => tHa * 4.05 * price;
    const fmt = (v: number) => `₹${Math.round(v).toLocaleString('en-IN')}`;
    return y[0] > 0 ? `${fmt(q(y[0]))} – ${fmt(q(y[1]))}` : fmt(q(y[1]));
  };

  const rows = cropsData.map((crop, index) => {
    const rawName = String(crop.name || '');
    const info = infoByCrop[rawName] ?? null;
    const history = historyByCrop[rawName] ?? null;

    // Real confidence only — never a made-up default.
    const rawConfidence =
      typeof crop.confidence === 'number' ? crop.confidence : undefined;
    const score =
      typeof crop.matchScore === 'number'
        ? crop.matchScore
        : rawConfidence != null
          ? Math.round(rawConfidence * 100)
          : null;

    const price = typeof crop.mandiPrice === 'number' ? crop.mandiPrice : null;
    const factor = (v: unknown): number | null =>
      typeof v === 'number' && Number.isFinite(v) ? v : null;

    // A price the backend flagged as an MSP reference is not a mandi
    // observation; the card must say so rather than calling it today's rate.
    const priceIsReference =
      crop.mandiIsReal === false || crop.mandiBadge === 'msp';

    return {
      id: rawName,
      rank: index + 1,
      name: rawName ? rawName.charAt(0).toUpperCase() + rawName.slice(1) : 'Crop',
      score,
      info,
      history,
      price,
      priceIsReference,
      priceSource: typeof crop.mandiMarket === 'string' ? crop.mandiMarket : null,
      priceScope: typeof crop.mandiScope === 'string' ? crop.mandiScope : null,
      duration: periodText(info),
      yieldText: yieldText(info),
      revenue: revenuePerAcre(info, price),
      spark: (history?.points || []).slice(-14).map((p) => p.price),
      // Evidence the advisor ranked on. Null stays null — no invented bars.
      soilFit: factor(crop.soil_fit),
      climateFit: factor(crop.climate_fit),
      regionShare: factor(crop.region_share),
      marketScore: factor(crop.market_score),
      grossPerHa: factor(crop.gross_return_per_ha),
      marketScope:
        typeof crop.market_price_scope === 'string' ? crop.market_price_scope : null,
      marketDate:
        typeof crop.market_price_date === 'string' ? crop.market_price_date : null,
      marketBadge:
        typeof crop.market_price_badge === 'string' ? crop.market_price_badge : null,
    };
  });

  if (!rows.length) {
    return (
      <AppShell>
        <PageHeader title="Crop results" />
        <EmptyState
          title="No results to show"
          description="Open the crop advisor and run a recommendation — results appear here with real agronomy and mandi data."
          action={<Button onClick={() => navigate('/crops')}>Open crop advisor</Button>}
        />
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div className="max-w-3xl">
        <div className="mb-3 flex items-center gap-2">
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="press grid h-10 w-10 place-items-center rounded-full border border-border bg-surface"
            aria-label="Back"
          >
            <ChevronLeft className="h-5 w-5" strokeWidth={2} />
          </button>
          <span className="text-[12px] font-600 text-ink-muted">
            {district
              ? `Prices scoped to ${district.charAt(0).toUpperCase()}${district.slice(1)}`
              : 'All India prices'}
          </span>
        </div>

        <PageHeader
          title="Recommended crops"
          subtitle="Ranked on your soil, climate, season, district cropping and mandi returns"
        />

        <div className="space-y-3">
          {rows.map((crop) => {
            const isOpen = open === crop.id;
            return (
              <Card key={crop.id} padded={false} className="overflow-hidden">
                <button
                  type="button"
                  onClick={() => setOpen(isOpen ? null : crop.id)}
                  aria-expanded={isOpen}
                  className="flex w-full items-center gap-3 p-3 text-left"
                >
                  <div className="relative">
                    <CropThumb crop={crop.name} size={56} />
                    <span className="absolute -left-1 -top-1 grid h-5 w-5 place-items-center rounded-full text-[10px] font-800 text-white" style={{ background: 'var(--grad-leaf)' }}>
                      {crop.rank}
                    </span>
                  </div>

                  <div className="min-w-0 flex-1">
                    <p className="truncate font-display text-[15px] font-800 text-ink">
                      {crop.name}
                    </p>
                    <p className="mt-0.5 flex flex-wrap items-center gap-x-2.5 gap-y-0.5 text-[11.5px] text-ink-muted">
                      <span className="inline-flex items-center gap-1">
                        <TrendingUp className="h-3 w-3" strokeWidth={2.2} />
                        {crop.yieldText || '--'}
                      </span>
                      <span className="inline-flex items-center gap-1">
                        <Clock className="h-3 w-3" strokeWidth={2.2} />
                        {crop.duration || '--'}
                      </span>
                      <span className="inline-flex items-center gap-1">
                        <Droplets className="h-3 w-3" strokeWidth={2.2} />
                        {crop.info?.water_needs || '--'}
                      </span>
                    </p>
                  </div>

                  <div className="flex shrink-0 items-center gap-2">
                    {crop.score != null ? (
                      <ProgressRing value={crop.score} size={46} stroke={4.5} label={`${crop.score}`} />
                    ) : (
                      <span className="text-[13px] font-700 text-ink-muted">--</span>
                    )}
                    {isOpen ? (
                      <ChevronUp className="h-4 w-4 text-ink-muted" strokeWidth={2} />
                    ) : (
                      <ChevronDown className="h-4 w-4 text-ink-muted" strokeWidth={2} />
                    )}
                  </div>
                </button>

                {isOpen && (
                  <div className="border-t border-border px-3 py-3">
                    <div className="grid gap-3 sm:grid-cols-2">
                      <div>
                        <CardLabel>
                          {crop.priceIsReference ? 'Reference price (MSP)' : "Today's mandi price"}
                        </CardLabel>
                        <p className="mt-1 font-display text-[26px] font-800 tabular-nums text-ink">
                          {crop.price != null ? `₹${crop.price.toLocaleString('en-IN')}` : '--'}
                          {crop.price != null && (
                            <span className="ml-1 text-[11px] font-600 text-ink-muted">/quintal</span>
                          )}
                        </p>
                        {crop.priceIsReference && (
                          <p className="mt-1 text-[10.5px] leading-snug text-ink-muted">
                            {crop.priceSource || 'Government MSP reference'} — not a mandi observation.
                          </p>
                        )}
                        {crop.spark.length > 1 && (
                          <div className="mt-1">
                            <Sparkline points={crop.spark} width={180} height={34} />
                          </div>
                        )}
                        {crop.history?.scope && crop.history.scope !== 'district' && (
                          <p className="mt-1 text-[10.5px] uppercase tracking-wide text-ink-muted">
                            {crop.history.scope} scope
                          </p>
                        )}
                      </div>

                      <div className="space-y-1.5">
                        <Detail icon={<IndianRupee className="h-3.5 w-3.5" />} label="Est. gross per acre" value={crop.revenue || '--'} />
                        <Detail icon={<Layers className="h-3.5 w-3.5" />} label="Soil" value={crop.info?.soil_type || '--'} />
                        <Detail icon={<Thermometer className="h-3.5 w-3.5" />} label="Temperature" value={crop.info?.temp_range_c || '--'} />
                        <Detail icon={<Droplets className="h-3.5 w-3.5" />} label="Rainfall" value={crop.info?.rainfall_range_mm || '--'} />
                        <Detail icon={<Sprout className="h-3.5 w-3.5" />} label="pH range" value={crop.info?.ph_range || '--'} />
                      </div>
                    </div>
                    {(crop.soilFit != null || crop.grossPerHa != null) && (
                      <div className="mt-3 rounded-sm border border-border bg-surface-2/60 p-2.5">
                        <p className="text-[10px] font-700 uppercase tracking-[0.1em] text-ink-muted">
                          Why this crop ranks here
                        </p>
                        <div className="mt-1.5 grid gap-1.5 sm:grid-cols-2">
                          <Factor label="Soil match" value={pct(crop.soilFit)} />
                          <Factor label="Climate match" value={pct(crop.climateFit)} />
                          <Factor
                            label="Already grown here"
                            value={
                              crop.regionShare != null
                                ? `${Math.round(crop.regionShare * 100)}% of cropped area`
                                : '--'
                            }
                          />
                          <Factor
                            label="Gross return per hectare"
                            value={
                              crop.grossPerHa != null
                                ? `₹${Math.round(crop.grossPerHa).toLocaleString('en-IN')}`
                                : '--'
                            }
                            note={
                              crop.grossPerHa != null
                                ? `yield × ${crop.marketScope === 'district' ? 'district' : 'state-wide'} mandi price${crop.marketDate ? ` · ${shortDate(crop.marketDate)}` : ''} · before input costs`
                                : 'needs both a yield band and a mandi price'
                            }
                          />
                        </div>
                      </div>
                    )}

                    <p className={cn('mt-2 text-[11px] leading-relaxed text-ink-muted')}>
                      {crop.priceIsReference
                        ? 'This figure is a government MSP reference, not a mandi trade. Revenue below it is a bench-mark, not a price you were offered. '
                        : ''}
                      Estimated gross revenue uses the real yield band × the price above. It is
                      not a profit figure and excludes input costs.
                    </p>
                  </div>
                )}
              </Card>
            );
          })}
        </div>
      </div>
    </AppShell>
  );
};

function Factor({
  label,
  value,
  note,
}: {
  label: string;
  value: string;
  note?: string;
}) {
  return (
    <div className="rounded-sm border border-border bg-surface px-2 py-1.5">
      <p className="text-[10px] uppercase tracking-wide text-ink-muted">{label}</p>
      <p className="tnum mt-0.5 text-[12.5px] font-700 text-ink">{value}</p>
      {note && <p className="mt-0.5 text-[10px] leading-snug text-ink-muted">{note}</p>}
    </div>
  );
}

function Detail({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-center justify-between gap-2 border-b border-border pb-1 last:border-0">
      <span className="inline-flex items-center gap-1.5 text-[11.5px] text-ink-muted">
        <span className="text-primary">{icon}</span>
        {label}
      </span>
      <span className="text-[12px] font-700 text-ink">{value}</span>
    </div>
  );
}

export default CropDetailPage;
