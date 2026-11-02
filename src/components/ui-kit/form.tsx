/**
 * Form primitives — the only inputs the app is allowed to use.
 *
 * Everything is 52px tall, sits on --surface-2, has a floating label, an
 * optional leading icon and unit suffix, and shows helper/error text.
 * No plain white native input boxes anywhere.
 */
import * as React from 'react';
import { Check, ChevronDown, Minus, Plus } from 'lucide-react';
import { cn } from '@/lib/utils';

const fieldShell =
  'group relative flex h-[52px] w-full items-center gap-2 rounded-sm border bg-surface-2 px-3 transition-all duration-200 ' +
  'focus-within:border-primary focus-within:ring-2 focus-within:ring-primary/20';

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label: string;
  icon?: React.ReactNode;
  unit?: string;
  helper?: string;
  error?: string;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ label, icon, unit, helper, error, className, id, ...props }, ref) => {
    const autoId = React.useId();
    const inputId = id || autoId;
    return (
      <div className="w-full">
        <div className={cn(fieldShell, error ? 'border-destructive' : 'border-border', className)}>
          {icon && <span className="shrink-0 text-ink-muted">{icon}</span>}
          <div className="relative flex-1">
            <label
              htmlFor={inputId}
              className="pointer-events-none absolute left-0 top-1.5 text-[10.5px] font-600 uppercase tracking-[0.07em] text-ink-muted"
            >
              {label}
            </label>
            <input
              id={inputId}
              ref={ref}
              className="peer w-full bg-transparent pt-5 text-[15px] font-500 text-ink outline-none placeholder:text-ink-muted/60"
              {...props}
            />
          </div>
          {unit && <span className="shrink-0 text-[12px] font-600 text-ink-muted">{unit}</span>}
        </div>
        {(error || helper) && (
          <p
            className={cn(
              'mt-1.5 pl-1 text-[11.5px] leading-snug',
              error ? 'text-destructive' : 'text-ink-muted',
            )}
          >
            {error || helper}
          </p>
        )}
      </div>
    );
  },
);
Input.displayName = 'Input';

export interface SelectOption {
  value: string;
  label: string;
}

export function Select({
  label,
  options,
  value,
  onChange,
  icon,
  helper,
  error,
  placeholder,
  disabled,
  className,
}: {
  label: string;
  options: SelectOption[];
  value: string;
  onChange: (value: string) => void;
  icon?: React.ReactNode;
  helper?: string;
  error?: string;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
}) {
  const id = React.useId();
  return (
    <div className="w-full">
      <div
        className={cn(
          fieldShell,
          error ? 'border-destructive' : 'border-border',
          disabled && 'opacity-60',
          className,
        )}
      >
        {icon && <span className="shrink-0 text-ink-muted">{icon}</span>}
        <div className="relative flex-1">
          <label
            htmlFor={id}
            className="pointer-events-none absolute left-0 top-1.5 text-[10.5px] font-600 uppercase tracking-[0.07em] text-ink-muted"
          >
            {label}
          </label>
          <select
            id={id}
            value={value}
            disabled={disabled}
            onChange={(e) => onChange(e.target.value)}
            className="w-full appearance-none bg-transparent pt-5 text-[15px] font-500 text-ink outline-none"
          >
            <option value="">{placeholder || `Select ${label.toLowerCase()}`}</option>
            {options.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
        <ChevronDown className="h-4 w-4 shrink-0 text-ink-muted" strokeWidth={1.75} />
      </div>
      {(error || helper) && (
        <p
          className={cn(
            'mt-1.5 pl-1 text-[11.5px] leading-snug',
            error ? 'text-destructive' : 'text-ink-muted',
          )}
        >
          {error || helper}
        </p>
      )}
    </div>
  );
}

export function NumberStepper({
  label,
  value,
  onChange,
  min = 0,
  max = 1000,
  step = 1,
  unit,
  helper,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  min?: number;
  max?: number;
  step?: number;
  unit?: string;
  helper?: string;
}) {
  const num = Number(value);
  const safe = Number.isFinite(num) ? num : min;
  const set = (n: number) => onChange(String(Math.max(min, Math.min(max, n))));

  return (
    <div className="w-full">
      <div className={cn(fieldShell, 'border-border')}>
        <div className="relative flex-1">
          <span className="absolute left-0 top-1.5 text-[10.5px] font-600 uppercase tracking-[0.07em] text-ink-muted">
            {label}
          </span>
          <input
            type="number"
            inputMode="decimal"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            className="w-full bg-transparent pt-5 text-[15px] font-500 tnum text-ink outline-none [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none"
          />
        </div>
        {unit && <span className="text-[12px] font-600 text-ink-muted">{unit}</span>}
        <div className="flex items-center gap-1">
          <button
            type="button"
            aria-label={`Decrease ${label}`}
            onClick={() => set(safe - step)}
            className="press grid h-8 w-8 place-items-center rounded-full border border-border bg-surface text-ink hover:bg-surface-2"
          >
            <Minus className="h-3.5 w-3.5" strokeWidth={2.2} />
          </button>
          <button
            type="button"
            aria-label={`Increase ${label}`}
            onClick={() => set(safe + step)}
            className="press grid h-8 w-8 place-items-center rounded-full border border-border bg-surface text-ink hover:bg-surface-2"
          >
            <Plus className="h-3.5 w-3.5" strokeWidth={2.2} />
          </button>
        </div>
      </div>
      {helper && <p className="mt-1.5 pl-1 text-[11.5px] leading-snug text-ink-muted">{helper}</p>}
    </div>
  );
}

export function OptionCard({
  selected,
  onClick,
  title,
  subtitle,
  icon,
  badge,
  className,
}: {
  selected?: boolean;
  onClick?: () => void;
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  icon?: React.ReactNode;
  badge?: React.ReactNode;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      className={cn(
        'press relative flex w-full items-center gap-3 rounded-sm border p-3 text-left transition-all',
        selected
          ? 'border-primary bg-primary/8 shadow-[0_0_0_1px_hsl(var(--primary))]'
          : 'border-border bg-surface hover:border-primary/40',
        className,
      )}
    >
      {icon && (
        <span
          className={cn(
            'grid h-10 w-10 shrink-0 place-items-center rounded-sm',
            selected ? 'bg-primary text-primary-foreground' : 'bg-surface-2 text-ink-muted',
          )}
        >
          {icon}
        </span>
      )}
      <span className="min-w-0 flex-1">
        <span className="block truncate font-display text-[14px] font-700">{title}</span>
        {subtitle && <span className="mt-0.5 block text-[12px] text-ink-muted">{subtitle}</span>}
      </span>
      {badge}
      <span
        className={cn(
          'grid h-5 w-5 shrink-0 place-items-center rounded-full border transition-colors',
          selected ? 'border-primary bg-primary text-primary-foreground' : 'border-border',
        )}
      >
        {selected && <Check className="h-3 w-3" strokeWidth={3} />}
      </span>
    </button>
  );
}

export function TextArea({
  label,
  helper,
  className,
  ...props
}: React.TextareaHTMLAttributes<HTMLTextAreaElement> & { label: string; helper?: string }) {
  return (
    <div className="w-full">
      <div className={cn('rounded-sm border border-border bg-surface-2 p-3 transition-all focus-within:border-primary focus-within:ring-2 focus-within:ring-primary/20', className)}>
        <span className="block text-[10.5px] font-600 uppercase tracking-[0.07em] text-ink-muted">
          {label}
        </span>
        <textarea
          className="mt-1 w-full resize-none bg-transparent text-[15px] text-ink outline-none placeholder:text-ink-muted/60"
          rows={3}
          {...props}
        />
      </div>
      {helper && <p className="mt-1.5 pl-1 text-[11.5px] text-ink-muted">{helper}</p>}
    </div>
  );
}

export function Toggle({
  checked,
  onChange,
  label,
  description,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  description?: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className="flex w-full items-center justify-between gap-4 rounded-sm border border-border bg-surface p-3 text-left"
    >
      <span className="min-w-0">
        <span className="block font-display text-[14px] font-700">{label}</span>
        {description && <span className="mt-0.5 block text-[12px] text-ink-muted">{description}</span>}
      </span>
      <span
        className={cn(
          'relative h-6 w-11 shrink-0 rounded-full transition-colors',
          checked ? 'bg-primary' : 'bg-surface-2 border border-border',
        )}
      >
        <span
          className={cn(
            'absolute top-0.5 h-5 w-5 rounded-full bg-white shadow-sm transition-transform duration-200',
            checked ? 'translate-x-[22px]' : 'translate-x-0.5',
          )}
        />
      </span>
    </button>
  );
}
