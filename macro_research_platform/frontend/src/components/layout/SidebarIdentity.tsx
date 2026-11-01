import { FundIdentity } from './FundIdentity';
import { Logo } from './Logo';

/** Same selected-fund identity in every workspace, including collapsed navigation. */
export function SidebarIdentity({ collapsed=false,currentRegime }: { collapsed?:boolean;currentRegime?:string }) {
 return <div className="h-14 shrink-0 flex items-center px-3 border-b border-border-subtle" data-sidebar-identity>
  <FundIdentity collapsed={collapsed} fallback={<><Logo currentRegime={currentRegime}/>{!collapsed&&<><span className="ml-2 font-mono text-sm text-text-secondary">MACRO TERMINAL</span><span className="ml-1.5 text-2xs text-text-tertiary">v8.0</span></>}</>}/>
 </div>;
}
