import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLanguage } from '@/contexts/LanguageContext';
import { languageNames, Language } from '@/lib/i18n';
import { ArrowLeft, Edit2, ChevronRight, Globe, Bell, Calendar, Moon, Shield, LogOut, Sprout, TrendingUp } from 'lucide-react';
import BottomNav from '@/components/BottomNav';

const FarmerProfilePage: React.FC = () => {
  const { t, language, setLanguage } = useLanguage();
  const navigate = useNavigate();
  const [showLangPicker, setShowLangPicker] = useState(false);

  const stats = [
    { value: '12.5', label: 'Acres' },
    { value: '4.8', label: 'Rating' },
    { value: '13', label: 'Crops' },
  ];

  const menuItems = [
    { icon: Sprout, label: t('cropHistory'), path: '/crop-detail' },
    { icon: Globe, label: t('changeLanguage'), action: () => setShowLangPicker(true) },
    { icon: Bell, label: t('priceAlerts'), path: '/market' },
    { icon: Calendar, label: t('harvestSchedule'), path: '/crop-rotation' },
    { icon: Shield, label: t('privacySecurity'), path: '#' },
  ];

  return (
    <div className="min-h-screen bg-background pb-20">
      <div className="px-5 pt-5 pb-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate(-1)} className="w-8 h-8 rounded-full bg-secondary flex items-center justify-center">
            <ArrowLeft className="w-4 h-4 text-foreground" />
          </button>
          <h1 className="text-lg font-extrabold text-foreground">{t('farmerProfile')}</h1>
        </div>
        <button className="w-8 h-8 rounded-full bg-secondary flex items-center justify-center">
          <Edit2 className="w-4 h-4 text-foreground" />
        </button>
      </div>

      <div className="px-5 space-y-4">
        {/* Profile Card */}
        <div className="glass-card p-5 text-center">
          <div className="w-16 h-16 rounded-full gradient-primary mx-auto flex items-center justify-center text-2xl">
            👨‍🌾
          </div>
          <h2 className="text-base font-extrabold text-foreground mt-2">Rajesh Kumar</h2>
          <p className="text-xs text-muted-foreground">Nashik, Maharashtra</p>

          <div className="flex justify-center gap-6 mt-4">
            {stats.map((s, i) => (
              <div key={i} className="text-center">
                <p className="text-lg font-extrabold text-foreground">{s.value}</p>
                <p className="text-[10px] text-muted-foreground">{s.label}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Menu */}
        <div className="space-y-1">
          {menuItems.map((item, i) => (
            <button
              key={i}
              onClick={() => item.action ? item.action() : item.path && navigate(item.path)}
              className="w-full glass-card p-3.5 flex items-center gap-3 hover:bg-primary/5 transition-colors"
            >
              <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
                <item.icon className="w-4 h-4 text-primary" />
              </div>
              <span className="flex-1 text-sm font-semibold text-foreground text-left">{item.label}</span>
              <ChevronRight className="w-4 h-4 text-muted-foreground" />
            </button>
          ))}
        </div>

        {/* Logout */}
        <button
          onClick={() => navigate('/')}
          className="w-full glass-card p-3.5 flex items-center gap-3 hover:bg-destructive/10 transition-colors"
        >
          <div className="w-8 h-8 rounded-lg bg-destructive/10 flex items-center justify-center">
            <LogOut className="w-4 h-4 text-destructive" />
          </div>
          <span className="flex-1 text-sm font-semibold text-destructive text-left">{t('logout')}</span>
        </button>
      </div>

      {/* Language Picker Modal */}
      {showLangPicker && (
        <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-end">
          <div className="w-full glass-card rounded-t-3xl p-5 pb-8 animate-in slide-in-from-bottom">
            <div className="w-10 h-1 bg-border rounded-full mx-auto mb-4" />
            <h3 className="text-base font-extrabold text-foreground mb-3">{t('changeLanguage')}</h3>
            <div className="space-y-2">
              {(Object.keys(languageNames) as Language[]).map((lang) => (
                <button
                  key={lang}
                  onClick={() => { setLanguage(lang); setShowLangPicker(false); }}
                  className={`w-full px-4 py-3 rounded-xl text-sm font-semibold text-left transition-all ${
                    language === lang
                      ? 'gradient-primary text-primary-foreground'
                      : 'bg-secondary text-secondary-foreground hover:bg-secondary/80'
                  }`}
                >
                  {languageNames[lang]}
                </button>
              ))}
            </div>
            <button
              onClick={() => setShowLangPicker(false)}
              className="w-full mt-3 bg-secondary text-secondary-foreground py-3 rounded-xl font-bold text-sm"
            >
              {t('cancel')}
            </button>
          </div>
        </div>
      )}

      <BottomNav />
    </div>
  );
};

export default FarmerProfilePage;
