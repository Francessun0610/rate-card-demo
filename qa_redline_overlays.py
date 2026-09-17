"""Redline overlay gallery QA.

Covers the modal and toast galleries: registry inventory, sidebar entry
points, navigation, staging every registered entry, dialog and live-region
semantics, inspection, logical measurement under scale, breakpoint behavior,
state isolation and cleanup.

qa_redline.py covers the Redline shell and inspection. qa_redline_state.py
covers entry-page state preservation. This suite covers only the galleries.

Run with: python3 qa_redline_overlays.py
"""

import base64
import json
import os
import re
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import urlopen

import websocket

ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = 8993
DEBUG_PORT = 9293
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
OUT = "/tmp/rate-card-redline-overlay-qa"
os.makedirs(OUT, exist_ok=True)

BREAKPOINTS = [
    ("1024", 1024, 760),
    ("1280", 1280, 800),
    ("1440", 1440, 900),
    ("1920", 1920, 1080),
    ("2560", 2560, 1440),
]


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
            ".jpg": "image/jpeg",
            ".json": "application/json",
            ".csv": "text/csv",
        }.get(os.path.splitext(filename)[1], "text/plain")
        with open(filename, "rb") as handle:
            payload = handle.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
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
profile = "/tmp/rate_card_redline_overlay_profile"
os.makedirs(profile, exist_ok=True)
chrome = subprocess.Popen(
    [
        CHROME,
        f"--remote-debugging-port={DEBUG_PORT}",
        f"--user-data-dir={profile}",
        "--headless=new",
        "--remote-allow-origins=*",
        "--no-first-run",
        "--window-size=1600,1000",
        "about:blank",
    ],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
time.sleep(1.4)
tabs = json.loads(urlopen(f"http://127.0.0.1:{DEBUG_PORT}/json").read())
ws_url = next(tab["webSocketDebuggerUrl"] for tab in tabs if tab.get("type") == "page")
ws = websocket.create_connection(ws_url)
message_id = 0
failures = []
passes = 0
console_messages = []


def send(method, params=None):
    global message_id
    message_id += 1
    expected = message_id
    ws.send(json.dumps({"id": expected, "method": method, "params": params or {}}))
    while True:
        event = json.loads(ws.recv())
        if event.get("method") == "Runtime.exceptionThrown":
            details = event.get("params", {}).get("exceptionDetails", {})
            console_messages.append(
                (details.get("exception") or {}).get("description", details.get("text", ""))
            )
        if event.get("method") == "Runtime.consoleAPICalled":
            if event.get("params", {}).get("type") == "error":
                args = event.get("params", {}).get("args", [])
                console_messages.append(
                    " ".join(str(a.get("value", a.get("description", ""))) for a in args)
                )
        if event.get("id") == expected:
            return event


def evaluate(expression):
    result = send(
        "Runtime.evaluate",
        {"expression": expression, "returnByValue": True, "awaitPromise": True},
    )
    payload = result.get("result", {})
    if "exceptionDetails" in payload:
        raise RuntimeError(json.dumps(payload["exceptionDetails"])[:400])
    return payload.get("result", {}).get("value")


def check(name, condition, detail=""):
    global passes
    if condition:
        passes += 1
        print(f"[PASS] {name}")
    else:
        failures.append({"name": name, "detail": str(detail)[:400]})
        print(f"[FAIL] {name}: {str(detail)[:400]}")


def screenshot(name):
    payload = send("Page.captureScreenshot", {"format": "png"})
    data = payload.get("result", {}).get("data", "")
    with open(os.path.join(OUT, name + ".png"), "wb") as handle:
        handle.write(base64.b64decode(data))


def wait_for(expression, timeout=8):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if evaluate(expression):
                return True
        except RuntimeError:
            pass
        time.sleep(0.1)
    return False


def navigate(query=""):
    # Page.navigate resolves before the new document commits, so the old page
    # can satisfy the readiness probe. A sentinel on the outgoing document
    # makes the wait observe the new one.
    try:
        evaluate("window.__qaNavToken = 1")
    except Exception:
        pass
    send("Page.navigate", {"url": f"http://127.0.0.1:{PORT}/{query}"})
    wait_for(
        "!window.__qaNavToken && !!document.body"
        " && !!document.body.getAttribute('data-route')",
        12,
    )
    time.sleep(0.8)


def enter_redline():
    evaluate("window.RedlineMode.enable('qa')")
    wait_for("window.RedlineMode.debugState().active")
    time.sleep(0.35)


def exit_redline():
    evaluate("window.RedlineMode.disable()")
    time.sleep(0.4)


def click(selector):
    evaluate(f"document.querySelector({json.dumps(selector)}).click()")


def open_gallery(mode, timeout=14):
    click(f'[data-redline-action="gallery:{mode}"]')
    ready = wait_for("window.RedlineMode.debugState().previewPhase === 'ready'", timeout)
    time.sleep(1.0)
    return ready


def debug():
    return evaluate("window.RedlineMode.debugState()")


def set_breakpoint(bp_id, timeout=10):
    click(f'[data-redline-action="breakpoint:{bp_id}"]')
    ready = wait_for("window.RedlineMode.debugState().previewPhase === 'ready'", timeout)
    time.sleep(0.6)
    return ready


# What is actually painted inside the preview right now.
PREVIEW_STATE_JS = """
(() => {
  const frame = document.querySelector('.redline__preview');
  const doc = frame && frame.contentDocument;
  if (!doc || !doc.body) return { error: 'no preview document' };
  const view = doc.defaultView;
  const shown = el => {
    if (!el || el.hasAttribute('hidden')) return false;
    const s = view.getComputedStyle(el);
    const r = el.getBoundingClientRect();
    return s.display !== 'none' && s.visibility !== 'hidden'
      && Number(s.opacity) > 0.01 && r.width > 4 && r.height > 4;
  };
  const surfaces = [...doc.querySelectorAll(
    '[data-modal], [data-qe-discard], [data-quick-edit], [data-v2-remove-modal],'
    + ' #filter-panel, #v2-lines-filter, [data-rc-create-modal],'
    + ' [data-wpc-modal], [data-rcle]')].filter(shown).map(el => {
      const r = el.getBoundingClientRect();
      const panel = el.querySelector(
        '.modal__panel, .qsheet__panel, .fpanel__inner, .wpc-modal__panel,'
        + ' .rcle__panel') || el;
      const pr = panel.getBoundingClientRect();
      return {
        key: el.id || el.getAttributeNames().find(n => n.startsWith('data-')),
        role: el.getAttribute('role'),
        ariaModal: el.getAttribute('aria-modal'),
        labelledBy: el.getAttribute('aria-labelledby'),
        width: Math.round(r.width),
        height: Math.round(r.height),
        panelWidth: Math.round(pr.width),
        panelLeft: Math.round(pr.left),
        panelRight: Math.round(pr.right),
        panelTop: Math.round(pr.top),
        panelBottom: Math.round(pr.bottom),
        closeLabel: (el.querySelector('[aria-label]') || {}).ariaLabel || '',
      };
    });
  const toasts = [...doc.querySelectorAll('[data-toast]')].map(t => {
    const r = t.getBoundingClientRect();
    return {
      variant: t.getAttribute('data-variant'),
      role: t.getAttribute('role'),
      live: t.getAttribute('aria-live'),
      title: t.querySelector('[data-toast-title]').textContent,
      message: t.querySelector('[data-toast-message]').textContent,
      hasIcon: !!t.querySelector('[data-toast-icon]'),
      closeLabel: (t.querySelector('[data-action="close-toast"]') || {}).ariaLabel || '',
      frozen: !t.__timer,
      top: Math.round(r.top),
      right: Math.round(r.right),
      width: Math.round(r.width),
      height: Math.round(r.height),
    };
  });
  return {
    route: doc.body.getAttribute('data-route'),
    viewportWidth: view.innerWidth,
    viewportHeight: view.innerHeight,
    surfaces,
    toasts,
    rowCount: doc.querySelectorAll('[data-row-id]').length,
  };
})()
"""


def preview_state():
    return evaluate(PREVIEW_STATE_JS)


print("\n=== 1. REGISTRY INVENTORY ===")
navigate()
modals = evaluate("window.RateCardOverlayGallery.entries('modal')")
toasts = evaluate("window.RateCardOverlayGallery.entries('toast')")
check("Modal registry is populated", len(modals) >= 10, len(modals))
check("Toast registry is populated", len(toasts) >= 30, len(toasts))

all_entries = modals + toasts
ids = [entry["id"] for entry in all_entries]
check("Every entry has a stable id", all(bool(i) for i in ids))
check("Entry ids are unique", len(ids) == len(set(ids)),
      [i for i in ids if ids.count(i) > 1])
check(
    "Every entry carries required metadata",
    all(entry["group"] and entry["name"] and entry["source"] for entry in all_entries),
    [e["id"] for e in all_entries if not (e["group"] and e["name"] and e["source"])],
)
check(
    "Every modal records an ADS component",
    all(entry["ads"] for entry in modals),
    [e["id"] for e in modals if not e["ads"]],
)
check(
    "Every toast declares a supported variant",
    all(entry["variant"] in ("success", "error", "warning", "info") for entry in toasts),
    [(e["id"], e["variant"]) for e in toasts
     if e["variant"] not in ("success", "error", "warning", "info")],
)
repeat = evaluate("window.RateCardOverlayGallery.entries('modal').map(e => e.id)")
check("Registry ordering is deterministic", repeat == [e["id"] for e in modals])

# Coverage guard: every product dialog surface declared in the markup has to
# be reachable from the registry, so a new overlay cannot ship unregistered.
# Two kinds of surface are excluded by design:
#   - ADS Popover (date picker) is not an overlay gallery surface, it is
#     inspected in place on the page that owns it.
#   - Presentation surfaces ([data-rcle], #wpc-modal) explain the product to
#     an audience instead of being product UI, so they are not redlined.
PRESENTATION_SURFACES = ("data-rcle", "data-wpc-modal")
with open(os.path.join(ROOT, "index.html"), encoding="utf-8") as handle:
    markup = handle.read()
ANCHORS = {
    "data-modal": "[data-modal]",
    "data-quick-edit": "[data-quick-edit]",
    "data-qe-discard": "[data-qe-discard]",
    "data-v2-remove-modal": "[data-v2-remove-modal]",
    "data-rc-create-modal": "[data-rc-create-modal]",
    'id="filter-panel"': "#filter-panel",
    'id="v2-lines-filter"': "#v2-lines-filter",
}
declared = set()
for tag in re.findall(r"<[a-zA-Z][^>]*?>", markup, re.S):
    if 'role="dialog"' not in tag and 'role="alertdialog"' not in tag:
        continue
    if "ads-datepicker__popover" in tag:
        continue
    if any(anchor in tag for anchor in PRESENTATION_SURFACES):
        continue
    match = next((ANCHORS[a] for a in ANCHORS if a in tag), None)
    declared.add(match or " ".join(tag.split())[:70])
registered_sources = " ".join(entry["source"] for entry in modals)
unregistered = sorted(a for a in declared if a not in registered_sources)
check("Every product dialog surface in the markup is registered",
      not unregistered, unregistered)

# The inverse guard: presentation and explainer content must never come back
# into the gallery, which is a product inspection tool.
PRESENTATION_MARKERS = ("explainer", "data-rcle", "wpc-modal", "presentation",
                        "slide", "atlas")
presentation_entries = [
    entry["id"] for entry in all_entries
    if any(marker in (entry["id"] + " " + entry["source"] + " "
                      + (entry.get("route") or "")).lower()
           for marker in PRESENTATION_MARKERS)
]
check("No presentation or explainer page is registered as an overlay",
      not presentation_entries, presentation_entries)

print("\n=== 2. SIDEBAR ENTRY POINTS ===")
enter_redline()
rows = evaluate("""
[...document.querySelectorAll(
  '[data-redline-section="overlays"] .redline__overlay-entry'
)].map(b => ({
  label: b.getAttribute('aria-label'),
  text: b.querySelector('.redline__overlay-entry-name').textContent,
  chevron: b.querySelector('.redline__overlay-entry-chevron').textContent,
  pressed: b.getAttribute('aria-pressed'),
  tag: b.tagName,
}))""")
check("Exactly two overlay entry rows exist", len(rows) == 2, rows)
check("Row labels are Modals and Toasts",
      [r["text"] for r in rows] == ["Modals", "Toasts"], rows)
check("Rows use the documented accessible names",
      [r["label"] for r in rows] == ["Open modal gallery", "Open toast gallery"], rows)
check("Rows carry a right-facing chevron",
      all(r["chevron"] == "\u203a" for r in rows), rows)
check("Rows are buttons, so the whole row is clickable",
      all(r["tag"] == "BUTTON" for r in rows), rows)
check("Rows start unpressed", all(r["pressed"] == "false" for r in rows), rows)
check(
    "The sidebar does not list individual overlays",
    evaluate("""
      (() => {
        const section = document.querySelector('[data-redline-section="overlays"]');
        const names = [...section.querySelectorAll('.redline__overlay-entry-name')]
          .map(n => n.textContent);
        return names.length === 2 && !section.textContent.includes('of ');
      })()"""),
)
check(
    "The sidebar shows no overlay counts",
    not evaluate("""
      /\\d/.test(document.querySelector('[data-redline-section="overlays"]').textContent)"""),
)
check("Redline opens on the current page",
      debug()["previewMode"] == "current-page", debug()["previewMode"])
check("The gallery toolbar is hidden outside a gallery",
      evaluate("document.querySelector('[data-redline-gallery]').hidden"))

print("\n=== 3. NAVIGATION AND TOOLBAR ===")
check("Modal gallery opens", open_gallery("modal-gallery"))
info = debug()
check("Preview mode switches to modal-gallery",
      info["previewMode"] == "modal-gallery", info["previewMode"])
check("Modal gallery total matches the registry",
      info["galleryTotal"] == len(modals), (info["galleryTotal"], len(modals)))
check("Modals row reports itself as selected",
      evaluate("""document.querySelector('[data-redline-action="gallery:modal-gallery"]')
        .getAttribute('aria-pressed')""") == "true")
check("The gallery toolbar is visible",
      not evaluate("document.querySelector('[data-redline-gallery]').hidden"))
label = evaluate("document.querySelector('[data-redline-gallery-label]').textContent")
check("The toolbar names the overlay, its state and its position",
      "1 of %d" % len(modals) in label and modals[0]["name"] in label, label)
check("Previous is disabled at the first entry",
      evaluate("""document.querySelector('[data-redline-action="gallery:previous"]').disabled"""))
check("Next is enabled at the first entry",
      not evaluate("""document.querySelector('[data-redline-action="gallery:next"]').disabled"""))

click('[data-redline-action="gallery:next"]')
time.sleep(0.8)
check("Next advances the entry", debug()["galleryEntryId"] == modals[1]["id"],
      debug()["galleryEntryId"])
click('[data-redline-action="gallery:previous"]')
time.sleep(0.8)
check("Previous returns to the entry before it",
      debug()["galleryEntryId"] == modals[0]["id"], debug()["galleryEntryId"])

evaluate("""document.dispatchEvent(new KeyboardEvent('keydown',
  { key: 'ArrowRight', bubbles: true }))""")
time.sleep(0.8)
check("Right Arrow advances the entry", debug()["galleryEntryId"] == modals[1]["id"],
      debug()["galleryEntryId"])
evaluate("""document.dispatchEvent(new KeyboardEvent('keydown',
  { key: 'ArrowLeft', bubbles: true }))""")
time.sleep(0.8)
check("Left Arrow steps back", debug()["galleryEntryId"] == modals[0]["id"],
      debug()["galleryEntryId"])

# Arrow keys must not steal typing from a field inside an overlay.
evaluate("""
  (() => {
    const input = document.createElement('input');
    input.id = 'qa-arrow-probe';
    document.body.appendChild(input);
    input.focus();
  })()""")
evaluate("""document.getElementById('qa-arrow-probe').dispatchEvent(
  new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }))""")
time.sleep(0.5)
check("Arrow shortcuts are ignored while focus is in a field",
      debug()["galleryEntryId"] == modals[0]["id"], debug()["galleryEntryId"])
evaluate("document.getElementById('qa-arrow-probe').remove()")

# Reset reopens an overlay the user dismissed by hand.
evaluate("""
  (() => {
    const doc = document.querySelector('.redline__preview').contentDocument;
    const cancel = doc.querySelector('[data-action="cancel-delete"]');
    if (cancel) cancel.click();
  })()""")
time.sleep(0.5)
dismissed = preview_state()
check("An overlay can be dismissed inside the preview",
      not dismissed["surfaces"], dismissed["surfaces"])
click('[data-redline-action="gallery:reset"]')
time.sleep(0.9)
check("Reset reopens the selected overlay", bool(preview_state()["surfaces"]))

check("Toast gallery opens", open_gallery("toast-gallery"))
info = debug()
check("Preview mode switches to toast-gallery",
      info["previewMode"] == "toast-gallery", info["previewMode"])
check("Toast gallery total matches the registry",
      info["galleryTotal"] == len(toasts), (info["galleryTotal"], len(toasts)))
check("Switching gallery type resets to the first entry", info["galleryIndex"] == 0)
check("Switching gallery type clears the previous overlay",
      not preview_state()["surfaces"], preview_state()["surfaces"])
check("Modals row is no longer selected",
      evaluate("""document.querySelector('[data-redline-action="gallery:modal-gallery"]')
        .getAttribute('aria-pressed')""") == "false")

# Toolbar typography and fit. Every label reads at the shell body/small
# size (14/20) and stays centred and unclipped at each shell width.
open_gallery("modal-gallery")
TOOLBAR_METRICS_JS = """
(() => {
  const bar = document.querySelector('[data-redline-gallery]');
  const barRect = bar.getBoundingClientRect();
  const read = el => {
    const s = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    return {
      name: el.className.replace('redline__gallery-', ''),
      fontSize: parseFloat(s.fontSize),
      fontFamily: s.fontFamily,
      fontWeight: s.fontWeight,
      lineHeight: s.lineHeight,
      height: Math.round(r.height),
      offCentre: Math.abs((r.top + r.bottom) / 2 - (barRect.top + barRect.bottom) / 2),
      clipped: r.top < barRect.top - 0.5 || r.bottom > barRect.bottom + 0.5
        || r.right > barRect.right + 0.5 || r.left < barRect.left - 0.5,
      scrollsHorizontally: el.scrollWidth > Math.ceil(r.width) + 1,
    };
  };
  return {
    barHeight: Math.round(barRect.height),
    controls: [...bar.querySelectorAll(
      '.redline__gallery-back, .redline__gallery-label,'
      + ' .redline__gallery-step, .redline__gallery-reset')].map(read),
    labelTitle: bar.querySelector('[data-redline-gallery-label]').title,
    labelText: bar.querySelector('[data-redline-gallery-label]').textContent,
    labelEllipsis: getComputedStyle(
      bar.querySelector('[data-redline-gallery-label]')).textOverflow,
  };
})()
"""
toolbar_issues = []
toolbar_shape = None
for shell_width in (1024, 1280, 1440, 1920):
    send("Emulation.setDeviceMetricsOverride", {
        "width": shell_width, "height": 900,
        "deviceScaleFactor": 1, "mobile": False,
    })
    time.sleep(0.6)
    metrics = evaluate(TOOLBAR_METRICS_JS)
    toolbar_shape = metrics
    for control in metrics["controls"]:
        where = (shell_width, control["name"])
        if control["fontSize"] < 14:
            toolbar_issues.append((where, "font-size " + str(control["fontSize"])))
        if "Open Sans" not in control["fontFamily"]:
            toolbar_issues.append((where, "font-family " + control["fontFamily"]))
        if control["offCentre"] > 1.5:
            toolbar_issues.append((where, "off centre by " + str(control["offCentre"])))
        if control["clipped"]:
            toolbar_issues.append((where, "clipped"))
        if control["scrollsHorizontally"] and control["name"] != "label":
            toolbar_issues.append((where, "text overflows its control"))
    screenshot("toolbar-%d" % shell_width)
send("Emulation.clearDeviceMetricsOverride")
time.sleep(0.5)
check("Toolbar text is at least 14px, centred and unclipped at every width",
      not toolbar_issues, toolbar_issues)
check("The toolbar keeps a single-row height", toolbar_shape["barHeight"] == 44,
      toolbar_shape["barHeight"])
check("A truncated page name still exposes its full text as a tooltip",
      toolbar_shape["labelTitle"] == toolbar_shape["labelText"]
      and toolbar_shape["labelEllipsis"] == "ellipsis", toolbar_shape)

click('[data-redline-action="gallery:back"]')
time.sleep(1.0)
check("Back to page returns to current-page mode",
      debug()["previewMode"] == "current-page", debug()["previewMode"])
check("Back to page hides the toolbar",
      evaluate("document.querySelector('[data-redline-gallery]').hidden"))

print("\n=== 4. MODAL PREVIEW: EVERY REGISTERED STATE ===")
open_gallery("modal-gallery")
modal_misses = []
backdrop_escapes = []
semantics_issues = []
phantom_selection = []
focus_issues = []
for index, entry in enumerate(modals):
    if index:
        click('[data-redline-action="gallery:next"]')
        time.sleep(0.75)
    # Several entries reach their overlay by driving real controls. Those
    # synthetic clicks must not register as an inspection selection.
    if debug()["hasLockedSelection"]:
        phantom_selection.append(entry["id"])
    # Focus has to land inside the overlay, the same as it does in the
    # product, or a keyboard user cannot reach what they are inspecting.
    if not evaluate("""
      (() => {
        const doc = document.querySelector('.redline__preview').contentDocument;
        const active = doc.activeElement;
        if (!active) return false;
        return !!active.closest(
          '[data-modal], [data-qe-discard], [data-quick-edit],'
          + ' [data-v2-remove-modal], #filter-panel, #v2-lines-filter,'
          + ' [data-rc-create-modal], [data-wpc-modal], [data-rcle]');
      })()"""):
        focus_issues.append(entry["id"])
    state = preview_state()
    surfaces = state.get("surfaces", [])
    if not surfaces:
        modal_misses.append(entry["id"])
        continue
    if entry["route"] and state["route"] != entry["route"]:
        modal_misses.append(f'{entry["id"]} (route {state["route"]})')
    for surface in surfaces:
        # The overlay must stay inside the preview viewport, which is what
        # keeps it off the Redline header, sidebar and inspector.
        if (surface["panelLeft"] < -2 or surface["panelTop"] < -2
                or surface["panelRight"] > state["viewportWidth"] + 2
                or surface["panelBottom"] > state["viewportHeight"] + 2):
            backdrop_escapes.append((entry["id"], surface["key"],
                                     surface["panelLeft"], surface["panelRight"]))
        if surface["role"] not in ("dialog", "alertdialog"):
            semantics_issues.append((entry["id"], surface["key"], surface["role"]))
        if not surface["labelledBy"]:
            semantics_issues.append((entry["id"], surface["key"], "no aria-labelledby"))

check("Every registered modal state renders", not modal_misses, modal_misses)
check("No modal is clipped by or escapes the preview viewport",
      not backdrop_escapes, backdrop_escapes)
check("Every modal surface has dialog semantics and an accessible name",
      not semantics_issues, semantics_issues)
check("Staging an entry never leaves a phantom selection",
      not phantom_selection, phantom_selection)
check("Focus lands inside every staged overlay", not focus_issues, focus_issues)

check(
    "No overlay paints over Redline chrome",
    evaluate("""
      (() => {
        const canvas = document.querySelector('[data-redline-canvas]')
          .getBoundingClientRect();
        const frame = document.querySelector('.redline__preview')
          .getBoundingClientRect();
        return frame.left >= canvas.left - 1 && frame.right <= canvas.right + 1
          && frame.top >= canvas.top - 1 && frame.bottom <= canvas.bottom + 1;
      })()"""),
)
check(
    "Gallery controls live outside the inspected document",
    evaluate("""
      (() => {
        const doc = document.querySelector('.redline__preview').contentDocument;
        return !doc.querySelector('[data-redline-gallery], .redline__overlay-entry');
      })()"""),
)

print("\n=== 5. TOAST PREVIEW: EVERY REGISTERED STATE ===")
open_gallery("toast-gallery")
toast_misses = []
unfrozen = []
role_issues = []
icon_issues = []
close_issues = []
background_issues = []
stack_orders = {}
for index, entry in enumerate(toasts):
    if index:
        click('[data-redline-action="gallery:next"]')
        time.sleep(0.7)
    state = preview_state()
    rendered = state.get("toasts", [])
    if not rendered:
        toast_misses.append(entry["id"])
        continue
    # Toasts stack over the page their flow runs on, never over whatever
    # page the previous gallery entry happened to leave behind.
    if state["route"] != (entry["route"] or "list"):
        background_issues.append((entry["id"], state["route"]))
    for toast in rendered:
        if not toast["frozen"]:
            unfrozen.append(entry["id"])
        expected_live = "assertive" if toast["variant"] in ("warning", "error") else "polite"
        if toast["role"] != "status" or toast["live"] != expected_live:
            role_issues.append((entry["id"], toast["role"], toast["live"]))
        # Status must not be carried by color alone.
        if not toast["hasIcon"]:
            icon_issues.append(entry["id"])
        if toast["closeLabel"] != "Dismiss notification":
            close_issues.append((entry["id"], toast["closeLabel"]))
    if entry["group"] == "Stacks":
        stack_orders[entry["id"]] = [t["top"] for t in rendered]

check("Every registered toast state renders", not toast_misses, toast_misses)
check("Every toast is staged over its own page", not background_issues,
      background_issues[:6])
check("Auto-dismiss is frozen for every toast", not unfrozen, sorted(set(unfrozen)))
check("Toast roles and live-region politeness are correct", not role_issues, role_issues[:6])
check("Every toast carries a status icon, not color alone",
      not icon_issues, sorted(set(icon_issues)))
check("Every toast has an accessible close label", not close_issues, close_issues[:6])
check(
    "Stacked toasts render in order with no overlap",
    all(tops == sorted(tops) and len(set(tops)) == len(tops)
        for tops in stack_orders.values()),
    stack_orders,
)
check("The largest registered stack shows every toast",
      max((len(v) for v in stack_orders.values()), default=0) >= 4, stack_orders)

toast_positions = preview_state()["toasts"]
check(
    "Toasts are positioned against the preview viewport, not the browser",
    all(t["right"] <= preview_state()["viewportWidth"] + 2 for t in toast_positions),
    toast_positions,
)

print("\n=== 6. INSPECTION ===")
open_gallery("modal-gallery")
selected = evaluate("""
  (() => {
    const doc = document.querySelector('.redline__preview').contentDocument;
    const title = doc.querySelector('[data-modal] .modal__title');
    if (!title) return null;
    const r = title.getBoundingClientRect();
    title.dispatchEvent(new MouseEvent('click', {
      bubbles: true, composed: true, clientX: r.left + 4, clientY: r.top + 4 }));
    return { width: Math.round(r.width), height: Math.round(r.height) };
  })()""")
time.sleep(0.6)
check("A modal element can be selected", bool(debug()["hasLockedSelection"]))
summary = debug()["selectionSummary"]
check("The selection summary describes the modal element",
      summary and summary != "Nothing selected.", summary)
inspector_text = evaluate(
    "document.querySelector('.redline__inspector').textContent")
check("The inspector reports the selected element",
      "Width" in inspector_text and "Height" in inspector_text,
      inspector_text[:160])

evaluate("""document.querySelector('[data-redline-action="toggle:typography"]').click()""")
time.sleep(0.5)
check("Typography inspection works in a gallery",
      "Font" in evaluate("document.querySelector('.redline__inspector').textContent"))
evaluate("""document.querySelector('[data-redline-action="toggle:typography"]').click()""")
evaluate("""document.querySelector('[data-redline-action="toggle:color"]').click()""")
time.sleep(0.6)
color_roles = evaluate("""
  [...document.querySelectorAll('.redline__inspector .redline__color-role-name')]
    .map(n => n.textContent)""")
check("Color inspection works in a gallery", len(color_roles) > 0, color_roles)
evaluate("""document.querySelector('[data-redline-action="toggle:color"]').click()""")
time.sleep(0.4)

click('[data-redline-action="gallery:next"]')
time.sleep(0.9)
check("Selection clears when the entry changes",
      not debug()["hasLockedSelection"])

open_gallery("toast-gallery")
evaluate("""
  (() => {
    const doc = document.querySelector('.redline__preview').contentDocument;
    const title = doc.querySelector('[data-toast] [data-toast-message]');
    const r = title.getBoundingClientRect();
    title.dispatchEvent(new MouseEvent('click', {
      bubbles: true, composed: true, clientX: r.left + 2, clientY: r.top + 2 }));
  })()""")
time.sleep(0.6)
check("A toast element can be selected", bool(debug()["hasLockedSelection"]))

print("\n=== 7. LOGICAL MEASUREMENT UNDER SCALE ===")
open_gallery("modal-gallery")
set_breakpoint("2560")
scaled = debug()
check("A 2560 gallery preview is scaled down", scaled["previewScale"] < 1,
      scaled["previewScale"])
check("The header reports the logical viewport and scale",
      evaluate("document.querySelector('[data-redline-viewport-info]').textContent")
      .startswith("2560 \u00d7 1440 ("),
      evaluate("document.querySelector('[data-redline-viewport-info]').textContent"))
measured = evaluate("""
  (() => {
    const doc = document.querySelector('.redline__preview').contentDocument;
    const panel = doc.querySelector('[data-modal] .modal__panel');
    if (!panel) return null;
    const r = panel.getBoundingClientRect();
    panel.dispatchEvent(new MouseEvent('click', {
      bubbles: true, composed: true, clientX: r.left + 4, clientY: r.top + 4 }));
    return Math.round(r.width);
  })()""")
time.sleep(0.7)
reported = evaluate("""
  (() => {
    const rows = [...document.querySelectorAll('.redline__inspector *')];
    const label = rows.find(n => n.textContent.trim() === 'Width');
    const value = label && label.nextElementSibling;
    return value ? value.textContent.trim() : '';
  })()""")
check(
    "The inspector reports logical CSS pixels, not the scaled display size",
    measured is not None and reported.startswith(str(measured)),
    {"logical": measured, "reported": reported, "scale": scaled["previewScale"]},
)
screenshot("measurement-2560")

print("\n=== 8. BREAKPOINT BEHAVIOR ===")
open_gallery("modal-gallery")
click('[data-redline-action="gallery:next"]')
time.sleep(0.7)
pinned = debug()["galleryEntryId"]
breakpoint_issues = []
for bp_id, width, height in BREAKPOINTS:
    if not set_breakpoint(bp_id):
        breakpoint_issues.append((bp_id, "preview not ready"))
        continue
    state = preview_state()
    info = debug()
    if info["galleryEntryId"] != pinned:
        breakpoint_issues.append((bp_id, "entry changed to " + info["galleryEntryId"]))
    if info["previewMode"] != "modal-gallery":
        breakpoint_issues.append((bp_id, "mode changed to " + info["previewMode"]))
    if state.get("viewportWidth") != width:
        breakpoint_issues.append((bp_id, "viewport width " + str(state.get("viewportWidth"))))
    if not state.get("surfaces"):
        breakpoint_issues.append((bp_id, "no overlay rendered"))
        continue
    surface = state["surfaces"][0]
    if (surface["panelLeft"] < -2 or surface["panelRight"] > width + 2
            or surface["panelTop"] < -2 or surface["panelBottom"] > height + 2):
        breakpoint_issues.append((bp_id, "overlay clipped: " + str(surface)))
    screenshot(f"modal-{bp_id}")
check("Every breakpoint renders the pinned modal correctly",
      not breakpoint_issues, breakpoint_issues)

set_breakpoint("current")
check("Current keeps the gallery open", debug()["previewMode"] == "modal-gallery",
      debug()["previewMode"])
check("Current keeps the selected entry", debug()["galleryEntryId"] == pinned,
      debug()["galleryEntryId"])
check("Current still renders the overlay", bool(preview_state().get("surfaces")))

open_gallery("toast-gallery")
toast_bp_issues = []
for bp_id, width, _height in BREAKPOINTS:
    if not set_breakpoint(bp_id):
        toast_bp_issues.append((bp_id, "preview not ready"))
        continue
    state = preview_state()
    rendered = state.get("toasts", [])
    if not rendered:
        toast_bp_issues.append((bp_id, "no toast rendered"))
        continue
    for toast in rendered:
        if toast["right"] > width + 2 or toast["top"] < -2:
            toast_bp_issues.append((bp_id, "toast outside viewport: " + str(toast)))
    screenshot(f"toast-{bp_id}")
check("Every breakpoint positions toasts inside the preview viewport",
      not toast_bp_issues, toast_bp_issues)
set_breakpoint("current")

print("\n=== 9. STATE ISOLATION ===")
exit_redline()
navigate()
baseline = evaluate("""
  (() => ({
    rows: document.querySelectorAll('[data-row-id]').length,
    firstName: (document.querySelector('[data-row-id] .name') || {}).textContent || '',
    route: document.body.getAttribute('data-route'),
    search: (document.querySelector('[data-action="search"]') || {}).value || '',
    storage: Object.keys(localStorage).sort().join('|'),
    url: location.href,
  }))()""")
enter_redline()
open_gallery("modal-gallery")

# Confirming a destructive dialog inside the gallery must do nothing.
evaluate("""
  (() => {
    const doc = document.querySelector('.redline__preview').contentDocument;
    const confirm = doc.querySelector('[data-action="confirm-delete"]');
    if (confirm) confirm.click();
  })()""")
time.sleep(0.7)
check("A destructive confirm inside the gallery is blocked",
      bool(preview_state().get("surfaces")),
      "the dialog closed, so the action was not blocked")
check("The preview list is unchanged after a blocked delete",
      preview_state()["rowCount"] == baseline["rows"],
      (preview_state()["rowCount"], baseline["rows"]))

# Walk every modal entry, then confirm nothing leaked to the source page.
for _ in range(len(modals) - 1):
    click('[data-redline-action="gallery:next"]')
    time.sleep(0.35)
open_gallery("toast-gallery")
for _ in range(6):
    click('[data-redline-action="gallery:next"]')
    time.sleep(0.25)

source = evaluate("""
  (() => ({
    rows: document.querySelectorAll('[data-row-id]').length,
    firstName: (document.querySelector('[data-row-id] .name') || {}).textContent || '',
    route: document.body.getAttribute('data-route'),
    search: (document.querySelector('[data-action="search"]') || {}).value || '',
    toasts: document.querySelectorAll('[data-toast]').length,
  }))()""")
check("The source page keeps its rows", source["rows"] == baseline["rows"],
      (source["rows"], baseline["rows"]))
check("The source page keeps its first record",
      source["firstName"] == baseline["firstName"],
      (source["firstName"], baseline["firstName"]))
check("The source page keeps its route", source["route"] == baseline["route"],
      source["route"])
check("The source page keeps its search value", source["search"] == baseline["search"])
check("Gallery toasts never replay on the source page", source["toasts"] == 0,
      source["toasts"])

print("\n=== 10. CLEANUP ===")
click('[data-redline-action="gallery:back"]')
time.sleep(1.0)
check("Back to page clears the gallery entry list",
      debug()["galleryTotal"] == 0, debug()["galleryTotal"])
check("Back to page removes every gallery overlay from the preview",
      not preview_state().get("surfaces") and not preview_state().get("toasts"),
      preview_state())
check("Back to page restores the preview route",
      preview_state()["route"] == baseline["route"], preview_state()["route"])

exit_redline()
after = evaluate("""
  (() => ({
    redlineNodes: document.querySelectorAll('.redline, [data-redline-ui]').length,
    frames: document.querySelectorAll('.redline__preview').length,
    toasts: document.querySelectorAll('[data-toast]').length,
    openModals: [...document.querySelectorAll('[data-modal], [data-quick-edit],'
      + ' [data-qe-discard], [data-v2-remove-modal]')].filter(n => !n.hidden).length,
    bodyClasses: document.body.className,
    storage: Object.keys(localStorage).sort().join('|'),
    route: document.body.getAttribute('data-route'),
    url: location.href,
    rows: document.querySelectorAll('[data-row-id]').length,
  }))()""")
check("Closing Redline removes all of its nodes", after["redlineNodes"] == 0,
      after["redlineNodes"])
check("Closing Redline removes the preview frame", after["frames"] == 0)
check("No gallery toast survives on the source page", after["toasts"] == 0)
check("No gallery overlay survives on the source page", after["openModals"] == 0)
check("The source page keeps its route", after["route"] == baseline["route"])
check("The source URL is unchanged", after["url"] == baseline["url"],
      (after["url"], baseline["url"]))
check("localStorage is unchanged", after["storage"] == baseline["storage"],
      (after["storage"], baseline["storage"]))
check("The source list is unchanged", after["rows"] == baseline["rows"])

print("\n=== 11. REPEATED ENTRY AND EXIT ===")
for cycle in range(3):
    enter_redline()
    open_gallery("modal-gallery")
    click('[data-redline-action="gallery:next"]')
    time.sleep(0.4)
    open_gallery("toast-gallery")
    time.sleep(0.3)
    exit_redline()
leak = evaluate("""
  (() => ({
    redlineNodes: document.querySelectorAll('.redline, [data-redline-ui]').length,
    toasts: document.querySelectorAll('[data-toast]').length,
    rows: document.querySelectorAll('[data-row-id]').length,
  }))()""")
check("Repeated entry and exit leaves no Redline nodes", leak["redlineNodes"] == 0,
      leak["redlineNodes"])
check("Repeated entry and exit leaves no toasts", leak["toasts"] == 0, leak["toasts"])
check("Repeated entry and exit leaves the list intact",
      leak["rows"] == baseline["rows"], leak["rows"])

print("\n=== 12. ENTRY FROM A NON-LIST ROUTE ===")
navigate("?section=create&mode=edit&cardId=RC-DAS-WPP-VIDEO-UF-2627")
enter_redline()
open_gallery("modal-gallery")
check("A gallery opens from the Edit Rate Card route",
      bool(preview_state().get("surfaces")), preview_state())
click('[data-redline-action="gallery:back"]')
time.sleep(1.2)
check("Back to page restores a non-list entry route",
      preview_state()["route"] == "create", preview_state()["route"])
exit_redline()
time.sleep(0.4)
check("Closing restores the non-list source route",
      evaluate("document.body.getAttribute('data-route')") == "create",
      evaluate("document.body.getAttribute('data-route')"))

print("\n=== 13. STABILITY ===")
real_errors = [m for m in console_messages if m and "favicon" not in m.lower()]
check("No console errors during the run", not real_errors, real_errors[:5])

print("\n" + "=" * 62)
print(f"PASS {passes}   FAIL {len(failures)}")
for failure in failures:
    print(f"  - {failure['name']}: {failure['detail']}")
print(f"screenshots: {OUT}")
print("=" * 62)

chrome.terminate()
server.shutdown()
raise SystemExit(1 if failures else 0)
