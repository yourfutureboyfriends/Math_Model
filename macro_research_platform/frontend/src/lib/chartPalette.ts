// Categorical palette for the dark terminal surface — eight hues in a fixed order that pass
// colour-vision-deficiency separation on adjacent pairs (worst ΔE 8.4 dark). Assign in this
// order, never cycle past eight: fold extra categories into "Other" (OTHER_GRAY).
export const CATEGORICAL = ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#008300', '#9085e9', '#e66767'];
export const OTHER_GRAY = '#5b6270';

/** Stable colour per label (first-seen order) so a filter never repaints the survivors. */
export function stableColors(labels: string[]): (label: string) => string {
  const map = new Map<string, string>();
  labels.forEach((l) => { if (!map.has(l) && map.size < CATEGORICAL.length) map.set(l, CATEGORICAL[map.size]); });
  return (label: string) => map.get(label) ?? OTHER_GRAY;
}
