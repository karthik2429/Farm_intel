import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLanguage } from '@/contexts/LanguageContext';
import { ArrowLeft, TestTube, Leaf, AlertCircle, Loader2, MapPin, Navigation } from 'lucide-react';
import { toast } from 'sonner';
import BottomNav from '@/components/BottomNav';
import { getFertilizerRecommendation, getDefaultNPK } from '@/lib/api';
import { allStates, getDistricts } from '@/lib/indian-locations';
import { useMemo } from 'react';

const FertilizerRecommendationPage: React.FC = () => {
  const { t } = useLanguage();
  const navigate = useNavigate();

  const [crop, setCrop] = useState('');
  const [soilType, setSoilType] = useState('');
  const [nitrogen, setNitrogen] = useState('');
  const [phosphorus, setPhosphorus] = useState('');
  const [potassium, setPotassium] = useState('');
  const [ph, setPh] = useState('');

  const [locationMode, setLocationMode] = useState<'current' | 'custom'>('current');
  const [selectedState, setSelectedState] = useState('Karnataka');
  const [selectedDistrict, setSelectedDistrict] = useState('Belagavi');
  const [autoNPK, setAutoNPK] = useState<{N: number, P: number, K: number, ph: number, rainfall: number, temperature: number} | null>(null);
  const [fetchingNPK, setFetchingNPK] = useState(false);
  const [detectingLocation, setDetectingLocation] = useState(false);
  const [coords, setCoords] = useState<{ lat: number; lon: number } | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);

  const districts = useMemo(() => getDistricts(selectedState), [selectedState]);

  const cropsList = [
    'Rice', 'Wheat', 'Maize', 'Cotton', 'Soybean', 'Sugarcane',
    'Chickpea', 'Pigeon Pea', 'Green Gram', 'Black Gram', 'Lentil',
    'Groundnut', 'Mustard', 'Sunflower', 'Sesame', 'Potato',
    'Tomato', 'Onion', 'Chilli', 'Turmeric', 'Ginger'
  ];

  const soilTypes = [
    'Loamy Soil', 'Clayey Soil', 'Sandy Soil', 'Black Soil',
    'Red Soil', 'Peaty Soil', 'Acidic Soil', 'Alkaline Soil'
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

  const handleGetRecommendation = async () => {
    if (!crop || !soilType) {
      toast.error("Please select crop and soil type");
      return;
    }

    setLoading(true);
    try {
      let payload: any = {
        crop,
        soil: soilType,
        top_k: 5
      };

      // Only add NPK/pH if provided
      if (nitrogen) payload.N = Number(nitrogen);
      if (phosphorus) payload.P = Number(phosphorus);
      if (potassium) payload.K = Number(potassium);
      if (ph) payload.PH = Number(ph);

      // Add location if NPK/pH not provided
      if (!nitrogen || !phosphorus || !potassium || !ph) {
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
            toast.message("Using selected district for fertilizer analysis");
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
      }

      console.log("FERTILIZER PAYLOAD:", payload);

      const data = await getFertilizerRecommendation(payload);

      if (data?.error) {
        toast.error(data.error);
        setLoading(false);
        return;
      }

      setResult(data);
      toast.success("Recommendations ready!");
    } catch (err) {
      console.error(err);
      toast.error("Something went wrong");
    } finally {
      setLoading(false);
    }
  };

  const fetchDefaultNPK = async (mode: 'auto' | 'coords') => {
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
        toast.success("Auto-filled NPK & pH from location!");
      } else {
        toast.error("Could not fetch location data");
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
        <h1 className="text-lg font-extrabold text-foreground">Fertilizer Advisor</h1>
      </div>

      <div className="px-5 space-y-4">

        {/* CROP & SOIL */}
        <div className="glass-card p-4 space-y-4">
          <p className="text-xs font-bold text-muted-foreground uppercase flex items-center gap-2">
            <TestTube className="w-4 h-4" />
            Crop & Soil Details
          </p>

          <div className="space-y-3">
            <select
              value={crop}
              onChange={(e) => setCrop(e.target.value)}
              className="w-full bg-secondary rounded px-3 py-2 text-sm"
            >
              <option value="">Select Crop</option>
              {cropsList.map(c => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>

            <select
              value={soilType}
              onChange={(e) => setSoilType(e.target.value)}
              className="w-full bg-secondary rounded px-3 py-2 text-sm"
            >
              <option value="">Select Soil Type</option>
              {soilTypes.map(s => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>
        </div>

        {/* SOIL NUTRIENTS (OPTIONAL) */}
        <div className="glass-card p-4 space-y-4">
          <p className="text-xs font-bold text-muted-foreground uppercase flex items-center gap-2">
            <Leaf className="w-4 h-4" />
            Current Soil Nutrients (Optional - Auto-filled from Location)
          </p>

          <div className="grid grid-cols-2 gap-2">
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
          onClick={handleGetRecommendation}
          disabled={loading}
          className="w-full gradient-primary py-3 rounded-xl font-bold flex items-center justify-center gap-2"
        >
          {loading ? (
            <>
              <Loader2 className="w-5 h-5 animate-spin" />
              Analyzing...
            </>
          ) : (
            'Get Recommendations'
          )}
        </button>

        {/* RESULTS */}
        {result && (
          <div className="space-y-4">
            <div className="glass-card p-4">
              <p className="text-xs font-bold text-muted-foreground uppercase mb-3">
                Recommended Fertilizers
              </p>
              <div className="flex flex-wrap gap-2">
                {result.recommended_fertilizers.map((fert: string, i: number) => (
                  <div key={i} className="bg-primary/10 text-primary px-3 py-1.5 rounded-full text-sm font-semibold flex items-center gap-1">
                    <span className="text-xs bg-primary text-white px-1.5 rounded-full">{i + 1}</span>
                    {fert}
                  </div>
                ))}
              </div>
            </div>

            <div className="glass-card p-4">
              <p className="text-xs font-bold text-muted-foreground uppercase mb-3">
                Top Matches from Dataset
              </p>
              <div className="space-y-2 max-h-64 overflow-y-auto">
                {result.top_matches.map((match: any, i: number) => (
                  <div key={i} className="p-3 bg-secondary/50 rounded-lg">
                    <div className="flex justify-between items-start">
                      <p className="font-semibold text-sm">{match.Fertilizer}</p>
                      <span className="text-xs text-primary font-bold">
                        {(match.Similarity * 100).toFixed(1)}%
                      </span>
                    </div>
                    <p className="text-[11px] text-muted-foreground mt-1 line-clamp-2">
                      {match.Remark}
                    </p>
                  </div>
                ))}
              </div>
            </div>

            <div className="glass-card p-4 border-l-4 border-primary">
              <p className="text-xs font-bold text-muted-foreground uppercase mb-2">
                Input Summary
              </p>
              <div className="grid grid-cols-4 gap-2 text-sm">
                <div><span className="text-muted-foreground">Crop:</span> <span className="font-semibold ml-1">{result.crop}</span></div>
                <div><span className="text-muted-foreground">Soil:</span> <span className="font-semibold ml-1">{result.soil}</span></div>
                <div><span className="text-muted-foreground">N:</span> <span className="font-semibold ml-1">{result.soil_nutrients.N}</span></div>
                <div><span className="text-muted-foreground">P:</span> <span className="font-semibold ml-1">{result.soil_nutrients.P}</span></div>
                <div><span className="text-muted-foreground">K:</span> <span className="font-semibold ml-1">{result.soil_nutrients.K}</span></div>
                <div><span className="text-muted-foreground">pH:</span> <span className="font-semibold ml-1">{result.soil_nutrients.PH}</span></div>
              </div>
            </div>
          </div>
        )}

      </div>

      <BottomNav />
    </div>
  );
};

export default FertilizerRecommendationPage;