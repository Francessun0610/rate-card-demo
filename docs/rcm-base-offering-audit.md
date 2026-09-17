# RCM Base Offering / Ad Type Business-Model Audit

> Generated: 2026-08-02
> Scope: Rate Card Manager v2.0 Create/Edit LINE step (`index.html`, `v2.js`, `fixtures/demo-rate-card-catalog.js`, `fixtures/demo-cross-platform-rate-card.js`, `qa_v2.py`, `qa_demo_dataset.py`)
> Source of truth: `Rate Card Manager (RCM) - 6 Pager.docx`, section "4. Proposed Solution" - "Inventory"
> Confidence: High for the Base Offering fix, high for the Ad Type fix. Both are corrected by direct textual example from the 6-Pager, not inference.

## Finding

The 6-Pager defines Inventory as a two-axis concept owned by the LINE object:

> "Inventory considerations are at the LINE level, and represent the Ad Type (e.g. Standard Video, Pause Ads) and the Base Offering (e.g. Disney+, Sports by ESPN)."

Two axes, two fields:
- **Ad Type** = the ad format. Platform-agnostic.
- **Base Offering** = the platform/property. Format-agnostic.

The v2.0 UI's live dropdown values violated this in both directions before this fix:

1. **Base Offering baked the delivery mechanism ("Addressable") into the platform name.** 4 of 8 values were `ABC Addressable`, `FX Addressable`, `Freeform Addressable`, `National Geographic Addressable`. The 6-Pager's own Base Offering example is a bare platform name with no delivery modifier (`Disney+`, `Sports by ESPN`), and the pre-fix Ad Type list already had a standalone `Addressable TV` value, proving "Addressable" is an Ad Type concept, not a Base Offering modifier.
2. **Ad Type baked the platform name into the format.** The 3 platform-specific values were `Disney+ Standard Video`, `Hulu CTV`, `ESPN Live Sports`, when the 6-Pager's own Ad Type examples (`Standard Video`, `Pause Ads`) are platform-agnostic. This duplicated the Base Offering axis inside the Ad Type field, so a LINE's platform was effectively encoded twice.

Net effect: Base Offering and Ad Type were not two clean, independent axes as specified; they were partially overlapping and inconsistently modeled across the same dropdown.

## Correction (the only content change)

| Field | Old value | New value |
|---|---|---|
| Base Offering | `ESPN` | `Sports by ESPN` (matches the 6-Pager's exact example) |
| Base Offering | `ABC Addressable` | `ABC` |
| Base Offering | `FX Addressable` | `FX` |
| Base Offering | `Freeform Addressable` | `Freeform` |
| Base Offering | `National Geographic Addressable` | `National Geographic` |
| Ad Type | `Disney+ Standard Video` | `Standard Video` |
| Ad Type | `Hulu CTV` | `Connected TV` |
| Ad Type | `ESPN Live Sports` | `Live Sports` |

Unchanged: `Disney+`, `Hulu` (Base Offering, already platform-only); `Streaming Bundle`, `Addressable TV` (Ad Type, already format-only). `Streaming Bundle` existing in both fields is a separate, lower-confidence observation, flagged below but not corrected in this pass.

No new enum values were invented. Every new string is either a documented 6-Pager example or an existing value already present elsewhere in the same dropdown (`Addressable TV`).

## Files changed

- `index.html` - Ad Type `<ul id="v2-ad-product-menu">` and Base Offering `<select id="v2-base-offering">` option lists.
- `v2.js` - `createSeedFile()` default new-card seed rotation.
- `fixtures/demo-rate-card-catalog.js` - `DENTSU_ADDRESSABLE_OFFERINGS`, `inventoryFor()`, `baseRateFor()`, `dentsuPremiumRequirements()`, `dentsuRateFor()`/`floorByOffering`, `buildDentsuAddressablePremiums()`, `premiumTemplate()`.
- `fixtures/demo-cross-platform-rate-card.js` - `inventoryPatterns`, `conditionFor()`, `primaryPremium()`, `seasonalPremium()`.
- `qa_v2.py` - dropdown option-text/value assertions, keyboard-selection assertions, LINE form-fill test data (~13 locations).
- `qa_demo_dataset.py` - enum allowlists, Dentsu offering distribution, cross-platform allowed-offering map, CSV import fixture rows (~20 locations).

Explicitly **not** touched (out of scope, confirmed by grep and left as-is on purpose):

- Legacy v1.x `AD_TYPE_OPTIONS` / `BASE_OFFERING_OPTIONS` / `AD_PRODUCT_OPTIONS` / `MARKETPLACE_OPTIONS` in `app.js`, and the seed rate card names in `app.js` that contain "ESPN Live Sports 2025-2026" as a display name. Different (inactive) UI vocabulary, already tracked as its own item in `docs/rate-card-manager-prd-audit.md`.
- `inventoryOptions()` in `fixtures/demo-rate-card-catalog.js` and the analogous inline literal in `fixtures/demo-cross-platform-rate-card.js`'s `conditionFor()`. These return **Line Condition tag pool values** (a different concept - targeting/context tags, not the Base Offering enum), and their regexes (`espn`, `abc`, `fx`, `freeform`, `national geographic`) still match the renamed values, so no functional change was needed.
- Rate Card **name** strings anywhere (e.g. `"WPP Disney+ Upfront 2025-2026"`) - a different field, out of scope.

## Verification

- `python3 qa_v2.py` - **177 passed, 0 failed.**
- `python3 qa_demo_dataset.py` - **41 passed, 0 failed**, when run against only this change (see note below).
- Visual check: Ad Type dropdown now reads `Standard Video | Connected TV | Live Sports | Streaming Bundle | Addressable TV`; Base Offering now reads `Disney+ | Hulu | Sports by ESPN | Streaming Bundle | ABC | FX | Freeform | National Geographic`. Confirmed on the `RC-1001` seed card and the `RC-DAS-DENTSU-ADDR-SC-2526` Addressable TV demo card (48 LINE rows spanning all 7 non-Disney+/Hulu offerings).

### Unrelated pre-existing failure found during verification

Running `qa_demo_dataset.py` against the **full** working tree (including other uncommitted changes from earlier, unrelated tasks this session: `v2.css`, `styles.css`, `app.js`, deleted pagination caret SVGs) shows one failure: `"Compact layout stacks without body-level horizontal overflow"` (700x900 viewport, cross-platform fixture). Isolating this change (stashing the unrelated files) confirms the suite is clean at 41/41; reverting to the last commit also passes. This regression predates this rename and was not introduced or fixed by it. Flagging for separate follow-up rather than fixing here, since it is outside this plan's scope.

## Lower-confidence item not acted on

`Streaming Bundle` appears as a value in both Ad Type and Base Offering. It is plausible as a legitimate cross-axis value (a bundled Ad Type sold against a bundled Base Offering), but the 6-Pager does not give an explicit example either way. Left unchanged pending product confirmation.

---

## Follow-up: 2026-08-04 Ad Type taxonomy correction

> Scope: Ad Type dropdown values only. Base Offering, Line Condition, Cost Method, Currency, Marketplace, and Status are unchanged.
> Source of truth: 6-Pager Ad Type examples (`Standard Video`, `Pause Ads`) + product-provided example (`BrightLine`).
> Confidence: High for removal of the four platform/property/delivery values, medium for the final option list (see caveat).

### Finding

Four of the five Ad Type values in the LINE step were platform, property, or delivery-mechanism classifications, not ad formats:

- `Connected TV` is a device / delivery-channel classification. The format shown on a CTV screen is still `Standard Video` (or an interactive unit).
- `Live Sports` is a content genre / property. The format shown during a live sporting event is `Standard Video`, `Pause Ads`, or an interactive unit; the sports signal belongs on Base Offering (`Sports by ESPN`) or a Line Condition (`Sports Fans`, `Live Events`).
- `Streaming Bundle` is a Base Offering (already listed in the Base Offering dropdown). Ad Type is a format axis; a bundle is a property axis.
- `Addressable TV` is a targeting / delivery mechanism (household-level addressability). The format delivered addressable-style is `Standard Video`; the addressable signal belongs in Line Condition (`Addressable Households`, `Authenticated Streaming`).

Net effect: Ad Type again mixed format, property, and delivery axes, which was the same category error the initial audit corrected on the platform side.

### Correction

| Field | Before | After |
|---|---|---|
| Ad Type option | `Standard Video` | `Standard Video` (kept) |
| Ad Type option | `Connected TV` | removed (delivery channel; format is `Standard Video`) |
| Ad Type option | `Live Sports` | removed (content genre; signal moves to Base Offering / Line Condition) |
| Ad Type option | `Streaming Bundle` | removed (Base Offering value) |
| Ad Type option | `Addressable TV` | removed (targeting mechanism; signal moves to Line Condition) |
| Ad Type option | (new) | `Pause Ads` (6-Pager example) |
| Ad Type option | (new) | `BrightLine` (product-confirmed interactive CTV format) |

Final Ad Type dropdown reads `Standard Video | Pause Ads | BrightLine`. Placeholder text (`Select Ad Type`), the single-select control, and the surrounding form layout are unchanged, per the requesting brief.

### Caveat: taxonomy source is not wired

Per the PRD summary, Ad Product is supposed to be sourced from ICM (P0 dependency), and the field is supposed to be multi-select. Neither is wired in this prototype. The three-value list above is the largest set that can be cited from a document in the repo. Additional format values (Beacon Ads, Binge Ads, Companion Banner, etc.) exist in the wider Disney Advertising catalog but are not sourced in this codebase and were intentionally not added. Wiring ICM / BDS is out of scope for this change.

Separately, this correction does not close the pre-existing "Ad Type vs. Ad Product" naming drift documented in `docs/rate-card-manager-prd-audit.md` item E4 (PRD calls the field Ad Product, multi-select). The requesting brief explicitly kept the field as a single-select labelled Ad Type.

### Downstream consistency updates (same change)

- `v2.js` `createSeedFile()` line rotation now cycles the three valid Ad Type values.
- `fixtures/demo-cross-platform-rate-card.js` inventory patterns use only the three valid Ad Type values; sports pricing and premium-name selection retargeted from `adProduct === "Live Sports"` to `baseOffering === "Sports by ESPN"`.
- `fixtures/demo-rate-card-catalog.js` `inventoryFor()` returns only the three valid Ad Type values; `baseRateFor()` sports / CTV pricing floor keys on Base Offering (Sports by ESPN, Hulu) instead of Ad Type; `premiumTemplate()` sports pricing keys on Base Offering; the Dentsu Addressable card now uses `Standard Video` (the "Addressable" signal is carried by the Line Condition tag pool).
- `qa_v2.py` option-list, keyboard-navigation, and LINE-fill assertions updated to the three valid Ad Type values.
- `qa_demo_dataset.py` allowlist, sports-content coherence checks, "Live Sports Premium" attachment checks, Dentsu Ad Type summary, CSV import fixture, and cross-platform allowedOfferings map updated.
- `qa_no_nav.py` slide-3 example string updated to match the corrected presentation copy.
- `index.html` product-explainer modal ("Toyota is buying Standard Video inventory during Monday Night Football with addressable household targeting.") and the "RCM organizes pricing" example line ("Standard Video / Monday Night Football / $20 CPM") updated. All other presentation copy is unchanged.

### Not touched (explicitly out of scope)

- Legacy v1 arrays in `app.js` (`AD_TYPE_OPTIONS`, `AD_PRODUCT_OPTIONS`, `BASE_OFFERING_OPTIONS`, `MARKETPLACE_OPTIONS`) and rate card display names containing "ESPN Live Sports". Same rationale as the original audit: inactive v1 vocabulary, tracked separately.
- Rate card business names that contain the string "Addressable TV" (e.g. `Dentsu – Addressable TV Scatter 2025–2026`). The card still sells addressable-inventory deals; the name describes the commercial concept and is not an enum value.
- Line Condition tag pools that contain `Live Sports`, `Connected TV Devices`, `Addressable Households`, `Authenticated Streaming`. These are correctly modeled as content / targeting tags at the Line Condition axis and are unaffected by the Ad Type cleanup.
- Premium display names containing "Live Sports Premium" or "Weekend Sports Inventory Premium". These are business labels for pricing adjustments and are not Ad Type enum references.

### Verification

- Ad Type dropdown visually shows only `Standard Video`, `Pause Ads`, `BrightLine`.
- Load a seeded rate card and confirm every LINE row's Ad Type falls in the new allowlist.
- Load the Dentsu Addressable TV Scatter demo card and confirm all 48 LINE rows show Ad Type `Standard Video` while their Line Conditions still carry the addressable / authenticated-streaming targeting.
- Run `python3 qa_v2.py`, `python3 qa_demo_dataset.py`, `python3 qa_no_nav.py`, `python3 qa_rcle.py`, `python3 qa_regression.py`.

## Follow-up: 2026-08-26 sales-demo vocabulary and derived pricing

The demo dataset was rewritten to read as a real pricing book. The two
axes still mean what the 2026-08-04 correction says they mean, Ad Type is
the format and Base Offering is the platform or property, but both
vocabularies grew and the rate is now derived rather than authored.

| Axis | Active values |
|---|---|
| Ad Type | `Standard Video`, `Connected TV Video`, `Live Event Video`, `Sports Video`, `Pause Ad` |
| Base Offering | `Disney+ Select`, `Hulu Select`, `Disney Streaming Bundle`, `ESPN Streaming Sports`, `Disney Streaming Live Events`, plus `ABC`, `FX`, `Freeform`, `National Geographic` for the addressable book |
| Line Condition | One readable rule per row, written `Category: Dimension → Value` (see `RCMCatalog.conditions`) |

`Connected TV Video` and `Live Event Video` name formats, not delivery
channels or genres: they are the CTV-native and live-stream creative
specs, and the platform and property signals they used to carry still sit
in Base Offering. `Pause Ads` was singularized to `Pause Ad` and
`BrightLine` was retired, since no rule in the dataset prices it.

Every rate in the dataset is a function of its rule. `RCMCatalog` owns
one model, published as `RCMCatalog.expectedRate(offering, adType,
condition)`: an offering floor plus an Ad Type lift plus a Line Condition
lift, which lands on quarter-dollar increments by construction. Flat Rate
and Unit Price rows are quoted off the same CPM. The consequence worth
knowing before editing a fixture is that a rate is never typed, so two
rows differ in price only when they differ in rule.

Verified by `python3 qa_rate_card_records.py`, which walks every LINE and
PREM record in every card the app can build and fails on any record whose
fields do not form one believable pricing rule.

## Follow-up: 2026-08-26 who a card is allowed to price

A card's Buying Entity decides which advertisers its rows may carry, and
the catalog now enforces it. An agency entity (`WPP`, `Omnicom`, `IPG`,
`Dentsu` and the rest of `AGENCIES`) buys for many clients, so its book
prices the whole advertiser roster. A client entity, either on its own
(`Visa`) or named after the agency that buys for it (`Dentsu / Toyota`),
prices that client and nobody else. Before this, a card called
`Visa - Scatter 2025-2026` was filled with Ford and Coca-Cola rules,
which is the first thing a Sales user would have called out.

Two consequences for anyone editing the fixture:

1. Client cards need many distinct rules from one advertiser, so each
   card carries an inventory reserve (`inventoryReserve`) that stays
   inside its own subject: a live sports book widens into other sports
   and live inventory, never into an on-demand Hulu rule.
2. Every buying entity must be classifiable. A new entity that is
   neither in `AGENCIES` nor in `CLIENT_ADVERTISERS` fails the record
   audit rather than silently falling back to the full roster.

Client advertisers carry the same `ADV-####-##` identity format as the
roster and one ID per advertiser, so `Toyota Motor North America` is
`ADV-1183-01` everywhere it appears.
