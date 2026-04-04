import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useLanguage } from '@/contexts/LanguageContext';
import { ArrowLeft, TrendingUp, Bell, AlertTriangle, Truck, CloudRain } from 'lucide-react';
import BottomNav from '@/components/BottomNav';

const PricePredictionPage: React.FC = () => {
  const { t } = useLanguage();
  const navigate = useNavigate();

  const priceData = [45, 50, 48, 55, 52, 58, 55, 62, 60, 68, 72, 78, 82, 85];

  const factors = [
    { icon: Truck, label: 'Monsoon Impact', desc: 'Late onset is harsh, might delay harvest, pushing early prices downwards' },
    { icon: AlertTriangle, label: 'Export Demand', desc: 'New trade agreements with UAE expected to increase demand by 15%' },
    { icon: CloudRain, label: 'Storage Trend', desc: 'Cold storage capacity at 92% — limited buffer pushing supply gap in the northern region.' },
  ];

  return (
    <div className="min-h-screen bg-background pb-20">
      <div className="px-5 pt-5 pb-3 flex items-center gap-3">
        <button onClick={() => navigate(-1)} className="w-8 h-8 rounded-full bg-secondary flex items-center justify-center">
          <ArrowLeft className="w-4 h-4 text-foreground" />
        </button>
        <h1 className="text-lg font-extrabold text-foreground">{t('pricePrediction')}</h1>
      </div>

      <div className="px-5 space-y-4">
        {/* Current Price */}
        <div className="glass-card p-4">
          <p className="text-xs text-muted-foreground">Onion (Red)</p>
          <div className="flex items-baseline gap-2 mt-1">
            <span className="text-xs text-muted-foreground">Current Price</span>
            <span className="text-xl font-extrabold text-foreground">₹1,450/q</span>
          </div>
        </div>

        {/* Forecast Chart */}
        <div className="glass-card p-4">
          <h3 className="text-sm font-bold text-foreground mb-1">{t('marketPriceForecast')}</h3>
          <div className="h-24 flex items-end gap-1 mb-2">
            {priceData.map((h, i) => (
              <div
                key={i}
                className="flex-1 rounded-t transition-all"
                style={{
                  height: `${h}%`,
                  background: i >= priceData.length - 4
                    ? 'hsl(152 65% 45% / 0.6)'
                    : 'hsl(152 65% 45% / 0.25)',
                  borderTop: i >= priceData.length - 4 ? '2px dashed hsl(152 65% 45%)' : 'none',
                }}
              />
            ))}
          </div>
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-muted-foreground">Peak: Feb 2024</span>
            <span className="text-xs font-bold text-primary">{t('confidence')}: 88%</span>
          </div>
        </div>

        {/* Best Time to Sell */}
        <div className="glass-card p-4 border-l-4 border-primary">
          <div className="flex items-center gap-2 mb-1">
            <TrendingUp className="w-4 h-4 text-primary" />
            <h3 className="text-sm font-bold text-foreground">{t('bestTimeToSell')}</h3>
          </div>
          <p className="text-xs text-muted-foreground">
            Hold your stock until late January. Prices expected to rise 15-18% due to festive demand and supply gap in the northern region.
          </p>
          <button className="mt-3 gradient-primary text-primary-foreground px-4 py-2 rounded-lg text-xs font-bold">
            {t('getMoreAlert')}
          </button>
        </div>

        {/* Next Best Action */}
        <div className="glass-card p-4">
          <h3 className="text-sm font-bold text-foreground mb-1">{t('nextBestAction')}</h3>
          <p className="text-xs text-muted-foreground">
            Sell your stock with late January prices for best returns 15-18% due to a supply gap in the northern region.
          </p>
        </div>

        {/* Factors */}
        <div>
          <h3 className="text-sm font-bold text-foreground mb-3">{t('factorsInfluencing')}</h3>
          <div className="space-y-2">
            {factors.map((f, i) => (
              <div key={i} className="glass-card p-3 flex gap-3">
                <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
                  <f.icon className="w-4 h-4 text-primary" />
                </div>
                <div>
                  <p className="text-xs font-bold text-foreground">{f.label}</p>
                  <p className="text-[10px] text-muted-foreground leading-relaxed">{f.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <BottomNav />
    </div>
  );
};

export default PricePredictionPage;
