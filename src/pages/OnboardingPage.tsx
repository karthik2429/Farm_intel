import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLanguage } from '@/contexts/LanguageContext';
import { useAuth } from '@/contexts/AuthContext';
import { supabase } from '@/integrations/supabase/client';
import { lovable } from '@/integrations/lovable/index';
import { ChevronRight, Loader2, Mail, Phone } from 'lucide-react';
import { toast } from 'sonner';
import heroFarm from '@/assets/hero-farm.jpg';

type AuthMode = 'login' | 'signup';
type AuthMethod = 'email' | 'phone';

const OnboardingPage: React.FC = () => {
  const { t } = useLanguage();
  const { user } = useAuth();
  const navigate = useNavigate();

  const [mode, setMode] = useState<AuthMode>('login');
  const [method, setMethod] = useState<AuthMethod>('email');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [otp, setOtp] = useState('');
  const [otpSent, setOtpSent] = useState(false);
  const [loading, setLoading] = useState(false);

  React.useEffect(() => {
    if (user) navigate('/home', { replace: true });
  }, [user, navigate]);

  // Fake OTP - no real backend verification
  const handleSendEmailOtp = async () => {
    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      toast.error('Please enter a valid email address');
      return;
    }
    setLoading(true);
    await new Promise((r) => setTimeout(r, 800));
    setOtpSent(true);
    toast.success('OTP sent to your email! (Enter any 6 digits)');
    setLoading(false);
  };

  const handleVerifyEmailOtp = async () => {
    if (otp.length < 6) {
      toast.error('Please enter the 6-digit OTP');
      return;
    }
    setLoading(true);
    await new Promise((r) => setTimeout(r, 600));
    toast.success(mode === 'signup' ? 'Account created!' : 'Logged in!');
    setLoading(false);
    navigate(mode === 'signup' ? '/setup' : '/home');
  };

  const handleSendPhoneOtp = async () => {
    const cleaned = phone.replace(/\s/g, '');
    if (cleaned.length < 10) {
      toast.error('Please enter a valid 10-digit phone number');
      return;
    }
    setLoading(true);
    await new Promise((r) => setTimeout(r, 800));
    setOtpSent(true);
    toast.success('OTP sent to your phone! (Enter any 6 digits)');
    setLoading(false);
  };

  const handleVerifyPhoneOtp = async () => {
    if (otp.length < 6) {
      toast.error('Please enter the 6-digit OTP');
      return;
    }
    setLoading(true);
    await new Promise((r) => setTimeout(r, 600));
    toast.success(mode === 'signup' ? 'Account created!' : 'Logged in!');
    setLoading(false);
    navigate(mode === 'signup' ? '/setup' : '/home');
  };



  const handleGoogleLogin = async () => {
    setLoading(true);
    const result = await lovable.auth.signInWithOAuth("google", {
      redirect_uri: window.location.origin,
    });
    if (result.error) {
      toast.error(String(result.error) || 'Google sign-in failed');
      setLoading(false);
    }
    if (result.redirected) return;
    navigate('/setup');
    setLoading(false);
  };

  const resetOtpState = () => {
    setOtp('');
    setOtpSent(false);
  };

  const switchMode = (newMode: AuthMode) => {
    setMode(newMode);
    resetOtpState();
  };

  const switchMethod = (newMethod: AuthMethod) => {
    setMethod(newMethod);
    resetOtpState();
  };

  const handleSendOtp = method === 'email' ? handleSendEmailOtp : handleSendPhoneOtp;
  const handleVerifyOtp = method === 'email' ? handleVerifyEmailOtp : handleVerifyPhoneOtp;

  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* Hero */}
      <div className="relative h-48 overflow-hidden">
        <img src={heroFarm} alt="Farm" className="w-full h-full object-cover" width={800} height={600} />
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-background/50 to-background" />
        <div className="absolute bottom-4 left-4">
          <span className="px-3 py-1 text-xs font-bold rounded-full gradient-primary text-primary-foreground">
            🌾 {t('empoweringFarmers')}
          </span>
        </div>
      </div>

      <div className="flex-1 px-5 pt-4 pb-8 flex flex-col">
        <h1 className="text-2xl font-extrabold text-foreground">{t('appName')}</h1>
        <p className="text-xs text-muted-foreground mt-1 leading-relaxed">{t('onboardingSubtitle')}</p>

        {/* Login / Signup Toggle */}
        <div className="flex mt-4 bg-secondary rounded-lg p-1">
          <button
            onClick={() => switchMode('login')}
            className={`flex-1 py-2 text-sm font-semibold rounded-md transition-all ${
              mode === 'login'
                ? 'gradient-primary text-primary-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            {t('signIn')}
          </button>
          <button
            onClick={() => switchMode('signup')}
            className={`flex-1 py-2 text-sm font-semibold rounded-md transition-all ${
              mode === 'signup'
                ? 'gradient-primary text-primary-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            {t('createAccount')}
          </button>
        </div>

        <div className="glass-card p-5 mt-4 space-y-4">
          <h2 className="text-lg font-bold text-foreground">
            {mode === 'login' ? t('welcomeBack') : t('createNewAccount')}
          </h2>

          {/* Email / Phone method toggle */}
          <div className="flex gap-2">
            <button
              onClick={() => switchMethod('email')}
              className={`flex-1 flex items-center justify-center gap-2 py-2 rounded-lg text-xs font-semibold transition-all border ${
                method === 'email'
                  ? 'border-primary bg-primary/10 text-primary'
                  : 'border-border bg-secondary text-muted-foreground hover:text-foreground'
              }`}
            >
              <Mail className="w-3.5 h-3.5" />
              {t('email')}
            </button>
            <button
              onClick={() => switchMethod('phone')}
              className={`flex-1 flex items-center justify-center gap-2 py-2 rounded-lg text-xs font-semibold transition-all border ${
                method === 'phone'
                  ? 'border-primary bg-primary/10 text-primary'
                  : 'border-border bg-secondary text-muted-foreground hover:text-foreground'
              }`}
            >
              <Phone className="w-3.5 h-3.5" />
              {t('phoneNumber')}
            </button>
          </div>

          {/* Email input */}
          {method === 'email' && (
            <div className="bg-secondary rounded-lg px-3 py-2.5">
              <input
                type="email"
                placeholder={t('enterEmail')}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground"
                disabled={otpSent}
              />
            </div>
          )}

          {/* Phone input */}
          {method === 'phone' && (
            <div className="flex items-center gap-2 bg-secondary rounded-lg px-3 py-2.5">
              <span className="text-sm text-muted-foreground">🇮🇳 +91</span>
              <input
                type="tel"
                placeholder={t('phoneNumber')}
                value={phone}
                onChange={(e) => setPhone(e.target.value.replace(/[^\d]/g, '').slice(0, 10))}
                className="flex-1 bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground"
                disabled={otpSent}
                maxLength={10}
              />
            </div>
          )}

          {/* OTP input */}
          {otpSent && (
            <div className="space-y-2">
              <label className="text-xs font-semibold text-muted-foreground">
                {method === 'email' ? t('enterEmailOtp') : t('enterPhoneOtp')}
              </label>
              <input
                type="text"
                inputMode="numeric"
                placeholder="● ● ● ● ● ●"
                value={otp}
                onChange={(e) => setOtp(e.target.value.replace(/[^\d]/g, '').slice(0, 6))}
                className="w-full bg-secondary rounded-lg px-3 py-2.5 text-sm text-foreground text-center tracking-[0.5em] outline-none placeholder:text-muted-foreground placeholder:tracking-[0.3em] font-mono"
                maxLength={6}
                autoFocus
              />
              <button
                onClick={() => { resetOtpState(); }}
                className="text-xs text-primary hover:underline"
              >
                {t('changeDetails')}
              </button>
            </div>
          )}

          {/* Action button */}
          <button
            onClick={otpSent ? handleVerifyOtp : handleSendOtp}
            disabled={loading}
            className="w-full gradient-primary text-primary-foreground py-3 rounded-lg font-bold text-sm flex items-center justify-center gap-2 hover:opacity-90 transition-opacity disabled:opacity-60"
          >
            {loading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <>
                {otpSent
                  ? t('verifyOtp')
                  : mode === 'signup'
                    ? t('createAndSendOtp')
                    : t('sendOtp')}
                <ChevronRight className="w-4 h-4" />
              </>
            )}
          </button>

          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            <div className="flex-1 h-px bg-border" />
            {t('orContinueWith')}
            <div className="flex-1 h-px bg-border" />
          </div>

          <button
            onClick={handleGoogleLogin}
            disabled={loading}
            className="w-full bg-secondary text-secondary-foreground py-2.5 rounded-lg text-sm font-semibold flex items-center justify-center gap-2 hover:bg-secondary/80 transition disabled:opacity-60"
          >
            <svg className="w-4 h-4" viewBox="0 0 24 24">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"/>
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
            </svg>
            {t('googleAccount')}
          </button>
        </div>

        <p className="text-[10px] text-muted-foreground text-center mt-4">{t('termsText')}</p>
      </div>
    </div>
  );
};

export default OnboardingPage;
