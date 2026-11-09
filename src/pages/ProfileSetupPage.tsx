import * as React from 'react';
import { useNavigate } from 'react-router-dom';
import { Check, ChevronLeft, ChevronRight, LocateFixed, MapPin, Sprout, User } from 'lucide-react';
import { toast } from 'sonner';
import { useLanguage } from '@/contexts/LanguageContext';
import { useAuth } from '@/contexts/AuthContext';
import { languageNames, type Language } from '@/lib/i18n';
import { allStates, getDistricts } from '@/lib/indian-locations';
import { env } from '@/lib/env';
import { emptyProfile, saveProfile, readCachedProfile, type Profile } from '@/lib/profile';
import { Button, Input, OptionCard, Select } from '@/components/ui-kit/form';
import { Card, Chip } from '@/components/ui-kit/core';
import { cn } from '@/lib/utils';

/**
 * Onboarding.
 *
 * Four one-question steps that write a single Profile document. The same code
 * path serves both modes: with Supabase keys the profile is upserted to the
 * `profiles` table, and without them it is stored on the device. Nothing here
 * requires a login — a farmer who skips sign-in still gets district-accurate
 * prices instead of the old dead-end "no location" state.
 */

const STEPS = ['You', 'Language', 'Location', 'Crops'] as const;

const SEASONS = [
  { value: 'kharif', label: 'Kharif', hint: 'Jun – Oct' },
  { value: 'rabi', label: 'Rabi', hint: 'Oct – Mar' },
  { value: 'zaid', label: 'Zaid', hint: 'Mar – Jun' },
];

const IRRIGATION = ['Rain-fed', 'Canal', 'Borewell', 'Drip', 'Sprinkler'];

/** Common crops offered as quick picks; free text is still allowed. */
const CROP_CHOICES = [
  'Rice', 'Wheat', 'Maize', 'Ragi', 'Jowar', 'Bajra', 'Cotton', 'Sugarcane',
  'Soybean', 'Groundnut', 'Chickpea', 'Turmeric', 'Onion', 'Tomato', 'Potato',
  'Chilli', 'Banana', 'Mango', 'Coconut', 'Coffee',
];

const ProfileSetupPage: React.FC = () => {
  const { t, setLanguage } = useLanguage();
  const { user } = useAuth();
  const navigate = useNavigate();

  const [step, setStep] = React.useState(0);
  const [saving, setSaving] = React.useState(false);
  const [detecting, setDetecting] = React.useState(false);

  const [profile, setProfile] = React.useState<Profile>(() => {
    const cached = readCachedProfile();
    return {
      ...emptyProfile,
      ...(cached || {}),
      name: cached?.name || user?.user_metadata?.full_name || user?.user_metadata?.name || '',
      email: cached?.email || user?.email || '',
    };
  });

  // Mark the first-run gate as satisfied as soon as onboarding is shown, so
  // "Skip" is honoured and the redirect can never loop.
  React.useEffect(() => {
    localStorage.setItem('agrosmart.onboarding_seen', '1');
  }, []);

  const patch = (next: Partial<Profile>) => setProfile((p) => ({ ...p, ...next }));

  const districts = React.useMemo(() => getDistricts(profile.state), [profile.state]);

  /**
   * Reverse-geocode to state + district using the configured endpoint
   * (BigDataCloud by default — no key needed). Falls back to a clear toast so
   * the farmer can pick manually; it never guesses a location.
   */
  const detectLocation = () => {
    if (!navigator.geolocation) {
      toast.error('This browser cannot share a location — pick your district instead');
      return;
    }
    setDetecting(true);
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const { latitude, longitude } = pos.coords;
        patch({ lat: latitude, lng: longitude });
        try {
          const url = `${env.reverseGeocodeUrl}?latitude=${latitude}&longitude=${longitude}&localityLanguage=en`;
          const res = await fetch(url);
          const data = await res.json();
          const candidates: string[] = [
            data?.principalSubdivision,
            ...(Array.isArray(data?.localityInfo?.administrative)
              ? data.localityInfo.administrative.map((a: { name?: string }) => a?.name)
              : []),
            data?.city,
            data?.locality,
          ].filter(Boolean);

          const matchedState = allStates.find((s) =>
            candidates.some((c) => c?.toLowerCase() === s.toLowerCase()),
          );
          if (!matchedState) {
            toast.info('Got your coordinates — please choose your state below');
            setDetecting(false);
            return;
          }
          const stateDistricts = getDistricts(matchedState);
          const matchedDistrict = stateDistricts.find((d) =>
            candidates.some((c) => c?.toLowerCase() === d.toLowerCase()),
          );
          patch({ state: matchedState, district: matchedDistrict || '' });
          toast.success(
            matchedDistrict ? `Located: ${matchedDistrict}, ${matchedState}` : `Located: ${matchedState}`,
          );
        } catch {
          toast.info('Got your coordinates — please choose your district below');
        } finally {
          setDetecting(false);
        }
      },
      () => {
        setDetecting(false);
        toast.error('Location permission denied — choose your district instead');
      },
      { enableHighAccuracy: true, timeout: 10000 },
    );
  };

  const canContinue = () => {
    if (step === 0) return profile.name.trim().length > 0;
    if (step === 2) return Boolean(profile.state && profile.district);
    return true;
  };

  const finish = async () => {
    setSaving(true);
    const final: Profile = {
      ...profile,
      id: profile.id || user?.id,
      email: profile.email || user?.email,
      onboarding_complete: true,
    };
    const res = await saveProfile(final);
    setLanguage(final.language); // keep the UI and the saved profile in sync
    setSaving(false);

    if (!res.ok) {
      toast.error(`Could not save to your account: ${res.error || 'unknown error'}. Kept on this device.`);
    } else if (res.storage === 'local') {
      toast.success('Profile saved on this device');
    } else {
      toast.success('Profile saved to your account');
    }
    navigate('/home', { replace: true });
  };

  const next = () => {
    if (!canContinue()) {
      if (step === 2) toast.error('Choose your state and district so prices match your mandi');
      else toast.error('Please enter your name');
      return;
    }
    if (step === STEPS.length - 1) void finish();
    else setStep((s) => Math.min(STEPS.length - 1, s + 1));
  };

  return (
    <div className="min-h-dvh bg-bg">
      {/* Progress */}
      <header className="sticky top-0 z-20 border-b border-border bg-bg/85 backdrop-blur-xl">
        <div className="mx-auto flex w-full max-w-2xl items-center gap-3 px-4 py-3">
          {step > 0 ? (
            <button
              type="button"
              onClick={() => setStep((s) => Math.max(0, s - 1))}
              className="press grid h-10 w-10 place-items-center rounded-full border border-border bg-surface text-ink"
              aria-label="Back"
            >
              <ChevronLeft className="h-5 w-5" strokeWidth={2} />
            </button>
          ) : (
            <span className="h-10 w-10" />
          )}
          <div className="flex-1">
            <div className="flex items-center justify-between text-[11px] font-700 uppercase tracking-[0.08em] text-ink-muted">
              <span>
                Step {step + 1} of {STEPS.length}
              </span>
              <span>{STEPS[step]}</span>
            </div>
            <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-surface-2">
              <div
                className="h-full rounded-full transition-all duration-300 ease-out"
                style={{
                  width: `${((step + 1) / STEPS.length) * 100}%`,
                  background: 'var(--grad-leaf)',
                }}
              />
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-2xl px-4 pb-32 pt-6">
        {step === 0 && (
          <section className="animate-fade-up space-y-5">
            <div>
              <h1 className="font-display text-[26px] font-800 leading-tight text-ink">
                {t('namaste')} 🙏
              </h1>
              <p className="mt-1 text-[14px] text-ink-muted">
                Two minutes now means every price you see is from your own mandi.
              </p>
            </div>
            <Input
              label={t('yourName')}
              icon={<User className="h-4 w-4" strokeWidth={1.9} />}
              value={profile.name}
              onChange={(e) => patch({ name: e.target.value })}
              placeholder="e.g. Ramesh Gowda"
              maxLength={80}
              autoFocus
            />
            <Input
              label="Email (optional)"
              icon={<MapPin className="h-4 w-4" strokeWidth={1.9} />}
              value={profile.email || ''}
              onChange={(e) => patch({ email: e.target.value })}
              placeholder="you@example.com"
              inputMode="email"
              helper={
                user
                  ? 'Taken from your sign-in account.'
                  : 'Only used to sync across devices once you sign in.'
              }
              disabled={Boolean(user?.email)}
            />
            <Card variant="flat" className="bg-surface-2">
              <p className="text-[12.5px] leading-relaxed text-ink-muted">
                {user
                  ? 'Your profile will be saved to your account.'
                  : 'You are not signed in, so this profile stays on this device. You can sign in later from Profile.'}
              </p>
            </Card>
          </section>
        )}

        {step === 1 && (
          <section className="animate-fade-up space-y-4">
            <div>
              <h1 className="font-display text-[26px] font-800 leading-tight text-ink">
                {t('preferredLanguage')}
              </h1>
              <p className="mt-1 text-[14px] text-ink-muted">
                Applies to the whole app and the assistant immediately.
              </p>
            </div>
            <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3">
              {(Object.keys(languageNames) as Language[]).map((lang) => {
                const active = profile.language === lang;
                return (
                  <button
                    key={lang}
                    type="button"
                    onClick={() => {
                      patch({ language: lang });
                      setLanguage(lang); // apply immediately, no reload
                    }}
                    aria-pressed={active}
                    className={cn(
                      'press flex h-[62px] items-center justify-between rounded-sm border px-3 text-left transition-all',
                      active
                        ? 'border-primary bg-primary/10 ring-1 ring-primary/30'
                        : 'border-border bg-surface hover:bg-surface-2',
                    )}
                  >
                    <span className="font-display text-[16px] font-700 text-ink">
                      {languageNames[lang]}
                    </span>
                    {active && <Check className="h-4 w-4 text-primary" strokeWidth={2.6} />}
                  </button>
                );
              })}
            </div>
          </section>
        )}

        {step === 2 && (
          <section className="animate-fade-up space-y-4">
            <div>
              <h1 className="font-display text-[26px] font-800 leading-tight text-ink">
                {t('location')}
              </h1>
              <p className="mt-1 text-[14px] text-ink-muted">
                We use this to show your district mandi prices and local weather.
              </p>
            </div>

            <Button
              variant="secondary"
              block
              loading={detecting}
              onClick={detectLocation}
              className="justify-center"
            >
              {!detecting && <LocateFixed className="h-4 w-4 text-primary" strokeWidth={2} />}
              {detecting ? 'Detecting…' : 'Auto-detect my location'}
            </Button>

            <Select
              label="State"
              placeholder="Choose a state"
              value={profile.state}
              onChange={(v) => patch({ state: v, district: '' })}
              options={allStates.map((s) => ({ value: s, label: s }))}
              icon={<MapPin className="h-4 w-4" strokeWidth={1.9} />}
            />

            <Select
              label="District"
              placeholder={profile.state ? 'Choose a district' : 'Choose a state first'}
              value={profile.district}
              onChange={(v) => patch({ district: v })}
              options={districts.map((d) => ({ value: d, label: d }))}
              disabled={!profile.state}
              helper={
                districts.length
                  ? `${districts.length} districts in ${profile.state}`
                  : undefined
              }
            />

            {profile.lat != null && (
              <p className="flex items-center gap-1.5 text-[11.5px] text-ink-muted">
                <MapPin className="h-3.5 w-3.5" strokeWidth={2} />
                {profile.lat.toFixed(3)}, {profile.lng?.toFixed(3)} — used for weather
              </p>
            )}
          </section>
        )}

        {step === 3 && (
          <section className="animate-fade-up space-y-5">
            <div>
              <h1 className="font-display text-[26px] font-800 leading-tight text-ink">
                {t('whatDoYouGrow')}
              </h1>
              <p className="mt-1 text-[14px] text-ink-muted">
                Pick the crops you grow. You can change these any time.
              </p>
            </div>

            <div className="flex flex-wrap gap-2">
              {CROP_CHOICES.map((crop) => {
                const active = profile.crops.includes(crop);
                return (
                  <Chip
                    key={crop}
                    active={active}
                    onClick={() =>
                      patch({
                        crops: active
                          ? profile.crops.filter((c) => c !== crop)
                          : [...profile.crops, crop],
                      })
                    }
                  >
                    {crop}
                  </Chip>
                );
              })}
            </div>

            <div className="space-y-2.5">
              <p className="text-[11px] font-700 uppercase tracking-[0.08em] text-ink-muted">
                Season focus
              </p>
              <div className="grid grid-cols-3 gap-2">
                {SEASONS.map((s) => (
                  <OptionCard
                    key={s.value}
                    title={s.label}
                    subtitle={s.hint}
                    selected={profile.season_focus === s.value}
                    onClick={() => patch({ season_focus: s.value })}
                  />
                ))}
              </div>
            </div>

            <Select
              label="Irrigation"
              placeholder="Select irrigation type"
              value={profile.irrigation || ''}
              onChange={(v) => patch({ irrigation: v })}
              options={IRRIGATION.map((i) => ({ value: i, label: i }))}
              icon={<Sprout className="h-4 w-4" strokeWidth={1.9} />}
            />

            <Input
              label="Land size"
              unit={profile.land_unit === 'hectare' ? 'ha' : 'acres'}
              value={profile.land_size ?? ''}
              onChange={(e) =>
                patch({ land_size: e.target.value ? Number(e.target.value) : null })
              }
              inputMode="decimal"
              placeholder="e.g. 2.5"
              helper="Used to size fertiliser doses."
            />
          </section>
        )}
      </main>

      {/* Sticky actions */}
      <footer className="fixed inset-x-0 bottom-0 z-20 border-t border-border bg-surface/90 px-4 pb-[calc(12px+env(safe-area-inset-bottom))] pt-3 backdrop-blur-xl">
        <div className="mx-auto flex w-full max-w-2xl items-center gap-3">
          <Button
            variant="secondary"
            onClick={() => navigate('/home')}
            className="shrink-0"
            type="button"
          >
            Skip
          </Button>
          <Button block loading={saving} onClick={next} type="button">
            {step === STEPS.length - 1 ? 'Finish setup' : 'Continue'}
            {step < STEPS.length - 1 && <ChevronRight className="h-4 w-4" strokeWidth={2.4} />}
          </Button>
        </div>
      </footer>
    </div>
  );
};

export default ProfileSetupPage;
