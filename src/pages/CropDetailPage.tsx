import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useLanguage } from '@/contexts/LanguageContext';
import { ArrowLeft, Droplets, Thermometer, CloudRain, Layers } from 'lucide-react';
import BottomNav from '@/components/BottomNav';
import cropRice from '@/assets/crop-rice.jpg';

const CropDetailPage: React.FC = () => {
  const { t } = useLanguage();
  const navigate = useNavigate();

  const requirements = [
    { icon: Layers, label: t('soilType'), value: 'Loamy, well-drained with good water retention capacity (Sandy Loam, Clay Loam)' },
    { icon: Thermometer, label: t('temperature'), value: 'Ideal range 20°C - 35°C during the growing and vegetable phase' },
    { icon: Droplets, label: t('irrigation'), value: 'Requires standing water (5-10cm) during initial vegetable phase' },
  ];

  const priceData = [30, 45, 40, 55, 50, 60, 55, 70, 65, 80, 75, 85];

  return (
    <div className="min-h-screen bg-background pb-20">
      {/* Hero */}
      <div className="relative h-48">
        <img src={cropRice} alt="Basmati Rice" className="w-full h-full object-cover" width={512} height={512} />
        <div className="absolute inset-0 bg-gradient-to-b from-transparent to-background" />
        <button
          onClick={() => navigate(-1)}
          className="absolute top-4 left-4 w-8 h-8 rounded-full bg-background/80 backdrop-blur flex items-center justify-center"
        >
          <ArrowLeft className="w-4 h-4 text-foreground" />
        </button>
      </div>

      <div className="px-5 -mt-6 relative z-10 space-y-4">
        <div>
          <h1 className="text-xl font-extrabold text-foreground">Basmati Rice (Pusa-1121)</h1>
          <div className="flex gap-4 mt-2 text-xs text-muted-foreground">
            <span>🌱 {t('kharif')}</span>
            <span>💧 High</span>
            <span>📅 120 Days</span>
            <span>📊 4.8 t/ha</span>
          </div>
        </div>

        {/* Market Price Trend */}
        <div className="glass-card p-4">
          <h3 className="text-sm font-bold text-foreground mb-3">{t('marketPriceTrend')}</h3>
          <div className="h-20 flex items-end gap-1 mb-2">
            {priceData.map((h, i) => (
              <div
                key={i}
                className="flex-1 rounded-t transition-all"
                style={{
                  height: `${h}%`,
                  background: i === priceData.length - 1
                    ? 'hsl(152 65% 45%)'
                    : 'hsl(152 65% 45% / 0.3)',
                }}
              />
            ))}
          </div>
          <div className="flex justify-between text-[10px] text-muted-foreground">
            <span>Jan</span>
            <span>Jun</span>
            <span>Dec</span>
          </div>
          <div className="mt-2 flex items-center justify-between">
            <span className="text-xs text-muted-foreground">{t('currentMandiAvg')}</span>
            <span className="text-sm font-bold text-primary">₹4,250 / Quintal</span>
          </div>
        </div>

        {/* Cultivation Requirements */}
        <div>
          <h3 className="text-sm font-bold text-foreground mb-3">{t('cultivationRequirements')}</h3>
          <div className="space-y-2">
            {requirements.map((req, i) => (
              <div key={i} className="glass-card p-3 flex gap-3">
                <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
                  <req.icon className="w-4 h-4 text-primary" />
                </div>
                <div>
                  <p className="text-xs font-bold text-foreground">{req.label}</p>
                  <p className="text-[10px] text-muted-foreground leading-relaxed mt-0.5">{req.value}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="flex gap-2">
          <button className="flex-1 gradient-primary text-primary-foreground py-3 rounded-xl font-bold text-sm">
            {t('downloadGuide')}
          </button>
          <button className="flex-1 bg-secondary text-secondary-foreground py-3 rounded-xl font-bold text-sm">
            {t('startSaving')}
          </button>
        </div>
      </div>

      <BottomNav />
    </div>
  );
};

export default CropDetailPage;
