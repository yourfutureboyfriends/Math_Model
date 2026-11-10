// Text on the accent colour, readable whatever the accent is. The accent changes with the theme and with the fund's
// brand (Moriah's light gold, BIFS's navy, the default orange / teal), and white text on a light gold is unreadable
// (1.9:1). This keeps --c-on-accent ("R G B") set to whichever of near-black or white contrasts more with the live
// accent, recomputed whenever the theme, skin or brand changes. index.css applies it to accent-filled controls.

const DARK = [10, 14, 20];
const WHITE = [255, 255, 255];

function luminance([r, g, b]: number[]): number {
  const ch = (v: number) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
  return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b);
}

export function onAccent(accent: number[]): number[] {
  const L = luminance(accent);
  const vsWhite = 1.05 / (L + 0.05), vsDark = (L + 0.05) / (luminance(DARK) + 0.05);
  return vsDark >= vsWhite ? DARK : WHITE;
}

let installed = false;

export function installAccentContrast(): void {
  if (installed || typeof document === 'undefined') return;
  installed = true;
  const root = document.documentElement;
  // the accent, and the green / red fills of buy-sell buttons and status badges (white on bright green is 2.3:1)
  const pairs: [string, string][] = [['--c-bloomberg', '--c-on-accent'], ['--c-green', '--c-on-green'], ['--c-red', '--c-on-red']];
  const update = () => {
    const cs = getComputedStyle(root);
    for (const [src, dst] of pairs) {
      const parts = cs.getPropertyValue(src).trim().split(/[\s,]+/).map(Number);
      if (parts.length < 3 || parts.some((x) => !Number.isFinite(x))) continue;
      const next = onAccent(parts).join(' ');
      if (root.style.getPropertyValue(dst) !== next) root.style.setProperty(dst, next);   // only on change: no loop
    }
  };
  update();
  new MutationObserver(update).observe(root, { attributes: true, attributeFilter: ['data-theme', 'data-brand', 'data-skin', 'style', 'class'] });
}
