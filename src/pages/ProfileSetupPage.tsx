import React, { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLanguage } from '@/contexts/LanguageContext';
import { useAuth } from '@/contexts/AuthContext';
import { languageNames, Language } from '@/lib/i18n';
import { allStates, getDistricts } from '@/lib/indian-locations';
import { MapPin, Wheat, Apple, Banknote, Locate, Loader2, Search, User } from 'lucide-react';
import { toast } from 'sonner';

const ProfileSetupPage: React.FC = () => {
  const { t, language, setLanguage } = useLanguage();
  const { user, loading: authLoading } = useAuth();
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [state, setState] = useState('');
  const [district, setDistrict] = useState('');
  const [districtSearch, setDistrictSearch] = useState('');
  const [showDistrictDropdown, setShowDistrictDropdown] = useState(false);
  const [selectedCrops, setSelectedCrops] = useState<string[]>(['cereals']);
  const [detectingLocation, setDetectingLocation] = useState(false);

  // Auto-fill name from Google OAuth metadata
  useEffect(() => {
    if (user) {
      const fullName =
        user.user_metadata?.full_name ||
        user.user_metadata?.name ||
        '';
      if (fullName) setName(fullName);
    }
  }, [user]);

  // Redirect to login if not authenticated
  useEffect(() => {
    if (!authLoading && !user) {
      navigate('/', { replace: true });
    }
  }, [user, authLoading, navigate]);

  const districts = useMemo(() => getDistricts(state), [state]);

  const filteredDistricts = useMemo(() => {
    if (!districtSearch) return districts;
    return districts.filter(d =>
      d.toLowerCase().includes(districtSearch.toLowerCase())
    );
  }, [districts, districtSearch]);

  const cropTypes = [
    { id: 'cereals', label: t('cerealsGrains'), icon: Wheat, desc: 'Rice, Wheat, Bajra...' },
    { id: 'fruits', label: t('fruitsVegetables'), icon: Apple, desc: 'Tomato, Mango, Onion...' },
    { id: 'cash', label: t('cashCrops'), icon: Banknote, desc: 'Sugarcane, Cotton, Tobacco' },
  ];

  const toggleCrop = (id: string) => {
    setSelectedCrops(prev => prev.includes(id) ? prev.filter(c => c !== id) : [...prev, id]);
  };

  const handleAutoDetect = () => {
    if (!navigator.geolocation) {
      toast.error('Geolocation is not supported by your browser');
      return;
    }

    setDetectingLocation(true);
    navigator.geolocation.getCurrentPosition(
      async (position) => {
        try {
          const { latitude, longitude } = position.coords;
          const response = await fetch(
            `https://nominatim.openstreetmap.org/reverse?format=json&lat=${latitude}&lon=${longitude}&addressdetails=1&accept-language=en`
          );
          const data = await response.json();
          const address = data.address;

          if (address?.state) {
            const matchedState = allStates.find(s =>
              s.toLowerCase() === address.state.toLowerCase() ||
              address.state.toLowerCase().includes(s.toLowerCase())
            );
            if (matchedState) {
              setState(matchedState);
              if (address.state_district || address.county) {
                const detectedDistrict = address.state_district || address.county;
                const stateDistricts = getDistricts(matchedState);
                const matchedDistrict = stateDistricts.find(d =>
                  d.toLowerCase() === detectedDistrict.toLowerCase() ||
                  detectedDistrict.toLowerCase().includes(d.toLowerCase()) ||
                  d.toLowerCase().includes(detectedDistrict.toLowerCase())
                );
                if (matchedDistrict) {
                  setDistrict(matchedDistrict);
                  setDistrictSearch(matchedDistrict);
                }
              }
              toast.success(`Location detected: ${matchedState}`);
            } else {
              toast.info(`Detected: ${address.state}. Please select manually.`);
            }
          } else {
            toast.error('Could not determine your state');
          }
        } catch {
          toast.error('Failed to detect location');
        }
        setDetectingLocation(false);
      },
      (error) => {
        setDetectingLocation(false);
        if (error.code === error.PERMISSION_DENIED) {
          toast.error('Location permission denied. Please select manually.');
        } else {
          toast.error('Could not detect your location');
        }
      },
      { enableHighAccuracy: true, timeout: 10000 }
    );
  };

  const selectDistrict = (d: string) => {
    setDistrict(d);
    setDistrictSearch(d);
    setShowDistrictDropdown(false);
  };

  if (authLoading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background px-5 py-6 pb-8">
      <h1 className="text-xl font-extrabold text-foreground">{t('namaste')} 🙏</h1>
      <p className="text-xs text-muted-foreground mt-1">{t('letsSetup')}</p>

      {/* Name */}
      <div className="mt-5">
        <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider">{t('yourName')}</label>
        <div className="flex items-center gap-2 bg-secondary rounded-lg px-3 py-2.5 mt-2">
          <User className="w-4 h-4 text-primary" />
          <input
            type="text"
            placeholder={t('enterYourName')}
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="flex-1 bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground"
            maxLength={100}
          />
        </div>
      </div>

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
        <div className="flex items-center justify-between">
          <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider">{t('location')}</label>
          <button
            onClick={handleAutoDetect}
            disabled={detectingLocation}
            className="flex items-center gap-1 text-xs font-semibold text-primary hover:text-primary/80 transition-colors disabled:opacity-60"
          >
            {detectingLocation ? (
              <Loader2 className="w-3 h-3 animate-spin" />
            ) : (
              <Locate className="w-3 h-3" />
            )}
            Auto Detect
          </button>
        </div>
        <div className="space-y-2 mt-2">
          {/* State selector */}
          <div className="flex items-center gap-2 bg-secondary rounded-lg px-3 py-2.5">
            <MapPin className="w-4 h-4 text-primary" />
            <select
              value={state}
              onChange={(e) => {
                setState(e.target.value);
                setDistrict('');
                setDistrictSearch('');
              }}
              className="flex-1 bg-transparent text-sm text-foreground outline-none"
            >
              <option value="">Select State</option>
              {allStates.map(s => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>

          {/* District searchable input */}
          <div className="relative">
            <div className="flex items-center gap-2 bg-secondary rounded-lg px-3 py-2.5">
              <Search className="w-4 h-4 text-primary" />
              <input
                type="text"
                placeholder={state ? 'Type or search district...' : 'Select state first'}
                value={districtSearch}
                onChange={(e) => {
                  setDistrictSearch(e.target.value);
                  setDistrict('');
                  setShowDistrictDropdown(true);
                }}
                onFocus={() => state && setShowDistrictDropdown(true)}
                disabled={!state}
                className="flex-1 bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground disabled:opacity-50"
              />
            </div>

            {/* District dropdown */}
            {showDistrictDropdown && filteredDistricts.length > 0 && (
              <div className="absolute z-20 top-full left-0 right-0 mt-1 bg-card border border-border rounded-lg shadow-lg max-h-48 overflow-y-auto">
                {filteredDistricts.map(d => (
                  <button
                    key={d}
                    onClick={() => selectDistrict(d)}
                    className={`w-full text-left px-3 py-2 text-sm hover:bg-secondary transition-colors ${
                      d === district ? 'text-primary font-semibold bg-primary/10' : 'text-foreground'
                    }`}
                  >
                    {d}
                  </button>
                ))}
              </div>
            )}
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
        onClick={() => { if (name) localStorage.setItem('profile_name', name); if (state) localStorage.setItem('profile_state', state); if (district) localStorage.setItem('profile_district', district); localStorage.setItem('profile_crops', JSON.stringify(selectedCrops)); navigate('/home'); }}
        className="w-full gradient-primary text-primary-foreground py-3 rounded-xl font-bold text-sm mt-6 hover:opacity-90 transition-opacity"
      >
        {t('completeSetup')} →
      </button>

      <p className="text-[10px] text-muted-foreground text-center mt-3">{t('agreeAlerts')}</p>
    </div>
  );
};

export default ProfileSetupPage;
