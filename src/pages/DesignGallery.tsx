/**
 * Dev-only component gallery (/design). Every kit component in light and dark,
 * at phone and desktop width — the visual contract for the redesign.
 */
import * as React from 'react';
import { Sprout, Store, TrendingUp } from 'lucide-react';
import { AppShell } from '@/components/ui-kit/AppShell';
import { HeroHeader, HeroChip } from '@/components/ui-kit/HeroHeader';
import {
  Avatar,
  Badge,
  Card,
  CardLabel,
  CardTitle,
  Chip,
  CountUp,
  EmptyState,
  ErrorState,
  PageHeader,
  PriceCardSkeleton,
  PriceSourceBadge,
  ProgressRing,
  SegmentedTabs,
  SectionHeader,
  Skeleton,
  Sparkline,
  StatTile,
} from '@/components/ui-kit/core';
import { Input, NumberStepper, OptionCard, Select, TextArea, Toggle } from '@/components/ui-kit/form';
import { PriceCard, CropThumb } from '@/components/ui-kit/PriceCard';
import { ForecastChart, ChartLegend } from '@/components/ui-kit/charts';
import { ThemeToggle } from '@/components/ThemeProvider';
import { LanguageSwitcher } from '@/components/LanguageSwitcher';

const DesignGallery: React.FC = () => {
  const [tab, setTab] = React.useState<'one' | 'two' | 'three'>('one');
  const [sel, setSel] = React.useState(true);

  return (
    <AppShell>
      <PageHeader
        title="Design system"
        subtitle="Every kit component, light and dark"
        right={<ThemeToggle />}
      />

      <div className="space-y-5">
        <section>
          <SectionHeader title="Hero" />
          <HeroHeader overlap>
            <p className="text-[11px] uppercase tracking-[0.14em] text-white/60">Namaste</p>
            <h2 className="font-display text-[24px] font-800">Ramesh</h2>
            <div className="mt-2 flex gap-1.5">
              <HeroChip icon={<Sprout className="h-3 w-3" />}>Guntur, Andhra Pradesh</HeroChip>
            </div>
          </HeroHeader>
          <div className="-mt-8">
            <Card>Content overlapping the hero edge</Card>
          </div>
        </section>

        <section>
          <SectionHeader title="Buttons & chips" />
          <div className="flex flex-wrap items-center gap-2">
            <button className="press rounded-sm px-4 py-2.5 text-[13px] font-700 text-white" style={{ background: 'var(--grad-leaf)' }}>
              Primary gradient
            </button>
            <button className="press rounded-sm border border-border bg-surface px-4 py-2.5 text-[13px] font-600">
              Secondary
            </button>
            <button className="press rounded-sm bg-gold px-4 py-2.5 text-[13px] font-700 text-forest">
              Gold
            </button>
            <Chip active>Active chip</Chip>
            <Chip>Idle chip</Chip>
          </div>
        </section>

        <section>
          <SectionHeader title="Badges" />
          <div className="flex flex-wrap gap-2">
            <Badge tone="live" dot>Live</Badge>
            <Badge tone="cached">Cached · 02 Nov</Badge>
            <Badge tone="unavailable">Unavailable</Badge>
            <Badge tone="gold">Harvest</Badge>
            <Badge tone="danger">Danger</Badge>
            <Badge tone="info">MSP reference</Badge>
            <PriceSourceBadge source="agmarknet_live" isReal />
            <PriceSourceBadge source="unavailable" />
          </div>
        </section>

        <section>
          <SectionHeader title="Stats & rings" />
          <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
            <StatTile label="Price" value={<CountUp value={8200} prefix="₹" />} deltaPct={2.4} icon={<TrendingUp className="h-4 w-4" />} />
            <StatTile label="Crops" value={12} icon={<Sprout className="h-4 w-4" />} />
            <Card className="flex items-center gap-3">
              <ProgressRing value={87} sublabel="match" />
              <div>
                <CardTitle>Rice</CardTitle>
                <p className="text-[11px] text-ink-muted">Suitability</p>
              </div>
            </Card>
            <Card className="flex items-center justify-between">
              <div>
                <CardLabel>30-day</CardLabel>
                <p className="text-[13px] font-700">Trend</p>
              </div>
              <Sparkline points={[10, 14, 12, 18, 22, 19, 26]} />
            </Card>
          </div>
        </section>

        <section>
          <SectionHeader title="Price cards" />
          <div className="space-y-2">
            <PriceCard
              data={{
                commodity: 'Tomato', market: 'Kolar APMC', price: 1850,
                min_price: 1200, max_price: 2200, date: '2026-10-31',
                source: 'agmarknet_live', is_real: true,
              }}
              spark={[14, 16, 13, 18, 17, 21, 19]}
              deltaPct={4.2}
            />
            <PriceCard
              data={{ commodity: 'Onion', market: '', price: null, source: 'unavailable', detail: 'No mandi record for this district yet' }}
            />
          </div>
        </section>

        <section>
          <SectionHeader title="Chart" />
          <Card>
            <ForecastChart
              history={[
                { date: '2026-10-01', price: 1500 },
                { date: '2026-10-10', price: 1620 },
                { date: '2026-10-20', price: 1580 },
              ]}
              forecast={[
                { date: '2026-10-31', predicted_price: 1650, ci_low: 1580, ci_high: 1720 },
                { date: '2026-11-05', predicted_price: 1710, ci_low: 1600, ci_high: 1830 },
                { date: '2026-11-12', predicted_price: 1780, ci_low: 1620, ci_high: 1930 },
              ]}
              height={200}
            />
            <ChartLegend />
          </Card>
        </section>

        <section>
          <SectionHeader title="Form controls" />
          <div className="grid gap-2 sm:grid-cols-2">
            <Input label="Search" placeholder="Tomato, onion…" />
            <Select label="District" value="" onChange={() => {}} options={[{ value: 'kolar', label: 'Kolar' }]} />
            <NumberStepper label="Nitrogen" value="90" onChange={() => {}} unit="kg/ha" helper="From your soil card" />
            <TextArea label="Notes" placeholder="Anything else…" />
            <Toggle checked onChange={() => {}} label="Price alerts" description="Get a ping when the target is hit" />
            <OptionCard selected={sel} onClick={() => setSel((s) => !s)} title="Organic" subtitle="No synthetic inputs" icon={<Sprout className="h-4 w-4" />} />
          </div>
          <div className="mt-2">
            <SegmentedTabs
              value={tab}
              onChange={setTab}
              tabs={[
                { value: 'one', label: 'Kharif' },
                { value: 'two', label: 'Rabi' },
                { value: 'three', label: 'Zaid' },
              ]}
            />
          </div>
        </section>

        <section>
          <SectionHeader title="States" />
          <div className="grid gap-2 sm:grid-cols-2">
            <EmptyState title="No data yet" description="This is the honest empty state." />
            <ErrorState description="Something failed" onRetry={() => {}} />
            <PriceCardSkeleton />
            <Card className="space-y-2">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-3 w-full" />
              <Skeleton className="h-3 w-2/3" />
            </Card>
          </div>
        </section>

        <section>
          <SectionHeader title="Identity" />
          <div className="flex flex-wrap items-center gap-2">
            <Avatar name="Ramesh Kumar" />
            <Avatar name="Lakshmi Devi" size={44} />
            <CropThumb crop="Tomato" />
            <CropThumb crop="Banana" />
            <CropThumb crop="Onion" />
            <LanguageSwitcher />
            <Badge tone="neutral"><Store className="h-3 w-3" /> Market</Badge>
          </div>
        </section>
      </div>
    </AppShell>
  );
};

export default DesignGallery;
