// Live TV for MAP: official live streams of business and news channels (the selected country's own
// channels first, then its region's, then global business TV), and recent clips from established
// outlets about that country's economy. Embedded with YouTube's privacy-enhanced player, muted.
import { useEffect, useMemo, useState } from 'react';
import { cn } from '@/lib/utils';
import { useJSON } from './shared';

type Channel = { channel_id: string; channel: string; focus: string; countries: string[]; region: string; live: boolean; video_id: string | null; title: string | null };
type Clip = { video_id: string; title: string; channel: string; age?: string | null; published?: string | null; live?: boolean };

const embed = (id: string) => `https://www.youtube-nocookie.com/embed/${id}?autoplay=1&mute=1&playsinline=1&rel=0&modestbranding=1`;

export function LiveTV({ iso, name, region }: { iso: string | null; name: string | null; region?: string | null }) {
  const tv = useJSON<{ channels: Channel[] }>('/api/v1/mkt/tv', 900_000);
  const clips = useJSON<{ clips: Clip[] }>(`/api/v1/mkt/tv/clips?limit=18${iso ? `&country=${iso}` : ''}`, 1_800_000);
  // order: the country's own channels, then its region's, then global business TV
  const ordered = useMemo(() => {
    const cs = tv.data?.channels ?? [];
    const rank = (c: Channel) => (iso && c.countries.includes(iso) ? 0 : region && c.region === region ? 1 : c.countries.includes('*') || c.focus === 'business' ? 2 : 3);
    return [...cs].sort((a, b) => rank(a) - rank(b) || Number(b.live) - Number(a.live));
  }, [tv.data, iso, region]);
  const [playing, setPlaying] = useState<{ id: string; label: string } | null>(null);
  // a new country starts on its own first live channel
  useEffect(() => {
    const first = ordered.find((c) => c.live && c.video_id);
    if (first) setPlaying({ id: first.video_id!, label: `${first.channel} — live` });
  }, [iso, tv.data]);           // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="bg-surface-1 border border-border">
      <div className="panel-bar px-2 h-6 flex items-center text-[11px] uppercase tracking-wide">
        <span className="text-bloomberg font-semibold">Live TV{name ? ` · ${name}` : ' · world'}</span>
        <span className="ml-auto normal-case tracking-normal text-[10px] text-text-tertiary">official channel streams · muted until you unmute</span>
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)] gap-2 p-2">
        <div className="space-y-1.5 min-w-0">
          <div className="relative w-full bg-black" style={{ aspectRatio: '16 / 9' }}>
            {playing ? <iframe key={playing.id} src={embed(playing.id)} title={playing.label} className="absolute inset-0 w-full h-full"
              allow="autoplay; encrypted-media; picture-in-picture; fullscreen" allowFullScreen referrerPolicy="strict-origin-when-cross-origin" />
              : <div className="absolute inset-0 grid place-items-center text-xs text-text-tertiary">{tv.loading ? 'Finding live channels…' : 'No channel live right now.'}</div>}
          </div>
          {playing && <div className="text-[11px] text-text-secondary truncate" title={playing.label}>{playing.label}</div>}
          <div className="flex flex-wrap gap-1">
            {ordered.map((c) => (
              <button key={c.channel_id} disabled={!c.live || !c.video_id} onClick={() => c.video_id && setPlaying({ id: c.video_id, label: `${c.channel} — ${c.title ?? 'live'}` })}
                title={c.live ? c.title ?? 'Live' : 'Off air right now'}
                className={cn('px-2 py-0.5 text-[11px] border inline-flex items-center gap-1',
                  playing?.id === c.video_id ? 'border-bloomberg text-bloomberg' : c.live ? 'border-border text-text-secondary hover:text-text-primary' : 'border-border-subtle text-text-tertiary opacity-50')}>
                {c.live && <span className="w-1.5 h-1.5 rounded-full bg-red animate-pulse" />}{c.channel}
                {iso && c.countries.includes(iso) && <span className="text-[9px] text-bloomberg">{iso}</span>}</button>))}
          </div>
        </div>
        <div className="min-w-0">
          <div className="text-[10px] uppercase tracking-wider text-text-tertiary mb-1">{name ? `${name}'s economy — recent clips` : 'Economy — recent clips'}</div>
          <ul className="space-y-1 max-h-[360px] overflow-y-auto pr-1">
            {(clips.data?.clips ?? []).map((v) => (
              <li key={v.video_id}>
                <button onClick={() => setPlaying({ id: v.video_id, label: `${v.channel} — ${v.title}` })}
                  className={cn('w-full flex gap-2 text-left p-1 hover:bg-surface-3', playing?.id === v.video_id && 'bg-surface-3')}>
                  <img src={`https://i.ytimg.com/vi/${v.video_id}/mqdefault.jpg`} alt="" loading="lazy" className="w-24 h-[54px] object-cover shrink-0 bg-surface-3" />
                  <span className="min-w-0">
                    <span className="block text-[11px] text-text-primary leading-snug line-clamp-2">{v.title}</span>
                    <span className="block text-[10px] text-text-tertiary">{v.channel}{v.age ? ` · ${v.age}` : v.published ? ` · ${new Date(v.published).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })}` : ''}</span>
                  </span>
                </button>
              </li>))}
            {clips.data && clips.data.clips.length === 0 && <li className="text-[11px] text-text-tertiary p-1">No recent clips about {name ?? 'this country'} from the outlets followed.</li>}
            {clips.loading && !clips.data && <li className="text-[11px] text-text-tertiary p-1">Finding clips…</li>}
          </ul>
        </div>
      </div>
    </div>
  );
}
