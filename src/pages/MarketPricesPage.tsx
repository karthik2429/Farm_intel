import * as React from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowDownUp, LayoutGrid, List, MapPin, RefreshCw, Search, SlidersHorizontal } from 'lucide-react';
import { AppShell } from '@/components/ui-kit/AppShell';
import { PageHeader } from '@/components/ui-kit/core';
import { Card, Chip, EmptyState, Badge, PriceCardSkeleton, Skeleton } from '@/components/ui-kit/core';
import { PriceCard, type PriceData } from '@/components/ui-kit/PriceCard';
import { Input } from '@/components/ui-kit/form';
import { useAuth } from '@/contexts/AuthContext';
import { useLanguage } from '@/contexts/LanguageContext';
import { useProfile, defaultLocation } from '@/lib/profile';
import { getMarketHistory, getMarketPrice } from '@/lib/marketApi';
import { getCommodities } from '@/lib/priceApi';
import { cn } from '@/lib/utils';

type SortKey = 'name' | 'price-asc' | 'price-desc';

interface Row {
  commodity: string;
  price: PriceData | null;
  spark: number[];
}

const PAGE = 14;

const MarketPricesPage: React.FC = () => {
  const { t } = useLanguage();
  const { user } = useAuth();
  const navigate = useNavigate();
  const { profile } = useProfile(user?.id, user?.email);
  const loc = defaultLocation(profile);

  const [commodities, setCommodities] = React.useState<string[]>([]);
  const [query, setQuery] = React.useState('');
  const [sort, setSort] = React.useState<SortKey>('name');
  // Desktop gets the denser grid by default; phones stay a single column.
  const [grid, setGrid] = React.useState(
    () => typeof window !== 'undefined' && window.innerWidth >= 1024,
  );
  const [onlyAvailable, setOnlyAvailable] = React.useState(false);
  const [rows, setRows] = React.useState<Record<string, Row>>({});
  const [visible, setVisible] = React.useState(PAGE);
  const [loadingList, setLoadingList] = React.useState(true);
  const [refreshing, setRefreshing] = React.useState(false);
  const [updatedAt, setUpdatedAt] = React.useState<Date | null>(null);

  // commodity catalogue comes from the real price store
  React.useEffect(() => {
    let alive = true;
    getCommodities()
      .then((list) => alive && setCommodities(list?.length ? list : []))
      .catch(() => alive && setCommodities([]))
      .finally(() => alive && setLoadingList(false));
    return () => {
      alive = false;
    };
  }, []);

  const filtered = React.useMemo(() => {
    const q = query.trim().toLowerCase();
    let list = commodities;
    if (q) list = list.filter((c) => c.toLowerCase().includes(q));
    return list;
  }, [commodities, query]);

  const shown = filtered.slice(0, visible);

  // fetch prices for the visible window only
  React.useEffect(() => {
    let alive = true;
    const missing = shown.filter((c) => !rows[c]);
    if (!missing.length) return;
    setRefreshing(true);
    Promise.all(
      missing.map(async (crop) => {
        const [p, hist] = await Promise.all([
          getMarketPrice(crop, loc.district, loc.state),
          getMarketHistory(crop, loc.district, 30, loc.state).catch(() => null),
        ]);
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
        return [crop, { commodity: crop, price: data, spark: (hist?.points || []).slice(-14).map((h) => h.price) }] as const;
      }),
    ).then((entries) => {
      if (!alive) return;
      setRows((prev) => {
        const next = { ...prev };
        entries.forEach(([k, v]) => {
          next[k] = v;
        });
        return next;
      });
      setUpdatedAt(new Date());
      setRefreshing(false);
    });
    return () => {
      alive = false;
    };
  }, [shown, loc.district, loc.state, rows]);

  const sorted = React.useMemo(() => {
    const list = shown.map((c) => rows[c]).filter(Boolean) as Row[];
    const byName = (a: Row, b: Row) => a.commodity.localeCompare(b.commodity);
    if (sort === 'name') return [...list].sort(byName);
    const val = (r: Row) => (r.price?.price == null ? -1 : r.price.price);
    return [...list].sort((a, b) => (sort === 'price-asc' ? val(a) - val(b) : val(b) - val(a)));
  }, [shown, rows, sort]);

  const visibleRows = onlyAvailable ? sorted.filter((r) => r.price?.price != null) : sorted;

  const refresh = () => {
    setRows({});
    setUpdatedAt(null);
  };

  const ago = (d: Date | null) => {
    if (!d) return '';
    const mins = Math.max(0, Math.round((Date.now() - d.getTime()) / 60000));
    return mins < 1 ? 'just now' : `${mins} min ago`;
  };

  return (
    <AppShell>
      <PageHeader
        title={t('mandiPrices')}
        subtitle={`${loc.label || 'All India'} · ${t('realTimeRates')}`}
        right={
          <button
            type="button"
            onClick={() => navigate('/profile')}
            className="press inline-flex h-11 items-center gap-1.5 rounded-full border border-border bg-surface px-3 text-[12px] font-600 shadow-sm"
          >
            <MapPin className="h-3.5 w-3.5 text-primary" strokeWidth={2.2} />
            {loc.district || 'Set district'}
          </button>
        }
      />

      {/* sticky search + filters */}
      <div className="sticky top-0 z-20 -mx-4 mb-3 bg-background/85 px-4 py-2 backdrop-blur-xl sm:-mx-6 sm:px-6">
        <div className="flex items-center gap-2">
          <Input
            label={t('search')}
            icon={<Search className="h-4 w-4" strokeWidth={2} />}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setVisible(PAGE);
            }}
            placeholder="Tomato, onion, cotton…"
            className="flex-1"
          />
          <button
            type="button"
            onClick={() => setGrid((g) => !g)}
            aria-label={grid ? 'Show list' : 'Show grid'}
            className="press grid h-[52px] w-[52px] shrink-0 place-items-center rounded-sm border border-border bg-surface text-ink-muted"
          >
            {grid ? <List className="h-4 w-4" strokeWidth={2} /> : <LayoutGrid className="h-4 w-4" strokeWidth={2} />}
          </button>
        </div>

        <div className="mt-2 flex items-center gap-1.5 overflow-x-auto pb-1 no-scrollbar">
          <Chip
            active={sort === 'name'}
            onClick={() => setSort('name')}
            icon={<SlidersHorizontal className="h-3 w-3" strokeWidth={2.2} />}
          >
            A–Z
          </Chip>
          <Chip active={sort === 'price-desc'} onClick={() => setSort('price-desc')} icon={<ArrowDownUp className="h-3 w-3" strokeWidth={2.2} />}>
            Highest
          </Chip>
          <Chip active={sort === 'price-asc'} onClick={() => setSort('price-asc')}>
            Lowest
          </Chip>
          <Chip active={onlyAvailable} onClick={() => setOnlyAvailable((v) => !v)}>
            Available only
          </Chip>
          <button
            type="button"
            onClick={refresh}
            className="press ml-auto inline-flex h-9 shrink-0 items-center gap-1 rounded-full border border-border bg-surface px-3 text-[12px] font-600 text-ink-muted"
          >
            <RefreshCw className={cn('h-3 w-3', refreshing && 'animate-spin')} strokeWidth={2.2} />
            {refreshing ? 'Updating' : 'Refresh'}
          </button>
        </div>
      </div>

      {updatedAt && (
        <p className="mb-2 text-[11px] text-ink-muted">Updated {ago(updatedAt)} · AGMARKNET</p>
      )}

      {loadingList ? (
        <div className="space-y-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <PriceCardSkeleton key={i} />
          ))}
        </div>
      ) : !commodities.length ? (
        <EmptyState
          title="No mandi catalogue yet"
          description="The price store is empty. Run the daily ingest (or set DATA_GOV_API_KEY) and rates will appear here — nothing is fabricated in the meantime."
        />
      ) : !visibleRows.length && !refreshing ? (
        <EmptyState
          title={`No rates for “${query}”`}
          description="That commodity has no real mandi record for this scope yet. Try All India or another crop."
          action={
            <button
              type="button"
              onClick={() => {
                setQuery('');
                setOnlyAvailable(false);
              }}
              className="rounded-full border border-border px-4 py-2 text-[12.5px] font-600"
            >
              Clear filters
            </button>
          }
        />
      ) : (
        <>
          <div className={cn(grid ? 'grid gap-2 sm:grid-cols-2 xl:grid-cols-3' : 'space-y-2', 'stagger')}>
            {visibleRows.map((r) =>
              r.price ? (
                <PriceCard
                  key={r.commodity}
                  data={r.price}
                  spark={r.spark}
                  onClick={() => navigate(`/predict?crop=${encodeURIComponent(r.commodity)}`)}
                />
              ) : (
                <Card key={r.commodity} className="flex items-center justify-between gap-3">
                  <span className="text-[13px] font-600">{r.commodity}</span>
                  <Skeleton className="h-5 w-16" />
                </Card>
              ),
            )}
          </div>

          {refreshing && (
            <div className="mt-2 space-y-2">
              <PriceCardSkeleton />
            </div>
          )}

          {visible < filtered.length && (
            <button
              type="button"
              onClick={() => setVisible((v) => v + PAGE)}
              className="press mt-3 h-11 w-full rounded-sm border border-border bg-surface text-[13px] font-600 hover:bg-surface-2"
            >
              Show more ({filtered.length - visible} left)
            </button>
          )}

          <div className="mt-4 flex flex-wrap items-center gap-2 text-[10.5px] text-ink-muted">
            <Badge tone="live" dot>
              Live
            </Badge>
            means a real AGMARKNET row for today
            <Badge tone="cached">Cached</Badge>
            means the last stored real row
            <Badge tone="unavailable">Unavailable</Badge>
            means there is no real record — never a guess
          </div>
        </>
      )}
    </AppShell>
  );
};

export default MarketPricesPage;
