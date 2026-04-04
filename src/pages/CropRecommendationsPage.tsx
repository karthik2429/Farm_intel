import React, { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLanguage } from '@/contexts/LanguageContext';
import { ArrowLeft, MapPin, FlaskConical, Navigation, ChevronDown, Search } from 'lucide-react';
import { allStates, getDistricts } from '@/lib/indian-locations';
import { toast } from 'sonner';
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

  const [locationMode, setLocationMode] = useState<'current' | 'custom'>('current');
  const [selectedState, setSelectedState] = useState('Karnataka');
  const [selectedDistrict, setSelectedDistrict] = useState('Belagavi');
  const [districtSearch, setDistrictSearch] = useState('');
  const [showDistrictDropdown, setShowDistrictDropdown] = useState(false);
  const [detectingLocation, setDetectingLocation] = useState(false);

  const districts = useMemo(() => getDistricts(selectedState), [selectedState]);
  const filteredDistricts = useMemo(
    () => districts.filter(d => d.toLowerCase().includes(districtSearch.toLowerCase())),
    [districts, districtSearch]
  );

  const handleAutoDetect = () => {
    setDetectingLocation(true);
    if (!navigator.geolocation) {
      toast.error('Geolocation not supported');
      setDetectingLocation(false);
      return;
    }
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        try {
          const res = await fetch(
            `https://nominatim.openstreetmap.org/reverse?lat=${pos.coords.latitude}&lon=${pos.coords.longitude}&format=json&addressdetails=1`
          );
          const data = await res.json();
          const detectedState = data.address?.state || '';
          const detectedDistrict = data.address?.state_district || data.address?.county || '';
          const matchedState = allStates.find(s => detectedState.toLowerCase().includes(s.toLowerCase()));
          if (matchedState) {
            setSelectedState(matchedState);
            const dists = getDistricts(matchedState);
            const matchedDist = dists.find(d => detectedDistrict.toLowerCase().includes(d.toLowerCase()));
            if (matchedDist) setSelectedDistrict(matchedDist);
            else if (dists.length > 0) setSelectedDistrict(dists[0]);
          }
          toast.success(`📍 ${detectedDistrict}, ${detectedState}`);
        } catch {
          toast.error('Could not detect location');
        }
        setDetectingLocation(false);
      },
      () => { toast.error('Location access denied'); setDetectingLocation(false); }
    );
  };

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
        <div className="glass-card p-4 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <MapPin className="w-4 h-4 text-primary" />
              <span className="text-xs font-bold text-muted-foreground">{t('chooseLocation')}</span>
            </div>
            <button
              onClick={handleAutoDetect}
              disabled={detectingLocation}
              className="flex items-center gap-1 text-[10px] font-bold text-primary bg-primary/10 px-2.5 py-1 rounded-full"
            >
              <Navigation className="w-3 h-3" />
              {detectingLocation ? '...' : t('autoDetect')}
            </button>
          </div>

          {/* Mode toggle */}
          <div className="flex gap-2">
            <button
              onClick={() => setLocationMode('current')}
              className={`flex-1 py-2 rounded-lg text-xs font-semibold transition-all ${
                locationMode === 'current' ? 'gradient-primary text-primary-foreground' : 'bg-secondary text-secondary-foreground'
              }`}
            >
              {t('useCurrentLocation')}
            </button>
            <button
              onClick={() => setLocationMode('custom')}
              className={`flex-1 py-2 rounded-lg text-xs font-semibold transition-all ${
                locationMode === 'custom' ? 'gradient-primary text-primary-foreground' : 'bg-secondary text-secondary-foreground'
              }`}
            >
              {t('selectDistrict')}
            </button>
          </div>

          {locationMode === 'current' ? (
            <p className="text-sm font-semibold text-foreground">{selectedDistrict}, {selectedState}</p>
          ) : (
            <div className="space-y-2">
              <select
                value={selectedState}
                onChange={(e) => {
                  setSelectedState(e.target.value);
                  const d = getDistricts(e.target.value);
                  setSelectedDistrict(d[0] || '');
                  setDistrictSearch('');
                }}
                className="w-full bg-secondary rounded-lg px-3 py-2.5 text-sm text-foreground outline-none"
              >
                {allStates.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
              <div className="relative">
                <div className="flex items-center bg-secondary rounded-lg px-3">
                  <Search className="w-3.5 h-3.5 text-muted-foreground" />
                  <input
                    type="text"
                    value={districtSearch || selectedDistrict}
                    onChange={(e) => { setDistrictSearch(e.target.value); setShowDistrictDropdown(true); }}
                    onFocus={() => setShowDistrictDropdown(true)}
                    placeholder={t('selectDistrict')}
                    className="w-full bg-transparent py-2.5 px-2 text-sm text-foreground outline-none"
                  />
                </div>
                {showDistrictDropdown && filteredDistricts.length > 0 && (
                  <div className="absolute z-20 top-full left-0 right-0 mt-1 bg-card border border-border rounded-lg max-h-40 overflow-y-auto">
                    {filteredDistricts.map(d => (
                      <button
                        key={d}
                        onClick={() => { setSelectedDistrict(d); setDistrictSearch(''); setShowDistrictDropdown(false); }}
                        className="w-full text-left px-3 py-2 text-sm text-foreground hover:bg-secondary transition-colors"
                      >
                        {d}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
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
