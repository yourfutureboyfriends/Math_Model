/**
 * The fund's identity inside the terminal: its logo shapes drawn as masks in the theme's colours (gold gradient for a
 * gold brand, the accent otherwise), the wordmark and tagline in the sidebar header, and a report letterhead on the
 * brand's own band colour — the same treatment as the fund's printed documents.
 */
import { cn } from '@/lib/utils';
import { useFundLogo, useFundShape, type LogoVariant } from '@/lib/fundLogo';
import { useCurrentFund } from '@/lib/fundBrand';

export function BrandShape({ variant, height, className, title }: { variant: LogoVariant; height: number; className?: string; title?: string }) {
  const s = useFundShape(variant);
  if (!s) return null;
  const mask = `url(${s.url})`;
  return <span role="img" aria-label={title} title={title} className={cn('brand-mask', className)}
               style={{ height, width: Math.round(height * s.ratio), WebkitMaskImage: mask, maskImage: mask }} />;
}

/** Sidebar header: mark + wordmark + tagline, the platform name beneath. Falls back to the platform header. */
export function FundIdentity({ collapsed, fallback }: { collapsed: boolean; fallback: React.ReactNode }) {
  const f = useCurrentFund();
  const b = f?.brand;
  if (!f?.logo_masks || !b) return <>{fallback}</>;
  const gold = b.mark_fill === 'gradient';                    // metallic brands (gold) vs a single ink colour
  if (collapsed) return <BrandShape variant="mark_mask" height={20} className={gold ? 'brand-gold' : 'text-bloomberg'} title={f.name} />;
  return (
    <div className="flex items-center gap-2 min-w-0" title={`${f.name} · ${f.base_currency ?? ''}`}>
      <BrandShape variant="mark_mask" height={30} className={gold ? 'brand-gold' : 'text-text-primary'} title={f.name} />
      <div className="min-w-0 leading-none">
        <BrandShape variant="word_mask" height={(b.word_height ?? 11) + 2} className={gold ? 'brand-gold' : 'text-text-primary'} title={f.name} />
        <div className="mt-1 h-px w-full" style={{ background: `rgb(${b.secondary ?? b.accent_dark} / 0.7)` }} />
        <div className={cn("mt-1 uppercase text-text-secondary", (b.tagline ?? "").length > 24 ? "text-[7.5px] leading-[9px] tracking-[0.12em] line-clamp-2" : "text-[8.5px] tracking-[0.2em] truncate")}>{b.tagline ?? 'Macro Terminal'}</div>
      </div>
    </div>
  );
}

/** Report letterhead on the brand's band colour with the full-colour logo (as on the fund's own documents). */
export function Letterhead({ title, sub }: { title: string; sub?: string }) {
  const f = useCurrentFund();
  const logo = useFundLogo('full');
  const band = f?.brand?.band;
  if (!band || !logo) {
    return <div className="border-b border-border pb-2"><div className="text-sm text-text-primary font-medium">{title}</div>{sub && <div className="text-2xs text-text-tertiary">{sub}</div>}</div>;
  }
  return (
    <div className="flex items-center gap-4 px-4 py-3 print:break-inside-avoid" style={{ background: `rgb(${band})`, WebkitPrintColorAdjust: 'exact', printColorAdjust: 'exact' }}>
      <img src={logo} alt={f?.name} className="h-12 w-auto max-w-[170px] object-contain" />
      <div className="ml-auto text-right">
        <div className="text-sm font-medium" style={{ color: 'rgb(240 236 228)' }}>{title}</div>
        {sub && <div className="text-2xs" style={{ color: `rgb(${f?.brand?.secondary ?? '200 200 200'})` }}>{sub}</div>}
      </div>
    </div>
  );
}
