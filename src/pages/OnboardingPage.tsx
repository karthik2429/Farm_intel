import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLanguage } from '@/contexts/LanguageContext';
import { useAuth } from '@/contexts/AuthContext';
import { supabase } from '@/integrations/supabase/client';
import { ChevronRight, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import heroFarm from '@/assets/hero-farm.jpg';

const OnboardingPage: React.FC = () => {
  const { t } = useLanguage();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [phone, setPhone] = useState('');
  const [otp, setOtp] = useState('');
  const [otpSent, setOtpSent] = useState(false);
  const [loading, setLoading] = useState(false);

  // Redirect if already logged in
  React.useEffect(() => {
    if (user) navigate('/setup', { replace: true });
  }, [user, navigate]);

  const handleSendOtp = async () => {
    const cleaned = phone.replace(/\s/g, '');
    if (cleaned.length < 10) {
      toast.error('Please enter a valid 10-digit phone number');
      return;
    }

    setLoading(true);
    const fullPhone = cleaned.startsWith('+91') ? cleaned : `+91${cleaned}`;

    const { error } = await supabase.auth.signInWithOtp({ phone: fullPhone });

    if (error) {
      toast.error(error.message || 'Failed to send OTP');
    } else {
      setOtpSent(true);
      toast.success('OTP sent to your phone!');
    }
    setLoading(false);
  };

  const handleVerifyOtp = async () => {
    if (otp.length < 6) {
      toast.error('Please enter the 6-digit OTP');
      return;
    }

    setLoading(true);
    const cleaned = phone.replace(/\s/g, '');
    const fullPhone = cleaned.startsWith('+91') ? cleaned : `+91${cleaned}`;

    const { error } = await supabase.auth.verifyOtp({
      phone: fullPhone,
      token: otp,
      type: 'sms',
    });

    if (error) {
      toast.error(error.message || 'Invalid OTP');
    } else {
      toast.success('Logged in successfully!');
      navigate('/setup');
    }
    setLoading(false);
  };

  const handleGoogleLogin = async () => {
    setLoading(true);
    const { error } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: `${window.location.origin}/setup`,
      },
    });
    if (error) {
      toast.error(error.message || 'Google sign-in failed');
      setLoading(false);
    }
  };

  const handleAppleLogin = async () => {
    setLoading(true);
    const { error } = await supabase.auth.signInWithOAuth({
      provider: 'apple',
      options: {
        redirectTo: `${window.location.origin}/setup`,
      },
    });
    if (error) {
      toast.error(error.message || 'Apple sign-in failed');
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* Hero */}
      <div className="relative h-56 overflow-hidden">
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

        <div className="glass-card p-5 mt-5 space-y-4">
          <h2 className="text-lg font-bold text-foreground">{t('welcomeBack')}</h2>
          <p className="text-xs text-muted-foreground">{t('signIn')}</p>

          {/* Phone input */}
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

          {/* OTP input (shown after OTP sent) */}
          {otpSent && (
            <div className="space-y-2">
              <label className="text-xs font-semibold text-muted-foreground">Enter 6-digit OTP</label>
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
                onClick={handleSendOtp}
                disabled={loading}
                className="text-xs text-primary hover:underline"
              >
                Resend OTP
              </button>
            </div>
          )}

          {/* Send OTP / Verify OTP button */}
          <button
            onClick={otpSent ? handleVerifyOtp : handleSendOtp}
            disabled={loading}
            className="w-full gradient-primary text-primary-foreground py-3 rounded-lg font-bold text-sm flex items-center justify-center gap-2 hover:opacity-90 transition-opacity disabled:opacity-60"
          >
            {loading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <>
                {otpSent ? 'Verify OTP' : t('sendOtp')}
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

          <button
            onClick={handleAppleLogin}
            disabled={loading}
            className="w-full bg-secondary text-secondary-foreground py-2.5 rounded-lg text-sm font-semibold flex items-center justify-center gap-2 hover:bg-secondary/80 transition disabled:opacity-60"
          >
            <span>🍎</span> {t('appleId')}
          </button>
        </div>

        <p className="text-[10px] text-muted-foreground text-center mt-4">{t('termsText')}</p>
      </div>
    </div>
  );
};

export default OnboardingPage;
