# JavaScript error investigation and recovery features — 28 October 2026

## Reported desktop error

The supplied screenshot shows an uncaught exception in the installed Codex/ChatGPT
macOS application, not in the terminal website:

`TypeError: Error converting argument 0 of setAcceptsMouseMovedEvents ... Expected a number or bigint`

The stack points to the app's Objective-C bridge and native window proximity tracking
under `/Applications/ChatGPT.app/Contents/Resources/`. Matching signatures were found
in today's desktop logs. No installed application files or trusted browser components
were modified. This repository cannot fix that native-app call. Running localhost in
a regular browser avoids the embedded-preview path; an exact desktop bug fix remains
outside this project.

[Official OpenAI troubleshooting](https://learn.chatgpt.com/docs/reference/troubleshooting)
documents feedback through the composer and desktop log locations. Review logs before
sharing them. If the problem persists after active work has finished, restarting the
desktop app is a recovery step, not evidence that the underlying bug was corrected.

## Project improvements

- Added root and per-area rendering boundaries. A failed view can be retried without
  clearing authentication or resetting the whole browser. Diagnostics can be expanded
  or copied locally; nothing is automatically sent to an external service.
- Validate pinned/recent workspace records and display preferences before rendering.
  Valid JSON with the wrong shape used to reach array operations unchecked.
- Added pin removal and scoped recent-history clearing.
- Added a shared Table explorer: choose a currently loaded table, search across
  columns, copy/download filtered CSV, and refresh the snapshot. Preview is limited
  to 250 rows, collection to 5,000 per table, both explicitly labeled. This is not a
  server-side full-dataset export. Headerless tables preserve their first data row.
- CSV quoting handles commas/quotes and protects text that spreadsheet applications
  might interpret as formulas.

## Verification

- Browser console was clear in the Macro/Trading/Quant views checked and while opening
  and using the table explorer. This does not prove every possible panel is error-free.
- Nine targeted tests cover corrupt storage, preferences, view restoration, recoverable
  rendering faults, filtering, headerless tables and CSV encoding.
- TypeScript and production build are checked separately after the final edits.
- A full lint scan still has substantial existing repository violations; it is not
  presented as a passing lint gate or as proof that the project is free of all defects.

## Branded fund selection at login

Fund choice now appears only on the sign-in page. The chosen fund's name, full logo
and tagline update before authentication; the in-program header is a read-only identity
badge. The public login-branding route contains only id, display name, palette and
logo flags/version. It does not return memberships, capital, holdings or private settings.
The new public logo route serves only the full sign-in logo; authenticated logo variants
retain their existing checks. Selecting a fund is not an authorization grant: the login
handler validates membership after credentials/MFA and before issuing a token. The
selected fund is returned and remembered for the signed-in workspace. Fund metadata
request caches are reset across login/logout to avoid stale account/fund identities.

Five fund backend tests and ten focused frontend tests passed, including login fund
selection and membership rejection. Existing authentication regressions and the final
frontend build were run separately.

## Login visual refinement

The login now has a responsive split layout, a native SVG research-workflow graphic
(explicitly illustrative, not market data), and a fund-coloured logo plaque. BIFS's
opaque logo corner is RGB 15/35/62, matching its existing brand band; the plaque uses
each fund's configured band so no bitmap editing or replacement logo is required.
Moriah's transparent gold artwork remains on its own navy brand band.

Added show/hide password, Caps Lock feedback, optional username remembering (never
password storage), retryable branding loading and a compact mobile layout. Shared
modern workspace controls and surfaces were refined without replacing the classic
terminal's dense styling. Fund choices are committed only after successful login;
signed-in tabs pin their own fund context so another tab's selection cannot switch
their next request into a different fund.

The previous branded-login and table-explorer browser checks passed with a clear
website console. The later visual-refinement browser check was blocked by the Codex
browser tooling returning `browser.user is unavailable`; this does not establish a
website fault. Final verification uses rendering tests, type checks and the production
build. A fresh rendered screenshot of the final visual refinement was not obtained.

Final checks for this pass: all 101 frontend tests passed across 17 files; TypeScript
and the production Vite build passed. The build retains large-chunk warnings. Fund
and authentication backend checks passed (five fund tests and twelve authentication
regressions). No full backend-suite or complete visual certification is claimed.
The live frontend and API remain available on ports 5173 and 8000 respectively.

The follow-up colour adjustment removes the separate logo plaque. The login canvas
now uses the selected fund's brand-band colour behind the artwork, fading darker only
toward the access form. BIFS's opaque navy background blends into the same flat navy;
Moriah's transparent logo sits directly on its fund colour. Mobile uses a uniform
fund-coloured canvas to keep centred logos seamless.
