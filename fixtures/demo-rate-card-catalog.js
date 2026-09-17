/*
 * Deterministic synthetic Rate Card catalog.
 * Builds coherent CARD, LINE, and PREM records for every list record.
 *
 * Everything in this file is representative demo data. The advertiser
 * names are recognizable brands so the prototype reads like a real
 * pricing book to Ad Sales, but no rate, condition, or relationship
 * here describes an actual Disney agreement with any of them.
 *
 * A LINE is a pricing rule, not a media plan row: the rate follows from
 * the combination of advertiser, Ad Type, Base Offering, Cost Method,
 * and Line Condition, so two rows only differ in price when something
 * about the rule differs.
 */
(function () {
  "use strict";

  var LINE_COUNTS = [1, 2, 3, 5, 8, 12, 20, 35, 60, 0];

  /* Canonical advertiser roster. One ID per advertiser, reused
   * everywhere the advertiser appears (fixtures, dropdowns, Details
   * panel, search, tests), so a name never travels with two IDs and an
   * ID never travels with two names. */
  var ADVERTISERS = [
    { key: "COKE",      id: "ADV-1048-01", name: "The Coca-Cola Company",       category: "Beverages" },
    { key: "FORD",      id: "ADV-1172-01", name: "Ford Motor Company",          category: "Automotive" },
    { key: "LOREAL",    id: "ADV-1236-01", name: "L\u2019Or\u00e9al USA",       category: "Beauty and personal care" },
    { key: "PG",        id: "ADV-1014-01", name: "Procter & Gamble",            category: "Consumer packaged goods" },
    { key: "UNILEVER",  id: "ADV-1087-01", name: "Unilever",                    category: "Consumer packaged goods" },
    { key: "VERIZON",   id: "ADV-1321-01", name: "Verizon",                     category: "Telecommunications" },
    { key: "CAPONE",    id: "ADV-1459-01", name: "Capital One",                 category: "Financial services" },
    { key: "MCDONALDS", id: "ADV-1128-01", name: "McDonald\u2019s USA",         category: "Quick-service restaurants" },
    { key: "NESTLE",    id: "ADV-1264-01", name: "Nestl\u00e9 USA",             category: "Consumer packaged goods" },
    { key: "GOOGLE",    id: "ADV-1383-01", name: "Google",                      category: "Technology" },
    { key: "TARGET",    id: "ADV-1195-01", name: "Target",                      category: "Retail" },
    { key: "JNJ",       id: "ADV-1076-01", name: "Johnson & Johnson",           category: "Health and personal care" },
    { key: "UNITED",    id: "ADV-1512-01", name: "United Airlines",             category: "Travel" },
    { key: "SAMSUNG",   id: "ADV-1427-01", name: "Samsung Electronics America", category: "Consumer electronics" },
    { key: "HOMEDEPOT", id: "ADV-1153-01", name: "The Home Depot",              category: "Home improvement retail" }
  ];

  var ADVERTISER_BY_KEY = {};
  ADVERTISERS.forEach(function (advertiser) {
    ADVERTISER_BY_KEY[advertiser.key] = advertiser;
  });

  /* Buying entities that buy on behalf of many clients. A card held by
   * one of these prices a book of advertisers, which is why an agency
   * card's rows carry the whole roster. "Disney Planning" is the house
   * planning team and behaves the same way. */
  var AGENCIES = {};
  [
    "WPP", "GroupM", "Mindshare", "Wavemaker", "EssenceMediacom",
    "Omnicom", "OMD", "PHD", "Hearts & Science",
    "IPG", "UM", "Initiative", "Publicis", "Dentsu", "Carat", "iProspect",
    "Havas", "Horizon", "Stagwell", "Assembly", "Crossmedia", "Wpromote",
    "Disney Planning"
  ].forEach(function (name) { AGENCIES[name] = true; });

  /* Advertisers that hold their own rate card, or that an agency card
   * names as its single client ("Dentsu / Toyota"). A client card prices
   * that client's inventory and nobody else's, so the buying entity
   * decides which advertiser its rows can carry. Entities already on the
   * roster reuse their roster identity; the rest carry one more stable
   * ADV id in the same format. */
  var CLIENT_ADVERTISERS = [
    { entity: "Coca-Cola",      key: "COKE" },
    { entity: "Ford",           key: "FORD" },
    { entity: "L\u2019Or\u00e9al", key: "LOREAL" },
    { entity: "L\u2019Or\u00e9al UK", key: "LOREAL" },
    { entity: "P&G",            key: "PG" },
    { entity: "Unilever",       key: "UNILEVER" },
    { entity: "Verizon",        key: "VERIZON" },
    { entity: "Capital One",    key: "CAPONE" },
    { entity: "McDonalds",      key: "MCDONALDS" },
    { entity: "Target",         key: "TARGET" },
    { entity: "Samsung",        key: "SAMSUNG" },
    { entity: "Mondelez",       id: "ADV-1029-01", name: "Mondelez International",     category: "Consumer packaged goods" },
    { entity: "PepsiCo",        id: "ADV-1052-01", name: "PepsiCo",                    category: "Beverages" },
    { entity: "Pepsi",          id: "ADV-1052-01", name: "PepsiCo",                    category: "Beverages" },
    { entity: "Diageo",         id: "ADV-1063-01", name: "Diageo North America",       category: "Beverages" },
    { entity: "AB InBev",       id: "ADV-1071-01", name: "Anheuser-Busch InBev",       category: "Beverages" },
    { entity: "Pfizer",         id: "ADV-1091-01", name: "Pfizer",                     category: "Health and personal care" },
    { entity: "General Motors", id: "ADV-1167-01", name: "General Motors",             category: "Automotive" },
    { entity: "Honda",          id: "ADV-1178-01", name: "American Honda Motor Co.",   category: "Automotive" },
    { entity: "Toyota",         id: "ADV-1183-01", name: "Toyota Motor North America", category: "Automotive" },
    { entity: "Lululemon",      id: "ADV-1206-01", name: "Lululemon Athletica",        category: "Apparel and footwear" },
    { entity: "Amazon",         id: "ADV-1218-01", name: "Amazon",                     category: "Retail" },
    { entity: "Nike",           id: "ADV-1229-01", name: "Nike",                       category: "Apparel and footwear" },
    { entity: "AT&T",           id: "ADV-1312-01", name: "AT&T",                       category: "Telecommunications" },
    { entity: "T-Mobile",       id: "ADV-1338-01", name: "T-Mobile USA",               category: "Telecommunications" },
    { entity: "Microsoft",      id: "ADV-1345-01", name: "Microsoft Corporation",      category: "Technology" },
    { entity: "JPMorgan Chase", id: "ADV-1446-01", name: "JPMorgan Chase",             category: "Financial services" },
    { entity: "Mastercard",     id: "ADV-1452-01", name: "Mastercard",                 category: "Financial services" },
    { entity: "American Express", id: "ADV-1465-01", name: "American Express",         category: "Financial services" },
    { entity: "State Farm",     id: "ADV-1468-01", name: "State Farm Insurance",       category: "Financial services" },
    { entity: "Visa",           id: "ADV-1471-01", name: "Visa Inc.",                  category: "Financial services" },
    { entity: "Progressive",    id: "ADV-1483-01", name: "Progressive Insurance",      category: "Financial services" },
    { entity: "Marriott",       id: "ADV-1527-01", name: "Marriott International",     category: "Travel" },
    { entity: "Expedia",        id: "ADV-1534-01", name: "Expedia Group",              category: "Travel" },
    { entity: "Carnival",       id: "ADV-1541-01", name: "Carnival Cruise Line",       category: "Travel" },
    { entity: "Airbnb",         id: "ADV-1556-01", name: "Airbnb",                     category: "Travel" }
  ];

  var ADVERTISER_BY_ENTITY = {};
  CLIENT_ADVERTISERS.forEach(function (entry) {
    var roster = entry.key ? ADVERTISER_BY_KEY[entry.key] : null;
    ADVERTISER_BY_ENTITY[entry.entity] = roster || {
      key: entry.entity,
      id: entry.id,
      name: entry.name,
      category: entry.category
    };
  });

  /* "Dentsu / Toyota" is Dentsu buying for Toyota, so the client is the
   * last segment. A plain entity is either an agency or the client
   * itself. */
  function clientFor(record) {
    var entity = text(record && record.buyingEntity);
    if (!entity) return null;
    var segments = entity.split("/").map(text);
    var last = segments[segments.length - 1];
    return ADVERTISER_BY_ENTITY[last] || null;
  }

  function advertiserPoolFor(record) {
    var client = clientFor(record);
    return client ? [client] : ADVERTISERS;
  }

  /* Base Offering vocabulary with the CPM band each offering prices in.
   * `floor` is the broad, untargeted rate for the offering; conditions
   * and Ad Type lift the rate from there. The streaming five are the
   * sales-facing package names; the four networks below them serve the
   * addressable book, which sells linear inventory by network. */
  var OFFERINGS = {
    "Hulu Select":                  { floor: 32, ceiling: 38 },
    "Disney+ Select":               { floor: 34, ceiling: 40 },
    "Disney Streaming Bundle":      { floor: 37, ceiling: 43 },
    "ESPN Streaming Sports":        { floor: 44, ceiling: 55 },
    "Disney Streaming Live Events": { floor: 52, ceiling: 68 },
    "ABC":                          { floor: 34, ceiling: 40 },
    "FX":                           { floor: 33, ceiling: 39 },
    "Freeform":                     { floor: 30, ceiling: 36 },
    "National Geographic":          { floor: 33, ceiling: 39 }
  };

  /* Ad Type carries the ad format. Connected TV and live formats cost
   * more to deliver than a standard in-stream spot, so each format
   * carries its own lift over the offering's broad rate. */
  var AD_TYPE_LIFT = {
    "Standard Video":     0,
    "Pause Ad":           0.75,
    "Sports Video":       2,
    "Connected TV Video": 3,
    "Live Event Video":   3.25
  };

  /* Line Condition vocabulary. One readable business rule per line,
   * written as "Category: Dimension to Value", with the lift the rule
   * adds to the offering's broad rate. Narrow, high-intent targeting
   * costs more than a broad demographic or national buy. */
  var C = {
    none:      "No additional targeting",
    a1849:     "DAR Demo: A18-49",
    a2554:     "DAR Demo: A25-54",
    national:  "Targeting: Longform Video Line",
    northeast: "Targeting: Shortform Video Line",
    ctv:       "Targeting: Livestreaming Line",
    auth:      "Format: Premier Product",
    streamers: "Format: Preemptible",
    nfl:       "Targeting: NFL",
    sports:    "Targeting: Football",
    live:      "Targeting: NBA",
    series:    "Format: Sponsorship Product",
    holiday:   "Format: Blitz Product",
    auto:      "DAR Demo: M25-54",
    finance:   "DAR Demo: A35-64",
    beauty:    "DAR Demo: F18-49",
    tech:      "DAR Demo: M18-34",
    travel:    "DAR Demo: A25-49",
    home:      "DAR Demo: A35UP",
    grocery:   "DAR Demo: F25-54",
    household: "DAR Demo: F35-64",
    dining:    "DAR Demo: A18-34",
    retail:    "DAR Demo: A21-49",
    wellness:  "DAR Demo: F18-34",
    wireless:  "DAR Demo: M18-49"
  };

  /* Triggers a premium can fire on that a LINE cannot be targeted by.
   *
   * A LINE is targeted by who is watching and where, so C above is the
   * whole of its vocabulary. A premium also prices how the ad is
   * delivered and when it was committed, which are properties of the
   * sale rather than of the audience: pod position and ad length are
   * decided in trafficking, and the early-commitment window is decided
   * at the negotiating table. Keeping them in their own map is what
   * stops "Format: Pod Position" from ever being offered as line
   * targeting, while still publishing them as canonical values that
   * fixtures and audits both read from one place instead of inventing
   * their own strings. */
  var PC = {
    championship: "Targeting: Livestreaming Line",
    topDma:       "Targeting: Geo",
    liveDelivery: "Targeting: Longform Video Line",
    pauseAd:      "Format: Premium Slate",
    limitedAds:   "Format: Sponsorship Product",
    shortForm:    "Duration: <= :10",
    longForm:     "Duration: :31-60",
    firstPod:     "Format: Sequential",
    earlyUpfront: "Targeting: Daypart Targeting",
    syndicated:   "Targeting: Syndicated Audience Data",
    disneySelect: "Targeting: Disney Select Audience Data",
    nonGuaranteed:"Targeting: Non-Guaranteed Audience",
    platform:     "Targeting: Platform / Device",
    splash:       "Format: Splash",
    videoPlus:    "Format: Video Plus",
    spanish:      "Targeting: Spanish Language Content",
    magicWords:   "Targeting: Standard Magic Words"
  };

  /* A LINE carries at most one optional condition, so "no additional
   * targeting" is the absence of a condition rather than a condition
   * whose value happens to say so. C.none stays in the pools because it
   * is how the rate model expresses an unconditioned rule (zero lift),
   * and this is the one place a rule turns into a stored record, so it
   * is where the sentinel becomes an empty field. Every surface then
   * shows one thing for "no condition" instead of three.
   *
   * Rate-neutral by construction: cpmFor() looks the condition up in
   * CONDITION_LIFT and falls back to 0, which is exactly the lift
   * C.none carries. */
  function lineCondition(value) {
    return value === C.none ? "" : text(value);
  }

  var CONDITION_LIFT = {};
  CONDITION_LIFT[C.none] = 0;
  CONDITION_LIFT[C.ctv] = 1.75;
  CONDITION_LIFT[C.a2554] = 2;
  CONDITION_LIFT[C.auth] = 2;
  CONDITION_LIFT[C.a1849] = 2.25;
  CONDITION_LIFT[C.national] = 2.5;
  CONDITION_LIFT[C.northeast] = 3;
  CONDITION_LIFT[C.household] = 3;
  CONDITION_LIFT[C.grocery] = 3.25;
  CONDITION_LIFT[C.retail] = 3.25;
  CONDITION_LIFT[C.streamers] = 3.25;
  CONDITION_LIFT[C.sports] = 3.5;
  CONDITION_LIFT[C.dining] = 3.5;
  CONDITION_LIFT[C.wellness] = 3.5;
  CONDITION_LIFT[C.holiday] = 3.5;
  CONDITION_LIFT[C.beauty] = 3.75;
  CONDITION_LIFT[C.series] = 3.75;
  CONDITION_LIFT[C.live] = 3.75;
  CONDITION_LIFT[C.nfl] = 4;
  CONDITION_LIFT[C.auto] = 4.5;
  CONDITION_LIFT[C.travel] = 4.5;
  CONDITION_LIFT[C.wireless] = 4.75;
  CONDITION_LIFT[C.tech] = 5;
  CONDITION_LIFT[C.finance] = 5.25;
  /* Home improvement clears at a lower premium than the other intent
   * segments: it is a seasonal, high-supply segment rather than a
   * scarce one, so its rules land just above the broad rate. */
  CONDITION_LIFT[C.home] = 1.75;

  /* The purchase-intent rule each advertiser's category buys against.
   * Rules are written for the advertiser's own category, so a beauty
   * book never prices auto intenders. */
  var INTENT_BY_CATEGORY = {
    "Beverages": C.grocery,
    "Automotive": C.auto,
    "Beauty and personal care": C.beauty,
    "Consumer packaged goods": C.household,
    "Telecommunications": C.wireless,
    "Financial services": C.finance,
    "Quick-service restaurants": C.dining,
    "Technology": C.tech,
    "Retail": C.retail,
    "Health and personal care": C.wellness,
    "Travel": C.travel,
    "Consumer electronics": C.tech,
    "Home improvement retail": C.home,
    "Apparel and footwear": C.retail
  };

  /* Every value that is somebody's purchase-intent segment. A rule may
   * only carry one of these when it belongs to that advertiser's own
   * category, which is what stops a telco book pricing grocery
   * shoppers. */
  var INTENT_CONDITIONS = {};
  Object.keys(INTENT_BY_CATEGORY).forEach(function (category) {
    INTENT_CONDITIONS[INTENT_BY_CATEGORY[category]] = true;
  });

  var GENERAL_CONDITIONS = [
    C.none, C.a1849, C.a2554, C.national, C.northeast,
    C.ctv, C.auth, C.streamers, C.series
  ];
  /* A sports book sells its own fan and genre targeting, and the
   * demographic, coverage and household guarantees any book sells. It
   * does not sell purchase intent, which is bought on-demand. */
  var SPORTS_CONDITIONS = [
    C.nfl, C.sports, C.live, C.a2554, C.national,
    C.a1849, C.northeast, C.auth, C.streamers
  ];

  var DENTSU_ADDRESSABLE_CARD_ID = "RC-DAS-DENTSU-ADDR-SC-2526";
  var WPP_UPFRONT_VIDEO_CARD_ID = "RC-DAS-WPP-VIDEO-UF-2627";

  var DENTSU_ADDRESSABLE_OFFERINGS = [
    ["Hulu Select", 14],
    ["Disney+ Select", 12],
    ["ESPN Streaming Sports", 10],
    ["ABC", 6],
    ["FX", 2],
    ["Freeform", 2],
    ["National Geographic", 2]
  ];

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function text(value) {
    return String(value == null ? "" : value).trim();
  }

  function hash(value) {
    var result = 2166136261;
    var source = text(value);
    for (var index = 0; index < source.length; index += 1) {
      result ^= source.charCodeAt(index);
      result = Math.imul(result, 16777619);
    }
    return result >>> 0;
  }

  function pad(value, length) {
    return String(value).padStart(length, "0");
  }

  function recordNumber(record) {
    var parsed = Number.parseInt(record && record.id, 10);
    return Number.isFinite(parsed) && parsed > 0
      ? parsed
      : (hash(record && record.rateCardId) % 1000) + 1;
  }

  function seasonFor(record) {
    var source = [
      record && record.dealSeason,
      record && record.season,
      record && record.name,
      record && record.rateCardId
    ].join(" ");
    var full = /20(\d{2})[- ]20(\d{2})/.exec(source);
    if (full) return "20" + full[1] + "-20" + full[2];
    var short = /(?:^|\D)(\d{2})-(\d{2})(?:\D|$)/.exec(source);
    if (short) return "20" + short[1] + "-20" + short[2];
    return "2025-2026";
  }

  function cardDates(record, season) {
    var years = season.split("-").map(Number);
    var startYear = years[0] || 2025;
    var endYear = years[1] || startYear + 1;
    if (record && record.marketplace === "Multi-Year") endYear += 1;
    return {
      start: startYear + "-10-01",
      end: endYear + "-09-30"
    };
  }

  function lineCount(record) {
    if (text(record && record.rateCardId) === WPP_UPFRONT_VIDEO_CARD_ID) {
      return WPP_UPFRONT_ROWS.length;
    }
    return LINE_COUNTS[(recordNumber(record) - 1) % LINE_COUNTS.length];
  }

  /* One rate model for every card. Sales-friendly quarter-dollar
   * increments fall out of the lift table, so no row needs a rounding
   * pass and no two rows differ in price without differing in rule. */
  function cpmFor(offering, adType, condition) {
    var band = OFFERINGS[offering] || OFFERINGS["Disney+ Select"];
    var rate = band.floor
      + (AD_TYPE_LIFT[adType] || 0)
      + (CONDITION_LIFT[condition] || 0);
    return Number(rate.toFixed(2));
  }

  /* A rule is written in the run-up to the season it prices and
   * maintained through it, so a 2023-2024 book carries 2023 dates rather
   * than whatever year the fixture happened to be authored in. Created
   * lands 110 to 150 days before the season opens, updated 30 to 100
   * days before, which keeps every record's history in order. */
  function scheduleDates(card, index, spread) {
    var day = 24 * 3600 * 1000;
    var start = Date.parse(text(card && card.effectiveStart) + "T14:00:00.000Z");
    if (!Number.isFinite(start)) start = Date.parse("2026-10-01T14:00:00.000Z");
    return {
      createdAt: new Date(start - (150 - ((index * 7) % 40)) * day).toISOString(),
      updatedAt: new Date(start - (100 - ((index * (spread || 3)) % 70)) * day).toISOString()
    };
  }

  /* ------------------------------------------------------------------
   * WPP - Streaming Video Upfront 2026-2027 (the sales demo card)
   *
   * Hand-authored so a salesperson reads a real book: 80 negotiated
   * pricing rules across 15 advertisers, sized the way real books are
   * (one advertiser carries a single rule, the largest carry nine and
   * ten), with no advertiser's rows sitting in one alphabetical block.
   *
   * Rows are authored newest first. The ten most recently maintained
   * rules lead the default Updated date sort, so the opening screen is
   * curated rather than whatever the generator happened to emit.
   * Columns: advertiser key, Base Offering, Ad Type, Line Condition,
   * updated date. The rate is derived, never typed.
   * ------------------------------------------------------------------ */
  var HS = "Hulu Select";
  var DS = "Disney+ Select";
  var BUNDLE = "Disney Streaming Bundle";
  var ESPN = "ESPN Streaming Sports";
  var LIVE = "Disney Streaming Live Events";
  var STD = "Standard Video";
  var CTV = "Connected TV Video";
  var SPORT = "Sports Video";
  var LIVEV = "Live Event Video";
  var PAUSE = "Pause Ad";

  var WPP_UPFRONT_ROWS = [
    // The curated opening screen, newest first.
    ["FORD",      DS,     STD,   C.auto,      "2026-08-21"],
    ["COKE",      HS,     STD,   C.a1849,     "2026-08-18"],
    ["VERIZON",   BUNDLE, CTV,   C.ctv,       "2026-08-14"],
    ["PG",        DS,     STD,   C.auth,      "2026-08-11"],
    ["CAPONE",    HS,     STD,   C.finance,   "2026-08-07"],
    /* One rule on the opening screen is priced at the broad rate with no
     * additional targeting. Every book has them, and putting one where a
     * reader lands is what shows that the Line condition column is
     * optional rather than leaving it looking mandatory for ten rows. */
    ["UNILEVER",  HS,     STD,   C.none,      "2026-08-06"],
    ["MCDONALDS", BUNDLE, STD,   C.national,  "2026-08-04"],
    ["LOREAL",    HS,     STD,   C.beauty,    "2026-07-29"],
    ["SAMSUNG",   DS,     CTV,   C.tech,      "2026-07-24"],
    ["UNITED",    HS,     STD,   C.travel,    "2026-07-17"],
    ["HOMEDEPOT", BUNDLE, STD,   C.home,      "2026-07-09"],

    // Early July: the bulk of the book was reviewed ahead of publish.
    ["PG",        HS,     STD,   C.none,      "2026-07-08"],
    ["COKE",      DS,     STD,   C.grocery,   "2026-07-08"],
    ["VERIZON",   HS,     STD,   C.wireless,  "2026-07-08"],
    ["TARGET",    HS,     STD,   C.retail,    "2026-07-08"],
    ["FORD",      HS,     STD,   C.auto,      "2026-07-08"],
    ["NESTLE",    HS,     STD,   C.grocery,   "2026-07-08"],

    ["SAMSUNG",   HS,     STD,   C.tech,      "2026-07-07"],
    ["MCDONALDS", HS,     STD,   C.dining,    "2026-07-07"],
    ["LOREAL",    DS,     STD,   C.beauty,    "2026-07-07"],
    ["CAPONE",    DS,     STD,   C.finance,   "2026-07-07"],
    ["JNJ",       HS,     STD,   C.wellness,  "2026-07-07"],
    ["PG",        HS,     STD,   C.a2554,     "2026-07-07"],
    ["COKE",      BUNDLE, STD,   C.a1849,     "2026-07-07"],

    ["FORD",      BUNDLE, STD,   C.auto,      "2026-07-06"],
    ["HOMEDEPOT", HS,     STD,   C.home,      "2026-07-06"],
    ["UNITED",    DS,     STD,   C.travel,    "2026-07-06"],
    ["GOOGLE",    BUNDLE, STD,   C.streamers, "2026-07-06"],
    ["VERIZON",   DS,     STD,   C.wireless,  "2026-07-06"],
    ["SAMSUNG",   BUNDLE, CTV,   C.tech,      "2026-07-06"],
    ["TARGET",    DS,     STD,   C.retail,    "2026-07-06"],

    /* The sports rules are spread through the book rather than filed in
     * one block: four rows priced alike, one after another, read as
     * generated data even when each belongs to a different advertiser. */
    ["COKE",      ESPN,   SPORT, C.nfl,       "2026-07-03"],
    ["UNILEVER",  HS,     STD,   C.household, "2026-07-03"],
    ["FORD",      ESPN,   SPORT, C.nfl,       "2026-07-03"],
    ["MCDONALDS", DS,     STD,   C.dining,    "2026-07-03"],
    ["CAPONE",    ESPN,   SPORT, C.nfl,       "2026-07-03"],
    ["PG",        DS,     STD,   C.a1849,     "2026-07-03"],
    ["VERIZON",   ESPN,   SPORT, C.nfl,       "2026-07-03"],

    ["LOREAL",    BUNDLE, STD,   C.beauty,    "2026-07-02"],
    ["MCDONALDS", ESPN,   SPORT, C.sports,    "2026-07-02"],
    ["PG",        DS,     PAUSE, C.household, "2026-07-02"],
    ["COKE",      ESPN,   SPORT, C.sports,    "2026-07-02"],
    ["SAMSUNG",   DS,     STD,   C.tech,      "2026-07-02"],
    ["FORD",      ESPN,   SPORT, C.auto,      "2026-07-02"],
    ["NESTLE",    DS,     STD,   C.household, "2026-07-02"],

    ["UNILEVER",  DS,     STD,   C.household, "2026-07-01"],
    ["HOMEDEPOT", DS,     STD,   C.home,      "2026-07-01"],
    ["JNJ",       DS,     STD,   C.a2554,     "2026-07-01"],
    ["VERIZON",   DS,     CTV,   C.ctv,       "2026-07-01"],
    ["TARGET",    BUNDLE, STD,   C.national,  "2026-07-01"],
    ["PG",        BUNDLE, STD,   C.household, "2026-07-01"],
    ["COKE",      LIVE,   LIVEV, C.live,      "2026-07-01"],

    // June: the negotiated core of the book.
    ["PG",        BUNDLE, STD,   C.national,  "2026-06-26"],
    ["COKE",      HS,     PAUSE, C.grocery,   "2026-06-26"],
    ["FORD",      DS,     CTV,   C.auto,      "2026-06-26"],

    ["VERIZON",   BUNDLE, STD,   C.none,      "2026-06-24"],
    ["SAMSUNG",   DS,     CTV,   C.ctv,       "2026-06-24"],
    ["UNILEVER",  DS,     STD,   C.a2554,     "2026-06-24"],

    ["MCDONALDS", BUNDLE, STD,   C.a1849,     "2026-06-19"],
    ["LOREAL",    HS,     STD,   C.a1849,     "2026-06-19"],
    ["CAPONE",    BUNDLE, STD,   C.finance,   "2026-06-19"],

    ["TARGET",    HS,     STD,   C.holiday,   "2026-06-17"],
    ["HOMEDEPOT", BUNDLE, STD,   C.northeast, "2026-06-17"],
    ["NESTLE",    BUNDLE, STD,   C.a1849,     "2026-06-17"],

    ["UNITED",    BUNDLE, CTV,   C.travel,    "2026-06-12"],
    ["PG",        HS,     STD,   C.household, "2026-06-12"],

    ["COKE",      DS,     CTV,   C.streamers, "2026-06-10"],
    ["FORD",      DS,     STD,   C.none,      "2026-06-10"],

    ["VERIZON",   BUNDLE, CTV,   C.auth,      "2026-06-05"],
    ["SAMSUNG",   LIVE,   LIVEV, C.tech,      "2026-06-05"],

    ["UNILEVER",  BUNDLE, PAUSE, C.household, "2026-06-03"],
    ["MCDONALDS", LIVE,   LIVEV, C.live,      "2026-06-03"],

    // May: the rules carried forward from the opening proposal.
    ["LOREAL",    DS,     PAUSE, C.series,    "2026-05-27"],
    ["CAPONE",    HS,     STD,   C.a2554,     "2026-05-27"],

    ["PG",        DS,     CTV,   C.auth,      "2026-05-22"],
    ["COKE",      HS,     STD,   C.none,      "2026-05-22"],

    ["FORD",      LIVE,   LIVEV, C.nfl,       "2026-05-15"],
    ["SAMSUNG",   HS,     CTV,   C.streamers, "2026-05-15"],

    ["UNILEVER",  HS,     CTV,   C.auth,      "2026-05-08"],
    ["PG",        BUNDLE, STD,   C.a2554,     "2026-05-08"]
  ];

  /* Rows sharing an updated date are minutes apart in authored order,
   * so the Updated date sort is stable and the curated ten always lead.
   * Late-afternoon UTC keeps the displayed date correct in the Americas. */
  function wppTimestamp(index) {
    var minutes = 17 * 60 - index * 7;
    var slot = ((minutes % 1440) + 1440) % 1440;
    return "T" + pad(Math.floor(slot / 60), 2) + ":" + pad(slot % 60, 2) + ":00.000Z";
  }

  function buildWppUpfrontLines(card) {
    return WPP_UPFRONT_ROWS.map(function (row, index) {
      var advertiser = ADVERTISER_BY_KEY[row[0]];
      return {
        id: card.id + "-LINE-" + pad(index + 1, 3),
        attachToCard: card.id,
        advertiserId: advertiser.id,
        advertiserName: advertiser.name,
        advertiserCategory: advertiser.category,
        adProduct: row[2],
        baseOffering: row[1],
        rateType: "CPM",
        baseRate: cpmFor(row[1], row[2], row[3]),
        currency: "USD",
        condition1: lineCondition(row[3]),
        createdAt: "2026-05-04T14:00:00.000Z",
        updatedAt: row[4] + wppTimestamp(index)
      };
    });
  }

  /* The premium book that sits on top of the negotiated base rates.
   *
   * A premium is a rule about inventory and targeting, not about a media
   * plan row, so each one names the offerings it can price, the trigger
   * that fires it, how it is applied, and where it sits in the stack.
   * Application order groups by kind so the arithmetic is predictable:
   * geo (10) and demographic or first-party audience (20) resolve before
   * third-party audience (30), then format and device (40s), content
   * (50-60), and finally the season and commitment adjustments (70-80)
   * that apply to whatever the earlier rules produced.
   *
   * Scope is the other half of the rule. Most of this book applies to
   * every advertiser buying the card, but a handful were negotiated for
   * one advertiser, so they carry that advertiser's roster identity and
   * the table names them. "card" scope is a deliberate value rather than
   * a blank advertiser field, so nothing has to guess later whether an
   * empty name means card-wide or missing.
   *
   * Columns: id, display name, category, calculation method, value,
   * application order, base offerings, condition, advertiser key or ""
   * for card-wide, effective start, effective end.
   */
  var ALL_ADVERTISERS = "";
  var WPP_UPFRONT_PREMIUMS = [
    ["PRM-WPP-2601", "Auto Intender Audience Premium", "3P Audience",
      "Additive CPM", 3.5, 30, [DS, HS],
      PC.syndicated,
      "FORD", "2026-10-01", "2027-09-30"],
    ["PRM-WPP-2602", "Authenticated Streaming Household Premium", "1P Audience",
      "Additive CPM", 2.5, 20, [DS, HS, BUNDLE],
      PC.disneySelect,
      ALL_ADVERTISERS, "2026-10-01", "2027-09-30"],
    ["PRM-WPP-2603", "Adults 18-49 Targeting Premium", "1P Audience",
      "Additive CPM", 2, 20, [DS, HS],
      PC.nonGuaranteed,
      "COKE", "2026-10-01", "2027-09-30"],
    ["PRM-WPP-2604", "Connected TV Device Premium", "Device Type",
      "Additive CPM", 3, 40, [DS, HS, BUNDLE],
      "Targeting: Livestreaming Line",
      "SAMSUNG", "2026-10-01", "2027-09-30"],
    ["PRM-WPP-2605", "Sports Content Premium", "Content",
      "Percent Adjustment", 15, 50, [ESPN],
      PC.platform,
      ALL_ADVERTISERS, "2026-10-01", "2027-09-30"],
    ["PRM-WPP-2606", "Championship Event Premium", "Content",
      "Percent Adjustment", 20, 60, [ESPN, LIVE],
      PC.championship,
      ALL_ADVERTISERS, "2026-10-01", "2027-09-30"],
    ["PRM-WPP-2607", "Live Event Video Premium", "Format",
      "Additive CPM", 8, 50, [LIVE],
      PC.liveDelivery,
      ALL_ADVERTISERS, "2026-10-01", "2027-09-30"],
    ["PRM-WPP-2608", "Pause Ad Format Premium", "Format",
      "Additive CPM", 5, 40, [HS],
      PC.pauseAd,
      "HOMEDEPOT", "2026-10-01", "2027-09-30"],
    ["PRM-WPP-2609", "Limited Commercial Interruption Premium", "Format",
      "Percent Adjustment", 10, 40, [DS, HS],
      PC.limitedAds,
      ALL_ADVERTISERS, "2026-10-01", "2027-09-30"],
    ["PRM-WPP-2610", "Original Series Adjacency Premium", "Content",
      "Additive CPM", 4, 50, [DS, HS],
      PC.splash,
      ALL_ADVERTISERS, "2026-10-01", "2027-09-30"],
    ["PRM-WPP-2611", "Entertainment Enthusiast Audience Premium", "1P Audience",
      "Additive CPM", 2.75, 20, [DS, HS, BUNDLE],
      PC.videoPlus,
      "LOREAL", "2026-10-01", "2027-09-30"],
    ["PRM-WPP-2612", "NFL Fan Audience Premium", "1P Audience",
      "Additive CPM", 3.25, 30, [ESPN],
      PC.spanish,
      "COKE", "2026-10-01", "2027-09-30"],
    ["PRM-WPP-2613", "Northeast Regional Targeting Premium", "Geo",
      "Additive CPM", 1.5, 10, [DS, HS],
      "Targeting: Shortform Video Line",
      "VERIZON", "2026-10-01", "2027-09-30"],
    ["PRM-WPP-2614", "Top DMA Targeting Premium", "Geo",
      "Additive CPM", 2.25, 10, [HS, BUNDLE],
      PC.topDma,
      "MCDONALDS", "2026-10-01", "2027-09-30"],
    ["PRM-WPP-2615", "Holiday Demand Premium", "Seasonality",
      "Percent Adjustment", 12.5, 70, [DS, HS, BUNDLE],
      PC.magicWords,
      ALL_ADVERTISERS, "2026-11-15", "2027-01-03"],
    ["PRM-WPP-2616", "Upfront Early Commitment Premium", "Commitment",
      "Percent Adjustment", 5, 80, [DS, HS, BUNDLE],
      PC.earlyUpfront,
      ALL_ADVERTISERS, "2026-10-01", "2026-12-31"],
    ["PRM-WPP-2617", "Short-Form Video Premium", "Format",
      "Additive CPM", 2, 40, [HS],
      PC.shortForm,
      "LOREAL", "2026-10-01", "2027-09-30"],
    ["PRM-WPP-2618", "First-Position Pod Premium", "Format",
      "Additive CPM", 4.5, 45, [HS, BUNDLE],
      PC.firstPod,
      "PG", "2026-10-01", "2027-09-30"]
  ];

  /* A premium attaches to the rules it can actually price: the LINE rows
   * on this card whose Base Offering it names, narrowed to one
   * advertiser when the premium was negotiated for one. The attachment
   * is what makes the premium answer "which of my rates does this move?"
   * rather than floating free of the book. */
  function wppPremiumLineIds(lines, offerings, advertiserId, limit) {
    return lines.filter(function (line) {
      if (offerings.indexOf(line.baseOffering) < 0) return false;
      return !advertiserId || line.advertiserId === advertiserId;
    }).slice(0, limit || 4).map(function (line) {
      return line.id;
    });
  }

  /* Premiums are authored after the base rates are agreed and revised
   * through the summer, so they carry later maintenance dates than the
   * rules they sit on, spread over July and August rather than landing
   * on one afternoon. */
  function wppPremiumUpdatedAt(index) {
    var day = 6 + index;
    var month = day > 31 ? "08" : "07";
    if (day > 31) day -= 31;
    return "2026-" + month + "-" + pad(day, 2) + "T"
      + pad(15 + (index % 3), 2) + ":" + pad((index * 13) % 60, 2) + ":00.000Z";
  }

  function buildWppUpfrontPremiums(card, lines) {
    return WPP_UPFRONT_PREMIUMS.map(function (definition, index) {
      var advertiser = definition[8] ? ADVERTISER_BY_KEY[definition[8]] : null;
      return {
        id: definition[0],
        attachToCard: card.id,
        lineItemIds: wppPremiumLineIds(
          lines, definition[6], advertiser && advertiser.id, 4),
        category: definition[2],
        displayName: definition[1],
        calculationMethod: definition[3],
        value: definition[4],
        stackOrder: definition[5],
        baseOffering: definition[6].join(", "),
        condition1: definition[7],
        advertiserScope: advertiser ? "advertiser" : "card",
        advertiserId: advertiser ? advertiser.id : "",
        advertiserName: advertiser ? advertiser.name : "",
        effectiveStart: definition[9],
        effectiveEnd: definition[10],
        createdAt: "2026-05-04T14:00:00.000Z",
        updatedAt: wppPremiumUpdatedAt(index)
      };
    });
  }

  function buildWppUpfrontFile(record, card) {
    var lines = buildWppUpfrontLines(card);
    return {
      schemaVersion: 1,
      status: record.status === "Draft" ? "Draft" : "Published",
      card: card,
      lines: lines,
      premiums: buildWppUpfrontPremiums(card, lines),
      createdAt: "2026-05-04T14:00:00.000Z",
      updatedAt: "2026-08-21T17:00:00.000Z",
      fixtureKey: "wpp-streaming-video-upfront-2026-2027-sales-v3",
      syntheticDemoData: true
    };
  }

  /* ------------------------------------------------------------------
   * Generic catalog cards
   * ------------------------------------------------------------------ */

  function inventoryFor(record, index) {
    var name = text(record && record.name).toLowerCase();
    var sports = /sport|espn|live event|sponsor/.test(name);
    var ctv = /ctv/.test(name);
    var hulu = /hulu/.test(name);
    var disneyPlus = /disney plus|disney\+|dplus/.test(name);
    var streaming = /stream|video/.test(name);
    var options;

    // Ad Type is the ad format. Platform and property signals live in
    // Base Offering, which is also where the rate model reads them from.
    if (sports) {
      options = [
        ["Sports Video", "ESPN Streaming Sports"],
        ["Live Event Video", "Disney Streaming Live Events"],
        ["Standard Video", "ESPN Streaming Sports"]
      ];
    } else if (ctv) {
      options = [
        ["Connected TV Video", "Hulu Select"],
        ["Connected TV Video", "Disney+ Select"]
      ];
    } else if (hulu) {
      options = [
        ["Standard Video", "Hulu Select"],
        ["Pause Ad", "Disney Streaming Bundle"]
      ];
    } else if (disneyPlus) {
      options = [
        ["Standard Video", "Disney+ Select"],
        ["Connected TV Video", "Disney Streaming Bundle"]
      ];
    } else if (streaming) {
      options = [
        ["Standard Video", "Disney+ Select"],
        ["Standard Video", "Hulu Select"],
        ["Pause Ad", "Disney Streaming Bundle"]
      ];
    } else {
      options = [
        ["Standard Video", "Disney+ Select"],
        ["Standard Video", "Hulu Select"],
        ["Sports Video", "ESPN Streaming Sports"],
        ["Connected TV Video", "Disney Streaming Bundle"]
      ];
    }
    return options[index % options.length];
  }

  /* The reserve a card draws on when one book needs more distinct rules
   * than its headline pairings can carry. It stays inside the card's own
   * subject: a live sports book widens into other sports and live
   * inventory, never into a Hulu on-demand rule, and a Hulu book widens
   * into other Hulu formats. The bundle sits in every reserve because
   * every one of these books can sell the bundle. */
  var BUNDLE_FORMATS = [
    ["Standard Video", "Disney Streaming Bundle"],
    ["Connected TV Video", "Disney Streaming Bundle"],
    ["Pause Ad", "Disney Streaming Bundle"]
  ];

  function formatsOn(offering) {
    return [
      ["Standard Video", offering],
      ["Connected TV Video", offering],
      ["Pause Ad", offering]
    ];
  }

  function inventoryReserve(record) {
    var name = text(record && record.name).toLowerCase();
    if (/sport|espn|live event|sponsor/.test(name)) {
      return [
        ["Sports Video", "ESPN Streaming Sports"],
        ["Standard Video", "ESPN Streaming Sports"],
        ["Live Event Video", "Disney Streaming Live Events"],
        ["Standard Video", "Disney Streaming Live Events"]
      ].concat(BUNDLE_FORMATS);
    }
    if (/hulu/.test(name)) return formatsOn("Hulu Select").concat(BUNDLE_FORMATS);
    if (/disney plus|disney\+|dplus/.test(name)) {
      return formatsOn("Disney+ Select").concat(BUNDLE_FORMATS);
    }
    if (/ctv/.test(name)) {
      return formatsOn("Hulu Select")
        .concat(formatsOn("Disney+ Select"))
        .concat(BUNDLE_FORMATS);
    }
    return formatsOn("Disney+ Select")
      .concat(formatsOn("Hulu Select"))
      .concat(BUNDLE_FORMATS);
  }

  function inventoryAlternatives(record) {
    var seen = {};
    var pool = [];
    var add = function (option) {
      var key = option.join("|");
      if (seen[key]) return;
      seen[key] = true;
      pool.push(option);
    };
    for (var index = 0; index < 4; index += 1) add(inventoryFor(record, index));
    inventoryReserve(record).forEach(add);
    return pool;
  }

  function costMethodFor(record, index) {
    var name = text(record && record.name).toLowerCase();
    if (/sport|sponsor|live event/.test(name) && index % 9 === 8) return "Flat Rate";
    if (record && record.marketplace === "Multi-Year" && index % 11 === 10) return "Unit Price";
    return "CPM";
  }

  /* The two negotiated cost methods are quoted off the same CPM the
   * rule would carry, rounded the way sponsorship and unit money is
   * actually quoted. Deriving them means a sponsorship moves for the
   * same reasons a CPM does, instead of two rows with one rule carrying
   * two unrelated prices. */
  function baseRateFor(inventory, method, condition) {
    var cpm = cpmFor(inventory[1], inventory[0], condition);
    if (method === "Flat Rate") return Math.round(cpm * 2000 / 5000) * 5000;
    if (method === "Unit Price") return Math.round(cpm * 20 / 25) * 25;
    return cpm;
  }

  function conditionPool(category, offering) {
    var sportsInventory = /ESPN|Live Events/.test(text(offering));
    var pool = sportsInventory ? SPORTS_CONDITIONS.slice() : GENERAL_CONDITIONS.slice();
    var intent = INTENT_BY_CATEGORY[text(category)];
    if (intent && !sportsInventory) pool = pool.concat([intent, intent]);
    if (/Retail|Beverages|Consumer packaged goods/.test(text(category)) && !sportsInventory) {
      pool = pool.concat([C.holiday]);
    }
    return pool;
  }

  function conditionFor(card, line, index, salt) {
    var pool = conditionPool(line.advertiserCategory, line.baseOffering);
    var seed = [card.id, line.advertiserId, line.baseOffering, index, salt || ""].join(":");
    return pool[hash(seed) % pool.length];
  }

  /* A pricing rule is the advertiser plus what it prices: format,
   * inventory, and targeting. Two rules with the same four values are the
   * same rule, and a book that lists one twice reads as generated data,
   * so each card keeps a register of the rules it has already written.
   *
   * Keyed on the stored condition, not the pool value it was picked from,
   * because a row is compared here both while it is still holding the
   * "no additional targeting" sentinel and after that has become an empty
   * field. Without normalizing, the same rule would register under one
   * key and be looked up under the other, and the card would price it
   * twice. */
  function ruleKey(line) {
    return [line.advertiserId, line.adProduct, line.baseOffering,
      lineCondition(line.condition1)].join("|");
  }

  /* A row is unusable if the card already prices that rule, or if it
   * repeats the row above it down to advertiser, inventory and
   * targeting. Two neighbours that differ only in ad format read as a
   * generated pair even though they are two real rules. */
  function unusable(line, written, previous) {
    if (written[ruleKey(line)]) return true;
    return Boolean(previous)
      && previous.advertiserId === line.advertiserId
      && previous.baseOffering === line.baseOffering
      && lineCondition(previous.condition1) === lineCondition(line.condition1);
  }

  function compatibleLineIds(lines, condition, count) {
    return lines.filter(function (line) {
      return line.condition1 === condition;
    }).slice(0, count).map(function (line) {
      return line.id;
    });
  }

  function buildLines(record, card) {
    var count = lineCount(record);
    var recordSeed = hash(card.id);
    var previous = null;
    var written = {};
    var roster = advertiserPoolFor(record);
    var reserve = inventoryAlternatives(record);
    return Array.from({ length: count }, function (_, index) {
      var advertiser = roster[(recordSeed + index) % roster.length];
      var inventory = inventoryFor(record, index);
      var method = costMethodFor(record, index);
      var dates = scheduleDates(card, index, 3);
      var line = {
        id: card.id + "-LINE-" + pad(index + 1, 3),
        attachToCard: card.id,
        advertiserId: advertiser.id,
        advertiserName: advertiser.name,
        advertiserCategory: advertiser.category,
        adProduct: inventory[0],
        baseOffering: inventory[1],
        rateType: method,
        baseRate: 0,
        currency: "USD",
        condition1: "",
        createdAt: dates.createdAt,
        updatedAt: dates.updatedAt
      };
      line.condition1 = conditionFor(card, line, index, "");
      /* Walk the card's own targeting pool, then the rest of the book's
       * inventory, for a rule this advertiser does not already have and
       * that does not echo the row above. A client card prices one
       * advertiser across many rows, so it leans on the reserve where an
       * agency card rarely needs to. */
      var pool = conditionPool(line.advertiserCategory, line.baseOffering);
      for (var step = 0; step < pool.length && unusable(line, written, previous); step += 1) {
        line.condition1 = pool[(pool.indexOf(line.condition1) + 1 + step) % pool.length];
      }
      for (var shift = 0; shift < reserve.length && unusable(line, written, previous); shift += 1) {
        var alternate = reserve[(index + shift) % reserve.length];
        line.adProduct = alternate[0];
        line.baseOffering = alternate[1];
        inventory = alternate;
        /* Targeting is re-picked from the new inventory's own pool, not
         * carried over: sports targeting belongs to sports inventory, so
         * a rule that moves to Hulu cannot keep pricing NFL fans. */
        var alternatePool = conditionPool(line.advertiserCategory, line.baseOffering);
        line.condition1 = alternatePool[0];
        for (var pick = 1;
             pick < alternatePool.length && unusable(line, written, previous);
             pick += 1) {
          line.condition1 = alternatePool[pick];
        }
      }
      /* Priced against the pool value, because that is what the rate
       * model is keyed on, then stored as a record. The sentinel becomes
       * an empty field only once the loops above have stopped re-picking
       * it, since they look the current value up in the pool. It has to
       * happen before the rule is registered and before this row becomes
       * the one the next is compared against, or two rules that both say
       * "no targeting" would read as different from each other. */
      line.baseRate = baseRateFor(inventory, method, line.condition1);
      line.condition1 = lineCondition(line.condition1);
      written[ruleKey(line)] = true;
      previous = line;
      return line;
    });
  }

  /* ------------------------------------------------------------------
   * Dentsu - Addressable TV Scatter 2025-2026
   * ------------------------------------------------------------------ */

  function dentsuOfferingSchedule() {
    var used = DENTSU_ADDRESSABLE_OFFERINGS.map(function () { return 0; });
    return Array.from({ length: 48 }, function (_, index) {
      var selected = 0;
      var selectedScore = -Infinity;
      DENTSU_ADDRESSABLE_OFFERINGS.forEach(function (offering, offeringIndex) {
        if (used[offeringIndex] >= offering[1]) return;
        var score = offering[1] * (index + 1) / 48 - used[offeringIndex];
        if (score > selectedScore) {
          selected = offeringIndex;
          selectedScore = score;
        }
      });
      used[selected] += 1;
      return DENTSU_ADDRESSABLE_OFFERINGS[selected][0];
    });
  }

  /* The addressable book prices a dozen distinct rules, so its rows
   * cycle through this list. Sports offerings take the sports triggers;
   * everything else takes the general ones, narrowed to the intent
   * segment the advertiser's own category buys. */
  var DENTSU_TRIGGERS = [
    C.a1849, C.a2554, C.auth, C.ctv, C.streamers, C.series,
    C.national, C.northeast, C.holiday, C.household, C.grocery, C.retail
  ];

  function dentsuTriggersFor(advertiser) {
    var own = INTENT_BY_CATEGORY[advertiser.category];
    var pool = DENTSU_TRIGGERS.filter(function (condition) {
      return !INTENT_CONDITIONS[condition] || condition === own;
    });
    if (own && pool.indexOf(own) < 0) pool.push(own);
    return pool;
  }
  /* Sports inventory prices off the sports triggers first, then off the
   * demographic and coverage guarantees that a sports book also sells,
   * which is what keeps two ESPN rules for one advertiser distinct. */
  var DENTSU_SPORTS_TRIGGERS = [C.nfl, C.sports, C.live, C.a2554, C.national];

  function buildDentsuAddressableLines(card) {
    var offerings = dentsuOfferingSchedule();
    var generalIndex = 0;
    var sportsIndex = 0;
    var written = {};
    return offerings.map(function (offering, index) {
      var advertiser = ADVERTISERS[index % ADVERTISERS.length];
      var sportsInventory = offering === "ESPN Streaming Sports";
      var adProduct = sportsInventory ? "Sports Video" : "Standard Video";
      var pool = sportsInventory
        ? DENTSU_SPORTS_TRIGGERS
        : dentsuTriggersFor(advertiser);
      var condition;
      if (sportsInventory) {
        condition = DENTSU_SPORTS_TRIGGERS[sportsIndex % DENTSU_SPORTS_TRIGGERS.length];
        sportsIndex += 1;
      } else if (index % 5 === 4) {
        condition = INTENT_BY_CATEGORY[advertiser.category] || C.none;
      } else {
        condition = pool[generalIndex % pool.length];
        generalIndex += 1;
      }
      var signature = function () {
        return [advertiser.id, adProduct, offering, condition].join("|");
      };
      for (var step = 0; step < pool.length && written[signature()]; step += 1) {
        condition = pool[(pool.indexOf(condition) + 1 + step) % pool.length];
      }
      written[signature()] = true;
      return {
        id: card.id + "-LINE-" + pad(index + 1, 3),
        attachToCard: card.id,
        advertiserId: advertiser.id,
        advertiserName: advertiser.name,
        advertiserCategory: advertiser.category,
        adProduct: adProduct,
        baseOffering: offering,
        rateType: "CPM",
        baseRate: cpmFor(offering, adProduct, condition),
        currency: "USD",
        condition1: lineCondition(condition),
        createdAt: "2026-05-" + pad(1 + (index % 28), 2) + "T14:00:00.000Z",
        updatedAt: "2026-07-" + pad(1 + ((index * 5) % 28), 2) + "T16:30:00.000Z"
      };
    });
  }

  /* The book charges for what it actually prices, so every adjustment
   * here is triggered by a rule that exists in the card rather than by a
   * fixed list that may have drifted from the rows. */
  function buildDentsuAddressablePremiums(card, lines) {
    var seen = {};
    var definitions = [];
    lines.forEach(function (line) {
      var definition = PREMIUM_BY_CONDITION[line.condition1];
      if (!definition || seen[definition[1]] || definitions.length >= 12) return;
      seen[definition[1]] = true;
      definitions.push(definition);
    });
    return definitions.map(function (definition, index) {
      return {
        id: card.id + "-PREM-" + pad(index + 1, 3),
        attachToCard: card.id,
        lineItemIds: compatibleLineIds(lines, definition[4], 2),
        category: definition[0],
        displayName: definition[1],
        calculationMethod: definition[2],
        value: definition[3],
        stackOrder: [10, 20, 30, 40][index % 4],
        condition1: definition[5],
        effectiveStart: "",
        effectiveEnd: "",
        createdAt: "2026-07-01T14:00:00.000Z",
        updatedAt: "2026-07-" + pad(1 + index, 2) + "T17:00:00.000Z"
      };
    });
  }

  function buildDentsuAddressableFile(record, card) {
    card.name = "Dentsu - Addressable TV Scatter 2025-2026";
    card.marketplace = "Scatter";
    card.buyingEntityName = "Dentsu";
    var lines = buildDentsuAddressableLines(card);
    return {
      schemaVersion: 1,
      status: record.status === "Draft" ? "Draft" : "Published",
      card: card,
      lines: lines,
      premiums: buildDentsuAddressablePremiums(card, lines),
      createdAt: "2026-05-01T14:00:00.000Z",
      updatedAt: "2026-07-31T16:00:00.000Z",
      fixtureKey: "dentsu-addressable-tv-scatter-2025-2026-sales-v2",
      syntheticDemoData: true
    };
  }

  /* ------------------------------------------------------------------
   * Premiums
   * ------------------------------------------------------------------ */

  function premiumCount(record, lines) {
    if (!lines.length) return 0;
    var name = text(record && record.name).toLowerCase();
    if (/premium/.test(name)) return Math.min(lines.length * 2, Math.max(12, Math.ceil(lines.length * 0.8)));
    if (/sport|espn|live event|sponsor/.test(name)) return Math.max(3, Math.ceil(lines.length * 0.5));
    switch (recordNumber(record) % 5) {
      case 0: return 0;
      case 1: return Math.min(2, lines.length);
      case 2: return Math.min(4, lines.length);
      case 3: return Math.max(1, Math.ceil(lines.length * 0.25));
      default: return Math.min(8, lines.length);
    }
  }

  /* One adjustment per Line Condition, so a premium's name always says
   * what it charges for and a premium only ever attaches to rules that
   * carry its trigger.
   * Values: [category, display name, calculation method, value, trigger]. */
  var PREMIUM_BY_CONDITION = {};
  [
    ["1P Audience", "Demographic Guarantee Premium", "Additive CPM", 3, C.a1849, PC.nonGuaranteed],
    ["1P Audience", "Adults 25-54 Guarantee Premium", "Additive CPM", 3.5, C.a2554, PC.disneySelect],
    ["Device Type", "Authenticated Streaming Premium", "Percent Adjustment", 8, C.auth, PC.syndicated],
    ["Device Type", "Connected TV Premium", "Percent Adjustment", 10, C.ctv, PC.platform],
    ["3P Audience", "Streaming Enthusiast Premium", "Additive CPM", 4, C.streamers, PC.videoPlus],
    ["Content", "Original Series Premium", "Percent Adjustment", 12, C.series, PC.splash],
    ["Geo", "National Coverage Premium", "Percent Adjustment", 6, C.national, PC.liveDelivery],
    ["Geo", "Regional Geo Premium", "Percent Adjustment", 9, C.northeast, PC.topDma],
    ["Content", "Seasonal Demand Premium", "Percent Adjustment", 18, C.holiday, PC.magicWords],
    ["3P Audience", "Household Intent Premium", "Additive CPM", 4.5, C.household, PC.championship],
    ["3P Audience", "Grocery Intent Premium", "Additive CPM", 5, C.grocery, PC.shortForm],
    ["3P Audience", "Retail Intent Premium", "Additive CPM", 4.75, C.retail, PC.longForm],
    ["3P Audience", "Auto Intent Premium", "Additive CPM", 6, C.auto, PC.firstPod],
    ["3P Audience", "Financial Intent Premium", "Additive CPM", 6.5, C.finance, PC.earlyUpfront],
    ["3P Audience", "Beauty Intent Premium", "Additive CPM", 5.25, C.beauty, PC.pauseAd],
    ["3P Audience", "Technology Intent Premium", "Additive CPM", 6.25, C.tech, PC.limitedAds],
    ["3P Audience", "Travel Intent Premium", "Additive CPM", 5.75, C.travel, PC.spanish],
    ["3P Audience", "Home Improvement Intent Premium", "Additive CPM", 3.75, C.home, PC.magicWords],
    ["3P Audience", "Dining Intent Premium", "Additive CPM", 5, C.dining, PC.shortForm],
    ["3P Audience", "Wellness Intent Premium", "Additive CPM", 5.5, C.wellness, PC.longForm],
    ["3P Audience", "Wireless Intent Premium", "Additive CPM", 6, C.wireless, PC.platform],
    ["Content", "Sports Content Premium", "Percent Adjustment", 15, C.sports, PC.videoPlus],
    ["3P Audience", "Sports Fan Premium", "Additive CPM", 6.75, C.nfl, PC.spanish],
    ["Content", "Live Event Premium", "Percent Adjustment", 20, C.live, PC.liveDelivery]
  ].forEach(function (definition) {
    PREMIUM_BY_CONDITION[definition[4]] = definition;
  });

  /* A card spends its distinct categories first, then its distinct
   * triggers, and repeats a name only when the book genuinely has
   * nothing else to charge for. */
  function buildPremiums(record, card, lines) {
    var count = premiumCount(record, lines);
    if (!count || !lines.length) return [];
    var usedNames = {};
    var usedCategories = {};
    var picks = [];
    [
      function (d) { return usedCategories[d[0]] || usedNames[d[1]]; },
      function (d) { return usedNames[d[1]]; },
      null
    ].forEach(function (reject) {
      for (var i = 0; i < lines.length && picks.length < count; i += 1) {
        var definition = PREMIUM_BY_CONDITION[lines[i].condition1];
        if (!definition) continue;
        if (reject && reject(definition)) continue;
        usedNames[definition[1]] = true;
        usedCategories[definition[0]] = true;
        picks.push({ line: lines[i], definition: definition });
      }
    });
    return picks.map(function (pick, index) {
      var definition = pick.definition;
      /* An adjustment applies to every rule carrying its trigger, not
       * only the rule that introduced it. Capped at three so the
       * attached-rows cell stays legible. */
      var attached = [pick.line.id].concat(
        compatibleLineIds(lines, definition[4], 4).filter(function (id) {
          return id !== pick.line.id;
        })
      ).slice(0, 3);
      var dates = scheduleDates(card, index, 5);
      return {
        id: card.id + "-PREM-" + pad(index + 1, 3),
        attachToCard: card.id,
        lineItemIds: attached,
        /* The rule that introduced the adjustment is the advertiser it
         * was negotiated for, so the premium carries that advertiser's
         * roster identity rather than a name with no ID behind it. */
        advertiserScope: "advertiser",
        advertiserId: pick.line.advertiserId,
        advertiserName: pick.line.advertiserName,
        category: definition[0],
        displayName: definition[1],
        calculationMethod: definition[2],
        value: definition[3],
        stackOrder: index + 1,
        condition1: definition[5],
        effectiveStart: index % 4 === 0 ? card.effectiveStart : "",
        effectiveEnd: index % 4 === 0 ? card.effectiveEnd : "",
        createdAt: dates.createdAt,
        updatedAt: dates.updatedAt
      };
    });
  }

  function buildFile(record) {
    if (!record || !record.rateCardId) return null;
    var season = seasonFor(record);
    var dates = cardDates(record, season);
    var card = {
      id: text(record.rateCardId),
      name: text(record.name) || text(record.rateCardId),
      marketplace: ["Upfront", "Scatter", "Multi-Year"].indexOf(record.marketplace) >= 0
        ? record.marketplace : "Upfront",
      dealSeason: season,
      buyingEntityId: text(record.saleshubId),
      buyingEntityName: text(record.buyingEntity),
      dcmRuleOrder: recordNumber(record),
      effectiveStart: dates.start,
      effectiveEnd: dates.end
    };
    if (card.id === DENTSU_ADDRESSABLE_CARD_ID) {
      return buildDentsuAddressableFile(record, card);
    }
    if (card.id === WPP_UPFRONT_VIDEO_CARD_ID) {
      return buildWppUpfrontFile(record, card);
    }
    var lines = buildLines(record, card);
    var premiums = buildPremiums(record, card, lines);
    return {
      schemaVersion: 1,
      status: record.status === "Draft" ? "Draft" : "Published",
      card: card,
      lines: lines,
      premiums: premiums,
      createdAt: "2026-06-01T14:00:00.000Z",
      updatedAt: "2026-07-31T16:00:00.000Z",
      fixtureKey: "rate-card-catalog-sales-v5",
      syntheticDemoData: true
    };
  }

  function summarize(records) {
    return (records || []).map(function (record) {
      var file = buildFile(record);
      return {
        rateCardId: file.card.id,
        name: file.card.name,
        marketplace: file.card.marketplace,
        dealSeason: file.card.dealSeason,
        lines: file.lines.length,
        premiums: file.premiums.length
      };
    });
  }

  function resetDentsuAddressable() {
    try {
      var files = JSON.parse(window.localStorage.getItem("rate-card-manager.v2.files") || "{}");
      delete files[DENTSU_ADDRESSABLE_CARD_ID];
      window.localStorage.setItem("rate-card-manager.v2.files", JSON.stringify(files));
    } catch (_) {
      window.localStorage.removeItem("rate-card-manager.v2.files");
    }
    try {
      var quickEdit = JSON.parse(
        window.localStorage.getItem("rate-card-manager.quick-edit.v1") || "{}"
      );
      delete quickEdit["1"];
      window.localStorage.setItem(
        "rate-card-manager.quick-edit.v1",
        JSON.stringify(quickEdit)
      );
    } catch (_) {
      window.localStorage.removeItem("rate-card-manager.quick-edit.v1");
    }
  }

  function resetConditionFixtures() {
    try {
      var files = JSON.parse(window.localStorage.getItem("rate-card-manager.v2.files") || "{}");
      Object.keys(files).forEach(function (key) {
        var file = files[key];
        if (file && file.syntheticDemoData === true
            && /^(?:rate-card-catalog|dentsu-addressable-tv-scatter|wpp-streaming-video-upfront)/.test(text(file.fixtureKey))) {
          delete files[key];
        }
      });
      window.localStorage.setItem("rate-card-manager.v2.files", JSON.stringify(files));
      window.localStorage.removeItem("rate-card-manager.quick-edit.v1");
    } catch (_) {
      window.localStorage.removeItem("rate-card-manager.v2.files");
      window.localStorage.removeItem("rate-card-manager.quick-edit.v1");
    }
  }

  window.RCMCatalog = Object.freeze({
    advertisers: clone(ADVERTISERS),
    /* Every advertiser identity the catalog can write, roster plus the
     * clients that hold their own card. One entry per ID. */
    allAdvertisers: function () {
      var seen = {};
      var all = [];
      ADVERTISERS.forEach(function (advertiser) {
        seen[advertiser.id] = true;
        all.push(clone(advertiser));
      });
      Object.keys(ADVERTISER_BY_ENTITY).forEach(function (entity) {
        var advertiser = ADVERTISER_BY_ENTITY[entity];
        if (seen[advertiser.id]) return;
        seen[advertiser.id] = true;
        all.push(clone(advertiser));
      });
      return all;
    },
    /* Who a card is allowed to price. Published so the record audit can
     * hold a client card to its own client instead of guessing from the
     * card name. */
    clientFor: function (record) {
      var client = clientFor(record);
      return client ? clone(client) : null;
    },
    isAgency: function (entity) {
      return Boolean(AGENCIES[text(entity)]);
    },
    conditions: clone(C),
    /* Premium-only triggers, published separately from conditions so a
     * caller has to opt in to them and no LINE picker can reach them. */
    premiumConditions: clone(PC),
    /* Published so every fixture stores "no targeting" the same way,
     * rather than each one deciding whether the sentinel or an empty
     * field is the record. */
    lineCondition: lineCondition,
    /* The purchase-intent segment each category buys against, published
     * so every fixture writes intent rules from one map instead of its
     * own pattern matching. */
    intentByCategory: clone(INTENT_BY_CATEGORY),
    offerings: Object.keys(OFFERINGS),
    adTypes: Object.keys(AD_TYPE_LIFT),
    /* The rate model, published so any fixture that quotes a CPM prices
     * off the same offering floors and lifts, and so the record audit
     * checks rows against the model rather than a second copy of it. */
    expectedRate: cpmFor,
    band: function (offering) {
      return OFFERINGS[offering] ? clone(OFFERINGS[offering]) : null;
    },
    buildFile: function (record) {
      return clone(buildFile(record));
    },
    summarize: function (records) {
      return clone(summarize(records));
    },
    resetDentsuAddressable: resetDentsuAddressable,
    resetConditionFixtures: resetConditionFixtures
  });
})();
