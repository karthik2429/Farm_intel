import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLanguage } from '@/contexts/LanguageContext';
import { useAuth } from '@/contexts/AuthContext';
import { Cloud, Sprout, TrendingUp, RotateCcw, Brain, ChevronRight, Droplets, Wind } from 'lucide-react';
import BottomNav from '@/components/BottomNav';
import cropRice from '@/assets/crop-rice.jpg';
import cropCotton from '@/assets/crop-cotton.jpg';
import cropSugarcane from '@/assets/crop-sugarcane.jpg';
import { getCropRecommendations } from '@/lib/api';

const HomeDashboard: React.FC = () => {

  const { t } = useLanguage();
  const { user } = useAuth();
  const navigate = useNavigate();

  const userName =
    user?.user_metadata?.full_name ||
    user?.user_metadata?.name ||
    localStorage.getItem('profile_name') ||
    '';

  const [recommendations, setRecommendations] = useState<any[]>([]);

  useEffect(() => {
    console.log("Dashboard useEffect running"); // ✅ MUST SHOW

    const fetchData = async (lat: number, lon: number) => {
      try {
        console.log("Fetching with:", lat, lon);

        const payload = {
          lat,
          lon,
          season: "kharif",
          mode: "coords"
        };

        const data = await getCropRecommendations(payload);

        console.log("DASHBOARD RESPONSE:", data); // 🔥

        if (!data || !data["Top Crops"]) {
          console.log("No data from backend");
          return;
        }

        const mapped = data["Top Crops"].map((c: any, i: number) => {
          const name = c[0];
          const score = Math.round(c[1] * 100);

          return {
            name: name.charAt(0).toUpperCase() + name.slice(1),
            period:
              i === 0 ? '4 Months • High Water' :
              i === 1 ? '10-18 Months • High Water' :
              '6 Months • Medium Water',
            score: `+${score}%`,
            img:
              name === "rice" ? cropRice :
              name === "sugarcane" ? cropSugarcane :
              cropCotton
          };
        });

        setRecommendations(mapped);

      } catch (err) {
        console.error("API ERROR:", err);
      }
    };

    // ✅ TRY LOCATION
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          console.log("Location success"); // ✅
          fetchData(pos.coords.latitude, pos.coords.longitude);
        },
        (err) => {
          console.log("Location failed → using fallback"); // ✅
          fetchData(15.8497, 74.4977); // 🔥 fallback (Belagavi)
        }
      );
    } else {
      console.log("No geolocation → fallback"); // ✅
      fetchData(15.8497, 74.4977);
    }

  }, []);
  const smartActions = [
    { icon: Sprout, label: t('cropRecs'), path: '/crop-recommendations' },
    { icon: TrendingUp, label: t('market'), path: '/market' },
    { icon: RotateCcw, label: t('rotation'), path: '/crop-rotation' },
    { icon: Brain, label: t('predict'), path: '/price-prediction' },
  ];

  return (
    <div className="min-h-screen bg-background pb-20">
      {/* Header */}
      <div className="px-5 pt-5 pb-3">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs text-muted-foreground">
              {t('namaste')}
              {userName ? `, ${userName}` : ''}
            </p>
            <h1 className="text-lg font-extrabold text-foreground">
              🌾 {t('appName')}
            </h1>
          </div>
          <button
            onClick={() => navigate('/profile')}
            className="w-9 h-9 rounded-full bg-secondary flex items-center justify-center"
          >
            👤
          </button>
        </div>
      </div>

      {/* Weather */}
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

      {/* Actions */}
      <div className="px-5 mb-4">
        <h2 className="text-sm font-bold text-foreground mb-3">
          {t('aiSmartActions')}
        </h2>
        <div className="grid grid-cols-4 gap-2">
          {smartActions.map((a, i) => (
            <button
              key={i}
              onClick={() => navigate(a.path)}
              className="glass-card p-3 flex flex-col items-center gap-2"
            >
              <a.icon className="w-5 h-5 text-primary" />
              <p className="text-[10px] font-bold text-foreground text-center">
                {a.label}
              </p>
            </button>
          ))}
        </div>
      </div>

      {/* Recommendations */}
      <div className="px-5 mb-4">
        <h2 className="text-sm font-bold text-foreground mb-3">
          {t('topRecommendations')}
        </h2>

      <div className="space-y-2">
        {recommendations.length === 0 ? (
          <p className="text-xs text-muted-foreground">Loading...</p>
        ) : (
          recommendations.map((rec, i) => (
            <button
              key={i}
              onClick={() => navigate('/crop-detail')}
              className="w-full glass-card p-3 flex items-center gap-3"
            >
              <img
                src={rec.img}
                className="w-11 h-11 rounded-lg object-cover"
              />
              <div className="flex-1 text-left">
                <p className="text-sm font-bold text-foreground">
                  {rec.name}
                </p>
                <p className="text-[10px] text-muted-foreground">
                  {rec.period}
                </p>
              </div>
              <span className="text-xs font-bold text-primary">
                {rec.score}
              </span>
            </button>
          ))
        )}
      </div>
    </div>

      <BottomNav />
    </div>
  );
};

export default HomeDashboard;