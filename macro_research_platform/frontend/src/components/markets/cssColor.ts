// Canvas can't read CSS variables: resolve `rgb(var(--c-…) / a)` through the browser (a hidden
// probe element) and cache it. The cache is dropped when the theme, skin or up/down colours change.
import { useEffect, useRef } from 'react';

export function useCssColor() {
  const probe = useRef<HTMLSpanElement | null>(null);
  const cache = useRef(new Map<string, string>());
  useEffect(() => {
    const mo = new MutationObserver(() => cache.current.clear());
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme', 'data-skin', 'data-updown', 'class'] });
    return () => mo.disconnect();
  }, []);
  return {
    probe,
    resolve: (c: string) => {
      if (!c.includes('var(')) return c;
      const hit = cache.current.get(c);
      if (hit) return hit;
      const el = probe.current;
      if (!el) return '#888';
      el.style.color = c;
      const v = getComputedStyle(el).color;
      cache.current.set(c, v);
      return v;
    },
  };
}
