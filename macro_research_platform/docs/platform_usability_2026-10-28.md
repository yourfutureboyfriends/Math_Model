# Platform usability and PE development — 28 October 2026

## Shared improvements across all five areas

- Workspace toolbar: pinned and recent destinations spanning Macro, Trading, Quant,
  Markets and PE. Navigation is local; pins/history are scoped by user and fund.
- Visible sidebar control with remembered collapse state, command-search access,
  shortcuts help and back-to-top action.
- Readable-table and reduced-motion preferences, keyboard focus outlines, skip-to-content
  access and row hover feedback. Preferences apply throughout the terminal.
- Browser offline feedback and background macro-refresh status.
- A macro startup/data failure no longer prevents entry to independent Markets/PE tools.
- Macro polling starts only after authentication and skips hidden-tab polling.
- Dashboard single-key shortcuts no longer intercept PE/Markets navigation, selects or
  contenteditable controls. Mode changes keep an explicit `?mode=` URL consistent.

## PE

Added sourced EBITDA adjustments, tax/covenant controls, cash-timing diagnostics,
diligence progress retained in the pipeline, searchable/filterable pipeline, draft
restore, undo/redo and comparison baseline. Results identify the exact input run and
cannot show a prior calculation as if it belonged to updated assumptions.

The Excel export now contains both the selected-method snapshot and a separately
labeled editable opening-interest model. See [PE methodology](private_equity.md) for
formulas, input conventions, sources and limits.

## Validation and limits

Numerical tests independently evaluate live spreadsheet formulas against the Python
engine. Frontend tests cover input undo/redo and branch history, pinning/restoring a
workspace, shared display preferences and offline feedback. Browser checks exercise
PE workbench loading, input tabs and the shared toolbar. Full-platform visual redesign,
complete legal/tax engines and integrated quarterly financing are not claimed.

Verification: 54 targeted backend tests and all 89 frontend tests passed; TypeScript
and production Vite builds passed. The build retains existing large-chunk warnings.
The PE browser view was checked with live calculation results, the shared toolbar
and the Diligence input tab. The final spreadsheet formatting/input-validation change
was checked with the workbook export test.
