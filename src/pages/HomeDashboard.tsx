import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLanguage } from '@/contexts/LanguageContext';
import { useAuth } from '@/contexts/AuthContext';
import { Cloud, Sprout, TrendingUp, RotateCcw, Brain, ChevronRight, Droplets, Wind, MapPin, X } from 'lucide-react';
import BottomNav from '@/components/BottomNav';
import cropRice from '@/assets/crop-rice.jpg';
import cropCotton from '@/assets/crop-cotton.jpg';
import cropSugarcane from '@/assets/crop-sugarcane.jpg';
import { getCropRecommendations } from '@/lib/api';
import { allStates, getDistricts } from '@/lib/indian-locations';

// "bengaluru urban" -> "Bengaluru Urban" (backend resolves names lowercase)
const prettyName = (s?: string | null) =>
  s ? s.replace(/\b\w/g, (c) => c.toUpperCase()) : '';

const HomeDashboard: React.FC = () => {

  const { t } = useLanguage();
  const { user } = useAuth();
  const navigate = useNavigate();

  const userName =
    user?.user_metadata?.full_name ||
    user?.user_metadata?.name ||
    localStorage.getItem('profile_name') ||
    '';

  // 🔥 LOCATION: profile village → GPS auto-detect → manual picker.
  // No hidden default: if detection fails the user chooses state/district.
  const [locSource, setLocSource] = useState<'profile' | 'gps' | 'manual' | 'detecting' | 'none'>('detecting');
  const [locState, setLocState] = useState('');
  const [locDistrict, setLocDistrict] = useState('');
  const [resolvedLoc, setResolvedLoc] = useState<{ district: string; state: string } | null>(null);
  const [locCoords, setLocCoords] = useState<{ lat: number; lon: number } | null>(null);
  const [showLocPicker, setShowLocPicker] = useState(false);
  const [locVersion, setLocVersion] = useState(0); // bump to refetch
  interface RecRow {
    name: string; district: string; period: string;
    score: string; img: string;
  }
  const [recommendations, setRecommendations] = useState<RecRow[]>([]);
  const [loadingRecs, setLoadingRecs] = useState(true);

  // Resolve initial location once: profile first, then GPS auto-detect.
  // If both fail we don't guess a district - we ask the user to pick one.
  useEffect(() => {
    const pState = localStorage.getItem('profile_state');
    const pDistrict = localStorage.getItem('profile_district');
    if (pState && pDistrict && getDistricts(pState).includes(pDistrict)) {
      setLocState(pState);
      setLocDistrict(pDistrict);
      setLocCoords(null);
      setLocSource('profile');
      setLocVersion(v => v + 1);
      return;
    }
    let settled = false;
    const settleNoLocation = () => {
      if (settled) return;
      settled = true;
      setLocSource('none');
      setShowLocPicker(true); // open the picker so they can choose
    };
    if (navigator.geolocation) {
      // Some webviews hang on the permission prompt - don't block forever.
      const gpsTimeout = setTimeout(settleNoLocation, 4000);
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          clearTimeout(gpsTimeout);
          if (settled) return;
          settled = true;
          setLocCoords({ lat: pos.coords.latitude, lon: pos.coords.longitude });
          setLocSource('gps');
          setLocVersion(v => v + 1);
        },
        () => {
          clearTimeout(gpsTimeout);
          settleNoLocation();
        },
        { timeout: 3500 }
      );
    } else {
      settleNoLocation();
    }
  }, []);

  // Fetch recommendations for the resolved location. The location values
  // are intentionally read at bump time (locVersion) so a change always
  // refetches exactly once.
  useEffect(() => {
    if (locVersion === 0) return;

    const fetchData = async () => {
      setLoadingRecs(true);
      try {
        const payload: Record<string, unknown> = { season: "kharif" };
        if (locSource === 'gps' && locCoords) {
          payload.lat = locCoords.lat;
          payload.lon = locCoords.lon;
          payload.mode = "coords";
        } else if (locState && locDistrict) {
          payload.state = locState;
          payload.district = locDistrict;
          payload.mode = "auto";
        } else {
          return; // no usable location yet
        }

        const data = await getCropRecommendations(payload);

        if (!data || !data["Top Crops"]) {
          return;
        }

        // The backend tells us which district/state it actually resolved
        // (GPS → nearest known district); show that to the farmer.
        setResolvedLoc({
          district: prettyName(data.district),
          state: prettyName(data.state),
        });

        const mapped = data["Top Crops"].map((c: [string, number], i: number) => {
          const name = c[0];
          const score = Math.round(c[1] * 100);
          const displayName = name.charAt(0).toUpperCase() + name.slice(1);

          return {
            name: displayName,
            district: data.district
              ? `${prettyName(data.district)}${data.state ? `, ${prettyName(data.state)}` : ''}`
              : (locSource === 'gps' ? 'your location' : prettyName(locDistrict)),
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
      } finally {
        setLoadingRecs(false);
      }
    };

    fetchData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [locVersion]);
  const smartActions = [
    { icon: Sprout, label: t('cropRecs'), path: '/crop-recommendations' },
    { icon: TrendingUp, label: t('market'), path: '/market' },
    { icon: RotateCcw, label: t('rotation'), path: '/crop-rotation' },
    { icon: Brain, label: t('predict'), path: '/price-prediction' },
  ];

  // 📍 Display helpers - GPS resolves to whatever district the backend
  // matched; manual/profile uses the picked names directly.
  const displayDistrict = locSource === 'gps'
    ? (resolvedLoc?.district || 'your location')
    : prettyName(locDistrict);
  const displayState = locSource === 'gps'
    ? resolvedLoc?.state
    : prettyName(locState);

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

        {/* 📍 Location chip - shows which district the cards are for */}
        <button
          onClick={() => setShowLocPicker(s => !s)}
          className="w-full mt-2 glass-card px-3 py-2 flex items-center gap-2"
        >
          <MapPin className="w-3.5 h-3.5 text-primary" />
          <span className="text-xs font-bold text-foreground flex-1 text-left truncate">
            {locSource === 'detecting' && 'Detecting your location…'}
            {locSource === 'none' && 'Choose your state & district'}
            {locSource !== 'detecting' && locSource !== 'none' && (
              <>
                {displayDistrict}{displayState ? `, ${displayState}` : ''}
                {locSource === 'gps' && ' (auto-detected)'}
              </>
            )}
          </span>
          <span className="text-[10px] text-primary font-semibold">
            {locSource === 'detecting' ? '…' : 'Change'}
          </span>
        </button>

        {showLocPicker && (
          <div className="glass-card p-3 mt-2 space-y-2">
            <div className="flex justify-between items-center">
              <p className="text-xs font-bold text-muted-foreground">YOUR LOCATION</p>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => {
                    setShowLocPicker(false);
                    setLocSource('detecting');
                    if (navigator.geolocation) {
                      navigator.geolocation.getCurrentPosition(
                        (pos) => {
                          setLocCoords({ lat: pos.coords.latitude, lon: pos.coords.longitude });
                          setLocState('');
                          setLocDistrict('');
                          setLocSource('gps');
                          setLocVersion(v => v + 1);
                        },
                        () => setLocSource(locState ? 'manual' : 'none'),
                        { timeout: 5000 }
                      );
                    }
                  }}
                  className="text-[10px] font-bold text-primary"
                >
                  📍 Auto Detect
                </button>
                <button onClick={() => setShowLocPicker(false)}>
                  <X className="w-3.5 h-3.5 text-muted-foreground" />
                </button>
              </div>
            </div>
            <select
              value={locState}
              onChange={(e) => {
                const s = e.target.value;
                setLocState(s);
                const ds = getDistricts(s);
                setLocDistrict(ds.length ? ds[0] : '');
              }}
              className="w-full bg-secondary rounded px-3 py-2 text-sm"
            >
              <option value="">Select State</option>
              {allStates.map(s => <option key={s}>{s}</option>)}
            </select>
            <select
              value={locDistrict}
              onChange={(e) => setLocDistrict(e.target.value)}
              className="w-full bg-secondary rounded px-3 py-2 text-sm"
              disabled={!locState}
            >
              <option value="">Select District</option>
              {getDistricts(locState).map(d => <option key={d}>{d}</option>)}
            </select>
            <button
              onClick={() => {
                if (!locState || !locDistrict) return;
                setLocCoords(null);
                setLocSource('manual');
                setShowLocPicker(false);
                setLocVersion(v => v + 1);
              }}
              disabled={!locState || !locDistrict}
              className="w-full gradient-primary py-2 rounded-lg text-sm font-bold disabled:opacity-50"
            >
              Use This Location
            </button>
          </div>
        )}
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
          {displayDistrict && (
            <span className="text-[10px] font-semibold text-muted-foreground ml-2">
              for {displayDistrict}
            </span>
          )}
        </h2>

      <div className="space-y-2">
        {loadingRecs ? (
          <p className="text-xs text-muted-foreground">
            Loading recommendations for {displayDistrict || 'your area'}…
          </p>
        ) : recommendations.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            {locSource === 'none'
              ? 'Choose your state & district above to see recommendations.'
              : 'No recommendations available right now.'}
          </p>
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