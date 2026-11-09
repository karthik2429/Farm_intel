import * as React from 'react';
import { AlertTriangle, ArrowRight, LocateFixed, MapPin, Repeat2, Sparkles } from 'lucide-react';
import { toast } from 'sonner';
import { AppShell } from '@/components/ui-kit/AppShell';
import { Badge, Card, CardLabel, EmptyState, PageHeader } from '@/components/ui-kit/core';
import { Button, Input, Select } from '@/components/ui-kit/form';
import { CropThumb } from '@/components/ui-kit/PriceCard';
import { cachedLocation, readCachedProfile } from '@/lib/profile';
import { getDistricts } from '@/lib/indian-locations';
import { getDefaultNPK, getRotationPlan } from '@/lib/api';
import type { RequestPayload } from '@/lib/apiTypes';

const CROPS = [
  'Rice', 'Wheat', 'Maize', 'Cotton', 'Soybean', 'Sugarcane', 'Chickpea',
  'Pigeon Pea', 'Green Gram', 'Black Gram', 'Lentil', 'Groundnut', 'Mustard',
  'Sunflower', 'Potato', 'Tomato', 'Onion', 'Chilli', 'Turmeric', 'Ginger',
  'Jowar', 'Bajra', 'Ragi', 'Barley', 'Cowpea', 'Castor', 'Jute', 'Mango',
  'Banana', 'Papaya', 'Pomegranate', 'Grapes', 'Coconut', 'Coriander', 'Cumin',
];

interface SeasonOption {
  crop: string;
  family?: string;
  season?: string;
  final_score?: number;
  nitrogen_fixing?: boolean;
  N_gap?: number;
  P_gap?: number;
  K_gap?: number;
  soil_type?: string;
  ph_range?: string;
  temp_range?: string;
}

interface PlanResponse {
  season1?: string;
  season2_options?: SeasonOption[];
  season2_best?: string;
  season3_preview?: string;
  soil_after_s1?: Record<string, number>;
  soil_after_s2?: Record<string, number>;
  warnings?: string[];
  input_npk?: Record<string, number>;
  error?: string;
}

/**
 * Rotation planner.
 * Soil values are prefilled from the saved soil card, or from the district soil
 * survey when there is none — and the card says which one was used.
 */
const CropRotationPage: React.FC = () => {
  const saved = React.useMemo(() => cachedLocation(), []);
  const soil = React.useMemo(() => readCachedProfile()?.soil || null, []);

  const [prevCrop, setPrevCrop] = React.useState('');
  const [nitrogen, setNitrogen] = React.useState(soil?.n != null ? String(soil.n) : '');
  const [phosphorus, setPhosphorus] = React.useState(soil?.p != null ? String(soil.p) : '');
  const [potassium, setPotassium] = React.useState(soil?.k != null ? String(soil.k) : '');
  const [ph, setPh] = React.useState(soil?.ph != null ? String(soil.ph) : '');
  const [district, setDistrict] = React.useState(saved.district);
  const districts = React.useMemo(() => getDistricts(saved.state), [saved.state]);

  const [loading, setLoading] = React.useState(false);
  const [fetching, setFetching] = React.useState(false);
  const [result, setResult] = React.useState<PlanResponse | null>(null);
  const [soilSource, setSoilSource] = React.useState<string | null>(
    soil ? 'your saved soil card' : null,
  );

  /** Pull real district soil survey values into the form. */
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
      setSoilSource(data.source === 'district_soil_survey' ? 'district soil survey' : data.source || 'district data');
      toast.success('Filled from district soil data');
    } catch {
      toast.error('Could not load district soil data');
    } finally {
      setFetching(false);
    }
  };

  const submit = async () => {
    if (!prevCrop) {
      toast.error('Choose the crop you just harvested');
      return;
    }
    if (!district) {
      toast.error('Choose your district');
      return;
    }
    setLoading(true);
    setResult(null);
    try {
      const payload: RequestPayload = {
        season1_crop: prevCrop,
        district,
        state: saved.state || undefined,
        mode: 'auto',
        top_n: 3,
      };
      if (nitrogen) payload.N = Number(nitrogen);
      if (phosphorus) payload.P = Number(phosphorus);
      if (potassium) payload.K = Number(potassium);
      if (ph) payload.ph = Number(ph);

      const data = (await getRotationPlan(payload)) as PlanResponse | null;
      if (!data) {
        toast.error('The rotation service did not answer — is the backend running?');
        return;
      }
      if (data.error) {
        toast.error(data.error);
        return;
      }
      setResult(data);
    } catch {
      toast.error('Something went wrong building the plan');
    } finally {
      setLoading(false);
    }
  };

  const pct = (v?: number) => (typeof v === 'number' ? Math.round(v * 100) : null);

  return (
    <AppShell>
      <PageHeader
        title="Crop rotation"
        subtitle="What to sow next, and what it will take from your soil"
      />

      <div className="max-w-2xl space-y-4">
        <Card>
          <CardLabel>After harvest</CardLabel>
          <div className="mt-2 space-y-2.5">
            <Select
              label="Previous crop"
              placeholder="Select the crop you harvested"
              value={prevCrop}
              onChange={setPrevCrop}
              options={CROPS.map((c) => ({ value: c, label: c }))}
              icon={<Repeat2 className="h-4 w-4" strokeWidth={1.9} />}
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
            <CardLabel>Soil now</CardLabel>
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
          {soilSource && (
            <p className="mt-1.5 text-[11px] text-ink-muted">Using {soilSource}</p>
          )}
          <div className="mt-2.5 grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Input label="Nitrogen" unit="kg/ha" inputMode="decimal" value={nitrogen} onChange={(e) => setNitrogen(e.target.value)} placeholder="—" />
            <Input label="Phosphorus" unit="kg/ha" inputMode="decimal" value={phosphorus} onChange={(e) => setPhosphorus(e.target.value)} placeholder="—" />
            <Input label="Potassium" unit="kg/ha" inputMode="decimal" value={potassium} onChange={(e) => setPotassium(e.target.value)} placeholder="—" />
            <Input label="pH" inputMode="decimal" value={ph} onChange={(e) => setPh(e.target.value)} placeholder="—" />
          </div>
        </Card>

        <Button block size="lg" loading={loading} onClick={submit}>
          <Sparkles className="h-4 w-4" strokeWidth={2.2} />
          {loading ? 'Building your plan…' : 'Generate rotation plan'}
        </Button>

        {result && (
          <div className="space-y-3 pb-4">
            {result.warnings?.length ? (
              <Card variant="flat" className="border-harvest/40 bg-harvest/10">
                <div className="flex items-start gap-2">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-ink" strokeWidth={2} />
                  <div className="space-y-0.5">
                    {result.warnings.map((w) => (
                      <p key={w} className="text-[12px] text-ink">{w}</p>
                    ))}
                  </div>
                </div>
              </Card>
            ) : null}

            <Card>
              <CardLabel>The plan</CardLabel>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <Stage label="Season 1" crop={result.season1 || prevCrop} muted />
                <ArrowRight className="h-3.5 w-3.5 text-ink-muted" strokeWidth={2.2} />
                <Stage label="Season 2" crop={result.season2_best || '—'} />
                <ArrowRight className="h-3.5 w-3.5 text-ink-muted" strokeWidth={2.2} />
                <Stage label="Season 3" crop={result.season3_preview || '—'} muted />
              </div>
            </Card>

            {result.season2_options?.length ? (
              <div className="space-y-2">
                <p className="px-1 text-[11px] font-700 uppercase tracking-[0.08em] text-ink-muted">
                  Best next crops
                </p>
                {result.season2_options.map((opt) => (
                  <Card key={opt.crop} className="flex items-start gap-3">
                    <CropThumb crop={opt.crop} size={48} />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <p className="font-display text-[14.5px] font-800 text-ink">{opt.crop}</p>
                        {opt.nitrogen_fixing && <Badge tone="live">fixes nitrogen</Badge>}
                        {pct(opt.final_score) != null && (
                          <Badge tone="neutral">{pct(opt.final_score)}% match</Badge>
                        )}
                      </div>
                      <p className="mt-0.5 text-[11.5px] text-ink-muted">
                        {[opt.family, opt.season, opt.soil_type].filter(Boolean).join(' · ') || '—'}
                      </p>
                      <div className="mt-1.5 flex flex-wrap gap-1.5">
                        <NutrientChip label="N top-up" value={opt.N_gap} />
                        <NutrientChip label="P top-up" value={opt.P_gap} />
                        <NutrientChip label="K top-up" value={opt.K_gap} />
                      </div>
                    </div>
                  </Card>
                ))}
              </div>
            ) : (
              <EmptyState
                title="No follow-on crops returned"
                description="The model found no suitable season-2 crop for this soil. Try another previous crop or refresh the soil values."
              />
            )}

            {result.soil_after_s1 && (
              <Card>
                <CardLabel>Soil after season 1</CardLabel>
                <div className="mt-2 grid grid-cols-3 gap-2">
                  {['N', 'P', 'K'].map((k) => (
                    <div key={k} className="rounded-sm bg-surface-2 px-2 py-2 text-center">
                      <p className="text-[10px] font-700 uppercase tracking-wide text-ink-muted">{k}</p>
                      <p className="font-display text-[16px] font-800 tabular-nums text-ink">
                        {result.soil_after_s1?.[k] ?? '--'}
                      </p>
                    </div>
                  ))}
                </div>
              </Card>
            )}
          </div>
        )}
      </div>
    </AppShell>
  );
};

function Stage({ label, crop, muted }: { label: string; crop: string; muted?: boolean }) {
  return (
    <div
      className={
        muted
          ? 'rounded-sm border border-border bg-surface-2 px-2.5 py-1.5'
          : 'rounded-sm border border-primary/35 bg-primary/10 px-2.5 py-1.5'
      }
    >
      <p className="text-[9.5px] font-700 uppercase tracking-wide text-ink-muted">{label}</p>
      <p className="font-display text-[13px] font-800 text-ink">{crop}</p>
    </div>
  );
}

function NutrientChip({ label, value }: { label: string; value?: number }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-border bg-surface-2 px-2 py-0.5 text-[10.5px] font-600 text-ink-muted">
      {label}
      <span className="font-800 tabular-nums text-ink">
        {typeof value === 'number' ? `${value}` : '--'}
      </span>
    </span>
  );
}

export default CropRotationPage;
