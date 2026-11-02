import { FundIdentity } from './FundIdentity';
import { Logo, Wordmark } from './Logo';

/** Same selected-fund identity in every workspace, including collapsed navigation. */
export function SidebarIdentity({ collapsed=false,currentRegime }: { collapsed?:boolean;currentRegime?:string }) {
 return <div className="h-14 shrink-0 flex items-center px-3 border-b border-border-subtle" data-sidebar-identity>
  <FundIdentity collapsed={collapsed} fallback={<><Logo currentRegime={currentRegime} size={28}/>{!collapsed&&<Wordmark className="ml-2.5" version="v8.0"/>}</>}/>
 </div>;
}
