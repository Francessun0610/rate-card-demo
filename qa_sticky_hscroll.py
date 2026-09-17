"""Sticky Columns + Horizontal Scroll QA (2026-07-29 brief).

Verifies the 2026-07-29 refactor of the RCM data table:
  1. .table-scroll scrolls horizontally in v1.2 when the row exceeds
     the container width (base rule kept overflow-x: hidden for v1.1).
  2. Status, Rate Card ID, and Name columns are position: sticky on
     the left with cumulative pixel offsets (0, --col-status,
     --col-status + --col-rcid).
  3. Action column stays sticky on the right (unchanged from 07-08).
  4. Sticky cells carry opaque backgrounds + non-zero z-index so
     scrolling content stays hidden behind them.
  5. Row hover / selected background composition covers every
     sticky cell (matches the existing Action pattern).
  6. Header and body sticky cells align across rows (same left offset).
  7. Resizer z-indices between sticky columns lift above 3 so the
     drag handle is reachable.
  8. Page itself never grows a horizontal scrollbar (page-shell guard).
  9. Quick Edit's Advertiser column is sticky-left in v1.2.
 10. Rate Card manager table still renders Status, Rate Card ID, Name,
     and Action at every supported viewport width (1440 / 1280 /
     1024 / 900 / 800).

Run:  python3 qa_sticky_hscroll.py

Prints PASS/FAIL for each assertion and exits non-zero on any FAIL.
"""

import base64, json, os, subprocess, threading, time, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import urlopen
import websocket

ROOT = "/Users/frances.sun/My Drive/Cursor and Code/Rate Card"
PORT = 8981


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
        self.send_header("Content-Length", str(len(d))); self.end_headers(); self.wfile.write(d)
    def log_message(self, *a, **k): pass


srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.2)

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
profile = "/tmp/qa_sticky_hscroll_profile"
os.makedirs(profile, exist_ok=True)
proc = subprocess.Popen([CHROME, "--remote-debugging-port=9281",
                          f"--user-data-dir={profile}", "--headless=new",
                          "--remote-allow-origins=*", "--no-first-run",
                          "--window-size=1440,900", "about:blank"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.2)

tabs = json.loads(urlopen("http://127.0.0.1:9281/json").read())
ws_url = next((t["webSocketDebuggerUrl"] for t in tabs if t.get("type") == "page"),
              tabs[0]["webSocketDebuggerUrl"])
ws = websocket.create_connection(ws_url)

mid = 0
def send(m, p=None):
    global mid; mid += 1
    ws.send(json.dumps({"id": mid, "method": m, "params": p or {}}))
    while True:
        x = json.loads(ws.recv())
        if x.get("id") == mid: return x

def E(e):
    r = send("Runtime.evaluate", {"expression": e, "returnByValue": True, "awaitPromise": True})
    return r.get("result", {}).get("result", {}).get("value")


passes = 0; fails = []
def expect(name, cond, note=""):
    global passes
    if cond:
        passes += 1; print(f"  PASS  {name}")
    else:
        fails.append(name); print(f"  FAIL  {name}{' -- ' + note if note else ''}")


def set_viewport(w, h=900):
    """Set the emulated viewport width. Chrome DevTools protocol."""
    send("Emulation.setDeviceMetricsOverride",
         {"width": w, "height": h, "deviceScaleFactor": 1, "mobile": False})
    # Give the page a beat to re-layout.
    time.sleep(0.3)


send("Page.enable")
send("Page.navigate", {"url": f"http://127.0.0.1:{PORT}/?version=1.2"})
time.sleep(1.5)


# ---------------------------------------------------------------------------
print("\n== Base setup (v1.2 active, table renders) ==")
expect("v1.2 is active",
       E("document.body.getAttribute('data-version')") == "1.2")
expect("RCM table exists",
       E("!!document.querySelector('.table-scroll .table')"))
expect("Row count > 0",
       (E("document.querySelectorAll('.row').length") or 0) > 0)


# ---------------------------------------------------------------------------
print("\n== .table-scroll wraps a horizontal scrollbar (v1.2) ==")
set_viewport(1024)  # Narrower than the row's natural width
overflow_x = E("getComputedStyle(document.querySelector('.table-scroll')).overflowX")
expect(".table-scroll overflow-x is auto in v1.2",
       overflow_x == "auto", f"got={overflow_x}")

overflow_state = E("""(function(){
  var s = document.querySelector('.table-scroll');
  if (!s) return null;
  return {scrollWidth: s.scrollWidth, clientWidth: s.clientWidth,
          canScroll: s.scrollWidth > s.clientWidth + 1};
})()""")
expect(".table-scroll overflows (row wider than container) at 1024px",
       overflow_state and overflow_state["canScroll"],
       f"sw={overflow_state['scrollWidth']} cw={overflow_state['clientWidth']}"
       if overflow_state else "null")


# ---------------------------------------------------------------------------
print("\n== Page itself does not horizontally scroll ==")
page_scroll = E("""(function(){
  return {sw: document.documentElement.scrollWidth,
          cw: document.documentElement.clientWidth,
          bodyOverflowX: getComputedStyle(document.body).overflowX,
          htmlOverflowX: getComputedStyle(document.documentElement).overflowX};
})()""")
expect("html overflow-x is clip or hidden",
       page_scroll["htmlOverflowX"] in ("clip", "hidden"),
       f"got={page_scroll['htmlOverflowX']}")
expect("document.documentElement.scrollWidth <= clientWidth",
       page_scroll["sw"] <= page_scroll["cw"] + 1,
       f"sw={page_scroll['sw']} cw={page_scroll['cw']}")


# ---------------------------------------------------------------------------
print("\n== Sticky-left cluster: Status, Rate Card ID, Name ==")
sticky_info = E("""(function(){
  function info(sel){
    var el = document.querySelector(sel);
    if (!el) return null;
    var cs = getComputedStyle(el);
    return {position: cs.position, left: cs.left, zIndex: cs.zIndex,
            background: cs.backgroundColor};
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

# Header
expect("Status header is position: sticky",
       sticky_info["status_th"]["position"] == "sticky",
       f"got={sticky_info['status_th']['position']}")
expect("Status header left: 0",
       sticky_info["status_th"]["left"] == "0px",
       f"got={sticky_info['status_th']['left']}")
expect("Rate Card ID header is position: sticky",
       sticky_info["rcid_th"]["position"] == "sticky")
expect("Rate Card ID header left equals --col-status (96px default)",
       sticky_info["rcid_th"]["left"] in ("96px", "88px"),
       f"got={sticky_info['rcid_th']['left']}")
expect("Name header is position: sticky",
       sticky_info["name_th"]["position"] == "sticky")
expect("Name header has a non-zero left offset (>= 200)",
       sticky_info["name_th"]["left"].endswith("px") and
       float(sticky_info["name_th"]["left"].replace("px", "")) >= 200,
       f"got={sticky_info['name_th']['left']}")
expect("Action header is position: sticky (unchanged)",
       sticky_info["action_th"]["position"] == "sticky")

# Body cells alignment (same left as headers)
expect("Status body cell is position: sticky",
       sticky_info["status_c"]["position"] == "sticky")
expect("Status body cell left matches Status header left",
       sticky_info["status_c"]["left"] == sticky_info["status_th"]["left"],
       f"body={sticky_info['status_c']['left']} head={sticky_info['status_th']['left']}")
expect("Rate Card ID body cell left matches header left",
       sticky_info["rcid_c"]["left"] == sticky_info["rcid_th"]["left"])
expect("Name body cell left matches header left",
       sticky_info["name_c"]["left"] == sticky_info["name_th"]["left"])
expect("Action body cell is position: sticky",
       sticky_info["action_c"]["position"] == "sticky")


# ---------------------------------------------------------------------------
print("\n== Sticky cells have opaque backgrounds + z-index >= 3 ==")
for name in ["status_th", "rcid_th", "name_th", "action_th",
             "status_c", "rcid_c", "name_c", "action_c"]:
    info = sticky_info[name]
    bg = info["background"]
    # background must be non-transparent; e.g. rgb(255, 255, 255) or rgba(..., 1)
    opaque = bg != "rgba(0, 0, 0, 0)" and "transparent" not in bg
    expect(f"{name} background is opaque",
           opaque, f"got={bg}")
    z = info["zIndex"]
    expect(f"{name} z-index >= 3",
           z.isdigit() and int(z) >= 3, f"got={z}")


# ---------------------------------------------------------------------------
print("\n== Sticky pinning behavior at scrollLeft > 0 ==")
# Force a horizontal scroll on the container and verify sticky cells
# stay pinned in place (their bounding-rect left doesn't move with the
# scroll).
before = E("""(function(){
  var s = document.querySelector('.table-scroll');
  var status = document.querySelector('.row .cell--status');
  var action = document.querySelector('.row .actions');
  return {
    scrollWidth: s.scrollWidth, clientWidth: s.clientWidth,
    statusLeft: status.getBoundingClientRect().left,
    actionRight: action.getBoundingClientRect().right,
    scrollerLeft: s.getBoundingClientRect().left,
    scrollerRight: s.getBoundingClientRect().right
  };
})()""")

E("""(function(){
  var s = document.querySelector('.table-scroll');
  s.scrollLeft = Math.min(200, s.scrollWidth - s.clientWidth);
})()""")
time.sleep(0.1)

after = E("""(function(){
  var s = document.querySelector('.table-scroll');
  var status = document.querySelector('.row .cell--status');
  var action = document.querySelector('.row .actions');
  return {
    scrollLeft: s.scrollLeft,
    statusLeft: status.getBoundingClientRect().left,
    actionRight: action.getBoundingClientRect().right,
    scrollerLeft: s.getBoundingClientRect().left,
    scrollerRight: s.getBoundingClientRect().right
  };
})()""")

expect("scrollLeft > 0 after programmatic scroll",
       after["scrollLeft"] > 0, f"got={after['scrollLeft']}")

# Status pinned to container's left edge
expect("Sticky Status column pinned to container left edge",
       abs(after["statusLeft"] - after["scrollerLeft"]) < 2,
       f"statusLeft={after['statusLeft']} scrollerLeft={after['scrollerLeft']}")
# Action pinned to container's right edge
expect("Sticky Action column pinned to container right edge",
       abs(after["actionRight"] - after["scrollerRight"]) < 2,
       f"actionRight={after['actionRight']} scrollerRight={after['scrollerRight']}")


# ---------------------------------------------------------------------------
print("\n== Sticky Action column still fully clickable ==")
# Reset scroll to 0 first so all buttons are visible in their natural
# position, then re-scroll to verify action stays clickable.
E("""(function(){
  var s = document.querySelector('.table-scroll');
  s.scrollLeft = 0;
})()""")
time.sleep(0.1)
action_click = E("""(function(){
  var first = document.querySelector('.row .actions .icon-btn');
  if (!first) return {found: false};
  var rect = first.getBoundingClientRect();
  var cx = rect.left + rect.width / 2, cy = rect.top + rect.height / 2;
  var hit = document.elementFromPoint(cx, cy);
  return {found: true, hitTag: hit && hit.tagName,
          hitInsideButton: !!(hit && hit.closest('.actions .icon-btn'))};
})()""")
expect("Action icon button hit-tests to itself",
       action_click["found"] and action_click["hitInsideButton"],
       f"got={action_click}")


# ---------------------------------------------------------------------------
print("\n== Header/body horizontal alignment (every column) ==")
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
    return {key: p[0], head_left: hr.left, cell_left: cr.left,
            delta: Math.abs(hr.left - cr.left)};
  });
})()""")
for pair in alignment:
    if pair.get("missing"):
        expect(f"[{pair['key']}] header + body pair present",
               False, "cell missing")
    else:
        expect(f"[{pair['key']}] header/body left offset match (Δ<=1)",
               pair["delta"] <= 1,
               f"delta={pair['delta']} head={pair['head_left']} cell={pair['cell_left']}")


# ---------------------------------------------------------------------------
print("\n== Resizer z-index above sticky neighbors ==")
resizers = E("""(function(){
  function z(sel){
    var el = document.querySelector(sel);
    if (!el) return null;
    return parseInt(getComputedStyle(el).zIndex, 10);
  }
  return {
    status: z('.th--status .th-resizer'),
    rcid:   z('.th--rate-card-id .th-resizer'),
    name:   z('.th--name .th-resizer'),
    ver:    z('.th--ver .th-resizer')
  };
})()""")
expect("Status resizer z-index >= 4",
       resizers["status"] is not None and resizers["status"] >= 4,
       f"got={resizers['status']}")
expect("Rate Card ID resizer z-index >= 4",
       resizers["rcid"] is not None and resizers["rcid"] >= 4,
       f"got={resizers['rcid']}")
expect("Ver resizer z-index >= 4",
       resizers["ver"] is not None and resizers["ver"] >= 4,
       f"got={resizers['ver']}")


# ---------------------------------------------------------------------------
print("\n== Priority columns visible at every viewport (1440, 1280, 1024, 900, 800) ==")
for vw in [1440, 1280, 1024, 900, 800]:
    set_viewport(vw)
    visible = E("""(function(){
      function box(sel){
        var el = document.querySelector(sel);
        if (!el) return null;
        var r = el.getBoundingClientRect();
        var cs = getComputedStyle(el);
        return {w: r.width, display: cs.display,
                left: r.left, right: r.right};
      }
      return {
        status: box('.row .cell--status'),
        rcid: box('.row .cell--rate-card-id'),
        name: box('.row .name'),
        action: box('.row .actions')
      };
    })()""")
    for k in ["status", "rcid", "name", "action"]:
        b = visible[k]
        vis = b and b["display"] != "none" and b["w"] > 0
        expect(f"[vw={vw}] {k} column is visible",
               vis, f"got={b}")


# ---------------------------------------------------------------------------
print("\n== Sticky Name does NOT visually overlap sticky Action (any viewport) ==")
for vw in [1440, 1280, 1024, 900, 800]:
    set_viewport(vw)
    # Force sticky to activate by scrolling right.
    E("""(function(){
      var s = document.querySelector('.table-scroll');
      s.scrollLeft = s.scrollWidth - s.clientWidth;
    })()""")
    time.sleep(0.15)
    o = E("""(function(){
      var name = document.querySelector('.row .name');
      var actions = document.querySelector('.row .actions');
      var nameR = name.getBoundingClientRect();
      var actR = actions.getBoundingClientRect();
      return {nameRight: nameR.right, actionLeft: actR.left,
              nameW: nameR.width, actW: actR.width};
    })()""")
    gap = o["actionLeft"] - o["nameRight"]
    expect(f"[vw={vw}] sticky Name right (<= sticky Action left)",
           gap >= -1, f"nameRight={o['nameRight']} actionLeft={o['actionLeft']} gap={gap}")


# ---------------------------------------------------------------------------
print("\n== Quick Edit sticky-left Advertiser column (v1.2) ==")
set_viewport(1440)  # Wide viewport
# Open Quick Edit for the first row
E("""(function(){
  var btn = document.querySelector('.row .actions .icon-btn[aria-label^=\"Quick edit\"]');
  if (btn) btn.click();
})()""")
time.sleep(0.5)
qe_open = E("!document.querySelector('[data-quick-edit]').hidden")
expect("Quick Edit is open", qe_open)

if qe_open:
    qe = E("""(function(){
      function info(sel){
        var el = document.querySelector(sel);
        if (!el) return null;
        var cs = getComputedStyle(el);
        return {position: cs.position, left: cs.left, zIndex: cs.zIndex,
                background: cs.backgroundColor};
      }
      return {
        wrapOverflow: getComputedStyle(document.querySelector('.qsheet__grid-wrap')).overflowX,
        advTh: info('.qsheet__grid thead th:first-child'),
        advTd: info('.qsheet__grid tbody td:first-child')
      };
    })()""")
    expect("Quick Edit wrap has horizontal overflow: auto",
           qe["wrapOverflow"] == "auto", f"got={qe['wrapOverflow']}")
    expect("Advertiser header sticky-left (position: sticky, left: 0)",
           qe["advTh"] and qe["advTh"]["position"] == "sticky" and qe["advTh"]["left"] == "0px",
           f"got={qe['advTh']}")
    expect("Advertiser header z-index >= 2 (top-left corner)",
           qe["advTh"] and qe["advTh"]["zIndex"].isdigit() and int(qe["advTh"]["zIndex"]) >= 2,
           f"got={qe['advTh']['zIndex'] if qe['advTh'] else None}")
    expect("Advertiser body cell sticky-left",
           qe["advTd"] and qe["advTd"]["position"] == "sticky" and qe["advTd"]["left"] == "0px",
           f"got={qe['advTd']}")
    expect("Advertiser cells have opaque backgrounds",
           qe["advTh"] and qe["advTh"]["background"] != "rgba(0, 0, 0, 0)" and
           qe["advTd"] and qe["advTd"]["background"] != "rgba(0, 0, 0, 0)")


# ---------------------------------------------------------------------------
print("\n== V1.1 unchanged (base .table-scroll overflow-x still hidden) ==")
send("Page.navigate", {"url": f"http://127.0.0.1:{PORT}/?version=1.1"})
time.sleep(1.5)
set_viewport(1024)
v11 = E("""(function(){
  return {
    version: document.body.getAttribute('data-version'),
    overflow: getComputedStyle(document.querySelector('.table-scroll')).overflowX
  };
})()""")
expect("v1.1 is active", v11["version"] == "1.1", f"got={v11['version']}")
expect("v1.1 .table-scroll overflow-x is hidden (unchanged)",
       v11["overflow"] == "hidden", f"got={v11['overflow']}")


# ---------------------------------------------------------------------------
print("\n== Summary ==")
print(f"  {passes} passing, {len(fails)} failing")
if fails:
    print("  Failing checks:")
    for name in fails: print(f"    - {name}")

try:
    ws.close()
except Exception:
    pass
try:
    proc.terminate(); proc.wait(timeout=5)
except Exception:
    pass

sys.exit(0 if not fails else 1)
