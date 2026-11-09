// Mandi price client (Phase 1): the FastAPI backend is the single source of
// truth. It serves real AGMARKNET data via the SQLite price store
// (cache -> live probe -> MSP reference) and reports provenance
// (source, date, is_real, badge) so the UI can badge every price.
//
// The old direct api.data.gov.in path is gone: a relative `/api/gov/...`
// URL can never work without a dev proxy, and an exposed api key in
// client code is the wrong place to hold one. The backend already runs
// the live query server-side with the same data.

import { env } from "@/lib/env";

const API_BASE = env.apiBaseUrl;
const BACKEND_PRICE_URL = `${API_BASE}/market/price`;

// District-name normalization (frontend names -> AGMARKNET spellings when
// the backend hasn't already handled it).
const districtMap: Record<string, string> = {
  belgaum: "Belagavi",
  bangalore: "Bengaluru Urban",
  bengaluru: "Bengaluru Urban",
  mysore: "Mysuru",
  tumkur: "Tumakuru",
  bellary: "Ballari",
  gulbarga: "Kalaburagi",
  bijapur: "Vijayapura",
  allahabad: "Prayagraj",
};

const normalizeDistrict = (district: string) => {
  if (!district) return "";
  const first = district.split(",")[0].trim();
  return districtMap[first.toLowerCase()] || first;
};

// Small helper: fetch JSON with a hard timeout; never throws
const fetchJson = async (url: string, ms: number, init?: RequestInit) => {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), ms);
  try {
    const res = await fetch(url, { ...init, signal: ctrl.signal });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
};

export interface MandiPrice {
  modal: number | null;
  min: number | null;
  max: number | null;
  market: string;
  date?: string;
  source?: string;
  /** true only for a real observed mandi transaction */
  is_real?: boolean;
  /** "cached" | "live" | "msp" | "unavailable" — drives the UI badge */
  badge?: string;
  /** human-readable detail when no price is available */
  detail?: string;
  /**
   * District the backend actually resolved the row from. The backend widens
   * the search district -> state -> India, so this can differ from the
   * requested district and the UI must say so instead of implying otherwise.
   */
  resolvedDistrict?: string | null;
  resolvedState?: string | null;
  /**
   * How wide the backend had to search: "district" | "state" | "india" |
   * "msp". A scoped request never widens past its own state.
   */
  scope?: string | null;
  /** Days since the quote was published (0 = today). A mandi does not trade
   *  every crop daily, so an older quote is still the latest real rate. */
  daysOld?: number | null;
  isToday?: boolean;
}

// ---------------- tiny response cache (dedupes parallel calls) ------------
const cache = new Map<string, MandiPrice | null>();
const inflight = new Map<string, Promise<MandiPrice | null>>();
let cacheTimer: ReturnType<typeof setTimeout> | null = null;
const cacheSet = (key: string, val: MandiPrice | null) => {
  cache.set(key, val);
  if (!cacheTimer) {
    cacheTimer = setTimeout(() => {
      cache.clear();
      cacheTimer = null;
    }, 60_000); // one trading day's quotes; keep the window short
  }
};

/** Drop every memoised quote so the next read asks the backend again
 *  (the Market page's Refresh button, and switching market scope). */
export const clearMarketCache = () => {
  cache.clear();
  inflight.clear();
  if (cacheTimer) {
    clearTimeout(cacheTimer);
    cacheTimer = null;
  }
};

const _getMarketPrice = async (
  crop: string,
  cleanDistrict: string,
  state?: string,
  strict = false,
): Promise<MandiPrice | null> => {
  const params = new URLSearchParams({ commodity: crop });
  if (cleanDistrict) params.set("district", cleanDistrict);
  if (state) params.set("state", state);
  // strict = this district only. The Market page lists one district's crops
  // and mandis, so a rate borrowed from a neighbouring district would be a
  // different market's price shown under this district's name.
  if (strict) params.set("strict", "1");
  const backend = await fetchJson(`${BACKEND_PRICE_URL}?${params}`, 8000);
  if (backend?.price) {
    return {
      modal: backend.price,
      min: backend.min_price ?? null,
      max: backend.max_price ?? null,
      market: backend.market || "",
      date: backend.date,
      source: backend.source,
      is_real: backend.is_real !== false,
      badge: backend.badge,
      detail: backend.detail,
      resolvedDistrict: backend.district ?? null,
      resolvedState: backend.state ?? null,
      scope: backend.scope ?? null,
      daysOld: backend.days_old ?? null,
      isToday: backend.is_today ?? null,
    };
  }
  if (backend && backend.source === "unavailable") {
    // Backend answered definitively: no real mandi data and no MSP —
    // surface that honestly instead of a fabricated number.
    return {
      modal: null,
      min: null,
      max: null,
      market: backend.market || "",
      source: "unavailable",
      is_real: false,
      badge: "unavailable",
      detail: backend.detail,
      resolvedDistrict: backend.district ?? null,
      resolvedState: backend.state ?? null,
      scope: backend.scope ?? null,
    };
  }
  return null;
};

export const getMarketPrice = async (
  crop: string,
  district: string,
  state?: string,
  opts?: { strict?: boolean; fresh?: boolean },
): Promise<MandiPrice | null> => {
  const cleanDistrict = normalizeDistrict(district);
  const strict = Boolean(opts?.strict && cleanDistrict);

  const key = `${crop}|${cleanDistrict}|${state || ""}|${strict ? "d" : "w"}`;
  if (opts?.fresh) cache.delete(key);
  if (cache.has(key)) return cache.get(key)!;

  // Coalesce identical parallel calls (crop lists fetch the same combos)
  const existing = inflight.get(key);
  if (existing) return existing;

  const p = _getMarketPrice(crop, cleanDistrict, state, strict)
    .then((result) => {
      cacheSet(key, result);
      return result;
    })
    .catch(() => null)
    .finally(() => inflight.delete(key));
  inflight.set(key, p);
  return p;
};

export interface HistoryPoint {
  date: string;
  price: number;
}
export interface MarketHistory {
  commodity: string;
  district: string | null;
  days: number;
  /** how far the scope drill-down went to find real history */
  scope: "district" | "state" | "india";
  points: HistoryPoint[];
  note?: string;
}

export interface CropInfo {
  requested: string;
  canonical?: string;
  /** true when neither the master dataset nor the reference table has it */
  unavailable?: boolean;
  family?: string | null;
  season?: string | null;
  soil_type?: string | null;
  ph_range?: string | null;
  temp_range_c?: string | null;
  rainfall_range_mm?: string | null;
  ideal_npk?: { N: number | null; P: number | null; K: number | null } | null;
  duration_days?: [number, number] | null;
  yield_t_ha?: [number, number] | null;
  water_needs?: string | null;
  perennial?: boolean;
  maturity_note?: string | null;
}

/** Real daily mandi history for a trend chart (empty points = no real data).
 *  The backend resolves AGMARKNET commodity aliases itself. */
export const getMarketHistory = (
  commodity: string,
  district?: string,
  days = 90,
  state?: string,
): Promise<MarketHistory | null> => {
  const params = new URLSearchParams({
    commodity,
    days: String(days),
  });
  if (district) params.set("district", normalizeDistrict(district));
  if (state) params.set("state", state);
  return fetchJson(`${API_BASE}/market/history?${params}`, 10000);
};

/** Agronomy metadata (duration/yield/soil/...). null on any failure. */
export const getCropInfo = (
  crops: string[],
): Promise<{ crops: Record<string, CropInfo> } | null> =>
  fetchJson(`${API_BASE}/crop/info?crops=${encodeURIComponent(crops.join(","))}`, 10000);

/** Current weather for the dashboard card. null on any failure. */
export const getWeather = (loc: {
  district?: string;
  state?: string;
  lat?: number;
  lon?: number;
}): Promise<{
  district: string | null;
  state: string | null;
  temperature: number;
  humidity: number;
  rainfall: number;
  source: string;
} | null> => {
  const params = new URLSearchParams();
  if (loc.lat != null) { params.set("lat", String(loc.lat)); params.set("lon", String(loc.lon)); }
  if (loc.district) params.set("district", loc.district);
  if (loc.state) params.set("state", loc.state);
  return fetchJson(`${API_BASE}/weather?${params}`, 10000);
};

/** AI assistant: real replies from the backend (server-side key).
 *  Throws an Error with the backend's detail so the UI can show it honestly. */
export const getAiReply = async (
  messages: Array<{ role: 'user' | 'assistant'; content: string }>,
  district?: string,
  state?: string,
): Promise<{ reply: string }> => {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 60000);

  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      messages,
      district: district || null,
      state: state || null,
    }),
    signal: ctrl.signal,
  }).finally(() => clearTimeout(timer));

  if (!res.ok) {
    let detail = `AI request failed (${res.status})`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* non-JSON body */
    }
    throw new Error(detail);
  }
  return (await res.json()) as { reply: string };
};
