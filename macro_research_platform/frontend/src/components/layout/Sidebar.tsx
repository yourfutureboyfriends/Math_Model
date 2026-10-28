// UPGRADE-9: Terminal Sidebar — Hedge Fund Workflow Organization
// Optimized navigation for PM daily workflow: Morning → Signals → Trades → Risk → Strategy

import { useState } from 'react';
import { ChevronLeft, ChevronRight, KeyRound, LogOut, Star } from 'lucide-react';
import { Logo } from './Logo';
import { FundIdentity } from './FundIdentity';
import { cn } from '@/lib/utils';
import { useAuth } from '@/context/AuthContext';
import { AccountDialog } from '@/components/account/AccountPanels';
import { useDesk } from '@/hooks/useDesk';
import { panelLabel } from '@/lib/panels';
import { setFocusMode, setWorkspace, useFocusMode, useWorkspace } from '@/lib/focusMode';
import { usePinnedSections } from '@/hooks/usePinnedSections';
import { navigation, navigationFor, type NavItem } from '@/lib/navigation';
import { isDashboardMode, useHubMode } from '@/lib/hubMode';

interface SidebarProps {
  activeSection?: string;
  onNavigate?: (section: string) => void;
  currentRegime?: string;
  collapsed?: boolean;
  onCollapse?: () => void;
}

export function Sidebar({ activeSection = 'master-signal', onNavigate, currentRegime, collapsed: externalCollapsed, onCollapse }: SidebarProps) {
  const [internalCollapsed, setInternalCollapsed] = useState(false);
  const { user, logout } = useAuth();
  const [accountOpen, setAccountOpen] = useState(false);

  // Use external state if provided, otherwise internal
  const collapsed = externalCollapsed ?? internalCollapsed;
  const handleCollapse = () => {
    if (onCollapse) {
      onCollapse();
    } else {
      setInternalCollapsed(!internalCollapsed);
    }
  };

  // FIXED: Navigation always renders — unconditional, no permission filtering
  // All users see all navigation items; permission-based feature hiding is deprecated
  const hub = useHubMode();
  const filteredNavigation = navigationFor(isDashboardMode(hub) ? hub : 'macro');   // this area's groups only

  // Per-user pinned panels for one-click access.
  const pinKey = user?.username || user?.display_name || 'default';
  const { pinned, toggle: togglePin, isPinned } = usePinnedSections(pinKey);
  const itemById: Record<string, NavItem> = Object.fromEntries(
    navigation.flatMap((s) => s.items).map((i) => [i.id, i])
  );
  const pinnedItems = pinned.map((id) => itemById[id]).filter(Boolean) as NavItem[];
  // Role desk: "My Desk" plus the panels this role works from (server-defined).
  const desk = useDesk(user?.username);
  const deskItems: NavItem[] = [
    { id: 'my-desk', label: 'My Desk', icon: '▣', permission: 'master_signal', highlight: true },
    ...((desk?.focus.panels ?? []).map((id) => itemById[id]).filter(Boolean) as NavItem[]),
  ];
  const deskQueue = desk?.queue.filter((i) => i.priority === 'high').length ?? 0;
  const focus = useFocusMode();
  const workspace = useWorkspace();

  const renderNavItem = (item: NavItem) => {
    const isActive = activeSection === item.id;
    const pinnedNow = isPinned(item.id);
    return (
      <div key={item.id} className="group relative flex items-center">
        <button
          onClick={() => onNavigate?.(item.id)}
          className={cn(
            'flex-1 h-7 flex items-center transition-colors duration-150 min-w-0 rounded-md',
            collapsed ? 'justify-center px-0 mx-1' : 'px-3 mx-2',
            isActive
              ? 'bg-bloomberg/10 text-text-primary'
              : item.highlight
                ? 'text-text-primary/90 hover:bg-text-primary/5'
                : 'text-text-secondary hover:bg-text-primary/5 hover:text-text-primary'
          )}
        >
          <span aria-hidden className={cn('nav-dot', item.highlight && 'is-key', isActive && 'is-active')} />
          {!collapsed && (
            <span className={cn('ml-2.5 text-xs truncate', (item.highlight || isActive) && 'font-medium')}>
              {panelLabel(item.id, item.label)}
            </span>
          )}
        </button>
        {!collapsed && (
          <button
            onClick={(e) => { e.stopPropagation(); togglePin(item.id); }}
            title={pinnedNow ? 'Unpin panel' : 'Pin panel'}
            className={cn(
              'absolute right-1.5 p-1 transition-opacity',
              pinnedNow
                ? 'opacity-100 text-amber'
                : 'opacity-0 group-hover:opacity-100 text-text-tertiary hover:text-amber'
            )}
          >
            <Star className="w-3 h-3" fill={pinnedNow ? 'currentColor' : 'none'} />
          </button>
        )}
      </div>
    );
  };

  const handleLogout = async () => {
    await logout();
  };

  return (
    <div
      className={cn(
        'h-full flex flex-col bg-surface-1',
        collapsed ? 'w-[48px] min-w-[48px]' : 'w-[224px] min-w-[224px]'
      )}
      style={{ display: 'flex', flexDirection: 'column' }}
    >
      {/* Platform ID */}
      <div className="h-14 flex items-center px-3 border-b border-border-subtle">
        <FundIdentity collapsed={collapsed} fallback={<>
          <Logo currentRegime={currentRegime} />
          {!collapsed && (
            <>
              <span className="ml-2 font-mono text-sm text-text-secondary">MACRO TERMINAL</span>
              <span className="ml-1.5 text-2xs text-text-tertiary">v8.0</span>
            </>
          )}
        </>} />
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto py-2">
        {/* Your desk — role-tailored entry points */}
        <div className="mb-1">
          {!collapsed && (
            <div className="px-5 pt-2 pb-1.5 text-2xs uppercase text-text-tertiary font-semibold tracking-[0.08em] flex items-center gap-1">
              My desk
              <button onClick={() => setFocusMode(!focus)}
                title={focus ? 'Showing only your panels — click to show all' : 'Show only the panels for your role'}
                className={`ml-2 px-1.5 rounded-full border text-[9.5px] normal-case tracking-normal font-medium transition-colors ${focus ? 'border-bloomberg/50 bg-bloomberg/10 text-bloomberg' : 'border-border-subtle text-text-tertiary hover:text-text-primary'}`}>
                {focus ? 'Focus on' : 'Focus'}
              </button>
              {deskQueue > 0 && (
                <span className="ml-auto px-1.5 text-2xs font-mono bg-red/15 text-red rounded-full" title="High-priority items in your queue">
                  {deskQueue}
                </span>
              )}
            </div>
          )}
          <div className="space-y-px">{deskItems.map((i) => renderNavItem({ ...i }))}</div>
          <div className="mx-5 my-2 border-t border-border-subtle/70" />
        </div>

        {/* Pinned panels — user's most-watched, one-click access */}
        {pinnedItems.length > 0 && (
          <div className="mb-1">
            {!collapsed && (
              <div className="px-5 pt-2 pb-1.5 text-2xs uppercase text-text-tertiary font-semibold tracking-[0.08em] flex items-center gap-1">
                <Star className="w-3 h-3 text-amber" fill="currentColor" /> Pinned
              </div>
            )}
            <div className="space-y-px">
              {pinnedItems.map(renderNavItem)}
            </div>
            <div className="mx-5 my-2 border-t border-border-subtle/70" />
          </div>
        )}

        {filteredNavigation.map((section) => (
          <div key={section.title} className="mb-1">
            {!collapsed && (
              <button onClick={() => { setWorkspace(section.title); window.scrollTo({ top: 0 }); }}
                title={`Show only ${section.title.toLowerCase()} panels`}
                className={cn('w-full text-left px-5 pt-3 pb-1.5 text-2xs uppercase font-semibold tracking-[0.08em] transition-colors',
                  workspace === section.title ? 'text-bloomberg' : 'text-text-tertiary hover:text-text-primary')}>
                {section.title}
              </button>
            )}
            <div className="space-y-px">
              {section.items.map(renderNavItem)}
            </div>
          </div>
        ))}
      </nav>

      {/* Role Badge & Logout */}
      {!collapsed && user && (
        <div className="px-3 py-2 border-t border-border-subtle">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-bloomberg" />
              <span className="text-xs text-text-secondary">
                {user.role.toUpperCase()} — {user.display_name}
              </span>
            </div>
            <div className="flex items-center">
            <button
              onClick={() => setAccountOpen(true)}
              className="p-1 text-text-tertiary hover:text-text-primary transition-colors"
              title={user.role === 'admin' ? 'Account & users' : 'Account'}
            >
              <KeyRound className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={handleLogout}
              className="p-1 text-text-tertiary hover:text-text-primary transition-colors"
              title="Logout"
            >
              <LogOut className="w-3.5 h-3.5" />
            </button>
            </div>
          </div>
          {accountOpen && <AccountDialog onClose={() => setAccountOpen(false)} />}
        </div>
      )}

      {/* Collapse button */}
      <button
        onClick={handleCollapse}
        className="h-8 flex items-center justify-center border-t border-border-subtle text-text-tertiary hover:text-text-primary hover:bg-surface-3 transition-colors"
      >
        {collapsed ? (
          <ChevronRight className="w-4 h-4" />
        ) : (
          <div className="flex items-center gap-1">
            <ChevronLeft className="w-4 h-4" />
            <span className="text-2xs">Collapse</span>
          </div>
        )}
      </button>
    </div>
  );
}
