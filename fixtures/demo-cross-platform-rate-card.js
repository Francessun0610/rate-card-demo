/*
 * Synthetic development fixture for the cross-platform Rate Card demo.
 * Enable with ?demoData=cross-platform-2026-27.
 * Remove that query parameter to disable the fixture.
 */
(function () {
  "use strict";

  var DEMO_KEY = "cross-platform-2026-27";
  /* Bumped with the naming pass so a copy stored under the old name and
   * id refreshes to the renamed fixture instead of lingering in the list. */
  var FIXTURE_KEY = "cross-platform-2026-27-records-v4";
  /* Follows the same RC-DAS-<ENTITY>-<SCOPE>-<MKT>-<SEASON> convention as
   * the seeded portfolio. It used to read RC-DEMO-CROSSPLATFORM-UF-2627,
   * which announced itself as demo scaffolding in a column Ad Sales
   * reads as a real identifier. The fixture is still opt-in behind
   * ?demoData=cross-platform-2026-27; only the label changed. */
  var CARD_ID = "RC-DAS-DISNEYADS-XPLAT-UF-2627";
  var LIST_ID = "demo-cross-platform-2627";
  var FILE_STORAGE_KEY = "rate-card-manager.v2.files";
  var QUICK_EDIT_STORAGE_KEY = "rate-card-manager.quick-edit.v1";

  /* Advertisers, Line Conditions, and the pricing bands all come from
   * the catalog fixture, which loads first and owns the controlled
   * vocabulary. Sharing it keeps one advertiser on one ID and one
   * offering on one display name across every demo surface. */
  var CATALOG = window.RCMCatalog || {};
  var advertisers = (CATALOG.advertisers || []).map(function (item) {
    return [item.id, item.name, item.category];
  });
  var C = CATALOG.conditions || {};
  /* One optional condition per LINE, stored the catalog's way: "no
   * additional targeting" is an absent field, not a value. */
  var lineCondition = CATALOG.lineCondition || function (value) { return value; };
  var PC = CATALOG.premiumConditions || {};

  /* Rows per advertiser. Real books are lopsided: a handful of large
   * advertisers carry most of the rules and the long tail carries a
   * few, so no advertiser owns an identical block of rows. */
  var ROWS_PER_ADVERTISER = [10, 9, 8, 8, 7, 7, 7, 7, 6, 6, 6, 6, 5, 4, 4];

  // Ad Type values are strictly formats. Base Offering carries the
  // platform / property axis (Disney+ Select, ESPN Streaming Sports,
  // Disney Streaming Bundle). Pricing keys on Base Offering, which is
  // where those platform/property semantics belong per the 6-Pager audit.
  var inventoryPatterns = [
    { adProduct: "Standard Video",     baseOffering: "Disney+ Select",               rateType: "CPM" },
    { adProduct: "Standard Video",     baseOffering: "Hulu Select",                  rateType: "CPM" },
    { adProduct: "Sports Video",       baseOffering: "ESPN Streaming Sports",        rateType: "CPM" },
    { adProduct: "Pause Ad",           baseOffering: "Disney Streaming Bundle",      rateType: "CPM" },
    { adProduct: "Standard Video",     baseOffering: "Disney Streaming Bundle",      rateType: "CPM" },
    { adProduct: "Connected TV Video", baseOffering: "Disney Streaming Bundle",      rateType: "CPM" },
    { adProduct: "Live Event Video",   baseOffering: "Disney Streaming Live Events", rateType: "Flat Rate" },
    { adProduct: "Pause Ad",           baseOffering: "Disney Streaming Bundle",      rateType: "Flat Rate" },
    { adProduct: "Standard Video",     baseOffering: "Disney+ Select",               rateType: "Unit Price" },
    { adProduct: "Connected TV Video", baseOffering: "Hulu Select",                  rateType: "Unit Price" }
  ];

  /* Price follows the rule, never the row number. CPM comes straight
   * from the catalog's shared model, and the two negotiated cost methods
   * are quoted off that same CPM so a sponsorship or unit price moves
   * for the same reasons a CPM does. */
  function rateFor(pattern, condition) {
    var cpm = CATALOG.expectedRate
      ? CATALOG.expectedRate(pattern.baseOffering, pattern.adProduct, condition)
      : 35;
    if (pattern.rateType === "Flat Rate") return Math.round(cpm * 2000 / 5000) * 5000;
    if (pattern.rateType === "Unit Price") return Math.round(cpm * 20 / 25) * 25;
    return cpm;
  }

  function pad(number, size) {
    return String(number).padStart(size, "0");
  }

  function isoDate(day) {
    return "2026-07-" + pad(day, 2);
  }

  function roundRate(value) {
    return Number(value.toFixed(4));
  }

  function hash(value) {
    var result = 2166136261;
    String(value).split("").forEach(function (character) {
      result ^= character.charCodeAt(0);
      result = Math.imul(result, 16777619);
    });
    return result >>> 0;
  }

  function pick(values, seed, salt) {
    return values[hash(seed + ":" + salt) % values.length];
  }

  /* The intent rule an advertiser's own category buys against, read from
   * the catalog's map so a beauty book never prices auto intenders and
   * "Home improvement retail" is not mistaken for mass retail. */
  var INTENT_BY_CATEGORY = CATALOG.intentByCategory || {};

  function intentFor(category) {
    return INTENT_BY_CATEGORY[category] || C.household;
  }

  function conditionPool(advertiser, pattern) {
    // Sports and live inventory carry content rules; everything else
    // carries an audience, geo, device, or the advertiser's own intent
    // segment. Base Offering, not Ad Type, decides which pool applies.
    if (/ESPN|Live Events/.test(pattern.baseOffering)) {
      return [C.nfl, C.sports, C.live, C.a2554, C.national];
    }
    return [
      C.none, C.a1849, C.a2554, C.national, C.northeast, C.ctv, C.auth,
      C.streamers, C.series, intentFor(advertiser[2])
    ];
  }

  /* Pick the first rule this advertiser does not already price: walk its
   * targeting pool from a per-row starting point, then move to the next
   * inventory pattern if the pool is spent. Ten patterns against ten
   * conditions leaves far more combinations than any advertiser's row
   * count, so a rule is always available and no row repeats another. */
  function assignRule(advertiser, patternIndex, seed, written) {
    for (var shift = 0; shift < inventoryPatterns.length; shift += 1) {
      var pattern = inventoryPatterns[(patternIndex + shift) % inventoryPatterns.length];
      var pool = conditionPool(advertiser, pattern);
      var offset = hash(seed + ":" + shift) % pool.length;
      for (var step = 0; step < pool.length; step += 1) {
        var condition = pool[(offset + step) % pool.length];
        /* Cost method is deliberately not part of the key: two rows that
         * price the same inventory, format and targeting read as the
         * same rule to a salesperson even when one is quoted on CPM and
         * the other on a unit price. */
        var key = [advertiser[0], pattern.adProduct, pattern.baseOffering,
          condition].join("|");
        if (written[key]) continue;
        written[key] = true;
        return { pattern: pattern, condition: condition };
      }
    }
    return null;
  }

  /* Real books interleave: the largest advertisers come round most
   * often, but no advertiser owns a consecutive block of rows, so a
   * salesperson paging through sees a mixed book rather than fifteen
   * alphabetical clusters. */
  function advertiserOrder() {
    var remaining = advertisers.map(function (advertiser, index) {
      return {
        advertiser: advertiser,
        index: index,
        slot: 0,
        left: ROWS_PER_ADVERTISER[index % ROWS_PER_ADVERTISER.length]
      };
    });
    var total = remaining.reduce(function (sum, entry) { return sum + entry.left; }, 0);
    var order = [];
    var previous = null;
    while (order.length < total) {
      var available = remaining.filter(function (entry) {
        return entry.left > 0 && entry !== previous;
      });
      if (!available.length) {
        available = remaining.filter(function (entry) { return entry.left > 0; });
      }
      var position = order.length;
      available.sort(function (left, right) {
        return (right.left - left.left)
          || (hash(CARD_ID + ":" + position + ":" + left.index) % 97)
           - (hash(CARD_ID + ":" + position + ":" + right.index) % 97);
      });
      var next = available[0];
      next.left -= 1;
      next.slot += 1;
      previous = next;
      order.push({ advertiser: next.advertiser, index: next.index, slot: next.slot - 1 });
    }
    return order;
  }

  function buildLines() {
    var written = {};
    return advertiserOrder().map(function (entry, position) {
      var advertiser = entry.advertiser;
      var lineNumber = position + 1;
      var rule = assignRule(
        advertiser,
        entry.index * 3 + entry.slot,
        CARD_ID + ":" + advertiser[0] + ":" + lineNumber,
        written
      );
      return {
        id: "LI-" + pad(lineNumber, 4),
        attachToCard: CARD_ID,
        advertiserId: advertiser[0],
        advertiserName: advertiser[1],
        advertiserCategory: advertiser[2],
        adProduct: rule.pattern.adProduct,
        baseOffering: rule.pattern.baseOffering,
        rateType: rule.pattern.rateType,
        baseRate: roundRate(rateFor(rule.pattern, rule.condition)),
        currency: "USD",
        condition1: lineCondition(rule.condition),
        createdAt: "2026-06-" + pad(10 + (lineNumber % 18), 2) + "T14:00:00.000Z",
        updatedAt: isoDate(1 + (lineNumber * 3) % 28) + "T16:30:00.000Z"
      };
    });
  }

  /* Each adjustment is named for the rule it charges for, so a premium
   * only ever appears against lines carrying that rule. */
  var PREMIUM_BY_CONDITION = {};
  [
    [C.a1849, "1P Audience", "Demographic Guarantee Premium", 3, 10],
    [C.a2554, "1P Audience", "Adults 25-54 Guarantee Premium", 3.5, 10],
    [C.auth, "Device Type", "Authenticated Streaming Premium", 8, 60],
    [C.ctv, "Device Type", "Connected TV Premium", 10, 60],
    [C.streamers, "3P Audience", "Streaming Enthusiast Premium", 4, 20],
    [C.series, "Content", "Original Series Premium", 12, 30],
    [C.national, "Geo", "National Coverage Premium", 6, 40],
    [C.northeast, "Geo", "Regional Geo Premium", 9, 40],
    [C.sports, "Content", "Sports Content Premium", 15, 30],
    [C.nfl, "3P Audience", "Sports Fan Premium", 6.75, 20],
    [C.live, "Content", "Live Event Premium", 20, 30],
    [C.auto, "3P Audience", "Auto Intent Premium", 6, 20],
    [C.travel, "3P Audience", "Travel Intent Premium", 5.75, 20],
    [C.tech, "3P Audience", "Technology Intent Premium", 6.25, 20],
    [C.wireless, "3P Audience", "Wireless Intent Premium", 6, 20],
    [C.finance, "3P Audience", "Financial Intent Premium", 6.5, 20],
    [C.beauty, "3P Audience", "Beauty Intent Premium", 5.25, 20],
    [C.wellness, "3P Audience", "Wellness Intent Premium", 5.5, 20],
    [C.grocery, "3P Audience", "Grocery Intent Premium", 5, 20],
    [C.dining, "3P Audience", "Dining Intent Premium", 5, 20],
    [C.retail, "3P Audience", "Retail Intent Premium", 4.75, 20],
    [C.home, "3P Audience", "Home Improvement Intent Premium", 3.75, 20],
    [C.household, "3P Audience", "Household Intent Premium", 4.5, 20],
    [C.none, "Format", "High-Impact Format Premium", 6, 50]
  ].forEach(function (definition) {
    PREMIUM_BY_CONDITION[definition[0]] = definition;
  });

  /* A premium is charged for something, so it always names a trigger,
   * even when the rule it sits on carries no condition of its own. Where
   * the line is unconditioned, the premium names the delivery dimension
   * its own category is about, drawn from the catalog's premium-only
   * vocabulary rather than invented here. */
  var PREMIUM_TRIGGER_BY_CATEGORY = {
    "Format": PC.pauseAd,
    "Duration": PC.longForm
  };

  function premiumTrigger(line, category) {
    return line.condition1
      || PREMIUM_TRIGGER_BY_CATEGORY[category]
      || PC.pauseAd;
  }

  function primaryPremium(line, index) {
    var definition = PREMIUM_BY_CONDITION[line.condition1]
      || PREMIUM_BY_CONDITION[C.none];
    var category = definition[1];
    var name = definition[2];
    var method = "Percent Adjustment";
    var value = definition[3];
    var stackOrder = definition[4];

    if (category === "3P Audience" || category === "1P Audience"
        || category === "Format") {
      method = "Additive CPM";
    }

    if (line.rateType === "Flat Rate") {
      category = "Content";
      name = /Live Events/.test(line.baseOffering)
        ? "Live Event Sponsorship Premium"
        : "Cross-Portfolio Sponsorship Premium";
      method = "Flat Fee";
      // A sponsorship uplift is quoted off the sponsorship it sits on,
      // rounded the way sponsorship money is actually quoted.
      value = Math.round(line.baseRate * 0.1 / 2500) * 2500;
      stackOrder = 90;
    }

    return {
      category: category,
      displayName: name,
      calculationMethod: method,
      value: value,
      stackOrder: stackOrder,
      condition1: premiumTrigger(line, category),
      effectiveStart: "",
      effectiveEnd: ""
    };
  }

  /* The second adjustment a book charges on top of the first, one per
   * category. Each carries a fixed uplift, so the same adjustment always
   * costs the same wherever it appears. */
  var SECONDARY_PREMIUMS = {
    "Geo": ["Expanded Geo Coverage Premium", 2.5],
    "Duration": ["Extended Duration Premium", 3.25],
    "3P Audience": ["Intent Audience Premium", 4],
    "Device Type": ["Device Delivery Premium", 3.5],
    "Format": ["High-Impact Format Premium", 6],
    "1P Audience": ["First-Party Audience Premium", 4.75],
    "Content": ["Content Alignment Premium", 5.5]
  };

  function secondaryPremium(line, index, category) {
    var definition = SECONDARY_PREMIUMS[category];
    return {
      category: category,
      displayName: definition[0],
      calculationMethod: "Additive CPM",
      value: definition[1],
      stackOrder: 20 + index * 5,
      condition1: premiumTrigger(line, category),
      effectiveStart: "",
      effectiveEnd: ""
    };
  }

  /* A demand-window uplift charges for when the rule runs, so it only
   * sits on rules the window applies to: the championship window prices
   * sports and live inventory, and nothing else.
   *
   * Named for the window rather than the event because the WPP book
   * already charges a "Championship Event Premium" against championship
   * inventory for the whole season at a different rate. One name has to
   * mean one charge, or a seller reading two cards cannot tell which
   * they are quoting. */
  function seasonalPremium(line, index) {
    return {
      category: "Content",
      displayName: "Championship Window Premium",
      calculationMethod: "Percent Adjustment",
      value: 22,
      stackOrder: 80 + index,
      condition1: line.condition1,
      effectiveStart: "2027-01-01",
      effectiveEnd: "2027-02-28"
    };
  }

  function makePremium(template, line, premiumNumber) {
    return Object.assign({
      id: "PREM-" + pad(premiumNumber, 4),
      attachToCard: CARD_ID,
      lineItemIds: [line.id],
      advertiserName: line.advertiserName,
      createdAt: "2026-07-01T14:00:00.000Z",
      updatedAt: isoDate(1 + premiumNumber % 28) + "T17:00:00.000Z"
    }, template);
  }

  function buildPremiums(lines) {
    var premiums = [];
    var primaryLines = lines.slice(0, 30);
    primaryLines.forEach(function (line, index) {
      premiums.push(makePremium(primaryPremium(line, index), line, premiums.length + 1));
    });

    /* Each secondary premium hangs off one rule of a given shape. The
     * Duration premium takes the unconditioned rule: a LINE with no
     * condition is priced at the broad rate, which is exactly where a
     * length-based uplift belongs. It used to match the old
     * "No additional targeting" sentinel, which records no longer
     * store. */
    var secondaryRules = [
      ["Geo", /^Targeting: (?:Longform|Shortform) Video Line/],
      ["Duration", /^$/],
      ["3P Audience", /^DAR Demo: [MF]/],
      ["Device Type", /^Targeting: Livestreaming Line/],
      ["Format", /^Format: Preemptible/],
      ["1P Audience", /^DAR Demo: A/],
      ["Content", /^Targeting: (?:Football|NBA|NFL|College Football)/]
    ];
    var secondaryLines = secondaryRules.map(function (rule) {
      return lines.find(function (line) {
        return rule[1].test(line.condition1 || "");
      });
    });
    secondaryLines.push(lines.find(function (line) {
      return secondaryRules[0][1].test(line.condition1 || "")
        && line !== secondaryLines[0];
    }));
    secondaryLines.forEach(function (line, index) {
      /* A book need not contain a rule of every shape, and one that does
       * not simply goes without that premium rather than taking the
       * whole fixture down. */
      if (!line) return;
      var category = secondaryRules[index % secondaryRules.length][0];
      premiums.push(makePremium(secondaryPremium(line, index, category), line, premiums.length + 1));
    });

    var seasonalLines = [];
    lines.some(function (line) {
      if (/ESPN|Live Events/.test(line.baseOffering)
          && !seasonalLines.some(function (candidate) { return candidate.id === line.id; })) {
        seasonalLines.push(line);
      }
      return seasonalLines.length === 6;
    });
    seasonalLines.forEach(function (line, index) {
      premiums.push(makePremium(seasonalPremium(line, index), line, premiums.length + 1));
    });
    return premiums;
  }

  function buildFile() {
    var lines = buildLines();
    return {
      schemaVersion: 1,
      status: "Published",
      card: {
        id: CARD_ID,
        name: "Disney Advertising - Cross-Platform Upfront 2026-2027",
        marketplace: "Upfront",
        dealSeason: "2026-2027",
        buyingEntityId: "0013a00005XpLt2AAF",
        buyingEntityName: "Disney Advertising National Sales",
        dcmRuleOrder: 10,
        effectiveStart: "2026-10-01",
        effectiveEnd: "2027-09-30"
      },
      lines: lines,
      premiums: buildPremiums(lines),
      createdAt: "2026-06-01T14:00:00.000Z",
      updatedAt: "2026-07-29T17:00:00.000Z",
      fixtureKey: FIXTURE_KEY,
      syntheticDemoData: true
    };
  }

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function isEnabled() {
    return new URLSearchParams(window.location.search).get("demoData") === DEMO_KEY;
  }

  function getListRecord() {
    if (!isEnabled()) return null;
    return {
      id: LIST_ID,
      status: "Published",
      saleshubId: "0013a00005XpLt2AAF",
      rateCardId: CARD_ID,
      name: "Disney Advertising - Cross-Platform Upfront 2026-2027",
      marketplace: "Upfront",
      buyingEntity: "Disney Advertising National Sales",
      lastUpdated: "Jul 29, 2026",
      version: 1,
      season: "2026-2027",
      cardRowCount: 1,
      syntheticDemoData: true
    };
  }

  function getFile(cardId) {
    if (!isEnabled() || cardId !== CARD_ID) return null;
    return clone(buildFile());
  }

  function reset() {
    try {
      var files = JSON.parse(window.localStorage.getItem(FILE_STORAGE_KEY) || "{}");
      delete files[CARD_ID];
      window.localStorage.setItem(FILE_STORAGE_KEY, JSON.stringify(files));
    } catch (_) {
      window.localStorage.removeItem(FILE_STORAGE_KEY);
    }
    try {
      var quickEdit = JSON.parse(window.localStorage.getItem(QUICK_EDIT_STORAGE_KEY) || "{}");
      delete quickEdit[LIST_ID];
      window.localStorage.setItem(QUICK_EDIT_STORAGE_KEY, JSON.stringify(quickEdit));
    } catch (_) {
      window.localStorage.removeItem(QUICK_EDIT_STORAGE_KEY);
    }
  }

  window.RCMDemoRateCard = Object.freeze({
    key: DEMO_KEY,
    cardId: CARD_ID,
    listId: LIST_ID,
    isEnabled: isEnabled,
    getListRecord: getListRecord,
    getFile: getFile,
    reset: reset
  });
})();
