"""Exhaustive record-level QA for every Rate Card LINE and PREM in the app.

This suite is deliberately not a sampling exercise. It builds every Rate
Card file the application can produce (the full catalog plus the opt-in
cross-platform demo card), walks every LINE and every PREM record in
each one, and fails on any record whose fields do not form one
believable pricing rule.

It then drives the rendered WPP sales card through every page of the
Line Items table, opens every row, and compares the Line Details panel
against the row it came from, so record-level data and the UI that shows
it are validated against the same source of truth.

Failures print the record index, advertiser, advertiser ID, the field at
fault, and why it failed. Full per-record verdicts are written to
/tmp/rate-card-record-audit/records.json.

Run with: python3 qa_rate_card_records.py
"""

import json
import os
import re
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import urlopen

import websocket


# Resolved from this file so the suite runs from any checkout.
ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = 8994
DEBUG_PORT = 9294
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
OUT = "/tmp/rate-card-record-audit"
SALES_CARD_ID = "RC-DAS-WPP-VIDEO-UF-2627"
os.makedirs(OUT, exist_ok=True)


class StaticHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0] or "/"
        if path == "/":
            path = "/index.html"
        filename = os.path.join(ROOT, path.lstrip("/"))
        if not os.path.isfile(filename):
            self.send_response(404)
            self.end_headers()
            return
        content_type = {
            ".html": "text/html",
            ".css": "text/css",
            ".js": "application/javascript",
            ".svg": "image/svg+xml",
            ".png": "image/png",
        }.get(os.path.splitext(filename)[1], "text/plain")
        with open(filename, "rb") as handle:
            payload = handle.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_args):
        return


server = ThreadingHTTPServer(("127.0.0.1", PORT), StaticHandler)
threading.Thread(target=server.serve_forever, daemon=True).start()
profile = "/tmp/rate_card_record_audit_profile"
os.makedirs(profile, exist_ok=True)
chrome = subprocess.Popen(
    [
        CHROME,
        f"--remote-debugging-port={DEBUG_PORT}",
        f"--user-data-dir={profile}",
        "--headless=new",
        "--remote-allow-origins=*",
        "--no-first-run",
        "--window-size=1440,960",
        "about:blank",
    ],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
time.sleep(1.2)
tabs = json.loads(urlopen(f"http://127.0.0.1:{DEBUG_PORT}/json").read())
ws_url = next(tab["webSocketDebuggerUrl"] for tab in tabs if tab.get("type") == "page")
ws = websocket.create_connection(ws_url, timeout=60)
message_id = 0
console_messages = []
results = []
failures = []


def send(method, params=None):
    global message_id
    message_id += 1
    expected = message_id
    ws.send(json.dumps({"id": expected, "method": method, "params": params or {}}))
    while True:
        event = json.loads(ws.recv())
        if event.get("method") == "Runtime.exceptionThrown":
            console_messages.append(json.dumps(event)[:400])
        if event.get("id") == expected:
            return event


def evaluate(expression):
    response = send(
        "Runtime.evaluate",
        {"expression": expression, "returnByValue": True, "awaitPromise": True},
    )
    result = response.get("result", {})
    if "exceptionDetails" in result:
        raise RuntimeError(json.dumps(result["exceptionDetails"])[:600])
    return result.get("result", {}).get("value")


def navigate(query, pause=1.2):
    send("Page.navigate", {"url": f"http://127.0.0.1:{PORT}/{query}"})
    time.sleep(pause)


def check(name, condition, detail=""):
    passed = bool(condition)
    results.append({"name": name, "status": "PASS" if passed else "FAIL"})
    print(f"[{'PASS' if passed else 'FAIL'}] {name}" + ("" if passed else f": {detail}"))


def js_array(source, name):
    """Pull one `var NAME = [ {...}, ... ];` literal out of app.js.

    The legacy v1.x create page keeps its LINE catalog in a closure, so
    the only way to audit those records is to read them from source.
    """
    match = re.search(r"(?:var|const|let) %s\s*=\s*\[" % name, source)
    if not match:
        raise AssertionError("%s is no longer declared in app.js" % name)
    start = match.start()
    depth = 0
    for offset in range(source.index("[", start), len(source)):
        if source[offset] == "[":
            depth += 1
        elif source[offset] == "]":
            depth -= 1
            if depth == 0:
                body = source[source.index("[", start): offset + 1]
                break
    records = []
    for block in re.findall(r"\{(.*?)\}", body, re.S):
        record = dict(re.findall(r'(\w+):\s*"((?:[^"\\]|\\.)*)"', block))
        records.append({k: v.encode().decode("unicode_escape") for k, v in record.items()})
    return records


def report_record_failures(label, rows):
    """Print one actionable line per failing record, then assert none."""
    for row in rows[:60]:
        print(
            f"    #{row['index']} {row['advertiserName']} ({row['advertiserId']})"
            f" field={row['field']} :: {row['reason']}"
        )
    if len(rows) > 60:
        print(f"    ... and {len(rows) - 60} more")
    check(label, not rows, f"{len(rows)} failing records")


# Empty is valid: the Line condition is optional and one per rule.
# Conditions now come from the Business Dictionary, whose categories are
# Format, Targeting, Duration and DAR Demo. A record may carry more than
# one, comma separated.
READABLE_CONDITION = re.compile(
    r"^(?:|(?:Format|Targeting|Duration|DAR Demo): [^|,]+"
    r"(?:, (?:Format|Targeting|Duration|DAR Demo): [^|,]+)*)$"
)
PLACEHOLDER_NAME = re.compile(
    r"(test advertiser|sample brand|advertiser \d|company abc|lorem ipsum"
    r"|demo client|acme|placeholder|aurora beauty|bluepeak|brightwave"
    r"|cloudnine|elevate sportswear|northstar)",
    re.I,
)


def audit_legacy_line_catalog(roster):
    """Audit the LINE records the v1.x create page searches over.

    These rows are not generated: they are hand-written records the PREM
    step attaches premiums to, so they get the same field-by-field
    contract the generated book gets, held to the legacy page's own
    Ad Type and Base Offering vocabulary.
    """
    with open(os.path.join(ROOT, "app.js"), encoding="utf-8") as handle:
        source = handle.read()
    lines = js_array(source, "EXISTING_LINE_ITEMS")
    cards = {record.get("name") for record in js_array(source, "RATE_CARDS")}
    enums = {}
    for name in ("AD_TYPE_OPTIONS", "BASE_OFFERING_OPTIONS", "RATE_TYPE_OPTIONS",
                 "CURRENCY_OPTIONS"):
        block = source[source.index("const %s = [" % name):]
        enums[name] = set(re.findall(r'"([^"]+)"', block[: block.index("]")]))
    id_by_name = {a["name"]: a["id"] for a in roster}

    failures = []
    seen_ids = set()
    seen_rules = {}
    for index, line in enumerate(lines, start=1):
        def fail(field, reason):
            failures.append({
                "index": index,
                "advertiserName": line.get("advertiserName", "(missing)"),
                "advertiserId": line.get("advertiserId", "(missing)"),
                "field": field,
                "reason": reason,
            })

        for field in ("id", "name", "advertiserName", "advertiserId", "rateCard",
                      "attachToLine", "adType", "baseOffering", "costMethod",
                      "baseRate", "currency", "lineConditions"):
            if not line.get(field):
                fail(field, "required field is missing or empty")
        if PLACEHOLDER_NAME.search(line.get("advertiserName", "")):
            fail("advertiserName", "reads as a placeholder or retired fixture name")
        if line.get("advertiserName") not in id_by_name:
            fail("advertiserName", "not part of the canonical advertiser roster")
        elif id_by_name[line["advertiserName"]] != line.get("advertiserId"):
            fail("advertiserId", "does not match the ID this advertiser carries elsewhere")
        if line.get("id") in seen_ids:
            fail("id", "duplicate record id")
        seen_ids.add(line.get("id"))
        if line.get("adType") not in enums["AD_TYPE_OPTIONS"]:
            fail("adType", "ad type is not offered by the LINE form")
        if line.get("baseOffering") not in enums["BASE_OFFERING_OPTIONS"]:
            fail("baseOffering", "base offering is not offered by the LINE form")
        if line.get("costMethod") not in enums["RATE_TYPE_OPTIONS"]:
            fail("costMethod", "cost method is not offered by the LINE form")
        if line.get("currency") not in enums["CURRENCY_OPTIONS"]:
            fail("currency", "currency is not offered by the LINE form")
        try:
            rate = float(line.get("baseRate", ""))
        except ValueError:
            rate = -1
        if rate <= 0:
            fail("baseRate", "rate must be a positive number")
        elif line.get("costMethod") == "CPM" and round(rate * 4) != rate * 4:
            fail("baseRate", "CPM is not quoted in quarter-dollar increments")
        elif line.get("costMethod") == "Flat" and rate % 5000:
            fail("baseRate", "flat fee is not a credible rounded sponsorship figure")
        if not READABLE_CONDITION.match(line.get("lineConditions", "")):
            fail("lineConditions", "targeting is not one readable business rule")
        if line.get("rateCard") not in cards:
            fail("rateCard", "attached to a rate card that is not in the list view")
        if line.get("attachToLine") != line.get("rateCard"):
            fail("attachToLine", "attachment disagrees with the record's own rate card")
        label = "%s - %s / %s" % (
            line.get("advertiserName"), line.get("adType"), line.get("baseOffering"))
        if line.get("name") != label:
            fail("name", "display label does not read Advertiser, Ad Type / Base Offering")
        rule = "|".join([line.get("advertiserId", ""), line.get("adType", ""),
                         line.get("baseOffering", ""), line.get("lineConditions", "")])
        if rule in seen_rules:
            fail("*", "exact duplicate of the pricing rule in row %d" % seen_rules[rule])
        seen_rules[rule] = index
    return lines, failures


# ---------------------------------------------------------------------
# The record contract. Every rule below is a business statement about
# what a credible pricing rule looks like, expressed once so the whole
# dataset is held to it.
# ---------------------------------------------------------------------
RECORD_AUDIT = r"""
(() => {
  const CATALOG = window.RCMCatalog;
  const ROSTER = CATALOG.allAdvertisers();
  const C = CATALOG.conditions;
  const nameById = {};
  const idByName = {};
  const categoryByName = {};
  ROSTER.forEach(a => {
    nameById[a.id] = a.name;
    idByName[a.name] = a.id;
    categoryByName[a.name] = a.category;
  });

  const AD_TYPES = ['Standard Video','Connected TV Video','Live Event Video',
    'Sports Video','Pause Ad'];
  const STREAMING = ['Disney+ Select','Hulu Select','Disney Streaming Bundle',
    'ESPN Streaming Sports','Disney Streaming Live Events'];
  const NETWORKS = ['ABC','FX','Freeform','National Geographic'];
  const OFFERINGS = STREAMING.concat(NETWORKS);
  const COST_METHODS = ['CPM','Flat Rate','Unit Price'];
  const CURRENCIES = ['USD'];
  const CALC_METHODS = ['Additive CPM','Flat Fee','Percent Adjustment'];

  // Format is only sold where the inventory supports it. Sports and live
  // formats belong to sports and live inventory; pause belongs to the
  // on-demand streaming packages.
  const OFFERING_BY_AD_TYPE = {
    'Standard Video': OFFERINGS,
    'Connected TV Video': ['Disney+ Select','Hulu Select','Disney Streaming Bundle'],
    'Sports Video': ['ESPN Streaming Sports'],
    'Live Event Video': ['Disney Streaming Live Events'],
    'Pause Ad': ['Disney+ Select','Hulu Select','Disney Streaming Bundle']
  };

  // Sports and live targeting only price against sports and live
  // inventory. Everything else is inventory-neutral.
  const SPORTS_CONDITIONS = [C.nfl, C.sports, C.live];
  const SPORTS_OFFERINGS = ['ESPN Streaming Sports','Disney Streaming Live Events'];

  // A purchase-intent rule is written for the advertiser's own category,
  // so a beauty book never prices auto intenders.
  const INTENT_CATEGORY = {};
  INTENT_CATEGORY[C.auto] = ['Automotive'];
  INTENT_CATEGORY[C.finance] = ['Financial services'];
  INTENT_CATEGORY[C.beauty] = ['Beauty and personal care'];
  INTENT_CATEGORY[C.tech] = ['Technology','Consumer electronics'];
  INTENT_CATEGORY[C.travel] = ['Travel'];
  INTENT_CATEGORY[C.home] = ['Home improvement retail'];
  INTENT_CATEGORY[C.grocery] = ['Beverages','Consumer packaged goods'];
  INTENT_CATEGORY[C.household] = ['Consumer packaged goods','Health and personal care'];
  INTENT_CATEGORY[C.dining] = ['Quick-service restaurants'];
  INTENT_CATEGORY[C.retail] = ['Retail'];
  INTENT_CATEGORY[C.wellness] = ['Health and personal care'];
  INTENT_CATEGORY[C.wireless] = ['Telecommunications'];
  INTENT_CATEGORY[C.retail].push('Apparel and footwear');

  const CONDITIONS = Object.keys(C).map(key => C[key]);
  // A premium fires on line targeting plus the delivery and commitment
  // dimensions only it can price. Both halves come from the catalog, so
  // this stays one vocabulary rather than a second copy that drifts.
  const PREMIUM_ONLY = CATALOG.premiumConditions || {};
  const PREMIUM_TRIGGERS = CONDITIONS.concat(
    Object.keys(PREMIUM_ONLY).map(key => PREMIUM_ONLY[key]));
  // A premium fires on everything a line can be targeted by, plus the
  // delivery and commitment dimensions that only a premium prices. Both
  // halves come from the catalog, so a fixture cannot widen the
  // vocabulary by inventing a string in place.
  const PC = CATALOG.premiumConditions;
  const PREMIUM_CONDITIONS = CONDITIONS.concat(
    Object.keys(PC).map(key => PC[key]));
  // One readable business rule, or nothing at all. "No additional
  // targeting" is how the rate model says a rule has no condition, and a
  // record states that by leaving the field empty, so the sentinel is no
  // longer an accepted stored value.
  const READABLE = /^(?:Format|Targeting|Duration|DAR Demo): [^|,]+(?:, (?:Format|Targeting|Duration|DAR Demo): [^|,]+)*$/;
  // Premium triggers add the two prefixes a line can never carry.
  const PREMIUM_READABLE =
    /^(?:Format|Targeting|Duration|DAR Demo): [^|,]+(?:, (?:Format|Targeting|Duration|DAR Demo): [^|,]+)*$/;
  const PLACEHOLDER = /(test advertiser|sample brand|advertiser \d|company abc|lorem ipsum|demo client|acme|placeholder|foo|bar\b|aurora beauty|bluepeak|brightwave|cloudnine|elevate sportswear|northstar)/i;
  const ADVERTISER_ID = /^ADV-\d{4}-\d{2}$/;
  const PREMIUM_NAME = /^[A-Z][A-Za-z0-9+\-\u2013&' ]+ Premium$/;
  const ISO_DATE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/;
  const CATEGORIES = ['1P Audience','3P Audience','Content','Device Type','Geo',
    'Duration','Format','Seasonality','Commitment'];

  const lineFailures = [];
  const premiumFailures = [];
  const lineRecords = [];
  const premiumRecords = [];
  const globalIdByName = {};
  const globalNameById = {};
  let lineIndex = 0;
  let premiumIndex = 0;

  const records = window.RCMRateCards.getAll().filter(record =>
    !window.RCMDemoRateCard || record.id !== window.RCMDemoRateCard.listId
  );
  const entries = records.map(record => ({ record, file: CATALOG.buildFile(record) }));
  if (window.RCMDemoRateCard && typeof window.RCMDemoRateCard.getFile === 'function') {
    const demo = window.RCMDemoRateCard.getFile(window.RCMDemoRateCard.cardId);
    if (demo) entries.push({ record: null, file: demo });
  }

  // A buying entity is either an agency buying for many clients or the
  // client itself. An unclassified entity means a card nobody can say
  // whose inventory it prices.
  const entityFailures = [];
  entries.forEach(({ record, file }) => {
    if (!record) return;
    const entity = String(record.buyingEntity || '').trim();
    if (!entity) {
      entityFailures.push({ card: file.card.id, entity: '(missing)',
        reason: 'card has no buying entity' });
    } else if (!CATALOG.clientFor(record) && !CATALOG.isAgency(entity.split('/').pop().trim())) {
      entityFailures.push({ card: file.card.id, entity,
        reason: 'buying entity is neither a known agency nor a known advertiser' });
    }
  });

  entries.forEach(({ record, file }) => {
    const card = file.card;
    // A client card prices its own client's inventory. An agency card
    // prices a book of advertisers.
    const client = record ? CATALOG.clientFor(record) : null;
    const lineIds = new Set(file.lines.map(line => line.id));
    const linesById = new Map(file.lines.map(line => [line.id, line]));
    const rulesSeen = new Map();
    const seasonStart = Date.parse(card.effectiveStart);
    const seasonEnd = Date.parse(card.effectiveEnd);
    // A rule is written in the run-up to the season and maintained
    // through it, never after the season it prices has closed.
    const windowStart = seasonStart - 400 * 24 * 3600 * 1000;
    const windowEnd = seasonEnd;

    file.lines.forEach((line, position) => {
      lineIndex += 1;
      const fail = (field, reason) => lineFailures.push({
        index: lineIndex, card: card.id, row: position + 1,
        advertiserName: line.advertiserName || '(missing)',
        advertiserId: line.advertiserId || '(missing)',
        field, reason
      });

      // condition1 is deliberately absent: a LINE carries at most one
      // condition and the field is optional, so an empty one is a real
      // rule priced at the broad rate, not a missing field.
      ['id','attachToCard','advertiserId','advertiserName','adProduct',
       'baseOffering','rateType','currency','createdAt','updatedAt']
        .forEach(field => {
          if (!line[field]) fail(field, 'required field is missing or empty');
        });
      if (!Number.isFinite(line.baseRate)) fail('baseRate', 'rate is not a finite number');
      if (line.attachToCard !== card.id) fail('attachToCard', 'row is attached to another card');

      if (PLACEHOLDER.test(line.advertiserName || '')) {
        fail('advertiserName', 'reads as a placeholder or retired fixture name');
      }
      if (!idByName[line.advertiserName]) {
        fail('advertiserName', 'not part of the canonical advertiser roster');
      }
      if (client && line.advertiserName !== client.name) {
        fail('advertiserName', 'client card for ' + client.name
          + ' prices a rule for another advertiser');
      }
      if (!ADVERTISER_ID.test(line.advertiserId || '')) {
        fail('advertiserId', 'does not match the ADV-####-## format');
      }
      if (idByName[line.advertiserName] && idByName[line.advertiserName] !== line.advertiserId) {
        fail('advertiserId', 'advertiser is using an ID that belongs to a different record');
      }
      if (globalIdByName[line.advertiserName]
          && globalIdByName[line.advertiserName] !== line.advertiserId) {
        fail('advertiserId', 'same advertiser carries two different IDs across the dataset');
      }
      if (globalNameById[line.advertiserId]
          && globalNameById[line.advertiserId] !== line.advertiserName) {
        fail('advertiserId', 'one ID is shared by two different advertisers');
      }
      globalIdByName[line.advertiserName] = line.advertiserId;
      globalNameById[line.advertiserId] = line.advertiserName;

      if (AD_TYPES.indexOf(line.adProduct) < 0) {
        fail('adProduct', 'ad type is outside the controlled format vocabulary');
      }
      if (OFFERINGS.indexOf(line.baseOffering) < 0) {
        fail('baseOffering', 'base offering is outside the controlled vocabulary');
      }
      const allowed = OFFERING_BY_AD_TYPE[line.adProduct];
      if (allowed && allowed.indexOf(line.baseOffering) < 0) {
        fail('adProduct', 'ad type is not sold on this base offering');
      }
      if (COST_METHODS.indexOf(line.rateType) < 0) {
        fail('rateType', 'cost method is not supported');
      }
      if (CURRENCIES.indexOf(line.currency) < 0) {
        fail('currency', 'currency is not USD');
      }

      if (line.rateType === 'CPM') {
        if (!(line.baseRate > 0)) fail('baseRate', 'CPM must be positive');
        if (Math.round(line.baseRate * 100) % 25 !== 0) {
          fail('baseRate', 'CPM is not quoted in quarter-dollar increments');
        }
        const expected = CATALOG.expectedRate(line.baseOffering, line.adProduct, line.condition1);
        if (Number.isFinite(expected) && Math.abs(expected - line.baseRate) > 0.001) {
          fail('baseRate', 'rate does not match the offering, format and targeting model'
            + ' (expected ' + expected.toFixed(2) + ')');
        }
        const band = CATALOG.band(line.baseOffering);
        if (band && (line.baseRate < band.floor || line.baseRate > band.ceiling + 4.5)) {
          fail('baseRate', 'rate falls outside the offering band');
        }
      } else if (line.rateType === 'Flat Rate') {
        if (!(line.baseRate >= 25000) || Math.round(line.baseRate) % 2500 !== 0) {
          fail('baseRate', 'flat rate is not a credible rounded sponsorship figure');
        }
      } else if (line.rateType === 'Unit Price') {
        if (!(line.baseRate >= 100) || Math.round(line.baseRate) % 25 !== 0) {
          fail('baseRate', 'unit price is not quoted in credible increments');
        }
      } else if (!(line.baseRate > 0)) {
        fail('baseRate', 'rate must be positive');
      }

      if (line.condition1) {
        if (!READABLE.test(line.condition1)) {
          fail('condition1', 'targeting is not one readable business rule');
        }
        if (CONDITIONS.indexOf(line.condition1) < 0) {
          fail('condition1', 'targeting is outside the controlled vocabulary');
        }
      }
      if ((line.condition1 || '').length > 140) {
        fail('condition1', 'targeting is longer than the stored maximum');
      }
      if (line.condition2 || line.condition3 || line.condition4) {
        fail('condition1', 'rule stacks more than one targeting condition');
      }
      if (SPORTS_CONDITIONS.indexOf(line.condition1) >= 0
          && SPORTS_OFFERINGS.indexOf(line.baseOffering) < 0) {
        fail('condition1', 'sports or live targeting priced against non-sports inventory');
      }
      const categories = INTENT_CATEGORY[line.condition1];
      if (categories && categories.indexOf(line.advertiserCategory) < 0) {
        fail('condition1', 'purchase-intent rule does not match the advertiser category ('
          + line.advertiserCategory + ')');
      }

      [['createdAt', line.createdAt], ['updatedAt', line.updatedAt]].forEach(pair => {
        if (!ISO_DATE.test(pair[1] || '')) {
          fail(pair[0], 'timestamp is not a valid ISO instant');
          return;
        }
        const stamp = Date.parse(pair[1]);
        if (stamp < windowStart || stamp > windowEnd) {
          fail(pair[0], 'timestamp sits outside the card setup and maintenance window');
        }
      });
      if (ISO_DATE.test(line.createdAt || '') && ISO_DATE.test(line.updatedAt || '')
          && Date.parse(line.updatedAt) < Date.parse(line.createdAt)) {
        fail('updatedAt', 'record was updated before it was created');
      }

      const rule = [line.advertiserId, line.adProduct, line.baseOffering, line.condition1].join(' | ');
      if (rulesSeen.has(rule)) {
        fail('*', 'exact duplicate of row ' + rulesSeen.get(rule) + ' in the same card');
      } else {
        rulesSeen.set(rule, position + 1);
      }

      lineRecords.push({
        index: lineIndex, card: card.id, row: position + 1, id: line.id,
        advertiserName: line.advertiserName, advertiserId: line.advertiserId,
        adProduct: line.adProduct, baseOffering: line.baseOffering,
        rateType: line.rateType, baseRate: line.baseRate, currency: line.currency,
        condition1: line.condition1, updatedAt: line.updatedAt
      });
    });

    file.premiums.forEach((premium, position) => {
      premiumIndex += 1;
      // The premium's own inventory list, however the fixture stores it.
      const premiumOfferings = (Array.isArray(premium.baseOffering)
        ? premium.baseOffering
        : String(premium.baseOffering || '').split(','))
        .map(value => value.trim()).filter(Boolean);
      const fail = (field, reason) => premiumFailures.push({
        index: premiumIndex, card: card.id, row: position + 1,
        advertiserName: premium.displayName || '(missing)',
        advertiserId: premium.id || '(missing)',
        field, reason
      });

      ['id','attachToCard','category','displayName','calculationMethod','condition1']
        .forEach(field => {
          if (!premium[field]) fail(field, 'required field is missing or empty');
        });
      if (premium.attachToCard !== card.id) fail('attachToCard', 'premium is attached to another card');
      if (!Number.isFinite(premium.value)) fail('value', 'adjustment value is not a number');
      if (!Array.isArray(premium.lineItemIds) || !premium.lineItemIds.length) {
        fail('lineItemIds', 'adjustment is not attached to any pricing rule');
      }
      (premium.lineItemIds || []).forEach(id => {
        if (!lineIds.has(id)) fail('lineItemIds', 'attached to a rule that is not in this card');
      });
      if (PLACEHOLDER.test(premium.displayName || '')) {
        fail('displayName', 'reads as a placeholder name');
      }
      if (!PREMIUM_NAME.test(premium.displayName || '')) {
        fail('displayName', 'is not written as a named adjustment ending in "Premium"');
      }
      if (idByName[(premium.displayName || '').replace(/ Premium$/, '')]) {
        fail('displayName', 'names an advertiser instead of the adjustment it charges for');
      }
      if (CATEGORIES.indexOf(premium.category) < 0) {
        fail('category', 'category is outside the supported list');
      }
      if (CALC_METHODS.indexOf(premium.calculationMethod) < 0) {
        fail('calculationMethod', 'calculation method is not one of the three PRD values');
      }
      if (premium.calculationMethod === 'Additive CPM'
          && (premium.value <= 0 || premium.value > 12
            || Math.round(premium.value * 100) % 25 !== 0)) {
        fail('value', 'additive CPM is not a credible quarter-dollar uplift');
      }
      if (premium.calculationMethod === 'Percent Adjustment'
          && (premium.value <= 0 || premium.value > 40
            || Math.round(premium.value * 100) % 50 !== 0)) {
        fail('value', 'percent adjustment is not a credible half-point uplift');
      }
      if (premium.calculationMethod === 'Flat Fee'
          && (premium.value < 1000 || Math.round(premium.value) % 500 !== 0)) {
        fail('value', 'flat fee is not a credible rounded sponsorship figure');
      }
      if (!Number.isInteger(premium.stackOrder) || premium.stackOrder <= 0) {
        fail('stackOrder', 'stack order must be a positive integer');
      }
      if (PREMIUM_TRIGGERS.indexOf(premium.condition1) < 0) {
        fail('condition1', 'trigger is outside the controlled premium vocabulary');
      }
      // The premium prices the offerings it names, so every rule it is
      // attached to has to be selling one of them. This replaces the older
      // rule that demanded the line carry the premium's exact targeting:
      // a premium now scopes by inventory and advertiser (Figma 697:3617
      // shows Base offering on the premium itself), and a format or
      // commitment trigger has no line-targeting counterpart to match.
      (premium.lineItemIds || []).forEach(id => {
        const line = linesById.get(id);
        if (!line) return;
        if (premiumOfferings.length
            && premiumOfferings.indexOf(line.baseOffering) < 0) {
          fail('lineItemIds', 'attached to a rule selling ' + line.baseOffering
            + ', which this adjustment does not price');
        }
      });
      // An adjustment named for sports, live or championship inventory
      // may only be charged against that inventory.
      if (/Sports|Live Event|Championship/.test(premium.displayName || '')) {
        (premium.lineItemIds || []).forEach(id => {
          const line = linesById.get(id);
          if (line && SPORTS_OFFERINGS.indexOf(line.baseOffering) < 0) {
            fail('lineItemIds', 'sports or live adjustment charged against '
              + line.baseOffering);
          }
        });
      }
      if (premium.effectiveStart && premium.effectiveEnd
          && Date.parse(premium.effectiveStart) > Date.parse(premium.effectiveEnd)) {
        fail('effectiveEnd', 'adjustment ends before it starts');
      }
      ['effectiveStart','effectiveEnd'].forEach(field => {
        const value = premium[field];
        if (!value) return;
        if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) {
          fail(field, 'date is not YYYY-MM-DD');
          return;
        }
        if (Date.parse(value) < seasonStart || Date.parse(value) > seasonEnd) {
          fail(field, 'date falls outside the card effective period');
        }
      });
      // Figma 697:3617 gives the premium a Base offering column, so the
      // record owns that field and it has to be a real, canonical list.
      // Rate, ad product and a bare advertiser id remain line-only: those
      // are what would make a premium read as an advertiser row.
      if (premium.baseRate !== undefined || premium.adProduct !== undefined
          || premium.rateType !== undefined) {
        fail('*', 'premium carries line-item pricing fields, so it reads as an advertiser row');
      }
      // Only some fixtures store the offering list on the record; the rest
      // derive it from the attached rules at render time. Either way the
      // table has to show one, which the rendered-row audit further down
      // asserts. Here we only hold a stored list to being a real one.
      premiumOfferings.forEach(offering => {
        if (OFFERINGS.indexOf(offering) < 0) {
          fail('baseOffering', 'prices "' + offering + '", which is not a sold offering');
        }
      });
      if (premiumOfferings.length
          !== new Set(premiumOfferings).size) {
        fail('baseOffering', 'names the same offering twice');
      }

      premiumRecords.push({
        index: premiumIndex, card: card.id, row: position + 1, id: premium.id,
        displayName: premium.displayName, category: premium.category,
        calculationMethod: premium.calculationMethod, value: premium.value,
        stackOrder: premium.stackOrder, condition1: premium.condition1,
        attached: (premium.lineItemIds || []).length
      });
    });
  });

  /* One rule, one price. A rate is a function of what it prices, so two
   * records anywhere in the dataset that price the same inventory,
   * format, cost method and targeting must quote the same number. This
   * is what catches a rate that was generated rather than reasoned. */
  const priceByRule = new Map();
  lineRecords.forEach(record => {
    const rule = [record.baseOffering, record.adProduct, record.rateType,
      record.condition1].join(' | ');
    const seen = priceByRule.get(rule);
    if (seen === undefined) {
      priceByRule.set(rule, record.baseRate);
      return;
    }
    if (Math.abs(seen - record.baseRate) > 0.001) {
      lineFailures.push({
        index: record.index, card: record.card, row: record.row,
        advertiserName: record.advertiserName, advertiserId: record.advertiserId,
        field: 'baseRate',
        reason: 'the same rule is priced at ' + seen.toFixed(2) + ' elsewhere in the dataset'
      });
    }
  });

  /* A narrower rule never costs less than the broad rule it narrows, so
   * a salesperson can always explain why one row costs more. */
  const broadPrice = new Map();
  lineRecords.forEach(record => {
    if (record.condition1 !== C.none) return;
    broadPrice.set([record.card, record.advertiserId, record.baseOffering,
      record.adProduct, record.rateType].join('|'), record.baseRate);
  });
  lineRecords.forEach(record => {
    if (record.condition1 === C.none) return;
    const broad = broadPrice.get([record.card, record.advertiserId, record.baseOffering,
      record.adProduct, record.rateType].join('|'));
    if (broad !== undefined && record.baseRate < broad) {
      lineFailures.push({
        index: record.index, card: record.card, row: record.row,
        advertiserName: record.advertiserName, advertiserId: record.advertiserId,
        field: 'baseRate',
        reason: 'targeted rule is cheaper than this advertiser\'s broad rule (' 
          + broad.toFixed(2) + ')'
      });
    }
  });

  /* One adjustment name means one adjustment. The same premium may sit
   * on many cards, but it charges the same way and the same amount. */
  const premiumShape = new Map();
  premiumRecords.forEach(record => {
    const shape = [record.category, record.calculationMethod, record.value].join(' | ');
    const seen = premiumShape.get(record.displayName);
    if (seen === undefined) {
      premiumShape.set(record.displayName, shape);
      return;
    }
    if (seen !== shape) {
      premiumFailures.push({
        index: record.index, card: record.card, row: record.row,
        advertiserName: record.displayName, advertiserId: record.id,
        field: 'value',
        reason: 'this adjustment is charged as "' + seen + '" elsewhere in the dataset'
      });
    }
  });

  return {
    cards: entries.length,
    lineCount: lineIndex,
    premiumCount: premiumIndex,
    entityFailures,
    lineFailures,
    premiumFailures,
    lineRecords,
    premiumRecords,
    pricingRules: priceByRule.size,
    premiumShapes: premiumShape.size
  };
})()
"""


try:
    send("Runtime.enable")
    send("Page.enable")
    navigate("?version=2.0&demoData=cross-platform-2026-27", pause=1.6)
    evaluate("window.RCMDemoRateCard.reset()")

    audit = evaluate(RECORD_AUDIT)
    with open(os.path.join(OUT, "records.json"), "w", encoding="utf-8") as handle:
        json.dump(audit, handle, indent=2)

    print(
        f"\n=== Dataset discovered: {audit['cards']} rate card files, "
        f"{audit['lineCount']} LINE records, {audit['premiumCount']} PREM records, "
        f"{audit['pricingRules']} distinct priced rules, "
        f"{audit['premiumShapes']} distinct adjustments ===\n"
    )
    for problem in audit["entityFailures"][:20]:
        print(f"    {problem['card']} entity={problem['entity']} :: {problem['reason']}")
    check(
        f"Every one of the {audit['cards']} cards names a buying entity the"
        " catalog can price for",
        not audit["entityFailures"],
        f"{len(audit['entityFailures'])} cards unclassified",
    )
    failures.extend(audit["entityFailures"])
    report_record_failures(
        f"All {audit['lineCount']} LINE records form a credible pricing rule",
        audit["lineFailures"],
    )
    report_record_failures(
        f"All {audit['premiumCount']} PREM records form a credible adjustment",
        audit["premiumFailures"],
    )
    failures.extend(audit["lineFailures"])
    failures.extend(audit["premiumFailures"])

    legacy_lines, legacy_failures = audit_legacy_line_catalog(
        evaluate("window.RCMCatalog.allAdvertisers()")
    )
    report_record_failures(
        f"All {len(legacy_lines)} LINE records in the v1.x attach catalog"
        " form a credible pricing rule",
        legacy_failures,
    )
    failures.extend(legacy_failures)

    # --- Distribution and duplicate audit on the sales card ------------
    distribution = evaluate(
        """(() => {
          const record = window.RCMRateCards.getByRateCardId('%s');
          const file = window.RCMCatalog.buildFile(record);
          const counts = {};
          file.lines.forEach(line => {
            counts[line.advertiserName] = (counts[line.advertiserName] || 0) + 1;
          });
          const months = {};
          file.lines.forEach(line => {
            const month = line.updatedAt.slice(0, 7);
            months[month] = (months[month] || 0) + 1;
          });
          let consecutive = 0;
          file.lines.forEach((line, index) => {
            if (!index) return;
            const previous = file.lines[index - 1];
            if (line.advertiserName === previous.advertiserName
                && line.baseOffering === previous.baseOffering
                && line.adProduct === previous.adProduct) consecutive += 1;
          });
          const nearDuplicates = [];
          file.lines.forEach((line, index) => {
            file.lines.slice(index + 1).forEach(other => {
              if (line.advertiserId === other.advertiserId
                  && line.baseOffering === other.baseOffering
                  && line.adProduct === other.adProduct
                  && line.condition1 === other.condition1) {
                nearDuplicates.push(line.id + ' / ' + other.id);
              }
            });
          });
          return {
            lines: file.lines.length,
            premiums: file.premiums.length,
            advertisers: Object.keys(counts).length,
            counts, months, consecutive, nearDuplicates,
            distinctConditions: new Set(file.lines.map(line => line.condition1)).size,
            distinctRules: new Set(file.lines.map(line =>
              [line.advertiserId, line.adProduct, line.baseOffering, line.condition1].join('|')
            )).size
          };
        })()"""
        % SALES_CARD_ID
    )
    check(
        "Sales card holds 80 distinct pricing rules with no near-duplicates",
        distribution["lines"] == 80
        and distribution["distinctRules"] == 80
        and not distribution["nearDuplicates"],
        json.dumps(distribution["nearDuplicates"][:5]),
    )
    check(
        "Sales card mixes 15 advertisers without mechanically repeating one",
        distribution["advertisers"] == 15
        and distribution["consecutive"] == 0
        and min(distribution["counts"].values()) == 1
        and distribution["distinctConditions"] >= 15,
        json.dumps(distribution["counts"]),
    )
    check(
        "Sales card maintenance dates spread across the 2026 setup period",
        len(distribution["months"]) >= 4
        and max(distribution["months"].values()) <= distribution["lines"] * 0.6
        and all(month.startswith("2026-") for month in distribution["months"]),
        json.dumps(distribution["months"]),
    )

    # --- UI sweep: every page, every row, every Details panel ----------
    # Start from the fixture as generated so the sweep reads the audited
    # records rather than whatever a previous run left in storage.
    evaluate("window.RCMCatalog.resetConditionFixtures()")
    navigate(
        f"?version=2.1&section=create&mode=edit&cardId={SALES_CARD_ID}",
        pause=1.8,
    )
    row_audit = evaluate(
        """(async () => {
          const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
          const rows = () => [...document.querySelectorAll('[data-v2-tbody="lines"] tr')];
          const headings = [...document.querySelectorAll(
            '[data-v2-table-region="lines"] thead tr:not(.create-md__selection-row) th')]
            .map(th => th.textContent.trim());
          const pages = [...document.querySelectorAll('[data-v2-go-page="lines"] option')]
            .map(option => option.value);
          const seen = [];
          const mismatches = [];
          const clipped = [];
          for (const page of pages) {
            const select = document.querySelector('[data-v2-go-page="lines"]');
            select.value = page;
            select.dispatchEvent(new Event('change', {bubbles: true}));
            await wait(220);
            const count = rows().length;
            for (let index = 0; index < count; index += 1) {
              const row = rows()[index];
              const id = row.dataset.v2RowId;
              const cells = [...row.children].map(cell => cell.innerText.trim());
              const advertiserCell = cells.find(text => /ID: /.test(text)) || '';
              const parts = advertiserCell.split('\\n').map(part => part.trim())
                .filter(part => part && part !== 'Selected.');
              // Read by column heading rather than by offset from either
              // end: this table has gained and lost columns, and an
              // offset-based read goes on comparing the wrong pairs
              // without ever saying so.
              const at = (heading) => {
                const i = headings.indexOf(heading);
                return i < 0 ? '' : cells[i];
              };
              const shown = {
                name: parts[0] || '',
                id: (parts[1] || '').replace('ID: ', ''),
                offering: at('Base offering'),
                method: at('Cost method'),
                rate: at('Base rate'),
                currency: at('Currency'),
                // The em dash is the table's way of writing "no
                // condition" (followed by screen-reader-only words), and
                // the record stores that as an empty field.
                condition: (() => {
                  const shownText = at('Line condition');
                  return shownText.indexOf('\u2014') === 0 ? '' : shownText;
                })(),
                updated: at('Updated date')
              };
              row.click();
              await wait(90);
              const form = document.querySelector('[data-v2-form="line"]');
              const adType = document.getElementById('v2-ad-product-value');
              const panel = {
                rowId: form.elements.id.value,
                id: form.elements.advertiserId.value,
                name: form.elements.advertiserName.value,
                adType: adType ? adType.textContent.trim() : '',
                offering: form.elements.baseOffering.value,
                method: form.elements.rateType.value,
                rate: Number(form.elements.baseRate.value),
                currency: form.elements.currency.value,
                condition: form.elements.condition1.value
              };
              const problems = [];
              if (panel.rowId !== id) problems.push('panel loaded a different record');
              if (panel.name !== shown.name) problems.push('advertiser name differs from the row');
              if (panel.id !== shown.id) problems.push('advertiser ID differs from the row');
              if (panel.offering !== shown.offering) problems.push('base offering differs from the row');
              if (panel.method !== shown.method) problems.push('cost method differs from the row');
              const quoted = '$' + panel.rate.toLocaleString('en-US',
                {minimumFractionDigits: 2, maximumFractionDigits: 2});
              if (quoted !== shown.rate) problems.push('base rate differs from the row');
              if (panel.currency !== shown.currency) problems.push('currency differs from the row');
              /* One optional condition per rule, shown the same way in
               * both places: a label the row prints in full, or nothing
               * at all, which the row draws as an em dash and the panel
               * selects as None. */
              if (panel.condition !== shown.condition) {
                problems.push('line condition differs from the row');
              }
              /* The condition field is a closed multi-select now, so an
                 empty condition is the absence of chips rather than a
                 "None" option, and every chip has to be one the
                 approved catalog recognises. */
              const condHost = form.querySelector('[data-conditions]');
              const shownCondition = condHost
                ? condHost.querySelector('.ads-cond__input').value.trim() : '';
              if (!panel.condition && shownCondition) {
                problems.push('an empty condition still shows a value');
              }
              if (panel.condition && shownCondition !== panel.condition) {
                problems.push('the field does not match the stored condition');
              }
              if (condHost && condHost.classList.contains('is-unrecognized')) {
                problems.push('condition is not in the approved catalog');
              }
              // Anything the column is too narrow to show in full has to
              // offer the full value through the shared tooltip.
              [...row.children].forEach(cell => {
                const nodes = cell.querySelectorAll('[data-tooltip]').length
                  ? [...cell.querySelectorAll('[data-tooltip]')]
                  : [cell];
                nodes.forEach(node => {
                  if (node.scrollWidth > node.clientWidth + 1
                      && !node.getAttribute('data-tooltip')) {
                    clipped.push(id + ' :: ' + node.textContent.trim());
                  }
                });
              });
              if (problems.length) {
                mismatches.push({index: seen.length + 1, id, name: shown.name,
                  advertiserId: shown.id, problems});
              }
              seen.push({page, id, name: shown.name, advertiserId: shown.id,
                offering: shown.offering, rate: shown.rate, updated: shown.updated,
                condition: panel.condition, adType: panel.adType});
            }
          }
          return {pages, inspected: seen.length, mismatches, clipped, seen};
        })()"""
    )
    with open(os.path.join(OUT, "rendered-rows.json"), "w", encoding="utf-8") as handle:
        json.dump(row_audit["seen"], handle, indent=2)
    for mismatch in row_audit["mismatches"][:40]:
        print(
            f"    #{mismatch['index']} {mismatch['name']} ({mismatch['advertiserId']})"
            f" field=LineDetails :: {'; '.join(mismatch['problems'])}"
        )
    check(
        "Every rendered row opens a Line Details panel that matches it exactly",
        row_audit["inspected"] == 80 and not row_audit["mismatches"],
        f"inspected {row_audit['inspected']} rows, "
        f"{len(row_audit['mismatches'])} mismatched",
    )
    check(
        "No cell in any row is clipped without offering the full value",
        not row_audit["clipped"],
        json.dumps(row_audit["clipped"][:5]),
    )
    failures.extend(row_audit["mismatches"])

    # --- Widest money in the dataset still renders in full -------------
    # Sponsorship flat fees and unit prices are the widest values a rate
    # column ever holds, and they only appear on the sports books.
    wide_money = []
    for card_id in ("RC-DAS-ABINBEV-SPORTS-MY-2526", "RC-DAS-TOYOTA-SPORTS-MY-2526"):
        navigate(f"?version=2.1&section=create&mode=edit&cardId={card_id}", pause=1.6)
        wide_money.extend(
            evaluate(
                """(async () => {
                  const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
                  const rows = () => [...document.querySelectorAll('[data-v2-tbody="lines"] tr')];
                  const pages = [...document.querySelectorAll('[data-v2-go-page="lines"] option')]
                    .map(option => option.value);
                  const clipped = [];
                  for (const page of pages) {
                    const select = document.querySelector('[data-v2-go-page="lines"]');
                    select.value = page;
                    select.dispatchEvent(new Event('change', {bubbles: true}));
                    await wait(200);
                    rows().forEach(row => {
                      [...row.children].forEach(cell => {
                        const nodes = cell.querySelectorAll('[data-tooltip]').length
                          ? [...cell.querySelectorAll('[data-tooltip]')]
                          : [cell];
                        nodes.forEach(node => {
                          if (node.scrollWidth > node.clientWidth + 1
                              && !node.getAttribute('data-tooltip')) {
                            clipped.push(row.dataset.v2RowId + ' :: '
                              + node.textContent.trim());
                          }
                        });
                      });
                    });
                  }
                  return clipped;
                })()"""
            )
        )
    check(
        "Flat fees and unit prices render in full on the sports books",
        not wide_money,
        json.dumps(wide_money[:5]),
    )
    navigate(
        f"?version=2.1&section=create&mode=edit&cardId={SALES_CARD_ID}",
        pause=1.6,
    )

    # --- Search, filter and sort across the whole roster ---------------
    search_audit = evaluate(
        """(async () => {
          const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
          const record = window.RCMRateCards.getByRateCardId('%s');
          const file = window.RCMCatalog.buildFile(record);
          const expected = {};
          file.lines.forEach(line => {
            expected[line.advertiserName] = expected[line.advertiserName]
              || {id: line.advertiserId, count: 0};
            expected[line.advertiserName].count += 1;
          });
          const search = document.querySelector('[data-v2-search="lines"]');
          const total = () => Number(
            document.querySelector('[data-v2-total="lines"]').textContent
          );
          const set = async value => {
            search.value = value;
            search.dispatchEvent(new Event('input', {bubbles: true}));
            await wait(160);
            return total();
          };
          /* Search reads the condition column too, and one advertiser is
             called Target while a whole category is called Targeting.
             A term that also appears in the condition vocabulary is
             expected to return more than that advertiser's own rows:
             that is the search working. Everything else stays exact. */
          const conditionText = file.lines
            .map(line => line.condition1 || '').join(' | ').toLowerCase();
          const collides = value =>
            conditionText.indexOf(String(value).toLowerCase()) !== -1;
          const problems = [];
          for (const name of Object.keys(expected)) {
            const want = expected[name].count;
            const byName = await set(name);
            const nameOk = collides(name) ? byName >= want : byName === want;
            if (!nameOk) {
              problems.push({name, id: expected[name].id, field: 'search by name',
                reason: 'returned ' + byName + ', expected ' + want});
            }
            const id = expected[name].id;
            const byId = await set(id);
            const idOk = collides(id) ? byId >= want : byId === want;
            if (!idOk) {
              problems.push({name, id: id, field: 'search by ID',
                reason: 'returned ' + byId + ', expected ' + want});
            }
          }
          await set('');
          return {advertisers: Object.keys(expected).length, problems};
        })()"""
        % SALES_CARD_ID
    )
    for problem in search_audit["problems"][:20]:
        print(
            f"    {problem['name']} ({problem['id']})"
            f" field={problem['field']} :: {problem['reason']}"
        )
    check(
        "Search finds every advertiser by full name and by advertiser ID",
        not search_audit["problems"],
        f"{len(search_audit['problems'])} advertisers failed",
    )
    failures.extend(search_audit["problems"])

    filter_audit = evaluate(
        """(async () => {
          const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
          const record = window.RCMRateCards.getByRateCardId('%s');
          const file = window.RCMCatalog.buildFile(record);
          const trigger = document.querySelector('[data-v2-filter-root="lines"] button');
          const total = () => Number(
            document.querySelector('[data-v2-total="lines"]').textContent
          );
          const problems = [];
          const offerings = [...new Set(file.lines.map(line => line.baseOffering))];
          for (const offering of offerings) {
            const wanted = file.lines.filter(line => line.baseOffering === offering).length;
            trigger.click();
            await wait(140);
            const select = document.querySelector('[data-v2-line-filter="baseOffering"]');
            select.value = offering;
            select.dispatchEvent(new Event('change', {bubbles: true}));
            const apply = document.querySelector('[data-v2-action="apply-line-filter"]');
            if (apply) apply.click();
            await wait(180);
            if (total() !== wanted) {
              problems.push({name: offering, id: '-', field: 'base offering filter',
                reason: 'returned ' + total() + ', expected ' + wanted});
            }
            trigger.click();
            await wait(120);
            const reset = document.querySelector('[data-v2-action="reset-line-filter"]');
            if (reset) reset.click();
            await wait(160);
          }
          return {offerings: offerings.length, problems, restored: total()};
        })()"""
        % SALES_CARD_ID
    )
    for problem in filter_audit["problems"][:10]:
        print(f"    {problem['name']} field={problem['field']} :: {problem['reason']}")
    check(
        "Base offering filter returns exactly the rules that carry each offering",
        not filter_audit["problems"] and filter_audit["restored"] == 80,
        json.dumps(filter_audit),
    )
    failures.extend(filter_audit["problems"])

    sort_audit = evaluate(
        """(async () => {
          const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
          // Columns are read from the end so the audit does not depend on
          // whether the checkbox column is mounted.
          const cells = fromEnd => [...document.querySelectorAll(
            '[data-v2-tbody="lines"] tr'
          )].map(row => row.children[row.children.length - fromEnd].innerText.trim());
          const names = () => [...document.querySelectorAll(
            '[data-v2-tbody="lines"] .create-md__advertiser-name'
          )].map(node => node.textContent.trim().toLowerCase());
          const clickSort = async key => {
            document.querySelector('[data-v2-sort="lines:' + key + '"]').click();
            await wait(200);
          };
          const problems = [];
          const ascending = list => list.every((value, index) =>
            !index || list[index - 1] <= value);
          const descending = list => list.every((value, index) =>
            !index || list[index - 1] >= value);

          await clickSort('advertiserName');
          if (!ascending(names())) problems.push('advertiser name ascending');
          await clickSort('advertiserName');
          if (!descending(names())) problems.push('advertiser name descending');

          await clickSort('baseRate');
          const rates = cells(3).map(text => Number(text.replace(/[^0-9.]/g, '')));
          if (!ascending(rates)) problems.push('base rate ascending');
          await clickSort('baseRate');
          const ratesDesc = cells(3).map(text => Number(text.replace(/[^0-9.]/g, '')));
          if (!descending(ratesDesc)) problems.push('base rate descending');

          await clickSort('updatedAt');
          const dates = cells(1).map(text => Date.parse(text));
          if (!ascending(dates)) problems.push('updated date ascending');
          await clickSort('updatedAt');
          const datesDesc = cells(1).map(text => Date.parse(text));
          if (!descending(datesDesc)) problems.push('updated date descending');
          return problems;
        })()"""
    )
    check(
        "Advertiser, base rate and updated date all sort in both directions",
        not sort_audit,
        json.dumps(sort_audit),
    )

    selection_audit = evaluate(
        """(async () => {
          const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
          const rows = () => [...document.querySelectorAll('[data-v2-tbody="lines"] tr')];
          const form = () => document.querySelector('[data-v2-form="line"]');
          const problems = [];

          rows()[2].click();
          await wait(200);
          const firstId = form().elements.id.value;
          const firstRate = form().elements.baseRate.value;

          const checkbox = rows()[5].querySelector('input[type="checkbox"]');
          if (checkbox) {
            checkbox.click();
            await wait(200);
            if (form().elements.id.value !== firstId) {
              problems.push('ticking a checkbox loaded a different record into the panel');
            }
            checkbox.click();
            await wait(150);
          }

          document.querySelector('[data-v2-action="close-panel"]').click();
          await wait(200);
          const reopened = rows().find(row => row.dataset.v2RowId === firstId);
          reopened.click();
          await wait(200);
          if (form().elements.id.value !== firstId) {
            problems.push('reopening Line Details selected the wrong record');
          }
          if (form().elements.baseRate.value !== firstRate) {
            problems.push('reopened panel shows a stale rate');
          }

          rows()[7].click();
          await wait(200);
          const secondId = form().elements.id.value;
          if (secondId === firstId) problems.push('switching rows kept the previous record');
          const secondName = form().elements.advertiserName.value;
          const secondRow = rows().find(row => row.dataset.v2RowId === secondId);
          if (!secondRow.innerText.includes(secondName)) {
            problems.push('panel shows stale data from the previously selected row');
          }
          return problems;
        })()"""
    )
    check(
        "Selection, checkbox ticking and reopening never load a stale record",
        not selection_audit,
        json.dumps(selection_audit),
    )

    save_audit = evaluate(
        """(async () => {
          const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
          const rows = () => [...document.querySelectorAll('[data-v2-tbody="lines"] tr')];
          const form = () => document.querySelector('[data-v2-form="line"]');
          const target = rows()[1];
          const targetId = target.dataset.v2RowId;
          target.click();
          await wait(220);
          const before = form().elements.baseRate.value;
          const others = rows().filter(row => row.dataset.v2RowId !== targetId)
            .map(row => row.innerText.replace(/\\s+/g, ' ').trim());
          form().elements.baseRate.value = '44.75';
          form().elements.baseRate.dispatchEvent(new Event('input', {bubbles: true}));
          form().elements.baseRate.dispatchEvent(new Event('change', {bubbles: true}));
          document.querySelector('[data-v2-line-submit]').click();
          await wait(320);
          const saved = rows().find(row => row.dataset.v2RowId === targetId);
          const savedText = saved.innerText.replace(/\\s+/g, ' ').trim();
          const untouched = rows().filter(row => row.dataset.v2RowId !== targetId)
            .map(row => row.innerText.replace(/\\s+/g, ' ').trim());
          const strayEdits = untouched.filter(text => text.includes('$44.75')).length;
          return {
            before,
            savedShowsEdit: savedText.includes('$44.75'),
            strayEdits,
            otherRowCount: others.length === untouched.length
          };
        })()"""
    )
    check(
        "Saving a Line Details edit writes to the selected record only",
        save_audit["savedShowsEdit"]
        and save_audit["strayEdits"] == 0
        and save_audit["otherRowCount"],
        json.dumps(save_audit),
    )

    # PRD R9 makes the 2.1 Details panel a live-sync surface: an existing
    # rule's fields save on blur, so Cancel closes the panel rather than
    # rolling the record back. Cancel only discards work for a new draft,
    # which is the one case where the work is not yet in the table. The
    # audit holds the panel to that contract instead of to a revert it was
    # deliberately not built to do.
    cancel_audit = evaluate(
        """(async () => {
          const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
          const rows = () => [...document.querySelectorAll('[data-v2-tbody="lines"] tr')];
          const form = () => document.querySelector('[data-v2-form="line"]');
          const rowText = id => {
            const row = rows().find(entry => entry.dataset.v2RowId === id);
            return row ? row.innerText.replace(/\\s+/g, ' ').trim() : '';
          };
          const target = rows()[3];
          const targetId = target.dataset.v2RowId;
          target.click();
          await wait(220);
          const saved = Number(form().elements.baseRate.value).toFixed(2);
          const others = rows().length;
          form().elements.baseRate.value = '99.75';
          form().elements.baseRate.dispatchEvent(new Event('input', {bubbles: true}));
          form().elements.baseRate.dispatchEvent(new FocusEvent('focusout', {bubbles: true}));
          await wait(200);
          const committedOnBlur = rowText(targetId).includes('$99.75');
          document.querySelector('[data-v2-action="cancel-line"]').click();
          await wait(320);
          const afterCancel = rowText(targetId);
          const panelClosed = !document.querySelector('[data-v2-accordion="line"].is-open');

          // A new draft is the case Cancel does discard.
          document.querySelector('[data-v2-action="add-line"]').click();
          await wait(240);
          const draftForm = document.querySelector('[data-v2-form="line"]');
          draftForm.elements.advertiserId.value = 'ADV-1048-01';
          draftForm.elements.advertiserId.dispatchEvent(new Event('input', {bubbles: true}));
          draftForm.elements.advertiserId.dispatchEvent(new Event('change', {bubbles: true}));
          await wait(160);
          document.querySelector('[data-v2-action="cancel-line"]').click();
          await wait(200);
          const confirm = [...document.querySelectorAll('[data-ads-confirm] button')]
            .find(button => /Discard/.test(button.textContent));
          if (confirm) confirm.click();
          await wait(320);
          return {
            saved, committedOnBlur, panelClosed,
            keptAfterCancel: afterCancel.includes('$99.75'),
            rowCountUnchanged: rows().length === others,
            draftDiscarded: rows().length === others
          };
        })()"""
    )
    check(
        "Details panel follows the PRD save-on-blur contract: existing edits"
        " commit, Cancel closes, new drafts discard",
        cancel_audit["committedOnBlur"]
        and cancel_audit["keptAfterCancel"]
        and cancel_audit["panelClosed"]
        and cancel_audit["draftDiscarded"],
        json.dumps(cancel_audit),
    )
    evaluate("window.RCMCatalog.resetConditionFixtures()")

    # --- Every Premium row on every page of the largest premium book ---
    navigate(
        "?version=2.1&section=create&mode=edit&demoData=cross-platform-2026-27"
        "&cardId=RC-DAS-DISNEYADS-XPLAT-UF-2627",
        pause=1.8,
    )
    premium_audit = evaluate(
        """(async () => {
          const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
          const tab = [...document.querySelectorAll('[role="tab"]')]
            .find(node => /Premium/.test(node.textContent));
          if (tab) tab.click();
          await wait(320);
          const rows = () => [...document.querySelectorAll('[data-v2-tbody="premiums"] tr')];
          // Heading text to column position, so the checks below survive a
          // reordering of the table.
          const headings = [...document.querySelectorAll(
            '[data-v2-table-region="premiums"] thead tr:not(.create-md__selection-row) th')]
            .map(th => th.textContent.trim());
          const column = (heading) => headings.indexOf(heading);
          const pages = [...document.querySelectorAll('[data-v2-go-page="premiums"] option')]
            .map(option => option.value);
          const mismatches = [];
          let inspected = 0;
          for (const page of pages) {
            const select = document.querySelector('[data-v2-go-page="premiums"]');
            select.value = page;
            select.dispatchEvent(new Event('change', {bubbles: true}));
            await wait(220);
            const count = rows().length;
            for (let index = 0; index < count; index += 1) {
              const row = rows()[index];
              const id = row.dataset.v2RowId;
              // Read each cell by its column heading rather than by
              // position. Figma 697:3617 reordered this table and added a
              // selection column, and an index-based read would have gone
              // on comparing the wrong pairs without ever failing loudly.
              const cellFor = (heading) => {
                const at = column(heading);
                if (at < 0) return null;
                const cell = row.children[at];
                if (!cell) return null;
                const title = cell.getAttribute('title');
                if (title) return title.trim();
                // The selection state announces itself inside the name cell
                // for screen readers ("Selected. "), so read what a sighted
                // user actually sees rather than the cell's whole text.
                const visible = cell.cloneNode(true);
                visible.querySelectorAll('.sr-only').forEach(node => node.remove());
                return (visible.textContent || '').trim();
              };
              const name = cellFor('Premium');
              // The name cell is the row's own link target, so clicking it
              // opens the panel without touching the selection checkbox.
              (row.children[column('Premium')] || row).click();
              await wait(80);
              const form = document.querySelector('[data-v2-form="premium"]');
              const problems = [];
              if (form.elements.id.value !== id) problems.push('panel loaded a different adjustment');
              if (form.elements.displayName.value !== name) {
                problems.push('adjustment name differs from the row');
              }
              if (form.elements.category.value !== cellFor('Category')) {
                problems.push('category differs from the row');
              }
              if (form.elements.calculationMethod.value !== cellFor('Calculation method')) {
                problems.push('calculation method differs from the row');
              }
              if (Number(form.elements.value.value).toFixed(2) !== cellFor('Value')) {
                problems.push('adjustment value differs from the row');
              }
              if (row.querySelector('input[type=checkbox]:checked')) {
                problems.push('opening the panel also ticked the row');
              }
              // Figma 697:3617 gives every premium row a Base offering, so
              // no card may render the column empty however it sources it.
              if (!cellFor('Base offering')) {
                problems.push('row shows no Base offering');
              }
              if (problems.length) {
                mismatches.push({index: inspected + 1, id, name, problems});
              }
              inspected += 1;
            }
          }
          return {pages: pages.length, inspected, mismatches};
        })()"""
    )
    for mismatch in premium_audit["mismatches"][:20]:
        print(
            f"    #{mismatch['index']} {mismatch['name']} ({mismatch['id']})"
            f" field=PremiumDetails :: {'; '.join(mismatch['problems'])}"
        )
    check(
        "Every rendered Premium row opens a panel that matches it exactly",
        premium_audit["inspected"] == 44 and not premium_audit["mismatches"],
        json.dumps({k: v for k, v in premium_audit.items() if k != "mismatches"}),
    )

    check("No runtime exceptions during the audit", not console_messages,
          "\n".join(console_messages[:2]))

finally:
    summary = {
        "passes": sum(item["status"] == "PASS" for item in results),
        "failures": sum(item["status"] == "FAIL" for item in results),
        "results": results,
    }
    with open(os.path.join(OUT, "report.json"), "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
    print("\n" + json.dumps(summary | {"results": len(results)}))
    print(f"Artifacts: {OUT}")
    ws.close()
    chrome.terminate()
    server.shutdown()
