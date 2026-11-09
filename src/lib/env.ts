/**
 * Single typed configuration module for the frontend (Phase 0).
 *
 * Every environment read in the app goes through here. No component touches
 * `import.meta.env` directly, and no URL or key is hardcoded anywhere else.
 *
 * Only VITE_ values are available to the browser (they are public and ship
 * inside the bundle). Never put a secret in this file or in `.env.local`.
 */

const raw = import.meta.env as Record<string, unknown>;

const str = (value: unknown, fallback = ''): string => {
  const v = typeof value === 'string' ? value.trim() : '';
  return v || fallback;
};

const flag = (value: unknown, fallback: boolean): boolean => {
  const v = str(value).toLowerCase();
  if (!v) return fallback;
  return v === '1' || v === 'true' || v === 'yes' || v === 'on';
};

export type SpeechProvider = 'browser' | 'bhashini' | 'sarvam';

export type LanguageCode =
  | 'en'
  | 'hi'
  | 'kn'
  | 'te'
  | 'ta'
  | 'ml'
  | 'mr'
  | 'gu'
  | 'bn'
  | 'pa'
  | 'or';

const LANGUAGES: LanguageCode[] = [
  'en', 'hi', 'kn', 'te', 'ta', 'ml', 'mr', 'gu', 'bn', 'pa', 'or',
];

const asLanguage = (value: unknown, fallback: LanguageCode = 'en'): LanguageCode => {
  const v = str(value).toLowerCase().split('-')[0] as LanguageCode;
  return LANGUAGES.includes(v) ? v : fallback;
};

const asSpeechProvider = (value: unknown): SpeechProvider => {
  const v = str(value, 'browser').toLowerCase();
  return v === 'bhashini' || v === 'sarvam' ? v : 'browser';
};

export const env = {
  /** FastAPI origin, e.g. http://127.0.0.1:8000 */
  apiBaseUrl: str(raw.VITE_API_BASE_URL, 'http://127.0.0.1:8000').replace(/\/$/, ''),
  supabaseUrl: str(raw.VITE_SUPABASE_URL),
  // Supabase renamed the browser key to "publishable key" (sb_publishable_…).
  // Accept either name so an existing .env keeps working.
  supabaseAnonKey: str(raw.VITE_SUPABASE_ANON_KEY) || str(raw.VITE_SUPABASE_PUBLISHABLE_KEY),
  enableGoogleLogin: flag(raw.VITE_ENABLE_GOOGLE_LOGIN, true),
  enableEmailOtp: flag(raw.VITE_ENABLE_EMAIL_OTP, true),
  speechProvider: asSpeechProvider(raw.VITE_SPEECH_PROVIDER),
  defaultLanguage: asLanguage(raw.VITE_DEFAULT_LANGUAGE),
  reverseGeocodeUrl: str(
    raw.VITE_REVERSE_GEOCODE_URL,
    'https://api.bigdatacloud.net/data/reverse-geocode-client',
  ),
  mapTileUrl: str(
    raw.VITE_MAP_TILE_URL,
    'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
  ),
  isDev: Boolean(raw.DEV),
  mode: str(raw.MODE, 'development'),
} as const;

/** True when Supabase auth can work at all. */
export const supabaseConfigured = Boolean(env.supabaseUrl && env.supabaseAnonKey);

/** True when the FastAPI backend origin is known (always, it has a default). */
export const backendConfigured = Boolean(env.apiBaseUrl);

export interface SetupItem {
  key: string;
  label: string;
  what: string;
  signup: string;
  done: boolean;
}

/**
 * Human-readable setup checklist for the dev-only "Setup status" panel.
 * Only public facts are derived here; secrets live on the backend and are
 * reported by GET /config/status.
 */
export const frontendSetupChecklist: SetupItem[] = [
  {
    key: 'VITE_API_BASE_URL',
    label: 'Backend URL',
    what: 'FastAPI origin used by every data call',
    signup: '',
    done: backendConfigured,
  },
  {
    key: 'VITE_SUPABASE_URL',
    label: 'Supabase project URL',
    what: 'Sign-in, saved profile and chat history',
    signup: 'https://supabase.com/dashboard',
    done: Boolean(env.supabaseUrl),
  },
  {
    key: 'VITE_SUPABASE_ANON_KEY',
    label: 'Supabase anon key',
    what: 'Public client key (safe to ship, RLS protects rows)',
    signup: 'https://supabase.com/dashboard/project/_/settings/api',
    done: Boolean(env.supabaseAnonKey),
  },
];

export default env;
