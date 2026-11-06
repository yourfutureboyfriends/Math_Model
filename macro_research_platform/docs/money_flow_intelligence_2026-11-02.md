# Money-flow intelligence — 2 November 2026

The flow page distinguishes estimated ETF primary issuance, dimensionless market pressure, reported cross-border positions/flows and SEC disclosures. No private feed, broker order ledger or live insider transaction feed is implied.

## Map and interpretation

The map uses the shared detailed atlas, cached geometry, entry-based hover updates and animation disabled initially. Zoom/reset controls and explicit source periods help exploration. Signed US inbound/outbound arrows are corrected. Routes are schematic; custody/reporting countries are not necessarily beneficial-owner destinations.

ETF estimates sum interval changes in reported shares outstanding times interval-ending NAV or price proxy. They are not observed cash transfers: creations can be in-kind, share effective dates are unverified and revisions/splits can distort estimates. Missing history, stale snapshots and unusually large share changes withhold estimates. The divergence watchlist compares issuance relative to starting AUM against price changes over exactly matched endpoints; it is a research screen, not a trading recommendation.

## Disclosures

An on-demand ticker lookup samples up to 20 recent SEC Form 4 filings. It displays filing dates, transaction dates, reporting roles, values, footnotes and source links. P/S include market or private transactions. Compensation codes are excluded from purchase/sale summary metrics. Duplicate rows and amendment-affected owner/date/security groups are excluded rather than treated as a reconciled ledger. Future filings cannot alter historical summaries. Unknown 10b5-1 status is distinct from a negative checkbox; a filing-level checkbox does not verify each transaction independently. Joint filings currently display the first reporting owner.

Institutional 13F comparisons use distinct reporting quarters, report dates and filing dates. A missing baseline is unavailable, not a new position. Values use filing-date-dependent SEC units rather than portfolio-size heuristics. Holdings changes are not inferred cash purchases. Amendments are not consolidated into a complete institutional ledger.

SEC coverage is US-focused. Form 4 is generally due within two business days; 13F can arrive 45 days after quarter-end and does not disclose complete short exposures. Overseas director dealings, licensed primary ETF flows and broader ownership histories remain separate data-integration work.

## Validation

- Backend focused regression suites: 65 passed.
- Frontend full suite: 542 passed across 58 files.
- Live Microsoft disclosure check: 20 requested filings parsed in the initial live verification.
- Component layout visually reviewed with clearly illustrative data; authenticated application navigation was limited by the login screen.

## Primary references

- SEC Form 4 instructions: https://www.sec.gov/about/forms/form4data.pdf
- SEC insider arrangements guidance: https://www.sec.gov/resources-small-businesses/small-business-compliance-guides/insider-trading-arrangements-and-related-disclosures
- SEC Form 13F FAQ: https://www.sec.gov/rules-regulations/staff-guidance/frequently-asked-questions-about-form-13f
- SEC EDGAR filer manual (2023 dollar convention): https://www.sec.gov/files/edgarfm-vol2-v65-draft.pdf
- ICI ETF primary versus secondary trading: https://www.ici.org/viewpoints/view_14_etf_paper_01
