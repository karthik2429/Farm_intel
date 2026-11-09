import * as React from 'react';
import { useNavigate } from 'react-router-dom';
import { LocateFixed, MapPin, Sprout } from 'lucide-react';
import { toast } from 'sonner';
import { AppShell } from '@/components/ui-kit/AppShell';
import { Card, CardLabel, Chip, PageHeader, SegmentedTabs } from '@/components/ui-kit/core';
import { Button, Input } from '@/components/ui-kit/form';
import { useLanguage } from '@/contexts/LanguageContext';
import { useAuth } from '@/contexts/AuthContext';
import { allStates, getDistricts } from '@/lib/indian-locations';
import { cachedLocation, readCachedProfile } from '@/lib/profile';
import { getCropRecommendations } from '@/lib/api';
import { getMarketPrice } from '@/lib/marketApi';
import { mapCropName } from '@/lib/cropMap';
import type { CropEntry, RequestPayload } from '@/lib/apiTypes';

/**
 * Crop advisor.
 *
 * Location and soil come from the saved profile by default, so the form opens
 * already filled in for the farmer's own district. Any value can still be
 * overridden. Results navigate to the detail screen with the resolved district
 * attached so prices there are scoped correctly.
 */
const CropRecommendationsPage: React.FC = () => {
  const { t } = useLanguage();
  const { user } = useAuth();
  const navigate = useNavigate();

  const saved = React.useMemo(() => cachedLocation(), []);
  const cached = React.useMemo(() => readCachedProfile(), []);
  const soil = cached?.soil || null;

  const [season, setSeason] = React.useState(cached?.season_focus || 'kharif');
  const [state, setState] = React.useState(saved.state || 'Karnataka');
  const [district, setDistrict] = React.useState(saved.district);
  const [coords, setCoords] = React.useState<{ lat: number; lon: number } | null>(
    saved.lat != null && saved.lon != null ? { lat: saved.lat, lon: saved.lon } : null,
  );
  const [detecting, setDetecting] = React.useState(false);
  const [loading, setLoading] = React.useState(false);

  const [nitrogen, setNitrogen] = React.useState(soil?.n != null ? String(soil.n) : '');
  const [phosphorus, setPhosphorus] = React.useState(soil?.p != null ? String(soil.p) : '');
  const [potassium, setPotassium] = React.useState(soil?.k != null ? String(soil.k) : '');
  const [ph, setPh] = React.useState(soil?.ph != null ? String(soil.ph) : '');
  const [rainfall, setRainfall] = React.useState('');

  const districts = React.useMemo(() => getDistricts(state), [state]);

  const detect = () => {
    if (!navigator.geolocation) {
      toast.error('This browser cannot share a location');
      return;
    }
    setDetecting(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setCoords({ lat: pos.coords.latitude, lon: pos.coords.longitude });
        setDetecting(false);
        toast.success('Using your current location');
      },
      () => {
        setDetecting(false);
        toast.error('Location denied — pick your district instead');
      },
      { enableHighAccuracy: true, timeout: 10000 },
    );
  };

  const enrichMarket = async (crops: CropEntry[], d: string, s?: string) =>
    Promise.all(
      crops.map(async (crop) => {
        const cropName = String(crop.name || '');
        const mapped = mapCropName(cropName);
        const market = d ? await getMarketPrice(mapped, d, s) : null;
        return {
          ...crop,
          mandiPrice: market?.modal || null,
          mandiMin: market?.min || null,
          mandiMax: market?.max || null,
          // Carry provenance through to the detail screen: an MSP reference
          // must not be shown under a "today's mandi price" label.
          mandiBadge: market?.badge ?? null,
          mandiIsReal: market?.is_real ?? null,
          mandiMarket: market?.market ?? null,
          mandiScope: market?.scope ?? null,
        };
      }),
    );

  const submit = async () => {
    setLoading(true);
    try {
      const payload: RequestPayload = { season };
      if (nitrogen) payload.N = Number(nitrogen);
      if (phosphorus) payload.P = Number(phosphorus);
      if (potassium) payload.K = Number(potassium);
      if (ph) payload.ph = Number(ph);
      if (rainfall) payload.rainfall = Number(rainfall);

      // Coordinates win when the farmer asked for their current spot.
      const useCoords = coords && (!district || district === saved.district);
      if (useCoords) {
        payload.lat = coords!.lat;
        payload.lon = coords!.lon;
        payload.mode = 'coords';
      } else {
        if (!district) {
          toast.error('Choose your district first');
          setLoading(false);
          return;
        }
        payload.state = state;
        payload.district = district;
      }

      const data = await getCropRecommendations(payload);
      if (!data || data.detail) {
        toast.error('The advisor could not answer — check the backend is running');
        return;
      }

      // Keep every factor the advisor returned (soil, climate, region, market
      // return) — the detail page explains the rank with them.
      const crops: CropEntry[] = Array.isArray(data.alternatives)
        ? (data.alternatives as CropEntry[]).map((a) => ({
            ...a,
            name: a.crop,
            confidence: a.confidence,
          }))
        : [];
      if (data.crop && !crops.some((c) => c.name === data.crop)) {
        crops.unshift({ name: data.crop, confidence: data.confidence });
      }
      if (!crops.length) {
        toast.error('No crops returned for this soil and season');
        return;
      }

      const resolvedDistrict = data.district || district;
      const enriched = await enrichMarket(
        crops.slice(0, 3),
        resolvedDistrict,
        data.state || state,
      );

      navigate('/crop-detail', {
        state: { crops: enriched, district: resolvedDistrict, season },
      });
    } catch {
      toast.error('Something went wrong reaching the advisor');
    } finally {
      setLoading(false);
    }
  };

  return (
    <AppShell>
      <PageHeader
        title="Crop advisor"
        subtitle="Matched to your soil, season and district"
      />

      <div className="max-w-2xl space-y-4">
        {/* Location */}
        <Card>
          <div className="flex items-center justify-between gap-2">
            <CardLabel>Location</CardLabel>
            <button
              type="button"
              onClick={detect}
              className="press inline-flex items-center gap-1.5 rounded-full border border-border bg-surface px-3 py-1.5 text-[11.5px] font-700 text-primary"
            >
              <LocateFixed className="h-3.5 w-3.5" strokeWidth={2.2} />
              {detecting ? 'Detecting…' : 'Auto-detect'}
            </button>
          </div>

          <p className="mt-2 flex items-center gap-1.5 text-[13px] font-600 text-ink">
            <MapPin className="h-4 w-4 text-primary" strokeWidth={2} />
            {district ? `${district}, ${state}` : 'No district selected'}
          </p>
          {coords && (
            <p className="mt-0.5 text-[11.5px] text-ink-muted">
              GPS {coords.lat.toFixed(3)}, {coords.lon.toFixed(3)} will be used
            </p>
          )}

          <div className="mt-3 flex flex-wrap gap-1.5">
            {allStates.slice(0, 6).map((s) => (
              <Chip key={s} active={state === s} onClick={() => { setState(s); setDistrict(''); }}>
                {s}
              </Chip>
            ))}
          </div>

          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            <label className="block">
              <span className="mb-1 block text-[10.5px] font-700 uppercase tracking-[0.07em] text-ink-muted">
                State
              </span>
              <select
                value={state}
                onChange={(e) => { setState(e.target.value); setDistrict(''); }}
                className="h-[46px] w-full rounded-sm border border-border bg-surface-2 px-3 text-[14px] text-ink outline-none focus:border-primary"
              >
                {allStates.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="mb-1 block text-[10.5px] font-700 uppercase tracking-[0.07em] text-ink-muted">
                District
              </span>
              <select
                value={district}
                onChange={(e) => setDistrict(e.target.value)}
                className="h-[46px] w-full rounded-sm border border-border bg-surface-2 px-3 text-[14px] text-ink outline-none focus:border-primary"
              >
                <option value="">Select district</option>
                {districts.map((d) => (
                  <option key={d} value={d}>{d}</option>
                ))}
              </select>
            </label>
          </div>
        </Card>

        {/* Season */}
        <Card>
          <CardLabel>Season</CardLabel>
          <div className="mt-2">
            <SegmentedTabs
              value={season}
              onChange={setSeason}
              tabs={[
                { value: 'kharif', label: 'Kharif' },
                { value: 'rabi', label: 'Rabi' },
                { value: 'zaid', label: 'Zaid' },
              ]}
            />
          </div>
        </Card>

        {/* Soil */}
        <Card>
          <div className="flex items-center justify-between gap-2">
            <CardLabel>Soil (optional)</CardLabel>
            {soil && (
              <span className="rounded-full border border-primary/30 bg-primary/10 px-2 py-0.5 text-[10px] font-700 uppercase tracking-wide text-primary">
                Using your saved soil card
              </span>
            )}
          </div>
          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
            <Input label="Nitrogen" unit="kg/ha" inputMode="decimal" value={nitrogen} onChange={(e) => setNitrogen(e.target.value)} placeholder="—" />
            <Input label="Phosphorus" unit="kg/ha" inputMode="decimal" value={phosphorus} onChange={(e) => setPhosphorus(e.target.value)} placeholder="—" />
            <Input label="Potassium" unit="kg/ha" inputMode="decimal" value={potassium} onChange={(e) => setPotassium(e.target.value)} placeholder="—" />
            <Input label="pH" inputMode="decimal" value={ph} onChange={(e) => setPh(e.target.value)} placeholder="—" />
            <Input label="Rainfall" unit="mm" inputMode="decimal" value={rainfall} onChange={(e) => setRainfall(e.target.value)} placeholder="—" />
          </div>
          <p className="mt-2 text-[11.5px] leading-relaxed text-ink-muted">
            Leave blank to use district soil averages — the result is labelled as an estimate.
          </p>
        </Card>

        <Button block size="lg" loading={loading} onClick={submit}>
          <Sprout className="h-4 w-4" strokeWidth={2.2} />
          {loading ? 'Matching crops…' : 'Get recommendations'}
        </Button>
        {!user && (
          <p className="pb-2 text-center text-[11px] text-ink-muted">
            You are not signed in — results use this device's profile.
          </p>
        )}
      </div>
    </AppShell>
  );
};

export default CropRecommendationsPage;
