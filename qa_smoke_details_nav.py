"""Quick smoke test: Create modal -> Rate Card Details page navigation.
Not the full QA suite (see qa_rate_card_details.py once the full workflow
is built) - just checks the wiring done so far doesn't crash and lands on
the right page with the right header data."""

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
PORT = 8998
DEBUG_PORT = 9298
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
OUT = "/tmp/rate-card-details-smoke"
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

profile = "/tmp/rate_card_details_smoke_profile"
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


def type_text(text):
    for ch in text:
        send("Input.dispatchKeyEvent", {"type": "keyDown", "text": ch})
        send("Input.dispatchKeyEvent", {"type": "keyUp", "text": ch})


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
send("Page.navigate", {"url": f"http://127.0.0.1:{PORT}/index.html?version=2.1"})
wait_for("document.body.dataset.version === '2.1'")
wait_for("document.querySelectorAll('[data-rows] .row').length > 0")
time.sleep(0.4)
drain_console()

E("document.querySelector('[data-action=\"create\"]').click()")
time.sleep(0.3)
E("""(() => {
  // The Rate Card ID is entered by the user now, and Confirm stays
  // disabled until it is present and valid.
  const id = document.querySelector('[data-rcm-card-id]');
  id.value = 'RC-SMOKE-VERIZON-UF-2526';
  id.dispatchEvent(new Event('input', {bubbles: true}));
  id.dispatchEvent(new FocusEvent('blur'));
  const el = document.getElementById('rcm-name');
  el.value = 'Verizon Wireless Holiday Streaming (2025-2026)';
  el.dispatchEvent(new Event('input', {bubbles: true}));
})()""")
E("document.querySelector('[data-action=\"confirm-rc-create\"]').click()")
navigated = wait_for("document.body.getAttribute('data-route') === 'create'", timeout=3)
check("navigates to Rate Card Details page after Confirm", navigated)
time.sleep(0.5)
drain_console()

shot("01-details-page")

url_ok = E("""(() => {
  const u = new URL(location.href);
  return u.searchParams.get('section') === 'create'
    && u.searchParams.get('mode') === 'edit'
    && !!u.searchParams.get('cardId');
})()""")
check("URL reflects section=create&mode=edit&cardId=...", url_ok)

title = E("document.querySelector('[data-v2-title]').textContent.trim()")
# The app's existing display formatting turns a "(25-26)" hyphen year range
# into an en dash "(25-26)" for display, same convention used elsewhere in
# the product (see the "(25-26)" pattern in v2.js). The accessible/stored
# value keeps the hyphen the user typed.
check(
    "header title shows the entered name",
    title == "Verizon Wireless Holiday Streaming (2025-2026)",
    title,
)

meta_visible = E("document.querySelector('[data-v2-meta]').hidden === false")
check("meta row is visible", meta_visible)

status_text = E("document.querySelector('[data-v2-meta-status]').textContent.trim()")
check("status chip shows Draft", status_text == "Draft", status_text)

splitbtn_visible = E("document.querySelector('[data-v2-header-splitbtn]').hidden === false")
check("split button is visible", splitbtn_visible)

legacy_hidden = E("document.querySelector('[data-v2-header-actions-legacy]').hidden === true")
check("legacy two-button header is hidden", legacy_hidden)

# Save Rate Card saves LINE and PREM rows, so a card that was just
# created has nothing to save yet: both segments stay disabled and the
# dropdown cannot open until the first line or premium change.
split_disabled = E("""(() => {
  const wrap = document.querySelector('[data-v2-header-splitbtn]');
  return wrap.querySelector('.splitbtn__main').disabled
    && wrap.querySelector('.splitbtn__caret').disabled;
})()""")
check("split button starts disabled on a card with no line or premium changes", split_disabled)

E("document.querySelector('[data-v2-action=\"toggle-save-menu\"]').click()")
time.sleep(0.2)
check("disabled dropdown does not open", E("document.querySelector('.splitbtn__menu').hidden"))

empty_state_visible = E("""(() => {
  const empty = document.querySelector('[data-v2-empty="lines"]');
  return empty && !empty.hidden;
})()""")
check("empty line state is visible", empty_state_visible)

# Add one complete line item so there is unsaved work, which is what
# turns the split button on.
E("""document.querySelector('[data-v2-action="add-line"]').click()""")
time.sleep(0.4)
E("""(() => {
  const form = document.querySelector('[data-v2-form="line"]');
  const set = (name, value) => {
    const control = form.elements[name];
    if (!control) return;
    control.value = value;
    control.dispatchEvent(new Event('input', { bubbles: true }));
    control.dispatchEvent(new Event('change', { bubbles: true }));
    if (typeof window.syncAdsDropdown === 'function' && control.tagName === 'SELECT') {
      window.syncAdsDropdown(control);
    }
    control.dispatchEvent(new FocusEvent('focusout', { bubbles: true }));
  };
  const advertiser = form.elements.advertiserName;
  const product = form.elements.adProduct;
  const offering = form.elements.baseOffering;
  set('advertiserId', 'ADV-330184');
  set('advertiserName', advertiser.options[1] ? advertiser.options[1].value : 'Verizon');
  set('adProduct', product.options && product.options[1] ? product.options[1].value : 'Standard Video');
  set('baseOffering', offering.options[1] ? offering.options[1].value : '');
  set('rateType', 'CPM');
  set('baseRate', '34');
  set('currency', 'USD');
})()""")
time.sleep(0.6)
split_enabled = E("!document.querySelector('.splitbtn__main').disabled")
check("split button enables once a line item is added", split_enabled)

# Exercise the split button's dropdown + Save as draft.
E("document.querySelector('[data-v2-action=\"toggle-save-menu\"]').click()")
time.sleep(0.2)
menu_open = E("!document.querySelector('.splitbtn__menu').hidden")
check("dropdown opens", menu_open)
menu_items = E("""JSON.stringify(Array.from(document.querySelectorAll('.splitbtn__item')).map(b => b.textContent.trim()))""")
check("dropdown contains exactly one item: Save as draft", menu_items == json.dumps(["Save as draft"]), menu_items)

E("document.querySelector('.splitbtn__item').click()")
time.sleep(0.3)
toast_shown = wait_for("document.querySelector('.ads-toast, [class*=toast]') !== null", timeout=2)
check("Save as draft shows a success notification", toast_shown)

check(
    "split button disables again once the save succeeds",
    E("document.querySelector('.splitbtn__main').disabled"),
)

drain_console()
check("no console errors during the flow", len(console_errors) == 0, console_errors)

print(f"\n{passes} passed, {len(failures)} failed. Screenshots in {OUT}")
for f in failures:
    print(f"  - {f['name']}: {f['detail']}")

chrome.terminate()
server.shutdown()
if failures:
    raise SystemExit(1)
