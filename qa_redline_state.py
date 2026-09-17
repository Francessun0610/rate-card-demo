"""Redline Mode state-preservation QA.

Covers the matrix that qa_redline.py (shell + inspection) does not: entering
Redline from every route with real UI state, preserving that state across the
full breakpoint sequence, preview loading and failure states, source-page
restoration, data integrity, and repeated entry and exit.

Run with: python3 qa_redline_state.py
"""

import base64
import json
import os
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import urlopen

import websocket


ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = 8994
DEBUG_PORT = 9294
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
OUT = "/tmp/rate-card-redline-state-qa"
os.makedirs(OUT, exist_ok=True)

BREAKPOINTS = [
    ("1024", 1024, 760),
    ("1280", 1280, 800),
    ("1440", 1440, 900),
    ("1920", 1920, 1080),
    ("2560", 2560, 1440),
]

# Flipped by the failure-state tests so the preview request (and only the
# preview request) can be made to fail on demand.
PREVIEW_FAILURE_MODE = ""


class StaticHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        raw = self.path
        path = raw.split("?")[0] or "/index.html"
        if path == "/":
            path = "/index.html"
        is_preview = "redlinePreview=1" in raw
        if is_preview and PREVIEW_FAILURE_MODE == "404":
            self.send_response(404)
            self.end_headers()
            return
        if is_preview and PREVIEW_FAILURE_MODE == "503":
            self.send_response(503)
            self.end_headers()
            return
        if is_preview and PREVIEW_FAILURE_MODE == "empty":
            body = b"<!doctype html><html><body><p>no app here</p></body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
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
profile = "/tmp/rate_card_redline_state_profile"
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
time.sleep(1.3)
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
                    " ".join(str(arg.get("value", arg.get("description", ""))) for arg in args)
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
        detail = payload["exceptionDetails"]
        raise RuntimeError(json.dumps(detail)[:500])
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


def wait_for(expression, timeout=6):
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
    send("Page.navigate", {"url": f"http://127.0.0.1:{PORT}/{query}"})
    wait_for("!!document.body && !!document.body.getAttribute('data-route')", 10)
    time.sleep(0.7)


def enter_redline():
    evaluate("window.RedlineMode.enable('qa')")
    wait_for("window.RedlineMode.debugState().active")
    time.sleep(0.3)


def exit_redline():
    evaluate("window.RedlineMode.disable()")
    time.sleep(0.35)


def set_breakpoint(bp_id, timeout=8):
    evaluate(
        "document.querySelector('[data-redline-action=\"breakpoint:%s\"]').click()" % bp_id
    )
    if bp_id == "current":
        time.sleep(0.35)
        return True
    ready = wait_for(
        "window.RedlineMode.debugState().previewPhase === 'ready'", timeout
    )
    time.sleep(0.45)
    return ready


# Reads the same facts out of either the live document or the preview
# document, so source and preview can be compared field by field.
PAGE_STATE_JS = """
(doc => {
  if (!doc || !doc.body) return null;
  const search = doc.querySelector('[data-action="search"]');
  const sorted = doc.querySelector('.th--sortable[aria-sort]:not([aria-sort="none"])');
  const rows = [...doc.querySelectorAll('[data-row-id]')];
  const name = doc.querySelector('[data-v2-form="card"] input[name="name"], #rc-name');
  return {
    route: doc.body.getAttribute('data-route'),
    version: doc.body.getAttribute('data-version'),
    search: search ? search.value : null,
    sortKey: sorted ? sorted.getAttribute('data-sort-key') : null,
    sortDir: sorted ? sorted.getAttribute('aria-sort') : null,
    rowCount: rows.length,
    rowIds: rows.slice(0, 6).map(r => r.getAttribute('data-row-id')),
    selectedRows: rows.filter(r => r.getAttribute('aria-selected') === 'true'
      || r.classList.contains('is-selected')).map(r => r.getAttribute('data-row-id')),
    total: (doc.querySelector('[data-total]') || {}).textContent || '',
    pageSize: (doc.querySelector('.edl-select[data-field="page-size"]') || {})
      .getAttribute ? doc.querySelector('.edl-select[data-field="page-size"]').getAttribute('data-value') : null,
    goToPage: (doc.querySelector('.edl-select[data-field="go-to-page"]') || {})
      .getAttribute ? doc.querySelector('.edl-select[data-field="go-to-page"]').getAttribute('data-value') : null,
    filterPanelOpen: !!(doc.getElementById('filter-panel')
      && doc.getElementById('filter-panel').classList.contains('is-open')),
    marketplaceFilter: [...doc.querySelectorAll(
      '[data-filter-checkbox="marketplace"]')].filter(box => box.checked)
      .map(box => box.getAttribute('data-filter-value')).join(',') || null,
    cardName: name ? name.value : null,
    activeTab: (doc.querySelector('[data-v2-tab][aria-selected="true"]') || {}).getAttribute
      ? doc.querySelector('[data-v2-tab][aria-selected="true"]').getAttribute('data-v2-tab') : null,
    openAccordions: [...doc.querySelectorAll('[data-v2-accordion].is-open, [data-accordion].is-open')]
      .map(a => a.getAttribute('data-v2-accordion') || a.getAttribute('data-accordion')),
    lineQuery: (doc.querySelector('[data-v2-search="lines"]') || {}).value || '',
    atlasSlide: (doc.querySelector('[data-atlas-slide].is-active, .atlas-slide.is-active') || {})
      .getAttribute ? (doc.querySelector('[data-atlas-slide].is-active, .atlas-slide.is-active')
        .getAttribute('data-atlas-slide') || '') : '',
    bodyTextLength: (doc.body.innerText || '').trim().length,
    url: doc.defaultView ? doc.defaultView.location.search : ''
  };
})
"""

SOURCE_STATE = f"({PAGE_STATE_JS})(document)"
PREVIEW_STATE = f"""(() => {{
  const frame = document.querySelector('.redline__preview');
  if (!frame) return null;
  let doc = null;
  try {{ doc = frame.contentDocument; }} catch (_) {{ return null; }}
  return ({PAGE_STATE_JS})(doc);
}})()"""

# Fields that must match between the entry page and the preview. Row ids and
# totals are included so a "same page" claim also means "same data".
COMPARED = [
    "route", "version", "search", "sortKey", "sortDir", "rowCount", "rowIds",
    "selectedRows", "total", "pageSize", "goToPage", "marketplaceFilter",
    "cardName", "activeTab", "openAccordions", "lineQuery", "atlasSlide",
]


def compare_states(label, source, preview, fields=None):
    if not isinstance(source, dict) or not isinstance(preview, dict):
        check(f"{label} preview state readable", False, f"source={source} preview={preview}")
        return
    mismatches = {}
    for field in (fields or COMPARED):
        if source.get(field) != preview.get(field):
            mismatches[field] = {"source": source.get(field), "preview": preview.get(field)}
    check(f"{label} preserves entry state", not mismatches, json.dumps(mismatches))


def seed_list_state():
    """Search + sort + filter + page size + row selection on the list."""
    return evaluate(
        """(async () => {
      const wait = ms => new Promise(r => setTimeout(r, ms));
      const search = document.querySelector('[data-action="search"]');
      search.value = 'disney';
      search.dispatchEvent(new Event('input', {bubbles:true}));
      await wait(220);
      document.querySelector('[data-action="sort"][data-sort-key="name"]').click();
      await wait(200);
      document.querySelector('[data-action="toggle-filter"]').click();
      await wait(180);
      const box = document.querySelector(
        '[data-filter-checkbox="marketplace"][data-filter-value="Upfront"]');
      if (box) {
        box.checked = true;
        box.dispatchEvent(new Event('change', {bubbles: true}));
      }
      await wait(120);
      document.querySelector('[data-action="apply-filters"]').click();
      await wait(240);
      const row = document.querySelector('[data-row-id]');
      if (row) row.click();
      await wait(180);
      return true;
    })()"""
    )


try:
    send("Runtime.enable")
    send("Page.enable")

    # =====================================================================
    # 1. Entry from the rate card list with search, filter, sort, selection
    # =====================================================================
    print("\n== list entry ==")
    navigate("?version=2.0")
    seed_list_state()
    source_list = evaluate(SOURCE_STATE)
    check(
        "list seed applied",
        bool(source_list["search"]) and source_list["sortKey"] == "name"
        and source_list["marketplaceFilter"] == "Upfront" and source_list["selectedRows"],
        json.dumps(source_list),
    )

    enter_redline()
    check(
        "entry snapshot captured",
        evaluate("window.RedlineMode.debugState().hasAppSnapshot"),
        "no snapshot captured on enable",
    )
    # The first preset is the only load of the session, and it must explain
    # itself rather than leaving an unexplained empty canvas.
    evaluate("document.querySelector('[data-redline-action=\"breakpoint:1440\"]').click()")
    loading = evaluate(
        """(() => {
      const overlay = document.querySelector('[data-redline-preview-status]');
      return {
        phase: overlay.getAttribute('data-redline-preview-status'),
        hidden: overlay.hidden,
        title: overlay.querySelector('[data-redline-preview-title]').textContent,
        retryHidden: overlay.querySelector('[data-redline-action="preview:retry"]').hidden
      };
    })()"""
    )
    check(
        "loading is distinguished from failure",
        loading["phase"] == "loading" and not loading["hidden"]
        and loading["title"] == "Loading preview" and loading["retryHidden"],
        json.dumps(loading),
    )
    check(
        "first preset loads",
        wait_for("window.RedlineMode.debugState().previewPhase === 'ready'", 10),
        "preview never reached ready",
    )
    time.sleep(0.45)
    check(
        "snapshot applied to preview",
        evaluate("window.RedlineMode.debugState().appSnapshotApplied"),
        "bridge reported no restore",
    )
    compare_states("list 1440", source_list, evaluate(PREVIEW_STATE))
    screenshot("list-1440")

    # =====================================================================
    # 2. Full breakpoint sequence keeps the same page, data and UI state
    # =====================================================================
    print("\n== list breakpoint sequence ==")
    sequence = ["1024", "1280", "1440", "1920", "2560", "current"]
    reload_count = evaluate(
        """(() => {
      const frame = document.querySelector('.redline__preview');
      window.__qaLoads = 0;
      frame.addEventListener('load', () => { window.__qaLoads += 1; });
      return 0;
    })()"""
    )
    for bp_id in sequence:
        ready = set_breakpoint(bp_id)
        if bp_id == "current":
            state_now = evaluate(SOURCE_STATE)
            check("current returns to live document", state_now["route"] == "list", state_now)
            info = evaluate(
                "document.querySelector('[data-redline-viewport-info]').textContent"
            )
            check("current reports 100%", info.endswith("(100%)"), info)
            continue
        width, height = next((w, h) for i, w, h in BREAKPOINTS if i == bp_id)
        check(f"{bp_id} preview ready", ready, "preview did not reach ready")
        preview = evaluate(PREVIEW_STATE)
        compare_states(f"list {bp_id}", source_list, preview)
        check(
            f"{bp_id} preview not blank",
            isinstance(preview, dict) and preview["bodyTextLength"] > 200,
            preview.get("bodyTextLength") if isinstance(preview, dict) else preview,
        )
        geometry = evaluate(
            """(() => {
          const frame = document.querySelector('.redline__preview');
          const shell = document.querySelector('.redline__preview-shell');
          const stage = document.querySelector('.redline__stage');
          const shellRect = shell.getBoundingClientRect();
          const stageRect = stage.getBoundingClientRect();
          const debug = window.RedlineMode.debugState();
          return {
            innerWidth: frame.contentWindow.innerWidth,
            innerHeight: frame.contentWindow.innerHeight,
            cssWidth: parseFloat(frame.style.width),
            cssHeight: parseFloat(frame.style.height),
            scale: debug.previewScale,
            info: document.querySelector('[data-redline-viewport-info]').textContent,
            centeredX: Math.abs(
              (shellRect.left + shellRect.width / 2) - (stageRect.left + stageRect.width / 2)
            ),
            withinStage: shellRect.width <= stageRect.width + 1
              && shellRect.height <= stageRect.height + 1,
            pressed: document.querySelector('[data-redline-action="breakpoint:%s"]')
              .getAttribute('aria-pressed'),
            statusHidden: document.querySelector('[data-redline-preview-status]').hidden
          };
        })()"""
            % bp_id
        )
        check(
            f"{bp_id} applies logical viewport",
            geometry["innerWidth"] == width and geometry["cssWidth"] == width
            and geometry["cssHeight"] == height,
            json.dumps(geometry),
        )
        expected_scale = min(1.0, geometry["scale"])
        check(
            f"{bp_id} header reports logical size and scale",
            geometry["info"] == f"{width} \u00d7 {height} ({round(expected_scale * 100)}%)",
            geometry["info"],
        )
        check(
            f"{bp_id} scaled preview stays inside the canvas",
            geometry["withinStage"] and geometry["centeredX"] < 2,
            json.dumps(geometry),
        )
        check(f"{bp_id} highlighted in sidebar", geometry["pressed"] == "true", geometry["pressed"])
        check(f"{bp_id} status overlay cleared", geometry["statusHidden"], "status overlay visible")
        screenshot(f"list-seq-{bp_id}")

    check(
        "preset switching never remounts the product",
        evaluate("window.__qaLoads") == 0,
        f"iframe reloaded {evaluate('window.__qaLoads')} times across the sequence",
    )

    # =====================================================================
    # 3. Measurements stay in logical CSS pixels under scale
    # =====================================================================
    print("\n== logical measurements ==")
    set_breakpoint("2560")
    logical = evaluate(
        """(async () => {
      const frame = document.querySelector('.redline__preview');
      const doc = frame.contentDocument;
      const target = doc.querySelector('.page-header, .page__header, main section, .surface');
      if (!target) return {error: 'no target'};
      const rect = target.getBoundingClientRect();
      const box = target.getBoundingClientRect();
      target.dispatchEvent(new PointerEvent('pointermove', {bubbles: true, clientX: box.left + 5, clientY: box.top + 5}));
      target.dispatchEvent(new MouseEvent('click', {bubbles: true, clientX: box.left + 5, clientY: box.top + 5}));
      await new Promise(r => setTimeout(r, 400));
      const values = [...document.querySelectorAll('[data-redline-inspector] .redline__inspect-row')]
        .map(row => row.textContent.replace(/\\s+/g, ' ').trim());
      return {
        logicalWidth: Math.round(rect.width),
        scale: window.RedlineMode.debugState().previewScale,
        values
      };
    })()"""
    )
    reported = ""
    for entry in logical.get("values", []):
        if entry.startswith("Width"):
            reported = entry
    check(
        "inspector reports logical CSS pixels, not scaled pixels",
        str(logical.get("logicalWidth")) in reported,
        f"logical={logical.get('logicalWidth')} scale={logical.get('scale')} reported={reported}",
    )

    print("\n== selection across breakpoints ==")
    before = evaluate("window.RedlineMode.debugState()")
    set_breakpoint("1024")
    after = evaluate(
        """(() => {
      const debug = window.RedlineMode.debugState();
      return {
        locked: debug.hasLockedSelection,
        summary: debug.selectionSummary,
        lines: document.querySelectorAll('[data-redline-svg] line').length,
        labels: document.querySelectorAll('[data-redline-labels] > *').length
      };
    })()"""
    )
    check(
        "selection survives a breakpoint change",
        before["hasLockedSelection"] and after["locked"],
        json.dumps({"before": before["hasLockedSelection"], "after": after}),
    )
    check(
        "measurement overlays redraw after the change",
        after["lines"] > 0 and after["labels"] > 0,
        json.dumps(after),
    )

    stale = evaluate(
        """(async () => {
      const frame = document.querySelector('.redline__preview');
      const doc = frame.contentDocument;
      const target = doc.querySelector('[data-row-id]');
      if (!target) return {error: 'no row'};
      const box = target.getBoundingClientRect();
      target.dispatchEvent(new PointerEvent('pointermove', {bubbles: true, clientX: box.left + 5, clientY: box.top + 5}));
      target.dispatchEvent(new MouseEvent('click', {bubbles: true, clientX: box.left + 5, clientY: box.top + 5}));
      await new Promise(r => setTimeout(r, 300));
      const locked = window.RedlineMode.debugState().hasLockedSelection;
      target.remove();
      await new Promise(r => setTimeout(r, 400));
      return {
        lockedBefore: locked,
        lines: document.querySelectorAll('[data-redline-svg] line').length,
        labels: document.querySelectorAll('[data-redline-labels] > *').length,
        summary: window.RedlineMode.debugState().selectionSummary
      };
    })()"""
    )
    check(
        "removed element clears its overlays",
        stale.get("lockedBefore") and stale.get("lines") == 0 and stale.get("labels") == 0,
        json.dumps(stale),
    )
    check(
        "selection summary returns to the empty state",
        (stale.get("summary") or "").startswith("Nothing selected"),
        stale.get("summary"),
    )

    # =====================================================================
    # 3b. Overlays stay anchored while the workspace changes around them
    # =====================================================================
    print("\n== overlay alignment ==")
    set_breakpoint("1440")
    alignment = evaluate(
        """(async () => {
      const wait = ms => new Promise(r => setTimeout(r, ms));
      const frame = document.querySelector('.redline__preview');
      const doc = frame.contentDocument;
      const target = doc.querySelector('.page-header, main section, .surface');
      const box = target.getBoundingClientRect();
      target.dispatchEvent(new PointerEvent('pointermove', {bubbles: true, clientX: box.left + 5, clientY: box.top + 5}));
      target.dispatchEvent(new MouseEvent('click', {bubbles: true, clientX: box.left + 5, clientY: box.top + 5}));
      await wait(350);
      const measure = () => {
        const rect = target.getBoundingClientRect();
        const scale = window.RedlineMode.debugState().previewScale;
        const frameRect = frame.getBoundingClientRect();
        const expectedLeft = frameRect.left + rect.left * scale;
        const outline = document.querySelector('[data-redline-svg] rect');
        if (!outline) return {drawn: false};
        const drawn = outline.getBoundingClientRect();
        return {drawn: true, delta: Math.abs(drawn.left - expectedLeft)};
      };
      const results = {initial: measure()};
      doc.defaultView.scrollTo(0, 160);
      await wait(400);
      results.afterPreviewScroll = measure();
      document.querySelector('[data-redline-action="panel:right"]').click();
      await wait(420);
      results.afterPanelToggle = measure();
      document.querySelector('[data-redline-action="panel:right"]').click();
      await wait(420);
      results.afterPanelRestore = measure();
      doc.defaultView.scrollTo(0, 0);
      await wait(400);
      results.afterScrollBack = measure();
      return results;
    })()"""
    )
    for phase, result in alignment.items():
        check(
            f"overlay stays anchored {phase}",
            result.get("drawn") and result.get("delta", 99) < 3,
            json.dumps(result),
        )

    # =====================================================================
    # 4. Source page restoration and data integrity
    # =====================================================================
    print("\n== close and restore ==")
    storage_before = evaluate("JSON.stringify(Object.entries(localStorage).sort())")
    exit_redline()
    restored = evaluate(SOURCE_STATE)
    compare_states("close", source_list, restored)
    leftovers = evaluate(
        """({
      roots: document.querySelectorAll('.redline').length,
      chrome: document.querySelectorAll('[data-redline-ui]').length,
      htmlClass: document.documentElement.className,
      bodyStyle: document.body.getAttribute('style') || ''
    })"""
    )
    check(
        "no Redline artifacts remain",
        leftovers["roots"] == 0 and leftovers["chrome"] == 0
        and "redline" not in leftovers["htmlClass"],
        json.dumps(leftovers),
    )
    storage_after = evaluate("JSON.stringify(Object.entries(localStorage).sort())")
    check(
        "source data is not mutated by a Redline session",
        storage_before == storage_after,
        "localStorage differs after the session",
    )

    print("\n== repeated entry and exit ==")
    for cycle in range(3):
        enter_redline()
        set_breakpoint("1280")
        set_breakpoint("current")
        exit_redline()
    repeated = evaluate(
        """({
      roots: document.querySelectorAll('.redline').length,
      frames: document.querySelectorAll('.redline__preview').length,
      state: (document.querySelector('[data-action="search"]') || {}).value
    })"""
    )
    check(
        "repeated sessions leave nothing behind",
        repeated["roots"] == 0 and repeated["frames"] == 0,
        json.dumps(repeated),
    )
    check(
        "repeated sessions do not disturb the source page",
        repeated["state"] == source_list["search"],
        json.dumps(repeated),
    )

    # =====================================================================
    # 5. Non-default pagination
    # =====================================================================
    print("\n== pagination entry ==")
    navigate("?version=2.0")
    evaluate(
        """(async () => {
      const wait = ms => new Promise(r => setTimeout(r, ms));
      const next = document.querySelector('[data-action="next-page"], [data-page-next]');
      if (next) { next.click(); await wait(250); next.click(); await wait(250); return 'clicked'; }
      const select = document.querySelector('[data-action="go-to-page"]');
      if (select) {
        select.value = '3';
        select.dispatchEvent(new Event('change', {bubbles:true}));
        await wait(250);
      }
      return 'select';
    })()"""
    )
    source_page = evaluate(SOURCE_STATE)
    enter_redline()
    set_breakpoint("1280")
    compare_states("pagination", source_page, evaluate(PREVIEW_STATE))
    check(
        "non-default page carried into the preview",
        source_page["goToPage"] not in (None, "1")
        and evaluate(PREVIEW_STATE)["goToPage"] == source_page["goToPage"],
        f"source page={source_page['goToPage']}",
    )
    screenshot("pagination-1280")
    exit_redline()

    # =====================================================================
    # 6. Create / Edit wizard with unsaved values
    # =====================================================================
    print("\n== create and edit entry ==")
    navigate("?version=2.0&section=create&mode=edit&cardId=RC-DAS-WPP-VIDEO-UF-2627")
    evaluate(
        """(async () => {
      const wait = ms => new Promise(r => setTimeout(r, ms));
      const name = document.querySelector('[data-v2-form="card"] input[name="name"]');
      if (name) {
        name.value = 'Unsaved QA edit';
        name.dispatchEvent(new Event('input', {bubbles:true}));
      }
      // Opening the LINE accordion switches to the Lines tab, so the tab
      // choice is made after it to leave a genuinely non-default pairing.
      const trigger = document.querySelector('[data-v2-accordion="line"] .create-md__accordion-trigger');
      if (trigger) { trigger.click(); await wait(250); }
      const lineSearch = document.querySelector('[data-v2-search="lines"]');
      if (lineSearch) {
        lineSearch.value = 'aurora';
        lineSearch.dispatchEvent(new Event('input', {bubbles:true}));
        await wait(200);
      }
      const premiums = document.querySelector('[data-v2-tab="premiums"]');
      if (premiums) { premiums.click(); await wait(250); }
      return true;
    })()"""
    )
    source_create = evaluate(SOURCE_STATE)
    check(
        "wizard seed applied",
        source_create["route"] == "create" and source_create["activeTab"] == "premiums"
        and source_create["lineQuery"] == "aurora",
        json.dumps(source_create),
    )
    enter_redline()
    for bp_id in ["1024", "1440", "2560", "current"]:
        ready = set_breakpoint(bp_id)
        if bp_id == "current":
            continue
        check(f"wizard {bp_id} ready", ready, "preview did not reach ready")
        preview = evaluate(PREVIEW_STATE)
        compare_states(f"wizard {bp_id}", source_create, preview)
        check(
            f"wizard {bp_id} not blank",
            isinstance(preview, dict) and preview["bodyTextLength"] > 200,
            preview.get("bodyTextLength") if isinstance(preview, dict) else preview,
        )
        screenshot(f"create-{bp_id}")
    exit_redline()
    check(
        "wizard unsaved value survives the round trip",
        evaluate(SOURCE_STATE)["cardName"] == "Unsaved QA edit",
        evaluate(SOURCE_STATE)["cardName"],
    )

    # =====================================================================
    # 7. Deep-linked presentation route
    # =====================================================================
    print("\n== atlas deep link ==")
    navigate("?section=atlas&slide=4")
    source_atlas = evaluate(SOURCE_STATE)
    enter_redline()
    for bp_id in ["1024", "1920"]:
        check(f"atlas {bp_id} ready", set_breakpoint(bp_id), "preview did not reach ready")
        preview = evaluate(PREVIEW_STATE)
        compare_states(f"atlas {bp_id}", source_atlas, preview)
        check(
            f"atlas {bp_id} keeps the deep link",
            isinstance(preview, dict) and "slide=4" in (preview.get("url") or ""),
            preview.get("url") if isinstance(preview, dict) else preview,
        )
        screenshot(f"atlas-{bp_id}")
    exit_redline()

    # =====================================================================
    # 8. Preview failure states
    # =====================================================================
    print("\n== preview failure states ==")
    navigate("?version=2.0")
    expectations = [
        ("404", "Route not found"),
        ("503", "Preview server error"),
        ("empty", "Preview failed to render"),
    ]
    for mode, expected_title in expectations:
        PREVIEW_FAILURE_MODE = mode
        enter_redline()
        evaluate(
            "document.querySelector('[data-redline-action=\"breakpoint:1280\"]').click()"
        )
        reached = wait_for(
            "window.RedlineMode.debugState().previewPhase === 'error'", 12
        )
        detail = evaluate(
            """(() => {
          const overlay = document.querySelector('[data-redline-preview-status]');
          if (!overlay) return null;
          const retry = overlay.querySelector('[data-redline-action="preview:retry"]');
          return {
            phase: overlay.getAttribute('data-redline-preview-status'),
            hidden: overlay.hidden,
            title: overlay.querySelector('[data-redline-preview-title]').textContent,
            body: overlay.querySelector('[data-redline-preview-body]').textContent,
            diagnostics: overlay.querySelector('[data-redline-preview-diagnostics]').textContent,
            retryVisible: retry ? !retry.hidden : false,
            live: overlay.getAttribute('aria-live'),
            role: overlay.getAttribute('role')
          };
        })()"""
        )
        check(
            f"{mode} surfaces an error state",
            reached and detail and not detail["hidden"] and detail["title"] == expected_title,
            json.dumps(detail),
        )
        check(
            f"{mode} offers retry and diagnostics",
            bool(detail) and detail["retryVisible"] and "URL:" in detail["diagnostics"],
            json.dumps(detail),
        )
        check(
            f"{mode} error is announced",
            bool(detail) and detail["role"] == "status" and detail["live"] == "polite",
            json.dumps(detail),
        )
        overlays = evaluate(
            """(() => {
          const canvas = document.querySelector('[data-redline-canvas]').getBoundingClientRect();
          const drawn = [...document.querySelectorAll('[data-redline-svg] *')]
            .filter(node => ['line', 'rect', 'path', 'polyline'].includes(node.tagName));
          const strays = [...document.querySelectorAll('[data-redline-labels] > *')]
            .map(node => node.getBoundingClientRect())
            .filter(rect => rect.width > 0 && (rect.left < canvas.left - 1 || rect.right > canvas.right + 1));
          return {
            drawn: drawn.length,
            strays: strays.length,
            selection: window.RedlineMode.debugState().selectionSummary,
            inspector: document.querySelector('[data-redline-inspector]').textContent.slice(0, 60)
          };
        })()"""
        )
        check(
            f"{mode} leaves no stale overlays behind",
            overlays["drawn"] == 0 and overlays["strays"] == 0,
            json.dumps(overlays),
        )
        check(
            f"{mode} resets the selection summary",
            (overlays["selection"] or "").startswith("Nothing selected"),
            json.dumps(overlays),
        )
        if mode == "empty":
            screenshot("preview-error")
            PREVIEW_FAILURE_MODE = ""
            evaluate(
                "document.querySelector('[data-redline-action=\"preview:retry\"]').click()"
            )
            recovered = wait_for(
                "window.RedlineMode.debugState().previewPhase === 'ready'", 12
            )
            time.sleep(0.4)
            check("retry recovers the preview", recovered, "still not ready after retry")
            check(
                "recovered preview renders the page",
                (evaluate(PREVIEW_STATE) or {}).get("bodyTextLength", 0) > 200,
                evaluate(PREVIEW_STATE),
            )
        PREVIEW_FAILURE_MODE = ""
        exit_redline()

    # =====================================================================
    # 9. Responsive Redline shell
    # =====================================================================
    print("\n== responsive shell ==")
    navigate("?version=2.0")
    enter_redline()
    set_breakpoint("1440")
    logical_before = evaluate("window.RedlineMode.debugState().breakpoint")
    send(
        "Emulation.setDeviceMetricsOverride",
        {"width": 900, "height": 820, "deviceScaleFactor": 1, "mobile": False},
    )
    time.sleep(0.6)
    narrow = evaluate(
        """(() => {
      const stage = document.querySelector('.redline__stage').getBoundingClientRect();
      const frame = document.querySelector('.redline__preview');
      const header = document.querySelector('.redline__header').getBoundingClientRect();
      const toggles = [...document.querySelectorAll('.redline__panel-toggle')];
      return {
        stageWidth: Math.round(stage.width),
        headerVisible: header.height > 0 && header.top >= 0,
        toggleCount: toggles.filter(t => t.offsetParent !== null).length,
        logicalWidth: frame.contentWindow.innerWidth,
        breakpoint: window.RedlineMode.debugState().breakpoint
      };
    })()"""
    )
    check("narrow window keeps the canvas usable", narrow["stageWidth"] > 200, json.dumps(narrow))
    check("narrow window keeps the header visible", narrow["headerVisible"], json.dumps(narrow))
    check("narrow window exposes panel toggles", narrow["toggleCount"] >= 2, json.dumps(narrow))
    check(
        "host width does not change the product breakpoint",
        narrow["breakpoint"] == logical_before and narrow["logicalWidth"] == 1440,
        json.dumps(narrow),
    )
    drawer = evaluate(
        """(async () => {
      const wait = ms => new Promise(r => setTimeout(r, ms));
      const results = {};
      for (const side of ['left', 'right']) {
        const toggle = document.querySelector('[data-redline-action="panel:' + side + '"]');
        const panel = document.querySelector('[data-redline-panel="' + side + '"]');
        toggle.click();
        await wait(260);
        results[side + 'Open'] = toggle.getAttribute('aria-expanded') === 'true'
          && panel.getBoundingClientRect().width > 0;
        toggle.click();
        await wait(260);
        results[side + 'Closed'] = toggle.getAttribute('aria-expanded') === 'false';
      }
      results.logicalWidth = document.querySelector('.redline__preview').contentWindow.innerWidth;
      return results;
    })()"""
    )
    check(
        "collapsed panels reopen and close",
        drawer["leftOpen"] and drawer["leftClosed"] and drawer["rightOpen"] and drawer["rightClosed"],
        json.dumps(drawer),
    )
    check(
        "opening a panel does not resize the product viewport",
        drawer["logicalWidth"] == 1440,
        json.dumps(drawer),
    )
    screenshot("narrow-shell")
    send("Emulation.clearDeviceMetricsOverride")
    time.sleep(0.4)

    # =====================================================================
    # 10. Accessibility
    # =====================================================================
    print("\n== accessibility ==")
    accessibility = evaluate(
        """(() => {
      const root = document.querySelector('.redline');
      const controls = [...root.querySelectorAll('[data-redline-action]')];
      const unnamed = controls.filter(control => {
        if (control.hidden || control.offsetParent === null) return false;
        const labelled = control.labels && control.labels.length
          ? [...control.labels].map(label => label.textContent).join('')
          : '';
        const label = (control.getAttribute('aria-label') || '')
          + (control.textContent || '')
          + (control.getAttribute('title') || '')
          + labelled;
        return !label.trim();
      }).map(c => c.getAttribute('data-redline-action'));
      const breakpoints = [...root.querySelectorAll('[data-redline-action^="breakpoint:"]')];
      const checkboxes = [...root.querySelectorAll('[data-redline-action^="annotation:"]')];
      return {
        unnamed,
        breakpointsFocusable: breakpoints.every(b => b.tagName === 'BUTTON' && b.tabIndex >= 0),
        pressedCount: breakpoints.filter(b => b.getAttribute('aria-pressed') === 'true').length,
        checkboxesLabelled: checkboxes.every(box => Boolean(
          box.labels && box.labels.length
        ) || Boolean(box.getAttribute('aria-label'))),
        canvasLabelled: Boolean(root.querySelector('[data-redline-panel="right"]').getAttribute('aria-label')),
        frameTitled: Boolean(document.querySelector('.redline__preview').getAttribute('title')),
        appRole: root.getAttribute('role')
      };
    })()"""
    )
    check("every shell control has an accessible name", not accessibility["unnamed"],
          json.dumps(accessibility["unnamed"]))
    check("breakpoints are keyboard reachable", accessibility["breakpointsFocusable"], "")
    check(
        "selected breakpoint is programmatically identifiable",
        accessibility["pressedCount"] == 1,
        accessibility["pressedCount"],
    )
    check("annotation checkboxes are labelled", accessibility["checkboxesLabelled"], "")
    check("inspector and preview are labelled", accessibility["canvasLabelled"]
          and accessibility["frameTitled"], json.dumps(accessibility))

    focus_state = evaluate(
        """(async () => {
      const wait = ms => new Promise(r => setTimeout(r, ms));
      const target = document.querySelector('[data-redline-action="breakpoint:1920"]');
      target.focus();
      const before = document.activeElement === target;
      target.click();
      await wait(500);
      return {
        before,
        after: document.activeElement === target,
        outline: getComputedStyle(target, ':focus-visible').outlineStyle
      };
    })()"""
    )
    check(
        "focus is not lost when the breakpoint changes",
        focus_state["before"] and focus_state["after"],
        json.dumps(focus_state),
    )
    scaling = evaluate(
        """(async () => {
      const wait = ms => new Promise(r => setTimeout(r, ms));
      const root = document.documentElement;
      const previous = root.style.fontSize;
      root.style.fontSize = '24px';
      await wait(320);
      const controls = [...document.querySelectorAll('.redline__breakpoint, .redline__segment, .redline__stack-button')];
      const clipped = controls.filter(control => {
        const rect = control.getBoundingClientRect();
        return rect.width < 8 || rect.height < 8 || rect.right > window.innerWidth;
      }).length;
      const stage = document.querySelector('.redline__stage').getBoundingClientRect();
      root.style.fontSize = previous;
      await wait(200);
      return {clipped, controls: controls.length, stageWidth: Math.round(stage.width)};
    })()"""
    )
    check(
        "text scaling keeps every control usable",
        scaling["clipped"] == 0 and scaling["controls"] > 5 and scaling["stageWidth"] > 200,
        json.dumps(scaling),
    )

    exit_redline()
    focus_after_close = evaluate(
        """({
      active: document.activeElement ? document.activeElement.tagName : '',
      isBody: document.activeElement === document.body
    })"""
    )
    check(
        "closing returns focus to the page",
        not focus_after_close["isBody"],
        json.dumps(focus_after_close),
    )

    # =====================================================================
    # 11. Stability
    # =====================================================================
    print("\n== stability ==")
    real_errors = [
        message for message in console_messages
        if message and "favicon" not in message.lower()
    ]
    check("no console errors during the run", not real_errors, json.dumps(real_errors[:5]))
    check(
        "no stray Redline nodes at the end of the run",
        evaluate("document.querySelectorAll('.redline, [data-redline-ui]').length") == 0,
        evaluate("document.querySelectorAll('.redline, [data-redline-ui]').length"),
    )

finally:
    print("\n" + "=" * 60)
    print(f"passed: {passes}  failed: {len(failures)}")
    for failure in failures:
        print(f"  - {failure['name']}: {failure['detail']}")
    print(f"screenshots: {OUT}")
    ws.close()
    chrome.terminate()
    server.shutdown()
    raise SystemExit(1 if failures else 0)
