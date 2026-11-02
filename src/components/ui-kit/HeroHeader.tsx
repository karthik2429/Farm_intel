/**
 * The one gradient hero per screen. Rounded bottom corners, leaf/topographic
 * texture at low opacity, and a slot whose children can overlap the hero edge
 * (the classic -48px card overlap).
 */
import * as React from 'react';
import { cn } from '@/lib/utils';

export function HeroHeader({
  children,
  className,
  overlap,
  bottomSlot,
}: {
  children: React.ReactNode;
  className?: string;
  /** When true, the wrapper pulls following content up by 48px. */
  overlap?: boolean;
  bottomSlot?: React.ReactNode;
}) {
  return (
    <div className={cn('relative -mx-4 -mt-4 sm:-mx-6', className)}>
      <div className="hero-gradient hero-texture grain overflow-hidden rounded-b-lg px-4 pb-20 pt-4 text-white sm:px-6">
        {children}
      </div>
      {overlap && <div className="pointer-events-none absolute -bottom-12 left-0 right-0 h-12" />}
      {bottomSlot}
    </div>
  );
}

/** Frosted chip used inside heroes (location, weather, time). */
export function HeroChip({
  icon,
  children,
  onClick,
  className,
}: {
  icon?: React.ReactNode;
  children: React.ReactNode;
  onClick?: () => void;
  className?: string;
}) {
  const Comp = onClick ? 'button' : 'span';
  return (
    <Comp
      type={onClick ? 'button' : undefined}
      onClick={onClick}
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border border-white/20 bg-white/12 px-3 py-1.5 text-[12px] font-600 text-white backdrop-blur-md',
        onClick && 'press hover:bg-white/20',
        className,
      )}
    >
      {icon}
      {children}
    </Comp>
  );
}
