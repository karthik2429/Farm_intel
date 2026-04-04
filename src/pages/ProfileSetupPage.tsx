import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLanguage } from '@/contexts/LanguageContext';
import { languageNames, Language } from '@/lib/i18n';
import { MapPin, ChevronDown, Wheat, Apple, Banknote } from 'lucide-react';

const ProfileSetupPage: React.FC = () => {
  const { t, language, setLanguage } = useLanguage();
  const navigate = useNavigate();
  const [state, setState] = useState('Karnataka');
  const [district, setDistrict] = useState('Belagavi');
  const [selectedCrops, setSelectedCrops] = useState<string[]>(['cereals']);

  const cropTypes = [
    { id: 'cereals', label: t('cerealsGrains'), icon: Wheat, desc: 'Rice, Wheat, Bajra...' },
    { id: 'fruits', label: t('fruitsVegetables'), icon: Apple, desc: 'Tomato, Mango, Onion...' },
    { id: 'cash', label: t('cashCrops'), icon: Banknote, desc: 'Sugarcane, Cotton, Tobacco' },
  ];

  const toggleCrop = (id: string) => {
    setSelectedCrops(prev => prev.includes(id) ? prev.filter(c => c !== id) : [...prev, id]);
  };

  return (
    <div className="min-h-screen bg-background px-5 py-6 pb-8">
      <h1 className="text-xl font-extrabold text-foreground">{t('namaste')} 🙏</h1>
      <p className="text-xs text-muted-foreground mt-1">{t('letsSetup')}</p>

      {/* Language Selection */}
      <div className="mt-5">
        <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider">{t('preferredLanguage')}</label>
        <div className="grid grid-cols-4 gap-2 mt-2">
          {(Object.keys(languageNames) as Language[]).map((lang) => (
            <button
              key={lang}
              onClick={() => setLanguage(lang)}
              className={`px-2 py-2 rounded-lg text-xs font-semibold transition-all ${
                language === lang
                  ? 'gradient-primary text-primary-foreground'
                  : 'bg-secondary text-secondary-foreground hover:bg-secondary/80'
              }`}
            >
              {languageNames[lang]}
            </button>
          ))}
        </div>
      </div>

      {/* Location */}
      <div className="mt-5">
        <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider">{t('location')}</label>
        <div className="space-y-2 mt-2">
          <div className="flex items-center gap-2 bg-secondary rounded-lg px-3 py-2.5">
            <MapPin className="w-4 h-4 text-primary" />
            <select
              value={state}
              onChange={(e) => setState(e.target.value)}
              className="flex-1 bg-transparent text-sm text-foreground outline-none"
            >
              <option value="Karnataka">Karnataka</option>
              <option value="Tamil Nadu">Tamil Nadu</option>
              <option value="Andhra Pradesh">Andhra Pradesh</option>
              <option value="Kerala">Kerala</option>
              <option value="Maharashtra">Maharashtra</option>
              <option value="Telangana">Telangana</option>
              <option value="Uttar Pradesh">Uttar Pradesh</option>
            </select>
          </div>
          <div className="flex items-center gap-2 bg-secondary rounded-lg px-3 py-2.5">
            <MapPin className="w-4 h-4 text-primary" />
            <select
              value={district}
              onChange={(e) => setDistrict(e.target.value)}
              className="flex-1 bg-transparent text-sm text-foreground outline-none"
            >
              <option value="Belagavi">Belagavi</option>
              <option value="Mysuru">Mysuru</option>
              <option value="Dharwad">Dharwad</option>
            </select>
          </div>
        </div>
      </div>

      {/* Crops */}
      <div className="mt-5">
        <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider">{t('whatDoYouGrow')}</label>
        <div className="space-y-2 mt-2">
          {cropTypes.map((crop) => (
            <button
              key={crop.id}
              onClick={() => toggleCrop(crop.id)}
              className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all ${
                selectedCrops.includes(crop.id)
                  ? 'bg-primary/15 border border-primary/40'
                  : 'bg-secondary border border-transparent'
              }`}
            >
              <crop.icon className={`w-5 h-5 ${selectedCrops.includes(crop.id) ? 'text-primary' : 'text-muted-foreground'}`} />
              <div className="text-left">
                <p className="text-sm font-semibold text-foreground">{crop.label}</p>
                <p className="text-[10px] text-muted-foreground">{crop.desc}</p>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Specific Crops */}
      <div className="mt-4 bg-secondary rounded-lg px-3 py-2.5">
        <input
          placeholder={t('specificCrops')}
          className="w-full bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground"
        />
      </div>

      <button
        onClick={() => navigate('/home')}
        className="w-full gradient-primary text-primary-foreground py-3 rounded-xl font-bold text-sm mt-6 hover:opacity-90 transition-opacity"
      >
        {t('completeSetup')} →
      </button>

      <p className="text-[10px] text-muted-foreground text-center mt-3">{t('agreeAlerts')}</p>
    </div>
  );
};

export default ProfileSetupPage;
