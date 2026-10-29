// Mandi price client (Phase 1): the FastAPI backend is the single source of
// truth. It serves real AGMARKNET data via the SQLite price store
// (cache -> live probe -> MSP reference) and reports provenance
// (source, date, is_real, badge) so the UI can badge every price.
//
// The old direct api.data.gov.in path is gone: a relative `/api/gov/...`
// URL can never work without a dev proxy, and an exposed api key in
// client code is the wrong place to hold one. The backend already runs
// the live query server-side with the same data.

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";
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
    }, 120_000); // 2-minute cache window
  }
};

const _getMarketPrice = async (
  crop: string,
  cleanDistrict: string,
  state?: string
): Promise<MandiPrice | null> => {
  const params = new URLSearchParams({ commodity: crop });
  if (cleanDistrict) params.set("district", cleanDistrict);
  if (state) params.set("state", state);
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
    };
  }
  return null;
};

export const getMarketPrice = async (
  crop: string,
  district: string,
  state?: string
): Promise<MandiPrice | null> => {
  const cleanDistrict = normalizeDistrict(district);

  const key = `${crop}|${cleanDistrict}|${state || ""}`;
  if (cache.has(key)) return cache.get(key)!;

  // Coalesce identical parallel calls (crop lists fetch the same combos)
  const existing = inflight.get(key);
  if (existing) return existing;

  const p = _getMarketPrice(crop, cleanDistrict, state)
    .then((result) => {
      cacheSet(key, result);
      return result;
    })
    .catch(() => null)
    .finally(() => inflight.delete(key));
  inflight.set(key, p);
  return p;
};
