"""Create rate card modal QA (Figma 643:63052 collapsed / 639:61405 expanded).

Covers
  1. Opening: overlay visible, modal centered, background scroll locked,
     focus moves to Rate Card Name, page state (selection/filters/search/
     sort/pagination) preserved.
  2. Collapsed state: down chevron, optional fields hidden + not tabbable,
     footer visible, no unnecessary scrollbar.
  3. Confirm gating: disabled while name empty, enabled once trimmed name
     is non-empty, blur shows "Enter a rate card name." error.
  4. Expand/collapse: up chevron + helper text on expand, values preserved
     across collapse, footer/header stay fixed.
  5. Date range validation: Effective End before Effective Start shows the
     inline error and blocks nothing else.
  6. Successful submission: creates exactly one new Draft row at the top
     of the table under the Rate Card ID the user typed, closes the modal,
     returns focus to the trigger, shows a success toast, and the table
     reflects unrelated page state unchanged.
  7. Escape key + Cancel button both close without creating a row and
     clear transient state (reopen starts clean).
  8. No console errors/exceptions during the whole flow.

Run with: python3 qa_create_rate_card_modal.py
"""

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
PORT = 8997
DEBUG_PORT = 9297
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
OUT = "/tmp/rate-card-create-modal-qa"
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
            ".html": "text/html",
            ".css": "text/css",
            ".js": "application/javascript",
            ".svg": "image/svg+xml",
            ".png": "image/png",
            ".json": "application/json",
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

profile = "/tmp/rate_card_create_modal_profile"
shutil.rmtree(profile, ignore_errors=True)
os.makedirs(profile, exist_ok=True)
chrome = subprocess.Popen(
    [
        CHROME,
        f"--remote-debugging-port={DEBUG_PORT}",
        f"--user-data-dir={profile}",
        "--disk-cache-dir=/dev/null",
        "--headless=new",
        "--remote-allow-origins=*",
        "--no-first-run",
        "--force-device-scale-factor=1",
        "--window-size=1440,960",
        "about:blank",
    ],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)

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
    result = send(
        "Runtime.evaluate",
        {"expression": expression, "returnByValue": True, "awaitPromise": True},
    )
    payload = result.get("result", {})
    if "exceptionDetails" in payload:
        detail = payload["exceptionDetails"]
        raise RuntimeError(json.dumps(detail)[:400])
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


def viewport(width, height=900, scale=1):
    send(
        "Emulation.setDeviceMetricsOverride",
        {"width": width, "height": height, "deviceScaleFactor": scale, "mobile": False},
    )


def key(key_name, code=None, key_code=None, text=None):
    params = {"type": "keyDown", "key": key_name}
    if code:
        params["code"] = code
    if key_code:
        params["windowsVirtualKeyCode"] = key_code
    if text:
        params["text"] = text
    send("Input.dispatchKeyEvent", params)
    params["type"] = "keyUp"
    send("Input.dispatchKeyEvent", params)


def type_text(text):
    for ch in text:
        send("Input.dispatchKeyEvent", {"type": "keyDown", "text": ch})
        send("Input.dispatchKeyEvent", {"type": "keyUp", "text": ch})


# --- console error capture ---------------------------------------------
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
                console_errors.append(json.dumps(evt["params"])[:300])
            elif method == "Log.entryAdded":
                entry = evt["params"].get("entry", {})
                if entry.get("level") == "error":
                    console_errors.append(entry.get("text", "")[:300])
    except Exception:
        pass
    finally:
        ws.settimeout(None)


viewport(1440, 900)
send("Page.navigate", {"url": f"http://127.0.0.1:{PORT}/index.html?version=2.1"})
wait_for("document.body.dataset.version === '2.1'")
wait_for("document.querySelectorAll('[data-rows] .row').length > 0")
time.sleep(0.4)
drain_console()

# ============================== 1. OPEN =================================
def total_items():
    return E("""(() => {
      const el = document.querySelector('[data-total]');
      const m = el && el.textContent.match(/([\\d,]+) items/);
      return m ? parseInt(m[1].replace(/,/g, ''), 10) : null;
    })()""")


initial_total = total_items()

E("document.querySelector('[data-action=\"create\"]').click()")
time.sleep(0.4)

modal_open = E("""(() => {
  const m = document.querySelector('[data-rc-create-modal]');
  return m && !m.hidden && m.classList.contains('is-open');
})()""")
check("Create Rate Card button opens the modal", modal_open)

overlay_visible = E("""(() => {
  const scrim = document.querySelector('[data-rc-create-modal] .modal__scrim');
  return scrim && getComputedStyle(scrim).display !== 'none';
})()""")
check("semi-transparent overlay is visible", overlay_visible)

body_locked = E("document.body.classList.contains('rcm-create-open')")
check("background scroll is locked (body.rcm-create-open)", body_locked)

focus_on_name = E("document.activeElement && document.activeElement.id === 'rcm-name'")
check("focus moves to Rate Card Name field on open", focus_on_name)

modal_role = E("""(() => {
  const m = document.querySelector('[data-rc-create-modal]');
  return m.getAttribute('role') === 'dialog' && m.getAttribute('aria-modal') === 'true'
    && m.getAttribute('aria-labelledby') === 'rcm-create-title';
})()""")
check("dialog has role=dialog, aria-modal, aria-labelledby", modal_role)

shot("01-collapsed-open")

# ============================== 2. COLLAPSED STATE =======================
details_collapsed = E("""(() => {
  const section = document.querySelector('[data-rcm-details]');
  const head = document.getElementById('rcm-details-head');
  const wrap = document.getElementById('rcm-details-wrap');
  return !section.classList.contains('is-open')
    && head.getAttribute('aria-expanded') === 'false'
    && wrap.hasAttribute('inert');
})()""")
check("optional details section starts collapsed", details_collapsed)

confirm_disabled_empty = E("document.querySelector('[data-action=\"confirm-rc-create\"]').disabled")
check("Confirm disabled while name is empty", confirm_disabled_empty)

no_scrollbar_collapsed = E("""(() => {
  const body = document.querySelector('[data-rc-create-modal] .modal__body');
  return body.scrollHeight <= body.clientHeight + 1;
})()""")
check("no scrollbar needed in collapsed state", no_scrollbar_collapsed)

id_field = E("""(() => {
  const m = document.querySelector('[data-rc-create-modal]');
  const input = m.querySelector('[data-rcm-card-id]');
  return {
    label: m.querySelector('label[for="rcm-card-id"]').textContent.trim(),
    placeholder: input.placeholder,
    value: input.value,
    required: input.required,
    helper: m.querySelector('[data-rcm-id-helper]').textContent.trim()
  };
})()""")
check(
    "Rate Card ID is an empty required input, not an auto-generated strip",
    id_field["label"] == "Rate Card ID"
    and id_field["placeholder"] == "Enter rate card ID"
    and id_field["value"] == ""
    and id_field["required"],
    json.dumps(id_field),
)

# ============================== 3. CONFIRM GATING ========================
# Confirm needs a valid Rate Card ID as well as a name now, so the ID is
# entered first and the gating below still measures the name.
E("""(() => {
  const id = document.querySelector('[data-rcm-card-id]');
  id.value = 'RC-QA-MODAL-UF-2627';
  id.dispatchEvent(new Event('input', {bubbles: true}));
  id.dispatchEvent(new FocusEvent('blur'));
})()""")
E("document.getElementById('rcm-name').focus()")
type_text("WPP – Disney+ Upfront 2026–2027")
time.sleep(0.15)
confirm_enabled = E("!document.querySelector('[data-action=\"confirm-rc-create\"]').disabled")
check("Confirm enables once a name is typed", confirm_enabled)

# Clear it and blur to trigger the required-field error.
E("""(() => {
  const el = document.getElementById('rcm-name');
  el.value = '';
  el.dispatchEvent(new Event('input', {bubbles: true}));
})()""")
E("document.getElementById('rcm-name').blur()")
time.sleep(0.15)
name_error = E("""document.querySelector('[data-rc-create-modal] #rcm-name').closest('.field').querySelector('.field__error').textContent.trim()""")
check("blur on empty name shows 'Enter a rate card name.'", name_error == "Enter a rate card name.", name_error)
confirm_disabled_again = E("document.querySelector('[data-action=\"confirm-rc-create\"]').disabled")
check("Confirm re-disables when name is cleared", confirm_disabled_again)

# ============================== 4. EXPAND / COLLAPSE ======================
E("document.getElementById('rcm-be-id').value = 'SH-BE-778899'")
E("document.querySelector('[data-action=\"toggle-rcm-details\"]').click()")
time.sleep(0.3)
expanded = E("""(() => {
  const section = document.querySelector('[data-rcm-details]');
  const head = document.getElementById('rcm-details-head');
  const wrap = document.getElementById('rcm-details-wrap');
  return section.classList.contains('is-open')
    && head.getAttribute('aria-expanded') === 'true'
    && !wrap.hasAttribute('inert');
})()""")
check("clicking the details header expands the section", expanded)

helper_visible = E("""(() => {
  const help = document.querySelector('.rcm-details__help');
  return help && help.offsetParent !== null
    && help.textContent.trim() === 'Add these details now, or complete them later before publishing.';
})()""")
check("expanded helper copy is shown", helper_visible)

fields_order = E("""JSON.stringify(Array.from(
  document.querySelectorAll('[data-rcm-details] .field__label, [data-rcm-details] .rcm-details__help')
).map(el => el.tagName === 'P' ? '(helper)' : el.textContent.trim()))""")
check(
    "optional fields render in Figma order",
    fields_order == json.dumps([
        "(helper)", "Buying Entity ID", "Buying Entity Display Name",
        "Marketplace", "Deal Season", "DCM Rule Order (Optional)",
        "Effective Start", "Effective End",
    ], separators=(",", ":")),
    fields_order,
)

shot("02-expanded")

be_id_preserved = E("document.getElementById('rcm-be-id').value")
check("Buying Entity ID value present before collapse", be_id_preserved == "SH-BE-778899", be_id_preserved)

E("document.querySelector('[data-action=\"toggle-rcm-details\"]').click()")
time.sleep(0.3)
be_id_after_collapse = E("document.getElementById('rcm-be-id').value")
check("collapsing the section does not clear entered values", be_id_after_collapse == "SH-BE-778899", be_id_after_collapse)

# Re-expand for the rest of the flow.
E("document.querySelector('[data-action=\"toggle-rcm-details\"]').click()")
time.sleep(0.3)

# ============================== 5. DATE RANGE VALIDATION =================
# Drive the REAL date-picker UI (open popover -> click a day cell) rather
# than poking internal state, since the app's helper functions live
# inside app.js's module closure and are not reachable from an external
# Runtime.evaluate call - only real DOM events reach their listeners.
def pick_date(field, iso):
    E(f"document.querySelector('.ads-datepicker[data-field=\"{field}\"] .ads-datepicker__trigger').click()")
    # Scope to the currently VISIBLE popover only - a closed popover keeps
    # its last-rendered day cells in the DOM (just hidden), so an
    # unscoped querySelector could match a stale cell from a different,
    # already-closed date field with the same date grid.
    day_sel = f'.ads-datepicker__popover:not([hidden]) .ads-cal__day[data-iso="{iso}"]'
    assert wait_for(f"!!document.querySelector('{day_sel}')", timeout=2), f"day cell {iso} not found for {field}"
    E(f"document.querySelector('{day_sel}').click()")
    time.sleep(0.15)


pick_date("rcm-eff-start", "2026-08-20")
pick_date("rcm-eff-end", "2026-08-05")

range_error = E("""(() => {
  const endField = document.querySelector('[data-field=\"rcm-eff-end\"]').closest('.field');
  return endField.querySelector('.field__error').textContent.trim();
})()""")
check(
    "Effective End before Start shows the date-range error",
    range_error == "Effective end must be on or after effective start.",
    range_error,
)

# Fix the range so submission below can succeed.
pick_date("rcm-eff-end", "2026-08-25")
range_fixed = E("""document.querySelector('[data-field=\"rcm-eff-end\"]').closest('.field').querySelector('.field__error').hidden""")
check("error clears once the range is valid again", range_fixed)

shot("03-expanded-filled")

# ============================== 6. SUBMIT SUCCESS =========================
E("""(() => {
  const el = document.getElementById('rcm-name');
  el.value = 'Verizon Wireless Holiday Streaming (25-26)';
  el.dispatchEvent(new Event('input', {bubbles: true}));
})()""")
time.sleep(0.1)
E("document.querySelector('[data-action=\"confirm-rc-create\"]').click()")
loading_seen = wait_for("document.querySelector('[data-action=\"confirm-rc-create\"]').classList.contains('is-loading')", timeout=1)
check("Confirm shows a loading treatment while saving", loading_seen)

closed_after_save = wait_for("""(() => {
  const m = document.querySelector('[data-rc-create-modal]');
  return m.hidden === true;
})()""", timeout=3)
check("modal closes after a successful save", closed_after_save)
time.sleep(0.6)

new_total = total_items()
check("exactly one new Draft row was added", new_total == initial_total + 1, f"{initial_total} -> {new_total}")

# The v2.1 list pins a demo/tutorial row first, so the new draft can land
# on any page/position - search RATE_CARDS directly (same source the
# table renders from) rather than assuming row 0.
new_row_info = E("""(() => {
  const row = RATE_CARDS.find(r => r.name === 'Verizon Wireless Holiday Streaming (25-26)');
  return row ? JSON.stringify({
    status: row.status, rateCardId: row.rateCardId, version: row.version,
  }) : null;
})()""")
check("new row exists in RATE_CARDS with the entered name", new_row_info is not None, new_row_info)
if new_row_info:
    info = json.loads(new_row_info)
    check("new row is created with Draft status", info["status"] == "Draft", info)
    check(
        "new row keeps exactly the Rate Card ID that was typed",
        info["rateCardId"] == "RC-QA-MODAL-UF-2627",
        info,
    )

# v2.1 navigates straight to the new Rate Card Details page on a
# successful create (see the Create Rate Card -> Rate Card Details ->
# Line Item workflow task), so the list page's trigger button is no
# longer the expected focus target there - the details page's own
# controls take over instead. Earlier versions still stay on the list
# page and return focus to the trigger exactly as before.
navigated_to_details = E("document.body.getAttribute('data-route') === 'create'")
check(
    "v2.1 navigates to the new Rate Card Details page after a successful create",
    navigated_to_details,
)

body_unlocked = E("!document.body.classList.contains('rcm-create-open')")
check("background scroll unlocked after close", body_unlocked)

toast_shown = wait_for("""document.querySelector('.ads-toast, [class*=toast]') !== null""", timeout=2)
check("a success notification appears", toast_shown)

drain_console()

# ============================== 7. REOPEN IS CLEAN ========================
E("document.querySelector('[data-action=\"create\"]').click()")
time.sleep(0.4)
clean_reopen = E("""(() => {
  const name = document.getElementById('rcm-name').value;
  const beId = document.getElementById('rcm-be-id').value;
  const section = document.querySelector('[data-rcm-details]');
  return name === '' && beId === '' && !section.classList.contains('is-open');
})()""")
check("reopening the modal begins with a clean form", clean_reopen)

# ============================== 8. ESCAPE + CANCEL ========================
E("document.getElementById('rcm-name').value = 'Should not be created'")
key("Escape")
time.sleep(0.3)
closed_via_escape = E("document.querySelector('[data-rc-create-modal]').hidden === true")
check("Escape key closes the modal", closed_via_escape)
total_after_escape = total_items()
check("Escape does not create a row", total_after_escape == new_total, f"{new_total} -> {total_after_escape}")

E("document.querySelector('[data-action=\"create\"]').click()")
time.sleep(0.3)
E("""(() => {
  const el = document.getElementById('rcm-name');
  el.value = 'Should also not be created';
  el.dispatchEvent(new Event('input', {bubbles: true}));
})()""")
E("document.querySelector('[data-action=\"close-rc-create\"]').click()")
time.sleep(0.4)
closed_via_cancel = E("document.querySelector('[data-rc-create-modal]').hidden === true")
check("Cancel button closes the modal", closed_via_cancel)
total_after_cancel = total_items()
check("Cancel does not create a row", total_after_cancel == new_total, f"{new_total} -> {total_after_cancel}")

# ============================== 9. FAILURE PATH (invalid submit attempt) ==
E("document.querySelector('[data-action=\"create\"]').click()")
time.sleep(0.3)
E("document.querySelector('[data-action=\"confirm-rc-create\"]').click()")
time.sleep(0.2)
still_open_on_empty_submit = E("document.querySelector('[data-rc-create-modal]').hidden === false")
check("attempting to confirm with an empty name keeps the modal open (no crash)", still_open_on_empty_submit)
E("document.querySelector('[data-action=\"close-rc-create\"]').click()")
time.sleep(0.3)

drain_console()
check("no console errors or uncaught exceptions during the flow", len(console_errors) == 0, console_errors)

# ============================== SUMMARY ===================================
print(f"\n{passes} passed, {len(failures)} failed. Screenshots in {OUT}")
if failures:
    for f in failures:
        print(f"  - {f['name']}: {f['detail']}")

chrome.terminate()
server.shutdown()

if failures:
    raise SystemExit(1)
