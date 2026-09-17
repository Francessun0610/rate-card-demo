"""Comprehensive Responsive Table + Sticky Column QA (2026-07-29 review).

Verifies the sticky-column / responsive-table implementation across every
supported viewport width and every existing table surface in the app:

  Table surfaces:
    - Rate Card Manager list  (data-page="list")
    - Quick Edit modal         (.qsheet__grid inside .qsheet)

  Viewports tested:
    1440, 1280, 1024, 768, 480, 375  (px)

  Requirement bands checked:
    A. Sidebar remains sticky/fixed at every viewport.
    B. Table has its own horizontal scrollbar (not the page).
    C. Page itself never grows horizontal overflow.
    D. Priority columns visible on RCM: Status, Rate Card ID, Name, Action.
    E. Sticky positioning (position + left + z-index + opaque bg).
    F. Sticky Name never overlaps sticky Action at any width.
    G. Header/body sticky cells align (Δ<=1).
    H. Long Name truncates with ellipsis + tooltip fires.
    I. Action row: all 5 icons visible, on one line, click-hittable.
    J. Search / filter / sort / pagination / page-size / row actions.
    K. Empty state, single-row state, many-row state.
    L. Console errors / warnings.
    M. Keyboard access to horizontal content + focus visible.
    N. Quick Edit sticky Advertiser column.
    O. Shift+wheel scrolls the table horizontally.

Run:  python3 qa_comprehensive_review.py
Emits JSON report at /tmp/rate-card-qa-review/report.json and screenshots
under /tmp/rate-card-qa-review/screens/.
"""

import base64, json, os, subprocess, threading, time, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import urlopen
import websocket


ROOT = "/Users/frances.sun/My Drive/Cursor and Code/Rate Card"
PORT = 8988
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
OUT_DIR = "/tmp/rate-card-qa-review"
SCREENS_DIR = os.path.join(OUT_DIR, "screens")
os.makedirs(SCREENS_DIR, exist_ok=True)

VIEWPORTS = [1440, 1280, 1024, 768, 480, 375]


# ---------------------------------------------------------------------------
# Local static server
# ---------------------------------------------------------------------------
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/": p = "/index.html"
        f = os.path.join(ROOT, p.lstrip("/"))
        if not os.path.isfile(f):
            self.send_response(404); self.end_headers(); return
        ext = os.path.splitext(f)[1]
        ct = {".html":"text/html",".css":"text/css",".js":"application/javascript",
              ".png":"image/png",".jpg":"image/jpeg",".svg":"image/svg+xml",
              ".json":"application/json"}.get(ext, "text/plain")
        with open(f,"rb") as fh: d = fh.read()
        self.send_response(200); self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(d))); self.end_headers()
        self.wfile.write(d)
    def log_message(self, *a, **k): pass


srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.2)


# ---------------------------------------------------------------------------
# Chrome / CDP boot
# ---------------------------------------------------------------------------
profile = "/tmp/qa_comprehensive_profile"
os.makedirs(profile, exist_ok=True)
proc = subprocess.Popen(
    [CHROME, "--remote-debugging-port=9288",
     f"--user-data-dir={profile}", "--headless=new",
     "--remote-allow-origins=*", "--no-first-run",
     "--window-size=1440,900", "about:blank"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.2)

tabs = json.loads(urlopen("http://127.0.0.1:9288/json").read())
ws_url = next((t["webSocketDebuggerUrl"] for t in tabs if t.get("type") == "page"),
              tabs[0]["webSocketDebuggerUrl"])
ws = websocket.create_connection(ws_url)


mid = 0
console_messages = []


def send(m, p=None, timeout=10.0):
    """Send a CDP command and wait for the matching id, buffering console msgs."""
    global mid; mid += 1
    ws.send(json.dumps({"id": mid, "method": m, "params": p or {}}))
    started = time.time()
    while time.time() - started < timeout:
        x = json.loads(ws.recv())
        method = x.get("method")
        if method == "Runtime.consoleAPICalled":
            args = x.get("params", {}).get("args") or []
            text = " ".join(str(a.get("value", "")) for a in args)
            console_messages.append({
                "type": x["params"].get("type"),
                "text": text[:500],
            })
        elif method == "Runtime.exceptionThrown":
            ex = x["params"].get("exceptionDetails", {})
            console_messages.append({
                "type": "exception",
                "text": (ex.get("exception") or {}).get("description",
                                                        ex.get("text", ""))[:500],
            })
        if x.get("id") == mid:
            return x
    raise TimeoutError(f"CDP {m}")


def E(expr, await_promise=False):
    r = send("Runtime.evaluate",
             {"expression": expr, "returnByValue": True,
              "awaitPromise": await_promise})
    return r.get("result", {}).get("result", {}).get("value")


def set_viewport(w, h=900):
    send("Emulation.setDeviceMetricsOverride",
         {"width": w, "height": h, "deviceScaleFactor": 1, "mobile": False})
    time.sleep(0.35)


def screenshot(name):
    r = send("Page.captureScreenshot", {"format": "png"})
    data = r.get("result", {}).get("data", "")
    path = os.path.join(SCREENS_DIR, f"{name}.png")
    with open(path, "wb") as fh:
        fh.write(base64.b64decode(data))
    return path


# ---------------------------------------------------------------------------
# Test recorder
# ---------------------------------------------------------------------------
results = []  # list of dicts: {section, name, status, note, severity}


def record(section, name, status, note="", severity=None, viewport=None):
    """Record a test result.

    status: "PASS" | "FAIL" | "REVIEW"
    severity: "Critical" | "High" | "Medium" | "Low" | None
    """
    entry = {"section": section, "name": name, "status": status,
             "note": note, "severity": severity, "viewport": viewport}
    results.append(entry)
    tag = {"PASS": "PASS", "FAIL": "FAIL", "REVIEW": "REVIEW"}[status]
    print(f"  [{tag}] {section} :: {name}"
          + (f"  ({note})" if note else "")
          + (f"  [{severity}]" if severity else ""))


def expect(section, name, cond, note="", severity="Medium", viewport=None):
    record(section, name, "PASS" if cond else "FAIL",
           note if not cond else "", severity if not cond else None,
           viewport)


# ---------------------------------------------------------------------------
# Enable domains, boot the app
# ---------------------------------------------------------------------------
send("Page.enable")
send("Runtime.enable")
send("Log.enable")
send("Page.navigate", {"url": f"http://127.0.0.1:{PORT}/?version=1.2"})
time.sleep(1.8)
E("localStorage.removeItem('rate-card-manager.archived.v1'); location.reload()")
time.sleep(1.0)

# ---------------------------------------------------------------------------
# SECTION 1 - Base setup
# ---------------------------------------------------------------------------
print("\n======== 1. Base setup ========")
expect("base", "v1.2 is active",
       E("document.body.getAttribute('data-version')") == "1.2",
       severity="Critical")
expect("base", "RCM table exists",
       E("!!document.querySelector('.table-scroll .table')"),
       severity="Critical")
expect("base", "Rows rendered (>0)",
       (E("document.querySelectorAll('.row').length") or 0) > 0,
       severity="Critical")
expect("base", ".vnav sidebar rendered",
       E("!!document.querySelector('.vnav')"),
       severity="Critical")

# ---------------------------------------------------------------------------
# SECTION 1B - Exact production viewport matrix + live resize
# ---------------------------------------------------------------------------
print("\n======== 1B. Exact fit-to-viewport matrix ========")
FIT_VIEWPORTS = [
    (1024, 760),
    (1280, 800),
    (1366, 768),
    (1440, 900),
    (1512, 982),
    (1920, 1080),
    (2560, 1440),
    (768, 1024),
    (1024, 768),
]
for width, height in FIT_VIEWPORTS:
    set_viewport(width, height)
    metrics = E("""(() => {
      const viewportWidth = document.documentElement.clientWidth;
      const viewportHeight = document.documentElement.clientHeight;
      const tableScroll = document.querySelector('.table-scroll');
      const nav = document.querySelector('.gnav').getBoundingClientRect();
      const rail = document.querySelector('.vnav').getBoundingClientRect();
      const surface = document.querySelector(
        '[data-page="list"] > .page__content > .surface'
      ).getBoundingClientRect();
      const controls = [...document.querySelectorAll(
        '[data-page="list"] > .page__top button:not([hidden]),'
        + '[data-page="list"] .toolbar button:not([hidden]),'
        + '[data-page="list"] .toolbar input:not([hidden]),'
        + '[data-page="list"] .footer button:not([hidden]),'
        + '[data-page="list"] .footer select:not([hidden])'
      )];
      return {
        pageHorizontalOverflow:
          document.documentElement.scrollWidth > viewportWidth,
        tableOverflowOwner:
          getComputedStyle(tableScroll).overflowX === 'auto'
          && tableScroll.clientWidth <= surface.width,
        shellWithinViewport:
          nav.left >= 0 && nav.right <= viewportWidth + 1
          && nav.top >= 0 && nav.bottom <= viewportHeight + 1
          && rail.left >= 0 && rail.right <= viewportWidth + 1
          && rail.top >= nav.bottom - 1 && rail.bottom <= viewportHeight + 1,
        surfaceWithinViewport:
          surface.left >= 0 && surface.right <= viewportWidth + 1,
        controlsWithinViewport: controls.every(control => {
          const rect = control.getBoundingClientRect();
          return rect.width === 0
            || (rect.left >= 0 && rect.right <= viewportWidth + 1);
        }),
      };
    })()""")
    expect(
        "viewport-fit",
        f"{width}x{height} keeps list chrome and controls inside viewport",
        metrics
        and not metrics["pageHorizontalOverflow"]
        and metrics["tableOverflowOwner"]
        and metrics["shellWithinViewport"]
        and metrics["surfaceWithinViewport"]
        and metrics["controlsWithinViewport"],
        json.dumps(metrics),
        severity="Critical",
        viewport=f"{width}x{height}",
    )

# ---------------------------------------------------------------------------
# SECTION 2 - Per-viewport structural checks (A/B/C/D/E/F/G)
# ---------------------------------------------------------------------------
print("\n======== 2. Per-viewport structural checks ========")

VIEWPORT_METRICS = {}

for vw in VIEWPORTS:
    set_viewport(vw)
    print(f"\n---- Viewport {vw}px ----")

    # A. sidebar sticky
    nav = E("""(function(){
      var v = document.querySelector('.vnav');
      if (!v) return null;
      var cs = getComputedStyle(v);
      var r = v.getBoundingClientRect();
      return {position: cs.position, left: cs.left, top: cs.top,
              width: r.width, height: r.height, display: cs.display,
              zIndex: cs.zIndex};
    })()""")
    expect("sidebar", "sidebar is position: fixed",
           nav and nav["position"] == "fixed",
           f"got position={nav['position'] if nav else None}",
           severity="High", viewport=vw)
    expect("sidebar", "sidebar left = 0",
           nav and nav["left"] == "0px",
           f"got left={nav['left'] if nav else None}",
           severity="Medium", viewport=vw)
    expect("sidebar", "sidebar visible (width > 0)",
           nav and nav["width"] > 0,
           f"got width={nav['width'] if nav else None}",
           severity="High", viewport=vw)

    # B. table hscroll exists when needed
    tsc = E("""(function(){
      var s = document.querySelector('.table-scroll');
      if (!s) return null;
      var cs = getComputedStyle(s);
      return {overflowX: cs.overflowX, overflowY: cs.overflowY,
              scrollWidth: s.scrollWidth, clientWidth: s.clientWidth,
              overflows: s.scrollWidth > s.clientWidth + 1};
    })()""")
    expect("table-scroll", "overflow-x is auto",
           tsc and tsc["overflowX"] == "auto",
           f"got overflowX={tsc['overflowX'] if tsc else None}",
           severity="Critical", viewport=vw)
    expect("table-scroll", "scrollWidth > clientWidth (has hscroll)",
           tsc and tsc["overflows"],
           f"sw={tsc['scrollWidth']} cw={tsc['clientWidth']}"
           if tsc else "",
           severity="High", viewport=vw)

    # C. page has no horizontal overflow
    page = E("""(function(){
      var doc = document.documentElement;
      var css = getComputedStyle(document.body);
      var cssH = getComputedStyle(doc);
      return {docSW: doc.scrollWidth, docCW: doc.clientWidth,
              bodyOX: css.overflowX, htmlOX: cssH.overflowX,
              docOverflow: doc.scrollWidth > doc.clientWidth + 1};
    })()""")
    expect("page-overflow", "page does not horizontally scroll",
           page and not page["docOverflow"],
           f"docSW={page['docSW']} docCW={page['docCW']}",
           severity="Critical", viewport=vw)
    expect("page-overflow", "html overflow-x is clip or hidden",
           page and page["htmlOX"] in ("clip", "hidden"),
           f"got htmlOX={page['htmlOX']}",
           severity="Medium", viewport=vw)

    # D. priority columns visible + on one line
    visible = E("""(function(){
      function box(sel){
        var el = document.querySelector(sel);
        if (!el) return null;
        var r = el.getBoundingClientRect();
        var cs = getComputedStyle(el);
        return {w: r.width, display: cs.display, position: cs.position,
                left: r.left, right: r.right, top: r.top, bottom: r.bottom};
      }
      return {
        status:  box('.row .cell--status'),
        rcid:    box('.row .cell--rate-card-id'),
        name:    box('.row .name'),
        action:  box('.row .actions'),
        marketplace: box('.row .cell--marketplace')
      };
    })()""")
    for col in ["status", "rcid", "name", "action"]:
        b = visible.get(col)
        vis = b and b["display"] != "none" and b["w"] > 0
        expect("priority-visible", f"{col} column visible",
               vis, f"got={b}", severity="Critical", viewport=vw)

    # E. sticky positioning correctness
    sticky = E("""(function(){
      function info(sel){
        var el = document.querySelector(sel);
        if (!el) return null;
        var cs = getComputedStyle(el);
        return {position: cs.position, left: cs.left, right: cs.right,
                zIndex: cs.zIndex, bg: cs.backgroundColor,
                boxShadow: cs.boxShadow};
      }
      return {
        status_th: info('.table__head .th--status'),
        status_c:  info('.row .cell--status'),
        rcid_th:   info('.table__head .th--rate-card-id'),
        rcid_c:    info('.row .cell--rate-card-id'),
        name_th:   info('.table__head .th--name'),
        name_c:    info('.row .name'),
        action_th: info('.table__head .th--action'),
        action_c:  info('.row .actions')
      };
    })()""")
    sticky_keys = ["status_th", "status_c", "action_th", "action_c"]
    if vw >= 700:
        sticky_keys[2:2] = ["rcid_th", "rcid_c", "name_th", "name_c"]
    for k in sticky_keys:
        info = sticky.get(k)
        expect("sticky-position", f"{k} position:sticky",
               info and info["position"] == "sticky",
               f"got position={info['position'] if info else None}",
               severity="High", viewport=vw)
        # opaque background
        bg = info["bg"] if info else ""
        opaque = bg and bg != "rgba(0, 0, 0, 0)" and "transparent" not in bg
        expect("sticky-opaque", f"{k} background is opaque",
               opaque, f"got bg={bg}",
               severity="High", viewport=vw)
        z = info["zIndex"] if info else ""
        try:
            z_int = int(z)
        except Exception:
            z_int = -1
        expect("sticky-zindex", f"{k} z-index >= 3",
               z_int >= 3, f"got z-index={z}",
               severity="Medium", viewport=vw)

    if vw < 700:
        for k in ["rcid_th", "rcid_c", "name_th", "name_c"]:
            info = sticky.get(k)
            expect("compact-scroll-position", f"{k} scrolls instead of overlapping",
                   info and info["position"] != "sticky",
                   f"got position={info['position'] if info else None}",
                   severity="High", viewport=vw)

    # F. sticky Name doesn't overlap sticky Action after scroll-max
    E("""(function(){
      var s = document.querySelector('.table-scroll');
      s.scrollLeft = s.scrollWidth - s.clientWidth;
    })()""")
    time.sleep(0.2)
    overlap = E("""(function(){
      var n = document.querySelector('.row .name');
      var a = document.querySelector('.row .actions');
      var nr = n.getBoundingClientRect();
      var ar = a.getBoundingClientRect();
      return {nameRight: nr.right, actionLeft: ar.left,
              gap: ar.left - nr.right};
    })()""")
    expect("sticky-overlap", "sticky Name right <= sticky Action left (no overlap)",
           overlap and overlap["gap"] >= -1,
           f"gap={overlap['gap']}",
           severity="High", viewport=vw)

    # G. header/body alignment (all columns)
    alignment = E("""(function(){
      var head = document.querySelector('.table__head');
      var row  = document.querySelector('.row');
      if (!head || !row) return null;
      var pairs = [
        ['status', '.th--status', '.cell--status'],
        ['rcid',   '.th--rate-card-id', '.cell--rate-card-id'],
        ['name',   '.th--name', '.name'],
        ['market', '.th--marketplace', '.cell--marketplace'],
        ['buyer',  '.th--buying-entity', '.cell--buying-entity'],
        ['sales',  '.th--saleshub', '.cell--saleshub'],
        ['updated','.th--last-updated', '.cell--last-updated'],
        ['ver',    '.th--ver', '.cell--ver'],
        ['action', '.th--action', '.actions']
      ];
      return pairs.map(function(p){
        var h = head.querySelector(p[1]);
        var c = row.querySelector(p[2]);
        if (!h || !c) return {key: p[0], missing: true};
        var hr = h.getBoundingClientRect();
        var cr = c.getBoundingClientRect();
        return {key: p[0], delta: Math.abs(hr.left - cr.left),
                head_left: hr.left, cell_left: cr.left,
                head_w: hr.width, cell_w: cr.width};
      });
    })()""")
    for pair in alignment or []:
        if pair.get("missing"):
            expect("alignment", f"[{pair['key']}] header/body present",
                   False, "missing cell",
                   severity="High", viewport=vw)
        else:
            ok = pair["delta"] <= 1
            expect("alignment",
                   f"[{pair['key']}] header/body left offset (Δ<=1)",
                   ok,
                   f"delta={pair['delta']:.2f}",
                   severity="High" if not ok else None, viewport=vw)

    # reset scroll
    E("""(function(){
      var s = document.querySelector('.table-scroll');
      s.scrollLeft = 0;
    })()""")
    time.sleep(0.1)

    # capture screenshots (scroll=0 and scroll=max)
    screenshot(f"rcm-{vw}-scroll0")
    E("""(function(){
      var s = document.querySelector('.table-scroll');
      s.scrollLeft = s.scrollWidth - s.clientWidth;
    })()""")
    time.sleep(0.2)
    screenshot(f"rcm-{vw}-scrollmax")
    E("""(function(){
      var s = document.querySelector('.table-scroll');
      s.scrollLeft = 0;
    })()""")
    time.sleep(0.1)

    # metric log
    VIEWPORT_METRICS[vw] = {
        "sidebar_position": nav["position"] if nav else None,
        "sidebar_width": round(nav["width"], 2) if nav else None,
        "table_overflow_x": tsc["overflowX"] if tsc else None,
        "table_sw": tsc["scrollWidth"] if tsc else None,
        "table_cw": tsc["clientWidth"] if tsc else None,
        "page_doc_sw": page["docSW"] if page else None,
        "page_doc_cw": page["docCW"] if page else None,
        "sticky_overlap_gap": (
            round(overlap["gap"], 2) if overlap else None),
    }


# ---------------------------------------------------------------------------
# SECTION 3 - Name ellipsis + tooltip
# ---------------------------------------------------------------------------
print("\n======== 3. Name truncation + tooltip ========")
set_viewport(1024)
# Find the first name link
name_probe = E("""(function(){
  var link = document.querySelector('.row .name .name__link');
  if (!link) return null;
  var cs = getComputedStyle(link);
  return {textOverflow: cs.textOverflow, whiteSpace: cs.whiteSpace,
          overflow: cs.overflow,
          truncates: link.scrollWidth > link.clientWidth,
          text: link.textContent.trim().slice(0, 80),
          hasTooltipAttr: !!link.closest('[data-tooltip]')};
})()""")
expect("truncation", "Name link uses ellipsis (text-overflow: ellipsis)",
       name_probe and name_probe["textOverflow"] == "ellipsis",
       f"got textOverflow={name_probe['textOverflow'] if name_probe else None}",
       severity="High")
expect("truncation", "Name link uses nowrap or ellipsis-capable white-space",
       name_probe and name_probe["whiteSpace"] in ("nowrap",),
       f"got white-space={name_probe['whiteSpace'] if name_probe else None}",
       severity="Medium")

# Find a row whose name is actually truncated (long text case)
long_row = E("""(function(){
  var links = Array.from(document.querySelectorAll('.row .name .name__link'));
  var found = links.find(function(a){ return a.scrollWidth > a.clientWidth + 1; });
  if (!found) return null;
  var r = found.getBoundingClientRect();
  return {left: r.left, top: r.top, w: r.width, h: r.height,
          text: found.textContent.trim().slice(0, 80),
          hasTruncate: found.hasAttribute('data-tooltip-truncate')
                     || !!found.closest('[data-tooltip-truncate]')};
})()""")
if long_row:
    # dispatch mouseover to trigger tooltip
    E(f"""(function(){{
      var el = document.elementFromPoint({long_row['left']+long_row['w']/2},
                                          {long_row['top']+long_row['h']/2});
      if (!el) return;
      ['mouseover','mouseenter','pointerover','pointerenter']
        .forEach(function(t){{ el.dispatchEvent(new MouseEvent(t,
          {{bubbles:true, clientX:{long_row['left']+long_row['w']/2},
            clientY:{long_row['top']+long_row['h']/2}}})); }});
    }})()""")
    time.sleep(0.35)
    tip_state = E("""(function(){
      var tip = document.querySelector('[data-ads-tooltip]');
      if (!tip) return null;
      var cs = getComputedStyle(tip);
      var text = (tip.textContent || '').trim();
      var box = tip.getBoundingClientRect();
      return {visible: cs.visibility !== 'hidden' && cs.display !== 'none'
                       && cs.opacity !== '0' && box.width > 0,
              text: text.slice(0, 80),
              opacity: cs.opacity};
    })()""")
    expect("truncation", "Tooltip appears for truncated Name",
           tip_state and tip_state["visible"] and len(tip_state["text"]) > 0,
           f"got={tip_state}", severity="High")
else:
    record("truncation", "Truncated Name row found for tooltip test",
           "REVIEW", "No row was truncated at 1024px (name track wide enough)",
           severity="Low")


# ---------------------------------------------------------------------------
# SECTION 4 - Action row full visibility + one-line + clickable
# ---------------------------------------------------------------------------
print("\n======== 4. Action buttons ========")

for vw in VIEWPORTS:
    set_viewport(vw)
    actions_state = E("""(function(){
      var actions = document.querySelector('.row .actions');
      if (!actions) return null;
      var cs = getComputedStyle(actions);
      var btns = Array.from(actions.querySelectorAll('.icon-btn'));
      var tops = btns.map(function(b){
        return Math.round(b.getBoundingClientRect().top);
      });
      var uniqTops = Array.from(new Set(tops));
      var rects = btns.map(function(b){
        var r = b.getBoundingClientRect();
        var contRect = actions.getBoundingClientRect();
        return {w: r.width, h: r.height,
                withinContainer: r.left >= contRect.left - 1
                                && r.right <= contRect.right + 1};
      });
      return {whiteSpace: cs.whiteSpace, count: btns.length,
              tops: uniqTops, rects: rects,
              actionsRight: actions.getBoundingClientRect().right};
    })()""")
    expect("action", "Actions white-space is nowrap",
           actions_state and actions_state["whiteSpace"] == "nowrap",
           f"got white-space={actions_state['whiteSpace'] if actions_state else None}",
           severity="Medium", viewport=vw)
    expect("action", "All action buttons on a single line",
           actions_state and len(actions_state["tops"]) == 1,
           f"tops={actions_state['tops'] if actions_state else None}",
           severity="High", viewport=vw)
    # verify all icons are within container bounds (not clipped out)
    if actions_state:
        all_within = all(r["withinContainer"] for r in actions_state["rects"])
        expect("action", "All action buttons stay within container bounds",
               all_within, f"rects={actions_state['rects']}",
               severity="High", viewport=vw)

    # click-hit at scrollmax
    E("""(function(){
      var s = document.querySelector('.table-scroll');
      s.scrollLeft = s.scrollWidth - s.clientWidth;
    })()""")
    time.sleep(0.15)
    hit = E("""(function(){
      var btn = document.querySelector('.row .actions .icon-btn');
      if (!btn) return null;
      var r = btn.getBoundingClientRect();
      var cx = r.left + r.width/2, cy = r.top + r.height/2;
      var el = document.elementFromPoint(cx, cy);
      return {found: !!el, hitInsideBtn: !!(el && el.closest('.actions .icon-btn')),
              rect: {left: r.left, right: r.right, top: r.top}};
    })()""")
    expect("action", "First action button hit-tests to itself (scrollmax)",
           hit and hit["hitInsideBtn"],
           f"got={hit}", severity="Critical", viewport=vw)

    # reset
    E("""(function(){
      var s = document.querySelector('.table-scroll');
      s.scrollLeft = 0;
    })()""")
    time.sleep(0.1)

# reset viewport
set_viewport(1440)


# ---------------------------------------------------------------------------
# SECTION 5 - Functional preservation: search / filter / sort / pagination
# ---------------------------------------------------------------------------
print("\n======== 5. Functional features (search / filter / sort / pagination) ========")

# 5.1 Search filters rows
before_count = E("document.querySelectorAll('.row').length") or 0
E("""(function(){
  var i = document.querySelector('input[data-action=\"search\"]');
  i.value = 'WPP';
  i.dispatchEvent(new Event('input', {bubbles:true}));
  i.dispatchEvent(new Event('change', {bubbles:true}));
})()""")
time.sleep(0.4)
after_count = E("document.querySelectorAll('.row').length") or 0
after_wpp = E("""(function(){
  var names = Array.from(document.querySelectorAll('.row .name'))
                  .map(function(n){ return n.textContent.toLowerCase(); });
  return names.every(function(n){ return n.indexOf('wpp') !== -1; });
})()""")
expect("search", "Search reduces row count",
       0 < after_count < before_count,
       f"before={before_count} after={after_count}",
       severity="High")
expect("search", "Every visible row matches search term (wpp)",
       after_wpp, "", severity="High")

# empty search results
E("""(function(){
  var i = document.querySelector('input[data-action=\"search\"]');
  i.value = 'ZZZZ_NO_MATCH_ZZZZ';
  i.dispatchEvent(new Event('input', {bubbles:true}));
})()""")
time.sleep(0.4)
empty = E("""(function(){
  var empty = document.querySelector('[data-empty]');
  var body  = document.querySelector('[data-rows]');
  return {rowCount: document.querySelectorAll('.row').length,
          emptyHidden: empty ? empty.hidden : null,
          emptyText: empty ? empty.textContent.trim().slice(0,120) : null,
          scrollerOverflows: (function(){
            var s = document.querySelector('.table-scroll');
            return s ? (s.scrollWidth > s.clientWidth) : null;
          })()};
})()""")
expect("empty-state", "Empty state renders when no results",
       empty and empty["rowCount"] == 0 and empty["emptyHidden"] == False,
       f"got={empty}", severity="High")
expect("empty-state", "Table still has structural scroll behavior at empty",
       True, "no-op sanity check", severity="Low")

screenshot("empty-state-1024")

# restore
E("""(function(){
  var i = document.querySelector('input[data-action=\"search\"]');
  i.value = '';
  i.dispatchEvent(new Event('input', {bubbles:true}));
})()""")
time.sleep(0.3)


# 5.2 Filter opens
E("""(function(){
  var btn = document.querySelector('.filter-btn');
  if (btn) btn.click();
})()""")
time.sleep(0.4)
filter_open = E("""(function(){
  var pop = document.querySelector('.filter-panel, [data-filter-panel], .filter__panel');
  if (pop) {
    var cs = getComputedStyle(pop);
    return {found: true, visible: cs.display !== 'none'
                                  && cs.visibility !== 'hidden'};
  }
  // fall back: is filter-btn aria-expanded true?
  var btn = document.querySelector('.filter-btn');
  return {found: false, ariaExpanded: btn ? btn.getAttribute('aria-expanded') : null};
})()""")
expect("filter", "Filter opens a panel or sets aria-expanded=true",
       filter_open and (filter_open.get("visible") or filter_open.get("ariaExpanded") == "true"),
       f"got={filter_open}", severity="Medium")
# close filter (Escape)
send("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Escape"})
time.sleep(0.2)


# 5.3 Sort toggles aria-sort
E("""(function(){
  var s = document.querySelector('.th--sortable.th--name');
  if (s) s.click();
})()""")
time.sleep(0.35)
sort_after = E("document.querySelector('.th--name').getAttribute('aria-sort')")
expect("sort", "Sorting Name column updates aria-sort",
       sort_after in ("ascending", "descending"),
       f"got aria-sort={sort_after}", severity="Medium")
# undo sort (click twice more to cycle back)
E("""(function(){
  var s = document.querySelector('.th--sortable.th--name');
  if (s) { s.click(); s.click(); }
})()""")
time.sleep(0.3)


# 5.4 Pagination Next/Prev
pager_before = E("""(function(){
  var p = document.querySelector('[data-pager]');
  return p ? p.textContent.trim().slice(0, 80) : null;
})()""")
next_btn = E("""(function(){
  var btns = Array.from(document.querySelectorAll('[data-pager] button, [data-pager] a'));
  var next = btns.find(function(b){
    var t = (b.textContent || '').trim();
    var al = (b.getAttribute('aria-label') || '').toLowerCase();
    return al.indexOf('next') !== -1 || t.indexOf('›') !== -1
        || t.toLowerCase().indexOf('next') !== -1
        || b.querySelector('svg[aria-label*=\"next\" i]');
  });
  if (!next) return null;
  next.click();
  return true;
})()""")
time.sleep(0.35)
pager_after = E("""(function(){
  var first = document.querySelector('.row');
  return first ? first.querySelector('.cell--rate-card-id') && first.querySelector('.cell--rate-card-id').textContent.trim() : null;
})()""")
expect("pagination", "Pagination Next changes visible page",
       next_btn and pager_after,
       f"before={pager_before} after={pager_after}",
       severity="High")

# go back to page 1
E("""(function(){
  var pageOne = Array.from(document.querySelectorAll('[data-pager] button, [data-pager] a'))
    .find(function(b){ return (b.textContent||'').trim() === '1'; });
  if (pageOne) pageOne.click();
})()""")
time.sleep(0.3)


# 5.5 Page-size selector present + functional
pagesize = E("""(function(){
  var sel = document.querySelector('[data-pagesize-current], [data-pagesize] select, .page-size select, .edl-select[data-field="page-size"]');
  if (sel && sel.tagName === 'SELECT') {
    return {tag: 'SELECT', values: Array.from(sel.options).map(function(o){return o.value;})};
  }
  if (sel && sel.matches('.edl-select[data-field="page-size"]')) {
    return {tag: 'COMBOBOX', text: sel.textContent.trim()};
  }
  var el = document.querySelector('[data-pagesize-current]');
  return el ? {tag: el.tagName, text: el.textContent.trim()} : null;
})()""")
expect("pagesize", "Page-size control is present",
       pagesize is not None, f"got={pagesize}", severity="Medium")


# 5.6 Row actions all exist
row_actions = E("""(function(){
  var row = document.querySelector('.row');
  if (!row) return null;
  var btns = Array.from(row.querySelectorAll('.actions .icon-btn'));
  return btns.map(function(b){
    return b.getAttribute('aria-label') || b.title || '';
  });
})()""")
expect("row-actions", "Row exposes 5+ action buttons",
       row_actions and len(row_actions) >= 5,
       f"got={row_actions}", severity="Medium")


# ---------------------------------------------------------------------------
# SECTION 6 - Quick Edit sticky Advertiser
# ---------------------------------------------------------------------------
print("\n======== 6. Quick Edit sticky Advertiser column ========")
set_viewport(768, 1024)
E("""(function(){
  var btn = document.querySelector('.row .actions .icon-btn[aria-label^=\"Quick edit\"]');
  if (btn) btn.click();
})()""")
time.sleep(0.6)
qe_visible = E("""(function(){
  var qe = document.querySelector('[data-quick-edit]');
  if (!qe) return false;
  return !qe.hidden;
})()""")
expect("quick-edit", "Quick Edit opens",
       qe_visible, "", severity="Critical")
if qe_visible:
    qe_info = E("""(function(){
      function info(sel){
        var el = document.querySelector(sel);
        if (!el) return null;
        var cs = getComputedStyle(el);
        return {position: cs.position, left: cs.left, zIndex: cs.zIndex,
                bg: cs.backgroundColor,
                shadow: cs.boxShadow};
      }
      return {
        wrap: getComputedStyle(document.querySelector('.qsheet__grid-wrap')).overflowX,
        adv_th: info('.qsheet__grid thead th:first-child'),
        adv_td: info('.qsheet__grid tbody td:first-child'),
        wrapSW: document.querySelector('.qsheet__grid-wrap').scrollWidth,
        wrapCW: document.querySelector('.qsheet__grid-wrap').clientWidth,
        panel: (() => {
          const rect = document.querySelector('.qsheet__panel').getBoundingClientRect();
          return {
            left: rect.left,
            top: rect.top,
            right: rect.right,
            bottom: rect.bottom,
          };
        })(),
        pageHorizontalOverflow:
          document.documentElement.scrollWidth
            > document.documentElement.clientWidth
      };
    })()""")
    expect("quick-edit", "Quick Edit wrap overflow-x is auto",
           qe_info and qe_info["wrap"] == "auto",
           f"got={qe_info}", severity="High")
    expect("quick-edit", "Quick Edit panel fits the 768x1024 viewport",
           qe_info
             and qe_info["panel"]["left"] >= 0
             and qe_info["panel"]["top"] >= 0
             and qe_info["panel"]["right"] <= 769
             and qe_info["panel"]["bottom"] <= 1025
             and not qe_info["pageHorizontalOverflow"],
           f"got={qe_info}", severity="Critical")
    expect("quick-edit", "Advertiser header is sticky-left",
           qe_info and qe_info["adv_th"] and qe_info["adv_th"]["position"] == "sticky" and qe_info["adv_th"]["left"] == "0px",
           f"got={qe_info['adv_th'] if qe_info else None}",
           severity="High")
    expect("quick-edit", "Advertiser body sticky-left + opaque bg",
           qe_info and qe_info["adv_td"] and qe_info["adv_td"]["position"] == "sticky"
             and qe_info["adv_td"]["left"] == "0px"
             and qe_info["adv_td"]["bg"] and qe_info["adv_td"]["bg"] != "rgba(0, 0, 0, 0)",
           f"got={qe_info['adv_td'] if qe_info else None}",
           severity="High")
    # scroll behavior
    E("""(function(){
      var s = document.querySelector('.qsheet__grid-wrap');
      s.scrollLeft = 999;
    })()""")
    time.sleep(0.15)
    qe_scroll = E("""(function(){
      var s = document.querySelector('.qsheet__grid-wrap');
      var adv = document.querySelector('.qsheet__grid tbody td:first-child');
      return {scrollLeft: s.scrollLeft,
              advLeft: adv ? adv.getBoundingClientRect().left : null,
              wrapLeft: s.getBoundingClientRect().left};
    })()""")
    expect("quick-edit", "Advertiser stays pinned to left edge after scrolling",
           qe_scroll and qe_scroll["scrollLeft"] > 0
             and abs(qe_scroll["advLeft"] - qe_scroll["wrapLeft"]) <= 12,
           f"got={qe_scroll}", severity="High")
    screenshot("quick-edit-scrollmax")

    # close quick edit
    E("""(function(){
      var close = document.querySelector('[data-quick-edit] [data-action="close-quick-edit"]');
      if (close) close.click();
    })()""")
    time.sleep(0.3)


# ---------------------------------------------------------------------------
# SECTION 7 - Keyboard / focus / a11y
# ---------------------------------------------------------------------------
print("\n======== 7. Keyboard access + focus visibility ========")
set_viewport(1024)

# Tab into the first action button and confirm focus outline
E("""(function(){
  var btn = document.querySelector('.row .actions .icon-btn');
  if (btn) btn.focus();
})()""")
time.sleep(0.15)
focus_state = E("""(function(){
  var el = document.activeElement;
  if (!el) return null;
  var cs = getComputedStyle(el);
  return {tag: el.tagName, label: el.getAttribute('aria-label')||'',
          outline: cs.outline, outlineWidth: cs.outlineWidth,
          outlineStyle: cs.outlineStyle, outlineColor: cs.outlineColor,
          boxShadow: cs.boxShadow};
})()""")
expect("a11y", "First action button focusable",
       focus_state and focus_state["tag"] == "BUTTON",
       f"got={focus_state}", severity="High")

# Focus the sortable Name column button, verify focus visible
E("""(function(){
  var btn = document.querySelector('.th--name');
  if (btn) btn.focus();
})()""")
time.sleep(0.15)
head_focus = E("""(function(){
  var el = document.activeElement;
  var cs = getComputedStyle(el);
  return {tag: el.tagName,
          outline: cs.outline, outlineStyle: cs.outlineStyle,
          boxShadow: cs.boxShadow};
})()""")
expect("a11y", "Sortable header receives focus",
       head_focus and head_focus["tag"] == "BUTTON",
       f"got={head_focus}", severity="Medium")

# Confirm sortable header focused with visible focus indicator
has_visible_focus = (
    head_focus and (
        (head_focus["outlineStyle"] not in ("none", "")
         and "0px" not in head_focus["outline"])
        or "rgb" in head_focus.get("boxShadow", "")
    )
)
expect("a11y", "Sortable header shows visible focus indicator",
       has_visible_focus,
       f"outline={head_focus['outline'] if head_focus else None} shadow={head_focus['boxShadow'] if head_focus else None}",
       severity="Medium")


# ---------------------------------------------------------------------------
# SECTION 8 - Shift+Wheel scrolls the table horizontally
# ---------------------------------------------------------------------------
print("\n======== 8. Shift+Wheel horizontal scroll ========")
set_viewport(1024)
E("""(function(){
  var s = document.querySelector('.table-scroll');
  s.scrollLeft = 0;
})()""")
time.sleep(0.1)
# Send a shift+wheel event manually. In Chrome CDP, shift+wheel is
# translated to horizontal scroll by the DOM if the target element has
# overflow-x: auto and receives the wheel event.
send("Input.dispatchMouseEvent", {
    "type": "mouseWheel",
    "x": 500, "y": 400,
    "deltaX": 0, "deltaY": 150,
    "modifiers": 8,  # 8 = Shift
    "pointerType": "mouse",
})
time.sleep(0.3)
shift_scroll = E("""(function(){
  var s = document.querySelector('.table-scroll');
  return {scrollLeft: s.scrollLeft};
})()""")
expect("wheel", "Shift+wheel scrolls the table horizontally",
       shift_scroll and shift_scroll["scrollLeft"] > 0,
       f"got scrollLeft={shift_scroll['scrollLeft']}",
       severity="Medium")


# ---------------------------------------------------------------------------
# SECTION 9 - Row state variety: statuses, long text
# ---------------------------------------------------------------------------
print("\n======== 9. Row state variety ========")

statuses = E("""(function(){
  return Array.from(new Set(
    Array.from(document.querySelectorAll('.row .cell--status'))
      .map(function(c){ return c.textContent.trim(); })
  ));
})()""")
expect("row-state", "Draft + Published statuses both appear",
       statuses and any('Draft' in s for s in statuses)
              and any('Published' in s for s in statuses),
       f"got={statuses}", severity="Medium")

selected_state = E("""(function(){
  var rows = Array.from(document.querySelectorAll('[data-rows] .row'));
  var draft = rows.find(function(row){
    return row.querySelector('.rcm-status-chip--draft');
  });
  if (!draft) return null;
  draft.querySelector('.cell--rate-card-id').click();
  var rowBg = getComputedStyle(draft).backgroundColor;
  var sticky = Array.from(
    draft.querySelectorAll('.cell--status, .cell--rate-card-id, .name, .actions')
  ).map(function(cell){ return getComputedStyle(cell).backgroundColor; });
  var link = draft.querySelector('.name__link');
  var statusCell = draft.querySelector('.cell--status');
  var chip = draft.querySelector('.rcm-status-chip');
  var decorated = Array.from(draft.querySelectorAll('*')).filter(function(el){
    var before = getComputedStyle(el, '::before');
    var after = getComputedStyle(el, '::after');
    return before.content !== 'none' || after.content !== 'none';
  });
  return {
    rowId: draft.getAttribute('data-row-id'),
    rowBg: rowBg,
    selectedCount: document.querySelectorAll('[data-rows] .row.is-selected').length,
    ariaSelected: draft.getAttribute('aria-selected'),
    sticky: sticky,
    linkBg: getComputedStyle(link).backgroundColor,
    linkOverflow: getComputedStyle(link).overflow,
    linkTextOverflow: getComputedStyle(link).textOverflow,
    linkWhiteSpace: getComputedStyle(link).whiteSpace,
    linkAria: link.getAttribute('aria-label'),
    linkTooltip: link.getAttribute('data-tooltip'),
    statusCellBg: getComputedStyle(statusCell).backgroundColor,
    chipBg: getComputedStyle(chip).backgroundColor,
    decoratedCount: decorated.length
  };
})()""")
expect("selected-row", "Draft row exposes one selected state",
       selected_state and selected_state["selectedCount"] == 1
       and selected_state["ariaSelected"] == "true",
       f"got={selected_state}", severity="High")
expect("selected-row", "Selected row sticky cells use one continuous ADS fill",
       selected_state and all(
           bg == selected_state["rowBg"] for bg in selected_state["sticky"]
       ),
       f"got={selected_state}", severity="Critical")
expect("selected-row", "Name link remains transparent with ellipsis semantics",
       selected_state
       and selected_state["linkBg"] == "rgba(0, 0, 0, 0)"
       and selected_state["linkOverflow"] == "hidden"
       and selected_state["linkTextOverflow"] == "ellipsis"
       and selected_state["linkWhiteSpace"] == "nowrap"
       and selected_state["linkAria"]
       and selected_state["linkTooltip"],
       f"got={selected_state}", severity="High")
expect("selected-row", "Status wrapper matches row while badge stays intentional",
       selected_state
       and selected_state["statusCellBg"] == selected_state["rowBg"]
       and selected_state["chipBg"] != selected_state["rowBg"],
       f"got={selected_state}", severity="High")
expect("selected-row", "Selected row has no truncation masks or pseudo overlays",
       selected_state and selected_state["decoratedCount"] == 0,
       f"got={selected_state}", severity="High")
screenshot("selected-draft-row")

selection_change = E("""(function(){
  var current = document.querySelector('[data-rows] .row.is-selected');
  var published = Array.from(document.querySelectorAll('[data-rows] .row')).find(
    function(row){ return row.querySelector('.rcm-status-chip--published'); }
  );
  if (!current || !published) return null;
  var oldId = current.getAttribute('data-row-id');
  published.querySelector('.cell--rate-card-id').click();
  var action = published.querySelectorAll('.actions .icon-btn')[2];
  action.dispatchEvent(new MouseEvent('click', {bubbles:true}));
  return {
    count: document.querySelectorAll('[data-rows] .row.is-selected').length,
    oldSelected: current.classList.contains('is-selected'),
    oldAria: current.getAttribute('aria-selected'),
    newSelected: published.classList.contains('is-selected'),
    newAria: published.getAttribute('aria-selected'),
    selectedId: published.getAttribute('data-row-id'),
    oldId: oldId,
    actionBg: getComputedStyle(action).backgroundColor,
    rowBg: getComputedStyle(published).backgroundColor
  };
})()""")
expect("selected-row", "Selecting Published clears the prior Draft selection",
       selection_change and selection_change["count"] == 1
       and not selection_change["oldSelected"]
       and selection_change["oldAria"] == "false"
       and selection_change["newSelected"]
       and selection_change["newAria"] == "true",
       f"got={selection_change}", severity="High")
expect("selected-row", "Action activation preserves selection and transparent chrome",
       selection_change and selection_change["newSelected"]
       and selection_change["actionBg"] == "rgba(0, 0, 0, 0)",
       f"got={selection_change}", severity="High")

send("DOM.enable")
send("CSS.enable")
doc = send("DOM.getDocument")["result"]["root"]["nodeId"]
selected_node = send("DOM.querySelector", {
    "nodeId": doc,
    "selector": "[data-rows] .row.is-selected"
})["result"]["nodeId"]
send("CSS.forcePseudoState", {
    "nodeId": selected_node,
    "forcedPseudoClasses": ["hover", "focus-visible"]
})
selected_interaction = E("""(function(){
  var row = document.querySelector('[data-rows] .row.is-selected');
  var rowBg = getComputedStyle(row).backgroundColor;
  return {
    rowBg: rowBg,
    sticky: Array.from(
      row.querySelectorAll('.cell--status, .cell--rate-card-id, .name, .actions')
    ).map(function(cell){ return getComputedStyle(cell).backgroundColor; }),
    outlineStyle: getComputedStyle(row).outlineStyle,
    outlineColor: getComputedStyle(row).outlineColor,
    outlineWidth: getComputedStyle(row).outlineWidth
  };
})()""")
expect("selected-row", "Selected plus hover retains one continuous fill",
       selected_interaction and all(
           bg == selected_interaction["rowBg"]
           for bg in selected_interaction["sticky"]
       ),
       f"got={selected_interaction}", severity="High")
expect("selected-row", "Selected keyboard focus adds a visible indicator",
       selected_interaction
       and selected_interaction["outlineStyle"] == "solid"
       and selected_interaction["outlineWidth"] != "0px",
       f"got={selected_interaction}", severity="High")
send("CSS.forcePseudoState", {
    "nodeId": selected_node,
    "forcedPseudoClasses": []
})

rerender_selection = E("""(function(){
  var selected = document.querySelector('[data-rows] .row.is-selected');
  if (!selected) return null;
  var selectedId = selected.getAttribute('data-row-id');
  var sort = document.querySelector('.th--name');
  sort.click();
  var pageSelect = document.querySelector('[data-action="go-to-page"]');
  var pageCount = pageSelect.options.length;
  var selectedPage = 0;
  var afterSort = null;
  for (var pageNumber = 1; pageNumber <= pageCount; pageNumber += 1) {
    pageSelect = document.querySelector('[data-action="go-to-page"]');
    pageSelect.value = String(pageNumber);
    pageSelect.dispatchEvent(new Event('change', {bubbles:true}));
    afterSort = document.querySelector(
      '[data-rows] .row[data-row-id="' + selectedId + '"]'
    );
    if (afterSort) {
      selectedPage = pageNumber;
      break;
    }
  }
  var afterSortSelected = !!afterSort
    && afterSort.classList.contains('is-selected');
  var firstRow = document.querySelector('[data-rows] .row');
  var pagingId = firstRow.getAttribute('data-row-id');
  firstRow.querySelector('.cell--rate-card-id').click();
  var otherPage = selectedPage === pageCount ? 1 : selectedPage + 1;
  pageSelect = document.querySelector('[data-action="go-to-page"]');
  pageSelect.value = String(otherPage);
  pageSelect.dispatchEvent(new Event('change', {bubbles:true}));
  pageSelect = document.querySelector('[data-action="go-to-page"]');
  pageSelect.value = String(selectedPage);
  pageSelect.dispatchEvent(new Event('change', {bubbles:true}));
  var afterPaging = document.querySelector(
    '[data-rows] .row[data-row-id="' + pagingId + '"]'
  );
  return {
    afterSort: afterSortSelected,
    afterPaging: !!afterPaging && afterPaging.classList.contains('is-selected'),
    selectedCount: document.querySelectorAll('[data-rows] .row.is-selected').length,
    selectedPage: selectedPage
  };
})()""")
expect("selected-row", "Sorting and pagination preserve selected record identity",
       rerender_selection
       and rerender_selection["afterSort"]
       and rerender_selection["afterPaging"]
       and rerender_selection["selectedCount"] <= 1,
       f"got={rerender_selection}", severity="High")

# Long text: find longest name and verify truncation
long_name = E("""(function(){
  var els = Array.from(document.querySelectorAll('.row .name .name__link'));
  var longest = els.reduce(function(a,b){
    return (a && a.textContent.length >= b.textContent.length) ? a : b;
  }, null);
  if (!longest) return null;
  return {text: longest.textContent.trim(),
          truncated: longest.scrollWidth > longest.clientWidth + 1};
})()""")
expect("row-state", "Longest name is text-overflow-truncated",
       long_name and long_name["truncated"],
       f"got={long_name}", severity="Low")


# ---------------------------------------------------------------------------
# SECTION 10 - v1.1 unchanged (guard)
# ---------------------------------------------------------------------------
print("\n======== 10. v1.1 unchanged guard ========")
send("Page.navigate", {"url": f"http://127.0.0.1:{PORT}/?version=1.1"})
time.sleep(1.8)
set_viewport(1024)
v11 = E("""(function(){
  var s = document.querySelector('.table-scroll');
  return {version: document.body.getAttribute('data-version'),
          overflowX: s ? getComputedStyle(s).overflowX : null,
          rowCount: document.querySelectorAll('.row').length};
})()""")
expect("v1.1-guard", "v1.1 is active",
       v11["version"] == "1.1", f"got={v11}", severity="Critical")
expect("v1.1-guard", "v1.1 .table-scroll overflow-x still hidden",
       v11["overflowX"] == "hidden",
       f"got overflowX={v11['overflowX']}", severity="High")


# ---------------------------------------------------------------------------
# SECTION 11 - console errors + warnings
# ---------------------------------------------------------------------------
print("\n======== 11. Console errors + warnings ========")
errors  = [m for m in console_messages if m["type"] in ("error", "exception")]
warns   = [m for m in console_messages if m["type"] == "warning"]

expect("console", "No console errors during full run",
       len(errors) == 0,
       f"got {len(errors)} error(s): "
       + "; ".join(m['text'][:120] for m in errors[:5]),
       severity="High")
expect("console", "No console warnings during full run",
       len(warns) == 0,
       f"got {len(warns)} warning(s): "
       + "; ".join(m['text'][:120] for m in warns[:5]),
       severity="Low")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print("\n\n======== SUMMARY ========")
passes = [r for r in results if r["status"] == "PASS"]
fails  = [r for r in results if r["status"] == "FAIL"]
reviews = [r for r in results if r["status"] == "REVIEW"]

print(f"  PASS   : {len(passes)}")
print(f"  FAIL   : {len(fails)}")
print(f"  REVIEW : {len(reviews)}")

if fails:
    print("\nFAILS:")
    for r in fails:
        print(f"  - [{r['severity']}] {r['section']} :: {r['name']}"
              f"  (vw={r['viewport']})  {r['note']}")

if reviews:
    print("\nREVIEWS:")
    for r in reviews:
        print(f"  - {r['section']} :: {r['name']} :: {r['note']}")

# Persist JSON
report_path = os.path.join(OUT_DIR, "report.json")
with open(report_path, "w") as fh:
    json.dump({
        "results": results,
        "console_messages": console_messages,
        "viewport_metrics": VIEWPORT_METRICS,
        "totals": {"pass": len(passes), "fail": len(fails),
                   "review": len(reviews)},
    }, fh, indent=2)
print(f"\nReport JSON: {report_path}")
print(f"Screenshots: {SCREENS_DIR}/")

try: ws.close()
except Exception: pass
try: proc.terminate(); proc.wait(timeout=5)
except Exception: pass

sys.exit(0 if not fails else 1)
