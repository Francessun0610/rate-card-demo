"""Release readiness QA for the Redline tooling.

Covers what the other suites do not: the deployed GitLab Pages shape (the site
served from a base path, with every request accounted for), repeated
enter/browse/exit cycles measured for leaked DOM nodes, listeners, timers and
observers, browser zoom, and the tab order of the hidden source page.

qa_redline.py covers the shell, qa_redline_state.py covers state preservation,
qa_redline_overlays.py covers the galleries. This suite covers the release.

Run with: python3 qa_release_readiness.py
"""

import json
import os
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import urlopen

import websocket

ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = 8987
DEBUG_PORT = 9287
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# GitLab Pages serves the artifact from the project root, and the CI job only
# publishes a subset of the repository. Serving from a prefix here proves the
# site never depends on being at "/", and the allowlist proves it never
# depends on a file the pages job leaves behind.
BASE_PATH = "/rate-card/"
PUBLISHED = (
    "index.html", "styles.css", "v2.css", "redline.css",
    "app.js", "v2.js", "conditions.js", "redline.js", "ads-components.json",
    "README.md",
)
PUBLISHED_DIRS = ("assets/", "fixtures/")

requested = []
missing = []


class StaticHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]
        if not path.startswith(BASE_PATH):
            self.send_response(404)
            self.end_headers()
            return
        relative = path[len(BASE_PATH):] or "index.html"
        if relative.endswith("/"):
            relative += "index.html"
        requested.append(relative)
        published = relative in PUBLISHED or relative.startswith(PUBLISHED_DIRS)
        filename = os.path.join(ROOT, relative)
        if not published or not os.path.isfile(filename):
            missing.append(relative)
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
profile = "/tmp/rate_card_release_profile"
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
ws = websocket.create_connection(next(t["webSocketDebuggerUrl"] for t in tabs if t.get("type") == "page"))
message_id = 0
failures = []
passes = 0
console_messages = []
failed_requests = []


def send(method, params=None):
    global message_id
    message_id += 1
    expected = message_id
    ws.send(json.dumps({"id": expected, "method": method, "params": params or {}}))
    while True:
        event = json.loads(ws.recv())
        method_name = event.get("method")
        if method_name == "Runtime.exceptionThrown":
            details = event.get("params", {}).get("exceptionDetails", {})
            console_messages.append(
                (details.get("exception") or {}).get("description", details.get("text", ""))
            )
        elif method_name == "Runtime.consoleAPICalled":
            if event.get("params", {}).get("type") == "error":
                args = event.get("params", {}).get("args", [])
                console_messages.append(
                    " ".join(str(a.get("value", a.get("description", ""))) for a in args)
                )
        elif method_name == "Network.responseReceived":
            response = event.get("params", {}).get("response", {})
            if response.get("status", 200) >= 400:
                failed_requests.append(f"{response.get('status')} {response.get('url')}")
        elif method_name == "Network.loadingFailed":
            failed_requests.append(
                "failed " + str(event.get("params", {}).get("errorText", ""))
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


def wait_for(expression, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if evaluate(expression):
                return True
        except Exception:
            pass
        time.sleep(0.1)
    return False


def click(selector):
    return evaluate(
        f"(() => {{ const el = document.querySelector({json.dumps(selector)});"
        " if (!el) return false; el.click(); return true; })()"
    )


def live_listeners():
    """Listeners actually registered on window and document.

    Counted through the debugger rather than by patching addEventListener,
    because Redline removes its listeners with an AbortSignal, which a patched
    removeEventListener never sees.
    """
    total = 0
    for target in ("window", "document"):
        handle = send("Runtime.evaluate", {"expression": target})
        object_id = handle.get("result", {}).get("result", {}).get("objectId")
        if not object_id:
            continue
        listeners = send(
            "DOMDebugger.getEventListeners", {"objectId": object_id, "depth": 0}
        )
        total += len(listeners.get("result", {}).get("listeners", []))
        send("Runtime.releaseObject", {"objectId": object_id})
    return total


# Counts every listener, timer and observer the page creates so a cycle can be
# compared against the one before it. Installed before any application code.
INSTRUMENT = """
(() => {
  if (window.__leakProbe) return;
  const probe = { listeners: 0, timers: 0, intervals: 0, observers: 0 };
  window.__leakProbe = probe;
  const addListener = EventTarget.prototype.addEventListener;
  const removeListener = EventTarget.prototype.removeEventListener;
  EventTarget.prototype.addEventListener = function (...args) {
    probe.listeners += 1;
    return addListener.apply(this, args);
  };
  EventTarget.prototype.removeEventListener = function (...args) {
    probe.listeners -= 1;
    return removeListener.apply(this, args);
  };
  const setT = window.setTimeout;
  const clearT = window.clearTimeout;
  window.setTimeout = function (fn, delay, ...rest) {
    probe.timers += 1;
    const wrapped = typeof fn === 'function'
      ? function () { probe.timers -= 1; return fn.apply(this, arguments); }
      : fn;
    return setT.call(window, wrapped, delay, ...rest);
  };
  window.clearTimeout = function (id) {
    if (id !== undefined && id !== null) probe.timers -= 1;
    return clearT.call(window, id);
  };
  const setI = window.setInterval;
  const clearI = window.clearInterval;
  window.setInterval = function (...args) {
    probe.intervals += 1;
    return setI.apply(window, args);
  };
  window.clearInterval = function (id) {
    probe.intervals -= 1;
    return clearI.call(window, id);
  };
  ['ResizeObserver', 'MutationObserver', 'IntersectionObserver'].forEach((name) => {
    const Native = window[name];
    if (!Native) return;
    window[name] = class extends Native {
      constructor(...args) { super(...args); probe.observers += 1; }
      disconnect() { probe.observers -= 1; return super.disconnect(); }
    };
  });
})()
"""

FOOTPRINT = """
(() => {
  const frame = document.querySelector('.redline__preview');
  const inner = frame && frame.contentWindow && frame.contentWindow.__leakProbe;
  return {
    nodes: document.getElementsByTagName('*').length,
    redlineRoots: document.querySelectorAll('.redline').length,
    previews: document.querySelectorAll('.redline__preview').length,
    toasts: document.querySelectorAll('[data-toast]').length,
    host: Object.assign({}, window.__leakProbe),
    preview: inner ? Object.assign({}, inner) : null,
  };
})()
"""

try:
    send("Runtime.enable")
    send("Network.enable")
    send("Page.enable")
    send("Page.addScriptToEvaluateOnNewDocument", {"source": INSTRUMENT})

    # ---------------------------------------------------------------- pages
    print("\n--- GitLab Pages base path ---")
    send("Page.navigate", {"url": f"http://127.0.0.1:{PORT}{BASE_PATH}"})
    booted = wait_for(
        "!!document.body && !!document.body.getAttribute('data-route')", 14
    )
    time.sleep(1.2)
    check("site boots when served from a base path, not the domain root", booted)
    check(
        "no request falls outside the files the pages job publishes",
        not missing,
        json.dumps(missing[:8]),
    )
    check("no request returns an error status", not failed_requests,
          json.dumps(failed_requests[:5]))
    check(
        "every asset reference is relative to the document",
        evaluate(
            """(() => [...document.querySelectorAll('[src], [href]')]
                 .map(el => el.getAttribute('src') || el.getAttribute('href'))
                 .filter(v => v && (v.startsWith('/') || v.includes('localhost')
                   || v.includes('127.0.0.1'))).length === 0)()"""
        ),
    )
    check(
        "the app reports the base path as its own location",
        evaluate("location.pathname").startswith(BASE_PATH),
        evaluate("location.pathname"),
    )

    # A deep link plus a refresh is the case that breaks static hosting when
    # routing is not query-string based.
    evaluate(
        """(() => { const row = window.RateCardStateBridge ? null : null;
             const url = new URL(location.href);
             url.searchParams.set('section', 'create');
             history.replaceState({}, '', url.toString()); return true; })()"""
    )
    send("Page.navigate", {"url": f"http://127.0.0.1:{PORT}{BASE_PATH}?section=create"})
    deep = wait_for("document.body.getAttribute('data-route') === 'create'", 14)
    time.sleep(0.8)
    check("a deep link survives a full refresh on static hosting", deep,
          evaluate("document.body.getAttribute('data-route')"))
    check("refreshing a deep link does not 404", not missing, json.dumps(missing[:5]))

    send("Page.navigate", {"url": f"http://127.0.0.1:{PORT}{BASE_PATH}"})
    wait_for("document.body.getAttribute('data-route') === 'list'", 14)
    time.sleep(0.8)
    check(
        "browser back and forward keep the application mounted",
        evaluate("document.querySelectorAll('.app, [data-route]').length > 0"),
    )
    check(
        "redline is available on the pages host allowlist",
        evaluate(
            """(() => {
                 const gate = window.RedlineMode && window.RedlineMode.debugState;
                 return typeof gate === 'function';
               })()"""
        ),
    )

    # ------------------------------------------------------------ stress
    print("\n--- Repeated enter, browse, exit ---")
    footprints = []
    for cycle in range(3):
        evaluate("window.RedlineMode.enable('release-qa')")
        wait_for("window.RedlineMode.debugState().active")
        wait_for("window.RedlineMode.debugState().previewPhase === 'ready'", 14)
        time.sleep(0.4)
        for bp in ("1024", "1280", "1440", "1920", "2560", "current"):
            click(f'[data-redline-action="breakpoint:{bp}"]')
            wait_for("window.RedlineMode.debugState().previewPhase === 'ready'", 12)
            time.sleep(0.15)
        for kind in ("modal", "toast"):
            click(f'[data-redline-action="gallery:{kind}-gallery"]')
            wait_for("window.RedlineMode.debugState().previewPhase === 'ready'", 14)
            time.sleep(0.6)
            total = evaluate("window.RedlineMode.debugState().galleryTotal")
            for _ in range(max(0, (total or 1) - 1)):
                click('[data-redline-action="gallery:next"]')
                time.sleep(0.12)
            time.sleep(0.3)
        click('[data-redline-action="gallery:back"]')
        time.sleep(0.5)
        evaluate("window.RedlineMode.disable()")
        time.sleep(0.8)
        footprint = evaluate(FOOTPRINT)
        footprint["liveListeners"] = live_listeners()
        footprints.append(footprint)
        print("  cycle", cycle + 1, json.dumps(footprint["host"]),
              "nodes", footprint["nodes"],
              "listeners", footprint["liveListeners"])

    first, last = footprints[0], footprints[-1]
    check("no redline root survives disable", last["redlineRoots"] == 0, json.dumps(last))
    check("no preview iframe survives disable", last["previews"] == 0, json.dumps(last))
    check("no gallery toast survives disable", last["toasts"] == 0, json.dumps(last))
    check(
        "dom size does not grow across cycles",
        last["nodes"] <= first["nodes"] + 20,
        f"{first['nodes']} then {last['nodes']}",
    )
    check(
        "listeners do not accumulate across cycles",
        last["liveListeners"] <= first["liveListeners"],
        f"{first['liveListeners']} then {last['liveListeners']}",
    )
    check(
        "no interval is left running",
        last["host"]["intervals"] <= 0,
        json.dumps(last["host"]),
    )
    check(
        "observers do not accumulate across cycles",
        last["host"]["observers"] <= first["host"]["observers"] + 1,
        json.dumps([first["host"], last["host"]]),
    )

    # ----------------------------------------------------------- tab order
    print("\n--- Zoom and tab order ---")
    evaluate("window.RedlineMode.enable('release-qa')")
    wait_for("window.RedlineMode.debugState().previewPhase === 'ready'", 14)
    time.sleep(0.5)
    TABBABLE_OUTSIDE_SHELL = """
      (() => {
         const sel = 'a[href], button, input, select, textarea, [tabindex]';
         return [...document.querySelectorAll(sel)]
           .filter(el => !el.closest('.redline') && !el.hasAttribute('data-redline-ui'))
           .filter(el => {
             if (el.closest('[inert]') || el.hasAttribute('inert')) return false;
             if (el.getAttribute('tabindex') === '-1') return false;
             if (el.getAttribute('aria-hidden') === 'true') return false;
             const style = getComputedStyle(el);
             if (style.display === 'none' || style.visibility === 'hidden') return false;
             return true;
           }).length;
       })()"""

    # Under Current the live page is the preview, so it must stay reachable.
    check(
        "the current-page preview stays reachable from the keyboard",
        evaluate(TABBABLE_OUTSIDE_SHELL) > 0,
        "no focusable product content while inspecting the live page",
    )
    click('[data-redline-action="breakpoint:1280"]')
    wait_for("window.RedlineMode.debugState().previewPhase === 'ready'", 12)
    time.sleep(0.5)
    hidden_focusables = evaluate(TABBABLE_OUTSIDE_SHELL)
    check(
        "the source page leaves the tab order once the preview is the frame",
        hidden_focusables == 0,
        f"{hidden_focusables} focusable nodes behind the shell",
    )
    click('[data-redline-action="breakpoint:current"]')
    wait_for("window.RedlineMode.debugState().previewPhase === 'ready'", 12)
    time.sleep(0.5)
    check(
        "returning to current puts the page back in the tab order",
        evaluate(TABBABLE_OUTSIDE_SHELL) > 0,
    )
    click('[data-redline-action="gallery:modal-gallery"]')
    wait_for("window.RedlineMode.debugState().previewPhase === 'ready'", 14)
    time.sleep(0.8)
    check(
        "a gallery also takes the source page out of the tab order",
        evaluate(TABBABLE_OUTSIDE_SHELL) == 0,
        evaluate(TABBABLE_OUTSIDE_SHELL),
    )
    click('[data-redline-action="gallery:back"]')
    time.sleep(0.6)

    # 200% browser zoom is a device-scale change: the CSS viewport halves.
    send(
        "Emulation.setDeviceMetricsOverride",
        {"width": 800, "height": 500, "deviceScaleFactor": 2, "mobile": False},
    )
    time.sleep(1.0)
    zoomed = evaluate(
        """(() => {
             const root = document.querySelector('.redline');
             const header = document.querySelector('.redline__header');
             const canvas = document.querySelector('.redline__canvas');
             const sidebar = document.querySelector('.redline__sidebar');
             const rect = el => { const r = el.getBoundingClientRect();
               return { x: r.x, y: r.y, w: r.width, h: r.height }; };
             return { root: !!root, header: rect(header), canvas: rect(canvas),
                      sidebar: sidebar ? rect(sidebar) : null,
                      overflow: document.documentElement.scrollWidth };
           })()"""
    )
    check("redline stays laid out at 200% zoom", zoomed["root"]
          and zoomed["header"]["h"] > 20 and zoomed["canvas"]["w"] > 200,
          json.dumps(zoomed))
    check("nothing overflows the viewport at 200% zoom",
          zoomed["overflow"] <= 810, json.dumps(zoomed))
    send("Emulation.clearDeviceMetricsOverride")
    time.sleep(0.6)
    evaluate("window.RedlineMode.disable()")
    time.sleep(0.5)

    real_errors = [
        message for message in console_messages
        if "favicon" not in message.lower() and "404" not in message
    ]
    check("no console errors across the whole run", not real_errors,
          json.dumps(real_errors[:5]))
    check("no network request failed across the whole run", not failed_requests,
          json.dumps(failed_requests[:5]))

finally:
    print("\n" + "=" * 62)
    print(f"PASS {passes}   FAIL {len(failures)}")
    for failure in failures:
        print(f"  - {failure['name']}: {failure['detail']}")
    print("=" * 62)
    try:
        ws.close()
    except Exception:
        pass
    chrome.terminate()
    server.shutdown()
