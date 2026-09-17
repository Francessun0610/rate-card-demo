"""Focused test: the v2.1 Rate Card edit page opens with Line Details
already showing the first visible line item, the X collapses the table to
full width without losing data, and clicking rows reopens or switches the
panel. Also covers the unsaved-changes guard on both exits.

Scope is the master-detail interaction only. Panel field content, save
and remove behavior belong to qa_smoke_line_panel.py and
qa_details_existing_records.py.
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
PORT = 9025
DEBUG_PORT = 9325
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
OUT = "/tmp/rate-card-line-details-default"
# The reference screenshots for this behavior were taken at the desktop
# width where the panel and the table sit side by side.
VIEWPORT = (1600, 1000)
# A seeded Published card with enough lines to page through. It is an
# agency book rather than a single client's, so searching one advertiser
# narrows the table instead of matching every row.
CARD_ID = "RC-DAS-OMNICOM-VIDEO-UF-2526"

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

profile = "/tmp/rate_card_line_details_default_profile"
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


# Reads the whole master-detail interaction in one pass so every check
# below is measured against the same frame.
STATE = """(() => {
  const md = document.querySelector('.create-md');
  const detail = document.querySelector('.create-md__detail');
  const ws = document.querySelector('.create-md__workspace');
  const form = document.querySelector('[data-v2-form="line"]');
  const rows = [...document.querySelectorAll('[data-v2-tbody="lines"] tr[data-v2-row-id]')];
  const selected = rows.filter((r) => r.classList.contains('is-selected'));
  const round = (n) => Math.round(n);
  const wsRect = ws.getBoundingClientRect();
  const detailRect = detail.getBoundingClientRect();
  return {
    panelOpen: md.classList.contains('is-panel-open'),
    detailDisplay: getComputedStyle(detail).display,
    detailPosition: getComputedStyle(detail).position,
    detailWidth: round(detailRect.width),
    workspaceWidth: round(wsRect.width),
    // A push layout leaves the table's right edge at or before the
    // panel's left edge; an overlay would sit on top of it.
    overlaps: detail.offsetParent !== null && round(wsRect.right) > round(detailRect.left),
    panelTitle: document.querySelector('[data-v2-panel-title]').textContent,
    selectedCount: selected.length,
    selectedId: selected.length ? selected[0].getAttribute('data-v2-row-id') : null,
    selectedIsFirstRow: selected.length === 1 && selected[0] === rows[0],
    ariaSelectedCount: rows.filter((r) => r.getAttribute('aria-selected') === 'true').length,
    rowCount: rows.length,
    rowIds: rows.map((r) => r.getAttribute('data-v2-row-id')),
    advertiserId: form.elements.advertiserId ? form.elements.advertiserId.value : null,
    baseRate: form.elements.baseRate ? form.elements.baseRate.value : null,
    submitLabel: document.querySelector('[data-v2-line-submit]').textContent,
    removeVisible: !document.querySelector('[data-v2-action="request-remove-line"]').hidden,
    checkedCount: rows.filter((r) => {
      const box = r.querySelector('input[type=checkbox]');
      return box && box.checked;
    }).length,
    total: (document.querySelector('[data-v2-total="lines"]') || {}).textContent,
    confirmOpen: !document.querySelector('[data-ads-confirm]').hidden,
    confirmBody: document.querySelector('[data-ads-confirm] .modal__body-text').textContent,
    activeTag: document.activeElement.tagName,
  };
})()"""


def state():
    return E(STATE)


def click_row(index, cell=3):
    """Click a plain data cell, which is how a user reaches the row
    without going through a control."""
    return E(f"""(() => {{
      const rows = [...document.querySelectorAll('[data-v2-tbody="lines"] tr[data-v2-row-id]')];
      const row = rows[{index}];
      if (!row) return null;
      const cells = row.querySelectorAll('td');
      cells[Math.min({cell}, cells.length - 1)].click();
      return row.getAttribute('data-v2-row-id');
    }})()""")


def dirty_the_panel():
    """Clear a required field so the panel holds work the live sync
    cannot silently commit for us."""
    return E("""(() => {
      const form = document.querySelector('[data-v2-form="line"]');
      form.elements.baseRate.focus();
      form.elements.baseRate.value = '';
      form.elements.baseRate.dispatchEvent(new Event('input', {bubbles: true}));
      return form.elements.baseRate.value;
    })()""")


def confirm_click(action):
    return E(f"""(() => {{
      const modal = document.querySelector('[data-ads-confirm]');
      if (modal.hidden) return false;
      modal.querySelector('[data-ads-confirm-action="{action}"]'
        + ({json.dumps(action)} === 'cancel' ? '.btn' : '')).click();
      return true;
    }})()""")


send("Emulation.setDeviceMetricsOverride", {
    "width": VIEWPORT[0], "height": VIEWPORT[1], "deviceScaleFactor": 1, "mobile": False})
send("Page.navigate", {
    "url": f"http://127.0.0.1:{PORT}/index.html"
          f"?version=2.1&section=create&mode=edit&cardId={CARD_ID}"})
wait_for("document.body.dataset.version === '2.1'")
wait_for("document.querySelectorAll('[data-v2-tbody=\"lines\"] tr[data-v2-row-id]').length > 0")
time.sleep(0.5)
drain_console()

# =====================================================================
#  1. Default state on entering an existing rate card
# =====================================================================
print("\n--- 1. Default state on page entry ---")
s = state()
shot("01-default-open")
check("entering an existing card opens Line Details", s["panelOpen"], s["detailDisplay"])
check("the panel names itself Line Details", s["panelTitle"] == "Line Details", s["panelTitle"])
check("exactly one row is highlighted", s["selectedCount"] == 1, s["selectedCount"])
check("the highlighted row is the first visible line item",
      s["selectedIsFirstRow"], s["selectedId"])
check("the highlight is exposed to assistive tech",
      s["ariaSelectedCount"] == 1, s["ariaSelectedCount"])
check("the panel is loaded with that row's data, not blank",
      bool(s["advertiserId"]) and bool(s["baseRate"]),
      {"advertiserId": s["advertiserId"], "baseRate": s["baseRate"]})
check("the panel opens in edit mode, not create mode",
      s["submitLabel"] == "Save changes" and s["removeVisible"],
      {"submit": s["submitLabel"], "remove": s["removeVisible"]})
check("opening by default does not bulk-check any row",
      s["checkedCount"] == 0, s["checkedCount"])
check("the panel keeps its existing fixed width",
      s["detailWidth"] in (400, 460), s["detailWidth"])

# Push, not overlay: the table gives up the width the panel takes.
check("the panel pushes the table rather than covering it",
      not s["overlaps"] and s["detailPosition"] == "static",
      {"overlaps": s["overlaps"], "position": s["detailPosition"]})
open_workspace = s["workspaceWidth"]

# Nobody asked for the panel, so it must not take the caret on load.
check("the automatic open does not steal focus into the panel",
      s["activeTag"] in ("BODY", "HTML"), s["activeTag"])

# =====================================================================
#  2. Closing with X expands the table to full width
# =====================================================================
print("\n--- 2. Close collapses to the full-width table ---")
rows_before = s["rowCount"]
total_before = s["total"]
selected_before = s["selectedId"]

E("document.querySelector('[data-v2-action=\"close-panel\"]').click()")
time.sleep(0.35)
s = state()
shot("02-collapsed-full-width")
check("a clean panel closes with no prompt", not s["confirmOpen"], s["confirmBody"])
check("X closes the panel", not s["panelOpen"] and s["detailDisplay"] == "none",
      s["detailDisplay"])
check("the table expands into the freed width",
      s["workspaceWidth"] > open_workspace,
      {"open": open_workspace, "closed": s["workspaceWidth"]})
check("closing removes the selected-row highlight",
      s["selectedCount"] == 0 and s["ariaSelectedCount"] == 0,
      {"selected": s["selectedCount"], "aria": s["ariaSelectedCount"]})
check("closing deletes no line item", s["rowCount"] == rows_before,
      {"before": rows_before, "after": s["rowCount"]})
check("closing does not change the result count", s["total"] == total_before,
      {"before": total_before, "after": s["total"]})
closed_workspace = s["workspaceWidth"]

# =====================================================================
#  3. Reopening and switching rows
# =====================================================================
print("\n--- 3. Reopen and switch ---")
reopen_id = click_row(2)
time.sleep(0.3)
s = state()
check("clicking a row in the full-width layout reopens the panel", s["panelOpen"])
check("the reopened panel shows the clicked row", s["selectedId"] == reopen_id,
      {"clicked": reopen_id, "selected": s["selectedId"]})
check("reopening restores the side-by-side width",
      s["workspaceWidth"] == open_workspace,
      {"expected": open_workspace, "got": s["workspaceWidth"]})
first_advertiser = s["advertiserId"]

switch_id = click_row(5)
time.sleep(0.3)
s = state()
shot("03-switched-row")
check("switching rows keeps the panel open", s["panelOpen"])
check("switching rows moves the highlight", s["selectedId"] == switch_id,
      {"clicked": switch_id, "selected": s["selectedId"]})
check("only one row is highlighted after switching", s["selectedCount"] == 1,
      s["selectedCount"])
check("switching rows replaces the panel contents",
      s["advertiserId"] != first_advertiser or switch_id != reopen_id,
      {"before": first_advertiser, "after": s["advertiserId"]})
check("switching rows does not resize the layout",
      s["workspaceWidth"] == open_workspace,
      {"expected": open_workspace, "got": s["workspaceWidth"]})

# Reselecting the row already on screen is not a change of any kind.
click_row(5)
time.sleep(0.2)
s = state()
check("reselecting the open row leaves it open and unchanged",
      s["panelOpen"] and s["selectedId"] == switch_id, s["selectedId"])

# =====================================================================
#  4. Checkboxes drive bulk selection only
# =====================================================================
print("\n--- 4. Checkbox is bulk selection only ---")
panel_row = s["selectedId"]
E("""(() => {
  const rows = [...document.querySelectorAll('[data-v2-tbody="lines"] tr[data-v2-row-id]')];
  rows[8].querySelector('input[type=checkbox]').click();
})()""")
time.sleep(0.3)
s = state()
check("checking a row checks exactly one box", s["checkedCount"] == 1, s["checkedCount"])
check("the checkbox does not switch the panel", s["selectedId"] == panel_row,
      {"panel": s["selectedId"], "expected": panel_row})
check("the checkbox does not close the panel", s["panelOpen"])

E("""(() => {
  const rows = [...document.querySelectorAll('[data-v2-tbody="lines"] tr[data-v2-row-id]')];
  rows[8].querySelector('input[type=checkbox]').click();
})()""")
time.sleep(0.3)
check("unchecking clears the bulk selection", state()["checkedCount"] == 0)

# A checkbox click with the panel closed must not open it either.
E("document.querySelector('[data-v2-action=\"close-panel\"]').click()")
time.sleep(0.3)
E("""(() => {
  const rows = [...document.querySelectorAll('[data-v2-tbody="lines"] tr[data-v2-row-id]')];
  rows[3].querySelector('input[type=checkbox]').click();
})()""")
time.sleep(0.3)
s = state()
check("a checkbox never opens the panel from the collapsed layout",
      not s["panelOpen"] and s["checkedCount"] == 1,
      {"open": s["panelOpen"], "checked": s["checkedCount"]})
E("""(() => {
  const rows = [...document.querySelectorAll('[data-v2-tbody="lines"] tr[data-v2-row-id]')];
  rows[3].querySelector('input[type=checkbox]').click();
})()""")
time.sleep(0.25)

# =====================================================================
#  5. Unsaved changes are never dropped silently
# =====================================================================
print("\n--- 5. Unsaved-changes guard ---")
click_row(0)
time.sleep(0.3)
guard_row = state()["selectedId"]
table_value_before = E("""(() => {
  const row = document.querySelector('[data-v2-row-id="%s"]');
  return row ? row.querySelectorAll('td')[5].textContent.trim() : null;
})()""" % guard_row)

# 5a. Switching rows with unsaved work asks first.
dirty_the_panel()
click_row(4)
time.sleep(0.3)
s = state()
shot("04-discard-prompt-switch")
check("switching rows with unsaved work opens the app's confirm dialog",
      s["confirmOpen"], s["confirmBody"])
check("the prompt names switching as the thing that would discard",
      "Switching rows" in s["confirmBody"], s["confirmBody"])
check("the panel holds its row while the prompt is up",
      s["selectedId"] == guard_row, s["selectedId"])

confirm_click("cancel")
time.sleep(0.3)
s = state()
check("Keep editing cancels the switch", s["selectedId"] == guard_row, s["selectedId"])
check("Keep editing preserves the unsaved edit", s["baseRate"] == "", repr(s["baseRate"]))
check("Keep editing leaves the panel open", s["panelOpen"])

# 5b. Discarding proceeds to the row that was clicked.
target = click_row(4)
time.sleep(0.3)
check("the guard fires again on a second attempt", state()["confirmOpen"])
confirm_click("confirm")
time.sleep(0.35)
s = state()
check("Discard changes completes the switch", s["selectedId"] == target,
      {"target": target, "selected": s["selectedId"]})
check("the discarded edit never reached the table",
      E("""(() => {
        const row = document.querySelector('[data-v2-row-id="%s"]');
        return row ? row.querySelectorAll('td')[5].textContent.trim() : null;
      })()""" % guard_row) == table_value_before, table_value_before)

# 5c. The X asks the same question.
dirty_the_panel()
E("document.querySelector('[data-v2-action=\"close-panel\"]').click()")
time.sleep(0.3)
s = state()
check("closing with unsaved work opens the same confirm dialog", s["confirmOpen"])
check("the prompt names closing as the thing that would discard",
      "Closing" in s["confirmBody"], s["confirmBody"])
check("the panel stays open behind the prompt", s["panelOpen"])
confirm_click("cancel")
time.sleep(0.3)
check("Keep editing keeps the panel open on close too", state()["panelOpen"])
E("document.querySelector('[data-v2-action=\"close-panel\"]').click()")
time.sleep(0.2)
confirm_click("confirm")
time.sleep(0.35)
check("Discard changes completes the close", not state()["panelOpen"])

# =====================================================================
#  6. Pagination, search and filters still work
# =====================================================================
print("\n--- 6. Pagination and search ---")
page_one_ids = state()["rowIds"]
page_two = E("""(() => {
  const btn = [...document.querySelectorAll('[data-v2-page]')]
    .find((b) => b.textContent.trim() === '2');
  if (!btn) return false;
  btn.click();
  return true;
})()""")
time.sleep(0.35)
s = state()
check("pagination still moves to page 2", page_two and s["rowCount"] > 0, s["rowCount"])
check("page 2 shows a different set of rows",
      s["rowIds"] and not set(s["rowIds"]) & set(page_one_ids),
      {"page1": page_one_ids[:3], "page2": s["rowIds"][:3]})

page_two_id = click_row(1)
time.sleep(0.3)
s = state()
check("a row on page 2 opens the panel", s["panelOpen"] and s["selectedId"] == page_two_id,
      {"open": s["panelOpen"], "selected": s["selectedId"]})

E("""(() => {
  const s = document.querySelector('[data-v2-search="lines"]');
  s.value = 'Verizon';
  s.dispatchEvent(new Event('input', {bubbles: true}));
})()""")
time.sleep(0.35)
s = state()
check("search still filters the table with the panel open",
      s["rowCount"] > 0 and s["rowCount"] < rows_before, s["rowCount"])
check("search does not close the panel", s["panelOpen"])

E("""(() => {
  const s = document.querySelector('[data-v2-search="lines"]');
  s.value = '';
  s.dispatchEvent(new Event('input', {bubbles: true}));
})()""")
time.sleep(0.35)
check("clearing search restores the full page", state()["rowCount"] == rows_before,
      state()["rowCount"])

# =====================================================================
#  7. Collapsed layout geometry matches the full-width reference
# =====================================================================
print("\n--- 7. Layout in both states ---")
E("document.querySelector('[data-v2-action=\"close-panel\"]').click()")
time.sleep(0.35)
s = state()
check("the collapsed table returns to the same full width",
      s["workspaceWidth"] == closed_workspace,
      {"expected": closed_workspace, "got": s["workspaceWidth"]})

# The controls above and below the table must keep their relationship to
# the table in both states. Tabs are right-aligned and pagination is
# centered by design, so "aligned" is measured per control against the
# workspace, not as one shared gutter.
ALIGNMENT = """(() => {
  const round = (n) => Math.round(n);
  const pick = (sel) => {
    const el = document.querySelector(sel);
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return [round(r.left), round(r.right)];
  };
  const ws = document.querySelector('.create-md__workspace').getBoundingClientRect();
  return {
    workspace: [round(ws.left), round(ws.right)],
    toolbar: pick('.create-md__toolbar'),
    tabs: pick('[data-v2-tabs]') || pick('.create-md__tabs'),
    table: pick('[data-v2-table-region="lines"] .create-md__table'),
    head: pick('[data-v2-table-region="lines"] thead'),
    footer: pick('[data-v2-table-region="lines"] .create-md__pagination')
      || pick('.create-md__pagination'),
  };
})()"""


def alignment_report(layout):
    """Left gutter shared by the stacked controls, plus how far each
    control's right edge sits from the workspace's right edge."""
    right = layout["workspace"][1]
    return {
        "gutters": sorted({v[0] for k, v in layout.items()
                           if v and k in ("toolbar", "table", "head", "workspace")}),
        "tabsInset": right - layout["tabs"][1] if layout["tabs"] else None,
        "footerCentered": layout["footer"] and abs(
            (layout["footer"][0] - layout["workspace"][0])
            - (right - layout["footer"][1])) <= 2,
    }


collapsed = alignment_report(E(ALIGNMENT))
check("collapsed: toolbar, header and rows share one left gutter",
      len(collapsed["gutters"]) <= 2, collapsed["gutters"])
check("collapsed: pagination stays centered under the table",
      collapsed["footerCentered"], collapsed)
shot("05-collapsed-alignment")

click_row(0)
time.sleep(0.35)
expanded = alignment_report(E(ALIGNMENT))
check("open: toolbar, header and rows keep the same left gutter",
      expanded["gutters"] == collapsed["gutters"],
      {"collapsed": collapsed["gutters"], "open": expanded["gutters"]})
check("open: tabs keep the same inset from the table's right edge",
      expanded["tabsInset"] == collapsed["tabsInset"],
      {"collapsed": collapsed["tabsInset"], "open": expanded["tabsInset"]})
check("open: pagination stays centered under the narrowed table",
      expanded["footerCentered"], expanded)
shot("06-open-alignment")

drain_console()
check("no console errors during the whole flow", len(console_errors) == 0, console_errors)

print(f"\n{passes} passed, {len(failures)} failed. Screenshots in {OUT}")
for f in failures:
    print(f"  - {f['name']}: {f['detail']}")

chrome.terminate()
server.shutdown()
if failures:
    raise SystemExit(1)
