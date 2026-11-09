/**
 * Loose-but-explicit shapes for the ML endpoints.
 *
 * These replace `any` in the legacy pages: request payloads are free-form
 * dictionaries, response items are typed on the fields the UI actually reads
 * (and still allowed to carry extra keys the backend adds later).
 */

export type RequestPayload = Record<string, unknown>;

export interface RotationSuggestion {
  crop?: string;
  season?: string;
  confidence?: number;
  score?: number;
  N_gap?: number;
  P_gap?: number;
  K_gap?: number;
  rationale?: string;
  fertiliser_topup?: { N?: number; P?: number; K?: number };
  [key: string]: unknown;
}

export interface RotationResult {
  season1_crop?: string;
  depleted_soil?: Record<string, number>;
  warnings?: string[];
  top_suggestions?: RotationSuggestion[];
  [key: string]: unknown;
}

export interface FertilizerMatch {
  Fertilizer?: string;
  Similarity?: number;
  Notes?: string;
  [key: string]: unknown;
}

export interface FertilizerResult {
  top_matches?: FertilizerMatch[];
  recommendation?: string;
  [key: string]: unknown;
}

export interface CropEntry {
  name?: string;
  crop?: string;
  score?: number;
  confidence?: number;
  display_score?: number;
  mandiPrice?: number | null;
  mandiMin?: number | null;
  mandiMax?: number | null;
  /** provenance of the figure shown on the detail card */
  mandiBadge?: string | null;
  mandiIsReal?: boolean | null;
  mandiMarket?: string | null;
  mandiScope?: string | null;
  /** Evidence behind the rank, straight from the advisor. */
  ml_prob?: number | null;
  soil_fit?: number | null;
  climate_fit?: number | null;
  hist_score?: number | null;
  /** Share of the district's cropped area this crop already holds. */
  region_share?: number | null;
  market_score?: number | null;
  market_price?: number | null;
  market_price_source?: string | null;
  market_price_date?: string | null;
  market_price_scope?: string | null;
  market_price_badge?: string | null;
  price_market?: string | null;
  price_district?: string | null;
  yield_t_ha?: [number, number] | null;
  /** yield (t/ha) × 10 × ₹/quintal — revenue before input costs. */
  gross_return_per_ha?: number | null;
  [key: string]: unknown;
}

export interface PredictResponse {
  crop?: string;
  confidence?: number;
  alternatives?: { crop: string; confidence: number }[];
  [key: string]: unknown;
}
