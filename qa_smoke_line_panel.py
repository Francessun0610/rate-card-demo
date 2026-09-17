"""Smoke test: Add line -> Line Details panel (create via the footer
button, then live-sync on blur while editing) -> checkbox selection ->
action bar -> Edit/Copy/Delete, on the v2.1 Rate Card Details page.
Not the full QA suite - just validates the wiring."""

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
PORT = 9021
DEBUG_PORT = 9321
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
OUT = "/tmp/rate-card-line-panel-smoke"
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

profile = "/tmp/rate_card_line_panel_smoke_profile"
shutil.rmtree(profile, ignore_errors=True)
os.makedirs(profile, exist_ok=True)
chrome = subprocess.Popen(
    [
        CHROME, f"--remote-debugging-port={DEBUG_PORT}", f"--user-data-dir={profile}",
        "--disk-cache-dir=/dev/null", "--headless=new", "--remote-allow-origins=*",
        "--no-first-run", "--force-device-scale-factor=1", "--window-size=1600,1000",
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


def set_field(name, value, form="line"):
    return E(f"""(() => {{
      const form = document.querySelector('[data-v2-form="{form}"]');
      const el = form.elements['{name}'];
      if (!el) return 'missing:{name}';
      el.value = {json.dumps(value)};
      el.dispatchEvent(new Event('input', {{bubbles: true}}));
      el.dispatchEvent(new Event('change', {{bubbles: true}}));
      el.dispatchEvent(new Event('blur', {{bubbles: true}}));
      el.dispatchEvent(new Event('focusout', {{bubbles: true}}));
      return 'ok';
    }})()""")


send("Emulation.setDeviceMetricsOverride", {"width": 1600, "height": 1000, "deviceScaleFactor": 1, "mobile": False})
send("Page.navigate", {"url": f"http://127.0.0.1:{PORT}/index.html?version=2.1"})
wait_for("document.body.dataset.version === '2.1'")
wait_for("document.querySelectorAll('[data-rows] .row').length > 0")
time.sleep(0.4)
drain_console()

# Create a rate card, land on the details page.
E("document.querySelector('[data-action=\"create\"]').click()")
time.sleep(0.3)
E("""(() => {
  // The Rate Card ID is entered by the user now, and Confirm stays
  // disabled until it is present and valid.
  const id = document.querySelector('[data-rcm-card-id]');
  id.value = 'RC-SMOKE-ESPN-SC-2526';
  id.dispatchEvent(new Event('input', {bubbles: true}));
  id.dispatchEvent(new FocusEvent('blur'));
  const el = document.getElementById('rcm-name');
  el.value = 'ESPN College Football Scatter (25-26)';
  el.dispatchEvent(new Event('input', {bubbles: true}));
})()""")
E("document.querySelector('[data-action=\"confirm-rc-create\"]').click()")
wait_for("document.body.getAttribute('data-route') === 'create'", timeout=3)
time.sleep(0.4)
drain_console()

# ---- Add line opens the panel, no blank row on close ------------------
E("document.querySelector('[data-v2-action=\"add-line\"]').click()")
time.sleep(0.3)
panel_open = E("document.querySelector('.create-md').classList.contains('is-panel-open')")
check("Add Line Item opens the panel (.is-panel-open)", panel_open)

panel_title = E("document.querySelector('[data-v2-panel-title]').textContent.trim()")
check("panel header shows 'Line Details'", panel_title == "Line Details", panel_title)

# Close immediately without filling anything in - no row should appear.
E("document.querySelector('[data-v2-action=\"close-panel\"]').click()")
time.sleep(0.3)
still_empty = E("!document.querySelector('[data-v2-empty=\"lines\"]').hidden")
check("closing an untouched new-line panel leaves the empty state (no blank row)", still_empty)
panel_closed = E("!document.querySelector('.create-md').classList.contains('is-panel-open')")
check("panel closes (.is-panel-open removed)", panel_closed)

# ---- Reopen, fill required fields, exactly one row appears ------------
E("document.querySelector('[data-v2-action=\"add-line\"]').click()")
time.sleep(0.2)
set_field("advertiserId", "ADV-55201")
set_field("baseRate", "24.50")
time.sleep(0.2)
res = E("""(() => {
  const form = document.querySelector('[data-v2-form="line"]');
  const setSelect = (name, value) => {
    const el = form.elements[name];
    if (!el) return 'missing:' + name;
    el.value = value;
    el.dispatchEvent(new Event('change', {bubbles: true}));
    return 'ok';
  };
  // adProduct (Ad Type) is a custom .ads-dd dropdown, not a native select.
  const ddOption = document.querySelector('#v2-ad-product-menu .ads-dd__option:not(.is-disabled)');
  if (ddOption) ddOption.click();
  return JSON.stringify({
    adProduct: ddOption ? 'ok' : 'missing:adProduct',
    baseOffering: setSelect('baseOffering', form.elements.baseOffering.options[1] ? form.elements.baseOffering.options[1].value : ''),
    rateType: setSelect('rateType', 'CPM'),
    currency: setSelect('currency', 'USD')
  });
})()""")
time.sleep(0.4)
drain_console()

# A new line is created by the footer button, never by a blur, so that the
# button stays clickable (a blur-driven create would fire on the way to it).
staged = E("document.querySelectorAll('[data-v2-tbody=\"lines\"] tr[data-v2-row-id]').length")
check("filling the form does not create the row on its own", staged == 0, staged)

submit_ready = E("!document.querySelector('[data-v2-line-submit]').disabled")
check("Add Line Item enables once required fields are valid", submit_ready, f"setResult={res}")

E("document.querySelector('[data-v2-line-submit]').click()")
time.sleep(0.4)
drain_console()

row_count = E("document.querySelectorAll('[data-v2-tbody=\"lines\"] tr[data-v2-row-id]').length")
check("Add Line Item creates exactly one row", row_count == 1, f"rows={row_count} setResult={res}")

table_visible = E("!document.querySelector('[data-v2-table-region=\"lines\"]').hidden")
check("table region replaces the empty state", table_visible)

# Continue editing - row should update, not duplicate.
set_field("baseRate", "31.00")
time.sleep(0.3)
row_count_2 = E("document.querySelectorAll('[data-v2-tbody=\"lines\"] tr[data-v2-row-id]').length")
check("editing further does not duplicate the row", row_count_2 == 1, row_count_2)

rate_text = E("document.querySelector('[data-v2-tbody=\"lines\"] tr[data-v2-row-id] td:nth-child(6)').textContent")
check("row reflects the updated base rate", "31" in rate_text, rate_text)

shot("01-line-details-open")

# Close panel; row should persist.
E("document.querySelector('[data-v2-action=\"close-panel\"]').click()")
time.sleep(0.3)
row_persists = E("document.querySelectorAll('[data-v2-tbody=\"lines\"] tr[data-v2-row-id]').length")
check("valid row persists after closing the panel", row_persists == 1, row_persists)
panel_closed_2 = E("!document.querySelector('.create-md').classList.contains('is-panel-open')")
check("panel fully closes, full width restored", panel_closed_2)

# ---- Clicking the row reopens its details -------------------------------
E("document.querySelector('[data-v2-tbody=\"lines\"] tr[data-v2-row-id]').click()")
time.sleep(0.3)
reopened = E("document.querySelector('.create-md').classList.contains('is-panel-open')")
check("clicking a row reopens the Line Details panel", reopened)
loaded_id = E("document.querySelector('[data-v2-form=\"line\"]').elements.advertiserId.value")
check("reopened panel loads that line's values", loaded_id == "ADV-55201", loaded_id)

E("document.querySelector('[data-v2-action=\"close-panel\"]').click()")
time.sleep(0.2)

# ---- Checkbox selection reveals the action bar --------------------------
checkbox_present = E("!!document.querySelector('[data-v2-tbody=\"lines\"] tr[data-v2-row-id] .ads-checkbox__input')")
check("row has a checkbox", checkbox_present)

E("""(() => {
  const cb = document.querySelector('[data-v2-tbody="lines"] tr[data-v2-row-id] .ads-checkbox__input');
  cb.checked = true;
  cb.dispatchEvent(new Event('change', {bubbles: true}));
})()""")
time.sleep(0.3)
bar_visible = E("""(() => {
  const bar = document.querySelector('[data-v2-selection-bar="lines"]');
  return bar && !bar.hidden;
})()""")
check("checking a row reveals the selection action bar", bar_visible)

panel_not_opened_by_checkbox = E("!document.querySelector('.create-md').classList.contains('is-panel-open')")
check("checking the checkbox does NOT open the Line Details panel", panel_not_opened_by_checkbox)

count_text = E("document.querySelector('[data-v2-selection-bar=\"lines\"] [data-selection-count]').textContent")
check("selection count reads '1 item selected'", count_text == "1 item selected", count_text)

# Figma 644:67875 puts the action bar inside the table, directly under the
# header row, and leaves Add Line Item / Filter / Search in place above it.
toolbar_state = E("""(() => {
  const toolbar = document.querySelector('.create-md__toolbar');
  const bar = document.querySelector('[data-v2-selection-bar="lines"]');
  return {
    toolbarVisible: !!(toolbar && !toolbar.hidden && toolbar.getClientRects().length),
    barInTable: !!(bar && bar.closest('tr.create-md__selection-row'))
  };
})()""")
check("toolbar stays visible while the action bar is shown",
      toolbar_state["toolbarVisible"], toolbar_state)
check("action bar renders as an in-table row", toolbar_state["barInTable"], toolbar_state)

shot("02-action-bar")

# ---- Copy action ---------------------------------------------------------
E("document.querySelector('[data-v2-selection-bar=\"lines\"] [data-selection-action=\"copy\"]').click()")
time.sleep(0.4)
drain_console()
row_count_after_copy = E("document.querySelectorAll('[data-v2-tbody=\"lines\"] tr[data-v2-row-id]').length")
check("Copy creates exactly one additional row", row_count_after_copy == 2, row_count_after_copy)

# ---- Edit action (single selection only) --------------------------------
E("""(() => {
  document.querySelectorAll('[data-v2-tbody="lines"] tr[data-v2-row-id] .ads-checkbox__input').forEach(cb => {
    cb.checked = false;
    cb.dispatchEvent(new Event('change', {bubbles: true}));
  });
})()""")
time.sleep(0.2)
E("""(() => {
  const cb = document.querySelector('[data-v2-tbody="lines"] tr[data-v2-row-id] .ads-checkbox__input');
  cb.checked = true;
  cb.dispatchEvent(new Event('change', {bubbles: true}));
})()""")
time.sleep(0.2)
edit_enabled = E("!document.querySelector('[data-v2-selection-bar=\"lines\"] [data-selection-action=\"edit\"]').disabled")
check("Edit is enabled for exactly one selected row", edit_enabled)
E("document.querySelector('[data-v2-selection-bar=\"lines\"] [data-selection-action=\"edit\"]').click()")
time.sleep(0.3)
edit_opened_panel = E("document.querySelector('.create-md').classList.contains('is-panel-open')")
check("Edit opens the Line Details panel", edit_opened_panel)
E("document.querySelector('[data-v2-action=\"close-panel\"]').click()")
time.sleep(0.2)

# Select both rows: Edit should now be disabled.
E("""(() => {
  document.querySelectorAll('[data-v2-tbody="lines"] tr[data-v2-row-id] .ads-checkbox__input').forEach(cb => {
    cb.checked = true;
    cb.dispatchEvent(new Event('change', {bubbles: true}));
  });
})()""")
time.sleep(0.2)
edit_disabled_multi = E("document.querySelector('[data-v2-selection-bar=\"lines\"] [data-selection-action=\"edit\"]').disabled")
check("Edit is disabled when multiple rows are selected", edit_disabled_multi)

count_text_2 = E("document.querySelector('[data-v2-selection-bar=\"lines\"] [data-selection-count]').textContent")
check("selection count reads '2 items selected'", count_text_2 == "2 items selected", count_text_2)

# ---- Delete action (with confirmation) -----------------------------------
E("document.querySelector('[data-v2-selection-bar=\"lines\"] [data-selection-action=\"delete\"]').click()")
time.sleep(0.3)
modal_open = E("!document.querySelector('[data-v2-remove-modal]').hidden")
check("Delete shows a confirmation modal before deleting", modal_open)
rows_before_confirm = E("document.querySelectorAll('[data-v2-tbody=\"lines\"] tr[data-v2-row-id]').length")
check("nothing is deleted before confirming", rows_before_confirm == 2, rows_before_confirm)

E("document.querySelector('[data-v2-action=\"confirm-remove-line\"]').click()")
time.sleep(0.4)
drain_console()
rows_after_delete = E("document.querySelectorAll('[data-v2-tbody=\"lines\"] tr[data-v2-row-id]').length")
check("confirming deletes all selected rows", rows_after_delete == 0, rows_after_delete)
back_to_empty = E("!document.querySelector('[data-v2-empty=\"lines\"]').hidden")
check("deleting the last line returns to the empty state", back_to_empty)
bar_hidden_after_delete = E("document.querySelector('[data-v2-selection-bar=\"lines\"]').hidden")
check("selection action bar hides once nothing remains selected", bar_hidden_after_delete)

drain_console()
check("no console errors during the whole flow", len(console_errors) == 0, console_errors)

print(f"\n{passes} passed, {len(failures)} failed. Screenshots in {OUT}")
for f in failures:
    print(f"  - {f['name']}: {f['detail']}")

chrome.terminate()
server.shutdown()
if failures:
    raise SystemExit(1)
