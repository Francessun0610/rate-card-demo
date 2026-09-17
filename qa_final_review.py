"""Pre-commit visual and interaction review of the Rate Card Manager.

Confirms, on the running app rather than from the diff:

  1. Default table state at the Figma frame width (472:17713): continuous
     page background, no Action column, no in-row action buttons.
  2. Multi-row selection: 1, 2, 5, deselect, clear, and the exact count
     sentence the action bar shows at each size.
  3. The action bar's placement and reference geometry (608:14479).
  4. The Ad Console brand lockup sitting to the right of the rail's icon
     centreline, with the logo and wordmark still one unit.
  5. Version 2.0 untouched: Action column, single-row selection, no bar.

Writes screenshots of the default state and the five-row selected state
to /tmp/rate-card-final-review.

Run with: python3 qa_final_review.py
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
OUT = "/tmp/rate-card-final-review"
shutil.rmtree(OUT, ignore_errors=True)
os.makedirs(OUT, exist_ok=True)


class Handler(BaseHTTPRequestHandler):
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
            ".html": "text/html", ".css": "text/css",
            ".js": "application/javascript", ".svg": "image/svg+xml",
            ".png": "image/png", ".json": "application/json",
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


server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()

profile = "/tmp/rate_card_final_review_profile"
shutil.rmtree(profile, ignore_errors=True)
os.makedirs(profile, exist_ok=True)
chrome = subprocess.Popen(
    [
        CHROME,
        f"--remote-debugging-port={DEBUG_PORT}",
        f"--user-data-dir={profile}",
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
passes = 0
failures = []
console_errors = []


def send(method, params=None):
    global message_id
    message_id += 1
    expected = message_id
    ws.send(json.dumps({"id": expected, "method": method, "params": params or {}}))
    while True:
        event = json.loads(ws.recv())
        if event.get("method") == "Runtime.exceptionThrown":
            detail = event.get("params", {}).get("exceptionDetails", {})
            console_errors.append(
                (detail.get("exception") or {}).get("description", detail.get("text"))
            )
        if event.get("method") == "Runtime.consoleAPICalled":
            if event.get("params", {}).get("type") == "error":
                console_errors.append("console.error")
        if event.get("id") == expected:
            return event


def E(expression):
    result = send("Runtime.evaluate", {
        "expression": expression, "returnByValue": True, "awaitPromise": True,
    })
    payload = result.get("result", {})
    if "exceptionDetails" in payload:
        raise RuntimeError(json.dumps(payload["exceptionDetails"])[:400])
    return payload.get("result", {}).get("value")


def check(name, condition, detail=""):
    global passes
    if condition:
        passes += 1
        print(f"  PASS  {name}")
    else:
        failures.append(name)
        print(f"  FAIL  {name} -- {detail}")


def wait_for(expression, timeout=12):
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
    with open(os.path.join(OUT, name + ".png"), "wb") as handle:
        handle.write(base64.b64decode(payload["result"]["data"]))


def viewport(width, height):
    send("Emulation.setDeviceMetricsOverride", {
        "width": width, "height": height, "deviceScaleFactor": 1, "mobile": False,
    })


def open_list(version, width=1440, height=960):
    viewport(width, height)
    try:
        E("window.__navToken = 1")
    except RuntimeError:
        pass
    send("Page.navigate", {
        "url": f"http://127.0.0.1:{PORT}/index.html?version={version}",
    })
    wait_for("!window.__navToken && !!document.body"
             f" && document.body.dataset.version === '{version}'")
    wait_for("document.querySelectorAll('[data-rows] .row').length > 0")
    time.sleep(0.5)


CLICK_ROW = """((i) => {
  const rows = document.querySelectorAll('[data-rows] .row');
  if (!rows[i]) return false;
  const cell = rows[i].querySelector('.cell--status') || rows[i];
  cell.dispatchEvent(new MouseEvent('click', {bubbles: true}));
  return true;
})(%d)"""

STATE = """(() => {
  const round = (n) => Math.round(n * 10) / 10;
  const rect = (el) => {
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return {x: round(r.x), y: round(r.y), w: round(r.width), h: round(r.height),
            right: round(r.right), bottom: round(r.bottom)};
  };
  const bar = document.querySelector('[data-selection-bar]');
  const count = bar ? bar.querySelector('[data-selection-count]') : null;
  const head = document.querySelector('.table__head');
  const firstRow = document.querySelector('[data-rows] .row');
  const cs = bar ? getComputedStyle(bar) : null;
  return {
    version: document.body.dataset.version,
    barExists: !!bar,
    barHidden: bar ? bar.hidden : null,
    barRect: bar && !bar.hidden ? rect(bar) : null,
    barBg: cs ? cs.backgroundColor : null,
    barBeforeHead: !!(bar && head && head.previousElementSibling === bar),
    headAfterBar: !!(bar && head && bar.nextElementSibling === head),
    headRect: rect(head),
    firstRowRect: rect(firstRow),
    countText: count ? count.textContent : null,
    actions: bar ? [...bar.querySelectorAll('.rcsel__btn')]
      .map((b) => b.getAttribute('aria-label')) : [],
    quickEditDisabled: bar
      ? !!bar.querySelector('[data-selection-action="quick-edit"]').disabled
      : null,
    selectedRows: document.querySelectorAll('[data-rows] .row.is-selected').length,
    ariaSelected: document.querySelectorAll(
      '[data-rows] .row[aria-selected="true"]').length,
    actionHeads: [...document.querySelectorAll('.th--action')]
      .filter((el) => el.getBoundingClientRect().width > 0).length,
    inRowActions: [...document.querySelectorAll('[data-rows] .row .actions')]
      .filter((el) => el.getBoundingClientRect().width > 0).length,
    pageTopBg: getComputedStyle(
      document.querySelector('[data-page="list"] > .page__top')).backgroundColor,
    pageContentBg: getComputedStyle(
      document.querySelector('[data-page="list"] > .page__content')).backgroundColor,
    docScrollW: document.documentElement.scrollWidth,
    docClientW: document.documentElement.clientWidth,
  };
})()"""


def state():
    return E(STATE)


try:
    send("Runtime.enable")
    send("Page.enable")

    # ---------------------------------------------------------------
    print("\n=== 1. DEFAULT TABLE STATE (Figma 472:17713, 1440) ===")
    open_list("2.1")
    base = state()
    shot("01-default-table")
    check("2.1 is the version under test", base["version"] == "2.1", base["version"])
    check("no action bar is shown with nothing selected",
          base["barHidden"] is True or base["barExists"] is False,
          json.dumps({"exists": base["barExists"], "hidden": base["barHidden"]}))
    check("the Action column header is gone", base["actionHeads"] == 0,
          base["actionHeads"])
    check("no in-row action buttons are built", base["inRowActions"] == 0,
          base["inRowActions"])
    check("the page background is continuous behind the title and the table",
          base["pageTopBg"] == base["pageContentBg"],
          json.dumps({"top": base["pageTopBg"], "content": base["pageContentBg"]}))
    check("the page does not scroll horizontally",
          base["docScrollW"] <= base["docClientW"] + 1,
          json.dumps({"scroll": base["docScrollW"], "client": base["docClientW"]}))

    # ---------------------------------------------------------------
    print("\n=== 2. SELECTION COUNTS ===")
    E(CLICK_ROW % 0)
    time.sleep(0.25)
    one = state()
    check('one selected row reads "1 item selected"',
          one["countText"] == "1 item selected", one["countText"])
    check("one selected row paints one row", one["selectedRows"] == 1,
          one["selectedRows"])
    check("Quick Edit is available on a single record",
          one["quickEditDisabled"] is False, one["quickEditDisabled"])

    E(CLICK_ROW % 3)
    time.sleep(0.25)
    two = state()
    check('two non-adjacent rows read "2 items selected"',
          two["countText"] == "2 items selected", two["countText"])
    check("two selected rows paint two rows", two["selectedRows"] == 2,
          two["selectedRows"])
    check("Quick Edit is disabled past one record",
          two["quickEditDisabled"] is True, two["quickEditDisabled"])

    for index in (1, 2, 4):
        E(CLICK_ROW % index)
        time.sleep(0.12)
    time.sleep(0.2)
    five = state()
    shot("02-five-selected")
    check('five selected rows read "5 items selected"',
          five["countText"] == "5 items selected", five["countText"])
    check("five selected rows paint five rows", five["selectedRows"] == 5,
          five["selectedRows"])
    check("aria-selected matches the painted selection",
          five["ariaSelected"] == five["selectedRows"],
          json.dumps({"aria": five["ariaSelected"], "painted": five["selectedRows"]}))
    check("all five production actions are present",
          five["actions"] == ["Quick Edit", "Copy", "Download",
                              "Archive", "Delete"],
          json.dumps(five["actions"]))

    E(CLICK_ROW % 4)
    time.sleep(0.25)
    four = state()
    check('deselecting one row falls back to "4 items selected"',
          four["countText"] == "4 items selected", four["countText"])

    E("""(() => {
      document.dispatchEvent(new KeyboardEvent('keydown',
        {key: 'Escape', bubbles: true}));
    })()""")
    time.sleep(0.3)
    cleared = state()
    check("clearing the selection hides the bar again",
          cleared["barHidden"] is True and cleared["selectedRows"] == 0,
          json.dumps({"hidden": cleared["barHidden"],
                      "rows": cleared["selectedRows"]}))

    # ---------------------------------------------------------------
    print("\n=== 3. ACTION BAR PLACEMENT AND GEOMETRY (104:23927) ===")
    E(CLICK_ROW % 0)
    time.sleep(0.3)
    bar = state()
    check("the bar sits directly above the column header row",
          bar["barBeforeHead"] and abs(bar["headRect"]["y"]
                                       - bar["barRect"]["bottom"]) <= 1,
          json.dumps({"headY": bar["headRect"]["y"],
                      "barBottom": bar["barRect"]["bottom"]}))
    check("the first data row still begins directly below the header row",
          bar["headAfterBar"] and abs(bar["firstRowRect"]["y"]
                                      - bar["headRect"]["bottom"]) <= 1,
          json.dumps({"rowY": bar["firstRowRect"]["y"],
                      "headBottom": bar["headRect"]["bottom"]}))
    check("the bar is the reference 44px tall",
          abs(bar["barRect"]["h"] - 44) <= 1, bar["barRect"]["h"])
    check("the bar is Indigo/300",
          bar["barBg"] == "rgb(64, 69, 194)", bar["barBg"])
    check("the bar spans the table's own width",
          abs(bar["barRect"]["w"] - bar["headRect"]["w"]) <= 1,
          json.dumps({"bar": bar["barRect"]["w"], "head": bar["headRect"]["w"]}))

    # ---------------------------------------------------------------
    print("\n=== 4. AD CONSOLE BRAND LOCKUP ===")
    brand = E("""(() => {
      const round = (n) => Math.round(n * 10) / 10;
      const rail = document.querySelector('.vnav');
      const icon = document.querySelector('.vnav__item .vnav__icon');
      /* The lockup ships both brand marks and hides the one the active
       * version does not use, so measure whichever is actually painted. */
      const mark = [...document.querySelectorAll('.gnav__brand-icon')]
        .find((el) => el.getBoundingClientRect().width > 0) || null;
      const lockup = document.querySelector('.gnav__logomark');
      const word = document.querySelector('.gnav__brand-name--v2');
      const gnav = document.querySelector('.gnav');
      const box = (el) => {
        if (!el) return null;
        const r = el.getBoundingClientRect();
        return {x: round(r.x), y: round(r.y), w: round(r.width),
                h: round(r.height), right: round(r.right),
                bottom: round(r.bottom), mid: round(r.y + r.height / 2)};
      };
      const railBox = box(rail);
      const iconBox = box(icon);
      return {
        rail: railBox,
        iconAxis: iconBox ? round(iconBox.x + iconBox.w / 2) : null,
        mark: box(mark),
        lockup: box(lockup),
        word: box(word),
        wordText: word ? word.textContent.trim() : null,
        wordVisible: word ? word.getBoundingClientRect().width > 0 : false,
        gnavMid: box(gnav) ? box(gnav).mid : null,
        lockupGap: null,
      };
    })()""")
    check('the header reads "Ad Console"',
          brand["wordText"] == "Ad Console" and brand["wordVisible"],
          json.dumps({"text": brand["wordText"], "visible": brand["wordVisible"]}))
    # 2026-08-15 header brief (see qa_header_sidebar_align.py): the brand
    # mark is centred on the rail's icon axis instead of starting after the
    # rail, so the logo and the rail icons share one vertical line.
    mark_axis = round(brand["mark"]["x"] + brand["mark"]["w"] / 2, 1)
    check("the brand mark centres on the rail's icon axis",
          abs(mark_axis - brand["iconAxis"]) <= 1,
          json.dumps({"markAxis": mark_axis, "iconAxis": brand["iconAxis"]}))
    check("the lockup starts inside the rail's width, not past it",
          0 < brand["lockup"]["x"] < brand["rail"]["right"],
          json.dumps({"lockupX": brand["lockup"]["x"],
                      "railRight": brand["rail"]["right"]}))
    check("the logo and wordmark travel together as one unit",
          brand["word"]["x"] > brand["mark"]["right"]
          and brand["word"]["x"] - brand["mark"]["right"] <= 16,
          json.dumps({"markRight": brand["mark"]["right"],
                      "wordX": brand["word"]["x"]}))
    check("the logo stays the reference 32 x 28 Disney mark",
          abs(brand["mark"]["w"] - 32) <= 1 and abs(brand["mark"]["h"] - 28) <= 1,
          json.dumps({"w": brand["mark"]["w"], "h": brand["mark"]["h"]}))
    check("the lockup stays vertically centred in the header",
          abs(brand["lockup"]["mid"] - brand["gnavMid"]) <= 1,
          json.dumps({"lockupMid": brand["lockup"]["mid"],
                      "headerMid": brand["gnavMid"]}))
    shot("03-brand-lockup")

    # ---------------------------------------------------------------
    print("\n=== 5. VERSION 2.0 REGRESSION GUARD ===")
    open_list("2.0")
    legacy = state()
    check("2.0 keeps its Action column", legacy["actionHeads"] == 1,
          legacy["actionHeads"])
    check("2.0 keeps its in-row action buttons", legacy["inRowActions"] > 0,
          legacy["inRowActions"])
    check("2.0 never builds the action bar", legacy["barExists"] is False,
          legacy["barExists"])
    E(CLICK_ROW % 0)
    time.sleep(0.2)
    E(CLICK_ROW % 2)
    time.sleep(0.25)
    legacy_two = state()
    check("2.0 selection stays single row", legacy_two["selectedRows"] == 1,
          legacy_two["selectedRows"])
    # 2.0 used to hide the rail's active bar and collapse control through
    # its own overrides. The sidebar is shared chrome, so those overrides
    # were dropped and 2.0 now gets the same rail every other app-shell
    # version has: collapsed by default, and on expand a selected Rate
    # cards row plus a collapse control. Confirm it is usable there.
    E("""(() => {
      const target = document.querySelector('[data-action="vnav-expand"]');
      if (target) target.click();
    })()""")
    time.sleep(0.4)
    rail = E("""(() => {
      const round = (n) => Math.round(n * 10) / 10;
      const close = document.querySelector('.vnav__close');
      const active = document.querySelector('.vnav__item--active');
      const bar = active ? active.querySelector('.vnav__active-bar') : null;
      const box = (el) => {
        if (!el) return null;
        const r = el.getBoundingClientRect();
        return {w: round(r.width), h: round(r.height), bottom: round(r.bottom)};
      };
      return {
        close: box(close),
        activeRoute: active ? active.getAttribute('data-route') : null,
        activeBarVisible: bar ? bar.getBoundingClientRect().height > 0 : false,
        viewportHeight: window.innerHeight,
      };
    })()""")
    check("2.0's expanded rail keeps a usable collapse control",
          rail["close"] is not None and rail["close"]["w"] > 0
          and rail["close"]["bottom"] <= rail["viewportHeight"],
          json.dumps(rail))
    check("2.0 selects Rate cards in the rail like every other version",
          rail["activeRoute"] == "pricing" and rail["activeBarVisible"],
          json.dumps({"route": rail["activeRoute"],
                      "bar": rail["activeBarVisible"]}))
    shot("04-version-2-0")

    print("\n=== 6. STABILITY ===")
    check("no uncaught errors during the run", not console_errors,
          json.dumps(console_errors[:3]))

finally:
    print("\n" + "=" * 60)
    print(f"PASS {passes}   FAIL {len(failures)}")
    for name in failures:
        print("  - " + name)
    print(f"screenshots: {OUT}")
    try:
        ws.close()
    except Exception:
        pass
    chrome.terminate()
    try:
        chrome.wait(timeout=5)
    except Exception:
        chrome.kill()
    server.shutdown()
