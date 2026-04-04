import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLanguage } from '@/contexts/LanguageContext';
import { Phone, ChevronRight } from 'lucide-react';
import heroFarm from '@/assets/hero-farm.jpg';

const OnboardingPage: React.FC = () => {
  const { t } = useLanguage();
  const navigate = useNavigate();
  const [phone, setPhone] = useState('');

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

          <div className="flex items-center gap-2 bg-secondary rounded-lg px-3 py-2.5">
            <span className="text-sm text-muted-foreground">🇮🇳 +91</span>
            <input
              type="tel"
              placeholder={t('phoneNumber')}
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              className="flex-1 bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground"
            />
          </div>

          <button
            onClick={() => navigate('/setup')}
            className="w-full gradient-primary text-primary-foreground py-3 rounded-lg font-bold text-sm flex items-center justify-center gap-2 hover:opacity-90 transition-opacity"
          >
            {t('sendOtp')}
            <ChevronRight className="w-4 h-4" />
          </button>

          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            <div className="flex-1 h-px bg-border" />
            {t('orContinueWith')}
            <div className="flex-1 h-px bg-border" />
          </div>

          <button className="w-full bg-secondary text-secondary-foreground py-2.5 rounded-lg text-sm font-semibold flex items-center justify-center gap-2 hover:bg-secondary/80 transition">
            <span>🔵</span> {t('googleAccount')}
          </button>
          <button className="w-full bg-secondary text-secondary-foreground py-2.5 rounded-lg text-sm font-semibold flex items-center justify-center gap-2 hover:bg-secondary/80 transition">
            <span>🍎</span> {t('appleId')}
          </button>
        </div>

        <p className="text-[10px] text-muted-foreground text-center mt-4">{t('termsText')}</p>
      </div>
    </div>
  );
};

export default OnboardingPage;
