import React, { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLanguage } from '@/contexts/LanguageContext';
import { ArrowLeft, MapPin, Navigation } from 'lucide-react';
import { allStates, getDistricts } from '@/lib/indian-locations';
import { toast } from 'sonner';
import BottomNav from '@/components/BottomNav';
import { getCropRecommendations } from '@/lib/api';

// 🔥 NEW IMPORTS
import { getMarketPrice } from '@/lib/marketApi';
import { mapCropName } from '@/lib/cropMap';

const CropRecommendationsPage: React.FC = () => {
  const { t } = useLanguage();
  const navigate = useNavigate();

  const [season, setSeason] = useState('kharif');

  const [nitrogen, setNitrogen] = useState('');
  const [phosphorus, setPhosphorus] = useState('');
  const [potassium, setPotassium] = useState('');
  const [ph, setPh] = useState('');
  const [rainfall, setRainfall] = useState('');

  const [locationMode, setLocationMode] = useState<'current' | 'custom'>('current');

  const [selectedState, setSelectedState] = useState('Karnataka');
  const [selectedDistrict, setSelectedDistrict] = useState('Belagavi');

  const [detectingLocation, setDetectingLocation] = useState(false);
  const [coords, setCoords] = useState<{ lat: number; lon: number } | null>(null);

  const districts = useMemo(() => getDistricts(selectedState), [selectedState]);

  // 📍 AUTO LOCATION
  const handleAutoDetect = () => {
    setDetectingLocation(true);

    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setCoords({
          lat: pos.coords.latitude,
          lon: pos.coords.longitude,
        });

        toast.success("📍 Location detected");
        setDetectingLocation(false);
      },
      () => {
        toast.error("Location access denied");
        setDetectingLocation(false);
      }
    );
  };

  // 🔥 ADD MARKET DATA
  const enrichMarket = async (crops: any[], district: string) => {
    return await Promise.all(
      crops.map(async (crop) => {
        const cropName = crop.name || crop[0];
        const mapped = mapCropName(cropName);

        const market = await getMarketPrice(mapped, district);

        return {
          ...crop,
          mandiPrice: market?.modal || null,
          mandiMin: market?.min || null,
          mandiMax: market?.max || null,
        };
      })
    );
  };

  // 🚀 FINAL LOGIC
  const handleGetRecommendations = async () => {
    try {
      let payload: any = {
        season,
      };

      // ✅ OPTIONAL FIELDS
      if (nitrogen) payload.N = Number(nitrogen);
      if (phosphorus) payload.P = Number(phosphorus);
      if (potassium) payload.K = Number(potassium);
      if (ph) payload.ph = Number(ph);
      if (rainfall) payload.rainfall = Number(rainfall);

      // ✅ LOCATION REQUIRED
      if (locationMode === 'current') {
        if (!coords) {
          toast.error("Click Auto Detect first");
          return;
        }

        payload.lat = coords.lat;
        payload.lon = coords.lon;
        payload.mode = "coords";
      } else {
        if (!selectedDistrict) {
          toast.error("Select district");
          return;
        }

        payload.state = selectedState;
        payload.district = selectedDistrict;
        payload.mode = "auto";
      }

      console.log("FINAL PAYLOAD:", payload);

      const data = await getCropRecommendations(payload);

      console.log("API RESPONSE:", data);

      if (!data || data.detail) {
        toast.error("Backend validation failed");
        return;
      }

      // 🔥 EXTRACT CROPS
      const crops = data["Top Crops"] || [];

      if (!crops.length) {
        toast.error("No crops found");
        return;
      }

      // 🔥 ADD MARKET DATA
      const enriched = await enrichMarket(
        crops.slice(0, 3),
        selectedDistrict
      );

      console.log("ENRICHED:", enriched);

      // 🚀 NAVIGATE
      navigate('/crop-detail', {
        state: { crops: enriched }
      });

    } catch (err) {
      console.error(err);
      toast.error("Something went wrong");
    }
  };

  return (
    <div className="min-h-screen bg-background pb-20">

      {/* HEADER */}
      <div className="px-5 pt-5 pb-3 flex items-center gap-3">
        <button onClick={() => navigate(-1)} className="w-8 h-8 rounded-full bg-secondary flex items-center justify-center">
          <ArrowLeft className="w-4 h-4 text-foreground" />
        </button>
        <h1 className="text-lg font-extrabold text-foreground">Crop AI Advisor</h1>
      </div>

      <div className="px-5 space-y-4">

        {/* LOCATION */}
        <div className="glass-card p-4 space-y-3">
          <div className="flex justify-between items-center">
            <div className="flex items-center gap-2">
              <MapPin className="w-4 h-4 text-primary" />
              <span className="text-xs font-bold text-muted-foreground">Choose Location</span>
            </div>

            <button
              onClick={handleAutoDetect}
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
                onChange={(e) => setSelectedState(e.target.value)}
                className="w-full bg-secondary rounded px-3 py-2"
              >
                {allStates.map(s => (
                  <option key={s}>{s}</option>
                ))}
              </select>

              <select
                value={selectedDistrict}
                onChange={(e) => setSelectedDistrict(e.target.value)}
                className="w-full bg-secondary rounded px-3 py-2"
              >
                {districts.map(d => (
                  <option key={d}>{d}</option>
                ))}
              </select>
            </div>
          )}
        </div>

        {/* SEASON */}
        <div>
          <p className="text-xs font-bold text-muted-foreground">SELECT SEASON</p>
          <div className="flex gap-2 mt-2">
            <button
              onClick={() => setSeason('kharif')}
              className={`flex-1 py-2 rounded-lg ${
                season === 'kharif' ? 'gradient-primary text-white' : 'bg-secondary'
              }`}
            >
              Kharif
            </button>

            <button
              onClick={() => setSeason('rabi')}
              className={`flex-1 py-2 rounded-lg ${
                season === 'rabi' ? 'gradient-primary text-white' : 'bg-secondary'
              }`}
            >
              Rabi
            </button>
          </div>
        </div>

        {/* SOIL */}
        <div>
          <label className="text-xs font-bold text-muted-foreground uppercase">
            SOIL COMPOSITION (OPTIONAL)
          </label>

          <div className="grid grid-cols-3 gap-2 mt-2">
            <input placeholder="Nitrogen (N)" value={nitrogen} onChange={(e)=>setNitrogen(e.target.value)} className="input"/>
            <input placeholder="Phosphorus (P)" value={phosphorus} onChange={(e)=>setPhosphorus(e.target.value)} className="input"/>
            <input placeholder="Potassium (K)" value={potassium} onChange={(e)=>setPotassium(e.target.value)} className="input"/>
          </div>

          <div className="grid grid-cols-2 gap-2 mt-2">
            <input placeholder="pH Level" value={ph} onChange={(e)=>setPh(e.target.value)} className="input"/>
            <input placeholder="Rainfall" value={rainfall} onChange={(e)=>setRainfall(e.target.value)} className="input"/>
          </div>
        </div>

        {/* BUTTON */}
        <button
          onClick={handleGetRecommendations}
          className="w-full gradient-primary py-3 rounded-xl font-bold"
        >
          Get Recommendations
        </button>

      </div>

      <BottomNav />
    </div>
  );
};

export default CropRecommendationsPage;