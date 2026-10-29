import React, { useEffect, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useLanguage } from '@/contexts/LanguageContext';
import { ArrowLeft, Droplets, Thermometer, Layers, TrendingUp, Clock, IndianRupee, ChevronDown, ChevronUp } from 'lucide-react';
import BottomNav from '@/components/BottomNav';
import cropRice from '@/assets/crop-rice.jpg';
import cropCotton from '@/assets/crop-cotton.jpg';
import cropSugarcane from '@/assets/crop-sugarcane.jpg';
import { getCropInfo, getMarketHistory, type CropInfo, type MarketHistory } from '@/lib/marketApi';

const CropDetailPage: React.FC = () => {
  const { t } = useLanguage();
  const navigate = useNavigate();
  const location = useLocation();

  const [selectedCrop, setSelectedCrop] = useState<string | null>(null);

  // ✅ NEW DATA FORMAT (FROM PREVIOUS PAGE)
  const cropsData: any[] = location.state?.crops || [];
  const district: string | undefined = location.state?.district;

  // Real agronomy + mandi history, fetched once for the recommended crops.
  // Anything missing stays missing ("--") - no fabricated defaults.
  const [infoByCrop, setInfoByCrop] = useState<Record<string, CropInfo | null>>({});
  const [historyByCrop, setHistoryByCrop] = useState<Record<string, MarketHistory | null>>({});

  useEffect(() => {
    if (!cropsData.length) return;
    let cancelled = false;
    const names = cropsData.map((c) => c.name || c[0]).filter(Boolean);

    getCropInfo(names)
      .then((res) => {
        if (cancelled || !res) { setInfoByCrop(Object.fromEntries(names.map((n) => [n, null])));
          return; }
        setInfoByCrop(res.crops);
      })
      .catch(() => !cancelled && setInfoByCrop(Object.fromEntries(names.map((n) => [n, null]))));

    Promise.all(
      names.map(async (n) => {
        const mapped = n.toLowerCase() === 'rice' ? 'Paddy'
          : n.charAt(0).toUpperCase() + n.slice(1);
        const h = await getMarketHistory(mapped, district, 60);
        return [n, h as MarketHistory | null];
      })
    )
      .then((entries) => !cancelled && setHistoryByCrop(Object.fromEntries(entries)))
      .catch(() => {});

    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const cropImage = (name: string) =>
    name === 'rice' ? cropRice
      : name === 'sugarcane' ? cropSugarcane
      : cropCotton;

  const periodText = (info?: CropInfo | null) => {
    const d = info?.duration_days;
    if (d && d[0] > 0 && d[1] > 0) {
      if (info?.perennial && info?.maturity_note) return info.maturity_note;
      const m1 = Math.round(d[0] / 30.4);
      const m2 = Math.round(d[1] / 30.4);
      return m1 === m2 ? `${m1} months` : `${m1}-${m2} months`;
    }
    return info?.maturity_note || null;
  };

  const yieldText = (info?: CropInfo | null) => {
    const y = info?.yield_t_ha;
    if (y && y[0] > 0 && y[1] > 0) {
      const f = (v: number) => (v % 1 === 0 ? v : v.toFixed(1));
      return y[0] === y[1] ? `${f(y[0])} t/ha` : `${f(y[0])}-${f(y[1])} t/ha`;
    }
    return null;
  };

  // Estimated gross revenue per acre from the real yield band x today's
  // real mandi price. 1 t/ha = ~4.05 quintals per acre.
  const revenuePerAcre = (info?: CropInfo | null, price?: number | null) => {
    const y = info?.yield_t_ha;
    if (!y || !price || y[1] <= 0) return null;
    const q = (t_ha: number) => t_ha * 4.05 * price;
    const fmt = (v: number) => `₹${Math.round(v).toLocaleString('en-IN')}`;
    return y[0] > 0 ? `${fmt(q(y[0]))} - ${fmt(q(y[1]))}` : `${fmt(q(y[1]))}`;
  };

  // 🔥 MAP DATA - every value either real or clearly absent
  const crops = cropsData.map((crop: any, index: number) => {
    const rawName = (crop.name || crop[0]) as string;
    const score = crop.matchScore
      || Math.round((crop.confidence ?? crop[1] ?? 0.8) * 100);
    const info = infoByCrop[rawName] ?? null;
    const history = historyByCrop[rawName] ?? null;

    return {
      id: rawName,
      name: rawName.charAt(0).toUpperCase() + rawName.slice(1),
      image: cropImage(rawName),
      matchScore: score,

      // REAL agronomy (bundled crop master + ICAR/MoAFW reference table)
      duration: periodText(info),
      yield: yieldText(info),
      waterNeeds: info?.water_needs || null,
      soilType: info?.soil_type || null,
      temperature: info?.temp_range_c || null,
      irrigation: info?.rainfall_range_mm
        ? `${info.rainfall_range_mm} rainfall need`
        : null,

      // Est. gross revenue/acre: real yield band x real mandi price,
      // labelled "est." in the UI - never shown as a guaranteed profit.
      revenuePerAcre: revenuePerAcre(info, crop.mandiPrice),

      // 🔥 REAL API DATA
      mandiPrice: crop.mandiPrice,
      mandiMin: crop.mandiMin,
      mandiMax: crop.mandiMax,

      // REAL history series (may be empty if the store has none yet)
      priceHistory: history,
      minHeight: index + 1,
    };
  });

  // Normalize a history series into chart bars (last series of ≤14 points)
  const chartBars = (history?: MarketHistory | null) => {
    if (!history || !history.points?.length) return null;
    const pts = history.points.slice(-14);
    const min = Math.min(...pts.map((p) => p.price));
    const max = Math.max(...pts.map((p) => p.price));
    const range = max - min || min;
    return {
      bars: pts.map((p) =>
        range <= 0 ? 100 : 20 + ((p.price - min) / range) * 80),
      highlightIndex: pts.length - 1,
      dateFrom: pts[0].date,
      dateTo: pts[pts.length - 1].date,
      latest: pts[pts.length - 1].price,
      scope: history.scope,
      total: history.points.length,
      days: history.days,
    };
  };


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

                    {/* STATS (real agronomy; missing values show "--") */}
                    <div className="flex gap-3 mt-2 text-[10px]">
                      <span className="flex items-center gap-1">
                        <TrendingUp className="w-3 h-3 text-primary" />
                        {crop.yield || '--'}
                      </span>
                      <span className="flex items-center gap-1">
                        <Clock className="w-3 h-3 text-primary" />
                        {crop.duration || '--'}
                      </span>
                      <span className="flex items-center gap-1">
                        <Droplets className="w-3 h-3 text-primary" />
                        {crop.waterNeeds || '--'}
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
              </button>                {/* EXPANDED */}
              {isExpanded && (
                <div className="px-4 pb-4 space-y-3">

                  {/* GRAPH: real mandi history from the price store */}
                  <div>
                    <h4 className="text-xs font-bold mb-2">Market Price Trend</h4>
                    {(() => {
                      const chart = chartBars(crop.priceHistory);
                      if (!chart) {
                        return (
                          <p className="text-[10px] text-muted-foreground">
                            No real mandi history recorded yet for this crop — accruing via daily ingestion.
                          </p>
                        );
                      }
                      return (
                        <>
                          <div className="h-16 flex gap-1 items-end">
                            {chart.bars.map((h, i) => (
                              <div
                                key={i}
                                className="flex-1 rounded-t"
                                style={{
                                  height: `${h}%`,
                                  backgroundColor:
                                    i === chart.highlightIndex
                                      ? 'hsl(var(--primary))'
                                      : 'hsl(var(--primary) / 0.25)',
                                }}
                              />
                            ))}
                            {chart.bars.length < 14 &&
                              Array.from({ length: 14 - chart.bars.length }).map((_, i) => (
                                <div key={`pad-${i}`} className="flex-1" />
                              ))}
                          </div>
                          <p className="text-[10px] text-muted-foreground mt-1">
                            {chart.latest?.toLocaleString('en-IN')} ₹/quintal · {chart.dateFrom} → {chart.dateTo}
                            {chart.scope !== 'district' && ` (${chart.scope} avg)`}
                          </p>
                        </>
                      );
                    })()}
                  </div>

                  {/* REVENUE: est. gross revenue/acre = real yield × today's real mandi price */}
                  <div className="flex justify-between bg-primary/10 p-3 rounded-lg">
                    <span className="text-xs">Est. gross revenue / acre</span>
                    <span className="font-bold text-primary">
                      {crop.revenuePerAcre || '--'}
                    </span>
                  </div>
                  <p className="text-[10px] text-muted-foreground -mt-2">
                    Yield band × today's mandi price; your costs differ.
                  </p>

                  {/* REQUIREMENTS: real ranges from the crop master dataset */}
                  <div className="space-y-2">
                    <div className="flex gap-2 text-xs">
                      <Layers className="w-4 h-4 text-primary" />
                      {crop.soilType || 'Soil suitability: see soil card'}
                    </div>
                    <div className="flex gap-2 text-xs">
                      <Thermometer className="w-4 h-4 text-primary" />
                      {crop.temperature || '--'}
                    </div>
                    <div className="flex gap-2 text-xs">
                      <Droplets className="w-4 h-4 text-primary" />
                      {crop.irrigation || '--'}
                    </div>
                  </div>

                  <button
                    onClick={() => navigate('/price-prediction', {
                      state: { commodity: crop.id, district },
                    })}
                    className="w-full gradient-primary py-2 rounded-lg font-bold"
                  >
                    See 14-Day Forecast →
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