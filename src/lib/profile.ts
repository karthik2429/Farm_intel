/**
 * Farmer profile.
 *
 * Source of truth is Supabase (`profiles` + `user_crops`), with localStorage
 * used only as an offline/first-paint cache. When Supabase is not configured
 * the app still works: it reads and writes the local cache and reports
 * `storage: 'local'` so the UI can say the profile is device-only instead of
 * pretending it was saved to an account.
 */
import { useCallback, useEffect, useState } from 'react';
import { supabase, supabaseConfigured } from '@/integrations/supabase/client';
import type { Language } from '@/lib/i18n';

const CACHE_KEY = 'farmintel_profile';
const LOCAL_KEY = 'agrosmart.profile.local';

export interface SoilCard {
  n?: number | null;
  p?: number | null;
  k?: number | null;
  ph?: number | null;
  ec?: number | null;
  oc?: number | null;
  file_url?: string | null;
  test_date?: string | null;
}

export interface Profile {
  id?: string;
  name: string;
  email?: string;
  phone?: string;
  language: Language;
  state: string;
  district: string;
  village?: string;
  lat?: number | null;
  lng?: number | null;
  land_size?: number | null;
  land_unit?: string;
  irrigation?: string;
  farming_type?: string;
  season_focus?: string;
  crops: string[];
  onboarding_complete: boolean;
  soil?: SoilCard | null;
  storage?: 'supabase' | 'local';
}

export const emptyProfile: Profile = {
  name: '',
  language: 'en',
  state: '',
  district: '',
  crops: [],
  onboarding_complete: false,
  soil: null,
};

/** Read the cache (used for first paint and for dev without Supabase). */
export function readCachedProfile(): Profile | null {
  const raw = localStorage.getItem(CACHE_KEY) || localStorage.getItem(LOCAL_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    return { ...emptyProfile, ...parsed, crops: parsed.crops || [] };
  } catch {
    return null;
  }
}

export function cacheProfile(p: Profile) {
  localStorage.setItem(CACHE_KEY, JSON.stringify(p));
  // keep the older key in sync for components that still read it
  localStorage.setItem(LOCAL_KEY, JSON.stringify(p));
  if (p.name) localStorage.setItem('profile_name', p.name);
  if (p.state) localStorage.setItem('profile_state', p.state);
  if (p.district) localStorage.setItem('profile_district', p.district);
}

export async function fetchProfile(userId: string): Promise<Profile | null> {
  if (!supabase) return readCachedProfile();
  const { data, error } = await supabase
    .from('profiles')
    .select('*')
    .eq('id', userId)
    .maybeSingle();
  if (error) {
    // Table missing (migrations not run) is not a crash: fall back to cache.
    return readCachedProfile();
  }
  if (!data) return null;

  const { data: cropRows } = await supabase
    .from('user_crops')
    .select('crop')
    .eq('user_id', userId);

  const { data: soil } = await supabase
    .from('soil_health_cards')
    .select('*')
    .eq('user_id', userId)
    .order('test_date', { ascending: false })
    .limit(1)
    .maybeSingle();

  const profile: Profile = {
    ...emptyProfile,
    ...(data as Record<string, unknown>),
    language: ((data as { language?: Language }).language || 'en') as Language,
    crops: (cropRows || []).map((r: { crop: string }) => r.crop),
    soil: (soil as SoilCard) || null,
    storage: 'supabase',
  } as Profile;
  cacheProfile(profile);
  return profile;
}

export async function saveProfile(profile: Profile): Promise<{ ok: boolean; storage: 'supabase' | 'local'; error?: string }> {
  cacheProfile(profile);
  if (!supabase || !profile.id) {
    return { ok: true, storage: 'local' };
  }
  const { crops, soil, storage, ...row } = profile;
  const { error } = await supabase.from('profiles').upsert(
    { ...row, id: profile.id, updated_at: new Date().toISOString() },
    { onConflict: 'id' },
  );
  if (error) return { ok: false, storage: 'local', error: error.message };

  if (crops?.length) {
    await supabase.from('user_crops').delete().eq('user_id', profile.id);
    await supabase.from('user_crops').insert(
      crops.map((crop) => ({ user_id: profile.id!, crop })),
    );
  }
  return { ok: true, storage: 'supabase' };
}

/**
 * Profile hook: cached value first, then the authoritative row.
 * Never throws when Supabase is missing or the table is not migrated yet.
 */
export function useProfile(userId?: string | null, userEmail?: string | null) {
  const [profile, setProfile] = useState<Profile | null>(() => readCachedProfile());
  const [loading, setLoading] = useState(Boolean(userId));

  useEffect(() => {
    let alive = true;
    if (!userId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    fetchProfile(userId)
      .then((p) => {
        if (!alive) return;
        setProfile(p || (readCachedProfile() ? { ...readCachedProfile()!, id: userId, email: userEmail || undefined } : { ...emptyProfile, id: userId, email: userEmail || undefined }));
      })
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [userId, userEmail]);

  const save = useCallback(
    async (next: Profile) => {
      const withId = { ...next, id: next.id || userId || undefined, email: next.email || userEmail || undefined };
      const res = await saveProfile(withId);
      if (res.ok) setProfile(withId);
      return res;
    },
    [userId, userEmail],
  );

  return { profile, loading, save, setProfile, supabaseEnabled: supabaseConfigured };
}

/** Convenience: the district to default every price screen to. */
export function defaultLocation(p: Profile | null) {
  return {
    state: p?.state || '',
    district: p?.district || '',
    lat: p?.lat ?? null,
    lon: p?.lng ?? null,
    label: [p?.district, p?.state].filter(Boolean).join(', '),
  };
}
