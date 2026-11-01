// Truncated text, readable on hover — app-wide. When the pointer rests on an element whose text is cut off (an
// ellipsis or hidden overflow) and that has no tooltip of its own, its full text becomes the tooltip. One delegated
// listener, measured only on hover, so it costs nothing until used.

let installed = false;

export function installTruncationTitles(): void {
  if (installed || typeof document === 'undefined') return;
  installed = true;
  document.addEventListener('mouseover', (e) => {
    let el = e.target as HTMLElement | null;
    for (let depth = 0; el && depth < 3; depth++, el = el.parentElement) {    // the text's own box or a near parent
      if (el.title || el.getAttribute('aria-label') || el.dataset.truncTitle === 'skip') return;
      if (el.scrollWidth > el.clientWidth + 1 && el.clientWidth > 0) {
        const style = getComputedStyle(el);
        if (style.textOverflow === 'ellipsis' || style.overflow === 'hidden' || style.overflowX === 'hidden') {
          const text = (el.textContent || '').replace(/\s+/g, ' ').trim();
          if (text && text.length < 500) el.title = text;
          return;
        }
      }
    }
  }, { passive: true });
}
