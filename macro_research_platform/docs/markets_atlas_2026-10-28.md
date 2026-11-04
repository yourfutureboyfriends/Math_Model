> **29 October correction:** the globe arc simplification described below was removed after a polygon-winding defect filled the ocean. Original geometry is now retained, with ocean/area regressions and actual browser verification. See `markets_ui_audit_2026-10-29.md` for the current implementation.

# Markets atlas refresh — 28 October 2026

The Markets MAP view retains the existing country data, policy merge, 22 data layers and market drilldowns. Its new compact layer selector, region presets, optional numeric labels, search with Enter/Escape, country panel and numeric range ranking replace the crowded map controls. A subdued navy canvas, teal/amber diverging scale and blue sequential scale distinguish numeric magnitude from investment judgements. Missing observations have a separate neutral swatch. The legend discloses percentile clipping. Live coverage loads only when opened.

## Rendering changes

- Fixed-size Equal Earth paths are cached per topology object and scaled with the SVG viewBox, rather than regenerated on resize. D3 handles antimeridian clipping. Shared projection helpers used by other screens remain unchanged.
- Memoized country paths are independent of hover and camera state. Pointer drag updates coalesce into one animation frame; hover updates only when the country changes. Plain scrolling does not hijack page scrolling; Ctrl/Command + scroll zooms. Keyboard +/− and Home work when the map is focused.
- The globe uses simplified shared topology arcs: **80,617 → 21,052 vertices (74% fewer)** in the checked-in 50m asset. Shared endpoints and country identities are preserved; small closed arcs retain enough points. Detail is intentionally reduced on the globe; the 2D atlas retains original detail.
- Globe rendering is demand-driven. Idle automatic spin is removed. Country transitions honor reduced motion. Frames pause when hidden/offscreen, drag and hover work coalesce, and canvas pixel ratio is capped at 1.5. Current callbacks and layer colours remain live without rebuilding geometry.
- Geometry requests are shared and failures are retryable. Invalid saved map modes fall back to 2D.

## Verification

Five focused regression tests cover actual atlas geometry, simplification/endpoints, camera bounds, idle frame scheduling/coalescing/cleanup, data-layer rendering, mode recovery and explicit video activation. Full frontend suite: 106 tests passed with local API access. Production build passed; existing large-bundle warnings remain. TypeScript checked separately.

Browser visual QA used the actual AtlasMap2D component with clearly labelled illustrative values in a temporary isolated preview, then removed that preview source. Zoom/reset were exercised with no captured console errors. Screenshot: `/tmp/markets-atlas-preview.jpg`. The authenticated Markets page was not exercised in that session. Vertex reduction and eliminated idle frame requests are measured/tested improvements; no device-specific FPS or memory benchmark is claimed.
