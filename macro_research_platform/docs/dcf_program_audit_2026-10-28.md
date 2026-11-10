# Follow-up valuation and application audit — 28 October 2026

## Scope and outcome

Reviewed the DCF evidence layer, route eligibility, valuation hub request lifecycle,
scenario assumptions, live application startup and existing regression tests. This is
a focused valuation/application audit, not a complete security or investment-performance
certification of every platform module.

## Fixed

1. **Research-ineligible estimates still generated convergence outlooks.** The API now
   returns a null outlook when eligibility fails; the hub also suppresses the path.
   A route regression test fails if the outlook engine is invoked for ineligible inputs.
2. **Old responses could enter a new blend.** The shared request hook retains previous
   data during a URL change. The valuation hub now consumes only responses whose URL
   matches the requested symbol and assumptions, showing loading while replacements arrive.
3. **Working-capital scenario assumptions were missing from the table.** Defaults now
   expose the returned ratio alongside the model's other effective assumptions.
4. **Statement dates had no age review.** Invalid/future dates now require research;
   annual bases older than 550 days and TTM bases older than 270 days require review.
   These are explicit screening thresholds, not statutory filing deadlines. Six cases
   verify annual/TTM ages, invalid dates and future dates.
5. **A selected dividend model could require review while the blend received a label
   based solely on the primary model.** A selected, useful dividend model must also
   pass its checks before automatic labels/thresholds are shown.
6. **Outlook could use the original assumptions after sliders changed.** It now follows
   the current primary response. Convergence timing is explicitly labeled an assumption.

## Runtime verification

The existing frontend is running at http://localhost:5173. Restarted this project's
backend on 127.0.0.1:8000 to load the fixes and verified the health response: status ok,
live mode, analytical integrity HEALTHY, no integrity errors. The Microsoft VAL screen
was opened and rendered in the in-app browser.

A live Microsoft result correctly requires research because filed SEC depreciation
and the Yahoo cash-flow evidence differ materially. The model retains the SEC input
and exposes the conflict; it does not silently average providers or present a buy label.
Resolving the accounting taxonomy requires inspection of the matching filing and
cash-flow line definitions. This audit has not established which alternative measure
should replace the filed figure.

## Tests

- 104 tests passed across the valuation modules and the full markets-functions file.
- TypeScript `tsc --noEmit` passed, including the final blend guard changes.
- All 84 frontend tests passed, including local API integration tests.
- The broader backend run stopped at its configured eight-failure limit: 204 passed,
  13 skipped, eight failed. Five failures involved blocked public-data DNS/network
  access; three involved nested process sandbox restrictions. All eight passed on a
  separate rerun with the required environment access. The remaining broad suite was
  not completed; these counts must not be described as a full-suite pass.
- `git diff --check` passed.

## Remaining priorities

1. Reconcile issuer-vs-provider accounting taxonomy, especially depreciation,
   acquisition cash flows, leases, restricted cash and recurring/nonrecurring earnings.
   The Microsoft live conflict is a concrete case for the reconciliation queue.
2. Build archived publication-time financial inputs and evaluate precommitted forecast
   and return tests with delistings, corporate actions, FX and costs. Price proximity
   and method agreement do not measure intrinsic-value accuracy.
3. Add specialist NAV/look-through valuation for property and holding companies and
   reserve/capex models for resource producers. Existing references and review flags
   are useful but do not implement these models.
4. Model refinancing, debt maturity, minimum operating cash and share dilution before
   interpreting projected financing gaps as investable equity values.
5. Add browser regression coverage for rapid symbol switches and slider changes; the
   current request guards typecheck and render, but lack a dedicated race-condition test.
6. Separate network-dependent tests and process-isolation tests in CI so an environment
   restriction is reported distinctly from a numerical or application regression.

No proprietary institutional model has been reproduced, and no newly fitted accuracy
probability or return guarantee is introduced. Unrelated existing options-engine work
and user data edits were left outside the scope of these fixes.
