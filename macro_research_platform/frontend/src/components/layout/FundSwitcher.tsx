/** Fund switcher (top bar): which fund's book, settings and records the app shows. Hidden with only one fund. */
import { useEffect, useState } from 'react';
import { Briefcase } from 'lucide-react';
import { currentFund, switchFund } from '@/lib/fund';
import { useFundLogo } from '@/lib/fundLogo';

type Fund = { id: string; name: string; base_currency?: string; benchmark?: string };

export function FundSwitcher() {
  const [funds, setFunds] = useState<Fund[] | null>(null);
  const cur = currentFund();
  const mark = useFundLogo('mark', cur);
  useEffect(() => {
    fetch('/api/v1/funds').then((r) => (r.ok ? r.json() : null)).then((j) => {
      const list: Fund[] = j?.funds ?? [];
      setFunds(list);
      if (list.length && !list.some((f) => f.id === cur)) switchFund('main');   // removed or no longer a member
    }).catch(() => setFunds(null));
  }, [cur]);
  const f = funds?.find((x) => x.id === cur);
  if (!funds || funds.length < 2) {
    // one fund: no switcher, but still show whose terminal this is
    return mark ? <img src={mark} alt={f?.name ?? 'Fund'} title={f?.name} className="h-4 w-auto max-w-[36px] object-contain shrink-0" /> : null;
  }
  return (
    <label className="flex items-center gap-1 px-1.5 border border-bloomberg-border bg-bloomberg-muted shrink-0" style={{ height: 22 }}
           title={f ? `${f.name} · base ${f.base_currency ?? '—'} · benchmark ${f.benchmark ?? '—'}` : 'Fund'}>
      {mark ? <img src={mark} alt="" className="h-4 w-auto max-w-[36px] object-contain" /> : <Briefcase className="w-3 h-3 text-bloomberg" />}
      <select aria-label="Fund" value={cur} onChange={(e) => switchFund(e.target.value)}
              className="bg-transparent font-mono text-bloomberg outline-none cursor-pointer" style={{ fontSize: 10 }}>
        {funds.map((x) => <option key={x.id} value={x.id}>{x.name}{x.base_currency ? ` · ${x.base_currency}` : ''}</option>)}
      </select>
    </label>
  );
}
