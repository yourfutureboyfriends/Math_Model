/** Read-only identity in the terminal. Fund selection is available only before sign-in. */
import { Briefcase } from 'lucide-react';
import { useCurrentFund } from '@/lib/fundBrand';
import { BrandShape } from './FundIdentity';
export function FundSwitcher() {
  const fund=useCurrentFund();
  if(!fund)return null;
  return <span className="flex items-center gap-1 px-1.5 border border-bloomberg-border bg-bloomberg-muted shrink-0" style={{height:22}}
    title={`${fund.name} · sign out to select another fund`} aria-label={`Current fund: ${fund.name}`}>
    {fund.logo_masks?<BrandShape variant="mark_mask" height={12} className="text-bloomberg"/>:<Briefcase className="w-3 h-3 text-bloomberg"/>}
    <span className="font-mono text-bloomberg max-w-[10rem] xl:max-w-[14rem] truncate" style={{fontSize:10}}>{fund.name}{fund.base_currency?` · ${fund.base_currency}`:''}</span>
  </span>;
}
