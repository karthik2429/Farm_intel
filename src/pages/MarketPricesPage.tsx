import React, { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLanguage } from '@/contexts/LanguageContext';
import { ArrowLeft, Search, TrendingUp, TrendingDown, MapPin } from 'lucide-react';
import BottomNav from '@/components/BottomNav';

import { getMarketPrice } from '@/lib/marketApi';
import { mapCropName } from '@/lib/cropMap';

// 🔥 IMPORT STATES
import { allStates, getDistricts } from '@/lib/indian-locations';

const MarketPricesPage: React.FC = () => {
  const { t } = useLanguage();
  const navigate = useNavigate();

  const [searchQuery, setSearchQuery] = useState('');
  const [activeRegion, setActiveRegion] = useState('all');
  interface MarketRow {
    name: string; display: string; district: string;
    price: number | null; min: number | null; max: number | null;
    market: string; date: string; source: string; trend: string;
    badge: string; isReal: boolean;
  }
  const [marketData, setMarketData] = useState<MarketRow[]>([]);

  // 🔥 NEW STATE + DISTRICT — default to the farmer's saved profile
  const [selectedState, setSelectedState] = useState(
    () => localStorage.getItem('profile_state') || "Karnataka"
  );
  const [selectedDistrict, setSelectedDistrict] = useState(
    () => localStorage.getItem('profile_district') || ""
  );

  const districts = useMemo(() => getDistricts(selectedState), [selectedState]);

  const regions = [
    { id: 'all', label: 'All India' },
    { id: 'karnataka', label: 'Karnataka' },
    { id: 'punjab', label: 'Punjab' },
    { id: 'maharashtra', label: 'Maharashtra' },
  ];

  const regionStateMap: Record<string, string> = {
    all: '',
    karnataka: 'Karnataka',
    punjab: 'Punjab',
    maharashtra: 'Maharashtra',
  };

  const cropsList = [
    { name: 'Wheat', display: 'Wheat (Banna)', district: 'Bhopal' },
    { name: 'Tomato', display: 'Tomato (Tamatar)', district: 'Nashik' },
    { name: 'Onion', display: 'Onion (Pyaz)', district: 'Lasalgaon' },
    { name: 'Cotton', display: 'Cotton (Kapas)', district: 'Rajkot' },
    { name: 'Rice', display: 'Rice (Basmati)', district: 'Karnal' },
  ];

  // 🔥 FINAL DATA FETCH
  useEffect(() => {
    const loadMarket = async () => {

      const stateDistricts = getDistricts(selectedState);

      const results = await Promise.all(
        cropsList.map(async (item, i) => {

          let district = "";
          let state = regionStateMap[activeRegion] || undefined;

          // ✅ PRIORITY SYSTEM
          if (selectedDistrict) {
            district = selectedDistrict;          // user choice
            state = selectedState;                // disambiguate same-name districts
          } else if (activeRegion !== 'all') {
            // real districts of the region's state, cycled per crop
            const ds = getDistricts(regionStateMap[activeRegion]);
            district = ds.length ? ds[i % ds.length] : item.district;
          } else if (stateDistricts.length) {
            // All India: cycle through the selected state's own districts so
            // prices actually differ per crop row
            district = stateDistricts[i % stateDistricts.length];
            state = selectedState;
          } else {
            district = item.district;
          }

          const mapped = mapCropName(item.name);

          const data = await getMarketPrice(mapped, district, state);

          return {
            ...item,
            district: state ? `${district}, ${state}` : district,
            price: data?.modal ?? null,
            min: data?.min ?? null,
            max: data?.max ?? null,
            market: data?.market ?? '',
            date: data?.date ?? '',
            source: data?.source ?? '',
            badge: data?.badge ?? '',
            isReal: data?.is_real !== false,
            trend: data?.max && data?.min && data?.modal != null
              ? (data.modal >= (data.max + data.min) / 2 ? 'up' : 'down')
              : '',
          };
        })
      );

      setMarketData(results);
    };

    loadMarket();
  }, [activeRegion, selectedState, selectedDistrict]);

  // 🔍 SEARCH
  const filtered = marketData.filter(c =>
    c.display.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="min-h-screen bg-background pb-20">

      {/* HEADER */}
      <div className="px-5 pt-5 pb-3 flex items-center gap-3">
        <button onClick={() => navigate(-1)} className="w-8 h-8 rounded-full bg-secondary flex items-center justify-center">
          <ArrowLeft className="w-4 h-4 text-foreground" />
        </button>
        <div>
          <h1 className="text-lg font-extrabold">{t('mandiPrices')}</h1>
          <p className="text-[10px] text-muted-foreground">{t('realTimeRates')}</p>
        </div>
      </div>

      <div className="px-5 space-y-3">

        {/* SEARCH */}
        <div className="flex items-center gap-2 bg-secondary rounded-lg px-3 py-2.5">
          <Search className="w-4 h-4 text-muted-foreground" />
          <input
            placeholder="Search crop..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="flex-1 bg-transparent text-sm outline-none"
          />
        </div>

        {/* 🔥 STATE + DISTRICT */}
        <div className="flex gap-2">

          <select
            value={selectedState}
            onChange={(e) => {
              setSelectedState(e.target.value);
              setSelectedDistrict("");
            }}
            className="bg-secondary rounded px-3 py-2 text-sm"
          >
            {allStates.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>

          <select
            value={selectedDistrict}
            onChange={(e) => setSelectedDistrict(e.target.value)}
            className="bg-secondary rounded px-3 py-2 text-sm"
          >
            <option value="">Select District</option>
            {districts.map((d) => (
              <option key={d}>{d}</option>
            ))}
          </select>

        </div>

        {/* REGIONS */}
        <div className="flex gap-2 overflow-x-auto no-scrollbar">
          {regions.map((r) => (
            <button
              key={r.id}
              onClick={() => setActiveRegion(r.id)}
              className={`px-3 py-1.5 rounded-full text-xs font-semibold ${
                activeRegion === r.id
                  ? 'gradient-primary text-white'
                  : 'bg-secondary'
              }`}
            >
              {r.label}
            </button>
          ))}
        </div>

        <p className="text-xs font-bold text-muted-foreground">
          {t('trendingInDistrict')}
        </p>

        {/* LIST */}
        <div className="space-y-2">

          {!marketData.length && (
            <p className="text-xs text-muted-foreground">Loading...</p>
          )}

          {filtered.map((crop, i) => (
            <div
              key={i}
              className="w-full glass-card p-3 flex items-center gap-3"
            >

              <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
                {crop.trend === 'up'
                  ? <TrendingUp className="text-primary" />
                  : crop.trend === 'down'
                    ? <TrendingDown className="text-destructive" />
                    : <MapPin className="text-muted-foreground" />}
              </div>

              <div className="flex-1 text-left">
                <p className="text-sm font-bold">{crop.display}</p>
                <p className="text-[10px] text-muted-foreground">{crop.district}</p>
                {crop.market && (
                  <p className="text-[10px] text-muted-foreground truncate max-w-[180px]">
                    {crop.market}{crop.date ? ` · ${crop.date}` : ''}
                  </p>
                )}
              </div>

              <div className="text-right">
                <p className="text-sm font-bold">
                  ₹ {crop.price ?? "--"}
                </p>
                <p className="text-[10px] text-muted-foreground">
                  {crop.min != null ? `₹${crop.min} - ₹${crop.max}` : "--"}
                </p>
                {crop.price == null ? (
                  <p className="text-[9px] font-semibold text-amber-600">Unavailable</p>
                ) : crop.source === 'msp_reference' ? (
                  <p className="text-[9px] font-semibold text-amber-600">MSP reference</p>
                ) : (
                  <p className="text-[9px] font-semibold text-green-700">Real mandi data</p>
                )}
              </div>

            </div>
          ))}

        </div>
      </div>

      <BottomNav />
    </div>
  );
};

export default MarketPricesPage;