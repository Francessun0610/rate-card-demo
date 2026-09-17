/* Rate Card Manager Version 2.x (2.0 and its 2.1 fork)
 * Isolated master-detail Create/Edit controller.
 *
 * SECURITY-REVIEW: localStorage is external, user-controlled serialized
 * input. Every payload is parsed inside try/catch, allowlisted into a known
 * schema, and rendered with textContent or DOM constructors only. */
(function () {
  "use strict";

  var STORAGE_KEY = "rate-card-manager.v2.files";
  /* Versions this controller drives. v2.1 was forked from v2.0 on
   * 2026-08-12 as an exact duplicate, so both tokens mount the same
   * master-detail experience and share STORAGE_KEY (a rate card saved
   * in one is visible in the other, which is what "2.1 has every 2.0
   * feature and its data" requires). Mirrors isV2Family() in app.js. */
  var ACTIVE_VERSIONS = ["2.0", "2.1"];
  var root = null;
  var file = null;
  var contextKey = "";
  var loadedCardName = "";
  var dirty = false;
  /* Persisted baseline of the pricing collections (LINE + PREM), captured
   * once the card finishes loading and again after every successful save.
   * "Save Rate Card" is gated on the working collections differing from
   * this baseline rather than on any click having happened, so viewing,
   * searching, sorting, paging, selecting, tab switching and re-renders
   * never enable it, and manually undoing an edit disables it again.
   * `draftBaseline` covers the extra case of a Details panel that is open
   * with meaningful input the live-sync has not committed yet (a new row
   * missing a required field, for instance). */
  var baseline = { lines: "", premiums: "", loaded: false };
  var draftBaseline = { line: "", premium: "" };
  var titleTimer = 0;
  var initiatedBy = null;
  var removeReturnFocus = null;
  var removeModalInertElements = [];
  var removeConfirmationProcessing = false;
  /* Set for the duration of the re-issued click that follows a confirmed
   * "leave without saving", so the guard lets that one through. */
  var leaveConfirmed = false;
  var loadError = "";
  var highlight = { type: "", id: "" };
  var state = {
    activeTab: "lines",
    selected: { lines: "", premiums: "" },
    /* Bulk/action-bar selection (Figma 644:67875) is a separate concept
     * from `selected` above, which tracks the single row open in the
     * Line Details panel. Checking a row never opens the panel and
     * opening the panel never checks a row - see R16 in the task brief. */
    checked: { lines: [], premiums: [] },
    submitting: { line: false, premium: false },
    saving: false,
    loading: false,
    error: "",
    /* LINE opens on Updated date, newest first: a pricing book is read
     * from its most recently negotiated rules, and the alphabetical
     * default stacked every advertiser's rules into one block. Every
     * column still sorts both ways from the header. */
    lines: {
      query: "", filters: {}, sortKey: "updatedAt",
      direction: -1, page: 1, pageSize: 10
    },
    premiums: { query: "", filter: "", sortKey: "displayName", direction: 1, page: 1, pageSize: 10 }
  };

  function isV2() {
    return ACTIVE_VERSIONS.indexOf(document.body.getAttribute("data-version")) !== -1;
  }

  // v2.1's Rate Card Details page (Figma 643:64605 / 643:65724 / 644:67875)
  // replaces the v2.0 always-visible right rail (CARD/LINE/PREM accordions)
  // with a toggleable "Line Details" / "Premium Details" slide-over panel
  // and folds CARD's fields into the read-only header metadata instead.
  // Every v2.1-only behavior in this file is gated behind this helper so
  // v2.0 stays byte-for-byte the same.
  function isV21() {
    return document.body.getAttribute("data-version") === "2.1";
  }

  // The current app's own required-field rules for a LINE row (used by
  // validateItemForm's explicit-submit path in v2.0/2.1, and reused as-is
  // by v2.1's live-sync check below - no new required fields invented).
  var LINE_REQUIRED_FIELDS = ["advertiserId", "adProduct", "baseOffering", "rateType", "baseRate", "currency"];
  var PREMIUM_REQUIRED_FIELDS = ["calculationMethod", "value"];
  // Base Rate and Premium Value are the two numeric required fields, and
  // 0 is a real value for both, so they are checked against this rather
  // than for truthiness anywhere a required field is tested.
  var DECIMAL_PATTERN = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/;

  function text(value, max) {
    var out = value == null ? "" : String(value).trim();
    return typeof max === "number" ? out.slice(0, max) : out;
  }

  function finiteNumber(value, allowBlank) {
    if (allowBlank && (value === "" || value == null)) return "";
    var n = Number(value);
    return Number.isFinite(n) ? n : "";
  }

  function displayCardTitle(value) {
    return text(value, 240);
  }

  function safeId(value, prefix) {
    var clean = text(value, 80).replace(/[^A-Za-z0-9_-]/g, "");
    return clean || prefix + "-" + Date.now().toString(36);
  }

  function validateCard(raw) {
    raw = raw && typeof raw === "object" ? raw : {};
    var marketplace = ["Upfront", "Scatter", "Multi-Year"].indexOf(raw.marketplace) >= 0
      ? raw.marketplace : "";
    return {
      id: text(raw.id, 100),
      name: text(raw.name, 240),
      marketplace: marketplace,
      dealSeason: /^\d{4}-\d{4}$/.test(text(raw.dealSeason, 9))
        ? text(raw.dealSeason, 9) : "2025-2026",
      buyingEntityId: text(raw.buyingEntityId, 100),
      buyingEntityName: text(raw.buyingEntityName, 160),
      effectiveStart: /^\d{4}-\d{2}-\d{2}$/.test(text(raw.effectiveStart, 10))
        ? text(raw.effectiveStart, 10) : "",
      effectiveEnd: /^\d{4}-\d{2}-\d{2}$/.test(text(raw.effectiveEnd, 10))
        ? text(raw.effectiveEnd, 10) : "",
      dcmRuleOrder: finiteNumber(raw.dcmRuleOrder, true)
    };
  }

  function validateLine(raw, idx) {
    raw = raw && typeof raw === "object" ? raw : {};
    var line = {
      id: safeId(raw.id, "line-" + (idx + 1)),
      attachToCard: text(raw.attachToCard, 240),
      advertiserId: text(raw.advertiserId, 100),
      advertiserName: text(raw.advertiserName, 160),
      advertiserCategory: text(raw.advertiserCategory, 120),
      adProduct: text(raw.adProduct, 300),
      baseOffering: text(raw.baseOffering, 120),
      rateType: text(raw.rateType, 80),
      baseRate: finiteNumber(raw.baseRate, false),
      currency: ["USD", "CAD", "EUR", "GBP"].indexOf(raw.currency) >= 0
        ? raw.currency : "USD",
      condition1: text(raw.condition1, 900),
      createdAt: text(raw.createdAt, 40),
      updatedAt: text(raw.updatedAt, 40)
    };
    ["upfrontId", "condition2", "condition3", "condition4"].forEach(function (key) {
      var legacyValue = text(raw[key], key === "upfrontId" ? 100 : 140);
      if (legacyValue) line[key] = legacyValue;
    });
    return line;
  }

  function validatePremium(raw, idx) {
    raw = raw && typeof raw === "object" ? raw : {};
    var methods = ["Additive CPM", "Flat Fee", "Percent Adjustment"];
    var lineItemIds = Array.isArray(raw.lineItemIds)
      ? raw.lineItemIds.slice(0, 1000).map(function (id) {
          return safeId(id, "");
        }).filter(Boolean)
      : [];
    var premium = {
      id: safeId(raw.id, "premium-" + (idx + 1)),
      attachToCard: text(raw.attachToCard, 240),
      category: text(raw.category, 120),
      displayName: text(raw.displayName, 160),
      calculationMethod: methods.indexOf(raw.calculationMethod) >= 0
        ? raw.calculationMethod : "",
      value: finiteNumber(raw.value, false),
      stackOrder: finiteNumber(raw.stackOrder, true),
      condition1: text(raw.condition1, 900),
      /* The offerings a premium is allowed to price. Authored on the
       * record because it is part of the rule, not a readout of whatever
       * rows happen to be attached; premiums without it fall back to the
       * attached rows' offerings (see premiumBaseOffering). */
      baseOffering: text(raw.baseOffering, 240),
      /* "card" means the premium applies to every advertiser buying this
       * rate card. It is a deliberate value rather than a blank
       * advertiser, so nothing downstream has to read an empty name as
       * either card-wide or missing. */
      advertiserScope: raw.advertiserScope === "card" ? "card"
        : (text(raw.advertiserId) || text(raw.advertiserName) ? "advertiser" : ""),
      advertiserId: text(raw.advertiserId, 100),
      effectiveStart: /^\d{4}-\d{2}-\d{2}$/.test(text(raw.effectiveStart, 10))
        ? text(raw.effectiveStart, 10) : "",
      effectiveEnd: /^\d{4}-\d{2}-\d{2}$/.test(text(raw.effectiveEnd, 10))
        ? text(raw.effectiveEnd, 10) : "",
      lineItemIds: Array.from(new Set(lineItemIds)),
      createdAt: text(raw.createdAt, 40),
      updatedAt: text(raw.updatedAt, 40)
    };
    ["advertiserName", "condition2", "condition3"].forEach(function (key) {
      var legacyValue = text(raw[key], key === "advertiserName" ? 160 : 140);
      if (legacyValue) premium[key] = legacyValue;
    });
    return premium;
  }

  /* One reading of a premium's advertiser scope for the table, search,
   * sort and export, so those four can never disagree about whether a
   * record is card-wide. */
  function premiumAdvertiserLabel(row) {
    if (row && row.advertiserScope === "card") return "All Advertisers";
    return text(row && row.advertiserName) || "All Advertisers";
  }

  function validateFile(raw) {
    if (!raw || typeof raw !== "object") return null;
    return {
      schemaVersion: 1,
      status: raw.status === "Published" ? "Published" : "Draft",
      card: validateCard(raw.card),
      lines: Array.isArray(raw.lines) ? raw.lines.slice(0, 1000).map(validateLine) : [],
      premiums: Array.isArray(raw.premiums)
        ? raw.premiums.slice(0, 1000).map(validatePremium) : [],
      createdAt: text(raw.createdAt, 40),
      updatedAt: text(raw.updatedAt, 40),
      fixtureKey: text(raw.fixtureKey, 80),
      syntheticDemoData: raw.syntheticDemoData === true
    };
  }

  function readFiles() {
    loadError = "";
    try {
      var parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        loadError = "The saved rate card data is not valid.";
        return {};
      }
      var out = {};
      Object.keys(parsed).slice(0, 500).forEach(function (key) {
        var valid = validateFile(parsed[key]);
        if (valid) out[safeId(key, "file")] = valid;
      });
      return out;
    } catch (_) {
      loadError = "The saved rate card data could not be read.";
      return {};
    }
  }

  function persistFile() {
    if (!file || !file.card.id) return false;
    try {
      var files = readFiles();
      file.updatedAt = new Date().toISOString();
      files[file.card.id] = validateFile(file);
      localStorage.setItem(STORAGE_KEY, JSON.stringify(files));
      return true;
    } catch (_) {
      showErrorToast("Unable to save rate card", "Try again.");
      return false;
    }
  }

  /* Hands the just-saved CARD values to the Rate Card Manager list so the
   * row there shows what was actually saved. app.js owns the list model
   * and does the matching, so a repeated save updates one row instead of
   * adding another. */
  function syncListRowFromFile() {
    if (!file || !file.card.id) return;
    var sync = window.RCMListSync;
    if (!sync || typeof sync.upsertFromRateCardFile !== "function") return;
    try {
      sync.upsertFromRateCardFile({
        rateCardId: file.card.id,
        name: file.card.name,
        status: file.status,
        marketplace: file.card.marketplace,
        buyingEntityId: file.card.buyingEntityId,
        buyingEntityName: file.card.buyingEntityName,
        dealSeason: file.card.dealSeason,
        effectiveStart: file.card.effectiveStart,
        effectiveEnd: file.card.effectiveEnd,
        dcmRuleOrder: file.card.dcmRuleOrder
      });
    } catch (_) { /* list sync is best effort; the rate card itself saved */ }
  }

  function blankFile() {
    return {
      schemaVersion: 1,
      status: "Draft",
      card: validateCard({ dealSeason: "2025-2026" }),
      lines: [],
      premiums: [],
      updatedAt: ""
    };
  }

  /* The rate card dialog lives in app.js and is shared with the list
   * page, but the open rate card file lives here. This is the seam: the
   * dialog reads the CARD it is about to edit, and hands the edited
   * values back to be validated, persisted, and mirrored to the list.
   * CARD metadata is saved on its own, so it deliberately leaves the
   * Line and Premium dirty state alone. */
  /* The dialog's Deal Season select speaks the list's short form
   * ("25-26"); the file keeps PRD R4's "YYYY-YYYY". */
  /* The dialog now speaks the same YYYY-YYYY the record stores, so this
   * is a pass-through. It is kept as the single place that would change
   * if the dialog ever needed a different presentation of a season. */
  function seasonToShortForm(value) {
    return text(value, 9);
  }

  function seasonToStoredForm(value) {
    // The season menu labels its options with an en dash while the
    // select's own default value uses a hyphen, so both reach here.
    var short = /^(\d{2})[-\u2013](\d{2})$/.exec(text(value, 9));
    if (!short) return text(value, 9);
    var start = Number(short[1]);
    var end = Number(short[2]);
    return "20" + short[1] + "-" + (end < start ? "21" : "20") + short[2];
  }

  /* The dialog's date pickers render MM/DD/YYYY; the file stores PRD
   * R4's ISO date. Anything already ISO passes through untouched. */
  function dateToStoredForm(value) {
    var raw = text(value, 10);
    if (!raw || /^\d{4}-\d{2}-\d{2}$/.test(raw)) return raw;
    var mdy = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(raw);
    return mdy ? mdy[3] + "-" + mdy[1] + "-" + mdy[2] : "";
  }

  window.RCMCardEditor = {
    getCard: function (cardId) {
      if (!file || !file.card || !cardId || file.card.id !== cardId) return null;
      return {
        id: file.card.id,
        name: file.card.name,
        marketplace: file.card.marketplace,
        season: seasonToShortForm(file.card.dealSeason),
        buyingEntityId: file.card.buyingEntityId,
        buyingEntityName: file.card.buyingEntityName,
        dcmRuleOrder: file.card.dcmRuleOrder === null ? "" : String(file.card.dcmRuleOrder),
        effectiveStart: file.card.effectiveStart,
        effectiveEnd: file.card.effectiveEnd
      };
    },
    /* The stored file is keyed by the card's ID, and every LINE and PREM
     * row points back at it by that same ID. Changing the ID therefore
     * cannot be a field edit: the old key has to be dropped and the
     * children repointed, or the rate card would still be on disk under
     * an ID nothing references and its rows would be orphaned. */
    renameCard: function (previousId, nextId) {
      if (!file || !file.card || !previousId || !nextId) return false;
      if (file.card.id !== previousId || previousId === nextId) return false;
      try {
        var files = readFiles();
        delete files[previousId];
        file.card.id = nextId;
        (file.lines || []).forEach(function (line) {
          if (line.attachToCard === previousId) line.attachToCard = nextId;
        });
        (file.premiums || []).forEach(function (premium) {
          if (premium.attachToCard === previousId) premium.attachToCard = nextId;
        });
        file.updatedAt = new Date().toISOString();
        files[nextId] = validateFile(file);
        localStorage.setItem(STORAGE_KEY, JSON.stringify(files));
      } catch (_) {
        return false;
      }
      /* The page identifies its record through the URL, so a deep link
       * left pointing at the old ID would reopen an empty card. */
      try {
        var url = new URL(window.location.href);
        if (url.searchParams.get("cardId") === previousId) {
          url.searchParams.set("cardId", nextId);
          window.history.replaceState({}, "", url.pathname + url.search + url.hash);
        }
      } catch (_) { /* URL rewriting is cosmetic; the file already moved */ }
      hydrateCardForm();
      return true;
    },
    applyCard: function (cardId, values) {
      if (!file || !file.card || !cardId || file.card.id !== cardId) return false;
      values = values && typeof values === "object" ? values : {};
      file.card = validateCard({
        id: cardId,
        name: values.name,
        marketplace: values.marketplace,
        dealSeason: values.season
          ? seasonToStoredForm(values.season) : file.card.dealSeason,
        buyingEntityId: values.buyingEntityId,
        buyingEntityName: values.buyingEntityName,
        effectiveStart: dateToStoredForm(values.effectiveStart),
        effectiveEnd: dateToStoredForm(values.effectiveEnd),
        dcmRuleOrder: values.dcmRuleOrder
      });
      if (!persistFile()) return false;
      loadedCardName = text(file.card.name, 240);
      syncListRowFromFile();
      hydrateCardForm();
      updateTitle(true);
      return true;
    }
  };

  // Matched on the row's own data-rate-card-id rather than the text of a
  // Rate Card ID cell: 2.1 folds that column into the combined
  // "Rate Card ID / Name" cell, so cell text is not a stable handle.
  function findListRow(cardId) {
    return document.querySelector(
      '.table__body .row[data-rate-card-id="' + cardId.replace(/"/g, '\\"') + '"]');
  }

  // A card the user just created through the Create rate card dialog has
  // no catalog record, but it is not an undemoed fixture either: it has
  // to open empty so the first line the user adds is the first line on
  // the card. RATE_CARDS marks those rows userSaved.
  function listRecordFor(cardId) {
    var cards = window.RATE_CARDS;
    if (!Array.isArray(cards)) return null;
    return cards.find(function (card) { return card.rateCardId === cardId; }) || null;
  }

  function seedEditFile(cardId) {
    var record = listRecordFor(cardId);
    if (record && record.userSaved) {
      var fresh = blankFile();
      fresh.status = record.status === "Published" ? "Published" : "Draft";
      fresh.card = validateCard({
        id: cardId,
        name: record.name || cardId,
        marketplace: ["Upfront", "Scatter", "Multi-Year"].indexOf(record.marketplace) >= 0
          ? record.marketplace : "",
        dealSeason: record.season || "",
        buyingEntityId: record.saleshubId || "",
        buyingEntityName: record.buyingEntity || "",
        effectiveStart: record.effectiveStart || "",
        effectiveEnd: record.effectiveEnd || ""
      });
      return validateFile(fresh);
    }

    var catalogRecord = window.RCMRateCards
      && typeof window.RCMRateCards.getByRateCardId === "function"
      ? window.RCMRateCards.getByRateCardId(cardId)
      : null;
    var catalogFile = catalogRecord && window.RCMCatalog
      && typeof window.RCMCatalog.buildFile === "function"
      ? window.RCMCatalog.buildFile(catalogRecord)
      : null;
    if (catalogFile) return validateFile(catalogFile);

    var row = findListRow(cardId);
    var name = row ? text((row.querySelector(".name") || {}).textContent, 240) : cardId;
    var marketplace = row ? text((row.querySelector(".cell--marketplace") || {}).textContent) : "Upfront";
    var buyer = row ? text((row.querySelector(".cell--buying-entity") || {}).textContent, 160) : "";
    var saleshub = row ? text((row.querySelector(".cell--saleshub") || {}).textContent, 100) : "";
    var seeded = blankFile();
    seeded.status = "Published";
    seeded.card = validateCard({
      id: cardId,
      name: name || cardId,
      marketplace: ["Upfront", "Scatter", "Multi-Year"].indexOf(marketplace) >= 0
        ? marketplace : "Upfront",
      dealSeason: "2025-2026",
      buyingEntityId: saleshub || "0013a00004Hc5w2AAB",
      buyingEntityName: buyer || "WPP",
      effectiveStart: "2025-10-01",
      effectiveEnd: "2026-09-30"
    });
    /* A LINE prices an advertiser, not the agency that bought the card.
     * This list used to hold holdcos and agencies (WPP Media, GroupM,
     * Mindshare, Omnicom Media Group), so a fallback-seeded card showed
     * its own buying entity sitting in the Advertiser column. Ids, names,
     * offerings and conditions match the catalog fixture's controlled
     * vocabulary so the same advertiser and the same rule read the same
     * way wherever they appear. */
    var advertisers = window.RCMCatalog && window.RCMCatalog.advertisers
      ? window.RCMCatalog.advertisers.map(function (item) { return [item.id, item.name]; })
      : [];
    var seedRules = [
      ["Standard Video", "Disney+ Select", "No additional targeting", 34],
      ["Standard Video", "Hulu Select", "Demographic: Age \u2192 Adults 18-49", 34.25],
      ["Connected TV Video", "Disney Streaming Bundle", "Device: Connected TV", 41.75],
      ["Standard Video", "Disney+ Select", "Audience: Authenticated Streaming Households", 36],
      ["Pause Ad", "Hulu Select", "Demographic: Age \u2192 Adults 25-54", 34.75],
      ["Sports Video", "ESPN Streaming Sports", "Audience: Sports Fans \u2192 NFL Fans", 50]
    ];
    seeded.lines = advertisers.map(function (adv, index) {
      var rule = seedRules[index % seedRules.length];
      return validateLine({
        id: "line-seed-" + (index + 1),
        attachToCard: seeded.card.id,
        advertiserId: adv[0],
        advertiserName: adv[1],
        adProduct: rule[0],
        baseOffering: rule[1],
        rateType: "CPM",
        baseRate: rule[3],
        currency: "USD",
        condition1: rule[2],
        updatedAt: new Date(2026, 5, 10 + index).toISOString()
      }, index);
    });
    /* Category must be a value the Premium Category dropdown offers
     * (Geo, Duration, 1P Audience, 3P Audience, Device Type, Format,
     * Content). Four of these used to be free text (Audience targeting,
     * Position, Sponsorship, Inventory), so opening a seeded premium
     * showed a Category the field could not round-trip. Display names
     * now say what triggers the adjustment and leave the amount to the
     * Value field. */
    seeded.premiums = [
      ["1P Audience", "Demographic Guarantee Premium", "Additive CPM", 3],
      ["Geo", "Regional Geo Premium", "Percent Adjustment", 9],
      ["Content", "Seasonal Demand Premium", "Percent Adjustment", 18],
      ["Content", "Live Event Premium", "Flat Fee", 25000],
      ["Format", "High-Impact Format Premium", "Additive CPM", 6.25],
      ["Device Type", "Connected TV Premium", "Percent Adjustment", 10]
    ].map(function (item, index) {
      return validatePremium({
        id: "premium-seed-" + (index + 1),
        attachToCard: seeded.card.id,
        advertiserName: index % 2 || !advertisers[index]
          ? "All Advertisers" : advertisers[index][1],
        category: item[0],
        displayName: item[1],
        calculationMethod: item[2],
        value: item[3],
        stackOrder: index + 1
      }, index);
    });
    return seeded;
  }

  function currentContext() {
    var params = new URLSearchParams(location.search);
    var mode = params.get("mode") === "edit" ? "edit" : "create";
    return {
      mode: mode,
      cardId: mode === "edit" ? text(params.get("cardId"), 100) : "",
      key: mode + ":" + (params.get("cardId") || "new")
    };
  }

  function loadContext(force) {
    if (!root || !isV2()) return;
    var ctx = currentContext();
    if (!force && ctx.key === contextKey && file) return;
    contextKey = ctx.key;
    state.loading = true;
    state.error = "";
    root.setAttribute("aria-busy", "true");
    var files = readFiles();
    state.error = loadError;
    if (ctx.mode === "edit" && ctx.cardId) {
      var demo = window.RCMDemoRateCard;
      var demoFile = demo && typeof demo.getFile === "function"
        ? validateFile(demo.getFile(ctx.cardId))
        : null;
      file = files[ctx.cardId] || demoFile || seedEditFile(ctx.cardId);
    } else {
      file = blankFile();
    }
    loadedCardName = ctx.mode === "edit" ? text(file.card.name, 240) : "";
    state.activeTab = "lines";
    state.selected.lines = "";
    state.selected.premiums = "";
    state.submitting.line = false;
    state.submitting.premium = false;
    state.lines = {
      query: "", filters: {}, sortKey: "updatedAt",
      direction: -1, page: 1, pageSize: 10
    };
    state.premiums = { query: "", filter: "", sortKey: "displayName", direction: 1, page: 1, pageSize: 10 };
    dirty = false;
    state.saving = false;
    /* No baseline while the card is still loading: Save has nothing to
     * compare against yet and must not flicker enabled during init. */
    baseline.loaded = false;
    hydrateCardForm();
    clearItemForm("line");
    clearItemForm("premium");
    openAccordion("card");
    renderAll();
    syncLineFilterBadge();
    updateTitle(true);
    syncWorkspaceState();
    updateSaveState();
    requestAnimationFrame(function () {
      if (contextKey !== ctx.key) return;
      state.loading = false;
      root.setAttribute("aria-busy", "false");
      renderAll();
      openFirstRowByDefault("lines");
      // Baseline is established only once the card and both collections
      // have resolved, so a load can never register as a change.
      captureBaseline();
      updateSaveState();
    });
  }

  /* The Details panel is the working surface of this page, so a tab that
   * already has rows opens with the first one showing rather than making
   * the user click a row to see anything at all. Nothing is selected on a
   * card with no rows, and a blank create draft has none, so this quietly
   * does nothing there.
   *
   * It runs on load and on every tab switch, because the panel is shared:
   * arriving on Premiums with the Line Details panel still holding a line
   * would leave the page describing a record the table no longer lists.
   * Callers guard unsaved work before getting here, so anything still
   * open is safe to replace.
   *
   * This is the active detail row, not a bulk selection: it never ticks
   * the row's checkbox and never raises the action bar. */
  function openFirstRowByDefault(type) {
    if (!isV21() || state.loading || state.activeTab !== type) return;
    var formType = type === "lines" ? "line" : "premium";
    var open = openPanelType();
    // The panel is already this tab's, including a record being created,
    // so it owns itself.
    if (open === formType) return;
    // A closed panel stays closed, because the user closed it. The one
    // exception is a tab nobody has opened a record on yet, which is the
    // load-time default of showing the first row.
    if (!open && state.selected[type]) return;
    var rows = filteredRows(type);
    var view = state[type];
    var start = (view.page - 1) * view.pageSize;
    // Back to the row this tab was last on when it is still in the
    // filtered results, otherwise the first row of the current page.
    var previous = state.selected[type];
    var target = previous && rows.some(function (row) { return row.id === previous; })
      ? previous
      : (rows.slice(start, start + view.pageSize)[0] || {}).id;
    if (!target) return;
    selectRow(type, target, null, { focusPanel: false });
  }

  function fieldValue(form, name) {
    var control = form.elements.namedItem(name);
    if (!control) return "";
    if (control instanceof RadioNodeList) return text(control.value);
    if (control.tagName === "SELECT" && control.multiple) {
      return Array.prototype.map.call(control.selectedOptions, function (option) {
        return text(option.value);
      }).filter(Boolean).join(", ");
    }
    if (control.type === "checkbox") return control.checked;
    return text(control.value);
  }

  function formObject(form) {
    var out = {};
    Array.prototype.forEach.call(form.elements, function (control) {
      if (!control.name || control.disabled) return;
      if (control.type === "checkbox") out[control.name] = control.checked;
      else if (control.tagName === "SELECT" && control.multiple) {
        out[control.name] = Array.prototype.map.call(control.selectedOptions, function (option) {
          return text(option.value);
        }).filter(Boolean).join(", ");
      } else out[control.name] = text(control.value);
    });
    return out;
  }

  function populateForm(form, values) {
    if (!form) return;
    Array.prototype.forEach.call(form.elements, function (control) {
      /* The conditions field owns two hidden inputs and a chip
       * rendering, so the control fills itself from the record below
       * rather than being written field by field here. */
      if (control.matches("[data-cond-value], [data-cond-json]")) return;
      if (!control.name) return;
      var value = values && values[control.name] != null ? values[control.name] : "";
      if (control.type === "checkbox") {
        control.checked = Boolean(value);
      } else if (control.tagName === "SELECT" && control.multiple) {
        var selected = String(value).split(",").map(function (part) { return part.trim(); });
        Array.prototype.forEach.call(control.options, function (option) {
          option.selected = selected.indexOf(option.value) >= 0;
        });
      } else {
        var dynamicLineSelect = control.tagName === "SELECT"
          && control.name === "advertiserName"
          && control.closest('[data-v2-form="line"]');
        var premiumSelect = control.tagName === "SELECT"
          && (control.name === "category" || control.name === "calculationMethod")
          && control.closest('[data-v2-form="premium"]');
        if (dynamicLineSelect) {
          control.querySelectorAll("option[data-runtime-option]").forEach(function (option) {
            option.remove();
          });
          if (value && !Array.prototype.some.call(control.options, function (option) {
            return option.value === String(value);
          })) {
            var runtimeOption = document.createElement("option");
            runtimeOption.value = String(value);
            runtimeOption.textContent = String(value);
            runtimeOption.setAttribute("data-runtime-option", "");
            control.appendChild(runtimeOption);
          }
        }
        if (control.name === "category" && control.tagName === "SELECT") {
          control.querySelectorAll("option[data-legacy-option]").forEach(function (option) {
            option.remove();
          });
        }
        if (control.name === "category" && control.tagName === "SELECT" && value
            && !Array.prototype.some.call(control.options, function (option) {
              return option.value === String(value);
            })) {
          var legacyOption = document.createElement("option");
          legacyOption.value = String(value);
          legacyOption.textContent = String(value);
          legacyOption.setAttribute("data-legacy-option", "");
          control.appendChild(legacyOption);
        }
        /* Money reads as money. The table quotes a rate to the cent, so
         * the panel showing the same record quotes it the same way
         * rather than dropping a trailing zero (38.5 next to $38.50). */
        var moneyField = control.tagName === "INPUT"
          && (control.name === "baseRate" || control.name === "value")
          && value !== "" && Number.isFinite(Number(value));
        control.value = moneyField ? Number(value).toFixed(2) : value;
        if ((premiumSelect || dynamicLineSelect)
            && control.tagName === "SELECT"
            && typeof window.refreshAdsDropdown === "function") {
          window.refreshAdsDropdown(control);
        }
      }
      control.removeAttribute("aria-invalid");
      if (control.closest(".ads-dd")) {
        var dropdownTrigger = control.closest(".ads-dd").querySelector(".ads-dd__trigger");
        if (dropdownTrigger) {
          dropdownTrigger.removeAttribute("aria-invalid");
          dropdownTrigger.removeAttribute("aria-describedby");
        }
        if (typeof window.syncAdsDropdown === "function") {
          window.syncAdsDropdown(control);
        }
      }
      var fieldEl = control.closest(".field");
      if (fieldEl) fieldEl.classList.remove("is-invalid");
    });
    form.querySelectorAll(".field__error").forEach(function (error) {
      error.hidden = true;
      error.textContent = "";
    });
    populateConditionField(form, values);
  }

  /* Conditions resolve against the approved catalog, so this runs after
   * the generic pass: it needs the record, not the form's own value. */
  function populateConditionField(form, values) {
    var host = form && form.querySelector("[data-conditions]");
    if (!host || !host.__conditionField) return;
    host.__conditionField.set(
      values && values.condition1 != null ? values.condition1 : "",
      values && values.conditionsJson != null ? values.conditionsJson : ""
    );
  }

  function hydrateCardForm() {
    var form = root.querySelector('[data-v2-form="card"]');
    populateForm(form, file.card);
    syncDatePicker("effectiveStart", file.card.effectiveStart, "Select start date");
    syncDatePicker("effectiveEnd", file.card.effectiveEnd, "Select end date");
    var idEl = root.querySelector("[data-v2-card-id]");
    if (idEl) {
      idEl.textContent = file.card.id || "Auto-generated on Save";
      idEl.classList.toggle("is-default", !file.card.id);
    }
  }

  function syncDatePicker(name, value, placeholder, formType) {
    var input = root.querySelector(
      '[data-v2-form="' + (formType || "card") + '"] [name="' + name + '"]'
    );
    var picker = input && input.closest(".ads-datepicker");
    var valueEl = picker && picker.querySelector(".ads-datepicker__value");
    if (!input || !valueEl) return;
    input.value = value || "";
    if (value) {
      var parts = value.split("-");
      valueEl.textContent = parts.length === 3
        ? parts[1] + "/" + parts[2] + "/" + parts[0]
        : value;
      valueEl.classList.remove("ads-datepicker__value--placeholder");
    } else {
      valueEl.textContent = placeholder;
      valueEl.classList.add("ads-datepicker__value--placeholder");
    }
  }

  function syncPremiumDatePickers(values) {
    values = values || {};
    syncDatePicker("effectiveStart", values.effectiveStart, "Select start date", "premium");
    syncDatePicker("effectiveEnd", values.effectiveEnd, "Select end date", "premium");
  }

  function updateFileCard() {
    var form = root.querySelector('[data-v2-form="card"]');
    if (!form || !file) return;
    var raw = formObject(form);
    raw.id = file.card.id;
    file.card = validateCard(raw);
    syncAttachFields();
  }

  function syncAttachFields() {
    var label = file.card.id || file.card.name || "Current rate card";
    var lineAttach = root.querySelector('[data-v2-form="line"] [name="attachToCard"]');
    var premiumAttach = root.querySelector('[data-v2-form="premium"] [name="attachToCard"]');
    if (lineAttach) lineAttach.value = label;
    if (premiumAttach) premiumAttach.value = label;
  }

  function cardIsValid(show) {
    var required = ["name", "marketplace", "effectiveStart", "effectiveEnd"];
    var form = root.querySelector('[data-v2-form="card"]');
    var valid = true;
    required.forEach(function (name) {
      var control = form.elements.namedItem(name);
      var value = fieldValue(form, name);
      var ok = Boolean(value);
      if (!ok) valid = false;
      if (show) setFieldValidity(control, ok, "Required");
    });
    var start = fieldValue(form, "effectiveStart");
    var end = fieldValue(form, "effectiveEnd");
    if (start && end && start > end) {
      valid = false;
      if (show) {
        setFieldValidity(
          form.elements.namedItem("effectiveEnd"),
          false,
          "Effective end date must be on or after the start date"
        );
      }
    }
    return valid;
  }

  function setFieldValidity(control, valid, message) {
    if (!control) return;
    var fieldEl = control.closest(".field");
    var error = fieldEl && fieldEl.querySelector(".field__error");
    var customTrigger = fieldEl && fieldEl.querySelector(".ads-dd__trigger");
    var displayControl = customTrigger || (control.type === "hidden"
      ? fieldEl && fieldEl.querySelector(".ads-datepicker__trigger")
      : control);
    if (displayControl) displayControl.setAttribute("aria-invalid", valid ? "false" : "true");
    if (fieldEl) fieldEl.classList.toggle("is-invalid", !valid);
    if (error) {
      if (!error.id) error.id = control.id + "-error";
      if (valid && displayControl) displayControl.removeAttribute("aria-describedby");
      else if (displayControl) displayControl.setAttribute("aria-describedby", error.id);
      if (typeof window.setFieldError === "function") {
        window.setFieldError(error, valid ? "" : message);
      } else {
        error.setAttribute("role", "alert");
        error.textContent = valid ? "" : message;
        error.hidden = valid;
      }
    }
  }

  function validateItemForm(type) {
    var form = root.querySelector('[data-v2-form="' + type + '"]');
    var rules = type === "line" ? LINE_REQUIRED_FIELDS : PREMIUM_REQUIRED_FIELDS;
    var valid = true;
    rules.forEach(function (name) {
      var control = form.elements.namedItem(name);
      var value = fieldValue(form, name);
      var ok = value !== "";
      var message = "Required";
      if ((name === "baseRate" || name === "value") && value !== "") {
        ok = DECIMAL_PATTERN.test(value) && Number.isFinite(Number(value));
        message = "Enter a valid decimal value";
      }
      if (!ok) valid = false;
      setFieldValidity(control, ok, message);
    });
    if (type === "premium") {
      /* Application Order is the premium's place in the stack, so it is a
       * whole positive number or nothing at all. PRD R11 already types it
       * as an integer; this is where the form enforces it. */
      var stackOrder = fieldValue(form, "stackOrder");
      var stackControl = form.elements.namedItem("stackOrder");
      var stackValid = !stackOrder
        || (/^\d+$/.test(stackOrder) && Number(stackOrder) > 0);
      if (!stackValid) valid = false;
      setFieldValidity(stackControl, stackValid, "Enter a whole number greater than 0");
      var premiumStart = fieldValue(form, "effectiveStart");
      var premiumEnd = fieldValue(form, "effectiveEnd");
      var startControl = form.elements.namedItem("effectiveStart");
      var endControl = form.elements.namedItem("effectiveEnd");
      var startValid = !premiumStart
        || (premiumStart >= file.card.effectiveStart && premiumStart <= file.card.effectiveEnd);
      var endValid = !premiumEnd
        || (premiumEnd >= file.card.effectiveStart && premiumEnd <= file.card.effectiveEnd);
      if (premiumStart && premiumEnd && premiumStart > premiumEnd) {
        endValid = false;
      }
      if (!startValid || !endValid) valid = false;
      setFieldValidity(
        startControl,
        startValid,
        "Date must fall within the rate card effective dates"
      );
      setFieldValidity(
        endControl,
        endValid,
        premiumStart && premiumEnd && premiumStart > premiumEnd
          ? "Effective end date must be on or after the start date"
          : "Date must fall within the rate card effective dates"
      );
    }
    if (!valid) {
      var first = form.querySelector('[aria-invalid="true"]');
      if (first) first.focus();
    }
    return valid;
  }

  function setDirty(next) {
    dirty = Boolean(next);
  }

  /* ---- Unsaved LINE / PREM change tracking ---------------------------
   * A signature is the persisted fields of a collection in a stable key
   * order, so re-rendering, re-sorting, paging or a round trip through
   * validateLine/validatePremium can never read as a change. updatedAt is
   * bookkeeping the user neither sees nor edits, so it stays out. Empty
   * values all normalise to "", while 0 keeps its own value because a
   * zero base rate or a zero premium is a real, meaningful number. */
  var PRICING_BOOKKEEPING_KEYS = ["updatedAt", "createdAt"];

  function pricingSignature(rows) {
    if (!Array.isArray(rows)) return "[]";
    return JSON.stringify(rows.map(function (row) {
      return Object.keys(row).filter(function (key) {
        return PRICING_BOOKKEEPING_KEYS.indexOf(key) === -1;
      }).sort().map(function (key) {
        return key + "=" + (row[key] == null ? "" : String(row[key]));
      });
    }));
  }

  /* The open Details panel is compared separately: a brand-new row that
   * is still missing a required field has not reached file.lines yet (the
   * live sync only commits complete rows), but the typing the user has
   * already done is unsaved work all the same. Comparing against the
   * snapshot taken when the panel opened means focusing a field, opening
   * a dropdown, or retyping the value that was already there all stay
   * clean. */
  function itemFormSignature(type) {
    var form = root && root.querySelector('[data-v2-form="' + type + '"]');
    if (!form) return "";
    var values = formObject(form);
    return Object.keys(values).filter(function (key) {
      return key !== "id" && key !== "attachToCard";
    }).sort().map(function (key) {
      return key + "=" + values[key];
    }).join("|");
  }

  function itemPanelOpen(type) {
    var accordion = root && root.querySelector('[data-v2-accordion="' + type + '"]');
    return Boolean(accordion && accordion.classList.contains("is-open"));
  }

  function captureDraftBaseline(type) {
    draftBaseline[type] = itemFormSignature(type);
    // Save changes is offered against this baseline, so the footer has to
    // be re-read whenever the baseline moves.
    syncPanelFooter(type);
  }

  function hasOpenDraftChanges() {
    return ["line", "premium"].some(function (type) {
      return itemPanelOpen(type) && itemFormSignature(type) !== draftBaseline[type];
    });
  }

  function hasUnsavedPricingChanges() {
    if (!file || !baseline.loaded) return false;
    return pricingSignature(file.lines) !== baseline.lines
      || pricingSignature(file.premiums) !== baseline.premiums
      || hasOpenDraftChanges();
  }

  // Card-level form edits (v2.0's CARD accordion) plus pricing changes.
  // Drives the leave-page guards only; Save Rate Card is pricing-only.
  function hasUnsavedWork() {
    return dirty || hasUnsavedPricingChanges();
  }

  function captureBaseline() {
    if (!file) {
      baseline.loaded = false;
      return;
    }
    baseline.lines = pricingSignature(file.lines);
    baseline.premiums = pricingSignature(file.premiums);
    baseline.loaded = true;
    captureDraftBaseline("line");
    captureDraftBaseline("premium");
  }

  function discardWorkingState() {
    dirty = false;
    baseline.loaded = false;
    contextKey = "";
    file = null;
  }

  function showOperationToast(message) {
    if (typeof window.toast !== "function") return null;
    return window.toast({
      title: message,
      message: "",
      variant: "info"
    });
  }

  function showErrorToast(title, message) {
    if (typeof window.toast !== "function") return null;
    return window.toast({
      title: title,
      message: message,
      variant: "error"
    });
  }

  function updateSaveState() {
    if (!root) return;
    var button = root.querySelector('[data-v2-action="save-card"]');
    var draft = root.querySelector('[data-v2-action="save-draft"]');
    var valid = cardIsValid(false);
    var named = Boolean(fieldValue(root.querySelector('[data-v2-form="card"]'), "name"));
    if (button) {
      button.disabled = !valid;
      button.setAttribute("aria-disabled", valid ? "false" : "true");
    }
    if (draft) {
      draft.disabled = !named;
      draft.setAttribute("aria-disabled", named ? "false" : "true");
    }
    updateSaveMenuAvailability();
  }

  function syncWorkspaceState() {
    if (!root) return;
    var form = root.querySelector('[data-v2-form="card"]');
    var control = form && form.elements.namedItem("name");
    var cardName = control ? control.value : file && file.card && file.card.name;
    var hasCardName =
      typeof cardName === "string" && cardName.trim().length > 0;
    var showCreateDescription = !hasCardName;
    var isEdit = currentContext().mode === "edit";
    root.setAttribute(
      "data-workspace-state",
      isEdit || hasCardName ? "named" : "initial"
    );
    var helper = root.querySelector("[data-v2-helper]");
    if (helper) {
      helper.textContent =
        "Enter the rate card details, then add line items and premium adjustments.";
      helper.hidden = !showCreateDescription;
    }
  }

  function updateTitle(immediate) {
    if (!root || !file) return;
    window.clearTimeout(titleTimer);
    var apply = function () {
      var ctx = currentContext();
      var form = root.querySelector('[data-v2-form="card"]');
      var control = form && form.elements.namedItem("name");
      var name = text(control ? control.value : file.card.name, 240);
      var titleEl = document.querySelector("[data-v2-title]");
      var caption = document.querySelector("[data-v2-title-caption]");
      var pageTitle = ctx.mode === "edit"
        ? displayCardTitle(name || loadedCardName || "Edit Rate Card")
        : (name || "Create New Rate Card");
      if (titleEl) {
        titleEl.textContent = pageTitle;
        titleEl.setAttribute("aria-label", pageTitle);
        titleEl.setAttribute("data-tooltip", pageTitle);
      }
      updateTitleEditAffordance(pageTitle, ctx);
      if (caption) caption.hidden = true;
      syncWorkspaceState();
      updateV2Meta();
    };
    if (immediate) apply();
    else titleTimer = window.setTimeout(apply, 240);
  }

  // Editing the CARD is reached from an explicit link at the end of the
  // metadata row, not from the title. Create mode has nothing saved to
  // edit yet, so the link is absent there rather than present and inert.
  function updateTitleEditAffordance(pageTitle, ctx) {
    var group = document.querySelector("[data-v2-meta-edit]");
    if (!group) return;
    var editable = isV21()
      && ctx.mode === "edit"
      && Boolean(currentCardId())
      && typeof window.openEditRateCardModal === "function";
    group.hidden = !editable;
    var link = group.querySelector("[data-v2-edit-card-link]");
    if (!link) return;
    /* The visible words are the accessible name. The rate card it acts
     * on is named by the heading directly above it, so repeating it here
     * would only make the link longer to hear. */
    link.disabled = !editable;
  }

  function currentCardId() {
    var ctx = currentContext();
    return (file && file.card && file.card.id) || ctx.cardId || "";
  }

  function openCardDetailsEditor(trigger) {
    var cardId = currentCardId();
    if (!cardId || typeof window.openEditRateCardModal !== "function") return;
    /* Passing the trigger is what returns focus here when the modal
     * closes; openAdsModal keeps it as the return target. */
    window.openEditRateCardModal(cardId, trigger
      || document.querySelector("[data-v2-edit-card-link]"));
  }

  // The shared modal writes the edited CARD straight to the same file
  // store this page reads, then announces it. Re-read that one card and
  // refresh only the header, so the table, panel, search, filters, and
  // pagination all stay exactly where the user left them.
  function refreshCardFromStorage(cardId) {
    if (!file || !cardId || cardId !== currentCardId()) return;
    var files = readFiles();
    var saved = files[cardId];
    if (!saved || !saved.card) return;
    file.card = saved.card;
    if (saved.updatedAt) file.updatedAt = saved.updatedAt;
    loadedCardName = text(file.card.name, 240);
    hydrateCardForm();
    updateTitle(true);
    updateSaveState();
  }

  // Shown as the stored YYYY-YYYY. Figma 644:67888 drew a fiscal-year
  // range ("FY26 - FY27"), but that is a second spelling of the same
  // season, and the season has to read the same everywhere it appears
  // so a reader can match this card to a file.
  function formatDealSeason(value) {
    return text(value);
  }

  // v2.1's Rate Card Details page shows read-only CARD metadata under
  // the name instead of the always-open CARD accordion. Chips lead and
  // the plain-text pair follows: Status, Marketplace, Deal Season, then
  // Buying Entity, using the Figma 644:67884 / 67888 / 67889 / 67890
  // treatments. Every piece is optional except Status - an unset value
  // is omitted outright rather than rendered as "undefined", "null", or
  // a dangling separator.
  function updateV2Meta() {
    if (!root) return;
    var wrap = document.querySelector("[data-v2-meta]");
    if (!wrap) return;
    var isEdit = currentContext().mode === "edit";
    var show = isV2() && document.body.getAttribute("data-version") === "2.1" && isEdit;
    wrap.hidden = !show;
    if (!show) return;
    var statusEl = wrap.querySelector("[data-v2-meta-status]");
    if (statusEl) {
      var draft = (file.status || "Draft") !== "Published";
      statusEl.textContent = draft ? "Draft" : "Published";
      statusEl.className = "chip rcm-status-chip chip--" + (draft ? "draft" : "published")
        + " rcm-status-chip--" + (draft ? "draft" : "published");
      statusEl.hidden = false;
    }
    // Display name only. Falling back to the Saleshub ID would print a
    // raw account id where the reader expects a company.
    var entity = text(file.card.buyingEntityName);
    var season = formatDealSeason(file.card.dealSeason);
    var marketplace = text(file.card.marketplace);
    var entityEl = wrap.querySelector("[data-v2-meta-entity]");
    if (entityEl) {
      entityEl.textContent = entity;
      entityEl.hidden = !entity;
    }
    var seasonEl = wrap.querySelector("[data-v2-meta-season]");
    if (seasonEl) {
      seasonEl.textContent = season;
      seasonEl.hidden = !season;
    }
    var separator = wrap.querySelector("[data-v2-meta-separator]");
    if (separator) separator.hidden = !(entity && season);
    var textEl = wrap.querySelector("[data-v2-meta-text]");
    if (textEl) textEl.hidden = !entity && !season;
    var marketplaceEl = wrap.querySelector("[data-v2-meta-marketplace]");
    if (marketplaceEl) {
      marketplaceEl.textContent = marketplace;
      marketplaceEl.hidden = !marketplace;
    }
    // An empty chip group still takes a column gap on each side, which
    // would read as a hole where the chips used to be. Status always
    // renders today, so this only guards future callers.
    var chipsEl = wrap.querySelector(".rcm-meta-chips");
    if (chipsEl) {
      chipsEl.hidden = !!(statusEl && statusEl.hidden) && !marketplace;
    }
  }

  function openAccordion(section, focusFirst) {
    if (isV21() && section === "card") {
      // v2.1 has no CARD accordion - its fields live in the read-only
      // header metadata instead (see updateV2Meta). Every v2.0 call site
      // that opens "card" as its way of saying "nothing is being edited
      // right now" instead closes the Line/Premium Details panel here.
      closeV2Panel();
      return;
    }
    root.querySelectorAll("[data-v2-accordion]").forEach(function (accordion) {
      var open = accordion.getAttribute("data-v2-accordion") === section;
      accordion.classList.toggle("is-open", open);
      var trigger = accordion.querySelector(".create-md__accordion-trigger");
      var panel = accordion.querySelector(".create-md__accordion-panel");
      if (trigger) trigger.setAttribute("aria-expanded", open ? "true" : "false");
      if (panel) panel.hidden = !open;
    });
    if (focusFirst) {
      requestAnimationFrame(function () {
        var panel = root.querySelector('[data-v2-accordion="' + section + '"] .create-md__accordion-panel');
        var first = panel && panel.querySelector("input:not([type=hidden]):not([readonly]), select, button");
        if (first) first.focus();
      });
    }
    updateV2PanelChrome();
  }

  // v2.1's "Save Rate Card" split button (this task). The dropdown holds
  // exactly one item, "Save as draft", which performs the identical
  // saveFile("Draft") action as the main button - see the save-draft/
  // save-card handler in init(). This only toggles the menu's own open/
  // closed UI state.
  function saveMenuEls() {
    var wrap = root && root.querySelector("[data-v2-header-splitbtn]");
    return {
      wrap: wrap,
      caret: wrap && wrap.querySelector('[data-v2-action="toggle-save-menu"]'),
      menu: wrap && wrap.querySelector(".splitbtn__menu")
    };
  }

  function openSaveMenu() {
    var els = saveMenuEls();
    if (!els.menu || !els.caret || els.caret.disabled) return;
    els.menu.hidden = false;
    els.caret.setAttribute("aria-expanded", "true");
    var firstItem = els.menu.querySelector(".splitbtn__item");
    if (firstItem) firstItem.focus();
    document.addEventListener("click", handleSaveMenuOutsideClick, true);
    document.addEventListener("keydown", handleSaveMenuKeydown, true);
  }

  function closeSaveMenu(returnFocus) {
    var els = saveMenuEls();
    if (!els.menu || els.menu.hidden) return;
    els.menu.hidden = true;
    if (els.caret) els.caret.setAttribute("aria-expanded", "false");
    document.removeEventListener("click", handleSaveMenuOutsideClick, true);
    document.removeEventListener("keydown", handleSaveMenuKeydown, true);
    if (returnFocus && els.caret) els.caret.focus();
  }

  function toggleSaveMenu() {
    var els = saveMenuEls();
    if (els.menu && !els.menu.hidden) closeSaveMenu(true);
    else openSaveMenu();
  }

  function handleSaveMenuOutsideClick(event) {
    var els = saveMenuEls();
    if (els.wrap && els.wrap.contains(event.target)) return;
    closeSaveMenu(false);
  }

  function handleSaveMenuKeydown(event) {
    var els = saveMenuEls();
    if (!els.menu || els.menu.hidden) return;
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      closeSaveMenu(true);
      return;
    }
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp" && event.key !== "Tab") return;
    var items = Array.prototype.slice.call(els.menu.querySelectorAll(".splitbtn__item"));
    if (!items.length) return;
    var index = items.indexOf(document.activeElement);
    if (event.key === "Tab") {
      // A single-item menu keeps Tab from escaping to the rest of the
      // page while open, matching the trapped feel of the other
      // dropdown/menu patterns in this app.
      event.preventDefault();
      items[0].focus();
      return;
    }
    event.preventDefault();
    var nextIndex = event.key === "ArrowDown"
      ? (index + 1) % items.length
      : (index - 1 + items.length) % items.length;
    items[nextIndex].focus();
  }

  /* v2.1's split button saves the LINE and PREM collections, so it stays
   * disabled until those collections actually differ from what is stored
   * (Figma 644:68223 disabled state). Creating a card, opening one,
   * browsing it, or opening a Details panel is not work to save. The card
   * still has to be named, since an unnamed card has nothing to save the
   * rows against, and a save already in flight keeps it disabled so the
   * same rows cannot be submitted twice. */
  function updateSaveMenuAvailability() {
    var els = saveMenuEls();
    if (!els.wrap) return;
    var mainButton = els.wrap.querySelector(".splitbtn__main");
    var named = Boolean(fieldValue(root.querySelector('[data-v2-form="card"]'), "name"));
    var enabled = named && hasUnsavedPricingChanges() && !state.saving;
    if (mainButton) {
      mainButton.disabled = !enabled;
      mainButton.setAttribute("aria-disabled", enabled ? "false" : "true");
    }
    if (els.caret) {
      els.caret.disabled = !enabled;
      els.caret.setAttribute("aria-disabled", enabled ? "false" : "true");
    }
    if (!enabled) closeSaveMenu(false);
  }

  function collapseAccordion(section) {
    var accordion = root.querySelector('[data-v2-accordion="' + section + '"]');
    if (!accordion) return;
    accordion.classList.remove("is-open");
    var trigger = accordion.querySelector(".create-md__accordion-trigger");
    var panel = accordion.querySelector(".create-md__accordion-panel");
    if (trigger) trigger.setAttribute("aria-expanded", "false");
    if (panel) panel.hidden = true;
    updateV2PanelChrome();
  }

  function switchTab(type, focusTab) {
    if (type !== "premiums") type = "lines";
    state.activeTab = type;
    root.querySelectorAll("[data-v2-tab]").forEach(function (tab) {
      var active = tab.getAttribute("data-v2-tab") === type;
      tab.classList.toggle("is-selected", active);
      tab.setAttribute("aria-selected", active ? "true" : "false");
      tab.tabIndex = active ? 0 : -1;
      if (active && focusTab) tab.focus();
    });
    root.querySelectorAll("[data-v2-panel]").forEach(function (panel) {
      panel.hidden = panel.getAttribute("data-v2-panel") !== type;
    });
    syncToolbarLayout();
    renderType(type);
    openFirstRowByDefault(type);
  }

  /* Both tabs share one Details panel, so leaving a tab is the same loss
   * of work as closing the panel or switching rows, and asks the same
   * question first. Every way into the other tab goes through here rather
   * than straight to switchTab, so none of them can become the one that
   * discards silently. */
  function requestSwitchTab(type, focusTab) {
    if (type !== "premiums") type = "lines";
    if (type === state.activeTab) {
      // Home/End can land on the tab already showing. Nothing to switch,
      // but roving tabindex still owes the key its focus move.
      var current = focusTab && root.querySelector('[data-v2-tab="' + type + '"]');
      if (current) current.focus();
      return;
    }
    var open = openPanelType();
    if (!open) {
      switchTab(type, focusTab);
      return;
    }
    if (open === "line") commitLineLiveSync();
    confirmDiscardDraft(open, "Switching tabs", function () {
      switchTab(type, focusTab);
    });
  }

  // ---- v2.1 single toolbar row (Figma 644:67875) -----------------------
  // Add Line Item, Filter and Search sit at the left of one row and the
  // Line / Premiums control sits at its right end. Both pieces already
  // exist: the tab list above the panels and one toolbar per panel. This
  // moves the active panel's toolbar and the tab list into the shared
  // row rather than duplicating either control, and puts them back where
  // the 2.0 markup expects them when the page is not on 2.1.
  var toolbarHomes = null;

  function rememberToolbarHomes() {
    if (toolbarHomes || !root) return;
    var tabs = root.querySelector(".create-md__tabs");
    toolbarHomes = {
      tabs: tabs ? { parent: tabs.parentNode, next: tabs.nextSibling } : null,
      toolbars: []
    };
    root.querySelectorAll("[data-v2-panel] > .create-md__toolbar").forEach(function (toolbar) {
      toolbarHomes.toolbars.push({
        node: toolbar,
        parent: toolbar.parentNode,
        next: toolbar.nextSibling
      });
    });
  }

  // 2.1 reads Add Line Item, Filter, Search left to right (644:68218);
  // every other version keeps search at the left edge and the add button
  // at the right edge (455:13900). Moving the nodes rather than reordering
  // them with CSS keeps tab order matching what is on screen.
  var detachedFilters = [];

  function syncToolbarControlOrder() {
    if (!root) return;
    var v21 = isV21();
    if (v21 && detachedFilters.length) {
      detachedFilters.forEach(function (home) {
        if (!home.node.parentNode) home.group.appendChild(home.node);
      });
      detachedFilters = [];
      enhanceV2Selects();
    }
    root.querySelectorAll(".create-md__toolbar-controls").forEach(function (group) {
      var add = group.querySelector(':scope > .btn[data-v2-action^="add-"]');
      var filter = group.querySelector(":scope > .create-md__filter");
      // Filtering is a 2.1 control. Earlier versions never offered it, so
      // it leaves the document entirely rather than sitting there hidden.
      if (filter && !v21) {
        detachedFilters.push({ group: group, node: filter });
        filter.remove();
        filter = null;
      }
      var order = v21
        ? [add, filter, group.querySelector(":scope > .create-md__search")]
        : [group.querySelector(":scope > .create-md__search"), add];
      order.forEach(function (node) {
        if (node) group.appendChild(node);
      });
    });
  }

  // Matches the header cells to the cell order renderRows() writes.
  // 2.1 merges the advertiser pair into one "Advertiser name / ID" column
  // (the list view's combined "Rate Card ID / Name" treatment): the ID
  // header keeps its DOM slot ahead of the name so CSS can drop it, and
  // the name header carries the combined label and the single sort
  // control. The label names the display order of the merged cell, which
  // leads with the advertiser and puts the ID underneath it. Earlier versions keep two separate Advertiser columns, name
  // first. Only the label text node is rewritten, leaving the button's
  // shape (text node then .th__sort span) the same as every other header,
  // so the icon renderSortableHeader() appends survives.
  function syncLineColumnOrder() {
    if (!root) return;
    var id = root.querySelector('[data-v2-sort-header="lines:advertiserId"]');
    var name = root.querySelector('[data-v2-sort-header="lines:advertiserName"]');
    if (!id || !name || id.parentNode !== name.parentNode) return;
    var first = isV21() ? id : name;
    var second = isV21() ? name : id;
    if (first.nextElementSibling !== second) {
      first.parentNode.insertBefore(first, second);
    }
    var label = isV21() ? "Advertiser name / ID" : "Advertiser";
    var button = name.querySelector("[data-v2-sort]");
    if (!button) return;
    button.setAttribute("data-v2-sort-label", label);
    var labelNode = button.firstChild;
    if (labelNode && labelNode.nodeType === 3) labelNode.nodeValue = label;
  }

  function syncToolbarLayout() {
    if (!root) return;
    rememberToolbarHomes();
    syncToolbarControlOrder();
    syncLineColumnOrder();
    var row = root.querySelector("[data-v2-toolbar-row]");
    var slot = root.querySelector("[data-v2-toolbar-slot]");
    var tabs = root.querySelector(".create-md__tabs");
    if (!row || !slot || !tabs || !toolbarHomes) return;
    if (!isV21()) {
      if (toolbarHomes.tabs && tabs.parentNode !== toolbarHomes.tabs.parent) {
        toolbarHomes.tabs.parent.insertBefore(tabs, toolbarHomes.tabs.next);
      }
      toolbarHomes.toolbars.forEach(function (home) {
        if (home.node.parentNode !== home.parent) {
          home.parent.insertBefore(home.node, home.next);
        }
      });
      row.hidden = true;
      return;
    }
    row.hidden = false;
    var activePanel = root.querySelector('[data-v2-panel="' + state.activeTab + '"]');
    var activeToolbar = null;
    toolbarHomes.toolbars.forEach(function (home) {
      if (home.parent === activePanel) activeToolbar = home.node;
      else if (home.node.parentNode !== home.parent) {
        home.parent.insertBefore(home.node, home.next);
      }
    });
    if (activeToolbar && activeToolbar.parentNode !== slot) slot.appendChild(activeToolbar);
    if (tabs.parentNode !== row) row.appendChild(tabs);
  }

  function linesById() {
    var map = {};
    (file.lines || []).forEach(function (line) { map[line.id] = line; });
    return map;
  }

  // A Premium that names the offerings it prices carries them on the
  // record, because that set is part of the rule and does not change when
  // an attached LINE is edited. Older Premiums do not, so they keep the
  // original behavior: their Base Offering is derived live from the
  // attached LINE rows (lineItemIds).
  function premiumBaseOffering(row, byId) {
    var authored = text(row.baseOffering);
    if (authored) return authored;
    var ids = row.lineItemIds || [];
    if (!ids.length) return "";
    var seen = [];
    ids.forEach(function (id) {
      var line = byId[id];
      var offering = line && text(line.baseOffering);
      if (offering && seen.indexOf(offering) < 0) seen.push(offering);
    });
    return seen.join(", ");
  }

  // ---- Line item filter (Figma 644:68219 trigger + ADS field pattern) --
  // The trigger opens a popover of ADS dropdowns built from the values
  // that actually exist on this rate card's LINE rows, so it can never
  // offer a filter that matches nothing. Choices are staged while the
  // popover is open and only applied on Apply, which matches the list
  // page's Cancel / Apply filter behavior.
  /* Drawer field order, and the only fields the Line items table filters
   * on. Line condition is deliberately absent: it stays searchable
   * through the toolbar's search box, where a partial match is more
   * use than picking one of two dozen exact strings. */
  var LINE_FILTER_FIELDS = [
    "advertiserName", "adProduct", "baseOffering", "rateType", "currency"
  ];

  function activeLineFilters() {
    if (!state.lines.filters) state.lines.filters = {};
    return state.lines.filters;
  }

  function lineFilterCount() {
    var filters = activeLineFilters();
    return LINE_FILTER_FIELDS.filter(function (field) { return filters[field]; }).length;
  }

  function lineFilterOptions(field) {
    var seen = [];
    (file && file.lines ? file.lines : []).forEach(function (row) {
      var value = text(row[field]);
      if (value && seen.indexOf(value) < 0) seen.push(value);
    });
    return seen.sort(function (a, b) {
      return a.localeCompare(b, undefined, { numeric: true, sensitivity: "base" });
    });
  }

  function populateLineFilterControls() {
    if (!root) return;
    var filters = activeLineFilters();
    root.querySelectorAll("[data-v2-line-filter]").forEach(function (select) {
      var field = select.getAttribute("data-v2-line-filter");
      var placeholder = select.getAttribute("data-placeholder") || "All";
      var current = filters[field] || "";
      var options = lineFilterOptions(field);
      select.replaceChildren();
      var blank = document.createElement("option");
      blank.value = "";
      blank.textContent = placeholder;
      select.appendChild(blank);
      options.forEach(function (value) {
        var option = document.createElement("option");
        option.value = value;
        option.textContent = value;
        select.appendChild(option);
      });
      select.value = options.indexOf(current) >= 0 ? current : "";
      if (typeof window.refreshAdsDropdown === "function") {
        window.refreshAdsDropdown(select);
      }
    });
  }

  function syncLineFilterBadge() {
    if (!root) return;
    var badge = root.querySelector("[data-v2-filter-count]");
    var trigger = root.querySelector('[data-v2-action="toggle-line-filter"]');
    var count = lineFilterCount();
    if (badge) {
      badge.textContent = count ? String(count) : "";
      badge.hidden = count === 0;
    }
    if (trigger) {
      trigger.classList.toggle("is-active", count > 0);
      trigger.setAttribute(
        "aria-label",
        count ? "Filter line items, " + count + " applied" : "Filter line items"
      );
    }
  }

  function lineFilterPanel() {
    return root && root.querySelector(".fpanel--lines");
  }

  function lineFilterPanelOpen() {
    var panel = lineFilterPanel();
    return Boolean(panel && panel.classList.contains("is-open"));
  }

  /* Everything focusable the drawer currently offers, in tab order. The
   * enhanced selects present as .ads-dd__trigger buttons, so the native
   * <select> each one wraps is skipped: it is hidden and holds
   * tabindex="-1". */
  function lineFilterFocusables() {
    var panel = lineFilterPanel();
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

  /* The drawer is modal, so Tab cycles inside it rather than walking off
   * into the table behind. Only wrapping is handled here; the browser
   * moves focus normally everywhere in between. */
  function trapLineFilterFocus(event) {
    if (event.key !== "Tab" || !lineFilterPanelOpen()) return;
    var items = lineFilterFocusables();
    if (!items.length) return;
    var first = items[0];
    var last = items[items.length - 1];
    var active = document.activeElement;
    if (!event.shiftKey && active === last) {
      event.preventDefault();
      first.focus();
    } else if (event.shiftKey && active === first) {
      event.preventDefault();
      last.focus();
    } else if (!lineFilterPanel().contains(active)) {
      event.preventDefault();
      first.focus();
    }
  }

  function openLineFilterPanel() {
    var panel = lineFilterPanel();
    var trigger = root && root.querySelector('[data-v2-action="toggle-line-filter"]');
    if (!panel || !trigger) return;
    /* One drawer at a time. The list's own filter panel lives on another
     * route and cannot normally be open at the same moment, but it is
     * the same component and closing any open instance costs nothing. */
    document.querySelectorAll(".fpanel.is-open").forEach(function (other) {
      if (other !== panel) other.classList.remove("is-open");
    });
    /* Reseed the controls from the applied filters, which is what makes
     * a close without Apply discard whatever was picked in between. */
    populateLineFilterControls();
    panel.classList.add("is-open");
    trigger.setAttribute("aria-expanded", "true");
    document.addEventListener("click", handleLineFilterOutsideClick, true);
    document.addEventListener("keydown", trapLineFilterFocus, true);
    var first = panel.querySelector(".ads-dd__trigger, select, button");
    if (first) first.focus();
  }

  function closeLineFilterPanel(returnFocus) {
    var panel = lineFilterPanel();
    var trigger = root && root.querySelector('[data-v2-action="toggle-line-filter"]');
    if (!panel || !panel.classList.contains("is-open")) return;
    panel.classList.remove("is-open");
    if (trigger) trigger.setAttribute("aria-expanded", "false");
    document.removeEventListener("click", handleLineFilterOutsideClick, true);
    document.removeEventListener("keydown", trapLineFilterFocus, true);
    if (returnFocus && trigger) trigger.focus();
  }

  function handleLineFilterOutsideClick(event) {
    var panel = lineFilterPanel();
    var host = root && root.querySelector("[data-v2-filter-root]");
    if (!panel || !host) return;
    /* The drawer is no longer inside the trigger's wrapper, so both it
     * and the trigger count as inside. A dropdown menu opened from a
     * field is inside the drawer, so it is covered by the same test. */
    if (panel.contains(event.target) || host.contains(event.target)) return;
    closeLineFilterPanel(false);
  }

  function applyLineFilters() {
    var filters = {};
    root.querySelectorAll("[data-v2-line-filter]").forEach(function (select) {
      filters[select.getAttribute("data-v2-line-filter")] = select.value || "";
    });
    state.lines.filters = filters;
    state.lines.page = 1;
    syncLineFilterBadge();
    renderType("lines");
    closeLineFilterPanel(true);
  }

  function resetLineFilters() {
    state.lines.filters = {};
    state.lines.page = 1;
    populateLineFilterControls();
    syncLineFilterBadge();
    renderType("lines");
  }

  function filteredRows(type) {
    var rows = type === "lines" ? file.lines.slice() : file.premiums.slice();
    var view = state[type];
    var query = text(view.query).toLowerCase();
    var byId = type === "premiums" ? linesById() : null;
    rows = rows.filter(function (row) {
      var searchable = type === "lines"
        ? [
            row.advertiserName,
            row.advertiserId,
            /* Ad type and Base offering are filterable in the drawer and
             * searchable here, because a seller who knows the words is
             * quicker typing them than opening a drawer to pick them. */
            row.adProduct,
            row.baseOffering,
            lineConditionLabel(row.condition1),
            row.attachToCard,
            file.card.id,
            file.card.marketplace,
            file.card.buyingEntityId,
            file.card.buyingEntityName
          ]
        : [row.displayName, row.id, row.category, row.calculationMethod, row.value,
           premiumBaseOffering(row, byId), premiumAdvertiserLabel(row),
           row.advertiserId,
           row.condition1, row.lineItemIds && row.lineItemIds.join(" ")];
      var matchesQuery = !query || searchable.some(function (value) {
        return String(value == null ? "" : value).toLowerCase().indexOf(query) >= 0;
      });
      var matchesFilter = !view.filter || (type === "lines"
        ? row.currency === view.filter : row.calculationMethod === view.filter);
      var matchesLineFilters = type !== "lines" || LINE_FILTER_FIELDS.every(function (field) {
        var wanted = (view.filters || {})[field];
        return !wanted || String(row[field] == null ? "" : row[field]) === wanted;
      });
      return matchesQuery && matchesFilter && matchesLineFilters;
    });
    var key = view.sortKey;
    var direction = view.direction;
    return rows.map(function (row, index) {
      return { row: row, index: index };
    }).sort(function (aEntry, bEntry) {
      var a = aEntry.row;
      var b = bEntry.row;
      var av = a[key];
      var bv = b[key];
      var compared = 0;
      /* Two premium columns show something other than a stored field, so
       * they sort on what the row actually displays: Base offering can be
       * derived from the attached rules, and Advertiser reads
       * "All Advertisers" for a card-wide premium. */
      if (type === "premiums" && (key === "baseOffering" || key === "advertiserName")) {
        av = key === "baseOffering" ? premiumBaseOffering(a, byId) : premiumAdvertiserLabel(a);
        bv = key === "baseOffering" ? premiumBaseOffering(b, byId) : premiumAdvertiserLabel(b);
        compared = String(av).localeCompare(String(bv), undefined, { numeric: true, sensitivity: "base" });
      } else if (type === "lines" && key === "condition1") {
        /* Sorts on the label the row shows, so a card still carrying the
         * legacy "No additional targeting" sentinel groups with the rest
         * of the unconditioned rules instead of filing under N. */
        compared = lineConditionLabel(av).localeCompare(
          lineConditionLabel(bv), undefined, { numeric: true, sensitivity: "base" }
        );
      } else if (key === "baseRate" || key === "value") {
        compared = (Number(av) || 0) - (Number(bv) || 0);
      } else if (key === "updatedAt") {
        compared = (Date.parse(av) || 0) - (Date.parse(bv) || 0);
      } else {
        compared = String(av == null ? "" : av).localeCompare(
          String(bv == null ? "" : bv), undefined, { numeric: true, sensitivity: "base" }
        );
      }
      return compared ? compared * direction : aEntry.index - bEntry.index;
    }).map(function (entry) {
      return entry.row;
    });
  }

  /* A LINE carries at most one optional condition, and "No additional
   * targeting" is how the rate model says there is not one. The fixtures
   * already store that as an empty field, but a rate card saved before
   * that rule can still hold the sentinel, so it is folded back to empty
   * here rather than surfacing as though a condition had been chosen. */
  var NO_LINE_CONDITION = "No additional targeting";

  function lineConditionLabel(value) {
    var label = text(value);
    return label === NO_LINE_CONDITION ? "" : label;
  }

  /* ---- Line conditions as a set -------------------------------------
   * A line item can carry several conditions. They are stored in the one
   * condition1 field as a comma-and-space list, so nothing downstream
   * (the table cell, Quick Edit, CSV export, search, sort) has to learn
   * a new shape.
   *
   * Splitting on the comma is safe for this vocabulary, which separates
   * its parts with ":" and an arrow and never with a comma. A pasted
   * comma list is therefore read as several conditions, which is what
   * someone pasting one means. */
  function lineConditionList(value) {
    var label = lineConditionLabel(value);
    if (!label) return [];
    var seen = Object.create(null);
    return label.split(",").map(function (part) {
      return part.trim();
    }).filter(function (part) {
      if (!part) return false;
      var key = part.toLowerCase();
      if (seen[key]) return false;
      seen[key] = true;
      return true;
    });
  }

  function serializeLineConditions(list) {
    return (list || []).join(", ");
  }

  /* ---- Approved pricing conditions ----------------------------------
   * Catalog, eligibility and the control itself live in conditions.js so
   * Line Details, Premium Details and Quick Edit share one implementation
   * rather than three. */
  var Conditions = window.RCMConditions;

  var conditionFields = [];

  function initConditionFields() {
    if (!root || !Conditions) return;
    root.querySelectorAll("[data-conditions]").forEach(function (host) {
      if (host.__conditionField) return;
      var api = Conditions.createField(host);
      if (api) conditionFields.push(api);
    });
  }

  function conditionFieldFor(formType) {
    var scope = formType === "premium" ? "premium" : "line";
    return conditionFields.filter(function (field) {
      return field.scope === scope;
    })[0] || null;
  }



  /* The Line condition cell.
   *
   * An unset condition prints an em dash rather than "Not set": the
   * field is legitimately empty, not missing. The dash is hidden from
   * assistive tech and paired with real words, so the cell is not
   * announced as a stray punctuation mark.
   *
   * A set condition stays on one line and truncates, with the full label
   * in the shared ADS truncation tooltip. That tooltip opens from
   * delegated mouseover and focusin handlers that walk up from the
   * event target, so the label lives in its own span: a <td> can be
   * hovered but never focused, and the span can be both. The span only
   * becomes a tab stop when the text is actually clipped (see
   * syncLineConditionFocus), so rows whose condition fits do not add a
   * keyboard stop that reveals nothing. */
  function buildLineConditionCell(label) {
    var cell = document.createElement("td");
    cell.className = "create-md__td-line-condition";
    if (!label) {
      cell.classList.add("is-empty");
      var dash = document.createElement("span");
      dash.setAttribute("aria-hidden", "true");
      dash.textContent = "\u2014";
      cell.appendChild(dash);
      var none = document.createElement("span");
      none.className = "sr-only";
      none.textContent = "No line condition";
      cell.appendChild(none);
      return cell;
    }
    var value = document.createElement("span");
    value.className = "create-md__line-condition";
    value.textContent = label;
    value.setAttribute("data-tooltip", label);
    value.setAttribute("data-tooltip-truncate", "auto");
    cell.appendChild(value);
    return cell;
  }

  /* Only a clipped condition owes the keyboard a way to read the rest of
   * it, and whether it clips is a question about the rendered row, so it
   * is answered once the rows are in the document. */
  function syncLineConditionFocus(tbody) {
    tbody.querySelectorAll(".create-md__line-condition").forEach(function (node) {
      var clipped = node.scrollWidth > node.clientWidth + 1;
      if (clipped) node.setAttribute("tabindex", "0");
      else node.removeAttribute("tabindex");
    });
  }

  function makeCell(value, tooltip, className) {
    var cell = document.createElement("td");
    cell.textContent = value == null || value === "" ? "Not set" : String(value);
    if (className) cell.className = className;
    if (tooltip) {
      cell.setAttribute("data-tooltip", String(value));
      cell.setAttribute("data-tooltip-truncate", "auto");
    }
    return cell;
  }

  /* 2.1's single advertiser cell: display name over "ID: ...", the same
   * two-line shape as the list view's combined Rate Card ID / Name cell.
   * With no display name the ID is promoted to the first line instead of
   * being printed twice, and with no ID the second line is dropped rather
   * than reserving empty space for it. */
  function buildAdvertiserCell(row) {
    var cell = document.createElement("td");
    cell.className = "create-md__td-advertiser";
    var stack = document.createElement("span");
    stack.className = "create-md__advertiser";
    var name = text(row.advertiserName);
    var id = text(row.advertiserId);
    stack.appendChild(advertiserLine(
      "create-md__advertiser-name", name || id || "Not set"));
    if (name && id) {
      stack.appendChild(advertiserLine(
        "create-md__advertiser-id", "ID: " + id));
    }
    cell.appendChild(stack);
    return cell;
  }

  function advertiserLine(className, value) {
    var line = document.createElement("span");
    line.className = className;
    line.textContent = value;
    line.setAttribute("data-tooltip", value);
    line.setAttribute("data-tooltip-truncate", "auto");
    return line;
  }

  function formatRate(value, currency) {
    var amount = Number(value);
    if (!Number.isFinite(amount)) return "Not set";
    var symbols = { USD: "$", CAD: "CA$", EUR: "€", GBP: "£" };
    /* Sponsorship and unit money runs into the tens of thousands, which
     * is unreadable as a run of digits, so amounts group by thousands. */
    return (symbols[currency] || "") + amount.toLocaleString("en-US", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    });
  }

  function formatUpdatedDate(value) {
    var timestamp = Date.parse(value);
    if (!Number.isFinite(timestamp)) return "Not set";
    return new Intl.DateTimeFormat(undefined, {
      month: "2-digit", day: "2-digit", year: "numeric"
    }).format(new Date(timestamp));
  }

  function renderRows(type, rows) {
    var tbody = root.querySelector('[data-v2-tbody="' + type + '"]');
    var byId = type === "premiums" ? linesById() : null;
    var checkable = isV21();
    /* 2.1 keeps the selected record in state while the Details panel is
     * closed so reopening returns to it, but the highlight is the panel's
     * pointer: with no panel on screen there is nothing for it to point
     * at, so it comes off until the panel comes back. 2.0 edits in an
     * always-visible rail, where the highlight always has a referent. */
    var panelShowing = !isV21()
      || itemPanelOpen(type === "lines" ? "line" : "premium");
    detachSelectionBar(type);
    tbody.replaceChildren();
    if (checkable) syncSelectionRowPlacement(type);
    rows.forEach(function (row) {
      var tr = document.createElement("tr");
      tr.tabIndex = 0;
      tr.setAttribute("data-v2-row-id", row.id);
      tr.setAttribute("data-v2-row-type", type);
      var selected = state.selected[type] === row.id && panelShowing;
      tr.classList.toggle("is-selected", selected);
      tr.setAttribute("aria-selected", selected ? "true" : "false");
      if (highlight.type === type && highlight.id === row.id) tr.classList.add("is-highlighted");

      /* The cell is always written, even on versions with no bulk
       * selection, because its <th> is always in the <thead>: skipping the
       * <td> would shift every value one column left of its own header.
       * Only the control inside it is version-gated, and CSS drops the
       * whole column on anything below 2.1. */
      var checkboxCell = document.createElement("td");
      checkboxCell.className = "create-md__td-checkbox";
      if (checkable) {
        var checked = state.checked[type].indexOf(row.id) >= 0;
        tr.classList.toggle("is-checked", checked);
        var rowLabel = type === "lines"
          ? "Select line item for "
            + (row.advertiserName || row.advertiserId || "this row")
          : "Select premium " + (row.displayName || row.category || "in this row");
        var box = typeof window.buildAdsCheckbox === "function"
          ? window.buildAdsCheckbox({ label: rowLabel })
          : document.createElement("input");
        var input = box.matches && box.matches("label") ? box.querySelector("input") : box;
        if (input) {
          input.checked = checked;
          input.addEventListener("click", function (event) { event.stopPropagation(); });
          input.addEventListener("change", function () {
            toggleRowChecked(type, row.id, input.checked);
          });
        }
        checkboxCell.appendChild(box);
      }
      tr.appendChild(checkboxCell);

      // 2.1 merges the advertiser pair into one two-line cell (644:67917).
      // The ID cell keeps its slot but renders empty, because the column
      // widths below it are positional and CSS is what drops the column.
      // Earlier versions keep two separate Advertiser cells, name first.
      var merged = type === "lines" && isV21();
      var lead = merged
        ? [row.advertiserId, row.advertiserName]
        : [row.advertiserName, row.advertiserId];
      // Premium columns follow Figma 697:3617: the premium name leads,
      // then the offerings it prices, its category, the adjustment and
      // how the adjustment is applied. Value carries no currency symbol
      // here because Percent Adjustment premiums are not money.
      //
      // 697:3617 has no Advertiser column: on this card a premium is
      // priced by offering and condition, so repeating the advertiser on
      // every row buys nothing. The cell still renders and CSS drops it
      // on 2.1, both to keep the positional column widths counting from
      // the same places and to leave 2.0's six-column table alone. The
      // scope itself is untouched on the record and still exports.
      var values = type === "lines"
        ? lead.concat([row.baseOffering, row.rateType,
           formatRate(row.baseRate, row.currency), row.currency,
           lineConditionLabel(row.condition1),
           formatUpdatedDate(row.updatedAt || file.updatedAt)])
        : [row.displayName || row.category || "Premium adjustment",
           premiumBaseOffering(row, byId), row.category,
           Number(row.value).toFixed(2), row.calculationMethod,
           premiumAdvertiserLabel(row)];
      var nameIndex = merged ? 1 : 0;
      // Base offering (2) runs long enough to truncate ("Disney Streaming
      // Live Events") and a flat sponsorship fee (4) runs wide, so both
      // carry the truncation tooltip the advertiser cell has. The Line
      // condition (6) holds the longest values on the row. Every premium
      // column except the two-decimal Value can outrun its width.
      var conditionIndex = 6;
      var tooltipIndexes = type === "lines"
        ? [nameIndex, 2, 4, conditionIndex] : [0, 1, 2, 4, 5];
      var emphasisIndex = type === "lines" ? nameIndex : 0;
      values.forEach(function (value, index) {
        var cell;
        if (merged && index === 0) {
          // Dropped by CSS on 2.1. Left empty so the advertiser ID is not
          // duplicated in the accessibility tree or in row text.
          cell = document.createElement("td");
          cell.className = "create-md__td-advertiser-id";
        } else if (merged && index === nameIndex) {
          cell = buildAdvertiserCell(row);
        } else if (type === "lines" && index === conditionIndex) {
          cell = buildLineConditionCell(value);
        } else {
          var cellClass = index === emphasisIndex ? "create-md__td-advertiser" : "";
          if (type === "premiums" && index === 5) {
            cellClass = "create-md__td-premium-advertiser";
          }
          cell = makeCell(value, tooltipIndexes.indexOf(index) >= 0, cellClass);
        }
        // Announce selection on the row's first rendered cell, which on
        // 2.1 is the advertiser cell rather than the dropped ID cell.
        if (index === nameIndex && selected) {
          var selectedText = document.createElement("span");
          selectedText.className = "sr-only";
          selectedText.textContent = "Selected. ";
          cell.insertBefore(selectedText, cell.firstChild);
        }
        tr.appendChild(cell);
      });
      tbody.appendChild(tr);
    });
    if (type === "lines") syncLineConditionFocus(tbody);
  }

  // ---- v2.1 bulk selection + action bar --------------------------------
  // Figma 644:67875 (LINE) and 697:3618 (PREM) are the same component in
  // the same place: an indigo row inside the table, between the header and
  // the first data row. Both tables therefore drive one implementation,
  // keyed by row type, rather than each growing its own copy.

  var ROW_NOUN = {
    lines: { one: "line item", many: "line items" },
    premiums: { one: "premium", many: "premiums" }
  };

  function rowNoun(type, count) {
    var noun = ROW_NOUN[type] || ROW_NOUN.lines;
    return count === 1 ? noun.one : noun.many;
  }

  function rowsFor(type) {
    if (!file) return [];
    return type === "lines" ? file.lines : file.premiums;
  }

  function rowLabelFor(type, row) {
    if (!row) return "";
    return type === "lines"
      ? text(row.advertiserName) || text(row.advertiserId)
      : text(row.displayName) || text(row.category);
  }

  function pruneChecked(type) {
    var ids = rowsFor(type).map(function (row) { return row.id; });
    state.checked[type] = state.checked[type].filter(function (id) {
      return ids.indexOf(id) >= 0;
    });
  }

  function toggleRowChecked(type, id, isChecked) {
    var list = state.checked[type];
    var index = list.indexOf(id);
    if (isChecked && index < 0) list.push(id);
    else if (!isChecked && index >= 0) list.splice(index, 1);
    syncHeaderCheckbox(type);
    syncSelectionBar(type);
    root.querySelectorAll('[data-v2-row-type="' + type + '"][data-v2-row-id="' + id + '"]')
      .forEach(function (tr) { tr.classList.toggle("is-checked", isChecked); });
  }

  function visibleIdsOnPage(type) {
    var filtered = filteredRows(type);
    var view = state[type];
    var start = (view.page - 1) * view.pageSize;
    return filtered.slice(start, start + view.pageSize).map(function (row) { return row.id; });
  }

  function syncHeaderCheckbox(type) {
    if (!root || !isV21()) return;
    var host = root.querySelector('[data-v2-checkbox-header="' + type + '"]');
    if (!host) return;
    if (!host.firstChild && typeof window.buildAdsCheckbox === "function") {
      var box = window.buildAdsCheckbox({
        label: "Select all " + rowNoun(type, 2) + " on this page"
      });
      var toggle = box.querySelector("input");
      toggle.addEventListener("change", function () {
        var visible = visibleIdsOnPage(type);
        if (toggle.checked) {
          visible.forEach(function (id) {
            if (state.checked[type].indexOf(id) < 0) state.checked[type].push(id);
          });
        } else {
          state.checked[type] = state.checked[type].filter(function (id) {
            return visible.indexOf(id) < 0;
          });
        }
        renderType(type);
      });
      host.appendChild(box);
    }
    var input = host.querySelector("input");
    if (!input) return;
    var visible = visibleIdsOnPage(type);
    var checkedVisible = visible.filter(function (id) { return state.checked[type].indexOf(id) >= 0; });
    input.checked = visible.length > 0 && checkedVisible.length === visible.length;
    input.indeterminate = checkedVisible.length > 0 && checkedVisible.length < visible.length;
  }

  /* Premiums carry Export as well, because a premium book is the part of
   * a rate card most often circulated on its own for finance review.
   * Duplicate is single-only for the same reason Edit is: the copy opens
   * for review, and only one record can hold the panel. */
  function selectionActionSpecs(type) {
    if (type === "premiums") {
      return [
        { key: "export", label: "Export", icon: window.ADS_ICON_DOWNLOAD || "",
          run: function (ids) { exportPremiums(ids); } },
        { key: "edit", label: "Edit", icon: window.ADS_ICON_EDIT || "",
          singleOnly: true,
          disabledTitle: "Select exactly one premium to edit.",
          run: function (ids) {
            var row = root.querySelector('[data-v2-row-id="' + ids[0] + '"][data-v2-row-type="premiums"]');
            requestSelectRow("premiums", ids[0], row);
          } },
        { key: "delete", label: "Delete", icon: window.ADS_ICON_TRASH || "",
          run: function (ids) { openDeleteRowsModal("premiums", ids); } },
        { key: "duplicate", label: "Duplicate", icon: window.ADS_ICON_COPY || "",
          singleOnly: true,
          disabledTitle: "Select exactly one premium to duplicate.",
          run: function (ids) { duplicateRows("premiums", ids); } }
      ];
    }
    return [
      { key: "edit", label: "Edit", icon: window.ADS_ICON_EDIT || "",
        singleOnly: true,
        disabledTitle: "Select exactly one line item to edit.",
        run: function (ids) {
          var row = root.querySelector('[data-v2-row-id="' + ids[0] + '"][data-v2-row-type="lines"]');
          requestSelectRow("lines", ids[0], row);
        } },
      { key: "copy", label: "Copy", icon: window.ADS_ICON_COPY || "",
        run: function (ids) { duplicateRows("lines", ids); } },
      { key: "delete", label: "Delete", icon: window.ADS_ICON_TRASH || "",
        run: function (ids) { openDeleteRowsModal("lines", ids); } }
    ];
  }

  function selectionBar(type) {
    var host = root.querySelector('[data-v2-selection-bar="' + type + '"]');
    if (!host) return null;
    if (host.firstChild) return host.firstChild;
    if (typeof window.createSelectionActionBar !== "function") return null;
    var bar = window.createSelectionActionBar({
      specs: selectionActionSpecs(type),
      ariaLabel: "Selected " + rowNoun(type, 2) + " actions",
      groupAriaLabel: "Actions for the selected " + rowNoun(type, 2),
      onAction: function (spec) {
        var ids = state.checked[type].slice();
        if (!ids.length) return;
        if (spec.singleOnly && ids.length !== 1) return;
        spec.run(ids);
      }
    });
    host.appendChild(bar);
    return bar;
  }

  // Keeping the host element and moving it into a full-width row (instead
  // of rebuilding it) preserves the shared list-page component and its
  // state, and the row carries no data-v2-row-id so the row-click handler
  // ignores it.
  var selectionHomes = {};

  function selectionHost(type) {
    var host = root && root.querySelector('[data-v2-selection-bar="' + type + '"]');
    if (host && !selectionHomes[type] && host.parentNode) {
      selectionHomes[type] = { parent: host.parentNode, next: host.nextSibling };
    }
    return host;
  }

  function detachSelectionBar(type) {
    var host = selectionHost(type);
    var home = selectionHomes[type];
    if (!host || !home) return;
    if (host.parentNode !== home.parent) home.parent.insertBefore(host, home.next);
  }

  // Figma 697:3617 puts the bar above the column labels, not between them
  // and the data, so it reads as a banner over the whole table rather than
  // as the first result. That means the head, ahead of the header row.
  function mountSelectionRow(type, table) {
    var host = selectionHost(type);
    if (!host) return;
    if (!state.checked[type].length) return;
    var head = table.querySelector("thead");
    var headerRow = head && head.querySelector("tr");
    if (!head) return;
    var tr = document.createElement("tr");
    tr.className = "create-md__selection-row";
    var td = document.createElement("td");
    td.className = "create-md__selection-cell";
    td.colSpan = headerRow ? headerRow.children.length : 1;
    td.appendChild(host);
    tr.appendChild(td);
    head.insertBefore(tr, headerRow);
  }

  function syncSelectionRowPlacement(type) {
    var tbody = root.querySelector('[data-v2-tbody="' + type + '"]');
    var table = tbody && tbody.closest("table");
    if (!table) return;
    var existing = table.querySelector(".create-md__selection-row");
    var host = selectionHost(type);
    if (state.checked[type].length) {
      /* The row lives in <thead>, which a table rebuild leaves alone, but
       * the bar itself is moved back to its home element first so the
       * rebuild cannot destroy it. That can leave an empty shell behind,
       * so a row without its bar in it is discarded rather than reused. */
      if (existing && host && !existing.contains(host)) {
        existing.remove();
        existing = null;
      }
      if (!existing) mountSelectionRow(type, table);
    } else if (existing) {
      detachSelectionBar(type);
      existing.remove();
    }
  }

  function syncSelectionBar(type) {
    if (!root || !isV21()) return;
    pruneChecked(type);
    var bar = selectionBar(type);
    var host = selectionHost(type);
    var count = state.checked[type].length;
    if (typeof window.applySelectionActionBarState === "function") {
      window.applySelectionActionBarState(bar, count, { specs: selectionActionSpecs(type) });
    }
    if (host) host.hidden = count === 0;
    syncSelectionRowPlacement(type);
  }

  /* A duplicate is a new record, so it takes a new id and keeps every
   * other field. Premium copies are renamed rather than left identical:
   * two rows reading "Holiday Demand Premium" tell a reader nothing about
   * which one they are about to edit. */
  function duplicateRows(type, ids) {
    if (!file) return;
    var rows = rowsFor(type);
    var created = [];
    ids.forEach(function (id) {
      var source = rows.find(function (row) { return row.id === id; });
      if (!source) return;
      var copy = Object.assign({}, source);
      copy.id = (type === "lines" ? "line-" : "premium-")
        + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 6);
      if (type === "premiums") copy.displayName = duplicateName(source.displayName, rows);
      copy.updatedAt = new Date().toISOString();
      rows.push(copy);
      created.push(copy.id);
    });
    if (!created.length) return;
    state.checked[type] = [];
    highlight = { type: type, id: created[created.length - 1] };
    renderType(type);
    updateSaveState();
    showOperationToast(
      created.length + " " + rowNoun(type, created.length)
        + (type === "lines" ? " copied" : " duplicated")
    );
    /* A duplicate is a draft the user still has to price, so it opens for
     * review the way the list page's Duplicate opens the new rate card. */
    if (type === "premiums" && created.length === 1) {
      requestSelectRow("premiums", created[0], null);
    }
    window.setTimeout(function () {
      highlight = { type: "", id: "" };
      renderType(type);
    }, 1700);
  }

  /* "Name (copy)", then "(copy 2)" and up, so duplicating twice does not
   * produce two rows with the same name. */
  function duplicateName(name, rows) {
    var base = text(name);
    if (!base) return "";
    var taken = {};
    rows.forEach(function (row) { taken[text(row.displayName)] = true; });
    var candidate = base + " (copy)";
    for (var n = 2; taken[candidate] && n < 100; n += 1) {
      candidate = base + " (copy " + n + ")";
    }
    return candidate;
  }

  /* Exporting the checked premiums writes the same RCM CSV the list page
   * writes, restricted to the selected PREM rows and the CARD row they
   * belong to, so the file opens in the same template a user would
   * re-import. The headers, escaping and download all come from app.js
   * rather than being reimplemented here. */
  function exportPremiums(ids) {
    var headers = window.RCM_CSV_HEADERS;
    var value = window.rcmExportValue;
    var download = window.rcmDownloadCsv;
    if (!file || !headers || typeof value !== "function" || typeof download !== "function") {
      showErrorToast("Unable to export premiums", "Try again.");
      return;
    }
    var selected = file.premiums.filter(function (premium) {
      return ids.indexOf(premium.id) >= 0;
    });
    if (!selected.length) return;
    var card = file.card;
    function line(values) {
      return headers.map(function (header) { return value(values[header]); }).join(",");
    }
    var rows = [line({
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
    })].concat(selected.map(function (premium) {
      return line({
        ROW_TYPE: "PREM",
        ID: premium.id,
        RATE_CARD_ID: card.id,
        ADVERTISER_ID: premium.advertiserId,
        ADVERTISER_DISPLAY_NAME: premiumAdvertiserLabel(premium),
        BASE_OFFERING: premiumBaseOffering(premium, linesById()),
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
    }));
    download(
      (card.id || "rate-card") + "-premiums.csv",
      headers.map(value).join(",") + "\r\n" + rows.join("\r\n") + "\r\n"
    );
    showOperationToast(
      selected.length + " " + rowNoun("premiums", selected.length) + " exported"
    );
  }

  // Bulk delete (v2.1 action bar) reuses the exact same confirmation
  // modal as the single-record "Remove" flow (data-v2-remove-modal) - see
  // openRemoveLineModal/confirmRemoveLine below, which branch on this
  // state to know whether a bulk delete is in flight.
  var deleteRowsModalState = { type: "lines", ids: [] };

  // Premiums share that dialog too, so every opener below writes the full
  // set of strings rather than only the ones it changes: the modal is a
  // single reused element, and text left over from the previous opener
  // would otherwise describe the wrong record.
  var removeModalKind = "line";

  function setRemoveModalCopy(modal, copy) {
    var title = modal.querySelector("#v2-remove-title");
    var bodyText = modal.querySelector(".modal__body-text");
    var summary = modal.querySelector(".modal__summary");
    var label = modal.querySelector("[data-v2-remove-label]");
    var target = modal.querySelector("[data-v2-remove-target]");
    var confirm = modal.querySelector('[data-v2-action="confirm-remove-line"]');
    if (title) title.textContent = copy.title;
    if (bodyText) bodyText.textContent = copy.body;
    if (summary) summary.hidden = !copy.target;
    if (label) label.textContent = copy.label || "";
    if (target) target.textContent = copy.target || "";
    if (confirm) confirm.textContent = copy.confirm;
  }

  function openDeleteRowsModal(type, ids) {
    var modal = root.querySelector("[data-v2-remove-modal]");
    if (!modal) return;
    deleteRowsModalState = { type: type, ids: ids.slice() };
    removeModalKind = type === "premiums" ? "premium" : "line";
    removeReturnFocus = document.activeElement;
    var plural = ids.length !== 1;
    var noun = rowNoun(type, ids.length);
    var row = plural ? null : rowsFor(type).find(function (item) {
      return item.id === ids[0];
    });
    setRemoveModalCopy(modal, {
      title: plural
        ? "Remove these " + ids.length + " " + noun + "?"
        : "Remove this " + noun + "?",
      body: (plural ? "These " : "This ") + noun
        + " will be removed from the rate card. This action cannot be undone.",
      label: type === "premiums" ? "Premium" : "Advertiser",
      target: plural ? "" : rowLabelFor(type, row) || ("Selected " + noun),
      confirm: "Remove " + noun
    });
    armRemoveModal(modal);
  }

  /* The three openers differ only in their copy; everything from here down
   * (busy flag, inert background, enabled confirm, focus on Cancel) is the
   * same dialog behaviour whichever record type is being removed. */
  function armRemoveModal(modal) {
    removeConfirmationProcessing = false;
    modal.removeAttribute("aria-busy");
    modal.hidden = false;
    setRemoveModalBackgroundInert(modal, true);
    var confirmBtn = modal.querySelector('[data-v2-action="confirm-remove-line"]');
    if (confirmBtn) {
      confirmBtn.disabled = false;
      confirmBtn.removeAttribute("aria-disabled");
    }
    focusRemoveModalCancel(modal);
  }

  /* Every confirmation in the app opens on its Cancel button, so arriving
   * on one and pressing Enter never destroys anything. The background is
   * already inert here, so this only decides where the caret lands. */
  function focusRemoveModalCancel(modal) {
    var cancel = modal.querySelector(
      '.modal__footer [data-v2-action="cancel-remove-line"]');
    if (cancel && typeof cancel.focus === "function") cancel.focus();
    if (document.body) document.body.classList.add("ads-modal-open");
  }

  function performDeleteRows(type, ids) {
    if (!file) return;
    if (type === "premiums") return performDeletePremiums(ids);
    var idSet = ids.reduce(function (acc, id) { acc[id] = true; return acc; }, {});
    var activeDeleted = idSet[state.selected.lines];
    file.lines = file.lines.filter(function (line) { return !idSet[line.id]; });
    file.premiums = file.premiums.reduce(function (remaining, premium) {
      var attached = premium.lineItemIds || [];
      if (!attached.length) {
        remaining.push(premium);
        return remaining;
      }
      var next = Object.assign({}, premium);
      next.lineItemIds = attached.filter(function (lineId) { return !idSet[lineId]; });
      if (next.lineItemIds.length) remaining.push(next);
      return remaining;
    }, []);
    state.checked.lines = state.checked.lines.filter(function (id) { return !idSet[id]; });
    if (activeDeleted) {
      state.selected.lines = "";
      clearItemForm("line");
      closeV2Panel();
    }
    renderType("lines");
    renderType("premiums");
    updateSaveState();
    showOperationToast(ids.length + " " + rowNoun("lines", ids.length) + " deleted");
  }

  /* Deleting premiums cannot orphan anything the way deleting lines can,
   * so this only has to drop the rows, release the panel if it was
   * showing one of them, and let renderType re-derive the count and the
   * page (paginationState clamps a page that no longer exists). */
  function performDeletePremiums(ids) {
    var idSet = ids.reduce(function (acc, id) { acc[id] = true; return acc; }, {});
    var activeDeleted = idSet[state.selected.premiums];
    file.premiums = file.premiums.filter(function (premium) {
      return !idSet[premium.id];
    });
    state.checked.premiums = state.checked.premiums.filter(function (id) {
      return !idSet[id];
    });
    if (activeDeleted) {
      state.selected.premiums = "";
      clearItemForm("premium");
      closeV2Panel();
    }
    renderType("premiums");
    updateSaveState();
    showOperationToast(ids.length + " " + rowNoun("premiums", ids.length) + " deleted");
  }

  // ---- v2.1 Line Details slide-over panel chrome ------------------------
  // v2.0 keeps its always-open sticky rail with CARD/LINE/PREM accordions.
  // v2.1 (this task) shows read-only CARD data in the header instead (see
  // updateV2Meta) and turns the rail into a panel that only appears while
  // a line or premium is actively being edited.

  function updateV2PanelChrome() {
    if (!isV21() || !root) return;
    var openSection = "";
    root.querySelectorAll("[data-v2-accordion]").forEach(function (accordion) {
      if (!accordion.classList.contains("is-open")) return;
      var section = accordion.getAttribute("data-v2-accordion");
      if (section === "line" || section === "premium") openSection = section;
    });
    root.classList.toggle("is-panel-open", Boolean(openSection));
    var header = document.querySelector("[data-v2-panel-header]");
    var title = document.querySelector("[data-v2-panel-title]");
    var titleText = openSection === "premium" ? "Premium Details" : "Line Details";
    if (header) header.hidden = !openSection;
    if (title) title.textContent = titleText;
    var detail = root.querySelector(".create-md__detail");
    if (detail) detail.setAttribute("aria-label", openSection ? titleText : "Rate card editor");
    var closeBtn = document.querySelector('[data-v2-action="close-panel"]');
    if (closeBtn) closeBtn.setAttribute("aria-label", "Close " + titleText);
  }

  function closeV2Panel() {
    collapseAccordion("line");
    collapseAccordion("premium");
  }

  function removeRow(type, id, trigger) {
    var rows = type === "lines" ? file.lines : file.premiums;
    var index = rows.findIndex(function (row) { return row.id === id; });
    if (index < 0) return;
    rows.splice(index, 1);
    if (type === "lines") {
      file.premiums = file.premiums.reduce(function (remainingPremiums, premium) {
        var attachedIds = premium.lineItemIds || [];
        if (!attachedIds.length) {
          remainingPremiums.push(premium);
          return remainingPremiums;
        }
        var next = Object.assign({}, premium);
        next.lineItemIds = attachedIds.filter(function (lineId) {
          return lineId !== id;
        });
        if (next.lineItemIds.length) remainingPremiums.push(next);
        return remainingPremiums;
      }, []);
      if (state.selected.premiums && !file.premiums.some(function (premium) {
        return premium.id === state.selected.premiums;
      })) {
        state.selected.premiums = "";
        clearItemForm("premium");
      }
    }
    if (state.selected[type] === id) {
      state.selected[type] = "";
      clearItemForm(type === "lines" ? "line" : "premium");
    }
    highlight = { type: "", id: "" };
    renderType(type);
    if (type === "lines") renderType("premiums");
    updateSaveState();
    showOperationToast(type === "lines"
      ? "Line item removed"
      : "Premium adjustment removed");
    var fallback = root.querySelector('[data-v2-action="' + (type === "lines" ? "add-line" : "add-premium") + '"]');
    if (fallback) fallback.focus();
    else if (trigger) trigger.focus();
  }

  function setRemoveModalBackgroundInert(modal, shouldInert) {
    if (!modal) return;
    if (!shouldInert) {
      removeModalInertElements.forEach(function (entry) {
        entry.element.inert = entry.wasInert;
      });
      removeModalInertElements = [];
      return;
    }
    removeModalInertElements = [];
    var branch = modal;
    while (branch && branch.parentElement) {
      Array.prototype.forEach.call(branch.parentElement.children, function (sibling) {
        if (sibling === branch) return;
        removeModalInertElements.push({
          element: sibling,
          wasInert: sibling.inert
        });
        sibling.inert = true;
      });
      branch = branch.parentElement;
      if (branch === document.body) break;
    }
  }

  /* Uses the shared ADS confirmation dialog app.js owns, so leaving the
   * details page with unsaved work is asked in the same shell as every
   * other confirmation. If that dialog is unavailable (this file loaded
   * without app.js), the browser's confirm still asks the question
   * rather than the page discarding the work silently. */
  function confirmLeaveWithUnsavedWork(onLeave) {
    var options = {
      title: "Leave without saving?",
      body: "This rate card has changes that have not been saved. "
        + "Leaving now discards them.",
      cancelLabel: "Keep editing",
      confirmLabel: "Leave without saving"
    };
    if (typeof window.adsConfirm === "function") {
      window.adsConfirm(options, onLeave);
      return;
    }
    if (window.confirm(options.body)) onLeave();
  }

  function closeRemoveLineModal(force) {
    var modal = root.querySelector("[data-v2-remove-modal]");
    if (removeConfirmationProcessing && !force) return;
    if (modal) {
      modal.hidden = true;
      modal.removeAttribute("aria-busy");
      setRemoveModalBackgroundInert(modal, false);
      if (document.body) document.body.classList.remove("ads-modal-open");
    }
    if (removeReturnFocus && document.contains(removeReturnFocus)) removeReturnFocus.focus();
    removeReturnFocus = null;
    deleteRowsModalState = { type: "lines", ids: [] };
    removeModalKind = "line";
  }

  function openRemoveLineModal(trigger) {
    var id = state.selected.lines;
    var row = file.lines.find(function (line) { return line.id === id; });
    if (!row) return;
    var modal = root.querySelector("[data-v2-remove-modal]");
    if (!modal) return;
    removeModalKind = "line";
    removeReturnFocus = trigger;
    setRemoveModalCopy(modal, {
      title: "Remove this line item?",
      body: "This line item will be removed from the rate card. This action cannot be undone.",
      label: "Advertiser",
      target: row.advertiserName || row.advertiserId || "Selected line item",
      confirm: "Remove line item"
    });
    armRemoveModal(modal);
  }

  /* Premium removal is destructive and irreversible in exactly the way line
   * removal is, so it asks in the same dialog rather than deleting straight
   * from the panel footer. */
  function openRemovePremiumModal(trigger) {
    var id = state.selected.premiums;
    var row = file.premiums.find(function (premium) { return premium.id === id; });
    if (!row) return;
    var modal = root.querySelector("[data-v2-remove-modal]");
    if (!modal) return;
    removeModalKind = "premium";
    removeReturnFocus = trigger;
    setRemoveModalCopy(modal, {
      title: "Remove this premium adjustment?",
      body: "This premium adjustment will be removed from the rate card. This action cannot be undone.",
      label: "Premium",
      target: row.displayName || row.category || "Selected premium adjustment",
      confirm: "Remove premium adjustment"
    });
    armRemoveModal(modal);
  }

  function confirmRemoveLine() {
    if (removeConfirmationProcessing) return;
    removeConfirmationProcessing = true;
    var kind = removeModalKind;
    var bulkType = deleteRowsModalState.type;
    var bulkIds = deleteRowsModalState.ids;
    var id = kind === "premium" ? state.selected.premiums : state.selected.lines;
    var modal = root.querySelector("[data-v2-remove-modal]");
    var confirm = modal && modal.querySelector('[data-v2-action="confirm-remove-line"]');
    if (modal) modal.setAttribute("aria-busy", "true");
    if (confirm) {
      confirm.disabled = true;
      confirm.setAttribute("aria-disabled", "true");
    }
    deleteRowsModalState = { type: "lines", ids: [] };
    closeRemoveLineModal(true);
    if (bulkIds.length) {
      performDeleteRows(bulkType, bulkIds);
      return;
    }
    if (kind === "premium") {
      if (id) removeRow("premiums", id);
      openAccordion("card");
      return;
    }
    if (id) removeRow("lines", id);
    openAccordion("card");
  }

  // One shared sort icon preserves identical geometry in every state. CSS
  // changes only the active direction color, so the footprint never shifts.
  var TABLE_SORT_SVG =
    '<svg viewBox="0 0 9 8" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">' +
    '<path class="th__sort-direction th__sort-direction--descending" fill-rule="evenodd" clip-rule="evenodd" d="M2 0C2.27614 0 2.5 0.223858 2.5 0.5L2.5 6.29289L3.14645 5.64645C3.34171 5.45118 3.65829 5.45118 3.85355 5.64645C4.04882 5.84171 4.04882 6.15829 3.85355 6.35355L2.35355 7.85355C2.25979 7.94732 2.13261 8 2 8C1.86739 8 1.74021 7.94732 1.64645 7.85355L0.146447 6.35355C-0.0488155 6.15829 -0.0488155 5.84171 0.146447 5.64645C0.341709 5.45118 0.658291 5.45118 0.853553 5.64645L1.5 6.29289L1.5 0.5C1.5 0.223858 1.72386 0 2 0Z" fill="currentColor"/>' +
    '<path class="th__sort-direction th__sort-direction--ascending" fill-rule="evenodd" clip-rule="evenodd" d="M7 0C7.13261 0 7.25979 0.0526787 7.35355 0.146447L8.85355 1.64645C9.04882 1.84171 9.04882 2.15829 8.85355 2.35355C8.65829 2.54882 8.34171 2.54882 8.14645 2.35355L7.5 1.70711V7.5C7.5 7.77614 7.27614 8 7 8C6.72386 8 6.5 7.77614 6.5 7.5V1.70711L5.85355 2.35355C5.65829 2.54882 5.34171 2.54882 5.14645 2.35355C4.95118 2.15829 4.95118 1.84171 5.14645 1.64645L6.64645 0.146447C6.74021 0.0526787 6.86739 0 7 0Z" fill="currentColor"/>' +
    '</svg>';

  function renderSortableHeader(button, sortState, active) {
    button.classList.remove("th--sort-asc", "th--sort-desc");
    if (active) {
      button.classList.add(sortState === "ascending" ? "th--sort-asc" : "th--sort-desc");
    }
    var icon = button.querySelector(".th__sort");
    if (!icon) {
      icon = document.createElement("span");
      icon.className = "th__sort";
      icon.setAttribute("aria-hidden", "true");
      button.appendChild(icon);
    }
    if (!icon.querySelector("svg")) icon.innerHTML = TABLE_SORT_SVG;
    icon.setAttribute("data-sort-state", sortState);
    var label = button.getAttribute("data-v2-sort-label")
      || button.textContent.trim()
      || "column";
    var nextDirection = active && sortState === "ascending" ? "descending" : "ascending";
    button.setAttribute(
      "aria-label",
      "Sort by " + label + ". Current sort: " + sortState
        + ". Activate to sort " + nextDirection + "."
    );
  }

  function syncSortHeaders(type) {
    var view = state[type];
    root.querySelectorAll('[data-v2-sort-header^="' + type + ':"]').forEach(function (header) {
      var active = header.getAttribute("data-v2-sort-header") === type + ":" + view.sortKey;
      var button = header.querySelector("[data-v2-sort]");
      var sortState = active ? (view.direction === 1 ? "ascending" : "descending") : "none";
      header.setAttribute("aria-sort", sortState);
      if (!button) return;
      renderSortableHeader(button, sortState, active);
    });
  }

  // ADS Pagination chevrons, Figma 35:36 (CaretLeft 1599:5223 / CaretRight
  // 1599:5238). Each icon is a 6x11 glyph centered inside a 16x16 slot, so
  // the <g> offset (4.5/2.5 and 5.5/2.5) reproduces Figma's inset instead of
  // stretching the glyph to fill the box. fill="currentColor" ties the icon
  // to the button's own color token so rest/hover/disabled stay in sync.
  var CARET_LEFT_SVG = '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">'
    + '<g transform="translate(4.5 2.5)"><path fill="currentColor" d="M5.85414 10.1465C5.9006 10.193 5.93745 10.2481 5.96259 10.3088C5.98773 10.3695 6.00067 10.4346 6.00067 10.5003C6.00067 10.566 5.98773 10.631 5.96259 10.6917C5.93745 10.7524 5.9006 10.8076 5.85414 10.854C5.80769 10.9005 5.75254 10.9373 5.69184 10.9625C5.63115 10.9876 5.56609 11.0006 5.50039 11.0006C5.4347 11.0006 5.36964 10.9876 5.30895 10.9625C5.24825 10.9373 5.1931 10.9005 5.14664 10.854L0.146643 5.85403C0.100155 5.80759 0.0632757 5.75245 0.0381136 5.69175C0.0129514 5.63105 0 5.56599 0 5.50028C0 5.43457 0.0129514 5.36951 0.0381136 5.30881C0.0632757 5.24811 0.100155 5.19296 0.146643 5.14653L5.14664 0.146528C5.24046 0.0527077 5.36771 -2.61548e-09 5.50039 0C5.63308 2.61548e-09 5.76032 0.0527077 5.85414 0.146528C5.94796 0.240348 6.00067 0.367596 6.00067 0.500278C6.00067 0.63296 5.94796 0.760208 5.85414 0.854028L1.20727 5.50028L5.85414 10.1465Z"/></g>'
    + '</svg>';
  var CARET_RIGHT_SVG = '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">'
    + '<g transform="translate(5.5 2.5)"><path fill="currentColor" d="M5.85403 5.85403L0.854028 10.854C0.807573 10.9005 0.752423 10.9373 0.691726 10.9625C0.63103 10.9876 0.565975 11.0006 0.500278 11.0006C0.434581 11.0006 0.369526 10.9876 0.30883 10.9625C0.248133 10.9373 0.192983 10.9005 0.146528 10.854C0.100073 10.8076 0.0632225 10.7524 0.0380812 10.6917C0.0129398 10.631 0 10.566 0 10.5003C0 10.4346 0.0129398 10.3695 0.0380812 10.3088C0.0632225 10.2481 0.100073 10.193 0.146528 10.1465L4.7934 5.50028L0.146528 0.854028C0.0527074 0.760208 -9.88558e-10 0.63296 0 0.500278C9.88559e-10 0.367596 0.0527074 0.240348 0.146528 0.146528C0.240348 0.0527077 0.367596 9.88558e-10 0.500278 0C0.63296 -9.88558e-10 0.760208 0.0527077 0.854028 0.146528L5.85403 5.14653C5.90052 5.19296 5.9374 5.24811 5.96256 5.30881C5.98772 5.36951 6.00067 5.43457 6.00067 5.50028C6.00067 5.56599 5.98772 5.63105 5.96256 5.69175C5.9374 5.75245 5.90052 5.80759 5.85403 5.85403Z"/></g>'
    + '</svg>';

  function paginationState(type, total) {
    var view = state[type];
    var totalPages = Math.ceil(total / view.pageSize);
    view.page = totalPages === 0
      ? 1
      : Math.min(Math.max(1, view.page), totalPages);
    return {
      currentPage: view.page,
      totalItems: total,
      totalPages: totalPages
    };
  }

  function paginationItems(currentPage, totalPages) {
    if (totalPages <= 7) {
      return Array.from({ length: totalPages }, function (_, index) {
        return index + 1;
      });
    }
    if (currentPage <= 4) return [1, 2, 3, 4, 5, "ellipsis", totalPages];
    if (currentPage >= totalPages - 3) {
      return [
        1,
        "ellipsis",
        totalPages - 4,
        totalPages - 3,
        totalPages - 2,
        totalPages - 1,
        totalPages
      ];
    }
    return [
      1,
      "ellipsis",
      currentPage - 1,
      currentPage,
      currentPage + 1,
      "ellipsis",
      totalPages
    ];
  }

  /* Line Items and Premiums answer "should the footer be here at all?" with
   * the same rule the Rate Card Manager list uses, so a one-page tab never
   * carries a footer on one screen and not the other. app.js owns the rule;
   * the inline fallback only matters if v2.js is loaded on its own. */
  function showPaginationFooter(total, pageSize) {
    if (typeof window.shouldShowPaginationFooter === "function") {
      return window.shouldShowPaginationFooter(total, pageSize);
    }
    return Number(total) > Number(pageSize);
  }

  function syncPaginationFooter(type, total) {
    var region = root.querySelector('[data-v2-table-region="' + type + '"]');
    if (!region) return;
    var footer = region.querySelector(".create-md__table-footer");
    var visible = showPaginationFooter(total, state[type].pageSize);
    /* `hidden` keeps the page-size select, the page buttons, and the
     * "Go to page" picker out of the tab order and the accessibility tree
     * while the result set fits on one page. */
    if (footer) footer.hidden = !visible;
    /* 2.1 gives the tab panel a 565px floor and pins the footer to it so
     * pagination never moves as rows come and go. With no footer to pin
     * there is nothing left to hold that height open, so the panel sizes to
     * its rows instead of stranding them above a tall blank area. The empty
     * and no-results states keep the floor: they are centred inside it. */
    var panel = region.closest(".create-md__tab-panel");
    if (panel) {
      panel.toggleAttribute("data-v2-rows-fit", !region.hidden && !visible);
    }
  }

  function renderPagination(type, total) {
    var host = root.querySelector('[data-v2-pagination="' + type + '"]');
    var view = state[type];
    var model = paginationState(type, total);
    var pages = model.totalPages;
    var goTo = root.querySelector('[data-v2-go-page="' + type + '"]');
    var pageSizeControl = root.querySelector('[data-v2-page-size="' + type + '"]');
    if (!host) return;
    syncPaginationFooter(type, total);
    if (pageSizeControl) {
      pageSizeControl.value = String(view.pageSize);
      if (typeof window.syncAdsDropdown === "function") {
        window.syncAdsDropdown(pageSizeControl);
      }
    }
    host.replaceChildren();
    function add(label, page, disabled, current, kind) {
      var button = document.createElement("button");
      button.type = "button";
      button.disabled = disabled;
      button.className = "create-md__pagination-item create-md__pagination-item--" + kind;
      button.setAttribute("data-v2-page", type + ":" + page);
      if (kind === "previous" || kind === "next") {
        button.innerHTML = kind === "previous" ? CARET_LEFT_SVG : CARET_RIGHT_SVG;
        button.setAttribute("aria-label", kind === "previous" ? "Previous page" : "Next page");
      } else {
        button.textContent = label;
      }
      if (current) {
        button.setAttribute("aria-current", "page");
        button.setAttribute("aria-label", "Page " + label + ", current page");
      } else if (kind === "page") {
        button.setAttribute("aria-label", "Go to page " + label);
      }
      host.appendChild(button);
    }
    if (pages > 0) {
      add("", view.page - 1, view.page <= 1, false, "previous");
      paginationItems(view.page, pages).forEach(function (entry) {
        if (entry === "ellipsis") {
          var ellipsis = document.createElement("span");
          ellipsis.className = "create-md__pagination-ellipsis";
          ellipsis.textContent = "...";
          ellipsis.setAttribute("aria-hidden", "true");
          host.appendChild(ellipsis);
        } else {
          add(String(entry), entry, false, entry === view.page, "page");
        }
      });
      add("", view.page + 1, view.page >= pages, false, "next");
    }
    if (goTo) {
      goTo.replaceChildren();
      for (var pageNo = 1; pageNo <= pages; pageNo += 1) {
        var option = document.createElement("option");
        option.value = String(pageNo);
        option.textContent = String(pageNo);
        option.selected = pageNo === view.page;
        goTo.appendChild(option);
      }
      goTo.disabled = pages <= 1;
      if (typeof window.refreshAdsDropdown === "function") {
        window.refreshAdsDropdown(goTo);
      }
    }
  }

  function renderType(type) {
    if (!file || !root) return;
    var all = type === "lines" ? file.lines : file.premiums;
    var empty = root.querySelector('[data-v2-empty="' + type + '"]');
    var region = root.querySelector('[data-v2-table-region="' + type + '"]');
    var total = root.querySelector('[data-v2-total="' + type + '"]');
    var loading = root.querySelector('[data-v2-loading="' + type + '"]');
    var error = root.querySelector('[data-v2-load-error="' + type + '"]');
    var noResults = root.querySelector('[data-v2-no-results="' + type + '"]');
    syncSortHeaders(type);
    /* The tabs read as text alone. The count still reaches assistive tech
     * through the tab's accessible name, and sighted users read it from
     * the "of N items" footer, so nothing writes a visible number here. */
    var tab = root.querySelector('[data-v2-tab="' + type + '"]');
    if (tab) {
      var itemLabel = type === "lines"
        ? (all.length === 1 ? "1 line item" : all.length + " line items")
        : (all.length === 1 ? "1 premium" : all.length + " premiums");
      tab.setAttribute(
        "aria-label",
        (type === "lines" ? "Line items" : "Premiums") + ", " + itemLabel
      );
    }
    if (loading) loading.hidden = !state.loading;
    if (error) error.hidden = !state.error;
    if (state.loading || state.error) {
      if (empty) empty.hidden = true;
      if (noResults) noResults.hidden = true;
      if (region) region.hidden = true;
      return;
    }

    var filtered = filteredRows(type);
    var view = state[type];
    var hasRefinement = Boolean(
      text(view.query) || text(view.filter) || (type === "lines" && lineFilterCount())
    );
    if (empty) empty.hidden = all.length !== 0;
    if (noResults) noResults.hidden = !(all.length && !filtered.length && hasRefinement);
    if (region) region.hidden = !filtered.length;
    if (!filtered.length) {
      renderRows(type, []);
      renderPagination(type, 0);
      if (total) total.textContent = "0";
      if (isV21()) {
        syncHeaderCheckbox(type);
        syncSelectionBar(type);
      }
      return;
    }
    paginationState(type, filtered.length);
    var start = (view.page - 1) * view.pageSize;
    renderRows(type, filtered.slice(start, start + view.pageSize));
    if (total) total.textContent = String(filtered.length);
    renderPagination(type, filtered.length);
    if (isV21()) {
      syncHeaderCheckbox(type);
      syncSelectionBar(type);
    }
  }

  function renderAll() {
    switchTab(state.activeTab, false);
    renderType(state.activeTab === "lines" ? "premiums" : "lines");
    syncAttachFields();
  }

  function clearItemForm(type) {
    var form = root.querySelector('[data-v2-form="' + type + '"]');
    if (!form) return;
    form.reset();
    populateForm(form, {});
    if (type === "line") {
      form.elements.rateType.value = "CPM";
      form.elements.currency.value = "USD";
      if (typeof window.syncAdsDropdown === "function") {
        window.syncAdsDropdown(form.elements.rateType);
        window.syncAdsDropdown(form.elements.currency);
      }
      root.querySelector("[data-v2-line-section-title]").textContent = "Line details";
      root.querySelector("#v2-acc-line-trigger").removeAttribute("aria-label");
    } else {
      syncPremiumDatePickers({});
      root.querySelector("[data-v2-premium-section-title]").textContent = "Premium adjustments";
    }
    syncAttachFields();
    syncPanelFooter(type);
  }

  function beginAdd(type, trigger) {
    initiatedBy = trigger || document.activeElement;
    var tabType = type === "line" ? "lines" : "premiums";
    switchTab(tabType, false);
    state.selected[tabType] = "";
    clearItemForm(type);
    openAccordion(type, true);
    renderType(tabType);
    // The empty draft the panel opens with is the thing later keystrokes
    // are measured against, so opening the panel is not a change.
    captureDraftBaseline(type);
    updateSaveState();
  }

  function premiumFormHasDraft() {
    if (state.selected.premiums) return true;
    var form = root.querySelector('[data-v2-form="premium"]');
    if (!form) return false;
    return Array.prototype.some.call(form.elements, function (control) {
      if (!control.name || ["id", "attachToCard"].indexOf(control.name) >= 0) return false;
      return fieldValue(form, control.name) !== "";
    });
  }

  /* opts.focusPanel === false opens the panel without moving the caret
   * into it. Every user-initiated open still takes focus, because the
   * user asked for the panel; only the automatic open on page entry
   * declines, since nobody asked for it and stealing focus from the top
   * of a freshly loaded page would strand keyboard and screen reader
   * users mid-document. */
  function selectRow(type, id, trigger, opts) {
    var row = (type === "lines" ? file.lines : file.premiums).find(function (item) {
      return item.id === id;
    });
    if (!row) return;
    var focusPanel = !(opts && opts.focusPanel === false);
    initiatedBy = focusPanel ? (trigger || document.activeElement) : null;
    state.selected[type] = id;
    var formType = type === "lines" ? "line" : "premium";
    populateForm(root.querySelector('[data-v2-form="' + formType + '"]'), row);
    if (formType === "premium") syncPremiumDatePickers(row);
    syncAttachFields();
    syncPanelFooter(formType);
    openAccordion(formType, focusPanel);
    renderType(type);
    // Opening an existing row loads its saved values, which is the
    // baseline for that panel: viewing a row is never a change.
    captureDraftBaseline(formType);
    updateSaveState();
  }

  /* Are every required field for this record type filled with something
   * usable? fieldValue trims, so a field holding only spaces reads as
   * empty and does not count. This is the one place the answer is worked
   * out: the panel's primary button, the v2.1 line live-sync, and the
   * silent-commit guard all ask it, so none of them can drift from the
   * validateItemForm rules above. */
  function itemRequiredFieldsFilled(type) {
    var form = root && root.querySelector('[data-v2-form="' + type + '"]');
    if (!form) return false;
    var names = type === "line" ? LINE_REQUIRED_FIELDS : PREMIUM_REQUIRED_FIELDS;
    return names.every(function (name) {
      var value = fieldValue(form, name);
      if (value === "") return false;
      if (name === "baseRate" || name === "value") {
        return DECIMAL_PATTERN.test(value) && Number.isFinite(Number(value));
      }
      return true;
    });
  }

  function lineRequiredFieldsFilled() {
    return itemRequiredFieldsFilled("line");
  }

  /* ---- Panel footer: create mode vs edit mode -------------------------
   * The footer answers one question, "is there already a record behind
   * this panel?", and it answers it from state.selected, the row's stable
   * id, never from what the fields happen to hold. A half-filled form is
   * still a create. A row that v2.1's live sync has already committed is
   * an edit even though the user never pressed anything. Deriving the
   * label, the Remove action and the submit branch from the same fact is
   * what keeps all three agreeing at every moment. */
  /* The create labels repeat the toolbar buttons that open the panel word
   * for word, so the footer confirms the action the user started rather
   * than naming it a second way. */
  var PANEL_CREATE_LABEL = { line: "Add Line Item", premium: "Add Premium" };

  function panelIsEditing(type) {
    return Boolean(state.selected[type === "line" ? "lines" : "premiums"]);
  }

  /* Create is offered once the required fields are valid; Save changes
   * once the form differs from the values the panel last committed or
   * opened with, so an untouched record cannot be re-saved into a false
   * dirty state. */
  function panelPrimaryReady(type) {
    return panelIsEditing(type)
      ? itemFormSignature(type) !== draftBaseline[type]
      : itemRequiredFieldsFilled(type);
  }

  function syncPanelFooter(type) {
    if (!root) return;
    var editing = panelIsEditing(type);
    var remove = root.querySelector(
      "[data-v2-action='request-remove-" + type + "']"
    );
    // Removing a record only makes sense once one exists, so create mode
    // never offers it.
    if (remove) remove.hidden = !editing;
    var submit = root.querySelector(
      type === "line" ? "[data-v2-line-submit]" : "[data-v2-premium-submit]"
    );
    if (!submit) return;
    // A submit in flight owns the button's label and disabled state until
    // it settles; overwriting it here would wipe out the loading text.
    if (state.submitting[type]) return;
    submit.textContent = editing ? "Save changes" : PANEL_CREATE_LABEL[type];
    // Gating the button is a 2.1 Details panel behaviour. 2.0's accordion
    // wizard reaches its inline errors by submitting an incomplete form,
    // so a disabled button there would take away the only way to see them.
    if (!isV21()) return;
    var ready = panelPrimaryReady(type);
    submit.disabled = !ready;
    submit.setAttribute("aria-disabled", ready ? "false" : "true");
  }

  /* v2.1's Line Details panel keeps an existing row in step with the form
   * as you go (Figma 643:65724), on blur/change rather than per keystroke
   * so a field commits only once the user is done with it (the app's
   * "fields save on blur" convention).
   *
   * It deliberately stops short of creating rows. Live sync used to cover
   * new lines too, which made "Add Line Item" impossible to click: moving
   * the pointer to the button blurs the last field, live sync commits, and
   * the click lands on a button that has already relabelled itself to a
   * disabled "Save changes". Creating is the footer's job now, so the
   * button and Enter are the only ways a new row appears. */
  function commitLineLiveSync(opts) {
    if (!isV21() || !root) return;
    var accordion = root.querySelector('[data-v2-accordion="line"]');
    if (!accordion || !accordion.classList.contains("is-open")) return;
    // Saving the whole card is the one exception: a draft complete enough
    // to commit is swept up rather than silently dropped on the way out.
    if (!panelIsEditing("line") && !(opts && opts.includeNewDraft)) return;
    if (!lineRequiredFieldsFilled()) return;
    submitItem("line", { silent: true });
  }

  /* Every way of leaving an edited panel asks the same question, so they
   * all come through here. `outcome` names what is about to happen
   * ("Closing", "Switching rows"), which is the only part of the prompt
   * that differs, because it is the only part of the situation that
   * differs. An untouched panel proceeds with no prompt.
   *
   * 2.0's wizard has always discarded an open section silently and its
   * CARD-level leave guard already covers the work; the prompt belongs to
   * the 2.1 Details panel, where this is a per-record action. */
  function confirmDiscardDraft(type, outcome, proceed) {
    if (!isV21()
      || !itemPanelOpen(type)
      || itemFormSignature(type) === draftBaseline[type]) {
      proceed();
      return;
    }
    var noun = type === "line" ? "line item" : "premium";
    var options = {
      title: "Discard changes?",
      body: "This " + noun + " has changes that have not been added to the "
        + "rate card. " + outcome + " now discards them.",
      cancelLabel: "Keep editing",
      confirmLabel: "Discard changes"
    };
    if (typeof window.adsConfirm === "function") {
      window.adsConfirm(options, proceed);
      return;
    }
    if (window.confirm(options.body)) proceed();
  }

  /* Cancel and the panel's close X are the same action, so both come
   * through here: neither may drop work the user cannot get back without
   * asking first. An existing line commits on blur, so the live sync is
   * given its chance before anything is measured and Cancel does not
   * offer to discard what is already in the table. A new line is never
   * committed here, because discarding the draft is the whole point of
   * cancelling one. */
  function requestCancelItem(type) {
    if (type === "line") commitLineLiveSync();
    confirmDiscardDraft(type, "Closing", function () { cancelItem(type); });
  }

  function openPanelType() {
    if (itemPanelOpen("line")) return "line";
    if (itemPanelOpen("premium")) return "premium";
    return "";
  }

  /* Clicking a row replaces whatever the panel is holding, which is the
   * same loss of work as closing it, so it asks the same question first.
   * Every row entry point (click, Enter/Space, the row's edit action, the
   * action bar's Edit) goes through here rather than straight to
   * selectRow, so none of them can become the one that discards silently. */
  function requestSelectRow(type, id, trigger) {
    var formType = type === "lines" ? "line" : "premium";
    // Reselecting the row already on screen changes nothing, so it is not
    // a discard and must not prompt.
    if (state.selected[type] === id && itemPanelOpen(formType)) return;
    var open = openPanelType();
    if (!open) {
      selectRow(type, id, trigger);
      return;
    }
    if (open === "line") commitLineLiveSync();
    confirmDiscardDraft(open, "Switching rows", function () {
      selectRow(type, id, trigger);
    });
  }

  function cancelItem(type) {
    var tabType = type === "line" ? "lines" : "premiums";
    var returnRowId = state.selected[tabType];
    clearItemForm(type);
    openAccordion("card");
    renderType(tabType);
    // An untouched draft is discarded with the panel, so nothing is left
    // to save unless a committed row still differs from the baseline.
    captureDraftBaseline(type);
    updateSaveState();
    var returnTarget = initiatedBy && document.contains(initiatedBy)
      ? initiatedBy
      : returnRowId
        ? root.querySelector('[data-v2-row-type="' + tabType + '"][data-v2-row-id="' + returnRowId + '"]')
        : null;
    if (returnTarget) returnTarget.focus();
    initiatedBy = null;
  }

  function submitItem(type, opts) {
    var silent = Boolean(opts && opts.silent);
    if (state.submitting[type]) return;
    if (silent) {
      // Live-sync commits happen continuously as the user types; running
      // the full validateItemForm (which paints errors and can steal
      // focus to the first invalid field) on every one would be a bad
      // experience, so the caller already confirmed required fields are
      // filled via lineRequiredFieldsFilled(). A silent commit still
      // skips entirely if that somehow isn't true.
      if (type === "line" && !lineRequiredFieldsFilled()) return;
    } else if (!validateItemForm(type)) {
      return;
    }
    /* The flag exists only to stop this function re-entering itself while
     * it re-renders the table; the commit below is entirely in-memory, so
     * there is no request to show a loading state for. */
    state.submitting[type] = true;
    var tabType = type === "line" ? "lines" : "premiums";
    var form = root.querySelector('[data-v2-form="' + type + '"]');
    var raw = formObject(form);
    var selectedId = state.selected[tabType];
    var rows = type === "line" ? file.lines : file.premiums;
    var index = rows.findIndex(function (row) { return row.id === selectedId; });
    var isUpdate = index >= 0;
    var candidate = index >= 0 ? Object.assign({}, rows[index], raw) : raw;
    candidate.id = selectedId || type + "-" + Date.now().toString(36);
    candidate.attachToCard = file.card.id || file.card.name || "Current rate card";
    if (type === "line") candidate.updatedAt = new Date().toISOString();
    var valid = type === "line"
      ? validateLine(candidate, rows.length)
      : validatePremium(candidate, rows.length);
    if (index >= 0) rows[index] = valid;
    else rows.push(valid);
    state.selected[tabType] = valid.id;
    highlight = { type: tabType, id: valid.id };
    renderType(tabType);
    updateSaveState();
    populateForm(form, valid);
    if (type === "line") {
      root.querySelector("[data-v2-line-section-title]").textContent = "Edit Line Item";
    } else {
      syncPremiumDatePickers(valid);
      root.querySelector("[data-v2-premium-section-title]").textContent = "Edit Premium";
    }
    syncAttachFields();
    // The record this panel is editing now matches what is in the file, so
    // the panel has nothing of its own left to save even though the rate
    // card does. Re-baselining is what settles Save changes back to
    // disabled while leaving Save Rate Card enabled. It has to happen in
    // this tick, not in the frame below: clicking Cancel blurs the field
    // first, and v2.1's line live sync commits on that blur, so a baseline
    // still one frame behind would have Cancel offering to discard work
    // that is already in the table.
    draftBaseline[type] = itemFormSignature(type);
    if (!silent) {
      showOperationToast(type === "line"
        ? (isUpdate ? "Line item updated" : "Line item added")
        : (isUpdate ? "Premium adjustment updated" : "Premium adjustment added"));
    }
    /* Released in the same tick the commit finished. Deferring this to an
     * animation frame stranded the footer on any save that happened while
     * the tab was in the background, because that frame never arrives and
     * syncPanelFooter refuses to touch a button mid-submit. */
    state.submitting[type] = false;
    captureDraftBaseline(type);
    window.setTimeout(function () {
      highlight = { type: "", id: "" };
      renderType(tabType);
    }, 1700);
  }

  /* Machine id for a user-created card, matching the seeded convention
   * RC-DAS-<ENTITY>-<UF|SC|MY>-<SSEE>. The season takes the last two
   * digits of each year, so 2026-2027 becomes 2627 rather than the 2027
   * an earlier slice(-4) produced. The trailing base-36 stamp guards
   * against two cards sharing an entity, marketplace, and season; the
   * seeded cards avoid that collision with a scope token instead. */
  function generateCardId() {
    var entity = (file.card.buyingEntityName || "NEW").toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 10) || "NEW";
    var marketplace = { "Upfront": "UF", "Scatter": "SC", "Multi-Year": "MY" }[file.card.marketplace] || "RC";
    var years = String(file.card.dealSeason || "").match(/\d{4}/g) || [];
    var season = years.length > 1 ? years[0].slice(2) + years[1].slice(2) : "2526";
    return "RC-DAS-" + entity + "-" + marketplace + "-" + season + "-" + Date.now().toString(36).toUpperCase().slice(-4);
  }

  function saveFile(status) {
    if (state.saving) return false;
    updateFileCard();
    commitLineLiveSync({ includeNewDraft: true });
    if (status === "Published" && !cardIsValid(true)) return false;
    if (!file.card.id) file.card.id = generateCardId();
    state.saving = true;
    updateSaveState();
    file.status = status;
    file.lines.forEach(function (line) { line.attachToCard = file.card.id; });
    file.premiums.forEach(function (premium) { premium.attachToCard = file.card.id; });
    if (!persistFile()) {
      // Failed write keeps every working row and the enabled button, so
      // the user can retry without retyping anything. persistFile has
      // already surfaced the error.
      state.saving = false;
      updateSaveState();
      return false;
    }
    loadedCardName = text(file.card.name, 240);
    hydrateCardForm();
    syncAttachFields();
    dirty = false;
    state.saving = false;
    // Baseline moves to the state that was actually written, so Save
    // switches back off and a later undo of a new edit is measured
    // against the saved rows rather than the ones loaded at open.
    captureBaseline();
    syncListRowFromFile();
    showOperationToast(status === "Published"
      ? "Rate card saved"
      : "Rate card saved as draft");
    try {
      var url = new URL(location.href);
      url.searchParams.set("section", "create");
      url.searchParams.set("mode", "edit");
      url.searchParams.set("cardId", file.card.id);
      /* Preserve whichever 2.x the user is actually on. Pinning the
       * literal "2.0" here would drop a 2.1 session back to 2.0 on the
       * next refresh of the deep link this line just wrote. */
      url.searchParams.set("version", document.body.getAttribute("data-version") || ACTIVE_VERSIONS[0]);
      history.replaceState({ section: "create" }, "", url.toString());
      contextKey = "edit:" + file.card.id;
      document.body.setAttribute("data-mode", "edit");
    } catch (_) {}
    updateTitle(true);
    updateSaveState();
    return true;
  }

  function wireRoot() {
    root.addEventListener("click", function (event) {
      var target = event.target instanceof Element ? event.target : null;
      if (!target) return;
      var tab = target.closest("[data-v2-tab]");
      if (tab) {
        requestSwitchTab(tab.getAttribute("data-v2-tab"), false);
        return;
      }
      var actionEl = target.closest("[data-v2-action]");
      var action = actionEl && actionEl.getAttribute("data-v2-action");
      if (action === "accordion") {
        var section = actionEl.getAttribute("data-section");
        var accordion = actionEl.closest("[data-v2-accordion]");
        if (accordion && accordion.classList.contains("is-open")) {
          collapseAccordion(section);
        } else if (section === "line") {
          beginAdd("line", actionEl);
        } else if (section === "premium") {
          if (premiumFormHasDraft()) {
            initiatedBy = actionEl;
            switchTab("premiums", false);
            openAccordion("premium", true);
            renderType("premiums");
          } else {
            beginAdd("premium", actionEl);
          }
        } else {
          openAccordion(section);
        }
        return;
      }
      if (action === "toggle-save-menu") {
        toggleSaveMenu();
        return;
      }
      if (action === "save-draft" && actionEl.closest(".splitbtn__menu")) {
        closeSaveMenu();
        // Falls through to the generic save-draft/save-card handler
        // registered on document below (same data-v2-action name), which
        // performs the actual saveFile("Draft") call.
      }
      if (action === "add-line") { beginAdd("line", actionEl); return; }
      if (action === "add-premium") { beginAdd("premium", actionEl); return; }
      if (action === "cancel-line") { requestCancelItem("line"); return; }
      if (action === "cancel-premium") { requestCancelItem("premium"); return; }
      if (action === "close-panel") {
        // Whichever of Line/Premium Details is open, the shared panel
        // close icon (Figma 643:65724) closes it exactly like that
        // section's own Cancel would, down to the discard prompt: being
        // in the header does not make it a different action.
        var openType = root.querySelector('[data-v2-accordion="line"].is-open')
          ? "line"
          : root.querySelector('[data-v2-accordion="premium"].is-open') ? "premium" : "";
        if (openType) requestCancelItem(openType);
        return;
      }
      if (action === "request-remove-line") { openRemoveLineModal(actionEl); return; }
      if (action === "cancel-remove-line") { closeRemoveLineModal(); return; }
      if (action === "confirm-remove-line") { confirmRemoveLine(); return; }
      if (action === "request-remove-premium") { openRemovePremiumModal(actionEl); return; }
      if (action === "clear-line-search") {
        var lineSearch = root.querySelector('[data-v2-search="lines"]');
        if (lineSearch) {
          lineSearch.value = "";
          lineSearch.dispatchEvent(new Event("input", { bubbles: true }));
          lineSearch.focus();
        }
        return;
      }
      if (action === "clear-premium-refinements") {
        var premiumSearch = root.querySelector('[data-v2-search="premiums"]');
        var premiumFilter = root.querySelector('[data-v2-filter="premiums"]');
        if (premiumSearch) {
          premiumSearch.value = "";
          premiumSearch.dispatchEvent(new Event("input", { bubbles: true }));
          premiumSearch.focus();
        }
        if (premiumFilter) {
          premiumFilter.value = "";
          premiumFilter.dispatchEvent(new Event("change", { bubbles: true }));
          if (typeof window.refreshAdsDropdown === "function") {
            window.refreshAdsDropdown(premiumFilter);
          }
        }
        return;
      }
      if (action === "retry-load") {
        state.error = "";
        loadContext(true);
        return;
      }
      if (action === "edit-row") {
        var row = actionEl.closest("[data-v2-row-id]");
        requestSelectRow(
          row.getAttribute("data-v2-row-type"),
          row.getAttribute("data-v2-row-id"),
          row
        );
        return;
      }
      if (action === "remove-row") {
        var removeRowEl = actionEl.closest("[data-v2-row-id]");
        removeRow(
          removeRowEl.getAttribute("data-v2-row-type"),
          removeRowEl.getAttribute("data-v2-row-id"),
          actionEl
        );
        return;
      }
      if (action === "edit-card-details") {
        openCardDetailsEditor(actionEl);
        return;
      }
      if (action === "toggle-line-filter") {
        if (lineFilterPanelOpen()) closeLineFilterPanel(true);
        else openLineFilterPanel();
        return;
      }
      if (action === "apply-line-filter") {
        applyLineFilters();
        return;
      }
      if (action === "reset-line-filter") {
        resetLineFilters();
        return;
      }
      if (action === "cancel-line-filter") {
        closeLineFilterPanel(true);
        return;
      }
      // A row opens Line Item Details; its checkbox only selects. The
      // checkbox is a <label> wrapping the input, so the label has to be
      // excluded here as well as the input itself.
      var rowEl = target.closest("[data-v2-row-id]");
      if (rowEl && !target.closest("button, a, input, select, label, .create-md__td-checkbox")) {
        requestSelectRow(
          rowEl.getAttribute("data-v2-row-type"),
          rowEl.getAttribute("data-v2-row-id"),
          rowEl
        );
        return;
      }
      var sort = target.closest("[data-v2-sort]");
      if (sort) {
        var parts = sort.getAttribute("data-v2-sort").split(":");
        var view = state[parts[0]];
        if (view.sortKey === parts[1]) view.direction *= -1;
        else { view.sortKey = parts[1]; view.direction = 1; }
        view.page = 1;
        renderType(parts[0]);
        return;
      }
      var pageButton = target.closest("[data-v2-page]");
      if (pageButton && !pageButton.disabled) {
        var pageParts = pageButton.getAttribute("data-v2-page").split(":");
        var pageType = pageParts[0];
        var totalPages = paginationState(
          pageType,
          filteredRows(pageType).length
        ).totalPages;
        state[pageType].page = Math.min(
          Math.max(1, Number(pageParts[1]) || 1),
          Math.max(1, totalPages)
        );
        renderType(pageType);
      }
    });

    root.addEventListener("keydown", function (event) {
      var activeRemoveModal = root.querySelector("[data-v2-remove-modal]");
      if (event.key === "Tab" && activeRemoveModal && !activeRemoveModal.hidden) {
        var modalFocusables = Array.prototype.slice.call(
          activeRemoveModal.querySelectorAll("button:not(:disabled), [href], input:not(:disabled), select:not(:disabled)")
        );
        if (modalFocusables.length) {
          var firstModalControl = modalFocusables[0];
          var lastModalControl = modalFocusables[modalFocusables.length - 1];
          if (event.shiftKey && document.activeElement === firstModalControl) {
            event.preventDefault();
            lastModalControl.focus();
          } else if (!event.shiftKey && document.activeElement === lastModalControl) {
            event.preventDefault();
            firstModalControl.focus();
          }
        }
      }
      if (event.key === "Escape") {
        if (activeRemoveModal && !activeRemoveModal.hidden) {
          event.preventDefault();
          closeRemoveLineModal();
          return;
        }
        if (root.querySelector('.ads-dd__trigger[aria-expanded="true"]')) return;
        /* The filter drawer is the topmost thing on screen while it is
         * open, so Escape belongs to it before anything underneath. It
         * used to be tested further down, past the accordion branch
         * below, which meant Escape cancelled the open Line Details item
         * instead of closing the filters whenever both were open, which
         * on this route is always. */
        if (lineFilterPanelOpen()) {
          event.preventDefault();
          closeLineFilterPanel(true);
          return;
        }
        var openItem = root.querySelector('[data-v2-accordion="line"].is-open, [data-v2-accordion="premium"].is-open');
        if (openItem) {
          event.preventDefault();
          requestCancelItem(openItem.getAttribute("data-v2-accordion"));
          return;
        }
      }
      var tab = event.target.closest && event.target.closest("[data-v2-tab]");
      if (tab && ["ArrowLeft", "ArrowRight", "Home", "End"].indexOf(event.key) >= 0) {
        event.preventDefault();
        var tabs = Array.prototype.slice.call(root.querySelectorAll("[data-v2-tab]"));
        var currentIndex = tabs.indexOf(tab);
        var nextIndex = event.key === "Home"
          ? 0
          : event.key === "End"
            ? tabs.length - 1
            : event.key === "ArrowRight"
              ? (currentIndex + 1) % tabs.length
              : (currentIndex - 1 + tabs.length) % tabs.length;
        requestSwitchTab(tabs[nextIndex].getAttribute("data-v2-tab"), true);
        return;
      }
      var row = event.target.closest && event.target.closest("[data-v2-row-id]");
      var onRowControl = event.target.closest
        && event.target.closest("input, label, button, a, select");
      if (row && !onRowControl && (event.key === "Enter" || event.key === " ")) {
        event.preventDefault();
        requestSelectRow(
          row.getAttribute("data-v2-row-type"),
          row.getAttribute("data-v2-row-id"),
          row
        );
      }
    });

    // Fired by the shared rate card modal (app.js) after an edit-mode
    // save succeeds.
    document.addEventListener("rcm:card-updated", function (event) {
      var cardId = event.detail && event.detail.cardId;
      refreshCardFromStorage(cardId);
    });

    root.addEventListener("rcle:capture-state", function (event) {
      var receiver = event.detail && event.detail.receive;
      if (typeof receiver !== "function") return;
      var openAccordionEl = root.querySelector("[data-v2-accordion].is-open");
      receiver({
        activeTab: state.activeTab,
        selected: {
          lines: state.selected.lines,
          premiums: state.selected.premiums
        },
        accordion: openAccordionEl
          ? openAccordionEl.getAttribute("data-v2-accordion")
          : ""
      });
    });

    root.addEventListener("rcle:restore-state", function (event) {
      var snapshot = event.detail && event.detail.state;
      if (!snapshot) return;
      state.selected.lines = snapshot.selected && snapshot.selected.lines || "";
      state.selected.premiums = snapshot.selected && snapshot.selected.premiums || "";

      ["line", "premium"].forEach(function (formType) {
        var tabType = formType === "line" ? "lines" : "premiums";
        var rows = formType === "line" ? file.lines : file.premiums;
        var selectedId = state.selected[tabType];
        var selectedRow = rows.find(function (row) { return row.id === selectedId; });
        if (!selectedRow) {
          clearItemForm(formType);
          return;
        }
        populateForm(root.querySelector('[data-v2-form="' + formType + '"]'), selectedRow);
        if (formType === "premium") syncPremiumDatePickers(selectedRow);
      });

      /* Row highlighting is painted, not derived, so restoring the
       * selection state is not enough: without a repaint the row the
       * presentation opened stays highlighted after it closes. */
      renderType("lines");
      renderType("premiums");

      switchTab(snapshot.activeTab === "premiums" ? "premiums" : "lines", false);
      if (snapshot.accordion) {
        openAccordion(snapshot.accordion, false);
      } else {
        ["card", "line", "premium"].forEach(collapseAccordion);
      }
    });

    root.querySelectorAll("[data-v2-search]").forEach(function (input) {
      var wrap = input.closest(".ads-search");
      var clear = wrap && wrap.querySelector("[data-v2-clear-search]");
      var syncPresentation = function () {
        var filled = Boolean(input.value);
        if (wrap) wrap.setAttribute("data-filled", String(filled));
        if (clear) clear.hidden = !filled;
      };
      input.addEventListener("input", function () {
        var type = input.getAttribute("data-v2-search");
        state[type].query = input.value;
        state[type].page = 1;
        syncPresentation();
        renderType(type);
      });
      if (clear) {
        clear.addEventListener("click", function () {
          var type = input.getAttribute("data-v2-search");
          input.value = "";
          state[type].query = "";
          state[type].page = 1;
          syncPresentation();
          renderType(type);
          input.focus();
        });
      }
      syncPresentation();
    });
    root.querySelectorAll("[data-v2-filter]").forEach(function (select) {
      select.addEventListener("change", function () {
        var type = select.getAttribute("data-v2-filter");
        state[type].filter = select.value;
        state[type].page = 1;
        renderType(type);
      });
    });
    root.querySelectorAll("[data-v2-page-size]").forEach(function (select) {
      select.addEventListener("change", function () {
        var type = select.getAttribute("data-v2-page-size");
        var next = Number(select.value);
        state[type].pageSize = [10, 20, 50].indexOf(next) >= 0 ? next : 10;
        state[type].page = 1;
        renderType(type);
      });
    });
    root.querySelectorAll("[data-v2-go-page]").forEach(function (select) {
      select.addEventListener("change", function () {
        var type = select.getAttribute("data-v2-go-page");
        var pages = Math.ceil(filteredRows(type).length / state[type].pageSize);
        state[type].page = Math.min(Math.max(1, Number(select.value) || 1), Math.max(1, pages));
        renderType(type);
      });
    });

    var cardForm = root.querySelector('[data-v2-form="card"]');
    cardForm.addEventListener("input", function (event) {
      updateFileCard();
      setDirty(true);
      updateSaveState();
      if (event.target.name === "name") updateTitle(true);
    });
    cardForm.addEventListener("change", function () {
      updateFileCard();
      setDirty(true);
      updateSaveState();
    });
    cardForm.addEventListener("focusout", function (event) {
      if (isDropdownChrome(event.target)) return;
      if (!(event.target instanceof HTMLInputElement || event.target instanceof HTMLSelectElement)) return;
      updateFileCard();
      if (event.target.name === "name") updateTitle(true);
      if (event.target.required) {
        var ok = Boolean(fieldValue(cardForm, event.target.name));
        if (event.target.name === "dealSeason") ok = /^\d{4}-\d{4}$/.test(event.target.value);
        setFieldValidity(event.target, ok, "Required");
      }
    });
    ["effectiveStart", "effectiveEnd"].forEach(function (name) {
      var trigger = cardForm.querySelector(
        '[data-field="v2-' + (name === "effectiveStart" ? "effective-start" : "effective-end") + '"] .ads-datepicker__trigger'
      );
      var touched = false;
      function validateTransition(relatedTarget) {
        var datePicker = trigger.closest(".ads-datepicker");
        var popover = datePicker && (datePicker._adsCalPop
          || datePicker.querySelector(".ads-datepicker__popover"));
        if (popover && relatedTarget instanceof Node && popover.contains(relatedTarget)) return;
        touched = false;
        updateFileCard();
        var dateControl = datePicker.querySelector('input[name="' + name + '"]');
        setFieldValidity(dateControl, Boolean(dateControl.value), "Required");
      }
      trigger.addEventListener("blur", function (event) {
        validateTransition(event.relatedTarget);
      });
      trigger.addEventListener("focus", function () {
        touched = true;
      });
      document.addEventListener("focusin", function (event) {
        if (!touched || event.target === trigger) return;
        validateTransition(event.target);
      });
    });

    var lineForm = root.querySelector('[data-v2-form="line"]');
    lineForm.addEventListener("change", function (event) {
      if (event.target.name !== "adProduct") return;
      setFieldValidity(event.target, Boolean(event.target.value), "Required");
    });

    /* Save Rate Card follows the panel as it is typed in, not only when a
     * row is committed: the first meaningful value in a new Line or
     * Premium is unsaved work even while the row is still incomplete.
     * itemFormSignature compares against the values the panel opened
     * with, so focusing a field or reopening a dropdown changes nothing. */
    ["line", "premium"].forEach(function (type) {
      var itemForm = root.querySelector('[data-v2-form="' + type + '"]');
      if (!itemForm) return;
      function onEdit() {
        updateSaveState();
        // Per keystroke, so the primary button turns on the moment the
        // last required field becomes valid and off again if it stops
        // being valid, rather than waiting for a blur.
        syncPanelFooter(type);
      }
      itemForm.addEventListener("input", onEdit);
      itemForm.addEventListener("change", onEdit);
    });

    // v2.1 live-sync (Figma 643:65724 has no submit button in the panel):
    // a field commit happens on blur/change - once it leaves an input or
    // a dropdown selection changes - never per keystroke, so mid-word
    // typing never fires a commit. See commitLineLiveSync.
    /* A dropdown's own search field is chrome, not a value: it lives
     * inside the form only because the listbox does. Committing on the
     * way out of it would re-render the panel underneath the user and
     * take the focus they were moving into the results. */
    function isDropdownChrome(node) {
      return Boolean(node && node.classList
        && node.classList.contains("ads-dd__search-input"));
    }

    lineForm.addEventListener("focusout", function (event) {
      if (!isV21()) return;
      if (isDropdownChrome(event.target)) return;
      if (!(event.target instanceof HTMLInputElement || event.target instanceof HTMLSelectElement)) return;
      commitLineLiveSync();
    });
    lineForm.addEventListener("change", function (event) {
      if (!isV21()) return;
      // Native <select> (Base Offering, Cost Method, Currency) fires
      // "change" directly on itself. Ad Type is the custom .ads-dd
      // dropdown (selectAdsDdOption in app.js), which fires "change" on
      // its own hidden input once a listbox option is picked.
      var isSelect = event.target.tagName === "SELECT";
      var isAdsDd = Boolean(event.target.closest && event.target.closest("[data-ads-dd]"));
      if (!isSelect && !isAdsDd) return;
      commitLineLiveSync();
    });

    lineForm.addEventListener("submit", function (event) {
      event.preventDefault();
      submitItem("line");
    });
    root.querySelector('[data-v2-form="premium"]').addEventListener("submit", function (event) {
      event.preventDefault();
      submitItem("premium");
    });
  }

  function activate(forceContext) {
    root = document.querySelector("[data-v2-root]");
    if (!root) return;
    var active = isV2();
    root.hidden = !active;
    document.querySelectorAll("[data-v2-heading], .create-md__header-action").forEach(function (el) {
      el.hidden = !active;
    });
    // v2.1's Rate Card Details page (this task) shows the "Save Rate
    // Card" split button in place of v2.0's original two separate
    // header buttons. Both markups always exist; only one is unhidden.
    var is21 = document.body.getAttribute("data-version") === "2.1";
    var legacyActions = document.querySelector("[data-v2-header-actions-legacy]");
    var splitbtn = document.querySelector("[data-v2-header-splitbtn]");
    if (legacyActions) legacyActions.hidden = active && is21;
    if (splitbtn) splitbtn.hidden = !(active && is21);
    if (active && document.body.getAttribute("data-route") === "create") loadContext(forceContext);
  }

  /* DCM Rule Order is a plain text input (no native number stepper), so this
   * strips any non-digit characters as the user types, the same input-filter
   * pattern already used for the v1.1/v1.2 CARD form's #dcm-rule field
   * (initDcmRuleInputFilter in app.js). Numeric coercion for save/validation
   * still happens in validateCard/finiteNumber; this only keeps the visible
   * text itself digits-only. */
  function initV2DcmRuleInputFilter() {
    var input = document.getElementById("v2-rule-order");
    if (!input) return;
    input.addEventListener("input", function () {
      var raw = input.value;
      var cleaned = raw.replace(/\D+/g, "");
      if (cleaned === raw) return;
      var caret = input.selectionStart || 0;
      var digitsBeforeCaret = raw.slice(0, caret).replace(/\D+/g, "").length;
      input.value = cleaned;
      try { input.setSelectionRange(digitsBeforeCaret, digitsBeforeCaret); }
      catch (_) { /* setSelectionRange throws on unsupported types; ignore. */ }
    });
  }

  function enhanceV2Selects() {
    if (typeof window.enhanceAdsSelect !== "function") return;
    root.querySelectorAll("select").forEach(function (select) {
      window.enhanceAdsSelect(select, { size: "small" });
    });
  }

  /* Wizard half of the UI state bridge (see app.js). loadContext() resets
   * the tab, selection, accordion and both item tables every time the
   * editor mounts, so a preview booted at the same edit URL would show the
   * default arrangement instead of what the user was looking at. These two
   * functions hand that arrangement across. Field values are copied by the
   * app-level bridge; this only covers state that lives in v2's closure. */
  function captureWizardState() {
    if (!root || root.hidden) return null;
    var openAccordionEl = root.querySelector("[data-v2-accordion].is-open");
    return {
      activeTab: state.activeTab,
      selected: {
        lines: state.selected.lines,
        premiums: state.selected.premiums
      },
      accordion: openAccordionEl
        ? openAccordionEl.getAttribute("data-v2-accordion")
        : "",
      lines: {
        query: state.lines.query,
        sortKey: state.lines.sortKey,
        direction: state.lines.direction,
        page: state.lines.page,
        pageSize: state.lines.pageSize
      },
      premiums: {
        query: state.premiums.query,
        filter: state.premiums.filter,
        sortKey: state.premiums.sortKey,
        direction: state.premiums.direction,
        page: state.premiums.page,
        pageSize: state.premiums.pageSize
      }
    };
  }

  function restoreWizardTable(type, snapshot) {
    if (!snapshot) return;
    var target = state[type];
    target.query = snapshot.query || "";
    target.sortKey = snapshot.sortKey || target.sortKey;
    target.direction = snapshot.direction === -1 ? -1 : 1;
    target.pageSize = Number(snapshot.pageSize) || target.pageSize;
    target.page = Number(snapshot.page) || 1;
    if (type === "premiums") target.filter = snapshot.filter || "";

    var search = root.querySelector('[data-v2-search="' + type + '"]');
    if (search) {
      search.value = target.query;
      var wrap = search.closest(".ads-search");
      var clear = wrap && wrap.querySelector("[data-v2-clear-search]");
      if (wrap) wrap.setAttribute("data-filled", String(Boolean(target.query)));
      if (clear) clear.hidden = !target.query;
    }
    var filter = root.querySelector('[data-v2-filter="' + type + '"]');
    if (filter && type === "premiums") {
      filter.value = target.filter;
      if (typeof window.syncAdsDropdown === "function") {
        try { window.syncAdsDropdown(filter); } catch (_) {}
      }
    }
  }

  function restoreWizardState(snapshot) {
    if (!root || root.hidden || !snapshot || !file) return false;
    state.selected.lines = (snapshot.selected && snapshot.selected.lines) || "";
    state.selected.premiums = (snapshot.selected && snapshot.selected.premiums) || "";
    restoreWizardTable("lines", snapshot.lines);
    restoreWizardTable("premiums", snapshot.premiums);

    ["line", "premium"].forEach(function (formType) {
      var tabType = formType === "line" ? "lines" : "premiums";
      var rows = formType === "line" ? file.lines : file.premiums;
      var selectedId = state.selected[tabType];
      var selectedRow = rows.find(function (row) { return row.id === selectedId; });
      if (!selectedRow) {
        clearItemForm(formType);
        return;
      }
      populateForm(root.querySelector('[data-v2-form="' + formType + '"]'), selectedRow);
      if (formType === "premium") syncPremiumDatePickers(selectedRow);
    });

    switchTab(snapshot.activeTab === "premiums" ? "premiums" : "lines", false);
    renderType("lines");
    renderType("premiums");
    if (snapshot.accordion) {
      openAccordion(snapshot.accordion, false);
    } else {
      ["card", "line", "premium"].forEach(collapseAccordion);
    }
    return true;
  }

  window.RateCardV2StateBridge = {
    capture: function () {
      try { return captureWizardState(); } catch (_) { return null; }
    },
    restore: function (snapshot) {
      try { return restoreWizardState(snapshot); } catch (_) { return false; }
    },
    /* activate() normally runs from the route observer, which is async, so a
     * caller that deep links straight into Edit Rate Card would look at the
     * wizard before it had loaded its record. Redline's overlay gallery uses
     * this to load that record first, and get the same result the observer
     * would have produced a tick later. */
    ensureContext: function () {
      try {
        activate(true);
        if (!file) return false;
        // loadContext() renders a loading state and only swaps in the real
        // rows on the next frame. Settle that here so the caller sees the
        // populated tables immediately. The pending frame just re-renders.
        state.loading = false;
        if (root) root.setAttribute("aria-busy", "false");
        renderAll();
        return true;
      } catch (_) {
        return false;
      }
    }
  };

  function init() {
    root = document.querySelector("[data-v2-root]");
    if (!root) return;
    enhanceV2Selects();
    initConditionFields();
    wireRoot();
    initV2DcmRuleInputFilter();
    document.addEventListener("click", function (event) {
      var target = event.target instanceof Element ? event.target : null;
      if (!target || !isV2()) return;
      var day = target.closest(".ads-cal__day");
      var datePopover = day && target.closest("[data-v2-date-field]");
      if (day && datePopover) {
        var dateName = datePopover.getAttribute("data-v2-date-field");
        var dateFormType = datePopover.getAttribute("data-v2-date-form") || "card";
        var dateInput = root.querySelector(
          '[data-v2-form="' + dateFormType + '"] [name="' + dateName + '"]'
        );
        if (dateInput) {
          dateInput.value = day.getAttribute("data-iso") || "";
          if (dateFormType === "card") {
            setDirty(true);
            setFieldValidity(dateInput, Boolean(dateInput.value), "Required");
            updateFileCard();
          }
          // A premium date picked here is a PREM field edit, so it has to
          // reach the same unsaved-changes check as a typed field.
          updateSaveState();
        }
      }
      var headerAction = target.closest("[data-v2-action]");
      var headerActionName = headerAction && headerAction.getAttribute("data-v2-action");
      if (headerActionName === "save-draft" || headerActionName === "save-card") {
        // v2.1's Rate Card Details page (this task) replaced the two
        // separate header buttons with one "Save Rate Card" split button
        // whose only dropdown option is "Save as draft". The dropdown
        // item always forces Draft (an explicit unpublish/keep-working
        // action). The main "Save Rate Card" button is a generic save
        // that preserves whatever status the card already has, so
        // saving edits to an existing Published card keeps it
        // Published instead of silently downgrading it - see R18 "do
        // not make read-only content editable... preserve current
        // status". A brand-new card has no status yet, so it defaults
        // to Draft either way (blankFile() already seeds "Draft").
        // Publish/"Save Rate Card File and Publish" is not part of this
        // workflow. v2.0 keeps its original two-button, two-outcome
        // behavior untouched.
        if (document.body.getAttribute("data-version") === "2.1") {
          if (headerActionName === "save-draft") saveFile("Draft");
          else saveFile(file && file.status === "Published" ? "Published" : "Draft");
        }
        else if (headerActionName === "save-draft") saveFile("Draft");
        else saveFile("Published");
      }
    });
    document.addEventListener("click", function (event) {
      if (!isV2() || !(event.target instanceof Element)) return;
      var create = event.target.closest('[data-action="create"]');
      var list = event.target.closest('[data-action="go-list"]');
      if (!create && !list) return;
      if (list && hasUnsavedWork() && !leaveConfirmed) {
        /* The guard is asked in an ADS dialog rather than the browser's
         * own confirm(), which means the answer arrives later than the
         * click. So this navigation is dropped, and on Leave the same
         * control is clicked again with the guard satisfied. */
        event.preventDefault();
        event.stopImmediatePropagation();
        var trigger = list;
        confirmLeaveWithUnsavedWork(function () {
          // Leaving without saving discards the working rows: the next
          // open of this card reloads the persisted baseline from storage.
          discardWorkingState();
          leaveConfirmed = true;
          try { trigger.click(); } finally { leaveConfirmed = false; }
        });
        return;
      }
      try {
        var url = new URL(location.href);
        url.searchParams.delete("mode");
        url.searchParams.delete("cardId");
        history.replaceState(history.state, "", url.toString());
      } catch (_) {}
      if (create) {
        contextKey = "";
        file = null;
        baseline.loaded = false;
      }
    }, true);
    window.addEventListener("beforeunload", function (event) {
      if (!isV2() || !hasUnsavedWork()) return;
      event.preventDefault();
      event.returnValue = "";
    });
    window.addEventListener("rcm:versionchange", function () {
      activate(true);
    });
    window.addEventListener("popstate", function () {
      activate(true);
    });
    var observer = new MutationObserver(function (records) {
      var relevant = records.some(function (record) {
        return record.attributeName === "data-route"
          || record.attributeName === "data-mode"
          || record.attributeName === "data-version";
      });
      if (relevant) requestAnimationFrame(function () { activate(false); });
    });
    observer.observe(document.body, {
      attributes: true,
      attributeFilter: ["data-route", "data-mode", "data-version"]
    });
    activate(true);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
