import * as React from 'react';
import { Beaker, FlaskConical, LocateFixed, MapPin, Sparkles } from 'lucide-react';
import { toast } from 'sonner';
import { AppShell } from '@/components/ui-kit/AppShell';
import { Badge, Card, CardLabel, EmptyState, PageHeader, ProgressRing } from '@/components/ui-kit/core';
import { Button, Input, Select } from '@/components/ui-kit/form';
import { cachedLocation, readCachedProfile } from '@/lib/profile';
import { getDistricts } from '@/lib/indian-locations';
import { getDefaultNPK, getFertilizerRecommendation } from '@/lib/api';
import type { RequestPayload } from '@/lib/apiTypes';

const CROPS = [
  'Rice', 'Wheat', 'Maize', 'Cotton', 'Soybean', 'Sugarcane', 'Chickpea',
  'Pigeon Pea', 'Green Gram', 'Black Gram', 'Lentil', 'Groundnut', 'Mustard',
  'Sunflower', 'Potato', 'Tomato', 'Onion', 'Chilli', 'Turmeric', 'Ginger',
  'Jowar', 'Bajra', 'Ragi', 'Barley',
];

const SOILS = [
  'Loamy Soil', 'Clayey Soil', 'Sandy Soil', 'Black Soil',
  'Red Soil', 'Peaty Soil', 'Acidic Soil', 'Alkaline Soil',
];

interface Match {
  Fertilizer?: string;
  Similarity?: number;
  Remark?: string;
}

interface FertilizerResponse {
  recommended_fertilizers?: string[];
  top_matches?: Match[];
  soil_nutrients?: Record<string, number>;
  source?: string;
  error?: string;
}

/**
 * Fertiliser advisor.
 * Crop + soil type are the only required inputs; NPK/pH come from the saved
 * soil card or the district soil survey. A repeated fertiliser in the model's
 * top matches is de-duplicated so the list is useful rather than padded.
 */
const FertilizerRecommendationPage: React.FC = () => {
  const saved = React.useMemo(() => cachedLocation(), []);
  const soil = React.useMemo(() => readCachedProfile()?.soil || null, []);
  const districts = React.useMemo(() => getDistricts(saved.state), [saved.state]);

  const [crop, setCrop] = React.useState('');
  const [soilType, setSoilType] = React.useState('');
  const [district, setDistrict] = React.useState(saved.district);
  const [nitrogen, setNitrogen] = React.useState(soil?.n != null ? String(soil.n) : '');
  const [phosphorus, setPhosphorus] = React.useState(soil?.p != null ? String(soil.p) : '');
  const [potassium, setPotassium] = React.useState(soil?.k != null ? String(soil.k) : '');
  const [ph, setPh] = React.useState(soil?.ph != null ? String(soil.ph) : '');

  const [loading, setLoading] = React.useState(false);
  const [fetching, setFetching] = React.useState(false);
  const [result, setResult] = React.useState<FertilizerResponse | null>(null);
  const [soilSource, setSoilSource] = React.useState<string | null>(
    soil ? 'your saved soil card' : null,
  );

  const autofill = async () => {
    if (!district) {
      toast.error('Select your district first');
      return;
    }
    setFetching(true);
    try {
      const data = await getDefaultNPK({ district, state: saved.state, mode: 'auto' });
      if (!data || data.error) {
        toast.error('Could not load district soil data');
        return;
      }
      setNitrogen(String(data.N));
      setPhosphorus(String(data.P));
      setPotassium(String(data.K));
      setPh(String(data.ph));
      setSoilSource(
        data.source === 'district_soil_survey' ? 'district soil survey' : data.source || 'district data',
      );
      toast.success('Filled from district soil data');
    } catch {
      toast.error('Could not load district soil data');
    } finally {
      setFetching(false);
    }
  };

  const submit = async () => {
    if (!crop || !soilType) {
      toast.error('Choose a crop and a soil type');
      return;
    }
    setLoading(true);
    setResult(null);
    try {
      const payload: RequestPayload = { crop, soil: soilType, top_k: 5 };
      if (nitrogen) payload.N = Number(nitrogen);
      if (phosphorus) payload.P = Number(phosphorus);
      if (potassium) payload.K = Number(potassium);
      if (ph) payload.PH = Number(ph);
      if (district) {
        payload.district = district;
        payload.state = saved.state || undefined;
        payload.mode = 'auto';
      }

      const data = (await getFertilizerRecommendation(payload)) as FertilizerResponse | null;
      if (!data) {
        toast.error('The fertiliser service did not answer — is the backend running?');
        return;
      }
      if (data.error) {
        toast.error(data.error);
        return;
      }
      setResult(data);
    } catch {
      toast.error('Something went wrong getting the advice');
    } finally {
      setLoading(false);
    }
  };

  // The model can return the same fertiliser more than once; keep the best hit.
  const matches = React.useMemo(() => {
    const seen = new Map<string, Match>();
    for (const m of result?.top_matches || []) {
      const key = (m.Fertilizer || '').trim();
      if (!key) continue;
      const existing = seen.get(key);
      if (!existing || (m.Similarity ?? 0) > (existing.Similarity ?? 0)) seen.set(key, m);
    }
    return [...seen.values()].sort((a, b) => (b.Similarity ?? 0) - (a.Similarity ?? 0));
  }, [result]);

  return (
    <AppShell>
      <PageHeader
        title="Fertiliser advice"
        subtitle="What to apply, and how your soil compares to the crop's need"
      />

      <div className="max-w-2xl space-y-4">
        <Card>
          <CardLabel>Crop & soil</CardLabel>
          <div className="mt-2 space-y-2.5">
            <Select
              label="Crop"
              placeholder="Which crop are you fertilising?"
              value={crop}
              onChange={setCrop}
              options={CROPS.map((c) => ({ value: c, label: c }))}
              icon={<Beaker className="h-4 w-4" strokeWidth={1.9} />}
            />
            <Select
              label="Soil type"
              placeholder="Select your soil"
              value={soilType}
              onChange={setSoilType}
              options={SOILS.map((s) => ({ value: s, label: s }))}
            />
            <Select
              label="District"
              placeholder="Choose your district"
              value={district}
              onChange={setDistrict}
              options={districts.map((d) => ({ value: d, label: d }))}
              icon={<MapPin className="h-4 w-4" strokeWidth={1.9} />}
              helper={saved.state ? `Districts in ${saved.state}` : 'Set a state in Profile first'}
            />
          </div>
        </Card>

        <Card>
          <div className="flex items-center justify-between gap-2">
            <CardLabel>Soil test (optional)</CardLabel>
            <button
              type="button"
              onClick={autofill}
              disabled={fetching}
              className="press inline-flex items-center gap-1.5 rounded-full border border-border bg-surface px-3 py-1.5 text-[11.5px] font-700 text-primary disabled:opacity-60"
            >
              <LocateFixed className="h-3.5 w-3.5" strokeWidth={2.2} />
              {fetching ? 'Filling…' : 'Auto-fill from district'}
            </button>
          </div>
          {soilSource && <p className="mt-1.5 text-[11px] text-ink-muted">Using {soilSource}</p>}
          <div className="mt-2.5 grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Input label="Nitrogen" unit="kg/ha" inputMode="decimal" value={nitrogen} onChange={(e) => setNitrogen(e.target.value)} placeholder="—" />
            <Input label="Phosphorus" unit="kg/ha" inputMode="decimal" value={phosphorus} onChange={(e) => setPhosphorus(e.target.value)} placeholder="—" />
            <Input label="Potassium" unit="kg/ha" inputMode="decimal" value={potassium} onChange={(e) => setPotassium(e.target.value)} placeholder="—" />
            <Input label="pH" inputMode="decimal" value={ph} onChange={(e) => setPh(e.target.value)} placeholder="—" />
          </div>
        </Card>

        <Button block size="lg" loading={loading} onClick={submit}>
          <FlaskConical className="h-4 w-4" strokeWidth={2.2} />
          {loading ? 'Matching fertilisers…' : 'Get fertiliser advice'}
        </Button>

        {result && (
          <div className="space-y-3 pb-4">
            {result.recommended_fertilizers?.length ? (
              <Card variant="gold">
                <p className="text-[10.5px] font-700 uppercase tracking-[0.08em] text-forest/70">
                  Recommended for this soil
                </p>
                <p className="mt-1 font-display text-[19px] font-800 leading-tight text-forest">
                  {[...new Set(result.recommended_fertilizers)].join(' + ')}
                </p>
              </Card>
            ) : null}

            {result.soil_nutrients && (
              <Card>
                <CardLabel>Soil used for this answer</CardLabel>
                <div className="mt-2 grid grid-cols-4 gap-2">
                  {Object.entries(result.soil_nutrients).map(([k, v]) => (
                    <div key={k} className="rounded-sm bg-surface-2 px-2 py-2 text-center">
                      <p className="text-[10px] font-700 uppercase tracking-wide text-ink-muted">{k}</p>
                      <p className="font-display text-[15px] font-800 tabular-nums text-ink">
                        {typeof v === 'number' ? Math.round(v) : '--'}
                      </p>
                    </div>
                  ))}
                </div>
              </Card>
            )}

            {matches.length ? (
              <div className="space-y-2">
                <p className="px-1 text-[11px] font-700 uppercase tracking-[0.08em] text-ink-muted">
                  Best matches
                </p>
                {matches.map((m) => {
                  const similarity = Math.round((m.Similarity ?? 0) * 100);
                  return (
                    <Card key={m.Fertilizer} className="flex items-start gap-3">
                      <ProgressRing value={similarity} size={46} stroke={4.5} label={`${similarity}`} />
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <p className="font-display text-[14.5px] font-800 text-ink">
                            {m.Fertilizer}
                          </p>
                          <Badge tone="neutral">{similarity}% match</Badge>
                        </div>
                        {m.Remark && (
                          <p className="mt-1 text-[12px] leading-relaxed text-ink-muted">{m.Remark}</p>
                        )}
                      </div>
                    </Card>
                  );
                })}
              </div>
            ) : (
              <EmptyState
                title="No fertiliser matched"
                description="The model returned nothing for this crop and soil combination. Try a different soil type or add your soil test values."
              />
            )}

            <p className="px-1 text-[11px] leading-relaxed text-ink-muted">
              Guidance based on the dataset model, not a laboratory soil test. Confirm doses with
              your local Krishi Vigyan Kendra before applying.
            </p>
          </div>
        )}
      </div>
    </AppShell>
  );
};

export default FertilizerRecommendationPage;
