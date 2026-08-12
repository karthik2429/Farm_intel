import { formatPrice } from '@/lib/utils';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

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
    district: filters?.district || 'North Goa',
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
    district: filters?.district || 'North Goa',
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
  market: string
): Promise<PricePrediction & { 
  confidence: number;
  factors: { season: string; supply_pressure: string; weather_impact: string; festival_nearby: boolean };
}> {
  return fetchJson(`/predict/single?district=${encodeURIComponent(district)}&commodity=${encodeURIComponent(commodity)}&market=${encodeURIComponent(market)}`);
}

export async function getCommodities(): Promise<string[]> {
  const data = await fetchJson<CommodityList>('/commodities');
  return data.commodities;
}

export async function getMarkets(district?: string): Promise<Array<{ district: string; market: string }>> {
  const query = district ? `?district=${encodeURIComponent(district)}` : '';
  const data = await fetchJson<MarketList>(`/markets${query}`);
  return data.markets;
}

export { formatPrice };