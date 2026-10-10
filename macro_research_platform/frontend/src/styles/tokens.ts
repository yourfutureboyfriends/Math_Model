/**
 * Design tokens (UI1) — the single JS-side reference for the terminal design system.
 *
 * The SOURCE OF TRUTH is the CSS custom properties in `src/index.css` (consumed everywhere
 * via Tailwind utilities + `var(--…)`); this file mirrors them 1:1 for the rare cases that
 * need a token in JS (inline styles, canvas, computed colours). Keep the two in sync.
 *
 * Rules the app already enforces:
 *  - Type scale: only the 8 `fontSize` steps below (10–32px). No ad-hoc font sizes.
 *  - Spacing: multiples of 4px (`spacing` below). No random margins.
 *  - Colour is reserved for signal meaning — green=positive, red=negative, amber=stale/warn,
 *    blue=neutral/info. Never decorative.
 */
export const tokens = {
  fontSize: {
    '2xs': '0.625rem', // 10px — micro labels
    xs: '0.6875rem',   // 11px — ticker labels
    sm: '0.75rem',     // 12px — table body / labels
    base: '0.875rem',  // 14px — UI default / body
    lg: '1rem',        // 16px — section headers
    xl: '1.25rem',     // 20px — panel titles
    '2xl': '1.5rem',   // 24px — KPI values
    '3xl': '2rem',     // 32px — master signal
  },
  spacing: {
    1: '0.25rem', 2: '0.5rem', 3: '0.75rem', 4: '1rem',
    5: '1.25rem', 6: '1.5rem', 8: '2rem', 10: '2.5rem', 12: '3rem',
  },
  radius: {
    none: '0', sm: '2px', md: '4px', full: '9999px', // terminal aesthetic favours sharp corners
  },
  surface: {
    1: '#0d1117', 2: '#131920', 3: '#1a2230', 4: '#1e2736',
  },
  border: {
    subtle: '#151f2e', DEFAULT: '#1e2d3d', strong: '#2a3f55',
  },
  /** Signal colours — reserved strictly for direction/state, never decoration. */
  colors: {
    positive: '#22c55e', // green — up / risk-on
    negative: '#ef4444', // red — down / risk-off
    warning: '#f59e0b',  // amber — stale / warning
    info: '#3b82f6',     // blue — neutral / info
    positiveDim: 'rgba(34, 197, 94, 0.12)',
    negativeDim: 'rgba(239, 68, 68, 0.12)',
    warningDim: 'rgba(245, 158, 11, 0.12)',
  },
} as const;

/** Convenience: read a signal colour by direction. */
export function directionColor(dir: 'up' | 'down' | 'neutral'): string {
  return dir === 'up' ? tokens.colors.positive : dir === 'down' ? tokens.colors.negative : tokens.border.strong;
}

export type Tokens = typeof tokens;
