"""Focused test for the v2.1 Premiums experience on the WPP Streaming
Video Upfront rate card (Figma 697:3617, 697:3618, 697:3889-3891).

Covers the premium dataset record by record, the table's column order and
sorting, checkbox selection and the indigo action bar, the Premium Details
panel, and pagination derived from the filtered count. Nothing here samples:
every premium in the file is validated individually, and every page of the
table is walked.

Line Items behavior is out of scope and belongs to qa_line_details_default.py
and qa_smoke_line_panel.py; this suite only asserts that tab still renders.
"""

import atexit
import base64
import json
import os
import shutil
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import urlopen

import websocket

ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = 9031
DEBUG_PORT = 9331
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
OUT = "/tmp/rate-card-premiums-experience"
VIEWPORT = (1600, 1000)
CARD_ID = "RC-DAS-WPP-VIDEO-UF-2627"
EXPECTED_PREMIUMS = 18

CATEGORIES = ["1P Audience", "3P Audience", "Content", "Commitment",
              "Device Type", "Format", "Geo", "Seasonality"]
METHODS = ["Additive CPM", "Percent Adjustment"]
OFFERINGS = ["Hulu Select", "Disney+ Select", "Disney Streaming Bundle",
             "ESPN Streaming Sports", "Disney Streaming Live Events"]
# Names retired by earlier data passes. None may survive anywhere in the
# premium book.
RETIRED_NAMES = ["HomeCraft", "Silverline Studios", "Elevate Sportswear",
                 "Redwood Health", "Aurora Beauty", "BluePeak Beverages",
                 "BrightWave Telecom", "CloudNine Airlines"]

shutil.rmtree(OUT, ignore_errors=True)
os.makedirs(OUT, exist_ok=True)


class StaticHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0] or "/index.html"
        if path == "/":
            path = "/index.html"
        filename = os.path.join(ROOT, path.lstrip("/"))
        if not os.path.isfile(filename):
            self.send_response(404)
            self.end_headers()
            return
        content_type = {
            ".html": "text/html", ".css": "text/css", ".js": "application/javascript",
            ".svg": "image/svg+xml", ".png": "image/png", ".json": "application/json",
        }.get(os.path.splitext(filename)[1], "text/plain")
        with open(filename, "rb") as handle:
            payload = handle.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, *_args):
        return


server = ThreadingHTTPServer(("127.0.0.1", PORT), StaticHandler)
threading.Thread(target=server.serve_forever, daemon=True).start()

profile = "/tmp/rate_card_premiums_experience_profile"
shutil.rmtree(profile, ignore_errors=True)
os.makedirs(profile, exist_ok=True)
chrome = subprocess.Popen(
    [
        CHROME, f"--remote-debugging-port={DEBUG_PORT}", f"--user-data-dir={profile}",
        "--disk-cache-dir=/dev/null", "--headless=new", "--remote-allow-origins=*",
        "--no-first-run", "--force-device-scale-factor=1",
        f"--window-size={VIEWPORT[0]},{VIEWPORT[1]}", "about:blank",
    ],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)

atexit.register(lambda: chrome.terminate() if chrome.poll() is None else None)
atexit.register(lambda: server.shutdown())

ws = None
for _ in range(80):
    try:
        tabs = json.loads(urlopen(f"http://127.0.0.1:{DEBUG_PORT}/json").read())
        page = next(t for t in tabs if t.get("type") == "page")
        ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=30)
        break
    except Exception:
        time.sleep(0.25)
if ws is None:
    raise RuntimeError("chrome failed to boot")

message_id = 0
failures = []
passes = 0
console_errors = []


def send(method, params=None):
    global message_id
    message_id += 1
    expected = message_id
    ws.send(json.dumps({"id": expected, "method": method, "params": params or {}}))
    while True:
        event = json.loads(ws.recv())
        if event.get("id") == expected:
            return event


def E(expression):
    result = send("Runtime.evaluate", {
        "expression": expression, "returnByValue": True, "awaitPromise": True})
    payload = result.get("result", {})
    if "exceptionDetails" in payload:
        raise RuntimeError(json.dumps(payload["exceptionDetails"])[:600])
    return payload.get("result", {}).get("value")


def check(name, condition, detail=""):
    global passes
    if condition:
        passes += 1
        print(f"[PASS] {name}")
    else:
        failures.append({"name": name, "detail": str(detail)})
        print(f"[FAIL] {name}: {detail}")


def wait_for(expression, timeout=8):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if E(expression):
                return True
        except RuntimeError:
            pass
        time.sleep(0.1)
    return False


def shot(name):
    payload = send("Page.captureScreenshot", {"format": "png"})
    data = payload.get("result", {}).get("data", "")
    with open(os.path.join(OUT, name + ".png"), "wb") as handle:
        handle.write(base64.b64decode(data))


send("Runtime.enable")
send("Log.enable")


def drain_console():
    ws.settimeout(0.05)
    try:
        while True:
            evt = json.loads(ws.recv())
            method = evt.get("method")
            if method == "Runtime.exceptionThrown":
                console_errors.append(json.dumps(evt["params"])[:400])
            elif method == "Log.entryAdded":
                entry = evt["params"].get("entry", {})
                if entry.get("level") == "error":
                    console_errors.append(entry.get("text", "")[:400])
    except Exception:
        pass
    finally:
        ws.settimeout(None)


send("Emulation.setDeviceMetricsOverride", {
    "width": VIEWPORT[0], "height": VIEWPORT[1], "deviceScaleFactor": 1, "mobile": False})
send("Page.navigate", {
    "url": f"http://127.0.0.1:{PORT}/index.html"
          f"?version=2.1&section=create&mode=edit&cardId={CARD_ID}"})
wait_for("document.body.dataset.version === '2.1'")
wait_for("document.querySelectorAll('[data-v2-tbody=\"lines\"] tr[data-v2-row-id]').length > 0")
time.sleep(0.5)

# The premium book is exported for the download assertion later, and
# swapping the CSV writer for a recorder keeps a real file off disk.
E("""(() => {
  window.__csv = null;
  const real = window.rcmDownloadCsv;
  window.rcmDownloadCsv = function (name, csv) { window.__csv = { name: name, csv: csv }; };
  window.__realDownload = real;
})()""")

# Switch to the Premiums tab the way a user does.
E("""document.querySelector('[data-v2-tab="premiums"]').click()""")
wait_for("document.querySelectorAll('[data-v2-tbody=\"premiums\"] tr[data-v2-row-id]').length > 0")
time.sleep(0.4)
drain_console()

# =====================================================================
#  1. The dataset, record by record
# =====================================================================
print("\n--- 1. Premium dataset ---")

# The edit page builds a seeded card from the catalog and only writes it to
# storage once the user saves, so the audit reads whichever copy is live:
# the saved file if there is one, otherwise the catalog build the page is
# rendering from.
DATA = """(() => {
  const files = JSON.parse(localStorage.getItem('rate-card-manager.v2.files') || '{}');
  const record = window.RCMRateCards.getByRateCardId(%s);
  const file = files[%s] || (record && window.RCMCatalog.buildFile(record));
  if (!file) return { missing: true };
  const byId = {};
  (file.lines || []).forEach((l) => { byId[l.id] = l; });
  const advertisers = {};
  (file.lines || []).forEach((l) => { advertisers[l.advertiserName] = l.advertiserId; });
  return {
    card: file.card,
    advertisers: advertisers,
    premiums: (file.premiums || []).map((p) => ({
      id: p.id,
      displayName: p.displayName,
      category: p.category,
      calculationMethod: p.calculationMethod,
      value: p.value,
      stackOrder: p.stackOrder,
      baseOffering: p.baseOffering,
      condition1: p.condition1,
      advertiserScope: p.advertiserScope,
      advertiserId: p.advertiserId,
      advertiserName: p.advertiserName,
      effectiveStart: p.effectiveStart,
      effectiveEnd: p.effectiveEnd,
      attachToCard: p.attachToCard,
      lineItemIds: p.lineItemIds || [],
      attachedOfferings: (p.lineItemIds || [])
        .map((id) => byId[id] && byId[id].baseOffering).filter(Boolean),
      attachedAdvertisers: (p.lineItemIds || [])
        .map((id) => byId[id] && byId[id].advertiserId).filter(Boolean),
    })),
  };
})()""" % (json.dumps(CARD_ID), json.dumps(CARD_ID))

data = E(DATA)
check("the WPP rate card file is present", not data.get("missing"), data)
premiums = data["premiums"]
roster = data["advertisers"]

check(f"the premium book holds {EXPECTED_PREMIUMS} records",
      len(premiums) == EXPECTED_PREMIUMS, len(premiums))

# Every record is inspected on its own so a failure names the row.
record_failures = []
seen_ids = {}
seen_rules = {}
for index, p in enumerate(premiums):
    label = f"#{index + 1} {p['displayName'] or p['id']}"

    def bad(field, reason):
        record_failures.append(f"{label} [{field}]: {reason}")

    if not p["id"]:
        bad("id", "missing")
    elif p["id"] in seen_ids:
        bad("id", f"duplicate of record #{seen_ids[p['id']] + 1}")
    else:
        seen_ids[p["id"]] = index

    if not p["displayName"]:
        bad("displayName", "missing")
    for retired in RETIRED_NAMES:
        if retired.lower() in json.dumps(p).lower():
            bad("record", f"still carries retired name {retired}")

    if p["category"] not in CATEGORIES:
        bad("category", f"{p['category']!r} is not a controlled category")
    if p["calculationMethod"] not in METHODS:
        bad("calculationMethod", f"{p['calculationMethod']!r} is not a controlled method")

    value = p["value"]
    if not isinstance(value, (int, float)):
        bad("value", f"{value!r} is not numeric")
    elif value <= 0:
        bad("value", f"{value} is not a positive adjustment")
    elif p["calculationMethod"] == "Additive CPM" and value > 25:
        bad("value", f"${value} CPM is not credible as an additive premium")
    elif p["calculationMethod"] == "Percent Adjustment" and value > 100:
        bad("value", f"{value}% is not a credible percent adjustment")

    order = p["stackOrder"]
    if not isinstance(order, (int, float)) or order <= 0 or int(order) != order:
        bad("stackOrder", f"{order!r} is not a positive integer")

    offerings = [o.strip() for o in (p["baseOffering"] or "").split(",") if o.strip()]
    if not offerings:
        bad("baseOffering", "no offering named")
    for offering in offerings:
        if offering not in OFFERINGS:
            bad("baseOffering", f"{offering!r} is not a canonical offering")
    for attached in p["attachedOfferings"]:
        if attached not in offerings:
            bad("lineItemIds", f"attached rule prices {attached!r}, outside this premium")

    condition = p["condition1"] or ""
    if ":" not in condition:
        bad("condition1", f"{condition!r} is not a readable business rule")

    for field in ("effectiveStart", "effectiveEnd"):
        if not p[field] or len(p[field]) != 10 or p[field][4] != "-":
            bad(field, f"{p[field]!r} is not an ISO date")
    if p["effectiveStart"] and p["effectiveEnd"] and p["effectiveEnd"] < p["effectiveStart"]:
        bad("effectiveEnd", "ends before it starts")
    card = data["card"]
    if p["effectiveStart"] and p["effectiveStart"] < card["effectiveStart"]:
        bad("effectiveStart", "starts before the rate card does")
    if p["effectiveEnd"] and p["effectiveEnd"] > card["effectiveEnd"]:
        bad("effectiveEnd", "ends after the rate card does")

    if p["advertiserScope"] not in ("card", "advertiser"):
        bad("advertiserScope", f"{p['advertiserScope']!r} is neither card-wide nor scoped")
    elif p["advertiserScope"] == "card":
        if p["advertiserId"] or p["advertiserName"]:
            bad("advertiserScope", "card-wide but still carries an advertiser")
    else:
        if not p["advertiserId"]:
            bad("advertiserId", "advertiser-scoped with no stable ID")
        if p["advertiserName"] not in roster:
            bad("advertiserName",
                f"{p['advertiserName']!r} is not an advertiser in this card's line items")
        elif roster[p["advertiserName"]] != p["advertiserId"]:
            bad("advertiserId",
                f"{p['advertiserId']} does not match the roster ID {roster[p['advertiserName']]}")
        for attached in p["attachedAdvertisers"]:
            if attached != p["advertiserId"]:
                bad("lineItemIds", "attached to another advertiser's rule")

    if p["attachToCard"] != CARD_ID:
        bad("attachToCard", f"{p['attachToCard']!r} is not this rate card")

    rule = (p["category"], p["calculationMethod"], p["value"],
            p["baseOffering"], p["condition1"], p["advertiserId"])
    if rule in seen_rules:
        bad("record", f"is an exact duplicate rule of #{seen_rules[rule] + 1}")
    else:
        seen_rules[rule] = index

check(f"all {len(premiums)} premiums pass every field rule individually",
      not record_failures, "\n      " + "\n      ".join(record_failures[:25]))

scoped = [p for p in premiums if p["advertiserScope"] == "advertiser"]
check("advertiser scope is used selectively, not as filler",
      0 < len(scoped) < len(premiums), f"{len(scoped)} of {len(premiums)} scoped")

# =====================================================================
#  2. Table structure and rendering
# =====================================================================
print("\n--- 2. Table structure ---")

TABLE = """(() => {
  const region = document.querySelector('[data-v2-table-region="premiums"]');
  const heads = [...region.querySelectorAll('thead th')];
  const rows = [...region.querySelectorAll('tbody tr[data-v2-row-id]')];
  const clipped = [];
  rows.forEach((r) => {
    r.querySelectorAll('td').forEach((td) => {
      if (td.scrollWidth > td.clientWidth + 1 && !td.getAttribute('data-tooltip')) {
        clipped.push(r.getAttribute('data-v2-row-id') + ' / ' + td.textContent.trim());
      }
    });
  });
  /* 697:3617 has no Advertiser column. Its <th>/<td> stay in the DOM so
     the positional column widths keep counting from the same places, so
     everything column-shaped here reads what is actually visible. */
  const shown = heads.filter((th) => th.offsetParent !== null
    || th.classList.contains('create-md__th-checkbox'));
  return {
    headers: shown.map((th) => th.textContent.trim()),
    ariaSort: shown.map((th) => th.getAttribute('aria-sort')),
    sortable: shown.map((th) => th.getAttribute('data-v2-sort-header')),
    advertiserColumnShown: heads.some((th) => th.textContent.trim() === 'Advertiser'
      && th.offsetParent !== null),
    checkboxHeader: Boolean(region.querySelector('[data-v2-checkbox-header="premiums"] input')),
    rowCount: rows.length,
    rowIds: rows.map((r) => r.getAttribute('data-v2-row-id')),
    firstRowCells: rows.length ? [...rows[0].querySelectorAll('td')]
      .map((td) => td.textContent.trim()) : [],
    rowCheckboxes: rows.filter((r) => r.querySelector('input[type=checkbox]')).length,
    checkboxLabels: rows.filter((r) => {
      const box = r.querySelector('input[type=checkbox]');
      return box && (box.getAttribute('aria-label') || '').trim().length > 0;
    }).length,
    clipped: clipped,
    total: document.querySelector('[data-v2-total="premiums"]').textContent,
    tabLabel: document.querySelector('[data-v2-tab="premiums"]').getAttribute('aria-label'),
    searchPlaceholder: document.querySelector('[data-v2-search="premiums"]').placeholder,
    addLabel: (document.querySelector('[data-v2-panel="premiums"] [data-v2-action="add-premium"]')
      || {}).textContent,
  };
})()"""

t = E(TABLE)
shot("01-premiums-default")
check("the table renders as a real table with a checkbox column plus five data columns",
      t["headers"] == ["", "Premium", "Base offering", "Category", "Value",
                       "Calculation method"],
      t["headers"])
check("Advertiser is not repeated on every premium row",
      t["advertiserColumnShown"] is False, t["advertiserColumnShown"])
check("every data column is sortable and the checkbox column is not",
      t["sortable"][0] is None and all(t["sortable"][1:]), t["sortable"])
check("sortable headers expose aria-sort",
      all(v in ("ascending", "descending", "none") for v in t["ariaSort"][1:]),
      t["ariaSort"])
check("the header carries a select-all checkbox", t["checkboxHeader"])
check("page 1 shows ten premiums", t["rowCount"] == 10, t["rowCount"])
check("every row has a checkbox with an accessible name",
      t["rowCheckboxes"] == t["rowCount"] and t["checkboxLabels"] == t["rowCount"],
      {"boxes": t["rowCheckboxes"], "labels": t["checkboxLabels"]})
check("the footer reports the real premium count",
      t["total"] == str(EXPECTED_PREMIUMS), t["total"])
check("the tab announces the real premium count",
      f"{EXPECTED_PREMIUMS} premiums" in (t["tabLabel"] or ""), t["tabLabel"])
check("the search field uses the Figma placeholder",
      t["searchPlaceholder"] == "Search premiums", t["searchPlaceholder"])
check("Add Premium is available", (t["addLabel"] or "").strip() == "Add Premium", t["addLabel"])
check("no premium cell is clipped without offering its full value",
      not t["clipped"], t["clipped"])

# Value renders at two decimals and carries no currency symbol.
values = E("""[...document.querySelectorAll('[data-v2-tbody="premiums"] tr[data-v2-row-id]')]
  .map((r) => r.querySelectorAll('td')[4].textContent.trim())""")
check("Value shows two decimals and no currency symbol",
      all(v.count(".") == 1 and len(v.split(".")[1]) == 2 and v.replace(".", "").isdigit()
          for v in values), values)

# =====================================================================
#  3. Sorting
# =====================================================================
print("\n--- 3. Sorting ---")


def sort_by(key):
    E(f"""document.querySelector('[data-v2-sort="premiums:{key}"]').click()""")
    time.sleep(0.25)


def column_values(column):
    """Row text minus the screen-reader-only "Selected." prefix the active
    detail row carries on its first cell."""
    return E(f"""[...document.querySelectorAll('[data-v2-tbody="premiums"] tr[data-v2-row-id]')]
      .map((r) => {{
        const td = r.querySelectorAll('td')[{column}].cloneNode(true);
        td.querySelectorAll('.sr-only').forEach((n) => n.remove());
        return td.textContent.trim();
      }})""")


SORT_COLUMNS = [
    ("displayName", 1, False), ("baseOffering", 2, False), ("category", 3, False),
    ("value", 4, True), ("calculationMethod", 5, False),
]
for key, column, numeric in SORT_COLUMNS:
    E("""(() => { const s = document.querySelector('[data-v2-page="premiums:1"]');
      if (s) s.click(); })()""")
    time.sleep(0.15)
    # Park the sort on another column first, so the column under test is
    # always inactive when it takes its first click.
    sort_by("displayName" if key == "value" else "value")
    sort_by(key)
    asc = column_values(column)
    state_asc = E(f"""document.querySelector('[data-v2-sort-header="premiums:{key}"]')
      .getAttribute('aria-sort')""")
    page_after_sort = E("""(() => {
      const active = document.querySelector('[data-v2-page][aria-current="page"]');
      return active ? active.textContent.trim() : null;
    })()""")
    sort_by(key)
    desc = column_values(column)
    state_desc = E(f"""document.querySelector('[data-v2-sort-header="premiums:{key}"]')
      .getAttribute('aria-sort')""")
    if numeric:
        ordered_asc = [float(v) for v in asc] == sorted(float(v) for v in asc)
        ordered_desc = [float(v) for v in desc] == sorted(
            (float(v) for v in desc), reverse=True)
    else:
        ordered_asc = [v.lower() for v in asc] == sorted(v.lower() for v in asc)
        ordered_desc = [v.lower() for v in desc] == sorted(
            (v.lower() for v in desc), reverse=True)
    check(f"{key} sorts ascending then descending",
          ordered_asc and ordered_desc, {"asc": asc[:4], "desc": desc[:4]})
    check(f"{key} reports its direction through aria-sort",
          state_asc == "ascending" and state_desc == "descending",
          {"asc": state_asc, "desc": state_desc})
    check(f"{key} sorting returns to page 1", page_after_sort == "1", page_after_sort)

# Back to the default order for the rest of the run.
E("""document.querySelector('[data-v2-sort="premiums:displayName"]').click()""")
time.sleep(0.25)

# =====================================================================
#  3b. Sortable header icon reveal (Figma 697:3635)
# =====================================================================
# 697:3635 rests the header row as labels only and reveals the
# Arrow-Down&Up glyph on the one header under the pointer. Keyboard focus
# stands in for hover, and neither may move anything on screen.
print("\n--- 3b. Sortable header icon reveal ---")

# Every sortable header, read together, so "only the hovered one" is a
# claim about the whole row rather than one column at a time. The label is
# measured through a Range over the button's own text node: it moves by a
# subpixel if the icon ever changes the flex layout around it.
HEADER_ICONS = """(() => {
  const out = {};
  document.querySelectorAll(
    '[data-v2-table-region="premiums"] thead th[data-v2-sort-header]'
  ).forEach((th) => {
    if (th.offsetParent === null) return;
    const button = th.querySelector('[data-v2-sort]');
    const icon = button.querySelector('.th__sort');
    const style = getComputedStyle(icon);
    const range = document.createRange();
    range.selectNodeContents(button.firstChild);
    const label = range.getBoundingClientRect();
    const box = icon.getBoundingClientRect();
    const cell = th.getBoundingClientRect();
    out[th.getAttribute('data-v2-sort-header').split(':')[1]] = {
      shown: style.visibility === 'visible' && Number(style.opacity) > 0,
      ariaSort: th.getAttribute('aria-sort'),
      ariaHidden: icon.getAttribute('aria-hidden'),
      focusable: !!icon.querySelector('[tabindex], a, button'),
      geometry: [
        Math.round(label.left), Math.round(label.right),
        Math.round(box.left), Math.round(box.width), Math.round(box.height),
        Math.round(cell.left), Math.round(cell.right),
      ],
      clipped: Math.round(box.left) < Math.round(label.right)
        || Math.round(box.right) > Math.round(cell.right),
    };
  });
  return out;
})()"""

SORT_KEYS = [key for key, _column, _numeric in SORT_COLUMNS]


def blur_headers():
    E("""(() => { const a = document.activeElement;
      if (a && a !== document.body) a.blur(); })()""")


def park_pointer():
    """Off every header, but still inside the page, so the browser holds a
    real hover target rather than an undefined one."""
    send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": 4, "y": 4,
                                      "buttons": 0})
    time.sleep(0.15)


def header_box(key):
    return E(f"""(() => {{
      const b = document.querySelector('[data-v2-sort="premiums:{key}"]');
      b.scrollIntoView({{block: 'center'}});
      const r = b.getBoundingClientRect();
      const icon = b.querySelector('.th__sort').getBoundingClientRect();
      return {{
        labelX: r.left + 6, iconX: icon.left + icon.width / 2,
        y: r.top + r.height / 2,
      }};
    }})()""")


def hover(key):
    box = header_box(key)
    send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": box["labelX"],
                                      "y": box["y"], "buttons": 0})
    time.sleep(0.15)
    return box


def click_at(x, y):
    for kind in ("mousePressed", "mouseReleased"):
        send("Input.dispatchMouseEvent", {
            "type": kind, "x": x, "y": y, "button": "left", "clickCount": 1,
            "buttons": 1 if kind == "mousePressed" else 0})
    time.sleep(0.3)


def press(key):
    codes = {"Enter": (13, "Enter", "\r"), " ": (32, "Space", " ")}
    code, name, text = codes[key]
    common = {"windowsVirtualKeyCode": code, "nativeVirtualKeyCode": code,
              "key": key, "code": name}
    send("Input.dispatchKeyEvent", dict(common, type="rawKeyDown"))
    send("Input.dispatchKeyEvent", dict(common, type="char", text=text))
    send("Input.dispatchKeyEvent", dict(common, type="keyUp"))
    time.sleep(0.3)


def active_sort():
    return E("""(() => {
      const th = document.querySelector(
        '[data-v2-table-region="premiums"] thead th[aria-sort="ascending"],'
        + '[data-v2-table-region="premiums"] thead th[aria-sort="descending"]');
      return th ? th.getAttribute('data-v2-sort-header').split(':')[1]
        + ':' + th.getAttribute('aria-sort') : null;
    })()""")


def close_premium_panel():
    E("""(() => {
      const close = document.querySelector('[data-v2-action="close-panel"]');
      if (close && document.querySelector('.create-md').classList.contains(
        'is-panel-open')) close.click();
    })()""")
    time.sleep(0.4)


def open_premium_panel():
    E("""(() => {
      const row = document.querySelector(
        '[data-v2-tbody="premiums"] tr[data-v2-row-id] td:nth-child(4)');
      if (row && !document.querySelector('.create-md').classList.contains(
        'is-panel-open')) row.click();
    })()""")
    time.sleep(0.4)


# displayName is still the active sort from the reset above, so the default
# state below is read with a column genuinely sorted: the icon has to stay
# hidden there too, which is the whole point of the override.
for panel in ("closed", "open"):
    close_premium_panel() if panel == "closed" else open_premium_panel()
    park_pointer()
    blur_headers()
    time.sleep(0.2)
    rest = E(HEADER_ICONS)
    check(f"[{panel}] all five sortable headers are present",
          sorted(rest.keys()) == sorted(SORT_KEYS), sorted(rest.keys()))
    check(f"[{panel}] no sorting icon is visible at rest, including on the "
          "sorted column",
          all(not v["shown"] for v in rest.values()),
          {k: v["shown"] for k, v in rest.items()})
    check(f"[{panel}] a column is still actively sorted while its icon is hidden",
          rest["displayName"]["ariaSort"] == "ascending"
          and not rest["displayName"]["shown"], rest["displayName"])
    check(f"[{panel}] the hidden icon is not a second control for assistive tech",
          all(v["ariaHidden"] == "true" and not v["focusable"]
              for v in rest.values()),
          {k: (v["ariaHidden"], v["focusable"]) for k, v in rest.items()})
    check(f"[{panel}] the icon box is reserved at rest, not collapsed",
          all(v["geometry"][3] == 12 and v["geometry"][4] == 12
              for v in rest.values()),
          {k: v["geometry"][3:5] for k, v in rest.items()})

    for key in SORT_KEYS:
        hover(key)
        hovered = E(HEADER_ICONS)
        check(f"[{panel}] hovering {key} reveals its icon",
              hovered[key]["shown"], hovered[key])
        check(f"[{panel}] hovering {key} reveals no other column's icon",
              [k for k, v in hovered.items() if v["shown"]] == [key],
              [k for k, v in hovered.items() if v["shown"]])
        check(f"[{panel}] revealing {key}'s icon moves nothing",
              all(hovered[k]["geometry"] == rest[k]["geometry"] for k in rest),
              {k: (rest[k]["geometry"], hovered[k]["geometry"])
               for k in rest if hovered[k]["geometry"] != rest[k]["geometry"]})
        check(f"[{panel}] {key}'s icon clears its label and stays inside the cell",
              not hovered[key]["clipped"], hovered[key])
        park_pointer()
        check(f"[{panel}] leaving {key} hides its icon again",
              not E(HEADER_ICONS)[key]["shown"])

        E(f"""document.querySelector('[data-v2-sort="premiums:{key}"]').focus()""")
        time.sleep(0.15)
        focused = E(HEADER_ICONS)
        check(f"[{panel}] keyboard focus on {key} reveals its icon",
              focused[key]["shown"], focused[key])
        check(f"[{panel}] focus on {key} reveals no other column's icon",
              [k for k, v in focused.items() if v["shown"]] == [key],
              [k for k, v in focused.items() if v["shown"]])
        check(f"[{panel}] focus on {key} moves nothing",
              all(focused[k]["geometry"] == rest[k]["geometry"] for k in rest),
              {k: (rest[k]["geometry"], focused[k]["geometry"])
               for k in rest if focused[k]["geometry"] != rest[k]["geometry"]})
        blur_headers()
        time.sleep(0.15)
        check(f"[{panel}] blurring {key} hides its icon again",
              not E(HEADER_ICONS)[key]["shown"])

    # The table body has to keep sitting under the same column edges the
    # header row draws, in both panel widths.
    alignment = E("""(() => {
      const cells = (row, tag) => [...row.querySelectorAll(tag)]
        .filter((c) => c.offsetParent !== null)
        .map((c) => Math.round(c.getBoundingClientRect().left));
      const head = document.querySelector(
        '[data-v2-table-region="premiums"] thead tr');
      const body = document.querySelector(
        '[data-v2-tbody="premiums"] tr[data-v2-row-id]');
      return {head: cells(head, 'th'), body: cells(body, 'td')};
    })()""")
    check(f"[{panel}] every body cell starts on its own header's edge",
          alignment["head"] == alignment["body"], alignment)

close_premium_panel()
park_pointer()
blur_headers()

# The checkbox column is a selection control, not a sortable header.
checkbox_header = E("""(() => {
  const th = document.querySelector(
    '[data-v2-table-region="premiums"] thead th.create-md__th-checkbox');
  return {
    exists: !!th,
    sortButtons: th ? th.querySelectorAll('[data-v2-sort]').length : -1,
    sortIcons: th ? th.querySelectorAll('.th__sort').length : -1,
    ariaSort: th ? th.getAttribute('aria-sort') : 'missing',
    hasCheckbox: th ? !!th.querySelector('input[type=checkbox]') : false,
  };
})()""")
check("the checkbox header offers selection and never a sort icon",
      checkbox_header["exists"] and checkbox_header["sortButtons"] == 0
      and checkbox_header["sortIcons"] == 0
      and checkbox_header["ariaSort"] is None
      and checkbox_header["hasCheckbox"], checkbox_header)

# Both halves of the hit area sort, not just the glyph, and both keys the
# button contract owes activate it.
for key in SORT_KEYS:
    # Park the sort on another column, then walk off page 1, so the column
    # under test always takes its first activation from inactive and has a
    # page to be pulled back from.
    parked = "value" if key != "value" else "displayName"
    E(f"""document.querySelector('[data-v2-sort="premiums:{parked}"]').click()""")
    time.sleep(0.2)
    E("""document.querySelector('[data-v2-page="premiums:2"]')?.click()""")
    time.sleep(0.2)
    box = hover(key)
    click_at(box["labelX"], box["y"])
    after_label = active_sort()
    page_after = E("""(() => {
      const active = document.querySelector(
        '[data-v2-pagination="premiums"] [data-v2-page][aria-current="page"]');
      return active ? active.textContent.trim() : null;
    })()""")
    check(f"clicking {key}'s label sorts it ascending",
          after_label == key + ":ascending", after_label)
    check(f"sorting {key} by pointer returns to page 1", page_after == "1",
          page_after)
    box = header_box(key)
    click_at(box["iconX"], box["y"])
    check(f"clicking {key}'s icon area reverses it to descending",
          active_sort() == key + ":descending", active_sort())
    park_pointer()

    E(f"""document.querySelector('[data-v2-sort="premiums:{key}"]').focus()""")
    time.sleep(0.15)
    press("Enter")
    check(f"Enter re-sorts {key} ascending",
          active_sort() == key + ":ascending", active_sort())
    press(" ")
    check(f"Space re-sorts {key} descending",
          active_sort() == key + ":descending", active_sort())
    # The icon carried the direction for the whole keyboard sequence, then
    # gives it up the moment focus does.
    check(f"{key} keeps its icon while it holds focus",
          E(HEADER_ICONS)[key]["shown"])
    blur_headers()
    time.sleep(0.15)
    check(f"{key} stays sorted descending after its icon is hidden",
          active_sort() == key + ":descending"
          and not E(HEADER_ICONS)[key]["shown"], active_sort())

# Figma 697:3635 comparison shots: the resting row, then one header hovered.
park_pointer()
blur_headers()
E("""document.querySelector('[data-v2-sort="premiums:displayName"]').click()""")
time.sleep(0.3)
park_pointer()
blur_headers()
time.sleep(0.2)
shot("03a-headers-rest")
hover("category")
shot("03b-headers-hover-category")
park_pointer()
blur_headers()

# =====================================================================
#  4. Pagination derived from the filtered count
# =====================================================================
print("\n--- 4. Pagination ---")

PAGER = """(() => {
  const nav = document.querySelector('[data-v2-pagination="premiums"]');
  const buttons = [...nav.querySelectorAll('[data-v2-page]')];
  const goTo = document.querySelector('[data-v2-go-page="premiums"]');
  return {
    footerVisible: !document.querySelector(
      '[data-v2-table-region="premiums"] .create-md__table-footer').hidden,
    pages: buttons.filter((b) => b.classList.contains('create-md__pagination-item--page'))
      .map((b) => b.textContent.trim()),
    current: (nav.querySelector('[aria-current="page"]') || {}).textContent,
    prevDisabled: (nav.querySelector('.create-md__pagination-item--previous') || {}).disabled,
    nextDisabled: (nav.querySelector('.create-md__pagination-item--next') || {}).disabled,
    ellipses: nav.querySelectorAll('.create-md__pagination-ellipsis').length,
    goToOptions: goTo ? [...goTo.options].map((o) => o.value) : [],
    rowCount: document.querySelectorAll(
      '[data-v2-tbody="premiums"] tr[data-v2-row-id]').length,
  };
})()"""

p1 = E(PAGER)
check("18 records at page size 10 produce exactly two pages",
      p1["pages"] == ["1", "2"], p1["pages"])
check("no ellipsis is drawn for two pages", p1["ellipses"] == 0, p1["ellipses"])
check("Go to page offers only the pages that exist",
      p1["goToOptions"] == ["1", "2"], p1["goToOptions"])
check("Previous is disabled on the first page", p1["prevDisabled"] is True, p1["prevDisabled"])
check("Next is enabled on the first page", p1["nextDisabled"] is False, p1["nextDisabled"])
check("page 1 holds ten records", p1["rowCount"] == 10, p1["rowCount"])

page_one_ids = E("""[...document.querySelectorAll('[data-v2-tbody="premiums"] tr[data-v2-row-id]')]
  .map((r) => r.getAttribute('data-v2-row-id'))""")
E("""document.querySelector('[data-v2-page="premiums:2"]').click()""")
time.sleep(0.3)
p2 = E(PAGER)
page_two_ids = E("""[...document.querySelectorAll('[data-v2-tbody="premiums"] tr[data-v2-row-id]')]
  .map((r) => r.getAttribute('data-v2-row-id'))""")
shot("02-page-two")
check("page 2 holds the remaining eight records", p2["rowCount"] == 8, p2["rowCount"])
check("Next is disabled on the last page", p2["nextDisabled"] is True, p2["nextDisabled"])
check("Previous is enabled on the last page", p2["prevDisabled"] is False, p2["prevDisabled"])
check("the two pages together expose every premium without repeats",
      len(set(page_one_ids) | set(page_two_ids)) == EXPECTED_PREMIUMS
      and not set(page_one_ids) & set(page_two_ids),
      {"page1": len(page_one_ids), "page2": len(page_two_ids)})

# Page size changes recalculate the page count.
E("""(() => {
  const s = document.querySelector('[data-v2-page-size="premiums"]');
  s.value = '20';
  s.dispatchEvent(new Event('change', {bubbles: true}));
})()""")
time.sleep(0.3)
big = E(PAGER)
check("page size 20 collapses 18 records to one page and hides the footer",
      not big["footerVisible"] and big["rowCount"] == EXPECTED_PREMIUMS,
      {"footer": big["footerVisible"], "rows": big["rowCount"]})
E("""(() => {
  const s = document.querySelector('[data-v2-page-size="premiums"]');
  s.value = '10';
  s.dispatchEvent(new Event('change', {bubbles: true}));
})()""")
time.sleep(0.3)

# =====================================================================
#  5. Search
# =====================================================================
print("\n--- 5. Search ---")


def search(term):
    E("""(() => {
      const s = document.querySelector('[data-v2-search="premiums"]');
      s.value = %s;
      s.dispatchEvent(new Event('input', {bubbles: true}));
    })()""" % json.dumps(term))
    time.sleep(0.3)


SEARCH_STATE = """(() => ({
  rowCount: document.querySelectorAll('[data-v2-tbody="premiums"] tr[data-v2-row-id]').length,
  total: document.querySelector('[data-v2-total="premiums"]').textContent,
  current: (document.querySelector('[data-v2-pagination="premiums"] [aria-current="page"]')
    || {}).textContent,
  pages: [...document.querySelectorAll(
    '[data-v2-pagination="premiums"] .create-md__pagination-item--page')]
    .map((b) => b.textContent.trim()),
  noResults: !document.querySelector('[data-v2-no-results="premiums"]').hidden,
  noResultsCopy: document.querySelector('[data-v2-no-results="premiums"] h3').textContent,
  regionHidden: document.querySelector('[data-v2-table-region="premiums"]').hidden,
}))()"""

# Go to page 2 first, so a query has a stale page to reset.
E("""document.querySelector('[data-v2-page="premiums:2"]').click()""")
time.sleep(0.25)
search("geo")
s = E(SEARCH_STATE)
check("search matches Category case-insensitively",
      s["rowCount"] == 2 and s["total"] == "2", s)
check("search resets to page 1", s["current"] == "1" or not s["pages"], s)

search("  PERCENT adjustment  ")
s = E(SEARCH_STATE)
check("search trims whitespace and matches Calculation method",
      s["total"] == "5", s["total"])

# Three premiums price ESPN Streaming Sports: the two content adjustments
# and the sports-fan audience premium.
search("ESPN Streaming Sports")
check("search matches Base offering", E(SEARCH_STATE)["total"] == "3",
      E(SEARCH_STATE)["total"])

search("PRM-WPP-2615")
check("search matches the premium ID", E(SEARCH_STATE)["total"] == "1",
      E(SEARCH_STATE)["total"])

PERCENT_ADJUSTMENT_COUNT = sum(
    1 for p in premiums if p["calculationMethod"] == "Percent Adjustment")
search("Percent Adjustment")
check("search matches the Calculation method",
      E(SEARCH_STATE)["total"] == str(PERCENT_ADJUSTMENT_COUNT),
      E(SEARCH_STATE)["total"])

# A trigger fragment that appears in no display name, offering, category or
# method, so a hit can only have come from the Condition. Counted from the
# book rather than hard-coded, so retuning the vocabulary cannot silently
# turn this into an assertion about nothing.
CONDITION_TERM = "Non-Guaranteed"
CONDITION_TERM_COUNT = sum(
    1 for p in premiums if CONDITION_TERM.lower() in p["condition1"].lower())
search(CONDITION_TERM)
check("search matches the Condition",
      CONDITION_TERM_COUNT == 1
      and E(SEARCH_STATE)["total"] == str(CONDITION_TERM_COUNT),
      (CONDITION_TERM_COUNT, E(SEARCH_STATE)["total"]))

search("zzzz no such premium")
s = E(SEARCH_STATE)
shot("03-empty-search")
check("an unmatched search shows the empty state and no page buttons",
      s["noResults"] and s["regionHidden"] and not s["pages"], s)
check("the empty-search copy names search as the reason",
      s["noResultsCopy"] == "No premiums match your search", s["noResultsCopy"])

E("""document.querySelector('[data-v2-clear-search="premiums"]').click()""")
time.sleep(0.3)
check("Clear search restores the full book",
      E(SEARCH_STATE)["total"] == str(EXPECTED_PREMIUMS), E(SEARCH_STATE)["total"])

# =====================================================================
#  6. Checkbox selection and the action bar
# =====================================================================
print("\n--- 6. Selection and the action bar ---")

SELECTION = """(() => {
  const region = document.querySelector('[data-v2-table-region="premiums"]');
  const bar = document.querySelector('[data-v2-selection-bar="premiums"]');
  const rcsel = bar && bar.querySelector('.rcsel');
  const header = region.querySelector('[data-v2-checkbox-header="premiums"] input');
  const rows = [...region.querySelectorAll('tbody tr[data-v2-row-id]')];
  const actions = rcsel ? [...rcsel.querySelectorAll('[data-selection-action]')] : [];
  const cell = bar && bar.closest('td');
  return {
    barVisible: Boolean(bar && !bar.hidden && bar.offsetParent !== null),
    inTable: Boolean(cell && cell.classList.contains('create-md__selection-cell')),
    background: cell ? getComputedStyle(cell).backgroundColor : null,
    count: rcsel ? rcsel.querySelector('[data-selection-count]').textContent.trim() : null,
    actions: actions.map((b) => b.querySelector('.rcsel__btn-label').textContent.trim()),
    disabled: actions.filter((b) => b.disabled)
      .map((b) => b.querySelector('.rcsel__btn-label').textContent.trim()),
    icons: actions.filter((b) => b.querySelector('.rcsel__btn-icon svg')).length,
    headerChecked: header ? header.checked : null,
    headerIndeterminate: header ? header.indeterminate : null,
    checkedRows: rows.filter((r) => r.classList.contains('is-checked')).length,
    selectedRows: rows.filter((r) => r.classList.contains('is-selected')).length,
    activeDetailId: (() => {
      const active = rows.find((r) => r.classList.contains('is-selected'));
      return active ? active.getAttribute('data-v2-row-id') : null;
    })(),
    panelOpen: document.querySelector('.create-md').classList.contains('is-panel-open'),
  };
})()"""


def click_checkbox(index):
    E(f"""(() => {{
      const rows = [...document.querySelectorAll(
        '[data-v2-tbody="premiums"] tr[data-v2-row-id]')];
      rows[{index}].querySelector('input[type=checkbox]').click();
    }})()""")
    time.sleep(0.25)


s = E(SELECTION)
check("no action bar is shown with nothing selected", not s["barVisible"], s["barVisible"])

# Bulk selection and the active detail row are separate states, so this
# section runs against a closed panel: a checkbox must not open it.
E("""(() => {
  const close = document.querySelector('[data-v2-action="close-panel"]');
  if (close && document.querySelector('.create-md').classList.contains('is-panel-open')) {
    close.click();
  }
})()""")
time.sleep(0.4)
check("the details panel starts this section closed", not E(SELECTION)["panelOpen"])

click_checkbox(0)
s = E(SELECTION)
shot("04-one-selected")
check("checking one row shows the action bar", s["barVisible"])
check("the bar sits inside the table above the first row", s["inTable"], s["background"])
check("the bar uses the ADS indigo fill",
      s["background"] == "rgb(64, 69, 194)", s["background"])
check("the bar reads '1 item selected'", s["count"] == "1 item selected", s["count"])
check("the bar carries Export, Edit, Delete and Duplicate in Figma order",
      s["actions"] == ["Export", "Edit", "Delete", "Duplicate"], s["actions"])
check("every action renders an ADS icon rather than a text glyph",
      s["icons"] == 4, s["icons"])
check("one selection enables every action", s["disabled"] == [], s["disabled"])
check("the header checkbox goes indeterminate on a partial selection",
      s["headerIndeterminate"] is True and s["headerChecked"] is False, s)
check("checking a row does not open Premium Details", not s["panelOpen"], s["panelOpen"])

click_checkbox(1)
s = E(SELECTION)
check("the bar pluralises at two selections", s["count"] == "2 items selected", s["count"])
check("Edit and Duplicate are disabled for a multi-selection",
      sorted(s["disabled"]) == ["Duplicate", "Edit"], s["disabled"])

# Select-all is page-scoped.
E("""document.querySelector('[data-v2-checkbox-header="premiums"] input').click()""")
time.sleep(0.3)
s = E(SELECTION)
shot("05-select-all")
check("select-all checks every row on this page",
      s["checkedRows"] == 10 and s["count"] == "10 items selected",
      {"checked": s["checkedRows"], "count": s["count"]})
check("select-all reads as fully checked, not indeterminate",
      s["headerChecked"] is True and s["headerIndeterminate"] is False, s)

page_two_checked = E("""(() => {
  document.querySelector('[data-v2-page="premiums:2"]').click();
  return true;
})()""")
time.sleep(0.3)
s = E(SELECTION)
check("select-all did not reach records on the other page",
      s["checkedRows"] == 0 and s["headerChecked"] is False,
      {"checked": s["checkedRows"], "header": s["headerChecked"]})
check("selections made on page 1 are still held by ID",
      s["count"] == "10 items selected", s["count"])
E("""document.querySelector('[data-v2-page="premiums:1"]').click()""")
time.sleep(0.3)

E("""document.querySelector('[data-v2-checkbox-header="premiums"] input').click()""")
time.sleep(0.3)
s = E(SELECTION)
check("clearing select-all hides the action bar",
      not s["barVisible"] and s["checkedRows"] == 0, s)

# Export writes only the selected records.
click_checkbox(2)
click_checkbox(4)
exported_ids = E("""[...document.querySelectorAll('[data-v2-tbody="premiums"] tr[data-v2-row-id]')]
  .filter((r) => r.classList.contains('is-checked'))
  .map((r) => r.getAttribute('data-v2-row-id'))""")
E("""(() => {
  const bar = document.querySelector('[data-v2-selection-bar="premiums"] .rcsel');
  bar.querySelector('[data-selection-action="export"]').click();
})()""")
time.sleep(0.4)
csv = E("window.__csv")
check("Export produces a CSV download", bool(csv and csv.get("csv")), csv and csv.get("name"))
if csv:
    body = csv["csv"]
    prem_rows = [line for line in body.splitlines() if line.startswith('"PREM"')]
    check("Export writes only the selected premiums",
          len(prem_rows) == 2 and all(any(pid in line for line in prem_rows)
                                      for pid in exported_ids),
          {"rows": len(prem_rows), "selected": exported_ids})
    check("Export reuses the RCM template headers",
          body.splitlines()[0].startswith('"ROW_TYPE","ID","RATE_CARD_ID"'),
          body.splitlines()[0][:60])

# Delete asks first, then recalculates.
E("""(() => {
  const bar = document.querySelector('[data-v2-selection-bar="premiums"] .rcsel');
  bar.querySelector('[data-selection-action="delete"]').click();
})()""")
time.sleep(0.3)
modal = E("""(() => {
  const m = document.querySelector('[data-v2-remove-modal]');
  return { open: !m.hidden, title: m.querySelector('#v2-remove-title').textContent };
})()""")
shot("06-delete-confirm")
check("Delete opens the app's destructive confirmation, never deleting silently",
      modal["open"] and "2 premiums" in modal["title"], modal)
E("""document.querySelector('[data-v2-action="cancel-remove-line"]').click()""")
time.sleep(0.3)
check("cancelling the confirmation keeps every premium",
      E("""document.querySelector('[data-v2-total="premiums"]').textContent""")
      == str(EXPECTED_PREMIUMS))

E("""(() => {
  const bar = document.querySelector('[data-v2-selection-bar="premiums"] .rcsel');
  bar.querySelector('[data-selection-action="delete"]').click();
})()""")
time.sleep(0.3)
E("""document.querySelector('[data-v2-action="confirm-remove-line"]').click()""")
time.sleep(0.5)
after_delete = E(PAGER)
check("confirming Delete removes the selected premiums and recounts",
      E("""document.querySelector('[data-v2-total="premiums"]').textContent""") == "16",
      E("""document.querySelector('[data-v2-total="premiums"]').textContent"""))
check("deleting recalculates pagination", after_delete["pages"] == ["1", "2"],
      after_delete["pages"])
check("the action bar disappears once the selection is gone",
      not E(SELECTION)["barVisible"])

# Duplicate is single-only and names the copy.
click_checkbox(0)
source_name = E("""(() => {
  const row = [...document.querySelectorAll('[data-v2-tbody="premiums"] tr[data-v2-row-id]')]
    .find((r) => r.classList.contains('is-checked'));
  return row.querySelectorAll('td')[1].textContent.trim();
})()""")
E("""(() => {
  const bar = document.querySelector('[data-v2-selection-bar="premiums"] .rcsel');
  bar.querySelector('[data-selection-action="duplicate"]').click();
})()""")
time.sleep(0.6)
dup = E("""(() => {
  const files = JSON.parse(localStorage.getItem('rate-card-manager.v2.files') || '{}');
  const names = [...document.querySelectorAll('[data-v2-tbody="premiums"] tr[data-v2-row-id]')]
    .map((r) => r.querySelectorAll('td')[1].textContent.trim());
  return {
    total: document.querySelector('[data-v2-total="premiums"]').textContent,
    names: names,
    panelOpen: document.querySelector('.create-md').classList.contains('is-panel-open'),
    panelName: document.querySelector('[data-v2-form="premium"]').elements.displayName.value,
  };
})()""")
check("Duplicate adds one premium", dup["total"] == "17", dup["total"])
check("the duplicate is named distinguishably",
      dup["panelName"] == source_name + " (copy)",
      {"source": source_name, "copy": dup["panelName"]})
check("the duplicate opens for review", dup["panelOpen"], dup["panelOpen"])

# Put the book back before the panel tests.
E("""(() => {
  const form = document.querySelector('[data-v2-form="premium"]');
  document.querySelector('[data-v2-action="request-remove-premium"]').click();
})()""")
time.sleep(0.3)
E("""document.querySelector('[data-v2-action="confirm-remove-line"]').click()""")
time.sleep(0.5)
check("removing the duplicate restores the count",
      E("""document.querySelector('[data-v2-total="premiums"]').textContent""") == "16",
      E("""document.querySelector('[data-v2-total="premiums"]').textContent"""))

# =====================================================================
#  7. Premium Details panel
# =====================================================================
print("\n--- 7. Premium Details ---")

PANEL = """(() => {
  const form = document.querySelector('[data-v2-form="premium"]');
  const md = document.querySelector('.create-md');
  const rows = [...document.querySelectorAll('[data-v2-tbody="premiums"] tr[data-v2-row-id]')];
  const active = rows.find((r) => r.classList.contains('is-selected'));
  const fields = [...form.querySelectorAll('.field')].map((f) => {
    const label = f.querySelector('.field__label');
    return label ? label.textContent.trim() : null;
  }).filter(Boolean);
  return {
    open: md.classList.contains('is-panel-open'),
    title: document.querySelector('[data-v2-panel-title]').textContent,
    fields: fields,
    activeId: active ? active.getAttribute('data-v2-row-id') : null,
    activeCells: active ? [...active.querySelectorAll('td')].map((td) => {
      const copy = td.cloneNode(true);
      copy.querySelectorAll('.sr-only').forEach((n) => n.remove());
      return copy.textContent.trim();
    }) : null,
    checkedRows: rows.filter((r) => r.classList.contains('is-checked')).length,
    values: {
      id: form.elements.id.value,
      calculationMethod: form.elements.calculationMethod.value,
      category: form.elements.category.value,
      displayName: form.elements.displayName.value,
      value: form.elements.value.value,
      stackOrder: form.elements.stackOrder.value,
      condition1: form.elements.condition1.value,
      effectiveStart: form.elements.effectiveStart.value,
      effectiveEnd: form.elements.effectiveEnd.value,
    },
    submitLabel: document.querySelector('[data-v2-premium-submit]').textContent.trim(),
    removeVisible: !document.querySelector(
      '[data-v2-action="request-remove-premium"]').hidden,
    /* Dropdowns and date pickers carry aria-invalid on their trigger
       button, which has no name, so the field name comes from the
       control inside the invalid .field wrapper. */
    invalid: [...form.querySelectorAll('.field.is-invalid')].map((f) => {
      const control = f.querySelector('input[name], select[name], textarea[name]');
      return control ? control.name : '';
    }),
    confirmOpen: !document.querySelector('[data-ads-confirm]').hidden,
  };
})()"""


SUBMIT_STATE = """(() => {
  const btn = document.querySelector('[data-v2-premium-submit]');
  return {
    label: btn.textContent.trim(),
    disabled: btn.disabled,
    ariaDisabled: btn.getAttribute('aria-disabled'),
  };
})()"""


def click_row(index, cell=3):
    return E(f"""(() => {{
      const rows = [...document.querySelectorAll(
        '[data-v2-tbody="premiums"] tr[data-v2-row-id]')];
      const row = rows[{index}];
      if (!row) return null;
      row.querySelectorAll('td')[{cell}].click();
      return row.getAttribute('data-v2-row-id');
    }})()""")


def pick_dropdown(name, value):
    """The ADS dropdown decorates a native select, so driving the select
    and firing change exercises the same path the trigger does."""
    E(f"""(() => {{
      const form = document.querySelector('[data-v2-form="premium"]');
      const control = form.elements.namedItem({name!r});
      control.value = {value!r};
      control.dispatchEvent(new Event('input', {{bubbles: true}}));
      control.dispatchEvent(new Event('change', {{bubbles: true}}));
    }})()""")
    time.sleep(0.3)


# Both tabs share one Details panel, so arriving on Premiums must not
# leave the panel describing a line item the premium table does not list.
E("""document.querySelector('[data-v2-tab="lines"]').click()""")
time.sleep(0.5)
check("the Line Items tab shows Line Details",
      E("""document.querySelector('[data-v2-panel-title]').textContent""") == "Line Details")
E("""document.querySelector('[data-v2-tab="premiums"]').click()""")
time.sleep(0.5)
s = E(PANEL)
check("switching to Premiums re-points the shared panel at a premium",
      s["open"] and s["title"] == "Premium Details" and s["values"]["id"].startswith("PRM-"),
      {"title": s["title"], "id": s["values"]["id"]})
check("the re-pointed panel matches the row it highlights",
      s["activeId"] == s["values"]["id"], {"row": s["activeId"], "panel": s["values"]["id"]})
check("arriving on the tab does not bulk-check anything",
      s["checkedRows"] == 0, s["checkedRows"])

# Leaving a tab is the same loss of work as closing the panel.
E("""(() => {
  const form = document.querySelector('[data-v2-form="premium"]');
  form.elements.displayName.value = 'Edited before leaving the tab';
  form.elements.displayName.dispatchEvent(new Event('input', {bubbles: true}));
})()""")
E("""document.querySelector('[data-v2-tab="lines"]').click()""")
time.sleep(0.4)
s = E(PANEL)
check("switching tabs with unsaved work asks before discarding",
      s["confirmOpen"], s["confirmOpen"])
E("""document.querySelector('[data-ads-confirm-action="cancel"]').click()""")
time.sleep(0.4)
check("keeping the edit stays on the Premiums tab",
      E("""document.querySelector('[data-v2-tab="premiums"]')
        .getAttribute('aria-selected')""") == "true")
E("""document.querySelector('[data-v2-action="cancel-premium"]').click()""")
time.sleep(0.4)
if E("""!document.querySelector('[data-ads-confirm]').hidden"""):
    E("""document.querySelector('[data-ads-confirm-action="confirm"]').click()""")
    time.sleep(0.35)

opened = click_row(0)
time.sleep(0.35)
s = E(PANEL)
shot("07-details-open")
check("clicking a row opens Premium Details", s["open"] and s["activeId"] == opened,
      {"open": s["open"], "active": s["activeId"]})
check("the panel is titled Premium Details", s["title"] == "Premium Details", s["title"])
check("the fields follow the Figma order",
      s["fields"] == ["Calculation Method", "Premium Category",
                      "Premium Display Name (Optional)", "Value",
                      "Application Order (Optional)",
                      "Premium Condition (Optional)",
                      "Effective Start", "Effective End"],
      s["fields"])
check("opening a row does not bulk-check it", s["checkedRows"] == 0, s["checkedRows"])
check("the panel opens in edit mode",
      s["submitLabel"] == "Save changes" and s["removeVisible"],
      {"submit": s["submitLabel"], "remove": s["removeVisible"]})

# Every visible row's panel must match its table cells. Walked in full,
# both pages, no sampling.
mismatches = []
inspected = 0
for page in (1, 2):
    E(f"""(() => {{
      const btn = document.querySelector('[data-v2-page="premiums:{page}"]');
      if (btn) btn.click();
    }})()""")
    time.sleep(0.3)
    count = E("""document.querySelectorAll(
      '[data-v2-tbody="premiums"] tr[data-v2-row-id]').length""")
    for index in range(count):
        click_row(index)
        time.sleep(0.18)
        row = E(PANEL)
        inspected += 1
        cells = row["activeCells"]
        values = row["values"]
        # cells: [checkbox, Premium, Base offering, Category, Value, Method]
        if values["displayName"] and cells[1] != values["displayName"]:
            mismatches.append(f"{values['id']}: name {cells[1]!r} vs {values['displayName']!r}")
        if cells[3] != values["category"]:
            mismatches.append(f"{values['id']}: category {cells[3]!r} vs {values['category']!r}")
        if cells[4] != f"{float(values['value']):.2f}":
            mismatches.append(f"{values['id']}: value {cells[4]!r} vs {values['value']!r}")
        if cells[5] != values["calculationMethod"]:
            mismatches.append(
                f"{values['id']}: method {cells[5]!r} vs {values['calculationMethod']!r}")
        if not values["condition1"]:
            mismatches.append(f"{values['id']}: panel shows no condition")

check(f"all {inspected} rendered premiums match their Details panel exactly",
      not mismatches, "\n      " + "\n      ".join(mismatches[:20]))

E("""document.querySelector('[data-v2-page="premiums:1"]').click()""")
time.sleep(0.3)
click_row(0)
time.sleep(0.3)

# Save.
target = E(PANEL)["values"]["id"]
E("""(() => {
  const form = document.querySelector('[data-v2-form="premium"]');
  form.elements.value.focus();
  form.elements.value.value = '7.25';
  form.elements.value.dispatchEvent(new Event('input', {bubbles: true}));
})()""")
E("""document.querySelector('[data-v2-premium-submit]').click()""")
time.sleep(0.5)
s = E(PANEL)
check("Save writes the edit back to the right row",
      s["activeId"] == target and s["activeCells"][4] == "7.25",
      {"id": s["activeId"], "cell": s["activeCells"][4] if s["activeCells"] else None})

# Cancel restores the last saved value.
E("""(() => {
  const form = document.querySelector('[data-v2-form="premium"]');
  form.elements.value.focus();
  form.elements.value.value = '99';
  form.elements.value.dispatchEvent(new Event('input', {bubbles: true}));
})()""")
E("""document.querySelector('[data-v2-action="cancel-premium"]').click()""")
time.sleep(0.4)
if E("""!document.querySelector('[data-ads-confirm]').hidden"""):
    E("""document.querySelector('[data-ads-confirm-action="confirm"]').click()""")
    time.sleep(0.4)
cancelled = E("""(() => {
  const row = document.querySelector('[data-v2-row-id="%s"]');
  return row ? row.querySelectorAll('td')[4].textContent.trim() : null;
})()""" % target)
check("Cancel leaves the saved value in place, discarding only the edit",
      cancelled == "7.25", cancelled)

# Required-field and range validation.
click_row(1)
time.sleep(0.3)
E("""(() => {
  const form = document.querySelector('[data-v2-form="premium"]');
  form.elements.value.value = 'abc';
  form.elements.value.dispatchEvent(new Event('input', {bubbles: true}));
})()""")
E("""document.querySelector('[data-v2-premium-submit]').click()""")
time.sleep(0.3)
check("a non-numeric Value blocks Save",
      "value" in E(PANEL)["invalid"], E(PANEL)["invalid"])

E("""(() => {
  const form = document.querySelector('[data-v2-form="premium"]');
  form.elements.value.value = '3';
  form.elements.value.dispatchEvent(new Event('input', {bubbles: true}));
  form.elements.stackOrder.value = '2.5';
  form.elements.stackOrder.dispatchEvent(new Event('input', {bubbles: true}));
})()""")
E("""document.querySelector('[data-v2-premium-submit]').click()""")
time.sleep(0.3)
check("a fractional Application Order blocks Save",
      "stackOrder" in E(PANEL)["invalid"], E(PANEL)["invalid"])

E("""(() => {
  const form = document.querySelector('[data-v2-form="premium"]');
  form.elements.stackOrder.value = '20';
  form.elements.stackOrder.dispatchEvent(new Event('input', {bubbles: true}));
  form.elements.effectiveStart.value = '2027-01-01';
  form.elements.effectiveEnd.value = '2026-11-01';
})()""")
E("""document.querySelector('[data-v2-premium-submit]').click()""")
time.sleep(0.3)
check("an end date before the start date blocks Save",
      "effectiveEnd" in E(PANEL)["invalid"], E(PANEL)["invalid"])

# Unsaved-changes protection on close.
E("""(() => {
  const form = document.querySelector('[data-v2-form="premium"]');
  form.elements.effectiveStart.value = '';
  form.elements.effectiveEnd.value = '';
  form.elements.displayName.value = 'Unsaved edit';
  form.elements.displayName.dispatchEvent(new Event('input', {bubbles: true}));
})()""")
E("""document.querySelector('[data-v2-action="close-panel"]').click()""")
time.sleep(0.35)
s = E(PANEL)
shot("08-unsaved-guard")
check("closing with unsaved work asks before discarding",
      s["confirmOpen"] and s["open"], {"confirm": s["confirmOpen"], "open": s["open"]})
E("""document.querySelector('[data-ads-confirm-action="confirm"]').click()""")
time.sleep(0.4)
check("discarding completes the close", not E(PANEL)["open"])

# Add Premium opens a blank record.
E("""document.querySelector(
  '[data-v2-panel="premiums"] [data-v2-action="add-premium"]').click()""")
time.sleep(0.4)
s = E(PANEL)
shot("09-add-premium")
check("Add Premium opens the panel with an empty record",
      s["open"] and not any(s["values"][k] for k in
                            ("id", "calculationMethod", "category", "displayName",
                             "value", "stackOrder", "condition1",
                             "effectiveStart", "effectiveEnd")),
      s["values"])
check("Add Premium hides Remove and offers Add rather than Save",
      not s["removeVisible"] and s["submitLabel"] == "Add Premium",
      {"remove": s["removeVisible"], "submit": s["submitLabel"]})
# 2.1 gates the panel's primary action instead of letting a blank form
# submit into an error list, so "blocked" here means the button never
# arms until Calculation Method and Value are both present.
check("a blank premium cannot be added at all",
      E(SUBMIT_STATE)["disabled"] is True, E(SUBMIT_STATE))
E("""(() => {
  const form = document.querySelector('[data-v2-form="premium"]');
  form.elements.value.value = '4.25';
  form.elements.value.dispatchEvent(new Event('input', {bubbles: true}));
  form.elements.value.dispatchEvent(new Event('change', {bubbles: true}));
})()""")
time.sleep(0.3)
check("a Value on its own still does not arm Add Premium",
      E(SUBMIT_STATE)["disabled"] is True, E(SUBMIT_STATE))
pick_dropdown("calculationMethod", "Additive CPM")
check("Add Premium arms once Calculation Method and Value are both set",
      E(SUBMIT_STATE)["disabled"] is False, E(SUBMIT_STATE))
E("""document.querySelector('[data-v2-action="cancel-premium"]').click()""")
time.sleep(0.4)
if E("""!document.querySelector('[data-ads-confirm]').hidden"""):
    E("""document.querySelector('[data-ads-confirm-action="confirm"]').click()""")
    time.sleep(0.3)

# =====================================================================
#  8. Layout with the panel open and closed
# =====================================================================
print("\n--- 8. Layout ---")

LAYOUT = """(() => {
  const md = document.querySelector('.create-md');
  const ws = document.querySelector('.create-md__workspace').getBoundingClientRect();
  const detail = document.querySelector('.create-md__detail');
  const detailRect = detail.getBoundingClientRect();
  const scroll = document.querySelector(
    '[data-v2-table-region="premiums"] .create-md__table-scroll');
  return {
    open: md.classList.contains('is-panel-open'),
    workspaceWidth: Math.round(ws.width),
    overlaps: detail.offsetParent !== null && Math.round(ws.right) > Math.round(detailRect.left),
    horizontalScroll: scroll.scrollWidth > scroll.clientWidth + 1,
    headers: [...document.querySelectorAll(
      '[data-v2-table-region="premiums"] thead th')].map((th) => th.textContent.trim()),
  };
})()"""

closed = E(LAYOUT)
shot("10-panel-closed")
check("with the panel closed the premium table does not scroll sideways",
      not closed["horizontalScroll"], closed)
click_row(0)
time.sleep(0.4)
opened_layout = E(LAYOUT)
shot("11-panel-open")
check("the panel pushes the table rather than covering it",
      not opened_layout["overlaps"], opened_layout)
check("the narrowed table keeps the same columns in the same order",
      opened_layout["headers"] == closed["headers"], opened_layout["headers"])
check("the narrowed table still fits without a sideways scroll",
      not opened_layout["horizontalScroll"], opened_layout)

# =====================================================================
#  9. Line Items regression
# =====================================================================
print("\n--- 9. Line Items regression ---")
E("""document.querySelector('[data-v2-tab="lines"]').click()""")
time.sleep(0.5)
lines = E("""(() => {
  const rows = [...document.querySelectorAll('[data-v2-tbody="lines"] tr[data-v2-row-id]')];
  return {
    rowCount: rows.length,
    total: document.querySelector('[data-v2-total="lines"]').textContent,
    /* 2.1 keeps the Advertiser ID <th> in the DOM and hides it with CSS so
       the nth-child column widths still line up, so the regression guard
       reads the columns the user actually sees. */
    headers: [...document.querySelectorAll(
      '[data-v2-table-region="lines"] thead th')]
      .filter((th) => th.offsetParent !== null || th.classList.contains(
        'create-md__th-checkbox'))
      .map((th) => th.textContent.trim()),
    checkboxes: rows.filter((r) => r.querySelector('input[type=checkbox]')).length,
  };
})()""")
check("the Line Items tab still renders its full book",
      lines["rowCount"] == 10 and lines["total"] == "80", lines)
# Line condition joined this table after the Premiums work, and it sits
# after the pricing fields so Base offering through Currency still read
# together. The guard exists to catch the Premiums columns leaking into
# Line Items, so it names the full expected set rather than a count.
check("the Line Items columns are the Line Items columns",
      lines["headers"] == ["", "Advertiser name / ID", "Base offering", "Cost method",
                           "Base rate", "Currency", "Line condition", "Updated date"],
      lines["headers"])
check("Line Items keeps its own checkboxes",
      lines["checkboxes"] == 10, lines["checkboxes"])

E("""(() => {
  const rows = [...document.querySelectorAll('[data-v2-tbody="lines"] tr[data-v2-row-id]')];
  rows[0].querySelector('input[type=checkbox]').click();
})()""")
time.sleep(0.3)
line_bar = E("""(() => {
  const bar = document.querySelector('[data-v2-selection-bar="lines"] .rcsel');
  return bar ? {
    count: bar.querySelector('[data-selection-count]').textContent.trim(),
    actions: [...bar.querySelectorAll('.rcsel__btn-label')].map((b) => b.textContent.trim()),
  } : null;
})()""")
check("the Line Items action bar keeps its own actions",
      line_bar and line_bar["actions"] == ["Edit", "Copy", "Delete"], line_bar)
check("the Line Items bar still counts correctly",
      line_bar and line_bar["count"] == "1 item selected", line_bar)

drain_console()
check("no console errors during the whole flow", len(console_errors) == 0, console_errors)

print(f"\n{passes} passed, {len(failures)} failed. Screenshots in {OUT}")
for f in failures:
    print(f"  - {f['name']}: {f['detail']}")

chrome.terminate()
server.shutdown()
if failures:
    raise SystemExit(1)
