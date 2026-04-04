import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLanguage } from '@/contexts/LanguageContext';
import { ArrowLeft, Search, TrendingUp, TrendingDown } from 'lucide-react';
import BottomNav from '@/components/BottomNav';

const MarketPricesPage: React.FC = () => {
  const { t } = useLanguage();
  const navigate = useNavigate();
  const [searchQuery, setSearchQuery] = useState('');
  const [activeRegion, setActiveRegion] = useState('all');

  const regions = [
    { id: 'all', label: 'All India' },
    { id: 'karnataka', label: 'Karnataka' },
    { id: 'punjab', label: 'Punjab' },
    { id: 'maharashtra', label: 'Maharashtra' },
  ];

  const crops = [
    { name: 'Wheat (Banna)', price: '₹3,200', range: '₹1,235 - ₹2,450', location: 'Bhopal, Madhya Pradesh', trend: 'up' as const },
    { name: 'Tomato (Tamatar)', price: '₹1,300', range: '₹800 - ₹1,800', location: 'Nashik, Maharashtra', trend: 'up' as const },
    { name: 'Onion (Pyaz)', price: '₹1,500', range: '₹1,200 - ₹1,800', location: 'Lasalgaon, Maharashtra', trend: 'down' as const },
    { name: 'Cotton (Kapas)', price: '₹7,200', range: '₹6,500 - ₹7,800', location: 'Gujarat', trend: 'up' as const },
    { name: 'Rice (Basmati)', price: '₹4,200', range: '₹3,200 - ₹4,800', location: 'Karnal, Haryana', trend: 'up' as const },
  ];

  const filtered = crops.filter(c => c.name.toLowerCase().includes(searchQuery.toLowerCase()));

  return (
    <div className="min-h-screen bg-background pb-20">
      <div className="px-5 pt-5 pb-3">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate(-1)} className="w-8 h-8 rounded-full bg-secondary flex items-center justify-center">
            <ArrowLeft className="w-4 h-4 text-foreground" />
          </button>
          <div>
            <h1 className="text-lg font-extrabold text-foreground">{t('mandiPrices')}</h1>
            <p className="text-[10px] text-muted-foreground">{t('realTimeRates')}</p>
          </div>
        </div>
      </div>

      <div className="px-5 space-y-3">
        {/* Search */}
        <div className="flex items-center gap-2 bg-secondary rounded-lg px-3 py-2.5">
          <Search className="w-4 h-4 text-muted-foreground" />
          <input
            placeholder={`${t('search')} Basmati Rice...`}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="flex-1 bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground"
          />
        </div>

        {/* Region Tabs */}
        <div className="flex gap-2 overflow-x-auto no-scrollbar">
          {regions.map((r) => (
            <button
              key={r.id}
              onClick={() => setActiveRegion(r.id)}
              className={`px-3 py-1.5 rounded-full text-xs font-semibold whitespace-nowrap transition-all ${
                activeRegion === r.id ? 'gradient-primary text-primary-foreground' : 'bg-secondary text-secondary-foreground'
              }`}
            >
              {r.label}
            </button>
          ))}
        </div>

        {/* Trending */}
        <p className="text-xs font-bold text-muted-foreground">{t('trendingInDistrict')}</p>

        {/* Crop List */}
        <div className="space-y-2">
          {filtered.map((crop, i) => (
            <button
              key={i}
              onClick={() => navigate('/price-prediction')}
              className="w-full glass-card p-3 flex items-center gap-3 hover:bg-primary/5 transition-colors"
            >
              <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
                {crop.trend === 'up' ? (
                  <TrendingUp className="w-5 h-5 text-primary" />
                ) : (
                  <TrendingDown className="w-5 h-5 text-destructive" />
                )}
              </div>
              <div className="flex-1 text-left">
                <p className="text-sm font-bold text-foreground">{crop.name}</p>
                <p className="text-[10px] text-muted-foreground">{crop.location}</p>
              </div>
              <div className="text-right">
                <p className="text-sm font-bold text-foreground">{crop.price}</p>
                <p className="text-[10px] text-muted-foreground">{crop.range}</p>
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
