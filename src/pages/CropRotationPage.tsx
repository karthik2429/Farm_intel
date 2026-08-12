import React, { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLanguage } from '@/contexts/LanguageContext';
import { ArrowLeft, Leaf, TrendingUp, Bug, Loader2, AlertCircle, Navigation, MapPin } from 'lucide-react';
import { toast } from 'sonner';
import BottomNav from '@/components/BottomNav';
import { getRotationPlan, getDefaultNPK } from '@/lib/api';
import { allStates, getDistricts } from '@/lib/indian-locations';

const CropRotationPage: React.FC = () => {
  const { t } = useLanguage();
  const navigate = useNavigate();

  const [prevCrop, setPrevCrop] = useState('');
  const [nitrogen, setNitrogen] = useState('');
  const [phosphorus, setPhosphorus] = useState('');
  const [potassium, setPotassium] = useState('');
  const [ph, setPh] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);

  const [locationMode, setLocationMode] = useState<'current' | 'custom'>('current');

  const [selectedState, setSelectedState] = useState('Karnataka');
  const [selectedDistrict, setSelectedDistrict] = useState('Belagavi');

  const [detectingLocation, setDetectingLocation] = useState(false);
  const [coords, setCoords] = useState<{ lat: number; lon: number } | null>(null);

  const [autoNPK, setAutoNPK] = useState<{ N: number; P: number; K: number; ph: number; rainfall: number; temperature: number } | null>(null);
  const [fetchingNPK, setFetchingNPK] = useState(false);

  const districts = useMemo(() => getDistricts(selectedState), [selectedState]);

  const cropsList = [
    'Rice', 'Wheat', 'Maize', 'Cotton', 'Soybean', 'Sugarcane',
    'Chickpea', 'Pigeon Pea', 'Green Gram', 'Black Gram', 'Lentil',
    'Groundnut', 'Mustard', 'Sunflower', 'Sesame', 'Potato',
    'Tomato', 'Onion', 'Chilli', 'Turmeric', 'Ginger',
    'Jowar', 'Bajra', 'Ragi', 'Barley', 'Foxtail Millet',
    'Little Millet', 'Kodo Millet', 'Barnyard Millet', 'Proso Millet',
    'Cowpea', 'Field Pea', 'Horse Gram', 'Moth Bean', 'Kidney Bean',
    'Lablab Bean', 'Castor', 'Linseed', 'Safflower', 'Niger',
    'Jute', 'Tobacco', 'Cabbage', 'Cauliflower', 'Cucumber',
    'Pumpkin', 'Bottle Gourd', 'Bitter Gourd', 'Okra', 'Brinjal',
    'Mango', 'Banana', 'Papaya', 'Pomegranate', 'Grapes',
    'Orange', 'Guava', 'Watermelon', 'Muskmelon', 'Coconut',
    'Coriander', 'Cumin', 'Fenugreek', 'Fennel'
  ];

  const handleAutoDetect = () => {
    setDetectingLocation(true);

    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setCoords({
          lat: pos.coords.latitude,
          lon: pos.coords.longitude,
        });

        toast.success("Location detected");
        setDetectingLocation(false);
      },
      () => {
        toast.error("Location access denied");
        setDetectingLocation(false);
      }
    );
  };

  const handleGetRotation = async () => {
    if (!prevCrop) {
      toast.error("Please select previous crop");
      return;
    }

    setLoading(true);
    try {
      let payload: any = {
        season1_crop: prevCrop,
        top_n: 3,
      };

      if (nitrogen) payload.N = Number(nitrogen);
      if (phosphorus) payload.P = Number(phosphorus);
      if (potassium) payload.K = Number(potassium);
      if (ph) payload.ph = Number(ph);

      if (locationMode === 'current') {
        if (coords) {
          payload.lat = coords.lat;
          payload.lon = coords.lon;
          payload.mode = "coords";
        } else {
          if (!selectedDistrict) {
            toast.error("Select district");
            setLoading(false);
            return;
          }
          payload.district = selectedDistrict;
          payload.mode = "auto";
          toast.message("Using selected district for soil analysis");
        }
      } else {
        if (!selectedDistrict) {
          toast.error("Select district");
          setLoading(false);
          return;
        }
        payload.district = selectedDistrict;
        payload.mode = "auto";
      }

      console.log("ROTATION PAYLOAD:", payload);

      const data = await getRotationPlan(payload);

      if (!data) {
        toast.error("Rotation service unavailable. Try again later.");
        setLoading(false);
        return;
      }

      if (data.error) {
        toast.error(data.error);
        setLoading(false);
        return;
      }

      const transformedResult = {
        season1_crop: data.season1 || payload.season1_crop,
        depleted_soil: data.soil_after_s1 || {},
        warnings: data.warnings || [],
        top_suggestions: (data.season2_options || []).map((s: any) => ({
          ...s,
          fertiliser_topup: {
            N: s.N_gap,
            P: s.P_gap,
            K: s.K_gap
          },
          match_score: s.final_score
        })),
        season3_preview: data.season3_preview || "N/A"
      };

      setResult(transformedResult);
      toast.success("Rotation plan ready!");
    } catch (err) {
      console.error(err);
      toast.error("Something went wrong");
    } finally {
      setLoading(false);
    }
  };

  const fetchDefaultNPK = async (mode: 'auto' | 'coords' = 'auto') => {
    setFetchingNPK(true);
    try {
      let payload: any = { mode };
      if (mode === 'auto' || !coords) {
        payload.district = selectedDistrict;
      }
      if (mode === 'coords' && coords) {
        payload.lat = coords.lat;
        payload.lon = coords.lon;
      }
      const data = await getDefaultNPK(payload);
      if (data && !data.error) {
        setAutoNPK(data);
        if (!nitrogen) setNitrogen(String(data.N));
        if (!phosphorus) setPhosphorus(String(data.P));
        if (!potassium) setPotassium(String(data.K));
        if (!ph) setPh(String(data.ph));
        toast.success("Auto-filled NPK & pH from location");
      }
    } catch (err) {
      console.error(err);
      toast.error("Failed to fetch location data");
    } finally {
      setFetchingNPK(false);
    }
  };

  return (
    <div className="min-h-screen bg-background pb-20">
      {/* HEADER */}
      <div className="px-5 pt-5 pb-3 flex items-center gap-3">
        <button onClick={() => navigate(-1)} className="w-8 h-8 rounded-full bg-secondary flex items-center justify-center">
          <ArrowLeft className="w-4 h-4 text-foreground" />
        </button>
        <h1 className="text-lg font-extrabold text-foreground">{t('rotationPlanner')}</h1>
      </div>

      <div className="px-5 space-y-4">

        {/* INPUT FORM */}
        <div className="glass-card p-4 space-y-4">
          <p className="text-xs font-bold text-muted-foreground uppercase flex items-center gap-2">
            <Leaf className="w-4 h-4" />
            Previous Crop & Soil Status
          </p>

          <div className="space-y-3">
            <select
              value={prevCrop}
              onChange={(e) => setPrevCrop(e.target.value)}
              className="w-full bg-secondary rounded px-3 py-2 text-sm"
            >
              <option value="">Select Previous Crop</option>
              {cropsList.map(c => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>

            <div className="grid grid-cols-3 gap-2">
              <input
                placeholder="Nitrogen (N) kg/ha"
                value={nitrogen}
                onChange={(e) => setNitrogen(e.target.value)}
                className="input"
                type="number"
                step="0.1"
              />
              <input
                placeholder="Phosphorus (P) kg/ha"
                value={phosphorus}
                onChange={(e) => setPhosphorus(e.target.value)}
                className="input"
                type="number"
                step="0.1"
              />
              <input
                placeholder="Potassium (K) kg/ha"
                value={potassium}
                onChange={(e) => setPotassium(e.target.value)}
                className="input"
                type="number"
                step="0.1"
              />
            </div>

            <div className="grid grid-cols-2 gap-2">
              <input
                placeholder="pH Level"
                value={ph}
                onChange={(e) => setPh(e.target.value)}
                className="input"
                type="number"
                step="0.1"
                min="3"
                max="10"
              />
            </div>
          </div>
        </div>

        {/* LOCATION */}
        <div className="glass-card p-4 space-y-3">
          <div className="flex justify-between items-center">
            <div className="flex items-center gap-2">
              <MapPin className="w-4 h-4 text-primary" />
              <span className="text-xs font-bold text-muted-foreground">Choose Location</span>
            </div>

            <button
              onClick={handleAutoDetect}
              disabled={detectingLocation}
              className="text-xs font-bold text-primary bg-primary/10 px-3 py-1 rounded-full flex items-center gap-1"
            >
              <Navigation className="w-3 h-3" />
              {detectingLocation ? "..." : "Auto Detect"}
            </button>
          </div>

          <div className="flex gap-2">
            <button
              onClick={() => setLocationMode('current')}
              className={`flex-1 py-2 rounded-lg ${
                locationMode === 'current'
                  ? 'gradient-primary text-white'
                  : 'bg-secondary'
              }`}
            >
              Use Current Location
            </button>

            <button
              onClick={() => setLocationMode('custom')}
              className={`flex-1 py-2 rounded-lg ${
                locationMode === 'custom'
                  ? 'gradient-primary text-white'
                  : 'bg-secondary'
              }`}
            >
              Select District
            </button>
          </div>

          {locationMode === 'current' ? (
            <p className="text-sm font-semibold">
              {coords ? "Location detected" : "No location"}
            </p>
          ) : (
            <div className="space-y-2">
              <select
                value={selectedState}
                onChange={(e) => {
                  setSelectedState(e.target.value);
                  setSelectedDistrict('');
                }}
                className="w-full bg-secondary rounded px-3 py-2"
              >
                {allStates.map(s => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>

              <select
                value={selectedDistrict}
                onChange={(e) => setSelectedDistrict(e.target.value)}
                className="w-full bg-secondary rounded px-3 py-2"
              >
                <option value="">Select District</option>
                {districts.map(d => (
                  <option key={d} value={d}>{d}</option>
                ))}
              </select>
            </div>
          )}

          <button
            onClick={() => fetchDefaultNPK(locationMode === 'current' ? 'coords' : 'auto')}
            disabled={fetchingNPK || (locationMode === 'custom' && !selectedDistrict)}
            className="w-full py-2 rounded-lg bg-primary/10 text-primary font-medium text-sm flex items-center justify-center gap-2"
          >
            {fetchingNPK ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Fetching NPK...
              </>
            ) : (
              'Auto-fill NPK & pH from Location'
            )}
          </button>

          {autoNPK && (
            <div className="p-3 bg-primary/5 rounded-lg border border-primary/20">
              <p className="text-xs font-bold text-primary mb-2">Auto-detected Soil & Weather</p>
              <div className="grid grid-cols-3 gap-2 text-sm">
                <div><span className="text-muted-foreground">N: </span><span className="font-semibold">{autoNPK.N} kg/ha</span></div>
                <div><span className="text-muted-foreground">P: </span><span className="font-semibold">{autoNPK.P} kg/ha</span></div>
                <div><span className="text-muted-foreground">K: </span><span className="font-semibold">{autoNPK.K} kg/ha</span></div>
                <div><span className="text-muted-foreground">pH: </span><span className="font-semibold">{autoNPK.ph}</span></div>
                <div><span className="text-muted-foreground">Temp: </span><span className="font-semibold">{autoNPK.temperature}°C</span></div>
                <div><span className="text-muted-foreground">Rain: </span><span className="font-semibold">{autoNPK.rainfall} mm</span></div>
              </div>
              <p className="text-[10px] text-muted-foreground mt-1">Values auto-filled in fields above. Edit if needed.</p>
            </div>
          )}
        </div>

        {/* BUTTON */}
        <button
          onClick={handleGetRotation}
          disabled={loading}
          className="w-full gradient-primary py-3 rounded-xl font-bold flex items-center justify-center gap-2"
        >
          {loading ? (
            <>
              <Loader2 className="w-5 h-5 animate-spin" />
              Generating Plan...
            </>
          ) : (
            'Generate Rotation Plan'
          )}
        </button>

        {/* RESULTS */}
        {result && (
          <div className="space-y-4">
            {/* SEASON 1 INFO */}
            <div className="glass-card p-4 bg-primary/5 border-l-4 border-primary">
              <div className="flex items-center gap-2 mb-2">
                <span className="px-2 py-0.5 rounded-full bg-primary/20 text-primary text-[10px] font-bold">
                  SEASON 1
                </span>
                <h3 className="text-base font-extrabold text-foreground">{result.season1_crop}</h3>
              </div>
              <div className="grid grid-cols-3 gap-2 text-sm">
                <div>
                  <span className="text-muted-foreground">N: </span>
                  <span className="font-semibold">{result.depleted_soil.N.toFixed(1)}</span>
                </div>
                <div>
                  <span className="text-muted-foreground">P: </span>
                  <span className="font-semibold">{result.depleted_soil.P.toFixed(1)}</span>
                </div>
                <div>
                  <span className="text-muted-foreground">K: </span>
                  <span className="font-semibold">{result.depleted_soil.K.toFixed(1)}</span>
                </div>
              </div>
              <p className="text-[10px] text-muted-foreground mt-2">
                Soil after {result.season1_crop} harvest
              </p>
            </div>

            {/* WARNINGS */}
            {result.warnings && result.warnings.length > 0 && (
              <div className="glass-card p-4 bg-destructive/5 border-l-4 border-destructive">
                <p className="text-xs font-bold text-destructive uppercase mb-2 flex items-center gap-1">
                  <AlertCircle className="w-3 h-3" />
                  Soil Warnings
                </p>
                <ul className="space-y-1 text-sm">
                  {result.warnings.map((w: string, i: number) => (
                    <li key={i} className="flex items-start gap-2 text-destructive/80">
                      <span className="w-1.5 h-1.5 rounded-full bg-destructive mt-1.5 flex-shrink-0" />
                      {w}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* SEASON 2 SUGGESTIONS */}
            <div>
              <p className="text-xs font-bold text-muted-foreground uppercase mb-3">
                Season 2 Recommendations
              </p>
              <div className="space-y-3">
                {result.top_suggestions.map((s: any, i: number) => (
                  <div key={i} className="glass-card p-4 overflow-hidden">
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2">
                          <span className="px-2 py-0.5 rounded-full bg-primary/20 text-primary text-[10px] font-bold">
                            #{i + 1}
                          </span>
                          <h3 className="text-base font-extrabold text-foreground">{s.crop}</h3>
                          <span className="px-2 py-0.5 rounded-full bg-secondary text-[10px] font-bold text-muted-foreground">
                            {s.season}
                          </span>
                        </div>
                        <p className="text-xs text-muted-foreground mb-2">{s.family}</p>

                        <div className="flex gap-2 mb-3">
                          <div className="flex items-center gap-1 bg-primary/10 px-2 py-1 rounded-full">
                            <Leaf className="w-3 h-3 text-primary" />
                            <span className="text-[10px] text-primary font-semibold">
                              {s.nitrogen_fixing ? 'N-Fixing' : 'Non N-Fixing'}
                            </span>
                          </div>
                          <span className="px-2 py-1 rounded-full bg-secondary text-[10px] font-semibold text-muted-foreground">
                            {s.soil_type}
                          </span>
                          <span className="px-2 py-1 rounded-full bg-secondary text-[10px] font-semibold text-muted-foreground">
                            pH: {s.ph_range}
                          </span>
                        </div>

                        <div className="flex gap-3 text-xs">
                          <div className="flex items-center gap-1 text-muted-foreground">
                            <span className="font-semibold text-primary">N+{s.fertiliser_topup.N.toFixed(1)}</span>
                          </div>
                          <div className="flex items-center gap-1 text-muted-foreground">
                            <span className="font-semibold text-primary">P+{s.fertiliser_topup.P.toFixed(1)}</span>
                          </div>
                          <div className="flex items-center gap-1 text-muted-foreground">
                            <span className="font-semibold text-primary">K+{s.fertiliser_topup.K.toFixed(1)}</span>
                          </div>
                        </div>
                      </div>

                      <div className="text-right">
                        <p className="text-2xl font-extrabold text-primary">{s.match_score}</p>
                        <p className="text-[10px] text-muted-foreground">Match Score</p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* SEASON 3 PREVIEW */}
            {result.season3_preview && (
              <div className="glass-card p-4 bg-secondary/50">
                <p className="text-xs font-bold text-muted-foreground uppercase mb-2">
                  Season 3 Preview (After Best Season 2 Pick)
                </p>
                <p className="font-semibold text-foreground">
                  {result.season3_preview}
                </p>
              </div>
            )}
          </div>
        )}

      </div>

      <BottomNav />
    </div>
  );
};

export default CropRotationPage;