# Page overlap audit — 3 November 2026

Scope: visual overlap, ambiguous navigation, repeated functionality, and page registration across Macro, Trading, Quant, Markets and PE.

## Fixed

- Five market shortcut collisions: CHART (price versus formula chart), ALPHA (signal board versus stock signal lab), CREDIT (company credit profile versus aggregate spreads), TOP (world overview versus news), GRID (Launchpad versus data grid). Removed conflicting aliases while preserving the existing destination of each shortcut. Canonical codes now resolve before aliases, independent of registry order, and lookup does not inherit object properties.
- Page outlines previously included CSS-hidden tabs and sections inside closed details. They now follow visibility and respond to class, style and open changes as well as hidden attributes.
- Workspace inventory generation previously read and overwrote a hardcoded October snapshot. It now accepts a date and consumes the corresponding current Markets inventory. Workspace rendering tests now use the November inventory.
- Regression checks cover unique market codes/aliases, unique dashboard destinations, exclusive workspace ownership, and hidden-section outline updates.

## Coverage and evidence

Current source inventory: 122 Markets functions, 47 Macro panels, 28 Trading panels, 11 Quant panels, five PE tools. No unmapped registry entries. Source mapping is not a pixel layout test or a certification of data quality.

247 focused market rendering/navigation/outline tests passed. Another 91 workspace rendering tests passed, along with one dashboard registry test (339 total before the new anchor regression test). Rendering audits exercise pending/unavailable data; populated charts and all responsive widths still need live inspection. Workspace tests emit existing React act warnings.

## Functional overlap reviewed

DCF and VAL are separate tools: a detailed standalone model and a multi-method valuation workspace. EDGE and ALPHA serve cross-asset unusual readings and stock-factor research respectively. Company credit profile and aggregate credit spreads are also different. Retained these tools and removed ambiguous shortcuts instead of discarding their capabilities. This does not establish that all nested research tabs have unique functionality.

## Authenticated browser follow-up

After the user signed in, navigated all 122 Markets destinations at 1864 × 984. No visible duplicate IDs or uncontained heading/control overflow detected in those observed states; no JavaScript console errors captured during that sweep. Used AAPL for company functions. This is a boundary/anchor sweep, not proof that every chart was populated: several pages were pending or unavailable, and a few intermediate observations did not yet contain their page heading.

At 915 × 1024, additionally checked VAL, DCF, FLOW, MAP, SHIP, FLY, DATA and LP; no detected boundary or anchor issue. Inspected Research Desk and Macro at 390 × 844. Outline rows and tables intentionally scroll horizontally; they are not duplicate pages.

The populated Macro workspace exposed a duplicate `master-signal` ID on the dashboard owner and its child component. Removed the child ID; browser recheck confirmed one anchor. Added a rendering regression for that composition. Collapsed dashboard sidebar buttons also lacked accessible names and tooltips; added both, plus a label for the expand/collapse control.

The PE inventory had a second coverage gap: a newly available Precedents tool was missing from a hardcoded four-tool list. Inventory generation now derives PE tool entries and count from the actual page mounts. Current registry also contains 11 Quant panels. Workspace component tests additionally check for repeated DOM anchors within each mounted component.

Populated Macro and Trading workspace DOM checks found no remaining visible duplicate IDs or uncontained heading/control overflow in their observed states. The subsequent Quant/PE interaction sequence timed out and the in-app browser transport disconnected. Recovery and a new preview attempt failed. Therefore live checks of every nested tab, every loaded-data state, and every Quant/PE tool remain incomplete. The temporary viewport override was reset before this disconnect. No authentication change, fund-record write, or financial action was performed.

## Follow-up validation

The updated workspace rendering/anchor suite passes all 91 cases. The navigation registry, market shortcuts, page-outline visibility and signal-owner regression checks also pass (97 focused cases in the follow-up, with 243 Markets rendering cases passed in the earlier run). Production Vite build passes; it retains the existing warning for large Dashboard and Markets bundles. That warning is a performance follow-up, not evidence of content overlap.

Final TypeScript check (`tsc --noEmit`) passed.
