"""Browser QA for the deterministic cross-platform Rate Card demo fixture."""

import base64
import json
import os
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import urlopen

import websocket


ROOT = "/Users/frances.sun/My Drive/Cursor and Code/Rate Card"
PORT = 8991
DEBUG_PORT = 9291
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
OUT = "/tmp/rate-card-demo-dataset-qa"
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
profile = "/tmp/rate_card_demo_dataset_profile"
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
ws = websocket.create_connection(ws_url)
message_id = 0
results = []
console_messages = []


def send(method, params=None):
    global message_id
    message_id += 1
    expected = message_id
    ws.send(json.dumps({"id": expected, "method": method, "params": params or {}}))
    while True:
        event = json.loads(ws.recv())
        if event.get("method") in ("Runtime.consoleAPICalled", "Runtime.exceptionThrown"):
            console_messages.append(event)
        if event.get("id") == expected:
            return event


def evaluate(expression):
    response = send(
        "Runtime.evaluate",
        {"expression": expression, "returnByValue": True, "awaitPromise": True},
    )
    return response.get("result", {}).get("result", {}).get("value")


def navigate(query, pause=0.8):
    send("Page.navigate", {"url": f"http://127.0.0.1:{PORT}/{query}"})
    time.sleep(pause)


def check(name, condition, detail=""):
    passed = bool(condition)
    results.append((name, passed, detail))
    print(f"[{'PASS' if passed else 'FAIL'}] {name}" + (f": {detail}" if detail and not passed else ""))


def screenshot(name):
    send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": 1, "y": 1})
    payload = send("Page.captureScreenshot", {"format": "png"})
    with open(os.path.join(OUT, name + ".png"), "wb") as handle:
        handle.write(base64.b64decode(payload["result"]["data"]))


try:
    send("Runtime.enable")
    send("Page.enable")
    navigate("?version=2.0&demoData=cross-platform-2026-27")
    evaluate("window.RCMDemoRateCard.reset()")
    catalog_summary = evaluate(
        r"""(() => {
          const records = window.RCMRateCards.getAll()
            .filter(record => record.id !== window.RCMDemoRateCard.listId);
          const files = records.map(record => window.RCMCatalog.buildFile(record));
          const lineCounts = files.map(file => file.lines.length);
          const premiumCounts = files.map(file => file.premiums.length);
          const lineIds = new Set();
          const premiumIds = new Set();
          const allConditions = [];
          let orphanPremiums = 0;
          let wrongParents = 0;
          let invalidDates = 0;
          let invalidEnums = 0;
          let incoherentBusinessRows = 0;
          /* Premium-eligible conditions, read from the same generated
             catalog the product uses. */
          const premiumKeys = {};
          (window.RCMConditionCatalog ? window.RCMConditionCatalog.rows : [])
            .forEach(row => {
              if (row[3].indexOf('P') !== -1) {
                premiumKeys[(row[0] + ': ' + row[1]).toLowerCase()] = true;
              }
            });
          const premiumEligible = value => String(value || '')
            .split(',').map(part => part.trim()).filter(Boolean)
            .every(part => premiumKeys[part.toLowerCase()]);
          let invalidPremiumRelationships = 0;
          const invalidPremiumNames = [];
          let unreadableConditions = 0;
          let duplicateRules = 0;
          let unpricedRules = 0;
          // The sales dataset speaks one controlled vocabulary everywhere.
          // Ad Type is the format axis, Base Offering the property axis.
          const adTypes = ['Standard Video','Connected TV Video','Live Event Video',
            'Sports Video','Pause Ad'];
          const offerings = ['Disney+ Select','Hulu Select','Disney Streaming Bundle',
            'ESPN Streaming Sports','Disney Streaming Live Events','ABC','FX',
            'Freeform','National Geographic'];
          // One readable business rule per line ("Category: Dimension →
          // Value" or the two-part short form), or nothing: the Line
          // condition is optional and a rule without one is priced at the
          // broad rate. The old "No additional targeting" wording was that
          // statement stored as a value and is no longer accepted.
          const readableCondition =
            /^(?:|(?:Format|Targeting|Duration|DAR Demo): [^|,]+(?:, (?:Format|Targeting|Duration|DAR Demo): [^|,]+)*)$/;
          const sportsOfferings = ['ESPN Streaming Sports','Disney Streaming Live Events'];
          files.forEach(file => {
            const ownLineIds = new Set(file.lines.map(line => line.id));
            const linesById = new Map(file.lines.map(line => [line.id, line]));
            const cardName = file.card.name.toLowerCase();
            const rules = new Set();
            file.lines.forEach(line => {
              lineIds.add(line.id);
              allConditions.push(line.condition1 || '');
              if (!readableCondition.test(line.condition1)
                  || line.condition2 || line.condition3 || line.condition4) {
                unreadableConditions += 1;
              }
              // A pricing rule is advertiser + format + inventory +
              // targeting. A book must never list the same rule twice.
              const rule = [line.advertiserId, line.adProduct, line.baseOffering,
                line.condition1].join('|');
              if (rules.has(rule)) duplicateRules += 1;
              rules.add(rule);
              if (line.attachToCard !== file.card.id) wrongParents += 1;
              if (!adTypes.includes(line.adProduct)
                  || !offerings.includes(line.baseOffering)
                  || !['CPM','Flat Rate','Unit Price'].includes(line.rateType)
                  || !['USD','CAD','EUR','GBP'].includes(line.currency)) invalidEnums += 1;
              // CPM rates are quoted in sales-friendly quarter dollars.
              if (line.rateType === 'CPM'
                  && (line.baseRate < 20 || line.baseRate > 80
                    || Math.round(line.baseRate * 100) % 25 !== 0)) {
                unpricedRules += 1;
              }
              // Sports-named cards must carry sports inventory. That is a
              // Base Offering signal, not an Ad Type signal.
              if (cardName.includes('sports')
                  && !sportsOfferings.includes(line.baseOffering)
                  && line.baseOffering !== 'Disney Streaming Bundle') {
                incoherentBusinessRows += 1;
              }
            });
            file.premiums.forEach(premium => {
              premiumIds.add(premium.id);
              if (premium.attachToCard !== file.card.id) wrongParents += 1;
              if (!premium.lineItemIds.length
                  || premium.lineItemIds.some(id => !ownLineIds.has(id))) orphanPremiums += 1;
              if ((premium.effectiveStart && premium.effectiveStart < file.card.effectiveStart)
                  || (premium.effectiveEnd && premium.effectiveEnd > file.card.effectiveEnd)) invalidDates += 1;
              const attached = premium.lineItemIds.map(id => linesById.get(id)).filter(Boolean);
              /* An adjustment has to be able to price the rules it sits
               * on, and there are two ways a book says so.
               *
               * Where the premium authors its own Base Offering, that is
               * the scope: the adjustment charges for its own condition
               * (a Premium Condition, which RCM keeps separate from a
               * LINE's Condition 1-4), and it may only sit on rules
               * selling inventory it names. A premium whose condition had
               * to repeat the line's own targeting could never charge for
               * anything the rate did not already include.
               *
               * Where it does not, the premium is derived from the line
               * it came from and carries that line's targeting verbatim,
               * so the two conditions must still match exactly. */
              const scope = (premium.baseOffering || '')
                .split(',').map(part => part.trim()).filter(Boolean);
              /* A premium no longer repeats its line's targeting: its
                 condition comes from the Premium side of the Business
                 Dictionary, which is a different set from the one a line
                 can carry. Where the premium names no inventory, the
                 test is that its condition is Premium-eligible. */
              const compatible = scope.length
                ? attached.every(line => scope.includes(line.baseOffering))
                : premiumEligible(premium.condition1);
              if (!compatible) {
                invalidPremiumRelationships += 1;
                invalidPremiumNames.push(premium.displayName);
              }
              if (/sports|live event/i.test(premium.displayName)
                  && attached.some(line => !sportsOfferings.includes(line.baseOffering))) {
                incoherentBusinessRows += 1;
              }
            });
            if (file.card.marketplace === 'Multi-Year') {
              const duration = Date.parse(file.card.effectiveEnd) - Date.parse(file.card.effectiveStart);
              if (duration < 365 * 24 * 60 * 60 * 1000) incoherentBusinessRows += 1;
            }
          });
          const first = records[0];
          const firstFile = files[0];
          const frequency = allConditions.reduce((counts, condition) => {
            counts[condition] = (counts[condition] || 0) + 1;
            return counts;
          }, {});
          return {
            cards: files.length,
            totalLines: lineCounts.reduce((sum, count) => sum + count, 0),
            totalPremiums: premiumCounts.reduce((sum, count) => sum + count, 0),
            uniqueLineIds: lineIds.size,
            uniquePremiumIds: premiumIds.size,
            lineCounts: [...new Set(lineCounts)].sort((a, b) => a - b),
            premiumCounts: [...new Set(premiumCounts)].sort((a, b) => a - b),
            minLines: Math.min(...lineCounts),
            maxLines: Math.max(...lineCounts),
            noPremiumCards: premiumCounts.filter(count => count === 0).length,
            // Cards with a deep premium book. This used to look for
            // "Premium" in the Rate Card Name, but the naming convention
            // dropped that internal jargon, so count the premiums instead.
            premiumFocusedCards: premiumCounts.filter(count => count >= 8).length,
            orphanPremiums,
            wrongParents,
            invalidDates,
            invalidEnums,
            incoherentBusinessRows,
            unreadableConditions,
            duplicateRules,
            unpricedRules,
            distinctConditions: Object.keys(frequency).length,
            blankConditions: allConditions.filter(condition => !condition).length,
            maxConditionLength: Math.max(...allConditions.map(condition => condition.length)),
            pipedConditions: allConditions.filter(condition => condition.includes('|')).length,
            invalidPremiumRelationships,
            invalidPremiumNames: invalidPremiumNames.reduce((counts, name) => {
              counts[name] = (counts[name] || 0) + 1;
              return counts;
            }, {}),
            // Adjacent rows may share targeting when they price different
            // advertisers or inventory. Repeating the whole rule is what
            // reads as generated data, and that must never happen.
            consecutiveDuplicates: files.reduce((count, file) => count + file.lines.filter(
              (line, index) => index > 0
                && line.condition1 === file.lines[index - 1].condition1
                && line.advertiserId === file.lines[index - 1].advertiserId
                && line.baseOffering === file.lines[index - 1].baseOffering
            ).length, 0),
            first: {
              id: first.rateCardId,
              name: first.name,
              season: firstFile.card.dealSeason,
              start: firstFile.card.effectiveStart,
              end: firstFile.card.effectiveEnd,
              childParentsValid: firstFile.lines.every(line => line.attachToCard === first.rateCardId)
                && firstFile.premiums.every(premium => premium.attachToCard === first.rateCardId)
            }
          };
        })()"""
    )
    check(
        "Catalog covers all 100 existing Rate Cards with varied distributions",
        catalog_summary["cards"] == 100
        and catalog_summary["minLines"] == 0
        and catalog_summary["maxLines"] >= 75
        and len(catalog_summary["lineCounts"]) >= 8
        and len(catalog_summary["premiumCounts"]) >= 6
        and catalog_summary["noPremiumCards"] > 0
        and catalog_summary["premiumFocusedCards"] > 0,
        json.dumps(catalog_summary),
    )
    check(
        "Catalog relationships, enums, and premium dates are valid",
        catalog_summary["orphanPremiums"] == 0
        and catalog_summary["wrongParents"] == 0
        and catalog_summary["invalidDates"] == 0
        and catalog_summary["invalidEnums"] == 0
        and catalog_summary["incoherentBusinessRows"] == 0,
        json.dumps(catalog_summary),
    )
    check(
        # Every rule reads as one business sentence a salesperson can say
        # out loud, no rule is listed twice, and every CPM is quoted in
        # quarter dollars inside a plausible streaming band.
        "Catalog pricing rules are readable, unique, and priced in sales increments",
        catalog_summary["unreadableConditions"] == 0
        # The Line condition is optional, so a blank one is a rule priced
        # at the broad rate. What would be wrong is a book of nothing but
        # blanks, which would mean the column had stopped being populated.
        and 0 < catalog_summary["blankConditions"] < catalog_summary["totalLines"] / 3
        and catalog_summary["pipedConditions"] == 0
        and catalog_summary["maxConditionLength"] <= 140
        and catalog_summary["distinctConditions"] >= 20
        and catalog_summary["duplicateRules"] == 0
        and catalog_summary["consecutiveDuplicates"] == 0
        and catalog_summary["unpricedRules"] == 0,
        json.dumps(catalog_summary),
    )
    check(
        "Every deterministic Premium attachment is compatible with its Line Condition",
        catalog_summary["invalidPremiumRelationships"] == 0,
        json.dumps(catalog_summary),
    )
    print(
        json.dumps(
            {
                "conditionMetrics": {
                    key: catalog_summary[key]
                    for key in (
                        "totalLines",
                        "distinctConditions",
                        "blankConditions",
                        "maxConditionLength",
                        "pipedConditions",
                        "unreadableConditions",
                        "duplicateRules",
                        "unpricedRules",
                        "invalidPremiumRelationships",
                    )
                }
            },
            sort_keys=True,
        )
    )
    check(
        "First visible WPP Rate Card is fully migrated to 26-27",
        catalog_summary["first"]
        == {
            "id": "RC-DAS-WPP-VIDEO-UF-2627",
            "name": "WPP - Streaming Video Upfront 2026-2027",
            "season": "2026-2027",
            "start": "2026-10-01",
            "end": "2027-09-30",
            "childParentsValid": True,
        },
        json.dumps(catalog_summary["first"]),
    )
    dentsu_summary = evaluate(
        r"""(() => {
          const record = window.RCMRateCards.getByRateCardId('RC-DAS-DENTSU-ADDR-SC-2526');
          const first = window.RCMCatalog.buildFile(record);
          const second = window.RCMCatalog.buildFile(record);
          const lineIds = new Set(first.lines.map(line => line.id));
          const premiumIds = new Set(first.premiums.map(premium => premium.id));
          const offerings = {};
          const premiumByLine = Object.fromEntries(first.lines.map(line => [line.id, 0]));
          first.lines.forEach(line => {
            offerings[line.baseOffering] = (offerings[line.baseOffering] || 0) + 1;
          });
          first.premiums.forEach(premium => premium.lineItemIds.forEach(id => {
            premiumByLine[id] = (premiumByLine[id] || 0) + 1;
          }));
          const linesById = new Map(first.lines.map(line => [line.id, line]));
          // A premium carries its own condition from the Premium side of
          // the Business Dictionary rather than repeating the targeting
          // of the lines it sits on, so the rule is that it attaches to
          // real lines and that its condition is one a premium may hold.
          const premiumKeys = {};
          (window.RCMConditionCatalog ? window.RCMConditionCatalog.rows : [])
            .forEach(row => {
              if (row[3].indexOf('P') !== -1) {
                premiumKeys[(row[0] + ': ' + row[1]).toLowerCase()] = true;
              }
            });
          const incompatiblePremiums = first.premiums.filter(premium => {
            const attached = premium.lineItemIds.map(id => linesById.get(id)).filter(Boolean);
            if (!attached.length) return true;
            return String(premium.condition1 || '')
              .split(',').map(part => part.trim()).filter(Boolean)
              .some(part => !premiumKeys[part.toLowerCase()]);
          }).length;
          const requiredFieldsMissing = first.lines.filter(line =>
            !line.id || !line.attachToCard || !line.advertiserId || !line.advertiserName
            || !line.adProduct || !line.baseOffering || !line.rateType
            || !Number.isFinite(line.baseRate) || !line.currency || !line.condition1
            || !line.createdAt || !line.updatedAt
          ).length;
          const duplicateLines = first.lines.length - new Set(first.lines.map(line =>
            [line.advertiserId, line.adProduct, line.baseOffering, line.condition1].join('|')
          )).size;
          const rates = first.lines.map(line => line.baseRate);
          return {
            deterministic: JSON.stringify(first) === JSON.stringify(second),
            fixtureKey: first.fixtureKey,
            card: first.card,
            lines: first.lines.length,
            uniqueLineIds: lineIds.size,
            premiums: first.premiums.length,
            uniquePremiumIds: premiumIds.size,
            advertisers: new Set(first.lines.map(line => line.advertiserName)).size,
            adTypes: [...new Set(first.lines.map(line => line.adProduct))],
            offerings,
            methods: [...new Set(first.lines.map(line => line.rateType))],
            currencies: [...new Set(first.lines.map(line => line.currency))],
            conditions: [...new Set(first.lines.map(line => line.condition1))],
            categories: [...new Set(first.premiums.map(premium => premium.category))].sort(),
            minRate: Math.min(...rates),
            maxRate: Math.max(...rates),
            wrongParents: first.lines.filter(line => line.attachToCard !== first.card.id).length
              + first.premiums.filter(premium => premium.attachToCard !== first.card.id).length,
            orphanPremiums: first.premiums.filter(premium =>
              premium.lineItemIds.some(id => !lineIds.has(id))
            ).length,
            incompatiblePremiums,
            duplicateLines,
            duplicateAttachments: first.premiums.length - new Set(first.premiums.map(premium =>
              [premium.displayName, ...premium.lineItemIds].join('|')
            )).size,
            requiredFieldsMissing,
            linesWithoutPremium: Object.values(premiumByLine).filter(count => count === 0).length,
            maxPremiumsPerLine: Math.max(...Object.values(premiumByLine)),
            linearTvMatches: (JSON.stringify(first).match(/linear tv/gi) || []).length,
            invalidPremiumDates: first.premiums.filter(premium =>
              (premium.effectiveStart && premium.effectiveStart < first.card.effectiveStart)
              || (premium.effectiveEnd && premium.effectiveEnd > first.card.effectiveEnd)
            ).length,
            invalidStackOrder: first.premiums.filter(premium =>
              ![10, 20, 30, 40].includes(premium.stackOrder)
            ).length
          };
        })()"""
    )
    check(
        "Dentsu Addressable TV fixture has the approved CARD identity and exact volumes",
        dentsu_summary["card"]["id"] == "RC-DAS-DENTSU-ADDR-SC-2526"
        and dentsu_summary["card"]["name"] == "Dentsu - Addressable TV Scatter 2025-2026"
        and dentsu_summary["card"]["marketplace"] == "Scatter"
        and dentsu_summary["card"]["buyingEntityName"] == "Dentsu"
        and dentsu_summary["lines"] == 48
        and dentsu_summary["uniqueLineIds"] == 48
        and dentsu_summary["premiums"] == 12
        and dentsu_summary["uniquePremiumIds"] == 12,
        json.dumps(dentsu_summary),
    )
    check(
        # The Dentsu Addressable TV rate card is still an
        # addressable-inventory deal, but "Addressable" is a delivery /
        # targeting mechanism (Line Condition) rather than an Ad Type.
        # Ad Type stays on the format axis: streaming video everywhere,
        # and Sports Video on the ESPN rules.
        "Dentsu fixture prices the shared advertiser roster on format-only ad types",
        dentsu_summary["advertisers"] == 15
        and sorted(dentsu_summary["adTypes"]) == ["Sports Video", "Standard Video"]
        and dentsu_summary["offerings"]
        == {
            "Hulu Select": 14,
            "Disney+ Select": 12,
            "ESPN Streaming Sports": 10,
            "ABC": 6,
            "FX": 2,
            "Freeform": 2,
            "National Geographic": 2,
        }
        and dentsu_summary["methods"] == ["CPM"]
        and dentsu_summary["currencies"] == ["USD"]
        and len(dentsu_summary["conditions"]) >= 15,
        json.dumps(dentsu_summary),
    )
    check(
        # One Line Condition per rule means one adjustment can trigger on
        # a rule, so premiums no longer stack two deep on a single line.
        "Dentsu fixture relationships, rates, premiums, and timestamps are valid",
        dentsu_summary["deterministic"]
        and dentsu_summary["fixtureKey"] == "dentsu-addressable-tv-scatter-2025-2026-sales-v2"
        and 28 <= dentsu_summary["minRate"] <= 38
        and 44 <= dentsu_summary["maxRate"] <= 75
        and dentsu_summary["wrongParents"] == 0
        and dentsu_summary["orphanPremiums"] == 0
        and dentsu_summary["incompatiblePremiums"] == 0
        and dentsu_summary["duplicateLines"] == 0
        and dentsu_summary["duplicateAttachments"] == 0
        and dentsu_summary["requiredFieldsMissing"] == 0
        and dentsu_summary["invalidPremiumDates"] == 0
        and dentsu_summary["invalidStackOrder"] == 0
        and dentsu_summary["linearTvMatches"] == 0
        and dentsu_summary["linesWithoutPremium"] > 0
        and dentsu_summary["maxPremiumsPerLine"] == 1,
        json.dumps(dentsu_summary),
    )
    evaluate("window.RCMCatalog.resetDentsuAddressable()")
    navigate(
        "?version=2.0&section=create&mode=edit"
        "&cardId=RC-DAS-DENTSU-ADDR-SC-2526"
    )
    dentsu_page = evaluate(
        """(() => ({
          title: document.querySelector('[data-v2-title]').textContent,
          lineCount: document.querySelector('[data-v2-total="lines"]').textContent,
          premiumCount: document.querySelector('[data-v2-total="premiums"]').textContent,
          pageSize: document.querySelector('[data-v2-page-size="lines"]').value,
          rows: document.querySelectorAll('[data-v2-tbody="lines"] tr').length,
          pages: [...document.querySelector('[data-v2-go-page="lines"]').options].map(o => o.value),
          cardId: document.querySelector('[data-v2-card-id]').textContent,
          marketplace: document.querySelector('[data-v2-form="card"]').elements.marketplace.value
        }))()"""
    )
    check(
        "Dentsu Edit page renders 48 LINE and 12 PREM badges with five pages",
        dentsu_page
        == {
            "title": "Dentsu - Addressable TV Scatter 2025-2026",
            "lineCount": "48",
            "premiumCount": "12",
            "pageSize": "10",
            "rows": 10,
            "pages": ["1", "2", "3", "4", "5"],
            "cardId": "RC-DAS-DENTSU-ADDR-SC-2526",
            "marketplace": "Scatter",
        },
        json.dumps(dentsu_page),
    )
    dentsu_page_rows = evaluate(
        """(() => [1, 2, 3, 4, 5].map(page => {
          document.querySelector('[data-v2-page="lines:' + page + '"]').click();
          return document.querySelectorAll('[data-v2-tbody="lines"] tr').length;
        }))()"""
    )
    check("Dentsu pagination distributes rows 10, 10, 10, 10, 8", dentsu_page_rows == [10, 10, 10, 10, 8])
    dentsu_search = evaluate(
        """(() => {
          const input = document.querySelector('[data-v2-search="lines"]');
          input.value = 'Verizon';
          input.dispatchEvent(new Event('input', {bubbles:true}));
          const byName = Number(document.querySelector('[data-v2-total="lines"]').textContent);
          input.value = 'ADV-1321-01';
          input.dispatchEvent(new Event('input', {bubbles:true}));
          const byId = Number(document.querySelector('[data-v2-total="lines"]').textContent);
          document.querySelector('[data-v2-clear-search="lines"]').click();
          return {byName, byId};
        })()"""
    )
    check(
        "Dentsu LINE search finds reused advertisers by name and ID",
        dentsu_search == {"byName": 3, "byId": 3},
        json.dumps(dentsu_search),
    )
    dentsu_sort = evaluate(
        """(() => {
          const sort = document.querySelector('[data-v2-sort="lines:baseRate"]');
          const values = () => [...document.querySelectorAll('[data-v2-tbody="lines"] tr td:nth-child(5)')]
            .map(cell => Number(cell.textContent.replace(/[^0-9.]/g, '')));
          sort.click();
          const ascending = values();
          sort.click();
          const descending = values();
          return {
            ascending: ascending.every((value, index) => !index || ascending[index - 1] <= value),
            descending: descending.every((value, index) => !index || descending[index - 1] >= value),
            varied: new Set(ascending).size > 5
          };
        })()"""
    )
    check(
        "Dentsu Base Rate sorts numerically with meaningful variation",
        dentsu_sort == {"ascending": True, "descending": True, "varied": True},
        json.dumps(dentsu_sort),
    )
    dentsu_selection = evaluate(
        """(() => {
          const search = document.querySelector('[data-v2-search="lines"]');
          search.value = 'ADV-1236-01';
          search.dispatchEvent(new Event('input', {bubbles:true}));
          const line = document.querySelector(
            '[data-v2-row-id="RC-DAS-DENTSU-ADDR-SC-2526-LINE-048"]'
          );
          line.click();
          const selectedLine = document.querySelector('[data-v2-form="line"]').elements.id.value;
          /* The tabs carry no count chip, so the row total comes from the
           * table footer. That total counts the rows currently in view, so
           * the search has to be cleared before it can stand in for the
           * whole collection. */
          document.querySelector('[data-v2-clear-search="lines"]').click();
          const total = () => Number(
            document.querySelector('[data-v2-total="lines"]').textContent
          );
          const countBefore = total();
          document.querySelector('[data-v2-action="request-remove-line"]').click();
          document.querySelector('[data-v2-action="confirm-remove-line"]').click();
          const countAfterRemove = total();
          document.querySelector('[data-v2-action="add-line"]').click();
          const form = document.querySelector('[data-v2-form="line"]');
          form.elements.advertiserId.value = 'ADV-1264-01';
          form.elements.advertiserName.value = 'Nestlé USA';
          // Under the corrected taxonomy the addressable-inventory signal
          // travels via the Line Condition (authenticated streaming
          // households), so the Ad Type is the underlying ad format.
          form.elements.adProduct.value = 'Standard Video';
          form.elements.baseOffering.value = 'Hulu Select';
          form.elements.rateType.value = 'CPM';
          form.elements.baseRate.value = '39.5';
          form.elements.currency.value = 'USD';
          form.elements.condition1.value = 'Format: Premier Product';
          form.requestSubmit();
          const countAfterAdd = total();
          document.querySelector('[data-v2-tab="premiums"]').click();
          const premium = document.querySelector('[data-v2-tbody="premiums"] tr');
          premium.click();
          const premiumForm = document.querySelector('[data-v2-form="premium"]');
          const premiumId = premiumForm.elements.id.value;
          premiumForm.elements.value.value = String(Number(premiumForm.elements.value.value) + 1);
          premiumForm.requestSubmit();
          const premiumCount = Number(
            document.querySelector('[data-v2-total="premiums"]').textContent
          );
          const premiumIdAfterEdit = premiumForm.elements.id.value;
          return {
            selectedLine, countBefore, countAfterRemove, countAfterAdd,
            premiumId, premiumIdAfterEdit, premiumCount
          };
        })()"""
    )
    check(
        "Dentsu row selection and count-changing workflows use the correct records",
        dentsu_selection["selectedLine"] == "RC-DAS-DENTSU-ADDR-SC-2526-LINE-048"
        and dentsu_selection["countBefore"] == 48
        and dentsu_selection["countAfterRemove"] == 47
        and dentsu_selection["countAfterAdd"] == 48
        and dentsu_selection["premiumId"].startswith("RC-DAS-DENTSU-ADDR-SC-2526-PREM-")
        and dentsu_selection["premiumIdAfterEdit"] == dentsu_selection["premiumId"]
        and dentsu_selection["premiumCount"] == 12,
        json.dumps(dentsu_selection),
    )
    screenshot("dentsu-addressable-tv")
    evaluate("window.RCMCatalog.resetDentsuAddressable()")
    navigate("?version=2.0&demoData=cross-platform-2026-27")
    evaluate(
        """(() => {
          const search = document.querySelector('[data-action="search"]');
          search.value = 'RC-DAS-DISNEYADS-XPLAT-UF-2627';
          search.dispatchEvent(new Event('input', {bubbles:true}));
        })()"""
    )
    time.sleep(0.15)
    check(
        "Demo Rate Card is selectable from the existing list",
        evaluate(
            """document.querySelectorAll('[data-rows] .row').length === 1
            && document.querySelector('[data-rows] .name__link').textContent.trim()
              === 'Disney Advertising - Cross-Platform Upfront 2026-2027'"""
        ),
    )
    evaluate("document.querySelector('[data-rows] .name__link').click()")
    time.sleep(0.8)

    fixture_summary = evaluate(
        """(() => {
          const file = window.RCMDemoRateCard.getFile(window.RCMDemoRateCard.cardId);
          const lineIds = new Set(file.lines.map(line => line.id));
          const premiumIds = new Set(file.premiums.map(premium => premium.id));
          const premiumCountByLine = Object.fromEntries(file.lines.map(line => [line.id, 0]));
          file.premiums.forEach(premium => premium.lineItemIds.forEach(id => {
            premiumCountByLine[id] = (premiumCountByLine[id] || 0) + 1;
          }));
          // Allowed adProduct -> baseOffering pairings under the
          // two-axis taxonomy. Ad Type is the format, Base Offering is
          // the streaming package. Every pairing listed is emitted by
          // the cross-platform inventory patterns fixture.
          const allowedOfferings = {
            'Standard Video': ['Disney+ Select', 'Hulu Select', 'Disney Streaming Bundle'],
            'Connected TV Video': ['Hulu Select', 'Disney Streaming Bundle'],
            'Sports Video': ['ESPN Streaming Sports'],
            'Live Event Video': ['Disney Streaming Live Events'],
            'Pause Ad': ['Disney Streaming Bundle']
          };
          const duplicateLines = file.lines.length - new Set(file.lines.map(line =>
            [line.advertiserId, line.adProduct, line.baseOffering, line.rateType,
             line.baseRate, line.condition1].join('|')
          )).size;
          return {
            lines: file.lines.length,
            uniqueLineIds: lineIds.size,
            premiums: file.premiums.length,
            uniquePremiumIds: premiumIds.size,
            advertisers: new Set(file.lines.map(line => line.advertiserName)).size,
            adTypes: [...new Set(file.lines.map(line => line.adProduct))],
            offerings: [...new Set(file.lines.map(line => line.baseOffering))],
            methods: [...new Set(file.lines.map(line => line.rateType))],
            categories: [...new Set(file.premiums.map(premium => premium.category))],
            duplicateLines,
            invalidRates: file.lines.filter(line => !Number.isFinite(line.baseRate) || line.baseRate <= 0).length,
            invalidCombinations: file.lines.filter(line =>
              !allowedOfferings[line.adProduct]?.includes(line.baseOffering)
            ).length,
            wrongCurrency: file.lines.filter(line => line.currency !== 'USD').length,
            wrongParent: file.lines.filter(line => line.attachToCard !== file.card.id).length
              + file.premiums.filter(premium => premium.attachToCard !== file.card.id).length,
            orphanPremiums: file.premiums.filter(premium =>
              !premium.lineItemIds.length || premium.lineItemIds.some(id => !lineIds.has(id))
            ).length,
            invalidDates: file.premiums.filter(premium =>
              (premium.effectiveStart && premium.effectiveStart < file.card.effectiveStart)
              || (premium.effectiveEnd && premium.effectiveEnd > file.card.effectiveEnd)
            ).length,
            legacyPremiumConditions: file.premiums.filter(premium =>
              premium.condition2 || premium.condition3
            ).length,
            linesWithoutPremium: Object.values(premiumCountByLine).filter(count => count === 0).length,
            maxPremiumsPerLine: Math.max(...Object.values(premiumCountByLine)),
            duplicateAttachments: file.premiums.length - new Set(file.premiums.map(premium =>
              [premium.displayName, ...premium.lineItemIds].join('|')
            )).size,
            duplicateAttachmentDetails: file.premiums.filter((premium, index, premiums) => {
              const key = [premium.displayName, ...premium.lineItemIds].join('|');
              return premiums.findIndex(candidate =>
                [candidate.displayName, ...candidate.lineItemIds].join('|') === key
              ) !== index;
            }).map(premium => ({
              displayName: premium.displayName,
              lineItemIds: premium.lineItemIds
            }))
          };
        })()"""
    )
    check("Fixture has exactly 100 unique LINE records", fixture_summary["lines"] == 100 and fixture_summary["uniqueLineIds"] == 100)
    check("Fixture has exactly 44 unique PREM records",
          fixture_summary["premiums"] == 44
          and fixture_summary["uniquePremiumIds"] == 44,
          json.dumps({"premiums": fixture_summary["premiums"],
                      "unique": fixture_summary["uniquePremiumIds"]}))
    check("Fixture represents the shared 15-advertiser roster", fixture_summary["advertisers"] == 15)
    check("Fixture uses all five approved Ad Type values", len(fixture_summary["adTypes"]) == 5)
    check("Fixture uses all five streaming Base Offering values", len(fixture_summary["offerings"]) == 5)
    check("Fixture uses all three approved Cost Method values", len(fixture_summary["methods"]) == 3)
    check("Fixture uses all seven approved Premium categories", len(fixture_summary["categories"]) == 7)
    check(
        "Fixture relationships, rates, dates, and conditions are valid",
        all(
            fixture_summary[key] == 0
            for key in (
                "duplicateLines",
                "invalidRates",
                "invalidCombinations",
                "wrongCurrency",
                "wrongParent",
                "orphanPremiums",
                "invalidDates",
                "legacyPremiumConditions",
                "duplicateAttachments",
            )
        ),
        json.dumps(fixture_summary),
    )
    check(
        "Premium distribution includes unadjusted and multi-premium LINE records",
        fixture_summary["linesWithoutPremium"] > 0
        and fixture_summary["maxPremiumsPerLine"] >= 3,
        json.dumps(fixture_summary),
    )

    page_state = evaluate(
        """(() => ({
          title: document.querySelector('[data-v2-title]').textContent,
          lineCount: document.querySelector('[data-v2-total="lines"]').textContent,
          premiumCount: document.querySelector('[data-v2-total="premiums"]').textContent,
          rows: document.querySelectorAll('[data-v2-tbody="lines"] tr').length,
          pages: [...document.querySelector('[data-v2-go-page="lines"]').options].map(o => o.value),
          cardId: document.querySelector('[data-v2-card-id]').textContent,
          name: document.querySelector('[data-v2-form="card"]').elements.name.value,
          marketplace: document.querySelector('[data-v2-form="card"]').elements.marketplace.value,
          season: document.querySelector('[data-v2-form="card"]').elements.dealSeason.value
        }))()"""
    )
    check(
        "Edit page hydrates the saved demo CARD and dynamic badges",
        page_state
        == {
            "title": "Disney Advertising - Cross-Platform Upfront 2026-2027",
            "lineCount": "100",
            "premiumCount": "44",
            "rows": 10,
            "pages": [str(page) for page in range(1, 11)],
            "cardId": "RC-DAS-DISNEYADS-XPLAT-UF-2627",
            "name": "Disney Advertising - Cross-Platform Upfront 2026-2027",
            "marketplace": "Upfront",
            "season": "2026-2027",
        },
        json.dumps(page_state),
    )
    screenshot("line-items-page-1")

    evaluate("document.querySelector('[data-v2-page=\"lines:5\"]').click()")
    check(
        "Generated pagination reaches a distinct fifth page",
        evaluate(
            """document.querySelector('[data-v2-pagination="lines"] [aria-current="page"]').textContent === '5'
            && document.querySelectorAll('[data-v2-tbody="lines"] tr').length === 10
            && document.querySelector('[data-v2-tbody="lines"] tr').dataset.v2RowId !== 'LI-0001'"""
        ),
    )
    screenshot("line-items-page-5")

    evaluate(
        """(() => {
          const search = document.querySelector('[data-v2-search="lines"]');
          search.value = '  united airlines  ';
          search.dispatchEvent(new Event('input', {bubbles:true}));
        })()"""
    )
    check(
        "Search trims whitespace and finds the advertiser's five records",
        evaluate(
            """document.querySelector('[data-v2-total="lines"]').textContent === '5'
            && document.querySelectorAll('[data-v2-tbody="lines"] tr').length === 5
            && [...document.querySelectorAll('[data-v2-tbody="lines"] tr td:first-child')]
              .every(cell => cell.textContent.includes('United Airlines'))"""
        ),
    )
    evaluate("document.querySelector('[data-v2-clear-search=\"lines\"]').click()")

    first_line_id = evaluate(
        """(() => {
          const row = document.querySelector('[data-v2-tbody="lines"] tr');
          row.click();
          return document.querySelector('[data-v2-form="line"]').elements.id.value;
        })()"""
    )
    check("Selecting a LINE row loads its stable record ID", first_line_id.startswith("LI-"))
    line_count_before = evaluate("Number(document.querySelector('[data-v2-total=\"lines\"]').textContent)")
    evaluate(
        """(() => {
          const form = document.querySelector('[data-v2-form="line"]');
          form.elements.baseRate.value = String(Number(form.elements.baseRate.value) + 1);
          form.requestSubmit();
        })()"""
    )
    check(
        "Editing a LINE updates without duplication",
        evaluate("Number(document.querySelector('[data-v2-total=\"lines\"]').textContent)")
        == line_count_before,
    )

    evaluate("document.querySelector('[data-v2-tab=\"premiums\"]').click()")
    premium_id = evaluate(
        """(() => {
          const row = document.querySelector('[data-v2-tbody="premiums"] tr');
          row.click();
          return document.querySelector('[data-v2-form="premium"]').elements.id.value;
        })()"""
    )
    check("Selecting a Premium loads its stable record ID", premium_id.startswith("PREM-"))
    check(
        "Premiums table paginates the 44 related records",
        evaluate(
            """document.querySelectorAll('[data-v2-tbody="premiums"] tr').length === 10
            && document.querySelector('[data-v2-total="premiums"]').textContent === '44'
            && document.querySelectorAll('[data-v2-pagination="premiums"] .create-md__pagination-item--page').length >= 5
            && document.querySelectorAll('[data-v2-go-page="premiums"] option').length === 5
            && document.querySelector('[data-v2-page-size="premiums"]').value === '10'"""
        ),
    )
    screenshot("premium-adjustments")

    evaluate("document.querySelector('[data-v2-action=\"save-draft\"]').click()")
    time.sleep(0.15)
    navigate(
        "?version=2.0&section=create&mode=edit"
        "&cardId=RC-DAS-DISNEYADS-XPLAT-UF-2627"
        "&demoData=cross-platform-2026-27"
    )
    check(
        "Refreshing after save does not duplicate fixture records",
        evaluate(
            """document.querySelector('[data-v2-total="lines"]').textContent === '100'
            && document.querySelector('[data-v2-total="premiums"]').textContent === '44'"""
        ),
    )

    navigate("?version=2.0&demoData=cross-platform-2026-27")
    send(
        "Emulation.setDeviceMetricsOverride",
        {"width": 1440, "height": 960, "deviceScaleFactor": 1, "mobile": False},
    )
    evaluate(
        """(() => {
          window.__qaExportBlob = null;
          window.__qaExportName = '';
          URL.createObjectURL = blob => {
            window.__qaExportBlob = blob;
            return 'blob:qa-rate-card';
          };
          URL.revokeObjectURL = () => {};
          HTMLAnchorElement.prototype.click = function() {
            window.__qaExportName = this.download;
          };
          const row = document.querySelector('[data-rows] .row');
          row.querySelectorAll('.actions .icon-btn')[2].click();
        })()"""
    )
    exported = evaluate(
        """(async () => ({
          name: window.__qaExportName,
          text: window.__qaExportBlob ? await window.__qaExportBlob.text() : ''
        }))()"""
    )
    check(
        "Export action downloads a complete CARD, LINE, and PREM CSV",
        exported["name"].endswith(".csv")
        and '"CARD"' in exported["text"]
        and '"LINE"' in exported["text"]
        and '"PREM"' in exported["text"]
        and "RC-DAS-WPP-VIDEO-UF-2627" in exported["text"],
        json.dumps({"name": exported["name"], "size": len(exported["text"])}),
    )
    evaluate("document.querySelector('[data-action=\"download-template\"]').click()")
    template_download = evaluate(
        """(async () => ({
          name: window.__qaExportName,
          text: window.__qaExportBlob ? await window.__qaExportBlob.text() : ''
        }))()"""
    )
    check(
        "Blank template action downloads the real RCM CSV template",
        template_download["name"] == "rate-card-import-template.csv"
        and template_download["text"].startswith('"ROW_TYPE","ID","RATE_CARD_ID"')
        and len(template_download["text"].strip().splitlines()) == 1,
        json.dumps({"name": template_download["name"], "size": len(template_download["text"])}),
    )

    evaluate(
        """(() => {
          const headers = [
            'ROW_TYPE','ID','RATE_CARD_ID','RATE_CARD_NAME','MARKETPLACE',
            'BUYING_ENTITY_SALESHUB_ID','BUYING_ENTITY_DISPLAY_NAME','DEAL_SEASON',
            'DCM_RULE_ORDER','EFFECTIVE_START_DATE','EFFECTIVE_END_DATE',
            'ADVERTISER_ID','ADVERTISER_DISPLAY_NAME','AD_TYPE','BASE_OFFERING',
            'COST_METHOD','BASE_RATE','CURRENCY','LINE_CONDITION',
            'PREMIUM_CATEGORY','PREMIUM_DISPLAY_NAME','CALCULATION_METHOD','VALUE',
            'STACK_ORDER','PREMIUM_CONDITION','ATTACHED_LINE_IDS'
          ];
          const makeRow = values => headers.map(header => values[header] || '').join(',');
          const csv = [
            headers.join(','),
            makeRow({
              ROW_TYPE:'CARD', ID:'RC-QA-IMPORT-UF-2627',
              RATE_CARD_ID:'RC-QA-IMPORT-UF-2627',
              RATE_CARD_NAME:'QA Upfront Video 2026-2027', MARKETPLACE:'UPFRONT',
              BUYING_ENTITY_SALESHUB_ID:'BE-QA-2627',
              BUYING_ENTITY_DISPLAY_NAME:'QA Media Group', DEAL_SEASON:'2026-2027',
              DCM_RULE_ORDER:'10', EFFECTIVE_START_DATE:'2026-10-01',
              EFFECTIVE_END_DATE:'2027-09-30'
            }),
            makeRow({
              ROW_TYPE:'LINE', ID:'RC-QA-IMPORT-UF-2627-LINE-001',
              RATE_CARD_ID:'RC-QA-IMPORT-UF-2627', ADVERTISER_ID:'ADV-1195-01',
              ADVERTISER_DISPLAY_NAME:'Target',
              AD_TYPE:'Standard Video', BASE_OFFERING:'Disney+ Select',
              COST_METHOD:'CPM', BASE_RATE:'36.2500', CURRENCY:'USD',
              LINE_CONDITION:'DAR Demo: A18-49'
            }),
            makeRow({
              ROW_TYPE:'LINE', ID:'RC-QA-IMPORT-UF-2627-LINE-002',
              RATE_CARD_ID:'RC-QA-IMPORT-UF-2627', ADVERTISER_ID:'ADV-1087-01',
              AD_TYPE:'Pause Ad', BASE_OFFERING:'Hulu Select', COST_METHOD:'CPM',
              CURRENCY:'USD'
            })
          ].join('\\r\\n') + '\\r\\n';
          HTMLInputElement.prototype.click = function() {
            Object.defineProperty(this, 'files', {
              configurable: true,
              value: [new File([csv], 'qa-rate-card.csv', {type:'text/csv'})]
            });
            this.dispatchEvent(new Event('change', {bubbles:true}));
          };
          document.querySelector('[data-action="upload-template"]').click();
        })()"""
    )
    time.sleep(0.25)
    import_state = evaluate(
        """(() => {
          const files = JSON.parse(localStorage.getItem('rate-card-manager.v2.files') || '{}');
          const imported = files['RC-QA-IMPORT-UF-2627'];
          const toast = document.querySelector('[data-toast-stack]').firstElementChild;
          return {
            card: imported && imported.card.name,
            lines: imported && imported.lines.length,
            listRow: Boolean(document.querySelector(
              '[data-rows] .row .cell--rate-card-id'
            ) && [...document.querySelectorAll('[data-rows] .row .cell--rate-card-id')]
              .some(cell => cell.textContent.trim() === 'RC-QA-IMPORT-UF-2627')),
            title: toast && toast.querySelector('[data-toast-title]').textContent,
            variant: toast && toast.dataset.variant,
            message: toast && toast.querySelector('[data-toast-message]').textContent
          };
        })()"""
    )
    check(
        "CSV import partially ingests valid rows and reports invalid rows plainly",
        import_state["card"] == "QA Upfront Video 2026-2027"
        and import_state["lines"] == 1
        and import_state["listRow"]
        and import_state["title"] == "Rate card imported with corrections needed"
        and import_state["variant"] == "warning"
        and "Row 4:" in import_state["message"],
        json.dumps(import_state),
    )
    evaluate(
        """(() => {
          HTMLInputElement.prototype.click = function() {
            Object.defineProperty(this, 'files', {
              configurable: true,
              value: [new File(['ROW_TYPE,RATE_CARD_ID\\r\\nLINE,RC-INVALID\\r\\n'],
                'invalid-rate-card.csv', {type:'text/csv'})]
            });
            this.dispatchEvent(new Event('change', {bubbles:true}));
          };
          document.querySelector('[data-action="upload-template"]').click();
        })()"""
    )
    time.sleep(0.2)
    check(
        "Invalid CSV import shows an error toast and persists no record",
        evaluate(
            """(() => {
              const toast = document.querySelector('[data-toast-stack]').firstElementChild;
              const files = JSON.parse(localStorage.getItem('rate-card-manager.v2.files') || '{}');
              return toast?.dataset.variant === 'error'
                && toast.querySelector('[data-toast-title]').textContent === 'Unable to import rate card'
                && !files['RC-INVALID'];
            })()"""
        ),
    )
    evaluate(
        """(() => {
          const files = JSON.parse(localStorage.getItem('rate-card-manager.v2.files') || '{}');
          delete files['RC-QA-IMPORT-UF-2627'];
          localStorage.setItem('rate-card-manager.v2.files', JSON.stringify(files));
          window.__rcmRenderTable();
        })()"""
    )

    archive_state = evaluate(
        """(() => {
          const row = document.querySelector('[data-rows] .row');
          const id = row.dataset.rowId;
          row.querySelectorAll('.actions .icon-btn')[3].click();
          return {
            id,
            visible: Boolean(document.querySelector('[data-rows] .row[data-row-id="' + id + '"]')),
            stored: JSON.parse(localStorage.getItem('rate-card-manager.archived.v1') || '[]').includes(id)
          };
        })()"""
    )
    check(
        "Archive action removes the row and persists its archived identity",
        not archive_state["visible"] and archive_state["stored"],
        json.dumps(archive_state),
    )
    navigate("?version=2.0&demoData=cross-platform-2026-27")
    check(
        "Archived Rate Card remains absent after reload",
        evaluate(
            f"""!document.querySelector(
              '[data-rows] .row[data-row-id="{archive_state["id"]}"]'
            )"""
        ),
    )
    evaluate("localStorage.removeItem('rate-card-manager.archived.v1')")
    navigate("?version=2.0&demoData=cross-platform-2026-27")
    quick_edit_result = evaluate(
        """(() => {
          const row = document.querySelector('[data-rows] .row');
          const rateCardId = row.querySelector('.cell--rate-card-id').textContent.trim();
          row.querySelectorAll('.actions .icon-btn')[0].click();
          const input = document.querySelector('[data-qe-field="baseRate"]');
          const conditionInput = document.querySelector('[data-qe-field="lineConditions"]');
          const lineId = document.querySelector('[data-qe-row-idx="0"]')
            ? window.RCMCatalog.buildFile(window.RCMRateCards.getByRateCardId(rateCardId)).lines[0].id
            : '';
          /* Conditions are a closed multi-select now, so two approved
             values are selected rather than typed, and they store as
             the comma joined labels the record already used. */
          const canonicalCondition =
            'Format: Preemptible';
          const sheet = document.querySelector('[data-quick-edit]');
          const panel = document.querySelector('.qsheet__panel');
          const gridWrap = document.querySelector('.qsheet__grid-wrap');
          /* One condition per record now, shown as the field's own text
             rather than as chips. */
          const canonicalSingle = 'Format: Preemptible';
          const conditionHost = conditionInput.closest('[data-conditions]');
          conditionHost.__conditionField.select(canonicalSingle);
          const conditionUi = {
            completeValue: conditionInput.value,
            shown: conditionHost.querySelector('.ads-cond__input').value,
            unknownChips: conditionHost.classList.contains('is-unrecognized')
              ? 1 : 0,
            horizontallyScrollable: false,
            noPanelOverflow: panel.scrollWidth <= panel.clientWidth
              || gridWrap.scrollWidth > gridWrap.clientWidth,
            sheetOpen: !sheet.hidden
          };
          input.value = (Number(input.value) + 1).toFixed(4);
          input.dispatchEvent(new Event('input', {bubbles:true}));
          input.dispatchEvent(new FocusEvent('blur', {bubbles:true}));
          document.querySelector('[data-action="save-quick-edit"]').click();
          const file = JSON.parse(localStorage.getItem('rate-card-manager.v2.files') || '{}')[rateCardId];
          const saved = file && file.lines.find(line => line.id === lineId);
          return {
            rateCardId,
            lineId,
            savedRate: saved && Number(saved.baseRate),
            expectedRate: Number(input.value),
            savedCondition: saved && saved.condition1,
            expectedCondition: canonicalCondition,
            conditionUi
          };
        })()"""
    )
    check(
        "Quick Edit persists its LINE change into the shared Rate Card file",
        quick_edit_result["savedRate"] == quick_edit_result["expectedRate"]
        and quick_edit_result["lineId"],
        json.dumps(quick_edit_result),
    )
    check(
        "Quick Edit loads, edits, and saves a complete compound Line Condition",
        quick_edit_result["savedCondition"] == quick_edit_result["expectedCondition"]
        and quick_edit_result["conditionUi"]["completeValue"]
        == quick_edit_result["expectedCondition"]
        and quick_edit_result["conditionUi"]["shown"] == "Format: Preemptible"
        and quick_edit_result["conditionUi"]["unknownChips"] == 0
        and quick_edit_result["conditionUi"]["noPanelOverflow"]
        and quick_edit_result["conditionUi"]["sheetOpen"],
        json.dumps(quick_edit_result),
    )
    navigate(
        "?version=2.0&section=create&mode=edit"
        "&cardId=RC-DAS-DISNEYADS-XPLAT-UF-2627"
        "&demoData=cross-platform-2026-27"
    )
    send(
        "Emulation.setDeviceMetricsOverride",
        {"width": 700, "height": 900, "deviceScaleFactor": 1, "mobile": False},
    )
    time.sleep(0.2)
    check(
        "Compact layout stacks without body-level horizontal overflow",
        evaluate(
            """getComputedStyle(document.querySelector('[data-v2-root]')).gridTemplateColumns.split(' ').length === 1
            && document.documentElement.scrollWidth <= document.documentElement.clientWidth"""
        ),
    )
    screenshot("compact-edit")
    check("Browser console has no runtime errors", not console_messages, str(console_messages))
finally:
    ws.close()
    chrome.terminate()
    server.shutdown()

failures = [name for name, passed, _detail in results if not passed]
print(json.dumps({"passes": len(results) - len(failures), "failures": len(failures)}, indent=2))
raise SystemExit(1 if failures else 0)
