import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLanguage } from '@/contexts/LanguageContext';
import { ArrowLeft, MapPin, FlaskConical } from 'lucide-react';
import BottomNav from '@/components/BottomNav';

const CropRecommendationsPage: React.FC = () => {
  const { t } = useLanguage();
  const navigate = useNavigate();
  const [season, setSeason] = useState('kharif');
  const [nitrogen, setNitrogen] = useState('40');
  const [phosphorus, setPhosphorus] = useState('15');
  const [potassium, setPotassium] = useState('10');
  const [ph, setPh] = useState('6.5');
  const [rainfall, setRainfall] = useState('800');

  const seasons = [
    { id: 'kharif', label: t('kharif') },
    { id: 'rabi', label: t('rabi') },
    { id: 'zaid', label: t('zaid') },
  ];

  return (
    <div className="min-h-screen bg-background pb-20">
      <div className="px-5 pt-5 pb-3 flex items-center gap-3">
        <button onClick={() => navigate(-1)} className="w-8 h-8 rounded-full bg-secondary flex items-center justify-center">
          <ArrowLeft className="w-4 h-4 text-foreground" />
        </button>
        <h1 className="text-lg font-extrabold text-foreground">{t('cropAdvisor')}</h1>
      </div>

      <div className="px-5 space-y-4">
        {/* Location */}
        <div className="glass-card p-4">
          <div className="flex items-center gap-2 mb-1">
            <MapPin className="w-4 h-4 text-primary" />
            <span className="text-xs font-bold text-muted-foreground">{t('currentLocation')}</span>
          </div>
          <p className="text-sm font-semibold text-foreground">Belagavi, Karnataka</p>
        </div>

        {/* Season */}
        <div>
          <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider">{t('selectSeason')}</label>
          <div className="flex gap-2 mt-2">
            {seasons.map((s) => (
              <button
                key={s.id}
                onClick={() => setSeason(s.id)}
                className={`flex-1 py-2.5 rounded-lg text-sm font-semibold transition-all ${
                  season === s.id ? 'gradient-primary text-primary-foreground' : 'bg-secondary text-secondary-foreground'
                }`}
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>

        {/* Soil Composition */}
        <div>
          <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider">{t('soilComposition')}</label>
          <div className="grid grid-cols-3 gap-2 mt-2">
            {[
              { label: t('nitrogen'), value: nitrogen, set: setNitrogen },
              { label: t('phosphorus'), value: phosphorus, set: setPhosphorus },
              { label: t('potassium'), value: potassium, set: setPotassium },
            ].map((item) => (
              <div key={item.label} className="glass-card p-3">
                <p className="text-[10px] text-muted-foreground mb-1">{item.label}</p>
                <input
                  type="number"
                  value={item.value}
                  onChange={(e) => item.set(e.target.value)}
                  className="w-full bg-secondary rounded px-2 py-1.5 text-sm text-foreground outline-none"
                />
              </div>
            ))}
          </div>
          <div className="grid grid-cols-2 gap-2 mt-2">
            <div className="glass-card p-3">
              <p className="text-[10px] text-muted-foreground mb-1">{t('phLevel')}</p>
              <input
                type="number"
                step="0.1"
                value={ph}
                onChange={(e) => setPh(e.target.value)}
                className="w-full bg-secondary rounded px-2 py-1.5 text-sm text-foreground outline-none"
              />
            </div>
            <div className="glass-card p-3">
              <p className="text-[10px] text-muted-foreground mb-1">{t('rainfall')}</p>
              <input
                type="number"
                value={rainfall}
                onChange={(e) => setRainfall(e.target.value)}
                className="w-full bg-secondary rounded px-2 py-1.5 text-sm text-foreground outline-none"
              />
            </div>
          </div>
        </div>

        <button
          onClick={() => navigate('/crop-detail')}
          className="w-full gradient-primary text-primary-foreground py-3 rounded-xl font-bold text-sm hover:opacity-90 transition-opacity"
        >
          {t('getRecommendations')}
        </button>
      </div>

      <BottomNav />
    </div>
  );
};

export default CropRecommendationsPage;
