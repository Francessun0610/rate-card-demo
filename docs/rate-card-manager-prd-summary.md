# Rate Card Manager (RCM) - PRD Summary

> Source of truth: `Rate Card Manager (RCM) - PRD.docx` (Author: Adam Hecht)
> Status: DRAFT
> Last summarized: 2026-06-25

This file is the **product requirements reference** for all Rate Card Manager work going forward. Cursor must read it before implementing, refactoring, auditing, or QAing any RCM functionality. When the current UI conflicts with this PRD, flag the conflict before changing behavior.

The full PRD lives outside the repo at `~/Downloads/Rate Card Manager (RCM) - PRD.docx`. This summary captures the implementation-relevant requirements; for full context (vision, OKRs, integrations, roles), open the source document.

---

## 1. Why RCM exists

Rate cards for the Direct business today are negotiated offline and circulated as Excel workbooks with inconsistent structure. DCM customers use a separate Pricing Manager tool with a different data model. **Rate Card Manager (RCM) in Atlas** is a flexibility-first replacement that normalizes every rate card to a single flat CSV with three row types: **CARD**, **LINE**, **PREM**. RCM supports:

- Planning Managers creating/maintaining rate cards in the UI
- An importer with tightly-defined validations + plain-language errors
- (Future) a Pricing Agent

RCM **replaces DCM's Pricing Manager in full** as part of the move to Core Planning.

---

## 2. Data model: CARD / LINE / PREM

RCM normalizes every rate card to **three row types** that map to **four pricing pillars** (Marketplace, Buying Entity, Inventory, Premiums).

| Row type | Pillars | Role | Key fields |
|---|---|---|---|
| **CARD** | Marketplace + Buying Entity | The parent rate card. A CARD row is one discrete rate card within a rate card file. | Marketplace, Buying Entity, Deal Season |
| **LINE** | Buying Entity + Inventory | One negotiated Base Price attached to an Ad Product and Base Offering. Supports custom conditions. | Advertiser, Base Rate, Ad Product, Base Offering |
| **PREM** | Inventory + Premiums | One premium adjustment to base price (targeting, duration, format fees, etc.) | Premium Name, Premium Value, Premium Condition |

**Mental model rules (UI must preserve):**
- A **Rate Card File** is the unit of import. One file can contain many CARD, many LINE, and zero+ PREM rows.
- A **Rate Card** is the unit of storage and the primary record. Each row in the Rate Card List view is a single CARD line from its parent file.
- CARD rows carry Marketplace + Buying Entity context.
- LINE rows carry Advertiser + Inventory + negotiated base rate.
- PREM rows carry premium adjustments to base prices.

---

## 3. CARD row fields

| Field | Type | Required | Notes |
|---|---|---|---|
| Id | varchar | system | Auto-generated. |
| Rate Card Name | varchar | Yes | |
| Marketplace | enum | Yes | **Only:** `UPFRONT`, `SCATTER`, `MULTI-YEAR`. Display labels: `Upfront`, `Scatter`, `Multi-Year`. No free text. No other values. Never spell it "marketspace". |
| Buying Entity Saleshub ID | varchar | Yes | Validates against Saleshub. |
| Buying Entity Display Name | varchar | Yes | Auto-populated from Saleshub when ID is entered. |
| Deal Season | YYYY-YYYY | Yes | E.g. `2025-2026`. |
| DCM Rule Order | int | No | |
| Effective Start Date | YYYY-MM-DD | Yes | |
| Effective End Date | YYYY-MM-DD | No | |

**CARD step behavior:**
- Fields save on blur. Validation runs on blur.
- Five close options: `Save and Create New CARD`, `Save and Create New LINE`, `Save Rate Card File as Draft`, `Save Rate Card File and Publish`, `Cancel`.
- `Save and Create New CARD` clears the form **but preserves Buying Entity Saleshub ID + Display Name** from the first CARD.
- `Save and Create New LINE` saves the CARD row and navigates to the LINE step.
- `Save Rate Card File and Publish` is **disabled until all required fields in all relevant record types are present**.
- `Cancel` warns before leaving.
- Saved CARD rows appear as a **tile above the entry fields** showing Rate Card Name, Buying Entity Display Name (if present), Marketplace, and an Edit button.

---

## 4. LINE row fields

| Field | Type | Required | Notes |
|---|---|---|---|
| Attach to Rate Card | enum | Yes | Values = valid CARD rows from the **same rate card file**. **All other LINE fields are disabled until this is chosen.** |
| Advertiser ID | varchar | Yes | Has a checkbox: **"Use Buying Entity ID from CARD"**. When checked, populate from selected CARD's Buying Entity Saleshub ID. |
| Advertiser Display Name | varchar | Yes | When "Use Buying Entity ID" is checked, also populate from selected CARD's Buying Entity Display Name. |
| Ad Product | enum (multi-select) | Yes | Values sourced from **ICM Ad Product**. New ICM values auto-flow into RCM. |
| Base Offering | enum (single?) | Yes | Values sourced from **ICM Base Offering** (includes App Groups). |
| Rate Type / Cost Method | enum (single) | Yes | Values from ICM Default Cost Method enum. |
| Base Rate | float | Yes | **0 is valid.** |
| Currency | enum | Yes | ISO currency codes. |
| Upfront ID | varchar | No | |
| Line Condition 1 | enum | No | Sourced from BDS Identifier Name. |
| Line Condition 2 | enum | No | Sourced from BDS Identifier Name. |
| Line Condition 3 | enum | No | Sourced from BDS Identifier Name. |
| Line Condition 4 | enum | No | Sourced from BDS Identifier Name. (Up to **four** condition slots, not three.) |
| Effective Start Date | YYYY-MM-DD | No | |
| Effective End Date | YYYY-MM-DD | No | |

**LINE step behavior:**
- Fields save on blur. Validation runs on blur.
- All LINE fields disabled until Attach to Rate Card is selected.
- Five close options: `Save and Create New LINE`, `Save and Create New PREM`, `Save Rate Card File as Draft`, `Save Rate Card File and Publish`, `Cancel`.
- Saved CARD tile + saved LINE tile show at the top.

---

## 5. PREM row fields

| Field | Type | Required | Notes |
|---|---|---|---|
| Attach to Rate Card | enum | Yes | Values = valid CARD rows from the same rate card file. |
| Attach to Advertiser | enum | No | **Only appears after a CARD is selected.** Values = Advertiser Display Names from existing LINE rows. |
| Premium Category | varchar | No | |
| Premium Display Name | varchar | No | Stakeholder-readable label. |
| Calculation Method | enum | Yes | Only: `Additive CPM`, `Flat Fee`, `Percent Adjustment`. |
| Value | float | Yes | **0 is valid. Negative values are valid.** |
| Stack Order | int | No | |
| Premium Condition 1..n | enum | No | Sourced from BDS Identifier Name. |

**PREM step behavior:**
- Four close options: `Save and Create New PREM`, `Save Rate Card File as Draft`, `Save Rate Card File and Publish`, `Cancel`.
- Saved PREM rows show at top: Premium Category, Premium Name, Premium Value, Premium Conditions. If Category + Name missing, show only Value + Conditions.

---

## 6. Rate Card List view

**Functionality (P0):**
- Search (case-insensitive)
- Sort
- Filter
- Upload completed CSV (importer)
- Download blank template (`rate-card-import-template.csv`)
- Create new rate card

**Columns (in order):**
1. Rate Card Name
2. Version
3. Status — only `Draft` or `Published` in UI (Published may map to `ACTIVE` internally; UI shows Published)
4. Rate Card ID
5. CARD row count
6. Last Modified user + timestamp (format: `HH:MM, MM-DD-YYYY`)
7. Actions

**Actions on each row:**
- Edit (opens full CARD/LINE/PREM wizard at `?section=card`)
- Quick Edit (bottom sheet for LINE/PREM only)
- Duplicate (creates new version with incremented branch version)
- Archive (with confirmation)
- Export (full copy in RCM template)
- **Continue** — only appears for Draft rows. Navigates to `?section=line` and resumes at the most recent unfinished row.

**Sort:** by name, version, uploaded date. **Action column is not sortable.**

**Sortable list of routes / URLs:**
- `/rate-card-manager` — list view
- `/rate-card-manager/{id}/edit?section=card` — CARD step of wizard
- `/rate-card-manager/{id}/edit?section=line` — LINE step
- `/rate-card-manager/{id}/edit?section=prem` — PREM step

---

## 7. Row click → Edit Rate Card (PRD says slideover; prototype simplifies)

**PRD specifies a Details slideover** that opens when a row is clicked outside the Actions column. The slideover would show summary fields (name, version, status, marketplace, deal season(s), effective dates, buying entity + Saleshub ID, advertiser(s), currency, total rows, created/updated by + timestamps).

**Design note: Details slideover removed in favor of direct edit from Name link to reduce duplicate navigation paths.** In this prototype the rate card Name link is the primary entry into the full Edit Rate Card page, and the Action column owns secondary row actions (Quick edit, Duplicate, Export, Archive/Delete). The Edit pencil icon was removed from the Action column for the same reason - it duplicates the Name link.

If we ever decide to bring the slideover back (e.g. for fast scanning without leaving the list), the field list above is the authoritative spec.

---

## 8. Create / Edit wizard

**Shell:** Three tabs — CARD, LINE, PREM — that match the CSV row types. Tabs highlight when objects exist at each step. URL pattern: `?section=card|line|prem`.

**Tab gating:** **LINE and PREM tabs are disabled until at least one CARD row exists** in the rate card file.

**Save behavior:**
- Fields save on blur. Validation on blur.
- Sticky footer with `Save as Draft`, `Save and Publish`, `Cancel`, and section-specific save actions.
- `Save and Publish` (a.k.a. `Save Rate Card File and Publish`) is **disabled until all required fields across all relevant record types are complete**.
- `Cancel` warns before leaving.

**Save and Create New {type}** at each step clears that step's form fields and preserves carryover fields (e.g. Buying Entity from CARD; selected CARD context for LINE/PREM).

---

## 9. Quick Edit

**Quick Edit is for LINE/PREM edits only — it is NOT a full CARD editor.**

**Flow:**
1. User opens Quick Edit (from List Actions or Detail view).
2. User selects a **CARD row** from an enum of Rate Card Names.
3. User selects a **record type**: `Line Rows` or `Premium Rows`.
4. User selects an **Advertiser** from an enum of Advertiser Display Names for the chosen CARD. Include an **`All Advertisers`** option for globally-scoped rows. **Do not show duplicate advertiser names.**
5. The panel shows rows for that CARD × record type × advertiser combo.

**Editable LINE fields:** Base Rate (truncate to 2 decimal places), All Line Condition fields.
**Read-only LINE fields:** Row number, Ad Product, Base Offering, Advertiser.

**Editable PREM fields:** Category, Display Name, Value (truncate to 2 decimal places), Calculation Method, All Premium Condition fields.
**Read-only PREM fields:** Row number, Ad Format (only if present — hide if blank), Base Offering (only if present — hide if blank).

**Save semantics:** Fields validate + save when the Save button is used. Changes persist to the Rate Card File.

---

## 10. Validation / supported values

- **Marketplace:** only `Upfront`, `Scatter`, `Multi-Year` (internal enum `UPFRONT`/`SCATTER`/`MULTI-YEAR`). No other values. Never "marketspace".
- **Status (UI):** only `Draft` and `Published`. Published may map internally to `ACTIVE`, but the UI shows `Published`.
- **Deal Season:** `YYYY-YYYY` (e.g. `2025-2026`), NOT `25-26` or `25–26`.
- **Effective dates:** `YYYY-MM-DD`.
- **Currency:** ISO currency codes.
- **Base Rate:** float, **0 is valid**.
- **PREM Value:** float, **0 valid, negatives valid**.
- **DCM Rule Order, Stack Order:** integers.
- **Search:** case-insensitive.
- **Sort:** only sortable columns (per PRD: name, version, uploaded date). Action column never sortable.

---

## 11. Import / Export

**Import:**
- Download blank CSV template named exactly `rate-card-import-template.csv`.
- Upload completed CSV.
- **Partial ingestion** when some rows have errors and others are valid (valid rows still ingest).
- Plain-language error messages tell the user how to fix issues.

**Export:**
- Export full copy of a selected rate card in the RCM template.

**Prototype rule:** if import/export is not fully implemented, **flag as missing** instead of faking the behavior.

---

## 12. Integrations (for context)

| Priority | Integration | Why |
|---|---|---|
| P0 | Saleshub | Validate every CARD Buying Entity Saleshub ID and LINE Advertiser ID. Auto-populate display names. |
| P0 | ICM | Source of truth for Ad Product + Base Offering enums (also auto-pulls new values). |
| P0 | DCM | RCM replaces Pricing Manager. DCM customers see RCM prices via account mapping. |
| P0 | Core Planning | Planners consume RCM-priced line items automatically. |
| P1 | Business Dictionary Service (BDS) | Sources Line Condition + Premium Condition enums by Identifier Name. |

---

## 13. Roles + Permissions (out of scope for prototype, in scope for future)

- Pricing Admin — full CRUD, view all (in scope for QTC agent release)
- Read Only Admin — full read (in scope for QTC agent release)
- Channel Lead — full CRUD for own Demand Channel (e.g. Direct, DCM)
- Read Only Team Lead — read only for that team's rate cards

---

## 14. Out of scope for V1

- Dynamic pricing based on forecast or other variables
- Floor / Ceiling values for automating approvals
- Programmatic biddable use cases

---

## 15. Implementation guardrails for this repo

When working on RCM in this repo:

1. **Read this file first**, then `.cursor/rules/rate-card-manager-prd.mdc`, then `DESIGN.md`, then `ads-components.json`.
2. **Do not rewrite product behavior based only on the current UI.** When current UI conflicts with this PRD, flag the conflict before changing.
3. **Do not invent unsupported enum values** (e.g. extra marketplaces, extra statuses, hand-written conditions).
4. **Do not fake import/export behavior** if the underlying machinery isn't built. Flag as missing.
5. **Mock data must obey the PRD** — Marketplace values, Status values, Deal Season format, etc.
6. **The three tabs (CARD/LINE/PREM) match the CSV** — the mental model must be preserved across UI, copy, and data.

When ambiguous, **flag for the human** rather than guess.
