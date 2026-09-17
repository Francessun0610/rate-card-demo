"""Contextual Action Bar QA: production placement, Figma fidelity,
selection counts, responsive behavior, and the Redline Mode specimen.

Reference: Figma 608:12966 (selected row state), whose bar is 608:14479.

Covers
  1. Production placement between the column header row and the first
     data row, and the reference geometry at the Figma frame width.
  2. Selection counts 0 / 1 / 2 / 5 / deselect / clear, and the single
     record rule that gates Quick Edit.
  3. Responsive behavior at 320, 375, 768, 1024, 1280, 1440 and at 200%
     zoom: every action reachable, nothing clipped, no page overflow.
  4. Redline Mode's Table components section: the Action Bar entry, the
     staged specimen, its state list, and the guarantee that pressing an
     action inside the specimen cannot touch a real rate card.

Run with: python3 qa_action_bar.py
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
PORT = 8994
DEBUG_PORT = 9294
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
OUT = "/tmp/rate-card-action-bar-qa"
shutil.rmtree(OUT, ignore_errors=True)
os.makedirs(OUT, exist_ok=True)

# Figma 608:14479. Every value read from the node, not from a screenshot.
FIGMA = {
    "height": 44,
    "bg": "rgb(64, 69, 194)",
    "divider": "rgba(15, 18, 20, 0.1)",
    "pad_x": 16,
    "count_inset": 28,          # 16 bar padding + 12 table cell padding
    "count_font": "14px",
    "count_line": "20px",
    "count_weight": "600",
    "count_color": "rgb(255, 255, 255)",
    "btn_height": 36,
    "btn_gap": 4,
    "btn_radius": "6px",
    "btn_pad_x": 12,
    "btn_pad_y": 8,
    "icon": 16,
    "icon_gap": 4,
    "labels": ["Quick Edit", "Copy", "Download", "Archive", "Delete"],
}

BREAKPOINTS = [320, 375, 768, 1024, 1280, 1440]


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

profile = "/tmp/rate_card_action_bar_profile"
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
failures = []
passes = 0


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


def shot(name, ctx=""):
    payload = send("Page.captureScreenshot", {"format": "png"})
    data = payload.get("result", {}).get("data", "")
    with open(os.path.join(OUT, name + ".png"), "wb") as handle:
        handle.write(base64.b64decode(data))


def viewport(width, height=900, scale=1):
    send(
        "Emulation.setDeviceMetricsOverride",
        {
            "width": width,
            "height": height,
            "deviceScaleFactor": scale,
            "mobile": False,
        },
    )


def open_list(version="2.1", width=1440, height=900):
    viewport(width, height)
    send("Page.navigate", {"url": f"http://127.0.0.1:{PORT}/index.html?version={version}"})
    wait_for("document.body.dataset.version === '" + version + "'")
    wait_for("document.querySelectorAll('[data-rows] .row').length > 0")
    time.sleep(0.4)


# Row clicks land on the Status cell: it is the first column, so it is on
# screen at every width whether or not the table is scrolled.
CLICK_ROW = """((i) => {
  const rows = document.querySelectorAll('[data-rows] .row');
  if (!rows[i]) return false;
  const cell = rows[i].querySelector('.cell--status') || rows[i];
  cell.dispatchEvent(new MouseEvent('click', {bubbles: true}));
  return true;
})(%d)"""

# One read of everything the bar and its neighbours are doing.
GEOM = """(() => {
  const round = (n) => Math.round(n * 10) / 10;
  const rect = (el) => {
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return {x: round(r.x), y: round(r.y), w: round(r.width), h: round(r.height),
            right: round(r.right), bottom: round(r.bottom)};
  };
  const style = (el, props) => {
    if (!el) return null;
    const cs = getComputedStyle(el);
    const out = {};
    props.forEach((p) => { out[p] = cs[p]; });
    return out;
  };
  const bar = document.querySelector('[data-selection-bar]');
  const head = document.querySelector('.table__head');
  const firstRow = document.querySelector('[data-rows] .row');
  const scroll = document.querySelector('.table-scroll');
  const group = bar ? bar.querySelector('.rcsel__actions') : null;
  const count = bar ? bar.querySelector('[data-selection-count]') : null;
  const btns = bar ? Array.prototype.slice.call(bar.querySelectorAll('.rcsel__btn')) : [];
  const groupRect = group ? group.getBoundingClientRect() : null;
  return {
    vw: window.innerWidth,
    docScrollW: document.documentElement.scrollWidth,
    docClientW: document.documentElement.clientWidth,
    bodyScrollW: document.body.scrollWidth,
    exists: !!bar,
    hidden: bar ? bar.hidden : null,
    bar: bar && !bar.hidden ? rect(bar) : null,
    barStyle: bar ? style(bar, ['backgroundColor', 'borderBottomWidth',
      'borderBottomColor', 'paddingLeft', 'paddingRight', 'position',
      'fontFamily']) : null,
    role: bar ? bar.getAttribute('role') : null,
    ariaLabel: bar ? bar.getAttribute('aria-label') : null,
    head: rect(head),
    firstRow: rect(firstRow),
    scrollport: scroll ? scroll.clientWidth : null,
    scrollW: scroll ? scroll.scrollWidth : null,
    scrollLeft: scroll ? scroll.scrollLeft : null,
    barBeforeHead: !!(bar && head && head.previousElementSibling === bar),
    headAfterBar: !!(bar && head && bar.nextElementSibling === head),
    countText: count ? count.textContent : null,
    countRect: count ? rect(count) : null,
    countStyle: count ? style(count, ['fontSize', 'lineHeight', 'fontWeight',
      'color', 'paddingLeft', 'whiteSpace']) : null,
    countLive: count ? count.getAttribute('aria-live') : null,
    group: groupRect ? rect(group) : null,
    groupTab: group ? group.getAttribute('tabindex') : null,
    groupRole: group ? group.getAttribute('role') : null,
    groupLabel: group ? group.getAttribute('aria-label') : null,
    groupScrolls: group ? group.scrollWidth - group.clientWidth > 1 : null,
    groupScrollW: group ? group.scrollWidth : null,
    groupClientW: group ? group.clientWidth : null,
    groupClass: group ? group.className : null,
    btns: btns.map((b) => {
      const r = b.getBoundingClientRect();
      const svg = b.querySelector('svg');
      const label = b.querySelector('.rcsel__btn-label');
      const cs = getComputedStyle(b);
      const lr = label ? label.getBoundingClientRect() : null;
      const ir = svg ? svg.getBoundingClientRect() : null;
      return {
        key: b.getAttribute('data-selection-action'),
        name: b.getAttribute('aria-label'),
        text: label ? label.textContent : '',
        labelVisible: !!(lr && lr.width > 2),
        title: b.getAttribute('title'),
        disabled: b.disabled,
        ariaDisabled: b.getAttribute('aria-disabled'),
        x: round(r.x), right: round(r.right), w: round(r.width), h: round(r.height),
        radius: cs.borderRadius,
        padX: cs.paddingLeft, padY: cs.paddingTop,
        gap: cs.gap,
        icon: ir ? round(ir.width) : null,
        iconMid: ir ? round(ir.y + ir.height / 2) : null,
        labelMid: lr && lr.width > 2 ? round(lr.y + lr.height / 2) : null,
        inGroup: !!(groupRect && r.x >= groupRect.x - 1.5
          && r.right <= groupRect.right + 1.5),
        reachable: !!(groupRect && r.width > 0),
        tabbable: b.tabIndex >= 0,
      };
    }),
    selectedRows: document.querySelectorAll('[data-rows] .row.is-selected').length,
    rowCount: document.querySelectorAll('[data-rows] .row').length,
  };
})()"""


def geom():
    return E(GEOM)


try:
    send("Runtime.enable")
    send("Page.enable")
    # A headless page is not focused, and an unfocused document fires no
    # focus events at all, so focus behavior would look broken here even
    # when it is not.
    send("Emulation.setFocusEmulationEnabled", {"enabled": True})

    # ==================================================================
    #  1. Production placement and Figma geometry at the frame width
    # ==================================================================
    print("\n--- 1. Production placement and Figma geometry (1440) ---")
    open_list()
    g = geom()
    check("no bar with nothing selected", g["exists"] is False or g["hidden"] is True,
          json.dumps({"exists": g["exists"], "hidden": g["hidden"]}))

    E(CLICK_ROW % 0)
    time.sleep(0.3)
    g = geom()
    check("selecting a row shows the bar", g["hidden"] is False, json.dumps(g["bar"]))
    check("bar sits directly above the column header row", g["barBeforeHead"],
          "head.previousElementSibling is not the bar")
    check("the column header row begins directly below the bar", g["headAfterBar"],
          "bar.nextElementSibling is not the header row")
    check("no gap between the bar and the header row",
          abs(g["head"]["y"] - g["bar"]["bottom"]) < 0.6,
          f"{g['head']['y']} vs {g['bar']['bottom']}")
    check("the first data row still sits against the header row",
          abs(g["firstRow"]["y"] - g["head"]["bottom"]) < 0.6,
          f"{g['firstRow']['y']} vs {g['head']['bottom']}")
    check("bar height matches Figma (44 plus its 1px divider)",
          abs(g["bar"]["h"] - (FIGMA["height"] + 1)) < 1.1, g["bar"]["h"])
    # The bar starts where the header row starts and spans what the table
    # is actually showing. Where every column fits that is the header row's
    # own width; where they do not it is the scrollport, because a bar as
    # wide as the columns would carry its actions off screen.
    check("bar starts at the header row and spans the visible table",
          abs(g["bar"]["x"] - g["head"]["x"]) < 1
          and abs(g["bar"]["w"] - g["scrollport"]) < 1.5
          and g["bar"]["w"] <= g["head"]["w"] + 1,
          f"bar {g['bar']} head {g['head']} port {g['scrollport']}")
    check("bar ground is Indigo/800",
          g["barStyle"]["backgroundColor"] == FIGMA["bg"],
          g["barStyle"]["backgroundColor"])
    check("bar divider is the table divider token",
          g["barStyle"]["borderBottomWidth"] == "1px"
          and g["barStyle"]["borderBottomColor"] == FIGMA["divider"],
          json.dumps(g["barStyle"]))
    check("bar padding is 16px each side",
          g["barStyle"]["paddingLeft"] == "16px"
          and g["barStyle"]["paddingRight"] == "16px",
          json.dumps(g["barStyle"]))
    check("bar is a labelled region",
          g["role"] == "region" and bool(g["ariaLabel"]),
          f"{g['role']} / {g['ariaLabel']}")

    count_x = g["countRect"]["x"] - g["bar"]["x"] + float(
        g["countStyle"]["paddingLeft"].replace("px", ""))
    check("count text starts at the reference 28px inset",
          abs(count_x - FIGMA["count_inset"]) < 1.5, count_x)
    check("count is 14/20 semibold white",
          g["countStyle"]["fontSize"] == FIGMA["count_font"]
          and g["countStyle"]["lineHeight"] == FIGMA["count_line"]
          and g["countStyle"]["fontWeight"] == FIGMA["count_weight"]
          and g["countStyle"]["color"] == FIGMA["count_color"],
          json.dumps(g["countStyle"]))
    check("count is announced as it changes", g["countLive"] == "polite", g["countLive"])

    labels = [b["name"] for b in g["btns"]]
    check("five actions in the reference order", labels == FIGMA["labels"],
          json.dumps(labels))
    check("every action is 36px tall",
          all(abs(b["h"] - FIGMA["btn_height"]) < 0.6 for b in g["btns"]),
          json.dumps([b["h"] for b in g["btns"]]))
    check("every action has a 16px icon",
          all(b["icon"] is not None and abs(b["icon"] - FIGMA["icon"]) < 0.6
              for b in g["btns"]),
          json.dumps([b["icon"] for b in g["btns"]]))
    check("actions use the 6px ghost radius and 12/8 padding",
          all(b["radius"] == FIGMA["btn_radius"]
              and b["padX"] == f"{FIGMA['btn_pad_x']}px"
              and b["padY"] == f"{FIGMA['btn_pad_y']}px" for b in g["btns"]),
          json.dumps([[b["radius"], b["padX"], b["padY"]] for b in g["btns"]]))
    check("icon to label gap is 4px",
          all(b["gap"] == f"{FIGMA['icon_gap']}px" for b in g["btns"]),
          json.dumps([b["gap"] for b in g["btns"]]))
    gaps = [round(g["btns"][i + 1]["x"] - g["btns"][i]["right"], 1)
            for i in range(len(g["btns"]) - 1)]
    check("actions are 4px apart",
          all(abs(v - FIGMA["btn_gap"]) < 0.6 for v in gaps), json.dumps(gaps))
    right_inset = g["bar"]["right"] - g["btns"][-1]["right"]
    check("the action group ends 16px from the bar's right edge",
          abs(right_inset - FIGMA["pad_x"]) < 1.5, right_inset)
    check("icons and labels are vertically centred on each other",
          all(b["labelMid"] is not None and abs(b["iconMid"] - b["labelMid"]) < 1.1
              for b in g["btns"]),
          json.dumps([[b["iconMid"], b["labelMid"]] for b in g["btns"]]))
    shot("01-production-1-selected")

    # ==================================================================
    #  2. Selection counts and the single record rule
    # ==================================================================
    print("\n--- 2. Selection counts ---")
    check("one row reads '1 item selected'", g["countText"] == "1 item selected",
          g["countText"])
    quick = next(b for b in g["btns"] if b["key"] == "quick-edit")
    check("Quick Edit is available for a single record",
          quick["disabled"] is False and quick["ariaDisabled"] == "false",
          json.dumps(quick))

    E(CLICK_ROW % 2)
    time.sleep(0.25)
    g = geom()
    check("two rows read '2 items selected'", g["countText"] == "2 items selected",
          g["countText"])
    quick = next(b for b in g["btns"] if b["key"] == "quick-edit")
    check("Quick Edit is disabled beyond a single record",
          quick["disabled"] is True and quick["ariaDisabled"] == "true"
          and "one rate card at a time" in (quick["title"] or ""),
          json.dumps(quick))
    check("the other four actions stay available",
          all(b["disabled"] is False for b in g["btns"] if b["key"] != "quick-edit"),
          json.dumps([[b["key"], b["disabled"]] for b in g["btns"]]))

    for index in (4, 5, 6):
        E(CLICK_ROW % index)
    time.sleep(0.25)
    g = geom()
    check("five rows read '5 items selected'", g["countText"] == "5 items selected",
          g["countText"])
    check("five rows are painted as selected", g["selectedRows"] == 5, g["selectedRows"])
    shot("02-production-5-selected")

    E(CLICK_ROW % 6)
    time.sleep(0.25)
    g = geom()
    check("deselecting one row drops the count to four",
          g["countText"] == "4 items selected" and g["selectedRows"] == 4,
          f"{g['countText']} / {g['selectedRows']}")

    for index in (0, 2, 4, 5):
        E(CLICK_ROW % index)
    time.sleep(0.25)
    g = geom()
    check("deselecting every row hides the bar",
          g["hidden"] is True and g["selectedRows"] == 0,
          f"hidden={g['hidden']} selected={g['selectedRows']}")

    # A hidden bar must not leave a band behind it. The bar now sits above
    # the header, so the header is what has to travel back up to the
    # toolbar; the rows never moved.
    check("hiding the bar leaves no band above the header row",
          abs(g["firstRow"]["y"] - g["head"]["bottom"]) < 0.6,
          f"{g['firstRow']['y']} vs {g['head']['bottom']}")

    # ==================================================================
    #  3. Responsive behavior
    # ==================================================================
    print("\n--- 3. Responsive behavior ---")
    for width in BREAKPOINTS:
        open_list(width=width)
        E(CLICK_ROW % 0)
        time.sleep(0.35)
        g = geom()
        tag = f"{width}px"
        check(f"{tag}: the bar is on screen", g["hidden"] is False, json.dumps(g["bar"]))
        check(f"{tag}: the bar spans the visible table exactly",
              abs(g["bar"]["w"] - g["scrollport"]) < 1.5,
              f"bar {g['bar']['w']} vs scrollport {g['scrollport']}")
        check(f"{tag}: the page gains no horizontal scrollbar",
              g["docScrollW"] <= g["docClientW"] + 1,
              f"{g['docScrollW']} vs {g['docClientW']}")
        check(f"{tag}: the count is readable and unwrapped",
              g["countRect"]["w"] > 60 and g["countStyle"]["whiteSpace"] == "nowrap"
              and g["countRect"]["x"] >= g["bar"]["x"] - 0.5
              and g["countRect"]["right"] <= g["bar"]["right"] + 0.5,
              json.dumps(g["countRect"]))
        check(f"{tag}: all five actions are present and reachable",
              len(g["btns"]) == 5
              and all(b["w"] > 0 and b["tabbable"] for b in g["btns"]),
              json.dumps([[b["key"], b["w"], b["tabbable"]] for b in g["btns"]]))
        check(f"{tag}: every action has an accessible name",
              [b["name"] for b in g["btns"]] == FIGMA["labels"],
              json.dumps([b["name"] for b in g["btns"]]))
        check(f"{tag}: the action group stays inside the bar",
              g["group"]["x"] >= g["bar"]["x"] - 4.5
              and g["group"]["right"] <= g["bar"]["right"] + 4.5,
              f"group {g['group']} bar {g['bar']}")
        check(f"{tag}: icons stay vertically centred with their labels",
              all(b["labelMid"] is None or abs(b["iconMid"] - b["labelMid"]) < 1.1
                  for b in g["btns"]),
              json.dumps([[b["iconMid"], b["labelMid"]] for b in g["btns"]]))
        check(f"{tag}: actions never overlap each other",
              all(g["btns"][i + 1]["x"] >= g["btns"][i]["right"] - 0.5
                  for i in range(4)),
              json.dumps([[b["x"], b["right"]] for b in g["btns"]]))

        if g["groupScrolls"]:
            check(f"{tag}: a scrolling action strip takes a tab stop",
                  g["groupTab"] == "0" and "is-scrollable" in (g["groupClass"] or ""),
                  f"tabindex={g['groupTab']} class={g['groupClass']}")
            # Scrolled to the end, the last action has to be fully in view.
            E("""(() => {
              const g = document.querySelector('.rcsel__actions');
              g.scrollLeft = g.scrollWidth;
              return true;
            })()""")
            time.sleep(0.25)
            after = geom()
            check(f"{tag}: scrolling the strip brings the last action into view",
                  after["btns"][-1]["inGroup"],
                  json.dumps(after["btns"][-1]))
            check(f"{tag}: the count does not scroll away with the actions",
                  abs(after["countRect"]["x"] - g["countRect"]["x"]) < 1,
                  f"{after['countRect']['x']} vs {g['countRect']['x']}")
        else:
            check(f"{tag}: every action fits, so the strip takes no tab stop",
                  g["groupTab"] is None
                  and all(b["inGroup"] for b in g["btns"]),
                  f"tabindex={g['groupTab']} "
                  + json.dumps([b["inGroup"] for b in g["btns"]]))

        if width < 768:
            check(f"{tag}: compact actions keep a 44px touch target",
                  all(b["w"] >= 43.5 and b["h"] >= 43.5 for b in g["btns"]),
                  json.dumps([[b["w"], b["h"]] for b in g["btns"]]))
            check(f"{tag}: compact actions hide the label but keep the name",
                  all(b["labelVisible"] is False and b["title"] for b in g["btns"]),
                  json.dumps([[b["labelVisible"], b["title"]] for b in g["btns"]]))
        if width >= 1024:
            check(f"{tag}: the reference one line layout is intact",
                  abs(g["bar"]["h"] - (FIGMA["height"] + 1)) < 1.1
                  and all(b["labelVisible"] for b in g["btns"]),
                  f"h={g['bar']['h']}")

        # The header row and the data rows still line up with each other
        # once the bar is between them.
        check(f"{tag}: the header row and first data row stay aligned",
              abs(g["head"]["x"] - g["firstRow"]["x"]) < 0.6
              and abs(g["head"]["w"] - g["firstRow"]["w"]) < 0.6,
              f"head {g['head']} row {g['firstRow']}")
        shot(f"03-responsive-{width}")

    # 200% zoom at the narrowest supported width is the hardest case: it
    # halves the space the bar has to work with.
    print("\n--- 3b. 200% zoom ---")
    open_list(width=1280)
    send("Emulation.setPageScaleFactor", {"pageScaleFactor": 1})
    viewport(640, 450)          # 1280 CSS px at 200% text and layout zoom
    E(CLICK_ROW % 0)
    time.sleep(0.4)
    g = geom()
    check("200% zoom: the bar still shows all five actions",
          g["hidden"] is False and len(g["btns"]) == 5
          and all(b["w"] > 0 and b["tabbable"] for b in g["btns"]),
          json.dumps([[b["key"], b["w"]] for b in g["btns"]]))
    check("200% zoom: the page gains no horizontal scrollbar",
          g["docScrollW"] <= g["docClientW"] + 1,
          f"{g['docScrollW']} vs {g['docClientW']}")
    check("200% zoom: the count stays readable",
          g["countRect"]["w"] > 60 and g["countRect"]["right"] <= g["bar"]["right"] + 0.5,
          json.dumps(g["countRect"]))
    shot("04-zoom-200")

    # Focus rings must not be clipped by the strip's own scrollport.
    print("\n--- 3c. Focus ---")
    open_list(width=375)
    E(CLICK_ROW % 0)
    time.sleep(0.35)
    focus = []
    for index in range(5):
        # Focus scrolls the strip, and the scroll is animated, so the ring
        # is measured once the strip has come to rest.
        E("document.querySelectorAll('.rcsel__btn')[%d].focus()" % index)
        time.sleep(0.45)
        focus.append(E("""((i) => {
          const b = document.querySelectorAll('.rcsel__btn')[i];
          const group = document.querySelector('.rcsel__actions');
          const r = b.getBoundingClientRect();
          const gr = group.getBoundingClientRect();
          return {
            key: b.getAttribute('data-selection-action'),
            focused: document.activeElement === b,
            // The strip scrolls the focused action into view, so the
            // ring needs room inside the scrollport on both sides. The
            // strip's own 4px padding is what provides it.
            roomLeft: Math.round(r.x - gr.x),
            roomRight: Math.round(gr.right - r.right),
          };
        })(%d)""" % index))
    check("every action can take keyboard focus",
          all(item["focused"] for item in focus), json.dumps(focus))
    check("focusing an action scrolls its ring fully inside the strip",
          all(item["roomLeft"] >= 3 and item["roomRight"] >= 3 for item in focus),
          json.dumps(focus))
    ring = E("""(() => {
      // :focus-visible does not match a scripted focus, so the ring is
      // read off the rule itself rather than off a synthetic state.
      const sheet = [...document.styleSheets].find((s) =>
        (s.href || '').includes('styles.css'));
      const rules = [...sheet.cssRules].filter((r) =>
        r.selectorText && r.selectorText.includes('.rcsel__btn:focus-visible'));
      return rules.map((r) => ({
        outline: r.style.outline || r.style.outlineWidth,
        offset: r.style.outlineOffset,
      }));
    })()""")
    check("the action focus ring is defined and offset from the button",
          len(ring) == 1 and bool(ring[0]["outline"]) and ring[0]["offset"] == "2px",
          json.dumps(ring))

    # ==================================================================
    #  4. Redline Mode: Table components section
    # ==================================================================
    print("\n--- 4. Redline Mode Action Bar section ---")
    open_list(width=1440, height=960)
    E("""(() => {
      document.querySelector('[data-action="toggle-profile"]').click();
      document.querySelector('[data-action="toggle-redline"]').click();
    })()""")
    check("Redline Mode activates", wait_for("window.RedlineMode.isActive()"))

    panel = E("""(() => {
      const sections = [...document.querySelectorAll('[data-redline-section]')]
        .map((s) => s.dataset.redlineSection);
      const labels = [...document.querySelectorAll('.redline__section-label')]
        .map((l) => l.textContent);
      const entry = document.querySelector(
        '[data-redline-action="gallery:action-bar"]');
      const componentsSection = entry ? entry.closest('[data-redline-section]') : null;
      const cs = entry ? getComputedStyle(entry) : null;
      const overlayEntry = document.querySelector(
        '[data-redline-action="gallery:modal-gallery"]');
      return {
        sections, labels,
        hasEntry: !!entry,
        entryText: entry ? entry.textContent.replace(/\\u203a/g, '').trim() : null,
        entryLabel: entry ? entry.getAttribute('aria-label') : null,
        entryPressed: entry ? entry.getAttribute('aria-pressed') : null,
        entrySection: componentsSection ? componentsSection.dataset.redlineSection : null,
        sameClassAsOverlayEntry: !!(entry && overlayEntry
          && entry.className === overlayEntry.className),
        focusable: entry ? entry.tabIndex >= 0 : false,
        breakpoints: [...document.querySelectorAll('.redline__breakpoint-name')]
          .map((b) => b.textContent),
        statesHidden: document.querySelector('[data-redline-states]')?.hidden,
      };
    })()""")
    check("Redline lists an Action Bar entry", panel["hasEntry"] and
          panel["entryText"] == "Action Bar", json.dumps(panel["entryText"]))
    check("the entry sits in its own table components section, not under Overlays",
          panel["entrySection"] == "components"
          and "Table components" in panel["labels"],
          f"{panel['entrySection']} / {json.dumps(panel['labels'])}")
    check("the entry follows the existing section chrome",
          panel["sameClassAsOverlayEntry"] and panel["focusable"]
          and panel["entryPressed"] == "false",
          json.dumps(panel))
    check("state controls stay hidden until the section is open",
          panel["statesHidden"] is True, panel["statesHidden"])
    check("the breakpoint list covers 320 through 1280",
          all(str(w) in panel["breakpoints"] for w in BREAKPOINTS)
          and panel["breakpoints"][0] == "Current",
          json.dumps(panel["breakpoints"]))

    E("""document.querySelector('[data-redline-action="gallery:action-bar"]').click()""")
    check("selecting Action Bar stages a preview",
          wait_for("""(() => {
            const f = document.querySelector('.redline__preview');
            if (!f || f.hidden) return false;
            const d = f.contentDocument;
            return !!(d && d.body && d.body.getAttribute('data-specimen') === 'action-bar');
          })()""", timeout=15))

    time.sleep(1.2)
    spec = E("""(() => {
      const doc = document.querySelector('.redline__preview').contentDocument;
      const win = document.querySelector('.redline__preview').contentWindow;
      const bar = doc.querySelector('[data-selection-bar]');
      const rect = (el) => {
        if (!el) return null;
        const r = el.getBoundingClientRect();
        return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width),
                h: Math.round(r.height)};
      };
      const visible = (sel) => {
        const el = doc.querySelector(sel);
        return !!(el && el.getBoundingClientRect().height > 2);
      };
      return {
        specimen: doc.body.getAttribute('data-specimen'),
        version: doc.body.getAttribute('data-version'),
        route: doc.body.getAttribute('data-route'),
        barVisible: !!(bar && !bar.hidden),
        barRect: rect(bar),
        headVisible: visible('.table__head'),
        rowsVisible: doc.querySelectorAll('[data-rows] .row').length,
        rowsPainted: [...doc.querySelectorAll('[data-rows] .row')]
          .filter((r) => r.getBoundingClientRect().height > 2).length,
        pageTopVisible: visible(
          '[data-page="list"] .surface__inner > .page__header'),
        toolbarVisible: visible('[data-page="list"] .toolbar'),
        footerVisible: visible('[data-page="list"] .footer'),
        count: bar ? bar.querySelector('[data-selection-count]').textContent : null,
        actions: bar ? [...bar.querySelectorAll('.rcsel__btn')]
          .map((b) => b.getAttribute('aria-label')) : [],
        // The specimen is the production element, not a copy of it.
        sharedFactory: !!(win.RateCardComponentGallery
          && win.RateCardComponentGallery.version === 1),
        barIsInTable: !!(bar && bar.nextElementSibling
          && bar.nextElementSibling.classList.contains('table__head')),
        states: [...document.querySelectorAll('.redline__state-button')]
          .map((b) => b.textContent),
        statePressed: [...document.querySelectorAll('.redline__state-button')]
          .map((b) => b.getAttribute('aria-pressed')),
        hint: document.querySelector('[data-redline-component-hint]')?.textContent,
        galleryLabel: document.querySelector('[data-redline-gallery-label]')?.textContent,
      };
    })()""")
    check("the specimen stages the real bar inside the real table",
          spec["barVisible"] and spec["barIsInTable"] and spec["headVisible"],
          json.dumps(spec))
    check("the specimen quiets the page around the table",
          spec["pageTopVisible"] is False and spec["toolbarVisible"] is False
          and spec["footerVisible"] is False,
          json.dumps({"top": spec["pageTopVisible"], "toolbar": spec["toolbarVisible"],
                      "footer": spec["footerVisible"]}))
    check("the specimen keeps the data row region for context",
          spec["rowsPainted"] >= 2, spec["rowsPainted"])
    check("the specimen shows all five production actions",
          spec["actions"] == FIGMA["labels"], json.dumps(spec["actions"]))
    check("the specimen opens on the singular count",
          spec["count"] == "1 item selected", spec["count"])
    check("the state list offers 1, 2, 5, a page, and a long count",
          spec["states"] == ["1 item selected", "2 items selected",
                             "5 items selected", "10 items selected",
                             "1,250 items selected"],
          json.dumps(spec["states"]))
    check("the first state reads as selected",
          spec["statePressed"][0] == "true"
          and spec["statePressed"].count("true") == 1,
          json.dumps(spec["statePressed"]))
    check("the section says the specimen is preview only",
          bool(spec["hint"]), spec["hint"])
    shot("05-redline-action-bar")

    # State switching drives the real component.
    def specimen_read():
        return E("""(() => {
          const doc = document.querySelector('.redline__preview').contentDocument;
          const bar = doc.querySelector('[data-selection-bar]');
          const quick = bar ? bar.querySelector('[data-selection-action="quick-edit"]') : null;
          return {
            count: bar ? bar.querySelector('[data-selection-count]').textContent : null,
            hidden: bar ? bar.hidden : null,
            quickDisabled: quick ? quick.disabled : null,
            selectedRows: doc.querySelectorAll('[data-rows] .row.is-selected').length,
            pressed: [...document.querySelectorAll('.redline__state-button')]
              .map((b) => b.getAttribute('aria-pressed')),
          };
        })()""")

    E("""document.querySelectorAll('.redline__state-button')[2].click()""")
    time.sleep(0.6)
    five = specimen_read()
    check("choosing the five item state updates the real bar",
          five["count"] == "5 items selected" and five["selectedRows"] == 5
          and five["pressed"][2] == "true",
          json.dumps(five))
    check("five selected disables Quick Edit in the specimen",
          five["quickDisabled"] is True, five["quickDisabled"])
    shot("06-redline-five-selected")

    E("""document.querySelectorAll('.redline__state-button')[4].click()""")
    time.sleep(0.6)
    long_count = specimen_read()
    check("the long count state renders without breaking the bar",
          long_count["count"] == "1,250 items selected", json.dumps(long_count))

    # Nothing pressed inside the specimen may reach a rate card.
    before = E("""(() => {
      const win = document.querySelector('.redline__preview').contentWindow;
      const doc = win.document;
      return {
        rows: doc.querySelectorAll('[data-rows] .row').length,
        store: (win.localStorage.getItem('rateCards') || '').length,
        total: doc.querySelector('[data-total]')?.textContent || '',
      };
    })()""")
    E("""(() => {
      const doc = document.querySelector('.redline__preview').contentDocument;
      const bar = doc.querySelector('[data-selection-bar]');
      bar.querySelectorAll('.rcsel__btn').forEach((b) => b.click());
      return true;
    })()""")
    time.sleep(0.8)
    after = E("""(() => {
      const win = document.querySelector('.redline__preview').contentWindow;
      const doc = win.document;
      return {
        rows: doc.querySelectorAll('[data-rows] .row').length,
        store: (win.localStorage.getItem('rateCards') || '').length,
        total: doc.querySelector('[data-total]')?.textContent || '',
        modal: !!doc.querySelector('[data-modal]:not([hidden])'),
        sheet: !!doc.querySelector('[data-quick-edit]:not([hidden])'),
        toasts: doc.querySelectorAll('[data-toast]').length,
      };
    })()""")
    check("pressing every specimen action leaves the records untouched",
          after["rows"] == before["rows"] and after["store"] == before["store"]
          and after["total"] == before["total"],
          json.dumps({"before": before, "after": after}))
    check("pressing a specimen action opens no modal, sheet, or toast",
          after["modal"] is False and after["sheet"] is False
          and after["toasts"] == 0,
          json.dumps(after))

    # Redline breakpoints drive the specimen through the same control.
    print("\n--- 4b. Specimen at each breakpoint ---")
    for width in (320, 375, 768, 1024, 1280):
        E(f"""document.querySelector('[data-redline-action="breakpoint:{width}"]').click()""")
        time.sleep(1.0)
        wide = E("""(() => {
          const frame = document.querySelector('.redline__preview');
          const doc = frame.contentDocument;
          const bar = doc.querySelector('[data-selection-bar]');
          if (!bar || bar.hidden) return null;
          const scroll = doc.querySelector('.table-scroll');
          const btns = [...bar.querySelectorAll('.rcsel__btn')];
          return {
            frameWidth: Math.round(parseFloat(frame.style.width || '0')),
            barW: Math.round(bar.getBoundingClientRect().width),
            port: scroll.clientWidth,
            actions: btns.length,
            named: btns.every((b) => !!b.getAttribute('aria-label')),
            count: bar.querySelector('[data-selection-count]').textContent,
            docOverflow: doc.documentElement.scrollWidth
              > doc.documentElement.clientWidth + 1,
          };
        })()""")
        check(f"specimen at {width}px stages the bar",
              wide is not None and wide["actions"] == 5 and wide["named"],
              json.dumps(wide))
        if wide:
            check(f"specimen at {width}px: the bar spans the visible table",
                  abs(wide["barW"] - wide["port"]) < 1.5,
                  f"{wide['barW']} vs {wide['port']}")
            check(f"specimen at {width}px: the preview page does not overflow",
                  wide["docOverflow"] is False, wide["docOverflow"])
        shot(f"07-redline-{width}")

    E("""document.querySelector('[data-redline-action="breakpoint:1440"]').click()""")
    time.sleep(0.8)

    # Leaving the section has to put the product back the way it was.
    E("""document.querySelector('[data-redline-action="gallery:back"]').click()""")
    time.sleep(1.2)
    left = E("""(() => {
      const frame = document.querySelector('.redline__preview');
      const doc = (frame && !frame.hidden && frame.contentDocument) || document;
      const bar = doc.querySelector('[data-selection-bar]');
      const visible = (sel) => {
        const el = doc.querySelector(sel);
        return !!(el && el.getBoundingClientRect().height > 2);
      };
      return {
        specimen: doc.body.getAttribute('data-specimen'),
        barHidden: bar ? bar.hidden : true,
        selected: doc.querySelectorAll('[data-rows] .row.is-selected').length,
        pageTopVisible: visible(
          '[data-page="list"] .surface__inner > .page__header'),
        toolbarVisible: visible('[data-page="list"] .toolbar'),
        statesHidden: document.querySelector('[data-redline-states]').hidden,
        entryPressed: document.querySelector(
          '[data-redline-action="gallery:action-bar"]').getAttribute('aria-pressed'),
      };
    })()""")
    check("leaving the section clears the specimen and its selection",
          left["specimen"] is None and left["barHidden"] and left["selected"] == 0,
          json.dumps(left))
    check("leaving the section restores the rest of the page",
          left["pageTopVisible"] and left["toolbarVisible"], json.dumps(left))
    check("leaving the section resets the panel controls",
          left["statesHidden"] is True and left["entryPressed"] == "false",
          json.dumps(left))

    # ==================================================================
    #  5. Earlier versions are untouched
    # ==================================================================
    print("\n--- 5. Version 2.0 regression guard ---")
    open_list(version="2.0")
    E(CLICK_ROW % 0)
    time.sleep(0.3)
    legacy = E("""(() => ({
      bar: document.querySelectorAll('[data-selection-bar]').length,
      actionColumn: document.querySelectorAll('.th--action').length,
      rowActions: document.querySelectorAll('[data-rows] .row .actions').length,
      selected: document.querySelectorAll('[data-rows] .row.is-selected').length,
      container: getComputedStyle(document.querySelector('.table-scroll')).containerType,
    }))()""")
    check("2.0 still has no action bar and keeps its Action column",
          legacy["bar"] == 0 and legacy["actionColumn"] > 0
          and legacy["rowActions"] > 0,
          json.dumps(legacy))
    check("2.0 keeps single row selection", legacy["selected"] == 1, legacy["selected"])
    check("2.0's table is not turned into a query container",
          legacy["container"] in ("normal", "", None), legacy["container"])

finally:
    print("\n" + "=" * 62)
    print(f"PASS {passes}   FAIL {len(failures)}")
    for item in failures:
        print(f"  - {item['name']}: {item['detail'][:300]}")
    print(f"screens: {OUT}")
    try:
        ws.close()
    except Exception:
        pass
    chrome.terminate()
    server.shutdown()
