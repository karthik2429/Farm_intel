import {
  FlaskConical,
  Home,
  Repeat2,
  Sprout,
  Store,
  TrendingUp,
  type LucideIcon,
} from 'lucide-react';

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  group: 'main' | 'tools';
  /** shows in the phone bottom bar */
  primary?: boolean;
}

/**
 * One nav definition for the desktop rail and the phone bottom bar.
 * There is no "AI App" and no "Marketplace" tab any more.
 */
export const NAV_ITEMS: NavItem[] = [
  { to: '/home', label: 'Home', icon: Home, group: 'main', primary: true },
  { to: '/market', label: 'Market', icon: Store, group: 'main', primary: true },
  { to: '/predict', label: 'Predict', icon: TrendingUp, group: 'main', primary: true },
  { to: '/crops', label: 'Crops', icon: Sprout, group: 'tools', primary: true },
  { to: '/rotation', label: 'Rotation', icon: Repeat2, group: 'tools' },
  { to: '/fertilizer', label: 'Fertilizer', icon: FlaskConical, group: 'tools' },
];

export const CHAT_ROUTE = '/chat';
