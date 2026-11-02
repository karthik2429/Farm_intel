/**
 * Legacy entry point. The app navigation now lives in ui-kit/AppShell
 * (desktop rail + glass phone bar + raised gold chat action). Pages that
 * still render <BottomNav /> get exactly the same chrome, without the old
 * Marketplace and "AI App" tabs.
 */
import { NavChrome } from '@/components/ui-kit/AppShell';

const BottomNav = () => <NavChrome />;

export default BottomNav;
