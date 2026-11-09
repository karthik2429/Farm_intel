import { formatPrice } from '@/lib/utils';

import { env } from '@/lib/env';

const API_BASE = env.apiBaseUrl;

export interface PricePrediction {
  district: string;
  commodity: string;
  market: string;
  current_price: number;
  predicted_price_14d: number;
  predicted_change_pct: number;
  prediction_date: string;
  model: string;
}

export interface TrajectoryResponse {
  district: string;
  commodity: string;
  market: string;
  current_price: number;
  trajectory: Array<{
    day: number;
    date: string;
    predicted_price: number;
    change_from_prev_pct?: number;
    change_from_initial_pct?: number;
  }>;
}

export type FactorDirection = 'up' | 'down' | 'neutral';
export type FactorStrength = 'high' | 'medium' | 'low';

export interface PriceFactorSignal {
  key: string;
  label: string;
  direction: FactorDirection;
  strength: FactorStrength;
  detail: string;
  festivals?: Array<{ name: string; date: string; days_until: number; approx: boolean }>;
}

export interface PriceFactorContext {
  commodity: string;
  district?: string | null;
  state?: string | null;
  as_of: string;
  tilt: 'firm' | 'soft' | 'balanced';
  up_count: number;
  down_count: number;
  signals: PriceFactorSignal[];
  shocks: string[];
  summary: string;
  season: { name: string; note: string; window: string | null };
  weather: {
    total_rain_7d_mm: number;
    max_day_rain_mm: number;
    max_3day_rain_mm: number;
    heavy_rain_days: number;
    heat_days: number;
    flood_risk: boolean;
  } | null;
  festivals: Array<{ name: string; date: string; days_until: number; approx: boolean }>;
  seasonality: {
    month: string;
    seasonal_index: number;
    delta_pct: number;
    observations: number;
    years: number;
    excluded_years?: number[];
    scope: string;
  } | null;
  supply: {
    change_pct: number;
    share_recent_pct: number;
    share_prior_pct: number;
    markets_recent: number;
    markets_prior: number;
    as_of: string;
    compared_with: string;
    scope: string;
  } | null;
  sources: string[];
  unavailable: string[];
  disclaimer: string;
}

export interface CommodityList {
  commodities: string[];
}

export interface MarketList {
  markets: Array<{ district: string; market: string }>;
}

async function fetchJson<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${endpoint}`, options);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(body || `API error: ${res.status}`);
  }
  return res.json();
}

export async function get14DayPredictions(filters?: {
  district?: string;
  commodity?: string;
  market?: string;
}): Promise<PricePrediction[]> {
  const body = {
    district: filters?.district || null,
    commodity: filters?.commodity || 'Banana',
    market: filters?.market || 'All',
  };

  const data = await fetchJson<PricePrediction | PricePrediction[]>('/predict/14day', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  return Array.isArray(data) ? data : [data];
}

export async function getTrajectory(filters?: {
  district?: string;
  commodity?: string;
  market?: string;
  days?: number;
}): Promise<TrajectoryResponse[]> {
  const body = {
    district: filters?.district || null,
    commodity: filters?.commodity || 'Banana',
    market: filters?.market || 'All',
  };

  const data = await fetchJson<TrajectoryResponse | TrajectoryResponse[]>('/predict/trajectory', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  return Array.isArray(data) ? data : [data];
}

export async function getSinglePrediction(
  district: string, 
  commodity: string, 
  market: string): Promise<PricePrediction & {
  confidence: number;
  factors: {
    season: string;
    supply_pressure: string;
    weather_impact: string;
    festival_nearby: boolean;
    /** Full season/weather/flood/festival/supply analysis. */
    context?: PriceFactorContext;
  };
}> {
  return fetchJson(`/predict/single?district=${encodeURIComponent(district)}&commodity=${encodeURIComponent(commodity)}&market=${encodeURIComponent(market)}`);
}

export async function getPriceFactors(params: {
  commodity: string;
  district?: string | null;
  state?: string | null;
}): Promise<PriceFactorContext> {
  const q = new URLSearchParams({ commodity: params.commodity });
  if (params.district) q.set('district', params.district);
  if (params.state) q.set('state', params.state);
  return fetchJson<PriceFactorContext>(`/predict/factors?${q.toString()}`);
}

export async function getCommodities(): Promise<string[]> {
  const data = await fetchJson<CommodityList>('/commodities');
  return data.commodities;
}

export interface ScopedCommodityList {
  /** crops this market reported first, then the rest of the state */
  commodities: string[];
  /** the subset the district itself reported */
  district_commodities?: string[];
  /** district, or state when the district has filed nothing yet */
  scope: 'district' | 'state' | 'all';
  district?: string | null;
  state?: string | null;
  /** true when the district list came (at least partly) from the live feed */
  live?: boolean;
  /** true when the live feed was unreachable and the last snapshot answered */
  cached?: boolean;
  /** newest trading day the live district feed returned */
  latest_date?: string | null;
  /** mandis that report in this district */
  markets?: string[];
}

/** Crop catalogue for one market (Market page). Unscoped = everything.
 *
 * `strict` keeps the answer inside one district: the live feed is asked for
 * that district's whole crop list and nothing from a neighbouring district is
 * mixed in. */
export async function getScopedCommodities(params: {
  district?: string;
  state?: string;
  /** keep only crops with enough history to forecast */
  predictable?: boolean;
  /** list only this district's own crops */
  strict?: boolean;
  /** ask the live feed again instead of the backend's short-lived snapshot */
  refresh?: boolean;
}): Promise<ScopedCommodityList> {
  const q = new URLSearchParams();
  if (params.district) q.set('district', params.district);
  if (params.state) q.set('state', params.state);
  if (params.predictable) q.set('predictable', '1');
  if (params.strict) q.set('strict', '1');
  if (params.refresh) q.set('refresh', '1');
  return fetchJson<ScopedCommodityList>(`/commodities?${q.toString()}`);
}

export async function getMarkets(
  district?: string,
  state?: string,
): Promise<Array<{ district: string; market: string }>> {
  const q = new URLSearchParams();
  if (district) q.set('district', district);
  if (state) q.set('state', state);
  // The endpoint refreshes the district from the live feed, so the list is
  // every mandi trading there rather than only the ones already ingested.
  const data = await fetchJson<MarketList>(`/markets?${q.toString()}`);
  return data.markets;
}

export { formatPrice };