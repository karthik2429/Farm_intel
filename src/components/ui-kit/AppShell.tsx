/**
 * App shell.
 *
 * Phone: glass top bar + glass bottom bar with a raised gold chat action.
 * Tablet/desktop: collapsible left rail with grouped nav and a user card,
 * content capped at 1200px. The floating chat button appears on every screen
 * from md upwards.
 */
import * as React from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { ChevronLeft, ChevronRight, Leaf, MessageCircle, Settings2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { CHAT_ROUTE, NAV_ITEMS } from '@/lib/nav';
import { Avatar } from './core';
import { ThemeToggle } from '@/components/ThemeProvider';
import { useLanguage } from '@/contexts/LanguageContext';

const RAIL_KEY = 'agrosmart.rail-collapsed';

/**
 * Navigation chrome only (desktop rail + phone bottom bar + floating chat).
 * Exported so legacy pages that still render <BottomNav /> get the same nav
 * instead of the old 8-tab bar with Marketplace and AI App.
 */
export function NavChrome() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { t } = useLanguage();
  const [collapsed, setCollapsed] = React.useState(() => localStorage.getItem(RAIL_KEY) === '1');
  const [name, setName] = React.useState<string>('');

  React.useEffect(() => {
    const raw = localStorage.getItem('farmintel_profile');
    if (raw) {
      try {
        setName(JSON.parse(raw)?.name || '');
      } catch {
        /* cache is best-effort only */
      }
    }
  }, []);

  const toggleRail = () => {
    setCollapsed((c) => {
      localStorage.setItem(RAIL_KEY, c ? '0' : '1');
      return !c;
    });
  };

  const main = NAV_ITEMS.filter((i) => i.primary);
  const phoneNav = [main[0], main[1], null, main[3], main[2]].filter(Boolean) as typeof NAV_ITEMS;

  return (
    <>
      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-40 hidden flex-col border-r border-border bg-surface/90 backdrop-blur-xl transition-[width] duration-300 ease-out md:flex',
          collapsed ? 'w-[76px]' : 'w-60',
        )}
      >
        <div className={cn('flex items-center gap-2.5 px-4 pb-4 pt-5', collapsed && 'justify-center px-2')}>
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-sm bg-hero text-white shadow-glow">
            <Leaf className="h-5 w-5" strokeWidth={2} />
          </span>
          {!collapsed && (
            <span className="min-w-0">
              <span className="block truncate font-display text-[15px] font-800 leading-tight">AgroSmart</span>
              <span className="block text-[10px] font-600 uppercase tracking-[0.12em] text-ink-muted">Kisan AI</span>
            </span>
          )}
        </div>

        <nav className="flex-1 space-y-1 overflow-y-auto px-2">
          {!collapsed && (
            <p className="px-3 pb-1 pt-2 text-[10px] font-700 uppercase tracking-[0.12em] text-ink-muted">
              {t('nav.main')}
            </p>
          )}
          {NAV_ITEMS.filter((i) => i.group === 'main').map((item) => (
            <RailLink key={item.to} item={item} active={pathname === item.to} collapsed={collapsed} />
          ))}
          {!collapsed && (
            <p className="px-3 pb-1 pt-3 text-[10px] font-700 uppercase tracking-[0.12em] text-ink-muted">
              {t('nav.tools')}
            </p>
          )}
          {NAV_ITEMS.filter((i) => i.group === 'tools').map((item) => (
            <RailLink key={item.to} item={item} active={pathname === item.to} collapsed={collapsed} />
          ))}
          <div className="pt-2">
            <RailLink
              item={{ to: CHAT_ROUTE, label: 'Chat', icon: MessageCircle, group: 'main' }}
              active={pathname === CHAT_ROUTE}
              collapsed={collapsed}
            />
          </div>
        </nav>

        <div className="border-t border-border p-2">
          <button
            type="button"
            onClick={() => navigate('/profile')}
            className={cn(
              'press flex w-full items-center gap-2.5 rounded-sm p-2 text-left hover:bg-surface-2',
              collapsed && 'justify-center',
            )}
          >
            <Avatar name={name} size={32} />
            {!collapsed && (
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[13px] font-700">{name || 'Your profile'}</span>
                <span className="block truncate text-[10.5px] text-ink-muted">Farm settings</span>
              </span>
            )}
            {!collapsed && <Settings2 className="h-4 w-4 text-ink-muted" strokeWidth={1.75} />}
          </button>
          <div className={cn('mt-2 flex items-center gap-2', collapsed ? 'justify-center' : 'justify-between px-1')}>
            <ThemeToggle />
            <button
              type="button"
              onClick={toggleRail}
              aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
              className="press grid h-8 w-8 place-items-center rounded-full border border-border text-ink-muted hover:bg-surface-2"
            >
              {collapsed ? <ChevronRight className="h-4 w-4" strokeWidth={2} /> : <ChevronLeft className="h-4 w-4" strokeWidth={2} />}
            </button>
          </div>
        </div>
      </aside>

      <button
        type="button"
        onClick={() => navigate(CHAT_ROUTE)}
        aria-label="Ask the farming assistant"
        className="press fixed bottom-6 right-6 z-40 hidden h-14 w-14 place-items-center rounded-full bg-gold text-forest shadow-lg animate-pulse-soft md:grid"
      >
        <MessageCircle className="h-6 w-6" strokeWidth={2} />
      </button>

      <nav className="fixed inset-x-0 bottom-0 z-40 md:hidden">
        <div className="mx-auto max-w-lg px-3 pb-safe">
          <div className="surface-glass relative flex items-end justify-around rounded-lg px-1.5 pb-1.5 pt-1 shadow-lg">
            {phoneNav.slice(0, 2).map((item) => (
              <PhoneLink key={item.to} item={item} active={pathname === item.to} />
            ))}
            <div className="relative -top-4">
              <button
                type="button"
                onClick={() => navigate(CHAT_ROUTE)}
                aria-label="Ask the farming assistant"
                className="press grid h-14 w-14 place-items-center rounded-full bg-gold text-forest shadow-[0_10px_24px_rgba(244,185,66,0.45)] ring-4 ring-background"
              >
                <MessageCircle className="h-6 w-6" strokeWidth={2} />
              </button>
            </div>
            {phoneNav.slice(2).map((item) => (
              <PhoneLink key={item.to} item={item} active={pathname === item.to} />
            ))}
          </div>
        </div>
      </nav>
    </>
  );
}

export function AppShell({
  children,
  hideNav,
  className,
}: {
  children: React.ReactNode;
  hideNav?: boolean;
  className?: string;
}) {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { t } = useLanguage();
  const [collapsed, setCollapsed] = React.useState(
    () => localStorage.getItem(RAIL_KEY) === '1',
  );
  const [name, setName] = React.useState<string>('');

  React.useEffect(() => {
    const raw = localStorage.getItem('farmintel_profile');
    if (raw) {
      try {
        setName(JSON.parse(raw)?.name || '');
      } catch {
        /* cache is best-effort only */
      }
    }
  }, []);

  const toggleRail = () => {
    setCollapsed((c) => {
      localStorage.setItem(RAIL_KEY, c ? '0' : '1');
      return !c;
    });
  };

  const main = NAV_ITEMS.filter((i) => i.primary);
  const phoneNav = [main[0], main[1], null, main[3], main[2]].filter(Boolean) as typeof NAV_ITEMS;

  if (hideNav) {
    return (
      <div className={cn('mx-auto min-h-screen w-full max-w-content px-4 sm:px-6', className)}>
        {children}
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      {/* ---------------------------------------------------- desktop rail */}
      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-40 hidden flex-col border-r border-border bg-surface/90 backdrop-blur-xl transition-[width] duration-300 ease-out md:flex',
          collapsed ? 'w-[76px]' : 'w-60',
        )}
      >
        <div className={cn('flex items-center gap-2.5 px-4 pb-4 pt-5', collapsed && 'justify-center px-2')}>
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-sm bg-hero text-white shadow-glow">
            <Leaf className="h-5 w-5" strokeWidth={2} />
          </span>
          {!collapsed && (
            <span className="min-w-0">
              <span className="block truncate font-display text-[15px] font-800 leading-tight">
                AgroSmart
              </span>
              <span className="block text-[10px] font-600 uppercase tracking-[0.12em] text-ink-muted">
                Kisan AI
              </span>
            </span>
          )}
        </div>

        <nav className="flex-1 space-y-1 overflow-y-auto px-2">
          {!collapsed && (
            <p className="px-3 pb-1 pt-2 text-[10px] font-700 uppercase tracking-[0.12em] text-ink-muted">
              {t('nav.main')}
            </p>
          )}
          {NAV_ITEMS.filter((i) => i.group === 'main').map((item) => (
            <RailLink key={item.to} item={item} active={pathname === item.to} collapsed={collapsed} />
          ))}
          {!collapsed && (
            <p className="px-3 pb-1 pt-3 text-[10px] font-700 uppercase tracking-[0.12em] text-ink-muted">
              {t('nav.tools')}
            </p>
          )}
          {NAV_ITEMS.filter((i) => i.group === 'tools').map((item) => (
            <RailLink key={item.to} item={item} active={pathname === item.to} collapsed={collapsed} />
          ))}
          <div className="pt-2">
            <RailLink
              item={{ to: CHAT_ROUTE, label: 'Chat', icon: MessageCircle, group: 'main' }}
              active={pathname === CHAT_ROUTE}
              collapsed={collapsed}
            />
          </div>
        </nav>

        <div className="border-t border-border p-2">
          <button
            type="button"
            onClick={() => navigate('/profile')}
            className={cn(
              'press flex w-full items-center gap-2.5 rounded-sm p-2 text-left hover:bg-surface-2',
              collapsed && 'justify-center',
            )}
          >
            <Avatar name={name} size={32} />
            {!collapsed && (
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[13px] font-700">{name || 'Your profile'}</span>
                <span className="block truncate text-[10.5px] text-ink-muted">Farm settings</span>
              </span>
            )}
            {!collapsed && <Settings2 className="h-4 w-4 text-ink-muted" strokeWidth={1.75} />}
          </button>
          <div className={cn('mt-2 flex items-center gap-2', collapsed ? 'justify-center' : 'justify-between px-1')}>
            <ThemeToggle />
            <button
              type="button"
              onClick={toggleRail}
              aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
              className="press grid h-8 w-8 place-items-center rounded-full border border-border text-ink-muted hover:bg-surface-2"
            >
              {collapsed ? (
                <ChevronRight className="h-4 w-4" strokeWidth={2} />
              ) : (
                <ChevronLeft className="h-4 w-4" strokeWidth={2} />
              )}
            </button>
          </div>
        </div>
      </aside>

      {/* ------------------------------------------------------- content */}
      <div className={cn('transition-[padding] duration-300', collapsed ? 'md:pl-[76px]' : 'md:pl-60')}>
        <div className="mx-auto min-h-screen w-full max-w-content px-4 pb-28 pt-3 sm:px-6 md:pb-10">
          {children}
        </div>
      </div>

      {/* --------------------------------------------- floating chat (md+) */}
      <button
        type="button"
        onClick={() => navigate(CHAT_ROUTE)}
        aria-label="Ask the farming assistant"
        className="press fixed bottom-6 right-6 z-40 hidden h-14 w-14 place-items-center rounded-full bg-gold text-forest shadow-lg animate-pulse-soft md:grid"
      >
        <MessageCircle className="h-6 w-6" strokeWidth={2} />
      </button>

      {/* ------------------------------------------------- phone bottom bar */}
      <nav className="fixed inset-x-0 bottom-0 z-40 md:hidden">
        <div className="mx-auto max-w-lg px-3 pb-safe">
          <div className="surface-glass relative flex items-end justify-around rounded-lg px-1.5 pb-1.5 pt-1 shadow-lg">
            {phoneNav.slice(0, 2).map((item) => (
              <PhoneLink key={item.to} item={item} active={pathname === item.to} />
            ))}

            <div className="relative -top-4">
              <button
                type="button"
                onClick={() => navigate(CHAT_ROUTE)}
                aria-label="Ask the farming assistant"
                className="press grid h-14 w-14 place-items-center rounded-full bg-gold text-forest shadow-[0_10px_24px_rgba(244,185,66,0.45)] ring-4 ring-background"
              >
                <MessageCircle className="h-6 w-6" strokeWidth={2} />
              </button>
            </div>

            {phoneNav.slice(2).map((item) => (
              <PhoneLink key={item.to} item={item} active={pathname === item.to} />
            ))}
          </div>
        </div>
      </nav>
    </div>
  );
}

function RailLink({
  item,
  active,
  collapsed,
}: {
  item: { to: string; label: string; icon: React.ComponentType<{ className?: string; strokeWidth?: number }> };
  active: boolean;
  collapsed: boolean;
}) {
  const Icon = item.icon;
  return (
    <Link
      to={item.to}
      title={collapsed ? item.label : undefined}
      className={cn(
        'flex items-center gap-3 rounded-sm px-3 py-2.5 text-[13.5px] font-600 transition-colors',
        active
          ? 'bg-primary/12 text-primary'
          : 'text-ink-muted hover:bg-surface-2 hover:text-ink',
        collapsed && 'justify-center px-0',
      )}
    >
      <Icon className={cn('h-[18px] w-[18px] shrink-0', active && 'text-primary')} strokeWidth={1.9} />
      {!collapsed && <span className="truncate">{item.label}</span>}
      {active && !collapsed && <span className="ml-auto h-1.5 w-1.5 rounded-full bg-primary" />}
    </Link>
  );
}

function PhoneLink({
  item,
  active,
}: {
  item: { to: string; label: string; icon: React.ComponentType<{ className?: string; strokeWidth?: number }> };
  active: boolean;
}) {
  const Icon = item.icon;
  return (
    <Link
      to={item.to}
      aria-current={active ? 'page' : undefined}
      className="press flex min-w-[56px] flex-1 flex-col items-center gap-0.5 rounded-sm px-1 py-1.5"
    >
      <span
        className={cn(
          'grid h-8 w-12 place-items-center rounded-full transition-colors',
          active ? 'bg-primary/14' : '',
        )}
      >
        <Icon
          className={cn('h-[20px] w-[20px]', active ? 'text-primary' : 'text-ink-muted')}
          strokeWidth={active ? 2.2 : 1.8}
        />
      </span>
      <span
        className={cn(
          'text-[10px] font-600 leading-none',
          active ? 'text-primary' : 'text-ink-muted',
        )}
      >
        {item.label}
      </span>
    </Link>
  );
}
