import { env } from "@/lib/env";

const BACKEND = env.apiBaseUrl;

// Abort a hanging request instead of freezing the UI forever
const withTimeout = (ms: number) => {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), ms);
  return { signal: ctrl.signal, done: () => clearTimeout(timer) };
};

export const getCropRecommendations = async (payload: any) => {
  // Forward ALL location context so the backend can resolve the district
  // (real soil NPK + district cropping pattern + season) on its own.
  const t1 = withTimeout(20000);
  try {
    const res = await fetch(`${BACKEND}/predict`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        N: payload.N ?? null,
        P: payload.P ?? null,
        K: payload.K ?? null,
        ph: payload.ph ?? null,
        rainfall: payload.rainfall ?? null,
        temperature: payload.temperature ?? null,
        humidity: payload.humidity ?? null,
        district: payload.district ?? null,
        state: payload.state ?? null,
        season: payload.season ?? "kharif",
        lat: payload.lat ?? null,
        lon: payload.lon ?? null,
        mode: payload.mode ?? "auto",
      }),
      signal: t1.signal,
    });
    if (!res.ok) {
      console.error("Predict API HTTP error:", res.status);
      return null;
    }
    return await res.json();
  } catch (err) {
    console.error("API Error:", err);
    return null;
  } finally {
    t1.done();
  }
};

export const getRotationSuggestions = async (payload: {
  prev_crop: string;
  N: number;
  P: number;
  K: number;
  top_n?: number;
}) => {
  const t = withTimeout(15000);
  try {
    const res = await fetch(`${BACKEND}/rotation/suggestions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
      signal: t.signal,
    });

    return await res.json();
  } catch (err) {
    console.error("Rotation API Error:", err);
    return null;
  } finally {
    t.done();
  }
};

export const getRotationPlan = async (payload: {
  season1_crop: string;
  N?: number;
  P?: number;
  K?: number;
  ph?: number;
  lat?: number;
  lon?: number;
  district?: string;
  state?: string;
  mode?: "auto" | "coords";
  top_n?: number;
}) => {
  const t = withTimeout(20000);
  try {
    const res = await fetch(`${BACKEND}/rotation/plan`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
      signal: t.signal,
    });

    return await res.json();
  } catch (err) {
    console.error("Rotation Plan API Error:", err);
    return null;
  } finally {
    t.done();
  }
};

export const getFertilizerRecommendation = async (payload: {
  crop: string;
  soil: string;
  N?: number;
  P?: number;
  K?: number;
  PH?: number;
  lat?: number;
  lon?: number;
  district?: string;
  state?: string;
  mode?: "auto" | "coords";
  top_k?: number;
}) => {
  const t = withTimeout(15000);
  try {
    const res = await fetch(`${BACKEND}/fertilizer/recommend`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
      signal: t.signal,
    });

    return await res.json();
  } catch (err) {
    console.error("Fertilizer API Error:", err);
    return null;
  } finally {
    t.done();
  }
};

export const getDefaultNPK = async (payload: {
  district?: string;
  state?: string;
  lat?: number;
  lon?: number;
  mode?: "auto" | "coords";
}) => {
  const t = withTimeout(15000);
  try {
    const res = await fetch(`${BACKEND}/location/default-npk`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
      signal: t.signal,
    });

    return await res.json();
  } catch (err) {
    console.error("Default NPK API Error:", err);
    return null;
  } finally {
    t.done();
  }
};