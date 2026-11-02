/**
 * Forecast chart: solid history line, dashed forecast line and a shaded
 * confidence band. Only real backtested numbers are plotted — an empty series
 * renders an EmptyState instead of a decorative fake curve.
 */
import * as React from 'react';
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { cn } from '@/lib/utils';

export interface HistoryPoint {
  date: string;
  price: number;
}

export interface ForecastPoint {
  date: string;
  predicted_price: number;
  ci_low?: number;
  ci_high?: number;
}

interface Row {
  date: string;
  actual?: number;
  forecast?: number;
  bandBase?: number;
  bandSize?: number;
}

function buildRows(history: HistoryPoint[], forecast: ForecastPoint[]): Row[] {
  const rows: Row[] = history.map((h) => ({ date: h.date, actual: h.price }));
  const last = history[history.length - 1];
  forecast.forEach((f, i) => {
    const low = f.ci_low ?? f.predicted_price;
    const high = f.ci_high ?? f.predicted_price;
    const row: Row = {
      date: f.date,
      forecast: f.predicted_price,
      bandBase: low,
      bandSize: Math.max(0, high - low),
    };
    if (i === 0 && last) {
      row.actual = last.price;
    }
    rows.push(row);
  });
  return rows;
}

const fmtDate = (d: string) => {
  const dt = new Date(d);
  if (Number.isNaN(dt.getTime())) return d;
  return dt.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' });
};

interface TipProps {
  active?: boolean;
  payload?: { payload?: Row }[];
  label?: string;
}

function TipBox({ active, payload, label }: TipProps) {
  if (!active || !payload?.length) return null;
  const row = payload[0]?.payload as Row;
  return (
    <div className="rounded-sm border border-border bg-surface px-3 py-2 shadow-md">
      <p className="text-[11px] font-600 uppercase tracking-wide text-ink-muted">{fmtDate(label)}</p>
      {row?.actual != null && (
        <p className="mt-0.5 text-[13px] font-700 tnum">
          ₹{row.actual.toLocaleString('en-IN')}
          <span className="ml-1 text-[10px] font-500 text-ink-muted">actual</span>
        </p>
      )}
      {row?.forecast != null && (
        <p className="mt-0.5 text-[13px] font-700 tnum text-primary">
          ₹{Math.round(row.forecast).toLocaleString('en-IN')}
          <span className="ml-1 text-[10px] font-500 text-ink-muted">forecast</span>
        </p>
      )}
      {row?.bandBase != null && row?.bandSize != null && (
        <p className="mt-0.5 text-[10.5px] text-ink-muted tnum">
          band ₹{Math.round(row.bandBase).toLocaleString('en-IN')}–
          {Math.round(row.bandBase + row.bandSize).toLocaleString('en-IN')}
        </p>
      )}
    </div>
  );
}

export function ForecastChart({
  history,
  forecast,
  height = 220,
  today,
  className,
}: {
  history: HistoryPoint[];
  forecast: ForecastPoint[];
  height?: number;
  today?: string;
  className?: string;
}) {
  const rows = React.useMemo(() => buildRows(history, forecast), [history, forecast]);
  const gid = React.useId().replace(/:/g, '');
  if (!rows.length) return null;

  const prices = rows.flatMap((r) => [r.actual, r.forecast, r.bandBase].filter(Boolean) as number[]);
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const pad = Math.max((max - min) * 0.15, 20);

  return (
    <div className={cn('w-full', className)} style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id={`area-${gid}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="hsl(var(--primary))" stopOpacity={0.32} />
              <stop offset="100%" stopColor="hsl(var(--primary))" stopOpacity={0} />
            </linearGradient>
            <linearGradient id={`band-${gid}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="hsl(var(--leaf))" stopOpacity={0.26} />
              <stop offset="100%" stopColor="hsl(var(--leaf))" stopOpacity={0.06} />
            </linearGradient>
          </defs>

          <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
          <XAxis
            dataKey="date"
            tickFormatter={fmtDate}
            tick={{ fontSize: 10, fill: 'hsl(var(--text-muted))' }}
            axisLine={false}
            tickLine={false}
            minTickGap={28}
          />
          <YAxis
            domain={[min - pad, max + pad]}
            allowDataOverflow
            tick={{ fontSize: 10, fill: 'hsl(var(--text-muted))' }}
            axisLine={false}
            tickLine={false}
            width={44}
            tickFormatter={(v: number) => `₹${Math.round(v / 100) / 10}k`}
          />
          <Tooltip content={<TipBox />} cursor={{ stroke: 'hsl(var(--border))' }} />

          {/* confidence band: invisible base + shaded size */}
          <Area
            type="monotone"
            dataKey="bandBase"
            stackId="band"
            stroke="none"
            fill="transparent"
            isAnimationActive={false}
          />
          <Area
            type="monotone"
            dataKey="bandSize"
            stackId="band"
            stroke="none"
            fill={`url(#band-${gid})`}
          />
          <Area
            type="monotone"
            dataKey="actual"
            stroke="hsl(var(--primary))"
            strokeWidth={2.4}
            fill={`url(#area-${gid})`}
            dot={false}
            activeDot={{ r: 3.5, strokeWidth: 0 }}
          />
          <Line
            type="monotone"
            dataKey="forecast"
            stroke="hsl(var(--accent))"
            strokeWidth={2.2}
            strokeDasharray="6 5"
            dot={false}
          />
          {today && (
            <ReferenceLine
              x={today}
              stroke="hsl(var(--text-muted))"
              strokeDasharray="3 3"
              label={{
                value: 'today',
                position: 'insideTopRight',
                fontSize: 9,
                fill: 'hsl(var(--text-muted))',
              }}
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

export function ChartLegend() {
  return (
    <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-[10.5px] text-ink-muted">
      <span className="inline-flex items-center gap-1.5">
        <span className="h-1.5 w-4 rounded-full bg-primary" /> Actual price
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="h-1.5 w-4 rounded-full" style={{ background: 'repeating-linear-gradient(90deg,hsl(var(--accent)) 0 4px,transparent 4px 7px)' }} />
        Forecast
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="h-2.5 w-4 rounded-sm bg-leaf/25" /> Confidence band
      </span>
    </div>
  );
}
