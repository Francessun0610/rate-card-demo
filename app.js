// ============================================================================
// Rate Card Manager - vanilla JS app
// ============================================================================
// All inputs (search query, filter selections, pagination) are treated as
// untrusted DOM input and rendered via textContent / known constructors only.
// No innerHTML interpolation of user-controlled values. Icon SVGs below are
// hardcoded constants, never user input.
// ============================================================================

(function () {
  "use strict";

  /** @typedef {"Published"|"Draft"} Status */
  /* Marketplace enum (RCM PRD R2).
   *   v1.2 (canonical): Upfront | Scatter | Multi-Year - the only three
   *     values allowed by the Rate Card Manager PRD.
   *   v1.1 (legacy):    the historical seed also mixed in Addressable /
   *     Programmatic / Sponsorship / Sports / Streaming / Multiplatform,
   *     which the PRD flags as ad product / demand channel / inventory
   *     values that should NOT live on Marketplace. v1.2 remaps those
   *     legacy values via MARKETPLACE_V12_MAP (see the V1.2 PROJECTION
   *     LAYER block below). */
  /** @typedef {"Upfront"|"Scatter"|"Multi-Year"|"Addressable"|"Programmatic"|"Sponsorship"|"Sports"|"Streaming"|"Multiplatform"} Marketplace */
  /** @typedef {"WPP"|"Dentsu"|"P&G"|"DMED"|"IPG / L’Oréal"|"The Wonderful Co."|"Havas"|"Publicis"|"Omnicom"|"Microsoft"|"GroupM"} BuyingEntity */
  /** @typedef {"25-26"|"24-25"} Season */
  /** @typedef {{id:string,status:Status,saleshubId:string,rateCardId:string,name:string,marketplace:Marketplace,buyingEntity:BuyingEntity,lastUpdated:string,version:number}} RateCard */

  /* ===================================================================
   * normalizeStatus(raw) -> "Published" | "Draft"
   *
   * Single source of truth for converting ANY incoming status value
   * (seed data, localStorage, save/duplicate flow, future import path)
   * to one of the two PRD-aligned visible labels.
   *
   * PRD mapping (Rate Card Manager PRD §Status):
   *   - The UI Status column only renders "Published" or "Draft".
   *   - "Save and Publish" may map to ACTIVE internally, but the
   *     visible label MUST be Published.
   *
   * Mapping table:
   *   ACTIVE          / Active          / active          -> Published
   *   PUBLISHED       / Published       / published       -> Published
   *   DRAFT           / Draft           / draft           -> Draft
   *   Pending         / Pending Review                    -> Draft
   *     (pending == not yet approved -> safest to surface as a
   *      Draft the user still needs to act on)
   *   Archived                                            -> Published
   *     (no archive view exists in the prototype; per brief
   *      "convert archived mock rows to Published for now")
   *   anything else / unknown / null / "" / undefined     -> Draft
   *     (safe default; never silently surface an unsupported chip)
   *
   * Returns one of exactly two strings: "Published" or "Draft". */
  function normalizeStatus(raw) {
    if (raw == null) return "Draft";
    var s = String(raw).trim().toLowerCase();
    if (s === "") return "Draft";
    if (s === "active" || s === "published" || s === "archived") return "Published";
    if (s === "draft") return "Draft";
    /* Pending and Pending Review both map to Draft (not-yet-approved
     * work that the user still needs to finish). */
    if (s === "pending" || s === "pending review") return "Draft";
    return "Draft";
  }

  /* ===================================================================
   * setFieldError(errEl, msg)
   *
   * Single source of truth for how a .field__error row is rendered.
   * Replaces the old inline "err.textContent = 'Required'" pattern so
   * every required field paints the SAME 16x16 warning-circle SVG +
   * text row, avoiding the pre-2026-07-05 bug where the first field's
   * error looked visually different from the rest.
   *
   * We build the SVG via createElementNS + setAttribute (never via
   * innerHTML) so we don't have to trust `msg`. `msg` is applied with
   * .textContent so it can never break out to markup even if a future
   * caller passes user-controlled data.
   *
   * Contract:
   *   - Pass a non-empty string to render the icon + text and un-hide.
   *   - Pass "" / null / undefined to clear the DOM and re-hide.
   *
   * All layout (6px icon-to-text gap, vertically centered, 16px line
   * height, uniform 8px offset from input) lives in the .field__error
   * CSS block; this function only touches the DOM contents. */
  var FIELD_ERROR_ICON_PATH =
    "M8 1.333A6.667 6.667 0 1 0 8 14.667 6.667 6.667 0 0 0 8 1.333Zm0 " +
    "1.334a5.333 5.333 0 1 1 0 10.666A5.333 5.333 0 0 1 8 2.667Zm0 " +
    "2.5a.667.667 0 0 0-.667.666v3.334a.667.667 0 0 0 1.334 0V5.833A" +
    ".667.667 0 0 0 8 5.167Zm0 6.166a.833.833 0 1 0 0 1.667.833.833 " +
    "0 0 0 0-1.667Z";
  var fieldErrorIdCounter = 0;
  function setFieldError(errEl, msg) {
    if (!errEl) return;
    var field = errEl.closest(".field");
    var control = field && field.querySelector(
      ".field__input:not([type=\"hidden\"]), .edl-select__trigger, " +
      ".ads-datepicker__trigger, .ads-dd__trigger"
    );
    if (!errEl.id && control) {
      var customControl = field.querySelector("[data-field]");
      var errorKey = control.id
        || (customControl && customControl.getAttribute("data-field"))
        || ("field-" + (++fieldErrorIdCounter));
      var candidateId = errorKey + "-error";
      if (document.getElementById(candidateId)) {
        candidateId = errorKey + "-" + (++fieldErrorIdCounter) + "-error";
      }
      errEl.id = candidateId;
    }
    function syncErrorAssociation(invalid) {
      if (!control || !errEl.id) return;
      var ids = (control.getAttribute("aria-describedby") || "")
        .split(/\s+/)
        .filter(Boolean)
        .filter(function (id) { return id !== errEl.id; });
      if (invalid) ids.push(errEl.id);
      if (ids.length) control.setAttribute("aria-describedby", ids.join(" "));
      else control.removeAttribute("aria-describedby");
      if (invalid) control.setAttribute("aria-invalid", "true");
      else control.removeAttribute("aria-invalid");
    }
    // Empty string / null / undefined: clear and hide.
    if (msg == null || msg === "") {
      errEl.textContent = "";
      errEl.hidden = true;
      syncErrorAssociation(false);
      return;
    }
    // Build a fresh icon + text row. textContent clear first, then
    // append DOM nodes - never innerHTML - so `msg` cannot inject
    // markup even if a future caller passes untrusted input.
    errEl.textContent = "";
    var svgNS = "http://www.w3.org/2000/svg";
    var svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("class", "field__error-icon");
    svg.setAttribute("width", "16");
    svg.setAttribute("height", "16");
    svg.setAttribute("viewBox", "0 0 16 16");
    svg.setAttribute("fill", "none");
    svg.setAttribute("aria-hidden", "true");
    var path = document.createElementNS(svgNS, "path");
    path.setAttribute("d", FIELD_ERROR_ICON_PATH);
    path.setAttribute("fill", "currentColor");
    path.setAttribute("fill-rule", "evenodd");
    path.setAttribute("clip-rule", "evenodd");
    svg.appendChild(path);
    errEl.appendChild(svg);
    var span = document.createElement("span");
    span.className = "field__error-text";
    span.textContent = msg;
    errEl.appendChild(span);
    errEl.hidden = false;
    errEl.setAttribute("role", "alert");
    syncErrorAssociation(true);
  }
  window.setFieldError = setFieldError;

  /** @type {RateCard[]} */
  /* 100 demo Disney Advertising rate cards. Shape matches the Figma
   * 129:5515 column set: Status / SalesHub ID / Rate Card ID / Name /
   * Marketplace / Last Updated / Version.
   *
   * Naming conventions (2026-08-25 fixture realism pass):
   *   - Display name = "<Buying Entity> - <Scope> <Marketplace> <Season>",
   *     with an en dash as the separator and the scope segment present
   *     only when the card is genuinely scoped to that product or
   *     inventory. The trailing words "Rate Card" were dropped: the list
   *     column is already headed Rate Card Name, so repeating it cost
   *     scan width without adding meaning. Season reads 2025-2026 with an
   *     en dash so no name mixes 25-26, 25-26 and FY25 - FY26 styles.
   *     En dashes are fine here; em dashes are the banned character
   *     (DESIGN.md rule 8).
   *   - The scope segment is load bearing, not decoration. The catalog
   *     fixture derives each card's LINE inventory by matching the name
   *     against Disney+, Hulu, sports and streaming tokens, so a card
   *     that says Disney+ generates Disney+ lines. Changing a scope word
   *     changes the generated inventory with it.
   *   - Rate Card ID = "RC-DAS-<ENTITY>[-<SCOPE>]-<MKT>-<SEASON>"
   *     (uppercase ASCII, hyphens only). DAS is the owning team. The
   *     scope segment repeats the name's scope so the ID and the label
   *     always describe the same card, and it keeps IDs unique where one
   *     buying entity holds several books in a season.
   *   - Marketplace is PRD-compliant in the seed itself: only Upfront,
   *     Scatter and Multi-Year. Earlier seeds carried Addressable,
   *     Programmatic, Sponsorship, Streaming and Sports and relied on
   *     MARKETPLACE_V12_MAP to normalise them at read time, which left
   *     names advertising a marketplace the record did not have.
   *     The map is retained below only to migrate persisted rows.
   *   - Status mix: Published, Draft only (per PRD Status).
   *   - Season is stored per row in the PRD's YYYY-YYYY form rather than
   *     being parsed back out of the display name.
   *   - SalesHub ID = 18-char Salesforce-style mixed alphanumeric.
   *   - Version: integer 1-4. Most published rows are 1, revisions 2-4. */
  const RATE_CARDS = [
    // Page 1 (rows 1-10)
    { id: "1",   status: "Published",  saleshubId: "0016r000022wUkxAAE", rateCardId: "RC-DAS-DENTSU-ADDR-SC-2526",      name: "Dentsu - Addressable TV Scatter 2025-2026",         marketplace: "Scatter",     buyingEntity: "Dentsu",                     season: "2025-2026", lastUpdated: "Jul 31, 2026", version: 1 },
    { id: "2",   status: "Published",  saleshubId: "0013a00004Hc5w2AAB", rateCardId: "RC-DAS-WPP-VIDEO-UF-2627",        name: "WPP - Streaming Video Upfront 2026-2027",           marketplace: "Upfront",     buyingEntity: "WPP",                        season: "2026-2027", lastUpdated: "Jun 16, 2026", version: 2 },
    { id: "3",   status: "Published",  saleshubId: "0019J00002e59RdQAI", rateCardId: "RC-DAS-DISNEY-UF-2526",           name: "Disney Planning - Upfront 2025-2026",               marketplace: "Upfront",     buyingEntity: "Disney Planning",            season: "2025-2026", lastUpdated: "Jun 14, 2026", version: 1 },
    { id: "4",   status: "Draft",      saleshubId: "0018X00003j3fFuQAI", rateCardId: "RC-DAS-IPG-LOREAL-MY-2526",       name: "IPG - L\u2019Or\u00e9al Multi-Year 2025-2026",      marketplace: "Multi-Year",  buyingEntity: "IPG / L\u2019Or\u00e9al",    season: "2025-2026", lastUpdated: "Jun 12, 2026", version: 1 },
    { id: "5",   status: "Published",  saleshubId: "0013a000019gzATAAY", rateCardId: "RC-DAS-PG-DPLUS-UF-2526",         name: "P&G - Disney+ Upfront 2025-2026",                   marketplace: "Upfront",     buyingEntity: "P&G",                        season: "2025-2026", lastUpdated: "Jun 10, 2026", version: 1 },
    { id: "6",   status: "Draft",      saleshubId: "0018X00002EA8hjQAD", rateCardId: "RC-DAS-HAVAS-AUD-SC-2526",        name: "Havas - Audience Targeting Scatter 2025-2026",      marketplace: "Scatter",     buyingEntity: "Havas",                      season: "2025-2026", lastUpdated: "Jun 08, 2026", version: 2 },
    { id: "7",   status: "Published",  saleshubId: "0018X00000Rx62rQAB", rateCardId: "RC-DAS-GROUPM-DIRECT-MY-2526",    name: "GroupM - Client Direct Multi-Year 2025-2026",       marketplace: "Multi-Year",  buyingEntity: "GroupM",                     season: "2025-2026", lastUpdated: "Jun 05, 2026", version: 1 },
    { id: "8",   status: "Draft",      saleshubId: "0015f00000ehHK3AAM", rateCardId: "RC-DAS-OMNICOM-VIDEO-UF-2526",    name: "Omnicom - Streaming Video Upfront 2025-2026",       marketplace: "Upfront",     buyingEntity: "Omnicom",                    season: "2025-2026", lastUpdated: "Jun 03, 2026", version: 1 },
    { id: "9",   status: "Published",  saleshubId: "0010y00000k77EcAAI", rateCardId: "RC-DAS-MICROSOFT-ADDR-MY-2526",   name: "Microsoft - Addressable TV Multi-Year 2025-2026",   marketplace: "Multi-Year",  buyingEntity: "Microsoft",                  season: "2025-2026", lastUpdated: "Jun 01, 2026", version: 1 },
    { id: "10",  status: "Published",  saleshubId: "0018X00004zh5KGQAY", rateCardId: "RC-DAS-IPG-SPORTS-MY-2526",       name: "IPG - Live Sports Multi-Year 2025-2026",            marketplace: "Multi-Year",  buyingEntity: "IPG",                        season: "2025-2026", lastUpdated: "May 28, 2026", version: 1 },

    // Page 2 (rows 11-20)
    { id: "11",  status: "Published",  saleshubId: "0010y00003egb2PAAQ", rateCardId: "RC-DAS-DISNEY-HULU-UF-2526",      name: "Disney Planning - Hulu Upfront 2025-2026",          marketplace: "Upfront",     buyingEntity: "Disney Planning",            season: "2025-2026", lastUpdated: "May 25, 2026", version: 2 },
    { id: "12",  status: "Draft",      saleshubId: "0014k00004HQa6nAAD", rateCardId: "RC-DAS-PUBLICIS-VIDEO-UF-2526",   name: "Publicis - Streaming Video Upfront 2025-2026",      marketplace: "Upfront",     buyingEntity: "Publicis",                   season: "2025-2026", lastUpdated: "May 22, 2026", version: 1 },
    { id: "13",  status: "Published",  saleshubId: "0018X000045beZwQAI", rateCardId: "RC-DAS-HORIZON-DIRECT-SC-2526",   name: "Horizon - Client Direct Scatter 2025-2026",         marketplace: "Scatter",     buyingEntity: "Horizon",                    season: "2025-2026", lastUpdated: "May 18, 2026", version: 1 },
    { id: "14",  status: "Published",  saleshubId: "0011t00001YVcK4AAL", rateCardId: "RC-DAS-VERIZON-SPORTS-MY-2526",   name: "Verizon - Live Sports Multi-Year 2025-2026",        marketplace: "Multi-Year",  buyingEntity: "Verizon",                    season: "2025-2026", lastUpdated: "May 14, 2026", version: 1 },
    { id: "15",  status: "Published",  saleshubId: "0014k00003v59NeAAI", rateCardId: "RC-DAS-DENTSU-DPLUS-SC-2526",     name: "Dentsu - Disney+ Scatter 2025-2026",                marketplace: "Scatter",     buyingEntity: "Dentsu",                     season: "2025-2026", lastUpdated: "May 10, 2026", version: 3 },
    { id: "16",  status: "Draft",      saleshubId: "0018X000008mjEtQAI", rateCardId: "RC-DAS-WPP-HULU-UF-2526",         name: "WPP - Hulu Upfront 2025-2026",                      marketplace: "Upfront",     buyingEntity: "WPP",                        season: "2025-2026", lastUpdated: "May 05, 2026", version: 1 },
    { id: "17",  status: "Published",  saleshubId: "0019J00000iDK8UQAW", rateCardId: "RC-DAS-TARGET-DPLUS-SC-2526",     name: "Target - Disney+ Scatter 2025-2026",                marketplace: "Scatter",     buyingEntity: "Target",                     season: "2025-2026", lastUpdated: "Apr 30, 2026", version: 1 },
    { id: "18",  status: "Published",  saleshubId: "0018X00002T9GtaQAF", rateCardId: "RC-DAS-STATEFARM-ADDR-SC-2526",   name: "State Farm - Addressable TV Scatter 2025-2026",     marketplace: "Scatter",     buyingEntity: "State Farm",                 season: "2025-2026", lastUpdated: "Apr 26, 2026", version: 1 },
    { id: "19",  status: "Draft",      saleshubId: "0013a000037V8uqAAC", rateCardId: "RC-DAS-TOYOTA-SPORTS-MY-2526",    name: "Toyota - Live Sports Multi-Year 2025-2026",         marketplace: "Multi-Year",  buyingEntity: "Toyota",                     season: "2025-2026", lastUpdated: "Apr 22, 2026", version: 2 },
    { id: "20",  status: "Published",  saleshubId: "0019J00002u4NYqQAM", rateCardId: "RC-DAS-GROUPM-VIDEO-UF-2526",     name: "GroupM - Streaming Video Upfront 2025-2026",        marketplace: "Upfront",     buyingEntity: "GroupM",                     season: "2025-2026", lastUpdated: "Apr 18, 2026", version: 1 },

    // Page 3 (rows 21-30)
    { id: "21",  status: "Published",  saleshubId: "0013a00000n7LjxAAE", rateCardId: "RC-DAS-OMNICOM-DPLUS-UF-2526",    name: "Omnicom - Disney+ Upfront 2025-2026",               marketplace: "Upfront",     buyingEntity: "Omnicom",                    season: "2025-2026", lastUpdated: "Apr 15, 2026", version: 2 },
    { id: "22",  status: "Published",  saleshubId: "0010y00001M8nWgAAJ", rateCardId: "RC-DAS-PG-VIDEO-SC-2526",         name: "P&G - Streaming Video Scatter 2025-2026",           marketplace: "Scatter",     buyingEntity: "P&G",                        season: "2025-2026", lastUpdated: "Apr 12, 2026", version: 1 },
    { id: "23",  status: "Draft",      saleshubId: "0013a00004eD5QtAAK", rateCardId: "RC-DAS-MICROSOFT-SPORTS-MY-2526", name: "Microsoft - Live Sports Multi-Year 2025-2026",      marketplace: "Multi-Year",  buyingEntity: "Microsoft",                  season: "2025-2026", lastUpdated: "Apr 10, 2026", version: 1 },
    { id: "24",  status: "Published",  saleshubId: "0014k00003Vc2ryAAB", rateCardId: "RC-DAS-IPG-HULU-UF-2526",         name: "IPG - Hulu Upfront 2025-2026",                      marketplace: "Upfront",     buyingEntity: "IPG",                        season: "2025-2026", lastUpdated: "Apr 06, 2026", version: 1 },
    { id: "25",  status: "Published",  saleshubId: "0012n00000xH3Z4AAK", rateCardId: "RC-DAS-PUBLICIS-VIDEO-SC-2526",   name: "Publicis - Streaming Video Scatter 2025-2026",      marketplace: "Scatter",     buyingEntity: "Publicis",                   season: "2025-2026", lastUpdated: "Apr 02, 2026", version: 1 },
    { id: "26",  status: "Draft",      saleshubId: "0015f00003vMFF8AAO", rateCardId: "RC-DAS-HAVAS-DPLUS-UF-2526",      name: "Havas - Disney+ Upfront 2025-2026",                 marketplace: "Upfront",     buyingEntity: "Havas",                      season: "2025-2026", lastUpdated: "Mar 28, 2026", version: 2 },
    { id: "27",  status: "Published",  saleshubId: "0010y00003G7BWgAAN", rateCardId: "RC-DAS-DISNEY-SPORTS-UF-2526",    name: "Disney Planning - Live Sports Upfront 2025-2026",   marketplace: "Upfront",     buyingEntity: "Disney Planning",            season: "2025-2026", lastUpdated: "Mar 24, 2026", version: 1 },
    { id: "28",  status: "Published",  saleshubId: "0018X00003qC6cYQAS", rateCardId: "RC-DAS-WPP-DPLUS-SC-2526",        name: "WPP - Disney+ Scatter 2025-2026",                   marketplace: "Scatter",     buyingEntity: "WPP",                        season: "2025-2026", lastUpdated: "Mar 20, 2026", version: 1 },
    { id: "29",  status: "Draft",      saleshubId: "0014k000008QihSAAS", rateCardId: "RC-DAS-HORIZON-VIDEO-UF-2526",    name: "Horizon - Streaming Video Upfront 2025-2026",       marketplace: "Upfront",     buyingEntity: "Horizon",                    season: "2025-2026", lastUpdated: "Mar 16, 2026", version: 1 },
    { id: "30",  status: "Published",  saleshubId: "0017Q000008T3UtQAK", rateCardId: "RC-DAS-TARGET-HULU-UF-2526",      name: "Target - Hulu Upfront 2025-2026",                   marketplace: "Upfront",     buyingEntity: "Target",                     season: "2025-2026", lastUpdated: "Mar 12, 2026", version: 1 },

    // Page 4 (rows 31-40)
    { id: "31",  status: "Published",  saleshubId: "0019J00000V3avpQAB", rateCardId: "RC-DAS-DENTSU-VIDEO-SC-2425",     name: "Dentsu - Streaming Video Scatter 2024-2025",        marketplace: "Scatter",     buyingEntity: "Dentsu",                     season: "2024-2025", lastUpdated: "Mar 08, 2026", version: 3 },
    { id: "32",  status: "Published",  saleshubId: "0013a000007gL4HAAU", rateCardId: "RC-DAS-WPP-UF-2425",              name: "WPP - Upfront 2024-2025",                           marketplace: "Upfront",     buyingEntity: "WPP",                        season: "2024-2025", lastUpdated: "Mar 04, 2026", version: 3 },
    { id: "33",  status: "Published",  saleshubId: "0010y00001mz6NcAAI", rateCardId: "RC-DAS-DISNEY-UF-2425",           name: "Disney Planning - Upfront 2024-2025",               marketplace: "Upfront",     buyingEntity: "Disney Planning",            season: "2024-2025", lastUpdated: "Mar 01, 2026", version: 2 },
    { id: "34",  status: "Published",  saleshubId: "0016r00003E2uagAAB", rateCardId: "RC-DAS-IPG-LOREAL-UF-2425",       name: "IPG - L\u2019Or\u00e9al Upfront 2024-2025",         marketplace: "Upfront",     buyingEntity: "IPG / L\u2019Or\u00e9al",    season: "2024-2025", lastUpdated: "Feb 25, 2026", version: 2 },
    { id: "35",  status: "Published",  saleshubId: "0010y000004zfM5AAI", rateCardId: "RC-DAS-PG-DPLUS-UF-2425",         name: "P&G - Disney+ Upfront 2024-2025",                   marketplace: "Upfront",     buyingEntity: "P&G",                        season: "2024-2025", lastUpdated: "Feb 20, 2026", version: 2 },
    { id: "36",  status: "Published",  saleshubId: "0012n00001CH6hgAAD", rateCardId: "RC-DAS-HAVAS-AUD-SC-2425",        name: "Havas - Audience Targeting Scatter 2024-2025",      marketplace: "Scatter",     buyingEntity: "Havas",                      season: "2024-2025", lastUpdated: "Feb 16, 2026", version: 2 },
    { id: "37",  status: "Published",  saleshubId: "0012n000018iFpKAAU", rateCardId: "RC-DAS-GROUPM-DIRECT-MY-2425",    name: "GroupM - Client Direct Multi-Year 2024-2025",       marketplace: "Multi-Year",  buyingEntity: "GroupM",                     season: "2024-2025", lastUpdated: "Feb 12, 2026", version: 2 },
    { id: "38",  status: "Published",  saleshubId: "0011t000048YGbyAAG", rateCardId: "RC-DAS-OMNICOM-VIDEO-UF-2425",    name: "Omnicom - Streaming Video Upfront 2024-2025",       marketplace: "Upfront",     buyingEntity: "Omnicom",                    season: "2024-2025", lastUpdated: "Feb 08, 2026", version: 2 },
    { id: "39",  status: "Published",  saleshubId: "0014k000028FjSMAA0", rateCardId: "RC-DAS-MICROSOFT-ADDR-SC-2425",   name: "Microsoft - Addressable TV Scatter 2024-2025",      marketplace: "Scatter",     buyingEntity: "Microsoft",                  season: "2024-2025", lastUpdated: "Feb 04, 2026", version: 2 },
    { id: "40",  status: "Published",  saleshubId: "0019J00003qd3pEQAQ", rateCardId: "RC-DAS-IPG-SPORTS-MY-2425",       name: "IPG - Live Sports Multi-Year 2024-2025",            marketplace: "Multi-Year",  buyingEntity: "IPG",                        season: "2024-2025", lastUpdated: "Jan 30, 2026", version: 2 },

    // Page 5 (rows 41-50)
    { id: "41",  status: "Published",  saleshubId: "0010y00002JtLt4AAF", rateCardId: "RC-DAS-DENTSU-DPLUS-SC-2425",     name: "Dentsu - Disney+ Scatter 2024-2025",                marketplace: "Scatter",     buyingEntity: "Dentsu",                     season: "2024-2025", lastUpdated: "Jan 25, 2026", version: 2 },
    { id: "42",  status: "Draft",      saleshubId: "0012n00003WN2q3AAD", rateCardId: "RC-DAS-WPP-HULU-UF-2425",         name: "WPP - Hulu Upfront 2024-2025",                      marketplace: "Upfront",     buyingEntity: "WPP",                        season: "2024-2025", lastUpdated: "Jan 20, 2026", version: 1 },
    { id: "43",  status: "Published",  saleshubId: "0017Q00000DAwB4QAL", rateCardId: "RC-DAS-PUBLICIS-SPORTS-MY-2425",  name: "Publicis - Live Sports Multi-Year 2024-2025",       marketplace: "Multi-Year",  buyingEntity: "Publicis",                   season: "2024-2025", lastUpdated: "Jan 16, 2026", version: 2 },
    { id: "44",  status: "Published",  saleshubId: "0015f00001kW3FsAAK", rateCardId: "RC-DAS-HAVAS-HULU-SC-2425",       name: "Havas - Hulu Scatter 2024-2025",                    marketplace: "Scatter",     buyingEntity: "Havas",                      season: "2024-2025", lastUpdated: "Jan 12, 2026", version: 2 },
    { id: "45",  status: "Draft",      saleshubId: "0012n00001r2A7vAAE", rateCardId: "RC-DAS-PG-DIRECT-MY-2425",        name: "P&G - Client Direct Multi-Year 2024-2025",          marketplace: "Multi-Year",  buyingEntity: "P&G",                        season: "2024-2025", lastUpdated: "Jan 08, 2026", version: 1 },
    { id: "46",  status: "Published",  saleshubId: "0018X00001uvmY2QAI", rateCardId: "RC-DAS-OMNICOM-HULU-UF-2425",     name: "Omnicom - Hulu Upfront 2024-2025",                  marketplace: "Upfront",     buyingEntity: "Omnicom",                    season: "2024-2025", lastUpdated: "Jan 04, 2026", version: 2 },
    { id: "47",  status: "Published",  saleshubId: "0018X000046iyxAQAQ", rateCardId: "RC-DAS-GROUPM-DPLUS-UF-2425",     name: "GroupM - Disney+ Upfront 2024-2025",                marketplace: "Upfront",     buyingEntity: "GroupM",                     season: "2024-2025", lastUpdated: "Dec 28, 2025", version: 2 },
    { id: "48",  status: "Published",  saleshubId: "0016r00003J9z4aAAB", rateCardId: "RC-DAS-MICROSOFT-VIDEO-UF-2425",  name: "Microsoft - Streaming Video Upfront 2024-2025",     marketplace: "Upfront",     buyingEntity: "Microsoft",                  season: "2024-2025", lastUpdated: "Dec 22, 2025", version: 2 },
    { id: "49",  status: "Draft",      saleshubId: "0012n00004qg2PfAAI", rateCardId: "RC-DAS-DISNEY-SC-2425",           name: "Disney Planning - Scatter 2024-2025",               marketplace: "Scatter",     buyingEntity: "Disney Planning",            season: "2024-2025", lastUpdated: "Dec 18, 2025", version: 1 },
    { id: "50",  status: "Published",  saleshubId: "0012n00004AYx4AAAT", rateCardId: "RC-DAS-VERIZON-SPORTS-MY-2425",   name: "Verizon - Live Sports Multi-Year 2024-2025",        marketplace: "Multi-Year",  buyingEntity: "Verizon",                    season: "2024-2025", lastUpdated: "Dec 14, 2025", version: 2 },

    // Page 6 (rows 51-60): current-season holdco and direct-client books
    { id: "51",  status: "Draft",      saleshubId: "0012n000015zcVMAAY", rateCardId: "RC-DAS-PEPSICO-DPLUS-UF-2526",    name: "PepsiCo - Disney+ Upfront 2025-2026",               marketplace: "Upfront",     buyingEntity: "PepsiCo",                    season: "2025-2026", lastUpdated: "Jun 23, 2026", version: 1 },
    { id: "52",  status: "Published",  saleshubId: "0016r00001sHNE4AAO", rateCardId: "RC-DAS-WAVEMAKER-SPORTS-UF-2526", name: "Wavemaker - Live Sports Upfront 2025-2026",         marketplace: "Upfront",     buyingEntity: "Wavemaker",                  season: "2025-2026", lastUpdated: "Jun 21, 2026", version: 1 },
    { id: "53",  status: "Published",  saleshubId: "0017Q000012f6MpQAI", rateCardId: "RC-DAS-COCACOLA-BUNDLE-UF-2526",  name: "Coca-Cola - Streaming Bundle Upfront 2025-2026",    marketplace: "Upfront",     buyingEntity: "Coca-Cola",                  season: "2025-2026", lastUpdated: "Jun 19, 2026", version: 2 },
    { id: "54",  status: "Draft",      saleshubId: "0015f00004v9QsNAAU", rateCardId: "RC-DAS-MONDELEZ-HULU-SC-2526",    name: "Mondelez - Hulu Scatter 2025-2026",                 marketplace: "Scatter",     buyingEntity: "Mondelez",                   season: "2025-2026", lastUpdated: "Jun 17, 2026", version: 1 },
    { id: "55",  status: "Published",  saleshubId: "0014k000029H3WyAAK", rateCardId: "RC-DAS-ESSENCEMG-DPLUS-UF-2526",  name: "EssenceMediacom - Disney+ Upfront 2025-2026",       marketplace: "Upfront",     buyingEntity: "EssenceMediacom",            season: "2025-2026", lastUpdated: "Jun 15, 2026", version: 1 },
    { id: "56",  status: "Published",  saleshubId: "0017Q00000uBAy4QAG", rateCardId: "RC-DAS-TMOBILE-UF-2526",          name: "T-Mobile - Upfront 2025-2026",                      marketplace: "Upfront",     buyingEntity: "T-Mobile",                   season: "2025-2026", lastUpdated: "Jun 13, 2026", version: 1 },
    { id: "57",  status: "Draft",      saleshubId: "0017Q00003XFsg4QAD", rateCardId: "RC-DAS-MINDSHARE-AUD-SC-2526",    name: "Mindshare - Audience Targeting Scatter 2025-2026",  marketplace: "Scatter",     buyingEntity: "Mindshare",                  season: "2025-2026", lastUpdated: "Jun 11, 2026", version: 2 },
    { id: "58",  status: "Published",  saleshubId: "0019J000048vSgKQAU", rateCardId: "RC-DAS-CHASE-HULU-UF-2526",       name: "JPMorgan Chase - Hulu Upfront 2025-2026",           marketplace: "Upfront",     buyingEntity: "JPMorgan Chase",             season: "2025-2026", lastUpdated: "Jun 09, 2026", version: 1 },
    { id: "59",  status: "Published",  saleshubId: "0010y0000136bCKAAY", rateCardId: "RC-DAS-NIKE-SPORTS-MY-2526",      name: "Nike - Live Sports Multi-Year 2025-2026",           marketplace: "Multi-Year",  buyingEntity: "Nike",                       season: "2025-2026", lastUpdated: "Jun 07, 2026", version: 2 },
    { id: "60",  status: "Draft",      saleshubId: "0018X00001yWWP8QAO", rateCardId: "RC-DAS-INITIATIVE-BUNDLE-UF-2526", name: "Initiative - Streaming Bundle Upfront 2025-2026",   marketplace: "Upfront",     buyingEntity: "Initiative",                 season: "2025-2026", lastUpdated: "Jun 06, 2026", version: 1 },

    // Page 7 (rows 61-70): direct-client CPG, QSR and financial services
    { id: "61",  status: "Published",  saleshubId: "0013a00004eaSH2AAM", rateCardId: "RC-DAS-UNILEVER-DPLUS-UF-2526",   name: "Unilever - Disney+ Upfront 2025-2026",              marketplace: "Upfront",     buyingEntity: "Unilever",                   season: "2025-2026", lastUpdated: "Jun 04, 2026", version: 1 },
    { id: "62",  status: "Published",  saleshubId: "0018X00002c5gyBQAQ", rateCardId: "RC-DAS-CARAT-HULU-SC-2526",       name: "Carat - Hulu Scatter 2025-2026",                    marketplace: "Scatter",     buyingEntity: "Carat",                      season: "2025-2026", lastUpdated: "Jun 02, 2026", version: 1 },
    { id: "63",  status: "Published",  saleshubId: "0015f00001B2hBrAAJ", rateCardId: "RC-DAS-MCDONALDS-SPORTS-MY-2526", name: "McDonalds - Live Sports Multi-Year 2025-2026",      marketplace: "Multi-Year",  buyingEntity: "McDonalds",                  season: "2025-2026", lastUpdated: "May 30, 2026", version: 1 },
    { id: "64",  status: "Draft",      saleshubId: "0011t00000GJ8XyAAL", rateCardId: "RC-DAS-PHD-HULU-SC-2526",         name: "PHD - Hulu Scatter 2025-2026",                      marketplace: "Scatter",     buyingEntity: "PHD",                        season: "2025-2026", lastUpdated: "May 27, 2026", version: 1 },
    { id: "65",  status: "Published",  saleshubId: "0018X00003yFP57QAG", rateCardId: "RC-DAS-GM-SC-2526",               name: "General Motors - Scatter 2025-2026",                marketplace: "Scatter",     buyingEntity: "General Motors",             season: "2025-2026", lastUpdated: "May 23, 2026", version: 2 },
    { id: "66",  status: "Published",  saleshubId: "0011t00004uLp4AAAS", rateCardId: "RC-DAS-STAGWELL-AUD-SC-2526",     name: "Stagwell - Audience Targeting Scatter 2025-2026",   marketplace: "Scatter",     buyingEntity: "Stagwell",                   season: "2025-2026", lastUpdated: "May 20, 2026", version: 1 },
    { id: "67",  status: "Draft",      saleshubId: "0019J0000242nNZQAY", rateCardId: "RC-DAS-DIAGEO-BUNDLE-UF-2526",    name: "Diageo - Streaming Bundle Upfront 2025-2026",       marketplace: "Upfront",     buyingEntity: "Diageo",                     season: "2025-2026", lastUpdated: "May 16, 2026", version: 1 },
    { id: "68",  status: "Published",  saleshubId: "0014k00004qKug5AAC", rateCardId: "RC-DAS-ABINBEV-SPORTS-MY-2526",   name: "AB InBev - Live Sports Multi-Year 2025-2026",       marketplace: "Multi-Year",  buyingEntity: "AB InBev",                   season: "2025-2026", lastUpdated: "May 13, 2026", version: 1 },
    { id: "69",  status: "Published",  saleshubId: "0017Q000025xzeYQAQ", rateCardId: "RC-DAS-HEARTSSCI-DPLUS-UF-2526",  name: "Hearts & Science - Disney+ Upfront 2025-2026",      marketplace: "Upfront",     buyingEntity: "Hearts & Science",           season: "2025-2026", lastUpdated: "May 10, 2026", version: 2 },
    { id: "70",  status: "Published",  saleshubId: "0019J00000aYY9QQAW", rateCardId: "RC-DAS-CAPITALONE-HULU-UF-2526",  name: "Capital One - Hulu Upfront 2025-2026",              marketplace: "Upfront",     buyingEntity: "Capital One",                season: "2025-2026", lastUpdated: "May 07, 2026", version: 1 },

    // Page 8 (rows 71-80): multi-year renewals and international books
    { id: "71",  status: "Published",  saleshubId: "0019J00002ZLVc8QAH", rateCardId: "RC-DAS-OMD-DPLUS-MY-2528",        name: "OMD - Disney+ Multi-Year 2025-2028",                marketplace: "Multi-Year",  buyingEntity: "OMD",                        season: "2025-2028", lastUpdated: "May 04, 2026", version: 2 },
    { id: "72",  status: "Published",  saleshubId: "0016r00000eT7yJAAS", rateCardId: "RC-DAS-AMEX-UF-2526",             name: "American Express - Upfront 2025-2026",              marketplace: "Upfront",     buyingEntity: "American Express",           season: "2025-2026", lastUpdated: "May 01, 2026", version: 1 },
    { id: "73",  status: "Draft",      saleshubId: "0018X00004DqCm7QAF", rateCardId: "RC-DAS-WPP-LOREALUK-SC-2526",     name: "WPP - L\u2019Or\u00e9al UK Scatter 2025-2026",      marketplace: "Scatter",     buyingEntity: "WPP / L\u2019Or\u00e9al UK", season: "2025-2026", lastUpdated: "Apr 29, 2026", version: 1, currency: "GBP" },
    { id: "74",  status: "Published",  saleshubId: "0017Q00003if5wGQAQ", rateCardId: "RC-DAS-UM-SPORTS-UF-2526",        name: "UM - Live Sports Upfront 2025-2026",                marketplace: "Upfront",     buyingEntity: "UM",                         season: "2025-2026", lastUpdated: "Apr 26, 2026", version: 2 },
    { id: "75",  status: "Published",  saleshubId: "0014k000032ViQHAA0", rateCardId: "RC-DAS-FORD-DPLUS-UF-2526",       name: "Ford - Disney+ Upfront 2025-2026",                  marketplace: "Upfront",     buyingEntity: "Ford",                       season: "2025-2026", lastUpdated: "Apr 23, 2026", version: 1 },
    { id: "76",  status: "Draft",      saleshubId: "0015f000002kLTuAAM", rateCardId: "RC-DAS-IPROSPECT-AUD-SC-2526",    name: "iProspect - Audience Targeting Scatter 2025-2026",  marketplace: "Scatter",     buyingEntity: "iProspect",                  season: "2025-2026", lastUpdated: "Apr 20, 2026", version: 1 },
    { id: "77",  status: "Published",  saleshubId: "0015f00003zm8SdAAI", rateCardId: "RC-DAS-STATEFARM-SPORTS-MY-2526", name: "State Farm - Live Sports Multi-Year 2025-2026",     marketplace: "Multi-Year",  buyingEntity: "State Farm",                 season: "2025-2026", lastUpdated: "Apr 17, 2026", version: 2 },
    { id: "78",  status: "Published",  saleshubId: "0016r000017hvnPAAQ", rateCardId: "RC-DAS-AIRBNB-HULU-SC-2526",      name: "Airbnb - Hulu Scatter 2025-2026",                   marketplace: "Scatter",     buyingEntity: "Airbnb",                     season: "2025-2026", lastUpdated: "Apr 14, 2026", version: 1 },
    { id: "79",  status: "Draft",      saleshubId: "0011t000014zH9FAAU", rateCardId: "RC-DAS-PUBLICIS-PFIZER-UF-2526",  name: "Publicis - Pfizer Upfront 2025-2026",               marketplace: "Upfront",     buyingEntity: "Publicis / Pfizer",          season: "2025-2026", lastUpdated: "Apr 11, 2026", version: 1 },
    { id: "80",  status: "Published",  saleshubId: "0011t00003apS6sAAE", rateCardId: "RC-DAS-AMAZON-UF-2526",           name: "Amazon - Upfront 2025-2026",                        marketplace: "Upfront",     buyingEntity: "Amazon",                     season: "2025-2026", lastUpdated: "Apr 08, 2026", version: 1 },

    // Page 9 (rows 81-90): niche verticals and prior-season carryover
    { id: "81",  status: "Published",  saleshubId: "0014k00002dtuB9AAI", rateCardId: "RC-DAS-MARRIOTT-DPLUS-UF-2526",   name: "Marriott - Disney+ Upfront 2025-2026",              marketplace: "Upfront",     buyingEntity: "Marriott",                   season: "2025-2026", lastUpdated: "Apr 05, 2026", version: 1 },
    { id: "82",  status: "Published",  saleshubId: "0017Q000016w8ZEQAY", rateCardId: "RC-DAS-WPROMOTE-AUD-SC-2526",     name: "Wpromote - Audience Targeting Scatter 2025-2026",   marketplace: "Scatter",     buyingEntity: "Wpromote",                   season: "2025-2026", lastUpdated: "Apr 02, 2026", version: 1 },
    { id: "83",  status: "Published",  saleshubId: "0017Q00000uwHU3QAM", rateCardId: "RC-DAS-HORIZON-ADDR-SC-2526",     name: "Horizon - Addressable TV Scatter 2025-2026",        marketplace: "Scatter",     buyingEntity: "Horizon",                    season: "2025-2026", lastUpdated: "Mar 30, 2026", version: 2 },
    { id: "84",  status: "Published",  saleshubId: "0010y00003zpD2WAAU", rateCardId: "RC-DAS-ESSENCEMG-HULU-SC-2425",   name: "EssenceMediacom - Hulu Scatter 2024-2025",          marketplace: "Scatter",     buyingEntity: "EssenceMediacom",            season: "2024-2025", lastUpdated: "Mar 27, 2026", version: 3 },
    { id: "85",  status: "Published",  saleshubId: "0012n00001EhF6GAAV", rateCardId: "RC-DAS-SAMSUNG-UF-2526",          name: "Samsung - Upfront 2025-2026",                       marketplace: "Upfront",     buyingEntity: "Samsung",                    season: "2025-2026", lastUpdated: "Mar 24, 2026", version: 1 },
    { id: "86",  status: "Draft",      saleshubId: "0019J00003rs96SQAQ", rateCardId: "RC-DAS-CROSSMEDIA-DPLUS-SC-2526", name: "Crossmedia - Disney+ Scatter 2025-2026",            marketplace: "Scatter",     buyingEntity: "Crossmedia",                 season: "2025-2026", lastUpdated: "Mar 21, 2026", version: 1 },
    { id: "87",  status: "Published",  saleshubId: "0017Q00000e8AwYQAU", rateCardId: "RC-DAS-CARNIVAL-HULU-UF-2526",    name: "Carnival - Hulu Upfront 2025-2026",                 marketplace: "Upfront",     buyingEntity: "Carnival",                   season: "2025-2026", lastUpdated: "Mar 18, 2026", version: 1 },
    { id: "88",  status: "Published",  saleshubId: "0013a00002h9SNMAA2", rateCardId: "RC-DAS-DENTSU-TOYOTA-UF-2425",    name: "Dentsu - Toyota Upfront 2024-2025",                 marketplace: "Upfront",     buyingEntity: "Dentsu / Toyota",            season: "2024-2025", lastUpdated: "Mar 15, 2026", version: 2 },
    { id: "89",  status: "Published",  saleshubId: "0019J00001c6i3SQAQ", rateCardId: "RC-DAS-LULULEMON-SPORTS-MY-2526", name: "Lululemon - Live Sports Multi-Year 2025-2026",      marketplace: "Multi-Year",  buyingEntity: "Lululemon",                  season: "2025-2026", lastUpdated: "Mar 12, 2026", version: 1 },
    { id: "90",  status: "Published",  saleshubId: "0013a00002LsXs6AAF", rateCardId: "RC-DAS-VISA-SC-2526",             name: "Visa - Scatter 2025-2026",                          marketplace: "Scatter",     buyingEntity: "Visa",                       season: "2025-2026", lastUpdated: "Mar 09, 2026", version: 2 },

    // Page 10 (rows 91-100): multi-year renewals and mature seasons
    { id: "91",  status: "Published",  saleshubId: "0013a00001H9cQEAAZ", rateCardId: "RC-DAS-OMNICOM-DPLUS-MY-2528",    name: "Omnicom - Disney+ Multi-Year 2025-2028",            marketplace: "Multi-Year",  buyingEntity: "Omnicom",                    season: "2025-2028", lastUpdated: "Mar 06, 2026", version: 1 },
    { id: "92",  status: "Published",  saleshubId: "0018X000016F6rhQAC", rateCardId: "RC-DAS-PROGRESSIVE-HULU-UF-2526", name: "Progressive - Hulu Upfront 2025-2026",              marketplace: "Upfront",     buyingEntity: "Progressive",                season: "2025-2026", lastUpdated: "Mar 03, 2026", version: 1 },
    { id: "93",  status: "Draft",      saleshubId: "0019J000024By8CQAS", rateCardId: "RC-DAS-EXPEDIA-BUNDLE-UF-2526",   name: "Expedia - Streaming Bundle Upfront 2025-2026",      marketplace: "Upfront",     buyingEntity: "Expedia",                    season: "2025-2026", lastUpdated: "Feb 28, 2026", version: 1 },
    { id: "94",  status: "Published",  saleshubId: "0017Q0000088Jv6QAE", rateCardId: "RC-DAS-HORIZON-VIDEO-SC-2526",    name: "Horizon - Streaming Video Scatter 2025-2026",       marketplace: "Scatter",     buyingEntity: "Horizon",                    season: "2025-2026", lastUpdated: "Feb 23, 2026", version: 1 },
    { id: "95",  status: "Published",  saleshubId: "0017Q000039vPakQAE", rateCardId: "RC-DAS-WPP-PEPSI-UF-2324",        name: "WPP - Pepsi Upfront 2023-2024",                     marketplace: "Upfront",     buyingEntity: "WPP / Pepsi",                season: "2023-2024", lastUpdated: "Feb 18, 2026", version: 4 },
    { id: "96",  status: "Published",  saleshubId: "0012n000032jgbUAAQ", rateCardId: "RC-DAS-MICROSOFT-SPORTS-MY-2324", name: "Microsoft - Live Sports Multi-Year 2023-2024",      marketplace: "Multi-Year",  buyingEntity: "Microsoft",                  season: "2023-2024", lastUpdated: "Feb 14, 2026", version: 3 },
    { id: "97",  status: "Published",  saleshubId: "0011t00001i6JT7AAM", rateCardId: "RC-DAS-DENTSU-HONDA-UF-2324",     name: "Dentsu - Honda Upfront 2023-2024",                  marketplace: "Upfront",     buyingEntity: "Dentsu / Honda",             season: "2023-2024", lastUpdated: "Feb 10, 2026", version: 4 },
    { id: "98",  status: "Published",  saleshubId: "0017Q00002bXNu8QAG", rateCardId: "RC-DAS-GROUPM-ATT-UF-2324",       name: "GroupM - AT&T Upfront 2023-2024",                   marketplace: "Upfront",     buyingEntity: "GroupM / AT&T",              season: "2023-2024", lastUpdated: "Feb 05, 2026", version: 4 },
    { id: "99",  status: "Draft",      saleshubId: "0015f00000Pxu5GAAR", rateCardId: "RC-DAS-ASSEMBLY-DPLUS-SC-2526",   name: "Assembly - Disney+ Scatter 2025-2026",              marketplace: "Scatter",     buyingEntity: "Assembly",                   season: "2025-2026", lastUpdated: "Jan 31, 2026", version: 1 },
    { id: "100", status: "Published",  saleshubId: "0017Q00000DpFm6QAF", rateCardId: "RC-DAS-IPG-MCARD-SC-2526",        name: "IPG - Mastercard Scatter 2025-2026",                marketplace: "Scatter",     buyingEntity: "IPG / Mastercard",           season: "2025-2026", lastUpdated: "Jan 28, 2026", version: 2 },
  ];

  RATE_CARDS.forEach(function (row) {
    if (["Upfront", "Scatter", "Multi-Year"].indexOf(row.marketplace) >= 0) return;
    var context = (row.name + " " + row.rateCardId).toLowerCase();
    if (/multi.?year|\bmy\b/.test(context)) row.marketplace = "Multi-Year";
    else if (/scatter|-sc-/.test(context)) row.marketplace = "Scatter";
    else row.marketplace = "Upfront";
  });

  // ----- Season ---------------------------------------------------------------
  // The Rate Card Manager filter panel (Figma 123-3159) exposes Season as a
  // filterable dimension. Season used to be recovered by regex from a (YY-YY)
  // suffix in the display name, which made the name the storage format and
  // produced 25-26 filter values the PRD does not allow. Each row now carries
  // an explicit `season` in the PRD's YYYY-YYYY form; this pass only fills in
  // rows that arrive without one (persisted or user-created records).
  (function backfillSeasonField(){
    var full = /(20\d{2})\s*[-\u2013]\s*(20\d{2})/;
    var short = /\((\d{2})-(\d{2})\)/;
    for (var i = 0; i < RATE_CARDS.length; i++) {
      var row = RATE_CARDS[i];
      if (row.season) continue;
      var m = full.exec(row.name || "");
      if (m) { row.season = m[1] + "-" + m[2]; continue; }
      m = short.exec(row.name || "");
      row.season = m ? "20" + m[1] + "-20" + m[2] : "";
    }
  })();

  /* ===================================================================
   * V1.2 PROJECTION LAYER (2026-07-09 PM feedback)
   *
   * v1.2 renders a projected view of RATE_CARDS with three PM-authored
   * changes applied:
   *   1. Marketplace values are normalised to only Upfront / Scatter /
   *      Multi-Year. Values not in that set (Addressable, Programmatic,
   *      Streaming, Sponsorship, Sports, Multiyear) remap via
   *      MARKETPLACE_V12_MAP.
   *   2. The first 10 visible rows are overridden with PM's exact
   *      spec (rate card ID, name, marketplace, version, last updated,
   *      SalesHub ID, buying entity). These overrides make row 1 the
   *      most recently updated WPP upfront and re-align names that
   *      previously advertised an unsupported marketplace.
   *   3. The first 10 rows are sorted in PM's exact display order (WPP
   *      first, Dentsu second, ...).
   *
   * v1.1 never sees this projection. RATE_CARDS is left untouched;
   * mutations (delete, duplicate, save-new) target RATE_CARDS
   * directly and the projection is rebuilt fresh on the next read.
   * That keeps v1.1 rendering byte-identical while v1.2's list view
   * reflects PM's semantics.
   *
   * Trade-off (accepted for the prototype scope): opening Edit on a
   * PM-overridden row (ids 1-10) loads the underlying RATE_CARDS
   * data, not the projected values. If PM later wants Edit to match
   * the projection we can either (a) bake the overrides into
   * RATE_CARDS (which would leak into v1.1) or (b) hydrate the Edit
   * form from the projection when body[data-version="1.2"]. This
   * brief does not require it.
   * =================================================================== */
  var MARKETPLACE_V12_MAP = {
    Addressable:  "Multi-Year",
    Programmatic: "Scatter",
    Streaming:    "Upfront",
    Sponsorship:  "Multi-Year",
    Sports:       "Multi-Year",
    Multiyear:    "Multi-Year"
  };

  /* PM's first-10-row spec (2026-07-09 brief). Keys are RATE_CARDS row
   * ids so the projection can locate each row cheaply; values are only
   * the fields that genuinely differ from the seed.
   *
   * This table used to restate all seven fields for each of the ten
   * rows, because the seed carried marketplaces the PRD does not allow
   * and names built around them. The 2026-08-25 fixture pass fixed those
   * at the source, so every restated value except WPP's date bump had
   * become an exact copy of the row it was overriding, and a second
   * place to forget to update. Only the delta is kept. */
  var RATE_CARDS_V12_OVERRIDES = {
    "2": {
      /* Bumped to Jul 09 so WPP naturally becomes the most-recently
       * updated card in the visible list. */
      lastUpdated: "Jul 09, 2026", version: 3
    }
  };

  /* PM's exact top-of-list order. WPP (id=2) moves to position 1
   * because its bumped Jul 09 lastUpdated makes it the newest card in
   * the book. The remaining ids retain their v1.1 seed order. */
  var RATE_CARDS_V12_ORDER = ["2", "1", "3", "4", "5", "6", "7", "8", "9", "10"];

  /* Build a fresh v1.2 projection from an arbitrary source array. Called
   * on every read via activeRateCards() so mutations to RATE_CARDS
   * (delete, duplicate, save-new) surface in v1.2 on the next render
   * without the projection going stale. The projection is O(N) in the
   * source array size; N ~ 100 today so this is inexpensive. */
  function buildRateCardsV12(source) {
    /* Shallow-clone each row so PM overrides + marketplace remaps
     * don't leak back into RATE_CARDS. */
    var out = source.map(function(r){ return Object.assign({}, r); });
    /* Apply PM overrides FIRST so their explicit marketplace values
     * are honoured on the next line (rather than being remapped from
     * whatever the underlying row previously advertised). */
    out.forEach(function(r){
      var ov = RATE_CARDS_V12_OVERRIDES[r.id];
      if (ov) Object.assign(r, ov);
    });
    /* Marketplace normalisation across all rows (including any post-
     * override rows that still carry an unsupported value, e.g. rows
     * 11-100 that never enter the override map). */
    out.forEach(function(r){
      if (r.marketplace && MARKETPLACE_V12_MAP[r.marketplace]) {
        r.marketplace = MARKETPLACE_V12_MAP[r.marketplace];
      }
    });
    /* Season is carried on the row itself now, so there is nothing to
     * re-derive here: an override that changes a card's season sets the
     * field directly rather than hiding it inside the display name. */
    /* Reorder the first 10 rows to match PM's spec, keeping any
     * remaining rows in their original v1.1 order. `filter` is O(N)
     * and safe because RATE_CARDS_V12_ORDER only holds 10 ids. */
    var pmSet = new Set(RATE_CARDS_V12_ORDER);
    var byId = {};
    out.forEach(function(r){ byId[r.id] = r; });
    var firstTen = RATE_CARDS_V12_ORDER
      .map(function(id){ return byId[id]; })
      .filter(Boolean);
    var rest = out.filter(function(r){ return !pmSet.has(r.id); });
    /* A rate card the user just created outranks the seeded ten. The
     * pinned order is a presentation choice for demo rows; a row the
     * user made is the one they are looking for, so it stays visible on
     * page 1 instead of being pushed behind the fixtures. */
    var created = rest.filter(function(r){ return r.userSaved; });
    var seeded = rest.filter(function(r){ return !r.userSaved; });
    return created.concat(firstTen, seeded);
  }

  /* Old -> new Rate Card IDs from the 2026-08-25 fixture realism pass,
   * which moved every seeded card onto
   * RC-DAS-<ENTITY>[-<SCOPE>]-<MKT>-<SEASON>.
   *
   * Anyone who opened or edited a card before the rename has that file
   * persisted in localStorage under its old key, with the old id echoed
   * again inside card.id, every line's attachToCard, and the id of every
   * line and premium (they are prefixed with the card id). Without this
   * remap those files are orphaned: the list renders the new card while
   * Edit silently rebuilds a fresh fixture and the user's edits vanish.
   * Retire this table once no stored file can predate the rename. */
  var LEGACY_RATE_CARD_IDS = {
    /* Pre-dates the rename: this card was already migrated once, from the
     * 25-26 season to 26-27, so both historic keys land on today's id. */
    "RC-WPP-VIDEO-UF-2526": "RC-DAS-WPP-VIDEO-UF-2627",
    /* The cross-platform showcase card is created on demand rather than
     * seeded, so a stored copy under the old key would otherwise sit in
     * the list alongside the renamed one as a duplicate. */
    "RC-DEMO-CROSSPLATFORM-UF-2627": "RC-DAS-DISNEYADS-XPLAT-UF-2627",
    "RC-DENTSU-CTV-SC-2526": "RC-DAS-DENTSU-ADDR-SC-2526",
    "RC-WPP-VIDEO-UF-2627": "RC-DAS-WPP-VIDEO-UF-2627",
    "RC-DMED-PLANNING-UF-2526": "RC-DAS-DISNEY-UF-2526",
    "RC-IPG-LOREAL-UF-2526": "RC-DAS-IPG-LOREAL-MY-2526",
    "RC-PG-DPLUS-UF-2526": "RC-DAS-PG-DPLUS-UF-2526",
    "RC-HAVAS-PG-SC-2526": "RC-DAS-HAVAS-AUD-SC-2526",
    "RC-GROUPM-DIRECT-UF-2526": "RC-DAS-GROUPM-DIRECT-MY-2526",
    "RC-OMNICOM-STREAM-SC-2526": "RC-DAS-OMNICOM-VIDEO-UF-2526",
    "RC-MICROSOFT-DAR-UF-2526": "RC-DAS-MICROSOFT-ADDR-MY-2526",
    "RC-IPG-SPORTS-UF-2526": "RC-DAS-IPG-SPORTS-MY-2526",
    "RC-HULU-PACK-UF-2526": "RC-DAS-DISNEY-HULU-UF-2526",
    "RC-PUBLICIS-MULTIYEAR-MY-2526": "RC-DAS-PUBLICIS-VIDEO-UF-2526",
    "RC-HORIZON-PROG-UF-2526": "RC-DAS-HORIZON-DIRECT-SC-2526",
    "RC-VERIZON-SPORTS-UF-2526": "RC-DAS-VERIZON-SPORTS-MY-2526",
    "RC-DENTSU-DPLUS-UF-2526": "RC-DAS-DENTSU-DPLUS-SC-2526",
    "RC-WPP-HULU-UF-2526": "RC-DAS-WPP-HULU-UF-2526",
    "RC-TARGET-DPLUS-SC-2526": "RC-DAS-TARGET-DPLUS-SC-2526",
    "RC-STATEFARM-UF-2526": "RC-DAS-STATEFARM-ADDR-SC-2526",
    "RC-TOYOTA-SPORTS-UF-2526": "RC-DAS-TOYOTA-SPORTS-MY-2526",
    "RC-GROUPM-STREAM-SC-2526": "RC-DAS-GROUPM-VIDEO-UF-2526",
    "RC-OMNICOM-VIDEO-UF-2526": "RC-DAS-OMNICOM-DPLUS-UF-2526",
    "RC-PG-CTV-UF-2526": "RC-DAS-PG-VIDEO-SC-2526",
    "RC-MICROSOFT-SPORTS-UF-2526": "RC-DAS-MICROSOFT-SPORTS-MY-2526",
    "RC-IPG-HULU-UF-2526": "RC-DAS-IPG-HULU-UF-2526",
    "RC-PUBLICIS-CTV-SC-2526": "RC-DAS-PUBLICIS-VIDEO-SC-2526",
    "RC-HAVAS-DPLUS-UF-2526": "RC-DAS-HAVAS-DPLUS-UF-2526",
    "RC-DMED-SPORTS-UF-2526": "RC-DAS-DISNEY-SPORTS-UF-2526",
    "RC-WPP-DPLUS-UF-2526": "RC-DAS-WPP-DPLUS-SC-2526",
    "RC-HORIZON-STREAM-SC-2526": "RC-DAS-HORIZON-VIDEO-UF-2526",
    "RC-TARGET-HULU-UF-2526": "RC-DAS-TARGET-HULU-UF-2526",
    "RC-DENTSU-CTV-SC-2425": "RC-DAS-DENTSU-VIDEO-SC-2425",
    "RC-WPP-MULTIYEAR-UF-2425": "RC-DAS-WPP-UF-2425",
    "RC-DMED-PLANNING-UF-2425": "RC-DAS-DISNEY-UF-2425",
    "RC-IPG-LOREAL-UF-2425": "RC-DAS-IPG-LOREAL-UF-2425",
    "RC-PG-DPLUS-UF-2425": "RC-DAS-PG-DPLUS-UF-2425",
    "RC-HAVAS-PG-SC-2425": "RC-DAS-HAVAS-AUD-SC-2425",
    "RC-GROUPM-DIRECT-UF-2425": "RC-DAS-GROUPM-DIRECT-MY-2425",
    "RC-OMNICOM-STREAM-SC-2425": "RC-DAS-OMNICOM-VIDEO-UF-2425",
    "RC-MICROSOFT-DAR-UF-2425": "RC-DAS-MICROSOFT-ADDR-SC-2425",
    "RC-IPG-SPORTS-UF-2425": "RC-DAS-IPG-SPORTS-MY-2425",
    "RC-DENTSU-DPLUS-UF-2425": "RC-DAS-DENTSU-DPLUS-SC-2425",
    "RC-WPP-HULU-UF-2425": "RC-DAS-WPP-HULU-UF-2425",
    "RC-PUBLICIS-SPORTS-UF-2425": "RC-DAS-PUBLICIS-SPORTS-MY-2425",
    "RC-HAVAS-HULU-SC-2425": "RC-DAS-HAVAS-HULU-SC-2425",
    "RC-PG-DIRECT-UF-2425": "RC-DAS-PG-DIRECT-MY-2425",
    "RC-OMNICOM-STREAM-UF-2425": "RC-DAS-OMNICOM-HULU-UF-2425",
    "RC-GROUPM-DPLUS-UF-2425": "RC-DAS-GROUPM-DPLUS-UF-2425",
    "RC-MICROSOFT-VIDEO-UF-2425": "RC-DAS-MICROSOFT-VIDEO-UF-2425",
    "RC-DMED-REVIEW-SC-2425": "RC-DAS-DISNEY-SC-2425",
    "RC-VERIZON-LIVE-UF-2425": "RC-DAS-VERIZON-SPORTS-MY-2425",
    "RC-PEPSICO-DPLUS-UF-2526": "RC-DAS-PEPSICO-DPLUS-UF-2526",
    "RC-WAVEMAKER-ESPN-UF-2526": "RC-DAS-WAVEMAKER-SPORTS-UF-2526",
    "RC-COKE-BUNDLE-UF-2526": "RC-DAS-COCACOLA-BUNDLE-UF-2526",
    "RC-MONDELEZ-HULU-SC-2526": "RC-DAS-MONDELEZ-HULU-SC-2526",
    "RC-ESSENCEMG-DPLUS-UF-2526": "RC-DAS-ESSENCEMG-DPLUS-UF-2526",
    "RC-TMOBILE-PREM-UF-2526": "RC-DAS-TMOBILE-UF-2526",
    "RC-MINDSHARE-AUD-UF-2526": "RC-DAS-MINDSHARE-AUD-SC-2526",
    "RC-CHASE-HULU-UF-2526": "RC-DAS-CHASE-HULU-UF-2526",
    "RC-NIKE-LIVE-UF-2526": "RC-DAS-NIKE-SPORTS-MY-2526",
    "RC-INITIATIVE-BUNDLE-UF-2526": "RC-DAS-INITIATIVE-BUNDLE-UF-2526",
    "RC-UNILEVER-DPLUS-UF-2526": "RC-DAS-UNILEVER-DPLUS-UF-2526",
    "RC-CARAT-HULU-SC-2526": "RC-DAS-CARAT-HULU-SC-2526",
    "RC-MCDONALDS-ESPN-UF-2526": "RC-DAS-MCDONALDS-SPORTS-MY-2526",
    "RC-PHD-FX-UF-2526": "RC-DAS-PHD-HULU-SC-2526",
    "RC-GM-PREM-UF-2526": "RC-DAS-GM-SC-2526",
    "RC-STAGWELL-AUD-UF-2526": "RC-DAS-STAGWELL-AUD-SC-2526",
    "RC-DIAGEO-BUNDLE-UF-2526": "RC-DAS-DIAGEO-BUNDLE-UF-2526",
    "RC-ABINBEV-LIVE-UF-2526": "RC-DAS-ABINBEV-SPORTS-MY-2526",
    "RC-HEARTSANDSCIENCE-DPLUS-UF-2526": "RC-DAS-HEARTSSCI-DPLUS-UF-2526",
    "RC-CAPITALONE-HULU-UF-2526": "RC-DAS-CAPITALONE-HULU-UF-2526",
    "RC-OMD-DPLUS-MY-2528": "RC-DAS-OMD-DPLUS-MY-2528",
    "RC-AMEX-PREM-UF-2526": "RC-DAS-AMEX-UF-2526",
    "RC-WPP-LOREAL-UF-2526": "RC-DAS-WPP-LOREALUK-SC-2526",
    "RC-UM-ESPN-UF-2526": "RC-DAS-UM-SPORTS-UF-2526",
    "RC-FORD-DPLUS-UF-2526": "RC-DAS-FORD-DPLUS-UF-2526",
    "RC-IPROSPECT-AUD-UF-2526": "RC-DAS-IPROSPECT-AUD-SC-2526",
    "RC-STATEFARM-LIVE-UF-2526": "RC-DAS-STATEFARM-SPORTS-MY-2526",
    "RC-AIRBNB-HULU-UF-2526": "RC-DAS-AIRBNB-HULU-SC-2526",
    "RC-PUBLICIS-PFIZER-UF-2526": "RC-DAS-PUBLICIS-PFIZER-UF-2526",
    "RC-AMAZON-PREM-UF-2526": "RC-DAS-AMAZON-UF-2526",
    "RC-MARRIOTT-DPLUS-UF-2526": "RC-DAS-MARRIOTT-DPLUS-UF-2526",
    "RC-WPROMOTE-AUD-UF-2526": "RC-DAS-WPROMOTE-AUD-SC-2526",
    "RC-HORIZON-VISA-UF-2526": "RC-DAS-HORIZON-ADDR-SC-2526",
    "RC-ESSENCEMG-HULU-SC-2425": "RC-DAS-ESSENCEMG-HULU-SC-2425",
    "RC-SAMSUNG-PREM-UF-2526": "RC-DAS-SAMSUNG-UF-2526",
    "RC-CROSSMEDIA-DPLUS-SC-2526": "RC-DAS-CROSSMEDIA-DPLUS-SC-2526",
    "RC-CARNIVAL-HULU-UF-2526": "RC-DAS-CARNIVAL-HULU-UF-2526",
    "RC-DENTSU-TOYOTA-UF-2425": "RC-DAS-DENTSU-TOYOTA-UF-2425",
    "RC-LULULEMON-LIVE-UF-2526": "RC-DAS-LULULEMON-SPORTS-MY-2526",
    "RC-VISA-PREM-UF-2526": "RC-DAS-VISA-SC-2526",
    "RC-OMNICOM-DPLUS-MY-2528": "RC-DAS-OMNICOM-DPLUS-MY-2528",
    "RC-PROGRESSIVE-HULU-UF-2526": "RC-DAS-PROGRESSIVE-HULU-UF-2526",
    "RC-EXPEDIA-BUNDLE-UF-2526": "RC-DAS-EXPEDIA-BUNDLE-UF-2526",
    "RC-HORIZON-WENDYS-SC-2526": "RC-DAS-HORIZON-VIDEO-SC-2526",
    "RC-WPP-PEPSI-UF-2324": "RC-DAS-WPP-PEPSI-UF-2324",
    "RC-MICROSOFT-ESPN-UF-2324": "RC-DAS-MICROSOFT-SPORTS-MY-2324",
    "RC-DENTSU-HONDA-UF-2324": "RC-DAS-DENTSU-HONDA-UF-2324",
    "RC-GROUPM-ATT-UF-2324": "RC-DAS-GROUPM-ATT-UF-2324",
    "RC-ASSEMBLY-DPLUS-UF-2526": "RC-DAS-ASSEMBLY-DPLUS-SC-2526",
    "RC-IPG-MASTERCARD-UF-2526": "RC-DAS-IPG-MCARD-SC-2526",
  };

  /* Rewrites any id that still carries a retired card id as its prefix.
   * LINE and PREM ids are built as "<card id>-LINE-001", so renaming the
   * card orphans every child id until they are remapped too. */
  function migrateRateCardChildId(value) {
    var current = String(value == null ? "" : value);
    var legacyIds = Object.keys(LEGACY_RATE_CARD_IDS);
    for (var i = 0; i < legacyIds.length; i += 1) {
      if (current.indexOf(legacyIds[i]) !== 0) continue;
      return LEGACY_RATE_CARD_IDS[legacyIds[i]] + current.slice(legacyIds[i].length);
    }
    return current;
  }

  /* Rewrites one persisted rate card file onto its new id, including the
   * ids that embed the card id as a prefix. Returns true when it changed
   * something so the caller only writes back on a real migration. */
  function migrateStoredRateCardIds(storedFiles) {
    var changed = false;
    Object.keys(LEGACY_RATE_CARD_IDS).forEach(function (legacyId) {
      var nextId = LEGACY_RATE_CARD_IDS[legacyId];
      var file = storedFiles[legacyId];
      if (!file) return;
      delete storedFiles[legacyId];
      changed = true;
      /* A file already saved under the new id wins: it is the one the
       * user has been editing since the rename. */
      if (storedFiles[nextId]) return;
      if (file.card) file.card.id = nextId;
      (file.lines || []).forEach(function (line) {
        line.id = migrateRateCardChildId(line.id);
        line.attachToCard = nextId;
      });
      (file.premiums || []).forEach(function (premium) {
        premium.id = migrateRateCardChildId(premium.id);
        premium.attachToCard = nextId;
        if (Array.isArray(premium.lineItemIds)) {
          premium.lineItemIds = premium.lineItemIds.map(migrateRateCardChildId);
        }
      });
      storedFiles[nextId] = file;
    });
    return changed;
  }

  /* Quick Edit rows are keyed by list-row id, so the rename leaves the
   * store reachable, but each row still points at its LINE by the old
   * prefixed id. Saving then matches nothing and drops the edit without
   * an error, so remap the rows the same way as the files. */
  function migrateQuickEditLineIds(quickEditStore) {
    var changed = false;
    Object.keys(quickEditStore || {}).forEach(function (rowId) {
      var saved = quickEditStore[rowId];
      if (!saved || !Array.isArray(saved.lines)) return;
      saved.lines.forEach(function (line) {
        var migrated = migrateRateCardChildId(line.id);
        if (migrated === line.id) return;
        line.id = migrated;
        changed = true;
      });
    });
    return changed;
  }

  /* Active data-source accessor used by every list-view READ site
   * (getFilteredRows, uniqueValues, openDeleteModal, openQuickEdit).
   * v1.1 (and v1.0) return the underlying RATE_CARDS array so their
   * behavior is byte-identical to the pre-v1.2 world. v1.2 returns a
   * fresh projection built on demand.
   *
   * Mutation sites (delete splice, duplicate/save unshift) intentionally
   * stay pointed at RATE_CARDS. This means:
   *   - A row deleted in v1.2 disappears from the RATE_CARDS array,
   *     so the next v1.2 render also excludes it.
   *   - A row created via "Save and create new" appears in the next
   *     v1.2 projection with normalised marketplace and no PM overlay
   *     (since it's a new id > 100).
   * That's the intended behavior. */
  function isModernAppVersion(value) {
    return value === "1.2" || isV2Family(value);
  }

  var ARCHIVED_STORAGE_KEY = "rate-card-manager.archived.v1";

  function readArchivedIds() {
    try {
      var parsed = JSON.parse(window.localStorage.getItem(ARCHIVED_STORAGE_KEY) || "[]");
      return Array.isArray(parsed) ? parsed.map(String) : [];
    } catch (_) {
      return [];
    }
  }

  function writeArchivedIds(ids) {
    try {
      window.localStorage.setItem(ARCHIVED_STORAGE_KEY, JSON.stringify(Array.from(new Set(ids))));
      return true;
    } catch (_) {
      return false;
    }
  }

  function activeRateCards() {
    var v = (typeof document !== "undefined" && document.body)
      ? document.body.getAttribute("data-version") : null;
    var source = RATE_CARDS;
    var demo = window.RCMDemoRateCard;
    var demoRecord = demo && typeof demo.getListRecord === "function"
      ? demo.getListRecord()
      : null;
    if (demoRecord && !source.some(function (row) { return row.id === demoRecord.id; })) {
      source = [demoRecord].concat(source);
    }
    var projected = isModernAppVersion(v) ? buildRateCardsV12(source) : source;
    if (isModernAppVersion(v)) {
      try {
        var storedFiles = JSON.parse(
          window.localStorage.getItem("rate-card-manager.v2.files") || "{}"
        );
        if (migrateStoredRateCardIds(storedFiles)) {
          window.localStorage.setItem(
            "rate-card-manager.v2.files",
            JSON.stringify(storedFiles)
          );
        }
        var dentsuAddressableId = "RC-DAS-DENTSU-ADDR-SC-2526";
        var dentsuRecord = projected.find(function (row) {
          return row.rateCardId === dentsuAddressableId;
        });
        var dentsuFixture = dentsuRecord && window.RCMCatalog
          && typeof window.RCMCatalog.buildFile === "function"
          ? window.RCMCatalog.buildFile(dentsuRecord)
          : null;
        var storedDentsu = storedFiles[dentsuAddressableId];
        var containsLinearTv = storedDentsu
          && JSON.stringify(storedDentsu).toLowerCase().indexOf("linear tv") >= 0;
        if (dentsuFixture && (!storedDentsu
          || storedDentsu.fixtureKey !== dentsuFixture.fixtureKey
          || containsLinearTv)) {
          storedFiles[dentsuAddressableId] = dentsuFixture;
          window.localStorage.setItem(
            "rate-card-manager.v2.files",
            JSON.stringify(storedFiles)
          );
        }
        var crossPlatformFixture = demoRecord && demo
          && typeof demo.getFile === "function"
          ? demo.getFile(demoRecord.rateCardId)
          : null;
        var storedCrossPlatform = crossPlatformFixture
          && storedFiles[crossPlatformFixture.card.id];
        if (crossPlatformFixture && storedCrossPlatform
            && storedCrossPlatform.syntheticDemoData === true
            && storedCrossPlatform.fixtureKey !== crossPlatformFixture.fixtureKey) {
          storedFiles[crossPlatformFixture.card.id] = crossPlatformFixture;
          window.localStorage.setItem(
            "rate-card-manager.v2.files",
            JSON.stringify(storedFiles)
          );
        }
        /* A synthetic demo file stored under an older fixture key holds
         * advertisers, offerings and rates the current catalog no
         * longer publishes, so a browser that visited before the data
         * pass would keep showing the old book. Any stored file that is
         * still flagged synthetic and carries a stale key is refreshed
         * from the catalog, the same way the Dentsu card above is. A
         * file the user saved keeps the current key, so nothing they
         * edited is thrown away. The cross-platform demo card is built
         * by its own fixture and refreshed above, so the catalog must
         * not claim it here. */
        var conditionFixturesChanged = false;
        var crossPlatformId = crossPlatformFixture && crossPlatformFixture.card.id;
        projected.forEach(function (record) {
          if (!window.RCMCatalog || typeof window.RCMCatalog.buildFile !== "function") return;
          if (record.rateCardId === crossPlatformId) return;
          var expected = window.RCMCatalog.buildFile(record);
          var stored = expected && storedFiles[record.rateCardId];
          if (!stored || stored.syntheticDemoData !== true
              || stored.fixtureKey === expected.fixtureKey) return;
          storedFiles[record.rateCardId] = expected;
          conditionFixturesChanged = true;
        });
        if (conditionFixturesChanged) {
          window.localStorage.setItem(
            "rate-card-manager.v2.files",
            JSON.stringify(storedFiles)
          );
        }
        var quickEditStore = JSON.parse(
          window.localStorage.getItem("rate-card-manager.quick-edit.v1") || "{}"
        );
        var quickEditIdsMigrated = migrateQuickEditLineIds(quickEditStore);
        if (quickEditStore.__lineConditionFixtureVersion !== 3) {
          /* Rows saved before the data pass name advertisers the roster
           * no longer carries. Those entries are dropped so the current
           * seed rebuilds them; the rest only need their rules refreshed. */
          var currentAdvertisers = window.RCMCatalog && window.RCMCatalog.advertisers
            ? window.RCMCatalog.advertisers.map(function (item) { return item.name; })
            : [];
          Object.keys(quickEditStore).forEach(function (key) {
            var saved = quickEditStore[key];
            if (!saved || !Array.isArray(saved.lines) || !currentAdvertisers.length) return;
            var retired = saved.lines.some(function (line) {
              return line.advertiser && currentAdvertisers.indexOf(line.advertiser) < 0;
            });
            if (retired) delete quickEditStore[key];
          });
          projected.forEach(function (record) {
            var saved = quickEditStore[record.id];
            if (!saved || !Array.isArray(saved.lines) || !window.RCMCatalog
                || typeof window.RCMCatalog.buildFile !== "function") return;
            var expected = window.RCMCatalog.buildFile(record);
            var expectedById = {};
            (expected.lines || []).forEach(function (line) {
              expectedById[line.id] = line.condition1;
            });
            saved.lines.forEach(function (line, index) {
              var replacement = expectedById[line.id];
              if (replacement == null && expected.lines[index]) {
                replacement = expected.lines[index].condition1;
              }
              if (replacement != null) line.lineConditions = replacement;
            });
          });
          quickEditStore.__lineConditionFixtureVersion = 3;
          quickEditIdsMigrated = true;
        }
        if (quickEditIdsMigrated) {
          window.localStorage.setItem(
            "rate-card-manager.quick-edit.v1",
            JSON.stringify(quickEditStore)
          );
        }
        Object.keys(storedFiles || {}).forEach(function (cardId) {
          var file = storedFiles[cardId];
          var card = file && file.card;
          if (!card || projected.some(function (row) {
            return row.rateCardId === card.id;
          })) return;
          var childDates = (file.lines || []).map(function (line) {
            return line.updatedAt;
          }).filter(Boolean);
          projected.unshift({
            id: "stored:" + card.id,
            status: normalizeStatus(file.status || "Draft"),
            saleshubId: card.buyingEntityId || "Not set",
            rateCardId: card.id,
            name: card.name,
            marketplace: card.marketplace,
            buyingEntity: card.buyingEntityName || "Not set",
            lastUpdated: childDates.sort().pop() || new Date().toISOString(),
            version: file.version || 1,
            season: card.dealSeason || ""
          });
        });
      } catch (_) {}
    }
    var archived = new Set(readArchivedIds());
    return projected.filter(function (row) { return !archived.has(String(row.id)); });
  }

  try {
    Object.defineProperty(window, "RCMRateCards", {
      value: Object.freeze({
        getAll: function () {
          return activeRateCards().map(function (row) { return Object.assign({}, row); });
        },
        getByRateCardId: function (cardId) {
          var row = activeRateCards().find(function (candidate) {
            return candidate.rateCardId === cardId;
          });
          return row ? Object.assign({}, row) : null;
        }
      }),
      writable: false,
      enumerable: false,
      configurable: false
    });
  } catch (_) {}

  /* Test affordance: expose the live mock store on window so QA scripts
   * can read RATE_CARDS via the DevTools Runtime.evaluate channel. The
   * reference is non-enumerable + read-only at the property level so it
   * doesn't accidentally leak into product code paths that iterate
   * window keys. The array itself stays mutable (commitFormToTable
   * still unshifts new rows into it). */
  try {
    Object.defineProperty(window, "RATE_CARDS", {
      value: RATE_CARDS,
      writable: false,
      enumerable: false,
      configurable: false
    });
  } catch (e) { /* property may already exist if app re-inits */ }

  /* Read-only browser QA hooks for refreshing and persisting the local
   * prototype data without exposing mutable controller state. */
  function __rcmExposeImportHooks() {
    try {
      if (!Object.getOwnPropertyDescriptor(window, "__rcmRenderTable")) {
        Object.defineProperty(window, "__rcmRenderTable", {
          value: function () { try { renderTable(); } catch (_) {} },
          writable: false, enumerable: false, configurable: false
        });
      }
    } catch (_) {}
    try {
      if (!Object.getOwnPropertyDescriptor(window, "__rcmPersistRows")) {
        Object.defineProperty(window, "__rcmPersistRows", {
          value: function () { try { persistSavedRowsToStorage(); } catch (_) {} },
          writable: false, enumerable: false, configurable: false
        });
      }
    } catch (_) {}
  }
  /* Defer until DOM ready - persistSavedRowsToStorage / renderTable
   * are defined later in this file but hoisted (function declarations);
   * still, scheduling on DOMContentLoaded is the safe path. */
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", __rcmExposeImportHooks);
  } else {
    __rcmExposeImportHooks();
  }

  /* =================== LINE CONDITION NORMALIZATION ======================
   *
   * Per Adam's 2026-07-09 product update the four separate Line Condition
   * fields (Line condition 1..4) have been consolidated into a single
   * free-form field named "Line conditions" that accepts multiple
   * comma-separated values (e.g. "A18-49, Preemptible"). This helper is
   * the single normalizer used everywhere the value crosses a save /
   * blur boundary (Quick Edit blur, LINE form blur, save-to-storage
   * writes, legacy-shape migrations). It:
   *   1. trims leading/trailing whitespace on the whole string,
   *   2. splits on ",", trims each fragment,
   *   3. drops empty fragments (so "A,,B" collapses to "A | B"),
   *   4. dedupes preserving first-seen order,
   *   5. joins with " | ", the canonical separator between two complete
   *      rules, which reads unambiguously when a rule's own text
   *      contains a comma.
   * The result is a plain string, not an array; the UI keeps a single
   * text input as the source of truth for both entry and display. */
  /* "No additional targeting" is how the rate model states that a LINE
   * has no condition, not a condition a seller chose. A LINE carries at
   * most one optional condition, so every surface shows the same thing
   * for "none": an em dash in the table, an empty field in Quick Edit,
   * and None in Line Details. Fixtures already store it as an empty
   * field; this catches rate cards saved before that rule. */
  var NO_LINE_CONDITION = "No additional targeting";

  /* Deal Season is stored as YYYY-YYYY (PRD R4). This banner used to
   * expand a two-digit "25-26" into "2025-2026", which turned a
   * four-digit season into "2020-206-2027", so the expansion now only
   * runs on the legacy shape it was written for and a full season is
   * printed as it is stored. */
  function quickEditSeasonLabel(season) {
    var value = String(season == null ? "" : season).trim();
    if (!value) return "Not set";
    if (/^\d{4}-\d{4}$/.test(value)) return value;
    if (/^\d{2}-\d{2}$/.test(value)) {
      return "20" + value.slice(0, 2) + "-20" + value.slice(3);
    }
    return value;
  }

  function quickEditConditionValue(value) {
    var label = String(value == null ? "" : value).trim();
    return label === NO_LINE_CONDITION ? "" : label;
  }

  function normalizeLineConditions(input) {
    if (input == null) return "";
    var parts = String(input).split(/\s*\|\s*|,/);
    var seen = Object.create(null);
    var out = [];
    for (var i = 0; i < parts.length; i += 1) {
      var v = parts[i].trim();
      if (!v) continue;
      if (seen[v]) continue;
      seen[v] = true;
      out.push(v);
    }
    /* Comma joined, which is what a record already stores and what the
     * shared condition control reads and writes. Quick Edit used to
     * canonicalize to " | ", so the same two conditions were saved in
     * one shape from the panel and another from the sheet. Both spellings
     * still parse, above. */
    return out.join(", ");
  }

  /* Migration helper: pre-consolidation records stored line conditions in
   * four discrete keys (lineCondition1..4 for LINE form persistence,
   * lc1..lc4 for Quick Edit rows). This collapses either legacy shape
   * into a single normalized string. Non-empty legacy values are
   * preserved in slot order; duplicates are dropped by the normalizer. */
  function coalesceLegacyLineConditions(record, keys) {
    if (!record) return "";
    var raw = [];
    for (var i = 0; i < keys.length; i += 1) {
      var v = record[keys[i]];
      if (v != null && String(v).trim() !== "") raw.push(String(v));
    }
    return normalizeLineConditions(raw.join(", "));
  }

  /* =================== QUICK EDIT DATA + PERSISTENCE =====================
   *
   * Quick Edit is a per-rate-card editable bottom sheet. Each rate card
   * owns a set of "line" rows that represent the negotiated rate variations
   * (advertiser x demo x ad product). The user can edit Base Rate
   * (4-decimal currency) and a single free-form Line Conditions field
   * that accepts multiple comma-separated values (e.g. "A18-49,
   * Preemptible"). Line conditions consolidate the pre-2026-07-09
   * lc1..lc4 quad; see normalizeLineConditions() above.
   *
   * Persistence:
   *   We use localStorage as the source of truth for edited values, keyed
   *   by rate card id. On first open of a given rate card we seed lines
   *   from the in-memory default seed (which for the IPG / L'Oréal rate
   *   card uses the exact 9 demo rows the brief specified, and for every
   *   other rate card synthesizes a small default
   *   set so Quick Edit works universally). On Save we write the dirty
   *   set back. On subsequent opens (and after a hard refresh) we read
   *   from localStorage first.
   *
   *   Storage key: "rate-card-manager.quick-edit.v1"
   *   Storage shape: { [rateCardId]: { lines: [...], updatedAt: ISOdate } }
   *
   *   The shared store is read once on boot into QUICK_EDIT_STORE so the
   *   open path is a synchronous in-memory lookup. We re-hydrate from
   *   localStorage on every getQuickEditLines() call so multi-tab edits
   *   remain consistent.
   * ===================================================================== */

  var QUICK_EDIT_STORAGE_KEY = "rate-card-manager.quick-edit.v1";

  /* Nine golden Quick Edit rows for the IPG / L'Oréal beauty book (list
   * row id 4).
   *
   * Every row used to read "QUINCY BIOSCIENCE, LLC" against a "DXP" base
   * offering. The advertiser was lifted from an early screenshot and
   * repeated nine times, and DXP is not a value ICM offers, so Quick
   * Edit displayed a Base Offering the dropdown cannot select. The rows
   * now price the card's own advertiser against real ICM offerings, and
   * vary format, offering and rule so the book reads as nine negotiated
   * rows rather than one row pasted nine times. Rates follow the same
   * bands the catalog fixture prices in. */
  var QUICK_EDIT_SEED_IPG_LOREAL = [
    { id: "ln-1", advertiser: "L\u2019Or\u00e9al USA", baseRate: "32.0000", costMethod: "CPM", baseOffering: "Hulu Select",             adProduct: "Standard Video",     lineConditions: "" },
    { id: "ln-2", advertiser: "L\u2019Or\u00e9al USA", baseRate: "35.7500", costMethod: "CPM", baseOffering: "Hulu Select",             adProduct: "Standard Video",     lineConditions: "DAR Demo: F18-49" },
    { id: "ln-3", advertiser: "L\u2019Or\u00e9al USA", baseRate: "34.2500", costMethod: "CPM", baseOffering: "Hulu Select",             adProduct: "Standard Video",     lineConditions: "DAR Demo: A18-49" },
    { id: "ln-4", advertiser: "L\u2019Or\u00e9al USA", baseRate: "34.0000", costMethod: "CPM", baseOffering: "Disney+ Select",          adProduct: "Standard Video",     lineConditions: "" },
    { id: "ln-5", advertiser: "L\u2019Or\u00e9al USA", baseRate: "37.7500", costMethod: "CPM", baseOffering: "Disney+ Select",          adProduct: "Standard Video",     lineConditions: "DAR Demo: F18-49" },
    { id: "ln-6", advertiser: "L\u2019Or\u00e9al USA", baseRate: "38.5000", costMethod: "CPM", baseOffering: "Disney+ Select",          adProduct: "Pause Ad",           lineConditions: "Format: Sponsorship Product" },
    { id: "ln-7", advertiser: "L\u2019Or\u00e9al USA", baseRate: "39.0000", costMethod: "CPM", baseOffering: "Disney+ Select",          adProduct: "Connected TV Video", lineConditions: "Format: Premier Product" },
    { id: "ln-8", advertiser: "L\u2019Or\u00e9al USA", baseRate: "40.7500", costMethod: "CPM", baseOffering: "Disney Streaming Bundle", adProduct: "Standard Video",     lineConditions: "DAR Demo: F18-49" },
    { id: "ln-9", advertiser: "L\u2019Or\u00e9al USA", baseRate: "40.0000", costMethod: "CPM", baseOffering: "Disney Streaming Bundle", adProduct: "Standard Video",     lineConditions: "Targeting: Shortform Video Line" },
  ];

  /* Contextual line-condition palette for the seeded Rate Cards, keyed
   * by RATE_CARDS.id. Values come from Adam's 2026-07-09 guidance:
   * conditions must reflect the rate card's marketplace, buying entity,
   * and ad product. Row 0/1/2 map to the three default seed rows, whose
   * rates rise with the rule they carry. Each value is one readable
   * business rule, matching the Line Condition vocabulary in
   * fixtures/demo-rate-card-catalog.js. An empty string renders as an
   * em dash in read-only views. */
  var LINE_CONDITIONS_BY_CARD_ID = {
    "1":  ["Targeting: Livestreaming Line", "DAR Demo: A25-54", "Format: Premier Product"],
    "2":  ["Targeting: Longform Video Line", "DAR Demo: A18-49", "DAR Demo: F35-64"],
    "3":  ["Targeting: Longform Video Line", "", "DAR Demo: A25-54"],
    "5":  ["DAR Demo: A18-49", "Format: Premier Product", "DAR Demo: F35-64"],
    "6":  ["DAR Demo: A18-49", "Targeting: Livestreaming Line", "Format: Preemptible"],
    "7":  ["Targeting: Longform Video Line", "Format: Sponsorship Product", "Targeting: Livestreaming Line"],
    "8":  ["Format: Premier Product", "DAR Demo: A18-49", "DAR Demo: A25-54"],
    "9":  ["DAR Demo: M18-34", "Targeting: Livestreaming Line", "Format: Premier Product"],
    "10": ["Targeting: NFL", "Targeting: Football", "Targeting: NBA"],
  };

  /* Marketplace + card-name based fallback for the remaining seeded
   * cards (ids 11+). Keeps every card credible without cloning the
   * hand-crafted set above. Some rows intentionally return "" so a
   * subset of seeded rows renders the empty-value placeholder.
   *
   * The trailing branches used to test for Addressable, Programmatic,
   * Sponsorship, Streaming and Sports. Those are not marketplaces the
   * PRD allows and no longer appear on any record, so they were dead
   * code that only made the real three harder to find. The inventory
   * branches above them match the scope segment of the current names
   * (Live Sports, Disney+, Hulu, Streaming Video, Streaming Bundle). */
  function fallbackLineConditionsFor(card) {
    var mkt = (card && card.marketplace) || "";
    var nm  = ((card && card.name) || "").toLowerCase();
    var A1849 = "DAR Demo: A18-49";
    var A2554 = "DAR Demo: A25-54";
    if (/live sports|espn/.test(nm))               return ["Targeting: NFL", "Targeting: Football", ""];
    if (/disney planning/.test(nm))                return ["", "Targeting: Longform Video Line", ""];
    if (/disney\+/.test(nm))                       return [A1849, "Format: Premier Product", A2554];
    if (/hulu|streaming/.test(nm))                 return [A1849, "Format: Preemptible", ""];
    if (/addressable/.test(nm))                    return ["Format: Premier Product", "Targeting: Livestreaming Line", ""];
    if (/audience targeting/.test(nm))             return [A1849, "DAR Demo: F35-64", ""];
    if (mkt === "Upfront")                         return [A1849, A2554, "Targeting: Longform Video Line"];
    if (mkt === "Scatter")                         return [A1849, A2554, ""];
    if (mkt === "Multi-Year")                      return [A1849, A2554, ""];
    return [A1849, A2554, ""];
  }

  function pickLineConditionsForCard(card) {
    if (card && card.id && LINE_CONDITIONS_BY_CARD_ID[card.id]) {
      return LINE_CONDITIONS_BY_CARD_ID[card.id].slice();
    }
    return fallbackLineConditionsFor(card);
  }

  /* Advertisers used by cards without a hand-authored Quick Edit seed.
   * A LINE row carries the advertiser being priced, not the holdco that
   * negotiated the card, so building the name from buyingEntity used to
   * render rows like "OMNICOM, LLC": a buying entity shouted in caps
   * with a suffix bolted on, and the same string on all three rows.
   * These are the advertisers the catalog fixture already prices, so
   * Quick Edit and the Line Items table name the same book. */
  var QUICK_EDIT_DEFAULT_ADVERTISERS = [
    "Ford Motor Company", "Capital One", "The Coca-Cola Company",
    "Target", "L\u2019Or\u00e9al USA", "United Airlines",
    "Johnson & Johnson", "Verizon", "Samsung Electronics America",
    "Procter & Gamble"
  ];

  /* Base Offering has to be a value ICM actually publishes, and it has to
   * agree with the scope the card's name advertises: a card called
   * "Carat - Hulu Scatter 2025-2026" must not seed Disney+ rows. */
  function defaultBaseOfferingFor(card) {
    var nm = ((card && card.name) || "").toLowerCase();
    if (/live sports|espn/.test(nm)) return "ESPN Streaming Sports";
    if (/hulu/.test(nm)) return "Hulu Select";
    if (/disney\+/.test(nm)) return "Disney+ Select";
    if (/bundle/.test(nm)) return "Disney Streaming Bundle";
    return "Disney+ Select";
  }

  /* Synthesize a small default seed for any rate card without a hand-
   * authored set. Advertisers are picked by row id so a card shows the
   * same three rows on every reload rather than re-rolling per render. */
  function buildDefaultLineSeed(card) {
    var offset = Math.abs(parseInt((card && card.id) || "0", 10) || 0);
    var pick = function (step) {
      return QUICK_EDIT_DEFAULT_ADVERTISERS[
        (offset + step) % QUICK_EDIT_DEFAULT_ADVERTISERS.length
      ];
    };
    var offering = defaultBaseOfferingFor(card);
    var conds = pickLineConditionsForCard(card);
    /* Rates sit in the same band the catalog fixture prices the
     * offering in, so a Quick Edit row and a Line Items row for the
     * same offering never disagree by ten dollars. */
    var floor = offering === "ESPN Streaming Sports" ? 44
      : offering === "Disney Streaming Bundle" ? 37
      : offering === "Hulu Select" ? 32 : 34;
    var rate = function (lift) { return (floor + lift).toFixed(4); };
    return [
      { id: "ln-1", advertiser: pick(0), baseRate: rate(0),    costMethod: "CPM", baseOffering: offering, adProduct: "Standard Video", lineConditions: conds[0] || "" },
      { id: "ln-2", advertiser: pick(1), baseRate: rate(2.25), costMethod: "CPM", baseOffering: offering, adProduct: "Standard Video", lineConditions: conds[1] || "" },
      { id: "ln-3", advertiser: pick(2), baseRate: rate(3.5),  costMethod: "CPM", baseOffering: offering, adProduct: "Standard Video", lineConditions: conds[2] || "" },
    ];
  }

  function getSeedLinesFor(card) {
    /* The brief's nine-row example maps to the IPG / L'Oréal book, list
     * row id 4. */
    if (card.id === "4") return QUICK_EDIT_SEED_IPG_LOREAL.map(function(r){ return Object.assign({}, r); });
    return buildDefaultLineSeed(card);
  }

  function readQuickEditStore() {
    try {
      var raw = window.localStorage.getItem(QUICK_EDIT_STORAGE_KEY);
      if (!raw) return {};
      var parsed = JSON.parse(raw);
      return (parsed && typeof parsed === "object") ? parsed : {};
    } catch (e) {
      /* Quota / parse / disabled storage all collapse to empty store.
       * Quick Edit still works in-memory for the session. */
      return {};
    }
  }

  function writeQuickEditStore(store) {
    try {
      window.localStorage.setItem(QUICK_EDIT_STORAGE_KEY, JSON.stringify(store));
      return true;
    } catch (e) {
      return false;
    }
  }

  /* Migrate a single legacy row (pre-2026-07-09 shape with lc1..lc4
   * discrete keys) into the consolidated { lineConditions } shape used
   * everywhere downstream. Idempotent: rows that already carry
   * lineConditions are returned unchanged (aside from the lc* keys
   * being stripped so stale data can't reappear via a diff). */
  function migrateQuickEditRow(row) {
    if (!row || typeof row !== "object") return row;
    if (typeof row.lineConditions === "string") {
      /* Already migrated; drop any residual legacy keys defensively so
       * dirty-diff never compares against them. */
      if ("lc1" in row || "lc2" in row || "lc3" in row || "lc4" in row) {
        var next = Object.assign({}, row);
        delete next.lc1; delete next.lc2; delete next.lc3; delete next.lc4;
        return next;
      }
      return row;
    }
    var merged = coalesceLegacyLineConditions(row, ["lc1", "lc2", "lc3", "lc4"]);
    var out = Object.assign({}, row);
    delete out.lc1; delete out.lc2; delete out.lc3; delete out.lc4;
    out.lineConditions = merged;
    return out;
  }

  /* Public-ish read: return the persisted lines for a card id if present,
   * else seed from defaults. Always returns a fresh array of fresh
   * objects so the caller can mutate freely without trashing the store.
   * Legacy lc1..lc4 storage shape is migrated on the fly so users with
   * pre-consolidation localStorage payloads keep their edits. */
  function getQuickEditLines(card) {
    var demo = window.RCMDemoRateCard;
    var demoFile = demo && typeof demo.getFile === "function"
      ? demo.getFile(card.rateCardId)
      : null;
    if (demoFile && Array.isArray(demoFile.lines)) {
      return demoFile.lines.map(function (line) {
        return {
          id: line.id,
          advertiser: line.advertiserName,
          baseRate: Number(line.baseRate).toFixed(4),
          costMethod: line.rateType,
          baseOffering: line.baseOffering,
          adProduct: line.adProduct,
          lineConditions: line.condition1 || ""
        };
      });
    }
    var store = readQuickEditStore();
    var saved = store[card.id];
    if (saved && Array.isArray(saved.lines)) {
      return saved.lines.map(function(r){ return migrateQuickEditRow(Object.assign({}, r)); });
    }
    var catalog = window.RCMCatalog;
    var catalogFile = catalog && typeof catalog.buildFile === "function"
      ? catalog.buildFile(card)
      : null;
    if (catalogFile && Array.isArray(catalogFile.lines)) {
      return catalogFile.lines.map(function (line) {
        return {
          id: line.id,
          advertiser: line.advertiserName,
          baseRate: Number(line.baseRate).toFixed(4),
          costMethod: line.rateType,
          baseOffering: line.baseOffering,
          adProduct: line.adProduct,
          lineConditions: line.condition1 || ""
        };
      });
    }
    return getSeedLinesFor(card);
  }

  /* Public-ish write: persist a card's lines + return the saved snapshot. */
  function saveQuickEditLines(cardId, lines) {
    var card = activeRateCards().find(function (candidate) {
      return String(candidate.id) === String(cardId);
    });
    if (!card) return null;
    try {
      var fileStore = JSON.parse(
        window.localStorage.getItem("rate-card-manager.v2.files") || "{}"
      );
      var demo = window.RCMDemoRateCard;
      var file = fileStore[card.rateCardId]
        || (demo && typeof demo.getFile === "function" && demo.getFile(card.rateCardId))
        || (window.RCMCatalog && typeof window.RCMCatalog.buildFile === "function"
          ? window.RCMCatalog.buildFile(card)
          : null);
      if (!file || !Array.isArray(file.lines)) return null;
      lines.forEach(function (quickLine) {
        var target = file.lines.find(function (line) { return line.id === quickLine.id; });
        if (!target) return;
        target.baseRate = Number(quickLine.baseRate);
        target.condition1 = quickLine.lineConditions || "";
        target.updatedAt = new Date().toISOString();
      });
      file.updatedAt = new Date().toISOString();
      fileStore[card.rateCardId] = file;
      window.localStorage.setItem("rate-card-manager.v2.files", JSON.stringify(fileStore));
    } catch (_) {
      return null;
    }
    var store = readQuickEditStore();
    store[cardId] = {
      lines: lines.map(function(r){ return Object.assign({}, r); }),
      updatedAt: new Date().toISOString(),
    };
    if (!writeQuickEditStore(store)) return null;
    return store[cardId];
  }

  // ----- App state ----------------------------------------------------------

  /* The one place the Rate Card Manager decides what a status is called.
   * normalizeStatus() above folds every stored spelling (active,
   * archived, pending) into these two, the table chips read from here,
   * and the filter drawer builds its checkboxes from here, so a label
   * cannot drift between the row and the control that filters it.
   *
   * Only Draft and Published exist. Archive is an action that takes a
   * row out of the list (see activeRateCards), not a state a row can be
   * seen in, so there is nothing for an "Archived" filter to match. */
  const RCM_STATUSES = Object.freeze([
    Object.freeze({ value: "Draft",     label: "Draft" }),
    Object.freeze({ value: "Published", label: "Published" })
  ]);

  /* Shown exactly as stored: YYYY-YYYY. An en dash was prettier but it
   * is a different string from the value the record carries, and the
   * normalized hyphenated form is what the PRD specifies. */
  function formatSeason(value) {
    return String(value == null ? "" : value);
  }

  /* A buying entity is a name plus a Saleshub ID, not just a name: a few
   * entities own more than one ID, and the ID is what a row is matched
   * on. No ID belongs to two entities, so the ID alone identifies one. */
  function entityLabel(name, saleshubId) {
    return String(name || "Not set") + " - " + String(saleshubId || "");
  }

  // Two-tier filter state per the Figma 123-3159 panel:
  //   appliedFilters: what the table is actually filtered by RIGHT NOW.
  //                   Only updated by Apply / a chip removal / Clear all.
  //   draftFilters:   what the user is currently composing in the open
  //                   panel. Reverts to appliedFilters when the panel
  //                   re-opens or Cancel is clicked.
  //
  // status, marketplace and season each hold an ARRAY of selected values.
  // Empty means "any", and several values OR together, while the four
  // dimensions AND with each other. buyingEntityId holds a single
  // Saleshub ID, because the autocomplete resolves a typed name or ID
  // down to exactly one entity and the ID is what a row is matched on.
  const DEFAULT_FILTERS = Object.freeze({
    status: [],
    marketplace: [],
    buyingEntityId: "",
    season: [],
  });
  const MULTI_FILTER_KEYS = ["marketplace", "season", "status"];

  function emptyFilters() {
    return { status: [], marketplace: [], buyingEntityId: "", season: [] };
  }
  function cloneFilters(source) {
    return {
      status: (source.status || []).slice(),
      marketplace: (source.marketplace || []).slice(),
      buyingEntityId: source.buyingEntityId || "",
      season: (source.season || []).slice(),
    };
  }
  let appliedFilters = emptyFilters();
  let draftFilters   = emptyFilters();
  let query = "";
  let page = 1;
  let pageSize = 10;

  /* Sorting state. Three-state click cycle per ADS Table sort pattern:
   *   none -> asc -> desc -> none (returns to dataset insertion order).
   * Only one column may be active at a time. The sort step lives between
   * filters and pagination in the render pipeline, so sorting always
   * applies to the currently filtered + searched result set. */
  /** @type {{ key: SortKey, dir: SortDir } | null} */
  let sortState = null;
  /* Row selection, keyed by rate card id so it survives sorting,
   * filtering, searching, pagination, and re-renders. Never keyed by
   * visible row index.
   *
   * 1.x and 2.0 keep single-row selection: selectRateCardRow() replaces
   * the whole set, so the set never holds more than one id there. 2.1
   * toggles instead, which is what its contextual action bar needs.
   * @type {Set<string>} */
  const selectedRateCardIds = new Set();
  /* Set only while Redline Mode is inspecting the Action Bar specimen.
   * It stands in for the selection size so the bar can be shown at
   * counts no page of real rows could produce, and it is the flag the
   * bar's press handler checks before it will touch a real record.
   * null means the product is running normally.
   * @type {number|null} */
  let selectionSpecimenCount = null;
  /** @typedef {"status"|"saleshubId"|"rateCardId"|"name"|"marketplace"|"lastUpdated"|"version"} SortKey */
  /** @typedef {"asc"|"desc"} SortDir */
  /* Rows the delete modal is currently confirming: one in 1.x and 2.0,
   * one or more when the 2.1 action bar opens it over a selection.
   * @type {string[]} */
  let pendingDeleteIds = [];

  /* Quick Edit session state. Lives only while the bottom sheet is open;
   * persisted state lives in localStorage (see QUICK_EDIT_STORAGE_KEY).
   *   cardId    - id of the rate card currently being edited
   *   original  - snapshot of the lines as loaded (used to compute dirty)
   *   draft     - mutable working copy bound to the inputs
   *   prevFocus - element to restore focus to when the sheet closes
   */
  /** @type {{ cardId: string, original: any[], draft: any[], prevFocus: Element|null } | null} */
  let quickEditState = null;

  // ----- Inline SVG icons. EDL 18px outline at 1.6 stroke, Indigo/70.
  // Hand-tuned to match the Figma row-action icon set (pencil-in-box, download
  // tray with horizontal bar at bottom, trash can with two vertical strokes).
  // Constants below are hardcoded and never include user input.
  // Action icons. Exported from Figma node 65-1604 (Feather icon set).
  // Filled-style 16×16 with currentColor fill so they inherit Indigo/70.
  const ICON_EDIT =
    '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">' +
    '<path fill-rule="evenodd" clip-rule="evenodd" d="M1.25245 2.58579C1.62753 2.21071 2.13623 2 2.66667 2H7.33333C7.70152 2 8 2.29848 8 2.66667C8 3.03486 7.70152 3.33333 7.33333 3.33333H2.66667C2.48986 3.33333 2.32029 3.40357 2.19526 3.5286C2.07024 3.65362 2 3.82319 2 4V13.3333C2 13.5101 2.07024 13.6797 2.19526 13.8047C2.32029 13.9298 2.48986 14 2.66667 14H12C12.1768 14 12.3464 13.9298 12.4714 13.8047C12.5964 13.6797 12.6667 13.5101 12.6667 13.3333V8.66667C12.6667 8.29848 12.9651 8 13.3333 8C13.7015 8 14 8.29848 14 8.66667V13.3333C14 13.8638 13.7893 14.3725 13.4142 14.7475C13.0391 15.1226 12.5304 15.3333 12 15.3333H2.66667C2.13623 15.3333 1.62753 15.1226 1.25245 14.7475C0.87738 14.3725 0.666667 13.8638 0.666667 13.3333V4C0.666667 3.46957 0.87738 2.96086 1.25245 2.58579Z" fill="currentColor"/>' +
    '<path fill-rule="evenodd" clip-rule="evenodd" d="M13.3333 1.91912C13.1351 1.91912 12.9449 1.99788 12.8047 2.13807L6.60198 8.34083L6.24958 9.75042L7.65917 9.39802L13.8619 3.19526C14.0021 3.05507 14.0809 2.86493 14.0809 2.66667C14.0809 2.46841 14.0021 2.27826 13.8619 2.13807C13.7217 1.99788 13.5316 1.91912 13.3333 1.91912ZM11.8619 1.19526C12.2522 0.805021 12.7815 0.585786 13.3333 0.585786C13.8852 0.585786 14.4145 0.805021 14.8047 1.19526C15.195 1.5855 15.4142 2.11478 15.4142 2.66667C15.4142 3.21855 15.195 3.74783 14.8047 4.13807L8.4714 10.4714C8.38597 10.5568 8.27891 10.6175 8.16169 10.6468L5.49502 11.3134C5.26784 11.3702 5.02752 11.3037 4.86193 11.1381C4.69634 10.9725 4.62978 10.7322 4.68657 10.505L5.35324 7.83831C5.38254 7.72109 5.44316 7.61404 5.5286 7.5286L11.8619 1.19526Z" fill="currentColor"/>' +
    '</svg>';
  const ICON_DOWNLOAD =
    '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">' +
    '<path fill-rule="evenodd" clip-rule="evenodd" d="M8 1.33333C8.36819 1.33333 8.66667 1.63181 8.66667 2V8.39052L10.8619 6.19526C11.1223 5.93491 11.5444 5.93491 11.8047 6.19526C12.0651 6.45561 12.0651 6.87772 11.8047 7.13807L8.4714 10.4714C8.21105 10.7318 7.78894 10.7318 7.5286 10.4714L4.19526 7.13807C3.93491 6.87772 3.93491 6.45561 4.19526 6.19526C4.45561 5.93491 4.87772 5.93491 5.13807 6.19526L7.33333 8.39052V2C7.33333 1.63181 7.63181 1.33333 8 1.33333ZM2 9.33333C2.36819 9.33333 2.66667 9.63181 2.66667 10V12.6667C2.66667 12.8435 2.7369 13.013 2.86193 13.1381C2.98695 13.2631 3.15652 13.3333 3.33333 13.3333H12.6667C12.8435 13.3333 13.013 13.2631 13.1381 13.1381C13.2631 13.013 13.3333 12.8435 13.3333 12.6667V10C13.3333 9.63181 13.6318 9.33333 14 9.33333C14.3682 9.33333 14.6667 9.63181 14.6667 10V12.6667C14.6667 13.1971 14.456 13.7058 14.0809 14.0809C13.7058 14.456 13.1971 14.6667 12.6667 14.6667H3.33333C2.8029 14.6667 2.29419 14.456 1.91912 14.0809C1.54405 13.7058 1.33333 13.1971 1.33333 12.6667V10C1.33333 9.63181 1.63181 9.33333 2 9.33333Z" fill="currentColor"/>' +
    '</svg>';
  const ICON_TRASH =
    '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">' +
    '<path fill-rule="evenodd" clip-rule="evenodd" d="M1.33333 4C1.33333 3.63181 1.63181 3.33333 2 3.33333H14C14.3682 3.33333 14.6667 3.63181 14.6667 4C14.6667 4.36819 14.3682 4.66667 14 4.66667H2C1.63181 4.66667 1.33333 4.36819 1.33333 4Z" fill="currentColor"/>' +
    '<path fill-rule="evenodd" clip-rule="evenodd" d="M6.66667 2C6.48986 2 6.32029 2.07024 6.19526 2.19526C6.07024 2.32029 6 2.48986 6 2.66667V3.33333H10V2.66667C10 2.48986 9.92976 2.32029 9.80474 2.19526C9.67971 2.07024 9.51014 2 9.33333 2H6.66667ZM11.3333 3.33333V2.66667C11.3333 2.13623 11.1226 1.62753 10.7475 1.25245C10.3725 0.87738 9.86377 0.666667 9.33333 0.666667H6.66667C6.13623 0.666667 5.62753 0.87738 5.25245 1.25245C4.87738 1.62753 4.66667 2.13623 4.66667 2.66667V3.33333H3.33333C2.96514 3.33333 2.66667 3.63181 2.66667 4V13.3333C2.66667 13.8638 2.87738 14.3725 3.25245 14.7475C3.62753 15.1226 4.13623 15.3333 4.66667 15.3333H11.3333C11.8638 15.3333 12.3725 15.1226 12.7475 14.7475C13.1226 14.3725 13.3333 13.8638 13.3333 13.3333V4C13.3333 3.63181 13.0349 3.33333 12.6667 3.33333H11.3333ZM4 4.66667V13.3333C4 13.5101 4.07024 13.6797 4.19526 13.8047C4.32029 13.9298 4.48986 14 4.66667 14H11.3333C11.5101 14 11.6797 13.9298 11.8047 13.8047C11.9298 13.6797 12 13.5101 12 13.3333V4.66667H4Z" fill="currentColor"/>' +
    '<path fill-rule="evenodd" clip-rule="evenodd" d="M6.66667 6.66667C7.03486 6.66667 7.33333 6.96514 7.33333 7.33333V11.3333C7.33333 11.7015 7.03486 12 6.66667 12C6.29848 12 6 11.7015 6 11.3333V7.33333C6 6.96514 6.29848 6.66667 6.66667 6.66667Z" fill="currentColor"/>' +
    '<path fill-rule="evenodd" clip-rule="evenodd" d="M9.33333 6.66667C9.70152 6.66667 10 6.96514 10 7.33333V11.3333C10 11.7015 9.70152 12 9.33333 12C8.96514 12 8.66667 11.7015 8.66667 11.3333V7.33333C8.66667 6.96514 8.96514 6.66667 9.33333 6.66667Z" fill="currentColor"/>' +
    '</svg>';
  /* Archive icon - Feather "archive" glyph (Figma node 338:4539,
   * "Feather/Objects & Tools/Archive"). Classic archive box: a
   * lidded rectangular top bar, a rectangular body below it, and
   * a short horizontal slot in the middle indicating a label /
   * pull tab. Rendered at 16x16 in the ADS outlined-glyph style
   * (evenodd fill for the "stroke" effect) so it visually matches
   * ICON_TRASH / ICON_COPY / ICON_DOWNLOAD which all use the same
   * hollow-rect + filled-detail pattern.
   *
   * Semantics: archive is recoverable (unlike delete). The PRD calls
   * out Archive as the correct row action (docs/rate-card-manager-
   * prd-audit.md A5), sitting immediately before Delete so the
   * destructive action is last in the icon cluster. */
  const ICON_ARCHIVE =
    '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">' +
    /* Lid: hollow rounded rectangle from y=2 to y=5.333, spanning the full width. */
    '<path fill-rule="evenodd" clip-rule="evenodd" d="M1.33333 3C1.33333 2.44772 1.78105 2 2.33333 2H13.6667C14.219 2 14.6667 2.44772 14.6667 3V5C14.6667 5.55229 14.219 6 13.6667 6H2.33333C1.78105 6 1.33333 5.55229 1.33333 5V3ZM2.66667 3.33333V4.66667H13.3333V3.33333H2.66667Z" fill="currentColor"/>' +
    /* Body: hollow rectangle under the lid, with slightly inset left/right
     * edges so it reads as a box tucked under the lid. */
    '<path fill-rule="evenodd" clip-rule="evenodd" d="M2 5.33333C2.36819 5.33333 2.66667 5.63181 2.66667 6V12.6667C2.66667 12.8435 2.7369 13.013 2.86193 13.1381C2.98695 13.2631 3.15652 13.3333 3.33333 13.3333H12.6667C12.8435 13.3333 13.013 13.2631 13.1381 13.1381C13.2631 13.013 13.3333 12.8435 13.3333 12.6667V6C13.3333 5.63181 13.6318 5.33333 14 5.33333C14.3682 5.33333 14.6667 5.63181 14.6667 6V12.6667C14.6667 13.1971 14.456 13.7058 14.0809 14.0809C13.7058 14.456 13.1971 14.6667 12.6667 14.6667H3.33333C2.8029 14.6667 2.29419 14.456 1.91912 14.0809C1.54405 13.7058 1.33333 13.1971 1.33333 12.6667V6C1.33333 5.63181 1.63181 5.33333 2 5.33333Z" fill="currentColor"/>' +
    /* Slot: short horizontal fill in the middle of the body, indicating
     * the pull tab / label position (Feather's characteristic detail). */
    '<path fill-rule="evenodd" clip-rule="evenodd" d="M6 8.66667C6 8.29848 6.29848 8 6.66667 8H9.33333C9.70152 8 10 8.29848 10 8.66667C10 9.03486 9.70152 9.33333 9.33333 9.33333H6.66667C6.29848 9.33333 6 9.03486 6 8.66667Z" fill="currentColor"/>' +
    '</svg>';
  // Copy/Duplicate icon - provided directly by the user (Figma node 65-1622).
  // Rendered as a visual icon button only; wired to a non-destructive toast.
  const ICON_COPY =
    '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">' +
    '<path fill-rule="evenodd" clip-rule="evenodd" d="M2.66699 1.99999C2.49018 1.99999 2.32061 2.07023 2.19559 2.19525C2.07056 2.32028 2.00033 2.48985 2.00033 2.66666V8.66666C2.00033 8.84347 2.07056 9.01304 2.19559 9.13806C2.32061 9.26309 2.49018 9.33332 2.66699 9.33332H3.33366C3.70185 9.33332 4.00033 9.6318 4.00033 9.99999C4.00033 10.3682 3.70185 10.6667 3.33366 10.6667H2.66699C2.13656 10.6667 1.62785 10.4559 1.25278 10.0809C0.877706 9.7058 0.666992 9.19709 0.666992 8.66666V2.66666C0.666992 2.13622 0.877706 1.62752 1.25278 1.25244C1.62785 0.87737 2.13656 0.666656 2.66699 0.666656H8.66699C9.19743 0.666656 9.70613 0.87737 10.0812 1.25244C10.4563 1.62752 10.667 2.13622 10.667 2.66666V3.33332C10.667 3.70151 10.3685 3.99999 10.0003 3.99999C9.63214 3.99999 9.33366 3.70151 9.33366 3.33332V2.66666C9.33366 2.48985 9.26342 2.32028 9.1384 2.19525C9.01337 2.07023 8.8438 1.99999 8.66699 1.99999H2.66699ZM7.33366 6.66666C6.96547 6.66666 6.66699 6.96513 6.66699 7.33332V13.3333C6.66699 13.7015 6.96547 14 7.33366 14H13.3337C13.7018 14 14.0003 13.7015 14.0003 13.3333V7.33332C14.0003 6.96513 13.7018 6.66666 13.3337 6.66666H7.33366ZM5.33366 7.33332C5.33366 6.22875 6.22909 5.33332 7.33366 5.33332H13.3337C14.4382 5.33332 15.3337 6.22875 15.3337 7.33332V13.3333C15.3337 14.4379 14.4382 15.3333 13.3337 15.3333H7.33366C6.22909 15.3333 5.33366 14.4379 5.33366 13.3333V7.33332Z" fill="currentColor"/>' +
    '</svg>';
  /* Quick edit icon - per user-provided SVG (paired pencil/notepad
   * silhouette filled in ADS Indigo brand #4045C2). This replaces
   * the prior hash glyph (Feather Hash) on the Action column's
   * first button. The literal SVG is preserved from the brief,
   * including the clipPath wrapper and the explicit #4045C2 fill,
   * so theme overrides do not silently swap the color.
   *
   * Note on duplicate shape with ICON_EDIT: the pencil-on-paper
   * outline is the same as the prior Edit icon, but the Edit icon
   * was REMOVED from the Action column in the simplified
   * interaction brief (Name link is now the Edit entry point), so
   * the pencil is now free to represent Quick edit. ICON_QUICK_EDIT
   * is the new public name; ICON_HASH / ICON_OPEN are kept as
   * back-compat aliases so any QA / dev tools that grep on them
   * still find the new Quick edit glyph. */
  /* Both paths use fill="currentColor" so the glyph inherits the
   * button's text color. In Ad Design System theme that resolves to
   * --ads-brand (#4045C2 indigo); in Wireframe theme that resolves
   * to the grayscale icon color set by the wireframe overrides
   * (#4D4D4D mid-dark gray). No theme-specific markup needed. */
  const ICON_QUICK_EDIT =
    '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">' +
    '<g clip-path="url(#clip0_194_1626)">' +
    '<path fill-rule="evenodd" clip-rule="evenodd" d="M1.2518 2.58578C1.62687 2.21071 2.13558 2 2.66602 2H7.33268C7.70087 2 7.99935 2.29848 7.99935 2.66667C7.99935 3.03485 7.70087 3.33333 7.33268 3.33333H2.66602C2.4892 3.33333 2.31964 3.40357 2.19461 3.52859C2.06959 3.65362 1.99935 3.82319 1.99935 4V13.3333C1.99935 13.5101 2.06959 13.6797 2.19461 13.8047C2.31964 13.9298 2.4892 14 2.66602 14H11.9993C12.1762 14 12.3457 13.9298 12.4708 13.8047C12.5958 13.6797 12.666 13.5101 12.666 13.3333V8.66667C12.666 8.29848 12.9645 8 13.3327 8C13.7009 8 13.9993 8.29848 13.9993 8.66667V13.3333C13.9993 13.8638 13.7886 14.3725 13.4136 14.7475C13.0385 15.1226 12.5298 15.3333 11.9993 15.3333H2.66602C2.13558 15.3333 1.62687 15.1226 1.2518 14.7475C0.876729 14.3725 0.666016 13.8638 0.666016 13.3333V4C0.666016 3.46957 0.876729 2.96086 1.2518 2.58578Z" fill="currentColor"/>' +
    '<path fill-rule="evenodd" clip-rule="evenodd" d="M13.3327 1.91912C13.1344 1.91912 12.9443 1.99788 12.8041 2.13807L6.60132 8.34083L6.24893 9.75042L7.65852 9.39802L13.8613 3.19526C14.0015 3.05507 14.0802 2.86493 14.0802 2.66667C14.0802 2.4684 14.0015 2.27826 13.8613 2.13807C13.7211 1.99788 13.5309 1.91912 13.3327 1.91912ZM11.8613 1.19526C12.2515 0.80502 12.7808 0.585785 13.3327 0.585785C13.8846 0.585785 14.4138 0.80502 14.8041 1.19526C15.1943 1.5855 15.4136 2.11478 15.4136 2.66667C15.4136 3.21855 15.1943 3.74783 14.8041 4.13807L8.47075 10.4714C8.38531 10.5568 8.27826 10.6175 8.16104 10.6468L5.49437 11.3134C5.26719 11.3702 5.02686 11.3037 4.86128 11.1381C4.69569 10.9725 4.62912 10.7322 4.68592 10.505L5.35259 7.83831C5.38189 7.72109 5.44251 7.61403 5.52794 7.52859L11.8613 1.19526Z" fill="currentColor"/>' +
    '</g>' +
    '<defs>' +
    '<clipPath id="clip0_194_1626"><rect width="16" height="16" fill="white"/></clipPath>' +
    '</defs>' +
    '</svg>';
  /* Back-compat aliases - kept so any code path (or future test)
   * referencing the old hash name still finds the new Quick edit
   * glyph. The Edit pencil icon ICON_EDIT above is unused by the
   * Action column today (removed per the simplified-interaction
   * brief) but kept for any future surface that needs an outlined
   * pencil shape. */
  const ICON_HASH = ICON_QUICK_EDIT;
  const ICON_OPEN = ICON_QUICK_EDIT;

  // ----- Helpers ------------------------------------------------------------

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = String(text);
    return node;
  }

  /* Format the lastUpdated field for the Last updated column.
   * Figma 129-5556 renders dates as MM/DD/YYYY (e.g. "06/18/2026"). Dataset
   * uses "MMM DD, YYYY" so users editing the data still see a human form
   * in the source. Convert once at render time; fall back to the raw
   * string if the source is unparseable. */
  function formatLastUpdated(raw) {
    if (!raw) return "";
    var d = new Date(raw);
    if (isNaN(d.getTime())) return raw;
    var mm = String(d.getMonth() + 1).padStart(2, "0");
    var dd = String(d.getDate()).padStart(2, "0");
    var yyyy = d.getFullYear();
    return mm + "/" + dd + "/" + yyyy;
  }

  /* Counts individual selected VALUES, not dimensions, so the number on
   * the trigger always equals the number of chips under the toolbar.
   * Two statuses plus one marketplace reads as 3 in both places. */
  function countFilterValues(filters) {
    return MULTI_FILTER_KEYS.reduce(function (total, key) {
      return total + (filters[key] || []).length;
    }, 0) + (filters.buyingEntityId ? 1 : 0);
  }

  function activeFilterCount() {
    return countFilterValues(appliedFilters);
  }

  function hasAnyFilters() {
    return activeFilterCount() > 0 || query.trim().length > 0;
  }

  /* =================== SORTING ============================================
   *
   * Sort lives between filters and pagination in the render pipeline:
   *   RATE_CARDS -> filter+search (getFilteredRows) -> sort (sortRows)
   *   -> page slice -> renderTable
   *
   * Helpers:
   *   getSortValue(row, key)   normalized comparable value per column
   *   compareValues(a, b)      stable, type-aware comparator (numbers
   *                            numeric, strings case-insensitive, dates
   *                            chronological, nullish placed last)
   *   compareRateCards(a, b, sort)  full row comparator honoring sortState
   *   sortRows(rows)           stable sort wrapper around the above
   *
   * Stability: Array.prototype.sort is spec-stable in all modern engines
   * (V8/JSC since 2018+), so equal sort keys preserve their input order.
   * We never mutate RATE_CARDS - getFilteredRows returns a fresh array
   * and sortRows works on that copy.
   * ===================================================================== */

  /* Stable business order for Status sorting. Per the PRD the UI only
   * surfaces "Draft" and "Published"; Draft is the earlier stage (work
   * in progress) and Published is the later stage (live), so Draft
   * sorts first ascending. normalizeStatus() guarantees every row in
   * RATE_CARDS uses one of these two labels before sort runs. */
  const STATUS_ORDER = Object.freeze({
    "Draft":     0,
    "Published": 1,
  });

  /* parseVersion - normalize a Ver. cell to a number for numeric sort.
   * Dataset uses plain integers today, but accept "v1", "v2", "1.0", "2"
   * defensively so any future dataset changes Just Work. Empty/unparseable
   * values fall to NaN (handled by compareValues -> placed last). */
  function parseVersion(v) {
    if (v == null || v === "") return NaN;
    if (typeof v === "number") return v;
    const m = String(v).match(/(\d+(?:\.\d+)?)/);
    return m ? Number(m[1]) : NaN;
  }

  /* parseDate - normalize a lastUpdated cell to a JS Date for chrono sort.
   * Dataset uses "MMM DD, YYYY" (e.g. "Jun 18, 2026") which the native
   * Date constructor parses reliably on modern engines. Invalid dates
   * fall through to NaN (handled by compareValues -> placed last). */
  function parseDate(s) {
    if (!s) return NaN;
    const d = new Date(s);
    const t = d.getTime();
    return isNaN(t) ? NaN : t;
  }

  /* getSortValue - return the comparable value for a given column.
   * Status is mapped through STATUS_ORDER so it sorts in business
   * order (Draft -> Published), not alphabetical. All string keys are
   * lowercased so case differences don't split groups. */
  function getSortValue(row, key) {
    switch (key) {
      case "status":        return STATUS_ORDER[row.status] ?? Number.MAX_SAFE_INTEGER;
      case "saleshubId":    return (row.saleshubId   || "").toLowerCase();
      case "rateCardId":    return (row.rateCardId   || "").toLowerCase();
      case "name":          return (row.name         || "").toLowerCase();
      case "marketplace":   return (row.marketplace  || "").toLowerCase();
      case "buyingEntity":  return (row.buyingEntity || "").toLowerCase();
      case "lastUpdated":   return parseDate(row.lastUpdated);
      case "version":       return parseVersion(row.version);
      default:              return "";
    }
  }

  /* compareValues - type-aware, nullish-last comparator. Returns -1/0/1.
   * NaN and "" sink to the bottom regardless of sort direction so empty
   * cells never confuse the user by floating to the top on asc. */
  function compareValues(a, b) {
    const aMissing = (a === null || a === undefined || a === "" || (typeof a === "number" && isNaN(a)));
    const bMissing = (b === null || b === undefined || b === "" || (typeof b === "number" && isNaN(b)));
    if (aMissing && bMissing) return 0;
    if (aMissing) return 1;
    if (bMissing) return -1;
    if (typeof a === "number" && typeof b === "number") {
      return a - b;
    }
    if (a < b) return -1;
    if (a > b) return 1;
    return 0;
  }

  function compareRateCards(a, b, sort) {
    const av = getSortValue(a, sort.key);
    const bv = getSortValue(b, sort.key);
    const cmp = compareValues(av, bv);
    return sort.dir === "desc" ? -cmp : cmp;
  }

  function sortRows(rows) {
    if (!sortState) return rows;
    /* Copy first so we never mutate the array getFilteredRows returned. */
    return rows.slice().sort((a, b) => compareRateCards(a, b, sortState));
  }

  /* Three-state click cycle. Called by the [data-action="sort"] handler.
   * If clicking a different column, always start at ascending. If clicking
   * the active column, advance asc -> desc -> none. Resets pagination to
   * page 1 so the user always sees the new top of the sorted list. */
  function toggleSort(key) {
    if (!sortState || sortState.key !== key) {
      sortState = { key, dir: "asc" };
    } else if (sortState.dir === "asc") {
      sortState = { key, dir: "desc" };
    } else {
      sortState = null;
    }
    page = 1;
    renderTable();
  }

  /* An empty selection is not a filter at all, so it matches everything.
   * Otherwise the row has to equal one of the chosen values. */
  function matchesAny(selected, value) {
    if (!selected || !selected.length) return true;
    return selected.indexOf(value) !== -1;
  }

  function getFilteredRows() {
    /* Filter logic:
     *   - OR within a category. Status Draft or Published matches either.
     *   - AND across categories. Those statuses AND marketplace Scatter.
     *   - An empty category means "any", so it stops narrowing.
     *   - Buying entity matches one exact Saleshub ID, which is what the
     *     autocomplete resolves a typed name or ID down to.
     *   - The top-of-page search box keeps working in parallel with the
     *     filter panel; rows must satisfy both. */
    /* Search query is normalized: trimmed, lower-cased, and any run of
     * whitespace, hyphens, or dashes is collapsed to a single space.
     * This lets users find "Omnicom Video" by typing either
     * "omnicom-video" or "omnicom  video" (or any mix), without losing
     * the substring semantics they expect from a search field. The en
     * dash is in the class because card names separate their sections
     * and seasons with one ("WPP - Streaming Video Upfront 2026-2027"
     * with en dashes), and nobody types that character: "2026-2027"
     * has to find it. */
    const qRaw = (query || "").trim().toLowerCase();
    const q = qRaw.replace(/[\s\u2013\u2014-]+/g, " ");
    const entityId = (appliedFilters.buyingEntityId || "").trim();
    /* v1.2 renders a projected view of RATE_CARDS with PM's marketplace
     * normalisation + first-10-row overrides applied. v1.1 gets the
     * raw array so its behavior is byte-identical to the pre-v1.2
     * world. See activeRateCards() docblock for details. */
    return activeRateCards().filter((c) => {
      if (!matchesAny(appliedFilters.status, c.status)) return false;
      if (!matchesAny(appliedFilters.marketplace, c.marketplace)) return false;
      if (!matchesAny(appliedFilters.season, c.season)) return false;
      if (entityId && c.saleshubId !== entityId) return false;
      if (q) {
        /* Top-of-page search hay. Spec (2026-06-28 brief) says match
         * across: name, rateCardId, saleshubId, marketplace, STATUS,
         * LAST UPDATED, and VERSION. Buying entity stays in the hay
         * because the input placeholder advertises it. Same normalization
         * (whitespace + hyphens -> single space) applied to the hay so
         * that "RC DAS DENTSU" also finds "RC-DAS-DENTSU-..." records.
         *
         * lastUpdated lives in storage as "Jun 18, 2026" but renders
         * as "06/18/2026" - include BOTH forms so the user can search
         * by whichever date format they're looking at. */
        const dateRaw  = c.lastUpdated || "";
        const dateView = formatLastUpdated(dateRaw);
        const hay = (
          c.name + " " +
          c.rateCardId + " " +
          c.marketplace + " " +
          c.buyingEntity + " " +
          c.saleshubId + " " +
          c.status + " " +
          dateRaw + " " + dateView + " " +
          "v" + (c.version || "") + " " + (c.version || "")
        ).toLowerCase().replace(/[\s\u2013\u2014-]+/g, " ");
        /* Note: hyphens in the QUERY were already collapsed above, but
         * dates contain '/' which we deliberately don't normalize - users
         * searching "06/18/2026" expect literal-slash matching. */
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }

  // ----- Rendering ----------------------------------------------------------

  /* Refresh the table-header sort affordances. All sortable .th elements
   * carry data-sort-key + aria-sort. We toggle .th--sort-asc / .th--sort-desc
   * on the active header (CSS swaps the neutral up-down glyph for a single
   * up or down arrow) and set aria-sort = "ascending" | "descending" |
   * "none" for assistive tech. Idempotent - safe to call every render. */
  /* Sort glyphs per Figma 157:1968 (Data Table / Sort Button).
   *
   *   NEUTRAL. Feather Arrow-Down&Up: DOWN arrow on the left, UP
   *             arrow on the right. Single 9x8 path lifted directly
   *             from the Figma asset (filled, not stroked) so the
   *             visual matches at every zoom level. The fill uses
   *             currentColor so .th__sort's `color` rule drives the
   *             tint - default state is Figma "EDL Gray/30" (#B8C7D0),
   *             active state inherits ADS Indigo/70 via the CSS rule.
   *
   *   ASC. Up-only arrow on the right side (single arrow, same
   *             9x8 viewBox so positioning matches).
   *   DESC. Down-only arrow on the left side (same viewBox).
   *
   * Active glyphs use a single arrow so the sort direction is
   * unambiguous; the inactive arrow on the opposite side is omitted
   * (matches Figma's active state for the Data Table sort button). */
  /* One shared sort icon keeps both direction paths mounted in every
   * state. The active direction is emphasized by CSS
   * (.th--sort-asc / .th--sort-desc), so the inactive arrow stays
   * visible but faint and the SVG geometry never shifts. */
  var SORT_SVG_NEUTRAL =
    '<svg viewBox="0 0 9 8" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">' +
    '<path class="th__sort-direction th__sort-direction--descending" fill-rule="evenodd" clip-rule="evenodd" d="M2 0C2.27614 0 2.5 0.223858 2.5 0.5L2.5 6.29289L3.14645 5.64645C3.34171 5.45118 3.65829 5.45118 3.85355 5.64645C4.04882 5.84171 4.04882 6.15829 3.85355 6.35355L2.35355 7.85355C2.25979 7.94732 2.13261 8 2 8C1.86739 8 1.74021 7.94732 1.64645 7.85355L0.146447 6.35355C-0.0488155 6.15829 -0.0488155 5.84171 0.146447 5.64645C0.341709 5.45118 0.658291 5.45118 0.853553 5.64645L1.5 6.29289L1.5 0.5C1.5 0.223858 1.72386 0 2 0Z" fill="currentColor"/>' +
    '<path class="th__sort-direction th__sort-direction--ascending" fill-rule="evenodd" clip-rule="evenodd" d="M7 0C7.13261 0 7.25979 0.0526787 7.35355 0.146447L8.85355 1.64645C9.04882 1.84171 9.04882 2.15829 8.85355 2.35355C8.65829 2.54882 8.34171 2.54882 8.14645 2.35355L7.5 1.70711V7.5C7.5 7.77614 7.27614 8 7 8C6.72386 8 6.5 7.77614 6.5 7.5V1.70711L5.85355 2.35355C5.65829 2.54882 5.34171 2.54882 5.14645 2.35355C4.95118 2.15829 4.95118 1.84171 5.14645 1.64645L6.64645 0.146447C6.74021 0.0526787 6.86739 0 7 0Z" fill="currentColor"/>' +
    '</svg>';

  function renderSortIndicators() {
    document.querySelectorAll('.th--sortable').forEach((th) => {
      const key = th.getAttribute('data-sort-key');
      th.classList.remove('th--sort-asc', 'th--sort-desc');
      if (sortState && sortState.key === key) {
        if (sortState.dir === 'asc') {
          th.classList.add('th--sort-asc');
          th.setAttribute('aria-sort', 'ascending');
        } else {
          th.classList.add('th--sort-desc');
          th.setAttribute('aria-sort', 'descending');
        }
      } else {
        th.setAttribute('aria-sort', 'none');
      }
      /* Sort glyphs are static SVG strings (no user input) so direct
       * innerHTML assignment is safe here. Both direction paths are
       * always mounted; CSS handles the active-state emphasis. We
       * only inject the SVG once per element to keep renderTable
       * cheap on every filter/search keystroke. */
      var sortEl = th.querySelector('.th__sort');
      if (sortEl && !sortEl.firstElementChild) {
        sortEl.innerHTML = SORT_SVG_NEUTRAL;
      }
      if (sortEl) {
        var nextState = sortState && sortState.key === key ? sortState.dir : 'none';
        sortEl.dataset.sortState = nextState;
      }
    });
  }

  /* One visibility rule for every paginated table in the app: the footer
   * only earns its space when there is a second page to reach. Below that
   * threshold "Show 10 of 4 items", a lone page-1 button, and a dead
   * "Go to page" picker are noise, so the whole footer is removed rather
   * than disabled. Exported because v2.js owns the Line Items and Premiums
   * footers and both surfaces have to answer this question the same way.
   * Callers pass the FILTERED result count, never the fixture size. */
  function shouldShowPaginationFooter(totalItems, pageSize) {
    const total = Number(totalItems);
    const size = Number(pageSize);
    if (!Number.isFinite(total) || !Number.isFinite(size) || size <= 0) return false;
    return total > size;
  }
  window.shouldShowPaginationFooter = shouldShowPaginationFooter;

  function renderTable() {
    const rowsRoot = document.querySelector("[data-rows]");
    const empty = document.querySelector("[data-empty]");
    const showTotal = document.querySelector("[data-total]");
    const pager = document.querySelector("[data-pager]");
    /* Resolved from the pager rather than by class lookup so the footer we
     * show or hide is always the one holding the controls we just rebuilt,
     * even when the Redline bridge reparents the list DOM. */
    const footer = pager ? pager.closest(".footer") : null;
    const filterBtn = document.querySelector('[data-action="toggle-filter"]');
    const emptyTitle = document.querySelector("[data-empty-title]");
    const emptyBody = document.querySelector("[data-empty-body]");
    const resetAllBtn = document.querySelector('[data-action="reset-all"]');
    const goSelect = document.querySelector('[data-action="go-to-page"]');

    /* Data pipeline (order matters):
     *   1. RATE_CARDS
     *   2. search + filters (getFilteredRows)
     *   3. sort (sortRows) - applied AFTER filters so the sorted view
     *      always reflects the currently visible result set
     *   4. page slice */
    const filtered = getFilteredRows();
    const all = sortRows(filtered);
    const total = all.length;
    const pageCount = Math.max(1, Math.ceil(total / pageSize));
    if (page > pageCount) page = pageCount;
    const start = (page - 1) * pageSize;
    const visible = all.slice(start, start + pageSize);

    // Reflect sort state on the sortable column headers
    renderSortIndicators();

    /* Filter trigger. It reports how many individual values are applied,
     * which is the same number as the chips below the toolbar, and it
     * answers to applied state only, never to the drawer being open. */
    const appliedCount = activeFilterCount();
    filterBtn.classList.toggle("is-active", appliedCount > 0);
    const filterLabel = filterBtn.querySelector("span");
    const filterText = appliedCount > 0 ? "Filters (" + appliedCount + ")" : "Filters";
    if (filterLabel) filterLabel.textContent = filterText;
    filterBtn.setAttribute("aria-label",
      appliedCount > 0 ? "Filter rate cards, " + appliedCount + " applied" : "Filter rate cards");

    renderFilterChips();
    announceFilterResults(total);

    /* "Show <pageSize> of <total> items" footer per Figma 129:5818
     * (Pagination / Show Results). The "of N items" half lives in
     * [data-total]; the page-size half is the existing <select> with
     * data-action="page-size" so changing the dropdown rerenders both.
     * On the last page where fewer rows are visible than pageSize, we
     * still show pageSize on the left half (matches Figma copy and the
     * brief, which says "Show [page size] of [total]"). If total === 0
     * we suppress the number to avoid "Show 10 of 0 items". */
    showTotal.textContent = total > 0 ? "of " + total + " items" : "of no items";

    /* Single-page result sets drop the footer entirely (no height, no top
     * border, no invisible controls). `hidden` rather than a class so the
     * page-size select, the pager buttons, and the "Go to page" picker
     * leave the accessibility tree and the tab order together, instead of
     * sitting off-screen where a keyboard user would still land on them.
     * The controls below still get rebuilt so the footer is correct the
     * moment a search or a page-size change brings it back. */
    if (footer) footer.hidden = !shouldShowPaginationFooter(total, pageSize);

    // Rebuild "Go to page" select to match current pageCount. The
    // visible control is the ADS .edl-select on the right side of
    // the footer; the hidden native <select> is kept as a sentinel
    // so the existing 'change' listener (which sets `page` +
    // re-renders) keeps firing when the user picks from the
    // floating menu. Both stay in sync with the current `page`.
    goSelect.replaceChildren();
    for (let p = 1; p <= pageCount; p++) {
      const opt = document.createElement("option");
      opt.value = String(p);
      opt.textContent = String(p);
      if (p === page) opt.selected = true;
      goSelect.appendChild(opt);
    }
    const goEdl = document.querySelector('.edl-select[data-field="go-to-page"]');
    if (goEdl) {
      /* The menu can be either inside .edl-select OR portaled to
       * document.body when open. _edlMenu (set by toggleEdlSelect)
       * always points at the live menu element regardless of where
       * it currently lives. Fall back to a scoped querySelector for
       * the closed-state lookup. */
      const menu = goEdl._edlMenu || goEdl.querySelector('.edl-select__menu');
      if (menu) {
        menu.innerHTML = "";
        for (let p = 1; p <= pageCount; p++) {
          const li = document.createElement("li");
          li.className = "edl-select__option" + (p === page ? " is-selected" : "");
          li.setAttribute("role", "option");
          li.setAttribute("data-value", String(p));
          li.setAttribute("tabindex", "-1");
          li.setAttribute("aria-selected", p === page ? "true" : "false");
          li.textContent = String(p);
          menu.appendChild(li);
        }
      }
      goEdl.setAttribute("data-value", String(page));
      const v = goEdl.querySelector(".edl-select__value");
      if (v) v.textContent = String(page);
    }

    // Body / empty. Three empty-state variants:
    //   1. Search query active (with or without filters) -> "No rate
    //      cards found" / "Try adjusting your search or filters."
    //      Matches the user-approved ADS copy in the 2026-06-28 brief.
    //   2. Filters only, no search -> previous "No rate cards match
    //      these filters" copy stays so filter-only users get the
    //      precise reason.
    //   3. Empty dataset -> "No rate cards yet." onboarding nudge.
    rowsRoot.replaceChildren();
    if (visible.length === 0) {
      empty.hidden = false;
      const hasSearch = query.trim().length > 0;
      if (hasSearch) {
        emptyTitle.textContent = "No rate cards found";
        emptyBody.textContent  = "Try adjusting your search or filters.";
        resetAllBtn.textContent = "Clear search";
        resetAllBtn.hidden = false;
      } else if (activeFilterCount() > 0) {
        emptyTitle.textContent = "No rate cards match these filters.";
        emptyBody.textContent  = "Adjust or clear filters to see more rate cards.";
        resetAllBtn.textContent = "Clear filters";
        resetAllBtn.hidden = false;
      } else {
        emptyTitle.textContent = "No rate cards yet.";
        emptyBody.textContent  = "Create a rate card or import a CSV to get started.";
        resetAllBtn.hidden = true;
      }
    } else {
      empty.hidden = true;
      for (const row of visible) rowsRoot.appendChild(buildRow(row));
    }

    renderPager(pager, page, pageCount);
    /* Keep the 2.1 selection header and selected-row action bar in step
     * with what is now on screen. Both hide themselves when the selected
     * rows are filtered, searched, or paginated out of view, and both
     * are no-ops before 2.1. */
    syncSelectAllHeader();
    syncSelectionActionBar();
  }

  /* ADS Checkbox, component set 71:62.
   *
   * One factory for every checkbox in the product. The 2.1 list's
   * selection column and the Rate Card Details line-item table both
   * mount it, so the control's structure and token hooks are described
   * in exactly one place and the two surfaces cannot drift apart.
   *
   * The native input stays in the accessibility tree and carries
   * checked / indeterminate / disabled itself, so assistive tech reports
   * the real state rather than the painted box. Everything visual is
   * CSS (".theme-ads .ads-checkbox" in styles.css); nothing here sets a
   * color, size, or radius.
   *
   * Published on window because v2.js renders the details table from its
   * own module and needs the same control.
   */
  const CHECKBOX_CHECK_SVG =
    '<svg class="ads-checkbox__check" viewBox="0 0 10 7" fill="none" aria-hidden="true">' +
    '<path d="M1 3.6 3.7 6.2 9 1" stroke="currentColor" stroke-width="1.5" ' +
    'stroke-linecap="round" stroke-linejoin="round"/></svg>';
  const CHECKBOX_MINUS_SVG =
    '<svg class="ads-checkbox__minus" viewBox="0 0 12 1" fill="none" aria-hidden="true">' +
    '<rect width="12" height="1" rx="0.5" fill="currentColor"/></svg>';

  function buildAdsCheckbox(options) {
    const opts = options || {};
    const label = el("label", "ads-checkbox");

    const input = document.createElement("input");
    input.type = "checkbox";
    input.className = "ads-checkbox__input";
    input.checked = !!opts.checked;
    input.disabled = !!opts.disabled;
    if (opts.label) input.setAttribute("aria-label", opts.label);

    /* Adjacent-sibling selectors drive every painted state, so the
     * control has to follow the input directly. */
    const control = el("span", "ads-checkbox__control");
    const box = el("span", "ads-checkbox__box");
    box.innerHTML = CHECKBOX_CHECK_SVG + CHECKBOX_MINUS_SVG;
    control.appendChild(box);

    label.appendChild(input);
    label.appendChild(control);

    /* Indeterminate is a property, not an attribute, so it has to be set
     * after the node exists and re-set whenever the box is rebuilt. */
    input.indeterminate = !!opts.indeterminate;

    if (typeof opts.onChange === "function") {
      input.addEventListener("change", function () {
        opts.onChange(input.checked, input);
      });
    }
    return label;
  }
  window.buildAdsCheckbox = buildAdsCheckbox;

  /* Render a single table body row. Column order matches the Figma 129:5515
   * Data Table header: Status, SalesHub ID, Rate Card ID, Name, Marketplace,
   * Last Updated, Ver, Action. Action cluster is 5 icons (Figma frame
   * 2134099623 shows 5 x 32 icon buttons). */
  function buildRow(row) {
    const r = el("div", "row");
    r.setAttribute("role", "row");
    r.setAttribute("data-row-id", row.id);
    /* The rate card id as an attribute, not only as cell text: 2.1 folds
     * the Rate Card ID column into the combined cell, so anything that
     * needs to find a row by that id (v2.js does, when it opens a card
     * the catalog has never seen) would otherwise depend on which
     * columns a given version happens to render. */
    r.setAttribute("data-rate-card-id", row.rateCardId);
    const selected = selectedRateCardIds.has(String(row.id));
    r.classList.toggle("is-selected", selected);
    r.setAttribute("aria-selected", selected ? "true" : "false");

    /* 0. Selection column (2.1 only, 645:68987). The row body still
     *    toggles selection the way it has since 2.1 shipped; the box is
     *    the explicit affordance for it and reports the state. The click
     *    stops here so the row's own handler cannot toggle the same
     *    record a second time and undo the change. */
    if (isVersion21()) {
      const selectCell = el("div", "cell cell--select");
      const selectBox = buildAdsCheckbox({
        label: "Select " + row.name,
        checked: selected,
        onChange: function () { selectRateCardRow(row.id); }
      });
      selectBox.addEventListener("click", function (e) { e.stopPropagation(); });
      selectCell.appendChild(selectBox);
      r.appendChild(selectCell);
    }

    // 1. Status chip
    const statusCell = el("div", "cell cell--status");
    statusCell.appendChild(buildChip(row.status));
    r.appendChild(statusCell);

    /* Truncation tooltips: .cell uses white-space:nowrap +
     * overflow:hidden + text-overflow:ellipsis, so any value wider
     * than the column gets clipped. We attach the full value as
     * data-tooltip; data-tooltip-truncate="auto" signals the runtime
     * tooltip controller (adsTooltipShow) to compare scrollWidth vs
     * clientWidth on hover and ONLY render the tooltip if actually
     * truncated. Non-truncated values stay quiet. title= NOT set
     * (the browser-native tooltip is forbidden by the brief).
     *
     * Cell classes carry a semantic modifier (cell--saleshub /
     * cell--rate-card-id / cell--marketplace / cell--last-updated) so
     * the v1.2 CSS can reorder columns without changing the DOM
     * append order. v1.1 has no rule matching those class names, so
     * v1.1 rendering is byte-identical. See body[data-version="1.2"]
     * order rules in styles.css. */
    // 2. SalesHub ID (monospace-feel digits + letters)
    const salesCell = el("div", "cell cell--code cell--saleshub", row.saleshubId);
    salesCell.setAttribute("data-tooltip", row.saleshubId);
    salesCell.setAttribute("data-tooltip-truncate", "auto");
    r.appendChild(salesCell);

    /* 3. Rate Card ID (monospace-feel uppercase identifier).
     *
     *    2.1 replaces this column and the Name column that follows with
     *    one combined "Rate Card ID / Name" cell (645:68987), so the two
     *    separate cells are not built at all rather than built and
     *    hidden. Both fields still drive search and sort in every
     *    version, and every earlier version renders them unchanged. */
    if (!isVersion21()) {
      const rcIdCell = el("div", "cell cell--code cell--rate-card-id", row.rateCardId);
      rcIdCell.setAttribute("data-tooltip", row.rateCardId);
      rcIdCell.setAttribute("data-tooltip-truncate", "auto");
      r.appendChild(rcIdCell);
    }

    // 4. Name - clickable brand-indigo link. This is the PRIMARY
    //    entry into the full Edit Rate Card page. Per the simplified
    //    interaction brief, there is no Details slideover - clicking
    //    Name navigates directly to Edit. The URL is enriched with
    //    section=create + cardId={rateCardId} so the route is
    //    bookmarkable and deep-linkable to this rate card's edit
    //    surface.
    //
    //    aria-label includes the row name so screen readers announce
    //    "Edit {rate card name}" instead of just the visible text.
    //    Enter key activation is automatic for <a href> elements.
    //
    //    Under 2.1 the link is the first line of the combined cell and
    //    the rate card id follows it as plain text, so the same single
    //    Edit affordance serves both versions.
    const nameCell = isVersion21()
      ? el("div", "cell cell--name-id")
      : el("div", "name");
    const link = el("a", "name__link", row.name);
    link.setAttribute("href",
      "?section=create&mode=edit&cardId=" + encodeURIComponent(row.rateCardId));
    link.setAttribute("aria-label", "Edit " + row.name);
    // ADS truncation tooltip: data-tooltip-truncate="auto" makes the
    // tooltip controller only show the full name when the link is
    // actually clipped by the column width (cheaper than always
    // showing it, and per the brief's "Do not show a tooltip when
    // the text is not truncated" rule). title= NOT set.
    link.setAttribute("data-tooltip", row.name);
    link.setAttribute("data-tooltip-truncate", "auto");
    link.addEventListener("click", (e) => {
      e.preventDefault();
      openEditRateCard(row);
    });
    nameCell.appendChild(link);
    /* Second line of the 2.1 combined cell: "ID: {rateCardId}", plain
     * text rather than a link so the row keeps exactly one navigation
     * target, with its own truncation tooltip so a long id still
     * surfaces its full value when the column clips it. */
    if (isVersion21()) {
      const idLine = el("span", "name-id__id", "ID: " + row.rateCardId);
      idLine.setAttribute("data-tooltip", "ID: " + row.rateCardId);
      idLine.setAttribute("data-tooltip-truncate", "auto");
      nameCell.appendChild(idLine);
    }
    r.appendChild(nameCell);

    // 5. Marketplace
    r.appendChild(el("div", "cell cell--marketplace", row.marketplace));

    // 6. Buying Entity. Added 2026-06-29 per PM brief. Rows that lack a
    //    buyingEntity value render the em-dash placeholder so the column
    //    never shows a blank cell (matches Marketplace's "Not set" convention).
    //    Truncation tooltip mirrors SalesHub ID / Rate Card ID so long
    //    entity names ("National Geographic", "Disney Planning", etc.)
    //    still surface their full value on hover when the column clips.
    //
    //    2.1's first reference node (472:17713) dropped this column, so
    //    the row used to skip it there. 645:68987 restores it between
    //    Marketplace and Last updated, and the 2.1 grid already reserves
    //    that track, so every version builds the cell again.
    var beValue = (row.buyingEntity && String(row.buyingEntity).trim()) || "Not set";
    var beCell = el("div", "cell cell--buying-entity");
    /* The value goes in an element of its own rather than straight into
     * the cell. Cells are flex containers, and text-overflow needs a
     * block box to put its ellipsis in, so a bare text node would clip
     * mid-letter instead. This is the column that gives ground first
     * when the card is too narrow for every track, so it is the one
     * that has to truncate legibly. */
    beCell.appendChild(el("span", "cell__text", beValue));
    beCell.setAttribute("data-tooltip", beValue);
    beCell.setAttribute("data-tooltip-truncate", "auto");
    r.appendChild(beCell);

    // 7. Last updated
    r.appendChild(el("div", "cell cell--last-updated", formatLastUpdated(row.lastUpdated)));

    // 8. Version (narrow numeric)
    r.appendChild(el("div", "cell cell--num cell--ver", String(row.version)));

    // 9. Actions - 5 icons in order:
    //      Quick edit -> Duplicate -> Export -> Archive -> Delete
    //    per Figma node 129:5535 (the RCM row-actions cluster now
    //    includes a Feather Archive glyph immediately before Delete,
    //    so the destructive action stays last). Each is a 24x24
    //    ADS icon button around a 16x16 glyph.
    //
    //    The Edit (pencil) icon remains OMITTED per the simplified
    //    interaction brief: the rate card Name link is the primary
    //    entry into the full Edit Rate Card page, so a redundant
    //    Edit affordance in the Action column is not built.
    //
    //    Archive is a recoverable action (unlike Delete). It persists the
    //    archived identity and removes the row from the active list.
    //
    //    Details slideover was intentionally NOT built (PRD calls
    //    it out, prototype simplifies). See docs/rate-card-manager-
    //    prd-summary.md "Design note: No row Details slideover".
    /* Version 2.1 removes this column outright and moves all five
     * actions into the selected-row action bar (see "VERSION 2.1 -
     * SELECTED ROW ACTION BAR" below), so 2.1 rows never build the
     * buttons at all. 1.x and 2.0 are untouched. */
    if (!isVersion21()) {
      const actions = el("div", "actions");
      actions.appendChild(
        buildIconButton(ICON_QUICK_EDIT, "Quick edit", () => openQuickEdit(row.id)),
      );
      actions.appendChild(
        buildIconButton(ICON_COPY, "Duplicate rate card", () =>
          duplicateRateCard(row),
        ),
      );
      actions.appendChild(
        buildIconButton(ICON_DOWNLOAD, "Export rate card", () => exportRateCard(row)),
      );
      actions.appendChild(
        buildIconButton(ICON_ARCHIVE, "Archive rate card", () => archiveRateCard(row)),
      );
      actions.appendChild(
        // Tooltip stays "Delete rate card" because the modal that opens
        // is still a delete modal. Archive (recoverable) lives one slot
        // to the left; Delete stays as the terminal destructive action.
        buildIconButton(ICON_TRASH, "Delete rate card",
          (e) => openDeleteModal(row.id, e.currentTarget)),
      );
      r.appendChild(actions);
    }

    r.querySelectorAll(":scope > .cell, :scope > .name, :scope > .actions")
      .forEach(function(cell) {
        cell.setAttribute("role", "cell");
      });

    /* Row selection is independent from navigation. The Name link is
     * the primary Edit affordance, while action buttons retain their
     * own behavior. Selecting a row updates aria-selected and the ADS
     * selected-row surface without activating any child action. */
    r.addEventListener("click", function(e){
      if (e.target.closest(".actions, .name__link, .ads-checkbox, button, a")) return;
      selectRateCardRow(row.id);
    });
    /* Rows remain keyboard reachable. Enter and Space select the row;
     * links and buttons keep their native keyboard behavior. */
    r.setAttribute("tabindex", "0");
    r.addEventListener("keydown", function(e){
      if ((e.key === "Enter" || e.key === " ")
          && !e.target.closest(".actions, .name__link, .ads-checkbox, button, a")) {
        e.preventDefault();
        selectRateCardRow(row.id);
      }
    });
    return r;
  }

  /* Click / Enter / Space on a row.
   *
   * 2.1 toggles the row in and out of the selection, so several rows can
   * be selected at once and clicking a selected row deselects it. Every
   * earlier version keeps its original single-row behavior: the clicked
   * row becomes the only selection and clicking it again is a no-op. */
  function selectRateCardRow(rowId) {
    var id = String(rowId);
    if (isVersion21()) {
      if (selectedRateCardIds.has(id)) {
        selectedRateCardIds.delete(id);
      } else {
        selectedRateCardIds.add(id);
      }
    } else {
      selectedRateCardIds.clear();
      selectedRateCardIds.add(id);
    }
    paintRowSelection();
    syncSelectionActionBar();
  }

  /* Reflect the selection set onto whatever rows are currently painted.
   * Rows for selected ids that are not on this page simply are not
   * found, which is fine: the set is the source of truth and buildRow()
   * re-applies the class when they come back into view. */
  function paintRowSelection() {
    document.querySelectorAll("[data-rows] .row").forEach(function (rowEl) {
      var selected = selectedRateCardIds.has(rowEl.getAttribute("data-row-id"));
      rowEl.classList.toggle("is-selected", selected);
      rowEl.setAttribute("aria-selected", selected ? "true" : "false");
      var box = rowEl.querySelector(".cell--select .ads-checkbox__input");
      if (box) box.checked = selected;
    });
    syncSelectAllHeader();
  }

  /* ---- Selection column header (2.1 only, 645:68987) ----------------
   *
   * Mounted from JS rather than parked in index.html so no earlier
   * version carries a column it does not have. It is inserted after
   * initColumnResize has stamped its positional handles, and that
   * function skips .th--select outright, so the resize mapping cannot
   * be shifted by this cell whenever it happens to mount.
   *
   * "On this page" is deliberate: selection survives paging, but Select
   * All acts on the rows the user can actually see, which is the only
   * scope the header checkbox can honestly report a mixed state for. */
  function ensureSelectAllHeader() {
    var head = document.querySelector('[data-page="list"] .table__head');
    if (!head) return null;
    var host = head.querySelector("[data-select-all-host]");
    if (!isVersion21()) {
      if (host) host.remove();
      return null;
    }
    if (host) return host;
    host = el("div", "th th--select");
    host.setAttribute("data-select-all-host", "");
    host.setAttribute("role", "columnheader");
    host.appendChild(buildAdsCheckbox({
      label: "Select all rate cards on this page",
      onChange: function (checked) { setPageSelection(checked); }
    }));
    head.insertAdjacentElement("afterbegin", host);
    return host;
  }

  /* Unchecked with nothing on the page selected, checked when every row
   * is, mixed in between, and disabled when there is nothing to act on.
   * The state is read off the native input so assistive tech and the
   * painted box can never disagree. */
  function syncSelectAllHeader() {
    var host = ensureSelectAllHeader();
    if (!host) return;
    var input = host.querySelector(".ads-checkbox__input");
    if (!input) return;
    var rows = document.querySelectorAll("[data-rows] .row");
    var total = rows.length;
    var chosen = 0;
    rows.forEach(function (rowEl) {
      if (selectedRateCardIds.has(rowEl.getAttribute("data-row-id"))) chosen++;
    });
    input.disabled = total === 0;
    input.checked = total > 0 && chosen === total;
    input.indeterminate = chosen > 0 && chosen < total;
  }

  /* Select All / Clear All across the visible page. Rows selected on
   * other pages are left alone, so paging away and back does not
   * silently drop them. */
  function setPageSelection(selectAll) {
    document.querySelectorAll("[data-rows] .row").forEach(function (rowEl) {
      var id = rowEl.getAttribute("data-row-id");
      if (selectAll) selectedRateCardIds.add(id);
      else selectedRateCardIds.delete(id);
    });
    paintRowSelection();
    syncSelectionActionBar();
  }

  /* ===================================================================
   *  VERSION 2.1 - CONTEXTUAL ACTION BAR  (Figma 603:11843)
   *
   *  2.1 drops the per-row Action column. Its five actions move into a
   *  bar that appears directly above the column header row as soon as
   *  one or more rows are selected, and reports how many rows those
   *  actions will apply to. (2026-08-24, style guide 104:23927: the bar
   *  used to sit between the header and the first data row, which read
   *  as a data row itself. Above the header it reads as a toolbar for
   *  the table, which is what it is.)
   *
   *  The bar reads the same selection set the rows paint from, so the
   *  count can never disagree with the highlighted rows. Selection is
   *  held by rate card id, so it survives sorting, filtering,
   *  searching, and paging; ids that leave the active data set (deleted
   *  or archived) are pruned on read rather than left to rot.
   *
   *  Each button calls the same handler the matching Action-column icon
   *  called in 2.0, applied across the whole selection. Quick Edit is
   *  the one action that only makes sense for a single record, so it is
   *  disabled rather than quietly acting on one of several rows.
   *
   *  1.x and 2.0 never build the bar and keep their Action column.
   * =================================================================== */
  function isVersion21() {
    return document.body.getAttribute("data-version") === "2.1";
  }

  /* "1 item selected" / "2 items selected". Singular only ever at one.
   * Grouped above a thousand, since selection survives paging and the
   * total can run well past what one page shows. */
  function selectionCountLabel(count) {
    return count.toLocaleString()
      + (count === 1 ? " item selected" : " items selected");
  }

  /* The selected rate cards, in the order the active data set holds
   * them, with any id that no longer exists dropped from the set. */
  function selectedRateCards() {
    if (selectedRateCardIds.size === 0) return [];
    var cards = activeRateCards().filter(function (card) {
      return selectedRateCardIds.has(String(card.id));
    });
    if (cards.length !== selectedRateCardIds.size) {
      var live = new Set(cards.map(function (card) { return String(card.id); }));
      selectedRateCardIds.forEach(function (id) {
        if (!live.has(id)) selectedRateCardIds.delete(id);
      });
    }
    return cards;
  }

  /* The five actions from the 2.0 Action column, in the same order,
   * with the labels the 2.1 reference uses.
   *
   * `singleOnly` marks an action that cannot be applied to a set. `run`
   * always receives the full selection so no action can silently
   * operate on the wrong row. */
  function selectionActionSpecs() {
    return [
      { key: "quick-edit", label: "Quick Edit", icon: ICON_QUICK_EDIT,
        singleOnly: true,
        run: function (cards) { openQuickEdit(cards[0].id); } },
      { key: "copy", label: "Copy", icon: ICON_COPY,
        run: function (cards) { duplicateRateCards(cards); } },
      { key: "download", label: "Download", icon: ICON_DOWNLOAD,
        run: function (cards) { exportRateCards(cards); } },
      /* "Archive", not "Archive rate card": 608:14479 sizes this button
       * at 95px, which is the icon, the 8/12 padding, and the one word.
       * The pre-2.1 Action column keeps its longer icon tooltip, where
       * there is no visible label to carry the meaning. */
      { key: "archive", label: "Archive", icon: ICON_ARCHIVE,
        run: function (cards) { archiveRateCards(cards); } },
      { key: "delete", label: "Delete", icon: ICON_TRASH,
        run: function (cards, button) {
          openDeleteModal(cards.map(function (c) { return c.id; }), button);
        } }
    ];
  }

  /* ---- The shared component ----------------------------------------
   *
   * Everything that puts an Action Bar on screen goes through these two
   * functions: the production table below, and Redline Mode's Action Bar
   * specimen (see the component gallery further down this file). Markup,
   * icon set, labels, order, and the rules for which action is available
   * at which selection size therefore exist once. The only thing a
   * caller supplies is what a press should do.
   *
   * `onAction` receives the spec the user pressed. Production runs it
   * against the live selection; the specimen ignores it, which is what
   * keeps an inspection session from touching real records. */
  function createSelectionActionBar(options) {
    var opts = options || {};
    /* opts.specs / opts.ariaLabel / opts.groupAriaLabel let a second
     * surface reuse this component with its own action set and its own
     * accessible names. The Rate Card Details line-item table does
     * exactly that, so both bars stay one implementation rather than
     * two that drift. Callers that pass nothing get the rate card list's
     * five actions, unchanged. */
    var specs = opts.specs || selectionActionSpecs();
    var bar = el("div", "rcsel");
    bar.setAttribute("data-selection-bar", "");
    bar.setAttribute("role", "region");
    bar.setAttribute("aria-label", opts.ariaLabel || "Selected rate card actions");
    bar.hidden = true;

    var count = el("span", "rcsel__count");
    count.setAttribute("data-selection-count", "");
    /* Announce the running total as rows are selected and deselected. */
    count.setAttribute("aria-live", "polite");
    bar.appendChild(count);

    var group = el("div", "rcsel__actions");
    group.setAttribute("role", "group");
    group.setAttribute(
      "aria-label", opts.groupAriaLabel || "Actions for the selected rate cards");
    /* Tabbing to an action that has scrolled out of the strip has to
     * bring it back, ring and all. Browsers scroll a focused element
     * into view on their own, but not reliably inside a nested scroller
     * and never with room to spare for the outline, so the strip does
     * it itself and leaves the same 4px its padding reserves. */
    group.addEventListener("focusin", function (event) {
      var target = event.target && event.target.closest
        ? event.target.closest(".rcsel__btn")
        : null;
      if (!target) return;
      if (group.scrollWidth - group.clientWidth <= 1) return;
      var strip = group.getBoundingClientRect();
      var btn = target.getBoundingClientRect();
      var margin = 4;
      if (btn.left < strip.left + margin) {
        group.scrollLeft -= (strip.left + margin) - btn.left;
      } else if (btn.right > strip.right - margin) {
        group.scrollLeft += btn.right - (strip.right - margin);
      }
    });
    specs.forEach(function (spec) {
      var btn = el("button", "rcsel__btn");
      btn.type = "button";
      btn.setAttribute("data-selection-action", spec.key);
      var glyph = el("span", "rcsel__btn-icon");
      glyph.innerHTML = spec.icon;   // trusted in-file SVG constant
      btn.appendChild(glyph);
      btn.appendChild(el("span", "rcsel__btn-label", spec.label));
      /* Narrow viewports drop the label to fit five actions in the
       * space available, so the accessible name has to come from the
       * button itself rather than the text it may not be showing, and
       * the tooltip has to be able to name an action the user can only
       * see as an icon. */
      btn.setAttribute("aria-label", spec.label);
      btn.setAttribute("title", spec.label);
      btn.addEventListener("click", function () {
        if (btn.disabled) return;
        /* The button goes with the spec: an action that opens a dialog
         * has to know what to hand focus back to when it closes. */
        if (typeof opts.onAction === "function") opts.onAction(spec, btn);
      });
      group.appendChild(btn);
    });
    bar.appendChild(group);
    return bar;
  }

  /* On a narrow table the five actions scroll inside the bar rather
   * than dropping one of them (see 7b in styles.css). Two things follow
   * from that and neither belongs in CSS:
   *
   *  - a region a mouse can scroll has to be reachable by keyboard, so
   *    it takes a tab stop, but only while it actually scrolls;
   *  - the user has to be able to tell there is more to the right, so
   *    the trailing edge fades until the strip is scrolled to its end.
   */
  function syncSelectionActionScroll(bar) {
    var group = bar && bar.querySelector(".rcsel__actions");
    if (!group) return;
    var scrolls = group.scrollWidth - group.clientWidth > 1;
    if (scrolls) group.setAttribute("tabindex", "0");
    else group.removeAttribute("tabindex");
    group.classList.toggle("is-scrollable", scrolls);
    group.classList.toggle(
      "is-scroll-end",
      scrolls && group.scrollLeft >= group.scrollWidth - group.clientWidth - 1
    );
    if (group.__rcselScrollBound) return;
    group.__rcselScrollBound = true;
    group.addEventListener("scroll", function () {
      group.classList.toggle(
        "is-scroll-end",
        group.scrollLeft >= group.scrollWidth - group.clientWidth - 1
      );
    }, { passive: true });
  }

  /* Apply a selection size to a bar built above: the count sentence and
   * the enablement of any action that only works on a single record. */
  function applySelectionActionBarState(bar, count, options) {
    if (!bar) return;
    var opts = options || {};
    bar.hidden = count === 0;
    var readout = bar.querySelector("[data-selection-count]");
    if (count === 0) {
      /* Empty the readout on the way out rather than leaving the last
       * count sitting inside the hidden bar. Nothing is on screen either
       * way, but a cleared selection should read as cleared wherever it
       * is inspected, and it means a list reached by the back link and
       * one reached by a browser Back are in the same state rather than
       * only looking like it. */
      if (readout && readout.textContent) readout.textContent = "";
      return;
    }

    var label = selectionCountLabel(count);
    if (readout && readout.textContent !== label) readout.textContent = label;

    (opts.specs || selectionActionSpecs()).forEach(function (spec) {
      if (!spec.singleOnly) return;
      var btn = bar.querySelector('[data-selection-action="' + spec.key + '"]');
      if (!btn) return;
      var blocked = count !== 1;
      btn.disabled = blocked;
      btn.setAttribute("aria-disabled", blocked ? "true" : "false");
      btn.setAttribute(
        "title",
        blocked
          ? (spec.disabledTitle || "Quick Edit opens one rate card at a time.")
          : spec.label
      );
    });

    syncSelectionActionScroll(bar);
  }

  /* Published for v2.js, which renders the Rate Card Details line-item
   * table from its own module and mounts this same bar over it. Its
   * three actions differ from the list's five, but the markup, the count
   * sentence, the single-record gating, and the scrolling action strip
   * are all this component's. */
  window.createSelectionActionBar = createSelectionActionBar;
  window.applySelectionActionBarState = applySelectionActionBarState;
  window.ADS_ICON_EDIT = ICON_EDIT;
  window.ADS_ICON_COPY = ICON_COPY;
  window.ADS_ICON_TRASH = ICON_TRASH;
  window.ADS_ICON_DOWNLOAD = ICON_DOWNLOAD;

  function ensureSelectionActionBar() {
    var head = document.querySelector(".table__head");
    if (!head || !head.parentElement) return null;
    var existing = head.parentElement.querySelector("[data-selection-bar]");
    if (existing) return existing;

    var bar = createSelectionActionBar({
      onAction: function (spec, button) {
        /* Redline's specimen drives this very element through a preview
         * count, so a press during inspection must stop here rather
         * than reach a real rate card. */
        if (selectionSpecimenCount !== null) return;
        var cards = selectedRateCards();
        if (cards.length === 0) return;
        if (spec.singleOnly && cards.length !== 1) return;
        spec.run(cards, button);
      }
    });

    head.insertAdjacentElement("beforebegin", bar);
    return bar;
  }

  /* Safe to call after any render, selection change, or version switch. */
  function syncSelectionActionBar() {
    if (!isVersion21()) {
      /* Booting ?version=2.0 paints once under the 2.1 default before
       * applyVersion() switches, so a bar can already exist by the time
       * we land on a non-2.1 version. Drop it, so those versions end up
       * with no extra markup rather than an inert hidden node. */
      var stale = document.querySelector("[data-selection-bar]");
      if (stale) stale.remove();
      return;
    }
    var bar = ensureSelectionActionBar();
    if (!bar) return;
    var cards = selectedRateCards();
    /* A specimen count stands in for the selection size while Redline
     * is inspecting the component, so states that no page of real rows
     * could produce (a five figure count, for one) can still be seen. */
    applySelectionActionBarState(
      bar,
      selectionSpecimenCount === null ? cards.length : selectionSpecimenCount
    );
  }

  function clearRateCardSelection() {
    selectedRateCardIds.clear();
    paintRowSelection();
    syncSelectionActionBar();
  }

  /* ---- Bulk wrappers over the existing single-record handlers -------
   *
   * Each reuses the per-card function 2.0 already ships so permissions,
   * validation, persistence, and error handling stay in one place. Only
   * the success toast is collapsed into one summary line, because five
   * stacked "Archived X" toasts is worse than one "5 rate cards
   * archived." */
  function duplicateRateCards(cards) {
    if (cards.length === 1) {
      duplicateRateCard(cards[0]);
      return;
    }
    cards.forEach(function (card) { duplicateRateCard(card, { quiet: true }); });
    toastV12(
      { message: cards.length + " rate cards duplicated.", variant: "success" },
      "Duplicated " + cards.length + " rate cards"
    );
  }

  function archiveRateCards(cards) {
    if (cards.length === 1) {
      archiveRateCard(cards[0]);
      return;
    }
    var archived = 0;
    cards.forEach(function (card) {
      if (archiveRateCard(card, { quiet: true })) archived++;
    });
    if (archived === 0) return;
    toastV12(
      { message: archived + " rate cards archived.", variant: "success" },
      "Archived " + archived + " rate cards"
    );
  }

  /* Is an overlay genuinely on screen? Each cheaper test is wrong for at
   * least one overlay in this app: the delete modal hides via the hidden
   * attribute, the filter panel stays display:flex and hides with
   * visibility:hidden, and a visible position:fixed overlay reports no
   * offsetParent. So check layout boxes and the properties that hide an
   * element without removing its box. */
  function isOverlayVisible(node) {
    if (!node || node.getClientRects().length === 0) return false;
    var cs = getComputedStyle(node);
    return cs.visibility !== "hidden" && cs.opacity !== "0";
  }

  /* Escape clears the selection so the bar is dismissible by keyboard.
   * Guarded so it never competes with a modal, sheet, or popover that
   * owns Escape, and never fires while the user is typing. */
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    if (!isVersion21() || selectedRateCardIds.size === 0) return;
    /* closest() only exists on elements, and a keydown can be delivered
     * with document or a text node as its target. */
    var target = e.target;
    if (target && typeof target.closest === "function" && target.closest(
      "input, textarea, select, [contenteditable]:not([contenteditable='false'])"
    )) return;
    var blocking = Array.prototype.some.call(
      document.querySelectorAll("[role='dialog'], .qsheet, .modal"),
      isOverlayVisible
    );
    if (blocking) return;
    clearRateCardSelection();
  });

  function exportValue(value) {
    if (value == null) return "";
    var source = String(value);
    if (typeof value === "string" && /^[=+\-@]/.test(source)) source = "'" + source;
    return '"' + source.replace(/"/g, '""') + '"';
  }

  var RCM_CSV_HEADERS = [
    "ROW_TYPE", "ID", "RATE_CARD_ID", "RATE_CARD_NAME", "MARKETPLACE",
    "BUYING_ENTITY_SALESHUB_ID", "BUYING_ENTITY_DISPLAY_NAME", "DEAL_SEASON",
    "DCM_RULE_ORDER", "EFFECTIVE_START_DATE", "EFFECTIVE_END_DATE",
    "ADVERTISER_ID", "ADVERTISER_DISPLAY_NAME", "AD_TYPE", "BASE_OFFERING",
    "COST_METHOD", "BASE_RATE", "CURRENCY", "LINE_CONDITION",
    "PREMIUM_CATEGORY", "PREMIUM_DISPLAY_NAME", "CALCULATION_METHOD", "VALUE",
    "STACK_ORDER", "PREMIUM_CONDITION", "ATTACHED_LINE_IDS"
  ];

  function downloadCsv(filename, csv) {
    var blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    var url = URL.createObjectURL(blob);
    var anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(function () { URL.revokeObjectURL(url); }, 0);
  }

  function downloadBlankTemplate() {
    var csv = RCM_CSV_HEADERS.map(exportValue).join(",") + "\r\n";
    downloadCsv("rate-card-import-template.csv", csv);
    toastV12(
      { message: "Blank template downloaded.", variant: "success" },
      "Rate card import template downloaded."
    );
  }

  /* SECURITY-REVIEW: CSV files are user-controlled external data. The parser
   * applies size, row-count, header, enum, date, numeric, and relationship
   * allowlists before persisting any value. */
  function parseCsv(source) {
    var rows = [];
    var row = [];
    var field = "";
    var quoted = false;
    for (var index = 0; index < source.length; index += 1) {
      var char = source[index];
      if (quoted) {
        if (char === '"' && source[index + 1] === '"') {
          field += '"';
          index += 1;
        } else if (char === '"') {
          quoted = false;
        } else {
          field += char;
        }
      } else if (char === '"') {
        quoted = true;
      } else if (char === ",") {
        row.push(field);
        field = "";
      } else if (char === "\n") {
        row.push(field.replace(/\r$/, ""));
        if (row.some(function (value) { return value !== ""; })) rows.push(row);
        row = [];
        field = "";
      } else {
        field += char;
      }
    }
    if (quoted) throw new Error("The CSV contains an unclosed quoted value.");
    row.push(field.replace(/\r$/, ""));
    if (row.some(function (value) { return value !== ""; })) rows.push(row);
    return rows;
  }

  function normalizeImportMarketplace(value) {
    var source = String(value || "").trim().toUpperCase();
    if (source === "UPFRONT") return "Upfront";
    if (source === "SCATTER") return "Scatter";
    if (source === "MULTI-YEAR" || source === "MULTI YEAR") return "Multi-Year";
    return "";
  }

  function isIsoDate(value) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
    var date = new Date(value + "T00:00:00Z");
    return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value;
  }

  function importRateCardCsv(file) {
    if (!file) return;
    if (!/\.csv$/i.test(file.name || "")) {
      toastV12(
        { title: "Unable to import rate card", message: "Choose a CSV file.", variant: "error" },
        "Rate card import failed."
      );
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      toastV12(
        { title: "Unable to import rate card", message: "Choose a CSV smaller than 5 MB.", variant: "error" },
        "Rate card import failed."
      );
      return;
    }
    var reader = new FileReader();
    reader.onerror = function () {
      toastV12(
        { title: "Unable to import rate card", message: "The selected file could not be read.", variant: "error" },
        "Rate card import failed."
      );
    };
    reader.onload = function () {
      try {
        var parsed = parseCsv(String(reader.result || "").replace(/^\uFEFF/, ""));
        if (!parsed.length) throw new Error("The CSV is empty.");
        if (parsed.length > 10001) throw new Error("The CSV contains more than 10,000 data rows.");
        var headers = parsed.shift().map(function (header) {
          return String(header || "").trim().toUpperCase();
        });
        var missing = RCM_CSV_HEADERS.filter(function (header) {
          return headers.indexOf(header) < 0;
        });
        if (missing.length) {
          throw new Error("Missing required columns: " + missing.join(", ") + ".");
        }
        var records = parsed.map(function (values, rowIndex) {
          var record = { __row: rowIndex + 2 };
          headers.forEach(function (header, columnIndex) {
            record[header] = String(values[columnIndex] == null ? "" : values[columnIndex]).trim();
          });
          return record;
        });
        var errors = [];
        var files = {};
        var importedRows = 0;
        records.filter(function (record) {
          return record.ROW_TYPE.toUpperCase() === "CARD";
        }).forEach(function (record) {
          var cardId = record.RATE_CARD_ID || record.ID;
          var marketplace = normalizeImportMarketplace(record.MARKETPLACE);
          var validSeason = /^\d{4}-\d{4}$/.test(record.DEAL_SEASON);
          var validDates = isIsoDate(record.EFFECTIVE_START_DATE)
            && (!record.EFFECTIVE_END_DATE || isIsoDate(record.EFFECTIVE_END_DATE))
            && (!record.EFFECTIVE_END_DATE
              || record.EFFECTIVE_END_DATE >= record.EFFECTIVE_START_DATE);
          var ruleOrderValid = !record.DCM_RULE_ORDER
            || /^-?\d+$/.test(record.DCM_RULE_ORDER);
          if (!cardId || !record.RATE_CARD_NAME || !marketplace
              || !record.BUYING_ENTITY_SALESHUB_ID
              || !record.BUYING_ENTITY_DISPLAY_NAME || !validSeason
              || !validDates || !ruleOrderValid) {
            errors.push("Row " + record.__row + ": complete the required CARD fields and use valid enum, date, and integer values.");
            return;
          }
          if (files[cardId]) {
            errors.push("Row " + record.__row + ": RATE_CARD_ID must be unique within the CSV.");
            return;
          }
          files[cardId] = {
            version: 1,
            status: "Draft",
            card: {
              id: cardId,
              name: record.RATE_CARD_NAME,
              marketplace: marketplace,
              buyingEntityId: record.BUYING_ENTITY_SALESHUB_ID,
              buyingEntityName: record.BUYING_ENTITY_DISPLAY_NAME,
              dealSeason: record.DEAL_SEASON,
              dcmRuleOrder: record.DCM_RULE_ORDER ? Number(record.DCM_RULE_ORDER) : "",
              effectiveStart: record.EFFECTIVE_START_DATE,
              effectiveEnd: record.EFFECTIVE_END_DATE
            },
            lines: [],
            premiums: []
          };
          importedRows += 1;
        });
        records.filter(function (record) {
          return record.ROW_TYPE.toUpperCase() === "LINE";
        }).forEach(function (record) {
          var cardId = record.RATE_CARD_ID;
          var target = files[cardId];
          var rateValid = record.BASE_RATE !== ""
            && /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(record.BASE_RATE)
            && Number.isFinite(Number(record.BASE_RATE));
          var lineId = record.ID
            || cardId + "-LINE-" + String(target ? target.lines.length + 1 : 1).padStart(3, "0");
          if (!target || !record.ADVERTISER_ID || !record.AD_TYPE
              || !record.BASE_OFFERING || !record.COST_METHOD
              || !rateValid || !/^[A-Z]{3}$/.test(record.CURRENCY)
              || target.lines.some(function (line) { return line.id === lineId; })) {
            errors.push("Row " + record.__row + ": attach the LINE to a valid CARD and complete its advertiser, inventory, rate, and currency fields.");
            return;
          }
          target.lines.push({
            id: lineId,
            attachToCard: cardId,
            advertiserId: record.ADVERTISER_ID,
            advertiserName: record.ADVERTISER_DISPLAY_NAME,
            adProduct: record.AD_TYPE,
            baseOffering: record.BASE_OFFERING,
            rateType: record.COST_METHOD,
            baseRate: Number(record.BASE_RATE),
            currency: record.CURRENCY,
            condition1: record.LINE_CONDITION,
            updatedAt: new Date().toISOString()
          });
          importedRows += 1;
        });
        records.filter(function (record) {
          return record.ROW_TYPE.toUpperCase() === "PREM";
        }).forEach(function (record) {
          var cardId = record.RATE_CARD_ID;
          var target = files[cardId];
          var valueValid = record.VALUE !== ""
            && /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(record.VALUE)
            && Number.isFinite(Number(record.VALUE));
          var stackValid = !record.STACK_ORDER || /^-?\d+$/.test(record.STACK_ORDER);
          var methodValid = ["Additive CPM", "Flat Fee", "Percent Adjustment"]
            .indexOf(record.CALCULATION_METHOD) >= 0;
          var lineIds = record.ATTACHED_LINE_IDS.split("|").map(function (id) {
            return id.trim();
          }).filter(Boolean);
          var ownIds = new Set(target ? target.lines.map(function (line) { return line.id; }) : []);
          var relationshipsValid = lineIds.every(function (id) { return ownIds.has(id); });
          var premiumId = record.ID
            || cardId + "-PREM-" + String(target ? target.premiums.length + 1 : 1).padStart(3, "0");
          var datesInRange = !target || (
            (!record.EFFECTIVE_START_DATE
              || record.EFFECTIVE_START_DATE >= target.card.effectiveStart)
            && (!record.EFFECTIVE_END_DATE || !target.card.effectiveEnd
              || record.EFFECTIVE_END_DATE <= target.card.effectiveEnd)
            && (!record.EFFECTIVE_START_DATE || !record.EFFECTIVE_END_DATE
              || record.EFFECTIVE_END_DATE >= record.EFFECTIVE_START_DATE)
          );
          if (!target || !methodValid || !valueValid || !stackValid || !relationshipsValid
              || !datesInRange
              || target.premiums.some(function (premium) { return premium.id === premiumId; })
              || (record.EFFECTIVE_START_DATE && !isIsoDate(record.EFFECTIVE_START_DATE))
              || (record.EFFECTIVE_END_DATE && !isIsoDate(record.EFFECTIVE_END_DATE))) {
            errors.push("Row " + record.__row + ": attach the PREM to valid rows and use an approved calculation method, numeric value, and valid dates.");
            return;
          }
          target.premiums.push({
            id: premiumId,
            attachToCard: cardId,
            lineItemIds: lineIds,
            category: record.PREMIUM_CATEGORY,
            displayName: record.PREMIUM_DISPLAY_NAME,
            calculationMethod: record.CALCULATION_METHOD,
            value: Number(record.VALUE),
            stackOrder: record.STACK_ORDER ? Number(record.STACK_ORDER) : "",
            condition1: record.PREMIUM_CONDITION,
            effectiveStart: record.EFFECTIVE_START_DATE,
            effectiveEnd: record.EFFECTIVE_END_DATE
          });
          importedRows += 1;
        });
        records.filter(function (record) {
          return ["CARD", "LINE", "PREM"].indexOf(record.ROW_TYPE.toUpperCase()) < 0;
        }).forEach(function (record) {
          errors.push("Row " + record.__row + ": ROW_TYPE must be CARD, LINE, or PREM.");
        });
        if (!Object.keys(files).length) {
          throw new Error(errors[0] || "No valid CARD rows were found.");
        }
        var stored = {};
        try {
          stored = JSON.parse(window.localStorage.getItem("rate-card-manager.v2.files") || "{}");
        } catch (_) {}
        Object.keys(files).forEach(function (cardId) { stored[cardId] = files[cardId]; });
        window.localStorage.setItem("rate-card-manager.v2.files", JSON.stringify(stored));
        /* Land the user on their import.
         *
         * Selection is dropped first. Whatever was ticked before the
         * upload is not what was just imported, and leaving the bulk bar
         * standing over a refreshed table offers Archive and Delete on a
         * selection the user is no longer looking at. Clearing the set is
         * enough for the whole selection UI: renderTable() reads it while
         * building each row and re-syncs the header checkbox and the bar
         * on its way out.
         *
         * Sort and page go back to their defaults for the same reason.
         * activeRateCards() puts a card that exists only in storage at the
         * head of the list, so the unsorted first page is exactly where
         * the new file is; an active sort or a page-3 view would leave the
         * user staring at a success toast about rows they cannot see.
         *
         * Only reached on success: every failure path throws above this
         * and is handled by the catch below, which leaves the list and the
         * selection exactly as they were. */
        selectedRateCardIds.clear();
        sortState = null;
        page = 1;
        /* One synchronous render, reading storage back through
         * activeRateCards(), so the table swaps straight from the old
         * rows to the new ones with no empty frame in between and no
         * second pass over the CSV. */
        renderTable();
        var summary = importedRows + " row" + (importedRows === 1 ? "" : "s") + " imported.";
        if (errors.length) {
          summary += " " + errors.length + " row" + (errors.length === 1 ? "" : "s")
            + " need correction. " + errors.slice(0, 3).join(" ");
        }
        toastV12(
          {
            title: errors.length ? "Rate card imported with corrections needed" : "Rate card import complete",
            message: summary,
            variant: errors.length ? "warning" : "success"
          },
          summary
        );
      } catch (error) {
        toastV12(
          {
            title: "Unable to import rate card",
            message: error && error.message ? error.message : "Check the CSV and try again.",
            variant: "error"
          },
          "Rate card import failed."
        );
      }
    };
    reader.readAsText(file);
  }

  function openRateCardImport() {
    var input = document.createElement("input");
    input.type = "file";
    input.accept = ".csv,text/csv";
    input.hidden = true;
    input.setAttribute("aria-label", "Upload completed rate card CSV");
    input.addEventListener("change", function () {
      var file = input.files && input.files[0];
      input.remove();
      importRateCardCsv(file);
    }, { once: true });
    document.body.appendChild(input);
    input.click();
  }

  function getExportFile(row) {
    try {
      var files = JSON.parse(window.localStorage.getItem("rate-card-manager.v2.files") || "{}");
      if (files && files[row.rateCardId]) return files[row.rateCardId];
    } catch (_) {}
    var demo = window.RCMDemoRateCard;
    var demoFile = demo && typeof demo.getFile === "function"
      ? demo.getFile(row.rateCardId)
      : null;
    if (demoFile) return demoFile;
    var catalog = window.RCMCatalog;
    return catalog && typeof catalog.buildFile === "function"
      ? catalog.buildFile(row)
      : null;
  }

  /* Build one rate card's CARD + LINE + PREM lines in RCM template
   * order. Returns null when the card has nothing exportable, so both
   * the single and the multi-select export paths can share the row
   * builder and only differ in how they package and name the file. */
  function exportFileRows(row) {
    var file = getExportFile(row);
    if (!file || !file.card) return null;
    var headers = RCM_CSV_HEADERS;
    var rows = [];
    var card = file.card;
    function append(values) {
      rows.push(headers.map(function (header) {
        return exportValue(values[header]);
      }).join(","));
    }
    append({
      ROW_TYPE: "CARD",
      ID: card.id,
      RATE_CARD_ID: card.id,
      RATE_CARD_NAME: card.name,
      MARKETPLACE: card.marketplace,
      BUYING_ENTITY_SALESHUB_ID: card.buyingEntityId,
      BUYING_ENTITY_DISPLAY_NAME: card.buyingEntityName,
      DEAL_SEASON: card.dealSeason,
      DCM_RULE_ORDER: card.dcmRuleOrder,
      EFFECTIVE_START_DATE: card.effectiveStart,
      EFFECTIVE_END_DATE: card.effectiveEnd
    });
    (file.lines || []).forEach(function (line) {
      append({
        ROW_TYPE: "LINE",
        ID: line.id,
        RATE_CARD_ID: card.id,
        ADVERTISER_ID: line.advertiserId,
        ADVERTISER_DISPLAY_NAME: line.advertiserName,
        AD_TYPE: line.adProduct,
        BASE_OFFERING: line.baseOffering,
        COST_METHOD: line.rateType,
        BASE_RATE: line.baseRate,
        CURRENCY: line.currency,
        LINE_CONDITION: line.condition1
      });
    });
    (file.premiums || []).forEach(function (premium) {
      append({
        ROW_TYPE: "PREM",
        ID: premium.id,
        RATE_CARD_ID: card.id,
        PREMIUM_CATEGORY: premium.category,
        PREMIUM_DISPLAY_NAME: premium.displayName,
        CALCULATION_METHOD: premium.calculationMethod,
        VALUE: premium.value,
        STACK_ORDER: premium.stackOrder,
        PREMIUM_CONDITION: premium.condition1,
        EFFECTIVE_START_DATE: premium.effectiveStart,
        EFFECTIVE_END_DATE: premium.effectiveEnd,
        ATTACHED_LINE_IDS: (premium.lineItemIds || []).join("|")
      });
    });
    return { card: card, rows: rows };
  }

  /* The v2.1 edit page exports a subset of one rate card (the premiums a
   * user has checked) rather than whole cards, so it composes rows with
   * these three primitives instead of carrying its own CSV writer. Same
   * headers, same escaping, same download path as the list page. */
  window.RCM_CSV_HEADERS = RCM_CSV_HEADERS;
  window.rcmExportValue = exportValue;
  window.rcmDownloadCsv = downloadCsv;

  function rcmCsv(dataRows) {
    return RCM_CSV_HEADERS.map(exportValue).join(",") + "\r\n"
      + dataRows.join("\r\n") + "\r\n";
  }

  function exportRateCard(row) {
    var built = exportFileRows(row);
    if (!built) {
      toastV12(
        { title: "Unable to export rate card", message: "Try again.", variant: "error" },
        "Unable to export rate card."
      );
      return;
    }
    downloadCsv(
      "rate-card-" + String(built.card.id).replace(/[^A-Za-z0-9_-]/g, "_") + ".csv",
      rcmCsv(built.rows)
    );
    toastV12(
      { message: "Rate card exported.", variant: "success" },
      'Exported "' + built.card.name + '"'
    );
  }

  /* Multi-select export produces ONE file, not one download per row. A
   * Rate Card File in the RCM template is defined as many CARD rows
   * plus their LINE and PREM rows (PRD R1), so the whole selection is a
   * single valid file and re-imports as one. */
  function exportRateCards(cards) {
    if (cards.length === 1) {
      exportRateCard(cards[0]);
      return;
    }
    var dataRows = [];
    var exported = 0;
    cards.forEach(function (card) {
      var built = exportFileRows(card);
      if (!built) return;
      dataRows = dataRows.concat(built.rows);
      exported++;
    });
    if (exported === 0) {
      toastV12(
        { title: "Unable to export rate cards", message: "Try again.", variant: "error" },
        "Unable to export rate cards."
      );
      return;
    }
    downloadCsv("rate-cards-" + exported + ".csv", rcmCsv(dataRows));
    toastV12(
      { message: exported + " rate cards exported.", variant: "success" },
      "Exported " + exported + " rate cards"
    );
  }

  /* Returns whether the row was archived, so the 2.1 bulk wrapper can
   * report how many of the selected rows actually made it. `quiet`
   * suppresses only the success toast; failures always speak up. */
  function archiveRateCard(row, options) {
    var quiet = !!(options && options.quiet);
    var ids = readArchivedIds();
    ids.push(String(row.id));
    if (!writeArchivedIds(ids)) {
      toastV12(
        { title: "Unable to archive rate card", message: "Try again.", variant: "error" },
        "Unable to archive rate card."
      );
      return false;
    }
    selectedRateCardIds.delete(String(row.id));
    renderTable();
    if (!quiet) {
      toastV12(
        { message: "Rate card archived.", variant: "success" },
        'Archived "' + row.name + '"'
      );
    }
    return true;
  }

  /* Status chip variants per Figma 157:1980 (Published) + 157:2008
   * (Draft). The PRD restricts the Rate Card Manager Status column to
   * exactly two visible labels: Published and Draft. Any other status
   * value (Active, Pending Review, Archived, ACTIVE, draft, ...) is
   * passed through normalizeStatus() first so we never paint an
   * unsupported chip into the DOM.
   *
   * normalizeStatus is centralised so the seed data, hydrate-from-
   * localStorage, save flow, duplicate flow, and any future import
   * flow all converge on the same two strings before reaching this
   * function. */
  function buildChip(status) {
    var visible = normalizeStatus(status);
    var variantKey = visible.toLowerCase();
    /* Render the status chip with the Rate Card Manager's custom
     * chip styling (Figma 157:1980 / 157:2008). The .rcm-status-chip
     * class scopes the Figma chip tokens to the Manager table so we
     * don't accidentally restyle .chip globally. variantKey is one
     * of "published" or "draft" only. */
    return el("span", "chip rcm-status-chip rcm-status-chip--" + variantKey + " chip--" + variantKey, visible);
  }

  /* Build a 32x32 ADS row-action icon button.
   *
   * `label` is used both as the accessible name (aria-label) AND as the
   * ADS tooltip text shown on hover / keyboard focus. We deliberately do
   * NOT set a native `title` attribute - the brief forbids the default
   * black browser tooltip, and the ADS tooltip controller in this file
   * picks up the [data-tooltip] attribute instead. */
  function buildIconButton(svgString, label, onClick) {
    const btn = el("button", "icon-btn");
    btn.type = "button";
    btn.setAttribute("aria-label", label);
    btn.setAttribute("data-tooltip", label);
    btn.innerHTML = svgString;
    btn.addEventListener("click", onClick);
    return btn;
  }

  // Pagination per Figma node 49:5940. Four chevron icon kinds + page-number
  // pills + ellipsis. Active page = small indigo underline bar under a still-
  // dark number (NOT recolored), matching the Figma "Pagination Number" component.
  //
  // Chevrons are 16×16 Feather icons embedded as inline SVG so they render at
  // the documented Figma size, not Unicode glyphs (which collapsed to ~10px).

  // 16×16 Feather chevron paths. `currentColor` lets CSS control color
  // (indigo when enabled, 40% opacity when disabled) without re-drawing.
  const CHEV_PATHS = {
    first: '<path d="M11 13L6 8l5-5M14 13L9 8l5-5" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
    back:  '<path d="M10 13L5 8l5-5" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
    next:  '<path d="M6 13l5-5-5-5" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
    last:  '<path d="M5 13l5-5-5-5M2 13l5-5-5-5" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
  };

  function renderPager(host, currentPage, pageCount) {
    host.replaceChildren();
    const makeNum = (n) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "page-btn page-btn--num";
      // Page-number buttons display the digit visibly ("1", "2", ...)
      // and the aria-label below carries the screen-reader context.
      // No tooltip needed - tooltip would be redundant ("Page 1" on
      // top of a "1" button reads as visual noise on hover).
      b.setAttribute("aria-label", "Page " + n);
      b.textContent = String(n);
      if (n === currentPage) {
        b.classList.add("is-active");
        b.setAttribute("aria-current", "page");
      }
      b.addEventListener("click", () => {
        page = n;
        renderTable();
      });
      return b;
    };
    const makeChevron = (kind, target, disabled, title) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "page-btn page-btn--chevron";
      /* ADS Tooltip on the icon-only chevron buttons - same pattern
       * as buildIconButton (table actions). aria-label still owns the
       * accessible name; data-tooltip carries the visible hover text.
       * We deliberately do NOT set b.title (would render the browser's
       * native tooltip which is forbidden by the brief). */
      b.setAttribute("aria-label", title);
      b.setAttribute("data-tooltip", title);
      b.innerHTML = `<svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">${CHEV_PATHS[kind]}</svg>`;
      if (disabled) {
        b.disabled = true;
        b.setAttribute("aria-disabled", "true");
      }
      b.addEventListener("click", () => {
        if (disabled) return;
        page = target;
        renderTable();
      });
      return b;
    };
    const ellipsis = () => {
      const s = document.createElement("span");
      s.className = "page-ellipsis";
      s.textContent = "…";
      s.setAttribute("aria-hidden", "true");
      return s;
    };

    const canPrev = currentPage > 1;
    const canNext = currentPage < pageCount;

    /* ADS Pagination per Figma 142:4070 renders the cells as a flat row:
     *   [prev chevron] [1] [2] [3] ... [N] [next chevron]
     * Items are 36 x 36 with 4px gap between them. No first/last chevrons.
     * The host (.footer__pager) is itself a flex row that holds the
     * chevrons + number cells directly. */
    host.appendChild(makeChevron("back", currentPage - 1, !canPrev, "Previous page"));

    if (pageCount <= 5) {
      for (let p = 1; p <= pageCount; p++) host.appendChild(makeNum(p));
    } else {
      for (let p = 1; p <= 3; p++) host.appendChild(makeNum(p));
      host.appendChild(ellipsis());
      host.appendChild(makeNum(pageCount));
    }

    host.appendChild(makeChevron("next", currentPage + 1, !canNext, "Next page"));
  }

  /* ====================== ADS TOOLTIP CONTROLLER ===========================
   *
   * Single-instance tooltip system - one DOM element rendered to <body>
   * (escapes overflow:hidden on the table card) is shown / hidden / moved
   * to track whichever element currently has hover or keyboard focus and
   * carries a [data-tooltip="..."] attribute.
   *
   * Triggers:
   *   - mouseenter / mouseleave (hover)
   *   - focus / blur            (keyboard)
   *   - Escape key              (hide while focus-shown)
   *
   * Placement:
   *   - Default: 'top' (tooltip ABOVE the trigger, arrow points DOWN).
   *     Matches the brief - keeps the tooltip out of the table row below.
   *   - Flip to 'bottom' when there isn't enough room above (e.g. trigger
   *     near the top of the viewport).
   *   - Horizontal clamping keeps the tooltip inside the viewport with an
   *     8px gutter. The arrow stays centered under the trigger (CSS
   *     `left: 50%`), even when the tooltip itself shifts.
   *
   * Important: We DO NOT set `title=...` on triggers. The native browser
   * tooltip races visually with the ADS tooltip. We rely on aria-label for
   * accessibility (already set on every trigger) and [data-tooltip] for
   * the ADS treatment.
   * ===================================================================== */

  /* Gap between trigger and tooltip frame (ADS spacing). */
  var ADS_TT_GAP = 8;
  var ADS_TT_OPEN_DELAY = 300;
  var adsTooltipOpenTimer = 0;
  var adsTooltipPendingTrigger = null;
  var adsTooltipActiveTrigger = null;

  function adsTooltipShow(trigger) {
    var tip = document.querySelector("[data-ads-tooltip]");
    if (!tip || !trigger) return;
    /* Two ways to source the tooltip text:
     *   1. data-tooltip="..."           static label baked into markup.
     *   2. data-tooltip-from-value      dynamic label read from the
     *                                   trigger's .value on demand.
     *
     * (2) exists for editable / read-only <input> fields (e.g. the
     * Rate card name input on the Edit form and the RCLE overlay)
     * whose value is user-editable or programmatically prefilled at
     * runtime. Reading .value on show means the tooltip always
     * reflects the CURRENT field value without any need to keep a
     * data-tooltip attribute in sync via input listeners or observer.
     * Empty values short-circuit before we render, so a blank field
     * never opens an empty tooltip. */
    var label;
    if (trigger.getAttribute("data-tooltip-from-value") === "true" &&
        (trigger.tagName === "INPUT" || trigger.tagName === "TEXTAREA")) {
      label = trigger.value || "";
    } else {
      label = trigger.getAttribute("data-tooltip");
    }
    if (!label) return;
    /* Truncation gate: triggers marked data-tooltip-truncate="auto"
     * only show the tooltip when the trigger's content overflows its
     * visible box. Used by table cells / Name links / Quick Edit
     * cells that use text-overflow:ellipsis so we don't render a
     * noisy hover tooltip on rows where the value already fits.
     *
     * Detection: scrollWidth > clientWidth + 1px slack (sub-pixel
     * rounding can falsely report 1px overflow on Retina screens).
     * Skip the gate if the trigger doesn't have measurable overflow
     * geometry (e.g. inline-only elements). */
    if (trigger.getAttribute("data-tooltip-truncate") === "auto") {
      // For <a> children inside a flex cell, measure the link itself.
      var measureEl = trigger;
      var overflow = measureEl.scrollWidth - measureEl.clientWidth;
      /* A cell whose value sits in a child that does its own
       * ellipsizing never overflows itself: the child absorbs the
       * clipping, so that is where the truncation shows up.
       *
       * Every child is measured, not just an only child: a dropdown
       * trigger holds its clipping value span next to a fixed-width
       * caret, so the value is the one that runs out of room while the
       * trigger and the caret never do. */
      if (overflow <= 1 && trigger.children.length) {
        overflow = Array.prototype.reduce.call(
          trigger.children,
          function (widest, child) {
            return Math.max(widest, child.scrollWidth - child.clientWidth);
          },
          overflow
        );
      }
      if (overflow <= 1) return;
    }

    var lbl = tip.querySelector("[data-ads-tooltip-label]");
    if (lbl) lbl.textContent = label;

    /* Reveal the element before measuring so getBoundingClientRect works,
     * but keep it invisible (opacity 0) until we know the final position
     * to avoid a one-frame "snap" at the wrong coordinates. */
    tip.hidden = false;
    tip.setAttribute("aria-hidden", "false");
    tip.style.visibility = "hidden";
    tip.style.opacity = "0";
    tip.removeAttribute("data-ads-tt-visible");
    /* Reset placement so width/height measurements are clean. */
    tip.setAttribute("data-ads-tt-placement", "top");

    /* Force layout, then measure. */
    var tipRect = tip.getBoundingClientRect();
    var tw = tipRect.width;
    var th = tipRect.height;
    var tRect = trigger.getBoundingClientRect();
    var vw = document.documentElement.clientWidth || window.innerWidth;
    var vh = document.documentElement.clientHeight || window.innerHeight;
    var gutter = 8;

    /* Vertical placement: prefer above; flip below if not enough room. */
    var placement = "top";
    var top = tRect.top - th - ADS_TT_GAP;
    if (top < gutter) {
      placement = "bottom";
      top = tRect.bottom + ADS_TT_GAP;
    }
    /* Horizontal: center on the trigger, then clamp to viewport gutter. */
    var triggerCenterX = tRect.left + tRect.width / 2;
    var left = triggerCenterX - tw / 2;
    left = Math.max(gutter, Math.min(left, vw - tw - gutter));

    tip.style.top = Math.round(top) + "px";
    tip.style.left = Math.round(left) + "px";
    tip.setAttribute("data-ads-tt-placement", placement);

    /* Position the arrow to point at the trigger center even when the
     * tooltip is clamped left/right against the viewport edge. */
    var arrow = tip.querySelector(".ads-tt__arrow");
    if (arrow) {
      var arrowOffset = triggerCenterX - left;
      /* Keep the arrow within the tooltip frame (4px gutters). */
      arrowOffset = Math.max(8, Math.min(arrowOffset, tw - 8));
      arrow.style.left = Math.round(arrowOffset) + "px";
      arrow.style.marginLeft = "-4px";
    }

    /* Reveal. */
    tip.style.visibility = "";
    tip.style.opacity = "";
    /* requestAnimationFrame so the CSS transition fires. */
    requestAnimationFrame(function(){
      tip.setAttribute("data-ads-tt-visible", "true");
    });
    adsTooltipActiveTrigger = trigger;
  }

  function adsTooltipHide() {
    if (adsTooltipOpenTimer) {
      clearTimeout(adsTooltipOpenTimer);
      adsTooltipOpenTimer = 0;
    }
    adsTooltipPendingTrigger = null;
    adsTooltipActiveTrigger = null;
    var tip = document.querySelector("[data-ads-tooltip]");
    if (!tip) return;
    tip.removeAttribute("data-ads-tt-visible");
    /* Wait for the close transition then unhide-clean. */
    setTimeout(function(){
      if (tip.getAttribute("data-ads-tt-visible") !== "true") {
        tip.hidden = true;
        tip.setAttribute("aria-hidden", "true");
      }
    }, 130);
  }

  function adsTooltipScheduleShow(trigger) {
    if (!trigger) return;
    if (adsTooltipOpenTimer) clearTimeout(adsTooltipOpenTimer);
    if (adsTooltipActiveTrigger && adsTooltipActiveTrigger !== trigger) {
      adsTooltipHide();
    }
    adsTooltipPendingTrigger = trigger;
    adsTooltipOpenTimer = setTimeout(function () {
      adsTooltipOpenTimer = 0;
      if (adsTooltipPendingTrigger !== trigger || !document.contains(trigger)) return;
      adsTooltipPendingTrigger = null;
      adsTooltipShow(trigger);
    }, ADS_TT_OPEN_DELAY);
  }

  /* Returns the trigger element under an event target, if it (or any
   * ancestor) carries [data-tooltip] OR [data-tooltip-from-value].
   *
   * The two attributes describe how the tooltip text is sourced:
   *   [data-tooltip]              static string baked into markup.
   *   [data-tooltip-from-value]   dynamic string read from the
   *                               trigger's .value on show (used by
   *                               editable / read-only <input> fields
   *                               like the Rate card name input on
   *                               the Edit form and the RCLE overlay).
   * Both must count as valid triggers here so hover / focus reach
   * adsTooltipShow, which then picks the right source. */
  function adsTooltipFindTrigger(node) {
    if (!(node instanceof Element)) return null;
    return node.closest("[data-tooltip], [data-tooltip-from-value]");
  }

  // ----- Toast --------------------------------------------------------------
  //
  // ADS Toast per Figma DJb3yM8aOQjIAbTQ9Cd8Mi node 70:62.
  //
  // API (backwards-compatible with all pre-existing toast(msg) callers):
  //   toast("Some message")                       // info variant, message only
  //   toast("Message", {title: "Rate card saved",  // full ADS layout
  //                    variant: "success"})
  //   toast({title, message, variant, duration})  // fully-opts form
  //
  // Variant sets the left-accent color, icon glyph, and title text color.
  // The close button is always neutral (ADS rule). Auto-dismiss defaults
  // to 25s; pass duration:0 to disable auto-dismiss (manual close only).
  const TOAST_DEFAULT_DURATION = 25000;
  const TOAST_ICONS = {
    /* All four Feather-style 24x24 glyphs. currentColor lets the icon
     * inherit the variant's accent color from the CSS variant rules. */
    success:
      '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" ' +
      'stroke="currentColor" stroke-width="2" stroke-linecap="round" ' +
      'stroke-linejoin="round" aria-hidden="true">' +
      '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/></svg>',
    info:
      '<img src="./assets/ads-toast-info.svg" alt="" width="19.5" height="19.5">',
    warning:
      '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" ' +
      'stroke="currentColor" stroke-width="2" stroke-linecap="round" ' +
      'stroke-linejoin="round" aria-hidden="true">' +
      '<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 ' +
      '1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>' +
      '<line x1="12" y1="9" x2="12" y2="13"/>' +
      '<line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
    error:
      '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" ' +
      'stroke="currentColor" stroke-width="2" stroke-linecap="round" ' +
      'stroke-linejoin="round" aria-hidden="true">' +
      '<circle cx="12" cy="12" r="10"/>' +
      '<line x1="15" y1="9" x2="9" y2="15"/>' +
      '<line x1="9" y1="9" x2="15" y2="15"/></svg>',
  };

  /* Stack container - fixed at top-right of the viewport (see
   * .ads-toast-stack CSS). Each toast() call PREPENDS a new element
   * so the newest toast sits at the top with 8px gap between siblings,
   * per the 2026-07-07 placement brief. Every toast owns its own
   * auto-dismiss timer stashed on the element (element.__timer) so
   * concurrent toasts don't interfere with each other's lifecycle. */
  function toast(msgOrOpts, opts) {
    var cfg = {};
    if (typeof msgOrOpts === "string") {
      cfg.message = msgOrOpts;
      cfg.title = (opts && opts.title) || "";
      cfg.variant = (opts && opts.variant) || "info";
      cfg.duration = (opts && typeof opts.duration === "number")
        ? opts.duration : TOAST_DEFAULT_DURATION;
    } else {
      var o = msgOrOpts || {};
      cfg.message = o.message || "";
      cfg.title = o.title || "";
      cfg.variant = o.variant || "info";
      cfg.duration = (typeof o.duration === "number")
        ? o.duration : TOAST_DEFAULT_DURATION;
    }

    var stack = document.querySelector("[data-toast-stack]");
    if (!stack) return null;

    /* Build a fresh toast element for this call so multiple toasts
     * can co-exist. Structure mirrors the previous singleton template
     * (icon slot, body with title + message, neutral close X) so all
     * existing CSS variant + empty-collapse rules keep working. */
    var t = document.createElement("div");
    t.className = "ads-toast";
    t.setAttribute("data-toast", "");
    t.setAttribute("data-variant", cfg.variant);
    t.setAttribute("role", "status");
    t.setAttribute("aria-atomic", "true");
    /* aria-live semantics: polite for info/success (announce when the
     * screen reader is idle), assertive for warning/error. Setting it
     * BEFORE injecting content ensures AT sees the initial text as
     * part of the live-region announcement. */
    t.setAttribute("aria-live",
      (cfg.variant === "warning" || cfg.variant === "error") ? "assertive" : "polite");

    var iconEl = document.createElement("span");
    iconEl.className = "ads-toast__icon";
    iconEl.setAttribute("data-toast-icon", "");
    iconEl.setAttribute("aria-hidden", "true");
    iconEl.innerHTML = TOAST_ICONS[cfg.variant] || "";

    var bodyEl = document.createElement("div");
    bodyEl.className = "ads-toast__body";
    var titleEl = document.createElement("p");
    titleEl.className = "ads-toast__title";
    titleEl.setAttribute("data-toast-title", "");
    titleEl.textContent = cfg.title;
    var msgEl = document.createElement("p");
    msgEl.className = "ads-toast__message";
    msgEl.setAttribute("data-toast-message", "");
    msgEl.textContent = cfg.message;
    bodyEl.appendChild(titleEl);
    bodyEl.appendChild(msgEl);

    var closeEl = document.createElement("button");
    closeEl.type = "button";
    closeEl.className = "ads-toast__close";
    closeEl.setAttribute("data-action", "close-toast");
    closeEl.setAttribute("aria-label", "Dismiss notification");
    closeEl.innerHTML = '<span class="ads-toast__close-icon" aria-hidden="true"></span>';

    t.appendChild(iconEl);
    t.appendChild(bodyEl);
    t.appendChild(closeEl);

    /* Prepend so the newest toast is at the TOP of the stack. */
    stack.prepend(t);

    /* Each toast owns its countdown, so one toast being dismissed or
     * held open never touches another's. Hovering or focusing banks
     * the time left and resumes from there, and because a pointer and
     * the keyboard can hold the same toast at once, both have to let
     * go before the clock restarts. */
    t.__duration = cfg.duration;
    t.__remaining = cfg.duration;
    t.__startedAt = 0;
    t.__hovered = false;
    t.__focused = false;
    function startTimer() {
      if (t.__duration <= 0 || t.__remaining <= 0 || t.__timer) return;
      if (t.__hovered || t.__focused) return;
      t.__startedAt = Date.now();
      t.__timer = setTimeout(function () {
        t.__timer = null;
        dismissToast(t);
      }, t.__remaining);
    }
    function pauseTimer() {
      if (!t.__timer) return;
      clearTimeout(t.__timer);
      t.__timer = null;
      t.__remaining = Math.max(0, t.__remaining - (Date.now() - t.__startedAt));
    }
    t.addEventListener("pointerenter", function () {
      t.__hovered = true;
      pauseTimer();
    });
    t.addEventListener("pointerleave", function () {
      t.__hovered = false;
      startTimer();
    });
    t.addEventListener("focusin", function () {
      t.__focused = true;
      pauseTimer();
    });
    t.addEventListener("focusout", function (event) {
      if (t.contains(event.relatedTarget)) return;
      t.__focused = false;
      startTimer();
    });
    requestAnimationFrame(function () {
      t.classList.add("is-visible");
      startTimer();
    });
    return t;
  }

  /* Detach a toast and tear down everything it owns. Every removal
   * path funnels through here so a node can never leave the DOM with a
   * live timer still pointed at it. */
  function removeToastNode(target) {
    if (!target) return;
    if (target.__timer) { clearTimeout(target.__timer); target.__timer = null; }
    if (target.__exitTimer) { clearTimeout(target.__exitTimer); target.__exitTimer = null; }
    if (target.parentNode) target.parentNode.removeChild(target);
  }

  /* How long the current version's exit styling actually runs. The
   * dismiss used to wait on animationend alone, which assumed every
   * version defines an exit animation. v1.0, v1.1 and v1.2 never did,
   * so the event never fired, the node was never detached, and the
   * toast sat on screen forever wearing .is-dismissing. Reading the
   * real duration lets the removal be scheduled instead of hoped for,
   * and it stays correct if the motion is retuned in CSS. */
  function toastExitDuration(target) {
    var style = window.getComputedStyle(target);
    function longest(value) {
      return (value || "").split(",").reduce(function (max, part) {
        var seconds = parseFloat(part) || 0;
        if (/ms\s*$/.test(part.trim())) seconds = seconds / 1000;
        return Math.max(max, seconds);
      }, 0);
    }
    var animation = longest(style.animationDuration) + longest(style.animationDelay);
    var transition = longest(style.transitionDuration) + longest(style.transitionDelay);
    return Math.max(animation, transition) * 1000;
  }

  /* Keyboard focus has to land somewhere deliberate when the control
   * the user just activated disappears under them. The next toast is
   * the closest equivalent; with the stack empty there is nothing
   * toast-shaped left, so focus goes to the page region without
   * scrolling it. Only manual dismissal calls this: an auto-dismiss
   * must never move focus out from under someone. */
  function restoreFocusAfterToast(target) {
    if (!target.contains(document.activeElement)) return;
    var sibling = target.nextElementSibling || target.previousElementSibling;
    var nextClose = sibling && sibling.querySelector('[data-action="close-toast"]');
    if (nextClose) { nextClose.focus(); return; }
    var page = document.querySelector("main.page") || document.body;
    if (page === document.body) { document.activeElement.blur(); return; }
    page.setAttribute("tabindex", "-1");
    page.focus({ preventScroll: true });
    page.addEventListener("blur", function () {
      page.removeAttribute("tabindex");
    }, { once: true });
  }

  /* A toast leaving the flex column takes its own height and one gap
   * with it, so the toasts below it snap upward the instant the node
   * detaches. Measuring both up front lets the exit animate them down
   * to zero, which turns that snap into part of the same motion as the
   * fade. The gap is read from the stack because each version sets its
   * own, and a lone toast is charged no gap because it never had a
   * neighbour to be separated from. */
  function measureToastCollapse(target) {
    var stack = target.parentNode;
    if (!stack) return;
    var gap = stack.children.length > 1
      ? (parseFloat(window.getComputedStyle(stack).rowGap) || 0)
      : 0;
    target.style.setProperty("--ads-toast-gap", gap + "px");
    target.style.setProperty("--ads-toast-height", target.offsetHeight + "px");
  }

  /* Manual dismiss. Two shapes:
   *   - dismissToast()            -> dismiss the OLDEST live toast
   *                                  (backward-compat with prior
   *                                  singleton behavior + QA hooks).
   *   - dismissToast(element)     -> dismiss that specific toast.
   * Cancels that toast's own auto-dismiss timer and leaves every other
   * toast's timer running. Idempotent, and safe on detached nodes. */
  function dismissToast(el, options) {
    var stack = document.querySelector("[data-toast-stack]");
    var target = null;
    if (el && el.nodeType === 1) {
      target = el;
    } else if (stack) {
      /* Oldest = last child (because we prepend newest to the top). */
      target = stack.lastElementChild;
    }
    if (!target || target.classList.contains("is-dismissing")) return;
    if (target.__timer) { clearTimeout(target.__timer); target.__timer = null; }
    if (options && options.manual) restoreFocusAfterToast(target);

    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      removeToastNode(target);
      return;
    }

    /* Order matters: the height has to be measured and locked before
     * the collapse starts, or the transition runs from `auto` and the
     * stack jumps anyway. */
    measureToastCollapse(target);
    target.classList.add("is-dismissing");
    void target.offsetHeight;
    target.classList.add("is-collapsing");
    target.addEventListener("animationend", function () {
      removeToastNode(target);
    }, { once: true });
    /* Backstop for the cases animationend cannot cover: a version with
     * no exit animation, a toast animating while the tab is hidden, or
     * the collapse outlasting the fade. */
    target.__exitTimer = setTimeout(function () {
      removeToastNode(target);
    }, toastExitDuration(target) + 60);
  }

  /* Safety net for removals that bypass dismissToast: a stack wiped by
   * the gallery, a node pulled by a future caller, or the page going
   * away. Without this a pending 25s timer would keep a detached node
   * alive and then fire against nothing. */
  (function watchToastRemoval() {
    var stack = document.querySelector("[data-toast-stack]");
    if (!stack || typeof MutationObserver !== "function") return;
    new MutationObserver(function (records) {
      records.forEach(function (record) {
        Array.prototype.forEach.call(record.removedNodes, function (node) {
          if (node.nodeType !== 1) return;
          if (node.__timer) { clearTimeout(node.__timer); node.__timer = null; }
          if (node.__exitTimer) { clearTimeout(node.__exitTimer); node.__exitTimer = null; }
        });
      });
    }).observe(stack, { childList: true });
    window.addEventListener("pagehide", function () {
      Array.prototype.forEach.call(stack.querySelectorAll("[data-toast]"), removeToastNode);
    });
  })();

  /* Test affordance: expose the toast primitives on window so QA
   * scripts can drive the exact same success/error surface the click
   * handler drives, without needing to fill every LINE + PREM field to
   * satisfy validateForm. Follows the existing RATE_CARDS pattern
   * above (non-enumerable + read-only property) so these hooks stay
   * out of accidental for-in iteration but remain callable from the
   * DevTools Runtime.evaluate channel. */
  try {
    Object.defineProperty(window, "toast", {
      value: toast, writable: false, enumerable: false, configurable: false
    });
    Object.defineProperty(window, "dismissToast", {
      value: dismissToast, writable: false, enumerable: false, configurable: false
    });
  } catch (e) { /* property may already exist if app re-inits */ }

  /* -----------------------------------------------------------------
   * toastV12(v12Config, legacyMessage, legacyOpts?)
   * -----------------------------------------------------------------
   * v1.2-only ADS toast routing per the 2026-07-09 restyle brief.
   *
   * On v1.2: fires the ADS-compliant toast (correct variant + copy
   *          from the PM's action-to-toast mapping).
   * On v1.0 / v1.1: fires the legacy toast(msg, opts) as before so
   *          older versions render byte-for-byte identically.
   *
   * v12Config = {
   *   message:  string,                        // ADS copy per brief
   *   variant:  "success"|"info"|"warning"|"error",
   *   title:    string (optional),             // ADS headline row
   *   duration: number (optional, ms)          // 0 = manual dismiss
   * }
   *
   * Keeps each call site short + readable while preserving legacy
   * behavior. Every existing toast(...) caller migrates to this shape
   * so v1.1 users don't see the copy churn.
   * ----------------------------------------------------------------- */
  function toastV12(v12Config, legacyMessage, legacyOpts) {
    var isV12 = isModernAppVersion(document.body.getAttribute("data-version"));
    if (isV12 && v12Config && v12Config.message) {
      var opts = { variant: v12Config.variant || "info" };
      if (v12Config.title)    opts.title    = v12Config.title;
      if (typeof v12Config.duration === "number") opts.duration = v12Config.duration;
      return toast(v12Config.message, opts);
    }
    return toast(legacyMessage, legacyOpts);
  }
  try {
    Object.defineProperty(window, "toastV12", {
      value: toastV12, writable: false, enumerable: false, configurable: false
    });
  } catch (e) { /* already defined on hot reload */ }

  // ----- Delete modal -------------------------------------------------------

  /* Accepts a single row id, or an array of ids from the 2.1 action bar.
   * The modal, its confirm button, its toast, and its focus handling are
   * shared: only the summary line changes, so a multi-row delete is
   * still one confirmation the user has to read. */
  /* ===================================================================
   *  CREATE RATE CARD MODAL
   *  (Figma 643:63052 collapsed, 639:61405 expanded)
   *
   *  Naming a rate card is now a dialog rather than a whole page. The
   *  modal collects the one required field, plus the optional CARD
   *  details behind a disclosure, and on Confirm it creates the Draft
   *  and hands the user to the shared Rate Card Details page in edit
   *  mode. That is what lets new and existing cards use one layout:
   *  the details page always opens against a real, named record, so the
   *  stripped-down "initial" workspace state is never reached from
   *  here.
   *
   *  Everything inside the dialog is an existing app primitive. The two
   *  selects are .edl-select and the two dates are .ads-datepicker, both
   *  driven by the delegated handlers the Create page already uses, so
   *  no second implementation of either control exists.
   * =================================================================== */
  var rcCreateReturnFocus = null;
  /* "" while creating, or the id of the rate card being edited. The
   * Rate Card Details page reuses this dialog as its CARD editor
   * (Figma 644:67882), so one dialog serves both jobs. */
  var rcEditCardId = "";

  function rcCreateModal() {
    return document.querySelector("[data-rc-create-modal]");
  }

  function isRcCreateOpen() {
    var modal = rcCreateModal();
    return Boolean(modal && !modal.hidden);
  }

  /* The dialog's own fields, read with the same shape collectForm()
   * returns for the Create page so both feed commitFormToTable
   * unchanged. Scoped to the modal because the page form uses the same
   * data-field names for Marketplace and Deal Season. */
  function collectRcCreateForm() {
    var modal = rcCreateModal();
    if (!modal) return {};
    var val = function (sel) {
      var node = modal.querySelector(sel);
      return node ? String(node.value).trim() : "";
    };
    var picked = function (field) {
      var node = modal.querySelector(
        '.ads-datepicker[data-field="' + field + '"] .ads-datepicker__value');
      if (!node || node.classList.contains("ads-datepicker__value--placeholder")) return "";
      return node.textContent.trim();
    };
    var chosen = function (field) {
      var node = modal.querySelector('.edl-select[data-field="' + field + '"]');
      return node ? node.getAttribute("data-value") || "" : "";
    };
    return {
      rateCardId: normalizeRateCardId(val("[data-rcm-card-id]")),
      name: val("#rcm-name"),
      buyingEntityId: val("#rcm-be-id"),
      buyingEntityName: val("#rcm-be-name"),
      marketplace: chosen("marketplace"),
      season: chosen("season"),
      dcmRuleOrder: val("#rcm-dcm-rule"),
      effectiveStart: picked("rcm-eff-start"),
      effectiveEnd: picked("rcm-eff-end")
    };
  }

  /* ---- Rate Card ID -------------------------------------------------
   * The ID is typed by the user and is what CSV imports and later
   * updates match a rate card on, so it has to be unique and it has to
   * survive round-tripping through a file name and a URL. That is the
   * whole reason for the character rule: letters, numbers, hyphens and
   * underscores only. */
  var RC_ID_ALLOWED = /^[A-Za-z0-9_-]+$/;
  var RC_ID_MESSAGES = {
    empty: "Enter a rate card ID.",
    duplicate: "This rate card ID is already in use.",
    format: "Use only letters, numbers, hyphens, and underscores.",
    failure: "We couldn't validate this rate card ID. Try again."
  };

  function normalizeRateCardId(raw) {
    return String(raw == null ? "" : raw).trim();
  }

  /* Returns the message to show, or "" when the value is usable.
   * `ignoreId` is the ID the card already has, so editing a card and
   * leaving its ID alone is not a collision with itself. Comparison is
   * case-insensitive: two IDs differing only in case would be two rows
   * a human would read as the same rate card. */
  function rateCardIdError(rawValue, ignoreId) {
    var value = normalizeRateCardId(rawValue);
    if (!value) return RC_ID_MESSAGES.empty;
    if (!RC_ID_ALLOWED.test(value)) return RC_ID_MESSAGES.format;
    try {
      var taken = value.toLowerCase();
      var skip = normalizeRateCardId(ignoreId).toLowerCase();
      var clash = activeRateCards().some(function (row) {
        var existing = normalizeRateCardId(row.rateCardId).toLowerCase();
        if (!existing) return false;
        if (skip && existing === skip) return false;
        return existing === taken;
      });
      return clash ? RC_ID_MESSAGES.duplicate : "";
    } catch (err) {
      console.error("Rate card ID validation failed:", err);
      return RC_ID_MESSAGES.failure;
    }
  }

  function rcCreateIdInput() {
    var modal = rcCreateModal();
    return modal ? modal.querySelector("[data-rcm-card-id]") : null;
  }

  /* Show the ID error, keeping the helper text associated as well. The
   * shared setFieldError would replace aria-describedby outright, which
   * would drop the helper from the accessible description just when the
   * user most needs both. */
  function setRcCreateIdError(message) {
    var input = rcCreateIdInput();
    var modal = rcCreateModal();
    var field = modal && modal.querySelector("[data-rcm-id-field]");
    var slot = field && field.querySelector(".field__error");
    if (!input || !slot) return;
    slot.textContent = message || "";
    slot.hidden = !message;
    if (message) slot.setAttribute("role", "alert");
    else slot.removeAttribute("role");
    if (field) field.classList.toggle("is-invalid", Boolean(message));
    input.setAttribute("aria-invalid", message ? "true" : "false");
    input.setAttribute("aria-describedby",
      message ? "rcm-card-id-help rcm-card-id-error" : "rcm-card-id-help");
  }

  /* The error appears on blur or on a Confirm attempt, never mid-typing:
   * "Enter a rate card ID" while someone is still entering one is noise. */
  var rcIdTouched = false;

  function refreshRcCreateIdValidity(force) {
    var input = rcCreateIdInput();
    if (!input) return "";
    var message = rateCardIdError(input.value, rcEditCardId);
    if (force || rcIdTouched) setRcCreateIdError(message);
    return message;
  }

  function rcCreateFieldError(input) {
    var field = input && input.closest(".field");
    return field ? field.querySelector(".field__error") : null;
  }

  function setRcCreateError(input, message) {
    var slot = rcCreateFieldError(input);
    if (!slot) return;
    slot.textContent = message || "";
    slot.hidden = !message;
    if (input) input.setAttribute("aria-invalid", message ? "true" : "false");
  }

  /* Confirm is the only gate on the required field, so it tracks the
   * name on every keystroke. The inline error is deliberately not shown
   * while typing: it appears on blur, and on a Confirm attempt. */
  function syncRcCreateConfirm() {
    var modal = rcCreateModal();
    if (!modal) return;
    var name = modal.querySelector("#rcm-name");
    var confirm = modal.querySelector('[data-action="confirm-rc-create"]');
    if (!confirm) return;
    var ready = Boolean(name && name.value.trim())
      && !rateCardIdError((rcCreateIdInput() || {}).value, rcEditCardId)
      && !rcCreateDateRangeInvalid();
    confirm.disabled = !ready;
    confirm.setAttribute("aria-disabled", ready ? "false" : "true");
  }

  function rcCreateDateRangeInvalid() {
    var v = collectRcCreateForm();
    if (!v.effectiveStart || !v.effectiveEnd) return false;
    var start = new Date(v.effectiveStart);
    var end = new Date(v.effectiveEnd);
    if (isNaN(start.getTime()) || isNaN(end.getTime())) return false;
    return end < start;
  }

  function validateRcCreateDates() {
    var modal = rcCreateModal();
    if (!modal) return true;
    var endField = modal.querySelector('.ads-datepicker[data-field="rcm-eff-end"]');
    var slot = endField && endField.closest(".field")
      ? endField.closest(".field").querySelector(".field__error")
      : null;
    var invalid = rcCreateDateRangeInvalid();
    if (slot) {
      slot.textContent = invalid
        ? "Effective end must be on or after effective start."
        : "";
      slot.hidden = !invalid;
    }
    syncRcCreateConfirm();
    return !invalid;
  }

  /* Every open starts from the same blank dialog: a cancelled attempt
   * must not leave a half-typed name or an expanded details section
   * waiting for the next user. */
  function resetRcCreateModal() {
    var modal = rcCreateModal();
    if (!modal) return;
    modal.querySelectorAll(".field__input").forEach(function (input) {
      if (input.tagName === "INPUT") input.value = "";
      setRcCreateError(input, "");
    });
    modal.querySelectorAll(".field__error").forEach(function (slot) {
      slot.textContent = "";
      slot.hidden = true;
    });
    modal.querySelectorAll(".edl-select").forEach(function (select) {
      var fallback = select.getAttribute("data-default-value") || "";
      select.setAttribute("data-value", fallback);
      var value = select.querySelector(".edl-select__value");
      if (!value) return;
      value.textContent = fallback || value.getAttribute("data-placeholder-text")
        || value.textContent;
      value.classList.toggle("edl-select__value--placeholder", !fallback);
    });
    modal.querySelectorAll(".ads-datepicker__value").forEach(function (value) {
      var placeholder = value.getAttribute("data-placeholder-text");
      if (placeholder) value.textContent = placeholder;
      value.classList.add("ads-datepicker__value--placeholder");
    });
    setRcCreateDetailsOpen(false);
    rcIdTouched = false;
    setRcCreateIdError("");
    syncRcCreateConfirm();
  }

  function setRcCreateDetailsOpen(open) {
    var modal = rcCreateModal();
    var section = modal && modal.querySelector("[data-rcm-details]");
    if (!section) return;
    var header = section.querySelector(".rcm-details__header");
    var wrap = section.querySelector(".rcm-details__wrap");
    section.classList.toggle("is-open", open);
    if (header) header.setAttribute("aria-expanded", open ? "true" : "false");
    /* The collapsed wrap still occupies the DOM for the height
     * transition, so it is made inert rather than left as a set of
     * fields a Tab press can reach behind a closed disclosure. */
    if (wrap) {
      if (open) wrap.removeAttribute("inert");
      else wrap.setAttribute("inert", "");
    }
  }

  /* Create and Edit are the same dialog with different copy: creating
   * has no id yet and no values to show, editing announces the card it
   * is about to change and opens the details already filled in. */
  function applyRcCreateMode(cardId) {
    var modal = rcCreateModal();
    if (!modal) return;
    rcEditCardId = cardId || "";
    var editing = Boolean(rcEditCardId);
    var title = modal.querySelector("#rcm-create-title");
    if (title) title.textContent = editing ? "Edit rate card" : "Create rate card";
    var intro = modal.querySelector("[data-rcm-body-text]");
    if (intro) {
      intro.textContent = editing
        ? "Update this rate card's name and details. Imports use the ID to match updates to this rate card."
        : "Create a draft rate card. Enter a name and a unique rate card ID. Imports use the ID to match updates to this rate card.";
    }
    var close = modal.querySelector('[data-action="close-rc-create"]');
    if (close) {
      close.setAttribute("aria-label",
        editing ? "Close edit rate card dialog" : "Close create rate card dialog");
    }
    /* Creating asks for an ID; editing shows the one the card already
     * has and explains what changing it would affect. */
    var id = rcCreateIdInput();
    if (id) id.value = editing ? rcEditCardId : "";
    var helper = modal.querySelector("[data-rcm-id-helper]");
    if (helper) {
      helper.textContent = editing
        ? "This ID is used to match imports and updates to this rate card."
        : "Enter the unique ID used to identify this rate card and match future updates.";
    }
    rcIdTouched = false;
    setRcCreateIdError("");
    syncRcCreateConfirm();
  }

  function fillRcCreateForm(values) {
    var modal = rcCreateModal();
    if (!modal || !values) return;
    var setInput = function (sel, value) {
      var node = modal.querySelector(sel);
      if (node) node.value = value || "";
    };
    setInput("#rcm-name", values.name);
    setInput("#rcm-be-id", values.buyingEntityId);
    setInput("#rcm-be-name", values.buyingEntityName);
    setInput("#rcm-dcm-rule", values.dcmRuleOrder);
    ["marketplace", "season"].forEach(function (field) {
      var value = field === "marketplace" ? values.marketplace : values.season;
      if (!value) return;
      var select = modal.querySelector('.edl-select[data-field="' + field + '"]');
      if (!select) return;
      select.setAttribute("data-value", value);
      var slot = select.querySelector(".edl-select__value");
      if (!slot) return;
      /* Show the option's own label rather than the raw value. Deal
       * Season is stored with a hyphen but the menu spells it with an
       * en dash, so the two are compared on their digits. */
      var key = function (v) { return String(v).replace(/\u2013/g, "-"); };
      var option = Array.prototype.find.call(
        select.querySelectorAll(".edl-select__menu li"),
        function (li) { return key(li.getAttribute("data-value")) === key(value); });
      if (option) {
        select.setAttribute("data-value", option.getAttribute("data-value"));
        slot.textContent = option.textContent.trim();
      } else {
        slot.textContent = value;
      }
      slot.classList.remove("edl-select__value--placeholder");
    });
    [["rcm-eff-start", values.effectiveStart], ["rcm-eff-end", values.effectiveEnd]]
      .forEach(function (pair) {
        if (!pair[1]) return;
        var parts = /^(\d{4})-(\d{2})-(\d{2})$/.exec(pair[1]);
        if (!parts) return;
        var slot = modal.querySelector(
          '.ads-datepicker[data-field="' + pair[0] + '"] .ads-datepicker__value');
        if (!slot) return;
        slot.textContent = formatDateMDY(
          new Date(Number(parts[1]), Number(parts[2]) - 1, Number(parts[3])));
        slot.classList.remove("ads-datepicker__value--placeholder");
      });
  }

  /* ===================================================================
   * SHARED ADS MODAL BEHAVIOUR
   * Every .modal--ads node in the app (Delete rate card, Discard quick
   * edit changes, Remove line item or premium, Create/Edit rate card,
   * and the shared confirmation) is the same ADS Modal 38:46 shell, so
   * the three things a dialog owes the keyboard are implemented once
   * here rather than per flow: the background scroll lock, Tab
   * containment, and focus put back where it came from on close.
   *
   * Dialogs are stacked rather than tracked one at a time: Quick Edit's
   * discard confirmation opens over the Quick Edit sheet, and the sheet
   * must keep its own lock when the confirmation closes.
   * ================================================================ */
  var adsModalStack = [];
  var adsConfirmCallback = null;

  function adsModalFocusables(modal) {
    return Array.prototype.filter.call(
      modal.querySelectorAll(
        'button:not([disabled]), [href], input:not([disabled]),'
        + ' select:not([disabled]), textarea:not([disabled]),'
        + ' [tabindex]:not([tabindex="-1"])'),
      function (node) {
        return !node.hidden && node.getAttribute("aria-hidden") !== "true"
          && node.offsetParent !== null;
      });
  }

  /* A select menu or date picker opened from inside a dialog renders to
   * <body> to escape the panel's overflow, so it is outside the modal in
   * the DOM while being inside it to the user. While one is open it owns
   * the arrow keys and Tab, and the trap stands down. */
  function adsModalPortalOpen() {
    return !!document.querySelector(
      '.ads-datepicker__popover:not([hidden]), .edl-select__menu:not([hidden]),'
      + ' .ads-dd__menu:not([hidden])');
  }

  function adsModalKeydown(e) {
    if (e.key !== "Tab" || !adsModalStack.length) return;
    var top = adsModalStack[adsModalStack.length - 1];
    if (!top.modal || top.modal.hidden || adsModalPortalOpen()) return;
    var focusables = adsModalFocusables(top.modal);
    if (!focusables.length) return;
    var first = focusables[0];
    var last = focusables[focusables.length - 1];
    var active = document.activeElement;
    if (!top.modal.contains(active)) {
      e.preventDefault();
      first.focus();
      return;
    }
    if (e.shiftKey && active === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && active === last) { e.preventDefault(); first.focus(); }
  }
  document.addEventListener("keydown", adsModalKeydown, true);

  /* Registers an already-visible dialog with the shared behaviour.
   * initialFocus is a node or a selector; when it is omitted the first
   * focusable in the dialog is used, which for the confirmations is the
   * Cancel button, deliberately, not the action that destroys data. */
  function openAdsModal(modal, options) {
    if (!modal) return;
    options = options || {};
    if (adsModalStack.some(function (entry) { return entry.modal === modal; })) return;
    adsModalStack.push({
      modal: modal,
      returnFocus: options.returnFocus || document.activeElement
    });
    document.body.classList.add("ads-modal-open");
    var focusTarget = typeof options.initialFocus === "string"
      ? modal.querySelector(options.initialFocus)
      : options.initialFocus;
    var moveFocus = function () {
      if (modal.hidden) return;
      var node = focusTarget || adsModalFocusables(modal)[0];
      if (node && typeof node.focus === "function") node.focus();
    };
    /* Twice: once now, so a dialog opened from a keypress is focused
     * before anything else can read activeElement, and once on the next
     * frame, because a caller that re-renders the page underneath (a
     * bulk delete, say) would otherwise pull focus back out. */
    moveFocus();
    requestAnimationFrame(moveFocus);
  }

  function closeAdsModal(modal, options) {
    options = options || {};
    var index = -1;
    for (var i = adsModalStack.length - 1; i >= 0; i -= 1) {
      if (adsModalStack[i].modal === modal) { index = i; break; }
    }
    if (index === -1) return;
    var entry = adsModalStack.splice(index, 1)[0];
    if (!adsModalStack.length) document.body.classList.remove("ads-modal-open");
    if (options.restoreFocus === false) return;
    var back = entry.returnFocus;
    if (back && back.isConnected && typeof back.focus === "function") {
      try { back.focus(); } catch (_) {}
    }
  }

  /* The ADS replacement for window.confirm(): one shared dialog node,
   * written per call. Used by the flows that had no dialog of their own
   * (removing a populated LINE or PREM row on the v1.2 wizard, leaving
   * the details page with unsaved work), so they get the same shell,
   * tokens, focus handling, and Escape behavior as every other
   * confirmation instead of browser chrome. */
  function adsConfirm(options, onConfirm) {
    var modal = document.querySelector("[data-ads-confirm]");
    if (!modal) {
      // No dialog node in this document: fail toward asking, never toward
      // silently discarding the user's work.
      if (window.confirm(options.body || options.title || "Are you sure?")) onConfirm();
      return;
    }
    options = options || {};
    var title = modal.querySelector(".modal__title");
    var body = modal.querySelector(".modal__body-text");
    var cancel = modal.querySelector('[data-ads-confirm-action="cancel"].btn');
    var confirm = modal.querySelector('[data-ads-confirm-action="confirm"]');
    if (title) title.textContent = options.title || "Are you sure?";
    if (body) body.textContent = options.body || "";
    if (cancel) cancel.textContent = options.cancelLabel || "Cancel";
    if (confirm) confirm.textContent = options.confirmLabel || "Confirm";
    adsConfirmCallback = typeof onConfirm === "function" ? onConfirm : null;
    modal.hidden = false;
    openAdsModal(modal, { initialFocus: cancel });
  }

  function closeAdsConfirm(run) {
    var modal = document.querySelector("[data-ads-confirm]");
    if (!modal || modal.hidden) return;
    var callback = adsConfirmCallback;
    adsConfirmCallback = null;
    modal.hidden = true;
    closeAdsModal(modal);
    if (run && callback) callback();
  }

  function isAdsConfirmOpen() {
    var modal = document.querySelector("[data-ads-confirm]");
    return !!modal && !modal.hidden;
  }

  document.addEventListener("click", function (event) {
    if (!(event.target instanceof Element)) return;
    var action = event.target.closest("[data-ads-confirm-action]");
    if (!action) return;
    event.preventDefault();
    closeAdsConfirm(action.getAttribute("data-ads-confirm-action") === "confirm");
  });

  /* v2.js runs in its own IIFE and needs the same dialog for the
   * "leave without saving" guard on the details page. */
  window.adsConfirm = adsConfirm;
  window.openAdsModal = openAdsModal;
  window.closeAdsModal = closeAdsModal;

  function openRcCreateModal(trigger) {
    var modal = rcCreateModal();
    if (!modal) return;
    rcCreateReturnFocus = trigger || document.activeElement;
    resetRcCreateModal();
    applyRcCreateMode("");
    modal.hidden = false;
    document.body.classList.add("rcm-create-open");
    openAdsModal(modal, {
      returnFocus: rcCreateReturnFocus,
      initialFocus: "#rcm-name"
    });
    requestAnimationFrame(function () {
      modal.classList.add("is-open");
    });
  }

  /* Called by the Rate Card Details page when the user activates the
   * pencil on the title. The page owns the rate card file, so it
   * supplies the values and takes the edited ones back. */
  function openEditRateCardModal(cardId, trigger) {
    var modal = rcCreateModal();
    var editor = window.RCMCardEditor;
    if (!modal || !cardId || !editor || typeof editor.getCard !== "function") return;
    var values = editor.getCard(cardId);
    if (!values) return;
    rcCreateReturnFocus = trigger || document.activeElement;
    resetRcCreateModal();
    applyRcCreateMode(cardId);
    fillRcCreateForm(values);
    /* The details this dialog hides behind a disclosure while creating
     * are the whole point of an edit, so they open with the dialog. */
    setRcCreateDetailsOpen(true);
    syncRcCreateConfirm();
    modal.hidden = false;
    document.body.classList.add("rcm-create-open");
    openAdsModal(modal, {
      returnFocus: rcCreateReturnFocus,
      initialFocus: "#rcm-name"
    });
    requestAnimationFrame(function () {
      modal.classList.add("is-open");
    });
  }
  window.openEditRateCardModal = openEditRateCardModal;

  function closeRcCreateModal() {
    var modal = rcCreateModal();
    if (!modal || modal.hidden) return;
    closeAllPopovers();
    closeAllAdsDds();
    modal.classList.remove("is-open");
    modal.hidden = true;
    document.body.classList.remove("rcm-create-open");
    resetRcCreateModal();
    applyRcCreateMode("");
    closeAdsModal(modal);
    rcCreateReturnFocus = null;
  }

  /* Confirm creates the Draft through the same two functions the Create
   * page's own saves use, so id minting, the newest-first insert, and
   * the localStorage mirror all stay in one place. The session draft is
   * cleared first and last: cleared first so this Confirm mints a fresh
   * id rather than upserting the previous draft's row, and cleared
   * after so the details page starts from the saved record. */
  function confirmRcCreate() {
    var modal = rcCreateModal();
    if (!modal) return;
    /* The ID is checked first because it is the field the whole record
     * is keyed on, and because a failure here has to take focus. */
    var idMessage = refreshRcCreateIdValidity(true);
    if (idMessage) {
      rcIdTouched = true;
      var idInput = rcCreateIdInput();
      if (idInput) idInput.focus();
      syncRcCreateConfirm();
      return;
    }
    var name = modal.querySelector("#rcm-name");
    if (!name || !name.value.trim()) {
      setRcCreateError(name, "Enter a rate card name.");
      if (name) name.focus();
      syncRcCreateConfirm();
      return;
    }
    if (!validateRcCreateDates()) return;
    if (rcEditCardId) {
      var editValues = collectRcCreateForm();
      /* Only an actual change to the ID is worth interrupting for.
       * Editing a name or a date must not raise this dialog. */
      if (editValues.rateCardId !== rcEditCardId) {
        var previousId = rcEditCardId;
        window.adsConfirm({
          title: "Change rate card ID?",
          body: "This ID is used to match imports and updates. Changing it may "
            + "prevent files using the previous ID from matching this rate card.",
          cancelLabel: "Cancel",
          confirmLabel: "Change ID"
        }, function () {
          confirmRcEdit(previousId, editValues);
        });
        return;
      }
      confirmRcEdit(rcEditCardId, editValues);
      return;
    }

    var confirm = modal.querySelector('[data-action="confirm-rc-create"]');
    if (confirm) {
      if (confirm.getAttribute("data-busy") === "true") return;
      confirm.setAttribute("data-busy", "true");
      confirm.classList.add("is-loading");
      confirm.disabled = true;
    }

    var values = collectRcCreateForm();
    /* The commit itself is synchronous, so it is deferred one frame:
     * without yielding, the browser never paints the busy button and
     * the user gets no acknowledgement that Confirm was pressed. */
    window.setTimeout(function () {
      var row = null;
      try {
        window.__rcDraft = null;
        row = commitFormToTable({ status: "Draft", values: values });
      } catch (err) {
        console.error("Create rate card failed:", err);
        if (confirm) {
          confirm.removeAttribute("data-busy");
          confirm.classList.remove("is-loading");
        }
        syncRcCreateConfirm();
        toastV12(
          { message: "Unable to create rate card.", variant: "error" },
          "Could not create the rate card. See console for details."
        );
        return;
      }
      window.__rcDraft = null;
      if (confirm) {
        confirm.removeAttribute("data-busy");
        confirm.classList.remove("is-loading");
      }
      closeRcCreateModal();
      page = 1;
      renderTable();
      toastV12(
        { message: values.name + " created.", variant: "success" },
        values.name + " created."
      );
      /* Straight to the shared details page, in edit mode against the
       * record that now exists, which is the same surface the list's
       * Name link opens. */
      if (row) openEditRateCard(row);
    }, 220);
  }

  /* Editing writes through the details page rather than the list: that
   * page holds the open rate card file, and it mirrors the saved CARD
   * back to the list row itself, so a repeated edit updates one row
   * instead of adding another. */
  /* The list row shows the same identity fields the dialog just
   * changed, so it is refreshed in place: matched on rateCardId, no new
   * row, no version bump (a metadata correction is not a new revision
   * of the rate card), and no status change. */
  function updateListRowFromCardEdit(cardId, values) {
    var row = RATE_CARDS.find(function (r) { return r.rateCardId === cardId; });
    if (!row) return;
    /* Matched on the ID the row still carries, then moved to the new one,
     * so the list keeps showing one rate card rather than growing a
     * second row under the new ID. */
    if (values.rateCardId && values.rateCardId !== cardId) {
      row.rateCardId = values.rateCardId;
    }
    if (values.name) row.name = values.name;
    row.marketplace = values.marketplace || row.marketplace || "";
    row.buyingEntity = values.buyingEntityName || row.buyingEntity || "";
    if (values.buyingEntityId) row.saleshubId = values.buyingEntityId;
    if (values.season) row.season = values.season;
    row.lastUpdated = formatLastUpdated(new Date());
    if (row.userSaved) persistSavedRowsToStorage();
  }

  function confirmRcEdit(cardId, values) {
    var editor = window.RCMCardEditor;
    var nextId = normalizeRateCardId(values && values.rateCardId) || cardId;
    /* Re-key first. applyCard only writes to the card it was opened on,
     * so the rename has to land before the field values do. */
    if (nextId !== cardId) {
      var renamed = editor && typeof editor.renameCard === "function"
        ? editor.renameCard(cardId, nextId)
        : false;
      if (!renamed) {
        toastV12(
          { message: "Unable to change the rate card ID.", variant: "error" },
          "Could not change the rate card ID."
        );
        return;
      }
    }
    var saved = editor && typeof editor.applyCard === "function"
      ? editor.applyCard(nextId, values)
      : false;
    if (!saved) {
      toastV12(
        { message: "Unable to save rate card details.", variant: "error" },
        "Could not save the rate card details."
      );
      return;
    }
    updateListRowFromCardEdit(cardId, values);
    closeRcCreateModal();
    renderTable();
    document.dispatchEvent(new CustomEvent("rcm:card-updated", {
      detail: { cardId: nextId, previousCardId: cardId }
    }));
    toastV12(
      { message: values.name + " updated.", variant: "success" },
      values.name + " updated."
    );
  }

  function initRcCreateModal() {
    var modal = rcCreateModal();
    if (!modal) return;
    var cardIdInput = rcCreateIdInput();
    if (cardIdInput) {
      cardIdInput.addEventListener("input", function () {
        /* Clear a showing error as soon as the value becomes usable, but
         * do not raise a new one mid-typing. */
        if (rcIdTouched && !rateCardIdError(cardIdInput.value, rcEditCardId)) {
          setRcCreateIdError("");
        }
        syncRcCreateConfirm();
      });
      cardIdInput.addEventListener("blur", function () {
        /* Trim on the way out so what is validated is what is saved. */
        cardIdInput.value = normalizeRateCardId(cardIdInput.value);
        rcIdTouched = true;
        refreshRcCreateIdValidity(true);
        syncRcCreateConfirm();
      });
    }
    var name = modal.querySelector("#rcm-name");
    if (name) {
      name.addEventListener("input", function () {
        if (name.value.trim()) setRcCreateError(name, "");
        syncRcCreateConfirm();
      });
      name.addEventListener("blur", function () {
        setRcCreateError(name, name.value.trim() ? "" : "Enter a rate card name.");
      });
    }
    modal.addEventListener("click", function (e) {
      if (e.target.closest(".modal__scrim")) closeRcCreateModal();
    });
    /* Both dates are set by the shared datepicker's delegated click
     * handler, which has no change event of its own, and its popover is
     * portaled out of the dialog, so the range is re-checked after any
     * press anywhere while the dialog is open. Cheap, and it cannot
     * miss a path the picker grows later. */
    document.addEventListener("click", function () {
      if (!isRcCreateOpen()) return;
      window.setTimeout(validateRcCreateDates, 0);
    });
    /* A dialog keeps focus inside itself. */
    modal.addEventListener("keydown", function (e) {
      if (e.key !== "Tab") return;
      var focusable = Array.prototype.filter.call(
        modal.querySelectorAll(
          'a[href], button:not([disabled]), input:not([disabled]), ' +
          'select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'),
        function (node) { return node.offsetParent !== null; });
      if (!focusable.length) return;
      var first = focusable[0];
      var last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    });
  }

  function openDeleteModal(rowId, trigger) {
    var ids = (Array.isArray(rowId) ? rowId : [rowId]).map(String);
    const active = activeRateCards();
    const cards = active.filter(function (c) { return ids.indexOf(String(c.id)) !== -1; });
    if (cards.length === 0) return;
    pendingDeleteIds = cards.map(function (c) { return c.id; });
    /* Look up the row in the ACTIVE view so v1.2 users see the
     * projected values (WPP Jul 09 / ver 3, IPG L'Oreal Multi-Year,
     * etc.) in the delete confirm modal. v1.1 gets RATE_CARDS
     * unchanged. */
    const card = cards.length === 1
      ? cards[0]
      : { name: cards.length + " rate cards" };
    const modal = document.querySelector("[data-modal]");
    const target = document.querySelector("[data-modal-target]");
    /* data-modal-target is the plain read-only summary value (<dd>)
     * holding the selected rate card name. Per the 2026-06-29 brief:
     * NOT an <input>, NOT a field-bordered chrome - so users don't
     * read the modal as a form. textContent is the only setter needed.
     *
     * Belt-and-braces for legacy callers / hot-reload: if for some
     * reason the slot is still rendered as an <input> (e.g. a stale
     * preview), fall back to .value so the name still renders. */
    /* A row with no usable name still has to name what is about to be
     * deleted, so the rate card id stands in rather than the dialog
     * showing an empty slot or a fragment of one. */
    var cardLabel = String(card.name == null ? "" : card.name).trim()
      || (cards.length === 1 && cards[0].rateCardId)
      || "Selected rate card";
    if (target) {
      if (target.tagName === "INPUT") {
        target.value = cardLabel;
      } else {
        target.textContent = cardLabel;
      }
      target.setAttribute("data-tooltip", cardLabel);
      target.setAttribute("data-tooltip-truncate", "auto");
    }
    /* Pluralize the confirm copy when the 2.1 action bar sends more than
     * one row, so the dialog never says "this rate card" over a list of
     * five. Singular wording is restored on every open, because the same
     * modal node serves both cases. */
    var many = cards.length > 1;
    var title = modal.querySelector(".modal__title");
    var bodyText = modal.querySelector(".modal__body-text");
    var summaryLabel = modal.querySelector(".modal__summary-label");
    var confirmBtn = modal.querySelector('[data-action="confirm-delete"]');
    if (title) {
      title.textContent = many ? "Delete these rate cards?" : "Delete this rate card?";
    }
    if (bodyText) {
      bodyText.textContent = many
        ? "This will permanently remove these rate cards from the manager. This action cannot be undone."
        : "This will permanently remove this rate card from the manager. This action cannot be undone.";
    }
    if (summaryLabel) summaryLabel.textContent = many ? "Rate cards" : "Rate card";
    if (confirmBtn) {
      confirmBtn.textContent = many ? "Delete rate cards" : "Delete rate card";
      /* Reopening after a run has to start from a clean button: a
       * confirm left busy from the previous open would refuse the
       * click. */
      confirmBtn.disabled = false;
      confirmBtn.removeAttribute("data-busy");
      confirmBtn.classList.remove("is-loading");
    }
    deleteConfirmProcessing = false;
    modal.hidden = false;
    /* Focus lands on Cancel, not on Delete: the project's convention for
     * a destructive confirmation is that Enter on arrival does nothing
     * irreversible. */
    openAdsModal(modal, {
      returnFocus: trigger || document.activeElement,
      initialFocus: '[data-action="cancel-delete"].btn'
    });
  }

  function closeDeleteModal() {
    pendingDeleteIds = [];
    deleteConfirmProcessing = false;
    var modal = document.querySelector("[data-modal]");
    if (!modal || modal.hidden) return;
    modal.hidden = true;
    closeAdsModal(modal);
  }

  /* Guards the window between the click and the row actually going: a
   * second click on Delete must not run the removal twice. */
  var deleteConfirmProcessing = false;

  function confirmDelete() {
    if (deleteConfirmProcessing) return;
    if (pendingDeleteIds.length === 0) {
      closeDeleteModal();
      return;
    }
    deleteConfirmProcessing = true;
    var busyModal = document.querySelector("[data-modal]");
    var busyBtn = busyModal
      && busyModal.querySelector('[data-action="confirm-delete"]');
    if (busyBtn) {
      busyBtn.setAttribute("data-busy", "true");
      busyBtn.classList.add("is-loading");
      busyBtn.disabled = true;
    }
    /* Splice mutates RATE_CARDS directly (the authoritative store).
     * The v1.2 projection is rebuilt on next render so the delete
     * naturally propagates. The toast message pulls from the ACTIVE
     * view so v1.2 users see the projected name (matters only for
     * the 10 PM-overridden rows, whose names differ from RATE_CARDS). */
    const active = activeRateCards();
    const deleted = [];
    pendingDeleteIds.forEach(function (id) {
      const displayCard = active.find((c) => c.id === id);
      const idx = RATE_CARDS.findIndex((c) => c.id === id);
      if (idx >= 0) RATE_CARDS.splice(idx, 1);
      selectedRateCardIds.delete(String(id));
      if (!displayCard) return;
      try {
        var files = JSON.parse(
          window.localStorage.getItem("rate-card-manager.v2.files") || "{}"
        );
        delete files[displayCard.rateCardId];
        window.localStorage.setItem(
          "rate-card-manager.v2.files",
          JSON.stringify(files)
        );
        var quickEdit = readQuickEditStore();
        delete quickEdit[displayCard.id];
        writeQuickEditStore(quickEdit);
      } catch (_) {}
      deleted.push(displayCard);
    });
    if (deleted.length === 1) {
      toastV12(
        { message: "Rate card deleted.", variant: "success" },
        'Deleted "' + deleted[0].name + '"'
      );
    } else if (deleted.length > 1) {
      toastV12(
        { message: deleted.length + " rate cards deleted.", variant: "success" },
        "Deleted " + deleted.length + " rate cards"
      );
    }
    closeDeleteModal();
    renderTable();
  }

  /* ====================== QUICK EDIT BOTTOM SHEET ======================
   *
   * UX:
   *   1. User clicks the "#" icon in the row's Action column.
   *   2. openQuickEdit(cardId) loads persisted lines + populates the sheet.
   *   3. The sheet slides up from the bottom over a dimmed scrim.
   *   4. User edits Base Rate (numeric, 4 decimals) or the single free-form
   *      Line Conditions field (comma-separated values, normalized on blur).
   *   5. Save is disabled until at least one cell differs from its
   *      loaded value (compared after on-blur normalization).
   *   6. Save validates all Base Rate cells (numeric, non-negative,
   *      <= 10000) and persists the result via saveQuickEditLines().
   *      On success: toast + close sheet + leave the editing dataset in
   *      place so reopening shows the saved values.
   *   7. Cancel / X / scrim / Escape:
   *        - clean state  -> close immediately
   *        - dirty state  -> open "Discard changes?" confirmation
   *   8. Focus is moved into the close button when the sheet opens and
   *      restored to the trigger when it closes.
   * ===================================================================== */

  /* Format a free-form user value as 4-decimal currency-ish text.
   * Returns the raw string if it cannot be parsed as a positive number. */
  function formatBaseRate(raw) {
    if (raw == null) return "";
    var s = String(raw).trim();
    if (s === "") return "";
    if (!/^-?\d*\.?\d*$/.test(s)) return s;
    var n = parseFloat(s);
    if (isNaN(n)) return s;
    return n.toFixed(4);
  }

  function isValidBaseRate(raw) {
    if (raw == null) return false;
    var s = String(raw).trim();
    if (s === "") return false;
    if (!/^-?\d*\.?\d+$/.test(s) && !/^-?\d+\.?$/.test(s)) return false;
    var n = parseFloat(s);
    return !isNaN(n) && n >= 0 && n <= 10000;
  }

  function isQuickEditOpen() {
    var sheet = document.querySelector("[data-quick-edit]");
    return !!(sheet && !sheet.hidden);
  }

  function openQuickEdit(cardId) {
    /* Load from the active view so v1.2 users see the projected
     * marketplace + name in the Quick Edit summary header. Line items
     * underneath are keyed to the underlying card id so their
     * persistence bucket is version-agnostic. */
    var card = activeRateCards().find(function(c){ return c.id === cardId; });
    if (!card) return;
    var sheet = document.querySelector("[data-quick-edit]");
    if (!sheet) return;

    /* Load the persisted (or seeded) lines for this card. */
    var lines = getQuickEditLines(card);

    quickEditState = {
      cardId: card.id,
      original: lines.map(function(r){ return Object.assign({}, r); }),
      draft:    lines.map(function(r){ return Object.assign({}, r); }),
      prevFocus: document.activeElement,
    };

    /* Header + summary band. */
    document.querySelector("[data-quick-edit-title]").textContent = card.name;
    document.querySelector("[data-qe-buying-entity]").textContent = card.buyingEntity || "Not set";
    document.querySelector("[data-qe-season]").textContent =
      quickEditSeasonLabel(card.season);
    document.querySelector("[data-qe-marketplace]").textContent = card.marketplace || "Not set";
    /* Type + Advertiser remain readonly text per brief; dropdown-driven
     * filtering would be a follow-up. */
    document.querySelector("[data-qe-type]").textContent = "Line rows";
    document.querySelector("[data-qe-advertiser]").textContent = "All advertisers";

    /* Header + colgroup must render before the rows so cell widths and
     * column count line up with the version-specific tbody shape. */
    renderQuickEditHeader();
    renderQuickEditRows();
    updateQuickEditSaveState();

    /* Show the sheet, then add .is-open on next frame so the
     * transform transition fires (instead of being applied while hidden). */
    sheet.hidden = false;
    sheet.setAttribute("aria-hidden", "false");
    document.body.classList.add("qe-open");
    requestAnimationFrame(function(){
      sheet.classList.add("is-open");
    });

    /* Move focus to the dialog surface so opening Quick Edit does not
     * synthesize a tooltip-triggering focus state on the close button.
     * The close button remains the first Tab stop. */
    setTimeout(function(){
      var panel = sheet.querySelector(".qsheet__panel");
      if (panel) panel.focus();
    }, 80);
  }

  /* Version helper for Quick Edit rendering. v1.2 uses the consolidated
   * single Line conditions column; v1.0 / v1.1 render four discrete
   * Line condition slots (projected from the canonical lineConditions
   * string). */
  function isQuickEditV12() {
    return document.body && isModernAppVersion(document.body.getAttribute("data-version"));
  }

  /* Split the canonical "A, B" comma-separated lineConditions string
   * into an array of up to `slotCount` fragments. Used by v1.1 render
   * to populate its four discrete #lc1..lc4 inputs from a single stored
   * value. Fragments past slot 4 are dropped (they would already have
   * been deduped by normalizeLineConditions on save). Empty tail slots
   * are filled with "" so all inputs render. */
  function splitLineConditionsIntoSlots(str, slotCount) {
    var parts = normalizeLineConditions(str).split(", ").filter(function(s){ return s; });
    var out = [];
    for (var i = 0; i < slotCount; i += 1) out.push(parts[i] || "");
    return out;
  }

  /* Read the four v1.1 Line condition inputs for a given row's <tr> and
   * merge them into the canonical comma-separated string. Used by the
   * v1.1 input/blur handler so the draft row's .lineConditions stays
   * the single source of truth even while the DOM shows four slots. */
  function readV11LineConditionsFromRow(tr) {
    if (!tr) return "";
    var parts = [];
    for (var i = 1; i <= 4; i += 1) {
      var el = tr.querySelector('[data-qe-field="lc' + i + '"]');
      if (el && el.value != null) parts.push(el.value);
    }
    return normalizeLineConditions(parts.join(", "));
  }

  /* Swap the Quick Edit <colgroup> + <thead> to the version-specific
   * shape. v1.1 shows four discrete Line condition columns (the static
   * HTML default); v1.2 collapses to one merged Line conditions column
   * (Adam's 2026-07-09 update). Called on every openQuickEdit() so a
   * runtime version switch via the profile menu re-renders correctly. */
  function renderQuickEditHeader() {
    var colgroup = document.querySelector("[data-qe-colgroup]");
    var thead    = document.querySelector("[data-qe-thead]");
    if (!colgroup || !thead) return;
    if (isQuickEditV12()) {
      colgroup.innerHTML =
        '<col class="qsheet__col qsheet__col--adv">' +
        '<col class="qsheet__col qsheet__col--rate">' +
        '<col class="qsheet__col qsheet__col--cm">' +
        '<col class="qsheet__col qsheet__col--bo">' +
        '<col class="qsheet__col qsheet__col--ap">' +
        '<col class="qsheet__col qsheet__col--lc">';
      thead.innerHTML =
        '<tr>' +
          '<th scope="col" class="qsheet__th qsheet__th--adv">Advertiser</th>' +
          '<th scope="col" class="qsheet__th qsheet__th--num">Base rate</th>' +
          '<th scope="col" class="qsheet__th">Cost method</th>' +
          '<th scope="col" class="qsheet__th">Base offering</th>' +
          '<th scope="col" class="qsheet__th">Ad product</th>' +
          '<th scope="col" class="qsheet__th">Line condition</th>' +
        '</tr>';
    } else {
      /* Restore the v1.1 nine-column shape. Kept in JS (not just the
       * HTML default) so a runtime version switch back to v1.1 rebuilds
       * the headers even if v1.2 had already rendered. */
      colgroup.innerHTML =
        '<col class="qsheet__col qsheet__col--adv">' +
        '<col class="qsheet__col qsheet__col--rate">' +
        '<col class="qsheet__col qsheet__col--cm">' +
        '<col class="qsheet__col qsheet__col--bo">' +
        '<col class="qsheet__col qsheet__col--ap">' +
        '<col class="qsheet__col qsheet__col--lc">' +
        '<col class="qsheet__col qsheet__col--lc">' +
        '<col class="qsheet__col qsheet__col--lc">' +
        '<col class="qsheet__col qsheet__col--lc">';
      thead.innerHTML =
        '<tr>' +
          '<th scope="col" class="qsheet__th qsheet__th--adv">Advertiser</th>' +
          '<th scope="col" class="qsheet__th qsheet__th--num">Base rate</th>' +
          '<th scope="col" class="qsheet__th">Cost method</th>' +
          '<th scope="col" class="qsheet__th">Base offering</th>' +
          '<th scope="col" class="qsheet__th">Ad product</th>' +
          '<th scope="col" class="qsheet__th">Line condition 1</th>' +
          '<th scope="col" class="qsheet__th">Line condition 2</th>' +
          '<th scope="col" class="qsheet__th">Line condition 3</th>' +
          '<th scope="col" class="qsheet__th">Line condition 4</th>' +
        '</tr>';
    }
  }

  function renderQuickEditRows() {
    if (!quickEditState) return;
    var tbody = document.querySelector("[data-qe-rows]");
    if (!tbody) return;
    var v12 = isQuickEditV12();
    tbody.replaceChildren();
    quickEditState.draft.forEach(function(row, idx){
      var tr = document.createElement("tr");
      tr.className = "qsheet__row";
      tr.setAttribute("data-qe-row-idx", String(idx));

      // Advertiser (readonly text)
      var cAdv = document.createElement("td");
      cAdv.className = "qsheet__cell qsheet__cell--ro";
      cAdv.textContent = row.advertiser;
      // ADS truncation tooltip (not browser native title).
      cAdv.setAttribute("data-tooltip", row.advertiser);
      cAdv.setAttribute("data-tooltip-truncate", "auto");
      tr.appendChild(cAdv);

      // Base Rate (editable numeric input, 4 decimals on blur)
      var cRate = document.createElement("td");
      cRate.className = "qsheet__cell qsheet__cell--num";
      var inpRate = document.createElement("input");
      inpRate.type = "text";
      inpRate.inputMode = "decimal";
      inpRate.className = "qsheet__input qsheet__input--num";
      inpRate.value = row.baseRate;
      inpRate.setAttribute("data-qe-field", "baseRate");
      inpRate.setAttribute("aria-label", "Base rate, row " + (idx + 1));
      cRate.appendChild(inpRate);
      tr.appendChild(cRate);

      // Cost Method, Base Offering, Ad Product (readonly text)
      ["costMethod","baseOffering","adProduct"].forEach(function(key){
        var c = document.createElement("td");
        c.className = "qsheet__cell qsheet__cell--ro";
        c.textContent = row[key];
        tr.appendChild(c);
      });

      if (v12) {
        /* One optional Line condition per row, so one field: a row
         * without a condition shows an empty input under its placeholder
         * rather than the words "No additional targeting", which is how
         * the rate model says there is no condition and not something a
         * seller ever typed. The value is normalized on blur (trim,
         * dedupe, spacing) via handleQuickEditFieldEvent. */
        var cLc = document.createElement("td");
        cLc.className = "qsheet__cell qsheet__cell--lc";
        /* The same closed list Line Details uses, so a seller cannot
         * type a condition here that the Business Dictionary does not
         * recognise. The control writes the canonical labels into its
         * own hidden input; tagging that input as the row's field is
         * what lets the existing draft and dirty tracking pick the
         * change up without a second save path. */
        var lcHost = document.createElement("div");
        lcHost.setAttribute("data-conditions", "");
        lcHost.setAttribute("data-conditions-scope", "line");
        cLc.appendChild(lcHost);
        var lcField = window.RCMConditions && window.RCMConditions.createField(
          lcHost,
          {
            id: "qe-cond-" + idx,
            ariaLabel: "Line condition, row " + (idx + 1),
            menuLabel: "Line condition"
          }
        );
        if (lcField) {
          lcHost.querySelector("[data-cond-value]")
            .setAttribute("data-qe-field", "lineConditions");
          lcField.set(row.lineConditions, "");
        }
        tr.appendChild(cLc);
      } else {
        /* v1.1 legacy: four discrete Line condition inputs. Values are
         * projected from the canonical row.lineConditions string so the
         * two shapes share one source of truth; on blur we merge the
         * four DOM values back into row.lineConditions (see
         * handleQuickEditFieldEvent). */
        var slots = splitLineConditionsIntoSlots(row.lineConditions, 4);
        for (var n = 1; n <= 4; n += 1) {
          var c = document.createElement("td");
          c.className = "qsheet__cell";
          var inp = document.createElement("input");
          inp.type = "text";
          inp.className = "qsheet__input";
          inp.value = slots[n - 1];
          inp.placeholder = "Not set";
          inp.setAttribute("data-qe-field", "lc" + n);
          inp.setAttribute("aria-label", "Line condition " + n + ", row " + (idx + 1));
          c.appendChild(inp);
          tr.appendChild(c);
        }
      }

      tbody.appendChild(tr);
    });

    paintQuickEditDirtyState();
  }

  /* Re-paint .is-dirty on every input by diffing draft vs original.
   * The draft/original rows always carry canonical `.lineConditions`
   * strings (see handleQuickEditFieldEvent's v1.1 branch, which merges
   * the four DOM inputs back before writing draft). v1.1 renders four
   * discrete lc1..lc4 inputs; each of those turns dirty when the
   * combined draft.lineConditions differs from original.lineConditions
   * (any of the four slots changing flips the whole row's LC dirty
   * signal, which matches the UX the user would expect - the row is
   * dirty when its conditions changed). */
  function paintQuickEditDirtyState() {
    if (!quickEditState) return;
    var rows = document.querySelectorAll("[data-qe-rows] [data-qe-row-idx]");
    rows.forEach(function(tr){
      var idx = parseInt(tr.getAttribute("data-qe-row-idx"), 10);
      var draftRow = quickEditState.draft[idx];
      var origRow = quickEditState.original[idx];
      if (!draftRow || !origRow) return;
      var lcDirty = String(draftRow.lineConditions || "") !== String(origRow.lineConditions || "");
      tr.querySelectorAll("[data-qe-field]").forEach(function(inp){
        var key = inp.getAttribute("data-qe-field");
        var dirty;
        if (key === "lc1" || key === "lc2" || key === "lc3" || key === "lc4" || key === "lineConditions") {
          dirty = lcDirty;
        } else {
          dirty = String(draftRow[key] || "") !== String(origRow[key] || "");
        }
        inp.classList.toggle("is-dirty", dirty);
      });
    });
  }

  function isQuickEditDirty() {
    if (!quickEditState) return false;
    for (var i = 0; i < quickEditState.draft.length; i++) {
      var d = quickEditState.draft[i];
      var o = quickEditState.original[i];
      if (!o) return true;
      if (String(d.baseRate || "") !== String(o.baseRate || "")) return true;
      /* Line conditions is a single free-form string; compare the raw
       * value so mid-edit typing still enables Save, but note the
       * blur-time normalizer (handleQuickEditFieldEvent) canonicalizes
       * both sides so "A, B" vs "A,B" don't stay dirty forever. */
      if (String(d.lineConditions || "") !== String(o.lineConditions || "")) return true;
    }
    return false;
  }

  function updateQuickEditSaveState() {
    var btn = document.querySelector("[data-qe-save]");
    if (!btn) return;
    btn.disabled = !isQuickEditDirty();
  }

  /* Capture every input/blur inside the rows. Live-update the draft + the
   * Save enabled state; on blur format Base Rate to 4 decimals. */
  function handleQuickEditFieldEvent(e) {
    if (!quickEditState) return;
    var inp = e.target;
    if (!(inp instanceof HTMLInputElement)) return;
    if (!inp.hasAttribute("data-qe-field")) return;
    var tr = inp.closest("[data-qe-row-idx]");
    if (!tr) return;
    var idx = parseInt(tr.getAttribute("data-qe-row-idx"), 10);
    var draftRow = quickEditState.draft[idx];
    if (!draftRow) return;
    var key = inp.getAttribute("data-qe-field");

    if (e.type === "blur" && key === "baseRate") {
      var formatted = formatBaseRate(inp.value);
      if (formatted !== inp.value) inp.value = formatted;
    }
    /* Line conditions handling:
     *   v1.2 - single #lineConditions input. Canonicalize on blur so
     *          "A18-49,Preemptible,, Live" settles to "A18-49,
     *          Preemptible, Live" (trim + dedupe + ", " spacing).
     *          Keep raw typing intact during input so the caret and
     *          cursor position stay stable while the user is mid-value.
     *   v1.1 - four discrete lc1..lc4 inputs. Merge the row's four DOM
     *          values into the canonical draftRow.lineConditions
     *          string. Do NOT persist lc1..lc4 on draftRow (those are
     *          transient DOM projections; the canonical shape stays
     *          single-string across versions). */
    var isLcKey = (key === "lc1" || key === "lc2" || key === "lc3" || key === "lc4");
    if (e.type === "blur" && key === "lineConditions") {
      var normalized = normalizeLineConditions(inp.value);
      if (normalized !== inp.value) inp.value = normalized;
    }
    if (isLcKey) {
      /* Read all four inputs from the row every time so the merged
       * value stays in sync even if the user edits multiple slots
       * before blurring. Save flow re-normalizes anyway (see
       * saveQuickEdit) so no need to canonicalize on each input. */
      draftRow.lineConditions = readV11LineConditionsFromRow(tr);
    } else {
      draftRow[key] = inp.value;
    }

    /* Validate Base Rate inline. */
    if (key === "baseRate") {
      var ok = inp.value === "" ? false : isValidBaseRate(inp.value);
      inp.classList.toggle("is-invalid", !ok);
    }

    paintQuickEditDirtyState();
    updateQuickEditSaveState();
  }

  function saveQuickEdit() {
    if (!quickEditState) return;

    /* Validate all Base Rate cells before persisting. Line conditions
     * are normalized in the same pass so an unblurred edit (e.g. user
     * hits Save via keyboard shortcut while an input is still focused)
     * still lands canonical "A, B" spacing in storage. */
    var firstBad = null;
    var draftCopy = quickEditState.draft.map(function(r){
      var out = Object.assign({}, r);
      out.baseRate = formatBaseRate(out.baseRate);
      out.lineConditions = normalizeLineConditions(out.lineConditions);
      return out;
    });
    for (var i = 0; i < draftCopy.length; i++) {
      if (!isValidBaseRate(draftCopy[i].baseRate)) {
        firstBad = i;
        break;
      }
    }
    if (firstBad !== null) {
      toastV12(
        { message: "Complete required fields before continuing.", variant: "warning" },
        "Row " + (firstBad + 1) + ": invalid base rate."
      );
      var trBad = document.querySelector('[data-qe-row-idx="' + firstBad + '"]');
      if (trBad) {
        var inp = trBad.querySelector('[data-qe-field="baseRate"]');
        if (inp) inp.focus();
      }
      return;
    }

    if (!saveQuickEditLines(quickEditState.cardId, draftCopy)) {
      toastV12(
        { title: "Unable to save rate card", message: "Try again.", variant: "error" },
        "Unable to save Quick Edit changes."
      );
      return;
    }
    /* Re-baseline original = saved snapshot so the sheet is clean again. */
    quickEditState.draft    = draftCopy.map(function(r){ return Object.assign({}, r); });
    quickEditState.original = draftCopy.map(function(r){ return Object.assign({}, r); });

    toastV12(
      { message: "Rate card saved.", variant: "success" },
      "Quick edit saved."
    );
    closeQuickEdit(true);
  }

  function closeQuickEdit(force) {
    var sheet = document.querySelector("[data-quick-edit]");
    if (!sheet || sheet.hidden) return;
    adsTooltipHide();

    if (!force && isQuickEditDirty()) {
      var discard = document.querySelector("[data-qe-discard]");
      if (discard) {
        discard.hidden = false;
        /* Opens on Keep editing: the confirmation appears because the
         * user tried to close, so the key that arrives next must not be
         * the one that throws the edits away. */
        openAdsModal(discard, {
          initialFocus: '[data-action="qe-keep-editing"].btn'
        });
      }
      return;
    }

    sheet.classList.remove("is-open");
    sheet.setAttribute("aria-hidden", "true");
    document.body.classList.remove("qe-open");
    var prev = quickEditState && quickEditState.prevFocus;

    /* Wait for the 220ms slide-down transition to finish before hiding,
     * so layout doesn't snap and the focus restore lands at the right time. */
    var done = function() {
      sheet.hidden = true;
      sheet.removeEventListener("transitionend", done);
      quickEditState = null;
      try { if (prev && typeof prev.focus === "function") prev.focus(); } catch (_) {}
    };
    var panel = sheet.querySelector(".qsheet__panel");
    if (panel) panel.addEventListener("transitionend", function once(ev){
      if (ev.propertyName === "transform") {
        panel.removeEventListener("transitionend", once);
        done();
      }
    }, { once: false });
    /* Fallback: if transitionend doesn't fire (reduced motion / browser
     * variance), force-close after 280ms. */
    setTimeout(function(){
      if (!sheet.hidden) done();
    }, 280);
  }

  function keepEditing() {
    var discard = document.querySelector("[data-qe-discard]");
    if (!discard || discard.hidden) return;
    discard.hidden = true;
    closeAdsModal(discard);
  }

  function discardQuickEditChanges() {
    /* Revert draft to original then close. */
    if (quickEditState) {
      quickEditState.draft = quickEditState.original.map(function(r){ return Object.assign({}, r); });
    }
    var discard = document.querySelector("[data-qe-discard]");
    if (discard && !discard.hidden) {
      discard.hidden = true;
      /* Focus is not sent back to the sheet's close button here: the
       * sheet is closing too, and closeQuickEdit restores focus to the
       * row that opened it. */
      closeAdsModal(discard, { restoreFocus: false });
    }
    closeQuickEdit(true);
  }

  /* Lightweight focus trap. Only active while the bottom sheet is open.
   * Catches Tab / Shift+Tab and wraps focus inside the panel. */
  function handleQuickEditKeydown(e) {
    if (!isQuickEditOpen()) return;
    var sheet = document.querySelector("[data-quick-edit]");
    if (!sheet) return;
    if (e.key === "Tab") {
      var focusables = sheet.querySelectorAll(
        'button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])'
      );
      if (!focusables.length) return;
      var first = focusables[0];
      var last = focusables[focusables.length - 1];
      var active = document.activeElement;
      if (e.shiftKey && active === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && active === last) { e.preventDefault(); first.focus(); }
    }
  }

  // ----- Dropdown / popover plumbing ----------------------------------------

  function closeAllPopovers(exceptName) {
    document.querySelectorAll("[data-dropdown]").forEach((wrap) => {
      const name = wrap.getAttribute("data-dropdown");
      if (name === exceptName) return;
      // The avatar button is the first [aria-expanded] inside the profile
      // wrap. querySelector returns the first match in tree order, so this
      // correctly targets the trigger and not the Theme submenu's button.
      const trigger = wrap.querySelector("[aria-expanded]");
      const panel =
        wrap.querySelector(".dropdown__menu") ||
        wrap.querySelector(".popover");
      if (trigger) trigger.setAttribute("aria-expanded", "false");
      if (panel) panel.hidden = true;
      /* Also collapse any submenu (Theme, Version, ...) inside this
       * wrap so re-opening the profile menu starts in a clean state.
       * The submenu panel class is derived from data-submenu so we
       * don't have to hardcode each one. */
      wrap.querySelectorAll("[data-submenu]").forEach((sub) => {
        sub.classList.remove("is-open");
        const subTrigger = sub.querySelector("[aria-expanded]");
        const subKey = sub.getAttribute("data-submenu");
        const subPanel = subKey ? sub.querySelector("." + subKey + "-submenu") : null;
        if (subTrigger) subTrigger.setAttribute("aria-expanded", "false");
        if (subPanel) subPanel.hidden = true;
      });
    });
    // Also close any open EDL select / ADS calendar. They are not in the
    // [data-dropdown] machinery but they share the same outside-click + Esc
    // dismissal contract. Same exception semantics: pass the field name to
    // keep that specific control open.
    document.querySelectorAll(".edl-select").forEach((el) => {
      if (exceptName && el.getAttribute("data-field") === exceptName) return;
      /* Use the dedicated portal-aware close helper so the menu is
       * moved back from document.body to its .edl-select parent and
       * the inline portal positioning styles are stripped. Falls back
       * to a direct hide for any select that wasn't opened via the
       * portal pattern. */
      if (typeof _edlCloseMenu === "function" && el._edlMenuOpen) {
        _edlCloseMenu(el);
      } else {
        const trig = el.querySelector(".edl-select__trigger");
        const menu = el.querySelector(".edl-select__menu");
        if (trig) trig.setAttribute("aria-expanded", "false");
        if (menu) menu.hidden = true;
      }
    });
    document.querySelectorAll(".ads-datepicker").forEach((el) => {
      if (exceptName && el.getAttribute("data-field") === exceptName) return;
      /* Use the dedicated close helper so popover is moved back to its
       * original parent (it lives in document.body while open per the
       * portal architecture). _adsClosePopover is a no-op if the picker
       * wasn't open, so it's safe to call unconditionally. */
      if (typeof _adsClosePopover === "function") {
        _adsClosePopover(el);
      } else {
        const trig = el.querySelector(".ads-datepicker__trigger");
        const pop = el.querySelector(".ads-datepicker__popover");
        if (trig) trig.setAttribute("aria-expanded", "false");
        if (pop) pop.hidden = true;
      }
    });
  }

  function togglePopover(wrap) {
    const trigger = wrap.querySelector("[aria-expanded]");
    const panel =
      wrap.querySelector(".dropdown__menu") || wrap.querySelector(".popover");
    if (!trigger || !panel) return;
    const wasOpen = trigger.getAttribute("aria-expanded") === "true";
    closeAllPopovers(wasOpen ? null : wrap.getAttribute("data-dropdown"));
    if (wasOpen) {
      trigger.setAttribute("aria-expanded", "false");
      panel.hidden = true;
    } else {
      trigger.setAttribute("aria-expanded", "true");
      panel.hidden = false;
    }
  }

  // ----- Filter side panel (Figma node 53-10723) -----------------------------
  // Tracks the trigger that opened the panel so we can return focus on close.
  let filterPanelOpenedFrom = null;

  // Compare collator for natural alphabetical sort (handles diacritics and
  // hyphenated season strings like "25-26" correctly).
  const collator = new Intl.Collator("en", { sensitivity: "base" });

  // Build sorted unique values for one row field. The "All …" default option
  // is added by populateFilterOptions; this only returns real values.
  function uniqueValues(field) {
    /* Feeds the filter dropdowns (Marketplace, Season, Status). Under
     * v1.2 we iterate the projected view so the Marketplace dropdown
     * only advertises Upfront / Scatter / Multi-Year (the values a
     * v1.2 user can actually match against the list). Under v1.1
     * this is the original RATE_CARDS iteration. */
    const set = new Set();
    const source = activeRateCards();
    for (const c of source) {
      const v = c[field];
      if (v != null && v !== "") set.add(v);
    }
    return Array.from(set).sort(collator.compare);
  }

  // ----- Theme switcher (Ad Design System + Wireframe) ---------------------
  // SAME DOM, SAME JS, SAME DATA. The body class flips and the .theme-ads
  // CSS layer activates. We do NOT touch product state when switching, so
  // search, filters, page, scroll position, and dropdown state survive.
  const THEME_STORAGE_KEY = "rcm.theme";
  /* Default theme is Ad Design System (ads-preview) - the high-fidelity
   * version. The second option is "wireframe", a grayscale UX-review mode
   * (renamed 2026-06-29 from the legacy "edl-light"). Both classes are
   * managed on body: .theme-ads layers ADS tokens on top of the default,
   * and .theme-wireframe layers grayscale overrides on top of either. */
  /** @type {"wireframe"|"ads-preview"} */
  function readStoredTheme() {
    try {
      const v = localStorage.getItem(THEME_STORAGE_KEY);
      if (v === "wireframe") return "wireframe";
      /* Migrate legacy "edl-light" stored value to "wireframe" -
       * previous users of the legacy "edl-light" key land in Wireframe, which is the
       * closest visual successor (both lean neutral / non-ADS). */
      if (v === "edl-light") return "wireframe";
      return "ads-preview";
    } catch (_) {
      return "ads-preview";
    }
  }
  function applyTheme(choice) {
    const next = choice === "ads-preview" ? "ads-preview" : "wireframe";
    /* `theme-ads` is the foundation theme that defines every ADS token
     * (colors, spacing, radii, typography) and applies every ADS
     * component rule (modal, button, field, popover, etc.). It stays
     * ON regardless of choice.
     *
     * `theme-wireframe` is a thin OVERLAY that redefines the
     * `--ads-*` color tokens to grayscale + nudges a small set of
     * hardcoded brand surfaces (nav, page-active pill, action icons,
     * Excel/Finder accents) to neutral. All ADS structural rules
     * continue to apply, only color shifts.
     *
     * `theme-edl` is kept in sync with `theme-wireframe` as a no-op
     * safety net for any historical CSS that referenced the old
     * label. The repo authors no `.theme-edl` rules today. */
    document.body.classList.add("theme-ads");
    document.body.classList.toggle("theme-wireframe", next === "wireframe");
    document.body.classList.toggle("theme-edl",       next === "wireframe");
    // Reflect selection in the Theme submenu so it stays in sync with the
    // active theme even when applyTheme is called outside a click (e.g. boot).
    document.querySelectorAll(".theme-submenu__item").forEach((it) => {
      const isActive = it.getAttribute("data-theme") === next;
      it.classList.toggle("theme-submenu__item--active", isActive);
      it.setAttribute("aria-checked", isActive ? "true" : "false");
    });
    try { localStorage.setItem(THEME_STORAGE_KEY, next); } catch (_) {}
  }

  /* ===================================================================
   * APP VERSION SWITCH
   *   1.0 = legacy top horizontal nav
   *   1.1 = app-shell side nav (default; Figma ATLAS side rail + top bar)
   *   1.2 = app-shell side nav, forked 2026-07-09 as the "latest" baseline.
   *         Renders identically to 1.1 today - future feature work targets
   *         v1.2 only so v1.1 stays frozen for stakeholders on that
   *         opt-in link.
   *
   * Default = "1.1". A first-time visitor opening the shared URL with no
   * ?version= query param and no localStorage entry lands on v1.1 so the
   * layout matches the design source of truth on first paint. v1.2 is
   * opt-in via ?version=1.2 or the Profile -> Version submenu (per the
   * 2026-07-09 brief - v1.2 is a selectable option, NOT the new default).
   *
   * 2026-07-13 policy revision ("Always open the latest by default"):
   *   The main / bare Rate Card URL must ALWAYS land on the latest
   *   available version, regardless of what a returning user opted
   *   into in a prior session. Older versions remain reachable only
   *   through an explicit URL param or via the Profile > Version
   *   submenu. Before this revision, applyVersion() and resolveVersion()
   *   both wrote the current pick to localStorage under
   *   VERSION_STORAGE_KEY, and resolveVersion() read it back on the
   *   next boot - which caused a stakeholder tab that had ever visited
   *   ?version=1.0 to keep reopening v1.0 forever, including during
   *   the recent leadership demo. That persistence tier is now removed.
   *
   * Precedence (resolveVersion() at boot):
   *   1. URL query param ?version=1.0 | 1.1 | 1.2 | 2.0 | 2.1 wins if
   *      present and valid. Any other value (missing, empty, "latest",
   *      "beta", typos, etc.) falls through to step 2.
   *   2. Fallback: VERSION_LATEST (the newest version this app knows
   *      about; today "2.1"). Bare URL, hard refresh, closed and
   *      reopened tab, and incognito all resolve to VERSION_LATEST.
   *
   * localStorage is NOT consulted for version. purgeStoredVersion()
   * runs once at boot to remove any legacy VERSION_STORAGE_KEY entry
   * from prior sessions so a returning user who used to be pinned to
   * v1.0 or v1.1 immediately lands on the latest.
   *
   * The version-submenu click handler (search "version-submenu__item"
   * below) writes the chosen version back into the URL via
   * history.replaceState(), so a mid-session refresh does keep the
   * user on the version they explicitly picked. Closing the tab and
   * reopening the bare URL still returns them to latest.
   *
   * applyVersion() is SAFE to call any number of times; it only
   * mutates CSS state:
   *   - body[data-version="1.0" | "1.1" | "1.2" | "2.0" | "2.1"]
   *   - body[data-vnav-pinned="1"] when nav is pinned (app-shell versions only)
   *   - .vnav element [hidden] attribute
   *   - .vnav .vnav--pinned class (when pinned)
   *   - .vnav__hover-zone [hidden] attribute
   * RATE_CARDS, filters, search, pagination, forms, scroll position,
   * and Quick Edit drafts are NEVER touched. Switching versions is a
   * pure layout reskin, not a data reset. v1.0 markup + styles stay
   * fully intact; hidden/reactivated purely via body[data-version].
   * =================================================================== */
  /* Retained for purgeStoredVersion() only. We no longer read or
   * write this key during normal operation; the constant lives on so
   * one line of boot code can clear any legacy entry from before the
   * 2026-07-13 "always-latest by default" policy revision. */
  var VERSION_STORAGE_KEY = "rcm.appVersion";
  /* Central enum of supported version tokens. Keep in sync with
   *   - HTML: the .version-submenu buttons (data-version)
   *   - CSS:  the app-shell body[data-version] selectors
   * A token missing from this list is normalised to VERSION_LATEST. */
  var VERSION_TOKENS = ["1.0", "1.1", "1.2", "2.0", "2.1"];
  /* Single source of truth for "the newest version this build ships".
   * When a future release ships, bump this constant and add its token
   * to VERSION_TOKENS + VERSION_APP_SHELL. Every other
   * default-versus-fallback code path derives from VERSION_LATEST, so
   * there is no other place that hard-codes an outdated version. */
  var VERSION_LATEST = "2.1";
  /* The 2.x line. v2.1 was forked from v2.0 on 2026-08-12 as an exact
   * duplicate: same pages, routes, data, layouts, and interactions.
   * Behaviour gated on "the v2 experience" therefore has to test the
   * whole family rather than a single token, otherwise a 2.1 session
   * silently falls back to 1.x behaviour. The CSS counterpart is the
   * :is([data-version="2.0"], [data-version="2.1"]) selector pair in
   * v2.css and styles.css. Declared as a function (not a var) so call
   * sites earlier in this IIFE resolve it regardless of source order.
   * When 2.1 diverges, branch inside the caller rather than removing
   * a token from this family. */
  function isV2Family(value) {
    return value === "2.0" || value === "2.1";
  }
  /* Historical alias kept because the identifier "VERSION_DEFAULT" is
   * still referenced by applyVersion()'s normalisation of unknown
   * tokens. It always points at VERSION_LATEST now, per the
   * always-latest-by-default policy. */
  var VERSION_DEFAULT = VERSION_LATEST;
  /* Tokens that render with the app-shell side-nav layout. v1.1 was
   * the original app-shell version; v1.2, v2.0, and v2.1 currently
   * share its visual layout, so all four share the same rendering
   * branch in applyVersion(). If a version needs bespoke rendering,
   * add a dedicated branch here rather than forking the whole
   * function. */
  var VERSION_APP_SHELL = ["1.1", "1.2", "2.0", "2.1"];
  /* Pin state for the app-shell side nav. Two values:
   *   "1" = expanded / open
   *   "0" (or missing) = collapsed icon rail
   *
   * Under the 2026-07-08 click-only revision the rail transitions
   * between these two states ONLY when the user clicks the toggle
   * button at the bottom of the rail (data-action="vnav-toggle").
   * Hover, click on the rail body, and focus no longer touch the
   * pinned state. This key persists the user's last chosen state
   * across refreshes AND across in-app navigations. */
  var VNAV_PIN_KEY = "rate-card-nav-pinned";
  /* Route-aware sidebar selection (2026-08-12, Figma 597:6779).
   *
   * This repo implements exactly one product: Rate Card Manager. Every
   * body[data-route] value this app ever sets ("list", "create", the
   * legacy "line" alias, and the full-bleed "atlas" intro deck) is a
   * Rate Card Manager route, so the "Rate cards" nav item is the only
   * item that can ever legitimately be selected here. "Admin" and the
   * other six items (Orders, Inventory, Targeting, Brand safety,
   * Finance, Planning agent) are decorative placeholders for sibling
   * products that are not implemented in this repo - they have no real
   * route to select into, so they stay in their rest state.
   *
   * Selection is therefore a PURE FUNCTION of the current route, not a
   * value persisted in localStorage: this guarantees a single selected
   * item at all times, guarantees the selection survives refresh
   * (recomputed fresh on every boot), and guarantees expand/collapse
   * and Redline Mode (which only ever call setVnavPinned) can never
   * change it. If a future route implements a real Admin/IAM page in
   * THIS repo, map it here explicitly - never hard-code Admin active. */
  var VNAV_ROUTE_KEY = "pricing";
  function resolveVnavRouteKey() {
    return VNAV_ROUTE_KEY;
  }

  /* Portfolio build: Finance and Admin remain visible in the rail, but
   * their cross-product destinations are not linked. */
  var VNAV_UNAVAILABLE = {
    finance: "Finance is not linked in this portfolio preview.",
    admin: "Admin is not linked in this portfolio preview."
  };

  /* These decks are redeployed between demos, and a presenter clicking
   * through to one must not land on the copy their browser cached last
   * week. A timestamp built at click time makes every navigation a
   * distinct URL, so the request always reaches the current build.
   *
   * The separator is read off the URL rather than assumed, so a
   * destination that grows its own query string later gains "&v=" and
   * not a second "?". */
  function vnavExternalUrl(base) {
    return base + (base.indexOf("?") >= 0 ? "&" : "?") + "v=" + Date.now();
  }

  function vnavUnavailableMessage(link) {
    var item = link && link.closest(".vnav__item");
    if (!item) return "";
    return VNAV_UNAVAILABLE[item.getAttribute("data-route")] || "";
  }
  function syncVnavTooltips(pinned) {
    document.querySelectorAll(".vnav__link").forEach(function (link) {
      var tip = link.getAttribute("aria-label") || "";
      if (pinned) link.removeAttribute("data-tooltip");
      else if (tip) link.setAttribute("data-tooltip", tip);
    });
  }
  function setVnavActive(route) {
    var next = route || resolveVnavRouteKey();
    document.querySelectorAll(".vnav__item").forEach(function (item) {
      var isActive = item.getAttribute("data-route") === next;
      item.classList.toggle("vnav__item--active", isActive);
      var link = item.querySelector(".vnav__link");
      if (!link) return;
      if (isActive) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
  }
  window.RateCardShell = window.RateCardShell || {};
  window.RateCardShell.setVnavPinned = setVnavPinned;
  window.RateCardShell.setVnavActive = setVnavActive;
  window.RateCardShell.readVnavPinned = readStoredVnavPinned;
  /* Boot-time cleanup for the pre-2026-07-13 policy. Prior versions
   * of resolveVersion() and applyVersion() wrote every URL-supplied
   * or menu-chosen version into localStorage under
   * VERSION_STORAGE_KEY, and read it back on the next boot to
   * "restore" the user's last choice. That behavior was the direct
   * cause of the leadership-demo regression where a stakeholder tab
   * that had ever visited ?version=1.0 kept reopening v1.0 forever.
   *
   * We now delete the stored token once at boot. Returning users who
   * still have the old entry from a prior visit immediately land on
   * VERSION_LATEST on their next hit of the bare URL, and no new
   * write ever recreates the entry (see resolveVersion() below +
   * applyVersion() which no longer touches localStorage).
   *
   * Wrapped in try/catch for private / no-storage mode safety. */
  function purgeStoredVersion() {
    try { localStorage.removeItem(VERSION_STORAGE_KEY); } catch (_) {}
  }
  /* URL-only resolver invoked once at boot (see applyVersion call in
   * DOMContentLoaded). Reads ?version= from the current URL. If the
   * value is one of VERSION_TOKENS, that wins. Anything else
   * (missing, empty, "latest", "beta", typos, ...) resolves to
   * VERSION_LATEST.
   *
   * localStorage is intentionally NOT consulted here. Restoring a
   * previously-chosen version on the next boot was the mechanism
   * that made an older version reopen by default; the
   * always-latest-by-default policy requires that the bare URL and
   * a hard refresh always resolve to VERSION_LATEST regardless of
   * any prior selection.
   *
   * When a user picks a specific version from the Profile > Version
   * submenu we surface that choice back into location.search via
   * history.replaceState (see the version-submenu click handler
   * below), so a MID-SESSION refresh still keeps them on the
   * version they picked. Closing the tab and reopening the bare
   * URL brings them back to VERSION_LATEST, which is the intended
   * always-latest behavior. */
  function resolveVersion() {
    try {
      var params = new URLSearchParams(location.search);
      var raw = (params.get("version") || "").trim();
      if (VERSION_TOKENS.indexOf(raw) !== -1) return raw;
    } catch (_) { /* URLSearchParams unavailable - fall through. */ }
    return VERSION_LATEST;
  }
  function readStoredVnavPinned() {
    try { return localStorage.getItem(VNAV_PIN_KEY) === "1"; }
    catch (_) { return false; }
  }
  /* Internal helper. The sidebar has exactly one visible control -
   * the toggle button at the bottom of the rail (data-action="vnav-
   * toggle"). Under the 2026-07-08 click-only revision, that button
   * is the ONLY affordance that changes state:
   *   - collapsed -> expanded : setVnavPinned(true)
   *   - expanded  -> collapsed: setVnavPinned(false)
   * Hover and focus do not promote the rail any more (see
   * wireVnavHover()). Both directions persist to localStorage so the
   * user's last chosen state survives a refresh and navigations. */
  function setVnavPinned(pinned) {
    var vnavEl = document.querySelector(".vnav");
    var hoverZone = document.querySelector(".vnav__hover-zone");
    var toggleBtn = document.querySelector('.vnav__close, [data-action="vnav-toggle"]');
    if (vnavEl) vnavEl.classList.toggle("vnav--pinned", pinned);
    if (pinned) document.body.setAttribute("data-vnav-pinned", "1");
    else        document.body.removeAttribute("data-vnav-pinned");
    /* 2026-07-08 click-only revision: the hover-zone element remains
     * in the DOM for CSS layout continuity but is permanently hidden
     * because we no longer treat pointerenter on it (or the rail) as
     * a signal to expand. Leaving it visibly hidden lets us delete
     * the wireVnavHover() listeners without touching markup. */
    if (hoverZone) hoverZone.setAttribute("hidden", "");
    /* Vestigial floating-overlay class - never set anymore. Clear if
     * anything legacy toggled it. */
    if (vnavEl) vnavEl.classList.remove("vnav--hovered");
    /* Sync the toggle button so screen readers + tooltip flip with
     * state. The chevron glyph itself rotates via CSS off .vnav
     * --pinned so we don't need to swap the SVG here. */
    if (toggleBtn) {
      var label = pinned ? "Collapse navigation" : "Expand navigation";
      toggleBtn.setAttribute("aria-label", label);
      toggleBtn.setAttribute("aria-expanded", pinned ? "true" : "false");
      if (pinned) toggleBtn.setAttribute("data-tooltip", label);
      else toggleBtn.removeAttribute("data-tooltip");
    }
    syncVnavTooltips(pinned);
    try { localStorage.setItem(VNAV_PIN_KEY, pinned ? "1" : "0"); } catch (_) {}
  }
  /* Search input placeholder swap (single source of truth).
   *
   * v1.0 / v1.1: always use the -v11 copy.
   * v1.2       : use -v12 at desktop widths, swap to the shortened
   *              -v12-narrow copy ("Search rate cards") once the
   *              viewport reaches the point where the toolbar's search
   *              input can no longer render the long copy without
   *              truncation. The threshold matches the first RCM
   *              responsive breakpoint (<=1280) so the placeholder
   *              swap fires at the same moment the table starts
   *              shedding SalesHub ID, Last updated, and Ver. columns.
   *
   * This function is called from applyVersion() and from the window
   * resize handler wired at the end of initApp(); v1.1 is a no-op path
   * so v1.1 users never see a placeholder change on resize. */
  var SEARCH_NARROW_MAX_WIDTH = 1280;
  function syncSearchPlaceholder(version) {
    var searchInput = document.querySelector('.search__input[data-action="search"]');
    if (!searchInput) return;
    var next;
    if (version === "2.1") {
      /* 2.1 pins the search field to the reference 399px at every
       * viewport, and the v1.2 copy is 41px too wide for it, so it needs
       * its own shorter line rather than the width-based swap below.
       * Same four searchable columns, just tighter. */
      next = searchInput.getAttribute("data-placeholder-v21")
        || searchInput.getAttribute("data-placeholder-v12");
    } else if (isModernAppVersion(version)) {
      var isNarrow = typeof window !== "undefined"
        && window.innerWidth > 0
        && window.innerWidth <= SEARCH_NARROW_MAX_WIDTH;
      next = isNarrow
        ? (searchInput.getAttribute("data-placeholder-v12-narrow")
           || searchInput.getAttribute("data-placeholder-v12"))
        : searchInput.getAttribute("data-placeholder-v12");
    } else {
      next = searchInput.getAttribute("data-placeholder-v11");
    }
    if (next) searchInput.setAttribute("placeholder", next);
  }
  function applyVersion(choice) {
    /* Normalise to a supported enum. Anything outside VERSION_TOKENS
     * (undefined / typo / stale localStorage) resolves to the
     * default so we never land on a partial/broken layout. */
    var next = VERSION_TOKENS.indexOf(choice) !== -1 ? choice : VERSION_DEFAULT;
    document.body.setAttribute("data-version", next);
    /* v1.1, v1.2, and v2.0 use the app-shell layout (side rail +
     * top bar). v1.0 hides the rail entirely and falls back to the
     * legacy horizontal top nav. */
    var isAppShell = VERSION_APP_SHELL.indexOf(next) !== -1;
    var vnavEl = document.querySelector(".vnav");
    var hoverZone = document.querySelector(".vnav__hover-zone");
    if (vnavEl) {
      if (isAppShell) {
        vnavEl.removeAttribute("hidden");
        /* Hover zone stays hidden in the 2026-07-08 click-only model
         * (no pointer-based expand any more). Kept in DOM so CSS
         * selectors that reference it still resolve without errors. */
        if (hoverZone) hoverZone.setAttribute("hidden", "");
        /* Restore the user's last pinned choice. Default = unpinned
         * (collapsed rail) per the brief: "On first load, show a
         * narrow left icon rail." */
        setVnavPinned(readStoredVnavPinned());
        setVnavActive(resolveVnavRouteKey());
      } else {
        vnavEl.setAttribute("hidden", "");
        vnavEl.classList.remove("vnav--pinned");
        vnavEl.classList.remove("vnav--hovered");
        if (hoverZone) hoverZone.setAttribute("hidden", "");
        document.body.removeAttribute("data-vnav-pinned");
      }
    }
    document.querySelectorAll(".version-submenu__item").forEach(function(it){
      var isActive = it.getAttribute("data-version") === next;
      it.classList.toggle("version-submenu__item--active", isActive);
      it.setAttribute("aria-checked", isActive ? "true" : "false");
    });
    /* v1.2 replaces the search placeholder because SalesHub ID moves
     * to the right of Buying Entity and is no longer the second
     * primary visual column - the placeholder should still advertise
     * it as searchable but with different emphasis. The input keeps
     * both texts as data attributes; JS just flips which one is
     * live. v1.0 and v1.1 both use the -v11 (default) copy. In v1.2,
     * we also swap to a shortened "Search rate cards" copy at narrow
     * widths so the placeholder stays readable when the toolbar is
     * compressed. syncSearchPlaceholder() below is the single source
     * of truth and is also wired to window resize. */
    syncSearchPlaceholder(next);
    /* v1.2 rows are a projection of RATE_CARDS with PM's marketplace
     * remap + first-10 row overrides applied. Re-render the table so
     * a version switch immediately reflects the new dataset (rather
     * than waiting for the next filter / search keystroke). We only
     * re-render if the .table__body node exists (avoids running
     * before the initial boot render).
     *
     * The Marketplace filter dropdown is also repopulated because it
     * caches its option list from uniqueValues() at boot. Without
     * this refresh, a live switch from v1.1 to v1.2 would still show
     * Addressable / Programmatic / Streaming / Sponsorship / Sports
     * in the filter menu even though those values no longer appear
     * in any visible row. */
    if (document.querySelector('[data-rows]')) {
      try { renderTable(); } catch (_) {}
      try { populateFilterOptions(); } catch (_) {}
    }
    /* Rebuild the Create / Edit form dropdowns so the Marketplace menu
     * reflects the active version's option set. Without this refresh,
     * a live switch from v1.1 to v1.2 would still show Addressable,
     * Programmatic, Sponsorship, Sports, Streaming, and Multiplatform
     * in the form's Marketplace dropdown even though the PRD-canonical
     * set is just Upfront / Scatter / Multi-Year. Same for the reverse
     * direction. Wrapped in a try because the Create page may not be
     * mounted in every route (returns without touching selects then). */
    try { populateEdlSelectOptions(); } catch (_) {}
    /* Keep the v1.2-only Buyer + Deal Context hoverable tiles' ARIA +
     * tabindex in sync with the active version. When switching to v1.2
     * each tile gains tabindex=0 / aria-label / aria-describedby; when
     * switching away, those attributes are stripped and any open hover
     * popover is closed. The sync functions are exposed by
     * wireHoverPopover() at boot. */
    /* Intentionally no localStorage write for version. Per the
     * 2026-07-13 always-latest-by-default policy, the bare URL and a
     * hard refresh must always resolve to VERSION_LATEST regardless
     * of what the user picked in a prior session. Mid-session refresh
     * persistence is instead handled by the version-submenu click
     * handler, which rewrites location.search via history.replaceState
     * so the chosen version rides on the URL, not on localStorage. */
    document.dispatchEvent(new CustomEvent("rcm:versionchange", {
      detail: { version: next }
    }));
  }

  /* ---- Hover / click expand wiring ----------------------------------
   * Click-only model (2026-07-08 revision):
   *   - The rail expands / collapses ONLY when the user clicks the
   *     dedicated toggle button at the bottom of the rail
   *     (data-action="vnav-toggle", handled in the delegated click
   *     handler in wireDelegatedEvents; that calls setVnavPinned
   *     with the flipped value).
   *   - No pointerenter / pointerleave / focusin / focusout handlers
   *     touch the pinned state. Moving the cursor over the rail is
   *     visually inert.
   *   - The 6px .vnav__hover-zone strip at the screen edge is left in
   *     the DOM but permanently hidden by setVnavPinned() so it can't
   *     receive pointer events either.
   *
   * The function stub is kept (rather than deleted) so the boot
   * sequence in DOMContentLoaded (wireVnavHover()) stays valid; this
   * lets us re-introduce hover behavior later behind a feature flag
   * without touching the init order. */
  function wireVnavHover() {
    /* Intentionally empty: hover-to-expand was removed per the
     * 2026-07-08 brief ("Remove all hover-to-expand behavior from the
     * left navigation/sidebar"). Do not reintroduce pointerenter /
     * focusin listeners on .vnav or .vnav__hover-zone without a new
     * brief - the sidebar state is now user-controlled via the toggle
     * button only, and adding hover triggers here silently breaks
     * that contract. */
  }

  /* ----- ADS Dropdown (filter panel) -------------------------------------
   * Vanilla JS implementation of the ADS Dropdown component (Figma 146:1903 +
   * 150:1791). One instance per .ads-dd[data-filter] element. State lives in
   * the DOM (data-value attribute + .is-selected option class) so refreshing
   * the panel re-renders cleanly.
   *
   * Options are populated from the live dataset (uniqueValues) so the panel
   * never offers a filter value that doesn't exist in the data.
   *
   * Interactions:
   *   - Click trigger toggles menu open/close
   *   - Click option selects + closes
   *   - Escape closes
   *   - Outside click closes (handled in the document-level click handler)
   *   - ArrowDown/ArrowUp move active option (when menu open)
   *   - Enter on focused option selects
   */
  /* The three checkbox groups. Status draws from the shared status list
   * so the drawer can only ever offer a state a row can actually be in;
   * the other two draw from the data, so a value nobody uses never
   * appears. `format` is display only, the stored value is untouched. */
  /* Declaration order is the order chips appear in and the order the
   * drawer reads, so it matches the drawer's field order. */
  const FILTER_GROUP_CONFIG = {
    marketplace: { field: "marketplace", legend: "Marketplace" },
    season:      { field: "season",      legend: "Deal season", format: formatSeason },
    status:      { field: "status",      legend: "Status" },
  };

  function filterGroupValues(filterKey) {
    if (filterKey === "status") {
      return RCM_STATUSES.map(function (entry) { return entry.value; });
    }
    return uniqueValues(FILTER_GROUP_CONFIG[filterKey].field);
  }

  function filterValueLabel(filterKey, value) {
    const cfg = FILTER_GROUP_CONFIG[filterKey];
    return cfg && cfg.format ? cfg.format(value) : value;
  }

  /* Builds one ADS checkbox per available value. Rebuilt whenever the
   * dataset or version changes, then re-checked from the draft by
   * renderDraftIntoSelects(). */
  function populateFilterOptions() {
    for (const filterKey of Object.keys(FILTER_GROUP_CONFIG)) {
      const host = document.querySelector('[data-filter-options="' + filterKey + '"]');
      if (!host) continue;
      host.replaceChildren();
      for (const value of filterGroupValues(filterKey)) {
        host.appendChild(buildFilterCheckbox(filterKey, value));
      }
    }
    populateEntityIndex();
  }

  /* One row of the group: the shared ADS checkbox plus its visible text.
   * buildAdsCheckbox only emits the control, so the label text is added
   * here and the whole row is a <label> that activates the box. */
  function buildFilterCheckbox(filterKey, value) {
    const label = filterValueLabel(filterKey, value);
    const row = document.createElement("label");
    row.className = "fgroup__option";
    row.setAttribute("data-filter-value", value);
    const control = window.buildAdsCheckbox({
      label: label,
      checked: false,
      onChange: function (checked) {
        setDraftMultiValue(filterKey, value, checked);
      }
    });
    /* The visible text names the control, so the aria-label the factory
     * adds would double it up for a screen reader. */
    const input = control.querySelector(".ads-checkbox__input");
    if (input) {
      input.removeAttribute("aria-label");
      input.setAttribute("data-filter-checkbox", filterKey);
      input.setAttribute("data-filter-value", value);
    }
    const text = document.createElement("span");
    text.className = "fgroup__option-text";
    text.textContent = label;
    row.appendChild(control);
    row.appendChild(text);
    return row;
  }

  /* The season dropdown's collapsed label. It answers "what is this
   * filtering by" without the list being open. */
  function syncSeasonSummary() {
    const summary = document.querySelector('[data-filter-summary="season"]');
    if (!summary) return;
    const chosen = draftFilters.season || [];
    if (!chosen.length) {
      summary.textContent = "All seasons";
      return;
    }
    summary.textContent = chosen.length === 1
      ? filterValueLabel("season", chosen[0])
      : chosen.length + " seasons selected";
  }

  function toggleSeasonMenu(force) {
    const trigger = document.querySelector('[data-action="toggle-season-menu"]');
    const menu = document.getElementById("fp-season-menu");
    if (!trigger || !menu) return;
    const open = typeof force === "boolean" ? force : menu.hidden;
    menu.hidden = !open;
    trigger.setAttribute("aria-expanded", open ? "true" : "false");
  }

  function setDraftMultiValue(filterKey, value, checked) {
    const current = draftFilters[filterKey] || [];
    const at = current.indexOf(value);
    if (checked && at === -1) current.push(value);
    if (!checked && at !== -1) current.splice(at, 1);
    draftFilters[filterKey] = current;
    if (filterKey === "season") syncSeasonSummary();
    syncFilterResultCount();
  }

  function buildAdsDdOption(value, label, disabled) {
    const li = document.createElement("li");
    li.className = "ads-dd__option";
    li.setAttribute("role", "option");
    li.setAttribute("data-value", value);
    li.setAttribute("tabindex", "-1");
    if (disabled) {
      li.classList.add("is-disabled");
      li.setAttribute("aria-disabled", "true");
    }
    li.textContent = label;
    return li;
  }

  var adsSelectCounter = 0;

  /* ------------------------------------------------------------------
   * Searchable single-select.
   *
   * A <select data-ads-search-select> gets the same ADS Dropdown as any
   * other, plus a search row at the top of its listbox. It stays one
   * component rather than a second picker: the trigger, the overlay
   * positioning, the outside-click and Escape handling, the option
   * markup and every token in .ads-dd__* are the ones already here.
   *
   * It is for enums that are too long to scan but still closed: the user
   * has to land on a real option, so nothing typed here is ever kept as
   * a value.
   * ------------------------------------------------------------------ */
  function adsDdSearchable(root) {
    return Boolean(root && root.querySelector('.ads-dd__search-input'));
  }

  /* Values read as "Category: Dimension to Value", and a seller looking
   * for auto intenders may type any part of that path in any order. So
   * the query is split on whitespace and every word has to appear
   * somewhere in the label, rather than the label having to start with
   * or contain the query as one run of characters. The arrow is folded
   * to a space so "purchase intent auto" and "intent > auto" both work
   * without the user reproducing a character they cannot type. */
  function adsDdNormalize(text) {
    return String(text == null ? '' : text)
      .toLocaleLowerCase()
      .replace(/[\u2192>]/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function adsDdMatches(label, query) {
    if (!query) return true;
    const haystack = adsDdNormalize(label);
    return adsDdNormalize(query).split(' ').every(function (word) {
      return haystack.indexOf(word) >= 0;
    });
  }

  function buildAdsDdSearchRow(select) {
    const row = document.createElement('li');
    row.className = 'ads-dd__search';
    /* Presentational: the listbox's options are its children, and a
     * search field is not one of them. */
    row.setAttribute('role', 'presentation');
    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'ads-dd__search-input';
    input.id = select.id + '-search';
    input.setAttribute('autocomplete', 'off');
    input.setAttribute('spellcheck', 'false');
    input.setAttribute('placeholder',
      select.getAttribute('data-ads-search-placeholder') || 'Search');
    input.setAttribute('aria-label',
      select.getAttribute('data-ads-search-label') || 'Search options');
    /* The field types into the listbox rather than owning it: the
     * trigger is the combobox and keeps aria-expanded, so this input
     * only points at the list it is filtering. */
    input.setAttribute('aria-controls', select.id + '-menu');
    row.appendChild(input);
    return row;
  }

  function buildAdsDdEmptyRow(select) {
    const row = document.createElement('li');
    row.className = 'ads-dd__empty';
    row.setAttribute('role', 'presentation');
    row.hidden = true;
    row.textContent = select.getAttribute('data-ads-search-empty')
      || 'No matches';
    return row;
  }

  /* Hides the options the query rules out and shows the empty row when
   * it rules out all of them. Options are hidden rather than removed so
   * the selected one keeps its place in the list the moment the query is
   * cleared. */
  function filterAdsDdOptions(root, query) {
    if (!root) return;
    const menu = root.querySelector('.ads-dd__menu');
    if (!menu) return;
    var visible = 0;
    menu.querySelectorAll('.ads-dd__option').forEach(function (option) {
      const match = adsDdMatches(option.textContent, query);
      option.hidden = !match;
      if (match) visible += 1;
    });
    const empty = menu.querySelector('.ads-dd__empty');
    if (empty) empty.hidden = visible > 0;
  }

  function adsDdVisibleOptions(menu) {
    if (!menu) return [];
    return Array.from(menu.querySelectorAll('.ads-dd__option'))
      .filter(function (option) {
        return !option.hidden && option.getAttribute('aria-disabled') !== 'true';
      });
  }

  function refreshAdsSelect(select) {
    if (!select) return;
    const root = select.closest('.ads-dd');
    if (!root) return;
    const menu = root.querySelector('.ads-dd__menu');
    if (!menu) return;
    /* Rebuilding the options must not throw away the search row or what
     * the user has typed into it: populateForm() refreshes this control
     * whenever the panel loads a record, which can happen while the menu
     * is open. */
    const searchRow = menu.querySelector('.ads-dd__search');
    const searchInput = searchRow && searchRow.querySelector('.ads-dd__search-input');
    const query = searchInput ? searchInput.value : '';
    menu.replaceChildren();
    if (searchRow) menu.appendChild(searchRow);
    Array.prototype.forEach.call(select.options, function (option) {
      menu.appendChild(buildAdsDdOption(option.value, option.textContent, option.disabled));
    });
    if (searchRow) {
      menu.appendChild(buildAdsDdEmptyRow(select));
      filterAdsDdOptions(root, query);
    }
    const selected = select.selectedOptions && select.selectedOptions[0];
    const label = selected ? selected.textContent : select.value;
    syncAdsDdPresentation(root, select.value, label);
    const trigger = root.querySelector('.ads-dd__trigger');
    if (trigger) {
      trigger.disabled = select.disabled;
      trigger.setAttribute('aria-disabled', select.disabled ? 'true' : 'false');
    }
  }

  function enhanceAdsSelect(select, config) {
    if (!select || select.hidden || select.multiple) return null;
    if (select.getAttribute('data-ads-enhanced') === 'true') {
      refreshAdsSelect(select);
      return select.closest('.ads-dd');
    }
    config = config || {};
    if (!select.id) select.id = 'ads-select-' + (++adsSelectCounter);
    const field = select.closest('.field, label, .create-md__filter');
    var label = document.querySelector('label[for="' + select.id + '"]');
    if (!label && field && field.tagName === 'LABEL') label = field;
    const labelText = label
      ? (label.querySelector('span') || label).textContent.trim()
      : (select.getAttribute('aria-label') || config.label || 'Select');
    if (label && !label.id) label.id = select.id + '-label';

    const root = document.createElement('div');
    const size = config.size === 'default' ? 'default' : 'small';
    root.className = 'ads-dd ads-dd--' + size + ' ads-dd--overlay ads-select';
    root.setAttribute('data-ads-dd', '');
    root.setAttribute('data-dropdown-control', select.id);
    const emptyOption = Array.prototype.find.call(
      select.options,
      function (option) { return option.value === ''; }
    );
    const placeholder = config.placeholder
      || (emptyOption && emptyOption.textContent)
      || select.getAttribute('data-placeholder')
      || 'Select option';
    root.setAttribute('data-placeholder', placeholder);

    const trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.className = 'ads-dd__trigger';
    trigger.id = select.id + '-trigger';
    trigger.setAttribute('role', 'combobox');
    trigger.setAttribute('aria-haspopup', 'listbox');
    trigger.setAttribute('aria-expanded', 'false');
    trigger.setAttribute('aria-controls', select.id + '-menu');
    trigger.setAttribute('data-action', 'toggle-ads-dd');
    if (label && label.id) trigger.setAttribute('aria-labelledby', label.id + ' ' + select.id + '-value');
    else trigger.setAttribute('aria-label', labelText);
    if (select.required) trigger.setAttribute('aria-required', 'true');

    const value = document.createElement('span');
    value.className = 'ads-dd__value';
    value.id = select.id + '-value';
    trigger.appendChild(value);

    const caret = document.createElement('span');
    caret.className = 'ads-dd__caret';
    caret.setAttribute('aria-hidden', 'true');
    const caretImage = document.createElement('img');
    caretImage.alt = '';
    caretImage.src = size === 'small'
      ? './assets/ads-dropdown-caret.svg'
      : './assets/ads-dropdown-caret-default.svg';
    caret.appendChild(caretImage);
    trigger.appendChild(caret);

    const menu = document.createElement('ul');
    menu.className = 'ads-dd__menu';
    menu.id = select.id + '-menu';
    menu.setAttribute('role', 'listbox');
    if (label && label.id) menu.setAttribute('aria-labelledby', label.id);
    else menu.setAttribute('aria-label', labelText);
    menu.setAttribute('tabindex', '-1');
    menu.hidden = true;

    if (select.hasAttribute('data-ads-search-select')) {
      root.classList.add('ads-dd--searchable');
      menu.appendChild(buildAdsDdSearchRow(select));
    }

    select.parentElement.insertBefore(root, select);
    root.appendChild(select);
    root.appendChild(trigger);
    root.appendChild(menu);
    select.hidden = true;
    select.classList.add('ads-dd__native');
    select.setAttribute('aria-hidden', 'true');
    select.setAttribute('tabindex', '-1');
    select.setAttribute('data-ads-enhanced', 'true');
    select.addEventListener('change', function () { refreshAdsSelect(select); });
    refreshAdsSelect(select);
    return root;
  }

  window.enhanceAdsSelect = enhanceAdsSelect;
  window.refreshAdsDropdown = refreshAdsSelect;

  // Reflect draftFilters into the drawer controls. Called every time the
  // panel opens, which is what makes Cancel discard changes: the draft is
  // reseeded from applied and the controls are repainted from it.
  function renderDraftIntoSelects() {
    document.querySelectorAll("[data-filter-checkbox]").forEach(function (input) {
      const key = input.getAttribute("data-filter-checkbox");
      const value = input.getAttribute("data-filter-value");
      input.checked = (draftFilters[key] || []).indexOf(value) !== -1;
    });
    renderEntitySelection();
    syncSeasonSummary();
    syncFilterResultCount();
  }

  /* ---- Buying entity autocomplete -----------------------------------
   * Every distinct name plus Saleshub ID pair in the current dataset,
   * built once per dataset change. A few entities own more than one ID,
   * so the pair is the unit, and the ID is what gets applied. */
  let ENTITY_INDEX = [];

  function populateEntityIndex() {
    const seen = Object.create(null);
    const out = [];
    activeRateCards().forEach(function (row) {
      const id = String(row.saleshubId || "");
      if (!id || seen[id]) return;
      seen[id] = true;
      out.push({ id: id, name: String(row.buyingEntity || "Not set") });
    });
    out.sort(function (a, b) { return a.name.localeCompare(b.name, "en"); });
    ENTITY_INDEX = out;
  }

  /* Name match is a case-insensitive substring so a seller can type what
   * they remember; ID match is exact, because a partial Saleshub ID is
   * not something anyone means to search for. */
  function searchEntities(term) {
    const q = String(term || "").trim().toLowerCase();
    if (!q) return [];
    return ENTITY_INDEX.filter(function (entry) {
      return entry.name.toLowerCase().indexOf(q) !== -1
        || entry.id.toLowerCase() === q;
    });
  }

  function findEntity(id) {
    for (var i = 0; i < ENTITY_INDEX.length; i++) {
      if (ENTITY_INDEX[i].id === id) return ENTITY_INDEX[i];
    }
    return null;
  }

  /* Paint the field from the draft. A chosen entity shows as its full
   * "name - id" label so the field reads as a selection rather than as
   * leftover text the user typed. */
  function renderEntitySelection() {
    const input = document.getElementById("fp-entity");
    if (!input) return;
    const chosen = findEntity(draftFilters.buyingEntityId || "");
    input.value = chosen ? entityLabel(chosen.name, chosen.id) : "";
    setEntityResults([], "");
    syncEntityPresentation();
  }

  function syncEntityPresentation() {
    const input = document.getElementById("fp-entity");
    if (!input) return;
    const wrap = input.closest(".ads-search");
    const clear = wrap && wrap.querySelector('[data-action="clear-filter-entity"]');
    const filled = Boolean(input.value);
    if (wrap) wrap.setAttribute("data-filled", String(filled));
    if (clear) clear.hidden = !filled;
  }

  function setEntityStatus(message) {
    const el = document.querySelector("[data-entity-status]");
    if (!el) return;
    el.textContent = message || "";
    el.hidden = !message;
  }

  function setEntityResults(results, term) {
    const list = document.getElementById("fp-entity-results");
    const input = document.getElementById("fp-entity");
    if (!list) return;
    list.replaceChildren();
    if (!term) {
      list.hidden = true;
      if (input) input.setAttribute("aria-expanded", "false");
      setEntityStatus("");
      return;
    }
    if (!results.length) {
      list.hidden = true;
      if (input) input.setAttribute("aria-expanded", "false");
      setEntityStatus("No buying entities match " + term + ".");
      return;
    }
    results.slice(0, 8).forEach(function (entry) {
      const li = document.createElement("li");
      li.className = "fentity__result";
      li.setAttribute("role", "option");
      li.setAttribute("aria-selected", "false");
      li.setAttribute("tabindex", "-1");
      li.setAttribute("data-action", "select-entity");
      li.setAttribute("data-entity-id", entry.id);
      li.textContent = entityLabel(entry.name, entry.id);
      list.appendChild(li);
    });
    list.hidden = false;
    if (input) input.setAttribute("aria-expanded", "true");
    setEntityStatus("");
  }

  function chooseEntity(id) {
    draftFilters.buyingEntityId = id || "";
    renderEntitySelection();
    syncFilterResultCount();
  }

  /* Typing is debounced so a burst of keystrokes resolves once. The
   * dataset is in memory, so the wait is the only thing between a
   * keystroke and results; the pending state is shown while it runs. */
  const ENTITY_SEARCH_DELAY = 200;
  let entitySearchTimer = null;

  function queueEntitySearch(term) {
    if (entitySearchTimer) clearTimeout(entitySearchTimer);
    const trimmed = String(term || "").trim();
    if (!trimmed) {
      setEntityResults([], "");
      return;
    }
    setEntityStatus("Searching buying entities");
    entitySearchTimer = setTimeout(function () {
      entitySearchTimer = null;
      setEntityResults(searchEntities(trimmed), trimmed);
    }, ENTITY_SEARCH_DELAY);
  }

  /* ---- Result count -------------------------------------------------
   * The Apply button counts what the DRAFT would return, so the user can
   * see the effect of a selection before committing to it. */
  function countRowsForFilters(filters) {
    const previous = appliedFilters;
    appliedFilters = filters;
    try {
      return getFilteredRows().length;
    } finally {
      appliedFilters = previous;
    }
  }

  function syncFilterResultCount() {
    const button = document.querySelector("[data-filter-apply]");
    if (!button) return;
    const count = countRowsForFilters(cloneFilters(draftFilters));
    button.textContent = "Show " + count + " rate card" + (count === 1 ? "" : "s");
    /* Zero is a legitimate answer, so the button stays enabled and the
     * user can go look at the empty state rather than being stuck. */
    button.disabled = false;
  }

  // Wire the free-text controls inside the drawer. Checkbox groups get
  // their handlers when they are built. Called once on boot.
  function wireDraftSelects() {
    const input = document.getElementById("fp-entity");
    if (!input) return;
    input.addEventListener("input", function (event) {
      /* Typing past a chosen entity means the user is replacing it. */
      if (draftFilters.buyingEntityId) {
        draftFilters.buyingEntityId = "";
        syncFilterResultCount();
      }
      syncEntityPresentation();
      queueEntitySearch(event.target.value);
    });
    input.addEventListener("keydown", function (event) {
      const list = document.getElementById("fp-entity-results");
      if (event.key === "ArrowDown" && list && !list.hidden) {
        event.preventDefault();
        const first = list.querySelector(".fentity__result");
        if (first) first.focus();
        return;
      }
      if (event.key === "Enter") {
        event.preventDefault();
        const first = list && !list.hidden && list.querySelector(".fentity__result");
        if (first) chooseEntity(first.getAttribute("data-entity-id"));
      }
    });
    const list = document.getElementById("fp-entity-results");
    if (!list) return;
    list.addEventListener("keydown", function (event) {
      const options = Array.prototype.slice.call(list.querySelectorAll(".fentity__result"));
      const at = options.indexOf(document.activeElement);
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        const next = event.key === "ArrowDown" ? at + 1 : at - 1;
        if (next < 0) { input.focus(); return; }
        if (options[next]) options[next].focus();
        return;
      }
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        if (options[at]) chooseEntity(options[at].getAttribute("data-entity-id"));
      }
    });
  }

  /* Toggle an ADS dropdown open/closed. Used by the document-level click
   * handler when the user clicks a [data-action="toggle-ads-dd"] trigger
   * (the trigger is inside a .ads-dd container). */
  function toggleAdsDd(root) {
    if (!root) return;
    const trigger = root.querySelector('.ads-dd__trigger');
    const menu = root.querySelector('.ads-dd__menu');
    if (!trigger || !menu || trigger.disabled) return;
    const isOpen = trigger.getAttribute('aria-expanded') === 'true';
    closeAllAdsDds(); // only one open at a time
    if (isOpen) return;
    trigger.setAttribute('aria-expanded', 'true');
    menu.hidden = false;
    if (root.classList.contains('ads-dd--overlay')
        || root.classList.contains('create-md__dropdown')) {
      const styles = window.getComputedStyle(root);
      const menuGap = parseFloat(styles.getPropertyValue('--ads-dd-menu-gap')) || 4;
      const rootRect = root.getBoundingClientRect();
      const triggerRect = trigger.getBoundingClientRect();
      const boundary = root.closest(
        '.create-md__accordion-panel, .create-md__detail, .fpanel__body'
      );
      const boundaryRect = boundary ? boundary.getBoundingClientRect() : null;
      const visibleTop = Math.max(0, boundaryRect ? boundaryRect.top : 0);
      const visibleBottom = Math.min(
        window.innerHeight,
        boundaryRect ? boundaryRect.bottom : window.innerHeight
      );
      const roomBelow = Math.max(0, visibleBottom - triggerRect.bottom - menuGap);
      const roomAbove = Math.max(0, triggerRect.top - visibleTop - menuGap);
      const placeAbove = menu.scrollHeight > roomBelow && roomAbove > roomBelow;
      const available = placeAbove ? roomAbove : roomBelow;
      menu.style.maxHeight = available + 'px';
      const menuHeight = Math.min(menu.scrollHeight, available);
      const menuTop = placeAbove
        ? triggerRect.top - rootRect.top - menuGap - menuHeight
        : triggerRect.bottom - rootRect.top + menuGap;
      menu.style.setProperty('--ads-dd-menu-top', menuTop + 'px');
    }
    /* A searchable list opens on its search field, so the first
     * keystroke filters instead of jumping the highlight. The query from
     * the previous visit is dropped: the list a user opens is always the
     * whole list, with their current choice showing as selected. */
    const search = menu.querySelector('.ads-dd__search-input');
    if (search) {
      search.value = '';
      filterAdsDdOptions(root, '');
      const chosen = menu.querySelector('.ads-dd__option.is-selected:not(.is-disabled)');
      if (chosen) chosen.scrollIntoView({ block: 'nearest' });
      search.focus({ preventScroll: true });
      return;
    }
    // Focus the currently selected option (or first) for keyboard nav
    const opts = menu.querySelectorAll('.ads-dd__option');
    const sel = menu.querySelector('.ads-dd__option.is-selected:not(.is-disabled)')
      || menu.querySelector('.ads-dd__option:not(.is-disabled)')
      || opts[0];
    if (sel) {
      sel.focus({ preventScroll: true });
      sel.scrollIntoView({ block: 'nearest' });
    }
  }

  function closeAllAdsDds(excludeRoot, restoreFocus) {
    document.querySelectorAll('.ads-dd').forEach((root) => {
      if (root === excludeRoot) return;
      const trigger = root.querySelector('.ads-dd__trigger');
      const menu = root.querySelector('.ads-dd__menu');
      const wasOpen = trigger && trigger.getAttribute('aria-expanded') === 'true';
      if (trigger) trigger.setAttribute('aria-expanded', 'false');
      if (menu) menu.hidden = true;
      if (restoreFocus && wasOpen && trigger) trigger.focus({ preventScroll: true });
    });
  }

  function syncAdsDdPresentation(root, value, label) {
    if (!root) return;
    const current = value || '';
    const placeholder = root.getAttribute('data-placeholder') || 'Select';
    root.setAttribute('data-value', current);
    const valueEl = root.querySelector('.ads-dd__value');
    if (valueEl) {
      valueEl.textContent = current ? (label || current) : placeholder;
      valueEl.classList.toggle('ads-dd__value--placeholder', !current);
      valueEl.classList.toggle('ads-dd__value--selected', Boolean(current));
      /* .ads-dd__value ellipsizes, and a condition path is long enough
       * to reach that. The shared truncation tooltip hands back the part
       * the field cannot show, on hover and on keyboard focus, and stays
       * out of the way when the value already fits. */
      if (root.classList.contains('ads-dd--searchable')) {
        const full = current ? (label || current) : '';
        const trigger = root.querySelector('.ads-dd__trigger');
        if (trigger) {
          if (full) {
            trigger.setAttribute('data-tooltip', full);
            trigger.setAttribute('data-tooltip-truncate', 'auto');
          } else {
            trigger.removeAttribute('data-tooltip');
            trigger.removeAttribute('data-tooltip-truncate');
          }
        }
      }
    }
    root.querySelectorAll('.ads-dd__option').forEach((option) => {
      const selected = option.getAttribute('data-value') === current;
      option.classList.toggle('is-selected', selected);
      option.setAttribute('aria-selected', selected ? 'true' : 'false');
    });
  }

  window.syncAdsDropdown = function (control) {
    if (!control) return;
    const root = control.closest('.ads-dd');
    const selected = control.selectedOptions && control.selectedOptions[0];
    syncAdsDdPresentation(root, control.value, selected ? selected.textContent : control.value);
  };

  function selectAdsDdOption(root, value, label) {
    if (!root) return;
    const chosen = Array.prototype.find.call(
      root.querySelectorAll('.ads-dd__option'),
      function (option) { return option.getAttribute('data-value') === value; }
    );
    if (chosen && chosen.getAttribute('aria-disabled') === 'true') return;
    const filterKey = root.getAttribute('data-filter');
    const controlId = root.getAttribute('data-dropdown-control');
    if (filterKey) {
      draftFilters[filterKey] = value;
      const cfg = FILTER_DD_CONFIG[filterKey] || {};
      root.setAttribute('data-placeholder', cfg.placeholder || 'Select');
      syncAdsDdPresentation(root, value, label);
      if (value === 'all') {
        const valueEl = root.querySelector('.ads-dd__value');
        if (valueEl) {
          valueEl.textContent = cfg.placeholder || 'Select';
          valueEl.classList.add('ads-dd__value--placeholder');
          valueEl.classList.remove('ads-dd__value--selected');
        }
      }
    } else if (controlId) {
      const control = document.getElementById(controlId);
      if (!control) return;
      control.value = value;
      syncAdsDdPresentation(root, value, label);
      control.dispatchEvent(new Event('input', { bubbles: true }));
      control.dispatchEvent(new Event('change', { bubbles: true }));
    } else {
      return;
    }
    // Close the menu and return focus to the trigger
    const trigger = root.querySelector('.ads-dd__trigger');
    const menu = root.querySelector('.ads-dd__menu');
    if (trigger) {
      trigger.setAttribute('aria-expanded', 'false');
      trigger.focus({ preventScroll: true });
    }
    if (menu) menu.hidden = true;
  }

  /* Everything focusable in the drawer, in tab order. */
  function filterPanelFocusables() {
    const panel = document.getElementById("filter-panel");
    if (!panel) return [];
    return Array.prototype.filter.call(
      panel.querySelectorAll("button, [href], input, select, textarea, [tabindex]"),
      function (node) {
        return !node.disabled
          && node.getAttribute("tabindex") !== "-1"
          && node.offsetParent !== null;
      }
    );
  }

  /* Escape dismisses the drawer the same way Cancel does: the draft is
   * abandoned and the applied filters are left alone. Bound with the
   * focus trap because both only matter while the drawer is open. */
  function closeFilterPanelOnEscape(event) {
    if (event.key !== "Escape" || !isFilterPanelOpen()) return;
    /* The season menu is a layer inside the drawer, so the first
     * Escape closes that and a second closes the drawer. */
    var seasonMenu = document.getElementById("fp-season-menu");
    if (seasonMenu && !seasonMenu.hidden) {
      toggleSeasonMenu(false);
      event.stopPropagation();
      return;
    }
    event.stopPropagation();
    closeFilterPanel();
  }

  /* The drawer is modal and dims the page behind it, so Tab has to stay
   * inside it rather than walking into a table the user cannot see. */
  function trapFilterPanelFocus(event) {
    if (event.key !== "Tab" || !isFilterPanelOpen()) return;
    const items = filterPanelFocusables();
    if (!items.length) return;
    const first = items[0];
    const last = items[items.length - 1];
    const panel = document.getElementById("filter-panel");
    if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    } else if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (panel && !panel.contains(document.activeElement)) {
      event.preventDefault();
      first.focus();
    }
  }

  function openFilterPanel() {
    const panel = document.getElementById("filter-panel");
    const trigger = document.querySelector('[data-action="toggle-filter"]');
    const scrim = document.querySelector("[data-filter-scrim]");
    if (!panel || !trigger) return;
    closeAllPopovers();
    filterPanelOpenedFrom = trigger;
    // CRITICAL: draft = applied each time we open. Anything the user does
    // inside the panel only mutates draftFilters; clicking Cancel just closes
    // and naturally discards because we'll re-seed draft from applied next
    // time the panel opens.
    draftFilters = cloneFilters(appliedFilters);
    renderDraftIntoSelects();
    toggleSeasonMenu(false);
    if (scrim) {
      scrim.hidden = false;
      /* Unhide first, then let a frame pass so the fade has a starting
       * opacity to animate from. */
      requestAnimationFrame(function () { scrim.classList.add("is-open"); });
    }
    panel.classList.add("is-open");
    trigger.setAttribute("aria-expanded", "true");
    document.addEventListener("keydown", trapFilterPanelFocus, true);
    document.addEventListener("keydown", closeFilterPanelOnEscape, true);
    // Land focus on the panel container so keyboard users are inside the
    // dialog, but no individual select shows a focus ring (matches the
    // Figma reference of a neutral, freshly-opened state). The panel
    // animates in from visibility:hidden, and a hidden element cannot take
    // focus, so wait one frame for the transition to start.
    panel.setAttribute("tabindex", "-1");
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        if (panel.classList.contains("is-open")) panel.focus({ preventScroll: true });
      });
    });
  }

  function closeFilterPanel() {
    const panel = document.getElementById("filter-panel");
    const trigger = document.querySelector('[data-action="toggle-filter"]');
    const scrim = document.querySelector("[data-filter-scrim]");
    if (!panel) return;
    panel.classList.remove("is-open");
    if (trigger) trigger.setAttribute("aria-expanded", "false");
    document.removeEventListener("keydown", trapFilterPanelFocus, true);
    document.removeEventListener("keydown", closeFilterPanelOnEscape, true);
    if (scrim) {
      scrim.classList.remove("is-open");
      /* Stay in the DOM until the fade finishes, or the scrim would
       * vanish instantly while the drawer is still sliding out. */
      setTimeout(function () {
        if (!isFilterPanelOpen()) scrim.hidden = true;
      }, 220);
    }
    // Discard any unapplied draft changes. Re-seed draft from applied so
    // a stale value can't bleed into the next open.
    draftFilters = cloneFilters(appliedFilters);
    if (filterPanelOpenedFrom && document.contains(filterPanelOpenedFrom)) {
      filterPanelOpenedFrom.focus();
    }
    filterPanelOpenedFrom = null;
  }

  /* ---- Commit, chips, and URL ---------------------------------------
   * One doorway for every change to what the table is filtered by, so
   * the table, the chips, the trigger count and the URL can never
   * disagree about the current state. */
  function commitFilters(next) {
    appliedFilters = next;
    page = 1;
    writeFiltersToUrl();
    renderTable();
  }

  function removeAppliedFilterValue(key, value) {
    const next = cloneFilters(appliedFilters);
    if (key === "buyingEntityId") {
      next.buyingEntityId = "";
    } else {
      next[key] = (next[key] || []).filter(function (entry) { return entry !== value; });
    }
    commitFilters(next);
    /* Keep the drawer honest if it happens to be open behind the chip. */
    draftFilters = cloneFilters(appliedFilters);
    renderDraftIntoSelects();
  }

  /* One chip per selected value, in the drawer's own field order, so the
   * bar reads the same way the drawer does. */
  function appliedFilterChips() {
    const chips = [];
    MULTI_FILTER_KEYS.forEach(function (key) {
      (appliedFilters[key] || []).forEach(function (value) {
        chips.push({
          key: key,
          value: value,
          group: FILTER_GROUP_CONFIG[key].legend,
          label: filterValueLabel(key, value)
        });
      });
    });
    if (appliedFilters.buyingEntityId) {
      const entry = findEntity(appliedFilters.buyingEntityId);
      chips.push({
        key: "buyingEntityId",
        value: appliedFilters.buyingEntityId,
        group: "Buying entity",
        label: entry
          ? entityLabel(entry.name, entry.id)
          : appliedFilters.buyingEntityId
      });
    }
    return chips;
  }

  function renderFilterChips() {
    const bar = document.querySelector("[data-filter-chips]");
    if (!bar) return;
    const list = bar.querySelector(".fchips__list");
    const chips = appliedFilterChips();
    bar.hidden = chips.length === 0;
    if (!list) return;
    list.replaceChildren();
    chips.forEach(function (chip) {
      const li = document.createElement("li");
      li.className = "fchips__item";
      const text = document.createElement("span");
      text.className = "fchips__text";
      text.textContent = chip.group + ": " + chip.label;
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "fchips__remove";
      remove.setAttribute("data-action", "remove-filter-chip");
      remove.setAttribute("data-chip-key", chip.key);
      remove.setAttribute("data-chip-value", chip.value);
      remove.setAttribute("aria-label", "Remove filter " + chip.group + " " + chip.label);
      remove.innerHTML = '<svg width="12" height="12" viewBox="0 0 16 16" fill="none" '
        + 'aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" '
        + 'stroke-width="1.6" stroke-linecap="round"/></svg>';
      li.appendChild(text);
      li.appendChild(remove);
      list.appendChild(li);
    });
  }

  /* Filters live in the query string so a refresh keeps them and a link
   * carries them. Multi-value keys join with a comma; nothing in the
   * data contains one. Params the rest of the app owns (section, cardId,
   * version) are left exactly as they were found. */
  const FILTER_URL_KEYS = { status: "status", marketplace: "marketplace", season: "season" };

  function writeFiltersToUrl() {
    if (!window.history || !window.history.replaceState) return;
    const url = new URL(window.location.href);
    Object.keys(FILTER_URL_KEYS).forEach(function (key) {
      const values = appliedFilters[key] || [];
      if (values.length) url.searchParams.set(FILTER_URL_KEYS[key], values.join(","));
      else url.searchParams.delete(FILTER_URL_KEYS[key]);
    });
    if (appliedFilters.buyingEntityId) url.searchParams.set("entity", appliedFilters.buyingEntityId);
    else url.searchParams.delete("entity");
    window.history.replaceState({}, "", url.pathname + url.search + url.hash);
  }

  /* Read filters back on load. Values that no longer exist in the data
   * are dropped rather than applied, so a stale link cannot leave the
   * user staring at an empty table with no way to tell why. */
  function readFiltersFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const next = emptyFilters();
    Object.keys(FILTER_URL_KEYS).forEach(function (key) {
      const raw = params.get(FILTER_URL_KEYS[key]);
      if (!raw) return;
      const allowed = filterGroupValues(key);
      next[key] = raw.split(",")
        .map(function (value) { return value.trim(); })
        .filter(function (value) { return value && allowed.indexOf(value) !== -1; });
    });
    const entity = (params.get("entity") || "").trim();
    if (entity && findEntity(entity)) next.buyingEntityId = entity;
    appliedFilters = next;
    draftFilters = cloneFilters(next);
  }

  /* Announce the count after a filter change only. Sorting and paging
   * also re-render, and re-reading the same total each time would make
   * the live region chatter. */
  let lastAnnouncedFilterState = "";
  function announceFilterResults(total) {
    const region = document.querySelector("[data-filter-live]");
    if (!region) return;
    const signature = JSON.stringify(appliedFilters) + "|" + query;
    if (signature === lastAnnouncedFilterState) return;
    lastAnnouncedFilterState = signature;
    region.textContent = total + " rate card" + (total === 1 ? "" : "s") + " match your filters.";
  }

  function isFilterPanelOpen() {
    const panel = document.getElementById("filter-panel");
    return !!(panel && panel.classList.contains("is-open"));
  }

  // ----- Event wiring -------------------------------------------------------

  function wire() {
    const search = document.querySelector('[data-action="search"]');
    const searchWrap = search.closest(".ads-search");
    const searchClear = searchWrap && searchWrap.querySelector('[data-action="clear-search"]');
    const syncSearchPresentation = () => {
      const filled = Boolean(search.value);
      if (searchWrap) searchWrap.setAttribute("data-filled", String(filled));
      if (searchClear) searchClear.hidden = !filled;
    };
    search.addEventListener("input", (e) => {
      query = e.target.value || "";
      page = 1;
      syncSearchPresentation();
      renderTable();
    });
    syncSearchPresentation();

    const pageSizeSel = document.querySelector('[data-action="page-size"]');
    pageSizeSel.addEventListener("change", (e) => {
      pageSize = Number(e.target.value) || 10;
      page = 1;
      renderTable();
    });

    const goSelect = document.querySelector('[data-action="go-to-page"]');
    goSelect.addEventListener("change", (e) => {
      const next = Number(e.target.value) || 1;
      page = next;
      renderTable();
    });

    document.body.addEventListener("keydown", (e) => {
      if (e.key !== " " && e.key !== "Spacebar") return;
      const t = e.target instanceof Element ? e.target : null;
      const vnavLink = t && t.closest(".vnav__link");
      if (!vnavLink) return;
      e.preventDefault();
      vnavLink.click();
    });

    document.body.addEventListener("click", (e) => {
      const t = e.target instanceof Element ? e.target : null;
      if (!t) return;

      var vnavLink = t.closest(".vnav__link");
      if (vnavLink) {
        var unavailable = vnavUnavailableMessage(vnavLink);
        if (unavailable) {
          e.preventDefault();
          toast({
            title: "Not available in portfolio",
            message: unavailable,
            variant: "info",
            duration: 6000
          });
          return;
        }
        e.preventDefault();
        /* Every route this app can navigate to belongs to Rate Card
         * Manager, so re-assert the route-derived selection rather than
         * trusting which decorative item was clicked - Orders, Admin,
         * etc. have no real page here and must never become selected
         * from a click alone (that would produce two selected items or
         * a selection that disagrees with the actual route). */
        setVnavActive(resolveVnavRouteKey());
        return;
      }

      const actionBtn = t.closest("[data-action]");
      const action = actionBtn ? actionBtn.getAttribute("data-action") : null;
      const inDropdown = t.closest("[data-dropdown]");

      if (action === "clear-search") {
        search.value = "";
        query = "";
        page = 1;
        syncSearchPresentation();
        renderTable();
        search.focus();
        return;
      }
      if (action === "toggle-season-menu") {
        toggleSeasonMenu();
        return;
      }
      if (action === "clear-filter-entity") {
        const entityInput = document.getElementById("fp-entity");
        if (entityInput) {
          chooseEntity("");
          entityInput.focus();
        }
        return;
      }
      if (action === "select-entity") {
        chooseEntity(t.getAttribute("data-entity-id"));
        const entityInput = document.getElementById("fp-entity");
        if (entityInput) entityInput.focus();
        return;
      }
      if (action === "toggle-import") {
        togglePopover(t.closest('[data-dropdown="import"]'));
        return;
      }
      if (action === "close-toast") {
        /* ADS Toast dismiss X. Walk up to the specific .ads-toast the
         * X belongs to and dismiss just that one - the stack container
         * can hold multiple concurrent toasts, so dismissing globally
         * would incorrectly clear siblings the user hasn't acknowledged.
         * Cancels the toast's per-instance auto-dismiss timer.
         * Idempotent - safe to click repeatedly. */
        var toastEl = t.closest(".ads-toast");
        dismissToast(toastEl, { manual: true });
        return;
      }
      if (action === "toggle-profile") {
        /* Profile menu uses the same togglePopover machinery; closing
         * the menu also clears any open Theme / Version submenu state
         * so the next open starts clean. */
        const wrap = t.closest('[data-dropdown="profile"]');
        togglePopover(wrap);
        ['theme', 'version'].forEach(function(key){
          var sub = wrap.querySelector('[data-submenu="' + key + '"]');
          if (!sub) return;
          sub.classList.remove("is-open");
          var subTrigger = sub.querySelector('[data-action="toggle-' + key + '"]');
          if (subTrigger) subTrigger.setAttribute("aria-expanded", "false");
          var submenuPanel = sub.querySelector('.' + key + '-submenu');
          if (submenuPanel) submenuPanel.hidden = true;
        });
        /* Presentation view: sync the row's enabled state to the
         * current route so it only offers to open something that
         * actually exists (list mode on the list page, exploded
         * detail mode on the v2.0 create page). */
        var presentationItem = wrap.querySelector(
          '[data-action="open-presentation-view"]'
        );
        if (presentationItem) {
          var api = window.RateCardPresentationView;
          var eligible = !!(api && api.isEligible && api.isEligible());
          presentationItem.disabled = !eligible;
          presentationItem.setAttribute(
            "aria-disabled", eligible ? "false" : "true"
          );
        }
        return;
      }
      if (action === "toggle-theme") {
        // Open the Theme submenu without closing the main profile menu.
        const wrap = t.closest('[data-submenu="theme"]');
        if (!wrap) return;
        const panel = wrap.querySelector(".theme-submenu");
        const trigger = wrap.querySelector('[data-action="toggle-theme"]');
        const open = wrap.classList.toggle("is-open");
        if (panel) panel.hidden = !open;
        if (trigger) trigger.setAttribute("aria-expanded", open ? "true" : "false");
        return;
      }
      if (action === "toggle-version") {
        /* Mirror of toggle-theme. Opens / closes the Version submenu
         * without dismissing the main profile menu. */
        const wrap = t.closest('[data-submenu="version"]');
        if (!wrap) return;
        const panel = wrap.querySelector(".version-submenu");
        const trigger = wrap.querySelector('[data-action="toggle-version"]');
        const open = wrap.classList.toggle("is-open");
        if (panel) panel.hidden = !open;
        if (trigger) trigger.setAttribute("aria-expanded", open ? "true" : "false");
        return;
      }
      if (t.closest(".version-submenu__item[data-version]")) {
        /* Version selection. Same surgical contract as theme:
         *   - Only CSS state changes (body[data-version=...] hook +
         *     .vnav visibility).
         *   - We never re-render the table or reset filters / search /
         *     pagination / forms - RATE_CARDS is untouched.
         * The toast confirms the new version to the user since the
         * layout swap is visually obvious but the menu closes.
         *
         * SELECTOR NOTE: we deliberately scope to ".version-submenu__item"
         * (not the bare "[data-version]") because the BODY also carries
         * a data-version attribute (the global hook). A bare ancestor
         * match would treat every click anywhere on the page as a
         * version-select and re-apply the current version on each
         * click - which silently swallows other actions like the
         * .vnav__collapse button below.
         *
         * URL sync (2026-07-13 always-latest-by-default policy): we
         * write the chosen version back into location.search so a
         * MID-SESSION refresh keeps the user on the version they
         * picked. Other query params (?section=atlas&slide=5 for
         * atlas deck deep-links, ?ref=1 for the reference overlay,
         * etc.) are preserved. localStorage is deliberately NOT
         * written - closing the tab and reopening the bare URL still
         * lands on VERSION_LATEST, which is the intended behavior. */
        const choice = t.closest(".version-submenu__item[data-version]").getAttribute("data-version");
        applyVersion(choice);
        try {
          var params = new URLSearchParams(location.search);
          params.set("version", choice);
          var newQs = params.toString();
          var newUrl = location.pathname + (newQs ? "?" + newQs : "") + location.hash;
          history.replaceState(history.state, "", newUrl);
        } catch (_) { /* history API unavailable - non-fatal, in-session choice still applied. */ }
        toastV12(
          { message: "Version " + choice, variant: "info" },
          "Version " + choice
        );
        closeAllPopovers();
        return;
      }
      if (t.closest("[data-theme]")) {
        // Theme selection. Visually mark the chosen item, swap the body class
        // so the ADS layer of styles.css activates (or deactivates), and
        // persist to localStorage so refresh keeps the selection.
        //
        // CRITICAL: we only toggle CSS state. We never re-render the table,
        // reset filters, search, page, or any product state. The same DOM
        // is reskinned in place. localStorage write is wrapped in try/catch
        // because some browsers throw in private/no-storage modes.
        const choice = t.closest("[data-theme]").getAttribute("data-theme");
        applyTheme(choice);
        const label = choice === "ads-preview" ? "Ad Design System" : "Wireframe";
        toastV12(
          { message: "Theme: " + label, variant: "info" },
          "Theme: " + label
        );
        closeAllPopovers();
        return;
      }
      if (action === "vnav-toggle" || action === "vnav-close") {
        var vnavEl = document.querySelector('.vnav');
        if (!vnavEl) return;
        var currentlyPinned = vnavEl.classList.contains('vnav--pinned');
        var nextPinned = !currentlyPinned;
        setVnavPinned(nextPinned);
        vnavEl.classList.remove('vnav--hovered');
        var focusTarget = nextPinned
          ? vnavEl.querySelector('.vnav__close')
          : vnavEl.querySelector('.vnav__expand-target');
        if (focusTarget && typeof focusTarget.focus === "function") focusTarget.focus();
        return;
      }
      if (action === "vnav-expand") {
        var expandVnav = document.querySelector('.vnav');
        if (!expandVnav || expandVnav.classList.contains('vnav--pinned')) return;
        setVnavPinned(true);
        expandVnav.classList.remove('vnav--hovered');
        var collapseBtn = expandVnav.querySelector('.vnav__close');
        if (collapseBtn && typeof collapseBtn.focus === "function") collapseBtn.focus();
        return;
      }
      if (action === "open-presentation-view") {
        /* Presentation view (2026-08-04).
         *
         * Contextual entry point in the profile menu: the same overlay
         * that the Cmd/Ctrl+P shortcut opens. RateCardPresentationView
         * .open() already inspects document.body[data-route] and
         * chooses the correct mode (Rate Card List presentation on the
         * list page, Create New Rate Card presentation on the create
         * page for v2.0), so the caller does not need to know which
         * presentation to show. On non-eligible routes the row's
         * disabled state prevents this handler from firing, but we
         * defensively no-op if the API is unavailable. */
        closeAllPopovers();
        var api = window.RateCardPresentationView;
        if (api && typeof api.open === "function") {
          api.open();
        }
        return;
      }
      if (action === "toggle-redline") {
        if (window.RedlineMode && typeof window.RedlineMode.toggle === "function") {
          window.RedlineMode.toggle("profile");
        }
        closeAllPopovers();
        return;
      }
      if (action === "logout") {
        toastV12(
          { message: "Logging out.", variant: "info" },
          "Logging out..."
        );
        closeAllPopovers();
        return;
      }

      /* ADS Dropdown (filter panel): trigger toggles the menu. */
      if (action === "toggle-ads-dd") {
        const root = t.closest('.ads-dd');
        if (root) toggleAdsDd(root);
        return;
      }
      /* ADS Dropdown option click: select + close. */
      const ddOpt = t.closest('.ads-dd__option');
      if (ddOpt) {
        const root = ddOpt.closest('.ads-dd');
        const value = ddOpt.getAttribute('data-value');
        const label = ddOpt.textContent.trim();
        selectAdsDdOption(root, value, label);
        return;
      }
      if (action === "toggle-filter") {
        if (isFilterPanelOpen()) closeFilterPanel();
        else openFilterPanel();
        return;
      }
      /* Sortable column header click. Three-state cycle (asc/desc/none)
       * lives in toggleSort which also resets pagination to page 1. */
      if (action === "sort") {
        const key = actionBtn.getAttribute("data-sort-key");
        if (key) toggleSort(key);
        return;
      }
      if (action === "close-filter") {
        closeFilterPanel();
        return;
      }
      if (action === "apply-filters") {
        // Commit the draft, refresh the table, reset pagination, write the
        // state to the URL, and close the panel.
        commitFilters(cloneFilters(draftFilters));
        closeFilterPanel();
        return;
      }
      if (action === "clear-filters") {
        /* "Reset filters" in the drawer header clears the DRAFT only, so
         * it is undoable: Cancel still restores whatever was applied
         * before the drawer opened. Applying the cleared draft is what
         * returns the full list. The drawer stays open. */
        draftFilters = emptyFilters();
        renderDraftIntoSelects();
        closeAllAdsDds();
        return;
      }
      if (action === "clear-all-filters") {
        /* "Clear all" on the chip bar acts on what is APPLIED, which is
         * the opposite end from Reset filters: it changes the table now
         * and needs no drawer. */
        draftFilters = emptyFilters();
        commitFilters(emptyFilters());
        return;
      }
      if (action === "remove-filter-chip") {
        removeAppliedFilterValue(
          actionBtn.getAttribute("data-chip-key"),
          actionBtn.getAttribute("data-chip-value")
        );
        return;
      }
      if (action === "reset-all") {
        /* Empty-state "Clear filters" button: clears both filters AND search. */
        query = "";
        search.value = "";
        syncSearchPresentation();
        draftFilters = emptyFilters();
        commitFilters(emptyFilters());
        closeAllAdsDds();
        return;
      }
      if (action === "create") {
        /* 2.1 names the rate card in a dialog (643:63052) and then hands
         * the user to the shared Rate Card Details page, so new and
         * existing cards land on the same layout. Earlier versions keep
         * the full Create Rate Card page (Figma 70:1660): route is a
         * body attribute so CSS controls visibility, and the form is
         * reset first so a prior Edit session is fully cleared. */
        if (isVersion21() && rcCreateModal()) {
          openRcCreateModal(actionBtn);
          return;
        }
        setCreatePageMode("create");
        window.__rcDraft = null;
        resetCreateForm();
        navigateTo("create");
        return;
      }
      if (action === "close-rc-create") {
        closeRcCreateModal();
        return;
      }
      if (action === "confirm-rc-create") {
        confirmRcCreate();
        return;
      }
      if (action === "toggle-rcm-details") {
        var detailsSection = actionBtn.closest("[data-rcm-details]");
        setRcCreateDetailsOpen(
          detailsSection ? !detailsSection.classList.contains("is-open") : true);
        return;
      }
      if (action === "go-list") {
        // Back link returns to the approved list page. e.preventDefault on
        // the anchor handled below via the [data-action] click intercept.
        // Clear edit state + reset the form so the next Create click
        // starts in a clean create state without carrying forward any
        // edited values or rate card id.
        e.preventDefault();
        setCreatePageMode("create");
        window.__rcDraft = null;
        resetCreateForm();
        navigateTo("list");
        return;
      }
      if (action === "go-card") {
        // LINE-step stepper allows clicking the completed CARD step to return.
        // State is preserved because both routes live in the DOM. We only
        // swap which one is visible via body[data-route].
        e.preventDefault();
        navigateTo("create");
        return;
      }
      if (action === "save-draft") {
        // "Save as Draft": persists the current (possibly incomplete)
        // form state as a Draft row in the shared RATE_CARDS store,
        // then mirrors it to localStorage so it survives a refresh.
        // - No validation: a draft is allowed to be missing required
        //   fields, only minimal field collection (in saveCardDraft)
        //   runs to mint the session Rate Card ID.
        // - Repeat clicks UPSERT the same draft row (keyed on the
        //   session cardId minted by saveCardDraft) instead of
        //   creating duplicates; the updated row is moved to the top.
        // - Form values stay on screen, no navigation, no reset.
        try {
          saveCardDraft();
          /* In edit mode: preserve the row's existing status (don't
           * downgrade a Published row to Draft just because the user
           * clicked "Save as Draft" while editing). In create mode:
           * always brand-new Drafts. */
          var draftEditMode = document.body.getAttribute("data-mode") === "edit";
          commitFormToTable(draftEditMode ? {} : { status: "Draft" });
          toastV12(
            { message: "Draft saved.", variant: "success" },
            "Draft saved."
          );
          /* Edit mode: refresh dirty snapshot so Save Changes
           * re-disables until the user makes a new edit. */
          if (draftEditMode) {
            snapshotEditFormState();
            recomputeEditDirtyState();
          }
        } catch (err) {
          console.error("Save as Draft failed:", err);
          toastV12(
            { message: "Unable to save rate card.", variant: "error" },
            "Could not save draft. See console for details."
          );
        }
        return;
      }
      if (action === "save-create-new") {
        // "Save and Create New Rate Card": validate, persist as a new
        // top-of-table row, reset the form so the user can immediately
        // start another, and stay on Create. The committed row is
        // unshifted onto RATE_CARDS so it's the first row when the
        // user returns to the Manager table. Multiple consecutive
        // saves stack newest-first (commitFormToTable handles the
        // unshift + persistence).
        try {
          /* Save attempt -> mark CARD as touched so the header
           * summary + field-level errors render if anything is
           * missing. The button is gated to be disabled when CARD-
           * required is incomplete, so reaching this path normally
           * means validation will pass - but we still want full
           * validateForm coverage for LINE/PREM. */
          window.__rcCardTouched = true;
          renderCardErrorState();
          if (!validateForm()) return;
          saveCardDraft();
          /* commitFormToTable() returns the newly-inserted row so we
           * can read its Rate card name for the confirmation toast
           * BEFORE resetCreateForm() blanks the inputs. Row.name is
           * already the trimmed, user-entered name (commitFormToTable
           * falls back to "Untitled Rate Card" if the field is
           * empty). */
          var savedRow = commitFormToTable();
          resetCreateForm();
          /* Compose the toast message per the 2026-07-07 brief:
           *   "{Rate card name} has been saved. A new blank rate card is ready."
           * If the name is empty (or the fallback placeholder), use
           * the "This rate card has been saved..." wording so users
           * never see the internal placeholder string in a toast. */
          var displayName = (savedRow && savedRow.name) || "";
          if (!displayName || displayName === "Untitled Rate Card") displayName = "";
          var message = displayName
            ? displayName + " has been saved. A new blank rate card is ready."
            : "This rate card has been saved. A new blank rate card is ready.";
          toastV12(
            { message: "Rate card created.", variant: "success" },
            message,
            { title: "Rate card saved", variant: "success" }
          );
        } catch (err) {
          console.error("Save and create new failed:", err);
          toastV12(
            { message: "Unable to save rate card.", variant: "error" },
            "Could not save. See console for details.",
            { title: "Save failed", variant: "error" }
          );
        }
        return;
      }
      if (action === "save-publish") {
        // "Save Rate Card" (create mode) / "Save Changes" (edit mode):
        // - Create mode: full required-field validation (CARD + LINE +
        //   PREM) then commitFormToTable upserts the new row.
        // - Edit mode: lighter validation - the row already exists and
        //   was valid when first saved; the seed data doesn't carry
        //   per-row LINE/PREM details so requiring them on save would
        //   block every edit. We require only Rate Card Name (the
        //   primary user-visible field). The commitFormToTable upsert
        //   then UPDATES the same row in place (keyed on the active
        //   __rcDraft.cardId set by openEditRateCard).
        try {
          var editMode = document.body.getAttribute("data-mode") === "edit";
          if (editMode) {
            var nameEl = document.querySelector('#rc-name');
            var nameVal = nameEl ? nameEl.value.trim() : '';
            if (!nameVal) {
              if (nameEl) {
                var field = nameEl.closest('.field');
                if (field) field.classList.add('is-invalid');
                var err = field && field.querySelector('.field__error');
                setFieldError(err, 'Rate Card Name is required.');
              }
              return;
            }
          } else {
            /* Create mode: full required-field validation. Mark CARD
             * as touched first so even if validateForm completes,
             * the header summaries + per-field errors render. */
            window.__rcCardTouched = true;
            renderCardErrorState();
            if (!validateForm()) return;
          }
          saveCardDraft();
          /* commitFormToTable() upserts into RATE_CARDS, bumps version,
           * persists to localStorage, and re-renders the table - so
           * when the user navigates back to the Manager list, the row
           * already reflects the saved edit. We deliberately stay on
           * the Edit page after Save Changes per the brief; the user
           * can return via the back link to see the updated row. */
          commitFormToTable({ status: editMode ? undefined : "Draft" });
          if (editMode) {
            toastV12(
              { message: "Rate card saved.", variant: "success" },
              "Rate card changes saved."
            );
            /* Stay on the Edit page; refresh the snapshot so future
             * edits start from this newly-saved baseline (and Save
             * Changes immediately re-disables until the user
             * actually changes a field again). */
            snapshotEditFormState();
            recomputeEditDirtyState();
          } else {
            toastV12(
              { message: "Rate card created.", variant: "success" },
              "Rate card saved."
            );
          }
        } catch (err) {
          console.error("Save rate card failed:", err);
          toastV12(
            { message: "Unable to save rate card.", variant: "error" },
            "Could not save. See console for details."
          );
        }
        return;
      }
      if (action === "toggle-accordion") {
        var section = t.closest("[data-accordion]");
        if (section) toggleAccordion(section);
        return;
      }
      if (action === "toggle-edl-select") {
        toggleEdlSelect(t.closest(".edl-select"));
        return;
      }
      if (action === "toggle-ads-cal") {
        toggleAdsCal(t.closest(".ads-datepicker"));
        return;
      }
      if (action === "cancel-delete") {
        closeDeleteModal();
        return;
      }
      if (action === "confirm-delete") {
        confirmDelete();
        return;
      }
      if (action === "close-quick-edit") {
        /* The scrim, header X, and footer Cancel all use this action. The
         * `force` argument is false so dirty state triggers the discard
         * confirmation; clean state closes immediately. */
        closeQuickEdit(false);
        return;
      }
      if (action === "save-quick-edit") {
        saveQuickEdit();
        return;
      }
      if (action === "download-template") {
        downloadBlankTemplate();
        return;
      }
      if (action === "upload-template") {
        openRateCardImport();
        return;
      }
      if (action === "qe-keep-editing") {
        keepEditing();
        return;
      }
      if (action === "qe-discard-changes") {
        discardQuickEditChanges();
        return;
      }

      const inDatePopover = t.closest(".ads-datepicker__popover");
      if (!inDropdown && !inDatePopover) closeAllPopovers();

      /* Close any open ADS dropdown when the click lands outside any
       * .ads-dd container. We allow clicks on the trigger / option without
       * closing because those paths return earlier. */
      if (!t.closest('.ads-dd')) closeAllAdsDds();
    });

    /* Filter a searchable dropdown as its search field is typed into.
     * Delegated, because these fields are built on demand by
     * enhanceAdsSelect and rebuilt whenever the panel loads a record. */
    document.addEventListener('input', function (e) {
      const input = e.target;
      if (!input || !input.classList
        || !input.classList.contains('ads-dd__search-input')) return;
      filterAdsDdOptions(input.closest('.ads-dd'), input.value);
    });

    /* Quick Edit input + blur. Delegated to the tbody so it covers all
     * dynamically rendered row inputs without re-binding on each render. */
    var qeRows = document.querySelector("[data-qe-rows]");
    if (qeRows) {
      qeRows.addEventListener("input", handleQuickEditFieldEvent);
      qeRows.addEventListener("blur", handleQuickEditFieldEvent, true);
    }
    /* Focus trap for the Quick Edit sheet. */
    document.addEventListener("keydown", handleQuickEditKeydown);

    /* ADS tooltip: show on hover + keyboard focus, hide on leave/blur.
     * mouseenter / mouseleave do not bubble, so we listen on mouseover /
     * mouseout with a trigger-equality check to get reliable "entered a
     * new trigger" semantics across rapid pointer movement. */
    document.addEventListener("mouseover", function(e){
      var trigger = adsTooltipFindTrigger(e.target);
      if (!trigger) return;
      /* If the pointer moved within the same trigger, no-op. */
      var related = e.relatedTarget instanceof Element ? adsTooltipFindTrigger(e.relatedTarget) : null;
      if (related === trigger) return;
      adsTooltipScheduleShow(trigger);
    });
    document.addEventListener("mouseout", function(e){
      var trigger = adsTooltipFindTrigger(e.target);
      if (!trigger) return;
      var related = e.relatedTarget instanceof Element ? adsTooltipFindTrigger(e.relatedTarget) : null;
      if (related === trigger) return;
      adsTooltipHide();
    });
    document.addEventListener("focusin", function(e){
      var trigger = adsTooltipFindTrigger(e.target);
      if (trigger) adsTooltipScheduleShow(trigger);
    });
    document.addEventListener("focusout", function(e){
      var trigger = adsTooltipFindTrigger(e.target);
      if (trigger) adsTooltipHide();
    });
    /* Hide tooltip on scroll/resize - position becomes stale. */
    window.addEventListener("scroll", adsTooltipHide, true);
    window.addEventListener("resize", adsTooltipHide);

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        /* ADS tooltip dismisses on Escape regardless of which other
         * surface owns the key (tooltip never blocks any other UX). */
        adsTooltipHide();
        const openAdsDd = document.querySelector('.ads-dd__trigger[aria-expanded="true"]');
        if (openAdsDd) {
          e.preventDefault();
          closeAllAdsDds(null, true);
          e.stopImmediatePropagation();
          return;
        }
        /* A confirmation raised on top of another surface answers
         * Escape first, and answers it with "no": Escape cancels a
         * dialog, it never confirms one. */
        if (isAdsConfirmOpen()) {
          e.stopImmediatePropagation();
          closeAdsConfirm(false);
          return;
        }
        var qeDiscard = document.querySelector("[data-qe-discard]");
        if (qeDiscard && !qeDiscard.hidden) {
          e.stopImmediatePropagation();
          keepEditing();
          return;
        }
        /* Quick Edit owns Escape when it's open (dirty state may show
         * a discard confirmation; clean state closes immediately). */
        if (isQuickEditOpen()) {
          closeQuickEdit(false);
          return;
        }
        const profileWrap = document.querySelector('[data-dropdown="profile"]');
        const profileMenu = profileWrap && profileWrap.querySelector('.profile-menu:not([hidden])');
        const profileTrigger = profileWrap && profileWrap.querySelector('[data-action="toggle-profile"]');
        /* A select or date picker open inside the Create rate card
         * dialog owns Escape first: dismissing it should not also throw
         * away the name the user has typed. */
        const popoverWasOpen = document.querySelector(
          '.edl-select__trigger[aria-expanded="true"],' +
          ' .ads-datepicker__trigger[aria-expanded="true"]');
        closeAllPopovers();
        closeAllAdsDds();
        if (!popoverWasOpen && isRcCreateOpen()) {
          closeRcCreateModal();
          return;
        }
        closeDeleteModal();
        if (isFilterPanelOpen()) closeFilterPanel();
        if (profileMenu && profileTrigger) profileTrigger.focus({ preventScroll: true });
      }
      const focused = document.activeElement;
      if (focused && focused.matches('[data-action="toggle-profile"]')
          && e.key === 'ArrowDown') {
        e.preventDefault();
        if (focused.getAttribute('aria-expanded') !== 'true') focused.click();
        const wrap = focused.closest('[data-dropdown="profile"]');
        const first = wrap && wrap.querySelector('.profile-menu [role^="menuitem"]');
        if (first) first.focus({ preventScroll: true });
        return;
      }
      if (focused && focused.matches('[role="menuitem"], [role="menuitemradio"]')) {
        const menu = focused.closest('[role="menu"]');
        if (menu && (e.key === 'ArrowDown' || e.key === 'ArrowUp'
            || e.key === 'Home' || e.key === 'End')) {
          const items = Array.from(menu.querySelectorAll('[role="menuitem"], [role="menuitemradio"]'))
            .filter(function (item) {
              return item.closest('[role="menu"]') === menu && !item.disabled;
            });
          if (items.length) {
            e.preventDefault();
            var menuIndex = items.indexOf(focused);
            if (e.key === 'Home') menuIndex = 0;
            else if (e.key === 'End') menuIndex = items.length - 1;
            else if (e.key === 'ArrowDown') menuIndex = (menuIndex + 1) % items.length;
            else menuIndex = (menuIndex - 1 + items.length) % items.length;
            items[menuIndex].focus({ preventScroll: true });
          }
          return;
        }
        if (e.key === 'ArrowRight' && focused.getAttribute('aria-haspopup') === 'menu') {
          e.preventDefault();
          if (focused.getAttribute('aria-expanded') !== 'true') focused.click();
          const subWrap = focused.closest('[data-submenu]');
          const subMenu = subWrap && subWrap.querySelector('[role="menu"]');
          const firstSubItem = subMenu && subMenu.querySelector('[role^="menuitem"]');
          if (firstSubItem) firstSubItem.focus({ preventScroll: true });
          return;
        }
        if (e.key === 'ArrowLeft') {
          const subWrap = focused.closest('[data-submenu]');
          const subMenu = focused.closest('[role="menu"]');
          const subTrigger = subWrap && subWrap.querySelector('[aria-haspopup="menu"]');
          if (subWrap && subMenu && subMenu !== subWrap.closest('.profile-menu')) {
            e.preventDefault();
            subWrap.classList.remove('is-open');
            subMenu.hidden = true;
            if (subTrigger) {
              subTrigger.setAttribute('aria-expanded', 'false');
              subTrigger.focus({ preventScroll: true });
            }
            return;
          }
        }
      }
      if (focused && focused.classList
          && focused.classList.contains('ads-dd__trigger')
          && (e.key === 'Enter' || e.key === ' ' || e.key === 'ArrowDown'
            || e.key === 'ArrowUp')) {
        e.preventDefault();
        if (e.key === ' ') focused.setAttribute('data-ads-dd-space-open', '');
        toggleAdsDd(focused.closest('.ads-dd'));
        return;
      }
      /* Typing in a searchable list's field: the query filters the
       * options and the arrow keys hand off into them. Enter takes the
       * first remaining match, which is what the user is looking at
       * after narrowing the list to one. */
      /* Read from the event's own target rather than document.activeElement:
       * the key was delivered to this field, which is the fact this branch
       * turns on, and the two can disagree when the window itself is not
       * focused. */
      const searchField = e.target && e.target.classList
        && e.target.classList.contains('ads-dd__search-input') ? e.target : null;
      if (searchField) {
        const searchRoot = searchField.closest('.ads-dd');
        const searchMenu = searchRoot && searchRoot.querySelector('.ads-dd__menu');
        if (e.key === 'Tab') {
          closeAllAdsDds();
        } else if (e.key === 'ArrowDown' || e.key === 'ArrowUp'
            || e.key === 'Home' || e.key === 'End') {
          e.preventDefault();
          const shown = adsDdVisibleOptions(searchMenu);
          const target = (e.key === 'ArrowUp' || e.key === 'End')
            ? shown[shown.length - 1] : shown[0];
          if (target) {
            target.focus({ preventScroll: true });
            target.scrollIntoView({ block: 'nearest' });
          }
        } else if (e.key === 'Enter') {
          e.preventDefault();
          const first = adsDdVisibleOptions(searchMenu)[0];
          if (first) first.click();
        }
        /* Escape is handled by the shared close-all handler, and every
         * other key is left to the input so it can be typed. */
        return;
      }
      /* Arrow-key navigation inside an open ADS dropdown menu. */
      if (focused && focused.classList && focused.classList.contains('ads-dd__option')) {
        if (e.key === 'Tab') {
          closeAllAdsDds();
        } else if (e.key === 'ArrowDown' || e.key === 'ArrowUp'
            || e.key === 'Home' || e.key === 'End') {
          e.preventDefault();
          const menu = focused.parentElement;
          if (!menu) return;
          const opts = Array.from(menu.querySelectorAll('.ads-dd__option'))
            .filter(function (option) {
              /* A filtered-out option is not somewhere the arrows may
               * land, and neither is a disabled one. */
              return !option.hidden
                && option.getAttribute('aria-disabled') !== 'true';
            });
          const i = opts.indexOf(focused);
          /* On a searchable list, arrowing up off the first option goes
           * back to the search field rather than sticking, so the user
           * can keep refining without reaching for the mouse. */
          const search = menu.querySelector('.ads-dd__search-input');
          if (search && e.key === 'ArrowUp' && i === 0) {
            search.focus({ preventScroll: true });
            return;
          }
          const next = e.key === 'Home'
            ? opts[0]
            : e.key === 'End'
              ? opts[opts.length - 1]
              : e.key === 'ArrowDown'
                ? opts[Math.min(i + 1, opts.length - 1)]
                : opts[Math.max(i - 1, 0)];
          if (next) {
            next.focus({ preventScroll: true });
            next.scrollIntoView({ block: 'nearest' });
          }
        } else if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          focused.click();
        } else if (e.key.length === 1 && !e.altKey && !e.ctrlKey && !e.metaKey) {
          const menu = focused.parentElement;
          /* On a searchable list a printable key belongs in the search
           * field, which is a better answer than jump-to-first-letter
           * and the reason the field is there. */
          const typeInto = menu && menu.querySelector('.ads-dd__search-input');
          if (typeInto) {
            typeInto.focus({ preventScroll: true });
            return;
          }
          const opts = menu && Array.from(menu.querySelectorAll('.ads-dd__option'))
            .filter(function (option) {
              return option.getAttribute('aria-disabled') !== 'true';
            });
          if (opts && opts.length) {
            const query = e.key.toLocaleLowerCase();
            const start = Math.max(0, opts.indexOf(focused) + 1);
            const ordered = opts.slice(start).concat(opts.slice(0, start));
            const match = ordered.find(function (option) {
              return option.textContent.trim().toLocaleLowerCase().startsWith(query);
            });
            if (match) {
              e.preventDefault();
              match.focus({ preventScroll: true });
              match.scrollIntoView({ block: 'nearest' });
            }
          }
        }
      }
    });
    document.addEventListener("keyup", (e) => {
      const trigger = document.querySelector('[data-ads-dd-space-open]');
      if (e.key === ' ' && trigger) {
        e.preventDefault();
        trigger.removeAttribute('data-ads-dd-space-open');
      }
    });
  }

  // ----- Boot ---------------------------------------------------------------

  // ============================================================
  //  CREATE RATE CARD PAGE  (Figma 70:1660)
  //  Routing, EDL select, ADS calendar, validation.
  //  All product state (RATE_CARDS, filters, table) is untouched.
  // ============================================================

  // --- Routing -------------------------------------------------
  //  Single source of truth = body[data-route]. CSS toggles which
  //  .page-route is visible. No re-render, no remount, no state loss.
  //
  //  URL contract (prototype-grade, refresh-safe):
  //    /                                 → list
  //    /?section=create                  → CARD step
  //    /?section=line&cardId=RC-DRAFT-…  → LINE step (cardId carried as draft ref)
  //  We keep the body[data-route] attribute as the rendering source of truth
  //  AND mirror it into the URL via replaceState so a refresh stays put.
  const ROUTE_TO_SECTION = { list: null, create: "create", line: "line", atlas: "atlas" };

  /* ----- Create / Edit mode switch ----------------------------------
   *
   * The Create Rate Card layout doubles as the Edit Rate Card layout
   * per brief - same fields, same accordion sections, same save
   * pipeline. The only differences are:
   *   - Title: "Create Rate Card" vs "Edit Rate Card"
   *   - Subtitle
   *   - Primary button label: "Save Rate Card" vs "Save Changes"
   *   - "Save and Create New Rate Card" is hidden in Edit mode
   *   - Rate Card ID metastrip shows the existing id (no
   *     "Auto-generated on Save" placeholder); auto-regeneration
   *     is suppressed for the session
   *
   * Mode is tracked via body[data-mode="create" | "edit"]; CSS uses
   * it to hide [data-create-only] buttons.
   *
   * setCreatePageMode(mode) updates ALL of the above so the same
   * .page-route[data-page="create"] DOM can serve both flows
   * without re-mount.
   */
  function setCreatePageMode(mode) {
    if (mode !== "edit") mode = "create";
    document.body.setAttribute("data-mode", mode);
    /* Title + subtitle text swap. Stored on data-* attrs in HTML so
     * no string literals leak into JS. */
    var title = document.querySelector('[data-page="create"] .page__title');
    if (title) {
      var key = mode === "edit" ? "data-edit-title" : "data-create-title";
      var txt = title.getAttribute(key);
      if (txt) title.textContent = txt;
    }
    var subtitle = document.querySelector('[data-page="create"] .page__subtitle');
    if (subtitle) {
      var subKey = mode === "edit" ? "data-edit-subtitle" : "data-create-subtitle";
      var subTxt = subtitle.getAttribute(subKey);
      if (subTxt) subtitle.textContent = subTxt;
    }
    /* Primary button label swap. data-create-label / data-edit-label
     * sit on the button element itself. */
    var primary = document.querySelector('[data-action="save-publish"]');
    if (primary) {
      var btnKey = mode === "edit" ? "data-edit-label" : "data-create-label";
      var btnTxt = primary.getAttribute(btnKey);
      if (btnTxt) primary.textContent = btnTxt;
    }
  }

  /* openEditRateCard(row) - entry point from the Name link + Edit
   * icon on the Manager table. Hydrates the Create page form with
   * the selected row's data, locks the active draft id so saves
   * UPDATE the same row (commitFormToTable upserts on cardId), and
   * flips the page into edit mode. */
  function openEditRateCard(row) {
    if (!row) return;
    /* Stamp the active session draft to point at this row so all
     * subsequent saves (Save Changes / Save as Draft) upsert the
     * SAME RATE_CARDS entry instead of creating a new one. */
    window.__rcDraft = { cardId: row.rateCardId, values: row };
    setCreatePageMode("edit");
    navigateTo("create");
    /* Enrich the URL with mode=edit + cardId={rateCardId} so the
     * route is bookmarkable and deep-linkable to this specific rate
     * card's Edit surface (brief: "URL becomes /rate-card-manager/
     * {id}/edit?section=card"). navigateTo("create") clears cardId
     * by default; we restore it here after the route flip. */
    try {
      var u = new URL(window.location.href);
      u.searchParams.set("mode", "edit");
      u.searchParams.set("cardId", row.rateCardId);
      window.history.replaceState({ section: "create" }, "", u.toString());
    } catch (_) { /* URL sync is best-effort */ }
    /* Defer the prefill so navigateTo's render + focus pass
     * complete first; the form fields then receive their values
     * after the page is visible. Then snapshot the post-prefill
     * state for dirty tracking, and start the Save Changes button
     * in its disabled state. */
    requestAnimationFrame(function(){
      prefillEditForm(row);
      /* Apply the same progressive-disclosure default as Create:
       * CARD open, LINE + PREM collapsed. Done AFTER prefill so
       * the form values are already populated in the DOM (collapsed
       * sections just hide their bodies, they don't drop values). */
      resetAccordionsToDefault();
      /* Clear any stray CARD-touched state from a previous Create
       * session. Edit mode uses dirty tracking, not the required-
       * field gate, so this is purely defensive. */
      window.__rcCardTouched = false;
      /* Initialize the auto-open-next-accordion flags from the
       * prefilled state. If CARD is already complete on entry
       * (typical for an existing published rate card), suppress the
       * auto-open of LINE so the user isn't surprised by a section
       * flying open on a page they just navigated to. Same for
       * PREM. If either upstream section is still incomplete on
       * entry (e.g. editing a draft that never got LINE filled in),
       * the flag stays false and the auto-open will fire the first
       * time the user finishes that section. */
      window.__rcAutoOpenedLine = countCardRequiredMissing() === 0;
      window.__rcAutoOpenedPrem =
        countCardRequiredMissing() === 0 && countLineRequiredMissing() === 0;
      /* Wait one more frame so the prefill's value/textContent
       * writes are observable when we snapshot. */
      requestAnimationFrame(function(){
        snapshotEditFormState();
        recomputeEditDirtyState();
      });
    });
  }

  /* --------- Edit-mode dirty tracking ---------------------------------
   * Save Changes (in edit mode) is enabled only when at least one
   * editable form value differs from the row originally loaded into
   * the form. We snapshot the post-prefill values into
   * window.__editSnapshot, then every input/change event on the
   * Create page recomputes whether the current form matches.
   *
   * Field universe (all editable values in CARD, LINE, PREM):
   *   - <input> + <textarea>: read .value (trimmed for diff so
   *     leading/trailing whitespace doesn't count as a change -
   *     mirrors collectForm()'s trim() behavior).
   *   - .edl-select: read data-value attribute (the listbox writes
   *     the chosen option there in selectEdlOption).
   *   - .ads-datepicker: read .ads-datepicker__value textContent,
   *     ignoring placeholder text (placeholder state is "no value").
   *
   * Custom controls (edl-select / ads-datepicker) don't dispatch
   * standard 'input'/'change' DOM events when their value changes,
   * so we call recomputeEditDirtyState() explicitly from inside
   * selectEdlOption + the date picker's day-click handler. */
  function snapshotEditFormState() {
    window.__editSnapshot = readEditFormState();
  }
  function readEditFormState() {
    var state = { inputs: {}, selects: {}, dates: {} };
    var root = document.querySelector('[data-page="create"]');
    if (!root) return state;
    root.querySelectorAll('input, textarea').forEach(function(inp){
      var key = inp.id || inp.name;
      if (!key) return;
      state.inputs[key] = (inp.value || "").trim();
    });
    root.querySelectorAll('.edl-select').forEach(function(sel){
      var field = sel.getAttribute('data-field');
      if (!field) return;
      state.selects[field] = sel.getAttribute('data-value') || "";
    });
    root.querySelectorAll('.ads-datepicker').forEach(function(dp){
      var field = dp.getAttribute('data-field');
      if (!field) return;
      var v = dp.querySelector('.ads-datepicker__value');
      var isPlaceholder = v && v.classList.contains('ads-datepicker__value--placeholder');
      state.dates[field] = (v && !isPlaceholder) ? v.textContent.trim() : "";
    });
    return state;
  }
  function editFormIsDirty() {
    var snap = window.__editSnapshot;
    if (!snap) return false;
    var cur = readEditFormState();
    function diff(a, b) {
      var keys = {};
      Object.keys(a).forEach(function(k){ keys[k] = 1; });
      Object.keys(b).forEach(function(k){ keys[k] = 1; });
      for (var k in keys) {
        if ((a[k] || "") !== (b[k] || "")) return true;
      }
      return false;
    }
    return diff(snap.inputs, cur.inputs)
        || diff(snap.selects, cur.selects)
        || diff(snap.dates, cur.dates);
  }
  function recomputeEditDirtyState() {
    var primary = document.querySelector('[data-action="save-publish"]');
    if (!primary) return;
    var editMode = document.body.getAttribute('data-mode') === 'edit';
    if (!editMode) {
      /* Create mode: never force-disable Save Rate Card via dirty
       * tracking - it has its own validation flow. */
      primary.disabled = false;
      primary.removeAttribute('aria-disabled');
      return;
    }
    var dirty = editFormIsDirty();
    primary.disabled = !dirty;
    primary.setAttribute('aria-disabled', dirty ? 'false' : 'true');
  }

  /* Hydrate the Create page form with a row's data. Maps the
   * minimum shared fields (the rest are LINE / PREM details that
   * the seed data doesn't carry per-row; if a future schema adds
   * them, they'll be picked up from row.<field> here). Setting
   * .value + dispatching an input event mirrors what the user
   * would do typing into the field, so all wired listeners
   * (placeholder toggle, validation reset, draft persistence)
   * stay in sync. */
  function prefillEditForm(row) {
    if (!row) return;
    function setInput(sel, val){
      var el = document.querySelector(sel);
      if (!el) return;
      el.value = val == null ? "" : String(val);
      el.dispatchEvent(new Event("input", {bubbles: true}));
      el.dispatchEvent(new Event("change", {bubbles: true}));
    }
    function setSelect(field, val){
      var sel = document.querySelector('.edl-select[data-field="' + field + '"]');
      if (!sel) return;
      sel.setAttribute("data-value", val == null ? "" : String(val));
      var v = sel.querySelector(".edl-select__value");
      if (v) {
        if (val) {
          v.textContent = String(val);
          v.classList.remove("edl-select__value--placeholder");
        } else {
          v.classList.add("edl-select__value--placeholder");
          var ph = v.getAttribute("data-placeholder-text");
          if (ph) v.textContent = ph;
        }
      }
    }
    /* CARD details */
    setInput("#rc-name", row.name);
    setInput("#be-id", row.buyingEntityId || "");
    setInput("#be-name", row.buyingEntity);
    setSelect("marketplace", row.marketplace);
    setSelect("season", row.season || "2025-2026");
    /* Update the Rate Card ID metastrip to display the existing id
     * (no "Auto-generated on Save" placeholder). The metastrip is
     * already read-only - it's a <span>, not an input. */
    var rcid = document.getElementById("rc-id");
    if (rcid && row.rateCardId) {
      rcid.textContent = row.rateCardId;
      rcid.classList.remove("is-default");
    }
    /* Clear any inline validation errors the form may have inherited
     * from a prior session. */
    document.querySelectorAll('[data-page="create"] .field.is-invalid')
      .forEach(function(f){ f.classList.remove("is-invalid"); });
    document.querySelectorAll('[data-page="create"] .field__error')
      .forEach(function(e){ setFieldError(e, ""); });
  }

  function navigateTo(route) {
    // Allowed routes:
    //   list   (default) - Rate Card Manager table
    //   create / line    - Create / Edit Rate Card (LINE legacy alias)
    //   atlas            - Standalone Atlas intro deck (2026-06-29 brief)
    const next = (route === "create" || route === "line") ? "create"
               : route === "atlas" ? "atlas"
               : "list";
    document.body.setAttribute("data-route", next);
    /* Arriving at the list is arriving at a fresh list.
     *
     * The selection set outlives the route, so without this a user who
     * ticked two rows, opened a card and came back would find the bulk
     * bar still standing over rows they had stopped thinking about,
     * offering Archive and Delete on a selection they made before a
     * detour. Clearing on entry rather than on leaving means every way
     * in lands the same: the back link, the atlas deck's exits, and the
     * boot default. A browser Back is a document load, which rebuilds
     * the set empty on its own.
     *
     * Repainting rather than re-rendering: the rows are already built
     * and only their selected state is wrong, so this unticks the boxes,
     * returns the header checkbox to unchecked, and drops the bar,
     * without disturbing the page, search, filters or sort the user
     * left the list on. */
    if (next === "list") clearRateCardSelection();
    /* list / create / line / atlas are all Rate Card Manager routes in
     * this repo, so re-assert the sidebar selection on every navigation
     * (list <-> create/edit <-> atlas) rather than letting it drift. */
    setVnavActive(resolveVnavRouteKey());
    // Mirror to URL so a hard refresh restores the same step. Use replaceState
    // (no history entry per click. Back-button should still jump straight
    // back to whatever the user was looking at before they opened Create).
    try {
      const u = new URL(window.location.href);
      const section = ROUTE_TO_SECTION[next];
      if (section) {
        u.searchParams.set("section", section);
        const draftId = window.__rcDraft && window.__rcDraft.cardId;
        if (next === "line" && draftId) {
          u.searchParams.set("cardId", draftId);
        } else if (
          next === "create"
          && isV2Family(document.body.getAttribute("data-version"))
          && u.searchParams.get("mode") === "edit"
          && u.searchParams.get("cardId")
        ) {
          /* Version 2.x restores Edit from the existing mode + cardId
           * deep-link contract. Keep both parameters while navigateTo()
           * normalizes section=create. Frozen 1.x behavior is unchanged. */
        } else {
          u.searchParams.delete("cardId");
        }
      } else {
        u.searchParams.delete("section");
        u.searchParams.delete("cardId");
      }
      // Strip cache-buster query params we add only for QA snapshots so the
      // restored URL stays clean for the user.
      ["cardlineqa","line1","line2","px2","px4","final","ovlp","resp","r2","s8regression","finalqa","resp480","listcheck","listcheck2","px","px3","btn","btn2","line","vis"].forEach(k => u.searchParams.delete(k));
      window.history.replaceState({ section: section || "list" }, "", u.toString());
    } catch (_) { /* URL sync is best-effort */ }
    // Always scroll to top when changing routes. Each page has its own
    // header at the top, so this matches user expectation.
    window.scrollTo({ top: 0, behavior: "instant" in window ? "auto" : "auto" });
    // Close any leaked popovers from the previous route.
    closeAllPopovers();
    // Focus the back link when entering Create (Figma 157-1924 merged
    // CARD + LINE + PREM onto a single Create page; the LINE route is
    // now an alias for Create). Returns focus to the Create button on
    // the list page.
    if (next === "create") {
      const visiblePage = document.querySelector('.page-route[data-page="create"]');
      const back = visiblePage && visiblePage.querySelector('[data-action="go-list"]');
      if (back) back.focus();
    } else {
      const create = document.querySelector('[data-action="create"]');
      if (create) create.focus();
    }
  }

  /* ------------- Rate Card ID generation -----------------------------
   * The existing RATE_CARDS seed data uses the pattern
   *   RC-{ENTITY}-{KEYWORD}-{MKT}-{SEASON}
   * where:
   *   ENTITY  = uppercase alphanumeric slug of the buying entity
   *             (e.g. DENTSU, WPP, GROUPM, DMED, IPG, PG)
   *   KEYWORD = a 1-2 token slug derived from the rate card name
   *             (e.g. CTV, VIDEO, PLANNING, MULTIYEAR, HULU, DPLUS,
   *             STREAM, PACK, SPORTS) - the descriptor that
   *             distinguishes the card within an entity+season
   *   MKT     = 2-letter marketplace code (UF/SC/PG/AD/SP)
   *   SEASON  = 4-digit year pair (2526, 2425)
   *
   * generateRateCardId(formValues) returns an id matching that
   * pattern. If a collision exists with an already-present id (seed
   * data or a previously persisted user row) we append a numeric
   * suffix "-N" until unique. */
  function generateRateCardId(v) {
    v = v || {};
    // ENTITY slug: uppercase alphanumeric only, take the first word
    // of the buying entity name (handles "P&G" -> "PG",
    // "IPG / L’Oréal" -> "IPG"). Fall back to "NEW" so a draft saved
    // before the user has typed anything still produces a valid id.
    var entityRaw = (v.buyingEntityName || "").trim();
    var entityFirstWord = entityRaw.split(/[\s/]+/)[0] || "";
    var entitySlug = entityFirstWord.toUpperCase().replace(/[^A-Z0-9]/g, "")
      || (v.buyingEntityName || "").toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 10)
      || "NEW";

    // KEYWORD slug from the rate card name, skipping noise words
    // ("Rate", "Card", "the", years, parenthesized season tokens).
    // Pick the first qualifying token; cap at 9 chars to match the
    // seed pattern (PLANNING, MULTIYEAR, STREAM, PACK, SPORTS, etc).
    var nameRaw = (v.name || "").replace(/\(\d{2}-\d{2}\)/g, "").trim();
    var skip = { "rate":1, "card":1, "the":1, "a":1, "and":1, "of":1, "for":1 };
    var keyword = "";
    var tokens = nameRaw.split(/[^A-Za-z0-9]+/);
    for (var i = 0; i < tokens.length; i++) {
      var t = tokens[i];
      if (!t) continue;
      if (skip[t.toLowerCase()]) continue;
      if (/^\d+$/.test(t)) continue;          // skip pure numbers
      keyword = t.toUpperCase().slice(0, 9);
      break;
    }
    if (!keyword) keyword = "DRAFT";

    // Marketplace 2-letter code (matches the seed data's MKT slot).
    var mktMap = {
      "upfront":"UF", "scatter":"SC", "programmatic":"PG",
      "addressable":"AD", "sponsorship":"SP", "sports":"SP",
      "streaming":"SC", "multiplatform":"MP"
    };
    var mkt = mktMap[(v.marketplace || "").toLowerCase()] || "SC";

    // SEASON: 4-digit year pair extracted from the season dropdown
    // (e.g. "25-26" -> "2526"). Defaults to current default 2526.
    var season = (v.season || "25-26").replace(/[^0-9]/g, "") || "2526";

    var baseId = "RC-" + entitySlug + "-" + keyword + "-" + mkt + "-" + season;

    // Disambiguate if the same id already exists (seed data or
    // previously persisted user row). Append -2, -3, ... until free.
    var id = baseId;
    var n = 2;
    while (RATE_CARDS.some(function(r){ return r.rateCardId === id; })) {
      id = baseId + "-" + n;
      n += 1;
      if (n > 999) { id = baseId + "-" + Date.now().toString(36).toUpperCase().slice(-4); break; }
    }
    return id;
  }

  // --- CARD draft state (in-memory) --------------------------------
  //  Prototype-grade. Real product would POST to /api/rate-cards/draft
  //  and get back a real cardId. Here we generate a stable mock so the
  //  LINE step can show "0 LINE rows attached to RC-<id>" and the
  //  URL can carry ?cardId=… for refresh restore.
  function saveCardDraft() {
    const v = (typeof collectForm === "function") ? collectForm() : {};
    if (!window.__rcDraft) {
      /* Mint a cardId ONCE per session for the active draft, in the
       * exact existing seed-data format (RC-{ENTITY}-{KEYWORD}-{MKT}-
       * {SEASON}). The same id is reused by every subsequent
       * "Save as Draft" click on this same form (commitFormToTable
       * keys its upsert on this id), so repeat draft saves UPDATE the
       * existing table row instead of creating duplicates. */
      window.__rcDraft = { cardId: generateRateCardId(v), values: v };
    } else {
      window.__rcDraft.values = v;
    }
    // Reflect the draft cardId in the inline Rate Card ID metadata
    // strip (Figma 173:2546 frame 181:4064). Was previously a disabled
    // input; now a <span id="rc-id"> with data-default holding the
    // initial "Auto-generated on Save" label. Writing textContent
    // replaces that placeholder copy with the actual draft ID.
    const idEl = document.getElementById("rc-id");
    if (idEl) {
      var current = idEl.textContent.trim();
      var defaultText = idEl.getAttribute("data-default") || "";
      if (!current || current === defaultText) {
        idEl.textContent = window.__rcDraft.cardId;
        idEl.classList.remove("is-default");
      }
    }
  }

  /* ===================================================================
   * commitFormToTable
   *
   * Persist the current Create-page form values as a brand-new row in
   * the shared RATE_CARDS mock store, then unshift so the new card
   * shows up as the FIRST row on the Rate Card Manager table.
   *
   * Row schema (matches the existing RATE_CARDS entries):
   *   { id, status, saleshubId, rateCardId, name, marketplace,
   *     buyingEntity, lastUpdated, version, season }
   *
   * Defaults applied when the form doesn't capture a value (table-
   * only metadata not in the brief's form):
   *   - status      = "Draft"   (saved cards start as Draft until
   *                              the user explicitly publishes; the
   *                              value is passed through
   *                              normalizeStatus() so internal labels
   *                              like "ACTIVE" still surface as the
   *                              PRD-aligned "Published")
   *   - version     = 1
   *   - saleshubId  = synthetic 15-char string in the existing format
   *   - lastUpdated = today in "MMM DD, YYYY"
   *   - rateCardId  = derived "RC-{entity}-{season}-{n}" if the form
   *                   hasn't been assigned a draft id yet
   *
   * After mutating RATE_CARDS the table is re-rendered (no-op if the
   * user is on the Create page; the next list-page render picks up
   * the new row from the same shared array).
   * ================================================================ */
  /* localStorage key for user-saved rows. The Quick Edit feature uses
   * its own key (rate-card-manager.quick-edit.v1); these two are
   * intentionally separate concerns. */
  var SAVED_ROWS_STORAGE_KEY = "rate-card-manager.saved-rows.v1";

  function commitFormToTable(opts) {
    opts = opts || {};
    /* opts.values lets a caller that is not the Create page supply the
     * record it collected itself (the Create rate card modal does), so
     * id minting, the upsert, and persistence still run here once. */
    var v = opts.values
      || ((typeof collectForm === "function") ? collectForm() : {});

    /* Prefer the session draft cardId minted by saveCardDraft() so
     * repeat "Save as Draft" clicks update the SAME row instead of
     * creating duplicates. Falls back to generateRateCardId() (same
     * RC-{ENTITY}-{KEYWORD}-{MKT}-{SEASON} format used everywhere)
     * when there's no active draft - e.g. someone clicks Save Rate
     * Card without ever clicking Save as Draft first. */
    /* A typed ID wins over a draft's generated one. The user's value is
     * the record's identity now, and silently replacing it with a
     * generated string is exactly what this field exists to stop. */
    var rateCardId = normalizeRateCardId(v.rateCardId)
      || (window.__rcDraft && window.__rcDraft.cardId) || "";
    if (!rateCardId) {
      rateCardId = generateRateCardId(v);
    }

    /* Find an existing row with this rateCardId so we can UPSERT.
     * upsert semantics:
     *   - new id: prepend a new row (newest-first)
     *   - existing id: update the row's fields, bump version, move to
     *     index 0 so the most-recently-touched draft stays at the top */
    var existingIdx = -1;
    for (var i = 0; i < RATE_CARDS.length; i++) {
      if (RATE_CARDS[i].rateCardId === rateCardId) { existingIdx = i; break; }
    }

    /* Today's date in the "MMM DD, YYYY" format the table uses. */
    var months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
    var dt = new Date();
    var lastUpdated = months[dt.getMonth()] + " " + String(dt.getDate()).padStart(2, "0") + ", " + dt.getFullYear();

    /* Season, in the PRD's YYYY-YYYY form. Prefer the form's deal-season
     * value, then the readable range the naming convention puts in the
     * name ("WPP, Streaming Video Upfront 2026-2027"). The "(25-26)"
     * shorthand is only still read because a user can type a name in the
     * pre-convention style; nothing seeded uses it any more. */
    var season = v.season || "";
    if (!season) {
      var m = /(20\d{2})\s*[-\u2013]\s*(20\d{2})/.exec(v.name || "");
      if (m) {
        season = m[1] + "-" + m[2];
      } else {
        m = /\((\d{2})-(\d{2})\)/.exec(v.name || "");
        season = m ? "20" + m[1] + "-20" + m[2] : "";
      }
    }

    var row;
    if (existingIdx >= 0) {
      /* UPDATE path: keep the same row id + SalesHub id + creation
       * lineage; refresh user-controlled fields + bump version.
       * normalizeStatus() guards against opts.status being passed in
       * as a deprecated value (e.g. "ACTIVE" from an internal API
       * mapping) and against any legacy row.status that may have
       * slipped past hydrate (e.g. localStorage from before the
       * 2026-06-25 status simplification). */
      row = RATE_CARDS[existingIdx];
      row.status = normalizeStatus(opts.status || row.status || "Draft");
      row.name = v.name || row.name || "Untitled Rate Card";
      row.marketplace = v.marketplace || row.marketplace || "";
      row.buyingEntity = v.buyingEntityName || row.buyingEntity || "";
      row.lastUpdated = lastUpdated;
      row.season = season || row.season;
      row.version = (parseInt(row.version, 10) || 1) + 1;
      row.userSaved = true;
      /* Move to top so the most-recently-touched record is first. */
      RATE_CARDS.splice(existingIdx, 1);
      RATE_CARDS.unshift(row);
    } else {
      /* INSERT path: mint a fresh numeric row id + SalesHub id. */
      var maxId = 0;
      for (var j = 0; j < RATE_CARDS.length; j++) {
        var n = parseInt(RATE_CARDS[j].id, 10);
        if (!isNaN(n) && n > maxId) maxId = n;
      }
      var newRowId = String(maxId + 1);

      /* SalesHub IDs in the existing seed data are 15 chars long and
       * start with "00141000". Mirror that format so the SalesHub-ID
       * filter behaves consistently. */
      var shSuffix = (Math.floor(Math.random() * 9_999_999_999) + 1_000_000_000)
        .toString().slice(0, 7);
      var saleshubId = "00141000" + shSuffix;

      row = {
        id: newRowId,
        /* Pass through normalizeStatus so an internal-mapped value
         * like "ACTIVE" (from a future Save and Publish endpoint)
         * still surfaces as the PRD-aligned visible label. */
        status: normalizeStatus(opts.status || "Draft"),
        saleshubId: saleshubId,
        rateCardId: rateCardId,
        name: v.name || "Untitled Rate Card",
        marketplace: v.marketplace || "",
        buyingEntity: v.buyingEntityName || "",
        lastUpdated: lastUpdated,
        version: 1,
        season: season,
        userSaved: true
      };
      RATE_CARDS.unshift(row);
    }

    /* Reset to page 1 so the new/updated top row is actually visible
     * (if the user had paginated deeper before saving). page is a
     * closure var declared higher up in this IIFE. */
    page = 1;
    /* Re-render so the new row is visible immediately (no-op when
     * the user is on the Create page since the list <tbody> is
     * hidden; the next navigateTo("list") still uses the same
     * shared RATE_CARDS array). */
    try { renderTable(); } catch (e) { /* table not mounted yet */ }
    /* Persist user-saved rows so they survive refresh. */
    persistSavedRowsToStorage();

    return row;
  }

  /* ------- Saved-rows persistence (localStorage) ----------------------
   * Snapshot every row in RATE_CARDS that was created by the user
   * (row.userSaved === true) into localStorage so the table state
   * survives a page refresh. On boot, hydrateSavedRowsFromStorage
   * reads the key and unshifts each persisted row back onto
   * RATE_CARDS, keyed by rateCardId so we never duplicate.
   *
   * Storage shape (key SAVED_ROWS_STORAGE_KEY):
   *   { v: 1, rows: [<row object>, ...] }
   *
   * The wrapper object lets us bump v: 1 -> v: 2 in the future if
   * the row schema changes, without crashing on stale data. */
  function persistSavedRowsToStorage() {
    try {
      var rows = RATE_CARDS.filter(function(r){ return r.userSaved === true; });
      var payload = { v: 1, rows: rows };
      window.localStorage.setItem(SAVED_ROWS_STORAGE_KEY, JSON.stringify(payload));
    } catch (e) {
      /* localStorage can throw in private-mode Safari or when quota is
       * exceeded. We silently swallow; the in-memory RATE_CARDS state
       * still reflects the save for the current session. */
    }
  }

  function hydrateSavedRowsFromStorage() {
    try {
      var raw = window.localStorage.getItem(SAVED_ROWS_STORAGE_KEY);
      if (!raw) return;
      var payload = JSON.parse(raw);
      if (!payload || !Array.isArray(payload.rows)) return;
      /* Build a set of ids already in RATE_CARDS so a duplicate
       * rateCardId (e.g. user reopens the same draft session) doesn't
       * stack. Persisted rows take precedence: we remove any existing
       * row sharing the same rateCardId, then unshift the persisted
       * one back on top to preserve recency. */
      payload.rows.forEach(function(saved){
        if (!saved || !saved.rateCardId) return;
        for (var i = RATE_CARDS.length - 1; i >= 0; i--) {
          if (RATE_CARDS[i].rateCardId === saved.rateCardId) {
            RATE_CARDS.splice(i, 1);
          }
        }
        saved.userSaved = true;
        /* Normalize any pre-fix browser state. A user who opened the
         * app before 2026-06-25 may have a localStorage row saved
         * with an old status (e.g. "Active", "Pending Review",
         * "Archived", "ACTIVE"). Coerce to the two-state model
         * BEFORE the row is unshifted onto RATE_CARDS so the table
         * + filters + sort never see a deprecated value. */
        saved.status = normalizeStatus(saved.status);
        RATE_CARDS.unshift(saved);
      });
    } catch (e) {
      /* Stale or corrupt JSON: ignore, fall back to the seeded data. */
    }
  }

  /* ===================================================================
   * duplicateRateCard(sourceRow)
   *
   * Clone an existing RATE_CARDS row and insert the clone at index 0
   * (top of the Manager table). Required behavior per brief:
   *  - Full deep copy of every field on the source object (status,
   *    saleshubId, rateCardId, name, marketplace, buyingEntity,
   *    lastUpdated, version, season, and any hidden/internal flags)
   *  - rateCardId = sourceBaseId + "-N" where N is the next unused
   *    integer for that base id (sourceBaseId strips any prior -N
   *    suffix so duplicating an already-duplicated row still
   *    increments cleanly off the original base)
   *  - name = sourceBaseName + " (Copy)" or " (Copy N)", tracking the
   *    same N as the id
   *  - lastUpdated = today (current MMM DD, YYYY string the seed +
   *    table use). Source row's lastUpdated stays untouched.
   *  - All other fields copied verbatim from source (status, etc).
   *  - Mark .userSaved so persistSavedRowsToStorage picks it up
   *    and the duplicate survives a browser refresh.
   *  - Re-render the table + toast "Rate card duplicated."
   * ================================================================ */
  function duplicateRateCard(sourceRow, options) {
    if (!sourceRow) return null;
    /* `quiet` suppresses only the per-row success toast so the 2.1
     * multi-select Copy can report one summary line instead of one
     * toast per duplicated row. Failures always still speak up. */
    var quiet = !!(options && options.quiet);

    /* 1. Derive the BASE id and BASE name by stripping any prior
     *    duplicate-counter suffix. The seed pattern is
     *      RC-{ENTITY}-{KEYWORD}-{MKT}-{SEASON}
     *    where SEASON is 4 digits (e.g. 2526). A duplicate appends a
     *    1-3 digit counter after that season -> RC-..-2526-3.
     *    Strip ONLY a trailing "-{1-3 digit}" that follows a 4-digit
     *    run, so we never accidentally chop the season itself. For
     *    the name (which doesn't end in a season but does end with
     *    "Rate Card" etc) strip any trailing "-{1-3 digit}". */
    var idSuffixRe = /(-\d{4})-\d{1,3}$/;
    /* Strip " (Copy)" / " (Copy 3)", plus the bare "-3" that copies
     * carried before names ended in a readable season. */
    var nameSuffixRe = /(?:\s*\(Copy(?:\s+\d{1,3})?\)|-\d{1,3})$/;
    var baseId = sourceRow.rateCardId.replace(idSuffixRe, "$1");
    var baseName = (sourceRow.name || "").replace(nameSuffixRe, "");

    /* 2. Walk RATE_CARDS to find the highest existing 1-3 digit
     *    duplicate-counter for THIS base id, then pick (max + 1).
     *    If no duplicates exist yet we start at 1, matching the
     *    brief's example "First duplicate: RC-...-2526-1". The
     *    1-3 digit cap mirrors step 1's strip rule so the season
     *    can never be misread as a counter. */
    var idEsc = baseId.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    var dupRe = new RegExp("^" + idEsc + "-(\\d{1,3})$");
    var maxN = 0;
    for (var i = 0; i < RATE_CARDS.length; i++) {
      var rcid = RATE_CARDS[i].rateCardId || "";
      var m = dupRe.exec(rcid);
      if (m) {
        var n = parseInt(m[1], 10);
        if (!isNaN(n) && n > maxN) maxN = n;
      }
    }
    var nextN = maxN + 1;
    var newRateCardId = baseId + "-" + nextN;
    /* The id keeps the compact "-N" counter because it is a machine
     * identifier. The visible name gets " (Copy)" instead: every name
     * now ends in a readable season, so "2025-2026-1" reads as a broken
     * year rather than as the first copy. */
    var newName = baseName + (nextN > 1 ? " (Copy " + nextN + ")" : " (Copy)");

    /* 3. Mint a fresh row.id (numeric, one greater than current
     *    max). Used by Quick Edit + per-row event handlers as a
     *    stable internal key independent of rateCardId. */
    var maxId = 0;
    for (var j = 0; j < RATE_CARDS.length; j++) {
      var nn = parseInt(RATE_CARDS[j].id, 10);
      if (!isNaN(nn) && nn > maxId) maxId = nn;
    }
    var newRowId = String(maxId + 1);

    /* 4. Today's date in the seed-data "MMM DD, YYYY" format so the
     *    list renderer (formatLastUpdated) converts it to MM/DD/YYYY
     *    consistently with every other row. */
    var months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
    var d = new Date();
    var today = months[d.getMonth()] + " " + String(d.getDate()).padStart(2, "0") + ", " + d.getFullYear();

    /* 5. Deep-copy every enumerable field from the source so any
     *    hidden/internal fields (e.g. future LINE / PREM nested
     *    blobs) come along. structuredClone is available in all
     *    target browsers; JSON round-trip is the fallback for any
     *    edge case that throws (functions, circular refs). */
    var clone;
    try {
      clone = structuredClone(sourceRow);
    } catch (e) {
      clone = JSON.parse(JSON.stringify(sourceRow));
    }

    /* 6. Apply the duplicate-specific field overrides on top of the
     *    full clone. Everything else (status, saleshubId, marketplace,
     *    buyingEntity, version, season, ...) stays identical to the
     *    source per the brief. */
    clone.id          = newRowId;
    clone.rateCardId  = newRateCardId;
    clone.name        = newName;
    clone.lastUpdated = today;
    clone.userSaved   = true;
    /* Per PRD: duplicates must only ever surface Draft or Published.
     * If the source row carried a legacy / deprecated status (e.g. a
     * row hydrated from a pre-fix localStorage payload) normalize it
     * here so the clone never propagates an unsupported chip. */
    clone.status      = "Draft";

    try {
      var sourceFile = getExportFile(sourceRow);
      if (sourceFile && sourceFile.card) {
        var duplicatedFile = JSON.parse(JSON.stringify(sourceFile));
        var lineIdMap = {};
        duplicatedFile.card.id = newRateCardId;
        duplicatedFile.card.name = newName;
        duplicatedFile.status = "Draft";
        duplicatedFile.lines = (duplicatedFile.lines || []).map(function (line, index) {
          var next = Object.assign({}, line);
          var nextId = newRateCardId + "-LINE-" + String(index + 1).padStart(3, "0");
          lineIdMap[line.id] = nextId;
          next.id = nextId;
          next.attachToCard = newRateCardId;
          return next;
        });
        duplicatedFile.premiums = (duplicatedFile.premiums || []).map(function (premium, index) {
          var next = Object.assign({}, premium);
          next.id = newRateCardId + "-PREM-" + String(index + 1).padStart(3, "0");
          next.attachToCard = newRateCardId;
          next.lineItemIds = (premium.lineItemIds || []).map(function (lineId) {
            return lineIdMap[lineId];
          }).filter(Boolean);
          return next;
        });
        duplicatedFile.updatedAt = new Date().toISOString();
        var files = JSON.parse(
          window.localStorage.getItem("rate-card-manager.v2.files") || "{}"
        );
        files[newRateCardId] = duplicatedFile;
        window.localStorage.setItem(
          "rate-card-manager.v2.files",
          JSON.stringify(files)
        );
      }
    } catch (_) {
      toastV12(
        { title: "Unable to duplicate rate card", message: "Try again.", variant: "error" },
        "Unable to duplicate rate card."
      );
      return null;
    }

    /* 7. Insert at the top of the table. */
    RATE_CARDS.unshift(clone);

    /* 8. Reset to page 1 + re-render so the new row is visible and
     *    persist so the duplicate survives a refresh. */
    page = 1;
    try { renderTable(); } catch (e) { /* table not mounted yet */ }
    persistSavedRowsToStorage();

    /* 9. Brief-mandated toast copy. v1.2 uses the ADS success variant
     * per the 2026-07-09 toast restyle brief; v1.1 keeps the neutral
     * info style so its visual contract stays unchanged. */
    if (quiet) {
      /* no per-row toast: the caller summarizes the whole batch */
    } else if (typeof toastV12 === "function") {
      toastV12(
        { message: "Rate card duplicated.", variant: "success" },
        "Rate card duplicated."
      );
    } else if (typeof toast === "function") {
      toast("Rate card duplicated.");
    }

    return clone;
  }

  /* Reset every editable field on the Create page (CARD + LINE + PREM
   * sections). Used by "Save and Create New Rate Card" so the user lands
   * on a clean form after persisting the current one. Resets:
   *   - text/number inputs to empty
   *   - edl-selects to their original placeholder (data-default-value)
   *   - datepicker values to empty
   *   - clears all inline error states
   *   - clears the draft cardId in #rc-id
   *   - clears window.__rcDraft so the next save mints a fresh ID
   */
  function resetCreateForm() {
    const root = document.querySelector('[data-page="create"]');
    if (!root) return;
    // Text + number inputs - rc-id is now a <span> not an input, so the
    // generic input clear sets only real form inputs to "". The
    // rc-id metadata strip is reset below alongside the draft state.
    root.querySelectorAll('input').forEach(function(inp){
      inp.value = "";
    });
    // Reset the Rate Card ID metadata strip back to its default copy
    // ("Auto-generated on Save"), matching its initial render state.
    var rcIdEl = root.querySelector("#rc-id");
    if (rcIdEl) {
      var defaultText = rcIdEl.getAttribute("data-default") || "";
      rcIdEl.textContent = defaultText;
      rcIdEl.classList.add("is-default");
    }
    // edl-select triggers - reset to placeholder text + clear data-value.
    // snapshotCreateFormPlaceholders() runs once at boot and stamps the
    // original placeholder copy onto each select / datepicker value via
    // data-placeholder-text so we can restore it precisely here without
    // hard-coding strings (and without breaking when the seed copy
    // changes in Figma later).
    root.querySelectorAll('.edl-select').forEach(function(sel){
      var defVal = sel.getAttribute('data-default-value') || "";
      sel.setAttribute('data-value', defVal);
      var valueEl = sel.querySelector('.edl-select__value');
      if (valueEl) {
        if (defVal) {
          /* Field has a meaningful default (e.g. Currency=USD,
           * Deal Season=25-26): restore that value as the live
           * selection so the "Keep default values where appropriate"
           * rule from the brief is honored. */
          valueEl.textContent = defVal;
          valueEl.classList.remove('edl-select__value--placeholder');
        } else {
          var ph = valueEl.getAttribute('data-placeholder-text');
          if (ph) valueEl.textContent = ph;
          valueEl.classList.add('edl-select__value--placeholder');
        }
      }
    });
    // Datepicker values - restore the original "Select Start Date" /
    // "Select End Date" placeholder text snapshotted at boot.
    root.querySelectorAll('.ads-datepicker__value').forEach(function(v){
      var ph = v.getAttribute('data-placeholder-text');
      if (ph) v.textContent = ph;
      v.classList.add('ads-datepicker__value--placeholder');
    });
    // Clear inline validation errors
    root.querySelectorAll('.field.is-invalid').forEach(function(f){ f.classList.remove('is-invalid'); });
    root.querySelectorAll('.field__error').forEach(function(e){ setFieldError(e, ""); });
    // Restore progressive-disclosure accordion default: CARD open,
    // LINE + PREM collapsed. Also clears header status badges.
    resetAccordionsToDefault();
    // Reset CARD-touched flag so a fresh Create form doesn't paint
    // errors on first render. Also recompute the save-button gate
    // so primary actions return to disabled state on a blank form.
    window.__rcCardTouched = false;
    /* Reset the auto-open-next-accordion one-shot flags. A fresh
     * blank Create form starts with everything empty, so auto-open
     * should be armed and fire the first time each upstream section
     * becomes complete. */
    window.__rcAutoOpenedLine = false;
    window.__rcAutoOpenedPrem = false;
    if (typeof recomputeCreateSaveState === 'function') recomputeCreateSaveState();
    // Clear the draft handle so the next save mints a fresh cardId
    window.__rcDraft = null;
  }

  /* Test affordance: expose commitFormToTable + resetCreateForm on
   * window so QA scripts can drive the post-validation branch of the
   * Save-and-Create-New handler directly. Same convention as the
   * RATE_CARDS + toast hooks (non-enumerable, read-only). */
  try {
    Object.defineProperty(window, "commitFormToTable", {
      value: commitFormToTable, writable: false, enumerable: false, configurable: false
    });
    Object.defineProperty(window, "resetCreateForm", {
      value: resetCreateForm, writable: false, enumerable: false, configurable: false
    });
  } catch (e) { /* property may already exist if app re-inits */ }

  /* Snapshot the original placeholder copy for every select-value and
   * datepicker-value on the Create page. Runs ONCE on boot before the
   * user can interact with the form, so resetCreateForm can later
   * restore the exact original text after a save. The placeholders
   * live in DOM as the initial textContent (e.g. "Select marketplace",
   * "Select Start Date") and would otherwise be lost the moment the
   * user picks a value. */
  function snapshotCreateFormPlaceholders() {
    var root = document.querySelector('[data-page="create"]');
    if (!root) return;
    root.querySelectorAll('.edl-select__value, .ads-datepicker__value').forEach(function(el){
      /* Only snapshot if the value is still in its placeholder state -
       * once a user has picked something we don't want to overwrite
       * the stamp with their value. */
      if (el.classList.contains('edl-select__value--placeholder') ||
          el.classList.contains('ads-datepicker__value--placeholder')) {
        if (!el.hasAttribute('data-placeholder-text')) {
          el.setAttribute('data-placeholder-text', el.textContent.trim());
        }
      }
    });
  }

  /* Toggle accordion open/closed.  is-open class + aria-expanded on the
   * header drive the visual + screen-reader state.  Form values stay in
   * the DOM (display:none on the body) so collapsing never loses data.
   *
   * Section-leave validation (2026-06-29 brief): when the user opens
   * LINE or PREM and CARD has missing required fields, mark CARD as
   * touched + paint its header error summary. We DO NOT block opening
   * the other section - the user can navigate freely - but the CARD
   * accordion now signals that work is incomplete.
   *
   * Manual-toggle short-circuit (2026-07-09 brief): once the user has
   * manually opened OR closed LINE / PREM, we treat that as "the user
   * has expressed intent about this section's open state" and never
   * auto-open it again in this form session. Setting the flag on
   * manual toggle keeps the auto-open flow from fighting the user
   * (e.g. user opens LINE, closes it, then completes CARD - LINE
   * stays closed because the flag is already true). */
  function toggleAccordion(section) {
    if (!section) return;
    var header = section.querySelector('.accordion__header');
    var nowOpen = !section.classList.contains('is-open');
    section.classList.toggle('is-open', nowOpen);
    if (header) header.setAttribute('aria-expanded', String(nowOpen));
    var key = section.getAttribute('data-accordion');
    /* Record manual engagement so auto-open never overrides the user's
     * explicit choice. Fires on both open and close, before any other
     * side effects. */
    if (key === 'line') window.__rcAutoOpenedLine = true;
    if (key === 'prem') window.__rcAutoOpenedPrem = true;
    if (nowOpen) {
      if (key === 'line' || key === 'prem') {
        /* User just opened LINE or PREM. If CARD-required fields
         * aren't all valid, surface that now (don't force the user
         * back to CARD, just light up the error summary). */
        var missing = countCardRequiredMissing();
        if (missing > 0) {
          window.__rcCardTouched = true;
          renderCardErrorState();
        }
      }
    }
  }

  /* Force a specific accordion into open / closed state (idempotent -
   * unlike toggleAccordion which flips current state). Used by the
   * progressive-disclosure flow when entering Create or Edit mode
   * (CARD opens, LINE+PREM collapse) and when validation expands the
   * first errored section. */
  function setAccordionOpen(section, open) {
    if (!section) return;
    var header = section.querySelector('.accordion__header');
    section.classList.toggle('is-open', !!open);
    if (header) header.setAttribute('aria-expanded', String(!!open));
  }

  /* Restore the progressive-disclosure default per the 2026-06-29
   * brief: CARD details starts expanded, LINE + PREM collapsed. Called
   * by both resetCreateForm (Create flow) and openEditRateCard (Edit
   * flow) so first paint of either always matches the same pattern. */
  function resetAccordionsToDefault() {
    var card = document.querySelector('[data-accordion="card"]');
    var line = document.querySelector('[data-accordion="line"]');
    var prem = document.querySelector('[data-accordion="prem"]');
    setAccordionOpen(card, true);
    setAccordionOpen(line, false);
    setAccordionOpen(prem, false);
    /* Clear any leftover header status badges so re-entering the form
     * doesn't show stale "N required fields missing" text from a
     * previous session. */
    document.querySelectorAll('[data-accordion-status]').forEach(function(el){
      el.textContent = "";
      el.classList.remove('accordion__status--error', 'accordion__status--ok');
    });
    document.querySelectorAll('.accordion').forEach(function(acc){
      acc.classList.remove('accordion--has-errors', 'accordion--complete');
    });
  }

  /* Render the per-section validation status into each accordion
   * header's right-aligned slot.
   *
   *   counts: { card: 0, line: 2, prem: 0 }   (from validateForm)
   *   touched: ["card","line","prem"] - which sections the validator
   *            actually exercised; sections in this list with count=0
   *            get the subtle "completed" check, sections NOT in the
   *            list stay neutral (no badge).
   *
   * Header copy follows the brief example: "3 required fields missing"
   * (singular: "1 required field missing"). Completed sections show
   * just the check icon - subtle and visually quiet. */
  function renderAccordionStatuses(counts, touched) {
    counts = counts || {};
    touched = touched || [];
    var sections = ["card", "line", "prem"];
    sections.forEach(function(key){
      var acc = document.querySelector('[data-accordion="' + key + '"]');
      var slot = document.querySelector('[data-accordion-status="' + key + '"]');
      if (!acc || !slot) return;
      var n = counts[key] || 0;
      acc.classList.toggle('accordion--has-errors', n > 0);
      acc.classList.toggle('accordion--complete', n === 0 && touched.indexOf(key) !== -1);
      if (n > 0) {
        var noun = n === 1 ? "required field missing" : "required fields missing";
        slot.textContent = n + " " + noun;
        slot.classList.add('accordion__status--error');
        slot.classList.remove('accordion__status--ok');
      } else if (touched.indexOf(key) !== -1) {
        /* Subtle ADS check + "Completed" label - the brief says keep
         * this quiet so it's a small icon + caption, not a chip. */
        slot.innerHTML =
          '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">' +
          '<path d="M5 12.5l4.2 4.2 9.8-9.8" stroke="currentColor"' +
            ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>' +
          '</svg><span>Completed</span>';
        slot.classList.add('accordion__status--ok');
        slot.classList.remove('accordion__status--error');
      } else {
        slot.textContent = "";
        slot.classList.remove('accordion__status--error', 'accordion__status--ok');
      }
    });
  }

  /* ===================================================================
   *  CARD-required field tracking + save-button gate
   *  (2026-06-29 brief: Save rate card + Save and create new should be
   *   disabled until the user has filled the minimum CARD-required set;
   *   header summary + field-level errors update live once CARD has
   *   been "touched" - either by attempting save or by opening LINE/PREM
   *   while CARD is incomplete.)
   * ================================================================ */
  const CARD_REQUIRED = [
    { id: 'name',           sel: '#rc-name',
      read: function(){ var el=document.querySelector('#rc-name'); return el ? el.value.trim() : ''; } },
    { id: 'buying-entity-id', sel: '#be-id',
      read: function(){ var el=document.querySelector('#be-id'); return el ? el.value.trim() : ''; } },
    { id: 'buying-entity-name', sel: '#be-name',
      read: function(){ var el=document.querySelector('#be-name'); return el ? el.value.trim() : ''; } },
    { id: 'marketplace',    sel: '.edl-select[data-field="marketplace"]',
      read: function(){ var el=document.querySelector('.edl-select[data-field="marketplace"]'); return el ? (el.getAttribute('data-value')||'').trim() : ''; } },
    { id: 'season',         sel: '.edl-select[data-field="season"]',
      read: function(){ var el=document.querySelector('.edl-select[data-field="season"]'); return el ? (el.getAttribute('data-value')||'').trim() : ''; } },
    { id: 'eff-start',      sel: '.ads-datepicker[data-field="eff-start"]',
      read: function(){
        var v = document.querySelector('.ads-datepicker[data-field="eff-start"] .ads-datepicker__value');
        if (!v) return '';
        if (v.classList.contains('ads-datepicker__value--placeholder')) return '';
        return (v.textContent || '').trim();
      }
    },
  ];

  /* Returns the count of CARD-required fields currently empty (0 = all
   * filled). Used by both the save-button gate and the header summary. */
  function countCardRequiredMissing() {
    var n = 0;
    CARD_REQUIRED.forEach(function(f){ if (!f.read()) n += 1; });
    return n;
  }

  /* Returns the list of CARD-required field ids currently empty.
   * Used by renderCardErrorState to paint per-field error markers. */
  function listCardRequiredMissing() {
    return CARD_REQUIRED.filter(function(f){ return !f.read(); }).map(function(f){ return f; });
  }

  /* LINE-required field set. Matches validateForm's LINE required list
   * (Figma 157:5466 - Ad Type / Ad Product, Base Offering, Cost Method,
   * Base Rate). Base Rate treats "" as missing but "0" as valid per
   * PRD R5, so the read() below is truthy for any non-empty value.
   * We treat non-numeric values as still "present" for auto-open
   * purposes; the full validator (validateForm) is what actually
   * blocks Save when a value fails the numeric regex. */
  const LINE_REQUIRED = [
    { id: 'ad-type',       sel: '.edl-select[data-field="ad-type"]',
      read: function(){ var el=document.querySelector('.edl-select[data-field="ad-type"]'); return el ? (el.getAttribute('data-value')||'').trim() : ''; } },
    { id: 'base-offering', sel: '.edl-select[data-field="base-offering"]',
      read: function(){ var el=document.querySelector('.edl-select[data-field="base-offering"]'); return el ? (el.getAttribute('data-value')||'').trim() : ''; } },
    { id: 'cost-method',   sel: '.edl-select[data-field="cost-method"]',
      read: function(){ var el=document.querySelector('.edl-select[data-field="cost-method"]'); return el ? (el.getAttribute('data-value')||'').trim() : ''; } },
    { id: 'base-rate',     sel: '#ln-baserate',
      read: function(){ var el=document.querySelector('#ln-baserate'); return el ? (el.value||'').trim() : ''; } },
  ];

  /* Returns the count of LINE-required fields currently empty (0 = all
   * filled). Used by the auto-open-next-accordion behavior below; not
   * a gate on Save. Full LINE validation still runs through
   * validateForm() at save time. */
  function countLineRequiredMissing() {
    var n = 0;
    LINE_REQUIRED.forEach(function(f){ if (!f.read()) n += 1; });
    return n;
  }

  /* ===================================================================
   *  Progressive auto-open of the next accordion section
   *  (2026-07-09 brief: when all required fields in CARD are complete,
   *   LINE opens automatically the FIRST time it happens; same for
   *   LINE -> PREM. This is NOT a stepper - users can still open or
   *   close any section at any time. See toggleAccordion() for how
   *   manual toggles short-circuit future auto-opens.)
   *
   * Session flags (per Create/Edit form session):
   *   window.__rcAutoOpenedLine  - true once LINE has been auto-opened
   *                                OR manually toggled by the user.
   *                                Once true, we never auto-open LINE
   *                                again for this session.
   *   window.__rcAutoOpenedPrem  - same semantics for PREM.
   *
   * The flags are reset to false by resetCreateForm() (fresh Create
   * flow) and initialized from the current field state by
   * openEditRateCard() (Edit mode: pre-filled sections are treated as
   * "already engaged" so they never trigger surprise auto-opens on
   * entry).
   * ================================================================ */
  function maybeAutoOpenNextAccordion() {
    // Only meaningful on the Create/Edit route. On other routes the
    // accordions don't exist yet and the flags aren't tracked.
    if (document.body.getAttribute('data-route') !== 'create') return;

    var card = document.querySelector('[data-accordion="card"]');
    var line = document.querySelector('[data-accordion="line"]');
    var prem = document.querySelector('[data-accordion="prem"]');
    if (!card || !line || !prem) return;

    // CARD complete + LINE hasn't been auto-opened yet -> auto-open LINE.
    if (!window.__rcAutoOpenedLine && countCardRequiredMissing() === 0) {
      window.__rcAutoOpenedLine = true;
      if (!line.classList.contains('is-open')) {
        setAccordionOpen(line, true);
        scrollAccordionHeaderIfOffscreen(line);
      }
    }

    // LINE complete + CARD complete + PREM hasn't been auto-opened yet
    // -> auto-open PREM. Requiring CARD complete too avoids the weird
    // case where the user manually opens LINE first, fills LINE, and
    // suddenly PREM opens even though CARD still has missing fields.
    if (!window.__rcAutoOpenedPrem
        && countCardRequiredMissing() === 0
        && countLineRequiredMissing() === 0) {
      window.__rcAutoOpenedPrem = true;
      if (!prem.classList.contains('is-open')) {
        setAccordionOpen(prem, true);
        scrollAccordionHeaderIfOffscreen(prem);
      }
    }
  }

  /* Scroll the accordion header into view ONLY if it's currently
   * outside the visible viewport, per the brief:
   *   "If the next section is partially off-screen, scroll just enough
   *    so the section header is visible. No aggressive scroll jump."
   * We compare the header's rect against a viewport window inset by
   * the sticky top nav (~72px) so the header doesn't hide underneath
   * it. block: 'nearest' means the browser scrolls by the minimum
   * needed, matching "scroll just enough" precisely. */
  function scrollAccordionHeaderIfOffscreen(section) {
    if (!section) return;
    var header = section.querySelector('.accordion__header');
    if (!header || typeof header.getBoundingClientRect !== 'function') return;
    var rect = header.getBoundingClientRect();
    var vh = window.innerHeight || document.documentElement.clientHeight || 0;
    // Sticky global nav height - keep the header from being pinned
    // underneath it. Matches the .gnav sticky top from styles.css.
    var stickyTop = 72;
    var fullyVisible = rect.top >= stickyTop && rect.bottom <= vh - 8;
    if (fullyVisible) return;
    try {
      header.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    } catch (_) {
      /* Older browsers without smooth-scroll options: fall back to
       * an unconditional scrollIntoView. */
      header.scrollIntoView();
    }
  }

  /* Paint / clear CARD's accordion header summary + per-field error
   * state. Only paints field-level errors when `window.__rcCardTouched`
   * is truthy - the brief says "Do not show errors before the user
   * interacts with the form or tries to move forward."
   *
   * Per-field error copy: "Required" (concise, per the brief). */
  function renderCardErrorState() {
    var missing = listCardRequiredMissing();
    var n = missing.length;
    var card = document.querySelector('[data-accordion="card"]');
    var slot = document.querySelector('[data-accordion-status="card"]');

    /* Always clear stale field errors for required fields the user
     * has now filled (the brief says "Once the user fills a required
     * field, clear that field's error immediately"). */
    CARD_REQUIRED.forEach(function(f){
      var target = document.querySelector(f.sel);
      if (!target) return;
      var field = target.closest('.field');
      if (!field) return;
      var hasVal = !!f.read();
      if (hasVal) {
        field.classList.remove('is-invalid');
        setFieldError(field.querySelector('.field__error'), '');
      } else if (window.__rcCardTouched) {
        /* Empty + touched: paint the ADS error state. */
        field.classList.add('is-invalid');
        setFieldError(field.querySelector('.field__error'), 'Required');
      }
    });

    if (!card || !slot) return;
    if (window.__rcCardTouched && n > 0) {
      card.classList.add('accordion--has-errors');
      card.classList.remove('accordion--complete');
      var noun = n === 1 ? 'required field missing' : 'required fields missing';
      slot.textContent = n + ' ' + noun;
      slot.classList.add('accordion__status--error');
      slot.classList.remove('accordion__status--ok');
    } else {
      card.classList.remove('accordion--has-errors');
      slot.textContent = '';
      slot.classList.remove('accordion__status--error', 'accordion__status--ok');
    }
  }

  /* Recompute the create-mode save button gate. Save rate card +
   * Save and create new rate card are DISABLED until all CARD-
   * required fields are filled. Save as draft stays enabled always.
   *
   * In edit mode this is a no-op - recomputeEditDirtyState owns the
   * Save Changes button (dirty tracking, not required-field gating).
   *
   * Idempotent + cheap; safe to call from every input/change event. */
  function recomputeCreateSaveState() {
    var editMode = document.body.getAttribute('data-mode') === 'edit';
    if (!editMode) {
      /* CREATE mode only: gate the primary save buttons on CARD
       * required completion. In Edit mode, recomputeEditDirtyState
       * owns the button state (dirty tracking, not required-field
       * gating). */
      var canSave = countCardRequiredMissing() === 0;
      var primary = document.querySelector('[data-action="save-publish"]');
      var createNew = document.querySelector('[data-action="save-create-new"]');
      [primary, createNew].forEach(function(b){
        if (!b) return;
        b.disabled = !canSave;
        b.setAttribute('aria-disabled', canSave ? 'false' : 'true');
      });
      /* If CARD has already been touched, also live-update the header
       * summary count as the user fills fields. */
      if (window.__rcCardTouched) renderCardErrorState();
    }
    /* Both modes: check whether the current input transition should
     * trigger the auto-open-next-accordion behavior. This runs on
     * every input/change event (delegated listener + custom widget
     * hooks), so any field completion in CARD or LINE opens the
     * downstream section on its first completion transition. */
    maybeAutoOpenNextAccordion();
  }

  // --- Dropdown options (single source of truth per field) ----------
  //  CARD step: Marketplace, Deal Season. LINE step: Ad Type, Base Offering,
  //  Rate Type, Currency. Line conditions moved to a free-form comma-
  //  separated text input on 2026-07-09 (see the removed
  //  LINE_CONDITION_OPTIONS block below) so this array set no longer
  //  covers it. Each field has its own array so the menu builder can
  //  stay generic. Keep these in sync with any business taxonomy that
  //  ships in production.
  /* Marketplace dropdown option sets.
   *
   * v1.1 (legacy): 8 values, matching the pre-PRD seed catalog. Kept
   *   intact so v1.1's visual contract stays byte-identical.
   * v1.2 (canonical, per RCM PRD R2): only Upfront / Scatter /
   *   Multi-Year. Addressable / Programmatic / Sponsorship / Sports /
   *   Streaming / Multiplatform are ad product, demand channel, or
   *   inventory-type values, not marketplaces, so they are excluded
   *   here. The v1.2 rate-card projection (MARKETPLACE_V12_MAP)
   *   remaps any legacy row into this three-value set before the
   *   list, filter, and Quick Edit views read it.
   *
   * The Create / Edit form Marketplace dropdown reads its options via
   * getMarketplaceOptions() so the menu stays in lock-step with the
   * active version. */
  const MARKETPLACE_OPTIONS = [
    "Upfront", "Scatter", "Addressable", "Programmatic",
    "Sponsorship", "Sports", "Streaming", "Multiplatform",
  ];
  const MARKETPLACE_OPTIONS_V12 = ["Upfront", "Scatter", "Multi-Year"];
  function getMarketplaceOptions() {
    var v = (typeof document !== "undefined" && document.body)
      ? document.body.getAttribute("data-version") : null;
    return isModernAppVersion(v) ? MARKETPLACE_OPTIONS_V12 : MARKETPLACE_OPTIONS;
  }
  /* PRD R4: a deal season is YYYY-YYYY. The short "25-26" form was
     ambiguous about the century and did not match what the record
     stores, so the menu now offers the same shape the data uses. */
  const SEASON_OPTIONS = ["2025-2026", "2024-2025", "2023-2024"];
  // LINE-step option sets.
  const AD_TYPE_OPTIONS = [
    "Video", "Display", "Audio", "Connected TV", "Sponsorship", "Native",
  ];
  const BASE_OFFERING_OPTIONS = [
    "Run of Network", "Premium", "Sports", "News", "Originals",
    "Live Events", "Streaming Bundle",
  ];
  // CPM = cost per mille (1k impressions); CPC = cost per click;
  // CPV = cost per view; CPCV = cost per completed view; CPA = cost per
  // acquisition; Flat = flat fee placement.
  const RATE_TYPE_OPTIONS = ["CPM", "CPC", "CPV", "CPCV", "CPA", "Flat"];
  const CURRENCY_OPTIONS = ["USD", "EUR", "GBP", "CAD", "AUD", "JPY"];
  /* Line conditions became a single free-form text input on 2026-07-09
   * (Adam's consolidation: "A18-49, Preemptible" etc). The old
   * LINE_CONDITION_OPTIONS enum + line-condition-1/2/3 dropdown wiring
   * is gone from the DOM; leaving the constant here would be dead code,
   * so it's intentionally removed. If a future task reintroduces
   * suggestions they should ship as an autocomplete over the free-form
   * field, not a dropdown replacement. */
  /* Ad Product / Cost Method options used by the LINE section on the
   * Create page (Figma 123-2833). Cost Method maps to CPM/CPC/etc.; in
   * the old layout the same enum was called "Rate Type" - here we keep
   * Rate Type for the legacy form but expose Cost Method as a separate
   * field for the new design. */
  const AD_PRODUCT_OPTIONS = [
    "Standard Video", "Premium Video", "Display Banner", "Audio Spot",
    "Connected TV", "Sponsorship Slot", "Native Article",
  ];
  const COST_METHOD_OPTIONS = ["CPM", "CPC", "CPV", "CPCV", "CPA", "Flat"];
  /* PREM section dropdown options per brief.
   *   Premium Category: Geo / Duration / 1P Audience / 3P Audience /
   *                     Device Type / Format / Content
   *   Attach Rows: populated from existing rate-card rows (placeholder
   *                examples here; production would query the dataset)
   *   Calculation Method: ADDITIVE_CPM / MULTIPLICATIVE_PCT / FLAT_RATE
   */
  const PREM_CATEGORY_OPTIONS = [
    "Geo", "Duration", "1P Audience", "3P Audience",
    "Device Type", "Format", "Content",
  ];
  const PREM_ATTACH_OPTIONS = [
    "All rows", "RC-DAS-DENTSU-ADDR-SC-2526", "RC-DAS-WPP-VIDEO-UF-2627",
    "RC-DAS-IPG-LOREAL-MY-2526", "RC-DAS-PG-DPLUS-UF-2526",
  ];
  const PREM_CALC_OPTIONS = [
    "ADDITIVE_CPM", "MULTIPLICATIVE_PCT", "FLAT_RATE",
  ];

  function populateEdlSelectOptions() {
    document.querySelectorAll(".edl-select").forEach((el) => {
      const field = el.getAttribute("data-field");
      const menu = el.querySelector(".edl-select__menu");
      if (!menu) return;
      /* page-size ships static HTML options (10/20/50) and go-to-page
       * is rebuilt dynamically by renderTable() to track the current
       * pageCount; both opt out of this generic populate path so the
       * empty-options fallback doesn't wipe their <li>s. Same skip
       * pattern would extend to any future .edl-select that prefers
       * to manage its own options outside the JS option-set
       * constants. */
      if (field === "page-size" || field === "go-to-page") return;
      const opts =
          field === "marketplace"        ? getMarketplaceOptions()
        : field === "season"             ? SEASON_OPTIONS
        : field === "ad-type"            ? AD_TYPE_OPTIONS
        : field === "base-offering"      ? BASE_OFFERING_OPTIONS
        : field === "ad-product"         ? AD_PRODUCT_OPTIONS
        : field === "cost-method"        ? COST_METHOD_OPTIONS
        : field === "rate-type"          ? RATE_TYPE_OPTIONS
        : field === "currency"           ? CURRENCY_OPTIONS
        : field === "prem-category"      ? PREM_CATEGORY_OPTIONS
        : field === "prem-attach"        ? PREM_ATTACH_OPTIONS
        : field === "prem-calc"          ? PREM_CALC_OPTIONS
        : [];
      const current = el.getAttribute("data-value") || "";
      menu.innerHTML = opts.map((v) => {
        const selected = v === current ? " is-selected" : "";
        return `<li class="edl-select__option${selected}" role="option" data-value="${v}" tabindex="-1" aria-selected="${v===current}">${v}</li>`;
      }).join("");
    });
  }

  /* --- EDL select interactions ---------------------------------------
   *
   * Open menus are PORTALED to document.body so they float above the
   * Create page's accordion cards (which have overflow:hidden on the
   * .surface container). Without the portal, the menu would either
   * clip at the card edge or push the form's height. Mirrors the
   * Date Picker portal pattern (_adsPositionPopover / _adsClosePopover).
   *
   * Portal lifecycle:
   *   open  -> stash original parent on el._edlMenuOriginalParent,
   *            move .edl-select__menu to document.body, switch to
   *            position:fixed, compute top/left from trigger rect,
   *            register scroll/resize listeners that close the menu
   *            (fixed coords go stale on scroll)
   *   close -> move menu back to its original parent so subsequent
   *            .edl-select scoped queries still find it
   */
  function _edlPositionMenu(el) {
    var trig = el.querySelector(".edl-select__trigger");
    var menu = el._edlMenu;
    if (!trig || !menu) return;
    var trigRect = trig.getBoundingClientRect();
    var menuW = Math.round(trigRect.width);
    /* Lock the menu width to the trigger width BEFORE measuring height -
     * otherwise an unconstrained position:fixed element fills the
     * viewport width and we'd both render too wide AND mis-measure
     * height. min-width:100% from .edl-select__menu is moot here
     * because the menu is no longer a child of .edl-select (it's
     * been portaled to body); explicit width is required. */
    menu.style.width = menuW + "px";
    var menuH = menu.getBoundingClientRect().height || 280;
    var gap = 4;
    /* Default: drop below the trigger. Flip up only if not enough room
     * below AND there's enough room above. */
    var top;
    var spaceBelow = window.innerHeight - trigRect.bottom;
    if (spaceBelow < menuH + gap && trigRect.top > menuH + gap) {
      top = trigRect.top - menuH - gap;
    } else {
      top = trigRect.bottom + gap;
    }
    var left = trigRect.left;
    /* Clamp to viewport so the menu never overflows the right edge. */
    if (left + menuW + 8 > window.innerWidth) {
      left = window.innerWidth - menuW - 8;
    }
    if (left < 8) left = 8;
    menu.style.top = Math.round(top) + "px";
    menu.style.left = Math.round(left) + "px";
  }

  function _edlCloseMenu(el) {
    if (!el || !el._edlMenuOpen) return;
    var trig = el.querySelector(".edl-select__trigger");
    var menu = el._edlMenu;
    if (trig) trig.setAttribute("aria-expanded", "false");
    if (menu) {
      menu.hidden = true;
      /* Strip the portal-only inline positioning so the next time the
       * menu is opened (or measured by other code) it starts clean. */
      menu.style.position = "";
      menu.style.top = "";
      menu.style.left = "";
      menu.style.width = "";
      menu.style.zIndex = "";
      /* Move menu back to its original parent so future .edl-select
       * scoped queries still find it. */
      if (el._edlMenuOriginalParent && menu.parentElement === document.body) {
        el._edlMenuOriginalParent.appendChild(menu);
      }
    }
    el._edlMenuOpen = false;
    if (el._edlMenuReposition) {
      window.removeEventListener("scroll", el._edlMenuReposition, true);
      window.removeEventListener("resize", el._edlMenuReposition);
      el._edlMenuReposition = null;
    }
  }

  function toggleEdlSelect(el) {
    if (!el) return;
    const trig = el.querySelector(".edl-select__trigger");
    const menu = el.querySelector(".edl-select__menu") || el._edlMenu;
    const open = trig.getAttribute("aria-expanded") === "true";
    /* Close other popovers (Import dropdown, profile menu, other selects)
     * before opening this one. Pass the field name so we don't immediately
     * close ourselves. */
    closeAllPopovers(el.getAttribute("data-field"));
    if (open) {
      _edlCloseMenu(el);
      trig.focus();
    } else {
      /* Portal: stash original parent + move menu to body so it floats
       * above every overflow:hidden / containment ancestor. */
      el._edlMenuOriginalParent = menu.parentElement;
      el._edlMenu = menu;
      el._edlMenuOpen = true;
      /* Switch to fixed positioning so the trigger.getBoundingClientRect()
       * coordinates land in the right viewport-space slot. */
      menu.style.position = "fixed";
      menu.style.zIndex = "1150";
      if (menu.parentElement !== document.body) {
        document.body.appendChild(menu);
      }
      trig.setAttribute("aria-expanded", "true");
      menu.hidden = false;
      /* Position now + again next frame after the browser computes the
       * menu's rendered height. */
      _edlPositionMenu(el);
      requestAnimationFrame(function(){ _edlPositionMenu(el); });
      /* Focus the selected option (or first) for keyboard nav. */
      const opts = menu.querySelectorAll(".edl-select__option");
      const target = menu.querySelector(".edl-select__option.is-selected") || opts[0];
      if (target) {
        opts.forEach((o) => o.classList.remove("is-active"));
        target.classList.add("is-active");
        target.scrollIntoView({ block: "nearest" });
      }
      /* Close on scroll/resize - fixed coords would go stale otherwise. */
      var reposition = function(){ _edlCloseMenu(el); };
      el._edlMenuReposition = reposition;
      window.addEventListener("scroll", reposition, true);
      window.addEventListener("resize", reposition);
    }
  }
  function selectEdlOption(el, value) {
    if (!el) return;
    el.setAttribute("data-value", value);
    const valueEl = el.querySelector(".edl-select__value");
    if (valueEl) {
      valueEl.textContent = value;
      valueEl.classList.remove("edl-select__value--placeholder");
    }
    // Update is-selected state in the menu so re-opening reflects it.
    el.querySelectorAll(".edl-select__option").forEach((o) => {
      const isSel = o.getAttribute("data-value") === value;
      o.classList.toggle("is-selected", isSel);
      o.setAttribute("aria-selected", isSel ? "true" : "false");
    });
    // Clear any validation error on this field.
    const field = el.closest(".field");
    if (field) field.classList.remove("is-invalid");
    /* Footer dropdowns: the ADS-styled edl-select instances on the
     * left ("page-size") and right ("go-to-page") of the table footer
     * are visual replacements for legacy hidden <select> elements.
     * Sync the matching native <select>'s value + dispatch 'change'
     * so the existing listeners (which update `pageSize` / `page`
     * and re-render) keep working without re-plumbing. */
    var footerField = el.getAttribute("data-field");
    if (footerField === "page-size" || footerField === "go-to-page") {
      var nativeSel = document.querySelector('select[data-action="' + footerField + '"]');
      if (nativeSel && nativeSel.value !== value) {
        nativeSel.value = value;
        nativeSel.dispatchEvent(new Event("change", {bubbles: true}));
      }
    }
    /* Close via the portal-aware helper so the menu is moved back to
     * its .edl-select parent and the inline portal styles are stripped. */
    _edlCloseMenu(el);
    const trig = el.querySelector(".edl-select__trigger");
    if (trig) trig.focus();
    /* edl-select doesn't dispatch a bubbling DOM event on the
     * trigger, so the Create-page dirty tracker would miss the
     * change. Recompute explicitly. (no-op outside edit mode) */
    if (typeof recomputeEditDirtyState === 'function') recomputeEditDirtyState();
        if (typeof recomputeCreateSaveState === 'function') recomputeCreateSaveState();
  }

  function wireEdlSelects() {
    /* Skip .edl-select--rcle: those are read-only, decorative variants
     * rendered inside the v1.2 Rate Card Layer Explainer overlay. They
     * intentionally omit the .edl-select__menu / .edl-select__option
     * children because the RCLE explains structure without opening a
     * real listbox. Iterating them here would throw on the missing
     * `menu.addEventListener`. See index.html around the .rcle__layer--v12
     * blocks. */
    document.querySelectorAll(".edl-select:not(.edl-select--rcle)").forEach((el) => {
      const menu = el.querySelector(".edl-select__menu");
      const trig = el.querySelector(".edl-select__trigger");
      if (!menu || !trig) return;
      el.classList.add("ads-select");
      el.classList.add(el.classList.contains("edl-select--compact")
        ? "ads-select--small"
        : "ads-select--default");
      trig.setAttribute("role", "combobox");
      if (!menu.id) {
        menu.id = "ads-select-menu-" + (++adsSelectCounter);
      }
      trig.setAttribute("aria-controls", menu.id);
      if (el.getAttribute("data-select-wired") === "true") return;
      el.setAttribute("data-select-wired", "true");
      // Click selection
      menu.addEventListener("click", (e) => {
        const opt = e.target.closest(".edl-select__option");
        if (!opt) return;
        selectEdlOption(el, opt.getAttribute("data-value"));
      });
      // Keyboard navigation on the trigger
      trig.addEventListener("keydown", (e) => {
        const open = trig.getAttribute("aria-expanded") === "true";
        if ((e.key === "ArrowDown" || e.key === "Enter" || e.key === " ") && !open) {
          e.preventDefault();
          toggleEdlSelect(el);
        }
      });
      // Keyboard navigation inside the menu
      menu.addEventListener("keydown", (e) => {
        const opts = Array.from(menu.querySelectorAll(".edl-select__option"));
        let idx = opts.findIndex((o) => o.classList.contains("is-active"));
        if (idx < 0) idx = 0;
        if (e.key === "ArrowDown") { e.preventDefault(); idx = Math.min(opts.length - 1, idx + 1); }
        else if (e.key === "ArrowUp") { e.preventDefault(); idx = Math.max(0, idx - 1); }
        else if (e.key === "Home") { e.preventDefault(); idx = 0; }
        else if (e.key === "End")  { e.preventDefault(); idx = opts.length - 1; }
        else if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          if (opts[idx]) selectEdlOption(el, opts[idx].getAttribute("data-value"));
          return;
        } else if (e.key === "Escape") {
          e.preventDefault();
          /* Use the portal-aware close helper so the menu is moved back
           * to its .edl-select parent. */
          _edlCloseMenu(el);
          trig.focus();
          return;
        } else return;
        opts.forEach((o) => o.classList.remove("is-active"));
        opts[idx].classList.add("is-active");
        opts[idx].focus({ preventScroll: true });
        opts[idx].scrollIntoView({ block: "nearest" });
      });
      // When menu opens, route subsequent keydowns into it by focusing the menu.
      // The toggle handler already pre-marks `is-active`; we just need to make
      // the menu itself focusable (tabindex=-1) and focus it on open.
      const observer = new MutationObserver(() => {
        if (!menu.hidden) {
          const active = menu.querySelector(".edl-select__option.is-active");
          if (active) active.focus({ preventScroll: true });
        }
      });
      observer.observe(menu, { attributes: true, attributeFilter: ["hidden"] });
    });
  }

  // --- ADS calendar (Effective Start + End) --------------------
  //  Lightweight self-contained month grid + popover. Default value =
  //  today; user can pick another. EDL Indigo/70 = selected. Header
  //  prev/next navigates months. Selection updates the field, closes
  //  the popover, and returns focus to the trigger.
  function formatDateMDY(d) {
    // MM/DD/YYYY (per spec: existing app uses this format)
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    return `${mm}/${dd}/${d.getFullYear()}`;
  }
  function parseDateMDY(s) {
    const m = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec((s || "").trim());
    if (!m) return null;
    const d = new Date(+m[3], +m[1] - 1, +m[2]);
    return isNaN(d) ? null : d;
  }
  function sameDate(a, b) {
    return a && b && a.getFullYear() === b.getFullYear()
        && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
  }
  function renderAdsCalendar(el, viewDate, selectedDate) {
    const pop = el._adsCalPop || el.querySelector(".ads-datepicker__popover");
    if (!pop) return;
    const year = viewDate.getFullYear();
    const month = viewDate.getMonth();
    const monthLabel = viewDate.toLocaleString(undefined, { month: "long", year: "numeric" });
    const first = new Date(year, month, 1);
    const firstDay = first.getDay();
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const prevMonthDays = new Date(year, month, 0).getDate();
    const today = new Date();
    const cells = [];
    // Leading days from previous month
    for (let i = firstDay - 1; i >= 0; i--) {
      const dayNum = prevMonthDays - i;
      const d = new Date(year, month - 1, dayNum);
      cells.push({ d, dayNum, outOfMonth: true });
    }
    // Current month
    for (let day = 1; day <= daysInMonth; day++) {
      const d = new Date(year, month, day);
      cells.push({ d, dayNum: day, outOfMonth: false });
    }
    // Trailing days to fill the last row (multiple of 7)
    while (cells.length % 7 !== 0) {
      const last = cells[cells.length - 1].d;
      const d = new Date(last.getFullYear(), last.getMonth(), last.getDate() + 1);
      cells.push({ d, dayNum: d.getDate(), outOfMonth: true });
    }
    const weekdays = ["Su","Mo","Tu","We","Th","Fr","Sa"];
    pop.innerHTML = `
      <div class="ads-cal">
        <div class="ads-cal__header">
          <button type="button" class="ads-cal__nav" data-cal-nav="prev" aria-label="Previous month">
            <svg class="ads-cal__navicon" width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
              <path d="M10 12.5L5.5 8L10 3.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </button>
          <span class="ads-cal__title">${monthLabel}</span>
          <button type="button" class="ads-cal__nav" data-cal-nav="next" aria-label="Next month">
            <svg class="ads-cal__navicon" width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
              <path d="M6 3.5L10.5 8L6 12.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </button>
        </div>
        <div class="ads-cal__weekdays" role="row">
          ${weekdays.map(w => `<span class="ads-cal__weekday" role="columnheader">${w}</span>`).join("")}
        </div>
        <div class="ads-cal__grid" role="grid">
          ${cells.map((c, i) => {
            const classes = ["ads-cal__day"];
            if (c.outOfMonth) classes.push("is-out-of-month");
            if (sameDate(c.d, today)) classes.push("is-today");
            if (sameDate(c.d, selectedDate)) classes.push("is-selected");
            const iso = `${c.d.getFullYear()}-${String(c.d.getMonth()+1).padStart(2,"0")}-${String(c.d.getDate()).padStart(2,"0")}`;
            const isSelected = sameDate(c.d, selectedDate);
            const isToday = sameDate(c.d, today);
            const ariaSel = isSelected ? ' aria-selected="true"' : "";
            const ariaCurrent = isToday ? ' aria-current="date"' : "";
            const tabIndex = isSelected || (!selectedDate && isToday) ? "0" : "-1";
            const ariaLabel = c.d.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric", year: "numeric" });
            return `<button type="button" class="${classes.join(" ")}" role="gridcell"${ariaSel}${ariaCurrent} tabindex="${tabIndex}" aria-label="${ariaLabel}" data-iso="${iso}">${c.dayNum}</button>`;
          }).join("")}
        </div>
      </div>
    `;
    // Store the current view (month/year) on the element so prev/next can
    // re-render from the same anchor without re-deriving from the value.
    el._adsCalView = new Date(year, month, 1);
    el._adsCalSelected = selectedDate || null;
  }
  /* Date Picker popover - portal architecture.
   *
   * The popover ELEMENT lives inside the trigger's .ads-datepicker wrapper
   * in the markup so that all the existing wireAdsCalendars click/keydown
   * delegation, closeAllPopovers lookups, and validation classes (.field
   * .is-invalid .ads-datepicker__trigger) keep working without touching
   * them. When the popover OPENS we move that element to document.body
   * via appendChild() so no ancestor's overflow:hidden / transform /
   * containment can clip it. Coordinates are computed via fixed
   * positioning relative to the trigger's viewport rect. When the
   * popover CLOSES we move the element back to its original parent so
   * scoped selectors (.ads-datepicker .ads-datepicker__popover) still
   * resolve next time we open the picker.
   *
   * On scroll / resize while the picker is open we close it because the
   * fixed coordinates become stale (the trigger may have moved). */
  function _adsPositionPopover(el) {
    var trig = el.querySelector(".ads-datepicker__trigger");
    var pop = el._adsCalPop;
    if (!trig || !pop) return;
    var trigRect = trig.getBoundingClientRect();
    var popH = pop.getBoundingClientRect().height || 320;
    var popW = pop.getBoundingClientRect().width  || 283;
    var gap = 4;
    /* Default: drop below the trigger. Flip up only if not enough room. */
    var top;
    var flipUp = false;
    var spaceBelow = window.innerHeight - trigRect.bottom;
    if (spaceBelow < popH + gap && trigRect.top > popH + gap) {
      flipUp = true;
      top = trigRect.top - popH - gap;
    } else {
      top = trigRect.bottom + gap;
    }
    /* Default: left-align to the trigger. Clamp to viewport if it would
     * overflow the right edge. */
    var left = trigRect.left;
    if (left + popW + 8 > window.innerWidth) {
      left = window.innerWidth - popW - 8;
    }
    if (left < 8) left = 8;
    pop.style.top = Math.round(top) + "px";
    pop.style.left = Math.round(left) + "px";
    el.classList.toggle("ads-datepicker--flip-up", flipUp);
  }

  function _adsClosePopover(el) {
    if (!el || !el._adsCalOpen) return;
    var trig = el.querySelector(".ads-datepicker__trigger");
    var pop = el._adsCalPop;
    if (trig) trig.setAttribute("aria-expanded", "false");
    if (pop) {
      pop.hidden = true;
      /* Move popover back to its original parent so future renderAdsCalendar
       * lookups (which use querySelector inside .ads-datepicker) still find it. */
      if (el._adsCalOriginalParent && pop.parentElement === document.body) {
        el._adsCalOriginalParent.appendChild(pop);
      }
    }
    el.classList.remove("ads-datepicker--flip-up");
    el._adsCalOpen = false;
    /* Remove the scroll/resize listeners we added on open. */
    if (el._adsCalReposition) {
      window.removeEventListener("scroll", el._adsCalReposition, true);
      window.removeEventListener("resize", el._adsCalReposition);
      el._adsCalReposition = null;
    }
  }

  function toggleAdsCal(el) {
    if (!el) return;
    const trig = el.querySelector(".ads-datepicker__trigger");
    if (!trig || trig.disabled
      || trig.getAttribute("aria-disabled") === "true"
      || trig.getAttribute("aria-readonly") === "true") return;
    const open = trig.getAttribute("aria-expanded") === "true";
    closeAllPopovers(el.getAttribute("data-field"));
    if (open) {
      _adsClosePopover(el);
      trig.focus();
    } else {
      const pop = el.querySelector(".ads-datepicker__popover");
      const valueEl = el.querySelector(".ads-datepicker__value");
      const selected = parseDateMDY(valueEl ? valueEl.textContent : "");
      const current = selected || new Date();
      renderAdsCalendar(el, current, selected);
      trig.setAttribute("aria-expanded", "true");
      pop.hidden = false;

      /* Portal: stash the original parent + move popover to body so it
       * escapes every overflow:hidden / transform / containment ancestor. */
      el._adsCalOriginalParent = pop.parentElement;
      el._adsCalPop = pop;
      el._adsCalOpen = true;
      if (pop.parentElement !== document.body) {
        document.body.appendChild(pop);
      }

      /* Position now that the popover is in body. Schedule for next frame
       * so the browser has a chance to compute its rendered height. */
      _adsPositionPopover(el);
      requestAnimationFrame(function(){
        _adsPositionPopover(el);
        var initialDay = pop.querySelector('.ads-cal__day[tabindex="0"]')
          || pop.querySelector(".ads-cal__day:not(.is-out-of-month)");
        if (initialDay) initialDay.focus();
      });

      /* Keep the portaled popover anchored on scroll and resize. Repositioning
       * also prevents keyboard focus movement inside the calendar from
       * dismissing it when the browser scrolls the focused day into view. */
      var reposition = function() {
        if (el._adsCalOpen) requestAnimationFrame(function () { _adsPositionPopover(el); });
      };
      el._adsCalReposition = reposition;
      window.addEventListener("scroll", reposition, true);
      window.addEventListener("resize", reposition);
    }
  }
  function wireAdsCalendars() {
    /* Skip .ads-datepicker--rcle for the same reason wireEdlSelects
     * skips .edl-select--rcle: those are decorative variants in the
     * v1.2 Rate Card Layer Explainer overlay with no popover to wire.
     *
     * Idempotency: gated by data-cal-wired so callers can safely re-
     * invoke this after cloning new .ads-datepicker instances (v1.2
     * Line Items and Premium Adjustments multi-attach flows both do
     * this via buildPremItemNode() / buildLineItemNode()). Without
     * the guard, existing elements would accumulate duplicate click
     * handlers on each re-wire. */
    document.querySelectorAll(".ads-datepicker:not(.ads-datepicker--rcle)").forEach((el) => {
      if (el.getAttribute("data-cal-wired") === "true") return;
      el.setAttribute("data-cal-wired", "true");
      const pop = el.querySelector(".ads-datepicker__popover");
      const trig = el.querySelector(".ads-datepicker__trigger");
      pop.addEventListener("click", (e) => {
        const nav = e.target.closest("[data-cal-nav]");
        if (nav) {
          e.stopPropagation();
          const dir = nav.getAttribute("data-cal-nav") === "next" ? 1 : -1;
          const v = el._adsCalView || new Date();
          renderAdsCalendar(el, new Date(v.getFullYear(), v.getMonth() + dir, 1), el._adsCalSelected);
          const nextNav = pop.querySelector('[data-cal-nav="' + (dir > 0 ? "next" : "prev") + '"]');
          if (nextNav) requestAnimationFrame(function () { nextNav.focus(); });
          return;
        }
        const day = e.target.closest(".ads-cal__day");
        if (!day) return;
        const iso = day.getAttribute("data-iso");
        const [y, m, d] = iso.split("-").map(Number);
        const picked = new Date(y, m - 1, d);
        const valueEl = el.querySelector(".ads-datepicker__value");
        if (valueEl) {
          valueEl.textContent = formatDateMDY(picked);
          /* Drop the placeholder treatment once the user picks a date so
           * the value renders in primary text color, not muted gray. */
          valueEl.classList.remove("ads-datepicker__value--placeholder");
        }
        const field = el.closest(".field");
        if (field) field.classList.remove("is-invalid");
        /* Use portal-aware close so popover is moved back to its original
         * parent (it lives in document.body while open). */
        _adsClosePopover(el);
        trig.focus();
        /* Date picker writes to a <span>, not a form input, so the
         * Create-page dirty tracker wouldn't see the change. Notify
         * explicitly. (no-op outside edit mode) */
        if (typeof recomputeEditDirtyState === 'function') recomputeEditDirtyState();
        if (typeof recomputeCreateSaveState === 'function') recomputeCreateSaveState();
      });
      pop.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
          e.preventDefault();
          _adsClosePopover(el);
          trig.focus();
          return;
        }
        const day = e.target.closest(".ads-cal__day");
        if (!day) return;
        const iso = day.getAttribute("data-iso");
        const parts = iso.split("-").map(Number);
        let target = new Date(parts[0], parts[1] - 1, parts[2]);
        let handled = true;
        if (e.key === "ArrowLeft") target.setDate(target.getDate() - 1);
        else if (e.key === "ArrowRight") target.setDate(target.getDate() + 1);
        else if (e.key === "ArrowUp") target.setDate(target.getDate() - 7);
        else if (e.key === "ArrowDown") target.setDate(target.getDate() + 7);
        else if (e.key === "Home") target.setDate(target.getDate() - target.getDay());
        else if (e.key === "End") target.setDate(target.getDate() + (6 - target.getDay()));
        else if (e.key === "PageUp") target.setMonth(target.getMonth() - 1);
        else if (e.key === "PageDown") target.setMonth(target.getMonth() + 1);
        else handled = false;
        if (!handled) return;
        e.preventDefault();
        renderAdsCalendar(el, target, el._adsCalSelected);
        const targetIso = `${target.getFullYear()}-${String(target.getMonth() + 1).padStart(2, "0")}-${String(target.getDate()).padStart(2, "0")}`;
        const nextDay = pop.querySelector('[data-iso="' + targetIso + '"]');
        if (nextDay) {
          pop.querySelectorAll(".ads-cal__day").forEach(function (button) {
            button.tabIndex = button === nextDay ? 0 : -1;
          });
          nextDay.focus();
        }
      });
    });
  }
  function initDateDefaults() {
    /* Per Figma 123-2833 brief: Effective Start / End fields render with
     * "Select Start Date" / "Select End Date" placeholders by default,
     * not today's date. If the markup specifies placeholder text in the
     * .ads-datepicker__value span we preserve it; otherwise we leave the
     * span empty (CSS placeholder color renders via the
     * --placeholder modifier). */
    document.querySelectorAll(".ads-datepicker .ads-datepicker__value").forEach((v) => {
      /* Only set today's date if the markup explicitly opts in via
       * data-default-today. The new Create page intentionally does NOT
       * opt in - we want the placeholder copy to show. */
      var trigger = v.closest('.ads-datepicker');
      if (trigger && trigger.getAttribute('data-default-today') === 'true') {
        v.textContent = formatDateMDY(new Date());
        v.classList.remove('ads-datepicker__value--placeholder');
      }
      /* Else: leave whatever placeholder text the markup specified, with
       * the --placeholder class for muted color. */
    });
  }

  /* DCM rule order input filter.
   *
   * The DCM rule order field renders as type="text" (see the input in
   * index.html) so the browser's native number-spinner controls never
   * appear. To keep the field numeric-only, we strip any non-digit
   * characters as they're typed / pasted / autofilled. The field is
   * optional so an empty value is valid; only non-digit content is
   * removed. Cursor position is preserved so users editing a mid-value
   * digit don't get their caret jumped to the end. */
  function initDcmRuleInputFilter() {
    var input = document.getElementById("dcm-rule");
    if (!input) return;
    input.addEventListener("input", function () {
      var raw = input.value;
      var cleaned = raw.replace(/\D+/g, "");
      if (cleaned === raw) return; // fast path: user typed a valid digit
      /* Preserve caret position across the mutation. Count digits up to
       * the original caret so if the user pasted "1a2" with caret at
       * index 3, the caret lands at index 2 after "1a2" -> "12". */
      var caret = input.selectionStart || 0;
      var digitsBeforeCaret = raw.slice(0, caret).replace(/\D+/g, "").length;
      input.value = cleaned;
      try { input.setSelectionRange(digitsBeforeCaret, digitsBeforeCaret); }
      catch (_) { /* setSelectionRange throws on unsupported types; ignore. */ }
    });
  }

  /* ==================================================================
   * initColumnResize
   * ==================================================================
   * Draggable column dividers for the Rate Card Manager table
   * (2026-07-08 brief).
   *
   * Design notes:
   *
   * 1. Column widths live in CSS custom properties on the .table
   *    element (--col-status, --col-saleshub, ... --col-action). Both
   *    .table__head and every .row read the same variables via
   *    grid-template-columns, so a single property update on drag
   *    synchronizes header + body without touching individual cells.
   *
   * 2. A resizer <span> is appended to every sortable header except
   *    the last (Action). The span sits absolutely-positioned at the
   *    right edge of its .th (see .th-resizer in styles.css) so the
   *    hit area straddles the column boundary with 8px total width
   *    (4px each side) while the visible divider stays 1px.
   *
   * 3. The Name column is a special case: it starts as
   *    minmax(--col-name, 1fr) so wide screens fill cleanly. On the
   *    FIRST drag of the Name divider we flip the .table root to
   *    .name-fixed, which switches the Name track to a fixed
   *    var(--col-name). Subsequent drags of Name (or of any other
   *    column) then behave predictably - no more "1fr eats my drag".
   *
   * 4. Sort click vs. resize click:
   *    - pointerdown on the resizer: stopPropagation so the button's
   *      internal click detection doesn't count it as a press.
   *    - click on the resizer (bubbling up to the sort button): a
   *      capturing document listener stops the click before it reaches
   *      the delegated body handler.
   *
   * 5. Widths are session-scoped only (no localStorage persistence).
   *    Per the brief: "Column widths should persist while the user
   *    stays on the page. It is okay if widths reset after browser
   *    refresh." CSS variables on .table naturally survive body
   *    re-renders from sort / filter / pagination since we don't
   *    replace .table itself.
   *
   * 6. Text-selection lock during drag: the .table.is-resizing class
   *    forces cursor: col-resize and user-select: none on every
   *    descendant so the cursor doesn't flicker back to pointer/link
   *    when the pointer briefly leaves the resizer during a fast
   *    drag. */
  function initColumnResize() {
    var table = document.querySelector('[data-page="list"] .table');
    if (!table) return;

    /* Column order MUST match the grid-template-columns ordering in
     * styles.css. If a column is inserted or reordered, this array
     * and the CSS-variable name must be updated together. */
    var COL_KEYS = [
      "status", "saleshub", "rcid", "name",
      "market", "buyer", "updated", "ver", "action"
    ];
    var CSS_VARS = {
      status:  "--col-status",
      saleshub:"--col-saleshub",
      rcid:    "--col-rcid",
      name:    "--col-name",
      market:  "--col-market",
      buyer:   "--col-buyer",
      updated: "--col-updated",
      ver:     "--col-ver",
      action:  "--col-action"
    };
    /* Brief-mandated minimum widths (px). Content stays usable when
     * clamped to these floors. The resize handler caps drag deltas
     * against these so users can never crush a column to zero.
     *
     * Name's floor is 300 per the 2026-07-08 sticky-Name brief
     * ("Name column minimum width: 300px. Do not allow Name width
     * below 300px."). This is 40px wider than the earlier resize
     * pass because when Name becomes the sticky-left frozen column
     * during horizontal scroll, it needs enough room to always
     * render the row's rate card name legibly. */
    var MIN_WIDTHS = {
      status:   88,
      saleshub: 150,
      rcid:     180,
      name:     300,
      market:   120,
      buyer:    150,
      updated:  130,
      ver:       72,
      /* Action min bumped 140 -> 160 on 2026-07-08 when the Archive
       * icon (5th action) was added between Export and Delete per
       * Figma 129:5535. 5 x 24 icon + 4 x 8 gap + 8 left pad = 160,
       * which is the smallest width that keeps Delete fully visible
       * inside the cell without clipping. */
      action:   160
    };

    /* COL_KEYS is positional, so the two headers that exist only under
     * 2.1 are excluded rather than renumbering every key: the selection
     * column app.js mounts ahead of Status, and the combined Rate Card
     * ID / Name header, which ships as a trailing sibling in index.html
     * so earlier versions keep their own two headers in place. Both are
     * fixed reference tracks with nothing to resize against, and leaving
     * them in would shift every mapping after them and hand Action a
     * resize handle it has never had. */
    var headers = table.querySelectorAll(
      ".table__head .th:not(.th--select):not(.th--name-id)");
    if (!headers.length) return;

    /* Inject resizer handles into every header EXCEPT the last one
     * (Action). No handle after Action per the brief - it's the
     * rightmost column and there's no next column to shrink into. */
    for (var i = 0; i < headers.length - 1; i++) {
      var th = headers[i];
      /* Idempotent: if init has already run once (e.g. hot reload)
       * don't duplicate the handle. */
      if (th.querySelector(".th-resizer")) continue;
      var rz = document.createElement("span");
      rz.className = "th-resizer";
      rz.setAttribute("data-col-index", String(i));
      rz.setAttribute("aria-hidden", "true");
      /* Title hint - shown as a plain browser tooltip only if the
       * user hovers with intent (no ADS Tooltip overhead for a
       * pointer-only affordance). */
      rz.title = "Drag to resize column";
      th.appendChild(rz);
    }

    /* Active drag state. Populated on pointerdown, cleared on pointerup /
     * pointercancel. `active` doubles as a "drag in progress" flag.
     *
     * Design note: pointermove + pointerup are attached to WINDOW at
     * drag-start (and removed at drag-end) rather than to the table
     * or the resizer. Rationale:
     *   1. Fast drags fly past the 8px resizer hit area within a
     *      single frame; window-level tracking guarantees we still
     *      receive the pointermove events.
     *   2. If the user releases the mouse outside the table (e.g.
     *      over the app shell or the browser chrome), we still get
     *      pointerup and can clean up state + remove the ghost line.
     *   3. Chromium's Input.dispatchMouseEvent (used by the CDP-based
     *      QA harness) doesn't reliably interact with
     *      setPointerCapture, so binding to window keeps QA and real
     *      user behavior aligned. */
    var active = null;
    /* Bound function references so removeEventListener can find and
     * detach them at drag-end (arrow functions bound inline would
     * create fresh references each call, defeating removeEventListener). */
    var boundMove = null;
    var boundEnd  = null;

    /* Capturing click blocker: a click that originates from a resizer
     * must never trigger the sort button that wraps it. Attached to
     * document (not table) with capture=true so it runs BEFORE the
     * delegated body click handler that owns data-action="sort". */
    document.addEventListener("click", function (e) {
      var t = e.target;
      if (t && t.closest && t.closest(".th-resizer")) {
        e.stopPropagation();
        e.preventDefault();
      }
    }, true);

    table.addEventListener("pointerdown", function (e) {
      /* Only respond to primary-button (usually left mouse) drags.
       * Middle- and right-clicks stay unhandled so context menus and
       * back-nav gestures work normally on the header. */
      if (e.button !== 0) return;
      var rz = e.target && e.target.closest && e.target.closest(".th-resizer");
      if (!rz) return;

      e.preventDefault();
      /* stopPropagation prevents the pointerdown from bubbling to the
       * sort <button>, which would otherwise register a press state
       * and (on pointerup) trigger the sort click. */
      e.stopPropagation();

      /* Defensive: if a previous drag is still marked active (should
       * only happen if pointerup was somehow lost), tear it down
       * before starting the next one so state doesn't leak. */
      if (active) endDrag();

      var idx = parseInt(rz.getAttribute("data-col-index"), 10);
      var key = COL_KEYS[idx];
      var th  = headers[idx];

      /* If this is the Name column and it's still in flex mode
       * (minmax(--col-name, 1fr)), capture the CURRENT visual width
       * before flipping to fixed - otherwise the user's first drag
       * of Name would "snap" from whatever 1fr resolved to down to
       * --col-name (typically 360), which reads as a layout jump. */
      var currentWidth = th.getBoundingClientRect().width;
      if (key === "name" && !table.classList.contains("name-fixed")) {
        table.style.setProperty(CSS_VARS.name, currentWidth + "px");
        table.classList.add("name-fixed");
      }

      /* Attach a ghost line to the .table so users see the drag target
       * span the entire table height (header + all rows), not just the
       * 32px header strip. Removed on drag end. */
      var ghost = document.createElement("div");
      ghost.className = "table__resize-ghost";
      table.appendChild(ghost);

      active = {
        rz: rz, key: key, idx: idx, th: th,
        startX: e.clientX,
        startWidth: currentWidth,
        ghost: ghost
      };
      rz.classList.add("is-dragging");
      table.classList.add("is-resizing");
      positionGhost();

      /* Bind pointermove + pointerup to WINDOW for the duration of
       * the drag (see design note on the `active` declaration
       * above). We track them via boundMove/boundEnd so endDrag can
       * detach the exact function references. */
      boundMove = onMove;
      boundEnd  = onEnd;
      window.addEventListener("pointermove", boundMove);
      window.addEventListener("pointerup", boundEnd);
      window.addEventListener("pointercancel", boundEnd);
    });

    /* Named move handler so removeEventListener can find it later.
     * Reads the current active drag state from the module-scoped
     * `active` variable so we don't need a closure per drag. */
    function onMove(e) {
      if (!active) return;
      var dx = e.clientX - active.startX;
      var min = MIN_WIDTHS[active.key];
      /* Clamp against the brief-mandated minimum so users can't crush
       * a column below its content-usable width. No max enforced -
       * the surrounding .table-scroll handles overflow if the sum
       * gets too big for the card. */
      var next = Math.max(min, Math.round(active.startWidth + dx));
      table.style.setProperty(CSS_VARS[active.key], next + "px");
      positionGhost();
    }

    /* Named up/cancel handler so removeEventListener can find it. */
    function onEnd() { endDrag(); }

    /* Shared teardown for pointerup + pointercancel + defensive
     * re-entry. Idempotent: safe to call when no drag is active. */
    function endDrag() {
      if (boundMove) {
        window.removeEventListener("pointermove", boundMove);
        boundMove = null;
      }
      if (boundEnd) {
        window.removeEventListener("pointerup", boundEnd);
        window.removeEventListener("pointercancel", boundEnd);
        boundEnd = null;
      }
      if (!active) return;
      if (active.rz) active.rz.classList.remove("is-dragging");
      if (active.ghost && active.ghost.parentNode) {
        active.ghost.parentNode.removeChild(active.ghost);
      }
      table.classList.remove("is-resizing");
      active = null;
    }

    /* Recompute the ghost line's `left` from the active <th>'s right
     * edge on every pointermove. Reading getBoundingClientRect each
     * frame is fine for a 60Hz drag on one element; measuring against
     * .table's rect keeps the ghost aligned even if the table is
     * horizontally scrolled inside .table-scroll. */
    function positionGhost() {
      if (!active || !active.ghost) return;
      var tRect  = table.getBoundingClientRect();
      var thRect = active.th.getBoundingClientRect();
      /* Position 1px left of the boundary so the ghost sits ON the
       * boundary line rather than one pixel to the right (which would
       * bleed into the next column). */
      var x = Math.round(thRect.right - tRect.left - 1);
      active.ghost.style.left = x + "px";
    }
  }

  // --- Form collection + validation ----------------------------
  function collectForm() {
    const get = (sel) => {
      const el = document.querySelector(sel);
      return el ? el.value.trim() : "";
    };
    // rc-id is now a <span> in the metadata strip (Figma 173:2546),
    // not an <input>. Read its textContent and treat the default
    // placeholder copy ("Auto-generated on Save") as no value yet.
    const rcIdGet = () => {
      const el = document.querySelector("#rc-id");
      if (!el) return "";
      const txt = el.textContent.trim();
      const def = el.getAttribute("data-default") || "";
      return txt === def ? "" : txt;
    };
    const mkt = document.querySelector('.edl-select[data-field="marketplace"]');
    const season = document.querySelector('.edl-select[data-field="season"]');
    const start = document.querySelector('.ads-datepicker[data-field="eff-start"] .ads-datepicker__value');
    const end   = document.querySelector('.ads-datepicker[data-field="eff-end"] .ads-datepicker__value');
    return {
      rateCardId: rcIdGet(),
      name: get("#rc-name"),
      buyingEntityId: get("#be-id"),
      buyingEntityName: get("#be-name"),
      marketplace: mkt ? mkt.getAttribute("data-value") : "",
      season: season ? season.getAttribute("data-value") : "",
      dcmRuleOrder: get("#dcm-rule"),
      effectiveStart: start ? start.textContent.trim() : "",
      effectiveEnd: end ? end.textContent.trim() : "",
    };
  }
  function validateForm() {
    const v = collectForm();
    let ok = true;
    /* Track which accordion section each error belongs to so we can
     * (a) render an "N required fields missing" summary in each
     *     errored section's header, and
     * (b) expand only the FIRST errored section (per the brief - other
     *     errored sections keep their header summary but stay in the
     *     user's current open/closed state). */
    const errorCounts = { card: 0, line: 0, prem: 0 };
    const setError = (sel, msg) => {
      const target = document.querySelector(sel);
      if (!target) { ok = false; return; }
      const field = target.closest(".field");
      if (!field) { ok = false; return; }
      field.classList.add("is-invalid");
      setFieldError(field.querySelector(".field__error"), msg);
      const acc = field.closest('.accordion');
      if (acc) {
        const sec = acc.getAttribute('data-accordion');
        if (sec && Object.prototype.hasOwnProperty.call(errorCounts, sec)) {
          errorCounts[sec] += 1;
        }
      }
      ok = false;
    };
    const clearError = (sel) => {
      const target = document.querySelector(sel);
      if (!target) return;
      const field = target.closest(".field");
      if (!field) return;
      field.classList.remove("is-invalid");
      setFieldError(field.querySelector(".field__error"), "");
    };
    /* Required fields per brief:
     *   CARD: Rate Card Name, Buying Entity ID, Buying Entity Display
     *         Name, Marketplace, Deal Season.
     *   LINE: Ad Type, Base Offering, Ad Product, Cost Method, Base Rate.
     *   PREM: Premium category, Attach rows to rate card, Calculation
     *         method, Value.
     * Effective dates / DCM / Advertiser IDs / conditions / display names
     * / stack order are explicitly OPTIONAL. If a section is collapsed
     * its inputs still exist in the DOM, so validation reaches them and
     * the user can expand the section to see the inline error markers.
     */
    // ---- CARD ----
    if (!v.name) setError("#rc-name", "Rate card name is required.");
    else clearError("#rc-name");
    if (!v.buyingEntityId) setError("#be-id", "Buying Entity ID is required.");
    else clearError("#be-id");
    if (!v.buyingEntityName) setError("#be-name", "Buying entity display name is required.");
    else clearError("#be-name");
    if (!v.marketplace) setError('.edl-select[data-field="marketplace"]', "Marketplace is required.");
    else clearError('.edl-select[data-field="marketplace"]');
    if (!v.season) setError('.edl-select[data-field="season"]', "Deal season is required.");
    else clearError('.edl-select[data-field="season"]');

    // ---- LINE (required per brief: Ad Type, Base Offering, Ad Product,
    //           Cost Method, Base Rate) ----
    var dval = function(field){
      var el = document.querySelector('.edl-select[data-field="' + field + '"]');
      return el ? (el.getAttribute("data-value") || "") : "";
    };
    var get = function(sel){
      var el = document.querySelector(sel);
      return el ? el.value.trim() : "";
    };
    /* LINE required per Figma 157:5466 - 3 dropdowns + Base Rate:
     *   Ad Type, Base Offering, Cost Method, Base Rate.
     * (Ad Product was removed in the LINE redesign - it's not in the
     * Figma target. Currency defaults to USD and isn't blocking save.) */
    if (!dval("ad-type"))     setError('.edl-select[data-field="ad-type"]', "Ad product is required.");
    else clearError('.edl-select[data-field="ad-type"]');
    if (!dval("base-offering"))setError('.edl-select[data-field="base-offering"]', "Base offering is required.");
    else clearError('.edl-select[data-field="base-offering"]');
    if (!dval("cost-method")) setError('.edl-select[data-field="cost-method"]', "Cost method is required.");
    else clearError('.edl-select[data-field="cost-method"]');
    var baseRate = get("#ln-baserate");
    // Base rate per PRD R5: required float, zero is valid. We accept any
    // numeric input (including 0); negatives are not explicitly listed
    // as valid in PRD, so we still reject those - leading-minus regex
    // would over-permit. Empty / non-numeric / negative all fail.
    if (!baseRate) setError("#ln-baserate", "Base rate is required. Zero is allowed.");
    else if (!/^\d*\.?\d+$/.test(baseRate) || isNaN(parseFloat(baseRate))) {
      setError("#ln-baserate", "Base rate must be a number.");
    } else clearError("#ln-baserate");

    // ---- PREM (required per brief: Premium category, Attach rows,
    //           Calculation method, Value) ----
    if (!dval("prem-category"))setError('.edl-select[data-field="prem-category"]', "Premium category is required.");
    else clearError('.edl-select[data-field="prem-category"]');
    if (!dval("prem-attach"))  setError('.edl-select[data-field="prem-attach"]', "Attach to rate card is required.");
    else clearError('.edl-select[data-field="prem-attach"]');
    if (!dval("prem-calc"))    setError('.edl-select[data-field="prem-calc"]', "Calculation method is required.");
    else clearError('.edl-select[data-field="prem-calc"]');
    var premValue = get("#prem-value");
    // PREM value per PRD R6: required float, zero AND negatives valid.
    // We accept a leading minus + digits + optional decimal.
    if (premValue === "") setError("#prem-value", "Premium value is required. Zero and negative values are allowed.");
    else if (!/^-?\d*\.?\d+$/.test(premValue) || isNaN(parseFloat(premValue))) {
      setError("#prem-value", "Premium value must be a number. Zero and negative values are allowed.");
    } else clearError("#prem-value");

    /* Render per-section status (error summary or completed check)
     * in every header. Validation always touches all 3 sections so
     * the third arg lists every key. */
    renderAccordionStatuses(errorCounts, ["card", "line", "prem"]);

    if (!ok) {
      /* Brief: "If validation fails, expand the first section with
       * errors and scroll to it. Keep any other sections with errors
       * collapsed or expanded based on current user state."
       * So we ONLY auto-expand the first errored section - other
       * errored sections keep their current open/closed state and
       * just show the header summary. */
      var firstSection = ["card", "line", "prem"].find(function(k){
        return errorCounts[k] > 0;
      });
      if (firstSection) {
        var acc = document.querySelector('[data-accordion="' + firstSection + '"]');
        if (acc) {
          setAccordionOpen(acc, true);
          /* Scroll into view with some headroom so the section header
           * isn't pinned against the sticky top nav. */
          if (typeof acc.scrollIntoView === "function") {
            acc.scrollIntoView({ behavior: "smooth", block: "start" });
          }
        }
      }
      /* Focus the first invalid field inside that first errored
       * section so keyboard users land at the actionable spot. */
      const first = document.querySelector(
        '[data-accordion="' + firstSection + '"] .field.is-invalid input,' +
        '[data-accordion="' + firstSection + '"] .field.is-invalid .edl-select__trigger,' +
        '[data-accordion="' + firstSection + '"] .field.is-invalid .ads-datepicker__trigger'
      );
      if (first && typeof first.focus === "function") first.focus();
    }
    return ok;
  }

  // --- LINE step: collect + validate -----------------------------------
  //  Per spec the LINE step validates only the core pricing fields:
  //  Ad Type, Base Offering, Rate Type, Base Rate, Currency.
  //  Everything else (Attach Rows, Advertiser ID, Advertiser Display Name,
  //  Line Conditions) is optional in this iteration.
  function collectLineForm() {
    const get = (sel) => {
      const el = document.querySelector(sel);
      return el ? el.value.trim() : "";
    };
    const dval = (field) => {
      const el = document.querySelector('.edl-select[data-field="' + field + '"]');
      return el ? (el.getAttribute("data-value") || "") : "";
    };
    /* Line conditions: v1.2 reads the single consolidated #ln-lc input
     * (Adam's 2026-07-09 update). v1.0 / v1.1 still see three discrete
     * slots (#ln-lc1..3) so those versions read the trio and merge
     * through normalizeLineConditions() to produce the same canonical
     * string. Both branches yield the same "A, B" comma-separated
     * shape so save + validate treat lineConditions the same way. */
    var isV12Doc = document.body
      && isModernAppVersion(document.body.getAttribute("data-version"));
    var lineConditions;
    if (isV12Doc) {
      lineConditions = normalizeLineConditions(get("#ln-lc"));
    } else {
      lineConditions = normalizeLineConditions(
        [get("#ln-lc1"), get("#ln-lc2"), get("#ln-lc3")].join(", ")
      );
    }
    return {
      attachRows:    get("#ln-attach"),
      advertiserId:  get("#ln-advid"),
      advertiserName: get("#ln-advname"),
      adType:        dval("ad-type"),
      baseOffering:  dval("base-offering"),
      rateType:      dval("rate-type"),
      baseRate:      get("#ln-baserate"),
      currency:      dval("currency"),
      lineConditions: lineConditions,
    };
  }
  function validateLineForm() {
    const v = collectLineForm();
    let ok = true;
    const setError = (sel, msg) => {
      const el = document.querySelector(sel);
      if (!el) return;
      const field = el.closest(".field");
      if (!field) return;
      field.classList.add("is-invalid");
      setFieldError(field.querySelector(".field__error"), msg);
      ok = false;
    };
    const clearError = (sel) => {
      const el = document.querySelector(sel);
      if (!el) return;
      const field = el.closest(".field");
      if (!field) return;
      field.classList.remove("is-invalid");
      setFieldError(field.querySelector(".field__error"), "");
    };
    // Required (minimal set per spec): Ad product, Base offering,
    // Cost method, Base rate, Currency. (Legacy LINE-page validator;
    // copy aligned to the PRD-aligned labels used in the unified
    // Create page.)
    if (!v.adType)       setError('.edl-select[data-field="ad-type"]', "Ad product is required.");
    else                 clearError('.edl-select[data-field="ad-type"]');
    if (!v.baseOffering) setError('.edl-select[data-field="base-offering"]', "Base offering is required.");
    else                 clearError('.edl-select[data-field="base-offering"]');
    if (!v.rateType)     setError('.edl-select[data-field="rate-type"]', "Cost method is required.");
    else                 clearError('.edl-select[data-field="rate-type"]');
    if (!v.baseRate)     setError("#ln-baserate", "Base rate is required. Zero is allowed.");
    else                 clearError("#ln-baserate");
    if (!v.currency)     setError('.edl-select[data-field="currency"]', "Currency is required.");
    else                 clearError('.edl-select[data-field="currency"]');
    if (!ok) {
      const first = document.querySelector('[data-page="line"] .field.is-invalid input, [data-page="line"] .field.is-invalid .edl-select__trigger');
      if (first) first.focus();
    }
    return ok;
  }

  /* Sticky Action column shadow toggle.
   *
   * The sticky-Action CSS shows a subtle left-edge shadow only when the
   * .table-scroll element has been horizontally scrolled (otherwise the
   * shadow would visually crowd the body row's last data cell when the
   * table fits and Actions sits flush). We toggle .is-scrolled based on
   * scrollLeft AND on overflow (scrollWidth > clientWidth) - the latter
   * matters at narrow viewports before the user has scrolled, so the
   * shadow appears as soon as the column starts overlapping content.
   *
   * Re-evaluates on scroll + on window resize so toggling between
   * breakpoints (e.g. 1440 -> 1280) updates state in real time. */
  function initStickyActionShadow() {
    const scroller = document.querySelector(".table-scroll");
    if (!scroller) return;
    const update = () => {
      const overflows = scroller.scrollWidth - scroller.clientWidth > 1;
      const scrolled = scroller.scrollLeft > 0;
      scroller.classList.toggle("is-scrolled", overflows && (scrolled || true));
    };
    scroller.addEventListener("scroll", update, {passive: true});
    scroller.addEventListener("wheel", (event) => {
      if (!event.shiftKey || Math.abs(event.deltaY) <= Math.abs(event.deltaX)) return;
      if (scroller.scrollWidth - scroller.clientWidth <= 1) return;
      event.preventDefault();
      scroller.scrollLeft += event.deltaY;
    }, {passive: false});
    window.addEventListener("resize", update);
    /* Run after the first table render so scrollWidth is accurate. */
    requestAnimationFrame(update);
  }

  /* Sticky Name column shadow toggle.
   *
   * Originally introduced 2026-07-08 when sticky Name pinned to
   * left:0. The 2026-07-29 horizontal-scroll refactor moved Name
   * to left: calc(--col-status + --col-rcid) so Name is now the
   * rightmost member of a three-column sticky cluster (Status,
   * Rate Card ID, Name) rather than pinned at the container edge.
   *
   * The subtle right-edge shadow on Name should still only show
   * when Name is ACTUALLY stuck - i.e. when non-sticky columns are
   * being covered by Name. Detection compares Name's current
   * bounding-rect.left to its natural position (row-left plus row
   * padding-left plus Status width plus Rate Card ID width). If
   * sticky pinning is active, the current position is less than
   * the natural position (sticky moved the box leftward relative
   * to the row's scroll). If the row hasn't scrolled far enough
   * to trigger sticky, the two align and we're not stuck.
   *
   * Runs on scroll + window resize so the shadow tracks state
   * transitions in real time (including column-resize induced
   * overflow changes). */
  function initStickyNameShadow() {
    const scroller = document.querySelector(".table-scroll");
    if (!scroller) return;
    const update = () => {
      const nameHead = scroller.querySelector('.table__head .th--name');
      const row      = scroller.querySelector('.table__head');
      if (!nameHead || !row) {
        scroller.classList.remove("is-name-stuck");
        return;
      }
      /* Natural position of Name = row's left + row's padding-left
       * + Status width + Rate Card ID width. Compare to Name's
       * actual painted left. When sticky is actively pinning, the
       * container has scrolled far enough that Name's natural
       * position moved leftward but sticky held Name at its pin
       * offset. So painted > natural signals active pinning: Name
       * is holding content behind it and the shadow should show. */
      const rowRect  = row.getBoundingClientRect();
      const cs       = getComputedStyle(row);
      const padLeft  = parseFloat(cs.paddingLeft) || 0;
      const tableCs  = getComputedStyle(scroller.querySelector('.table'));
      const colStatus = parseFloat(tableCs.getPropertyValue('--col-status')) || 0;
      const colRcid   = parseFloat(tableCs.getPropertyValue('--col-rcid')) || 0;
      const naturalLeft = rowRect.left + padLeft + colStatus + colRcid;
      const paintedLeft = nameHead.getBoundingClientRect().left;
      /* 1px slack so sub-pixel rendering doesn't flicker the class
       * on/off at the boundary. */
      const stuck = paintedLeft > naturalLeft + 1;
      scroller.classList.toggle("is-name-stuck", stuck);
    };
    scroller.addEventListener("scroll", update, {passive: true});
    window.addEventListener("resize", update);
    /* Also re-check after any column drag: initColumnResize mutates
     * grid-template-columns via CSS custom properties, which can
     * change whether Name's natural position is left of the
     * container edge. */
    scroller.addEventListener("pointerup", () => {
      /* rAF so the DOM has settled after endDrag's cleanup. */
      requestAnimationFrame(update);
    });
    /* Run after the first table render so scrollWidth is accurate. */
    requestAnimationFrame(update);
  }

  document.addEventListener("DOMContentLoaded", () => {
    /* Hydrate persisted user-saved rows BEFORE the first table render
     * so refreshing the page keeps any "Save as Draft" / "Save Rate
     * Card" / "Save and Create New" rows pinned at the top. */
    hydrateSavedRowsFromStorage();
    /* PRD-aligned status normalization (defensive boot pass). Walks
     * every row currently in RATE_CARDS - both the in-source seed
     * and any rows just unshifted from localStorage - and coerces
     * each row.status to one of "Published" or "Draft". This is
     * idempotent (running it on already-normalized data is a no-op)
     * and protects the UI in three scenarios:
     *   1. The seed is hand-edited to a deprecated value in the
     *      future and the boot still renders the correct chip.
     *   2. A user's pre-2026-06-25 localStorage payload contains
     *      "Active" / "Pending Review" / "Archived" / "ACTIVE" / ...
     *      and is migrated to Published / Draft on the next load.
     *   3. An import flow added later inserts rows directly into
     *      RATE_CARDS without going through commitFormToTable. */
    for (var __i = 0; __i < RATE_CARDS.length; __i++) {
      RATE_CARDS[__i].status = normalizeStatus(RATE_CARDS[__i].status);
    }
    /* If the boot-time pass changed any value, write the normalized
     * shape back to localStorage so the next refresh starts clean. */
    persistSavedRowsToStorage();
    populateFilterOptions();       // Generate options from real RATE_CARDS
    /* After the options exist, so a value from the URL can be checked
     * against what the dataset actually offers before it is applied. */
    readFiltersFromUrl();
    wireDraftSelects();            // Free-text controls update draftFilters
    renderDraftIntoSelects();      // Reflect the restored draft
    wire();
    renderTable();
    initColumnResize();                // Draggable column dividers (RCM table)
    initRcCreateModal();               // Create rate card dialog (2.1)
    applyTheme(readStoredTheme()); // Restore last-selected theme from storage
    purgeStoredVersion();          // Clear any pre-2026-07-13 stored version so returning users land on latest
    applyVersion(resolveVersion()); // URL ?version= (if valid) else VERSION_LATEST; localStorage is not consulted
    /* v1.2 shortens the RCM search placeholder to "Search rate cards" at
     * narrow widths so it stays readable when the toolbar shrinks. The
     * threshold matches the first table breakpoint (<=1280). A tiny
     * requestAnimationFrame debounce prevents thrashing during native
     * window drag-resize. v1.1 short-circuits inside the sync fn. */
    var placeholderResizeTick = 0;
    window.addEventListener("resize", function () {
      if (placeholderResizeTick) cancelAnimationFrame(placeholderResizeTick);
      placeholderResizeTick = requestAnimationFrame(function () {
        placeholderResizeTick = 0;
        syncSearchPlaceholder(document.body.getAttribute("data-version") || "1.1");
      });
    });
    wireVnavHover();                   // App-shell side-nav hover behavior
    initReferenceOverlay();
    // Create Rate Card page setup
    populateEdlSelectOptions();
    wireEdlSelects();
    wireAdsCalendars();
    initDateDefaults();
    snapshotCreateFormPlaceholders();
    initDcmRuleInputFilter();
    // QA affordance: ?openFilter=1 opens the panel on load (for headless diffs).
    if (new URLSearchParams(location.search).get("openFilter") === "1") {
      openFilterPanel();
    }
    /* Sticky-action shadow: toggle .is-scrolled on .table-scroll so the
     * Action column's left-edge shadow only renders when the table is
     * actually scrolled horizontally. At >=1440 widths the table fits
     * the card and no shadow is needed; below that the table scrolls
     * and the sticky column needs the shadow to read as floating
     * above the content. Window resize also re-evaluates so toggling
     * between breakpoints updates correctly. */
    initStickyActionShadow();
    initStickyNameShadow();
    /* The action strip only takes a tab stop and a fade while it is
     * actually scrollable, and whether it is depends on the width the
     * table is showing, so it is re-read whenever that can change. */
    window.addEventListener("resize", function () {
      syncSelectionActionScroll(document.querySelector("[data-selection-bar]"));
    });
    /* Edit-mode dirty tracking: any input/change inside the Create
     * page form recomputes whether Save Changes should be enabled
     * (we only act in edit mode - create mode skips inside
     * recomputeEditDirtyState). Delegated listener handles every
     * future-rendered input automatically. selectEdlOption + the
     * date picker also call recomputeEditDirtyState directly since
     * those custom widgets don't fire standard input/change events
     * on the inputs the form actually reads. */
    var createRoot = document.querySelector('[data-page="create"]');
    if (createRoot) {
      /* Edit-mode dirty tracking AND create-mode save-button gate
       * both fire on every form input. recomputeCreateSaveState
       * is a no-op in edit mode; recomputeEditDirtyState is a no-op
       * in create mode. */
      var onCreateInput = function(){
        recomputeEditDirtyState();
        recomputeCreateSaveState();
      };
      createRoot.addEventListener('input', onCreateInput);
      createRoot.addEventListener('change', onCreateInput);
      /* Boot-time gate: Save buttons start disabled on a blank
       * form regardless of how the user arrived (Create button
       * click, URL deep-link to ?section=create, browser back/
       * forward). resetCreateForm also calls this whenever the
       * form is reset; this initial call covers first paint. */
      window.__rcCardTouched = false;
      /* Boot-time defaults for the auto-open-next-accordion flags.
       * A blank Create form starts empty, so both flags are false
       * and auto-open is armed. If the URL routes into Edit mode,
       * openEditRateCard() will overwrite these based on the
       * prefilled state (already-complete sections suppress the
       * auto-open on entry). */
      window.__rcAutoOpenedLine = false;
      window.__rcAutoOpenedPrem = false;
      recomputeCreateSaveState();
    }
    // Refresh-safe routing: if the URL has ?section=create|line|atlas,
    // restore that step. cardId is treated as a draft reference; we
    // re-hydrate window.__rcDraft so the LINE-step stepper chip can
    // still reference it. atlas is the standalone Atlas intro deck
    // (2026-06-29 brief).
    const params = new URLSearchParams(location.search);
    const section = params.get("section");
    if (section === "create" || section === "line") {
      const cardId = params.get("cardId");
      if (section === "line" && cardId) {
        window.__rcDraft = { cardId, values: (window.__rcDraft && window.__rcDraft.values) || {} };
      }
      navigateTo(section);
    } else if (section === "atlas") {
      navigateTo("atlas");
    }
    /* Convenience: bare /atlas (no query string) routes to the deck.
     * Since this is a static site without server-side rewrites, we
     * implement /atlas via a query-string convention and treat any
     * pathname ending in /atlas the same. */
    else if (/\/atlas\/?$/.test(window.location.pathname)) {
      navigateTo("atlas");
    }
    /* Default route: explicitly call navigateTo("list") so the body
     * carries data-route="list" on first paint. Without this, a hard
     * refresh on / leaves the body without any data-route attribute,
     * which still happens to render the table because the route-
     * hiding CSS only hides when data-route is explicitly NOT list,
     * but it leaves a few defensive selectors (and QA assertions)
     * without anything to read. Be explicit. */
    else {
      navigateTo("list");
    }
    initAtlasDeck();
    initAtlasMediaPlanSteps();
    initAtlasRightPrice();
    initAtlasSupermarket();
    initAtlasUpfrontScatter();
    initAtlasSameAdRate();
    initAtlasThreeQuestions();
    initAtlasConnectedWorkflows();
    initRateCardLayerExplainer();
    initPricingComplexityModals();
    initLineItemsMultiAttach();
    initPremiumMultiAttach();

    /* Brand-lockup click: navigate back to the Atlas intro deck and
     * always reset to slide 1. The anchor keeps its href fallback
     * (?section=atlas&slide=1) so a modifier-key click, middle-click,
     * or a no-JS environment still lands on slide 1. In the common
     * left-click case we intercept and do the same thing via SPA nav.
     * The 'atlas:reset' custom event is handled inside initAtlasDeck
     * so we can reach into the deck's private setSlide() without
     * exposing it globally. */
    var brandLockup = document.querySelector('.gnav__logomark[data-action="go-atlas-intro"]');
    if (brandLockup) {
      brandLockup.addEventListener('click', function(e){
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
        e.preventDefault();
        navigateTo('atlas');
        document.dispatchEvent(new CustomEvent('atlas:reset'));
      });
    }
  });

  /* =====================================================================
   *  UI STATE BRIDGE
   *
   *  Redline Mode inspects the screen the user is on inside a same-origin
   *  iframe pinned to a fixed logical viewport. That iframe boots the app
   *  from scratch, so anything held in memory rather than in the URL is
   *  missing from the copy being measured: search text, applied filters,
   *  sort, pagination, row selection, unsaved field values, accordion
   *  state and scroll offsets.
   *
   *  capture() serializes that state from the live page. restore() replays
   *  it into the freshly booted copy using the same render functions the
   *  product already uses, so the preview is a faithful reproduction
   *  rather than a second, differently-configured page.
   *
   *  Both halves are inert unless a caller opts in. restore() never
   *  persists to storage and never submits a form, which keeps the preview
   *  read-only with respect to product data.
   * ===================================================================== */

  /* Structural address of a node (child indexes from <html> down). The
   * preview boots the same markup at the same route, so index paths
   * resolve reliably and, unlike ids, also cover the many controls that
   * carry no id or name. */
  function bridgePath(node) {
    if (!node || node.nodeType !== 1) return "";
    const parts = [];
    let current = node;
    while (current && current !== document.documentElement) {
      const parent = current.parentElement;
      if (!parent) return "";
      parts.push(Array.prototype.indexOf.call(parent.children, current));
      current = parent;
    }
    return parts.reverse().join(".");
  }

  function bridgeNode(path) {
    if (!path && path !== 0) return null;
    let node = document.documentElement;
    const parts = String(path).split(".");
    for (let i = 0; i < parts.length && node; i += 1) {
      node = node.children[Number(parts[i])];
    }
    return node || null;
  }

  function bridgeSkip(node) {
    return Boolean(node.closest("[data-redline-ui]"));
  }

  function bridgeCaptureControls() {
    const controls = [];
    document.querySelectorAll("input, select, textarea").forEach((control) => {
      if (bridgeSkip(control)) return;
      // File inputs cannot be assigned; password fields are never copied.
      if (control.type === "file" || control.type === "password") return;
      const path = bridgePath(control);
      if (!path) return;
      controls.push({
        path,
        tag: control.tagName,
        type: control.type || "",
        value: control.value,
        checked: Boolean(control.checked),
      });
    });
    return controls;
  }

  function bridgeRestoreControls(controls) {
    (controls || []).forEach((entry) => {
      const control = bridgeNode(entry.path);
      if (!control || control.tagName !== entry.tag) return;
      if ((control.type || "") !== entry.type) return;
      if (control.type === "checkbox" || control.type === "radio") {
        control.checked = entry.checked;
        return;
      }
      control.value = entry.value;
      // ADS dropdowns render their label separately from the native
      // <select> that backs them, so the presentation needs a nudge.
      if (control.tagName === "SELECT" && typeof window.syncAdsDropdown === "function") {
        try { window.syncAdsDropdown(control); } catch (_) {}
      }
    });
  }

  /* Custom EDL listbox widgets keep their value on the wrapper rather than
   * in a form control, so they are captured and repainted separately. */
  function bridgeCaptureSelects() {
    const selects = [];
    document.querySelectorAll(".edl-select[data-value]").forEach((widget) => {
      if (bridgeSkip(widget)) return;
      const path = bridgePath(widget);
      if (!path) return;
      selects.push({ path, value: widget.getAttribute("data-value") || "" });
    });
    return selects;
  }

  function bridgeRestoreSelects(selects) {
    (selects || []).forEach((entry) => {
      const widget = bridgeNode(entry.path);
      if (!widget || !widget.classList || !widget.classList.contains("edl-select")) return;
      if ((widget.getAttribute("data-value") || "") === entry.value) return;
      widget.setAttribute("data-value", entry.value);
      const option = entry.value
        ? widget.querySelector('.edl-select__option[data-value="' + CSS.escape(entry.value) + '"]')
        : null;
      const valueEl = widget.querySelector(".edl-select__value");
      if (valueEl) {
        if (entry.value) {
          valueEl.textContent = option ? option.textContent.trim() : entry.value;
          valueEl.classList.remove("edl-select__value--placeholder");
        } else {
          valueEl.classList.add("edl-select__value--placeholder");
          const placeholder = valueEl.getAttribute("data-placeholder-text");
          if (placeholder) valueEl.textContent = placeholder;
        }
      }
      widget.querySelectorAll(".edl-select__option").forEach((opt) => {
        const selected = opt.getAttribute("data-value") === entry.value;
        opt.classList.toggle("is-selected", selected);
        opt.setAttribute("aria-selected", selected ? "true" : "false");
      });
    });
  }

  function bridgeCaptureAccordions() {
    const sections = [];
    document.querySelectorAll("[data-accordion]").forEach((node) => {
      sections.push({
        key: node.getAttribute("data-accordion"),
        open: node.classList.contains("is-open"),
      });
    });
    return sections;
  }

  /* Replayed through the product's own toggle handler so the header
   * chevron, aria-expanded and validation status stay consistent. */
  function bridgeRestoreAccordions(sections) {
    (sections || []).forEach((entry) => {
      const node = document.querySelector('[data-accordion="' + CSS.escape(entry.key) + '"]');
      if (!node) return;
      if (node.classList.contains("is-open") === Boolean(entry.open)) return;
      const header = node.querySelector('[data-action="toggle-accordion"]');
      if (header) header.click();
    });
  }

  function bridgeCaptureScroll() {
    const nodes = [];
    document.querySelectorAll("*").forEach((node) => {
      if (!node.scrollTop && !node.scrollLeft) return;
      if (bridgeSkip(node)) return;
      const path = bridgePath(node);
      if (!path) return;
      nodes.push({ path, top: node.scrollTop, left: node.scrollLeft });
    });
    return {
      x: window.scrollX,
      y: window.scrollY,
      nodes,
    };
  }

  function bridgeRestoreScroll(scroll) {
    if (!scroll) return;
    (scroll.nodes || []).forEach((entry) => {
      const node = bridgeNode(entry.path);
      if (!node) return;
      node.scrollTop = entry.top;
      node.scrollLeft = entry.left;
    });
    window.scrollTo(scroll.x || 0, scroll.y || 0);
  }

  /* =====================================================================
   *  REDLINE OVERLAY GALLERY REGISTRY
   *
   *  Backs the Overlays section of Redline Mode. Every entry drives the
   *  real product overlay: the same markup, the same open/close functions
   *  and the same copy the application ships. Nothing here is a replica,
   *  a screenshot or a simplified stand-in, so what a designer measures in
   *  the gallery is exactly what ships.
   *
   *  The registry only ever runs inside the Redline preview, which is an
   *  isolated same-origin copy of the app. While a gallery entry is open,
   *  installMutationGuard() blocks the confirm actions that would write
   *  data, so inspecting a destructive dialog cannot delete anything.
   *
   *  To add an overlay see docs/redline-overlay-gallery.md.
   * ===================================================================== */

  // Confirm actions that would write product data. Blocked for as long as
  // a gallery entry is on screen.
  var GALLERY_BLOCKED_ACTIONS = [
    "confirm-delete",
    "save-quick-edit",
    "qe-discard-changes",
    "apply-filters",
    "clear-filters",
    "reset-all",
    "download-template",
    "upload-template",
  ];
  var GALLERY_BLOCKED_V2_ACTIONS = [
    "confirm-remove-line",
    "save-card",
    "save-draft",
    "submit-line",
    "submit-premium",
  ];
  var galleryActiveId = "";
  var galleryGuard = null;
  var galleryEntryUrl = "";

  function installGalleryGuard() {
    if (galleryGuard) return;
    galleryGuard = function (event) {
      var target = event.target instanceof Element ? event.target : null;
      if (!target) return;
      var control = target.closest("[data-action], [data-v2-action]");
      if (!control) return;
      var action = control.getAttribute("data-action");
      var v2Action = control.getAttribute("data-v2-action");
      var blocked = (action && GALLERY_BLOCKED_ACTIONS.indexOf(action) >= 0)
        || (v2Action && GALLERY_BLOCKED_V2_ACTIONS.indexOf(v2Action) >= 0);
      if (!blocked) return;
      event.preventDefault();
      event.stopImmediatePropagation();
    };
    document.addEventListener("click", galleryGuard, true);
    document.addEventListener("submit", galleryGuard, true);
  }

  function removeGalleryGuard() {
    if (!galleryGuard) return;
    document.removeEventListener("click", galleryGuard, true);
    document.removeEventListener("submit", galleryGuard, true);
    galleryGuard = null;
  }

  function galleryClick(selector) {
    var control = document.querySelector(selector);
    if (control) control.click();
    return Boolean(control);
  }

  function galleryClearToasts() {
    var stack = document.querySelector("[data-toast-stack]");
    if (!stack) return;
    Array.prototype.slice.call(stack.querySelectorAll("[data-toast]")).forEach(function (node) {
      if (node.__timer) {
        clearTimeout(node.__timer);
        node.__timer = null;
      }
      node.remove();
    });
  }

  /* Quick Edit's real close runs a 220ms slide-out and finishes the teardown
   * on transitionend (with a 280ms fallback). Between gallery entries that
   * pending work would land after the next entry has already reopened the
   * sheet and hide it again, so the gallery closes it in one synchronous
   * step instead. Everything the animated path does is done here too. */
  function galleryForceCloseQuickEdit() {
    var sheet = document.querySelector("[data-quick-edit]");
    if (!sheet || sheet.hidden) return;
    sheet.classList.remove("is-open");
    sheet.hidden = true;
    sheet.setAttribute("aria-hidden", "true");
    document.body.classList.remove("qe-open");
  }

  /* Dismisses whatever the previous entry left on screen using each
   * overlay's real close path, so focus, inert backgrounds and body
   * classes unwind exactly as they do in the product. */
  function galleryCloseOverlays() {
    galleryClearToasts();
    galleryForceCloseQuickEdit();
    var discard = document.querySelector("[data-qe-discard]");
    if (discard && !discard.hidden) galleryClick('[data-action="qe-keep-editing"]');
    try { closeDeleteModal(); } catch (_) {}
    var removeModal = document.querySelector("[data-v2-remove-modal]");
    if (removeModal && !removeModal.hidden) {
      galleryClick('[data-v2-action="cancel-remove-line"]');
    }
    if (isFilterPanelOpen()) {
      try { closeFilterPanel(); } catch (_) {}
    }
  }

  var GALLERY_SURFACES = "[data-modal], [data-qe-discard], [data-quick-edit], "
    + "[data-v2-remove-modal], #filter-panel";

  /* Staging an entry can change route, and the screen a route change lands on
   * focuses its own primary action a frame later. Put focus back inside the
   * overlay once that has settled so it stays keyboard reachable, the same as
   * it is when a user opens it themselves. */
  function galleryFocusOverlay() {
    /* One pass is not enough. A route change lands its own focus a frame
     * or two after the overlay opens, and an overlay that manages focus
     * itself adds another. Re-asserting over the next few frames means
     * whichever settles last, focus still finishes inside the surface,
     * and each pass is a no-op once it already is. */
    var attempts = 0;
    function assert() {
      /* A drawer that is closed still measures its full width, because it
       * is parked off screen by a transform rather than by being resized.
       * Width alone would therefore pick a closed drawer and focus into
       * something nobody can see, so visibility is part of the test. */
      var surface = Array.prototype.slice
        .call(document.querySelectorAll(GALLERY_SURFACES))
        .find(function (node) {
          if (node.hidden) return false;
          if (node.getBoundingClientRect().width <= 4) return false;
          return window.getComputedStyle(node).visibility !== "hidden";
        });
      if (surface && !surface.contains(document.activeElement)) {
        var focusable = surface.querySelector(
          'button:not([disabled]), [href], input:not([disabled]), '
          + 'select:not([disabled]), textarea:not([disabled]), [tabindex="-1"]'
        );
        var target = focusable || (surface.hasAttribute("tabindex") ? surface : null);
        if (target) target.focus({ preventScroll: true });
      }
      attempts += 1;
      if (attempts < 4) window.setTimeout(assert, 60);
    }
    window.requestAnimationFrame(assert);
  }

  function galleryRoute(route) {
    if (document.body.getAttribute("data-route") === route) return;
    navigateTo(route);
  }

  /* The v2 wizard reads its record from the URL, so reaching an overlay that
   * only exists on a populated Edit Rate Card page means deep linking to one
   * first. Only the preview's URL changes, and close() puts it back. */
  function galleryEditWizard() {
    var row = galleryRow(function (item) { return Boolean(item.rateCardId); });
    if (!row) return false;
    try {
      var url = new URL(window.location.href);
      url.searchParams.set("section", "create");
      url.searchParams.set("mode", "edit");
      url.searchParams.set("cardId", row.rateCardId);
      window.history.replaceState(null, "", url.toString());
    } catch (_) {
      return false;
    }
    navigateTo("create");
    if (document.body.getAttribute("data-route") !== "create") return false;
    // The wizard loads its record from the route observer, which runs a tick
    // later. Load it now so the line item table exists to select from.
    var bridge = window.RateCardV2StateBridge;
    if (bridge && typeof bridge.ensureContext === "function") bridge.ensureContext();
    return true;
  }

  function galleryOpenRemoveLine() {
    if (!galleryEditWizard()) return false;
    // The Remove Line Item action only exists once a row is selected.
    var row = document.querySelector('[data-v2-row-type="lines"][data-v2-row-id]');
    if (!row) return false;
    row.click();
    var trigger = document.querySelector('[data-v2-action="request-remove-line"]');
    if (!trigger || trigger.hidden) return false;
    trigger.click();
    var modal = document.querySelector("[data-v2-remove-modal]");
    return Boolean(modal && !modal.hidden);
  }

  function galleryRows() {
    try {
      return activeRateCards() || [];
    } catch (_) {
      return [];
    }
  }

  function galleryRow(matcher) {
    var rows = galleryRows();
    var found = matcher ? rows.find(matcher) : null;
    return found || rows[0] || null;
  }

  function galleryLongNameRow() {
    return galleryRows().slice().sort(function (a, b) {
      return String(b.name || "").length - String(a.name || "").length;
    })[0] || null;
  }

  // Quick Edit is only worth inspecting on a card that actually has LINE
  // rows, so the grid renders with representative content.
  function galleryQuickEditRow() {
    var rows = galleryRows();
    for (var index = 0; index < rows.length; index += 1) {
      try {
        var lines = getQuickEditLines(rows[index]);
        if (lines && lines.length) return rows[index];
      } catch (_) {}
    }
    return rows[0] || null;
  }

  function galleryOpenQuickEdit() {
    galleryRoute("list");
    var row = galleryQuickEditRow();
    if (!row) return false;
    openQuickEdit(row.id);
    return true;
  }

  function gallerySetBaseRate(value) {
    var input = document.querySelector('[data-qe-row-idx="0"] [data-qe-field="baseRate"]');
    if (!input) return false;
    input.value = value;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
    input.dispatchEvent(new Event("blur", { bubbles: true }));
    return true;
  }

  /* Toast entries call the production toast() with the exact copy their
   * flow ships, and with duration 0 so auto-dismiss is frozen for as long
   * as the designer needs. */
  function galleryToast(config) {
    galleryClearToasts();
    var payload = Object.assign({ duration: 0 }, config);
    toast(payload);
    return true;
  }

  function galleryToastStack(configs) {
    galleryClearToasts();
    // Rendered oldest first because toast() prepends, which keeps the
    // stack order identical to a real sequence of events.
    configs.forEach(function (config) {
      toast(Object.assign({ duration: 0 }, config));
    });
    return true;
  }

  var IMPORT_SUMMARY_CLEAN = "24 rows imported.";
  var IMPORT_SUMMARY_CORRECTIONS = "22 rows imported. 2 rows need correction. "
    + "Row 14: attach the LINE to a valid CARD and complete its advertiser, "
    + "inventory, rate, and currency fields. "
    + "Row 27: ROW_TYPE must be CARD, LINE, or PREM.";
  var IMPORT_SUMMARY_LONG = "18 rows imported. 6 rows need correction. "
    + "Row 9: complete the required CARD fields and use valid enum, date, and "
    + "integer values. "
    + "Row 14: RATE_CARD_ID must be unique within the CSV. "
    + "Row 27: attach the PREM to valid rows and use an approved calculation "
    + "method, numeric value, and valid dates.";

  var GALLERY_MODALS = [
    {
      id: "modal.delete.default",
      group: "Delete",
      name: "Delete rate card",
      stateName: "Confirmation",
      description: "Destructive confirmation opened from the list row Delete action.",
      route: "list",
      source: "index.html [data-modal], app.js openDeleteModal()",
      ads: "Modal (ADS Modal, ADS Primary confirm)",
      open: function () {
        galleryRoute("list");
        var row = galleryRow();
        if (!row) return false;
        openDeleteModal(row.id);
        return true;
      },
    },
    {
      id: "modal.delete.long-name",
      group: "Delete",
      name: "Delete rate card",
      stateName: "Long rate card name",
      description: "Summary row stress state using the longest rate card name in the catalog.",
      route: "list",
      source: "index.html [data-modal], app.js openDeleteModal()",
      ads: "Modal (ADS Modal, ADS Primary confirm)",
      open: function () {
        galleryRoute("list");
        var row = galleryLongNameRow();
        if (!row) return false;
        openDeleteModal(row.id);
        return true;
      },
    },
    {
      id: "modal.quick-edit.default",
      group: "Quick edit",
      name: "Quick edit",
      stateName: "Loaded line rows",
      description: "Bottom sheet as it opens, with Save disabled until a value changes.",
      route: "list",
      source: "index.html [data-quick-edit], app.js openQuickEdit()",
      ads: "Sheet (ADS Sheet with SheetHeader and SheetFooter)",
      open: galleryOpenQuickEdit,
    },
    {
      id: "modal.quick-edit.dirty",
      group: "Quick edit",
      name: "Quick edit",
      stateName: "Edited, Save enabled",
      description: "A base rate has been changed, so the primary action becomes available.",
      route: "list",
      source: "index.html [data-quick-edit], app.js updateQuickEditSaveState()",
      ads: "Sheet (ADS Sheet, primary action enabled)",
      open: function () {
        if (!galleryOpenQuickEdit()) return false;
        gallerySetBaseRate("42.75");
        return true;
      },
    },
    {
      id: "modal.quick-edit.invalid",
      group: "Quick edit",
      name: "Quick edit",
      stateName: "Invalid base rate",
      description: "Base rate that fails validation, the state Save reports on.",
      route: "list",
      source: "index.html [data-quick-edit], app.js saveQuickEdit()",
      ads: "Sheet (ADS Sheet, ADS Text Field error state)",
      open: function () {
        if (!galleryOpenQuickEdit()) return false;
        gallerySetBaseRate("not a rate");
        return true;
      },
    },
    {
      id: "modal.quick-edit.discard",
      group: "Quick edit",
      name: "Discard quick edit changes",
      stateName: "Confirmation",
      description: "Unsaved changes confirmation raised when Quick Edit is closed while dirty.",
      route: "list",
      source: "index.html [data-qe-discard], app.js closeQuickEdit()",
      ads: "Modal (ADS Modal, ADS Primary confirm)",
      open: function () {
        if (!galleryOpenQuickEdit()) return false;
        gallerySetBaseRate("42.75");
        closeQuickEdit(false);
        return true;
      },
    },
    {
      id: "modal.remove-line.default",
      group: "Line items",
      name: "Remove line item",
      stateName: "Confirmation",
      description: "Destructive confirmation from the Edit Rate Card line item form.",
      route: "create",
      source: "index.html [data-v2-remove-modal], v2.js openRemoveLineModal()",
      ads: "Modal (ADS Modal, ADS Primary confirm)",
      open: galleryOpenRemoveLine,
    },
    {
      id: "modal.remove-line.submitting",
      group: "Line items",
      name: "Remove line item",
      stateName: "Submitting",
      description: "Busy state while the removal is applied, with the confirm action disabled.",
      route: "create",
      source: "v2.js confirmRemoveLine() busy state",
      ads: "Modal (ADS Modal, ADS Button loading state)",
      open: function () {
        if (!galleryOpenRemoveLine()) return false;
        // Mirrors the busy state v2.js applies while the removal runs.
        var modal = document.querySelector("[data-v2-remove-modal]");
        modal.setAttribute("aria-busy", "true");
        var confirm = modal.querySelector('[data-v2-action="confirm-remove-line"]');
        if (confirm) {
          confirm.disabled = true;
          confirm.setAttribute("aria-disabled", "true");
        }
        return true;
      },
    },
    {
      id: "modal.filters.default",
      group: "Filters",
      name: "Filters",
      stateName: "No filters applied",
      description: "Filter panel in its reset state, opened from the list toolbar.",
      route: "list",
      source: "index.html #filter-panel, app.js openFilterPanel()",
      ads: "Sheet (ADS side panel, role dialog)",
      open: function () {
        galleryRoute("list");
        openFilterPanel();
        return true;
      },
    },
    {
      id: "modal.filters.applied",
      group: "Filters",
      name: "Filters",
      stateName: "Marketplace selected",
      description: "Filter panel with a marketplace choice staged in the draft state.",
      route: "list",
      source: "index.html #filter-panel, app.js renderDraftIntoSelects()",
      ads: "Sheet (ADS side panel with ADS Checkbox group)",
      open: function () {
        galleryRoute("list");
        openFilterPanel();
        /* Array, not a string: marketplace holds a set of choices now. */
        draftFilters = Object.assign(cloneFilters(draftFilters), { marketplace: ["Upfront"] });
        renderDraftIntoSelects();
        return true;
      },
    },
  ];

  /* Deliberately not registered: the Cmd+P rate card explainer
   * ([data-rcle]) and the pricing complexity dialog (#wpc-modal). Both are
   * presentation surfaces that explain the product to an audience rather
   * than parts of the product a user works in, so they are not product
   * pages a designer redlines. They remain fully functional in the app. */

  var GALLERY_TOASTS = [
    {
      id: "toast.create.created",
      group: "Create and edit",
      name: "Rate card created",
      variant: "success",
      route: "create",
      source: "app.js save-publish handler",
      config: { message: "Rate card created.", variant: "success" },
    },
    {
      id: "toast.create.saved",
      group: "Create and edit",
      name: "Rate card saved",
      variant: "success",
      route: "create",
      source: "app.js save-publish handler",
      config: { message: "Rate card saved.", variant: "success" },
    },
    {
      id: "toast.create.draft-saved",
      group: "Create and edit",
      name: "Draft saved",
      variant: "success",
      route: "create",
      source: "app.js save-draft handler",
      config: { message: "Draft saved.", variant: "success" },
    },
    {
      id: "toast.create.save-failed",
      group: "Create and edit",
      name: "Unable to save rate card",
      stateName: "Message only",
      variant: "error",
      route: "create",
      source: "app.js save-publish catch",
      config: { message: "Unable to save rate card.", variant: "error" },
    },
    {
      id: "toast.create.save-failed-detailed",
      group: "Create and edit",
      name: "Unable to save rate card",
      stateName: "Title and supporting message",
      variant: "error",
      route: "create",
      source: "v2.js persistFile() catch",
      config: { title: "Unable to save rate card", message: "Try again.", variant: "error" },
    },
    {
      id: "toast.create.required-fields",
      group: "Create and edit",
      name: "Complete required fields",
      variant: "warning",
      route: "list",
      source: "app.js saveQuickEdit() validation",
      config: { message: "Complete required fields before continuing.", variant: "warning" },
    },
    {
      id: "toast.v2.card-saved",
      group: "Create and edit",
      name: "Rate card saved",
      stateName: "Title only",
      variant: "info",
      route: "create",
      source: "v2.js showOperationToast()",
      config: { title: "Rate card saved", message: "", variant: "info" },
    },
    {
      id: "toast.v2.card-draft",
      group: "Create and edit",
      name: "Rate card saved as draft",
      stateName: "Title only",
      variant: "info",
      route: "create",
      source: "v2.js showOperationToast()",
      config: { title: "Rate card saved as draft", message: "", variant: "info" },
    },
    {
      id: "toast.v2.line-added",
      group: "Line items and premiums",
      name: "Line item added",
      variant: "info",
      route: "create",
      source: "v2.js submitItem()",
      config: { title: "Line item added", message: "", variant: "info" },
    },
    {
      id: "toast.v2.line-updated",
      group: "Line items and premiums",
      name: "Line item updated",
      variant: "info",
      route: "create",
      source: "v2.js submitItem()",
      config: { title: "Line item updated", message: "", variant: "info" },
    },
    {
      id: "toast.v2.line-removed",
      group: "Line items and premiums",
      name: "Line item removed",
      variant: "info",
      route: "create",
      source: "v2.js removeRow()",
      config: { title: "Line item removed", message: "", variant: "info" },
    },
    {
      id: "toast.v2.premium-added",
      group: "Line items and premiums",
      name: "Premium adjustment added",
      variant: "info",
      route: "create",
      source: "v2.js submitItem()",
      config: { title: "Premium adjustment added", message: "", variant: "info" },
    },
    {
      id: "toast.v2.premium-updated",
      group: "Line items and premiums",
      name: "Premium adjustment updated",
      variant: "info",
      route: "create",
      source: "v2.js submitItem()",
      config: { title: "Premium adjustment updated", message: "", variant: "info" },
    },
    {
      id: "toast.v2.premium-removed",
      group: "Line items and premiums",
      name: "Premium adjustment removed",
      variant: "info",
      route: "create",
      source: "v2.js removeRow()",
      config: { title: "Premium adjustment removed", message: "", variant: "info" },
    },
    {
      id: "toast.attach.line-duplicate",
      group: "Line items and premiums",
      name: "Line item already attached",
      variant: "info",
      route: "create",
      source: "app.js initLineItemsMultiAttach()",
      config: { message: "This line item is already attached.", variant: "info" },
    },
    {
      id: "toast.attach.premium-duplicate",
      group: "Line items and premiums",
      name: "Premium adjustment already attached",
      variant: "info",
      route: "create",
      source: "app.js initPremiumMultiAttach()",
      config: { message: "This premium adjustment is already attached.", variant: "info" },
    },
    {
      id: "toast.import.complete",
      group: "Upload and import",
      name: "Rate card import complete",
      variant: "success",
      source: "app.js importRateCardCsv()",
      config: {
        title: "Rate card import complete",
        message: IMPORT_SUMMARY_CLEAN,
        variant: "success",
      },
    },
    {
      id: "toast.import.corrections",
      group: "Upload and import",
      name: "Rate card imported with corrections needed",
      stateName: "Partial import",
      variant: "warning",
      source: "app.js importRateCardCsv()",
      config: {
        title: "Rate card imported with corrections needed",
        message: IMPORT_SUMMARY_CORRECTIONS,
        variant: "warning",
      },
    },
    {
      id: "toast.import.corrections-long",
      group: "Upload and import",
      name: "Rate card imported with corrections needed",
      stateName: "Long validation summary",
      variant: "warning",
      source: "app.js importRateCardCsv()",
      config: {
        title: "Rate card imported with corrections needed",
        message: IMPORT_SUMMARY_LONG,
        variant: "warning",
      },
    },
    {
      id: "toast.import.file-type",
      group: "Upload and import",
      name: "Unable to import rate card",
      stateName: "Unsupported file type",
      variant: "error",
      source: "app.js importRateCardCsv()",
      config: {
        title: "Unable to import rate card",
        message: "Choose a CSV file.",
        variant: "error",
      },
    },
    {
      id: "toast.import.file-size",
      group: "Upload and import",
      name: "Unable to import rate card",
      stateName: "File too large",
      variant: "error",
      source: "app.js importRateCardCsv()",
      config: {
        title: "Unable to import rate card",
        message: "Choose a CSV smaller than 5 MB.",
        variant: "error",
      },
    },
    {
      id: "toast.import.unreadable",
      group: "Upload and import",
      name: "Unable to import rate card",
      stateName: "File could not be read",
      variant: "error",
      source: "app.js importRateCardCsv()",
      config: {
        title: "Unable to import rate card",
        message: "The selected file could not be read.",
        variant: "error",
      },
    },
    {
      id: "toast.import.missing-columns",
      group: "Upload and import",
      name: "Unable to import rate card",
      stateName: "Missing required columns",
      variant: "error",
      source: "app.js importRateCardCsv()",
      config: {
        title: "Unable to import rate card",
        message: "Missing required columns: MARKETPLACE, DEAL_SEASON.",
        variant: "error",
      },
    },
    {
      id: "toast.import.generic",
      group: "Upload and import",
      name: "Unable to import rate card",
      stateName: "Generic failure",
      variant: "error",
      source: "app.js importRateCardCsv()",
      config: {
        title: "Unable to import rate card",
        message: "Check the CSV and try again.",
        variant: "error",
      },
    },
    {
      id: "toast.export.template",
      group: "Download and export",
      name: "Blank template downloaded",
      variant: "success",
      source: "app.js downloadBlankTemplate()",
      config: { message: "Blank template downloaded.", variant: "success" },
    },
    {
      id: "toast.export.exported",
      group: "Download and export",
      name: "Rate card exported",
      variant: "success",
      source: "app.js exportRateCard()",
      config: { message: "Rate card exported.", variant: "success" },
    },
    {
      id: "toast.export.failed",
      group: "Download and export",
      name: "Unable to export rate card",
      variant: "error",
      source: "app.js exportRateCard()",
      config: {
        title: "Unable to export rate card",
        message: "Try again.",
        variant: "error",
      },
    },
    {
      id: "toast.archive.archived",
      group: "Archive and delete",
      name: "Rate card archived",
      variant: "success",
      source: "app.js archiveRateCard()",
      config: { message: "Rate card archived.", variant: "success" },
    },
    {
      id: "toast.archive.failed",
      group: "Archive and delete",
      name: "Unable to archive rate card",
      variant: "error",
      source: "app.js archiveRateCard()",
      config: {
        title: "Unable to archive rate card",
        message: "Try again.",
        variant: "error",
      },
    },
    {
      id: "toast.delete.deleted",
      group: "Archive and delete",
      name: "Rate card deleted",
      variant: "success",
      source: "app.js confirmDelete()",
      config: { message: "Rate card deleted.", variant: "success" },
    },
    {
      id: "toast.duplicate.duplicated",
      group: "Duplicate",
      name: "Rate card duplicated",
      variant: "success",
      source: "app.js duplicateRateCard()",
      config: { message: "Rate card duplicated.", variant: "success" },
    },
    {
      id: "toast.duplicate.failed",
      group: "Duplicate",
      name: "Unable to duplicate rate card",
      variant: "error",
      source: "app.js duplicateRateCard()",
      config: {
        title: "Unable to duplicate rate card",
        message: "Try again.",
        variant: "error",
      },
    },
    {
      id: "toast.system.version",
      group: "Application chrome",
      name: "Version changed",
      variant: "info",
      source: "app.js version submenu handler",
      config: { message: "Version 2.0", variant: "info" },
    },
    {
      id: "toast.system.theme",
      group: "Application chrome",
      name: "Theme changed",
      variant: "info",
      source: "app.js theme submenu handler",
      config: { message: "Theme: Ad Design System", variant: "info" },
    },
    {
      id: "toast.system.logout",
      group: "Application chrome",
      name: "Logging out",
      variant: "info",
      source: "app.js log out handler",
      config: { message: "Logging out.", variant: "info" },
    },
    {
      id: "toast.stack.two-success",
      group: "Stacks",
      name: "Two success toasts",
      stateName: "Stack of 2",
      variant: "success",
      source: "app.js toast() stack container",
      stack: [
        { message: "Rate card duplicated.", variant: "success" },
        { message: "Rate card created.", variant: "success" },
      ],
    },
    {
      id: "toast.stack.success-warning",
      group: "Stacks",
      name: "Success and warning",
      stateName: "Stack of 2",
      variant: "warning",
      source: "app.js toast() stack container",
      stack: [
        { message: "Rate card created.", variant: "success" },
        {
          title: "Rate card imported with corrections needed",
          message: IMPORT_SUMMARY_CORRECTIONS,
          variant: "warning",
        },
      ],
    },
    {
      id: "toast.stack.warning-error",
      group: "Stacks",
      name: "Warning and error",
      stateName: "Stack of 2",
      variant: "error",
      source: "app.js toast() stack container",
      stack: [
        { message: "Complete required fields before continuing.", variant: "warning" },
        {
          title: "Unable to import rate card",
          message: "Choose a CSV smaller than 5 MB.",
          variant: "error",
        },
      ],
    },
    {
      id: "toast.stack.mixed",
      group: "Stacks",
      name: "Mixed status stack",
      stateName: "Stack of 4",
      variant: "info",
      source: "app.js toast() stack container",
      stack: [
        { message: "Blank template downloaded.", variant: "success" },
        { message: "Rate card archived.", variant: "success" },
        { message: "Complete required fields before continuing.", variant: "warning" },
        {
          title: "Unable to export rate card",
          message: "Try again.",
          variant: "error",
        },
      ],
    },
    {
      id: "toast.stack.long-content",
      group: "Stacks",
      name: "Long content stack",
      stateName: "Stack of 2",
      variant: "warning",
      source: "app.js toast() stack container",
      stack: [
        {
          title: "Rate card imported with corrections needed",
          message: IMPORT_SUMMARY_LONG,
          variant: "warning",
        },
        {
          title: "Unable to import rate card",
          message: "Missing required columns: MARKETPLACE, DEAL_SEASON, EFFECTIVE_START_DATE.",
          variant: "error",
        },
      ],
    },
  ];

  function galleryMeta(entry, kind) {
    return {
      id: entry.id,
      kind: kind,
      group: entry.group,
      name: entry.name,
      stateName: entry.stateName || "",
      description: entry.description || "",
      variant: entry.variant || "",
      route: entry.route || "",
      source: entry.source || "",
      ads: entry.ads || "",
    };
  }

  function galleryEntryById(id) {
    var found = GALLERY_MODALS.find(function (entry) { return entry.id === id; });
    if (found) return { entry: found, kind: "modal" };
    found = GALLERY_TOASTS.find(function (entry) { return entry.id === id; });
    return found ? { entry: found, kind: "toast" } : null;
  }

  window.RateCardOverlayGallery = {
    version: 1,

    entries: function (kind) {
      if (kind === "toast") {
        return GALLERY_TOASTS.map(function (entry) { return galleryMeta(entry, "toast"); });
      }
      if (kind === "modal") {
        return GALLERY_MODALS.map(function (entry) { return galleryMeta(entry, "modal"); });
      }
      return GALLERY_MODALS.map(function (entry) { return galleryMeta(entry, "modal"); })
        .concat(GALLERY_TOASTS.map(function (entry) { return galleryMeta(entry, "toast"); }));
    },

    activeId: function () {
      return galleryActiveId;
    },

    open: function (id) {
      var match = galleryEntryById(id);
      if (!match) return false;
      // Remembered on the first open so close() can undo any deep link an
      // entry needed to reach its overlay.
      if (!galleryEntryUrl) galleryEntryUrl = window.location.href;
      galleryCloseOverlays();
      installGalleryGuard();
      galleryActiveId = id;
      try {
        if (match.kind === "toast") {
          // Toasts stack against the page they were raised from, so each
          // one is staged over the screen its flow actually runs on.
          galleryRoute(match.entry.route || "list");
          return match.entry.stack
            ? galleryToastStack(match.entry.stack)
            : galleryToast(match.entry.config);
        }
        var opened = Boolean(match.entry.open());
        if (opened) galleryFocusOverlay();
        return opened;
      } catch (_) {
        galleryActiveId = "";
        return false;
      }
    },

    close: function () {
      galleryCloseOverlays();
      removeGalleryGuard();
      galleryActiveId = "";
      if (galleryEntryUrl) {
        try {
          window.history.replaceState(null, "", galleryEntryUrl);
        } catch (_) {}
        galleryEntryUrl = "";
      }
      return true;
    },
  };

  /* ===================================================================
   *  COMPONENT SPECIMENS  (Redline Mode)
   *
   *  The overlay gallery above stages transient surfaces: a modal or a
   *  toast that appears over whatever screen raised it. A component
   *  specimen is a different thing. It stages a piece of the product's
   *  own furniture in place, so it can be measured where it actually
   *  lives rather than in a mock of it.
   *
   *  The Action Bar specimen is the list page with everything that is
   *  not the table quieted down (see body[data-specimen] in styles.css)
   *  and a selection size applied to it. The bar on screen is the
   *  production bar, in the production table, at the production width.
   *  Nothing is copied, so nothing can drift.
   *
   *  Selection sizes up to a page of rows select real rows, so the bar
   *  is read against genuinely selected records. Larger sizes stand in
   *  a count on top of that, which is honest: selection survives paging
   *  in this product, so "1,250 items selected" over a page of ten is a
   *  state a user can really reach.
   *
   *  Reading a row is not writing one, and every press inside the
   *  specimen stops at the guard in ensureSelectionActionBar(), so an
   *  inspection session cannot edit, copy, export, archive, or delete.
   * =================================================================== */
  var SPECIMEN_ACTION_BAR = [
    {
      id: "component.action-bar.1",
      count: 1,
      stateName: "1 item selected",
      description: "Singular count. Quick Edit is the only action that "
        + "works on one record, so this is the one state where it is "
        + "available.",
    },
    {
      id: "component.action-bar.2",
      count: 2,
      stateName: "2 items selected",
      description: "Plural count, and the smallest selection that "
        + "disables Quick Edit.",
    },
    {
      id: "component.action-bar.5",
      count: 5,
      stateName: "5 items selected",
      description: "Five records, the reference multi-selection.",
    },
    {
      id: "component.action-bar.page",
      count: 10,
      stateName: "10 items selected",
      description: "A full page of rows at the default page size, "
        + "selected at once.",
    },
    {
      id: "component.action-bar.large",
      count: 1250,
      stateName: "1,250 items selected",
      description: "A four figure count against a page of ten rows, the "
        + "widest the count sentence gets. Selection survives paging, so "
        + "the bar has to hold a total larger than the page it sits on.",
    },
  ];

  var specimenActiveId = "";
  var specimenEntryUrl = "";

  function specimenMeta(entry) {
    return {
      id: entry.id,
      kind: "action-bar",
      group: "Table",
      name: "Action Bar",
      stateName: entry.stateName,
      description: entry.description || "",
      variant: "",
      route: "list",
      source: "app.js createSelectionActionBar()",
      ads: "Figma 603:11843",
    };
  }

  /* Select the first `count` rows on the page. Selection is read state,
   * so this is the same thing a designer clicking those rows would do. */
  function specimenSelectRows(count) {
    selectedRateCardIds.clear();
    var rows = document.querySelectorAll("[data-rows] .row");
    for (var i = 0; i < rows.length && i < count; i += 1) {
      var id = rows[i].getAttribute("data-row-id");
      if (id) selectedRateCardIds.add(id);
    }
    paintRowSelection();
  }

  window.RateCardComponentGallery = {
    version: 1,

    entries: function () {
      return SPECIMEN_ACTION_BAR.map(specimenMeta);
    },

    activeId: function () {
      return specimenActiveId;
    },

    open: function (id) {
      var entry = SPECIMEN_ACTION_BAR.find(function (item) {
        return item.id === id;
      });
      if (!entry) return false;
      if (!specimenEntryUrl) specimenEntryUrl = window.location.href;
      try {
        galleryCloseOverlays();
        installGalleryGuard();
        galleryRoute("list");
        if (!isVersion21()) return false;
        document.body.setAttribute("data-specimen", "action-bar");
        specimenActiveId = id;
        selectionSpecimenCount = entry.count;
        specimenSelectRows(entry.count);
        syncSelectionActionBar();
        return Boolean(document.querySelector("[data-selection-bar]:not([hidden])"));
      } catch (_) {
        specimenActiveId = "";
        selectionSpecimenCount = null;
        return false;
      }
    },

    close: function () {
      document.body.removeAttribute("data-specimen");
      specimenActiveId = "";
      selectionSpecimenCount = null;
      clearRateCardSelection();
      removeGalleryGuard();
      if (specimenEntryUrl) {
        try {
          window.history.replaceState(null, "", specimenEntryUrl);
        } catch (_) {}
        specimenEntryUrl = "";
      }
      return true;
    },
  };

  window.RateCardStateBridge = {
    version: 1,

    capture() {
      let wizard = null;
      try {
        wizard = window.RateCardV2StateBridge
          && typeof window.RateCardV2StateBridge.capture === "function"
          ? window.RateCardV2StateBridge.capture()
          : null;
      } catch (_) {
        wizard = null;
      }
      return {
        v: 1,
        route: document.body.getAttribute("data-route") || "list",
        version: document.body.getAttribute("data-version") || "",
        mode: document.body.getAttribute("data-mode") || "",
        list: {
          query,
          filters: cloneFilters(appliedFilters),
          draftFilters: cloneFilters(draftFilters),
          sort: sortState ? { key: sortState.key, dir: sortState.dir } : null,
          page,
          pageSize,
          selectedRateCardIds: Array.from(selectedRateCardIds),
          filterPanelOpen: isFilterPanelOpen(),
        },
        accordions: bridgeCaptureAccordions(),
        wizard,
        controls: bridgeCaptureControls(),
        selects: bridgeCaptureSelects(),
        scroll: bridgeCaptureScroll(),
      };
    },

    restore(snapshot) {
      if (!snapshot || snapshot.v !== 1) return false;
      // The overlay gallery can route the preview elsewhere to reach an
      // overlay, so returning to the captured page comes first.
      if (snapshot.route && snapshot.route !== document.body.getAttribute("data-route")) {
        navigateTo(snapshot.route);
        if (snapshot.route !== document.body.getAttribute("data-route")) return false;
      }

      const list = snapshot.list;
      if (list) {
        query = list.query || "";
        /* cloneFilters, not a spread: the multi-value keys are arrays and
         * a shallow copy would let a snapshot and the live state share
         * one array and drift together. */
        appliedFilters = cloneFilters(Object.assign(emptyFilters(), list.filters || {}));
        draftFilters = cloneFilters(
          Object.assign(emptyFilters(), list.draftFilters || list.filters || {}));
        sortState = list.sort && list.sort.key
          ? { key: list.sort.key, dir: list.sort.dir }
          : null;
        pageSize = Number(list.pageSize) || 10;
        page = Number(list.page) || 1;
        /* Snapshots taken before 2.1 carried a single selectedRateCardId,
         * so accept either shape. */
        selectedRateCardIds.clear();
        (Array.isArray(list.selectedRateCardIds)
          ? list.selectedRateCardIds
          : [list.selectedRateCardId]
        ).forEach(function (id) {
          if (id) selectedRateCardIds.add(String(id));
        });

        const search = document.querySelector('[data-action="search"]');
        if (search) {
          search.value = query;
          const wrap = search.closest(".ads-search");
          const clear = wrap && wrap.querySelector('[data-action="clear-search"]');
          if (wrap) wrap.setAttribute("data-filled", String(Boolean(query)));
          if (clear) clear.hidden = !query;
        }
        const pageSizeSel = document.querySelector('[data-action="page-size"]');
        if (pageSizeSel) pageSizeSel.value = String(pageSize);
        renderDraftIntoSelects();
        renderTable();
        if (list.filterPanelOpen && !isFilterPanelOpen()) {
          const trigger = document.querySelector('[data-action="toggle-filter"]');
          if (trigger) trigger.click();
        }
      }

      bridgeRestoreAccordions(snapshot.accordions);

      try {
        if (snapshot.wizard
          && window.RateCardV2StateBridge
          && typeof window.RateCardV2StateBridge.restore === "function") {
          window.RateCardV2StateBridge.restore(snapshot.wizard);
        }
      } catch (_) {}

      // Field values run last so unsaved edits win over anything the
      // wizard repopulated from its saved file.
      bridgeRestoreControls(snapshot.controls);
      bridgeRestoreSelects(snapshot.selects);

      // Scroll offsets are only meaningful once the restored content has
      // been laid out.
      requestAnimationFrame(() => bridgeRestoreScroll(snapshot.scroll));
      return true;
    },
  };

  /* =====================================================================
   *  ATLAS INTRO DECK (2026-06-29 brief, 2026-08-04 re-order)
   *
   *  Standalone /atlas route surfaces an intro deck before the user
   *  enters the Rate Card Manager table.
   *
   *  The running order is not written down here. The deck indexes
   *  .atlas-slide in DOM order, so index.html is the only place the
   *  order exists, and the ROUTE: atlas comment there lists it. Copies
   *  of that list in other files went stale every time a slide moved.
   *
   *  Every slide is authored as HTML/CSS/SVG at the Figma-native
   *  1920x1080 coordinate space. The deck is a single .atlas-deck container
   *  that scales the 1920x1080 inner stage to the viewport via CSS
   *  transform: scale(); only one slide is visible at a time
   *  (.atlas-slide.is-active).
   *
   *  Navigation:
   *    - Click / tap anywhere = advance
   *    - Keyboard: ArrowRight / Space / PageDown = next
   *                ArrowLeft / PageUp           = prev
   *                Home / End                   = first / last
   *                Escape                       = exit to Rate Card Manager
   *    - Atlas brand-mark button on the final slide = navigateTo("list")
   *  The current slide index is mirrored to the URL as ?section=atlas
   *  &slide=N so a hard refresh keeps the user where they were.
   * ===================================================================== */
  /* Slides that run their own walkthrough register here, keyed by the
   * slide element. initAtlasDeck() asks the active slide whether it wants
   * a "next" gesture before treating it as navigation. */
  var atlasSlideGestures = [];

  function atlasSlideConsumes(slide, gesture) {
    if (!slide) return false;
    for (var i = 0; i < atlasSlideGestures.length; i += 1) {
      var entry = atlasSlideGestures[i];
      if (entry.slide === slide) {
        if (gesture === 'back' && !entry.back) return false;
        return Boolean(entry.handle(gesture));
      }
    }
    return false;
  }

  /* ------------------------------------------------------------------
   * Slide 6: "Each line item is priced as the media plan is built".
   *
   * One line item crosses five stops and comes back priced. The
   * advertiser's ad is already on screen when the slide opens, because at
   * that moment there is no line item yet, only the buyer whose ad it will
   * carry. Everything after that is the presenter's, one stop per gesture:
   *
   *   0 ad -> 1 line item + ICM -> 2 offering + TOM
   *     -> 3 targeting + RCM -> 4 rate found -> 5 rate applied
   *
   * Four of those are the presenter's. The fifth is not: once the rate is
   * back with Core Planning the return leg draws itself, a second later, so
   * the presenter never has to ask for the thing that says the work goes on.
   *
   * Step 5 does not finish anything. The return leg is the point: pricing
   * one line item is not finishing a plan, so the row still points past it.
   *
   * The controller only writes data-mpl-step and is-revealed; every
   * position, delay and fade lives in styles.css, so the two cannot drift
   * and no animation can leave an element anywhere but its Figma
   * coordinate.
   *
   * Timings are the contract shared with qa_media_plan_slide.py.
   * ------------------------------------------------------------------ */
  function initAtlasMediaPlanSteps() {
    var slide = document.getElementById('atlas-slide-media-plan');
    if (!slide) return;
    var mpl = slide.querySelector('[data-media-plan]');
    if (!mpl) return;
    var live = mpl.querySelector('[data-mpl-live]');

    /* One line item, five stops. The first four are clicks; the fifth
     * follows on its own.
     *
     * Each entry lists what that step brings on screen, how long the whole
     * chain takes to settle, and what a screen reader should hear.
     *
     * `runs` is not decoration. Navigation is held for that long, so a fast
     * or repeated click cannot land two stops at once, strand a window
     * mid-wipe, or fall through to the next slide. Each number is the last
     * animation-delay for that step in styles.css plus its duration, and the
     * two are checked against each other by qa_media_plan_slide.py. */
    var PLAN = [
      null,
      { show: ['card-1', 'link-1', 'icm-shelf', 'icm-pumpkin', 'icm-label'],
        runs: 1460,
        say: 'Line item created from the buyer context. ICM provides the offering context.' },
      { show: ['card-2', 'link-2', 'tom-shelf', 'tom-sign', 'tom-label'],
        runs: 1940,
        say: 'Offering added. TOM provides the targeting context.' },
      { show: ['card-3', 'link-3', 'rcm-scene', 'rcm-pumpkin', 'rcm-label'],
        runs: 2080,
        say: 'Targeting added. RCM weighs it and finds the rate.' },
      /* `settles` is the moment the Core Planning panel reaches full
       * opacity, which is what the one second before the return leg is
       * measured from. It is animation-delay 960 plus the 450ms fade. */
      { show: ['card-4', 'link-4', 'core-panel', 'core-label'],
        runs: 1480, settles: 1410,
        say: 'RCM returns the applicable rate, 20 dollars CPM. Illustrative.' },
      { show: ['loop', 'loop-label'],
        runs: 1300,
        say: 'Rate applied to the line item. Core Planning continues with the next one.' }
    ];
    var STEPS = PLAN.length - 1;
    /* The last stop is not asked for. It arrives a second after the rate
     * lands, because that pause is what makes the return leg read as a
     * consequence rather than as another item on the list. */
    var AUTO_STEP = STEPS;
    var AUTO_DELAY = 1000;
    /* Under reduced motion the chain collapses to a short fade, so holding
     * navigation for the full travelling time would just make the slide feel
     * stuck. The hold shrinks to match what is actually happening. */
    var REDUCED_HOLD = 220;

    var step = 0;
    var heldUntil = 0;
    var running = false;
    var autoTimer = 0;

    function isLive() {
      return slide.classList.contains('is-active')
        && document.body.getAttribute('data-route') === 'atlas';
    }

    function now() {
      return (window.performance && window.performance.now)
        ? window.performance.now() : Date.now();
    }

    function reducedMotion() {
      return typeof window.matchMedia === 'function'
        && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    }

    function say(text) {
      if (live) live.textContent = text || '';
    }

    function cancelAuto() {
      if (autoTimer) { window.clearTimeout(autoTimer); autoTimer = 0; }
    }

    function setStep(next, animate) {
      step = Math.max(0, Math.min(STEPS, next));
      mpl.setAttribute('data-mpl-step', String(step));

      /* Visibility is rebuilt from the plan rather than nudged step by step,
       * so a jump in either direction always lands on exactly the right set
       * and a half-finished stop cannot survive it. */
      var wanted = {};
      for (var n = 1; n <= step; n += 1) {
        for (var j = 0; j < PLAN[n].show.length; j += 1) {
          wanted[PLAN[n].show[j]] = true;
        }
      }
      var all = mpl.querySelectorAll('[data-mpl-reveal]');
      for (var k = 0; k < all.length; k += 1) {
        all[k].classList.toggle('is-revealed', !!wanted[all[k].dataset.mplReveal]);
      }

      if (!step) { say(''); return; }
      say(PLAN[step].say);

      /* Once the rate is home, start counting down to the return leg. */
      if (animate && step === AUTO_STEP - 1) {
        cancelAuto();
        var wait = (PLAN[step].settles || PLAN[step].runs) + AUTO_DELAY;
        autoTimer = window.setTimeout(function () {
          autoTimer = 0;
          if (!isLive() || step !== AUTO_STEP - 1) return;
          setStep(AUTO_STEP, true);
          heldUntil = now() + PLAN[AUTO_STEP].runs;
        }, reducedMotion() ? REDUCED_HOLD + AUTO_DELAY : wait);
      }
    }

    function resetToStart() {
      cancelAuto();
      heldUntil = 0;
      setStep(0, false);
    }

    function start() {
      if (running) return;
      running = true;
      resetToStart();
    }

    function stop() {
      if (!running) return;
      running = false;
      resetToStart();
    }

    /* The deck offers every forward and backward gesture here first.
     * Returning true keeps it on this slide; returning false lets the deck
     * take it. */
    function handle(gesture) {
      if (!isLive()) return false;

      if (gesture === 'back') {
        if (!step) return false;
        /* Going back restores the earlier state outright. Nothing replays,
         * so no entrance animation fires for a stop that was already told,
         * and any pending return leg is called off. */
        cancelAuto();
        heldUntil = 0;
        setStep(step - 1, false);
        return true;
      }

      /* A stop is still arriving, or the return leg is on its way. Either
       * way the gesture is swallowed rather than queued, so nothing can be
       * skipped and the deck cannot move on underneath it. */
      if (now() < heldUntil || autoTimer) return true;
      if (step >= STEPS) return false;      /* told in full, let the deck go */

      setStep(step + 1, true);
      heldUntil = now() + (reducedMotion() ? REDUCED_HOLD : PLAN[step].runs);
      return true;
    }

    atlasSlideGestures.push({ slide: slide, handle: handle, back: true });

    function sync() {
      if (isLive()) start();
      else stop();
    }

    new MutationObserver(sync)
      .observe(slide, { attributes: true, attributeFilter: ['class'] });
    new MutationObserver(sync)
      .observe(document.body, { attributes: true, attributeFilter: ['data-route'] });

    /* A deep link or a refresh lands with the slide already active, before
     * either observer exists. */
    sync();
  }

  /* ------------------------------------------------------------------
   * Slide 2: "A Rate Card tells us the right price for each deal".
   *
   * The slide is a formula, so it is read out one term at a time:
   * Buyer + Deal + Product + Price Change, and then the equals sign.
   * A card and the question under it always arrive together, because
   * the question is what the card means. The answer, Right Price, is
   * deliberately withheld: the deck stops after the equals sign and
   * waits for the presenter to ask for it, which is the beat the slide
   * exists for.
   *
   * Three phases, written to data-rpx-phase so CSS (and QA) can see
   * them: revealing-inputs -> waiting-for-result -> result-visible.
   * The gold card is bound to the phase rather than to a class of its
   * own, so an interrupted run cannot leave the answer on screen.
   *
   * This slide owns click / Space / Enter while it still has something
   * to show, and hands them back once the result is up. Arrow keys are
   * never taken, so a presenter always has a way straight past it.
   *
   * Timings are the contract shared with qa_right_price_slide.py.
   * ------------------------------------------------------------------ */
  function initAtlasRightPrice() {
    var rpx = document.querySelector('[data-right-price]');
    if (!rpx) return;
    var slide = rpx.closest('.atlas-slide');
    if (!slide) return;

    var LEAD_IN = 260;      // beat before the first card lands
    var TERM_TO_OP = 180;   // card settles, then its operator fades in
    var OP_TO_TERM = 200;   // operator settles, then the next card
    var ADVANCE_GUARD = 400; // swallow repeats right after a reveal

    /* Reveal order. Terms and operators alternate, so a term and the
     * one before it are TERM_TO_OP + OP_TO_TERM apart. */
    var SEQUENCE = [
      'term-1', 'op-1',
      'term-2', 'op-2',
      'term-3', 'op-3',
      'term-4', 'op-4'
    ];

    var timers = [];
    var running = false;
    var revealedAt = 0;

    function after(ms, fn) {
      var id = window.setTimeout(function () {
        timers = timers.filter(function (t) { return t !== id; });
        /* A pending step must never paint onto a slide the presenter has
         * already left, so every callback re-checks before it runs. */
        if (!isLive()) return;
        fn();
      }, ms);
      timers.push(id);
      return id;
    }

    function clearTimers() {
      timers.forEach(window.clearTimeout);
      timers = [];
    }

    function isLive() {
      return slide.classList.contains('is-active')
        && document.body.getAttribute('data-route') === 'atlas';
    }

    function parts() {
      return Array.prototype.slice.call(
        rpx.querySelectorAll('[data-rpx-reveal]')
      );
    }

    function phase() {
      return rpx.getAttribute('data-rpx-phase') || 'revealing-inputs';
    }

    function setPhase(value) {
      rpx.setAttribute('data-rpx-phase', value);
    }

    function say(message) {
      var live = rpx.querySelector('[data-rpx-live]');
      if (live) live.textContent = message;
    }

    function showResult(visible) {
      var result = rpx.querySelector('[data-rpx-result]');
      if (result) result.setAttribute('aria-hidden', visible ? 'false' : 'true');
    }

    function reveal(name) {
      var node = rpx.querySelector('[data-rpx-reveal="' + name + '"]');
      if (node) node.classList.add('is-revealed');
    }

    function waitForPresenter() {
      setPhase('waiting-for-result');
    }

    /* Lay the whole formula out at once. Used both when the sequence
     * reaches its end and when a presenter clicks through it early. */
    function finishInputs() {
      clearTimers();
      parts().forEach(function (node) { node.classList.add('is-revealed'); });
      waitForPresenter();
    }

    function revealResult() {
      setPhase('result-visible');
      showResult(true);
      revealedAt = Date.now();
      say('Right Price revealed.');
    }

    function resetToHidden() {
      clearTimers();
      parts().forEach(function (node) { node.classList.remove('is-revealed'); });
      setPhase('revealing-inputs');
      showResult(false);
      revealedAt = 0;
      say('');
    }

    function start() {
      if (running) return;
      running = true;
      resetToHidden();
      var elapsed = LEAD_IN;
      SEQUENCE.forEach(function (name, index) {
        if (index > 0) {
          elapsed += index % 2 === 1 ? TERM_TO_OP : OP_TO_TERM;
        }
        var last = index === SEQUENCE.length - 1;
        after(elapsed, function () {
          reveal(name);
          if (last) waitForPresenter();
        });
      });
    }

    function stop() {
      if (!running) return;
      running = false;
      resetToHidden();
    }

    function handle(gesture) {
      /* Arrow keys and PageDown stay deck navigation on every slide, so
       * the formula can always be skipped. */
      if (gesture === 'arrow') return false;
      if (!isLive()) return false;

      var current = phase();
      if (current === 'revealing-inputs') {
        /* An early gesture buys the rest of the formula, not the answer. */
        finishInputs();
        return true;
      }
      if (current === 'waiting-for-result') {
        revealResult();
        return true;
      }
      /* result-visible: the deck takes over again, except for the tail of
       * a double click or a held key still arriving from the reveal. */
      if (Date.now() - revealedAt < ADVANCE_GUARD) return true;
      return false;
    }

    atlasSlideGestures.push({ slide: slide, handle: handle });

    /* The deck keeps one DOM for every slide, so entering and leaving is
     * only visible as this slide's own class flipping, and leaving the
     * atlas route entirely is only visible on the body. Watching both
     * keeps the sequence from running against a hidden slide. */
    function sync() {
      if (isLive()) start();
      else stop();
    }

    new MutationObserver(sync)
      .observe(slide, { attributes: true, attributeFilter: ['class'] });
    new MutationObserver(sync)
      .observe(document.body, { attributes: true, attributeFilter: ['data-route'] });

    /* A deep link or a refresh lands with the slide already active,
     * before either observer exists. */
    sync();
  }

  /* ------------------------------------------------------------------
   * Slide 15: "Pricing decisions change as the deal changes".
   *
   * One slide, two internal views: current-design (Figma 741:13577)
   * and previous-design (Figma 741:19209). They are a design
   * comparison, not two deck slides, so nothing here touches the slide
   * index, the URL or history. The back control returns to the current
   * design; it is emphatically not the deck's previous-slide handler.
   *
   * The previous design is the Create Rate Card step wizard, which
   * already exists as structured markup inside the Rate Card layer
   * explainer. Rather than re-author or screenshot it, the first swap
   * clones that node in. One copy of the prototype, one set of .prev-*
   * styles, and nothing to drift.
   * ------------------------------------------------------------------ */
  function initAtlasConnectedWorkflows() {
    var cw = document.querySelector('[data-connected-workflows]');
    if (!cw) return;
    var slide = cw.closest('.atlas-slide');
    if (!slide) return;

    var GUARD_MS = 400;   // swallow double clicks and key repeat
    var FADE_MS = 240;    // matches the .cw__view transition

    var panels = {
      'current-design': cw.querySelector('[data-cw-panel="current-design"]'),
      'previous-design': cw.querySelector('[data-cw-panel="previous-design"]')
    };
    var triggers = {
      'previous-design': cw.querySelector('.cw__toggle'),
      'current-design': cw.querySelector('.cw__back')
    };
    if (!panels['current-design'] || !panels['previous-design']) return;

    var timers = [];
    var guardUntil = 0;
    var mounted = false;

    function after(ms, fn) {
      var id = window.setTimeout(function () {
        timers = timers.filter(function (t) { return t !== id; });
        fn();
      }, ms);
      timers.push(id);
      return id;
    }

    function clearTimers() {
      timers.forEach(window.clearTimeout);
      timers = [];
    }

    function view() {
      return cw.getAttribute('data-cw-view') || 'current-design';
    }

    /* The prototype is cloned, not duplicated in the document, so the
     * two copies cannot fall out of step. It carries aria-hidden and
     * is inert product chrome, so nothing inside it is focusable. */
    function mountPrototype() {
      if (mounted) return;
      var mount = cw.querySelector('[data-cw-prev-mount]');
      /* By the data attribute, not the class: the mount wears the same
       * class to inherit the prototype's type and surface, and it comes
       * first in the document, so a class lookup finds itself. */
      var source = document.querySelector('[data-rcle-previous-prototype]');
      if (!mount || !source || mount.childElementCount) return;
      var copy = source.cloneNode(true);
      while (copy.firstChild) mount.appendChild(copy.firstChild);
      mount.querySelectorAll(
        'a, button, input, select, textarea, [tabindex]'
      ).forEach(function (node) { node.setAttribute('tabindex', '-1'); });
      mounted = true;
    }

    function setView(next, moveFocus) {
      if (next !== 'current-design' && next !== 'previous-design') return;
      if (view() === next) return;
      if (next === 'previous-design') mountPrototype();

      clearTimers();
      Object.keys(panels).forEach(function (name) {
        var panel = panels[name];
        var active = name === next;
        panel.hidden = !active;
        /* Hidden outright rather than faded out, so the inactive view
         * is never a duplicate reading of the same slide. */
        if (active) {
          panel.removeAttribute('aria-hidden');
          panel.classList.add('is-entering');
        } else {
          panel.setAttribute('aria-hidden', 'true');
          panel.classList.remove('is-entering');
        }
      });
      /* Let the entering panel paint at opacity 0 before releasing it,
       * or the transition has nothing to animate from. */
      window.requestAnimationFrame(function () {
        window.requestAnimationFrame(function () {
          panels[next].classList.remove('is-entering');
        });
      });

      cw.setAttribute('data-cw-view', next);

      var live = cw.querySelector('[data-cw-live]');
      if (live) {
        live.textContent = next === 'previous-design'
          ? 'Previous design displayed'
          : 'Current design displayed';
      }

      if (moveFocus) {
        var target = triggers[next === 'previous-design'
          ? 'current-design'
          : 'previous-design'];
        if (target) after(FADE_MS, function () { target.focus(); });
      }
    }

    function activate(event, next) {
      /* The deck advances on a click anywhere, so both controls have to
       * take the event out of circulation before it reaches it. */
      event.preventDefault();
      event.stopPropagation();
      if (typeof event.stopImmediatePropagation === 'function') {
        event.stopImmediatePropagation();
      }
      if (Date.now() < guardUntil) return;
      guardUntil = Date.now() + GUARD_MS;
      setView(next, true);
    }

    Object.keys(triggers).forEach(function (name) {
      var button = triggers[name];
      if (!button) return;
      var next = button.getAttribute('data-cw-show');
      button.addEventListener('click', function (event) {
        activate(event, next);
      });
      /* A button already fires click on Enter and Space, so the keydown
       * handler only exists to stop the deck seeing the keystroke and
       * to drop auto-repeat on a held key. */
      button.addEventListener('keydown', function (event) {
        if (event.key !== 'Enter' && event.key !== ' '
            && event.key !== 'Spacebar') return;
        event.stopPropagation();
        if (event.repeat) event.preventDefault();
      });
    });



    function reset() {
      clearTimers();
      guardUntil = 0;
      panels['current-design'].hidden = false;
      panels['current-design'].removeAttribute('aria-hidden');
      panels['current-design'].classList.remove('is-entering');
      panels['previous-design'].hidden = true;
      panels['previous-design'].setAttribute('aria-hidden', 'true');
      panels['previous-design'].classList.remove('is-entering');
      cw.setAttribute('data-cw-view', 'current-design');
      var live = cw.querySelector('[data-cw-live]');
      if (live) live.textContent = '';
    }

    function isLive() {
      return slide.classList.contains('is-active')
        && document.body.getAttribute('data-route') === 'atlas';
    }

    /* Leaving always returns the slide to the current design, so a
     * presenter never comes back to a comparison they left open. */
    function sync() {
      if (!isLive()) reset();
    }

    /* Escape backs out of the comparison. It has to be caught on the
     * document, in the capture phase, because the deck's own Escape
     * (which leaves the presentation entirely) is bound there too and a
     * keystroke with focus on the body would never reach this slide.
     * It is only claimed while the previous design is actually up, so
     * Escape still exits the deck everywhere else. */
    document.addEventListener('keydown', function (event) {
      if (event.key !== 'Escape') return;
      if (!isLive() || view() !== 'previous-design') return;
      event.preventDefault();
      event.stopPropagation();
      if (typeof event.stopImmediatePropagation === 'function') {
        event.stopImmediatePropagation();
      }
      setView('current-design', true);
    }, true);

    new MutationObserver(sync)
      .observe(slide, { attributes: true, attributeFilter: ['class'] });
    new MutationObserver(sync)
      .observe(document.body, { attributes: true, attributeFilter: ['data-route'] });

    reset();
  }

  /* ------------------------------------------------------------------
   * Slide 8: "RCM organizes pricing into three connected sections".
   *
   * Six states, written to data-tq-state so CSS and QA can see them:
   *
   *   intro -> details-visible -> line-items-visible -> premiums-visible
   *   -> waiting-for-result -> result-visible
   *
   * The first four are automatic. The last two are the presenter's, and
   * the wait between them is the whole design: the room should hear what
   * the three inputs are before the answer is on screen, so no timer is
   * allowed to put the equals sign or the Right Price card up.
   *
   * That makes gesture ownership three-deep. A gesture during the run
   * buys the finished inputs and stops at waiting-for-result. The next
   * one spends the answer. Only the one after that belongs to the deck.
   * Each hop sets a short guard so a double click cannot skip the pause,
   * which would throw away the point of the slide.
   *
   * Timings are the contract shared with qa_three_questions_slide.py.
   * ------------------------------------------------------------------ */
  function initAtlasThreeQuestions() {
    var tq = document.querySelector('[data-three-questions]');
    if (!tq) return;
    var slide = tq.closest('.atlas-slide');
    if (!slide) return;

    var ADVANCE_GUARD = 400;   // swallow repeats right after a state change
    var EQUALS_MS = 340;       // the equals sign travels, then the answer

    /* [what to reveal, the state it lands in, when it fires]. A null state
     * means the step is punctuation rather than a state of its own. */
    var SEQUENCE = [
      ['header',  null,                 250],
      ['group-1', 'details-visible',    900],
      ['plus-1',  null,                 1450],
      ['group-2', 'line-items-visible', 1800],
      ['plus-2',  null,                 2350],
      ['group-3', 'premiums-visible',   2700]
    ];
    var RUN_MS = 3200;         // group-3 settled; the pause begins

    var timers = [];
    var running = false;
    var guardUntil = 0;

    function isLive() {
      return slide.classList.contains('is-active')
        && document.body.getAttribute('data-route') === 'atlas';
    }

    function after(ms, fn) {
      var id = window.setTimeout(function () {
        timers = timers.filter(function (t) { return t !== id; });
        /* A pending step must never paint onto a slide the presenter has
         * already left, so every callback re-checks before it runs. */
        if (!isLive()) return;
        fn();
      }, ms);
      timers.push(id);
      return id;
    }

    function clearTimers() {
      timers.forEach(window.clearTimeout);
      timers = [];
    }

    function parts() {
      return Array.prototype.slice.call(
        tq.querySelectorAll('[data-tq-reveal]')
      );
    }

    function phase() {
      return tq.getAttribute('data-tq-phase') || 'intro';
    }

    function setState(state) {
      if (state) tq.setAttribute('data-tq-state', state);
    }

    function revealStep(name) {
      var node = tq.querySelector('[data-tq-reveal="' + name + '"]');
      if (node) node.classList.add('is-revealed');
    }

    /* Everything except the answer. Used both when the run reaches its end
     * and when a presenter clicks through it early: either way the slide
     * stops here and waits. */
    function completeInputs() {
      clearTimers();
      SEQUENCE.forEach(function (step) { revealStep(step[0]); });
      setState('premiums-visible');
      tq.setAttribute('data-tq-phase', 'waiting-for-result');
    }

    /* The presenter's reveal. The equals sign lands first so the card
     * reads as the result of the three inputs, not a fourth one. */
    function revealResult() {
      revealStep('equals');
      tq.setAttribute('data-tq-phase', 'result-visible');
      setState('result-visible');
      after(EQUALS_MS, function () {
        revealStep('result');
        var live = tq.querySelector('[data-tq-live]');
        if (live) live.textContent = 'Right Price revealed. The price used in planning.';
      });
    }

    function resetToStart() {
      clearTimers();
      parts().forEach(function (node) { node.classList.remove('is-revealed'); });
      tq.setAttribute('data-tq-phase', 'intro');
      tq.setAttribute('data-tq-state', 'intro');
      var live = tq.querySelector('[data-tq-live]');
      if (live) live.textContent = '';
      guardUntil = 0;
    }

    function start() {
      if (running) return;
      running = true;
      resetToStart();
      SEQUENCE.forEach(function (step) {
        after(step[2], function () {
          revealStep(step[0]);
          setState(step[1]);
        });
      });
      /* The run ends by waiting, not by revealing. */
      after(RUN_MS, function () {
        tq.setAttribute('data-tq-phase', 'waiting-for-result');
      });
    }

    function stop() {
      if (!running) return;
      running = false;
      resetToStart();
    }

    function handle(gesture) {
      /* Arrow keys and PageDown stay deck navigation on every slide. */
      if (gesture === 'arrow') return false;
      if (!isLive()) return false;

      var current = phase();

      if (current === 'intro') {
        /* Buys the three inputs and nothing else. The answer stays back,
         * so this gesture cannot skip the pause it exists to create. */
        completeInputs();
        guardUntil = Date.now() + ADVANCE_GUARD;
        return true;
      }

      if (current === 'waiting-for-result') {
        /* Still inside the guard means this is the tail of the gesture
         * that just finished the inputs, not the presenter asking for the
         * answer. */
        if (Date.now() < guardUntil) return true;
        revealResult();
        guardUntil = Date.now() + ADVANCE_GUARD;
        return true;
      }

      /* result-visible: the deck takes over again, except for the tail of
       * a double click or a held key still arriving from the reveal. */
      if (Date.now() < guardUntil) return true;
      return false;
    }

    atlasSlideGestures.push({ slide: slide, handle: handle });

    function sync() {
      if (isLive()) start();
      else stop();
    }

    new MutationObserver(sync)
      .observe(slide, { attributes: true, attributeFilter: ['class'] });
    new MutationObserver(sync)
      .observe(document.body, { attributes: true, attributeFilter: ['data-route'] });

    /* A deep link or a refresh lands with the slide already active,
     * before either observer exists. */
    sync();
  }

  /* ------------------------------------------------------------------
   * Slide 3: "Think of Disney Advertising as a supermarket".
   *
   * The heading arrives on its own, a line at a time. The metaphor is
   * presenter owned from there: one forward gesture brings in one whole
   * column (its drawing and both of its captions), one backward gesture
   * takes the last column back out, and the three columns go left to
   * right. A column is one reveal target, so a drawing can never be up
   * while the words under it are still missing.
   *
   * Phases are written to data-sup-phase: revealing -> complete for the
   * heading, and the column count to data-sup-group-step. Once the third
   * column is up there is nothing left to show, so the deck owns the next
   * gesture again.
   *
   * Timings are the contract shared with qa_supermarket_slide.py.
   * ------------------------------------------------------------------ */
  function initAtlasSupermarket() {
    var sup = document.querySelector('[data-supermarket]');
    if (!sup) return;
    var slide = sup.closest('.atlas-slide');
    if (!slide) return;

    var TITLE_AT = 120;      // beat before the first line lands
    var SUBTITLE_AFTER = 180; // second line follows the first
    var ADVANCE_GUARD = 400;  // swallow repeats right after a state change

    var SEQUENCE = [
      ['title', TITLE_AT],
      ['subtitle', TITLE_AT + SUBTITLE_AFTER]
    ];

    /* Left to right, the order the metaphor is told in. */
    var GROUP_ORDER = ['group-store', 'group-shelves', 'group-produce'];

    var timers = [];
    var running = false;
    var guardUntil = 0;
    var groupStep = 0;

    function isLive() {
      return slide.classList.contains('is-active')
        && document.body.getAttribute('data-route') === 'atlas';
    }

    function after(ms, fn) {
      var id = window.setTimeout(function () {
        timers = timers.filter(function (t) { return t !== id; });
        /* A pending step must never paint onto a slide the presenter has
         * already left, so every callback re-checks before it runs. */
        if (!isLive()) return;
        fn();
      }, ms);
      timers.push(id);
      return id;
    }

    function clearTimers() {
      timers.forEach(window.clearTimeout);
      timers = [];
    }

    function parts() {
      return Array.prototype.slice.call(
        sup.querySelectorAll('[data-sup-reveal]')
      );
    }

    function phase() {
      return sup.getAttribute('data-sup-phase') || 'revealing';
    }

    /* Skipping the heading run brings both lines in at once. It does not
     * touch the columns: those are the presenter's to spend. */
    function completeHeading() {
      clearTimers();
      SEQUENCE.forEach(function (step) {
        var node = sup.querySelector('[data-sup-reveal="' + step[0] + '"]');
        if (node) node.classList.add('is-revealed');
      });
      sup.setAttribute('data-sup-phase', 'complete');
    }

    function setGroupStep(next) {
      groupStep = Math.max(0, Math.min(GROUP_ORDER.length, next));
      GROUP_ORDER.forEach(function (name, index) {
        var node = sup.querySelector('[data-sup-reveal="' + name + '"]');
        if (node) node.classList.toggle('is-revealed', index < groupStep);
      });
      sup.setAttribute('data-sup-group-step', String(groupStep));
    }

    function resetToHidden() {
      clearTimers();
      parts().forEach(function (node) { node.classList.remove('is-revealed'); });
      sup.setAttribute('data-sup-phase', 'revealing');
      setGroupStep(0);
      guardUntil = 0;
    }

    function start() {
      if (running) return;
      running = true;
      resetToHidden();
      SEQUENCE.forEach(function (step, index) {
        var last = index === SEQUENCE.length - 1;
        after(step[1], function () {
          var node = sup.querySelector('[data-sup-reveal="' + step[0] + '"]');
          if (node) node.classList.add('is-revealed');
          if (last) sup.setAttribute('data-sup-phase', 'complete');
        });
      });
    }

    function stop() {
      if (!running) return;
      running = false;
      resetToHidden();
    }

    function handle(gesture) {
      if (!isLive()) return false;

      /* Backward: give the last column back, one gesture at a time. With
       * nothing left to take back the deck retreats as usual. */
      if (gesture === 'back') {
        if (groupStep <= 0) return false;
        if (Date.now() < guardUntil) return true;
        setGroupStep(groupStep - 1);
        guardUntil = Date.now() + ADVANCE_GUARD;
        return true;
      }

      /* A gesture during the heading run buys the rest of the heading,
       * not the first column: the room should read the premise before
       * any of the metaphor is on screen. */
      if (phase() === 'revealing') {
        completeHeading();
        guardUntil = Date.now() + ADVANCE_GUARD;
        return true;
      }

      /* The tail of a double click or a held key still arriving from the
       * last change is not the presenter asking for the next column. */
      if (Date.now() < guardUntil) return true;
      if (groupStep >= GROUP_ORDER.length) return false;
      setGroupStep(groupStep + 1);
      guardUntil = Date.now() + ADVANCE_GUARD;
      return true;
    }

    atlasSlideGestures.push({ slide: slide, handle: handle, back: true });

    function sync() {
      if (isLive()) start();
      else stop();
    }

    new MutationObserver(sync)
      .observe(slide, { attributes: true, attributeFilter: ['class'] });
    new MutationObserver(sync)
      .observe(document.body, { attributes: true, attributeFilter: ['data-route'] });

    /* A deep link or a refresh lands with the slide already active,
     * before either observer exists. */
    sync();
  }

  /* ------------------------------------------------------------------
   * Slide 4: "Buyers can purchase through different deal types".
   *
   * Only the heading arrives on its own. Both columns are held back, so
   * the slide opens on the question and nothing else, and each column is
   * one presenter gesture:
   *
   *   1 Upfront. The warehouse arrives and the two workers in it move a
   *     carton out of the van and onto the committed stack.
   *   2 Scatter. The shop floor arrives and its three staff each put a
   *     single product onto shelves that already hold stock.
   *
   * Every scene is a stack of drawn layers rather than a rig: the room,
   * a still plate of the people who never move where there are any, and
   * one cut-out per timeline of people who do. A cut-out carries only the
   * staff on that timeline, so the room is the single place every wall,
   * shelf, product and crate is drawn. The two rules the stack depends on
   * are that no scenery is ever painted twice, and that no two drawings of
   * the same person are painted at the same time.
   *
   * Phases are written to data-usc-phase (revealing -> complete) and the
   * stage count to data-usc-stage. Timings are the contract shared with
   * qa_upfront_scatter_slide.py.
   * ------------------------------------------------------------------ */
  function initAtlasUpfrontScatter() {
    var usc = document.querySelector('[data-upfront-scatter]');
    if (!usc) return;
    var slide = usc.closest('.atlas-slide');
    if (!slide) return;
    /* Idempotent: a second call must not stack a second set of gesture
     * handlers, observers or animation loops onto the same markup. */
    if (usc.hasAttribute('data-usc-ready')) return;
    usc.setAttribute('data-usc-ready', '');

    var SEQUENCE = [
      ['header', 250]
    ];
    var ADVANCE_GUARD = 400; // swallow repeats right after the heading skip

    /* Left to right, the order the comparison is argued in. */
    var STAGES = ['upfront', 'scatter'];

    /* ---- the people -------------------------------------------------
     * Four complete drawings per timeline: reaching for the goods, holding
     * them, setting them down, and standing back with empty hands.
     *
     * They are shown one at a time, cut, never dissolved. Cross-fading two
     * drawings of the same person standing slightly apart is what produces
     * a double body: at the midpoint both are half painted, which reads as
     * a torn back on the worker, and a carried product fades out of one
     * hand before it has faded into the other, so it looks like it
     * vanishes. A cut always shows one whole drawing.
     *
     * Each drawing holds only the people on its own timeline, cut to their
     * outline, so a drawing cannot repaint the room, the shelving or
     * anybody else. Upfront's two warehouse workers pass a carton between
     * them and so share one timeline. Scatter's three staff split over two:
     * the pair working the left aisle move together, and the one on the
     * right runs out of step with them.
     * ------------------------------------------------------------------ */
    var BEATS = [
      { pose: '01-pickup',  hold: 1150 },
      { pose: '02-handoff', hold: 1250 },
      { pose: '03-place',   hold: 1150 },
      { pose: '04-release', hold: 1050 }
    ];
    var CYCLE = BEATS.reduce(function (total, beat) {
      return total + beat.hold;
    }, 0);

    /* Timelines within one scene run the same four drawings out of step, so
     * the people are not all moving on the same frame. */
    var WINDOW_OFFSET = [0, 1700];

    /* The drawings that already contain the delivered carton standing on
     * the stack. Painting the separate carton over one of these would lay
     * two slightly different drawings of it on the same spot, which shows
     * as a doubled edge. */
    var POSES_HOLDING_CARTON = ['03-place', '04-release'];

    var RESTING_POSE = '02-handoff';

    function reduced() {
      return typeof window.matchMedia === 'function'
        && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    }

    function scenePoses(svg) {
      var windows = Array.prototype.slice.call(
        svg.querySelectorAll('[data-usc-window]')
      );
      if (!windows.length) return null;

      var rigs = windows.map(function (group, i) {
        var layers = {};
        BEATS.forEach(function (beat) {
          layers[beat.pose] =
            group.querySelector('[data-usc-pose="' + beat.pose + '"]');
        });
        return {
          layers: layers,
          placed: group.querySelector('[data-usc-placed]'),
          offset: WINDOW_OFFSET[i % WINDOW_OFFSET.length] || 0,
          shown: null,
          laps: 0
        };
      });

      var frame = 0;
      var run = 0; // invalidates any callback left over from an earlier run

      /* One drawing on, every other drawing off, in the same tick. A layer
       * that is not the current one is switched off twice over, transparent
       * and hidden, so a person cannot survive a switch as a faint second
       * copy. The whole artwork is already pointer-events: none. */
      function paint(node, on) {
        node.setAttribute('opacity', on ? '1' : '0');
        node.style.visibility = on ? 'visible' : 'hidden';
        if (on) node.removeAttribute('aria-hidden');
        else node.setAttribute('aria-hidden', 'true');
      }

      function show(rig, pose, laps) {
        if (rig.shown !== pose) {
          BEATS.forEach(function (beat) {
            paint(rig.layers[beat.pose], beat.pose === pose);
          });
          rig.shown = pose;
        }
        /* The delivered carton stays on the stack once it is set down, so a
         * new lap reads as fetching the next box rather than the last one
         * jumping back into a worker's hands. The place and release
         * drawings already hold it, so this only covers the laps after. */
        if (rig.placed) {
          paint(rig.placed,
                laps > 0 && POSES_HOLDING_CARTON.indexOf(pose) === -1);
        }
      }

      function beatAt(ms) {
        var t = ms % CYCLE;
        for (var i = 0; i < BEATS.length; i++) {
          if (t < BEATS[i].hold) return i;
          t -= BEATS[i].hold;
        }
        return BEATS.length - 1;
      }

      function mark(state) {
        var group = svg.closest('[data-usc-scene]');
        if (group) group.setAttribute('data-usc-run', state);
      }

      /* Write every layer from scratch rather than trusting the cached
       * pose, so the scene lands in the same state however it got here. */
      function settle(pose) {
        rigs.forEach(function (rig) {
          rig.laps = 0;
          rig.shown = null;
          show(rig, pose, 0);
        });
      }

      function reset() {
        cancel();
        settle(BEATS[0].pose);
        mark('ready');
      }

      function cancel() {
        run += 1;
        if (frame) window.cancelAnimationFrame(frame);
        frame = 0;
      }

      function play() {
        cancel();
        if (reduced()) {
          settle(RESTING_POSE);
          mark('settled');
          return;
        }
        mark('running');
        var mine = run;
        var start = 0;
        rigs.forEach(function (rig) { rig.laps = 0; rig.shown = null; });
        frame = window.requestAnimationFrame(function step(now) {
          if (mine !== run) return; // cancelled while this tick was queued
          if (!start) start = now;
          var ms = now - start;
          rigs.forEach(function (rig) {
            var local = ms + rig.offset;
            rig.laps = Math.floor(local / CYCLE);
            show(rig, BEATS[beatAt(local)].pose, rig.laps);
          });
          frame = window.requestAnimationFrame(step);
        });
      }

      function running() { return !!frame; }

      reset();
      return { play: play, reset: reset, cancel: cancel, running: running };
    }

    var motion = {};
    STAGES.forEach(function (name) {
      var svg = usc.querySelector('#' + name + '-scene');
      if (svg) motion[name] = scenePoses(svg);
    });

    var timers = [];
    var running = false;
    var guardUntil = 0;
    var stageIndex = 0;

    function isLive() {
      return slide.classList.contains('is-active')
        && document.body.getAttribute('data-route') === 'atlas';
    }

    function after(ms, fn) {
      var id = window.setTimeout(function () {
        timers = timers.filter(function (t) { return t !== id; });
        if (!isLive()) return;
        fn();
      }, ms);
      timers.push(id);
      return id;
    }

    function clearTimers() {
      timers.forEach(window.clearTimeout);
      timers = [];
    }

    function parts() {
      return Array.prototype.slice.call(
        usc.querySelectorAll('[data-usc-reveal]')
      );
    }

    function phase() {
      return usc.getAttribute('data-usc-phase') || 'revealing';
    }

    function completeHeading() {
      clearTimers();
      SEQUENCE.forEach(function (step) {
        var node = usc.querySelector('[data-usc-reveal="' + step[0] + '"]');
        if (node) node.classList.add('is-revealed');
      });
      usc.setAttribute('data-usc-phase', 'complete');
    }

    function setStage(next) {
      var previous = stageIndex;
      stageIndex = Math.max(0, Math.min(STAGES.length, next));
      STAGES.forEach(function (name, index) {
        var group = usc.querySelector('[data-usc-scene="' + name + '"]');
        if (!group) return;
        var on = index < stageIndex;
        group.classList.toggle('is-revealed', on);
        if (!motion[name]) return;
        if (!on) { motion[name].reset(); return; }
        /* Only the column that just opened starts working. A column that
         * was already up is left alone, so opening Scatter never cuts
         * Upfront's hands off mid carry. */
        if (index === previous && stageIndex > previous) motion[name].play();
      });
      usc.setAttribute('data-usc-stage', String(stageIndex));
    }

    function resetToHidden() {
      clearTimers();
      parts().forEach(function (node) { node.classList.remove('is-revealed'); });
      usc.setAttribute('data-usc-phase', 'revealing');
      setStage(0);
      guardUntil = 0;
    }

    function start() {
      if (running) return;
      running = true;
      resetToHidden();
      SEQUENCE.forEach(function (step, index) {
        var last = index === SEQUENCE.length - 1;
        after(step[1], function () {
          var node = usc.querySelector('[data-usc-reveal="' + step[0] + '"]');
          if (node) node.classList.add('is-revealed');
          if (last) usc.setAttribute('data-usc-phase', 'complete');
        });
      });
    }

    function stop() {
      if (!running) return;
      running = false;
      resetToHidden();
    }

    function handle(gesture) {
      if (!isLive()) return false;

      if (gesture === 'back') {
        if (stageIndex <= 0) return false;
        if (Date.now() < guardUntil) return true;
        setStage(stageIndex - 1);
        guardUntil = Date.now() + ADVANCE_GUARD;
        return true;
      }

      if (phase() === 'revealing') {
        completeHeading();
        guardUntil = Date.now() + ADVANCE_GUARD;
        return true;
      }

      /* A presenter who moves on while a column is still animating means
       * it: the next column opens straight away and the one behind is left
       * standing on its finished pose. Only the tail of a double click is
       * swallowed, so one press can never spend two stages. */
      if (Date.now() < guardUntil) return true;
      if (stageIndex >= STAGES.length) return false;
      setStage(stageIndex + 1);
      guardUntil = Date.now() + ADVANCE_GUARD;
      return true;
    }

    atlasSlideGestures.push({ slide: slide, handle: handle, back: true });

    function sync() {
      if (isLive()) start();
      else stop();
    }

    new MutationObserver(sync)
      .observe(slide, { attributes: true, attributeFilter: ['class'] });
    new MutationObserver(sync)
      .observe(document.body, { attributes: true, attributeFilter: ['data-route'] });

    sync();
  }

  /* ------------------------------------------------------------------
   * Slide 5: "Same product. Different applicable rate".
   *
   * The slide opens on the question and nothing else: the heading, the ad,
   * the short line running out of it, and the footnote. The answer is the
   * presenter's to give, in three clicks.
   *
   *   1 Branch. The connector grows out of that short line: the upright
   *     opens from its middle towards both junctions, the two arms run
   *     right, and the heads arrive as the arms reach them. Both sides at
   *     once, because the point is that one ad divides in two. 615ms.
   *   2 Upfront. The stocked shelf and its rate come up together, 7px low
   *     and settling, 450ms. That inventory is already committed, so it
   *     simply arrives full.
   *   3 Scatter. The shelf comes up the same way but holding only the
   *     other produce. It sits there for 600ms, long enough for the room
   *     to see that the ad is not on it, and then ten pumpkins come down
   *     the lower branch and take the open positions. The $28 rate takes
   *     a beat once the last one lands. 2935ms.
   *
   * Every stage is one gesture, and a gesture arriving while a stage is
   * still running is dropped rather than banked, so the presenter cannot
   * skip the Scatter shelf filling or land two stages on one click. Only
   * once the third has finished does the deck take the next gesture back.
   *
   * Portfolio deck exception: the same three-stage order autoplays once
   * on slide entry (500ms settle, then ~700ms between steps). Forward
   * gestures never consume navigation, so ArrowRight / click can leave
   * immediately. prefers-reduced-motion jumps straight to the completed
   * state. Leaving cancels timers; returning replays once from the start.
   *
   * Nothing here listens for animationend: the stages are CSS timelines
   * and the guard is a clock, so a finished stage can never start the next
   * one. Backward navigation belongs to the deck, and leaving the slide is
   * what puts the opening state back.
   *
   * Written to data-sar-stage (0..3) and data-sar-phase (revealing ->
   * complete). Timings are the contract shared with
   * qa_same_ad_rate_slide.py.
   * ------------------------------------------------------------------ */
  function initAtlasSameAdRate() {
    var sar = document.querySelector('[data-same-ad-rate]');
    if (!sar) return;
    var slide = sar.closest('.atlas-slide');
    if (!slide) return;

    /* The order the argument runs in: it divides, here is one price, here
     * is the other and how it fills. */
    var STAGES = ['branch', 'upfront', 'scatter'];

    /* How long each stage's own timeline runs, matched to the transitions
     * and keyframes in styles.css. The deck refuses the next gesture until
     * the running one has finished. */
    var RUNTIME = { branch: 615, upfront: 450, scatter: 2935 };

    /* Reduced motion has far less to protect: the branch and the results
     * crossfade in a moment. Scatter still holds, because the pause and
     * the order the shelf fills in are the argument, not decoration. */
    var RUNTIME_REDUCED = { branch: 200, upfront: 200, scatter: 1370 };

    /* Portfolio autoplay: settle, then fire the existing stages in order. */
    var AUTOPLAY_START_MS = 500;
    var AUTOPLAY_STEP_MS = 700;

    var stageIndex = 0;
    var guardUntil = 0;
    var autoplayTimers = [];

    function isPortfolio() {
      return document.body.getAttribute('data-deck-variant') === 'portfolio';
    }

    function prefersReducedMotion() {
      return typeof window.matchMedia === 'function'
        && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    }

    function isLive() {
      return slide.classList.contains('is-active')
        && document.body.getAttribute('data-route') === 'atlas';
    }

    function runtime(name) {
      return (prefersReducedMotion() ? RUNTIME_REDUCED : RUNTIME)[name];
    }

    /* A stage can own several elements: the branch is two half-uprights,
     * two arms, two corner joints and two heads, and Scatter is the result
     * box, the shelf inside it and the rate that applies to it. */
    function stageNodes(name) {
      return Array.prototype.slice.call(
        sar.querySelectorAll('[data-sar-reveal="' + name + '"]')
      );
    }

    function setStage(next) {
      stageIndex = Math.max(0, Math.min(STAGES.length, next));
      STAGES.forEach(function (name, index) {
        var on = index < stageIndex;
        stageNodes(name).forEach(function (node) {
          node.classList.toggle('is-revealed', on);
        });
      });
      sar.setAttribute('data-sar-stage', String(stageIndex));
      sar.setAttribute('data-sar-phase',
        stageIndex >= STAGES.length ? 'complete' : 'revealing');
    }

    function clearAutoplay() {
      autoplayTimers.forEach(function (id) { window.clearTimeout(id); });
      autoplayTimers = [];
    }

    function reset() {
      clearAutoplay();
      setStage(0);
      guardUntil = 0;
    }

    function startPortfolioAutoplay() {
      clearAutoplay();
      if (prefersReducedMotion()) {
        setStage(STAGES.length);
        return;
      }
      setStage(0);
      STAGES.forEach(function (_name, index) {
        var delay = AUTOPLAY_START_MS + (index * AUTOPLAY_STEP_MS);
        autoplayTimers.push(window.setTimeout(function () {
          if (!isLive() || !isPortfolio()) return;
          setStage(index + 1);
        }, delay));
      });
    }

    function handle(gesture) {
      if (!isLive()) return false;
      /* Portfolio autoplays the sequence; never trap deck navigation. */
      if (isPortfolio()) return false;
      /* A gesture arriving mid-stage is dropped, not banked: the presenter
       * asked for the next beat while this one was still speaking. */
      if (Date.now() < guardUntil) return true;
      if (stageIndex >= STAGES.length) return false;
      var name = STAGES[stageIndex];
      setStage(stageIndex + 1);
      guardUntil = Date.now() + runtime(name);
      return true;
    }

    /* No back entry: ArrowLeft stays deck navigation, and leaving the
     * slide is what puts the opening state back. */
    atlasSlideGestures.push({ slide: slide, handle: handle });

    function sync() {
      clearAutoplay();
      if (isLive() && isPortfolio()) {
        startPortfolioAutoplay();
        return;
      }
      reset();
    }

    new MutationObserver(sync)
      .observe(slide, { attributes: true, attributeFilter: ['class'] });
    new MutationObserver(sync)
      .observe(document.body, { attributes: true, attributeFilter: ['data-route'] });

    /* A deep link or a refresh lands with the slide already active,
     * before either observer exists. */
    sync();
  }

  /* ---------------------------------------------------------------------
   * Presentation click-to-advance, shared
   *
   * Every presentation surface steps forward when the presenter clicks
   * its own empty space. What counts as empty is decided here rather
   * than in each view, so the surfaces cannot drift apart and so a
   * control added to a slide later is excluded without anyone having to
   * remember to call stopPropagation on it.
   *
   * The walk upwards stops at the view's own container, and that bound
   * is load-bearing: the presentation overlay is itself a role="dialog",
   * so an unbounded closest() would read every click inside it as a
   * click on a control and nothing would ever advance.
   *
   * Menus that render into document.body instead of into the slide they
   * belong to never reach these listeners at all, because the listener
   * is on the view. Menus that render in place are caught by the role
   * and class selectors below.
   * ------------------------------------------------------------------ */
  var PRESENTATION_INTERACTIVE = [
    'a[href]', 'button', 'input', 'select', 'textarea', 'label', 'summary',
    'details', 'iframe', 'audio[controls]', 'video[controls]',
    '[role="button"]', '[role="link"]', '[role="checkbox"]', '[role="radio"]',
    '[role="switch"]', '[role="tab"]', '[role="menu"]', '[role="menuitem"]',
    '[role="menuitemcheckbox"]', '[role="menuitemradio"]', '[role="listbox"]',
    '[role="option"]', '[role="combobox"]', '[role="slider"]',
    '[role="spinbutton"]', '[role="textbox"]', '[role="treeitem"]',
    '[contenteditable=""]', '[contenteditable="true"]',
    '[tabindex]:not([tabindex="-1"])',
    '[data-action]',
    /* Popovers the product renders in place rather than at body level. */
    '.edl-select__menu', '.ads-datepicker__popover'
  ].join(',');

  /* True when this click belongs to something other than the backdrop,
   * and so must not move the presentation on. `blockedSelector` lets a
   * view name whole regions that are never advance targets. */
  function presentationClickIsInteractive(event, container, blockedSelector) {
    if (!event || !container) return true;
    /* Someone upstream already treated this click as theirs.
     *
     * Deliberately not filtering on event.detail: a click raised by the
     * keyboard reports a count of zero, but so does element.click(), and
     * the keyboard case is already covered because such a click is
     * targeted at the control that was focused, which the element tests
     * below catch on their own. */
    if (event.defaultPrevented) return true;
    var node = event.target;
    if (node && node.nodeType !== 1) node = node.parentElement;
    if (!node || !container.contains(node)) return true;
    for (; node && node !== container; node = node.parentElement) {
      if (typeof node.matches !== 'function') continue;
      if (node.matches(PRESENTATION_INTERACTIVE)) return true;
      if (blockedSelector && node.matches(blockedSelector)) return true;
    }
    return false;
  }

  function initAtlasDeck() {
    var deck = document.querySelector('[data-page="atlas"]');
    if (!deck) return;

    /* -----------------------------------------------------------------
     * The running order is derived, not authored.
     *
     * index.html keeps every section in one list, but three kinds live
     * there: regular slides, the two appendix sections (marked
     * data-atlas-appendix), and the closing card (data-atlas-closing).
     * The main run is "regular slides in DOM order, then the closing card,
     * once". Nobody has to remember to keep the closing card last: drop a
     * new section anywhere in the markup and it lands in front of it. And
     * the appendix is off the run entirely, reachable only through its own
     * links, so forward navigation can never wander into it.
     * --------------------------------------------------------------- */
    var everySlide = Array.prototype.slice.call(
      deck.querySelectorAll('.atlas-slide')
    );
    function isAppendix(el) { return el.hasAttribute('data-atlas-appendix'); }
    function isClosing(el)  { return el.hasAttribute('data-atlas-closing'); }

    var closingSlide = everySlide.filter(isClosing)[0] || null;
    var slides = everySlide
      .filter(function (el) { return !isAppendix(el) && !isClosing(el); })
      .concat(closingSlide ? [closingSlide] : []);

    var stage   = deck.querySelector('.atlas-stage');
    var wrap    = deck.querySelector('.atlas-stage-wrap');
    var backBtn = deck.querySelector('[data-atlas-appendix-back]');
    var total   = slides.length;
    if (!total) return;

    function slideById(id) {
      if (!id) return null;
      for (var i = 0; i < everySlide.length; i++) {
        if (everySlide[i].getAttribute('data-atlas-slide-id') === id) {
          return everySlide[i];
        }
      }
      return null;
    }

    /* Where the closing card ended up, asked rather than assumed. */
    function closingIndex() {
      for (var i = total - 1; i >= 0; i--) {
        if (isClosing(slides[i])) return i;
      }
      return total - 1;
    }

    /* -----------------------------------------------------------------
     * No on-screen navigation chrome. The full slide canvas is the
     * advance target (handler bound to .atlas-stage-wrap below).
     * Keyboard handles back/forward + edge cases. The only opted-in
     * pointer-events: auto element inside the stage is the invisible
     * [data-atlas-enter] CTA on the final slide (Figma brand mark),
     * which keeps its own click handler.
     * --------------------------------------------------------------- */

    /* Fit-to-viewport: keep the 1920x1080 logical stage intact and scale
     * the complete composition into the wrapper's safe-area-aware content
     * box. CSS owns the breathing inset as wrapper padding. */
    var ATLAS_WIDTH = 1920;
    var ATLAS_HEIGHT = 1080;
    var fitFrame = 0;

    function fitStage() {
      if (!stage || !wrap) return;
      var deck = wrap.closest('.atlas-deck');
      var wrapStyle = window.getComputedStyle(wrap);
      var paddingLeft = parseFloat(wrapStyle.paddingLeft) || 0;
      var paddingRight = parseFloat(wrapStyle.paddingRight) || 0;
      var paddingTop = parseFloat(wrapStyle.paddingTop) || 0;
      var paddingBottom = parseFloat(wrapStyle.paddingBottom) || 0;
      var availW = Math.max(
        0,
        wrap.clientWidth - paddingLeft - paddingRight
      );
      var availH = Math.max(
        0,
        wrap.clientHeight - paddingTop - paddingBottom
      );
      /* The wrap can still read 0x0 on first paint, while the route
       * panel is hidden, or before the fixed deck receives its final
       * size after a browser chrome resize. Falling back to scale=1
       * in that window leaves the native 1920x1080 stage anchored at
       * the top-left with empty canvas around it. Measure the deck
       * shell and visualViewport before giving up, and defer a retry
       * instead of committing a bad scale. */
      if ((!availW || !availH) && deck) {
        availW = Math.max(
          availW,
          deck.clientWidth - paddingLeft - paddingRight
        );
        availH = Math.max(
          availH,
          deck.clientHeight - paddingTop - paddingBottom
        );
      }
      if (window.visualViewport) {
        if (!availW) {
          availW = Math.max(
            0,
            window.visualViewport.width - paddingLeft - paddingRight
          );
        }
        if (!availH) {
          availH = Math.max(
            0,
            window.visualViewport.height - paddingTop - paddingBottom
          );
        }
      }
      if (!availW || !availH) {
        requestStageFit();
        return;
      }
      var scale = Math.min(
        availW / ATLAS_WIDTH,
        availH / ATLAS_HEIGHT
      );
      if (!isFinite(scale) || scale <= 0) {
        requestStageFit();
        return;
      }
      stage.style.setProperty('--atlas-scale', String(scale));
      var sw = ATLAS_WIDTH * scale;
      var sh = ATLAS_HEIGHT * scale;
      var marginLeft = Math.max(0, (availW - sw) / 2);
      var marginTop = Math.max(0, (availH - sh) / 2);
      stage.style.marginLeft = marginLeft + 'px';
      stage.style.marginTop  = marginTop  + 'px';
    }

    function requestStageFit() {
      if (fitFrame) cancelAnimationFrame(fitFrame);
      fitFrame = requestAnimationFrame(function () {
        fitFrame = 0;
        fitStage();
      });
    }

    requestStageFit();
    window.addEventListener('resize', requestStageFit);
    window.addEventListener('orientationchange', requestStageFit);
    if (window.visualViewport) {
      window.visualViewport.addEventListener('resize', requestStageFit);
      window.visualViewport.addEventListener('scroll', requestStageFit);
    }
    if (typeof ResizeObserver === 'function') {
      var deck = wrap.closest('.atlas-deck');
      var stageResizeObserver = new ResizeObserver(requestStageFit);
      stageResizeObserver.observe(wrap);
      if (deck) stageResizeObserver.observe(deck);
    }
    /* Refit when the deck becomes visible (route change) - the wrap
     * has zero dimensions until display flips on. The same observer
     * is reused below to re-arm the "exiting" latch when the user
     * re-enters /atlas after having previously exited. */
    var onAtlasRouteEnter = null;        /* hooked up further below */
    var routeObserver = new MutationObserver(function(){
      if (document.body.getAttribute('data-route') === 'atlas') {
        requestStageFit();
        if (typeof onAtlasRouteEnter === 'function') onAtlasRouteEnter();
      }
    });
    routeObserver.observe(document.body, { attributes: true, attributeFilter: ['data-route'] });

    var current = 0;
    var appendixOpen = null;
    var bootAppendix = null;
    /* Restore from the URL so refresh keeps position. ?slide= takes either
     * a 1-based position in the main run (what the deck writes back) or a
     * data-atlas-slide-id. The id form is what the appendix links use,
     * because an appendix section has no position to name. */
    try {
      var raw = (new URLSearchParams(location.search)).get('slide');
      if (raw) {
        raw = raw.trim();
        var idx = parseInt(raw, 10);
        if (!isNaN(idx) && String(idx) === raw) {
          if (idx >= 1 && idx <= total) current = idx - 1;
        } else {
          var wanted = slideById(raw);
          if (wanted && isAppendix(wanted)) {
            bootAppendix = wanted;
          } else if (wanted) {
            var at = slides.indexOf(wanted);
            if (at >= 0) current = at;
          }
        }
      }
    } catch (_) {}

    function writeUrl(value) {
      if (document.body.getAttribute('data-route') !== 'atlas') return;
      try {
        var u = new URL(window.location.href);
        u.searchParams.set('section', 'atlas');
        u.searchParams.set('slide', String(value));
        window.history.replaceState(
          { section: 'atlas', slide: value }, '', u.toString()
        );
      } catch (_) {}
    }

    function setSlide(i) {
      if (i < 0) i = 0;
      if (i >= total) i = total - 1;
      current = i;
      appendixOpen = null;
      deck.removeAttribute('data-atlas-appendix-open');
      if (backBtn) backBtn.hidden = true;
      /* Sweep every section, not just the main run, so an appendix left
       * showing is cleared by the same pass that shows the new slide. */
      everySlide.forEach(function (s) {
        var on = s === slides[current];
        s.classList.toggle('is-active', on);
        s.setAttribute('aria-hidden', on ? 'false' : 'true');
      });
      /* Mirror to URL (replaceState so back/forward only crosses
       * meaningful boundaries, not every slide flip).
       *
       * IMPORTANT: only mirror when the user is actually on the atlas
       * route. initAtlasDeck() runs once on every page load (so the
       * deck is ready to go the moment the user routes to it), but
       * during that init it calls setSlide(0) which would otherwise
       * stamp ?section=atlas&slide=1 onto whatever URL the user is on
       * (e.g. clobbering ?section=list at boot). The route check
       * gates the URL write to the cases where the deck is the user-
       * facing surface. */
      writeUrl(current + 1);
    }

    /* -----------------------------------------------------------------
     * Appendix sections are shown by the same renderer as everything else;
     * they are simply not in the main run, so opening one is a separate
     * verb from advancing. Returning always lands on the closing card by
     * identity, so it keeps working if the run is reordered later.
     * --------------------------------------------------------------- */
    function openAppendix(target) {
      if (!target || !isAppendix(target)) return;
      appendixOpen = target;
      everySlide.forEach(function (s) {
        var on = s === target;
        s.classList.toggle('is-active', on);
        s.setAttribute('aria-hidden', on ? 'false' : 'true');
      });
      deck.setAttribute(
        'data-atlas-appendix-open',
        target.getAttribute('data-atlas-slide-id') || ''
      );
      if (backBtn) backBtn.hidden = false;
      writeUrl(target.getAttribute('data-atlas-slide-id'));
    }

    function closeAppendix() {
      if (!appendixOpen) return false;
      setSlide(closingIndex());
      return true;
    }

    /* -----------------------------------------------------------------
     * Forward navigation - single entry point so click / Space /
     * ArrowRight / PageDown all share the same rules:
     *
     *   slides 1..N-1 (current < total - 1)  -> setSlide(current + 1)
     *   final slide   (current === total - 1) -> navigateTo('list')
     *
     * `exiting` is a one-shot latch: once a "forward off the deck"
     * gesture has fired, every subsequent advance attempt is a no-op
     * until the user re-enters /atlas. This prevents a fast double-
     * click or held arrow key from queueing a second navigateTo()
     * after the route has already flipped to /list, and it also
     * prevents the wrap-level click from racing the routed-page click
     * (since the wrap is hidden but the click event is already in
     * flight by the time the route changes).
     * --------------------------------------------------------------- */
    var exiting = false;
    function advance(gesture) {
      if (exiting) return;
      /* An aside is not part of the run: a forward gesture closes it and
       * puts the presenter back where they left off, rather than stepping
       * into whatever section happens to sit next in the markup. */
      if (appendixOpen) { closeAppendix(); return; }
      /* A slide may own the "next" gesture before the deck does: the
       * presenter-driven slides use click, Space and ArrowRight to advance
       * grouped states in place before normal deck navigation resumes. */
      if (atlasSlideConsumes(slides[current], gesture || "click")) return;
      if (current < total - 1) {
        setSlide(current + 1);
        return;
      }
      /* On the last slide, the next forward gesture enters the
       * Rate Card Manager landing page. */
      exiting = true;
      navigateTo('list');
    }
    function retreat() {
      if (exiting) return;
      if (appendixOpen) { closeAppendix(); return; }
      if (atlasSlideConsumes(slides[current], "back")) return;
      if (current > 0) setSlide(current - 1);
      /* On slide 1, ArrowLeft is a no-op (spec). */
    }

    /* Click anywhere on the empty slide canvas advances. The final
     * slide's brand-mark CTA still has its own pointer-events: auto
     * target inside the SVG; its handler stopPropagation()s so we never
     * double-trigger (CTA-click + wrap-click would otherwise both call
     * navigateTo). The shared guard is the second line of that defence:
     * a control that forgets to stop the event is still not an advance.
     *
     * The closing card is deliberately not a wrap-around. A forward
     * gesture there walks into the Rate Card Manager, which is the
     * deck's way in to the product, so there is no dead end to rescue. */
    if (wrap) {
      wrap.addEventListener('click', function(event){
        if (presentationClickIsInteractive(event, wrap)) return;
        advance('click');
      });
    }

    /* Keyboard navigation - scoped to the Atlas route. The handler
     * stays registered for the lifetime of the page, but the
     * data-route guard at the top of the function silently no-ops
     * once the user leaves /atlas, so it never reaches the rest of
     * the app after navigation. */
    document.addEventListener('keydown', function(e){
      if (document.body.getAttribute('data-route') !== 'atlas') return;
      /* Defensive: ignore when focus is on a form field. There are
       * none on /atlas today, but this future-proofs the deck. */
      var tag = (e.target && e.target.tagName) || '';
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
      /* A focused link or button owns Enter and Space. The closing card's
       * three links are real anchors, and the deck must not swallow the
       * keystroke that activates them. */
      if ((tag === 'A' || tag === 'BUTTON') &&
          (e.key === 'Enter' || e.key === ' ' || e.key === 'Spacebar')) return;
      if (e.key === 'Enter') {
        /* Enter is not a deck gesture. It exists so a slide that runs its
         * own walkthrough can be started from the keyboard without also
         * being the key that skips past it. */
        if (atlasSlideConsumes(slides[current], 'enter')) e.preventDefault();
      } else if (e.key === 'ArrowRight' || e.key === ' ' || e.key === 'Spacebar' || e.key === 'PageDown') {
        e.preventDefault();
        advance(e.key === ' ' || e.key === 'Spacebar' ? 'space' : 'arrow');
      } else if (e.key === 'ArrowLeft' || e.key === 'PageUp') {
        e.preventDefault();
        retreat();
      } else if (e.key === 'Home') {
        e.preventDefault();
        if (!exiting) setSlide(0);
      } else if (e.key === 'End') {
        e.preventDefault();
        if (!exiting) setSlide(total - 1);
      } else if (e.key === 'Escape') {
        /* Escape returns to the Rate Card Manager - natural "exit
         * presentation" gesture. Same latch keeps it single-shot. */
        e.preventDefault();
        /* Inside an appendix, Escape means "close the aside", not "leave
         * the deck". Leaving still works, one Escape later. */
        if (appendixOpen) { closeAppendix(); return; }
        if (exiting) return;
        exiting = true;
        navigateTo('list');
      }
    });

    /* Re-arm the exit latch if the user navigates BACK into /atlas
     * (e.g. via the global nav). Hooked into the existing route
     * observer above so we don't allocate a second MutationObserver. */
    onAtlasRouteEnter = function(){ exiting = false; };

    /* External "reset to slide 1" hook. The Rate Card brand lockup in
     * the top nav dispatches 'atlas:reset' immediately after routing
     * to /atlas so the deck opens on slide 1 regardless of the last
     * viewed slide. Also clears the exit latch so a follow-up
     * ArrowRight/click still advances (which it wouldn't if the user
     * had previously exited off slide N via the wrap click). Kept
     * inside initAtlasDeck so we can reach the closure-scoped
     * setSlide()/exiting without exposing them on window. */
    document.addEventListener('atlas:reset', function(){
      exiting = false;
      setSlide(0);
    });

    /* Final-slide brand-mark CTA: still enters the Rate Card Manager
     * directly. stopPropagation prevents the wrap-level click from
     * also firing advance() (which would re-trigger navigateTo via
     * the exit latch path). preventDefault() keeps the <button>'s
     * default focus/scroll behavior from interfering with the route
     * change animation. */
    var enter = deck.querySelector('[data-atlas-enter]');
    if (enter) {
      enter.addEventListener('click', function(e){
        e.preventDefault();
        e.stopPropagation();
        if (exiting) return;
        exiting = true;
        navigateTo('list');
      });
    }

    /* -----------------------------------------------------------------
     * Closing-card links.
     *
     * Both handlers stop propagation, and that is the whole point of
     * binding them on the elements rather than on the deck: the canvas-
     * wide advance handler sits on .atlas-stage-wrap, which is an
     * ancestor, so without this a click on a link would open the link
     * AND move the presentation underneath it.
     * --------------------------------------------------------------- */
    Array.prototype.forEach.call(
      deck.querySelectorAll('[data-atlas-appendix-link]'),
      function (link) {
        link.addEventListener('click', function (e) {
          e.preventDefault();
          e.stopPropagation();
          openAppendix(slideById(link.getAttribute('data-atlas-appendix-link')));
        });
      }
    );

    /* The prototype link keeps its default action (new tab) and only needs
     * the advance handler held off. */
    Array.prototype.forEach.call(
      deck.querySelectorAll('[data-atlas-external]'),
      function (link) {
        link.addEventListener('click', function (e) { e.stopPropagation(); });
      }
    );

    if (backBtn) {
      backBtn.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        closeAppendix();
      });
    }

    /* Initial paint */
    if (bootAppendix) openAppendix(bootAppendix);
    else setSlide(current);
  }

  // ----- Live Rate Card Layer Explainer --------------------------------------
  // Reparents the version 2.0 editor without changing its data or state.
  function initExplodedRateCardLayerDiagram(overlay) {
    var panel = overlay.querySelector('.rcle__panel');
    var diagram = overlay.querySelector('.rcle__diagram');
    var liveSlot = overlay.querySelector('[data-rcle-live-slot]');
    var productFrame = overlay.querySelector('[data-rcle-product-frame]');
    var calloutSvg = overlay.querySelector('[data-rcle-callouts]');
    var v2Root = document.querySelector('[data-v2-root]');
    var listView = overlay.querySelector('[data-rcle-list-view]');
    var listSlot = overlay.querySelector('[data-rcle-list-live-slot]');
    var listFrame = overlay.querySelector('[data-rcle-list-frame]');
    var listCalloutSvg = overlay.querySelector('[data-rcle-list-callouts]');
    var listRoot = document.querySelector('[data-page="list"]');
    var explainerTitle = overlay.querySelector('#rcle-title');
    var explainerSubtitle = overlay.querySelector('#rcle-subtitle');
    var slidePanels = Array.prototype.slice.call(
      overlay.querySelectorAll('[data-rcle-slide-panel]')
    );
    var slidePrevBtn = overlay.querySelector('[data-rcle-slide-prev]');
    var slideNextBtn = overlay.querySelector('[data-rcle-slide-next]');
    var slideIndicator = overlay.querySelector('[data-rcle-slide-indicator]');
    /* 2026-08-04 previous-design references. The view toggle + the
     * previous-design frame / prototype are optional: if the HTML
     * hasn't been updated yet the explainer still opens the carousel
     * without the view swap. setView() is a no-op in that case. */
    var viewToggle = overlay.querySelector('[data-rcle-view-toggle]');
    var previousView = overlay.querySelector('[data-rcle-previous-view]');
    var previousFrame = overlay.querySelector('[data-rcle-previous-frame]');
    var previousPrototype = overlay.querySelector('[data-rcle-previous-prototype]');
    if (!panel || !diagram || !liveSlot || !productFrame || !calloutSvg ||
        !v2Root || !listView || !listSlot || !listFrame || !listCalloutSvg ||
        !listRoot || !explainerTitle || !explainerSubtitle ||
        slidePanels.length !== 3 || !slidePrevBtn || !slideNextBtn ||
        !slideIndicator) {
      return;
    }

    var lastFocused = null;
    var savedScroll = { x: 0, y: 0 };
    var placeholder = null;
    var inertSiblings = [];
    var liveStateSnapshot = null;
    var controlSnapshot = [];
    var scrollSnapshot = [];
    var mutationObserver = null;
    var resizeObserver = null;
    var renderFrame = 0;
    var rootWasInert = false;
    var activeMode = '';
    var listRootWasInert = false;
    var listControlSnapshot = [];
    var listScrollSnapshot = [];
    var presentationIdSnapshot = [];
    /* Carousel state (2026-08-04 carousel revision).
     *
     * The three pricing layers are now shown one at a time via a
     * carousel. currentSlide is 1-based (matches data-rcle-slide-panel
     * values and the 01/02/03 markers). SLIDE_COUNT is fixed because
     * the pricing hierarchy is a 3-tier concept: Rate Card Details ->
     * Line Item Details -> Premium Adjustments. */
    var SLIDE_COUNT = 3;
    var currentSlide = 1;
    /* The list state tells the same three-beat story, so it reuses the
     * carousel's Previous/Next contract rather than inventing a second
     * one. Only the annotation moves; the live list is never filtered,
     * reordered or navigated by the reveal. */
    var LIST_STEP_COUNT = 3;
    var listStep = 1;

    /* Detail-mode sub-view (2026-08-04 previous-design brief).
     *
     * The detail explainer has two full-screen sub-views that swap in
     * place via setView():
     *
     *   'current'  -> three-slide carousel (Rate Card / Line / Premium)
     *   'previous' -> full-page reconstruction of Figma node 523:8884
     *
     * currentSlide is preserved across the swap so returning to the
     * carousel lands on whichever slide the user last viewed. List
     * mode ignores this state entirely (there is no previous view for
     * the list). */
    var currentView = 'current';
    var VIEW_CURRENT = 'current';
    var VIEW_PREVIOUS = 'previous';

    /* Per-slide live-product target: which accordion is expanded and
     * which region the red marker points at. Kept next to the copy so
     * the "what's expanded, what's highlighted" contract is legible.
     *
     * accordion:  data-v2-accordion value to expand for this slide.
     * target():   returns the live element the callout ring wraps and
     *             the leader line lands next to (or an array if the
     *             annotation spans multiple regions). Called lazily so
     *             it always reflects the current DOM after the slide's
     *             accordion has been opened. */
    /* When a slide's accordion is expanded, wrap the entire accordion
     * (trigger + panel) so the red ring visibly covers everything the
     * slide is teaching. Fall back to just the trigger row for the
     * (transient) state before the accordion has finished opening,
     * so the ring always has a measurable target. */
    function buildAccordionTarget(section) {
      return function () {
        var expanded = v2Root.querySelector(
          '[data-v2-accordion="' + section + '"].is-open'
        );
        if (expanded) return expanded;
        return v2Root.querySelector(
          '[data-v2-accordion="' + section + '"] .create-md__accordion-trigger'
        );
      };
    }

    /* Secondary target: the table region on the left side of the
     * frame (Line items table for slide 2, Premiums table for slide
     * 3). Slide 2 / 3 use one numbered marker + two connector lines
     * so the reader understands the layer spans both the existing
     * records table and the add-or-edit form. Falls back to the
     * surrounding tab panel while the table is still empty / loading
     * so the ring always has a measurable target. */
    function buildTableTarget(region) {
      return function () {
        var tableRegion = v2Root.querySelector(
          '[data-v2-table-region="' + region + '"]'
        );
        if (tableRegion && !tableRegion.hidden) return tableRegion;
        var panel = v2Root.querySelector('[data-v2-panel="' + region + '"]');
        if (!panel || panel.hidden) return null;
        var empty = panel.querySelector('[data-v2-empty="' + region + '"]');
        if (empty && !empty.hidden) return empty;
        var noResults = panel.querySelector(
          '[data-v2-no-results="' + region + '"]'
        );
        if (noResults && !noResults.hidden) return noResults;
        return panel;
      };
    }

    /* Slide 1 uses primary-only (single ring on the CARD accordion).
     * Slides 2 / 3 add a secondary target so the annotation covers
     * both the existing-records table and the add-or-edit form. See
     * setSlideAccordion for the tab-selection logic that keeps the
     * correct table visible. */
    var slideConfigs = {
      /* Slide 1 demonstrates the real Edit rate card modal rather than a
       * CARD accordion. The modal is the product's own component, opened
       * through the same entry point a user would use, so what the
       * audience sees is what ships. */
      1: {
        tab: 'lines',
        modal: true,
        target: function () {
          var modal = document.querySelector('[data-rc-create-modal]');
          return modal && !modal.hidden
            ? modal.querySelector('.modal__panel')
            : v2Root.querySelector('[data-v2-edit-card-link]');
        }
      },
      2: {
        accordion: 'line',
        tab: 'lines',
        record: 'lines',
        target: buildAccordionTarget('line'),
        targetSecondary: buildTableTarget('lines')
      },
      3: {
        accordion: 'premium',
        tab: 'premiums',
        record: 'premiums',
        target: buildAccordionTarget('premium'),
        targetSecondary: buildTableTarget('premiums')
      }
    };

    /* Presentation edits live only for the length of the presentation.
     * The rate card files store is the one thing the modal writes to, so
     * it is snapshotted on open and put back on close: a presenter can
     * type, Confirm, and see real validation without the seeded demo
     * data being different afterwards. */
    var presentationDataSnapshot = null;
    var V2_FILES_KEY = 'rate-card-manager.v2.files';

    function capturePresentationData() {
      try {
        presentationDataSnapshot = window.localStorage.getItem(V2_FILES_KEY);
      } catch (_) {
        presentationDataSnapshot = null;
      }
    }

    function restorePresentationData() {
      if (presentationDataSnapshot === null) return;
      try {
        if (window.localStorage.getItem(V2_FILES_KEY) !== presentationDataSnapshot) {
          window.localStorage.setItem(V2_FILES_KEY, presentationDataSnapshot);
        }
      } catch (_) { /* nothing to put back if storage is unavailable */ }
      presentationDataSnapshot = null;
    }

    function isOpen() {
      return !overlay.hidden;
    }

    function isEligible() {
      var route = document.body.getAttribute('data-route');
      return route === 'list' || (
        route === 'create' &&
        isV2Family(document.body.getAttribute('data-version'))
      );
    }

    function isEditable(target) {
      if (!target || target.nodeType !== 1) return false;
      return Boolean(target.closest(
        "input, textarea, select, [contenteditable]:not([contenteditable='false']), " +
        "[role='textbox'], .CodeMirror, .monaco-editor, .ace_editor"
      ));
    }

    function visibleFocusables() {
      return Array.prototype.slice.call(overlay.querySelectorAll(
        "button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), " +
        "textarea:not([disabled]), [tabindex]:not([tabindex='-1'])"
      )).filter(function (element) {
        return !element.closest('[hidden], [inert]') &&
          element.getClientRects().length > 0;
      });
    }

    function setBackgroundInert(inert) {
      if (inert) {
        inertSiblings = Array.prototype.slice.call(overlay.parentElement.children)
          .filter(function (element) {
            return element !== overlay && !element.matches('script, style, link');
          })
          .map(function (element) {
            var state = {
              element: element,
              inert: element.inert,
              ariaHidden: element.getAttribute('aria-hidden')
            };
            element.inert = true;
            element.setAttribute('aria-hidden', 'true');
            return state;
          });
        return;
      }
      inertSiblings.forEach(function (state) {
        state.element.inert = state.inert;
        if (state.ariaHidden === null) state.element.removeAttribute('aria-hidden');
        else state.element.setAttribute('aria-hidden', state.ariaHidden);
      });
      inertSiblings = [];
    }

    function setMode(mode) {
      activeMode = mode;
      overlay.setAttribute('data-rcle-mode', mode);
      overlay.querySelectorAll('[data-rcle-detail-view]').forEach(function (element) {
        element.hidden = mode !== 'detail';
      });
      overlay.querySelectorAll('[data-rcle-list-view]').forEach(function (element) {
        element.hidden = mode !== 'list';
      });
      /* Detail-mode title/subtitle are per-slide (carousel) or
       * per-view (previous). List mode still uses the single
       * data-rcle-list-* pair. When switching into detail mode we
       * always land on the current sub-view; setView() rewires the
       * current / previous-view element visibility and the header. */
      if (mode === 'list') {
        explainerTitle.textContent =
          explainerTitle.getAttribute('data-rcle-list-title');
        explainerSubtitle.textContent =
          explainerSubtitle.getAttribute('data-rcle-list-subtitle');
        /* The list state runs the same three-beat reveal, so it keeps
         * the shared Previous/Next control rather than hiding it. */
        var listNav = overlay.querySelector('[data-rcle-carousel-nav]');
        if (listNav) listNav.hidden = false;
        goToListStep(1);
      } else {
        setView(VIEW_CURRENT);
      }
    }

    function syncSlideHeader() {
      var slideTitle = explainerTitle.getAttribute(
        'data-rcle-slide-' + currentSlide + '-title'
      );
      var slideSubtitle = explainerSubtitle.getAttribute(
        'data-rcle-slide-' + currentSlide + '-subtitle'
      );
      explainerTitle.textContent = slideTitle ||
        explainerTitle.getAttribute('data-rcle-detail-title');
      explainerSubtitle.textContent = slideSubtitle ||
        explainerSubtitle.getAttribute('data-rcle-detail-subtitle');
    }

    /* Swap between the carousel (VIEW_CURRENT) and the previous-design
     * reconstruction (VIEW_PREVIOUS). Called from setMode('detail')
     * (which forces current on open) and from the header view-toggle
     * click. Safe to call when the previous-design markup is missing
     * (older HTML), in which case VIEW_PREVIOUS is treated as a no-op
     * and the toggle button is left disabled. */
    function setView(view) {
      if (activeMode !== 'detail') return;
      if (view === VIEW_PREVIOUS && !previousView) view = VIEW_CURRENT;
      currentView = view;
      overlay.setAttribute('data-rcle-view', view);
      overlay.querySelectorAll('[data-rcle-current-view]').forEach(function (element) {
        element.hidden = view !== VIEW_CURRENT;
      });
      overlay.querySelectorAll('[data-rcle-previous-view]').forEach(function (element) {
        element.hidden = view !== VIEW_PREVIOUS;
      });
      /* Header text swaps per view:
       *   current  -> per-slide carousel copy (data-rcle-slide-N-*)
       *   previous -> the fixed "Previous Design" title + the muted
       *               supporting-explanation subtitle. */
      if (view === VIEW_PREVIOUS) {
        var prevTitle = explainerTitle.getAttribute('data-rcle-previous-title');
        var prevSub = explainerSubtitle.getAttribute('data-rcle-previous-subtitle');
        if (prevTitle) explainerTitle.textContent = prevTitle;
        if (prevSub) explainerSubtitle.textContent = prevSub;
      } else {
        syncSlideHeader();
      }
      /* Sync the toggle button label + a11y state. The two labels come
       * from data attributes so we don't have to hard-code them here. */
      if (viewToggle) {
        var isPrevious = view === VIEW_PREVIOUS;
        var labelCurrent = viewToggle.getAttribute('data-rcle-label-current')
          || 'Previous design';
        var labelPrevious = viewToggle.getAttribute('data-rcle-label-previous')
          || 'Current design';
        viewToggle.textContent = isPrevious ? labelPrevious : labelCurrent;
        viewToggle.setAttribute('aria-pressed', isPrevious ? 'true' : 'false');
        viewToggle.setAttribute(
          'data-rcle-target-view', isPrevious ? VIEW_CURRENT : VIEW_PREVIOUS
        );
      }
      /* Render tasks differ by view: the current view needs the
       * callout SVG (marker / connector), the previous view needs the
       * prototype re-scaled to fit the frame. Both are deferred to
       * requestAnimationFrame so the hidden->shown layout is stable. */
      if (view === VIEW_PREVIOUS) {
        requestAnimationFrame(function () {
          fitPreviousPrototype();
          applyMinimumPresentationText();
        });
      } else {
        applyMinimumPresentationText();
        scheduleRender();
      }
    }

    /* Compute a proportional zoom for the previous-design prototype.
     * The prototype is 1440 px wide at natural size; --rcle-prev-scale
     * is the multiplier applied to it via CSS `zoom` (layout-aware, so
     * the scroll container sees the scaled dimensions).
     *
     * We never scale above 1 -- the natural 1440 px width is already
     * the largest the design supports -- so on wider viewports the
     * prototype simply fills the available width without upscaling
     * and blurring the labels. */
    function fitPreviousPrototype() {
      if (!previousFrame || !previousPrototype) return;
      var frameWidth = previousFrame.clientWidth;
      if (!frameWidth) return;
      var scale = Math.min(frameWidth / 1440, 1);
      previousPrototype.style.setProperty(
        '--rcle-prev-scale', String(scale)
      );
    }

    function applyMinimumPresentationText() {
      overlay.querySelectorAll('[data-rcle-min-text]').forEach(function (element) {
        element.removeAttribute('data-rcle-min-text');
      });
      overlay.querySelectorAll('*').forEach(function (element) {
        if (element.closest('[hidden]') || !element.getClientRects().length) return;
        var hasDirectText = Array.prototype.some.call(
          element.childNodes,
          function (node) {
            return node.nodeType === Node.TEXT_NODE &&
              Boolean(node.textContent && node.textContent.trim());
          }
        );
        var isTextControl = element.matches(
          'input, textarea, select, option'
        );
        if (!hasDirectText && !isTextControl) return;
        var fontSize = parseFloat(window.getComputedStyle(element).fontSize);
        if (isFinite(fontSize) && fontSize < 14) {
          element.setAttribute('data-rcle-min-text', '');
        }
      });
    }

    function clearMinimumPresentationText() {
      overlay.querySelectorAll('[data-rcle-min-text]').forEach(function (element) {
        element.removeAttribute('data-rcle-min-text');
      });
    }

    function ensureUniquePresentationSvgIds() {
      presentationIdSnapshot = [];
      var seen = Object.create(null);
      var duplicateIndex = 0;
      overlay.querySelectorAll('svg [id]').forEach(function (element) {
        var originalId = element.id;
        if (!originalId) return;
        if (!seen[originalId]) {
          seen[originalId] = true;
          return;
        }
        duplicateIndex += 1;
        var uniqueId = 'rcle-' + duplicateIndex + '-' + originalId;
        var svg = element.closest('svg');
        var references = [];
        if (svg) {
          svg.querySelectorAll('*').forEach(function (candidate) {
            Array.prototype.forEach.call(candidate.attributes || [], function (attribute) {
              if (attribute.value.indexOf('#' + originalId) === -1) return;
              references.push({
                element: candidate,
                name: attribute.name,
                value: attribute.value
              });
              candidate.setAttribute(
                attribute.name,
                attribute.value.replaceAll('#' + originalId, '#' + uniqueId)
              );
            });
          });
        }
        presentationIdSnapshot.push({
          element: element,
          id: originalId,
          references: references
        });
        element.id = uniqueId;
      });
    }

    function restorePresentationSvgIds() {
      presentationIdSnapshot.forEach(function (entry) {
        entry.references.forEach(function (reference) {
          reference.element.setAttribute(reference.name, reference.value);
        });
        entry.element.id = entry.id;
      });
      presentationIdSnapshot = [];
    }

    function captureListState() {
      listControlSnapshot = Array.prototype.slice.call(
        listRoot.querySelectorAll('input, select, textarea')
      ).map(function (control) {
        return {
          control: control,
          value: control.value,
          checked: control.checked,
          selectedIndex: control.selectedIndex
        };
      });
      listScrollSnapshot = [listRoot].concat(Array.prototype.slice.call(
        listRoot.querySelectorAll('*')
      )).filter(function (element) {
        return element.scrollTop || element.scrollLeft;
      }).map(function (element) {
        return {
          element: element,
          top: element.scrollTop,
          left: element.scrollLeft
        };
      });
    }

    function restoreListState() {
      listControlSnapshot.forEach(function (snapshot) {
        if (!snapshot.control.isConnected) return;
        snapshot.control.value = snapshot.value;
        snapshot.control.checked = snapshot.checked;
        if (snapshot.control.matches('select')) {
          snapshot.control.selectedIndex = snapshot.selectedIndex;
        }
      });
      listScrollSnapshot.forEach(function (snapshot) {
        if (!snapshot.element.isConnected) return;
        snapshot.element.scrollTop = snapshot.top;
        snapshot.element.scrollLeft = snapshot.left;
      });
      listControlSnapshot = [];
      listScrollSnapshot = [];
    }

    function captureLiveState() {
      liveStateSnapshot = null;
      v2Root.dispatchEvent(new CustomEvent('rcle:capture-state', {
        detail: {
          receive: function (state) {
            liveStateSnapshot = state;
          }
        }
      }));
      controlSnapshot = Array.prototype.slice.call(
        v2Root.querySelectorAll('input, select, textarea')
      ).map(function (control) {
        return {
          control: control,
          value: control.value,
          checked: control.checked,
          selectedIndex: control.selectedIndex
        };
      });
      scrollSnapshot = [v2Root].concat(Array.prototype.slice.call(
        v2Root.querySelectorAll('*')
      )).filter(function (element) {
        return element.scrollTop || element.scrollLeft;
      }).map(function (element) {
        return {
          element: element,
          top: element.scrollTop,
          left: element.scrollLeft
        };
      });
    }

    function restoreLiveState() {
      if (liveStateSnapshot) {
        v2Root.dispatchEvent(new CustomEvent('rcle:restore-state', {
          detail: { state: liveStateSnapshot }
        }));
      }
      controlSnapshot.forEach(function (snapshot) {
        if (!snapshot.control.isConnected) return;
        snapshot.control.value = snapshot.value;
        snapshot.control.checked = snapshot.checked;
        if (snapshot.control.matches('select')) {
          snapshot.control.selectedIndex = snapshot.selectedIndex;
        }
      });
      scrollSnapshot.forEach(function (snapshot) {
        if (!snapshot.element.isConnected) return;
        snapshot.element.scrollTop = snapshot.top;
        snapshot.element.scrollLeft = snapshot.left;
      });
      liveStateSnapshot = null;
      controlSnapshot = [];
      scrollSnapshot = [];
    }

    function cleanText(element, fallback) {
      var value = element && String(element.textContent || '')
        .replace(/^Selected\.\s*/i, '')
        .trim();
      return value || fallback;
    }

    function controlValue(selector, fallback) {
      var control = v2Root.querySelector(selector);
      return control && String(control.value || '').trim() || fallback;
    }

    function setExplainerText(selector, value) {
      var element = overlay.querySelector(selector);
      if (element) element.textContent = value;
    }

    /* syncExtractedFragments was removed with the 2026-08-04 carousel
     * revision: slide contents are now static illustrative examples
     * (see the three <article data-rcle-slide-panel> blocks in
     * index.html) rather than live-derived values, so the teaching
     * frame reads clearly even before the user has entered anything.
     * cleanText / controlValue / setExplainerText are still used by
     * other paths in this init closure so they intentionally remain. */

    function intersectRect(rect, clip, origin) {
      if (!rect || !clip) return null;
      var left = Math.max(rect.left, clip.left);
      var top = Math.max(rect.top, clip.top);
      var right = Math.min(rect.right, clip.right);
      var bottom = Math.min(rect.bottom, clip.bottom);
      if (right <= left || bottom <= top) return null;
      return {
        left: left - origin.left,
        top: top - origin.top,
        right: right - origin.left,
        bottom: bottom - origin.top,
        width: right - left,
        height: bottom - top
      };
    }

    /* renderConnector was rewritten with the 2026-08-04 carousel
     * revision, then extended for the 2026-08 Adam / Alex pass to
     * support an optional secondary target so slides 2 and 3 can
     * annotate BOTH the existing-records table (on the left of the
     * frame) and the add-or-edit form (on the right) with one
     * numbered marker. There is a single SVG group ([data-rcle-
     * callout="active"]) that is retargeted per slide. The primary
     * connector draws an L-elbow from the current slide card's
     * inner edge to the primary ring's far edge, with the marker
     * sitting at the elbow so the reading order is "explanation
     * card -> red leader -> red marker -> red ring on the live UI".
     * When a secondary target is provided, a second connector runs
     * from the same marker up along the top gutter of the frame and
     * lands just above the secondary ring's top edge, so the line
     * never crosses table text. */
    function renderConnector(target, card, diagramRect, frameRect, secondary) {
      var group = calloutSvg.querySelector('[data-rcle-callout="active"]');
      var scrim = calloutSvg.querySelector('[data-rcle-scrim]');
      if (!group) return;
      var targets = Array.isArray(target) ? target : (target ? [target] : []);
      var validTargets = targets.filter(function (element) {
        return element && !element.closest('[hidden]');
      });
      if (!validTargets.length || !card) {
        group.hidden = true;
        if (scrim) scrim.setAttribute('d', '');
        return;
      }
      var rawRect = validTargets.length === 1
        ? validTargets[0].getBoundingClientRect()
        : unionClientRect(validTargets);
      var sourceRect = intersectRect(rawRect, frameRect, diagramRect);
      var cardRect = card.getBoundingClientRect();
      if (!sourceRect || !cardRect.width || !cardRect.height) {
        group.hidden = true;
        if (scrim) scrim.setAttribute('d', '');
        return;
      }

      /* Every coordinate below is derived from the live target's own
       * bounding rect, so the annotation follows the product at any
       * viewport rather than sitting at a remembered position. */
      var frameLeft = frameRect.left - diagramRect.left;
      var frameTop = frameRect.top - diagramRect.top;
      var frameRight = frameRect.right - diagramRect.left;
      var frameBottom = frameRect.bottom - diagramRect.top;
      var PAD = 6;
      var focus = {
        left: Math.max(frameLeft, sourceRect.left - PAD),
        top: Math.max(frameTop, sourceRect.top - PAD),
        right: Math.min(frameRight, sourceRect.left + sourceRect.width + PAD),
        bottom: Math.min(frameBottom, sourceRect.top + sourceRect.height + PAD)
      };

      group.hidden = false;

      /* Outer subpath is the whole frame, inner subpath is the focus
       * region, both wound the same way so evenodd leaves the focus
       * unpainted. The product underneath keeps full opacity there. */
      if (scrim) {
        scrim.setAttribute('d', [
          'M', frameLeft, frameTop,
          'H', frameRight, 'V', frameBottom, 'H', frameLeft, 'Z',
          'M', Math.round(focus.left), Math.round(focus.top),
          'H', Math.round(focus.right),
          'V', Math.round(focus.bottom),
          'H', Math.round(focus.left), 'Z'
        ].join(' '));
      }

      var ring = group.querySelector('[data-rcle-callout-target]');
      var line = group.querySelector('[data-rcle-callout-line]');
      var secondaryRing = group.querySelector(
        '[data-rcle-slide-callout-target-secondary]'
      );
      var secondaryLine = group.querySelector(
        '[data-rcle-slide-callout-line-secondary]'
      );
      var marker = group.querySelector('[data-rcle-callout-marker]');
      var label = group.querySelector('[data-rcle-callout-number]');

      ring.setAttribute('x', String(Math.round(focus.left)));
      ring.setAttribute('y', String(Math.round(focus.top)));
      ring.setAttribute('width',
        String(Math.max(0, Math.round(focus.right - focus.left))));
      ring.setAttribute('height',
        String(Math.max(0, Math.round(focus.bottom - focus.top))));

      /* One thin leader from the focus ring toward the copy. It stops
       * short of the text so it can never run through a word, and it
       * travels along the focus region's own vertical centre so it
       * reads as belonging to that region. */
      var cardOnLeft = cardRect.right <= frameRect.left;
      var ringEdgeX = cardOnLeft ? focus.left : focus.right;
      /* Stop partway across the gutter rather than at a measured card
       * edge. The copy shifts by a few pixels once its offset applies,
       * and a leader aimed at that edge could land on the first word;
       * the gutter is by definition empty. */
      var frameEdgeX = cardOnLeft
        ? frameRect.left - diagramRect.left
        : frameRect.right - diagramRect.left;
      var gutter = cardOnLeft
        ? (frameRect.left - cardRect.right)
        : (cardRect.left - frameRect.right);
      var copyEdgeX = cardOnLeft
        ? frameEdgeX - gutter * 0.55
        : frameEdgeX + gutter * 0.55;
      var leaderY = Math.round((focus.top + focus.bottom) / 2);
      var runsTowardCopy = cardOnLeft ? copyEdgeX < ringEdgeX : copyEdgeX > ringEdgeX;
      if (runsTowardCopy) {
        line.removeAttribute('hidden');
        line.setAttribute('d', [
          'M', Math.round(ringEdgeX), leaderY,
          'H', Math.round(copyEdgeX)
        ].join(' '));
      } else {
        line.setAttribute('hidden', '');
      }

      /* The floating numbered circle is gone: the step number lives in
       * the copy, and a second numeral in the gutter only competed with
       * it. The secondary ring is gone too, because ringing a whole
       * table alongside the form highlighted two things at once. */
      if (marker) marker.setAttribute('hidden', '');
      if (label) label.setAttribute('hidden', '');
      if (secondaryRing) secondaryRing.setAttribute('hidden', '');
      if (secondaryLine) secondaryLine.setAttribute('hidden', '');

      /* Sit the copy's first line with the region it describes, rather
       * than with the top of the whole frame, and never let it push
       * past the bottom of the composition. */
      var carousel = overlay.querySelector('[data-rcle-carousel]');
      if (carousel) {
        var available = Math.max(0, diagramRect.height - cardRect.height);
        var offset = Math.max(0, Math.min(focus.top, available));
        carousel.style.setProperty('--rcle-copy-offset', Math.round(offset) + 'px');
      }
    }

    function renderDiagram() {
      renderFrame = 0;
      if (!isOpen() || activeMode !== 'detail') return;
      var diagramRect = diagram.getBoundingClientRect();
      var frameRect = productFrame.getBoundingClientRect();
      if (!diagramRect.width || !diagramRect.height) return;
      calloutSvg.setAttribute(
        'viewBox',
        '0 0 ' + Math.round(diagramRect.width) + ' ' + Math.round(diagramRect.height)
      );
      calloutSvg.setAttribute('width', String(Math.round(diagramRect.width)));
      calloutSvg.setAttribute('height', String(Math.round(diagramRect.height)));

      var config = slideConfigs[currentSlide];
      var activeCard = overlay.querySelector(
        '[data-rcle-slide-panel="' + currentSlide + '"]'
      );
      if (!config || !activeCard) return;
      var secondary = typeof config.targetSecondary === 'function'
        ? config.targetSecondary()
        : null;
      renderConnector(
        config.target(),
        activeCard,
        diagramRect,
        frameRect,
        secondary
      );
    }

    function scheduleRender() {
      if (renderFrame) cancelAnimationFrame(renderFrame);
      renderFrame = requestAnimationFrame(function () {
        renderDiagram();
      });
    }

    /* Bring the live wizard into the state the current slide
     * illustrates. Only the target accordion is expanded; the others
     * are collapsed. The v2 accordion widget's own openAccordion path
     * closes siblings when it opens one, so we only need explicit
     * close calls for accordions that must be closed when the target
     * accordion is already open (edge cases where clicking would
     * toggle the same section closed). */
    function setSlideAccordion(slideIndex) {
      var config = slideConfigs[slideIndex];
      if (!config) return;
      /* Slide 1 + 2 sit on the "Line items" tab so the Line items
       * table stays visible on the left. Slide 3 switches to the
       * "Premiums" tab so the Premiums table becomes the visible
       * secondary annotation target. */
      var tabName = config.tab || 'lines';
      var tab = v2Root.querySelector('[data-v2-tab="' + tabName + '"]');
      if (tab && tab.getAttribute('aria-selected') !== 'true') {
        tab.click();
      }
      /* Only one editing surface at a time. Leaving slide 1 closes the
       * modal; entering it closes the Line Details panel first so the
       * modal is not sitting on top of a second editor. */
      if (!config.modal) {
        closeRcCreateModal();
        unmountPresentationCardModal();
      } else {
        var panelClose = v2Root.querySelector('[data-v2-action="close-panel"]');
        if (panelClose && v2Root.querySelector('.create-md.is-panel-open')) {
          panelClose.click();
        }
      }
      var targetSection = config.accordion;
      var sections = ['card', 'line', 'premium'];
      sections.forEach(function (section) {
        var accordion = v2Root.querySelector(
          '[data-v2-accordion="' + section + '"]'
        );
        if (!accordion) return;
        var isOpenSection = accordion.classList.contains('is-open');
        var trigger = accordion.querySelector('.create-md__accordion-trigger');
        if (!trigger) return;
        if (section === targetSection && !isOpenSection) {
          trigger.click();
        } else if (section !== targetSection && isOpenSection) {
          trigger.click();
        }
      });

      if (config.record) openPresentationRecord(config.record);

      if (config.modal) openPresentationCardModal();
    }

    /* Opens the details panel on a real row rather than the blank "add"
     * form the section trigger gives you. The slide is explaining what a
     * saved record looks like, so the panel has to hold one, and the row
     * it came from has to be the highlighted one. */
    function openPresentationRecord(region) {
      var table = v2Root.querySelector(
        '[data-v2-table-region="' + region + '"]'
      );
      if (!table) return;
      var row = table.querySelector('tbody [data-v2-row-id]');
      if (!row) return;
      if (row.classList.contains('is-selected')
          && v2Root.querySelector('.create-md.is-panel-open')) return;
      /* The checkbox cell selects for bulk actions; any other cell opens
       * the row. */
      var cell = Array.prototype.filter.call(row.children, function (td) {
        return String(td.className).indexOf('checkbox') === -1;
      })[0];
      if (cell) cell.click();
      revealPresentationConditions();
    }

    /* The conditions field is the last one in the panel, so on a form
     * taller than the frame it starts below the fold. These slides are
     * about that field, so bring it into view once the panel has
     * painted. */
    function revealPresentationConditions() {
      window.requestAnimationFrame(function () {
        var field = v2Root.querySelector('.create-md__detail [data-conditions]');
        if (!field) return;
        var scroller = field.parentElement;
        while (scroller && scroller.scrollHeight <= scroller.clientHeight + 1) {
          scroller = scroller.parentElement;
        }
        if (scroller) scroller.scrollTop = scroller.scrollHeight;
      });
    }

    /* Opens the product's own Edit rate card modal through the page's
     * normal entry point. Re-entering the slide reopens it with the demo
     * values, because presentation edits are rolled back on close. */
    /* The modal is a body-level sibling, which the presentation makes
     * inert and paints behind its own overlay. To show it as the live
     * product component it is, it is moved into the product frame for
     * the length of this slide and put back afterwards. */
    var cardModalPlaceholder = null;

    function mountPresentationCardModal() {
      var modal = document.querySelector('[data-rc-create-modal]');
      if (!modal || cardModalPlaceholder) return;
      cardModalPlaceholder = document.createComment('rcle-card-modal');
      modal.parentNode.insertBefore(cardModalPlaceholder, modal);
      productFrame.appendChild(modal);
      modal.inert = false;
      modal.removeAttribute('aria-hidden');
      modal.classList.add('is-presented');
    }

    function unmountPresentationCardModal() {
      var modal = document.querySelector('[data-rc-create-modal]');
      if (!modal || !cardModalPlaceholder) return;
      modal.classList.remove('is-presented');
      if (cardModalPlaceholder.parentNode) {
        cardModalPlaceholder.parentNode.insertBefore(modal, cardModalPlaceholder);
        cardModalPlaceholder.parentNode.removeChild(cardModalPlaceholder);
      }
      cardModalPlaceholder = null;
    }

    function openPresentationCardModal() {
      var modal = document.querySelector('[data-rc-create-modal]');
      if (modal && !modal.hidden) return;
      if (typeof window.openEditRateCardModal !== 'function') return;
      var cardId = '';
      try {
        cardId = new URL(window.location.href).searchParams.get('cardId') || '';
      } catch (_) { cardId = ''; }
      if (!cardId) return;
      /* Calls the product's own modal rather than clicking the header
       * link, because the link is a 2.1 affordance and the presentation
       * runs on 2.0 as well. Same function the link invokes, so the
       * audience sees the shipping component either way. */
      var trigger = v2Root.querySelector('[data-v2-edit-card-link]')
        || v2Root.querySelector('[data-v2-title]');
      window.openEditRateCardModal(cardId, trigger);
      mountPresentationCardModal();
      /* Focus the heading rather than the first field. Presentation
       * navigation is arrow keys, and arrows inside a text input mean
       * "move the caret", so landing in a field would have made Next
       * and Previous unreachable from the keyboard. A presenter who
       * clicks into a field still gets normal text behaviour. */
      var heading = document.querySelector('[data-rc-create-modal] .modal__title');
      if (heading) {
        heading.setAttribute('tabindex', '-1');
        /* After the modal's own initial focus, which lands a frame
         * later on the first field. */
        window.requestAnimationFrame(function () {
          window.requestAnimationFrame(function () {
            var modalNow = document.querySelector('[data-rc-create-modal]');
            if (modalNow && !modalNow.hidden) heading.focus({ preventScroll: true });
          });
        });
      }
      scheduleRender();
    }

    /* preparePresentationState is called from open(). It hands off to
     * setSlideAccordion for the currently-active slide so the wizard
     * is already in the correct state before the callout SVG is drawn. */
    function preparePresentationState() {
      setSlideAccordion(currentSlide);
    }

    /* Carousel controller: swap the visible slide, sync the header
     * copy, update accordion state, and redraw the callout. direction
     * ("next" | "prev" | "") drives the horizontal enter animation.
     * Called from clicks on the arrow buttons, Left/Right arrow keys,
     * and open() (which resets to slide 1 with direction ""). */
    function goToSlide(nextIndex, direction) {
      if (activeMode === 'list') return goToListStep(nextIndex);
      var clamped = Math.max(1, Math.min(SLIDE_COUNT, nextIndex));
      if (clamped === currentSlide && direction) return;
      currentSlide = clamped;
      slidePanels.forEach(function (panelEl) {
        var index = Number(panelEl.getAttribute('data-rcle-slide-panel'));
        var active = index === currentSlide;
        panelEl.hidden = !active;
        panelEl.setAttribute('aria-hidden', active ? 'false' : 'true');
        panelEl.classList.remove('rcle__slide--enter-next');
        panelEl.classList.remove('rcle__slide--enter-prev');
        if (active && direction === 'next') {
          panelEl.classList.add('rcle__slide--enter-next');
        } else if (active && direction === 'prev') {
          panelEl.classList.add('rcle__slide--enter-prev');
        }
      });
      slidePrevBtn.disabled = currentSlide === 1;
      slideNextBtn.disabled = currentSlide === SLIDE_COUNT;
      slidePrevBtn.setAttribute(
        'aria-disabled', currentSlide === 1 ? 'true' : 'false'
      );
      slideNextBtn.setAttribute(
        'aria-disabled', currentSlide === SLIDE_COUNT ? 'true' : 'false'
      );
      slideIndicator.textContent = currentSlide + ' of ' + SLIDE_COUNT;
      overlay.setAttribute('data-rcle-slide', String(currentSlide));
      if (activeMode === 'detail') {
        syncSlideHeader();
        setSlideAccordion(currentSlide);
        applyMinimumPresentationText();
        scheduleRender();
      }
    }

    function goToListStep(nextIndex) {
      var clamped = Math.max(1, Math.min(LIST_STEP_COUNT, nextIndex));
      listStep = clamped;
      slidePrevBtn.disabled = listStep === 1;
      slideNextBtn.disabled = listStep === LIST_STEP_COUNT;
      slidePrevBtn.setAttribute(
        'aria-disabled', listStep === 1 ? 'true' : 'false'
      );
      slideNextBtn.setAttribute(
        'aria-disabled', listStep === LIST_STEP_COUNT ? 'true' : 'false'
      );
      slideIndicator.textContent = listStep + ' of ' + LIST_STEP_COUNT;
      overlay.setAttribute('data-rcle-list-step', String(listStep));
      renderListDiagram();
    }

    function unionClientRect(elements) {
      var rects = [];
      elements.forEach(function (element) {
        if (!element) return;
        // Range objects (used to target text substrings such as the
        // year inside a rate-card name) support getBoundingClientRect
        // but not closest / hidden checks; treat them as always visible.
        if (typeof element.closest === 'function'
            && element.closest('[hidden]')) return;
        var rect = element.getBoundingClientRect();
        if (rect.width > 0 && rect.height > 0) rects.push(rect);
      });
      if (!rects.length) return null;
      return {
        left: Math.min.apply(null, rects.map(function (rect) { return rect.left; })),
        top: Math.min.apply(null, rects.map(function (rect) { return rect.top; })),
        right: Math.max.apply(null, rects.map(function (rect) { return rect.right; })),
        bottom: Math.max.apply(null, rects.map(function (rect) { return rect.bottom; }))
      };
    }

    /* The frame is sized to what the list actually renders, not to the
     * space the stage happens to offer. The page keeps a tall surface
     * below its pagination, so filling the row left a white band under
     * the footer that grew with the viewport: 174px at 1920. */
    var appliedListScale = 1;
    var appliedListFrameHeight = 0;
    var LIST_FRAME_PAD = 16;

    function fitListRoot() {
      var stage = listFrame.parentElement;
      if (!stage) return;
      var availWidth = stage.clientWidth;
      var availHeight = stage.clientHeight;
      if (!availWidth || !availHeight) return;

      var content = listRoot.querySelector('.page__inner')
        || listRoot.querySelector('.card')
        || listRoot;
      /* The scale lands on listRoot, which CSS pins to a fixed width, so
       * that is the width it has to be measured against. Measuring the
       * inner content instead scaled a narrower number and then applied it
       * to the wider root, so the root rendered past its frame and the
       * right-hand columns were cut off once the frame was narrow enough
       * for the width term to bind. offsetWidth is the layout width and
       * ignores the transform already on the element. */
      var naturalWidth = Math.max(
        960,
        listRoot.offsetWidth || 0,
        content.scrollWidth || 0
      );

      /* Everything worth showing ends at the pagination footer. Measured
       * through the live rects and divided by the scale already applied,
       * because the root is transformed and its rect is not in page
       * units. */
      var rootRect = listRoot.getBoundingClientRect();
      /* Anchor on the pagination controls rather than the footer
       * element, whose own bottom padding would be added to the gap and
       * push it past the intended band. The footer is hidden entirely
       * when everything fits on one page, so fall back to the last row,
       * then to the content: measuring a hidden element would report a
       * zero rect and collapse the frame. */
      var anchorRect = null;
      var candidates = [
        listRoot.querySelector('[data-pager]'),
        listRoot.querySelector('.table__body .row:last-child'),
        listRoot.querySelector('[data-empty]:not([hidden])'),
        content
      ];
      for (var i = 0; i < candidates.length; i++) {
        if (!candidates[i]) continue;
        var candidateRect = candidates[i].getBoundingClientRect();
        if (candidateRect.height > 0) { anchorRect = candidateRect; break; }
      }
      if (!anchorRect) return;
      var usefulHeight = appliedListScale > 0
        ? (anchorRect.bottom - rootRect.top) / appliedListScale
        : anchorRect.bottom - rootRect.top;
      if (!(usefulHeight > 0)) usefulHeight = content.scrollHeight || 560;

      /* Width sets the scale; height only ever reduces it, so the whole
       * list is visible without a row being cut in half. */
      var scale = Math.min(availWidth / naturalWidth, 1);
      var maxContent = availHeight - LIST_FRAME_PAD;
      if (usefulHeight * scale > maxContent) {
        scale = Math.max(0.1, maxContent / usefulHeight);
      }

      var frameHeight = Math.min(
        availHeight,
        Math.round(usefulHeight * scale) + LIST_FRAME_PAD
      );

      /* The frame is observed for resize, so writing an unchanged value
       * would spin the observer. */
      if (Math.abs(scale - appliedListScale) > 0.001) {
        appliedListScale = scale;
        listRoot.style.setProperty('--rcle-list-scale', String(scale));
      }
      if (Math.abs(frameHeight - appliedListFrameHeight) > 1) {
        appliedListFrameHeight = frameHeight;
        listFrame.style.setProperty('--rcle-list-frame-h', frameHeight + 'px');
      }
      // Force a synchronous layout flush so subsequent getBoundingClientRect
      // calls reflect the new transform on the reparented list root.
      void listRoot.offsetWidth;
    }

    // 2026-08-05: dropped the red source-ring outline and the leader-line
    // connector entirely. The badge alone now carries the association
    // between callout card and product area, so it is centered directly
    // above its target with a small fixed gap instead of anchoring to the
    // target's corner (which only made sense as a line's endpoint).
    var LIST_BADGE_W = 30;
    var LIST_BADGE_H = 22;
    var LIST_BADGE_GAP = 10; // px between the badge bottom and the target top

    /* One representative row carries steps 02 and 03, so the audience
     * follows a single rate card through "confirm it" and "open it"
     * rather than being shown a whole column of them. */
    function listStepTargets(step) {
      var row = listRoot.querySelector('.table__body .row');
      if (step === 1) {
        return [
          listRoot.querySelector('[aria-label="Filter rate cards"]')
            || listRoot.querySelector('.filter-btn'),
          listRoot.querySelector('[data-main-search]')
            || listRoot.querySelector('.search')
        ].filter(Boolean);
      }
      if (!row) return [];
      if (step === 2) {
        /* Status, Marketplace, Buying Entity and Version in that one
         * row. Effective dates are deliberately absent: this screen
         * does not show them, so there is nothing to point at. */
        return Array.prototype.slice.call(row.querySelectorAll(
          '.cell--status, .cell--marketplace, .cell--buying-entity, .cell--ver'
        ));
      }
      return [row.querySelector('.name__link') || row.querySelector('.cell--name-id')]
        .filter(Boolean);
    }

    function renderListDiagram() {
      if (!isOpen() || activeMode !== 'list') return;
      fitListRoot();
      var listRect = listView.getBoundingClientRect();
      var frameRect = listFrame.getBoundingClientRect();
      if (!listRect.width || !listRect.height || !frameRect.width) return;
      listCalloutSvg.setAttribute(
        'viewBox',
        '0 0 ' + Math.round(listRect.width) + ' ' + Math.round(listRect.height)
      );
      listCalloutSvg.setAttribute('width', String(Math.round(listRect.width)));
      listCalloutSvg.setAttribute('height', String(Math.round(listRect.height)));

      var scrim = listCalloutSvg.querySelector('[data-rcle-list-scrim]');
      var ring = listCalloutSvg.querySelector('[data-rcle-list-ring]');
      var line = listCalloutSvg.querySelector('[data-rcle-list-line]');
      var step = listStep;

      /* Mark the active step in the rail. The other two stay legible but
       * recede, so the whole story is readable at a glance while one
       * point is being made. */
      var activePanel = null;
      Array.prototype.forEach.call(
        overlay.querySelectorAll('[data-rcle-list-step]'),
        function (panel) {
          var on = panel.getAttribute('data-rcle-list-step') === String(step);
          panel.classList.toggle('is-active', on);
          if (on) activePanel = panel;
        }
      );

      var targets = listStepTargets(step).filter(function (node) {
        return node && !node.closest('[hidden]');
      });
      if (!targets.length) {
        if (scrim) scrim.setAttribute('d', '');
        if (ring) ring.setAttribute('hidden', '');
        if (line) line.setAttribute('hidden', '');
        return;
      }
      var sourceRect = intersectRect(
        unionClientRect(targets), frameRect, listRect
      );
      if (!sourceRect || !sourceRect.width || !sourceRect.height) {
        if (scrim) scrim.setAttribute('d', '');
        if (ring) ring.setAttribute('hidden', '');
        if (line) line.setAttribute('hidden', '');
        return;
      }

      var frameLeft = frameRect.left - listRect.left;
      var frameTop = frameRect.top - listRect.top;
      var frameRight = frameRect.right - listRect.left;
      var frameBottom = frameRect.bottom - listRect.top;
      var PAD = 6;
      var focus = {
        left: Math.max(frameLeft, sourceRect.left - PAD),
        top: Math.max(frameTop, sourceRect.top - PAD),
        right: Math.min(frameRight, sourceRect.right + PAD),
        bottom: Math.min(frameBottom, sourceRect.bottom + PAD)
      };

      if (scrim) {
        scrim.setAttribute('d', [
          'M', Math.round(frameLeft), Math.round(frameTop),
          'H', Math.round(frameRight),
          'V', Math.round(frameBottom),
          'H', Math.round(frameLeft), 'Z',
          'M', Math.round(focus.left), Math.round(focus.top),
          'H', Math.round(focus.right),
          'V', Math.round(focus.bottom),
          'H', Math.round(focus.left), 'Z'
        ].join(' '));
      }

      if (ring) {
        ring.removeAttribute('hidden');
        ring.setAttribute('x', String(Math.round(focus.left)));
        ring.setAttribute('y', String(Math.round(focus.top)));
        ring.setAttribute('width',
          String(Math.max(0, Math.round(focus.right - focus.left))));
        ring.setAttribute('height',
          String(Math.max(0, Math.round(focus.bottom - focus.top))));
      }

      /* A single leader for the active step, stopping partway across the
       * gutter. Only one is ever drawn, so two lines cannot cross, and
       * it never reaches the copy. */
      if (line && activePanel) {
        var railRect = activePanel.getBoundingClientRect();
        var gutter = Math.max(0, (railRect.left - frameRect.right));
        var stopX = frameRight + gutter * 0.55;
        var y = Math.round((focus.top + focus.bottom) / 2);
        if (gutter > 12) {
          line.removeAttribute('hidden');
          line.setAttribute('d', [
            'M', Math.round(focus.right), y,
            'H', Math.round(stopX)
          ].join(' '));
        } else {
          line.setAttribute('hidden', '');
        }
      }
    }

    function scheduleListRender() {
      if (renderFrame) cancelAnimationFrame(renderFrame);
      renderFrame = requestAnimationFrame(function () {
        renderFrame = 0;
        renderListDiagram();
      });
    }

    function connectListOpenState() {
      overlay.addEventListener('scroll', scheduleListRender, true);
      window.addEventListener('resize', scheduleListRender);
      mutationObserver = new MutationObserver(scheduleListRender);
      mutationObserver.observe(listRoot, {
        subtree: true,
        childList: true,
        characterData: true,
        attributes: true,
        attributeFilter: ['class', 'hidden', 'aria-sort', 'aria-selected']
      });
      if (typeof ResizeObserver === 'function') {
        resizeObserver = new ResizeObserver(scheduleListRender);
        [panel, listView, listFrame, listRoot].forEach(function (element) {
          resizeObserver.observe(element);
        });
      }
    }

    function connectOpenState() {
      overlay.addEventListener('scroll', scheduleRender, true);
      window.addEventListener('resize', scheduleRender);
      mutationObserver = new MutationObserver(scheduleRender);
      mutationObserver.observe(v2Root, {
        subtree: true,
        childList: true,
        characterData: true,
        attributes: true,
        attributeFilter: ['class', 'hidden', 'aria-selected', 'aria-expanded']
      });
      if (typeof ResizeObserver === 'function') {
        resizeObserver = new ResizeObserver(scheduleRender);
        [panel, diagram, productFrame, v2Root].forEach(function (element) {
          resizeObserver.observe(element);
        });
      }
    }

    function disconnectOpenState() {
      overlay.removeEventListener('scroll', scheduleRender, true);
      overlay.removeEventListener('scroll', scheduleListRender, true);
      window.removeEventListener('resize', scheduleRender);
      window.removeEventListener('resize', scheduleListRender);
      if (mutationObserver) mutationObserver.disconnect();
      if (resizeObserver) resizeObserver.disconnect();
      mutationObserver = null;
      resizeObserver = null;
      if (renderFrame) cancelAnimationFrame(renderFrame);
      renderFrame = 0;
    }

    function open() {
      if (isOpen() || !isEligible()) return;
      var listMode = document.body.getAttribute('data-route') === 'list';
      var root = listMode ? listRoot : v2Root;
      var slot = listMode ? listSlot : liveSlot;
      if (!root.parentNode) return;
      lastFocused = document.activeElement;
      savedScroll = { x: window.scrollX, y: window.scrollY };
      if (listMode) captureListState();
      else captureLiveState();
      capturePresentationData();
      placeholder = document.createComment('rcle-live-root');
      root.parentNode.insertBefore(placeholder, root);
      slot.appendChild(root);
      /* Reset the carousel to slide 1 (Rate Card Details) whenever the
       * detail explainer opens so the teaching flow always starts at
       * the top of the pricing hierarchy. Direction is intentionally
       * "" so the initial paint doesn't apply an enter animation.
       * currentView is also reset to VIEW_CURRENT so a previously
       * lingering previous-design view never bleeds into a fresh open
       * (setMode -> setView(VIEW_CURRENT) enforces this as well; the
       * assignment here just keeps the JS state coherent before
       * setMode runs). */
      if (!listMode) {
        currentSlide = 1;
        currentView = VIEW_CURRENT;
        goToSlide(1, '');
      }
      setMode(listMode ? 'list' : 'detail');
      document.body.classList.add('rcle-open');
      document.body.classList.toggle('rcle-list-open', listMode);
      overlay.hidden = false;
      setBackgroundInert(true);
      if (listMode) {
        listRootWasInert = listRoot.inert;
        listRoot.inert = true;
        connectListOpenState();
      } else {
        rootWasInert = v2Root.inert;
        preparePresentationState();
        v2Root.inert = true;
        connectOpenState();
      }
      requestAnimationFrame(function () {
        if (!isOpen()) return;
        ensureUniquePresentationSvgIds();
        applyMinimumPresentationText();
        panel.focus({ preventScroll: true });
        if (listMode) scheduleListRender();
        else scheduleRender();
      });
    }

    function close() {
      if (!isOpen()) return;
      /* The Edit rate card modal is a real product component, so a
       * presenter can type in it. Closing it and rolling the store back
       * is what keeps a demo from editing the seeded rate card. */
      closeRcCreateModal();
      unmountPresentationCardModal();
      restorePresentationData();
      disconnectOpenState();
      var listMode = activeMode === 'list';
      var root = listMode ? listRoot : v2Root;
      if (listMode) listRoot.inert = listRootWasInert;
      else v2Root.inert = rootWasInert;
      if (placeholder && placeholder.parentNode) {
        placeholder.parentNode.insertBefore(root, placeholder.nextSibling);
        placeholder.remove();
      }
      placeholder = null;
      if (listMode) {
        listRoot.style.removeProperty('--rcle-list-scale');
        restoreListState();
      } else {
        restoreLiveState();
      }
      /* Reset the previous-design prototype zoom so the next open
       * doesn't inherit a stale scale from a smaller viewport. Also
       * force the view state back to current so any consumer that
       * inspects currentView after close sees a clean slate. */
      if (previousPrototype) {
        previousPrototype.style.removeProperty('--rcle-prev-scale');
      }
      currentView = VIEW_CURRENT;
      overlay.removeAttribute('data-rcle-view');
      clearMinimumPresentationText();
      restorePresentationSvgIds();
      setBackgroundInert(false);
      document.body.classList.remove('rcle-open');
      document.body.classList.remove('rcle-list-open');
      overlay.hidden = true;
      window.scrollTo(savedScroll.x, savedScroll.y);
      if (lastFocused && lastFocused.isConnected &&
          typeof lastFocused.focus === 'function') {
        try {
          lastFocused.focus({ preventScroll: true });
        } catch (_) {
          lastFocused.focus();
        }
      }
      window.scrollTo(savedScroll.x, savedScroll.y);
      lastFocused = null;
      activeMode = '';
    }

    overlay.querySelectorAll('[data-rcle-close]').forEach(function (button) {
      button.addEventListener('click', function (event) {
        event.preventDefault();
        close();
      });
    });

    /* Carousel navigation buttons. Prev / next are also disabled at
     * the ends via the goToSlide side-effects, but we defensively
     * guard here so a stale enabled state can't advance out of range. */
    function stepBy(delta, direction) {
      if (activeMode === 'list') {
        var nextStep = listStep + delta;
        if (nextStep >= 1 && nextStep <= LIST_STEP_COUNT) goToListStep(nextStep);
        return;
      }
      var next = currentSlide + delta;
      if (next >= 1 && next <= SLIDE_COUNT) goToSlide(next, direction);
    }
    slidePrevBtn.addEventListener('click', function (event) {
      event.preventDefault();
      stepBy(-1, 'prev');
    });
    slideNextBtn.addEventListener('click', function (event) {
      event.preventDefault();
      stepBy(1, 'next');
    });

    /* Click-to-advance, the same gesture the Atlas deck answers to.
     *
     * Two regions are deliberately not advance targets. The live product
     * frame is the running prototype, which owns its own clicks and is
     * the thing being demonstrated. The previous-design comparison has
     * no carousel behind it to step through.
     *
     * Where the arrow buttons stop at the ends, a click wraps: the
     * buttons show their limits by going disabled, but a click on the
     * backdrop has no such tell, so it returns to the first step rather
     * than quietly doing nothing. */
    var ADVANCE_BLOCKED = [
      '[data-rcle-product-frame]',
      '[data-rcle-live-slot]',
      '[data-rcle-list-live-slot]',
      '[data-rcle-carousel-nav]',
      '.rcle__header-actions'
    ].join(',');

    panel.addEventListener('click', function (event) {
      if (!isOpen()) return;
      if (activeMode === 'detail' && currentView !== VIEW_CURRENT) return;
      if (presentationClickIsInteractive(event, panel, ADVANCE_BLOCKED)) return;
      if (activeMode === 'list') {
        goToListStep(listStep < LIST_STEP_COUNT ? listStep + 1 : 1);
        return;
      }
      goToSlide(currentSlide < SLIDE_COUNT ? currentSlide + 1 : 1, 'next');
    });

    /* Header view toggle: "Previous design" / "Current design". Reads
     * data-rcle-target-view (rewritten by setView) so the click always
     * flips to the opposite view without needing to know the current
     * state here. The button is hidden in list mode via
     * data-rcle-detail-view. */
    if (viewToggle) {
      viewToggle.addEventListener('click', function (event) {
        event.preventDefault();
        var target = viewToggle.getAttribute('data-rcle-target-view')
          || VIEW_PREVIOUS;
        setView(target);
      });
    }

    /* Keep the previous-design prototype fitted to whatever width the
     * frame currently has (viewport resize, orientation change, etc.).
     * Cheap to run: fitPreviousPrototype early-returns unless we're in
     * the previous view, and the setProperty is a no-op when the value
     * doesn't change. */
    window.addEventListener('resize', function () {
      if (isOpen() && activeMode === 'detail' && currentView === VIEW_PREVIOUS) {
        fitPreviousPrototype();
      }
    });

    document.addEventListener('keydown', function (event) {
      var printShortcut = (event.key === 'p' || event.key === 'P') &&
        (event.ctrlKey || event.metaKey) && !event.shiftKey && !event.altKey;
      if (printShortcut && isOpen()) {
        event.preventDefault();
        event.stopImmediatePropagation();
        close();
        return;
      }
      if (printShortcut && isEligible() && !isEditable(event.target)) {
        event.preventDefault();
        event.stopImmediatePropagation();
        open();
        return;
      }
      if (!isOpen()) return;
      if (event.key === 'Escape') {
        event.preventDefault();
        event.stopImmediatePropagation();
        close();
        return;
      }
      /* Left / Right arrow keys drive the carousel in detail mode
       * only. Modifier keys are excluded so browser / OS shortcuts
       * (Alt+Left = back, etc.) continue to work, and text-field
       * focus is excluded so caret navigation inside the reparented
       * live UI is never hijacked. List mode has no carousel. */
      if (activeMode === 'detail' && !event.altKey && !event.ctrlKey &&
          !event.metaKey && !event.shiftKey && !isEditable(event.target)) {
        if (event.key === 'ArrowRight' && currentSlide < SLIDE_COUNT) {
          event.preventDefault();
          event.stopImmediatePropagation();
          goToSlide(currentSlide + 1, 'next');
          return;
        }
        if (event.key === 'ArrowLeft' && currentSlide > 1) {
          event.preventDefault();
          event.stopImmediatePropagation();
          goToSlide(currentSlide - 1, 'prev');
          return;
        }
      }
      if (event.key !== 'Tab') return;
      var focusables = visibleFocusables();
      if (!focusables.length) {
        event.preventDefault();
        panel.focus({ preventScroll: true });
        return;
      }
      var first = focusables[0];
      var last = focusables[focusables.length - 1];
      var active = document.activeElement;
      if (event.shiftKey && (active === first || active === panel ||
          !overlay.contains(active))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (active === last ||
          !overlay.contains(active))) {
        event.preventDefault();
        first.focus();
      }
    }, true);

    new MutationObserver(function () {
      if (isOpen() && !isEligible()) close();
    }).observe(document.body, {
      attributes: true,
      attributeFilter: ['data-route', 'data-version']
    });

    // Small global API so the profile menu's "Presentation view" row can
    // open the same overlay the Cmd/Ctrl+P shortcut opens. open() itself
    // already infers list vs. detail from data-route, so the caller does
    // not need to know which presentation to show.
    window.RateCardPresentationView = {
      open: open,
      close: close,
      isOpen: isOpen,
      isEligible: isEligible
    };
  }

  function initRateCardLayerExplainer() {
    var overlay = document.querySelector('[data-rcle]');
    if (overlay && overlay.hasAttribute('data-rcle-exploded')) {
      initExplodedRateCardLayerDiagram(overlay);
      return;
    }
    var panel = overlay && overlay.querySelector('.rcle__panel');
    var liveSlot = overlay && overlay.querySelector('[data-rcle-live-slot]');
    var productViewport = overlay && overlay.querySelector('[data-rcle-product-viewport]');
    var v2Root = document.querySelector('[data-v2-root]');
    var layerButtons = overlay && overlay.querySelectorAll('[data-rcle-layer-option]');
    var copy = overlay && overlay.querySelector('[data-rcle-copy]');
    var layerLabel = overlay && overlay.querySelector('[data-rcle-layer-label]');
    var sectionTitle = overlay && overlay.querySelector('[data-rcle-section-title]');
    var definition = overlay && overlay.querySelector('[data-rcle-definition]');
    var seeingList = overlay && overlay.querySelector('[data-rcle-seeing-list]');
    var calloutLegend = overlay && overlay.querySelector('[data-rcle-callout-legend]');
    var calloutSvg = overlay && overlay.querySelector('[data-rcle-callouts]');
    if (!overlay || !panel || !liveSlot || !productViewport || !v2Root ||
        !layerButtons || !copy || !layerLabel || !sectionTitle || !definition ||
        !seeingList || !calloutLegend || !calloutSvg) return;

    var productFrame = productViewport.closest('[data-rcle-product-frame]');
    var layerCopy = {
      card: {
        label: 'Layer 1',
        title: 'Rate Card Details',
        definition: 'Sets the deal context shared by its line items and premiums.',
        bullets: [
          'Marketplace and buyer define who the rate card applies to.',
          'Deal season and effective dates define when it applies.',
          'The Rate Card ID connects its line items and premiums.'
        ]
      },
      line: {
        label: 'Layer 2',
        title: 'Line Items',
        definition: 'Each row defines inventory and its negotiated base rate.',
        bullets: [
          'Each table row represents one negotiated base rate.',
          'Advertiser and offering identify where the rate applies.',
          'Select a row to review its details and related premiums.'
        ]
      },
      premium: {
        label: 'Layer 3',
        title: 'Premium Adjustments',
        definition: 'Each premium adjusts a base rate when its conditions match.',
        bullets: [
          'Each row defines one premium adjustment.',
          'Method and value define how the rate changes.',
          'Conditions determine when the premium applies.'
        ]
      }
    };
    var lastFocused = null;
    var savedScroll = { x: 0, y: 0 };
    var placeholder = null;
    var mutationObserver = null;
    var resizeObserver = null;
    var calloutFrame = 0;
    var syncFrame = 0;
    var syncLayerHint = null;
    var changeFrame = 0;
    var changeToken = 0;
    var inertSiblings = [];
    var liveStateSnapshot = null;
    var controlSnapshot = [];
    var scrollSnapshot = [];

    function isOpen() {
      return !overlay.hidden;
    }

    function isEligible() {
      return document.body.getAttribute('data-route') === 'create' &&
        isV2Family(document.body.getAttribute('data-version'));
    }

    function isEditable(target) {
      if (!target || target.nodeType !== 1) return false;
      return Boolean(target.closest(
        "input, textarea, select, [contenteditable]:not([contenteditable='false']), " +
        "[role='textbox'], .CodeMirror, .monaco-editor, .ace_editor"
      ));
    }

    function visibleFocusables() {
      return Array.prototype.slice.call(overlay.querySelectorAll(
        "button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), " +
        "textarea:not([disabled]), [tabindex]:not([tabindex='-1'])"
      )).filter(function (element) {
        return !element.closest('[hidden]') && element.getClientRects().length > 0;
      });
    }

    function setBackgroundInert(inert) {
      if (inert) {
        inertSiblings = Array.prototype.slice.call(overlay.parentElement.children)
          .filter(function (element) {
            return element !== overlay &&
              !element.matches('script, style, link');
          })
          .map(function (element) {
            var state = {
              element: element,
              inert: element.inert,
              ariaHidden: element.getAttribute('aria-hidden')
            };
            element.inert = true;
            element.setAttribute('aria-hidden', 'true');
            return state;
          });
        return;
      }
      inertSiblings.forEach(function (state) {
        state.element.inert = state.inert;
        if (state.ariaHidden === null) state.element.removeAttribute('aria-hidden');
        else state.element.setAttribute('aria-hidden', state.ariaHidden);
      });
      inertSiblings = [];
    }

    function captureLiveState() {
      liveStateSnapshot = null;
      v2Root.dispatchEvent(new CustomEvent('rcle:capture-state', {
        detail: {
          receive: function (state) {
            liveStateSnapshot = state;
          }
        }
      }));
      controlSnapshot = Array.prototype.slice.call(
        v2Root.querySelectorAll('input, select, textarea')
      ).map(function (control) {
        return {
          control: control,
          value: control.value,
          checked: control.checked,
          selectedIndex: control.selectedIndex
        };
      });
      scrollSnapshot = [v2Root].concat(Array.prototype.slice.call(
        v2Root.querySelectorAll('*')
      )).filter(function (element) {
        return element.scrollTop || element.scrollLeft;
      }).map(function (element) {
        return {
          element: element,
          top: element.scrollTop,
          left: element.scrollLeft
        };
      });
    }

    function restoreLiveState() {
      if (liveStateSnapshot) {
        v2Root.dispatchEvent(new CustomEvent('rcle:restore-state', {
          detail: { state: liveStateSnapshot }
        }));
      }
      controlSnapshot.forEach(function (snapshot) {
        if (!snapshot.control.isConnected) return;
        snapshot.control.value = snapshot.value;
        snapshot.control.checked = snapshot.checked;
        if (snapshot.control.matches('select')) {
          snapshot.control.selectedIndex = snapshot.selectedIndex;
        }
      });
      scrollSnapshot.forEach(function (snapshot) {
        if (!snapshot.element.isConnected) return;
        snapshot.element.scrollTop = snapshot.top;
        snapshot.element.scrollLeft = snapshot.left;
      });
      liveStateSnapshot = null;
      controlSnapshot = [];
      scrollSnapshot = [];
    }

    function setLayer(layer, options) {
      var next = layerCopy[layer] ? layer : 'card';
      var content = layerCopy[next];
      overlay.setAttribute('data-rcle-layer', next);
      Array.prototype.forEach.call(layerButtons, function (button) {
        var active = button.getAttribute('data-rcle-layer-option') === next;
        button.classList.toggle('is-active', active);
        if (active) button.setAttribute('aria-current', 'true');
        else button.removeAttribute('aria-current');
      });
      layerLabel.textContent = content.label;
      sectionTitle.textContent = content.title;
      definition.textContent = content.definition;
      seeingList.replaceChildren();
      content.bullets.forEach(function (bullet) {
        var item = document.createElement('li');
        item.textContent = bullet;
        seeingList.appendChild(item);
      });
      calloutLegend.hidden = next !== 'line';
      if (next !== 'line') {
        calloutSvg.hidden = true;
        [1, 2, 3].forEach(function (number) {
          hideCallout(calloutSvg.querySelector(
            '[data-rcle-callout="' + number + '"]'
          ));
        });
      }

      changeToken += 1;
      var token = changeToken;
      copy.classList.add('is-changing');
      if (changeFrame) cancelAnimationFrame(changeFrame);
      changeFrame = requestAnimationFrame(function () {
        changeFrame = requestAnimationFrame(function () {
          if (token === changeToken) copy.classList.remove('is-changing');
          changeFrame = 0;
        });
      });
      if (!(options && options.skipCallouts)) scheduleCallouts();
    }

    function layerFromLiveState() {
      var openAccordion = v2Root.querySelector(
        '[data-v2-accordion].is-open, [data-v2-accordion] > ' +
        '.create-md__accordion-trigger[aria-expanded="true"]'
      );
      if (openAccordion) {
        var accordion = openAccordion.matches('[data-v2-accordion]')
          ? openAccordion
          : openAccordion.closest('[data-v2-accordion]');
        var section = accordion && accordion.getAttribute('data-v2-accordion');
        if (section === 'card' || section === 'line' || section === 'premium') {
          return section;
        }
      }
      var activeTab = v2Root.querySelector(
        '[data-v2-tab][aria-selected="true"], [data-v2-tab].is-selected'
      );
      return activeTab && activeTab.getAttribute('data-v2-tab') === 'premiums'
        ? 'premium'
        : 'line';
    }

    function elementIsVisible(element) {
      if (!element || element.closest('[hidden]')) return false;
      var rect = element.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0;
    }

    function unionFor(elements, panelRect) {
      var rects = elements.filter(elementIsVisible).map(function (element) {
        return element.getBoundingClientRect();
      });
      if (!rects.length) return null;
      var left = Math.min.apply(null, rects.map(function (rect) { return rect.left; }));
      var top = Math.min.apply(null, rects.map(function (rect) { return rect.top; }));
      var right = Math.max.apply(null, rects.map(function (rect) { return rect.right; }));
      var bottom = Math.max.apply(null, rects.map(function (rect) { return rect.bottom; }));
      return {
        left: left - panelRect.left,
        top: top - panelRect.top,
        right: right - panelRect.left,
        bottom: bottom - panelRect.top,
        width: right - left,
        height: bottom - top
      };
    }

    function intersectRects(rect, clip) {
      if (!rect || !clip) return null;
      var left = Math.max(rect.left, clip.left);
      var top = Math.max(rect.top, clip.top);
      var right = Math.min(rect.right, clip.right);
      var bottom = Math.min(rect.bottom, clip.bottom);
      if (right <= left || bottom <= top) return null;
      return {
        left: left,
        top: top,
        right: right,
        bottom: bottom,
        width: right - left,
        height: bottom - top
      };
    }

    function visibleRectOrEdge(rect, clip) {
      var visible = intersectRects(rect, clip);
      if (visible || !rect || !clip) return visible;
      var top = Math.max(rect.top, clip.top);
      var bottom = Math.min(rect.bottom, clip.bottom);
      if (bottom <= top) return null;
      var left = rect.left >= clip.right
        ? clip.right - 3
        : clip.left;
      return {
        left: left,
        top: top,
        right: left + 3,
        bottom: bottom,
        width: 3,
        height: bottom - top
      };
    }

    function setRect(rectElement, rect) {
      if (!rectElement) return;
      rectElement.hidden = !rect;
      if (!rect) return;
      rectElement.setAttribute('x', String(Math.round(rect.left - 2)));
      rectElement.setAttribute('y', String(Math.round(rect.top - 2)));
      rectElement.setAttribute('width', String(Math.round(rect.width + 4)));
      rectElement.setAttribute('height', String(Math.round(rect.height + 4)));
    }

    function pathTo(start, target, laneX, laneY, secondary, markerPoint) {
      var markerX = markerPoint ? markerPoint.x : target.left - 12;
      var markerY = markerPoint
        ? markerPoint.y
        : target.top + target.height / 2;
      return {
        markerX: markerX,
        markerY: markerY,
        d: [
          'M', Math.round(start.x), Math.round(start.y),
          'H', Math.round(laneX),
          'V', Math.round(laneY),
          'H', Math.round(markerX),
          'V', Math.round(markerY)
        ].join(' ')
      };
    }

    function hideCallout(group) {
      if (!group) return;
      group.hidden = true;
      var secondaryRect = group.querySelector('[data-rcle-callout-target-secondary]');
      var secondaryLine = group.querySelector('[data-rcle-callout-line-secondary]');
      if (secondaryRect) secondaryRect.hidden = true;
      if (secondaryLine) secondaryLine.hidden = true;
    }

    function drawCallout(
      number,
      primary,
      secondary,
      panelRect,
      frameRect,
      markerPoint
    ) {
      var group = calloutSvg.querySelector('[data-rcle-callout="' + number + '"]');
      var label = overlay.querySelector('[data-rcle-callout-label="' + number + '"]');
      if (!group || !label || !primary || !elementIsVisible(label)) {
        hideCallout(group);
        return;
      }
      var labelRect = label.getBoundingClientRect();
      var start = {
        x: labelRect.right - panelRect.left,
        y: labelRect.top + labelRect.height / 2 - panelRect.top
      };
      var laneX = frameRect.left - panelRect.left + 10;
      var laneY = frameRect.top - panelRect.top + 12 + (number - 1) * 6;
      var primaryPath = pathTo(
        start,
        primary,
        laneX,
        laneY,
        false,
        markerPoint
      );
      var primaryRect = group.querySelector('[data-rcle-callout-target]');
      var primaryLine = group.querySelector('[data-rcle-callout-line]');
      var secondaryRect = group.querySelector('[data-rcle-callout-target-secondary]');
      var secondaryLine = group.querySelector('[data-rcle-callout-line-secondary]');
      var marker = group.querySelector('[data-rcle-callout-marker]');
      var textNode = group.querySelector('[data-rcle-callout-number]');

      group.hidden = false;
      setRect(primaryRect, primary);
      if (primaryLine) primaryLine.setAttribute('d', primaryPath.d);
      if (marker) {
        marker.setAttribute('cx', String(Math.round(primaryPath.markerX)));
        marker.setAttribute('cy', String(Math.round(primaryPath.markerY)));
      }
      if (textNode) {
        textNode.setAttribute('x', String(Math.round(primaryPath.markerX)));
        textNode.setAttribute('y', String(Math.round(primaryPath.markerY)));
      }

      setRect(secondaryRect, secondary);
      if (secondaryLine) {
        secondaryLine.hidden = !secondary;
        if (secondary) {
          secondaryLine.setAttribute(
            'd',
            pathTo(start, secondary, laneX + 6, laneY + 6, true, null).d
          );
        }
      }
    }

    function renderCallouts() {
      calloutFrame = 0;
      if (!isOpen() || overlay.getAttribute('data-rcle-layer') !== 'line' ||
          !productFrame) {
        calloutSvg.hidden = true;
        [1, 2, 3].forEach(function (number) {
          hideCallout(calloutSvg.querySelector('[data-rcle-callout="' + number + '"]'));
        });
        return;
      }
      var panelRect = panel.getBoundingClientRect();
      var frameRect = productFrame.getBoundingClientRect();
      if (!panelRect.width || !panelRect.height || !frameRect.width || !frameRect.height) {
        calloutSvg.hidden = true;
        return;
      }
      calloutSvg.hidden = false;
      calloutSvg.setAttribute('width', String(Math.round(panelRect.width)));
      calloutSvg.setAttribute('height', String(Math.round(panelRect.height)));
      calloutSvg.setAttribute(
        'viewBox',
        '0 0 ' + Math.round(panelRect.width) + ' ' + Math.round(panelRect.height)
      );

      var headerCells = Array.prototype.slice.call(v2Root.querySelectorAll(
        '[data-v2-table-region="lines"] .create-md__table thead th'
      ));
      var tableScroll = v2Root.querySelector(
        '[data-v2-table-region="lines"] .create-md__table-scroll'
      );
      var lineRows = Array.prototype.slice.call(v2Root.querySelectorAll(
        '[data-v2-tbody="lines"] [data-v2-row-id]'
      )).filter(elementIsVisible);
      var selectedRow = lineRows.find(function (row) {
        return row.classList.contains('is-selected') ||
          row.getAttribute('aria-selected') === 'true';
      });
      var accordionTriggers = ['line', 'premium'].map(function (section) {
        return v2Root.querySelector(
          '[data-v2-accordion="' + section + '"] .create-md__accordion-trigger'
        );
      }).filter(Boolean);
      var frameClip = unionFor([productFrame], panelRect);
      var tableClip = intersectRects(
        unionFor(tableScroll ? [tableScroll] : [], panelRect),
        frameClip
      );
      var detailClip = intersectRects(
        unionFor([
          v2Root.querySelector('.create-md__detail')
        ].filter(Boolean), panelRect),
        frameClip
      );
      var scopeTarget = intersectRects(
        unionFor(headerCells.slice(0, 3), panelRect),
        tableClip
      );
      var priceTarget = visibleRectOrEdge(
        unionFor(headerCells.slice(3, 6), panelRect),
        tableClip
      );
      var rowTarget = intersectRects(
        unionFor(selectedRow ? [selectedRow] : lineRows.slice(0, 1), panelRect),
        tableClip
      );
      var detailTarget = intersectRects(
        unionFor(accordionTriggers, panelRect),
        detailClip
      );

      drawCallout(
        1,
        scopeTarget,
        null,
        panelRect,
        frameRect
      );
      drawCallout(
        2,
        priceTarget,
        null,
        panelRect,
        frameRect,
        priceTarget && tableClip ? {
          x: tableClip.left - 12,
          y: priceTarget.top - 14
        } : null
      );
      drawCallout(
        3,
        rowTarget,
        detailTarget,
        panelRect,
        frameRect
      );
    }

    function scheduleCallouts() {
      if (calloutFrame) cancelAnimationFrame(calloutFrame);
      calloutFrame = requestAnimationFrame(renderCallouts);
    }

    function layerHintFromMutations(records) {
      var hint = null;
      var priority = 0;
      function consider(layer, nextPriority) {
        if (layerCopy[layer] && nextPriority >= priority) {
          hint = layer;
          priority = nextPriority;
        }
      }
      function considerElement(element) {
        if (!element || element.nodeType !== 1) return;
        var accordionTrigger = element.matches('.create-md__accordion-trigger')
          ? element
          : null;
        var accordionPanel = element.matches('.create-md__accordion-panel')
          ? element
          : null;
        var accordion = element.matches('[data-v2-accordion]')
          ? element
          : (accordionTrigger || accordionPanel)
            ? element.closest('[data-v2-accordion]')
            : null;
        if (accordion && (
          accordion.classList.contains('is-open') ||
          (accordionTrigger && accordionTrigger.getAttribute('aria-expanded') === 'true')
        )) {
          consider(accordion.getAttribute('data-v2-accordion'), 3);
        }
        var row = element.matches('[data-v2-row-id]') ? element : null;
        if (row && (
          row.classList.contains('is-selected') ||
          row.getAttribute('aria-selected') === 'true'
        )) {
          consider(row.getAttribute('data-v2-row-type') === 'premiums'
            ? 'premium'
            : 'line', 2);
        }
        var tab = element.matches('[data-v2-tab]') ? element : null;
        if (tab && (
          tab.classList.contains('is-selected') ||
          tab.getAttribute('aria-selected') === 'true'
        )) {
          consider(tab.getAttribute('data-v2-tab') === 'premiums'
            ? 'premium'
            : 'line', 1);
        }
        var tabPanel = element.matches('[data-v2-panel]') ? element : null;
        if (tabPanel && !tabPanel.hidden) {
          consider(tabPanel.getAttribute('data-v2-panel') === 'premiums'
            ? 'premium'
            : 'line', 1);
        }
      }
      records.forEach(function (record) {
        considerElement(record.target);
        Array.prototype.forEach.call(record.addedNodes || [], considerElement);
      });
      return hint;
    }

    function scheduleLiveSync(layerHint) {
      if (layerHint) syncLayerHint = layerHint;
      if (syncFrame) return;
      syncFrame = requestAnimationFrame(function () {
        syncFrame = 0;
        if (!isOpen()) return;
        var nextLayer = syncLayerHint;
        syncLayerHint = null;
        if (nextLayer) setLayer(nextLayer, { skipCallouts: true });
        scheduleCallouts();
      });
    }

    function onLiveClick(event) {
      var target = event.target && event.target.nodeType === 1 ? event.target : null;
      if (!target) return;
      var tab = target.closest('[data-v2-tab]');
      if (tab) {
        setLayer(tab.getAttribute('data-v2-tab') === 'premiums' ? 'premium' : 'line');
        return;
      }
      var accordion = target.closest('[data-section]');
      if (!accordion) return;
      var section = accordion.getAttribute('data-section');
      if (section === 'card' || section === 'line' || section === 'premium') {
        setLayer(section);
      }
    }

    function onGeometryChange() {
      scheduleCallouts();
    }

    function connectOpenState() {
      v2Root.addEventListener('click', onLiveClick);
      overlay.addEventListener('scroll', onGeometryChange, true);
      window.addEventListener('resize', onGeometryChange);
      mutationObserver = new MutationObserver(function (records) {
        scheduleLiveSync(layerHintFromMutations(records));
      });
      mutationObserver.observe(v2Root, {
        subtree: true,
        childList: true,
        attributes: true,
        attributeFilter: ['aria-selected', 'aria-expanded', 'class', 'hidden']
      });
      if (typeof ResizeObserver === 'function') {
        resizeObserver = new ResizeObserver(onGeometryChange);
        [panel, productFrame, v2Root].filter(Boolean).forEach(function (element) {
          resizeObserver.observe(element);
        });
      }
    }

    function disconnectOpenState() {
      v2Root.removeEventListener('click', onLiveClick);
      overlay.removeEventListener('scroll', onGeometryChange, true);
      window.removeEventListener('resize', onGeometryChange);
      if (mutationObserver) mutationObserver.disconnect();
      if (resizeObserver) resizeObserver.disconnect();
      mutationObserver = null;
      resizeObserver = null;
      if (calloutFrame) cancelAnimationFrame(calloutFrame);
      if (syncFrame) cancelAnimationFrame(syncFrame);
      calloutFrame = 0;
      syncFrame = 0;
      syncLayerHint = null;
    }

    function open() {
      if (isOpen() || !isEligible() || !v2Root.parentNode) return;
      lastFocused = document.activeElement;
      savedScroll = { x: window.scrollX, y: window.scrollY };
      captureLiveState();
      placeholder = document.createComment('rcle-live-root');
      v2Root.parentNode.insertBefore(placeholder, v2Root);
      liveSlot.appendChild(v2Root);
      document.body.classList.add('rcle-open');
      overlay.hidden = false;
      setBackgroundInert(true);
      setLayer(layerFromLiveState());
      connectOpenState();
      requestAnimationFrame(function () {
        if (!isOpen()) return;
        panel.focus({ preventScroll: true });
        scheduleCallouts();
      });
    }

    function close() {
      if (!isOpen()) return;
      disconnectOpenState();
      if (placeholder && placeholder.parentNode) {
        placeholder.parentNode.insertBefore(v2Root, placeholder.nextSibling);
        placeholder.remove();
      }
      placeholder = null;
      restoreLiveState();
      setBackgroundInert(false);
      document.body.classList.remove('rcle-open');
      overlay.hidden = true;
      window.scrollTo(savedScroll.x, savedScroll.y);
      if (lastFocused && lastFocused.isConnected &&
          typeof lastFocused.focus === 'function') {
        try {
          lastFocused.focus({ preventScroll: true });
        } catch (_) {
          lastFocused.focus();
        }
      }
      window.scrollTo(savedScroll.x, savedScroll.y);
      lastFocused = null;
    }

    function navigateLayer(layer) {
      setLayer(layer);
      if (layer === 'card') {
        var cardTrigger = v2Root.querySelector(
          '[data-v2-accordion="card"] .create-md__accordion-trigger'
        );
        if (cardTrigger && cardTrigger.getAttribute('aria-expanded') !== 'true') {
          cardTrigger.click();
        }
        return;
      }
      var type = layer === 'premium' ? 'premiums' : 'lines';
      var tab = v2Root.querySelector('[data-v2-tab="' + type + '"]');
      if (tab) tab.click();
      var selected = v2Root.querySelector(
        '[data-v2-row-type="' + type + '"].is-selected, ' +
        '[data-v2-row-type="' + type + '"][aria-selected="true"]'
      );
      var trigger = v2Root.querySelector(
        '[data-v2-accordion="' + layer + '"] .create-md__accordion-trigger'
      );
      if (selected && trigger && trigger.getAttribute('aria-expanded') !== 'true') {
        trigger.click();
      }
    }

    Array.prototype.forEach.call(layerButtons, function (button) {
      button.addEventListener('click', function () {
        navigateLayer(button.getAttribute('data-rcle-layer-option'));
      });
    });
    overlay.querySelectorAll('[data-rcle-close]').forEach(function (button) {
      button.addEventListener('click', function (event) {
        event.preventDefault();
        close();
      });
    });

    document.addEventListener('keydown', function (event) {
      var printShortcut = (event.key === 'p' || event.key === 'P') &&
        (event.ctrlKey || event.metaKey) && !event.shiftKey && !event.altKey;
      if (printShortcut && isOpen()) {
        event.preventDefault();
        event.stopImmediatePropagation();
        close();
        return;
      }
      if (printShortcut && isEligible() && !isEditable(event.target)) {
        event.preventDefault();
        event.stopImmediatePropagation();
        open();
        return;
      }
      if (!isOpen()) return;
      if (event.key === 'Escape') {
        event.preventDefault();
        event.stopImmediatePropagation();
        close();
        return;
      }
      if (event.key !== 'Tab') return;
      var focusables = visibleFocusables();
      if (!focusables.length) {
        event.preventDefault();
        panel.focus({ preventScroll: true });
        return;
      }
      var first = focusables[0];
      var last = focusables[focusables.length - 1];
      var active = document.activeElement;
      if (event.shiftKey && (active === first || active === panel ||
          !overlay.contains(active))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (active === last || !overlay.contains(active))) {
        event.preventDefault();
        first.focus();
      }
    }, true);

    new MutationObserver(function () {
      if (isOpen() && !isEligible()) close();
    }).observe(document.body, {
      attributes: true,
      attributeFilter: ['data-route', 'data-version']
    });
  }

  // ----- Slide 6 pricing explanation modal -------------------------------
  function initPricingComplexityModals() {
    var slide = document.querySelector('.atlas-slide--why-pricing');
    if (!slide) return;

    var cards = Array.from(slide.querySelectorAll('[data-wpc-card]'));
    var modal = slide.querySelector('[data-wpc-modal]');
    if (!cards.length || !modal) return;

    var stage = document.querySelector('.atlas-stage');
    var ATLAS_STAGE_NATIVE_WIDTH = 1920;

    var panel = modal.querySelector('.wpc-modal__panel');
    var closeButton = modal.querySelector('[data-wpc-modal-close]');
    var dismissTarget = modal.querySelector('[data-wpc-modal-dismiss]');
    var title = modal.querySelector('#wpc-modal-title');
    var contentSections = Array.from(
      modal.querySelectorAll('[data-wpc-modal-content]')
    );
    if (!panel || !closeButton || !dismissTarget || !title) return;

    /* Titles match the six card labels on the slide exactly (see
     * .wpc__label in index.html): Buyer Scope, Deal Context, Product,
     * Base Rate, Premium Details, Calculation. All six modals share one
     * Toyota / Monday Night Football example, so the numbers stay
     * consistent as a presenter opens them in any order. */
    var titles = {
      buyer: 'Buyer Scope',
      deal: 'Deal Context',
      product: 'Product',
      'base-rate': 'Base Rate',
      premiums: 'Premium Details',
      calculation: 'Calculation',
    };

    var openTimer = null;
    var closeTimer = null;
    var activeCard = null;
    var pinned = false;
    var suppressFocusPreview = false;
    var suppressHoverUntil = 0;
    var HOVER_OPEN_DELAY = 60;
    var HOVER_CLOSE_DELAY = 400;
    /* Anchoring the popover beside its card (instead of dead-centering
     * it) means a popover can now sit on top of a neighboring card in
     * the same row. Closing it (Escape, the close icon, or click-
     * outside) can leave the pointer resting over that neighbor once
     * the popover is removed from the layout; Chrome recomputes
     * :hover on that DOM change and fires a real mouseenter even
     * though the pointer never moved, which would otherwise reopen an
     * unrelated preview right after the user closed the one they
     * meant to close. This short window swallows that one synthetic
     * re-hover without blocking genuine hovers for long. */
    var HOVER_REOPEN_SUPPRESS_MS = 350;

    function clearOpenTimer() {
      if (!openTimer) return;
      clearTimeout(openTimer);
      openTimer = null;
    }

    function clearCloseTimer() {
      if (!closeTimer) return;
      clearTimeout(closeTimer);
      closeTimer = null;
    }

    function setActiveCard(card) {
      cards.forEach(function (candidate) {
        var isActive = candidate === card;
        candidate.classList.toggle('is-active', isActive);
        candidate.setAttribute('aria-expanded', isActive ? 'true' : 'false');
      });
      activeCard = card;
    }

    function showContent(key) {
      contentSections.forEach(function (section) {
        section.hidden = section.getAttribute('data-wpc-modal-content') !== key;
      });
      title.textContent = titles[key] || 'Monday Night Football';
    }

    /* Anchors the popover beside whichever card triggered it, instead of
     * the old dead-center placement. The deck renders at native 1920x1080
     * coordinates and is uniformly scaled to fit the viewport via
     * .atlas-stage's `transform: scale(--atlas-scale)` (see fitStage() in
     * initAtlasDeck), so all math below is done in real, on-screen pixels
     * (getBoundingClientRect) and only converted back to the stage's
     * native coordinate space at the very end, right before writing the
     * panel's inline left/top. The visible stage box (not the raw
     * browser viewport) is used as the collision boundary, since
     * .atlas-stage clips overflow and letterboxes inside its wrap. */
    function positionPanel(card) {
      if (!stage) return;
      var stageRect = stage.getBoundingClientRect();
      if (!stageRect.width || !stageRect.height) return;
      var scale = stageRect.width / ATLAS_STAGE_NATIVE_WIDTH;
      if (!isFinite(scale) || scale <= 0) scale = 1;

      var modalRect = modal.getBoundingClientRect();
      var cardRect = card.getBoundingClientRect();
      var panelRect = panel.getBoundingClientRect();
      var panelWidth = panelRect.width;
      var panelHeight = panelRect.height;

      var GAP = 14;   // within the requested 12-16px card <-> popover gap
      var EDGE = 16;  // minimum breathing room from the visible stage edge

      var stageLeft = stageRect.left;
      var stageRight = stageRect.right;
      var stageTop = stageRect.top;
      var stageBottom = stageRect.bottom;

      // Priority 1: place to the right of the card, top-aligned.
      var left = cardRect.right + GAP;
      if (left + panelWidth + EDGE > stageRight) {
        // Priority 2: not enough room on the right, try the left side.
        var leftAlt = cardRect.left - GAP - panelWidth;
        if (leftAlt >= stageLeft + EDGE) {
          left = leftAlt;
        } else {
          // Neither side fully fits (very narrow viewport) - use
          // whichever side has more room, then clamp inside the stage.
          var roomRight = stageRight - EDGE - (cardRect.right + GAP);
          var roomLeft = (cardRect.left - GAP) - (stageLeft + EDGE);
          left = roomLeft > roomRight
            ? Math.max(stageLeft + EDGE, leftAlt)
            : Math.min(left, stageRight - EDGE - panelWidth);
        }
      }

      var top = cardRect.top;
      if (top + panelHeight + EDGE > stageBottom) {
        top = stageBottom - EDGE - panelHeight;
      }
      if (top < stageTop + EDGE) top = stageTop + EDGE;

      var nativeLeft = (left - modalRect.left) / scale;
      var nativeTop = (top - modalRect.top) / scale;

      panel.style.position = 'absolute';
      panel.style.margin = '0';
      panel.style.left = nativeLeft + 'px';
      panel.style.top = nativeTop + 'px';
    }

    function open(card, shouldPin) {
      var key = card.getAttribute('data-wpc-card');
      if (!key || !titles[key]) return;
      clearOpenTimer();
      clearCloseTimer();
      pinned = Boolean(shouldPin);
      setActiveCard(card);
      showContent(key);
      modal.hidden = false;
      modal.classList.toggle('is-pinned', pinned);
      modal.setAttribute('aria-modal', pinned ? 'true' : 'false');
      positionPanel(card);

      if (pinned) {
        requestAnimationFrame(function () {
          closeButton.focus({ preventScroll: true });
        });
      }
    }

    function close(options) {
      clearOpenTimer();
      clearCloseTimer();
      var returnFocus = Boolean(options && options.returnFocus);
      var trigger = activeCard;
      pinned = false;
      modal.hidden = true;
      modal.classList.remove('is-pinned');
      modal.setAttribute('aria-modal', 'false');
      setActiveCard(null);
      suppressHoverUntil = Date.now() + HOVER_REOPEN_SUPPRESS_MS;
      if (returnFocus && trigger) {
        suppressFocusPreview = true;
        trigger.focus({ preventScroll: true });
        requestAnimationFrame(function () {
          suppressFocusPreview = false;
        });
      }
    }

    function previewSoon(card) {
      if (pinned) return;
      if (Date.now() < suppressHoverUntil) return;
      clearCloseTimer();
      if (!modal.hidden && activeCard === card) return;
      clearOpenTimer();
      openTimer = setTimeout(function () {
        openTimer = null;
        open(card, false);
      }, HOVER_OPEN_DELAY);
    }

    function closePreviewSoon() {
      clearOpenTimer();
      if (pinned || modal.hidden) return;
      clearCloseTimer();
      closeTimer = setTimeout(function () {
        closeTimer = null;
        if (!pinned) close();
      }, HOVER_CLOSE_DELAY);
    }

    cards.forEach(function (card) {
      card.addEventListener('mouseenter', function () {
        previewSoon(card);
      });
      card.addEventListener('mouseleave', closePreviewSoon);
      card.addEventListener('focus', function () {
        if (!pinned && !suppressFocusPreview) open(card, false);
      });
      card.addEventListener('blur', closePreviewSoon);
      card.addEventListener('click', function (event) {
        event.preventDefault();
        event.stopPropagation();
        open(card, true);
      });
      card.addEventListener('keydown', function (event) {
        if (event.key !== 'Enter' && event.key !== ' ') return;
        event.preventDefault();
        event.stopPropagation();
        open(card, true);
      });
    });

    panel.addEventListener('mouseenter', clearCloseTimer);
    panel.addEventListener('mouseleave', closePreviewSoon);
    panel.addEventListener('focusin', clearCloseTimer);
    panel.addEventListener('focusout', closePreviewSoon);
    panel.addEventListener('click', function (event) {
      event.stopPropagation();
    });

    closeButton.addEventListener('click', function (event) {
      event.preventDefault();
      event.stopPropagation();
      close({ returnFocus: true });
    });

    dismissTarget.addEventListener('click', function (event) {
      if (!pinned) return;
      event.preventDefault();
      event.stopPropagation();
      close({ returnFocus: true });
    });

    document.addEventListener('keydown', function (event) {
      if (modal.hidden) return;
      if (event.key === 'Escape') {
        event.preventDefault();
        event.stopImmediatePropagation();
        close({ returnFocus: pinned });
        return;
      }
      if (pinned && event.key === 'Tab') {
        event.preventDefault();
        closeButton.focus({ preventScroll: true });
      }
    }, true);

    var slideObserver = new MutationObserver(function () {
      if (!slide.classList.contains('is-active') && !modal.hidden) close();
    });
    slideObserver.observe(slide, {
      attributes: true,
      attributeFilter: ['class'],
    });

    // Recalculate the anchored position whenever the viewport resizes
    // (window resize, orientation change, sidebar collapse/expand, etc).
    // --atlas-scale itself only changes inside fitStage()'s own single
    // rAF-deferred callback (see initAtlasDeck), and .atlas-stage's own
    // layout box never changes size (only its `transform: scale()`
    // does, which ResizeObserver cannot see) - so this defers with a
    // double rAF to guarantee it re-reads the stage's rect strictly
    // after fitStage's update has already landed, instead of racing it
    // with a stale scale.
    function repositionIfOpen() {
      requestAnimationFrame(function () {
        requestAnimationFrame(function () {
          if (!modal.hidden && activeCard) positionPanel(activeCard);
        });
      });
    }
    var wrap = document.querySelector('.atlas-stage-wrap');
    if (wrap && typeof ResizeObserver === 'function') {
      new ResizeObserver(repositionIfOpen).observe(wrap);
    } else {
      window.addEventListener('resize', repositionIfOpen);
    }
    window.addEventListener('orientationchange', repositionIfOpen);
    if (window.visualViewport) {
      window.visualViewport.addEventListener('resize', repositionIfOpen);
    }
  }

  // ----- Buyer Complexity Modal (BCM)  -  v1.2 only -----------------------
  //
  // Educational modal that opens when a user clicks the "Buyer" tile on
  // the Atlas "Why Pricing Gets Complicated Before Planning" slide. Only
  // reachable when body[data-version="1.2"] is active; v1.0 / v1.1 users
  // continue to see the tile as static informational content.
  //
  // Interaction contract (2026-07-09 hover-popover redesign):
  //   - pointerenter tile OR panel -> open (60ms grace so drive-by
  //     hovers don't fire; 0-100ms window per PM brief)
  //   - pointerleave tile AND panel -> close (200ms grace so the
  //     mouse can travel from tile to panel without flicker; 150-
  //     250ms window per PM brief)
  //   - focusin tile OR panel  -> open (keyboard equivalent)
  //   - focusout tile AND panel -> close
  //   - Escape                 -> close immediately (a11y affordance)
  //   - click on tile          -> falls through to atlas wrap-click
  //                               (advances the slide, matches every
  //                               other tile on the slide). No longer
  //                               opens the popover.
  //   - click inside panel     -> stopPropagation so the atlas
  //                               wrap-click does NOT advance
  //   - click outside panel    -> falls through (see .bcm rule
  //                               pointer-events: none; only the
  //                               panel itself re-enables input)
  /* --- Shared hover popover factory --------------------------------
   * The Buyer and Deal Context tiles on the "Why Pricing Gets
   * Complicated Before Planning" atlas slide both expand into a
   * v1.2-only hover-triggered popover. The interaction contract
   * (open / close debounce, focus-in/out equivalents, Escape closes,
   * click-inside-panel does NOT advance the deck, reposition on
   * resize/scroll, viewport clamping) is byte-identical across both
   * tiles; only the DOM selectors and a11y copy vary. This factory
   * centralizes that wiring so both tiles inherit the exact same
   * behavior automatically, per the PM's "match Buyer exactly" brief.
   *
   * config:
   *   tileSelector      querySelector for the trigger tile
   *   overlaySelector   querySelector for the .bcm overlay
   *   ariaLabel         v1.2-only aria-label applied to the tile
   *   ariaDescribedby   v1.2-only aria-describedby id applied to the
   *                     tile; must match an id inside the panel body
   *   syncGlobalKey     window key to expose the tile-sync fn under so
   *                     applyVersion() can re-run it on version switch
   */
  function wireHoverPopover(config) {
    var tile    = document.querySelector(config.tileSelector);
    var overlay = document.querySelector(config.overlaySelector);
    if (!tile || !overlay) return;
    var panel   = overlay.querySelector('.bcm__panel');
    if (!panel) return;

    /* Debounce timers so mouse travel from tile to panel doesn't
     * flicker the popover, and drive-by hovers don't accidentally
     * open it. Delays fall inside the PM brief's tolerances. */
    var openTimer  = null;
    var closeTimer = null;
    var OPEN_DELAY  = 60;
    var CLOSE_DELAY = 200;

    function isV12() {
      return isModernAppVersion(document.body.getAttribute('data-version'));
    }
    function isOpen() { return !overlay.hidden; }

    /* Version-aware sync of the tile's a11y hooks. In v1.2 the tile
     * is focusable (Tab lands on it) and carries an aria-label
     * matching the popover content so screen-reader users get the
     * example even without a visible popover. In v1.0 / v1.1 the tile
     * reverts to a plain listitem. Exposed on window under
     * config.syncGlobalKey so applyVersion() can call it whenever the
     * app switches versions live. */
    function syncTile() {
      if (isV12()) {
        /* role stays "listitem" (set by the HTML). We intentionally
         * DO NOT use role="button" or aria-haspopup here: click no
         * longer opens the popover (hover / focus do), and clicks on
         * the tile fall through to the atlas wrap-click. Announcing
         * a button role would mislead screen readers. */
        tile.setAttribute('tabindex', '0');
        tile.setAttribute('aria-label', config.ariaLabel);
        tile.setAttribute('aria-describedby', config.ariaDescribedby);
      } else {
        tile.removeAttribute('tabindex');
        tile.removeAttribute('aria-label');
        tile.removeAttribute('aria-describedby');
        if (isOpen()) forceClose();
      }
    }
    if (config.syncGlobalKey) {
      window[config.syncGlobalKey] = syncTile;
    }

    /* Position the panel next to the trigger tile via
     * getBoundingClientRect(). The atlas slide is scaled via
     * transform: scale(...) but getBoundingClientRect returns rects
     * AFTER the transform, so the coordinates are already in viewport
     * space and no manual scale math is needed.
     *
     * Preferred: to the right of the tile, top-aligned. Fallback:
     * below the tile, horizontally centered with the tile. Always
     * clamped inside the viewport with a 16px margin. */
    function positionPanel() {
      var t = tile.getBoundingClientRect();
      var pw = panel.offsetWidth  || 520;
      var ph = panel.offsetHeight || 320;
      var vw = window.innerWidth;
      var vh = window.innerHeight;
      var gap = 12;
      var margin = 16;
      var left = t.right + gap;
      var top  = t.top;
      if (left + pw > vw - margin) {
        /* Not enough room to the right - fall back to below the tile. */
        left = t.left + t.width / 2 - pw / 2;
        top  = t.bottom + gap;
      }
      if (left < margin)                     left = margin;
      if (left + pw > vw - margin)           left = vw - margin - pw;
      if (top + ph > vh - margin)            top = vh - margin - ph;
      if (top < margin)                      top = margin;
      panel.style.left = left + 'px';
      panel.style.top  = top  + 'px';
    }

    /* --- open / close with debounce ---------------------------------
     * openSoon()/closeSoon() cancel each other so mid-flight timers
     * from the OPPOSITE state never fire. This prevents the classic
     * hover-popover flicker where the mouse crosses the tile-to-panel
     * gap and both a "close" and an "open" timer fire in sequence. */
    function openSoon() {
      if (!isV12()) return;
      if (closeTimer) { clearTimeout(closeTimer); closeTimer = null; }
      if (isOpen() || openTimer) return;
      openTimer = setTimeout(function () {
        openTimer = null;
        openNow();
      }, OPEN_DELAY);
    }
    function openNow() {
      overlay.hidden = false;
      /* offsetWidth/Height are only reliable after the browser has
       * painted the newly-visible panel; requestAnimationFrame gives
       * us the first painted frame's real dimensions. */
      requestAnimationFrame(positionPanel);
    }
    function closeSoon() {
      if (openTimer) { clearTimeout(openTimer); openTimer = null; }
      if (!isOpen() || closeTimer) return;
      closeTimer = setTimeout(function () {
        closeTimer = null;
        forceClose();
      }, CLOSE_DELAY);
    }
    function forceClose() {
      if (openTimer)  { clearTimeout(openTimer);  openTimer  = null; }
      if (closeTimer) { clearTimeout(closeTimer); closeTimer = null; }
      overlay.hidden = true;
    }

    /* --- hover triggers ---------------------------------------------
     * mouseenter/mouseleave (rather than pointerenter/pointerleave)
     * because pointer-* events are not reliably fired by synthesized
     * mouseMoved sequences in some browsers / headless test harnesses,
     * and mouse-* is what the atlas deck's existing tile hover uses.
     * Both the tile AND the panel arm openSoon() so moving from tile
     * onto the panel keeps the popover alive. */
    tile.addEventListener('mouseenter', openSoon);
    tile.addEventListener('mouseleave', closeSoon);
    panel.addEventListener('mouseenter', openSoon);
    panel.addEventListener('mouseleave', closeSoon);

    /* --- keyboard focus triggers ------------------------------------
     * Focusing the tile (via Tab) is the keyboard equivalent of a
     * hover, and losing focus (Shift+Tab or focus-out) is the
     * equivalent of pointerleave. focusin/focusout bubble, so a
     * single pair on the tile+panel is enough. */
    tile.addEventListener('focus', openSoon);
    tile.addEventListener('blur',  closeSoon);
    panel.addEventListener('focusin',  openSoon);
    panel.addEventListener('focusout', closeSoon);

    /* --- Escape closes immediately ----------------------------------
     * Registered in the CAPTURE phase and uses
     * stopImmediatePropagation so the Atlas deck's document-level
     * Escape handler (which navigates back to the Rate Card Manager
     * list) does not fire while a hover popover is open. */
    document.addEventListener('keydown', function (e) {
      if (!isOpen()) return;
      if (e.key === 'Escape') {
        e.preventDefault();
        e.stopImmediatePropagation();
        forceClose();
      }
    }, true);

    /* --- click-inside-panel guard -----------------------------------
     * The .bcm wrapper has pointer-events: none in v1.2, so clicks on
     * empty slide area already fall through to the atlas wrap-click
     * (which advances the slide - the PM's "click-to-next" behavior).
     * BUT clicks that land INSIDE the panel (its pointer-events: auto)
     * would otherwise bubble up to document and re-enter the atlas
     * wrap listener via event capture on the wrap. stopPropagation on
     * the panel keeps those informational clicks contained. */
    panel.addEventListener('click', function (e) {
      e.stopPropagation();
    });

    /* --- reposition on resize + scroll ------------------------------
     * The atlas deck is not scrollable in the normal sense, but the
     * root document may scroll on narrow heights, and the deck stage
     * scales on window resize. Both invalidate the cached tile rect,
     * so reposition the panel while it's open. */
    var reposition = function () { if (isOpen()) positionPanel(); };
    window.addEventListener('resize', reposition);
    window.addEventListener('scroll', reposition, true);

    /* Initial sync so keyboard users can Tab to the tile on first
     * paint when v1.2 is already the active version. */
    syncTile();
  }

  function initBuyerComplexityModal() {
    wireHoverPopover({
      tileSelector:    '[data-buyer-tile]',
      overlaySelector: '[data-bcm]',
      ariaLabel:       'Buyer example: same agency, different advertiser mix',
      ariaDescribedby: 'bcm-desc',
      syncGlobalKey:   '__syncBuyerTile',
    });
  }

  /* Deal Context hover popover (v1.2 only). Reuses the shared factory
   * so its trigger, animation, radius, shadow, typography, spacing,
   * viewport clamping, click-through, and reposition behavior all
   * match the Buyer popover byte-for-byte per PM brief. Only the
   * panel's inner body copy differs (see [data-dcm] in index.html). */
  function initDealContextModal() {
    wireHoverPopover({
      tileSelector:    '[data-dcontext-tile]',
      overlaySelector: '[data-dcm]',
      ariaLabel:       'Deal Context example: same inventory prices differently depending on how the deal is bought',
      ariaDescribedby: 'dcm-desc',
      syncGlobalKey:   '__syncDealContextTile',
    });
  }

  /* Downstream hover popover (v1.2 only). Reuses the shared factory so
   * its trigger, animation, radius, shadow, typography, spacing, viewport
   * clamping, click-through, and reposition behavior all match the Deal
   * Context popover byte-for-byte per PM brief ("same modal style as
   * Deal Context"). Only the panel's inner body copy differs (see
   * [data-dsm] in index.html). */
  function initDownstreamModal() {
    wireHoverPopover({
      tileSelector:    '[data-downstream-tile]',
      overlaySelector: '[data-dsm]',
      ariaLabel:       'Downstream example: approved pricing needs to flow into planning, execution, billing, and reconciliation',
      ariaDescribedby: 'dsm-desc',
      syncGlobalKey:   '__syncDownstreamTile',
    });
  }

  /* Base Rate hover popover (v1.2 only). Reuses the shared factory so
   * its trigger, animation, radius, shadow, typography, spacing, viewport
   * clamping, click-through, and reposition behavior all match the Deal
   * Context, Downstream, and Buyer popovers byte-for-byte per PM brief
   * ("same modal style as the other hover modals"). Only the panel's
   * inner body copy differs (see [data-brm] in index.html). */
  function initBaseRateModal() {
    wireHoverPopover({
      tileSelector:    '[data-baserate-tile]',
      overlaySelector: '[data-brm]',
      ariaLabel:       'Base Rate example: the starting price before deal rules are applied; a CPM, flat rate, or unit price that can be adjusted by buyer, deal, targeting, timing, premiums, or discounts',
      ariaDescribedby: 'brm-desc',
      syncGlobalKey:   '__syncBaseRateTile',
    });
  }

  // ----- Dev-only Reference Overlay ----------------------------------------
  // Pins assets/reference-rate-card.svg (or .png fallback) over the live UI so
  // the agent and user can visually verify pixel alignment. NEVER product UI.
  function initReferenceOverlay() {
    const overlay = document.getElementById("ref-overlay");
    if (!overlay) return;
    const opacityInput = document.getElementById("ref-opacity");
    const opacityVal = document.getElementById("ref-opacity-val");
    const flip = document.getElementById("ref-flip");
    const hide = document.getElementById("ref-hide");

    const params = new URLSearchParams(location.search);
    let visible = params.get("ref") === "1";
    const setVisible = (v) => {
      visible = v;
      overlay.hidden = !v;
    };
    setVisible(visible);

    const setOpacity = (pct) => {
      const clamped = Math.max(0, Math.min(100, pct));
      document.documentElement.style.setProperty("--ref-opacity", clamped / 100);
      if (opacityInput) opacityInput.value = String(clamped);
      if (opacityVal) opacityVal.textContent = clamped + "%";
    };
    setOpacity(50);
    if (opacityInput) opacityInput.addEventListener("input", (e) => setOpacity(parseInt(e.target.value, 10)));
    if (flip) flip.addEventListener("change", (e) => overlay.classList.toggle("is-flip", e.target.checked));
    if (hide) hide.addEventListener("click", () => setVisible(false));

    // Hotkeys: O = toggle, [ / ] = ±10% opacity. Ignore when typing in an input.
    document.addEventListener("keydown", (e) => {
      if (e.target && /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return;
      if (e.key === "o" || e.key === "O") { setVisible(!visible); e.preventDefault(); }
      else if (e.key === "[") { setOpacity(parseInt(opacityInput.value, 10) - 10); }
      else if (e.key === "]") { setOpacity(parseInt(opacityInput.value, 10) + 10); }
    });
  }

  /* =====================================================================
   *  v1.2 Line Items multi-attach workflow
   *  ---------------------------------------------------------------------
   *  Wraps the existing LINE form in a three-stage flow (Figma 364-4588
   *  empty, 364-4993 one attached, 364-5705 many attached) with an ADS
   *  Search field (37-16) that finds existing line items by advertiser
   *  name, advertiser ID, line-item name, or rate-card name (case-
   *  insensitive), plus an "Add line item" secondary button.
   *
   *  State transitions (attached count):
   *    0 -> Stage 1: hide form. Show only search + Add.
   *    1 -> Stage 2: show one form + header + Remove. Button label
   *                  becomes "Add another line item".
   *    N -> Stage 3: N stacked forms, each with header + Remove,
   *                  separated by a subtle divider.
   *
   *  DOM model:
   *    Item 0 wraps the CANONICAL existing #line-form so the current
   *    save/validate/quick-edit wiring (LINE_REQUIRED, collectLineForm,
   *    validateForm) continues to read from the same IDs it always did.
   *    Additional items (idx >= 1) are dynamically appended <article>s
   *    with per-index IDs (e.g. ln-attach-1). Their values live in the
   *    DOM; they are prototype-only visual state in this iteration and
   *    do not participate in save. This is intentional: the current
   *    RCM app persists ONE LINE row per session, matching the frozen
   *    v1.1 behavior; extending the save pipeline to N rows is tracked
   *    separately.
   *
   *  Version gating:
   *    All chrome is CSS-hidden on non-v1.2. The wire-up below reads
   *    body[data-version] on each interaction, so a runtime version
   *    switch (via the profile menu) never leaves stale handlers armed.
   *
   *  Mock catalog: EXISTING_LINE_ITEMS
   *    12 demo lines drawn from the same advertiser roster the catalog
   *    fixture prices (L'Oreal USA, Ford Motor Company, The Coca-Cola
   *    Company, Target, Capital One, United Airlines), two per
   *    advertiser so a search on one name returns a real choice. Each
   *    advertiser carries the one Advertiser ID it carries everywhere.
   *
   *    Each row carries the metadata a Sales user needs to disambiguate:
   *    display label, advertiser display name + ID, attached rate card,
   *    ad type, base offering, base rate, currency, cost method, and
   *    line conditions.
   *
   *    The PRD has no LINE name field, so `name` is only a display
   *    label, derived here the same way the rest of the app derives it:
   *    Advertiser, Ad Type / Base Offering. Nothing reads it back into a
   *    saved record. `rateCard` and `attachToLine` must stay in sync
   *    with real seeded card names in RATE_CARDS; adType values come
   *    from AD_TYPE_OPTIONS and baseOffering from BASE_OFFERING_OPTIONS
   *    so an attached line populates selects the LINE form can show.
   * ================================================================ */

  var EXISTING_LINE_ITEMS = [
    {
      id: "LN-49201738",
      name: "L\u2019Or\u00e9al USA - Video / Premium",
      advertiserName: "L\u2019Or\u00e9al USA",
      advertiserId: "ADV-1236-01",
      rateCard: "WPP - Streaming Video Upfront 2026-2027",
      attachToLine: "WPP - Streaming Video Upfront 2026-2027",
      adType: "Video",
      baseOffering: "Premium",
      costMethod: "CPM",
      baseRate: "35.7500",
      currency: "USD",
      lineConditions: "DAR Demo: F18-49",
    },
    {
      id: "LN-49201802",
      name: "L\u2019Or\u00e9al USA - Display / Run of Network",
      advertiserName: "L\u2019Or\u00e9al USA",
      advertiserId: "ADV-1236-01",
      rateCard: "IPG - Hulu Upfront 2025-2026",
      attachToLine: "IPG - Hulu Upfront 2025-2026",
      adType: "Display",
      baseOffering: "Run of Network",
      costMethod: "CPM",
      baseRate: "12.0000",
      currency: "USD",
      lineConditions: "DAR Demo: A18-49",
    },
    {
      id: "LN-58312044",
      name: "Ford Motor Company - Connected TV / Premium",
      advertiserName: "Ford Motor Company",
      advertiserId: "ADV-1172-01",
      rateCard: "Dentsu - Addressable TV Scatter 2025-2026",
      attachToLine: "Dentsu - Addressable TV Scatter 2025-2026",
      adType: "Connected TV",
      baseOffering: "Premium",
      costMethod: "CPM",
      baseRate: "41.5000",
      currency: "USD",
      lineConditions: "DAR Demo: M25-54",
    },
    {
      id: "LN-58312109",
      name: "Ford Motor Company - Video / Live Events",
      advertiserName: "Ford Motor Company",
      advertiserId: "ADV-1172-01",
      rateCard: "IPG - Live Sports Multi-Year 2025-2026",
      attachToLine: "IPG - Live Sports Multi-Year 2025-2026",
      adType: "Video",
      baseOffering: "Live Events",
      costMethod: "CPM",
      baseRate: "59.2500",
      currency: "USD",
      lineConditions: "Targeting: NFL",
    },
    {
      id: "LN-67104553",
      name: "The Coca-Cola Company - Video / Run of Network",
      advertiserName: "The Coca-Cola Company",
      advertiserId: "ADV-1048-01",
      rateCard: "GroupM - Streaming Video Upfront 2025-2026",
      attachToLine: "GroupM - Streaming Video Upfront 2025-2026",
      adType: "Video",
      baseOffering: "Run of Network",
      costMethod: "CPM",
      baseRate: "28.0000",
      currency: "USD",
      lineConditions: "DAR Demo: A18-49",
    },
    {
      id: "LN-67104611",
      name: "The Coca-Cola Company - Sponsorship / Sports",
      advertiserName: "The Coca-Cola Company",
      advertiserId: "ADV-1048-01",
      rateCard: "IPG - Live Sports Multi-Year 2025-2026",
      attachToLine: "IPG - Live Sports Multi-Year 2025-2026",
      adType: "Sponsorship",
      baseOffering: "Sports",
      costMethod: "Flat",
      baseRate: "125000.0000",
      currency: "USD",
      lineConditions: "Targeting: NBA",
    },
    {
      id: "LN-71920004",
      name: "Target - Video / Originals",
      advertiserName: "Target",
      advertiserId: "ADV-1195-01",
      rateCard: "Omnicom - Disney+ Upfront 2025-2026",
      attachToLine: "Omnicom - Disney+ Upfront 2025-2026",
      adType: "Video",
      baseOffering: "Originals",
      costMethod: "CPM",
      baseRate: "37.7500",
      currency: "USD",
      lineConditions: "Format: Sponsorship Product",
    },
    {
      id: "LN-71920071",
      name: "Target - Display / Run of Network",
      advertiserName: "Target",
      advertiserId: "ADV-1195-01",
      rateCard: "Horizon - Client Direct Scatter 2025-2026",
      attachToLine: "Horizon - Client Direct Scatter 2025-2026",
      adType: "Display",
      baseOffering: "Run of Network",
      costMethod: "CPM",
      baseRate: "11.5000",
      currency: "USD",
      lineConditions: "DAR Demo: A21-49",
    },
    {
      id: "LN-82044318",
      name: "Capital One - Video / News",
      advertiserName: "Capital One",
      advertiserId: "ADV-1459-01",
      rateCard: "Publicis - Streaming Video Upfront 2025-2026",
      attachToLine: "Publicis - Streaming Video Upfront 2025-2026",
      adType: "Video",
      baseOffering: "News",
      costMethod: "CPM",
      baseRate: "26.5000",
      currency: "USD",
      lineConditions: "DAR Demo: A25-54",
    },
    {
      id: "LN-82044412",
      name: "Capital One - Connected TV / Premium",
      advertiserName: "Capital One",
      advertiserId: "ADV-1459-01",
      rateCard: "Dentsu - Addressable TV Scatter 2025-2026",
      attachToLine: "Dentsu - Addressable TV Scatter 2025-2026",
      adType: "Connected TV",
      baseOffering: "Premium",
      costMethod: "CPM",
      baseRate: "42.2500",
      currency: "USD",
      lineConditions: "DAR Demo: A35-64",
    },
    {
      id: "LN-90118225",
      name: "United Airlines - Video / Streaming Bundle",
      advertiserName: "United Airlines",
      advertiserId: "ADV-1512-01",
      rateCard: "WPP - Streaming Video Upfront 2026-2027",
      attachToLine: "WPP - Streaming Video Upfront 2026-2027",
      adType: "Video",
      baseOffering: "Streaming Bundle",
      costMethod: "CPM",
      baseRate: "41.5000",
      currency: "USD",
      lineConditions: "DAR Demo: A25-49",
    },
    {
      id: "LN-90118287",
      name: "United Airlines - Video / Run of Network",
      advertiserName: "United Airlines",
      advertiserId: "ADV-1512-01",
      rateCard: "Publicis - Streaming Video Scatter 2025-2026",
      attachToLine: "Publicis - Streaming Video Scatter 2025-2026",
      adType: "Video",
      baseOffering: "Run of Network",
      costMethod: "CPM",
      baseRate: "24.0000",
      currency: "USD",
      lineConditions: "Targeting: Longform Video Line",
    },
  ];

  /* Field descriptor for both the canonical item-0 form (id="line-form"
   * with base IDs) and dynamically-cloned additional items (id="line-form-N"
   * with suffixed IDs). Keys map to EXISTING_LINE_ITEMS record keys so a
   * single populate() loop can hydrate either. */
  var LINE_FIELDS = [
    { key: 'attachToLine',   id: 'ln-attach',    kind: 'input' },
    { key: 'advertiserId',   id: 'ln-advid',     kind: 'input' },
    { key: 'advertiserName', id: 'ln-advname',   kind: 'input' },
    { key: 'adType',         field: 'ad-type',   kind: 'edl-select', labelKey: 'lbl-adtype',    placeholder: 'Select ad product' },
    { key: 'baseOffering',   field: 'base-offering', kind: 'edl-select', labelKey: 'lbl-baseoff', placeholder: 'Select base offering' },
    { key: 'costMethod',     field: 'cost-method', kind: 'edl-select', labelKey: 'lbl-costmethod', placeholder: 'Select cost method' },
    { key: 'baseRate',       id: 'ln-baserate',  kind: 'input' },
    { key: 'currency',       field: 'currency',  kind: 'edl-select', labelKey: 'lbl-currency', placeholder: 'USD', defaultValue: 'USD' },
    /* Line conditions: single free-form text input consolidated per
     * Adam's 2026-07-09 update. EXISTING_LINE_ITEMS records already
     * carry lineConditions directly; populateNodeWithValues reads
     * values[f.key] so no legacy adapter is needed here. */
    { key: 'lineConditions', id: 'ln-lc',        kind: 'input' },
  ];

  function initLineItemsMultiAttach() {
    var wrapper = document.querySelector('[data-lineitems]');
    if (!wrapper) return;

    var list          = wrapper.querySelector('[data-lineitems-list]');
    var controls      = wrapper.querySelector('[data-lineitems-controls]');
    var searchWrap    = wrapper.querySelector('[data-ads-search]');
    var searchInput   = wrapper.querySelector('[data-lineitems-search-input]');
    var searchClear   = wrapper.querySelector('[data-lineitems-search-clear]');
    var resultsBox    = wrapper.querySelector('[data-lineitems-search-results]');
    var addBtn        = wrapper.querySelector('[data-lineitems-add]');
    var addBtnLabel   = wrapper.querySelector('[data-lineitems-add-label]');
    if (!list || !searchInput || !resultsBox || !addBtn) return;

    /* Attached items registry. Item 0 is always the canonical form and
     * exists in the DOM at boot time; its entry is added here so state
     * transitions can treat every attached item uniformly.
     *
     * When count = 0, wrapper[data-stage] = "1" and item 0 is CSS-hidden.
     * When user attaches or adds, count -> 1 and stage -> "2".
     * Adding again -> count = 2, stage -> "3". */
    var attached = [];        // [{ idx, source: 'new'|'existing', existingId }]
    var nextIdx  = 1;         // next dynamic-item index (0 is reserved)
    var activeResultIdx = -1; // keyboard-highlighted result row
    var filtered = [];        // current filtered EXISTING_LINE_ITEMS

    function isV12() {
      return isModernAppVersion(document.body.getAttribute('data-version'));
    }

    /* -----------------------------------------------------------------
     *  Stage management
     *  Also drives per-item visibility via the .is-attached class so
     *  detached item-0 (which stays in the DOM to preserve save/
     *  validate wiring) actually hides.
     * ---------------------------------------------------------------- */
    function updateStage() {
      var n = attached.length;
      var stage = n === 0 ? '1' : (n === 1 ? '2' : '3');
      wrapper.setAttribute('data-stage', stage);
      if (addBtnLabel) {
        addBtnLabel.textContent = n === 0 ? 'Add line item' : 'Add another line item';
      }
      /* Sync .is-attached class on every .lineitem based on attached[]. */
      var attachedIdxs = attached.reduce(function(m, a) { m[a.idx] = true; return m; }, {});
      list.querySelectorAll('.lineitem').forEach(function(el) {
        var idx = parseInt(el.getAttribute('data-lineitem-idx'), 10);
        if (attachedIdxs[idx]) el.classList.add('is-attached');
        else el.classList.remove('is-attached');
      });
      /* Reflect the count on the accordion status pill so users get
       * feedback when items are attached without opening the section. */
      var statusEl = document.querySelector('[data-accordion-status="line"]');
      if (statusEl && isV12()) {
        statusEl.textContent = n > 0 ? (n + (n === 1 ? ' line item' : ' line items')) : '';
      }
    }

    /* -----------------------------------------------------------------
     *  Form template: dynamically clone the item-0 markup with per-
     *  index IDs. Uses the existing #line-form as the reference so
     *  labels, placeholders, help text, and edl-select shells stay
     *  consistent - only the id="" / for="" / aria-labelledby="" get
     *  rewritten so the DOM stays unique.
     * ---------------------------------------------------------------- */
    function buildLineItemNode(idx, initialValues) {
      var item0 = list.querySelector('[data-lineitem-idx="0"]');
      if (!item0) return null;
      var clone = item0.cloneNode(true);
      clone.setAttribute('data-lineitem-idx', String(idx));

      /* Multi-attach is a v1.2-only feature; the LINE form template
       * carries BOTH a v1.1 line-condition row (three #ln-lc1..3 inputs)
       * and a v1.2 line-condition row (one #ln-lc input) so v1.1 and
       * v1.2 can each show the correct shape without JS re-authoring.
       * When we clone, the v1.1 row rides along and would produce
       * duplicate #ln-lc1/2/3 IDs in the DOM. Remove that row from the
       * clone here (LINE_FIELDS only rewires the v1.2 #ln-lc input, so
       * dropping the v1.1 row is safe and keeps the clone lean). */
      var v11LcRow = clone.querySelector('[data-lc-version="1.1"]');
      if (v11LcRow && v11LcRow.parentNode) v11LcRow.parentNode.removeChild(v11LcRow);

      /* Rewrite the header title val + remove button idx. */
      var titleVal = clone.querySelector('[data-lineitem-id]');
      if (titleVal) titleVal.textContent = (initialValues && initialValues.id) ? initialValues.id : 'New';
      var removeBtn = clone.querySelector('[data-action="remove-line-item"]');
      if (removeBtn) removeBtn.setAttribute('data-lineitem-idx', String(idx));

      /* Rewrite the inner <form> id. */
      var formEl = clone.querySelector('form.create-form');
      if (formEl) formEl.setAttribute('id', 'line-form-' + idx);

      /* Rewrite input IDs + <label for="..."> pairs + <label id="..."> +
       * .edl-select[aria-labelledby] targets. Uses LINE_FIELDS as the
       * canonical list so we don't rely on selector guesses. */
      LINE_FIELDS.forEach(function(f) {
        if (f.kind === 'input' && f.id) {
          var input = clone.querySelector('#' + f.id);
          if (input) {
            var newId = f.id + '-' + idx;
            input.setAttribute('id', newId);
            input.value = '';
            var lbl = clone.querySelector('label[for="' + f.id + '"]');
            if (lbl) lbl.setAttribute('for', newId);
            /* Wire per-input listeners for auto-open / save-state
             * re-compute? Not needed - additional items are prototype-
             * only; the canonical validate/save reads from item-0
             * IDs. Field values on cloned items live in the DOM. */
          }
        } else if (f.kind === 'edl-select' && f.field) {
          var sel = clone.querySelector('.edl-select[data-field="' + f.field + '"]');
          if (sel) {
            /* Reset selected value (or default) + placeholder text. */
            var defaultV = f.defaultValue || '';
            sel.setAttribute('data-value', defaultV);
            var valSpan = sel.querySelector('.edl-select__value');
            if (valSpan) {
              if (defaultV) {
                valSpan.textContent = defaultV;
                valSpan.classList.remove('edl-select__value--placeholder');
              } else {
                valSpan.textContent = f.placeholder || 'Select';
                valSpan.classList.add('edl-select__value--placeholder');
              }
            }
            /* Unique label id + trigger aria-labelledby so screen
             * readers can distinguish "Ad Type" for item 1 vs item 2. */
            if (f.labelKey) {
              var newLbl = f.labelKey + '-' + idx;
              var oldLblEl = clone.querySelector('#' + f.labelKey);
              if (oldLblEl) oldLblEl.setAttribute('id', newLbl);
              var trigger = sel.querySelector('.edl-select__trigger');
              if (trigger) trigger.setAttribute('aria-labelledby', newLbl);
              var menu = sel.querySelector('.edl-select__menu');
              if (menu) menu.setAttribute('aria-labelledby', newLbl);
            }
            /* Reset the menu so populateEdlSelectOptions() can refill. */
            var menu2 = sel.querySelector('.edl-select__menu');
            if (menu2) menu2.innerHTML = '';
          }
        }
      });

      /* Reset any inline error states on the clone. */
      var errs = clone.querySelectorAll('.field__error');
      errs.forEach(function(e) { e.hidden = true; e.textContent = ''; });
      var invalids = clone.querySelectorAll('.field.is-invalid');
      invalids.forEach(function(el) { el.classList.remove('is-invalid'); });

      /* Populate with initial values if provided (from search result). */
      if (initialValues) {
        populateNodeWithValues(clone, initialValues, idx);
      }

      return clone;
    }

    /* Populate a single line-item node's form with a values object. */
    function populateNodeWithValues(node, values, idx) {
      LINE_FIELDS.forEach(function(f) {
        var v = values[f.key];
        if (v == null) return;
        if (f.kind === 'input' && f.id) {
          var domId = idx === 0 ? f.id : (f.id + '-' + idx);
          var inp = node.querySelector('#' + domId);
          if (inp) inp.value = v;
        } else if (f.kind === 'edl-select' && f.field) {
          var sel = node.querySelector('.edl-select[data-field="' + f.field + '"]');
          if (sel) {
            sel.setAttribute('data-value', v);
            var valSpan = sel.querySelector('.edl-select__value');
            if (valSpan) {
              valSpan.textContent = v || (f.placeholder || 'Select');
              if (v) valSpan.classList.remove('edl-select__value--placeholder');
              else valSpan.classList.add('edl-select__value--placeholder');
            }
          }
        }
      });
      /* Update the header title with the record id. */
      var titleVal = node.querySelector('[data-lineitem-id]');
      if (titleVal && values.id) titleVal.textContent = values.id;
    }

    /* -----------------------------------------------------------------
     *  Attach / remove line items
     * ---------------------------------------------------------------- */
    function attachNewBlank(focusFirst) {
      var itemIdx;
      if (attached.length === 0) {
        /* Reuse item 0. Just reveal it (Stage 2). */
        itemIdx = 0;
        attached.push({ idx: 0, source: 'new', existingId: null });
        /* Ensure item 0 form is cleared (in Edit mode it might be
         * pre-populated - we DON'T clear in that case; only reveal). */
      } else {
        /* Append a new dynamic item. */
        itemIdx = nextIdx++;
        var node = buildLineItemNode(itemIdx, null);
        if (node) {
          list.appendChild(node);
          /* Refill edl-select options for the freshly cloned selects. */
          try { populateEdlSelectOptions(); } catch (_) {}
          try { wireEdlSelects(); } catch (_) {}
        }
        attached.push({ idx: itemIdx, source: 'new', existingId: null });
      }
      updateStage();
      if (focusFirst) {
        setTimeout(function() { focusFirstFieldOfItem(itemIdx); }, 20);
      }
    }

    function attachExisting(record) {
      /* Duplicate detection: if this record is already attached, flash
       * the existing entry and do nothing else. */
      var already = attached.find(function(a) { return a.existingId === record.id; });
      if (already) {
        flashItem(already.idx);
        closeResults(false);
        return;
      }

      var itemIdx;
      if (attached.length === 0) {
        itemIdx = 0;
        attached.push({ idx: 0, source: 'existing', existingId: record.id });
        var item0 = list.querySelector('[data-lineitem-idx="0"]');
        if (item0) populateNodeWithValues(item0, record, 0);
      } else {
        itemIdx = nextIdx++;
        var node = buildLineItemNode(itemIdx, record);
        if (node) {
          list.appendChild(node);
          try { populateEdlSelectOptions(); } catch (_) {}
          try { wireEdlSelects(); } catch (_) {}
        }
        attached.push({ idx: itemIdx, source: 'existing', existingId: record.id });
      }
      updateStage();
      closeResults(true);
      searchInput.value = '';
      updateClearVisibility();
      /* Scroll the new item into view smoothly. */
      requestAnimationFrame(function() {
        var el = list.querySelector('[data-lineitem-idx="' + itemIdx + '"]');
        if (el && el.scrollIntoView) {
          el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
      });
    }

    function removeItem(idx) {
      /* Untouched blank item 0: no confirmation. Item 0 stays in the
       * DOM (it's the canonical form) but is CSS-hidden by stage=1. */
      if (idx === 0) {
        var item0 = list.querySelector('[data-lineitem-idx="0"]');
        if (item0) {
          /* Clear item-0 form fields so re-entering Stage 2 gives a
           * fresh blank form. Skip the currency default reset - keeping
           * USD default matches Figma. */
          LINE_FIELDS.forEach(function(f) {
            if (f.kind === 'input' && f.id) {
              var inp = item0.querySelector('#' + f.id);
              if (inp) inp.value = '';
            } else if (f.kind === 'edl-select' && f.field) {
              var sel = item0.querySelector('.edl-select[data-field="' + f.field + '"]');
              if (sel) {
                var v = f.defaultValue || '';
                sel.setAttribute('data-value', v);
                var valSpan = sel.querySelector('.edl-select__value');
                if (valSpan) {
                  valSpan.textContent = v || (f.placeholder || 'Select');
                  if (v) valSpan.classList.remove('edl-select__value--placeholder');
                  else valSpan.classList.add('edl-select__value--placeholder');
                }
              }
            }
          });
          var titleVal = item0.querySelector('[data-lineitem-id]');
          if (titleVal) titleVal.textContent = 'New';
        }
        attached = attached.filter(function(a) { return a.idx !== 0; });
      } else {
        var node = list.querySelector('[data-lineitem-idx="' + idx + '"]');
        if (node && node.parentNode) node.parentNode.removeChild(node);
        attached = attached.filter(function(a) { return a.idx !== idx; });
      }
      updateStage();
    }

    function focusFirstFieldOfItem(idx) {
      var node = list.querySelector('[data-lineitem-idx="' + idx + '"]');
      if (!node) return;
      var first = node.querySelector('.field__input');
      if (first && first.focus) first.focus();
    }

    function flashItem(idx) {
      var node = list.querySelector('[data-lineitem-idx="' + idx + '"]');
      if (!node) return;
      node.classList.add('is-flash');
      setTimeout(function() { node.classList.remove('is-flash'); }, 900);
      if (node.scrollIntoView) node.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      /* Toast a subtle info message so screen readers pick it up. */
      try {
        if (typeof toastV12 === 'function') {
          toastV12(
            { message: 'This line item is already attached.', variant: 'info', duration: 3200 },
            'This line item is already attached.',
            { variant: 'info', duration: 3200 }
          );
        }
      } catch (_) {}
    }

    /* -----------------------------------------------------------------
     *  Search + results
     * ---------------------------------------------------------------- */
    function filterResults(query) {
      var q = (query || '').trim().toLowerCase();
      if (!q) return [];
      return EXISTING_LINE_ITEMS.filter(function(r) {
        return (
          (r.name && r.name.toLowerCase().indexOf(q) !== -1) ||
          (r.advertiserName && r.advertiserName.toLowerCase().indexOf(q) !== -1) ||
          (r.advertiserId && r.advertiserId.toLowerCase().indexOf(q) !== -1) ||
          (r.rateCard && r.rateCard.toLowerCase().indexOf(q) !== -1)
        );
      });
    }

    function escapeHtml(s) {
      return String(s == null ? '' : s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    }

    function renderResultsList() {
      if (filtered.length === 0) {
        resultsBox.innerHTML =
          '<div class="ads-search__empty">' +
          '<strong>No matches</strong>' +
          '<div class="ads-search__empty-hint">Try an advertiser name, advertiser ID, line-item name, or rate card.</div>' +
          '</div>';
        return;
      }
      var html = '<div class="ads-search__group-head">Existing line items</div>';
      html += filtered.map(function(r, i) {
        var attachedAlready = attached.some(function(a) { return a.existingId === r.id; });
        return (
          '<button type="button" role="option" class="ads-search__result' +
          (i === activeResultIdx ? ' is-active' : '') + '"' +
          (attachedAlready ? ' data-disabled="true"' : '') +
          ' data-result-idx="' + i + '"' +
          ' aria-selected="' + (i === activeResultIdx ? 'true' : 'false') + '">' +
            '<div class="ads-search__result-line1">' +
              '<span class="ads-search__result-name">' + escapeHtml(r.name) + '</span>' +
              '<span class="ads-search__result-rate">' + escapeHtml(formatRate(r.baseRate)) + ' ' + escapeHtml(r.currency) + ' ' + escapeHtml(r.costMethod) + '</span>' +
            '</div>' +
            '<div class="ads-search__result-line2">' +
              '<span class="ads-search__result-meta"><strong>' + escapeHtml(r.advertiserId) + '</strong></span>' +
              '<span class="ads-search__result-meta">' + escapeHtml(r.rateCard) + '</span>' +
              '<span class="ads-search__result-meta">' + escapeHtml(r.adType) + '</span>' +
              '<span class="ads-search__result-meta">' + escapeHtml(r.baseOffering) + '</span>' +
            '</div>' +
            (attachedAlready
              ? '<div class="ads-search__result-attached">' +
                  '<svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true"><path d="M2.5 6.2l2.4 2.3 4.6-5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>' +
                  'Already attached' +
                '</div>'
              : ''
            ) +
          '</button>'
        );
      }).join('');
      resultsBox.innerHTML = html;
    }

    function formatRate(v) {
      /* Trim trailing zeros on 4dp base rates so "28.0000" -> "28.00"
       * for compact search rows. */
      if (v == null) return '';
      var n = parseFloat(v);
      if (isNaN(n)) return String(v);
      return '$' + n.toFixed(2);
    }

    function openResults() {
      if (!isV12()) return;
      resultsBox.hidden = false;
      searchInput.setAttribute('aria-expanded', 'true');
      /* When the input has a non-empty query, refresh the filter so
       * the caller doesn't have to. */
      var q = searchInput.value;
      filtered = filterResults(q);
      if (filtered.length && activeResultIdx < 0) activeResultIdx = 0;
      if (activeResultIdx >= filtered.length) activeResultIdx = filtered.length - 1;
      renderResultsList();
      searchWrap.setAttribute('data-filled', q ? 'true' : 'false');
    }

    function closeResults(clearActive) {
      resultsBox.hidden = true;
      searchInput.setAttribute('aria-expanded', 'false');
      if (clearActive) activeResultIdx = -1;
    }

    function updateClearVisibility() {
      var has = searchInput.value.length > 0;
      searchClear.hidden = !has;
      searchWrap.setAttribute('data-filled', has ? 'true' : 'false');
    }

    /* -----------------------------------------------------------------
     *  Wire events
     * ---------------------------------------------------------------- */
    searchInput.addEventListener('input', function() {
      if (!isV12()) return;
      activeResultIdx = -1;
      updateClearVisibility();
      if (searchInput.value.trim().length === 0) {
        closeResults(true);
        return;
      }
      openResults();
    });

    searchInput.addEventListener('focus', function() {
      if (!isV12()) return;
      if (searchInput.value.trim().length > 0) openResults();
    });

    searchInput.addEventListener('keydown', function(e) {
      if (!isV12()) return;
      /* If dropdown is closed and user presses Down with a query,
       * open it. Otherwise navigate within it. */
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        if (resultsBox.hidden) { openResults(); return; }
        if (filtered.length === 0) return;
        activeResultIdx = (activeResultIdx + 1) % filtered.length;
        renderResultsList();
        scrollActiveIntoView();
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        if (resultsBox.hidden || filtered.length === 0) return;
        activeResultIdx = activeResultIdx <= 0 ? filtered.length - 1 : activeResultIdx - 1;
        renderResultsList();
        scrollActiveIntoView();
      } else if (e.key === 'Enter') {
        if (resultsBox.hidden || filtered.length === 0 || activeResultIdx < 0) return;
        e.preventDefault();
        var r = filtered[activeResultIdx];
        if (r) attachExisting(r);
      } else if (e.key === 'Escape') {
        if (!resultsBox.hidden) {
          e.preventDefault();
          closeResults(true);
        }
      }
    });

    function scrollActiveIntoView() {
      var el = resultsBox.querySelector('.ads-search__result.is-active');
      if (el && el.scrollIntoView) el.scrollIntoView({ block: 'nearest' });
    }

    /* Click on a result: select it. Delegated so the innerHTML redraws
     * don't need re-binding. */
    resultsBox.addEventListener('click', function(e) {
      var btn = e.target && e.target.closest ? e.target.closest('.ads-search__result') : null;
      if (!btn) return;
      var idx = parseInt(btn.getAttribute('data-result-idx'), 10);
      if (isNaN(idx)) return;
      var r = filtered[idx];
      if (!r) return;
      if (btn.getAttribute('data-disabled') === 'true') {
        /* Already attached: flash the attached entry. */
        var already = attached.find(function(a) { return a.existingId === r.id; });
        if (already) flashItem(already.idx);
        return;
      }
      attachExisting(r);
    });

    /* Hover: sync activeResultIdx with the pointer so keyboard nav
     * stays consistent with the visible active row. */
    resultsBox.addEventListener('mousemove', function(e) {
      var btn = e.target && e.target.closest ? e.target.closest('.ads-search__result') : null;
      if (!btn) return;
      var idx = parseInt(btn.getAttribute('data-result-idx'), 10);
      if (isNaN(idx) || idx === activeResultIdx) return;
      activeResultIdx = idx;
      renderResultsList();
    });

    /* Clear button */
    searchClear.addEventListener('click', function(e) {
      e.preventDefault();
      searchInput.value = '';
      updateClearVisibility();
      closeResults(true);
      searchInput.focus();
    });

    /* Click outside: close the dropdown. Use pointerdown so it fires
     * before the focus/blur ping-pong. */
    document.addEventListener('pointerdown', function(e) {
      if (!isV12()) return;
      if (resultsBox.hidden) return;
      if (searchWrap.contains(e.target)) return;
      closeResults(true);
    });

    /* Add button */
    addBtn.addEventListener('click', function(e) {
      if (!isV12()) return;
      e.preventDefault();
      attachNewBlank(true);
    });

    /* Remove buttons (delegated on the list container) */
    list.addEventListener('click', function(e) {
      if (!isV12()) return;
      var btn = e.target && e.target.closest ? e.target.closest('[data-action="remove-line-item"]') : null;
      if (!btn) return;
      e.preventDefault();
      var idx = parseInt(btn.getAttribute('data-lineitem-idx'), 10);
      if (isNaN(idx)) return;
      /* Confirmation policy per brief:
       *   - Untouched blank -> no confirm
       *   - Edited existing -> confirm (only when meaningful data
       *     would be discarded)
       *   For this prototype we treat any item with a filled
       *   Advertiser ID or Base Rate as "meaningful" and confirm
       *   removal. Blank items skip the confirm. */
      var meaningful = isItemMeaningful(idx);
      if (!meaningful) {
        removeItem(idx);
        return;
      }
      adsConfirm({
        title: 'Remove this line item?',
        body: 'This line item will be removed from the rate card file. '
          + 'Any changes to it will be discarded.',
        confirmLabel: 'Remove line item'
      }, function () { removeItem(idx); });
    });

    function isItemMeaningful(idx) {
      var node = list.querySelector('[data-lineitem-idx="' + idx + '"]');
      if (!node) return false;
      var advIdSel = idx === 0 ? '#ln-advid' : ('#ln-advid-' + idx);
      var rateSel  = idx === 0 ? '#ln-baserate' : ('#ln-baserate-' + idx);
      var advId = node.querySelector(advIdSel);
      var rate  = node.querySelector(rateSel);
      return (
        (advId && advId.value && advId.value.trim().length > 0) ||
        (rate && rate.value && rate.value.trim().length > 0)
      );
    }

    /* Initial state: no items attached. Stage 1. */
    updateStage();
    updateClearVisibility();

    /* Edit-mode entry: if the canonical item-0 form is already
     * populated (openEditRateCard pre-fills it), auto-attach item 0
     * so the user lands in Stage 2 instead of a confusing Stage 1
     * with hidden pre-filled fields. */
    if (isV12()) {
      var advIdEl = document.getElementById('ln-advid');
      var rateEl  = document.getElementById('ln-baserate');
      var attachEl = document.getElementById('ln-attach');
      var prefilled = (
        (advIdEl && advIdEl.value && advIdEl.value.trim())
        || (rateEl && rateEl.value && rateEl.value.trim())
        || (attachEl && attachEl.value && attachEl.value.trim())
      );
      if (prefilled) {
        attached.push({ idx: 0, source: 'new', existingId: null });
        updateStage();
      }
    }
  }

  /* =====================================================================
   *  v1.2 Premium Adjustments multi-attach workflow
   *  ---------------------------------------------------------------------
   *  Mirrors the Line Items workflow (initLineItemsMultiAttach) beat-
   *  for-beat: three stages, ADS Search (Figma 37-16), Add/Add-another
   *  toggle, per-item header + Remove, duplicate detection, keyboard
   *  navigation, click-outside close, scroll-into-view on attach.
   *
   *  Why mirror? The user brief calls out that the Premium adjustments
   *  section should feel like a member of the same component family as
   *  Line items - same alignment, spacing, transitions, and item
   *  affordances. We share the ADS Search visual grammar (.ads-search
   *  and .ads-search__*) and split only the state (attached[], nextIdx)
   *  and the field-map (PREM_FIELDS) between the two functions so a
   *  future refactor can consolidate them behind a factory.
   *
   *  DOM model:
   *    Item 0 wraps the CANONICAL existing #prem-form so the current
   *    save/validate wiring (PREM_REQUIRED, validateForm PREM checks
   *    at app.js ~5830) continues to read from the same IDs it always
   *    did. Additional items (idx >= 1) are dynamically appended
   *    <article>s with per-index IDs (e.g. prem-attach-1). Their values
   *    live in the DOM; they are prototype-only visual state in this
   *    iteration and do not participate in save. Same trade-off as
   *    Line items.
   *
   *  Version gating:
   *    All chrome is CSS-hidden on non-v1.2. The wire-up below reads
   *    body[data-version] on each interaction, so a runtime version
   *    switch (via the profile menu) never leaves stale handlers armed.
   *
   *  Mock catalog: EXISTING_PREMIUM_ADJUSTMENTS
   *    10 realistic Disney Advertising examples. Categories align with
   *    PREM_CATEGORY_OPTIONS (Geo / Duration / 1P Audience / 3P
   *    Audience / Device Type / Format / Content). Calculation methods
   *    align with PREM_CALC_OPTIONS (ADDITIVE_CPM / MULTIPLICATIVE_PCT
   *    / FLAT_RATE). Attach values align with PREM_ATTACH_OPTIONS so a
   *    selected result populates the form's edl-select with a value
   *    that renders (not a stray string that shows as placeholder).
   *
   *    Values are stored in the record as raw floats so form population
   *    matches the field format (rate-4dp for prem-value). Search
   *    rendering formats the value as "$X.XX CPM" for ADDITIVE_CPM,
   *    "X.X%" for MULTIPLICATIVE_PCT, or "$X.XX flat" for FLAT_RATE so
   *    Ad Sales users can disambiguate at a glance.
   * ================================================================ */

  var EXISTING_PREMIUM_ADJUSTMENTS = [
    {
      id: "PA-38210014",
      name: "Live Sports Video Premium",
      category: "Content",
      calcMethod: "MULTIPLICATIVE_PCT",
      value: "15.0000",
      attach: "RC-DAS-DENTSU-ADDR-SC-2526",
      attachedRows: "ESPN Live Sports Video, National Sports Video",
      displayName: "Live Sports Video Premium",
      stackOrder: "10",
      cond1: "M18-49",
      cond2: "Live",
      cond3: "30s",
      effStart: "2025-10-01",
      effEnd: "2026-09-30",
    },
    {
      id: "PA-38210027",
      name: "Championship Event Premium",
      category: "Content",
      calcMethod: "ADDITIVE_CPM",
      value: "8.0000",
      attach: "RC-DAS-DENTSU-ADDR-SC-2526",
      attachedRows: "NFL Playoffs, College Football Championship",
      displayName: "Championship Event Premium",
      stackOrder: "20",
      cond1: "M18-54",
      cond2: "Live",
      cond3: "30s",
      effStart: "2025-11-15",
      effEnd: "2026-02-28",
    },
    {
      id: "PA-49315063",
      name: "Prime Time Streaming Premium",
      category: "Duration",
      calcMethod: "MULTIPLICATIVE_PCT",
      value: "12.5000",
      attach: "RC-DAS-PG-DPLUS-UF-2526",
      attachedRows: "Hulu Premium Video, Prime Time",
      displayName: "Prime Time Streaming Premium",
      stackOrder: "15",
      cond1: "A25-54",
      cond2: "CTV",
      cond3: "30s",
      effStart: "2025-09-01",
      effEnd: "2026-08-31",
    },
    {
      id: "PA-56420089",
      name: "Advanced Audience Targeting Premium",
      category: "1P Audience",
      calcMethod: "ADDITIVE_CPM",
      value: "4.5000",
      attach: "RC-DAS-IPG-LOREAL-MY-2526",
      attachedRows: "Disney+ Addressable Video, Audience Targeted Video",
      displayName: "Advanced Audience Targeting Premium",
      stackOrder: "25",
      cond1: "F18-49",
      cond2: "Household",
      cond3: "",
      effStart: "2025-09-01",
      effEnd: "2026-08-31",
    },
    {
      id: "PA-56420112",
      name: "Third-Party Audience Segment Premium",
      category: "3P Audience",
      calcMethod: "ADDITIVE_CPM",
      value: "3.7500",
      attach: "RC-DAS-WPP-VIDEO-UF-2627",
      attachedRows: "Disney+ Programmatic Video, Open Auction Video",
      displayName: "Third-Party Audience Segment Premium",
      stackOrder: "30",
      cond1: "A18-49",
      cond2: "PMP",
      cond3: "",
      effStart: "2025-09-01",
      effEnd: "2026-08-31",
    },
    {
      id: "PA-63501207",
      name: "Holiday Programming Premium",
      category: "Content",
      calcMethod: "MULTIPLICATIVE_PCT",
      value: "10.0000",
      attach: "All rows",
      attachedRows: "ABC Holiday Specials, Disney Entertainment Video",
      displayName: "Holiday Programming Premium",
      stackOrder: "35",
      cond1: "A18-49",
      cond2: "",
      cond3: "30s",
      effStart: "2025-11-01",
      effEnd: "2026-01-05",
    },
    {
      id: "PA-71829040",
      name: "Premium Streaming Inventory Adjustment",
      category: "Format",
      calcMethod: "ADDITIVE_CPM",
      value: "6.0000",
      attach: "RC-DAS-PG-DPLUS-UF-2526",
      attachedRows: "Disney+ Premium Video, Hulu Premium Video",
      displayName: "Premium Streaming Inventory Adjustment",
      stackOrder: "40",
      cond1: "A25-54",
      cond2: "CTV",
      cond3: "",
      effStart: "2025-09-01",
      effEnd: "2026-08-31",
    },
    {
      id: "PA-88214056",
      name: "Extended Duration Premium (60s)",
      category: "Duration",
      calcMethod: "MULTIPLICATIVE_PCT",
      value: "20.0000",
      attach: "RC-DAS-WPP-VIDEO-UF-2627",
      attachedRows: "Hulu Upfront Video, Disney+ Upfront Video",
      displayName: "Extended Duration Premium (60s)",
      stackOrder: "45",
      cond1: "A18-49",
      cond2: "CTV",
      cond3: "60s",
      effStart: "2025-09-01",
      effEnd: "2026-08-31",
    },
    {
      id: "PA-94017218",
      name: "Mobile Device Premium",
      category: "Device Type",
      calcMethod: "ADDITIVE_CPM",
      value: "2.5000",
      attach: "RC-DAS-IPG-LOREAL-MY-2526",
      attachedRows: "ESPN Mobile, Disney+ Mobile Video",
      displayName: "Mobile Device Premium",
      stackOrder: "50",
      cond1: "A18-34",
      cond2: "Mobile",
      cond3: "15s",
      effStart: "2025-09-01",
      effEnd: "2026-08-31",
    },
    {
      id: "PA-99120118",
      name: "West Coast Geographic Premium",
      category: "Geo",
      calcMethod: "MULTIPLICATIVE_PCT",
      value: "8.0000",
      attach: "All rows",
      attachedRows: "Disney+ West Coast, ESPN Live Sports Video",
      displayName: "West Coast Geographic Premium",
      stackOrder: "55",
      cond1: "A18-49",
      cond2: "West",
      cond3: "",
      effStart: "2025-09-01",
      effEnd: "2026-08-31",
    },
  ];

  /* Field descriptor. Mirrors LINE_FIELDS shape so buildPremItemNode()
   * can rewrite IDs and populate values with the same loop pattern.
   *
   * Datepicker kind: rewrites data-field so the two triggers do not
   * collide with item 0 when cloned. Population sets the visible span
   * text and toggles the placeholder class; the actual date state
   * lives on data-value for save-side parity if this ever gets wired
   * to persistence. */
  var PREM_FIELDS = [
    { key: 'attach',      field: 'prem-attach',   kind: 'edl-select', labelKey: 'lbl-prem-attach',   placeholder: 'Select rate card row to attach...' },
    { key: 'category',    field: 'prem-category', kind: 'edl-select', labelKey: 'lbl-prem-category', placeholder: 'Select premium category...' },
    { key: 'calcMethod',  field: 'prem-calc',     kind: 'edl-select', labelKey: 'lbl-prem-calc',     placeholder: 'Select calculation method...' },
    { key: 'displayName', id: 'prem-displayname', kind: 'input' },
    { key: 'value',       id: 'prem-value',       kind: 'input' },
    { key: 'stackOrder',  id: 'prem-stack',       kind: 'input' },
    { key: 'cond1',       id: 'prem-cond1',       kind: 'input' },
    { key: 'cond2',       id: 'prem-cond2',       kind: 'input' },
    { key: 'cond3',       id: 'prem-cond3',       kind: 'input' },
    { key: 'effStart',    field: 'prem-eff-start', kind: 'datepicker', labelKey: 'lbl-prem-effstart', placeholder: 'Select start date' },
    { key: 'effEnd',      field: 'prem-eff-end',   kind: 'datepicker', labelKey: 'lbl-prem-effend',   placeholder: 'Select end date' },
  ];

  function initPremiumMultiAttach() {
    var wrapper = document.querySelector('[data-premitems]');
    if (!wrapper) return;

    var list        = wrapper.querySelector('[data-premitems-list]');
    var searchWrap  = wrapper.querySelector('[data-ads-search]');
    var searchInput = wrapper.querySelector('[data-premitems-search-input]');
    var searchClear = wrapper.querySelector('[data-premitems-search-clear]');
    var resultsBox  = wrapper.querySelector('[data-premitems-search-results]');
    var addBtn      = wrapper.querySelector('[data-premitems-add]');
    var addBtnLabel = wrapper.querySelector('[data-premitems-add-label]');
    if (!list || !searchInput || !resultsBox || !addBtn) return;

    var attached = [];
    var nextIdx  = 1;
    var activeResultIdx = -1;
    var filtered = [];

    function isV12() {
      return isModernAppVersion(document.body.getAttribute('data-version'));
    }

    /* -----------------------------------------------------------------
     *  Stage management + per-item visibility
     * ---------------------------------------------------------------- */
    function updateStage() {
      var n = attached.length;
      var stage = n === 0 ? '1' : (n === 1 ? '2' : '3');
      wrapper.setAttribute('data-stage', stage);
      if (addBtnLabel) {
        addBtnLabel.textContent = n === 0 ? 'Add premium adjustment' : 'Add another premium adjustment';
      }
      var attachedIdxs = attached.reduce(function(m, a) { m[a.idx] = true; return m; }, {});
      list.querySelectorAll('.premitem').forEach(function(el) {
        var idx = parseInt(el.getAttribute('data-premitem-idx'), 10);
        if (attachedIdxs[idx]) el.classList.add('is-attached');
        else el.classList.remove('is-attached');
      });
      var statusEl = document.querySelector('[data-accordion-status="prem"]');
      if (statusEl && isV12()) {
        statusEl.textContent = n > 0
          ? (n + (n === 1 ? ' premium adjustment' : ' premium adjustments'))
          : '';
      }
    }

    /* -----------------------------------------------------------------
     *  Form template: clone item-0 markup with per-index IDs. Uses
     *  the existing #prem-form as the reference so labels, help text,
     *  placeholders, edl-select shells, and datepicker triggers stay
     *  consistent - only id="" / for="" / aria-labelledby="" and
     *  .ads-datepicker[data-field] get rewritten so the DOM stays
     *  unique.
     * ---------------------------------------------------------------- */
    function buildPremItemNode(idx, initialValues) {
      var item0 = list.querySelector('[data-premitem-idx="0"]');
      if (!item0) return null;
      var clone = item0.cloneNode(true);
      clone.setAttribute('data-premitem-idx', String(idx));

      var titleVal = clone.querySelector('[data-premitem-name]');
      if (titleVal) {
        titleVal.textContent = (initialValues && initialValues.name)
          ? initialValues.name
          : 'New premium adjustment';
      }
      var removeBtn = clone.querySelector('[data-action="remove-prem-item"]');
      if (removeBtn) removeBtn.setAttribute('data-premitem-idx', String(idx));

      var formEl = clone.querySelector('form.create-form');
      if (formEl) formEl.setAttribute('id', 'prem-form-' + idx);

      PREM_FIELDS.forEach(function(f) {
        if (f.kind === 'input' && f.id) {
          var input = clone.querySelector('#' + f.id);
          if (input) {
            var newId = f.id + '-' + idx;
            input.setAttribute('id', newId);
            input.value = '';
            var lbl = clone.querySelector('label[for="' + f.id + '"]');
            if (lbl) lbl.setAttribute('for', newId);
          }
        } else if (f.kind === 'edl-select' && f.field) {
          /* Rewrite the edl-select's data-field so item-N's dropdown
           * options don't share state with item-0. populateEdlSelectOptions()
           * only fills selects whose data-field matches a known key,
           * so keep the base prefix (prem-attach / prem-category /
           * prem-calc) and use a suffix only for uniqueness. But then
           * the switch in populateEdlSelectOptions() would miss the
           * suffixed variant. So instead, KEEP data-field intact and
           * ensure the options refill runs after cloning - the DOM
           * still allows two selects with the same data-field because
           * option state lives per-<ul> not shared. */
          var sel = clone.querySelector('.edl-select[data-field="' + f.field + '"]');
          if (sel) {
            sel.setAttribute('data-value', '');
            var valSpan = sel.querySelector('.edl-select__value');
            if (valSpan) {
              valSpan.textContent = f.placeholder || 'Select';
              valSpan.classList.add('edl-select__value--placeholder');
            }
            if (f.labelKey) {
              var newLbl = f.labelKey + '-' + idx;
              var oldLblEl = clone.querySelector('#' + f.labelKey);
              if (oldLblEl) oldLblEl.setAttribute('id', newLbl);
              var trigger = sel.querySelector('.edl-select__trigger');
              if (trigger) trigger.setAttribute('aria-labelledby', newLbl);
              var menu = sel.querySelector('.edl-select__menu');
              if (menu) menu.setAttribute('aria-labelledby', newLbl);
            }
            var menu2 = sel.querySelector('.edl-select__menu');
            if (menu2) menu2.innerHTML = '';
          }
        } else if (f.kind === 'datepicker' && f.field) {
          /* Rewrite datepicker data-field so cloned triggers don't
           * collide with item-0. Also rewrite the label id +
           * aria-labelledby for a11y. Strip data-cal-wired so
           * wireAdsCalendars() (re-invoked below after append) treats
           * the clone as fresh and binds day-cell / nav click
           * handlers to its popover. */
          var dp = clone.querySelector('.ads-datepicker[data-field="' + f.field + '"]');
          if (dp) {
            var newField = f.field + '-' + idx;
            dp.setAttribute('data-field', newField);
            dp.removeAttribute('data-value');
            dp.removeAttribute('data-cal-wired');
            var valSpan2 = dp.querySelector('.ads-datepicker__value');
            if (valSpan2) {
              valSpan2.textContent = f.placeholder || 'Select date';
              valSpan2.classList.add('ads-datepicker__value--placeholder');
            }
            if (f.labelKey) {
              var newDpLbl = f.labelKey + '-' + idx;
              var oldDpLbl = clone.querySelector('#' + f.labelKey);
              if (oldDpLbl) oldDpLbl.setAttribute('id', newDpLbl);
              var dpTrigger = dp.querySelector('.ads-datepicker__trigger');
              if (dpTrigger) dpTrigger.setAttribute('aria-labelledby', newDpLbl);
            }
          }
        }
      });

      /* Reset error states on the clone. */
      var errs = clone.querySelectorAll('.field__error');
      errs.forEach(function(e) { e.hidden = true; e.textContent = ''; });
      var invalids = clone.querySelectorAll('.field.is-invalid');
      invalids.forEach(function(el) { el.classList.remove('is-invalid'); });

      if (initialValues) {
        populateNodeWithValues(clone, initialValues, idx);
      }

      return clone;
    }

    /* Populate a single premium-item node's form with a values object. */
    function populateNodeWithValues(node, values, idx) {
      PREM_FIELDS.forEach(function(f) {
        var v = values[f.key];
        if (v == null) return;
        if (f.kind === 'input' && f.id) {
          var domId = idx === 0 ? f.id : (f.id + '-' + idx);
          var inp = node.querySelector('#' + domId);
          if (inp) inp.value = v;
        } else if (f.kind === 'edl-select' && f.field) {
          var sel = node.querySelector('.edl-select[data-field="' + f.field + '"]');
          if (sel) {
            sel.setAttribute('data-value', v);
            var valSpan = sel.querySelector('.edl-select__value');
            if (valSpan) {
              valSpan.textContent = v || (f.placeholder || 'Select');
              if (v) valSpan.classList.remove('edl-select__value--placeholder');
              else valSpan.classList.add('edl-select__value--placeholder');
            }
          }
        } else if (f.kind === 'datepicker' && f.field) {
          /* For dynamic items the data-field has been suffixed; for
           * item 0 it's the base value. Query both so this populates
           * either variant. */
          var dp = node.querySelector('.ads-datepicker[data-field="' + f.field + '"]')
                 || node.querySelector('.ads-datepicker[data-field="' + f.field + '-' + idx + '"]');
          if (dp) {
            dp.setAttribute('data-value', v);
            var valSpan2 = dp.querySelector('.ads-datepicker__value');
            if (valSpan2) {
              valSpan2.textContent = formatDateForDisplay(v);
              valSpan2.classList.remove('ads-datepicker__value--placeholder');
            }
          }
        }
      });
      var titleVal = node.querySelector('[data-premitem-name]');
      if (titleVal && values.name) titleVal.textContent = values.name;
    }

    function formatDateForDisplay(iso) {
      /* Convert YYYY-MM-DD to a friendly MM/DD/YYYY string. Falls back
       * to the raw string if parsing fails. */
      if (!iso) return '';
      var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(iso));
      if (!m) return String(iso);
      return m[2] + '/' + m[3] + '/' + m[1];
    }

    /* -----------------------------------------------------------------
     *  Attach / remove
     * ---------------------------------------------------------------- */
    function attachNewBlank(focusFirst) {
      var itemIdx;
      if (attached.length === 0) {
        itemIdx = 0;
        attached.push({ idx: 0, source: 'new', existingId: null });
      } else {
        itemIdx = nextIdx++;
        var node = buildPremItemNode(itemIdx, null);
        if (node) {
          list.appendChild(node);
          try { populateEdlSelectOptions(); } catch (_) {}
          try { wireEdlSelects(); } catch (_) {}
          /* Wire day-cell + nav click handlers on the freshly cloned
           * .ads-datepicker instances (guarded by data-cal-wired so
           * existing wired instances aren't double-bound). */
          try { wireAdsCalendars(); } catch (_) {}
        }
        attached.push({ idx: itemIdx, source: 'new', existingId: null });
      }
      updateStage();
      if (focusFirst) {
        setTimeout(function() { focusFirstFieldOfItem(itemIdx); }, 20);
      }
    }

    function attachExisting(record) {
      var already = attached.find(function(a) { return a.existingId === record.id; });
      if (already) {
        flashItem(already.idx);
        closeResults(false);
        return;
      }

      var itemIdx;
      if (attached.length === 0) {
        itemIdx = 0;
        attached.push({ idx: 0, source: 'existing', existingId: record.id });
        var item0 = list.querySelector('[data-premitem-idx="0"]');
        if (item0) populateNodeWithValues(item0, record, 0);
      } else {
        itemIdx = nextIdx++;
        var node = buildPremItemNode(itemIdx, record);
        if (node) {
          list.appendChild(node);
          try { populateEdlSelectOptions(); } catch (_) {}
          try { wireEdlSelects(); } catch (_) {}
          try { wireAdsCalendars(); } catch (_) {}
        }
        attached.push({ idx: itemIdx, source: 'existing', existingId: record.id });
      }
      updateStage();
      closeResults(true);
      searchInput.value = '';
      updateClearVisibility();
      requestAnimationFrame(function() {
        var el = list.querySelector('[data-premitem-idx="' + itemIdx + '"]');
        if (el && el.scrollIntoView) {
          el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
      });
    }

    function removeItem(idx) {
      if (idx === 0) {
        var item0 = list.querySelector('[data-premitem-idx="0"]');
        if (item0) {
          PREM_FIELDS.forEach(function(f) {
            if (f.kind === 'input' && f.id) {
              var inp = item0.querySelector('#' + f.id);
              if (inp) inp.value = '';
            } else if (f.kind === 'edl-select' && f.field) {
              var sel = item0.querySelector('.edl-select[data-field="' + f.field + '"]');
              if (sel) {
                sel.setAttribute('data-value', '');
                var valSpan = sel.querySelector('.edl-select__value');
                if (valSpan) {
                  valSpan.textContent = f.placeholder || 'Select';
                  valSpan.classList.add('edl-select__value--placeholder');
                }
              }
            } else if (f.kind === 'datepicker' && f.field) {
              var dp = item0.querySelector('.ads-datepicker[data-field="' + f.field + '"]');
              if (dp) {
                dp.removeAttribute('data-value');
                var valSpan2 = dp.querySelector('.ads-datepicker__value');
                if (valSpan2) {
                  valSpan2.textContent = f.placeholder || 'Select date';
                  valSpan2.classList.add('ads-datepicker__value--placeholder');
                }
              }
            }
          });
          var titleVal = item0.querySelector('[data-premitem-name]');
          if (titleVal) titleVal.textContent = 'New premium adjustment';
        }
        attached = attached.filter(function(a) { return a.idx !== 0; });
      } else {
        var node = list.querySelector('[data-premitem-idx="' + idx + '"]');
        if (node && node.parentNode) node.parentNode.removeChild(node);
        attached = attached.filter(function(a) { return a.idx !== idx; });
      }
      updateStage();
    }

    function focusFirstFieldOfItem(idx) {
      var node = list.querySelector('[data-premitem-idx="' + idx + '"]');
      if (!node) return;
      /* First logical field is the edl-select trigger for "Attach rows
       * to rate card". field__input class covers both text inputs and
       * edl-select triggers. */
      var first = node.querySelector('.field__input');
      if (first && first.focus) first.focus();
    }

    function flashItem(idx) {
      var node = list.querySelector('[data-premitem-idx="' + idx + '"]');
      if (!node) return;
      node.classList.add('is-flash');
      setTimeout(function() { node.classList.remove('is-flash'); }, 900);
      if (node.scrollIntoView) node.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      try {
        if (typeof toastV12 === 'function') {
          toastV12(
            { message: 'This premium adjustment is already attached.', variant: 'info', duration: 3200 },
            'This premium adjustment is already attached.',
            { variant: 'info', duration: 3200 }
          );
        }
      } catch (_) {}
    }

    /* -----------------------------------------------------------------
     *  Search + results
     *  Matches: name, category, calcMethod (raw + friendly), attach,
     *  attachedRows, displayName. Case-insensitive.
     * ---------------------------------------------------------------- */
    function filterResults(query) {
      var q = (query || '').trim().toLowerCase();
      if (!q) return [];
      return EXISTING_PREMIUM_ADJUSTMENTS.filter(function(r) {
        var friendlyCalc = friendlyCalcMethod(r.calcMethod).toLowerCase();
        return (
          (r.name && r.name.toLowerCase().indexOf(q) !== -1) ||
          (r.category && r.category.toLowerCase().indexOf(q) !== -1) ||
          (r.calcMethod && r.calcMethod.toLowerCase().indexOf(q) !== -1) ||
          friendlyCalc.indexOf(q) !== -1 ||
          (r.attach && r.attach.toLowerCase().indexOf(q) !== -1) ||
          (r.attachedRows && r.attachedRows.toLowerCase().indexOf(q) !== -1) ||
          (r.displayName && r.displayName.toLowerCase().indexOf(q) !== -1)
        );
      });
    }

    function escapeHtml(s) {
      return String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    function friendlyCalcMethod(m) {
      if (m === 'ADDITIVE_CPM') return 'Fixed CPM increase';
      if (m === 'MULTIPLICATIVE_PCT') return 'Percentage increase';
      if (m === 'FLAT_RATE') return 'Flat rate';
      return m || '';
    }

    function formatValue(v, calcMethod) {
      if (v == null) return '';
      var n = parseFloat(v);
      if (isNaN(n)) return String(v);
      if (calcMethod === 'MULTIPLICATIVE_PCT') return n.toFixed(1) + '%';
      if (calcMethod === 'ADDITIVE_CPM')       return '+$' + n.toFixed(2) + ' CPM';
      if (calcMethod === 'FLAT_RATE')          return '$' + n.toFixed(2) + ' flat';
      return String(v);
    }

    function renderResultsList() {
      if (filtered.length === 0) {
        resultsBox.innerHTML =
          '<div class="ads-search__empty">' +
          '<strong>No matches</strong>' +
          '<div class="ads-search__empty-hint">Try a premium name, category, calculation method, or attached rate card row.</div>' +
          '</div>';
        return;
      }
      var html = '<div class="ads-search__group-head">Existing premium adjustments</div>';
      html += filtered.map(function(r, i) {
        var attachedAlready = attached.some(function(a) { return a.existingId === r.id; });
        return (
          '<button type="button" role="option" class="ads-search__result' +
          (i === activeResultIdx ? ' is-active' : '') + '"' +
          (attachedAlready ? ' data-disabled="true"' : '') +
          ' data-result-idx="' + i + '"' +
          ' aria-selected="' + (i === activeResultIdx ? 'true' : 'false') + '">' +
            '<div class="ads-search__result-line1">' +
              '<span class="ads-search__result-name">' + escapeHtml(r.name) + '</span>' +
              '<span class="ads-search__result-rate">' + escapeHtml(formatValue(r.value, r.calcMethod)) + '</span>' +
            '</div>' +
            '<div class="ads-search__result-line2">' +
              '<span class="ads-search__result-meta"><strong>' + escapeHtml(r.category) + '</strong></span>' +
              '<span class="ads-search__result-meta">' + escapeHtml(friendlyCalcMethod(r.calcMethod)) + '</span>' +
              '<span class="ads-search__result-meta">' + escapeHtml(r.attach) + '</span>' +
              (r.attachedRows
                ? '<span class="ads-search__result-meta">' + escapeHtml(r.attachedRows) + '</span>'
                : ''
              ) +
            '</div>' +
            (attachedAlready
              ? '<div class="ads-search__result-attached">' +
                  '<svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true"><path d="M2.5 6.2l2.4 2.3 4.6-5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>' +
                  'Already attached' +
                '</div>'
              : ''
            ) +
          '</button>'
        );
      }).join('');
      resultsBox.innerHTML = html;
    }

    function openResults() {
      if (!isV12()) return;
      resultsBox.hidden = false;
      searchInput.setAttribute('aria-expanded', 'true');
      var q = searchInput.value;
      filtered = filterResults(q);
      if (filtered.length && activeResultIdx < 0) activeResultIdx = 0;
      if (activeResultIdx >= filtered.length) activeResultIdx = filtered.length - 1;
      renderResultsList();
      searchWrap.setAttribute('data-filled', q ? 'true' : 'false');
    }

    function closeResults(clearActive) {
      resultsBox.hidden = true;
      searchInput.setAttribute('aria-expanded', 'false');
      if (clearActive) activeResultIdx = -1;
    }

    function updateClearVisibility() {
      var has = searchInput.value.length > 0;
      searchClear.hidden = !has;
      searchWrap.setAttribute('data-filled', has ? 'true' : 'false');
    }

    /* -----------------------------------------------------------------
     *  Wire events
     * ---------------------------------------------------------------- */
    searchInput.addEventListener('input', function() {
      if (!isV12()) return;
      activeResultIdx = -1;
      updateClearVisibility();
      if (searchInput.value.trim().length === 0) {
        closeResults(true);
        return;
      }
      openResults();
    });

    searchInput.addEventListener('focus', function() {
      if (!isV12()) return;
      if (searchInput.value.trim().length > 0) openResults();
    });

    searchInput.addEventListener('keydown', function(e) {
      if (!isV12()) return;
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        if (resultsBox.hidden) { openResults(); return; }
        if (filtered.length === 0) return;
        activeResultIdx = (activeResultIdx + 1) % filtered.length;
        renderResultsList();
        scrollActiveIntoView();
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        if (resultsBox.hidden || filtered.length === 0) return;
        activeResultIdx = activeResultIdx <= 0 ? filtered.length - 1 : activeResultIdx - 1;
        renderResultsList();
        scrollActiveIntoView();
      } else if (e.key === 'Enter') {
        if (resultsBox.hidden || filtered.length === 0 || activeResultIdx < 0) return;
        e.preventDefault();
        var r = filtered[activeResultIdx];
        if (r) attachExisting(r);
      } else if (e.key === 'Escape') {
        if (!resultsBox.hidden) {
          e.preventDefault();
          closeResults(true);
        }
      }
    });

    function scrollActiveIntoView() {
      var el = resultsBox.querySelector('.ads-search__result.is-active');
      if (el && el.scrollIntoView) el.scrollIntoView({ block: 'nearest' });
    }

    resultsBox.addEventListener('click', function(e) {
      var btn = e.target && e.target.closest ? e.target.closest('.ads-search__result') : null;
      if (!btn) return;
      var idx = parseInt(btn.getAttribute('data-result-idx'), 10);
      if (isNaN(idx)) return;
      var r = filtered[idx];
      if (!r) return;
      if (btn.getAttribute('data-disabled') === 'true') {
        var already = attached.find(function(a) { return a.existingId === r.id; });
        if (already) flashItem(already.idx);
        return;
      }
      attachExisting(r);
    });

    resultsBox.addEventListener('mousemove', function(e) {
      var btn = e.target && e.target.closest ? e.target.closest('.ads-search__result') : null;
      if (!btn) return;
      var idx = parseInt(btn.getAttribute('data-result-idx'), 10);
      if (isNaN(idx) || idx === activeResultIdx) return;
      activeResultIdx = idx;
      renderResultsList();
    });

    searchClear.addEventListener('click', function(e) {
      e.preventDefault();
      searchInput.value = '';
      updateClearVisibility();
      closeResults(true);
      searchInput.focus();
    });

    document.addEventListener('pointerdown', function(e) {
      if (!isV12()) return;
      if (resultsBox.hidden) return;
      if (searchWrap.contains(e.target)) return;
      closeResults(true);
    });

    addBtn.addEventListener('click', function(e) {
      if (!isV12()) return;
      e.preventDefault();
      attachNewBlank(true);
    });

    list.addEventListener('click', function(e) {
      if (!isV12()) return;
      var btn = e.target && e.target.closest ? e.target.closest('[data-action="remove-prem-item"]') : null;
      if (!btn) return;
      e.preventDefault();
      var idx = parseInt(btn.getAttribute('data-premitem-idx'), 10);
      if (isNaN(idx)) return;
      /* Confirmation policy: untouched blank -> no confirm; edited or
       * populated -> confirm. Treat any item with a Value or attached
       * category as meaningful. */
      var meaningful = isItemMeaningful(idx);
      if (!meaningful) {
        removeItem(idx);
        return;
      }
      adsConfirm({
        title: 'Remove this premium?',
        body: 'This premium adjustment will be removed from the rate card '
          + 'file. Any changes to it will be discarded.',
        confirmLabel: 'Remove premium'
      }, function () { removeItem(idx); });
    });

    function isItemMeaningful(idx) {
      var node = list.querySelector('[data-premitem-idx="' + idx + '"]');
      if (!node) return false;
      var valueSel = idx === 0 ? '#prem-value' : ('#prem-value-' + idx);
      var value = node.querySelector(valueSel);
      var categorySel = node.querySelector('.edl-select[data-field="prem-category"]');
      var hasValue = value && value.value && value.value.trim().length > 0;
      var hasCategory = categorySel && (categorySel.getAttribute('data-value') || '').trim().length > 0;
      return hasValue || hasCategory;
    }

    /* Initial state: Stage 1. */
    updateStage();
    updateClearVisibility();

    /* Edit-mode entry: if the canonical item-0 form is already
     * populated (openEditRateCard pre-fills it), auto-attach item 0
     * so the user lands in Stage 2 instead of Stage 1 with hidden
     * pre-filled fields. */
    if (isV12()) {
      var valueEl = document.getElementById('prem-value');
      var categoryEl = document.querySelector('.edl-select[data-field="prem-category"]');
      var attachEl2 = document.querySelector('.edl-select[data-field="prem-attach"]');
      var prefilled = (
        (valueEl && valueEl.value && valueEl.value.trim())
        || (categoryEl && (categoryEl.getAttribute('data-value') || '').trim())
        || (attachEl2 && (attachEl2.getAttribute('data-value') || '').trim())
      );
      if (prefilled) {
        attached.push({ idx: 0, source: 'new', existingId: null });
        updateStage();
      }
    }
  }
})();
