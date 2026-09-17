# Rate Card Manager - PRD Audit Findings

> Generated: 2026-06-25
> PRD source: `docs/rate-card-manager-prd-summary.md`
> Code audited at commit: `542c234` (post-sort-icon)

This file is an **audit only**. No code was changed. The findings below are organized by Area and Severity. Each row lists Current behavior → PRD requirement → Recommended fix → File. Use this as the queue for follow-up fixes.

**Severity scale:**
- **P0** — Wrong enum value, missing required field, broken Acceptance Criteria, fake behavior that misrepresents the product.
- **P1** — Wrong format / order / copy / column / interaction that violates an Acceptance Criterion but is visually understandable.
- **P2** — Minor drift, missing nice-to-haves, polish items called out in the PRD but not strictly required for a working flow.

---

## Section A — List view & data model

| # | Area | Current behavior | PRD requirement | Severity | Recommended fix | File |
|---|---|---|---|---|---|---|
| A1 | **Data / Marketplace enum** | `MARKETPLACE_OPTIONS = ["Upfront", "Scatter", "Addressable", "Programmatic", "Sponsorship", "Sports", "Streaming", "Multiplatform"]`. Seed data uses all 8 values. | Only `Upfront`, `Scatter`, `Multi-Year` (PRD R2). | **P0** | Trim `MARKETPLACE_OPTIONS` to 3 values. Rewrite every seed row that uses an unsupported marketplace to one of the 3 valid options (preserve a sensible mapping, e.g. Addressable/Programmatic/Streaming/Sports/Multiplatform/Sponsorship → either Scatter or Multi-Year depending on naming). Add `Multi-Year` option. | `app.js` (RATE_CARDS seed, MARKETPLACE_OPTIONS, filter panel options) |
| A2 | **Data / Status enum** | **RESOLVED 2026-06-25.** Seed data + localStorage hydrate + commit + duplicate all flow through a new `normalizeStatus()` helper that collapses every incoming value to `Published` or `Draft`. Seed rows remapped: `Active`/`Archived` → `Published` (Archive view does not exist in the prototype, so per the brief these become Published); `Pending Review`/`Pending` → `Draft` (work the user still owes). Chip CSS variants `.chip--active|--pending-review|--archived` and `.rcm-status-chip--active|--pending-review|--archived` deleted. `STATUS_ORDER` reduced to `{Draft:0, Published:1}`. `STATUS_LABEL_OVERRIDES` removed. Filter panel automatically reflects the two-state model because it pulls from `uniqueValues("status")` over `RATE_CARDS`. | UI shows only `Draft` or `Published` (PRD R3). Published may map to ACTIVE internally; UI shows Published. | **DONE** | — | `app.js`, `styles.css`, `index.html` (cache-bust) |
| A3 | **List columns** | Columns: Status, SalesHub ID, Rate Card ID, Name, Marketplace, Last updated, Ver., Action. **Missing:** CARD row count, Last Modified user. **Wrong order:** Name should be first. **Wrong column:** SalesHub ID is not a PRD column. | Columns per PRD R7: Rate Card Name, Version, Status, Rate Card ID, CARD row count, Last Modified user + timestamp, Actions. | **P1** | Replace the column set. Add `cardRowCount` (int) and `lastModifiedBy` (string) to seed rows. Remove SalesHub ID column (the spec does not require it; it can live in the Details slideover instead). Reorder columns. Update sort keys + sticky-Action wiring + column widths. | `index.html` (table head), `app.js` (renderRow, sortRows, table grid CSS in `styles.css`) |
| A4 | **List timestamp format** | `lastUpdated` is a string like `"Jun 18, 2026"`. | Format: `HH:MM, MM-DD-YYYY` (PRD R7). | **P1** | Convert seed lastUpdated to the PRD format. Update any place that renders the value (currently rendered as-is by `renderRow`). | `app.js` (seed + render) |
| A5 | **List actions — Continue (Draft only)** | Action column has 4 fixed icons: Quick edit, Duplicate, Export, Delete. **Edit pencil removed** in favor of Name-link-as-edit (see Section B above). **Still missing:** Archive (Delete remap), and the **Draft-only `Continue` action**. | Actions per PRD R7: Edit, Quick Edit, Duplicate, Archive, Export. Draft rows additionally get a `Continue` action that opens `?section=line`. Since Edit is now the Name link, the Action column needs Quick edit + Duplicate + Archive + Export (+ Continue for drafts). | **P1** | Swap Trash → Archive (with confirmation, mark `archived=true` rather than delete). Add per-row `Continue` button when `row.status === 'Draft'`. Export icon already in place (tooltip "Export rate card") - implementation H3 below. | `app.js` (renderRow actions) |
| A6 | **List sorting** | Sort works on Status, SalesHub ID, Rate Card ID, Name, Marketplace, Last updated, Ver. (7 columns). | PRD R7 calls out **name, version, uploaded date** as the sortable set. | **P2** | Defensible to keep the broader sort set since users benefit; flag to PM. If we narrow per PRD, sort glyph should only appear on those 3 headers. | `app.js` (sortRows + which `.th--sortable` markers are added) |
| A7 | **Search** | Case-insensitive substring across name, rateCardId, marketplace, buyingEntity. | "Search by name, file, rate card id, marketplace, and related fields" (PRD R7). Case-insensitive. | ✓ OK (matches) | No fix. | n/a |

---

## Section B — Row click → Details slideover

**Status: closed as "won't build".** Per the simplified interaction
brief (2026-06-25), the prototype intentionally skips the Details
slideover. The Name link is the primary entry into the full Edit
Rate Card page; the Action column owns secondary actions. The Edit
pencil icon was also removed from the Action column to avoid
duplicate Edit affordances. If product decides to bring the slideover
back later, the B1/B2 spec below is the authoritative target.

| # | Area | Original PRD requirement | Decision |
|---|---|---|---|
| B1 | Row click target | Row click (outside Actions) opens a Details slideover; Edit action stays in Actions. | **Won't build.** Name link opens Edit directly. URL becomes `?section=create&mode=edit&cardId={rateCardId}`. |
| B2 | Slideover content | Rate Card Name, Version, Status, Marketplace, Deal Season(s), CARD Effective dates, Buying Entity + Saleshub ID, Advertiser(s), Currency, Total Rows, Created/Updated By + timestamp. | **Won't build.** All fields remain available on the Edit page. |

---

## Section C — Create / Edit wizard (CARD/LINE/PREM)

| # | Area | Current behavior | PRD requirement | Severity | Recommended fix | File |
|---|---|---|---|---|---|---|
| C1 | **Wizard shell, three tabs** | Create page shows three accordion sections (CARD details, Line, PREM details) on a single scrollable page. No tab strip; no per-section URL routing; LINE/PREM accordions are always expanded by default. | Three tabs labeled CARD, LINE, PREM. URL pattern `?section=card|line|prem`. Tabs indicate whether objects exist at each step via highlights (PRD R9). | **P1** | Add a tab strip above the form. Update `navigateTo` to honor `?section=card|line|prem`. Keep the accordion layout as the in-tab body, or refactor to a single tab body. Either way, expose URL routing. | `index.html` (Create page header), `app.js` (navigateTo, route restore) |
| C2 | **LINE / PREM gating** | LINE and PREM sections are always editable from page load, even with no CARD saved. | LINE and PREM tabs disabled until at least one CARD row exists in the rate card file (PRD R9). | **P0** | Track CARD-saved state per rate card file. Disable LINE/PREM sections (or their tabs in C1) until at least one CARD row exists. | `app.js` (form state, accordion enabling) |
| C3 | **Save on blur** | Form fields do not auto-save on blur. Only Save buttons persist. Validation runs only on Save click. | Fields save on blur. Validation runs on blur (PRD R9, R4, R5, R6). | **P1** | Add `blur` listeners on each editable field that snapshot the value into the active draft and run that field's validator. | `app.js` (wire on all `input/edl-select/ads-datepicker` inside `[data-page="create"]`) |
| C4 | **`Save and Publish` gating** | Primary button label is `Save Rate Card` (create) / `Save Changes` (edit). Both run full validation on click but are NOT pre-disabled based on form completeness. | `Save and Publish` (a.k.a. `Save Rate Card File and Publish`) must be disabled until all required fields across all record types are complete (PRD R9). | **P1** | Recompute `[data-action="save-publish"].disabled` after every field change; enable only when full validation would pass. The existing `recomputeEditDirtyState` infra already gives a hook. | `app.js` (extend recomputeEditDirtyState OR add `recomputePublishReadiness`) |
| C5 | **`Cancel` warning** | No Cancel button exists in the wizard header today. Back link returns to list without warning. | `Cancel` button on each step warns the user before leaving if there are unsaved changes (PRD R9). | **P1** | Add a Cancel button to the wizard footer / header. On click, if dirty, show an ADS confirm dialog ("You have unsaved changes. Discard them?"). Confirmed → navigate away. Declined → stay. | `index.html` (button), `app.js` (handler + modal), `styles.css` |
| C6 | **Save and Create New CARD carryover** | No "Save and Create New CARD" button. (The list page has "Save and Create New Rate Card" which is a different concept — it saves and resets the whole form.) | `Save and Create New CARD` clears the CARD form **but preserves Buying Entity Saleshub ID + Display Name** from the first CARD in the same file (PRD R4). | **P1** | Add `Save and Create New CARD` to the CARD step. On click, save the CARD row, blank all CARD fields except `be-id` and `be-name` which carry over. | `index.html`, `app.js` |
| C7 | **Saved CARD/LINE/PREM tiles** | Saved CARD/LINE/PREM rows do not appear as tiles above the entry form. The user can only see the row in the Manager list after navigating back. | Saved CARD rows appear as a tile listing Rate Card Name + Buying Entity Display Name + Marketplace + Edit button (PRD R4). Saved LINE rows likewise (advertiser, Ad Product, Base Offering, Base Rate, Rate Card Name). Saved PREM rows likewise (Category, Name, Value, Conditions). | **P1** | Render a stacked-tiles strip at the top of each step body, sourced from the active rate card file's saved rows. | `index.html` (placeholder), `app.js` (render), `styles.css` (tile chrome) |

---

## Section D — CARD field-level audit

| # | Area | Current behavior | PRD requirement | Severity | Recommended fix | File |
|---|---|---|---|---|---|---|
| D1 | **CARD field — Rate Card ID** | Displayed as a `<span id="rc-id">` metadata strip, system-generated on save. Format used today is `RC-{ENTITY}-{KEYWORD}-{MKT}-{SEASON}`. | Auto-generated `varchar`. ✓ OK as design. | ✓ OK | No change. | n/a |
| D2 | **CARD field — Rate Card Name** | Required. `<input #rc-name>`. | Required varchar. | ✓ OK | No change. | n/a |
| D3 | **CARD field — Marketplace** | Required `edl-select[data-field=marketplace]`. Options drawn from MARKETPLACE_OPTIONS (8 values — see A1). | Required enum from 3 values (see A1). | **P0** | Bundled with A1. | `app.js` |
| D4 | **CARD field — Buying Entity Saleshub ID** | Required `<input #be-id>` placeholder `BE-GROUPM-2526`. | Required varchar — should match Saleshub format `00141000…`. Auto-populates Display Name. | **P1** | Use a Saleshub-style placeholder (`0014100000…`). Stub auto-populate Display Name (since Saleshub isn't wired) by mapping a few hardcoded examples; otherwise leave it manual and flag Saleshub integration as out of scope. | `index.html`, `app.js` |
| D5 | **CARD field — Buying Entity Display Name** | Required `<input #be-name>`. | Required. Auto-populates from Saleshub. | **P1** | See D4. | n/a |
| D6 | **CARD field — Deal Season format** | Currently rendered as `25–26` (en-dash) in `SEASON_OPTIONS` and seed data. | `YYYY-YYYY` per PRD (e.g. `2025-2026`). | **P0** | Replace `SEASON_OPTIONS = ["25–26", "24–25", "23–24"]` with `["2025-2026", "2024-2025", "2023-2024"]`. Migrate seed `season: "25-26"` to `"2025-2026"`. Update name regexp that extracts seasons. | `app.js` |
| D7 | **CARD field — DCM Rule Order** | `<input #dcm-rule type="number" min="0" step="1">`. Optional. | Optional int. | ✓ OK | No change. | n/a |
| D8 | **CARD field — Effective Start Date** | `ads-datepicker[data-field=eff-start]`. Optional today (no required validation). | **Required** per PRD. Format `YYYY-MM-DD`. | **P0** | Mark `Effective Start Date` required in `validateForm`. Verify the picker stores/emits `YYYY-MM-DD` strings (today they render `MM/DD/YYYY`). Add a `YYYY-MM-DD` storage layer + display formatter. | `app.js` (validateForm + collectForm) |
| D9 | **CARD field — Effective End Date** | `ads-datepicker[data-field=eff-end]`. Optional. | Optional `YYYY-MM-DD`. | **P1** | Apply the same `YYYY-MM-DD` storage as D8. | `app.js` |

---

## Section E — LINE field-level audit

| # | Area | Current behavior | PRD requirement | Severity | Recommended fix | File |
|---|---|---|---|---|---|---|
| E1 | **LINE field — Attach to Rate Card** | `<input #ln-attach type="text">` free-text with placeholder `e.g. Disney+ Upfront Video 25-26 Rate Card`. Label is "Allow Rows to Rate Card". | **Enum required**. Values = valid CARD rows in the same rate card file. All other LINE fields disabled until selected (PRD R5). Label per PRD: "Attach to Rate Card". | **P0** | Replace with `edl-select[data-field=attach-card]` populated from the active rate card file's saved CARD rows (at minimum the seed RC- IDs in this prototype). Rename label to "Attach to Rate Card". Disable every other LINE field while value is empty. | `index.html`, `app.js` |
| E2 | **LINE field — Advertiser ID + "Use Buying Entity ID" checkbox** | `<input #ln-advid>` exists. **No checkbox** to "Use Buying Entity ID from CARD". | Required. Add checkbox under Advertiser ID: "Use Buying Entity ID from CARD". When checked, populate Advertiser ID from selected CARD's Saleshub ID and Advertiser Display Name from CARD's Display Name (PRD R5). | **P0** | Add the checkbox below Advertiser ID. Wire it to populate both fields from the chosen CARD (requires E1 first). | `index.html`, `app.js` |
| E3 | **LINE field — Advertiser Display Name** | `<input #ln-advname>` required. | Required. Auto-populate when E2 checkbox is on. | **P1** | Wire population per E2. | `app.js` |
| E4 | **LINE field — Ad Product** | The current form has **no Ad Product field** (it was removed in an earlier "fix LINE layout" task). The form has Ad Type instead. | **Required, multi-select**, sourced from ICM Ad Product (PRD R5). | **P0** | Reintroduce Ad Product as a multi-select. ICM isn't wired; seed a placeholder option list. Drop or relabel the current "Ad Type" field, which doesn't appear in the PRD. | `index.html` (LINE Row 2), `app.js` |
| E5 | **LINE field — Base Offering** | Required `edl-select[data-field=base-offering]`. | Required. Sourced from ICM. | ✓ OK structurally | Options today are placeholders; flag ICM integration as out of scope. | n/a |
| E6 | **LINE field — Cost Method / Rate Type** | Required `edl-select[data-field=cost-method]`. | Required, single-select, sourced from ICM Default Cost Method. PRD calls it "Rate Type / Cost Method". | ✓ OK structurally | n/a |
| E7 | **LINE field — Base Rate** | Required `<input #ln-baserate>`. Validator: `/^\d*\.?\d+$/` — **disallows negative**. The current rule also implicitly forbids `0` because empty string fails `if (!baseRate)`. | Required float, **0 is valid**. (Negatives are not explicitly mentioned as valid for LINE — only PREM.) | **P0** | Change validator to accept `0` (e.g. parse to Number, check `!isNaN && >= 0`). Keep `> 0` if PM clarifies, but PRD explicitly says "Can be 0". | `app.js` (validateForm) |
| E8 | **LINE field — Currency** | Default USD; required not enforced (defaulted). | Required. ISO codes. ✓ OK as defaulted. | ✓ OK | n/a |
| E9 | **LINE field — Upfront ID** | **Missing field entirely.** | Optional varchar. | **P2** | Add `<input #ln-upfrontid>` to the LINE section. | `index.html` |
| E10 | **LINE conditions — count** | **Superseded by Adam's 2026-07-09 update.** The four legacy Line condition slots are consolidated into a single `Line conditions` field (`#ln-lc`) that accepts a comma-separated list (e.g. `A18-49, Preemptible`). The PRD source document still shows four discrete slots; treat this row as a resolved conflict, not open drift. | Four Line Condition fields per PRD R5. | ✓ Resolved (product decision supersedes PRD wording) | Flag if PM re-opens the multi-slot spec. | `index.html`, `app.js` |
| E11 | **LINE conditions — type** | Free-text `<input type="text">` accepting comma-separated values. Normalizer trims / dedupes / re-spaces `A, B` on blur. | Enum sourced from BDS Identifier Name (PRD R5). | **P1** | Free-form text is intentional for the 2026-07-09 consolidation. If BDS suggestions are added later, ship as an autocomplete over the same free-form field (do not revert to a dropdown). | `index.html`, `app.js` |
| E12 | **LINE field — Effective Start/End** | **Missing.** | Optional `YYYY-MM-DD`. | **P2** | Add date pickers in LINE step (optional). | `index.html` |

---

## Section F — PREM field-level audit

| # | Area | Current behavior | PRD requirement | Severity | Recommended fix | File |
|---|---|---|---|---|---|---|
| F1 | **PREM field — Attach to Rate Card** | `edl-select[data-field=prem-attach]` with hardcoded RC- IDs. | Required enum from valid CARD rows in the same rate card file (PRD R6). | **P1** | Populate dynamically from saved CARDs. | `app.js` |
| F2 | **PREM field — Attach to Advertiser** | **Missing field entirely.** | Appears only after a CARD is selected. Values = Advertiser Display Names from existing LINE rows for that CARD. | **P0** | Add `edl-select[data-field=prem-advertiser]` that shows up after CARD pick. Populate dynamically. | `index.html`, `app.js` |
| F3 | **PREM field — Premium Category** | `edl-select[data-field=prem-category]` with `Geo / Duration / 1P Audience / 3P Audience / Device Type / Format / Content`. Required today. | Optional varchar per PRD. (PRD does not require it. Categories are user-defined labels, not an enum.) | **P1** | Convert to optional `<input type="text">`, drop the required validator, drop the fixed enum. | `index.html`, `app.js` (validateForm) |
| F4 | **PREM field — Premium Display Name** | `<input #prem-displayname>` optional. | Optional varchar. ✓ OK | ✓ OK | n/a |
| F5 | **PREM field — Calculation Method** | `edl-select[data-field=prem-calc]` with values `ADDITIVE_CPM / MULTIPLICATIVE_PCT / FLAT_RATE`. Required. | Required. Only: `Additive CPM`, `Flat Fee`, `Percent Adjustment` (PRD R6 — different labels from current). | **P0** | Rename options to PRD labels (display labels: `Additive CPM`, `Flat Fee`, `Percent Adjustment`; internal codes can stay `ADDITIVE_CPM`/`FLAT_FEE`/`PERCENT_ADJUSTMENT`). | `app.js` (PREM_CALC_OPTIONS) |
| F6 | **PREM field — Value** | Required `<input #prem-value>`. Validator: `/^\d*\.?\d+$/` — **disallows negative and 0**. | Required float, **0 valid, negatives valid** (PRD R6). | **P0** | Change validator to accept negatives and 0 (`!isNaN(parseFloat(val))`). | `app.js` (validateForm) |
| F7 | **PREM field — Stack Order** | `<input #prem-stack type="number" min="0" step="1">`. Optional. | Optional int. ✓ OK | ✓ OK | n/a |
| F8 | **PREM conditions — type** | Three free-text fields `prem-cond1..3`. | Optional enums from BDS Identifier Name. | **P1** | Same treatment as E11. | `index.html`, `app.js` |

---

## Section G — Quick Edit audit

| # | Area | Current behavior | PRD requirement | Severity | Recommended fix | File |
|---|---|---|---|---|---|---|
| G1 | **Quick Edit scope** | Opens a bottom sheet for the clicked CARD's rate grid. Lets the user edit base rate per row directly. | Quick Edit is for LINE/PREM edits only. Flow must include: select CARD → select record type (`Line Rows` / `Premium Rows`) → select Advertiser (with `All Advertisers`, no duplicate names) → edit (PRD R10). | **P1** | Add the three selector dropdowns at the top of the sheet (CARD, record type, Advertiser). Render different edit grids for LINE vs PREM. | `index.html` (qsheet head), `app.js` (qsheet render) |
| G2 | **Quick Edit — LINE editable fields** | Editable today: Base Rate + line conditions per row. | Editable: Base Rate (2dp truncation), all Line Condition fields. Read-only: Row, Ad Product, Base Offering, Advertiser. | **P1** | Truncate Base Rate display to 2 decimal places. Surface Row number column. Render Advertiser as read-only (today there's no per-row advertiser shown). | `app.js` |
| G3 | **Quick Edit — PREM editable fields** | **Not implemented.** Quick Edit today only handles LINE-style rate edits. | Editable PREM: Category, Display Name, Value (2dp), Calculation Method, all Premium Condition fields. Read-only: Row, Ad Format (hide if blank), Base Offering (hide if blank). | **P0** | Build the PREM-mode panel inside Quick Edit. | `app.js`, `index.html`, `styles.css` |

---

## Section H — Import / Export audit

| # | Area | Current behavior | PRD requirement | Severity | Recommended fix | File |
|---|---|---|---|---|---|---|
| H1 | **Download blank template** | `[data-action="download-template"]` button exists in the list-page header. Behavior is a toast only (no file download). | Browser downloads `rate-card-import-template.csv` (PRD R7). | **P0** | Either implement the CSV blob download with the proper headers, or replace the button copy with "Coming soon" + flag missing in PRD audit. **Prototype rule R12: do not fake.** | `app.js` |
| H2 | **Upload completed CSV** | `[data-action="upload-template"]` button exists. Opens a placeholder modal; does not actually parse a CSV. | Parse CSV, partial ingestion on row errors, plain-language errors, new card appears at top (PRD R7 + R12). | **P0** | Implement at least a minimum CSV parser (Papa Parse-style), validate each row against the CARD/LINE/PREM schemas, surface per-row errors. If out of scope for this iteration, mark "Coming soon". | `app.js` |
| H3 | **Export rate card** | Per-row Download icon toasts "Exporting CSV: {name}" — no file produced. | Action exports a full copy of that rate card in the RCM template. | **P0** | Implement CSV export per row (serialize CARD + LINE + PREM rows for that file). Otherwise drop the icon and surface as "Coming soon". | `app.js` |

---

## Section I — Misc validation & UX

| # | Area | Current behavior | PRD requirement | Severity | Recommended fix | File |
|---|---|---|---|---|---|---|
| I1 | **Em dashes in copy** | Seed data and option labels use en-dashes in season strings (`25–26`). Per `.cursorrules`: "No em dashes anywhere." | No em dashes (project-wide rule). En-dash `–` (U+2013) is also not an ASCII dash — D6 fix already addresses Season strings, but audit other strings. | **P1** | Sweep `app.js`, `index.html`, `styles.css` for `–` (en-dash) and `—` (em-dash) and replace with hyphen or restructure. | repo-wide |
| I2 | **"Allow Rows to Rate Card" label** | LINE step label says "Allow Rows to Rate Card". | Label per PRD: "Attach to Rate Card". Bundled with E1. | **P1** | Rename label. | `index.html` |
| I3 | **Effective dates format on render** | Date picker renders selected dates as `MM/DD/YYYY`. | Stored / API-level format `YYYY-MM-DD`. PRD doesn't specify display format (MM/DD/YYYY is acceptable for US UI as long as storage uses ISO). | **P2** | Confirm with PM. Keep MM/DD/YYYY display; ensure storage / collectForm normalizes to YYYY-MM-DD before any persistence or import/export round-trips. | `app.js` (collectForm) |

---

## Roll-up by severity

- **P0 issues:** A1, A2, B1, B2, C2, D3 (=A1), D6, D8, E1, E2, E4, E7, F2, F5, F6, G3, H1, H2, H3 — **18 items**.
- **P1 issues:** A3, A4, A5, C1, C3, C4, C5, C6, C7, D4, D5, D9, E3, E10, E11, F1, F3, F8, G1, G2, I1, I2 — **22 items**.
- **P2 issues:** A6, D7, E9, E12, I3 — **5 items**.

Total: **45 audit items** across List, CARD, LINE, PREM, Quick Edit, Import/Export, Validation, Data.

---

## Suggested fix sequencing

If you approve the fixes, a sensible batching:

1. **Batch 1 — Data model truth-up (P0).** A1 (marketplace enum), A2 (status enum), D6 (season format), E7 (Base Rate allows 0), F5 (Calc Method labels), F6 (PREM Value allows 0/negative). All in `app.js` mock data + validateForm + option constants. Cheap, foundational, regression-safe.
2. **Batch 2 — Field truth-up (P0).** D8 (Effective Start required), E1 (Attach to Rate Card enum + gating), E2 (Use Buying Entity ID checkbox), E4 (Ad Product), F2 (Attach to Advertiser).
3. **Batch 3 — Row click + slideover (P0).** B1 + B2 — replace name-click → Edit with name-click → Details slideover. Move Edit to its existing icon only.
4. **Batch 4 — Quick Edit completion (P0/P1).** G1, G2, G3.
5. **Batch 5 — List columns + Continue + Archive (P1).** A3, A4, A5.
6. **Batch 6 — Wizard tabs + gating + save-on-blur + Cancel guard (P1).** C1, C2, C3, C4, C5, C6, C7.
7. **Batch 7 — Conditions / minor LINE fields / formatting (P1/P2).** E10, E11, E12, F8, I1, I2.
8. **Batch 8 — Import/export honesty pass (P0).** H1, H2, H3 — either implement minimally or surface "Coming soon" and remove fake toasts.

Open question for PM before starting: **what to do with the seed rows that currently use unsupported marketplaces / statuses?** Drop them, remap them, or leave them as a known seed-data artifact?
