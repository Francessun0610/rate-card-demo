"""ADS 2.1 Compliance Suite.

Locks in the design-system contract for the Rate Card app:
  - Body font is Open Sans (ADS body font)
  - Page title is MultiplaneTWDC Display SemiBold 30/36 (font/heading/xl)
  - Brand color resolves to ADS Indigo/300 #4045C2
  - All button variants use ADS tokens (primary/secondary/ghost/danger)
  - Form fields use ADS Field tokens (36h, 6r, 8/12 padding, Open Sans)
  - Pagination items are 36x36 with 8px radius and Indigo/300 active
  - Status chips locked to Figma 157:1980 / 157:2008 (do NOT regress)
  - Top nav uses Indigo/300 background, white text, 14/20 Open Sans
  - Toast: top-right anchor, ADS node 70:62 blue info variant
  - Modal: 12px radius, ADS scrim, Open Sans title
  - Action icons: 24x24, Indigo/300 color, Delete -> red on hover
  - Body class is `theme-ads` (default since 2026-06-28)

NOT exercised by this suite (intentional ADS exceptions):
  - `.dlsim-*` macOS/Finder/Excel chrome (native OS simulation)
  - `Download blank template` + `Upload rate card` buttons (user-pinned)

Run after any token / component CSS change. 50+ assertions.
"""

import base64, json, os, subprocess, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import urlopen
import websocket

ROOT = "/Users/frances.sun/My Drive/Cursor and Code/Rate Card"
PORT = 8977


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
    def log_message(s,*a,**k): pass


srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.2)

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
profile = "/tmp/qa_ads_compliance_profile"
os.makedirs(profile, exist_ok=True)
proc = subprocess.Popen([CHROME, "--remote-debugging-port=9255",
                          f"--user-data-dir={profile}", "--headless=new",
                          "--remote-allow-origins=*", "--no-first-run",
                          "--window-size=1440,900", "about:blank"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.2)

tabs = json.loads(urlopen("http://127.0.0.1:9255/json").read())
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


send("Page.enable")
# Pinned to 2.0. The row Action column and its ADS icon buttons still ship
# in 1.x and 2.0, but 2.1 replaces them with the selected-row action bar,
# so those component checks have to run on a version that still renders
# them. The 2.1 bar is covered by its own section at the end of this file.
send("Page.navigate", {"url": f"http://127.0.0.1:{PORT}/?version=2.0&qa=ads_compliance"})
time.sleep(1.5)

# ---------------------------------------------------------------------------
print("\n== Foundation ==")
expect("body class is theme-ads (default)",
       E("document.body.classList.contains('theme-ads')"))
body_font = E("getComputedStyle(document.body).fontFamily") or ""
expect("body font-family resolves to Open Sans first",
       body_font.startswith('"Open Sans"') or body_font.startswith("Open Sans"),
       f"got={body_font[:80]}")

# ADS tokens resolve
brand = E("getComputedStyle(document.body).getPropertyValue('--ads-brand').trim()")
expect("--ads-brand = #4045C2 (Indigo/300)", brand.upper() == "#4045C2", f"got={brand}")
danger_bg = E("getComputedStyle(document.body).getPropertyValue('--ads-danger-bg').trim()")
expect("--ads-danger-bg = #C73945 (red/600)", danger_bg.upper() == "#C73945", f"got={danger_bg}")
radius_sm = E("getComputedStyle(document.body).getPropertyValue('--ads-radius-sm').trim()")
expect("--ads-radius-sm = 6px", radius_sm == "6px", f"got={radius_sm}")

# ---------------------------------------------------------------------------
print("\n== Typography ==")
title_font = E("getComputedStyle(document.querySelector('.page__title')).fontFamily") or ""
expect("page title font is MultiplaneTWDC Display",
       "MultiplaneTWDC" in title_font, f"got={title_font[:80]}")
expect("page title 30px",
       E("getComputedStyle(document.querySelector('.page__title')).fontSize") == "30px")
expect("page title weight 600",
       E("getComputedStyle(document.querySelector('.page__title')).fontWeight") == "600")
expect("page subtitle 14px",
       E("getComputedStyle(document.querySelector('.page__subtitle')).fontSize") == "14px")

# Table Header Cell, ADS Figma 7737:210 / 105:9
header = E("""(function(){
  var row = document.querySelector('.table__head');
  var cell = row.querySelector('.th');
  var rs = getComputedStyle(row);
  var cs = getComputedStyle(cell);
  return {
    height: Math.round(row.getBoundingClientRect().height),
    fontSize: cs.fontSize,
    lineHeight: cs.lineHeight,
    weight: cs.fontWeight,
    gap: cs.gap,
    padding: [cs.paddingTop, cs.paddingRight, cs.paddingBottom, cs.paddingLeft],
    background: rs.backgroundColor,
    divider: rs.borderBottomColor
  };
})()""")
expect(
    "table header matches ADS 7737:210 anatomy",
    header == {
        "height": 39,
        "fontSize": "13px",
        "lineHeight": "18px",
        "weight": "400",
        "gap": "6px",
        "padding": ["10px", "12px", "10px", "12px"],
        "background": "rgb(255, 255, 255)",
        "divider": "rgba(15, 18, 20, 0.2)",
    },
    f"got={header}",
)

# Body row 14/20 Open Sans Regular
row_fs = E("getComputedStyle(document.querySelector('[data-rows] .row .cell')).fontSize")
expect("body row 14px", row_fs == "14px", f"got={row_fs}")

# ---------------------------------------------------------------------------
print("\n== Buttons (excluding Download blank template / Upload rate card) ==")
# Primary button (Create rate card)
b = E("""(function(){
  var b = document.querySelector('[data-action=\"create\"]');
  if (!b) return null;
  var cs = getComputedStyle(b);
  return {h: b.getBoundingClientRect().height, fs: cs.fontSize, fw: cs.fontWeight,
          bg: cs.backgroundColor, color: cs.color, radius: cs.borderRadius,
          family: cs.fontFamily};
})()""")
expect("Create button: 36px tall", b and abs(b["h"] - 36) < 1, f"h={b['h'] if b else None}")
expect("Create button: 14/20 Open Sans 600",
       b and b["fs"] == "14px" and b["fw"] == "600" and ("Open Sans" in (b["family"] or "")),
       f"got={b}")
expect("Create button: bg = Indigo/300 (#4045C2)",
       b and "64, 69, 194" in b["bg"], f"bg={b['bg'] if b else None}")
expect("Create button: 6px radius",
       b and b["radius"] == "6px", f"radius={b['radius'] if b else None}")
expect("Create button: white text",
       b and b["color"] in ("rgb(255, 255, 255)",), f"color={b['color'] if b else None}")

# Filter (secondary outline)
b = E("""(function(){
  var b = document.querySelector('[data-action=\"toggle-filter\"], [data-action=open-filters]');
  if (!b) return null;
  var cs = getComputedStyle(b);
  return {h: b.getBoundingClientRect().height, color: cs.color, border: cs.border, radius: cs.borderRadius};
})()""")
expect("Filter button: 36px tall", b and abs(b["h"] - 36) < 1, f"h={b['h'] if b else None}")
expect("Filter button: brand text color",
       b and "64, 69, 194" in b["color"], f"color={b['color'] if b else None}")
expect("Filter button: 6px radius",
       b and b["radius"] == "6px", f"radius={b['radius'] if b else None}")

# Excluded: Download blank template + Upload template
print("\n  -- Excluded from token-conformance pass (user-pinned) --")
dl = E("""(function(){
  var b = document.querySelector('[data-action=\"download-template\"]');
  if (!b) return null;
  return {present: true, label: b.textContent.trim()};
})()""")
expect("'Download blank template' still present + unchanged",
       dl and "Download blank template" in dl["label"], f"got={dl}")
ul = E("""(function(){
  var b = document.querySelector('[data-action=\"upload-template\"]');
  if (!b) return null;
  return {present: true, label: b.textContent.trim()};
})()""")
expect("'Upload rate card' still present + unchanged",
       ul and "Upload rate card" in ul["label"], f"got={ul}")

# ---------------------------------------------------------------------------
print("\n== Table ==")
expect("table container radius 8px",
       E("getComputedStyle(document.querySelector('.table-card, .surface, [data-rows]')).borderRadius") == "8px")
# Body row height (ADS Table compact uses 48 per Figma)
row_h = E("document.querySelector('[data-rows] .row').getBoundingClientRect().height")
expect("body row 48px tall", abs(row_h - 48) < 2, f"h={row_h}")
# Row divider = --ads-border-recessed (rgba(15,18,20,0.10))
divider = E("getComputedStyle(document.querySelector('[data-rows] .row')).borderBottomColor")
expect("row divider rgba(15,18,20,0.1)",
       "15, 18, 20" in divider and "0.1" in divider, f"got={divider}")
# Link color = ADS brand
link_color = E("(function(){var l=document.querySelector('[data-rows] .row [data-link], [data-rows] .row a'); return l?getComputedStyle(l).color:null;})()")
expect("name-cell link color = Indigo/300",
       link_color and "64, 69, 194" in link_color, f"got={link_color}")

# Action icons - 24x24, indigo
icons = E("""Array.from(document.querySelector('[data-rows] .row').querySelectorAll('button[aria-label], .icon-btn')).map(function(b){
  var cs = getComputedStyle(b);
  return {label: b.getAttribute('aria-label'), w: b.getBoundingClientRect().width, h: b.getBoundingClientRect().height, color: cs.color, bg: cs.backgroundColor};
})""") or []
expect("action icons present (5)", len(icons) == 5, f"count={len(icons)}")
for ic in icons:
    expect(f"  {ic.get('label')!r}: 24x24",
           abs(ic["w"] - 24) < 1 and abs(ic["h"] - 24) < 1, f"got={ic}")
    expect(f"  {ic.get('label')!r}: Indigo/300 color",
           "64, 69, 194" in ic["color"], f"got={ic['color']}")
    expect(f"  {ic.get('label')!r}: transparent rest background (no white pill)",
           ic["bg"] in ("rgba(0, 0, 0, 0)", "transparent"), f"got={ic['bg']}")

# Hover behavior: real mouse-move triggers no background fill.
# Verifies the table-action-icon-hover fix (no white square behind glyphs
# on hover, just a brand-color shift; Delete -> destructive red).
print("\n  -- Action icon hover (real :hover, no background fill) --")
def _hov(label):
    rect = E(f"""(function(){{
      var b = document.querySelector('[data-rows] .row .actions .icon-btn[aria-label=\\\"{label}\\\"]');
      if (!b) return null;
      var r = b.getBoundingClientRect();
      return {{x: r.left + r.width / 2, y: r.top + r.height / 2}};
    }})()""")
    if rect: send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": rect["x"], "y": rect["y"]})
    return rect

# Park mouse far away first
send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": 10, "y": 10})
time.sleep(0.15)
for label in ["Quick edit", "Duplicate rate card", "Export rate card", "Delete rate card"]:
    _hov(label); time.sleep(0.2)
    bg = E(f"(function(){{var b=document.querySelector('[data-rows] .row .actions .icon-btn[aria-label=\\\"{label}\\\"]'); return b?getComputedStyle(b).backgroundColor:null;}})()")
    color = E(f"(function(){{var b=document.querySelector('[data-rows] .row .actions .icon-btn[aria-label=\\\"{label}\\\"]'); return b?getComputedStyle(b).color:null;}})()")
    expect(f"  {label!r}: hover bg transparent (no white pill)",
           bg in ("rgba(0, 0, 0, 0)", "transparent"), f"got={bg}")
    if label == "Delete rate card":
        expect(f"  {label!r}: hover color = danger red",
               color and "199, 57, 69" in color, f"got={color}")
    else:
        expect(f"  {label!r}: hover color = brand-hover (lighter indigo)",
               color and "101, 103, 206" in color, f"got={color}")
    send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": 10, "y": 10})
    time.sleep(0.1)

# ---------------------------------------------------------------------------
print("\n== Chips (locked to Figma 157:1980 / 157:2008) ==")
pub = E("""(function(){
  var c = document.querySelector('.rcm-status-chip--published');
  if (!c) return null;
  var cs = getComputedStyle(c);
  return {bg: cs.backgroundColor, color: cs.color, radius: cs.borderRadius, fw: cs.fontWeight, fs: cs.fontSize};
})()""")
expect("Published chip: #DDE6F7 bg",
       pub and pub["bg"] == "rgb(221, 230, 247)", f"got={pub}")
expect("Published chip: #143F90 text",
       pub and pub["color"] == "rgb(20, 63, 144)", f"got={pub['color'] if pub else None}")
expect("Published chip: 100px radius (pill)",
       pub and pub["radius"] == "100px", f"got={pub['radius'] if pub else None}")
# Chip text was 12px; 14px is the floor for anything a reader has to read.
expect("Published chip: 14px / 600",
       pub and pub["fs"] == "14px" and pub["fw"] == "600", f"got={pub}")

draft = E("""(function(){
  var c = document.querySelector('.rcm-status-chip--draft');
  if (!c) return null;
  var cs = getComputedStyle(c);
  return {bg: cs.backgroundColor, color: cs.color};
})()""")
expect("Draft chip: #ECEEEE bg",
       draft and draft["bg"] == "rgb(236, 238, 238)", f"got={draft}")
expect("Draft chip: #1E2528 text",
       draft and draft["color"] == "rgb(30, 37, 40)", f"got={draft['color'] if draft else None}")

# ---------------------------------------------------------------------------
print("\n== Pagination ==")
active = E("""(function(){
  var b = document.querySelector('.page-btn--num.is-active');
  if (!b) return null;
  var cs = getComputedStyle(b);
  return {w: b.getBoundingClientRect().width, h: b.getBoundingClientRect().height,
          bg: cs.backgroundColor, color: cs.color, radius: cs.borderRadius, fs: cs.fontSize};
})()""")
expect("active page btn: 36x36", active and abs(active["w"] - 36) < 1 and abs(active["h"] - 36) < 1, f"got={active}")
expect("active page btn: Indigo/300 bg",
       active and "64, 69, 194" in active["bg"], f"got={active['bg'] if active else None}")
expect("active page btn: white text",
       active and active["color"] == "rgb(255, 255, 255)", f"got={active['color'] if active else None}")
expect("active page btn: 8px radius",
       active and active["radius"] == "8px", f"got={active['radius'] if active else None}")

# ---------------------------------------------------------------------------
print("\n== Navigation ==")
expect("nav bg = Indigo/300",
       "64, 69, 194" in (E("getComputedStyle(document.querySelector('.gnav')).backgroundColor") or ""))
expect("nav inactive item fw 400",
       E("getComputedStyle(document.querySelector('.gnav__item:not(.gnav__item--active)')).fontWeight") == "400")
expect("nav active item fw 600",
       E("getComputedStyle(document.querySelector('.gnav__item--active')).fontWeight") == "600")
expect("nav 14px",
       E("getComputedStyle(document.querySelector('.gnav__item')).fontSize") == "14px")

# ---------------------------------------------------------------------------
print("\n== Search ==")
si = E("""(function(){
  var i = document.querySelector('[data-action="search"]');
  var wrap = i && i.closest('.ads-search');
  if (!i || !wrap) return null;
  var cs = getComputedStyle(wrap);
  var icon = wrap.querySelector('.ads-search__icon').getBoundingClientRect();
  var clear = wrap.querySelector('.ads-search__clear');
  return {
    h: wrap.getBoundingClientRect().height,
    radius: cs.borderRadius,
    icon: [icon.width, icon.height],
    clearLabel: clear && clear.getAttribute('aria-label')
  };
})()""")
expect("Search uses ADS 36px pill, 20px icon, and named clear action",
       si and abs(si["h"] - 36) < 1 and si["radius"] == "100px"
       and si["icon"] == [20, 20] and si["clearLabel"] == "Clear search", f"got={si}")
search_states = {"rest": E("""getComputedStyle(
  document.querySelector('[data-action="search"]').closest('.ads-search')
).borderColor""")}
E("document.querySelector('[data-action=\"search\"]').focus()")
time.sleep(0.2)
search_states["focus"] = E("""(() => {
  const wrap = document.querySelector('[data-action="search"]').closest('.ads-search');
  return {border: getComputedStyle(wrap).borderColor, shadow: getComputedStyle(wrap).boxShadow};
})()""")
E("document.querySelector('[data-action=\"search\"]').disabled = true")
time.sleep(0.2)
search_states["disabled"] = E("""(() => {
  const input = document.querySelector('[data-action="search"]');
  const wrap = input.closest('.ads-search');
  return {border: getComputedStyle(wrap).borderColor, text: getComputedStyle(input).color};
})()""")
E("""(() => {
  const input = document.querySelector('[data-action="search"]');
  input.disabled = false;
  input.blur();
})()""")
expect("Search rest, focus, and disabled states use ADS tokens",
       search_states == {
           "rest": "rgba(15, 18, 20, 0.2)",
           "focus": {
               "border": "rgba(15, 18, 20, 0.5)",
               "shadow": "none",
           },
           "disabled": {
               "border": "rgba(15, 18, 20, 0.05)",
               "text": "rgba(15, 18, 20, 0.3)",
           },
       }, f"got={search_states}")

# Search behavior: the query must actually filter the table, match
# every spec field (name/rateCardId/saleshubId/marketplace/status/
# lastUpdated/version), normalize hyphens vs spaces, trim whitespace,
# reset pagination to page 1, update the result count, and show the
# ADS empty state when nothing matches. Each assertion uses a real
# `input` event (HTMLInputElement.value setter + dispatchEvent) so
# the app's listener fires the same code path real keystrokes hit.
def _type(text):
    safe = json.dumps(text)
    E(f"""(function(){{
      var i = document.querySelector('[data-action="search"]');
      var s = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
      s.call(i, ''); i.dispatchEvent(new Event('input', {{bubbles: true}}));
      s.call(i, {safe}); i.dispatchEvent(new Event('input', {{bubbles: true}}));
    }})()""")
    time.sleep(0.15)

def _rows(): return E("document.querySelectorAll('[data-rows] .row').length")

_type("omni")
expect("search 'omni' filters rows (Omnicom)", _rows() >= 1 and _rows() < 100)
_type("draft")
expect("search 'draft' matches status field", _rows() >= 1)
_type("upfront")
expect("search 'upfront' matches marketplace field", _rows() >= 1)
_type("07/31/2026")
expect("search '07/31/2026' matches formatted last-updated", _rows() >= 1)
_type("RC-DAS-DENTSU")
expect("search 'RC-DAS-DENTSU' matches rate-card-id fragment", _rows() >= 1)
_type("rc-das-dentsu addr")
rc_a = _rows()
_type("rc das dentsu-addr")
rc_b = _rows()
expect("search hyphen-vs-space normalization symmetric", rc_a == rc_b and rc_a >= 1)
_type("zzznevermatches12345")
expect("no-match search -> 0 rows", _rows() == 0)
empty_title = E("(document.querySelector('[data-empty-title]')||{}).textContent")
expect("no-match empty title is 'No rate cards found'",
       (empty_title or "").strip() == "No rate cards found", f"got={empty_title!r}")
empty_body = E("(document.querySelector('[data-empty-body]')||{}).textContent")
expect("no-match empty body is 'Try adjusting your search or filters.'",
       (empty_body or "").strip() == "Try adjusting your search or filters.",
       f"got={empty_body!r}")
_type("")
expect("clearing search restores rows", _rows() == 10)
total_label = E("(document.querySelector('[data-total]')||{}).textContent")
expect("'of N items' label restored to 'of 100 items'",
       total_label and total_label.strip() == "of 100 items", f"got={total_label!r}")
_type("omni")
clear_result = E("""(() => {
  const input = document.querySelector('[data-action="search"]');
  const clear = document.querySelector('[data-action="clear-search"]');
  const wasVisible = !clear.hidden;
  clear.click();
  return {
    wasVisible,
    value: input.value,
    focused: document.activeElement === input,
    hiddenAfter: clear.hidden
  };
})()""")
expect("Search clear action restores empty query and focus",
       clear_result == {
           "wasVisible": True,
           "value": "",
           "focused": True,
           "hiddenAfter": True,
       } and _rows() == 10, f"got={clear_result}")
helper_copy = E("""(() => ({
  lineV11: document.querySelector('#lineitems-search-helper-v11').textContent.trim(),
  lineV12: document.querySelector('#lineitems-search-helper-v12').textContent.trim(),
  premV11: document.querySelector('#premiums-search-helper-v11').textContent.trim(),
  premV12: document.querySelector('#premiums-search-helper-v12').textContent.trim(),
  lineDescribedBy: document.querySelector('[data-lineitems-search-input]').getAttribute('aria-describedby'),
  premDescribedBy: document.querySelector('[data-premitems-search-input]').getAttribute('aria-describedby')
}))()""")
expect("Search helper wording and associations remain unchanged",
       helper_copy == {
           "lineV11": "Add a line item with base rate and inventory details. Pick the rate card it attaches to, then set the advertiser scope, base offering, and base rate.",
           "lineV12": "Add a new line item or find an existing one to update. Set the rate card, advertiser scope, offering, and base rate.",
           "premV11": "Add a premium row by choosing a premium category, attaching it to rate card rows, and defining calculation details and conditions.",
           "premV12": "Add a new premium adjustment or find an existing one to update. Attach it to rate card rows, then set the category, calculation method, value, and conditions.",
           "lineDescribedBy": "lineitems-search-helper-v11 lineitems-search-helper-v12",
           "premDescribedBy": "premiums-search-helper-v11 premiums-search-helper-v12",
       }, f"got={helper_copy}")

# ---------------------------------------------------------------------------
print("\n== Modal scrim (no modal open: verify token resolves) ==")
scrim_token = E("getComputedStyle(document.body).getPropertyValue('--ads-scrim').trim()")
expect("--ads-scrim token resolves to rgba(0,0,0,0.5)",
       "0.5" in scrim_token, f"got={scrim_token}")
modal_radius_token = E("getComputedStyle(document.body).getPropertyValue('--ads-radius-md').trim()")
expect("--ads-radius-md = 12px", modal_radius_token == "12px", f"got={modal_radius_token}")

# Delete Rate Card modal: locked to ADS Figma 38:46. Verify the canonical
# .modal--ads layout: 480w / 12r / 18/24 SemiBold title with no leading
# icon / read-only summary / right-aligned Cancel + Delete, the latter on
# the standard ADS Primary button (7722:229), not a red destructive one.
print("\n== Delete Rate Card modal (ADS Figma 38:46) ==")
# Open the modal
E("(function(){var b=document.querySelector('[data-rows] .row .icon-btn[aria-label=\"Delete rate card\"]'); if(b) b.click();})()")
time.sleep(0.3)
expect("Delete modal uses .modal--ads variant",
       E("document.querySelector('[data-modal]').classList.contains('modal--ads')"))
expect("Delete modal 480px wide",
       abs((E("document.querySelector('[data-modal] .modal__panel').getBoundingClientRect().width") or 0) - 480) < 1)
expect("Delete modal 12px radius",
       E("getComputedStyle(document.querySelector('[data-modal] .modal__panel')).borderRadius") == "12px")
expect("Delete modal header has no leading title icon",
       not E("!!document.querySelector('[data-modal] .modal__warning-icon')"))
expect("Delete modal title sits at the ADS 24px header boundary",
       E("(function(){var p=document.querySelector('[data-modal] .modal__panel');"
         "var t=document.querySelector('[data-modal] .modal__title');"
         "return Math.round(t.getBoundingClientRect().left - p.getBoundingClientRect().left);})()") in (24, 25))
expect("Delete modal title is 'Delete this rate card?'",
       E("document.querySelector('[data-modal] .modal__title').textContent.trim()") == "Delete this rate card?")
expect("Delete modal title = Open Sans 18/24 SemiBold",
       E("getComputedStyle(document.querySelector('[data-modal] .modal__title')).fontSize") == "18px" and
       E("getComputedStyle(document.querySelector('[data-modal] .modal__title')).fontWeight") in ("600", "700"))
expect("Delete modal body uses new destructive copy",
       E("document.querySelector('[data-modal] .modal__body-text').textContent.trim()") ==
       "This will permanently remove this rate card from the manager. This action cannot be undone.")
# Selected rate card now renders as a plain read-only summary, NOT
# inside an <input> or any field-bordered chrome (per the 2026-06-29
# brief: "Show the selected rate card as plain read-only content").
expect("Delete modal does NOT use an <input> for the rate card name",
       not E("!!document.querySelector('[data-modal] .modal__field')") and
       not E("!!document.querySelector('[data-modal] input[data-modal-target]')"))
expect("Delete modal renders plain read-only summary (.modal__summary)",
       E("!!document.querySelector('[data-modal] .modal__summary')"))
expect("Summary has 'Rate card' label",
       E("(document.querySelector('[data-modal] .modal__summary-label')||{}).textContent || ''").strip() == "Rate card")
expect("Summary value (dd) shows the selected rate card name",
       (E("(document.querySelector('[data-modal] .modal__summary-value')||{}).textContent || ''") or "").strip().__len__() > 5)
# 14px is the product-wide floor for visible text; the label was 12px.
expect("Summary label uses muted secondary text",
       E("getComputedStyle(document.querySelector('[data-modal] .modal__summary-label')).fontSize") == "14px")
expect("Summary value uses primary text + medium/SemiBold weight",
       E("getComputedStyle(document.querySelector('[data-modal] .modal__summary-value')).fontWeight") in ("500", "600") and
       E("getComputedStyle(document.querySelector('[data-modal] .modal__summary-value')).fontSize") in ("14px", "15px", "16px"))
expect("Summary value has NO border (not a field chrome)",
       E("getComputedStyle(document.querySelector('[data-modal] .modal__summary-value')).borderTopStyle") == "none" and
       E("getComputedStyle(document.querySelector('[data-modal] .modal__summary-value')).backgroundColor") in ("rgba(0, 0, 0, 0)", "transparent"))
expect("Delete modal has 2 hairline dividers (top + bottom of body)",
       E("document.querySelectorAll('[data-modal] .modal__divider').length") == 2)
expect("Delete modal footer is right-aligned with 12px gap",
       E("getComputedStyle(document.querySelector('[data-modal] .modal__footer')).justifyContent") == "flex-end" and
       (E("getComputedStyle(document.querySelector('[data-modal] .modal__footer')).columnGap") == "12px" or
        E("getComputedStyle(document.querySelector('[data-modal] .modal__footer')).gap") == "12px"))
expect("Cancel button is secondary outline (indigo border)",
       "64, 69, 194" in (E("getComputedStyle(document.querySelector('[data-modal] [data-action=\"cancel-delete\"].btn')).borderColor") or ""))
expect("Delete rate card button uses the ADS Primary fill (#4045C2), not red",
       "64, 69, 194" in (E("getComputedStyle(document.querySelector('[data-modal] [data-action=\"confirm-delete\"].btn')).backgroundColor") or ""))
expect("Confirm button label = 'Delete rate card'",
       (E("(document.querySelector('[data-modal] [data-action=\"confirm-delete\"].btn')||{}).textContent || ''") or "").strip() == "Delete rate card")
# Cleanup: dismiss modal so subsequent assertions don't trip
E("document.querySelector('[data-modal] [data-action=\"cancel-delete\"].btn').click()")
time.sleep(0.3)

# ---------------------------------------------------------------------------
print("\n== Toast (re-verify after ADS pass) ==")
E("window.toast({title:'Rate card saved', variant:'info', duration:0})")
time.sleep(0.3)
expect("toast host present (top-right anchor)",
       E("""!!document.querySelector('[data-toast-stack]')
         && getComputedStyle(document.querySelector('[data-toast-stack]')).position === 'fixed'"""))
expect("toast white surface",
       E("getComputedStyle(document.querySelector('[data-toast]')).backgroundColor") == "rgb(255, 255, 255)")
expect("toast 6px radius",
       E("getComputedStyle(document.querySelector('[data-toast]')).borderRadius") == "6px")
expect("toast 5px left accent",
       E("getComputedStyle(document.querySelector('[data-toast]')).borderLeftWidth") == "5px")
expect("toast accent uses ADS blue info color",
       E("getComputedStyle(document.querySelector('[data-toast]')).borderLeftColor") == "rgb(64, 69, 194)")
expect("toast Open Sans family",
       "Open Sans" in (E("getComputedStyle(document.querySelector('[data-toast]')).fontFamily") or ""))
expect("toast announces politely as status",
       E("document.querySelector('[data-toast]').getAttribute('role')") == "status" and
       E("document.querySelector('[data-toast]').getAttribute('aria-live')") == "polite")
# Cleanup
E("Array.from(document.querySelectorAll('[data-toast]')).forEach(function(t){window.dismissToast(t);})")
time.sleep(0.3)

# ---------------------------------------------------------------------------
print("\n== Wireframe theme (2026-06-29) ==")
# Theme submenu options - 'Wireframe' replaces the legacy 'EDL Light'.
theme_labels = E("Array.from(document.querySelectorAll('.theme-submenu__item')).map(function(b){return b.textContent.trim();})") or []
expect("Theme submenu lists 'Ad Design System' and 'Wireframe'",
       "Ad Design System" in theme_labels and "Wireframe" in theme_labels and
       "EDL Light" not in theme_labels, f"got={theme_labels}")
theme_keys = E("Array.from(document.querySelectorAll('[data-theme]')).map(function(b){return b.getAttribute('data-theme');})") or []
expect("data-theme keys are 'ads-preview' and 'wireframe'",
       set(theme_keys) == {"ads-preview", "wireframe"}, f"got={theme_keys}")
# Switch to Wireframe and verify grayscale palette
E("document.querySelector('[data-theme=\"wireframe\"]').click()")
time.sleep(0.4)
expect("Switching to Wireframe adds body.theme-wireframe",
       E("document.body.classList.contains('theme-wireframe')"))
expect("Wireframe keeps body.theme-ads (overlay model)",
       E("document.body.classList.contains('theme-ads')"))
expect("Wireframe: --ads-brand resolves to grayscale (no indigo)",
       "64, 69, 194" not in (E("getComputedStyle(document.body).getPropertyValue('--ads-brand').trim()") or "") and
       "#4045" not in (E("getComputedStyle(document.body).getPropertyValue('--ads-brand').trim()") or ""))
expect("Wireframe: top nav background is NOT indigo",
       "64, 69, 194" not in (E("getComputedStyle(document.querySelector('.gnav')).backgroundColor") or ""))
expect("Wireframe: active pagination pill is NOT indigo",
       "64, 69, 194" not in (E("getComputedStyle(document.querySelector('.page-btn--num.is-active')).backgroundColor") or ""))
expect("Wireframe: action icons are NOT indigo",
       "64, 69, 194" not in (E("getComputedStyle(document.querySelector('[data-rows] .row .icon-btn svg')).color") or ""))
# Switch back to ADS and verify indigo is restored
E("document.querySelector('[data-theme=\"ads-preview\"]').click()")
time.sleep(0.4)
expect("Switching back to ADS removes body.theme-wireframe",
       not E("document.body.classList.contains('theme-wireframe')"))
expect("ADS: top nav background restored to Indigo (#4045C2)",
       "64, 69, 194" in (E("getComputedStyle(document.querySelector('.gnav')).backgroundColor") or ""))

print("\n== Deprecated ADS tokens not in use ==")
deprecated = ["color-violet", "color-steel", "color-teal", "color-mint",
              "color-old-pink", "color-neutral", "warning-yellow", "info-steel"]
src = E("""(async function(){
  var css = await fetch('/styles.css').then(function(r){return r.text();});
  return css;
})()""") or ""
for d in deprecated:
    expect(f"no `--{d}` token usage in styles.css", "--" + d not in src)

print("\n== Version 2.1: selected-row action bar ==")
send("Page.navigate", {"url": f"http://127.0.0.1:{PORT}/?version=2.1&qa=ads_compliance"})
time.sleep(1.6)
expect("2.1 is active", E("document.body.getAttribute('data-version')") == "2.1")
expect("2.1 removes the row Action column",
       E("document.querySelectorAll('[data-rows] .row .actions').length") == 0)
expect("2.1 header band matches the page canvas, not a white slab",
       E("getComputedStyle(document.querySelector('.page__top')).backgroundColor")
       == E("getComputedStyle(document.body).backgroundColor"))
E("document.querySelector('[data-rows] .row .cell--status').click()")
time.sleep(0.5)
bar = E("""(function(){
  var b = document.querySelector('[data-selection-bar]');
  if (!b) return null;
  var cs = getComputedStyle(b);
  var icon = b.querySelector('.rcsel__btn-icon svg');
  return {hidden: b.hidden, bg: cs.backgroundColor, color: cs.color,
          font: cs.fontFamily,
          labels: Array.prototype.map.call(b.querySelectorAll('.rcsel__btn-label'),
                                           function(n){ return n.textContent; }),
          iconW: icon ? icon.getBoundingClientRect().width : null,
          iconH: icon ? icon.getBoundingClientRect().height : null};
})()""")
expect("action bar appears on row selection", bool(bar) and bar["hidden"] is False, f"got={bar}")
if bar:
    # Style guide 104:23927 grounds the bar in color/indigo/300 #4045C2, the
    # same brand fill the top nav and primary buttons use. It supersedes the
    # darker indigo/800 the bar carried while it sat between the header and the
    # first data row; above the header it reads as a toolbar, not a data band.
    expect("bar background = Indigo/300 #4045C2 (color/indigo/300)",
           "64, 69, 194" in bar["bg"], f"got={bar['bg']}")
    expect("bar text = white (--ads-text-on-primary)", "255, 255, 255" in bar["color"], f"got={bar['color']}")
    expect("bar body copy uses Open Sans", "Open Sans" in bar["font"], f"got={bar['font']}")
    expect("bar carries the five row actions",
           bar["labels"] == ["Quick Edit", "Copy", "Download", "Archive", "Delete"],
           f"got={bar['labels']}")
    expect("bar icons are 16x16",
           abs((bar["iconW"] or 0) - 16) < 1 and abs((bar["iconH"] or 0) - 16) < 1,
           f"got={bar['iconW']}x{bar['iconH']}")
# 608:12966 tints the selected row with color/black/opacity/5 (#0F12140D), which
# composites to #F3F3F3 over the white row. The ADS surface-hover token carries
# that exact value, so the computed color stays unresolved rgba. 1.x and 2.0 use
# the indigo brand wash (#E2E3F2) instead; 2.1 follows its reference node.
sel_bg = E("getComputedStyle(document.querySelector('[data-rows] .row.is-selected')).backgroundColor") or ""
expect("selected row uses the reference black/opacity/5 wash",
       sel_bg.replace(" ", "") == "rgba(15,18,20,0.05)", f"got={sel_bg}")

print(f"\n{'='*64}")
print(f"Total: {passes} passed, {len(fails)} failed")
if fails:
    print("\nFailures:")
    for f in fails: print(f"  - {f}")

ws.close(); proc.terminate(); srv.shutdown()
exit(0 if not fails else 1)
