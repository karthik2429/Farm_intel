import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLanguage } from '@/contexts/LanguageContext';
import { ArrowLeft, Droplets, Thermometer, Layers, TrendingUp, Clock, Sprout, IndianRupee, ChevronDown, ChevronUp } from 'lucide-react';
import BottomNav from '@/components/BottomNav';
import cropRice from '@/assets/crop-rice.jpg';
import cropCotton from '@/assets/crop-cotton.jpg';
import cropSugarcane from '@/assets/crop-sugarcane.jpg';

interface CropData {
  id: string;
  name: string;
  variety: string;
  image: string;
  matchScore: number;
  season: string;
  duration: string;
  yield: string;
  waterNeeds: string;
  profitPerAcre: string;
  mandiPrice: string;
  priceData: number[];
  soilType: string;
  temperature: string;
  irrigation: string;
}

const CropDetailPage: React.FC = () => {
  const { t } = useLanguage();
  const navigate = useNavigate();
  const [selectedCrop, setSelectedCrop] = useState<string | null>(null);

  const crops: CropData[] = [
    {
      id: 'rice',
      name: 'Basmati Rice',
      variety: 'Pusa-1121',
      image: cropRice,
      matchScore: 95,
      season: 'Kharif',
      duration: '120 Days',
      yield: '4.8 t/ha',
      waterNeeds: 'High',
      profitPerAcre: '₹32,000',
      mandiPrice: '₹4,250 / Quintal',
      priceData: [30, 45, 40, 55, 50, 60, 55, 70, 65, 80, 75, 85],
      soilType: 'Loamy, well-drained (Sandy Loam, Clay Loam)',
      temperature: '20°C - 35°C ideal range',
      irrigation: 'Standing water (5-10cm) during vegetative phase',
    },
    {
      id: 'sugarcane',
      name: 'Sugarcane',
      variety: 'Co-0238',
      image: cropSugarcane,
      matchScore: 87,
      season: 'Kharif',
      duration: '300 Days',
      yield: '80 t/ha',
      waterNeeds: 'Very High',
      profitPerAcre: '₹55,000',
      mandiPrice: '₹3,150 / Quintal',
      priceData: [40, 42, 45, 48, 50, 55, 52, 58, 60, 62, 65, 70],
      soilType: 'Deep rich loamy soil with good drainage',
      temperature: '21°C - 27°C optimal',
      irrigation: 'Furrow irrigation every 10-15 days',
    },
    {
      id: 'cotton',
      name: 'Cotton',
      variety: 'Bt Cotton (Bollgard II)',
      image: cropCotton,
      matchScore: 78,
      season: 'Kharif',
      duration: '150 Days',
      yield: '2.5 t/ha',
      waterNeeds: 'Medium',
      profitPerAcre: '₹28,000',
      mandiPrice: '₹6,800 / Quintal',
      priceData: [50, 48, 55, 60, 58, 65, 62, 70, 68, 75, 72, 80],
      soilType: 'Black cotton soil, well-drained alluvial',
      temperature: '21°C - 30°C during growth',
      irrigation: 'Drip irrigation preferred, moderate water',
    },
  ];

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
      {/* Header */}
      <div className="px-5 pt-5 pb-3 flex items-center gap-3">
        <button onClick={() => navigate(-1)} className="w-8 h-8 rounded-full bg-secondary flex items-center justify-center">
          <ArrowLeft className="w-4 h-4 text-foreground" />
        </button>
        <div>
          <h1 className="text-lg font-extrabold text-foreground">{t('topCropRecommendations')}</h1>
          <p className="text-[10px] text-muted-foreground">Based on your soil, location & season</p>
        </div>
      </div>

      <div className="px-5 space-y-4">
        {/* Top 3 Crop Cards */}
        {crops.map((crop, index) => {
          const isExpanded = selectedCrop === crop.id;
          return (
            <div
              key={crop.id}
              className={`glass-card overflow-hidden transition-all duration-300 ${
                isExpanded ? 'ring-2 ring-primary/50' : ''
              }`}
            >
              {/* Card Header - Always Visible */}
              <button
                onClick={() => setSelectedCrop(isExpanded ? null : crop.id)}
                className="w-full text-left"
              >
                <div className="flex gap-3 p-4">
                  {/* Rank Badge */}
                  <div className="relative flex-shrink-0">
                    <img
                      src={crop.image}
                      alt={crop.name}
                      className="w-16 h-16 rounded-xl object-cover"
                      width={64}
                      height={64}
                    />
                    <div className="absolute -top-1.5 -left-1.5 w-6 h-6 rounded-full gradient-primary flex items-center justify-center">
                      <span className="text-[10px] font-black text-primary-foreground">#{index + 1}</span>
                    </div>
                  </div>

                  {/* Crop Info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between">
                      <div>
                        <h3 className="text-sm font-extrabold text-foreground">{crop.name}</h3>
                        <p className="text-[10px] text-muted-foreground">{crop.variety}</p>
                      </div>
                      <div className={`px-2 py-1 rounded-lg border ${getScoreBg(crop.matchScore)}`}>
                        <span className={`text-xs font-black ${getScoreColor(crop.matchScore)}`}>
                          {crop.matchScore}%
                        </span>
                      </div>
                    </div>

                    {/* Quick Stats */}
                    <div className="flex gap-3 mt-2">
                      <div className="flex items-center gap-1">
                        <TrendingUp className="w-3 h-3 text-primary" />
                        <span className="text-[10px] text-muted-foreground">{crop.yield}</span>
                      </div>
                      <div className="flex items-center gap-1">
                        <Clock className="w-3 h-3 text-primary" />
                        <span className="text-[10px] text-muted-foreground">{crop.duration}</span>
                      </div>
                      <div className="flex items-center gap-1">
                        <Droplets className="w-3 h-3 text-primary" />
                        <span className="text-[10px] text-muted-foreground">{crop.waterNeeds}</span>
                      </div>
                    </div>
                  </div>

                  {/* Expand indicator */}
                  <div className="flex items-center">
                    {isExpanded ? (
                      <ChevronUp className="w-4 h-4 text-muted-foreground" />
                    ) : (
                      <ChevronDown className="w-4 h-4 text-muted-foreground" />
                    )}
                  </div>
                </div>

                {/* Price Strip */}
                <div className="px-4 pb-3 flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <IndianRupee className="w-3 h-3 text-primary" />
                    <span className="text-[10px] text-muted-foreground">{t('currentMandiAvg')}</span>
                  </div>
                  <span className="text-xs font-bold text-primary">{crop.mandiPrice}</span>
                </div>
              </button>

              {/* Expanded Details */}
              {isExpanded && (
                <div className="border-t border-border/50 px-4 pb-4 space-y-4 animate-in slide-in-from-top-2 duration-200">
                  {/* Market Price Chart */}
                  <div className="pt-3">
                    <h4 className="text-xs font-bold text-foreground mb-2">{t('marketPriceTrend')}</h4>
                    <div className="h-16 flex items-end gap-[3px]">
                      {crop.priceData.map((h, i) => (
                        <div
                          key={i}
                          className="flex-1 rounded-t transition-all"
                          style={{
                            height: `${h}%`,
                            background: i === crop.priceData.length - 1
                              ? 'hsl(152 65% 45%)'
                              : 'hsl(152 65% 45% / 0.25)',
                          }}
                        />
                      ))}
                    </div>
                    <div className="flex justify-between text-[9px] text-muted-foreground mt-1">
                      <span>Jan</span><span>Jun</span><span>Dec</span>
                    </div>
                  </div>

                  {/* Profit Highlight */}
                  <div className="flex items-center justify-between bg-primary/5 rounded-xl p-3">
                    <span className="text-xs font-semibold text-foreground">{t('profitPerAcre')}</span>
                    <span className="text-sm font-black text-primary">{crop.profitPerAcre}</span>
                  </div>

                  {/* Cultivation Requirements */}
                  <div>
                    <h4 className="text-xs font-bold text-foreground mb-2">{t('cultivationRequirements')}</h4>
                    <div className="space-y-2">
                      {[
                        { icon: Layers, label: t('soilType'), value: crop.soilType },
                        { icon: Thermometer, label: t('temperature'), value: crop.temperature },
                        { icon: Droplets, label: t('irrigation'), value: crop.irrigation },
                      ].map((req, i) => (
                        <div key={i} className="flex gap-2.5 items-start">
                          <div className="w-7 h-7 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
                            <req.icon className="w-3.5 h-3.5 text-primary" />
                          </div>
                          <div>
                            <p className="text-[10px] font-bold text-foreground">{req.label}</p>
                            <p className="text-[9px] text-muted-foreground leading-relaxed">{req.value}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Select Button */}
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      // This is where the user's model will be connected
                      navigate('/price-prediction');
                    }}
                    className="w-full gradient-primary text-primary-foreground py-2.5 rounded-xl font-bold text-sm hover:opacity-90 transition-opacity"
                  >
                    {t('selectThisCrop')} →
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
