import React, { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLanguage } from '@/contexts/LanguageContext';
import { ArrowLeft, Search, TrendingUp, TrendingDown } from 'lucide-react';
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
  const [marketData, setMarketData] = useState<any[]>([]);

  // 🔥 NEW STATE + DISTRICT
  const [selectedState, setSelectedState] = useState("Karnataka");
  const [selectedDistrict, setSelectedDistrict] = useState("");

  const districts = useMemo(() => getDistricts(selectedState), [selectedState]);

  const regions = [
    { id: 'all', label: 'All India' },
    { id: 'karnataka', label: 'Karnataka' },
    { id: 'punjab', label: 'Punjab' },
    { id: 'maharashtra', label: 'Maharashtra' },
  ];

  // 🔥 REGION DISTRICTS
  const regionDistrictMap: Record<string, string[]> = {
    all: ["Bhopal", "Nashik", "Lasalgaon", "Rajkot", "Karnal"],

    karnataka: ["Koppal", "Belagavi", "Mysuru", "Tumakuru"],
    maharashtra: ["Nashik", "Lasalgaon", "Pune", "Nagpur"],
    punjab: ["Ludhiana", "Amritsar", "Patiala"],
  };

  const cropsList = [
    { name: 'Wheat', display: 'Wheat (Banna)', district: 'Bhopal, Madhya Pradesh' },
    { name: 'Tomato', display: 'Tomato (Tamatar)', district: 'Nashik, Maharashtra' },
    { name: 'Onion', display: 'Onion (Pyaz)', district: 'Lasalgaon, Maharashtra' },
    { name: 'Cotton', display: 'Cotton (Kapas)', district: 'Rajkot, Gujarat' },
    { name: 'Rice', display: 'Rice (Basmati)', district: 'Karnal, Haryana' },
  ];

  // 🔥 FINAL DATA FETCH
  useEffect(() => {
    const loadMarket = async () => {

      const regionDistricts = regionDistrictMap[activeRegion] || [];

      const results = await Promise.all(
        cropsList.map(async (item, i) => {

          let district = "";

          // ✅ PRIORITY SYSTEM
          if (selectedDistrict) {
            district = selectedDistrict; // user choice
          } else if (activeRegion !== "all") {
            district = regionDistricts[i % regionDistricts.length];
          } else {
            district = item.district.split(",")[0];
          }

          const mapped = mapCropName(item.name);

          const data = await getMarketPrice(mapped, district);

          return {
            ...item,
            district,
            price: data?.modal ?? null,
            min: data?.min ?? null,
            max: data?.max ?? null,
            trend: Math.random() > 0.5 ? 'up' : 'down',
          };
        })
      );

      console.log("FINAL MARKET:", results);
      setMarketData(results);
    };

    loadMarket();
  }, [activeRegion, selectedDistrict]);

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
            <button
              key={i}
              onClick={() => navigate('/price-prediction')}
              className="w-full glass-card p-3 flex items-center gap-3"
            >

              <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
                {crop.trend === 'up'
                  ? <TrendingUp className="text-primary" />
                  : <TrendingDown className="text-destructive" />}
              </div>

              <div className="flex-1 text-left">
                <p className="text-sm font-bold">{crop.display}</p>
                <p className="text-[10px] text-muted-foreground">{crop.district}</p>
              </div>

              <div className="text-right">
                <p className="text-sm font-bold">
                  ₹ {crop.price ?? "--"}
                </p>
                <p className="text-[10px] text-muted-foreground">
                  ₹{crop.min ?? "--"} - ₹{crop.max ?? "--"}
                </p>
              </div>

            </button>
          ))}

        </div>
      </div>

      <BottomNav />
    </div>
  );
};

export default MarketPricesPage;