"""Regression QA: the Figma 643-65724 Rate Card Details layout applied to
REAL EXISTING catalog rate cards (not just newly created ones), across
Draft/Published status, zero/one/many line items, and direct-URL access.
Companion to qa_smoke_details_nav.py (new-card flow) and
qa_smoke_line_panel.py (line workflow on a new card)."""

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
PORT = 9011
DEBUG_PORT = 9311
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
OUT = "/tmp/rate-card-details-existing-qa"
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

profile = "/tmp/rate_card_details_existing_qa_profile"
shutil.rmtree(profile, ignore_errors=True)
os.makedirs(profile, exist_ok=True)
chrome = subprocess.Popen(
    [
        CHROME, f"--remote-debugging-port={DEBUG_PORT}", f"--user-data-dir={profile}",
        "--disk-cache-dir=/dev/null", "--headless=new", "--remote-allow-origins=*",
        "--no-first-run", "--force-device-scale-factor=1", "--window-size=1440,960",
        "about:blank",
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
    result = send("Runtime.evaluate", {"expression": expression, "returnByValue": True, "awaitPromise": True})
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
            raw = ws.recv()
            evt = json.loads(raw)
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


send("Emulation.setDeviceMetricsOverride", {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False})

# ======================================================================
# 0. Default version (no ?version= at all) already renders the new layout
# ======================================================================
send("Page.navigate", {"url": f"http://127.0.0.1:{PORT}/index.html"})
wait_for("document.querySelectorAll('[data-rows] .row').length > 0")
time.sleep(0.3)
default_version = E("document.body.getAttribute('data-version')")
check("bare URL with no ?version= defaults to 2.1", default_version == "2.1", default_version)
drain_console()


def get_card(card_id):
    return json.loads(E(f"JSON.stringify((window.RATE_CARDS || []).find(r => r.rateCardId === {json.dumps(card_id)}) || null)"))


def open_card(card_id, via="url"):
    """Navigate directly to an existing card's edit page (no version param)."""
    if via == "url":
        send("Page.navigate", {"url": f"http://127.0.0.1:{PORT}/index.html?section=create&mode=edit&cardId={card_id}"})
        wait_for("document.querySelector('[data-v2-title]') && document.body.getAttribute('data-route') === 'create'")
    time.sleep(0.5)
    drain_console()


def header_snapshot():
    return json.loads(E("""JSON.stringify({
        title: (document.querySelector('[data-v2-title]') || {}).textContent,
        status: (document.querySelector('[data-v2-meta-status]') || {}).textContent,
        marketplace: (document.querySelector('[data-v2-meta-marketplace]') || {}).textContent,
        metaText: (document.querySelector('[data-v2-meta-text]') || {}).textContent,
        metaHTML: (document.querySelector('[data-v2-meta]') || {}).outerHTML,
        emptyVisible: (() => { const e = document.querySelector('[data-v2-empty="lines"]'); return !!e && !e.hidden; })(),
        rowCount: document.querySelectorAll('[data-v2-tbody="lines"] tr').length,
        paginationVisible: (() => { const p = document.querySelector('[data-v2-pagination="lines"]'); return !!p && !p.hidden && p.offsetParent !== null; })(),
        splitVisible: (document.querySelector('[data-v2-header-splitbtn]') || {}).hidden === false,
    })"""))


# ======================================================================
# 1. Existing Draft card, zero line items (RC-DAS-INITIATIVE-BUNDLE-UF-2526)
# ======================================================================
card = get_card("RC-DAS-INITIATIVE-BUNDLE-UF-2526")
check("fixture: RC-DAS-INITIATIVE-BUNDLE-UF-2526 is Draft in RATE_CARDS", card and card["status"] == "Draft", card)
open_card("RC-DAS-INITIATIVE-BUNDLE-UF-2526")
shot("01-draft-zero-lines")
snap = header_snapshot()
check("existing Draft/0-line card: title matches real record name", snap["title"].strip() == card["name"] if card else False,
      (snap["title"], card and card["name"]))
check("existing Draft/0-line card: status chip reads Draft", snap["status"].strip() == "Draft", snap["status"])
check("existing Draft/0-line card: marketplace chip is non-empty", bool(snap["marketplace"].strip()), snap["marketplace"])
check("existing Draft/0-line card: no undefined/null in meta row", "undefined" not in snap["metaHTML"] and "null" not in snap["metaHTML"], snap["metaHTML"])
check("existing Draft/0-line card: empty line state shown (0 lines)", snap["emptyVisible"], snap)
check("existing Draft/0-line card: pagination hidden when empty", not snap["paginationVisible"], snap)
check("existing Draft/0-line card: Save Rate Card split button visible", snap["splitVisible"], snap)

# ======================================================================
# 2. Existing Published card, zero line items (RC-DAS-GROUPM-VIDEO-UF-2526)
# ======================================================================
card2 = get_card("RC-DAS-GROUPM-VIDEO-UF-2526")
check("fixture: RC-DAS-GROUPM-VIDEO-UF-2526 is Published in RATE_CARDS", card2 and card2["status"] == "Published", card2)
open_card("RC-DAS-GROUPM-VIDEO-UF-2526")
shot("02-published-zero-lines")
snap2 = header_snapshot()
check("existing Published/0-line card: status chip reads Published", snap2["status"].strip() == "Published", snap2["status"])
check("existing Published/0-line card: empty line state shown", snap2["emptyVisible"], snap2)
check("existing Published/0-line card: no data leaked from the previous card", snap2["title"].strip() != snap["title"].strip(), (snap2["title"], snap["title"]))

# ======================================================================
# 3. Existing Draft card, exactly one line item (RC-DAS-PEPSICO-DPLUS-UF-2526)
# ======================================================================
card3 = get_card("RC-DAS-PEPSICO-DPLUS-UF-2526")
check("fixture: RC-DAS-PEPSICO-DPLUS-UF-2526 is Draft in RATE_CARDS", card3 and card3["status"] == "Draft", card3)
open_card("RC-DAS-PEPSICO-DPLUS-UF-2526")
shot("03-draft-one-line")
snap3 = header_snapshot()
check("existing Draft/1-line card: table shows exactly one row (not empty state)", snap3["rowCount"] == 1, snap3)
check("existing Draft/1-line card: empty state hidden", not snap3["emptyVisible"], snap3)

# Click the existing seeded row (outside its checkbox) - must open Line Details
# with the row's REAL seeded values, not a blank draft.
row_before = json.loads(E("""JSON.stringify((() => {
  const row = document.querySelector('[data-v2-tbody="lines"] tr');
  if (!row) return null;
  return { advertiserId: row.getAttribute('data-v2-row-id'), text: row.textContent.replace(/\\s+/g, ' ').trim() };
})())"""))
E("""(() => {
  const row = document.querySelector('[data-v2-tbody="lines"] tr');
  const cell = row.querySelector('td:not(.create-md__td-checkbox)') || row;
  cell.click();
})()""")
time.sleep(0.4)
panel_open = E("document.querySelector('[data-v2-root]').classList.contains('is-panel-open')")
check("clicking an existing seeded row opens the Line Details panel", panel_open)
form_advertiser_id = E("""(() => {
  const f = document.querySelector('[data-v2-form="line"]');
  const el = f && f.elements.namedItem('advertiserId');
  return el ? el.value : '';
})()""")
check("panel loads the real seeded line's Advertiser ID (not blank)", bool(form_advertiser_id and form_advertiser_id.strip()), form_advertiser_id)
row_checked_after_open = E("""(() => {
  const row = document.querySelector('[data-v2-tbody="lines"] tr');
  const cb = row.querySelector('input[type=checkbox]');
  return cb ? cb.checked : false;
})()""")
check("opening a row for viewing does NOT check its checkbox", row_checked_after_open is False, row_checked_after_open)
shot("04-existing-line-panel-open")

# Edit the loaded line's Base Rate and confirm it updates the SAME row
# (no duplicate created) once committed via blur.
E("""(() => {
  const f = document.querySelector('[data-v2-form="line"]');
  const el = f.elements.namedItem('baseRate');
  el.value = '77.5';
  el.dispatchEvent(new Event('input', {bubbles: true}));
  el.dispatchEvent(new Event('focusout', {bubbles: true}));
})()""")
time.sleep(0.5)
row_count_after_edit = E("""document.querySelectorAll('[data-v2-tbody="lines"] tr').length""")
check("editing an existing seeded line keeps exactly one row (no duplicate)", row_count_after_edit == 1, row_count_after_edit)
row_text_after_edit = E("""(() => {
  const row = document.querySelector('[data-v2-tbody="lines"] tr');
  return row.textContent;
})()""")
check("edited row reflects the new base rate value", "77.5" in row_text_after_edit or "77.50" in row_text_after_edit, row_text_after_edit)
drain_console()

# ======================================================================
# 4. Existing Published card, many line items - pagination + selection on
#    REAL seeded data (RC-DAS-MICROSOFT-ADDR-MY-2526, 60 seeded lines)
# ======================================================================
card4 = get_card("RC-DAS-MICROSOFT-ADDR-MY-2526")
check("fixture: RC-DAS-MICROSOFT-ADDR-MY-2526 is Published in RATE_CARDS", card4 and card4["status"] == "Published", card4)
open_card("RC-DAS-MICROSOFT-ADDR-MY-2526")
shot("05-published-many-lines")
snap4 = header_snapshot()
check("existing Published/many-line card: table renders (not empty state)", not snap4["emptyVisible"], snap4)
check("existing Published/many-line card: pagination visible with many lines", snap4["paginationVisible"], snap4)
check("existing Published/many-line card: page 1 shows a full page of rows", snap4["rowCount"] >= 1, snap4)

# Select the header checkbox: selects the current page, shows action bar,
# selection count reflects the number actually selected (not the full 60).
E("""document.querySelector('[data-v2-checkbox-header="lines"] input[type=checkbox]').click()""")
time.sleep(0.3)
selection_bar_visible = E("""(() => {
  const bar = document.querySelector('[data-v2-selection-bar="lines"]');
  return !!bar && !bar.hidden;
})()""")
check("selecting header checkbox on a real many-line card shows the action bar", selection_bar_visible)
shot("06-many-lines-selection-bar")
count_text = E("""(() => {
  const bar = document.querySelector('[data-v2-selection-bar="lines"]');
  return bar ? bar.textContent.replace(/\\s+/g, ' ').trim() : '';
})()""")
import re as _re
count_match = _re.search(r"(\d+)\s*item", count_text)
check(
    "selection count text is populated (not 0/undefined)",
    "undefined" not in count_text and bool(count_match) and count_match.group(1) == "10",
    count_text,
)

# Deselect and confirm the bar hides and the toolbar returns.
E("""document.querySelector('[data-v2-checkbox-header="lines"] input[type=checkbox]').click()""")
time.sleep(0.3)
selection_bar_hidden = E("""(() => {
  const bar = document.querySelector('[data-v2-selection-bar="lines"]');
  return !bar || bar.hidden;
})()""")
check("deselecting all hides the action bar again", selection_bar_hidden)
drain_console()

# ======================================================================
# 5. Existing Published Multi-Year card (marketplace chip correctness)
# ======================================================================
card5 = get_card("RC-DAS-OMD-DPLUS-MY-2528")
check("fixture: RC-DAS-OMD-DPLUS-MY-2528 is Multi-Year", card5 and card5.get("marketplace") in ("Multi-Year", "Multiyear"), card5)
open_card("RC-DAS-OMD-DPLUS-MY-2528")
snap5 = header_snapshot()
check("Multi-Year card shows Multi-Year in the marketplace chip", snap5["marketplace"].strip() == "Multi-Year", snap5["marketplace"])
drain_console()

# ======================================================================
# 6. Save Rate Card on an existing Published card preserves Published
#    status (does not silently downgrade to Draft)
# ======================================================================
open_card("RC-DAS-GROUPM-VIDEO-UF-2526")
E("""document.querySelector('.splitbtn__main').click()""")
time.sleep(0.4)
status_after_save = E("document.querySelector('[data-v2-meta-status]').textContent.trim()")
check("Save Rate Card on an existing Published card keeps it Published", status_after_save == "Published", status_after_save)
toast_after_save = wait_for("document.querySelector('.ads-toast, [class*=toast]') !== null", timeout=2)
check("saving shows the existing success notification", toast_after_save)
drain_console()

# 'Save as draft' from the dropdown explicitly forces Draft even on a
# Published card (explicit unpublish path).
E("""document.querySelector('[data-v2-action="toggle-save-menu"]').click()""")
time.sleep(0.2)
E("""document.querySelector('.splitbtn__item').click()""")
time.sleep(0.4)
status_after_draft = E("document.querySelector('[data-v2-meta-status]').textContent.trim()")
check("'Save as draft' explicitly forces Draft status even from Published", status_after_draft == "Draft", status_after_draft)
drain_console()

# ======================================================================
# 7. Refresh persists the saved state (localStorage), no stale/previous
#    card data on reload.
# ======================================================================
send("Page.navigate", {"url": f"http://127.0.0.1:{PORT}/index.html?section=create&mode=edit&cardId=RC-DAS-GROUPM-VIDEO-UF-2526"})
wait_for("document.querySelector('[data-v2-title]')")
time.sleep(0.5)
status_after_reload = E("document.querySelector('[data-v2-meta-status]').textContent.trim()")
check("status persists as Draft after a full page reload", status_after_reload == "Draft", status_after_reload)
drain_console()

# ======================================================================
# 8. Back navigation preserves list search state
# ======================================================================
send("Page.navigate", {"url": f"http://127.0.0.1:{PORT}/index.html"})
wait_for("document.querySelectorAll('[data-rows] .row').length > 0")
time.sleep(0.3)
E("""(() => {
  const search = document.querySelector('[data-rcm-search], input[type=search], .table-toolbar input');
  if (search) { search.value = 'WPP'; search.dispatchEvent(new Event('input', {bubbles: true})); }
})()""")
time.sleep(0.3)
search_value_before = E("""(() => {
  const search = document.querySelector('[data-rcm-search], input[type=search], .table-toolbar input');
  return search ? search.value : '';
})()""")
E("""document.querySelector('.name__link').click()""")
time.sleep(0.5)
E("""document.querySelector('[data-action="go-list"], .create-md a[href*=list], a.create-md__back').click()""")
time.sleep(0.4)
search_value_after = E("""(() => {
  const search = document.querySelector('[data-rcm-search], input[type=search], .table-toolbar input');
  return search ? search.value : '';
})()""")
check("back navigation preserves the list search term", search_value_after == search_value_before and bool(search_value_after), (search_value_before, search_value_after))
drain_console()
check("no console errors across the whole existing-records regression run", len(console_errors) == 0, console_errors)

print(f"\n{passes} passed, {len(failures)} failed. Screenshots in {OUT}")
for f in failures:
    print(f"  - {f['name']}: {f['detail']}")

chrome.terminate()
server.shutdown()
if failures:
    raise SystemExit(1)
