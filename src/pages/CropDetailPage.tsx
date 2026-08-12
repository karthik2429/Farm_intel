import React, { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useLanguage } from '@/contexts/LanguageContext';
import { ArrowLeft, Droplets, Thermometer, Layers, TrendingUp, Clock, IndianRupee, ChevronDown, ChevronUp } from 'lucide-react';
import BottomNav from '@/components/BottomNav';
import cropRice from '@/assets/crop-rice.jpg';
import cropCotton from '@/assets/crop-cotton.jpg';
import cropSugarcane from '@/assets/crop-sugarcane.jpg';

const CropDetailPage: React.FC = () => {
  const { t } = useLanguage();
  const navigate = useNavigate();
  const location = useLocation();

  const [selectedCrop, setSelectedCrop] = useState<string | null>(null);

  // ✅ NEW DATA FORMAT (FROM PREVIOUS PAGE)
  const cropsData = location.state?.crops || [];

  // 🔥 MAP DATA
  const crops = cropsData.map((crop: any, index: number) => {
    const name = crop.name || crop[0];
    const score = crop.matchScore || Math.round((crop[1] || 0.8) * 100);

    return {
      id: name,
      name: name.charAt(0).toUpperCase() + name.slice(1),

      image:
        name === "rice"
          ? cropRice
          : name === "sugarcane"
          ? cropSugarcane
          : cropCotton,

      matchScore: score,

      duration: index === 0 ? "120 Days" : index === 1 ? "300 Days" : "150 Days",
      yield: index === 0 ? "4.8 t/ha" : index === 1 ? "80 t/ha" : "2.5 t/ha",
      waterNeeds: index === 0 ? "High" : index === 1 ? "Very High" : "Medium",

      profitPerAcre: "₹30,000",

      // 🔥 REAL API DATA
      mandiPrice: crop.mandiPrice,
      mandiMin: crop.mandiMin,
      mandiMax: crop.mandiMax,

      priceData: [30, 45, 40, 55, 50, 60, 55, 70, 65, 80, 75, 85],

      soilType: "Suitable soil conditions",
      temperature: "20°C - 35°C",
      irrigation: "Moderate irrigation required",
    };
  });

  const getScoreColor = (score: number) => {
    if (score >= 90) return 'text-green-500';
    if (score >= 80) return 'text-yellow-500';
    return 'text-orange-500';
  };

  const getScoreBg = (score: number) => {
    if (score >= 90) return 'bg-green-500/15 border-green-500/30';
    if (score >= 80) return 'bg-yellow-500/15 border-yellow-500/30';
    return 'bg-orange-500/15 border-orange-500/30';
  };

  return (
    <div className="min-h-screen bg-background pb-20">
      
      {/* HEADER */}
      <div className="px-5 pt-5 pb-3 flex items-center gap-3">
        <button onClick={() => navigate(-1)} className="w-8 h-8 rounded-full bg-secondary flex items-center justify-center">
          <ArrowLeft className="w-4 h-4 text-foreground" />
        </button>
        <div>
          <h1 className="text-lg font-extrabold text-foreground">
            {t('topCropRecommendations')}
          </h1>
          <p className="text-[10px] text-muted-foreground">
            Based on your soil, location & season
          </p>
        </div>
      </div>

      <div className="px-5 space-y-4">

        {/* CARDS */}
        {crops.map((crop, index) => {
          const isExpanded = selectedCrop === crop.id;

          return (
            <div
              key={crop.id}
              className={`glass-card overflow-hidden ${
                isExpanded ? 'ring-2 ring-primary/50' : ''
              }`}
            >

              {/* CLICK AREA */}
              <button
                onClick={() => setSelectedCrop(isExpanded ? null : crop.id)}
                className="w-full text-left"
              >
                <div className="flex gap-3 p-4">

                  {/* IMAGE */}
                  <div className="relative">
                    <img
                      src={crop.image}
                      className="w-16 h-16 rounded-xl object-cover"
                    />
                    <div className="absolute -top-1 -left-1 w-6 h-6 rounded-full gradient-primary flex items-center justify-center text-[10px] font-bold text-white">
                      #{index + 1}
                    </div>
                  </div>

                  {/* INFO */}
                  <div className="flex-1">
                    <div className="flex justify-between">
                      <div>
                        <h3 className="text-sm font-bold">{crop.name}</h3>
                        <p className="text-[10px] text-muted-foreground">
                          Recommended Variety
                        </p>
                      </div>

                      <div className={`px-2 py-1 rounded ${getScoreBg(crop.matchScore)}`}>
                        <span className={`text-xs font-bold ${getScoreColor(crop.matchScore)}`}>
                          {crop.matchScore}%
                        </span>
                      </div>
                    </div>

                    {/* STATS */}
                    <div className="flex gap-3 mt-2 text-[10px]">
                      <span className="flex items-center gap-1">
                        <TrendingUp className="w-3 h-3 text-primary" />
                        {crop.yield}
                      </span>
                      <span className="flex items-center gap-1">
                        <Clock className="w-3 h-3 text-primary" />
                        {crop.duration}
                      </span>
                      <span className="flex items-center gap-1">
                        <Droplets className="w-3 h-3 text-primary" />
                        {crop.waterNeeds}
                      </span>
                    </div>
                  </div>

                  {/* ARROW */}
                  <div className="flex items-center">
                    {isExpanded ? <ChevronUp /> : <ChevronDown />}
                  </div>
                </div>

                {/* 🔥 MANDI PRICE (REAL DATA) */}
                <div className="px-4 pb-3 flex justify-between">
                  <span className="text-[10px] text-muted-foreground">
                    ₹ Current Mandi Avg
                  </span>

                  <span className="text-xs font-bold text-primary">
                    ₹ {crop.mandiPrice ? crop.mandiPrice : "--"} / Quintal
                  </span>
                </div>

                {/* 🔥 MIN MAX */}
                {crop.mandiMin && (
                  <div className="px-4 pb-2 text-[10px] text-muted-foreground">
                    ₹{crop.mandiMin} - ₹{crop.mandiMax}
                  </div>
                )}
              </button>

              {/* EXPANDED */}
              {isExpanded && (
                <div className="px-4 pb-4 space-y-3">

                  {/* GRAPH */}
                  <div>
                    <h4 className="text-xs font-bold mb-2">Market Price Trend</h4>
                    <div className="h-16 flex gap-1 items-end">
                      {crop.priceData.map((h, i) => (
                        <div
                          key={i}
                          className="flex-1 bg-primary/20 rounded-t"
                          style={{ height: `${h}%` }}
                        />
                      ))}
                    </div>
                  </div>

                  {/* PROFIT */}
                  <div className="flex justify-between bg-primary/10 p-3 rounded-lg">
                    <span className="text-xs">Profit / Acre</span>
                    <span className="font-bold text-primary">{crop.profitPerAcre}</span>
                  </div>

                  {/* REQUIREMENTS */}
                  <div className="space-y-2">
                    <div className="flex gap-2 text-xs">
                      <Layers className="w-4 h-4 text-primary" />
                      {crop.soilType}
                    </div>
                    <div className="flex gap-2 text-xs">
                      <Thermometer className="w-4 h-4 text-primary" />
                      {crop.temperature}
                    </div>
                    <div className="flex gap-2 text-xs">
                      <Droplets className="w-4 h-4 text-primary" />
                      {crop.irrigation}
                    </div>
                  </div>

                  <button
                    onClick={() => navigate('/price-prediction')}
                    className="w-full gradient-primary py-2 rounded-lg font-bold"
                  >
                    Select This Crop →
                  </button>

                </div>
              )}
            </div>
          );
        })}
      </div>

      <BottomNav />
    </div>
  );
};

export default CropDetailPage;