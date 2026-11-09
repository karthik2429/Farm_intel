import * as React from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowRight,
  BadgeCheck,
  CheckCircle2,
  Loader2,
  Lock,
  Mail,
  Sparkles,
  TrendingUp,
} from 'lucide-react';
import { toast } from 'sonner';
import { supabase } from '@/integrations/supabase/client';
import { useAuth } from '@/contexts/AuthContext';
import { useLanguage } from '@/contexts/LanguageContext';
import { LanguageSwitcher } from '@/components/LanguageSwitcher';
import { ThemeToggle } from '@/components/ThemeProvider';
import { env, supabaseConfigured } from '@/lib/env';
import { readCachedProfile } from '@/lib/profile';
import { cn } from '@/lib/utils';
import farmHero from '@/assets/hero-farm.jpg';

type Tab = 'login' | 'signup';

const LoginPage: React.FC = () => {
  const { t } = useLanguage();
  const { user, loading: authLoading } = useAuth();
  const navigate = useNavigate();

  const [tab, setTab] = React.useState<Tab>('login');
  const [email, setEmail] = React.useState('');
  const [otp, setOtp] = React.useState(['', '', '', '', '', '']);
  const [step, setStep] = React.useState<'email' | 'code'>('email');
  const [busy, setBusy] = React.useState(false);
  const [resendIn, setResendIn] = React.useState(0);
  const [attempts, setAttempts] = React.useState(0);
  const inputs = React.useRef<(HTMLInputElement | null)[]>([]);

  // Already signed in → straight to the app (or onboarding when incomplete).
  React.useEffect(() => {
    if (authLoading || !user) return;
    const cached = readCachedProfile();
    navigate(cached?.onboarding_complete ? '/home' : '/onboarding', { replace: true });
  }, [user, authLoading, navigate]);

  React.useEffect(() => {
    if (resendIn <= 0) return;
    const id = setTimeout(() => setResendIn((s) => s - 1), 1000);
    return () => clearTimeout(id);
  }, [resendIn]);

  const emailValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());

  const sendCode = async () => {
    if (!supabaseConfigured || !supabase) {
      toast.error('Sign-in is not configured: set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY.');
      return;
    }
    if (!emailValid) {
      toast.error('Enter a valid email address');
      return;
    }
    setBusy(true);
    try {
      const { error } = await supabase.auth.signInWithOtp({
        email: email.trim(),
        options: { shouldCreateUser: true },
      });
      if (error) {
        toast.error(error.message || 'Could not send the code');
        return;
      }
      setStep('code');
      setResendIn(30);
      setAttempts(0);
      toast.success('Code sent — check your inbox');
      setTimeout(() => inputs.current[0]?.focus(), 80);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Network error while sending the code');
    } finally {
      setBusy(false);
    }
  };

  const verify = async (code: string) => {
    if (!supabase) return;
    if (code.length !== 6) {
      toast.error('Enter all 6 digits');
      return;
    }
    if (attempts >= 5) {
      toast.error('Too many attempts. Request a new code.');
      return;
    }
    setBusy(true);
    try {
      const { error } = await supabase.auth.verifyOtp({ email: email.trim(), token: code, type: 'email' });
      if (error) {
        setAttempts((a) => a + 1);
        toast.error(error.message || 'Invalid or expired code');
        setOtp(['', '', '', '', '', '']);
        inputs.current[0]?.focus();
        return;
      }
      const cached = readCachedProfile();
      navigate(cached?.onboarding_complete ? '/home' : '/onboarding', { replace: true });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Verification failed');
    } finally {
      setBusy(false);
    }
  };

  const google = async () => {
    if (!supabaseConfigured || !supabase) {
      toast.error('Google sign-in is not configured: set the Supabase URL and anon key.');
      return;
    }
    if (!env.enableGoogleLogin) {
      toast.error('Google sign-in is disabled in this build');
      return;
    }
    const { error } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: { redirectTo: `${window.location.origin}/home` },
    });
    if (error) toast.error(error.message || 'Google sign-in is not enabled in Supabase yet');
  };

  const setDigit = (i: number, value: string) => {
    const digits = value.replace(/\D/g, '');
    if (!digits) {
      const next = [...otp];
      next[i] = '';
      setOtp(next);
      return;
    }
    const next = [...otp];
    digits.split('').forEach((d, k) => {
      if (i + k < 6) next[i + k] = d;
    });
    setOtp(next);
    const target = Math.min(5, i + digits.length);
    inputs.current[target]?.focus();
    const joined = next.join('');
    if (joined.length === 6) void verify(joined);
  };

  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      {/* ---------------------------------------------------------- visual */}
      <div className="relative hidden overflow-hidden lg:block">
        <img src={farmHero} alt="" className="absolute inset-0 h-full w-full object-cover" />
        <div
          className="absolute inset-0"
          style={{
            background:
              'linear-gradient(160deg, rgba(11,61,46,0.92) 0%, rgba(11,61,46,0.62) 45%, rgba(20,118,74,0.55) 100%)',
          }}
        />
        <div className="relative flex h-full flex-col justify-between p-10 text-white">
          <div className="flex items-center gap-2.5">
            <span className="grid h-10 w-10 place-items-center rounded-sm bg-white/15 backdrop-blur">
              <Sparkles className="h-5 w-5" strokeWidth={2} />
            </span>
            <div>
              <p className="font-display text-[17px] font-800 leading-tight">FarmIntel</p>
              <p className="text-[11px] uppercase tracking-[0.16em] text-white/70">Kisan intelligence</p>
            </div>
          </div>

          <div className="max-w-md">
            <h1 className="font-display text-[34px] font-800 leading-[1.15] tracking-tight">
              Smarter farming,
              <br />
              better prices.
            </h1>
            <p className="mt-3 text-[14px] leading-relaxed text-white/80">
              Real AGMARKNET mandi rates, 14-day price forecasts and crop advice
              for your own soil and district — in your language.
            </p>

            <div className="mt-8 grid grid-cols-2 gap-3">
              <GlassStat icon={<TrendingUp className="h-4 w-4" />} label="Mandi records" value="36,480" />
              <GlassStat icon={<BadgeCheck className="h-4 w-4" />} label="Forecast model" value="Holt-Winters" />
            </div>
          </div>

          <p className="text-[11px] text-white/60">
            Prices come from data.gov.in (AGMARKNET). No made-up numbers: if a
            district has no real rate, the app says so.
          </p>
        </div>
      </div>

      {/* ------------------------------------------------------------ form */}
      <div className="relative flex min-h-screen flex-col bg-background">
        <div className="flex items-center justify-between px-4 pt-4 sm:px-6">
          <div className="flex items-center gap-2 lg:hidden">
            <span className="grid h-8 w-8 place-items-center rounded-sm bg-hero text-white">
              <Sparkles className="h-4 w-4" strokeWidth={2} />
            </span>
            <span className="font-display text-[15px] font-800">FarmIntel</span>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <LanguageSwitcher compact />
            <ThemeToggle />
          </div>
        </div>

        <div className="flex flex-1 items-center justify-center px-4 py-6 sm:px-8">
          <div className="w-full max-w-[400px] animate-fade-up">
            <div className="mb-5 lg:hidden">
              <h1 className="font-display text-[26px] font-800 leading-tight tracking-tight">
                Smarter farming,
                <br />
                better prices.
              </h1>
              <p className="mt-1.5 text-[13px] text-ink-muted">
                Real mandi prices and forecasts, in your language.
              </p>
            </div>

            <div className="rounded-lg border border-border bg-surface p-5 shadow-md sm:p-6">
              <div className="mb-5">
                <h2 className="font-display text-[21px] font-800 tracking-tight">
                  {tab === 'login' ? t('logIn') : t('createAccount')}
                </h2>
                <p className="mt-0.5 text-[12.5px] text-ink-muted">
                  {tab === 'login'
                    ? 'Use Google or a one-time email code. No password.'
                    : 'Takes 10 seconds — Google or email, no password.'}
                </p>
              </div>

              {/* tabs */}
              <div className="mb-5 grid grid-cols-2 rounded-full border border-border bg-surface-2 p-1">
                {(['login', 'signup'] as Tab[]).map((v) => (
                  <button
                    key={v}
                    type="button"
                    onClick={() => {
                      setTab(v);
                      setStep('email');
                    }}
                    className={cn(
                      'h-8 rounded-full text-[12.5px] font-600 transition-all',
                      tab === v ? 'bg-surface text-ink shadow-sm' : 'text-ink-muted',
                    )}
                  >
                    {v === 'login' ? t('logIn') : t('createAccount')}
                  </button>
                ))}
              </div>

              {!supabaseConfigured && (
                <div className="mb-4 rounded-sm border border-harvest/40 bg-harvest/10 p-3">
                  <p className="text-[12px] font-700 text-ink">Sign-in is not configured yet</p>
                  <p className="mt-1 text-[11.5px] leading-relaxed text-ink-muted">
                    Add <code className="rounded bg-surface-2 px-1">VITE_SUPABASE_URL</code> and{' '}
                    <code className="rounded bg-surface-2 px-1">VITE_SUPABASE_ANON_KEY</code> to{' '}
                    <code className="rounded bg-surface-2 px-1">.env.local</code>. You can still
                    browse the app and the setup panel explains what each key unlocks.
                  </p>
                  <button
                    type="button"
                    onClick={() => navigate('/onboarding')}
                    className="mt-2 text-[11.5px] font-700 text-primary hover:underline"
                  >
                    Continue without an account →
                  </button>
                </div>
              )}

              <button
                type="button"
                onClick={google}
                className="press flex h-12 w-full items-center justify-center gap-2.5 rounded-sm border border-border bg-surface text-[14px] font-600 shadow-sm hover:bg-surface-2"
              >
                <GoogleMark />
                {t('googleAccount')}
              </button>

              <div className="my-4 flex items-center gap-3">
                <span className="h-px flex-1 bg-border" />
                <span className="text-[10.5px] font-600 uppercase tracking-[0.1em] text-ink-muted">
                  {t('orContinueWith')}
                </span>
                <span className="h-px flex-1 bg-border" />
              </div>

              {step === 'email' ? (
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    void sendCode();
                  }}
                  className="space-y-3"
                >
                  <label className="block">
                    <span className="mb-1 block text-[11px] font-600 uppercase tracking-[0.07em] text-ink-muted">
                      {t('email')}
                    </span>
                    <div className="flex h-[52px] items-center gap-2 rounded-sm border border-border bg-surface-2 px-3 focus-within:border-primary focus-within:ring-2 focus-within:ring-primary/20">
                      <Mail className="h-4 w-4 text-ink-muted" strokeWidth={1.9} />
                      <input
                        type="email"
                        inputMode="email"
                        autoComplete="email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        placeholder={t('enterEmail')}
                        className="h-full w-full bg-transparent text-[15px] outline-none placeholder:text-ink-muted/60"
                      />
                    </div>
                  </label>

                  <button
                    type="submit"
                    disabled={busy || !emailValid}
                    className="press flex h-12 w-full items-center justify-center gap-2 rounded-sm bg-leaf text-[14.5px] font-700 text-white shadow-glow disabled:opacity-50"
                    style={{ background: 'var(--grad-leaf)' }}
                  >
                    {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                    {busy ? 'Sending…' : t('sendOtp')}
                    {!busy && <ArrowRight className="h-4 w-4" strokeWidth={2.2} />}
                  </button>
                  <p className="flex items-center justify-center gap-1.5 text-[11px] text-ink-muted">
                    <Lock className="h-3 w-3" strokeWidth={2} />
                    Passwordless. Only {env.enableEmailOtp ? 'email' : 'Google'} sign-in is enabled.
                  </p>
                </form>
              ) : (
                <div className="space-y-3">
                  <p className="text-[12.5px] text-ink-muted">
                    {t('enterEmailOtp')} sent to <span className="font-600 text-ink">{email}</span>
                  </p>
                  <div className="flex justify-between gap-1.5">
                    {otp.map((d, i) => (
                      <input
                        key={i}
                        ref={(el) => {
                          inputs.current[i] = el;
                        }}
                        value={d}
                        inputMode="numeric"
                        autoComplete="one-time-code"
                        maxLength={6}
                        aria-label={`Digit ${i + 1}`}
                        onChange={(e) => setDigit(i, e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Backspace' && !otp[i] && i > 0) inputs.current[i - 1]?.focus();
                        }}
                        className="h-14 w-full rounded-sm border border-border bg-surface-2 text-center font-display text-[20px] font-800 tnum outline-none transition-all focus:border-primary focus:ring-2 focus:ring-primary/20"
                      />
                    ))}
                  </div>

                  <button
                    type="button"
                    onClick={() => void verify(otp.join(''))}
                    disabled={busy || otp.join('').length !== 6}
                    className="press flex h-12 w-full items-center justify-center gap-2 rounded-sm text-[14.5px] font-700 text-white shadow-glow disabled:opacity-50"
                    style={{ background: 'var(--grad-leaf)' }}
                  >
                    {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" strokeWidth={2.2} />}
                    {t('verifyOtp')}
                  </button>

                  <div className="flex items-center justify-between text-[11.5px]">
                    <button
                      type="button"
                      disabled={resendIn > 0}
                      onClick={() => void sendCode()}
                      className="font-600 text-primary disabled:text-ink-muted"
                    >
                      {resendIn > 0 ? `${t('resendIn')} ${resendIn}s` : t('resend')}
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setStep('email');
                        setOtp(['', '', '', '', '', '']);
                      }}
                      className="font-600 text-ink-muted hover:text-ink"
                    >
                      {t('changeEmail')}
                    </button>
                  </div>
                </div>
              )}
            </div>

            <p className="mt-4 text-center text-[11px] leading-relaxed text-ink-muted">
              {t('termsText')}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

function GlassStat({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="rounded-md border border-white/15 bg-white/10 p-3 backdrop-blur-md">
      <span className="flex items-center gap-1.5 text-white/70">{icon}</span>
      <p className="mt-1.5 font-display text-[15px] font-800">{value}</p>
      <p className="text-[10.5px] uppercase tracking-wide text-white/60">{label}</p>
    </div>
  );
}

function GoogleMark() {
  return (
    <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden>
      <path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9 3.6l6.7-6.7C35.6 2.5 30.2 0 24 0 14.6 0 6.5 5.4 2.6 13.2l7.8 6c1.9-5.6 7.1-9.7 13.6-9.7Z" />
      <path fill="#4285F4" d="M46.1 24.5c0-1.6-.1-3.2-.4-4.7H24v9h12.4c-.6 3-2.2 5.5-4.7 7.2l7.6 5.9c4.4-4.1 6.8-10.1 6.8-17.4Z" />
      <path fill="#FBBC05" d="M10.4 28.8a14.6 14.6 0 0 1 0-9.6l-7.8-6a24 24 0 0 0 0 21.6l7.8-6Z" />
      <path fill="#34A853" d="M24 48c6.5 0 11.9-2.1 15.9-5.8l-7.6-5.9c-2.1 1.4-4.8 2.3-8.3 2.3-6.5 0-11.7-4.1-13.6-9.8l-7.8 6C6.5 42.6 14.6 48 24 48Z" />
    </svg>
  );
}

export default LoginPage;
