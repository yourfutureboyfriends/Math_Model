/** Controls for the ML workbench on Radix primitives: slider, segmented toggle, tooltip; plus panel and stat tile. */
import * as Slider from '@radix-ui/react-slider';
import * as ToggleGroup from '@radix-ui/react-toggle-group';
import * as Tip from '@radix-ui/react-tooltip';

export function RangeSlider({ value, min, max, step, onChange, label }: { value: number; min: number; max: number; step?: number; onChange: (v: number) => void; label: string }) {
  return (
    <Slider.Root className="ml-slider" value={[value]} min={min} max={max} step={step ?? ((max - min) / 200 || 0.01)} onValueChange={(v) => onChange(v[0])} aria-label={label}>
      <Slider.Track className="ml-slider-track"><Slider.Range className="ml-slider-range" /></Slider.Track>
      <Slider.Thumb className="ml-slider-thumb" aria-label={label} />
    </Slider.Root>
  );
}

export function Segmented<T extends string>({ value, onChange, options, label }: { value: T; onChange: (v: T) => void; options: { value: T; label: string }[]; label: string }) {
  return (
    <ToggleGroup.Root type="single" value={value} onValueChange={(v) => v && onChange(v as T)} className="ml-seg" aria-label={label}>
      {options.map((o) => <ToggleGroup.Item key={o.value} value={o.value} className="ml-seg-item">{o.label}</ToggleGroup.Item>)}
    </ToggleGroup.Root>
  );
}

export function Hint({ children, text }: { children: React.ReactNode; text: React.ReactNode }) {
  return (
    <Tip.Provider delayDuration={200}>
      <Tip.Root>
        <Tip.Trigger asChild>{children}</Tip.Trigger>
        <Tip.Portal><Tip.Content className="ml-hint" sideOffset={6}>{text}<Tip.Arrow className="ml-hint-arrow" /></Tip.Content></Tip.Portal>
      </Tip.Root>
    </Tip.Provider>
  );
}

/** A dashboard panel: header with title, subtitle and actions; body; optional footer. */
export function Panel({ title, sub, actions, children, footer, className = '', bodyClass = '' }: {
  title: React.ReactNode; sub?: React.ReactNode; actions?: React.ReactNode; children: React.ReactNode; footer?: React.ReactNode; className?: string; bodyClass?: string;
}) {
  return (
    <section className={`ml-panel ${className}`}>
      <header className="ml-panel-head"><div className="min-w-0"><h3>{title}</h3>{sub && <p>{sub}</p>}</div>{actions && <div className="ml-panel-actions">{actions}</div>}</header>
      <div className={`ml-panel-body ${bodyClass}`}>{children}</div>
      {footer && <footer className="ml-panel-foot">{footer}</footer>}
    </section>
  );
}

export function Stat({ label, value, delta, tone, hint }: { label: string; value: React.ReactNode; delta?: React.ReactNode; tone?: 'good' | 'warn' | 'bad'; hint?: string }) {
  return (
    <div className="ml-stat" title={hint}>
      <div className="ml-stat-label">{label}</div>
      <div className={`ml-stat-value ${tone ? `ml-tone-${tone}` : ''}`}>{value}</div>
      {delta && <div className="ml-stat-delta">{delta}</div>}
    </div>
  );
}
