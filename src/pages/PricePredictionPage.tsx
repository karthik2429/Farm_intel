import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLanguage } from '@/contexts/LanguageContext';
import { ArrowLeft, TrendingUp, Bell, AlertTriangle, Truck, CloudRain, ChevronDown, RefreshCw } from 'lucide-react';
import BottomNav from '@/components/BottomNav';
import { get14DayPredictions, getTrajectory as getTrajectoryData } from '@/lib/priceApi';

interface Prediction {
  district: string;
  commodity: string;
  market: string;
  current_price: number;
  predicted_price_14d: number;
  predicted_change_pct: number;
  prediction_date: string;
  model: string;
}

interface Trajectory {
  district: string;
  commodity: string;
  market: string;
  current_price: number;
  trajectory: Array<{
    day_ahead: number;
    date: string;
    predicted_price: number;
    change_from_current_pct: number;
  }>;
}

const PricePredictionPage: React.FC = () => {
  const { t } = useLanguage();
  const navigate = useNavigate();
  
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [trajectories, setTrajectories] = useState<Trajectory[]>([]);
  const [selectedCommodity, setSelectedCommodity] = useState<string>('');
  const [selectedMarket, setSelectedMarket] = useState<string>('');
  const [selectedDistrict, setSelectedDistrict] = useState<string>('North Goa');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  const commodities = [
    'Arecanut(Betelnut/Supari)', 'Banana', 'Brinjal', 'Cashewnuts', 'Chikoos(Sapota)',
    'Coconut', 'Copra', 'Grapes', 'Green Chilli', 'Mango', 'Marigold(Loose)',
    'Mousambi(Sweet Lime)', 'Onion', 'Orange', 'Papaya', 'Pineapple',
    'Potato', 'Rose(Loose)', 'Water Melon', 'Apple'
  ];
  
  const markets = {
    'North Goa': ['Goa State Horticultural Corporation Ltd.', 'Mapusa', 'Pernem', 'Sanquelim', 'Valpol'],
    'South Goa': ['Canacona', 'Curchorem', 'Margao', 'Ponda']
  };

  const fetchPredictions = async () => {
    setLoading(true);
    setError(null);
    try {
      const [predictionData, trajectoryData] = await Promise.all([
        get14DayPredictions({
          district: selectedDistrict || undefined,
          commodity: selectedCommodity || undefined,
          market: selectedMarket || undefined,
        }),
        getTrajectoryData({
          district: selectedDistrict || undefined,
          commodity: selectedCommodity || undefined,
          market: selectedMarket || undefined,
        }),
      ]);

      if ((predictionData as any)?.error) {
        throw new Error((predictionData as any).error);
      }

      setPredictions(predictionData);
      setTrajectories(trajectoryData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load predictions');
      console.error('Prediction fetch error:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPredictions();
  }, [selectedDistrict, selectedCommodity, selectedMarket]);

  const getFilteredPredictions = () => {
    return predictions;
  };

  const getTrajectoryForSelection = (commodity: string, market: string) => {
    return trajectories.find(t => t.commodity === commodity && t.market === market);
  };

  const formatPrice = (price: number) => {
    return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(price);
  };

  const selectedPrediction = selectedCommodity && selectedMarket 
    ? predictions.find(p => p.commodity === selectedCommodity && p.market === selectedMarket)
    : (predictions[0] || null);

  const trajectory = selectedPrediction 
    ? getTrajectoryForSelection(selectedPrediction.commodity, selectedPrediction.market)
    : null;

  return (
    <div className="min-h-screen bg-background pb-20">
      <div className="px-5 pt-5 pb-3 flex items-center gap-3">
        <button onClick={() => navigate(-1)} className="w-8 h-8 rounded-full bg-secondary flex items-center justify-center">
          <ArrowLeft className="w-4 h-4 text-foreground" />
        </button>
        <h1 className="text-lg font-extrabold text-foreground">{t('pricePrediction')}</h1>
      </div>

      <div className="px-5 space-y-4">
        {/* Filters */}
        <div className="glass-card p-3 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-muted-foreground block mb-1">{t('district') || 'District'}</label>
              <select 
                value={selectedDistrict} 
                onChange={(e) => setSelectedDistrict(e.target.value)}
                className="w-full bg-input border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              >
                <option value="North Goa">North Goa</option>
                <option value="South Goa">South Goa</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-muted-foreground block mb-1">{t('commodity') || 'Commodity'}</label>
              <select 
                value={selectedCommodity} 
                onChange={(e) => setSelectedCommodity(e.target.value)}
                className="w-full bg-input border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              >
                <option value="">All Commodities</option>
                {commodities.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div className="col-span-2">
              <label className="text-xs text-muted-foreground block mb-1">{t('market') || 'Market'}</label>
              <select 
                value={selectedMarket} 
                onChange={(e) => setSelectedMarket(e.target.value)}
                className="w-full bg-input border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              >
                <option value="">All Markets</option>
                {markets[selectedDistrict]?.map(m => <option key={m} value={m}>{m}</option>)}
              </select>
            </div>
          </div>
          <button 
            onClick={fetchPredictions}
            disabled={loading}
            className="w-full gradient-primary text-primary-foreground px-4 py-2 rounded-lg text-sm font-bold flex items-center justify-center gap-2"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            {loading ? t('loading') || 'Loading...' : t('refresh') || 'Refresh Predictions'}
          </button>
        </div>

        {error && (
          <div className="glass-card p-3 border-l-4 border-destructive">
            <p className="text-xs text-destructive">{error}</p>
          </div>
        )}

        {/* Summary Cards */}
        <div className="grid grid-cols-2 gap-3">
          <div className="glass-card p-4">
            <p className="text-xs text-muted-foreground">{t('totalCommodities') || 'Commodities Tracked'}</p>
            <p className="text-2xl font-extrabold text-foreground mt-1">{new Set(predictions.map(p => p.commodity)).size}</p>
          </div>
          <div className="glass-card p-4">
            <p className="text-xs text-muted-foreground">{t('avgChange') || 'Avg 14-Day Change'}</p>
            <p className="text-2xl font-extrabold text-foreground mt-1">
              {predictions.length > 0 
                ? `${(predictions.reduce((a, b) => a + b.predicted_change_pct, 0) / predictions.length).toFixed(1)}%`
                : '—'}
            </p>
          </div>
        </div>

        {/* Selected Commodity Detail */}
        {selectedPrediction && (
          <div className="glass-card p-4 border-l-4 border-primary">
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="text-xs text-muted-foreground">{selectedPrediction.district} • {selectedPrediction.market}</p>
                <p className="text-lg font-extrabold text-foreground">{selectedPrediction.commodity}</p>
              </div>
              <div className="text-right">
                <p className="text-xs text-muted-foreground">Current Price</p>
                <p className="text-xl font-extrabold text-foreground">{formatPrice(selectedPrediction.current_price)}/q</p>
              </div>
            </div>
            
            <div className="mt-3 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <TrendingUp className={`w-4 h-4 ${selectedPrediction.predicted_change_pct >= 0 ? 'text-green-500' : 'text-red-500'}`} />
                <span className={`text-sm font-bold ${selectedPrediction.predicted_change_pct >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                  {selectedPrediction.predicted_change_pct >= 0 ? '+' : ''}{selectedPrediction.predicted_change_pct.toFixed(1)}%
                </span>
              </div>
              <span className="text-xs font-bold text-primary">
                14-Day: {formatPrice(selectedPrediction.predicted_price_14d)}/q
              </span>
            </div>

            {/* Trajectory Chart */}
            {trajectory && (
              <div className="mt-3">
                <h3 className="text-sm font-bold text-foreground mb-2">Daily Outlook</h3>
                <div className="h-24 flex items-end gap-1 mb-2">
                  {trajectory.trajectory.map((point, i) => {
                      const changePct = (point.change_from_prev_pct ?? point.change_from_initial_pct) ?? 0;
                    return (
                      <div
                        key={i}
                        className="flex-1 rounded-t transition-all"
                        style={{
                            height: `${Math.min(100, Math.max(8, 50 + changePct * 2))}%`,
                            background: changePct >= 0 
                            ? 'hsl(152 65% 45% / 0.6)' 
                            : 'hsl(0 65% 45% / 0.6)',
                          borderTop: `2px dashed ${changePct >= 0 ? 'hsl(152 65% 45%)' : 'hsl(0 65% 45%)'}`,
                        }}
                      />
                    );
                  })}
                </div>
                <div className="flex items-center justify-between text-[10px] text-muted-foreground">
                  <span>Day 1</span>
                  <span>Day 14</span>
                </div>
                <div className="mt-2 space-y-1">
                  {trajectory.trajectory.map((point, i) => {
                    const dayChange = point.change_from_prev_pct ?? point.change_from_initial_pct ?? 0;
                    return (
                      <div key={i} className="flex items-center justify-between text-[11px] text-muted-foreground">
                        <span>{point.date}</span>
                        <span className="font-semibold text-foreground">{formatPrice(point.predicted_price)}</span>
                        <span className={(dayChange >= 0 ? 'text-green-500' : 'text-red-500')}>
                          {dayChange >= 0 ? '+' : ''}{dayChange.toFixed(1)}%
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            <div className="mt-3 flex gap-2">
              <span className="text-xs text-muted-foreground px-2 py-1 bg-secondary rounded">
                Model: {selectedPrediction.model}
              </span>
              <span className="text-xs text-muted-foreground px-2 py-1 bg-secondary rounded">
                As of: {selectedPrediction.prediction_date}
              </span>
            </div>
          </div>
        )}

        {/* All Predictions Table */}
        <div className="glass-card p-3">
          <h3 className="text-sm font-bold text-foreground mb-2">{t('allPredictions') || 'All Predictions'}</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-muted-foreground border-b border-border">
                  <th className="pb-1">Commodity</th>
                  <th className="pb-1">Market</th>
                  <th className="pb-1 text-right">Current</th>
                  <th className="pb-1 text-right">14-Day</th>
                  <th className="pb-1 text-right">Change</th>
                </tr>
              </thead>
              <tbody>
                {getFilteredPredictions().map((pred, i) => (
                  <tr key={i} className="border-b border-border/50 last:border-0 hover:bg-secondary/50">
                    <td className="py-2 font-medium">{pred.commodity}</td>
                    <td className="py-2">{pred.market}</td>
                    <td className="py-2 text-right">{formatPrice(pred.current_price)}</td>
                    <td className="py-2 text-right">{formatPrice(pred.predicted_price_14d)}</td>
                    <td className={`py-2 text-right font-bold ${pred.predicted_change_pct >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                      {pred.predicted_change_pct >= 0 ? '+' : ''}{pred.predicted_change_pct.toFixed(1)}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Factors Influencing */}
        <div>
          <h3 className="text-sm font-bold text-foreground mb-3">{t('factorsInfluencing')}</h3>
          <div className="space-y-2">
            {[
              { icon: CloudRain, label: 'Monsoon Impact', desc: 'Heavy rainfall in Jul-Aug affects harvest timing and transport' },
              { icon: Truck, label: 'Supply Pressure', desc: 'Market arrivals tracked daily; high supply pushes prices down' },
              { icon: AlertTriangle, label: 'Festival Demand', desc: 'Diwali, Christmas, Carnival create seasonal price spikes' },
              { icon: TrendingUp, label: 'Weather Stress', desc: 'Heat waves, floods, drought risk factored into forecasts' },
            ].map((f, i) => (
              <div key={i} className="glass-card p-3 flex gap-3">
                <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
                  <f.icon className="w-4 h-4 text-primary" />
                </div>
                <div>
                  <p className="text-xs font-bold text-foreground">{f.label}</p>
                  <p className="text-[10px] text-muted-foreground leading-relaxed">{f.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <BottomNav />
    </div>
  );
};

export default PricePredictionPage;