import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useLanguage } from '@/contexts/LanguageContext';
import { Cloud, Sprout, TrendingUp, RotateCcw, Brain, ChevronRight, Droplets, Wind } from 'lucide-react';
import BottomNav from '@/components/BottomNav';
import cropRice from '@/assets/crop-rice.jpg';
import cropCotton from '@/assets/crop-cotton.jpg';
import cropSugarcane from '@/assets/crop-sugarcane.jpg';

const HomeDashboard: React.FC = () => {
  const { t } = useLanguage();
  const navigate = useNavigate();

  const smartActions = [
    { icon: Sprout, label: t('cropRecs'), desc: t('aiBasedSelection'), color: 'text-primary', path: '/crop-recommendations' },
    { icon: TrendingUp, label: t('market'), desc: t('livePrediction'), color: 'text-primary', path: '/market' },
    { icon: RotateCcw, label: t('rotation'), desc: t('soilHealthLoss'), color: 'text-primary', path: '/crop-rotation' },
    { icon: Brain, label: t('predict'), desc: t('priceForcast'), color: 'text-primary', path: '/price-prediction' },
  ];

  const recommendations = [
    { name: 'Sugarcane', period: '10-18 Months • High Water', score: '+18%', img: cropSugarcane },
    { name: 'Cotton', period: '6 Months • Medium Water', score: '+12%', img: cropCotton },
    { name: 'Rice (Basmati)', period: '4 Months • High Water', score: '+8%', img: cropRice },
  ];

  return (
    <div className="min-h-screen bg-background pb-20">
      {/* Header */}
      <div className="px-5 pt-5 pb-3">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs text-muted-foreground">{t('namaste')}, Rajesh</p>
            <h1 className="text-lg font-extrabold text-foreground">🌾 {t('appName')}</h1>
          </div>
          <button onClick={() => navigate('/profile')} className="w-9 h-9 rounded-full bg-secondary flex items-center justify-center">
            <span className="text-sm">👤</span>
          </button>
        </div>
      </div>

      {/* Weather Card */}
      <div className="px-5 mb-4">
        <div className="glass-card p-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Cloud className="w-8 h-8 text-primary" />
            <div>
              <p className="text-2xl font-extrabold text-foreground">28°C</p>
              <p className="text-xs text-muted-foreground">{t('partlyCloudy')}</p>
            </div>
          </div>
          <div className="flex gap-4">
            <div className="flex items-center gap-1">
              <Droplets className="w-3.5 h-3.5 text-primary" />
              <span className="text-xs text-muted-foreground">65%</span>
            </div>
            <div className="flex items-center gap-1">
              <Wind className="w-3.5 h-3.5 text-primary" />
              <span className="text-xs text-muted-foreground">12 km/h</span>
            </div>
          </div>
        </div>
      </div>

      {/* AI Smart Actions */}
      <div className="px-5 mb-4">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-bold text-foreground">{t('aiSmartActions')}</h2>
          <button className="text-xs text-primary font-semibold">{t('viewAll')}</button>
        </div>
        <div className="grid grid-cols-4 gap-2">
          {smartActions.map((action, i) => (
            <button
              key={i}
              onClick={() => navigate(action.path)}
              className="glass-card p-3 flex flex-col items-center gap-2 hover:bg-primary/5 transition-colors"
            >
              <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center">
                <action.icon className={`w-5 h-5 ${action.color}`} />
              </div>
              <p className="text-[10px] font-bold text-foreground text-center leading-tight">{action.label}</p>
              <p className="text-[8px] text-muted-foreground text-center">{action.desc}</p>
            </button>
          ))}
        </div>
      </div>

      {/* Market Trend Mini Chart */}
      <div className="px-5 mb-4">
        <div className="glass-card p-4">
          <div className="flex items-center justify-between mb-2">
            <p className="text-xs font-bold text-foreground">Onion (Nashik Mandi)</p>
            <span className="text-xs text-primary font-bold">+8.5%</span>
          </div>
          <div className="h-12 flex items-end gap-1">
            {[40, 55, 45, 65, 50, 70, 60, 80, 75, 90, 85, 95].map((h, i) => (
              <div
                key={i}
                className="flex-1 rounded-t bg-primary/30"
                style={{ height: `${h}%` }}
              />
            ))}
          </div>
        </div>
      </div>

      {/* Top Recommendations */}
      <div className="px-5 mb-4">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-bold text-foreground">{t('topRecommendations')}</h2>
        </div>
        <div className="space-y-2">
          {recommendations.map((rec, i) => (
            <button
              key={i}
              onClick={() => navigate('/crop-detail')}
              className="w-full glass-card p-3 flex items-center gap-3 hover:bg-primary/5 transition-colors"
            >
              <img src={rec.img} alt={rec.name} className="w-11 h-11 rounded-lg object-cover" loading="lazy" width={44} height={44} />
              <div className="flex-1 text-left">
                <p className="text-sm font-bold text-foreground">{rec.name}</p>
                <p className="text-[10px] text-muted-foreground">{rec.period}</p>
              </div>
              <span className="text-xs font-bold text-primary">{rec.score}</span>
              <ChevronRight className="w-4 h-4 text-muted-foreground" />
            </button>
          ))}
        </div>
      </div>

      {/* Ask AI */}
      <div className="px-5">
        <button
          onClick={() => navigate('/ai-chat')}
          className="w-full glass-card p-4 flex items-center gap-3 hover:bg-primary/5 transition-colors"
        >
          <div className="w-10 h-10 rounded-full gradient-primary flex items-center justify-center">
            <Brain className="w-5 h-5 text-primary-foreground" />
          </div>
          <div className="flex-1 text-left">
            <p className="text-sm font-bold text-foreground">{t('askAgroSmartAi')}</p>
            <p className="text-[10px] text-muted-foreground">{t('askInLanguage')}</p>
          </div>
          <ChevronRight className="w-4 h-4 text-muted-foreground" />
        </button>
      </div>

      <BottomNav />
    </div>
  );
};

export default HomeDashboard;
