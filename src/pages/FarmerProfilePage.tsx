import React, { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLanguage } from '@/contexts/LanguageContext';
import { useAuth } from '@/contexts/AuthContext';
import { languageNames, Language } from '@/lib/i18n';
import { allStates, getDistricts } from '@/lib/indian-locations';
import {
  ArrowLeft, Edit2, ChevronRight, Globe, Bell, Calendar, Shield, LogOut,
  Sprout, MapPin, Wheat, Apple, Banknote, User, Search, Locate, Loader2, Check, X
} from 'lucide-react';
import BottomNav from '@/components/BottomNav';
import { toast } from 'sonner';

const FarmerProfilePage: React.FC = () => {
  const { t, language, setLanguage } = useLanguage();
  const { user } = useAuth();
  const navigate = useNavigate();

  // Editing state
  const [editingSection, setEditingSection] = useState<string | null>(null);
  const [showLangPicker, setShowLangPicker] = useState(false);

  // Profile data (local state — you'll connect your backend later)
  const [name, setName] = useState(() => localStorage.getItem('profile_name') || user?.user_metadata?.full_name || user?.user_metadata?.name || '');
  const [state, setState] = useState(() => localStorage.getItem('profile_state') || '');
  const [district, setDistrict] = useState(() => localStorage.getItem('profile_district') || '');
  const [districtSearch, setDistrictSearch] = useState(() => localStorage.getItem('profile_district') || '');
  const [showDistrictDropdown, setShowDistrictDropdown] = useState(false);
  const [selectedCrops, setSelectedCrops] = useState<string[]>(() => {
    const saved = localStorage.getItem('profile_crops');
    return saved ? JSON.parse(saved) : ['cereals'];
  });
  const [detectingLocation, setDetectingLocation] = useState(false);

  const districts = useMemo(() => getDistricts(state), [state]);
  const filteredDistricts = useMemo(() => {
    if (!districtSearch) return districts;
    return districts.filter(d => d.toLowerCase().includes(districtSearch.toLowerCase()));
  }, [districts, districtSearch]);

  const cropTypes = [
    { id: 'cereals', label: t('cerealsGrains'), icon: Wheat, desc: 'Rice, Wheat, Bajra...' },
    { id: 'fruits', label: t('fruitsVegetables'), icon: Apple, desc: 'Tomato, Mango, Onion...' },
    { id: 'cash', label: t('cashCrops'), icon: Banknote, desc: 'Sugarcane, Cotton, Tobacco' },
  ];

  const toggleCrop = (id: string) => {
    setSelectedCrops(prev => prev.includes(id) ? prev.filter(c => c !== id) : [...prev, id]);
  };

  const selectDistrict = (d: string) => {
    setDistrict(d);
    setDistrictSearch(d);
    setShowDistrictDropdown(false);
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
      () => {
        setDetectingLocation(false);
        toast.error('Could not detect your location');
      },
      { enableHighAccuracy: true, timeout: 10000 }
    );
  };

  const stats = [
    { value: '12.5', label: 'Acres' },
    { value: '4.8', label: 'Rating' },
    { value: selectedCrops.length.toString(), label: 'Crops' },
  ];

  const menuItems = [
    { icon: Sprout, label: t('cropHistory'), path: '/crop-detail' },
    { icon: Bell, label: t('priceAlerts'), path: '/market' },
    { icon: Calendar, label: t('harvestSchedule'), path: '/crop-rotation' },
    { icon: Shield, label: t('privacySecurity'), path: '#' },
  ];

  return (
    <div className="min-h-screen bg-background pb-20">
      {/* Header */}
      <div className="px-5 pt-5 pb-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate(-1)} className="w-8 h-8 rounded-full bg-secondary flex items-center justify-center">
            <ArrowLeft className="w-4 h-4 text-foreground" />
          </button>
          <h1 className="text-lg font-extrabold text-foreground">{t('farmerProfile')}</h1>
        </div>
      </div>

      <div className="px-5 space-y-4">
        {/* Profile Card */}
        <div className="glass-card p-5 text-center">
          <div className="w-16 h-16 rounded-full gradient-primary mx-auto flex items-center justify-center text-2xl">
            👨‍🌾
          </div>
          <h2 className="text-base font-extrabold text-foreground mt-2">{name || 'Farmer'}</h2>
          <p className="text-xs text-muted-foreground">
            {district && state ? `${district}, ${state}` : state || t('location')}
          </p>
          <div className="flex justify-center gap-6 mt-4">
            {stats.map((s, i) => (
              <div key={i} className="text-center">
                <p className="text-lg font-extrabold text-foreground">{s.value}</p>
                <p className="text-[10px] text-muted-foreground">{s.label}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Editable: Name */}
        <div className="glass-card p-4">
          <div className="flex items-center justify-between mb-2">
            <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider">{t('yourName')}</label>
            <button onClick={() => { if (editingSection === 'name') { localStorage.setItem('profile_name', name); } setEditingSection(editingSection === 'name' ? null : 'name'); }} className="text-primary">
              {editingSection === 'name' ? <Check className="w-4 h-4" /> : <Edit2 className="w-4 h-4" />}
            </button>
          </div>
          {editingSection === 'name' ? (
            <div className="flex items-center gap-2 bg-secondary rounded-lg px-3 py-2.5">
              <User className="w-4 h-4 text-primary" />
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="flex-1 bg-transparent text-sm text-foreground outline-none"
                autoFocus
              />
            </div>
          ) : (
            <p className="text-sm font-semibold text-foreground">{name || '—'}</p>
          )}
        </div>

        {/* Editable: Language */}
        <div className="glass-card p-4">
          <div className="flex items-center justify-between mb-2">
            <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider">{t('preferredLanguage')}</label>
            <button onClick={() => setEditingSection(editingSection === 'language' ? null : 'language')} className="text-primary">
              {editingSection === 'language' ? <Check className="w-4 h-4" /> : <Globe className="w-4 h-4" />}
            </button>
          </div>
          {editingSection === 'language' ? (
            <div className="grid grid-cols-4 gap-2">
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
          ) : (
            <p className="text-sm font-semibold text-foreground">{languageNames[language]}</p>
          )}
        </div>

        {/* Editable: Location */}
        <div className="glass-card p-4">
          <div className="flex items-center justify-between mb-2">
            <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider">{t('location')}</label>
            <button onClick={() => { if (editingSection === 'location') { localStorage.setItem('profile_state', state); localStorage.setItem('profile_district', district); } setEditingSection(editingSection === 'location' ? null : 'location'); }} className="text-primary">
              {editingSection === 'location' ? <Check className="w-4 h-4" /> : <Edit2 className="w-4 h-4" />}
            </button>
          </div>
          {editingSection === 'location' ? (
            <div className="space-y-2">
              <div className="flex justify-end">
                <button
                  onClick={handleAutoDetect}
                  disabled={detectingLocation}
                  className="flex items-center gap-1 text-xs font-semibold text-primary disabled:opacity-60"
                >
                  {detectingLocation ? <Loader2 className="w-3 h-3 animate-spin" /> : <Locate className="w-3 h-3" />}
                  Auto Detect
                </button>
              </div>
              <div className="flex items-center gap-2 bg-secondary rounded-lg px-3 py-2.5">
                <MapPin className="w-4 h-4 text-primary" />
                <select
                  value={state}
                  onChange={(e) => { setState(e.target.value); setDistrict(''); setDistrictSearch(''); }}
                  className="flex-1 bg-transparent text-sm text-foreground outline-none"
                >
                  <option value="">Select State</option>
                  {allStates.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
              <div className="relative">
                <div className="flex items-center gap-2 bg-secondary rounded-lg px-3 py-2.5">
                  <Search className="w-4 h-4 text-primary" />
                  <input
                    type="text"
                    placeholder={state ? 'Type or search district...' : 'Select state first'}
                    value={districtSearch}
                    onChange={(e) => { setDistrictSearch(e.target.value); setDistrict(''); setShowDistrictDropdown(true); }}
                    onFocus={() => state && setShowDistrictDropdown(true)}
                    disabled={!state}
                    className="flex-1 bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground disabled:opacity-50"
                  />
                </div>
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
          ) : (
            <p className="text-sm font-semibold text-foreground">
              {district && state ? `${district}, ${state}` : state || '—'}
            </p>
          )}
        </div>

        {/* Editable: Crops */}
        <div className="glass-card p-4">
          <div className="flex items-center justify-between mb-2">
            <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider">{t('whatDoYouGrow')}</label>
            <button onClick={() => { if (editingSection === 'crops') { localStorage.setItem('profile_crops', JSON.stringify(selectedCrops)); } setEditingSection(editingSection === 'crops' ? null : 'crops'); }} className="text-primary">
              {editingSection === 'crops' ? <Check className="w-4 h-4" /> : <Edit2 className="w-4 h-4" />}
            </button>
          </div>
          {editingSection === 'crops' ? (
            <div className="space-y-2">
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
          ) : (
            <p className="text-sm font-semibold text-foreground">
              {selectedCrops.map(c => cropTypes.find(ct => ct.id === c)?.label).filter(Boolean).join(', ') || '—'}
            </p>
          )}
        </div>

        {/* Quick Menu */}
        <div className="space-y-1">
          {menuItems.map((item, i) => (
            <button
              key={i}
              onClick={() => item.path && navigate(item.path)}
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

      <BottomNav />
    </div>
  );
};

export default FarmerProfilePage;
