import * as React from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Check,
  CloudOff,
  Globe,
  LogOut,
  MapPin,
  ShieldCheck,
  Sprout,
  Trash2,
  User,
} from 'lucide-react';
import { toast } from 'sonner';
import { AppShell } from '@/components/ui-kit/AppShell';
import { Avatar, Card, CardLabel, Chip, ProgressRing } from '@/components/ui-kit/core';
import { Button, Input, Select } from '@/components/ui-kit/form';
import { ThemeToggle } from '@/components/ThemeProvider';
import { useAuth } from '@/contexts/AuthContext';
import { useLanguage } from '@/contexts/LanguageContext';
import { languageNames, type Language } from '@/lib/i18n';
import { allStates, getDistricts } from '@/lib/indian-locations';
import { useProfile, type Profile } from '@/lib/profile';
import { supabase } from '@/integrations/supabase/client';
import { cn } from '@/lib/utils';

const CROP_CHOICES = [
  'Rice', 'Wheat', 'Maize', 'Ragi', 'Jowar', 'Bajra', 'Cotton', 'Sugarcane',
  'Soybean', 'Groundnut', 'Chickpea', 'Turmeric', 'Onion', 'Tomato', 'Potato',
  'Chilli', 'Banana', 'Mango', 'Coconut', 'Coffee',
];

const SEASONS = ['kharif', 'rabi', 'zaid'];

/**
 * Profile.
 *
 * Everything here writes through `useProfile`, the same store the price screens
 * read, so editing a district immediately changes which mandi prices appear.
 * With Supabase keys the row is synced; without them it stays on the device and
 * the page says so instead of pretending it was saved to an account.
 */
const FarmerProfilePage: React.FC = () => {
  const { t, language, setLanguage } = useLanguage();
  const { user, signOut, configured } = useAuth();
  const navigate = useNavigate();
  const { profile, loading, save, supabaseEnabled } = useProfile(user?.id, user?.email);

  const [draft, setDraft] = React.useState<Profile | null>(null);
  const [saving, setSaving] = React.useState(false);

  React.useEffect(() => {
    if (profile) setDraft(profile);
  }, [profile]);

  const dirty = React.useMemo(
    () => Boolean(draft && profile && JSON.stringify(draft) !== JSON.stringify(profile)),
    [draft, profile],
  );

  const patch = (next: Partial<Profile>) => setDraft((d) => (d ? { ...d, ...next } : d));

  const districts = React.useMemo(() => getDistricts(draft?.state || ''), [draft?.state]);

  const completeness = React.useMemo(() => {
    const checks = [
      Boolean(draft?.name),
      Boolean(draft?.state && draft?.district),
      Boolean(draft?.crops?.length),
      Boolean(draft?.season_focus),
      Boolean(draft?.land_size),
      Boolean(draft?.soil),
    ];
    return Math.round((checks.filter(Boolean).length / checks.length) * 100);
  }, [draft]);

  const saveAll = async () => {
    if (!draft) return;
    setSaving(true);
    const res = await save({ ...draft, onboarding_complete: true });
    setSaving(false);
    if (!res.ok) {
      toast.error(`Saved on this device — account sync failed: ${res.error || 'unknown'}`);
    } else {
      toast.success(res.storage === 'supabase' ? 'Profile saved' : 'Saved on this device');
    }
    if (draft.language !== language) setLanguage(draft.language);
  };

  const changeLanguage = (lang: Language) => {
    patch({ language: lang });
    setLanguage(lang); // apply immediately, everywhere
  };

  const logout = async () => {
    await signOut();
    navigate('/', { replace: true });
  };

  const deleteAccount = async () => {
    if (!supabase || !user) return;
    const ok = window.confirm(
      'Delete your account and all saved data? This cannot be undone.\n\n' +
        'If your Supabase project restricts self-deletion, remove the user from the dashboard instead.',
    );
    if (!ok) return;
    const { error } = await supabase.from('profiles').delete().eq('id', user.id);
    if (error) {
      toast.error(`Could not delete: ${error.message}`);
      return;
    }
    await supabase.auth.signOut();
    localStorage.clear();
    navigate('/', { replace: true });
  };

  if (loading && !draft) {
    return (
      <AppShell>
        <div className="mx-auto w-full max-w-3xl animate-pulse space-y-3 px-4 py-6">
          <div className="h-28 rounded-md bg-surface-2" />
          <div className="h-40 rounded-md bg-surface-2" />
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div className="mx-auto w-full max-w-3xl px-4 pb-24 pt-4 md:px-6">
        {/* Header */}
        <div
          className="hero-gradient grain relative overflow-hidden rounded-md px-5 py-6 text-white shadow-lg"
          style={{ borderRadius: 'var(--r-lg)' }}
        >
          <div className="relative flex items-center gap-4">
            <Avatar name={draft?.name || 'Farmer'} size={64} />
            <div className="min-w-0 flex-1">
              <h1 className="truncate font-display text-[22px] font-800 leading-tight">
                {draft?.name || 'Your name'}
              </h1>
              <p className="mt-0.5 flex items-center gap-1.5 text-[12.5px] text-white/80">
                <MapPin className="h-3.5 w-3.5" strokeWidth={2} />
                {draft?.district && draft?.state
                  ? `${draft.district}, ${draft.state}`
                  : 'No district set yet'}
              </p>
              {draft?.email && (
                <p className="mt-0.5 truncate text-[11.5px] text-white/60">{draft.email}</p>
              )}
            </div>
            <ProgressRing value={completeness} size={54} stroke={5} label={`${completeness}%`} />
          </div>
        </div>

        {!supabaseEnabled && (
          <Card variant="flat" className="mt-4 flex items-start gap-3 bg-surface-2">
            <CloudOff className="mt-0.5 h-4 w-4 shrink-0 text-ink-muted" strokeWidth={2} />
            <p className="text-[12.5px] leading-relaxed text-ink-muted">
              <span className="font-700 text-ink">Device-only profile.</span> Supabase keys are not
              configured, so this profile is stored in this browser. Add{' '}
              <code className="rounded bg-surface px-1">VITE_SUPABASE_URL</code> and{' '}
              <code className="rounded bg-surface px-1">VITE_SUPABASE_ANON_KEY</code> to sync it.
            </p>
          </Card>
        )}

        <div className="mt-5 space-y-4">
          {/* Farm details */}
          <Card>
            <CardLabel>Farmer details</CardLabel>
            <div className="mt-3 space-y-3">
              <Input
                label={t('yourName')}
                icon={<User className="h-4 w-4" strokeWidth={1.9} />}
                value={draft?.name || ''}
                onChange={(e) => patch({ name: e.target.value })}
                placeholder="Your name"
              />
              <div className="grid gap-3 sm:grid-cols-2">
                <Select
                  label="State"
                  placeholder="Choose a state"
                  value={draft?.state || ''}
                  onChange={(v) => patch({ state: v, district: '' })}
                  options={allStates.map((s) => ({ value: s, label: s }))}
                />
                <Select
                  label="District"
                  placeholder={draft?.state ? 'Choose a district' : 'Choose a state first'}
                  value={draft?.district || ''}
                  onChange={(v) => patch({ district: v })}
                  options={districts.map((d) => ({ value: d, label: d }))}
                  disabled={!draft?.state}
                />
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <Input
                  label="Land size"
                  unit="acres"
                  inputMode="decimal"
                  placeholder="e.g. 2.5"
                  value={draft?.land_size ?? ''}
                  onChange={(e) =>
                    patch({ land_size: e.target.value ? Number(e.target.value) : null })
                  }
                />
                <Select
                  label="Season focus"
                  value={draft?.season_focus || ''}
                  onChange={(v) => patch({ season_focus: v })}
                  options={SEASONS.map((s) => ({
                    value: s,
                    label: s.charAt(0).toUpperCase() + s.slice(1),
                  }))}
                />
              </div>
            </div>
          </Card>

          {/* Crops */}
          <Card>
            <CardLabel>My crops</CardLabel>
            <p className="mt-1 text-[12px] text-ink-muted">
              These appear first on Home, Market and Predict.
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {CROP_CHOICES.map((crop) => {
                const active = draft?.crops?.includes(crop) ?? false;
                return (
                  <Chip
                    key={crop}
                    active={active}
                    onClick={() =>
                      patch({
                        crops: active
                          ? (draft?.crops || []).filter((c) => c !== crop)
                          : [...(draft?.crops || []), crop],
                      })
                    }
                  >
                    {crop}
                  </Chip>
                );
              })}
            </div>
          </Card>

          {/* Soil card */}
          <Card>
            <CardLabel>Soil health card</CardLabel>
            {draft?.soil ? (
              <div className="mt-3 grid grid-cols-3 gap-2 sm:grid-cols-6">
                {(
                  [
                    ['N', draft.soil.n],
                    ['P', draft.soil.p],
                    ['K', draft.soil.k],
                    ['pH', draft.soil.ph],
                    ['EC', draft.soil.ec],
                    ['OC', draft.soil.oc],
                  ] as const
                ).map(([label, value]) => (
                  <div key={label} className="rounded-sm bg-surface-2 px-2 py-2 text-center">
                    <p className="text-[10px] font-700 uppercase tracking-wide text-ink-muted">
                      {label}
                    </p>
                    <p className="font-display text-[15px] font-800 tabular-nums text-ink">
                      {value ?? '--'}
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="mt-2 text-[12.5px] text-ink-muted">
                No soil card saved. Crop, rotation and fertiliser advice fall back to district soil
                estimates and label them as estimates.
              </p>
            )}
          </Card>

          {/* Language */}
          <Card>
            <CardLabel>{t('preferredLanguage')}</CardLabel>
            <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
              {(Object.keys(languageNames) as Language[]).map((lang) => {
                const active = (draft?.language || language) === lang;
                return (
                  <button
                    key={lang}
                    type="button"
                    onClick={() => changeLanguage(lang)}
                    aria-pressed={active}
                    className={cn(
                      'press flex h-11 items-center justify-between rounded-sm border px-3 text-left transition-all',
                      active
                        ? 'border-primary bg-primary/10'
                        : 'border-border bg-surface hover:bg-surface-2',
                    )}
                  >
                    <span className="font-display text-[14px] font-700 text-ink">
                      {languageNames[lang]}
                    </span>
                    {active && <Check className="h-3.5 w-3.5 text-primary" strokeWidth={3} />}
                  </button>
                );
              })}
            </div>
          </Card>

          {/* Appearance */}
          <Card className="flex items-center justify-between gap-3">
            <div>
              <CardLabel>Appearance</CardLabel>
              <p className="mt-1 text-[12px] text-ink-muted">System default, or pick one.</p>
            </div>
            <ThemeToggle />
          </Card>

          {/* Account */}
          <Card>
            <CardLabel>Account</CardLabel>
            {configured && user ? (
              <div className="mt-3 space-y-2">
                <div className="flex items-center gap-2 text-[12.5px] text-ink-muted">
                  <ShieldCheck className="h-4 w-4 text-primary" strokeWidth={2} />
                  Signed in as <span className="font-600 text-ink">{user.email}</span>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button variant="secondary" onClick={() => void logout()}>
                    <LogOut className="h-4 w-4" strokeWidth={2} />
                    {t('logout')}
                  </Button>
                  <Button
                    variant="ghost"
                    className="text-destructive"
                    onClick={() => void deleteAccount()}
                  >
                    <Trash2 className="h-4 w-4" strokeWidth={2} />
                    Delete my account and data
                  </Button>
                </div>
              </div>
            ) : (
              <div className="mt-2 space-y-2">
                <p className="text-[12.5px] text-ink-muted">
                  Not signed in. Sign in to sync this profile, your soil card and chat history
                  across devices.
                </p>
                <div className="flex flex-wrap gap-2">
                  <Button variant="secondary" onClick={() => navigate('/')}>
                    <Globe className="h-4 w-4" strokeWidth={2} />
                    Sign in
                  </Button>
                  <Button variant="ghost" onClick={() => navigate('/onboarding')}>
                    <Sprout className="h-4 w-4" strokeWidth={2} />
                    Redo onboarding
                  </Button>
                </div>
              </div>
            )}
          </Card>
        </div>
      </div>

      {/* Save bar */}
      {dirty && (
        // Sits clear of the floating assistant button (56px + gutter) so a tap
        // on Save can never land on the chat FAB instead.
        <div className="fixed inset-x-0 bottom-[calc(72px+env(safe-area-inset-bottom))] z-50 px-4 md:bottom-4 md:left-auto md:right-24 md:w-80">
          <div className="mx-auto flex max-w-3xl items-center gap-3 rounded-md border border-border bg-surface/95 p-2.5 shadow-lg backdrop-blur-xl">
            <p className="flex-1 pl-1 text-[12.5px] font-600 text-ink">Unsaved changes</p>
            <Button size="sm" variant="ghost" onClick={() => setDraft(profile)}>
              Reset
            </Button>
            <Button size="sm" loading={saving} onClick={() => void saveAll()}>
              Save
            </Button>
          </div>
        </div>
      )}
    </AppShell>
  );
};

export default FarmerProfilePage;
