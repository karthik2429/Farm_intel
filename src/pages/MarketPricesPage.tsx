import * as React from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowDownUp,
  LayoutGrid,
  List,
  MapPin,
  RefreshCw,
  Search,
  SlidersHorizontal,
  Sprout,
} from 'lucide-react';
import { AppShell } from '@/components/ui-kit/AppShell';
import { PageHeader } from '@/components/ui-kit/core';
import { Chip, EmptyState, Badge, PriceCardSkeleton, shortDate } from '@/components/ui-kit/core';
import { PriceCard, type PriceData } from '@/components/ui-kit/PriceCard';
import { Input, Select } from '@/components/ui-kit/form';
import { useAuth } from '@/contexts/AuthContext';
import { useLanguage } from '@/contexts/LanguageContext';
import { allStates, getDistricts } from '@/lib/indian-locations';
import { useProfile, defaultLocation } from '@/lib/profile';
import { clearMarketCache, getMarketHistory, getMarketPrice } from '@/lib/marketApi';
import { getScopedCommodities } from '@/lib/priceApi';
import { cn } from '@/lib/utils';

type SortKey = 'name' | 'price-asc' | 'price-desc';

interface Row {
  commodity: string;
  price: PriceData;
  spark: number[];
}

const PAGE = 14;

/**
 * AGMARKNET ships the same crop under more than one spelling — the monthly
 * backfill writes "Arecanut" while the daily feed writes
 * "Arecanut(Betelnut/Supari)". Both are real rows, but two cards at wildly
 * different prices look like a bug, so each group is shown once.
 */
const VARIANT_OF: Record<string, string> = {
  'arecanut(betelnut/supari)': 'arecanut',
  'arecanut': 'arecanut',
  'rice(fine/superfine/grade a)': 'rice',
  'paddy(fine/superfine/grade a)': 'paddy',
  'rose(local)': 'rose',
  'rose(loose)': 'rose',
  'rose(loose))': 'rose',
  'amla(nelli kai)': 'amla',
  'turmeric(raw)': 'turmeric',
};

const commodityKey = (name: string) => {
  const clean = name.trim().toLowerCase().replace(/\s+/g, ' ');
  return VARIANT_OF[clean] || clean;
};

const MarketPricesPage: React.FC = () => {
  const { t } = useLanguage();
  const { user } = useAuth();
  const navigate = useNavigate();
  const { profile } = useProfile(user?.id, user?.email);
  const loc = defaultLocation(profile);

  // Crops this market actually reported — never the national catalogue.
  const [commodities, setCommodities] = React.useState<string[]>([]);
  const [catalogueScope, setCatalogueScope] =
    React.useState<'district' | 'state' | 'all'>('state');
  /** How many of the listed crops this district itself reported. */
  const [localCount, setLocalCount] = React.useState(0);
  /** Mandis that report in the selected district (live feed first). */
  const [mandis, setMandis] = React.useState<string[]>([]);
  const [latestDate, setLatestDate] = React.useState<string | null>(null);
  /** The live feed could not be reached; the list is the last stored one. */
  const [fromCache, setFromCache] = React.useState(false);
  const [loadingList, setLoadingList] = React.useState(true);
  /** Bumped by the Refresh button: re-asks the feed and re-reads every card. */
  const [reloadKey, setReloadKey] = React.useState(0);

  const [query, setQuery] = React.useState('');
  const [cropFilter, setCropFilter] = React.useState('');
  const [sort, setSort] = React.useState<SortKey>('name');
  // Desktop gets the denser grid by default; phones stay a single column.
  const [grid, setGrid] = React.useState(
    () => typeof window !== 'undefined' && window.innerWidth >= 1024,
  );
  const [rows, setRows] = React.useState<Record<string, Row>>({});
  const [visible, setVisible] = React.useState(PAGE);
  const [refreshing, setRefreshing] = React.useState(false);
  const [updatedAt, setUpdatedAt] = React.useState<Date | null>(null);

  /**
   * The market being looked at: the farmer's own district ("nearest") by
   * default, or any state / district they pick. There is no "All India" here
   * — mandi rates are shown for a real market or not at all.
   */
  const [scope, setScope] = React.useState({ state: loc.state, district: loc.district });
  const scopeTouched = React.useRef(false);

  React.useEffect(() => {
    if (!scopeTouched.current) setScope({ state: loc.state, district: loc.district });
  }, [loc.state, loc.district]);

  const scopeDistricts = React.useMemo(() => getDistricts(scope.state), [scope.state]);
  const nearest = scope.state === loc.state && scope.district === loc.district;
  const scopeLabel = scope.district ? `${scope.district}, ${scope.state}` : scope.state;

  const pickScope = (next: { state: string; district: string }) => {
    scopeTouched.current = true;
    setScope(next);
  };

  // Scoped catalogue: refetched whenever the market changes, which also drops
  // every price card fetched for the previous one.
  React.useEffect(() => {
    if (!scope.state) {
      setCommodities([]);
      setRows({});
      setLoadingList(false);
      return;
    }
    let alive = true;
    setLoadingList(true);
    setRows({});
    setUpdatedAt(null);
    setVisible(PAGE);
    setCropFilter('');
    setFromCache(false);
    // A district page is strictly that district: its own crops, its own
    // mandis, its own latest trading day. Nothing is borrowed from a
    // neighbouring district, so the price under "Davangere" is a Davangere
    // price or it says unavailable.
    const strict = Boolean(scope.district);
    // Always ask the feed when the market changes (or Refresh is pressed) and
    // fall back to the last stored rows only when it cannot answer — a cached
    // district list must never be what a farmer sees while live data exists.
    getScopedCommodities({
      district: scope.district,
      state: scope.state,
      strict,
      refresh: true,
    })
      .then((res) => {
        if (!alive) return;
        setCommodities(res?.commodities ?? []);
        setCatalogueScope(res?.scope ?? (scope.district ? 'district' : 'state'));
        setLocalCount(res?.district_commodities?.length ?? 0);
        setMandis(res?.markets ?? []);
        setLatestDate(res?.latest_date ?? null);
        setFromCache(Boolean(res?.cached));
      })
      .catch(() => {
        if (alive) setCommodities([]);
      })
      .finally(() => {
        if (alive) setLoadingList(false);
      });
    return () => {
      alive = false;
    };
  }, [scope.state, scope.district, reloadKey]);

  const filtered = React.useMemo(() => {
    const q = query.trim().toLowerCase();
    let list = commodities;
    if (cropFilter) list = list.filter((c) => c === cropFilter);
    if (q) list = list.filter((c) => c.toLowerCase().includes(q));
    return list;
  }, [commodities, cropFilter, query]);

  const shown = filtered.slice(0, visible);

  // The batch key is a stable string, so re-rendering does not restart the
  // in-flight fetches (which used to cancel itself and leave the page blank).
  const pendingKey = React.useMemo(
    () => shown.filter((c) => !rows[c]).join('|'),
    [shown, rows],
  );

  // fetch prices for the visible window only
  React.useEffect(() => {
    if (!pendingKey) {
      setRefreshing(false);
      return;
    }
    let alive = true;
    const pending = pendingKey.split('|');
    setRefreshing(true);
    Promise.all(
      pending.map(async (crop) => {
        const [p, hist] = await Promise.all([
          // strict: a card for this district may only carry this district's
          // rate — the backend refreshes it from the live feed first.
          getMarketPrice(crop, scope.district, scope.state, {
            strict: Boolean(scope.district),
            fresh: true,
          }),
          getMarketHistory(crop, scope.district, 30, scope.state).catch(() => null),
        ]);
        // A commodity with no rate for this market is dropped by the render
        // below — the card is built only so the fetch can resolve.
        const data: PriceData = {
          commodity: crop,
          district: scope.district,
          state: scope.state,
          market: p?.market ?? '',
          price: p?.modal ?? null,
          min_price: p?.min ?? null,
          max_price: p?.max ?? null,
          date: p?.date,
          source: p?.source ?? 'unavailable',
          is_real: p?.is_real ?? false,
          badge: p?.badge ?? 'unavailable',
          detail: p?.detail,
          resolvedDistrict: p?.resolvedDistrict ?? null,
          resolvedState: p?.resolvedState ?? null,
          scope: p?.scope ?? null,
          daysOld: p?.daysOld ?? null,
        };
        return [
          crop,
          { commodity: crop, price: data, spark: (hist?.points || []).slice(-14).map((h) => h.price) },
        ] as const;
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
  }, [pendingKey, scope.district, scope.state]);

  // Every listed crop is shown: a priced card, or "--" with the backend's
  // reason. Silently dropping the ones without a rate was why crops looked
  // missing from this page.
  const available = React.useMemo(() => {
    const seen = new Map<string, Row>();
    shown.forEach((c) => {
      const row = rows[c];
      if (!row) return;
      const key = commodityKey(row.commodity);
      const prev = seen.get(key);
      if (!prev) {
        seen.set(key, row);
        return;
      }
      // Prefer the variant that actually carries a price, then the fresher one.
      const score = (r: Row) =>
        (r.price.price != null ? 1_000_000 : 0) + (r.spark.at(-1) ?? 0) - (r.price.daysOld ?? 0);
      if (score(row) > score(prev)) seen.set(key, row);
    });
    const list = [...seen.values()];
    const byName = (a: Row, b: Row) => a.commodity.localeCompare(b.commodity);
    if (sort === 'name') {
      return list.sort(
        (a, b) =>
          Number(b.price.price != null) - Number(a.price.price != null) || byName(a, b),
      );
    }
    const val = (r: Row) => r.price.price ?? -1;
    return list.sort((a, b) => (sort === 'price-asc' ? val(a) - val(b) : val(b) - val(a)));
  }, [shown, rows, sort]);

  const priced = React.useMemo(
    () => available.filter((r) => r.price.price != null).length,
    [available],
  );

  // If this window came back empty, widen it instead of showing a blank page.
  React.useEffect(() => {
    if (refreshing) return;
    if (visible < filtered.length && shown.length > 0 && priced === 0) {
      setVisible((v) => Math.min(v + PAGE, filtered.length));
    }
  }, [refreshing, visible, filtered.length, shown.length, priced]);

  // The district has no report of its own, so the list came back state-wide —
  // or it reports a few crops and the rest of the list is state-wide.
  const widenedToState =
    Boolean(scope.district) && catalogueScope === 'state' && commodities.length > 0;
  const partlyWidened =
    Boolean(scope.district) &&
    !widenedToState &&
    commodities.length > 0 &&
    localCount > 0 &&
    localCount < commodities.length;
  const subtitleScope = widenedToState
    ? `${scope.state} · ${scope.district} has no report yet`
    : scopeLabel;
  const subtitleRates = widenedToState
    ? 'state-wide rates'
    : nearest
      ? 'nearest real AGMARKNET rates'
      : 'real AGMARKNET rates';

  const refresh = () => {
    // Drop the per-crop memo as well, or the cards would be re-rendered from
    // the same cached quotes the button is meant to replace.
    clearMarketCache();
    setRows({});
    setUpdatedAt(null);
    setReloadKey((k) => k + 1);
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
        subtitle={`${subtitleScope || 'No location set'} · ${subtitleRates}`}
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

        <div className="mt-2 flex items-end gap-2">
          <Select
            label="State"
            value={scope.state}
            onChange={(v) => pickScope({ state: v, district: '' })}
            options={allStates.map((s) => ({ value: s, label: s }))}
            placeholder="Choose a state"
            className="flex-1"
          />
          <Select
            label="District"
            value={scope.district}
            onChange={(v) => pickScope({ state: scope.state, district: v })}
            options={scopeDistricts.map((d) => ({ value: d, label: d }))}
            placeholder="All districts"
            disabled={!scope.state}
            className="flex-1"
          />
        </div>

        <div className="mt-2">
          <Select
            label="Crop"
            value={cropFilter}
            onChange={(v) => {
              setCropFilter(v);
              setVisible(PAGE);
            }}
            options={commodities.map((c) => ({ value: c, label: c }))}
            placeholder="All crops this mandi reports"
            icon={<Sprout className="h-4 w-4" strokeWidth={1.9} />}
            disabled={!commodities.length}
          />
        </div>

        <div className="mt-2 flex items-center gap-1.5 overflow-x-auto pb-1 no-scrollbar">
          {loc.state && (
            <Chip
              active={nearest}
              onClick={() => {
                scopeTouched.current = false;
                setScope({ state: loc.state, district: loc.district });
              }}
              icon={<MapPin className="h-3 w-3" strokeWidth={2.2} />}
            >
              Nearest
            </Chip>
          )}
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
        <p className="mb-2 text-[11px] text-ink-muted">
          Updated {ago(updatedAt)} · AGMARKNET
          {latestDate ? ` · trading day ${shortDate(latestDate)}` : ''}
        </p>
      )}

      {scope.district && mandis.length > 0 && (
        <div className="mb-2 flex flex-wrap items-center gap-1.5 text-[11px] text-ink-muted">
          <span className="font-700 uppercase tracking-[0.08em]">
            {mandis.length} mandi{mandis.length === 1 ? '' : 's'} in {scope.district}
          </span>
          {mandis.map((m) => (
            <span
              key={m}
              className="rounded-full border border-border bg-surface px-2 py-0.5 text-[10.5px] font-600"
            >
              {m}
            </span>
          ))}
        </div>
      )}

      {fromCache && scope.district && (
        <div className="mb-2 rounded-sm border border-border bg-surface-2 px-3 py-2 text-[11.5px] text-ink-muted">
          The live AGMARKNET feed could not be reached, so these are the last
          stored rates for {scope.district} — every card carries its own date.
          Press Refresh to try the feed again.
        </div>
      )}

      {widenedToState && (
        <div className="mb-2 rounded-sm border border-harvest/40 bg-harvest/10 px-3 py-2 text-[11.5px] text-ink">
          No mandi in {scope.district} has filed a rate in the store yet — showing{' '}
          {scope.state} crops instead.
        </div>
      )}

      {partlyWidened && (
        <div className="mb-2 rounded-sm border border-harvest/40 bg-harvest/10 px-3 py-2 text-[11.5px] text-ink">
          {scope.district} reports {localCount} crop{localCount === 1 ? '' : 's'}. The
          other crops show the latest rate from elsewhere in {scope.state}, each
          labelled with its district and date.
        </div>
      )}

      {!loadingList && !refreshing && available.length > priced && (
        <div className="mb-2 rounded-sm border border-border bg-surface-2 px-3 py-2 text-[11.5px] text-ink-muted">
          {available.length - priced} of {available.length} listed crops have no
          AGMARKNET rate for this scope in the last 45 days — they are shown with
          "--" and the reason instead of being hidden.
        </div>
      )}

      {!scope.state ? (
        <EmptyState
          title="Set your state to see mandi rates"
          description="Mandi prices are shown only for a real state and district. Pick where you farm and this page lists what that market actually reported."
          action={
            <button
              type="button"
              onClick={() => navigate('/profile')}
              className="rounded-full border border-border px-4 py-2 text-[12.5px] font-600"
            >
              Choose my district
            </button>
          }
        />
      ) : loadingList ? (
        <div className="space-y-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <PriceCardSkeleton key={i} />
          ))}
        </div>
      ) : !commodities.length ? (
        <EmptyState
          title={`No mandi rates for ${scopeLabel} yet`}
          description="No market in this scope has filed a rate in the store yet. Rates appear as the daily AGMARKNET ingest runs — nothing is invented in the meantime."
          action={
            scope.district ? (
              <button
                type="button"
                onClick={() => pickScope({ state: scope.state, district: '' })}
                className="rounded-full border border-border px-4 py-2 text-[12.5px] font-600"
              >
                See all of {scope.state}
              </button>
            ) : undefined
          }
        />
      ) : !filtered.length ? (
        <EmptyState
          title={`No crop matches “${cropFilter || query}”`}
          description={`This mandi has not reported that crop. It reports ${commodities.length} crops — clear the filter to see them.`}
          action={
            <button
              type="button"
              onClick={() => {
                setQuery('');
                setCropFilter('');
              }}
              className="rounded-full border border-border px-4 py-2 text-[12.5px] font-600"
            >
              Clear filters
            </button>
          }
        />
      ) : !available.length && !refreshing ? (
        <EmptyState
          title={`No live rates for ${scopeLabel} right now`}
          description="The crops this market reports have no stored rate inside the freshness window. Run the daily ingest, or look at another district."
        />
      ) : (
        <>
          <div className={cn(grid ? 'grid gap-2 sm:grid-cols-2 xl:grid-cols-3' : 'space-y-2', 'stagger')}>
            {available.map((r) => (
              <PriceCard
                key={r.commodity}
                data={r.price}
                spark={r.spark}
                onClick={() => navigate(`/predict?crop=${encodeURIComponent(r.commodity)}`)}
              />
            ))}
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
            <Badge tone="gold">Monthly average</Badge>
            means a published district month average, not a single day's trade
            <Badge tone="info">MSP reference</Badge>
            is the government support price — not a mandi trade. A card marked
            "state-wide rate" is the latest real quote from another district in
            your state, with its district and date so it is never mistaken for a
            local price — pick a district and nothing outside it is shown.
          </div>
        </>
      )}
    </AppShell>
  );
};

export default MarketPricesPage;
