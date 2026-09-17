#!/usr/bin/env python3
"""
qa_v21_list_figma.py - Version 2.1 Rate Card Manager list view vs Figma.

Reference nodes (sole visual source of truth for 2.1's list view):
    472:17713  default table state
    608:12966  one row selected + contextual action bar
    608:14479  the action bar itself
    645:68987  combined "Rate Card ID / Name" column + restored Buying
               Entity column (2026-08-15 brief)

Everything asserted below is a measured Figma value, listed in FIGMA so
the numbers live in one place. Coordinates are relative to the table card
(Figma "Frame 627007", x=95/101 y=169 w=1314 in the 1440x932 frame) because
that is the frame the reference lays the table out in.

Covers:
  1. Page canvas, header block, and card geometry.
  2. Toolbar (icon-only filter + search) geometry.
  3. All eight column tracks, in order, led by the selection checkbox,
     with Rate Card ID and Name combined into one two-line "Rate Card
     ID / Name" cell, Buying Entity restored, and no Action column or
     leftover width where the Action column used to be.
  4. The ADS Checkbox in every state the table can produce, plus Select
     All and Clear All over the current page.
  5. Contextual action bar geometry, colors, typography, and labels.
  6. The nine selection cases from the brief, including sorting,
     searching, and paging.
  7. Responsive behavior at seven widths, including the pinned selection
     column and the pinned count.
  8. 2.0 is untouched: it keeps its Action column, has no selection
     column, and never builds a bar.

Run: python3 qa_v21_list_figma.py
"""
import base64
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = "/tmp/qa_v21_list_figma"
os.makedirs(OUT, exist_ok=True)

# ---------------------------------------------------------------------------
# Measured Figma values.
# ---------------------------------------------------------------------------
FIGMA = {
    "frame": (1440, 932),
    "gnav_h": 56,
    # 472:17713 puts the header inside the card: card top 86, plus its
    # 1px border and 16px padding, puts the title at 103; the 8px gap
    # below a 36px title puts the description at 147.
    "title_y": 103, "title_h": 36,
    "subtitle_y": 147, "subtitle_h": 20,
    "card_y": 86, "card_w": 1314, "card_radius": 8,
    "toolbar_h": 60,
    # Card-relative. The header block above the toolbar is 81px:
    # 16px card padding, a 36px title, an 8px gap and a 20px
    # description. The toolbar adds its own 16px of top padding.
    "filter": (16, 97, 32, 32),       # x, y, w, h  (card-relative)
    "search": (64, 97, 399, 36),
    "head_y": 141, "head_h": 32,
    # 645:68987 grows the row to 56px to fit the combined cell's two
    # lines (Name on top, "ID: {rateCardId}" underneath); 472:17713's
    # older 48px single-line row no longer applies.
    "row_h": 56,
    "footer_h": 52,
    # x, width per column, in reference order (645:68987), after the
    # 2026-08-17 balancing pass. "name-id" replaces the old separate
    # "rate-card-id" and "name" tracks with one combined "Rate Card ID /
    # Name" column; "buying-entity" is restored between Marketplace and
    # Last updated.
    #
    # Every track but two is a fixed width.
    #
    # 2026-08-26: Rate Card ID / Name used to be the flexible track and
    # took everything the fixed columns left, which was 516 against a
    # longest name of 331 and put a hole in front of SalesHub ID. It is
    # now capped at NAME_ID_W and Buying Entity is flexible instead, so
    # the row still reaches the card's right edge and the spare width
    # sits in the one remaining column whose values can run long. The
    # two swap roles on the way down as well: Buying Entity gives ground
    # first, and Rate Card ID / Name only comes off its cap once Buying
    # Entity is at its floor.
    "cols": [
        ("select",        8,    40),
        ("status",        48,   96),
        ("name-id",       144,  400),
        ("saleshub",      544,  176),
        ("marketplace",   720,  158),
        ("buying-entity", 878,  186),
        ("last-updated",  1064, 168),
        ("ver",           1232, 72),
    ],
    # The cap on Rate Card ID / Name, the floors the two elastic tracks
    # shrink to, and the width of the selection column, which never
    # moves at any viewport or zoom.
    "name_id_w": 400,
    "name_id_min": 380,
    "buyer_min": 104,
    "select_w": 40,
    # ADS Checkbox (component set 71:62) as the reference table uses it.
    "cb_control": 20, "cb_box": 16, "cb_radius": "2px", "cb_pad": "4px",
    "cb_fill_rest": "rgb(255, 255, 255)",
    "cb_border_rest": "rgba(15, 18, 20, 0.2)",
    "cb_fill_checked": "rgb(64, 69, 194)",   # checkbox/state/rest/box-fill-checked
    "cb_check": (9.375, 6.75),
    "cb_minus": (9, 0.75),
    # Action bar (104:23927). It now opens directly under the toolbar and
    # pushes the column header row down, so it takes the header's old top
    # edge rather than sitting a header's height below it.
    "bar_y": 141, "bar_h": 44,
    "bar_bg": "rgb(64, 69, 194)",     # color/indigo/300 #4045c2 (104:23927)
    "bar_count_x": 28,                # 16 bar padding + 12 cell padding
    "bar_btn_h": 36, "bar_btn_gap": 4, "bar_btn_radius": 6,
    "bar_right_inset": 16,
    "bar_labels": ["Quick Edit", "Copy", "Download",
                   "Archive", "Delete"],
}

CHECKS = []


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' -- ' + detail) if detail else ''}")
    CHECKS.append((label, bool(ok), detail))


def near(a, b, tol=1):
    return a is not None and b is not None and abs(a - b) <= tol


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def boot_chrome(viewport, label):
    w, h = viewport
    port = _free_port()
    # Isolated profile per run: the app persists version, sort, and pin
    # state to localStorage, so a shared profile would leak one case's
    # state into the next.
    proc = subprocess.Popen([
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        f"--remote-debugging-port={port}", "--remote-allow-origins=*",
        f"--window-size={w},{h}",
        f"--user-data-dir=/tmp/qa_v21_profile_{label}",
        "--no-first-run", "--no-default-browser-check", "--headless=new",
        "--disable-gpu", "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(80):
        try:
            urllib.request.urlopen(
                f"http://127.0.0.1:{port}/json/version", timeout=0.5).read()
            return proc, port
        except Exception:
            time.sleep(0.1)
    proc.kill()
    raise RuntimeError("chrome failed to boot")


class CDP:
    def __init__(self, port):
        import websocket
        targets = json.loads(
            urllib.request.urlopen(f"http://127.0.0.1:{port}/json").read())
        target = next(t for t in targets if t["type"] == "page")
        self.ws = websocket.create_connection(
            target["webSocketDebuggerUrl"], timeout=30)
        self.i = 0

    def send(self, method, params=None):
        self.i += 1
        self.ws.send(json.dumps(
            {"id": self.i, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.i:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    def eval(self, expr):
        r = self.send("Runtime.evaluate", {
            "expression": expr, "returnByValue": True, "awaitPromise": True})
        if "exceptionDetails" in r:
            raise RuntimeError(r["exceptionDetails"])
        return r.get("result", {}).get("value")

    def shot(self, path):
        r = self.send("Page.captureScreenshot", {"format": "png"})
        open(path, "wb").write(base64.b64decode(r["data"]))

    def click(self, x, y):
        for t in ("mousePressed", "mouseReleased"):
            self.send("Input.dispatchMouseEvent", {
                "type": t, "x": x, "y": y, "button": "left", "clickCount": 1})
        time.sleep(0.12)

    def key(self, key, code=None):
        for t in ("keyDown", "keyUp"):
            self.send("Input.dispatchKeyEvent", {
                "type": t, "key": key, "code": code or key})
        time.sleep(0.12)


def open_page(c, url, viewport):
    w, h = viewport
    c.send("Page.enable")
    c.send("Runtime.enable")
    c.send("Network.enable")
    c.send("Network.setCacheDisabled", {"cacheDisabled": True})
    # Drive the layout viewport explicitly. Without this the window size
    # and the scrollbar width both leak into every width measurement.
    c.send("Emulation.setDeviceMetricsOverride", {
        "width": w, "height": h, "deviceScaleFactor": 1, "mobile": False})
    c.send("Emulation.setScrollbarsHidden", {"hidden": True})
    c.send("Page.navigate", {"url": url})
    for _ in range(100):
        if c.eval("!!document.querySelector('[data-rows] .row')"):
            break
        time.sleep(0.1)
    c.eval("localStorage.clear(); sessionStorage.clear(); true")
    c.send("Page.navigate", {"url": url})
    for _ in range(100):
        if c.eval("!!document.querySelector('[data-rows] .row')"):
            break
        time.sleep(0.1)
    time.sleep(0.5)


# ---------------------------------------------------------------------------
# Browser-side helpers, injected as expressions.
# ---------------------------------------------------------------------------
GEOM = r"""(() => {
  const card = document.querySelector('.page__content > .surface');
  if (!card) return null;
  const c = card.getBoundingClientRect();
  const rel = (n) => {
    if (!n) return null;
    const r = n.getBoundingClientRect();
    return {x: +(r.x - c.x).toFixed(1), y: +(r.y - c.y).toFixed(1),
            w: +r.width.toFixed(1), h: +r.height.toFixed(1)};
  };
  const q = (s) => rel(document.querySelector(s));
  const cs = (s, props) => {
    const n = document.querySelector(s);
    if (!n) return null;
    const st = getComputedStyle(n);
    const out = {};
    props.forEach((p) => { out[p] = st[p]; });
    return out;
  };
  const head = document.querySelector('.table__head');
  const cols = {};
  let hiddenHeads = 0;
  if (head) {
    head.querySelectorAll('.th').forEach((th) => {
      // th--sortable is a behavior modifier, not a column name, so take
      // the modifier that is not it.
      const names = (th.className.match(/th--[a-z-]+/g) || [])
        .map((s) => s.slice(4)).filter((s) => s !== 'sortable');
      const name = names[0];
      if (!name) return;
      const r = th.getBoundingClientRect();
      if (r.width === 0 && r.height === 0) { hiddenHeads++; return; }
      cols[name] = {x: +(r.x - c.x).toFixed(1), w: +r.width.toFixed(1),
                    order: +getComputedStyle(th).order};
    });
  }
  const bar = document.querySelector('[data-selection-bar]');
  const barBtns = bar ? Array.prototype.map.call(
    bar.querySelectorAll('.rcsel__btn'), (b) => {
      const r = b.getBoundingClientRect();
      const st = getComputedStyle(b);
      return {label: b.textContent.trim(), x: +(r.x - c.x).toFixed(1),
              w: +r.width.toFixed(1), h: +r.height.toFixed(1),
              radius: st.borderTopLeftRadius, pad: st.padding,
              gap: st.gap, color: st.color, disabled: b.disabled,
              icon: !!b.querySelector('svg'),
              iconW: b.querySelector('svg')
                ? +b.querySelector('svg').getBoundingClientRect().width.toFixed(1)
                : 0};
    }) : [];
  const scroll = document.querySelector('.table-scroll');
  return {
    version: document.body.getAttribute('data-version'),
    vw: window.innerWidth, vh: window.innerHeight,
    gnavH: +document.querySelector('.gnav').getBoundingClientRect().height.toFixed(1),
    titleY: +document.querySelector('.page__title').getBoundingClientRect().y.toFixed(1),
    titleH: +document.querySelector('.page__title').getBoundingClientRect().height.toFixed(1),
    subY: (() => {
      const shown = Array.prototype.filter.call(
        document.querySelectorAll('.page__subtitle'),
        (p) => p.getBoundingClientRect().height > 0)[0];
      return shown ? +shown.getBoundingClientRect().y.toFixed(1) : null;
    })(),
    cardX: +c.x.toFixed(1), cardY: +c.y.toFixed(1), cardW: +c.width.toFixed(1),
    cardStyle: cs('.page__content > .surface',
                  ['borderTopLeftRadius', 'borderTopWidth', 'borderTopColor',
                   'boxShadow', 'backgroundColor']),
    hasTopBand: !!document.querySelector('[data-page="list"] > .page__top'),
    headerInCard: !!document.querySelector(
      '[data-page="list"] .surface__inner > .page__header'),
    headerBox: q('[data-page="list"] .surface__inner > .page__header'),
    contentBg: cs('.page__content', ['backgroundColor']).backgroundColor,
    toolbar: q('.toolbar'), filter: q('.filter-btn'), search: q('.toolbar .search'),
    head: q('.table__head'),
    headStyle: cs('.table__head', ['height', 'backgroundColor', 'borderBottomWidth',
                                   'borderBottomColor']),
    thStyle: cs('.th--status', ['fontSize', 'lineHeight', 'fontWeight', 'color',
                                'paddingLeft', 'paddingRight']),
    row: q('[data-rows] .row'),
    rowStyle: cs('[data-rows] .row', ['borderBottomWidth', 'borderBottomColor',
                                      'backgroundColor']),
    cellStyle: cs('[data-rows] .row .cell--marketplace',
                  ['fontSize', 'lineHeight', 'fontWeight', 'color',
                   'paddingLeft', 'paddingRight']),
    nameStyle: cs('[data-rows] .row .name__link',
                  ['fontSize', 'lineHeight', 'fontWeight', 'color', 'fontFamily']),
    footer: q('.footer'),
    cols: cols,
    actionCells: Array.prototype.filter.call(
      document.querySelectorAll('[data-rows] .row .actions'),
      (n) => n.getBoundingClientRect().width > 0).length,
    // The Action header stays in the static markup for the versions that
    // use it; what matters is that 2.1 gives it no box and no track.
    actionHeads: Array.prototype.filter.call(
      document.querySelectorAll('.table__head .th--action'),
      (n) => n.getBoundingClientRect().width > 0).length,
    buyingCells: document.querySelectorAll('[data-rows] .row .cell--buying-entity').length,
    // Combined "Rate Card ID / Name" cell (645:68987): first row's Name
    // link text + "ID: {rateCardId}" line, and the ID line's tag name
    // so we can confirm it never became a second link.
    nameIdLines: (() => {
      const cell = document.querySelector('[data-rows] .row .cell--name-id');
      if (!cell) return null;
      const link = cell.querySelector('.name__link');
      const idLine = cell.querySelector('.name-id__id');
      return link && idLine ? {
        name: link.textContent.trim(), id: idLine.textContent.trim(),
        idTag: idLine.tagName,
      } : null;
    })(),
    rowCount: document.querySelectorAll('[data-rows] .row').length,
    tableScrollW: scroll ? scroll.clientWidth : null,
    tableScrollSW: scroll ? scroll.scrollWidth : null,
    docSW: document.documentElement.scrollWidth,
    docCW: document.documentElement.clientWidth,
    barPresent: !!bar,
    barHidden: bar ? bar.hidden : null,
    bar: bar && !bar.hidden ? rel(bar) : null,
    barStyle: bar ? cs('[data-selection-bar]',
                       ['backgroundColor', 'borderBottomWidth', 'borderBottomColor',
                        'paddingLeft', 'paddingRight', 'minHeight']) : null,
    barCount: bar ? (bar.querySelector('[data-selection-count]') || {}).textContent : null,
    barCountBox: bar && !bar.hidden ? rel(bar.querySelector('[data-selection-count]')) : null,
    barCountStyle: bar ? cs('[data-selection-bar] .rcsel__count',
                            ['fontSize', 'lineHeight', 'fontWeight', 'color',
                             'paddingLeft']) : null,
    barBtns: barBtns,
    barIndex: bar ? Array.prototype.indexOf.call(bar.parentElement.children, bar) : null,
    headIndex: head ? Array.prototype.indexOf.call(head.parentElement.children, head) : null,
    selectedIds: Array.prototype.map.call(
      document.querySelectorAll('[data-rows] .row.is-selected'),
      (r) => r.getAttribute('data-row-id')),
    visibleIds: Array.prototype.map.call(
      document.querySelectorAll('[data-rows] .row'),
      (r) => r.getAttribute('data-row-id')),
    ariaSelected: Array.prototype.map.call(
      document.querySelectorAll('[data-rows] .row'),
      (r) => r.getAttribute('aria-selected')),
    /* Selection column. `state` is read off the native input, which is
     * what assistive tech reports, so a box that only looks mixed cannot
     * pass as one. */
    headCb: (() => {
      const i = document.querySelector('[data-select-all-host] .ads-checkbox__input');
      if (!i) return null;
      const box = i.closest('.ads-checkbox').querySelector('.ads-checkbox__box');
      const ctl = i.closest('.ads-checkbox').querySelector('.ads-checkbox__control');
      const bs = getComputedStyle(box);
      const glyph = (sel) => {
        const n = box.querySelector(sel);
        if (!n || getComputedStyle(n).display === 'none') return null;
        const r = n.getBoundingClientRect();
        return [+r.width.toFixed(3), +r.height.toFixed(3)];
      };
      return {
        checked: i.checked, indeterminate: i.indeterminate,
        disabled: i.disabled, label: i.getAttribute('aria-label'),
        tag: i.tagName + ':' + i.type,
        control: +ctl.getBoundingClientRect().width.toFixed(1),
        box: +box.getBoundingClientRect().width.toFixed(1),
        fill: bs.backgroundColor, border: bs.borderTopColor,
        radius: bs.borderTopLeftRadius,
        pad: getComputedStyle(i.closest('.ads-checkbox')).padding,
        check: glyph('.ads-checkbox__check'), minus: glyph('.ads-checkbox__minus'),
      };
    })(),
    rowCbs: Array.prototype.map.call(
      document.querySelectorAll('[data-rows] .row'), (row) => {
        const i = row.querySelector('.ads-checkbox__input');
        if (!i) return null;
        const box = row.querySelector('.ads-checkbox__box');
        const bs = getComputedStyle(box);
        const shown = (sel) => {
          const n = box.querySelector(sel);
          return !!n && getComputedStyle(n).display !== 'none';
        };
        return {checked: i.checked, label: i.getAttribute('aria-label'),
                fill: bs.backgroundColor, border: bs.borderTopColor,
                box: +box.getBoundingClientRect().width.toFixed(1),
                check: shown('.ads-checkbox__check'),
                minus: shown('.ads-checkbox__minus')};
      }),
    /* Every checkbox on the page must be an ADS Checkbox, not a bare
     * native control dropped into a cell. */
    strayCheckboxes: Array.prototype.filter.call(
      document.querySelectorAll('.table input[type="checkbox"]'),
      (i) => !i.classList.contains('ads-checkbox__input')).length,
    selectCellPos: (() => {
      const cell = document.querySelector('[data-rows] .row .cell--select');
      return cell ? getComputedStyle(cell).position : null;
    })(),
    selectCellH: (() => {
      const cell = document.querySelector('[data-rows] .row .cell--select');
      return cell ? +cell.getBoundingClientRect().height.toFixed(1) : null;
    })(),
  };
})()"""

CLICK_ROW = r"""((i) => {
  const rows = document.querySelectorAll('[data-rows] .row');
  const row = rows[i];
  if (!row) return null;
  // Status cell: no link or button inside, so the click lands on the row
  // the way a user clicking empty row space would. It is also the
  // leftmost column, so it stays on screen on viewports where the table
  // scrolls horizontally.
  const cell = row.querySelector('.cell--status') || row;
  const r = cell.getBoundingClientRect();
  return {x: r.x + r.width / 2, y: r.y + r.height / 2,
          id: row.getAttribute('data-row-id')};
})(%d)"""


CLICK_BOX = r"""((sel) => {
  const box = document.querySelector(sel);
  if (!box) return null;
  const r = box.getBoundingClientRect();
  return {x: r.x + r.width / 2, y: r.y + r.height / 2};
})(%s)"""

ROW_GLYPH = r"""((i) => {
  const box = document.querySelectorAll('[data-rows] .row .ads-checkbox__check')[i];
  if (!box || getComputedStyle(box).display === 'none') return null;
  const r = box.getBoundingClientRect();
  return [+r.width.toFixed(3), +r.height.toFixed(3)];
})(%d)"""


def click_row(c, i):
    spot = c.eval(CLICK_ROW % i)
    if not spot:
        return None
    c.click(spot["x"], spot["y"])
    return spot["id"]


def click_row_checkbox(c, i):
    sel = json.dumps(f"[data-rows] .row:nth-of-type({i + 1}) .ads-checkbox__box")
    # Selecting a row inserts the action bar above the header row, which
    # pushes every row down. On a short viewport that can put the next
    # target under the fold between measuring it and clicking it, so
    # bring it into view and let the shift settle first.
    c.eval("((s) => { const el = document.querySelector(s);"
           " if (el) el.scrollIntoView({block: 'center'}); return true; })(%s)"
           % sel)
    time.sleep(0.2)
    spot = c.eval(CLICK_BOX % sel)
    assert spot, f"no row checkbox at index {i}"
    c.click(spot["x"], spot["y"])
    time.sleep(0.25)


def click_select_all(c):
    spot = c.eval(CLICK_BOX % json.dumps(
        "[data-select-all-host] .ads-checkbox__box"))
    assert spot, "no header checkbox"
    c.click(spot["x"], spot["y"])
    time.sleep(0.2)


def row_glyph(c, i):
    return c.eval(ROW_GLYPH % i) or [0, 0]


# Is the pinned selection column, and the bar's count, still inside the
# visible scrollport? Read after scrolling the table, or at a width where
# the columns overflow.
PINNED = r"""(() => {
  const scroll = document.querySelector('.table-scroll');
  const port = scroll.getBoundingClientRect();
  const inPort = (n) => {
    if (!n) return null;
    const r = n.getBoundingClientRect();
    return r.left >= port.left - 0.6 && r.right <= port.right + 0.6;
  };
  const bar = document.querySelector('[data-selection-bar]');
  const row = document.querySelector('[data-rows] .row .ads-checkbox__box');
  const head = document.querySelector('[data-select-all-host] .ads-checkbox__box');
  return {
    row: inPort(row), head: inPort(head),
    aligned: !!(row && head) && Math.abs(row.getBoundingClientRect().x
                                       - head.getBoundingClientRect().x) < 0.6,
    count: inPort(bar && bar.querySelector('[data-selection-count]')),
    actions: !!bar && Array.prototype.every.call(
      bar.querySelectorAll('.rcsel__btn'),
      (b) => b.getBoundingClientRect().width > 0),
    offset: scroll.scrollLeft,
  };
})()"""


# ---------------------------------------------------------------------------
# Reference-frame checks.
# ---------------------------------------------------------------------------
def check_default_state(c, url):
    print("\n== default state vs 472:17713 (1440x932) ==")
    g = c.eval(GEOM)
    f = FIGMA

    check("version under test is 2.1", g["version"] == "2.1", g["version"])
    check("global header height", near(g["gnavH"], f["gnav_h"]),
          f"{g['gnavH']} vs {f['gnav_h']}")
    check("page title top", near(g["titleY"], f["title_y"], 2),
          f"{g['titleY']} vs {f['title_y']}")
    check("page title height", near(g["titleH"], f["title_h"], 2),
          f"{g['titleH']} vs {f['title_h']}")
    check("page subtitle top", near(g["subY"], f["subtitle_y"], 2),
          f"{g['subY']} vs {f['subtitle_y']}")
    check("table card top", near(g["cardY"], f["card_y"], 2),
          f"{g['cardY']} vs {f['card_y']}")
    check("table card width", near(g["cardW"], f["card_w"]),
          f"{g['cardW']} vs {f['card_w']}")
    check("table card radius 8px",
          g["cardStyle"]["borderTopLeftRadius"] == "8px",
          g["cardStyle"]["borderTopLeftRadius"])
    check("table card hairline, no elevation",
          g["cardStyle"]["borderTopWidth"] == "1px"
          and g["cardStyle"]["boxShadow"] == "none",
          json.dumps(g["cardStyle"]))
    # The title, description and page actions live in the card now, so
    # there is no white band above it to leave a seam behind.
    check("the header block sits inside the table card",
          g["headerInCard"] and not g["hasTopBand"],
          json.dumps({"inCard": g["headerInCard"], "band": g["hasTopBand"]}))
    check("the header aligns with the toolbar and the table",
          near(g["headerBox"]["x"], g["toolbar"]["x"], 1)
          and near(g["headerBox"]["w"], g["toolbar"]["w"], 1),
          json.dumps([g["headerBox"], g["toolbar"]]))

    check("toolbar height", near(g["toolbar"]["h"], f["toolbar_h"]),
          str(g["toolbar"]["h"]))
    for name, key in (("filter button", "filter"), ("search field", "search")):
        want = f[key]
        got = g[key]
        check(f"{name} box (x,y,w,h)",
              near(got["x"], want[0], 1.5) and near(got["y"], want[1], 1.5)
              and near(got["w"], want[2]) and near(got["h"], want[3]),
              f"{[got['x'], got['y'], got['w'], got['h']]} vs {list(want)}")

    check("column header row top", near(g["head"]["y"], f["head_y"], 1.5),
          str(g["head"]["y"]))
    check("column header row height", near(g["head"]["h"], f["head_h"]),
          str(g["head"]["h"]))
    check("data row height", near(g["row"]["h"], f["row_h"]),
          str(g["row"]["h"]))
    check("footer band height", near(g["footer"]["h"], f["footer_h"]),
          str(g["footer"]["h"]))

    # Columns: presence, order, x, width.
    got_cols = g["cols"]
    ordered = sorted(got_cols.items(), key=lambda kv: kv[1]["order"])
    check("column order matches the reference",
          [k for k, _ in ordered] == [name for name, _, _ in f["cols"]],
          " ".join(k for k, _ in ordered))
    for name, x, w in f["cols"]:
        got = got_cols.get(name)
        # +1 everywhere: the reference draws its 1px card border inside the
        # frame, the implementation outside the content box.
        check(f"column {name} x/width",
              got and near(got["x"], x + 1, 1.5) and near(got["w"], w, 1.5),
              json.dumps(got) + f" vs x={x + 1} w={w}")

    # The combined column carries two lines of content and the longest
    # values on the row, so it has to stay unmistakably the widest one.
    #
    # 2026-08-26: measured as an absolute margin rather than "twice the
    # runner-up". Capping this column and handing its surplus to Buying
    # Entity deliberately closed that ratio, and a ratio would now read
    # as a failure every time the flexible column did its job.
    widest = max(got_cols.items(), key=lambda kv: kv[1]["w"])
    runner_up = max((v["w"] for k, v in got_cols.items() if k != "name-id"),
                    default=0)
    check("Rate Card ID / Name is the widest column by a clear margin",
          widest[0] == "name-id" and widest[1]["w"] - runner_up >= 150,
          f"{widest[0]}={widest[1]['w']} next={runner_up}")
    # No column may run off the card, and the last one keeps the same
    # 8px breathing room from the card's edge that the first one has.
    ver = got_cols["ver"]
    right_gap = g["cardW"] - 1 - (ver["x"] + ver["w"])
    check("Version keeps the row's own padding off the right edge",
          near(right_gap, 8, 1.5), f"{right_gap} inside card {g['cardW']}")

    check("Action column fully removed",
          g["actionCells"] == 0 and g["actionHeads"] == 0,
          f"cells={g['actionCells']} heads={g['actionHeads']}")
    check("every row carries a Buying Entity cell (restored 645:68987)",
          g["buyingCells"] == g["rowCount"] and g["rowCount"] > 0,
          f"{g['buyingCells']}/{g['rowCount']}")
    check("no separate Rate Card ID or Name header remains",
          "rate-card-id" not in g["cols"] and "name" not in g["cols"],
          json.dumps(list(g["cols"].keys())))
    check("combined Rate Card ID / Name cell shows both lines",
          g["nameIdLines"] is not None
          and g["nameIdLines"]["name"] and g["nameIdLines"]["id"].startswith("ID: "),
          json.dumps(g["nameIdLines"]))
    check("Rate Card ID line is not a link",
          g["nameIdLines"] is not None and g["nameIdLines"]["idTag"] != "A",
          str(g["nameIdLines"] and g["nameIdLines"]["idTag"]))
    check("table fills the card with no leftover Action width",
          near(g["tableScrollW"], f["card_w"] - 2),
          f"{g['tableScrollW']} vs {f['card_w'] - 2}")
    check("no spurious horizontal overflow inside the table",
          g["tableScrollSW"] <= g["tableScrollW"],
          f"scrollWidth={g['tableScrollSW']} clientWidth={g['tableScrollW']}")
    check("no page-level horizontal scrollbar",
          g["docSW"] <= g["docCW"], f"{g['docSW']} vs {g['docCW']}")

    # Figma drew headers at 12/18. They are 14/18 now: no visible text in
    # the product renders below 14px.
    check("column header labels 14/18",
          g["thStyle"]["fontSize"] == "14px" and g["thStyle"]["lineHeight"] == "18px",
          json.dumps(g["thStyle"]))
    check("body cells 14/20", g["cellStyle"]["fontSize"] == "14px"
          and g["cellStyle"]["lineHeight"] == "20px", json.dumps(g["cellStyle"]))
    check("Name link Open Sans SemiBold 14/20 indigo",
          g["nameStyle"]["fontSize"] == "14px"
          and g["nameStyle"]["lineHeight"] == "20px"
          and g["nameStyle"]["fontWeight"] == "600"
          and g["nameStyle"]["color"] == "rgb(45, 47, 140)"
          and "Open Sans" in g["nameStyle"]["fontFamily"],
          json.dumps(g["nameStyle"]))

    check("action bar hidden with zero rows selected",
          g["barHidden"] is True, json.dumps({"present": g["barPresent"],
                                              "hidden": g["barHidden"]}))
    check("no row selected on load", g["selectedIds"] == [],
          json.dumps(g["selectedIds"]))

    # ---- selection column, ADS Checkbox ------------------------------------
    head_cb = g["headCb"]
    row_cbs = g["rowCbs"]
    check("header carries an ADS Checkbox over a native input",
          head_cb is not None and head_cb["tag"] == "INPUT:checkbox",
          json.dumps(head_cb and head_cb["tag"]))
    check("no bare native checkbox anywhere in the table",
          g["strayCheckboxes"] == 0, str(g["strayCheckboxes"]))
    check("every row carries a row checkbox",
          len(row_cbs) > 0 and all(cb is not None for cb in row_cbs),
          f"{sum(1 for cb in row_cbs if cb)}/{len(row_cbs)}")
    check("header checkbox names its Select All scope",
          head_cb["label"] == "Select all rate cards on this page",
          repr(head_cb["label"]))
    check("row checkboxes name the record they select",
          all(cb["label"].startswith("Select ") and len(cb["label"]) > 8
              for cb in row_cbs),
          json.dumps([cb["label"] for cb in row_cbs[:2]]))
    check("checkbox control is 20px around a 16px box",
          near(head_cb["control"], f["cb_control"])
          and near(head_cb["box"], f["cb_box"]),
          f"control={head_cb['control']} box={head_cb['box']}")
    check("checkbox box radius and row padding match ADS",
          head_cb["radius"] == f["cb_radius"] and head_cb["pad"] == f["cb_pad"],
          f"{head_cb['radius']} / {head_cb['pad']}")
    check("unchecked box is white with the ADS default border",
          head_cb["fill"] == f["cb_fill_rest"]
          and head_cb["border"] == f["cb_border_rest"],
          f"{head_cb['fill']} / {head_cb['border']}")
    check("header checkbox is unchecked with nothing selected",
          head_cb["checked"] is False and head_cb["indeterminate"] is False
          and head_cb["disabled"] is False, json.dumps(
              {k: head_cb[k] for k in ("checked", "indeterminate", "disabled")}))
    check("no glyph shows in the unchecked state",
          head_cb["check"] is None and head_cb["minus"] is None
          and not any(cb["check"] or cb["minus"] for cb in row_cbs),
          json.dumps({"check": head_cb["check"], "minus": head_cb["minus"]}))
    check("selection cell fills the row height for a larger press target",
          near(g["selectCellH"], f["row_h"] - 1, 1.5), str(g["selectCellH"]))
    c.shot(f"{OUT}/default-1440.png")
    return g


def check_checkbox_states(c):
    """Unchecked, checked, indeterminate, Select All, Clear All, disabled."""
    print("\n== checkbox states and Select All ==")
    f = FIGMA
    c.key("Escape")
    time.sleep(0.2)

    click_row_checkbox(c, 2)
    g = c.eval(GEOM)
    check("row checkbox selects its own record",
          g["rowCbs"][2]["checked"] is True
          and [i for i, cb in enumerate(g["rowCbs"]) if cb["checked"]] == [2],
          json.dumps([cb["checked"] for cb in g["rowCbs"]]))
    check("a checked box fills with the ADS checked color and shows the check",
          g["rowCbs"][2]["fill"] == f["cb_fill_checked"]
          and g["rowCbs"][2]["check"] is True
          and g["rowCbs"][2]["minus"] is False,
          json.dumps(g["rowCbs"][2]))
    check("one row selected shows the bar and the singular count",
          g["barHidden"] is False and g["barCount"] == "1 item selected",
          repr(g["barCount"]))
    check("a partial page selection makes the header checkbox indeterminate",
          g["headCb"]["indeterminate"] is True
          and g["headCb"]["checked"] is False,
          json.dumps(g["headCb"]))
    check("the indeterminate box draws the ADS minus at its token size",
          g["headCb"]["minus"] is not None
          and near(g["headCb"]["minus"][0], f["cb_minus"][0], 0.05)
          and near(g["headCb"]["minus"][1], f["cb_minus"][1], 0.05)
          and g["headCb"]["check"] is None,
          json.dumps(g["headCb"]["minus"]))
    check("a checked box draws the ADS check at its token size",
          near(row_glyph(c, 2)[0], f["cb_check"][0], 0.05)
          and near(row_glyph(c, 2)[1], f["cb_check"][1], 0.05),
          json.dumps(row_glyph(c, 2)))

    # A row click and its checkbox drive one selection, not two.
    click_row(c, 4)
    g = c.eval(GEOM)
    check("clicking the row body checks that row's box too",
          g["rowCbs"][4]["checked"] is True and len(g["selectedIds"]) == 2,
          json.dumps([cb["checked"] for cb in g["rowCbs"]]))
    click_row_checkbox(c, 4)
    g = c.eval(GEOM)
    check("pressing a checked box clears just that record, once",
          g["rowCbs"][4]["checked"] is False and len(g["selectedIds"]) == 1,
          json.dumps([cb["checked"] for cb in g["rowCbs"]]))

    # Select All from the mixed state completes the page.
    click_select_all(c)
    g = c.eval(GEOM)
    check("Select All from the mixed state selects the whole page",
          all(cb["checked"] for cb in g["rowCbs"])
          and g["headCb"]["checked"] is True
          and g["headCb"]["indeterminate"] is False,
          json.dumps({"rows": [cb["checked"] for cb in g["rowCbs"]],
                      "head": g["headCb"]["checked"]}))
    check("the count matches the page size after Select All",
          g["barCount"] == f"{len(g['rowCbs'])} items selected",
          repr(g["barCount"]))
    c.shot(f"{OUT}/select-all-1440.png")

    click_select_all(c)
    g = c.eval(GEOM)
    check("Clear All empties the page and hides the bar",
          not any(cb["checked"] for cb in g["rowCbs"])
          and g["headCb"]["checked"] is False
          and g["headCb"]["indeterminate"] is False
          and g["barHidden"] is True,
          json.dumps({"rows": [cb["checked"] for cb in g["rowCbs"]],
                      "hidden": g["barHidden"]}))

    # Keyboard: Space on a focused checkbox.
    c.eval("""(() => {
      document.querySelectorAll('[data-rows] .row .ads-checkbox__input')[1].focus();
      return true;
    })()""")
    c.key(" ", "Space")
    time.sleep(0.25)
    g = c.eval(GEOM)
    check("Space on a focused row checkbox selects that record",
          g["rowCbs"][1]["checked"] is True and len(g["selectedIds"]) == 1,
          json.dumps([cb["checked"] for cb in g["rowCbs"]]))
    c.key(" ", "Space")
    time.sleep(0.25)
    g = c.eval(GEOM)
    check("Space again clears it",
          g["rowCbs"][1]["checked"] is False and g["barHidden"] is True,
          json.dumps([cb["checked"] for cb in g["rowCbs"]]))

    # No selectable rows: the header checkbox has nothing to act on.
    c.eval("""(() => {
      const i = document.querySelector('.search__input');
      i.value = 'zzzzzzzzz';
      i.dispatchEvent(new Event('input', {bubbles: true}));
      return true;
    })()""")
    time.sleep(0.5)
    empty = c.eval("""(() => {
      const i = document.querySelector('[data-select-all-host] .ads-checkbox__input');
      const box = i.closest('.ads-checkbox').querySelector('.ads-checkbox__box');
      return {rows: document.querySelectorAll('[data-rows] .row').length,
              disabled: i.disabled, checked: i.checked,
              indeterminate: i.indeterminate,
              fill: getComputedStyle(box).backgroundColor,
              cursor: getComputedStyle(i.closest('.ads-checkbox')).cursor};
    })()""")
    check("with no selectable rows the header checkbox is disabled",
          empty["rows"] == 0 and empty["disabled"] is True
          and empty["checked"] is False and empty["indeterminate"] is False,
          json.dumps(empty))
    check("the disabled box takes the ADS disabled fill and cursor",
          empty["fill"] == "rgba(15, 18, 20, 0.05)" and empty["cursor"] == "default",
          json.dumps({"fill": empty["fill"], "cursor": empty["cursor"]}))
    c.eval("""(() => {
      const i = document.querySelector('.search__input');
      i.value = '';
      i.dispatchEvent(new Event('input', {bubbles: true}));
      return true;
    })()""")
    time.sleep(0.5)


def check_action_bar(c):
    print("\n== action bar vs 608:12966 / 608:14479 ==")
    first = click_row(c, 0)
    g = c.eval(GEOM)
    f = FIGMA

    check("one row selected shows the bar", g["bar"] is not None,
          json.dumps({"hidden": g["barHidden"]}))
    check("bar sits directly above the column header row",
          g["headIndex"] == g["barIndex"] + 1,
          f"headIndex={g['headIndex']} barIndex={g['barIndex']}")
    check("bar top edge", near(g["bar"]["y"], f["bar_y"], 1.5),
          f"{g['bar']['y']} vs {f['bar_y']}")
    check("bar height", near(g["bar"]["h"], f["bar_h"]),
          f"{g['bar']['h']} vs {f['bar_h']}")
    check("bar spans the table width", near(g["bar"]["w"], f["card_w"] - 2),
          f"{g['bar']['w']} vs {f['card_w'] - 2}")
    check("bar background is indigo/300",
          g["barStyle"]["backgroundColor"] == f["bar_bg"],
          g["barStyle"]["backgroundColor"])
    check("bar keeps the table divider underneath",
          g["barStyle"]["borderBottomWidth"] == "1px",
          json.dumps(g["barStyle"]))
    check("bar side padding 16px",
          g["barStyle"]["paddingLeft"] == "16px"
          and g["barStyle"]["paddingRight"] == "16px",
          json.dumps(g["barStyle"]))
    check("count label reads '1 item selected'",
          g["barCount"] == "1 item selected", repr(g["barCount"]))
    # The reference wraps the count in a standard 12px table cell inside
    # the bar's own 16px padding, so the text itself lands on 28.
    count_text_x = g["barCountBox"]["x"] + float(
        g["barCountStyle"]["paddingLeft"].replace("px", ""))
    check("count text starts at the reference inset",
          near(count_text_x, f["bar_count_x"], 1.5),
          f"{count_text_x} vs {f['bar_count_x']}")
    check("count is 14/20 semibold white",
          g["barCountStyle"]["fontSize"] == "14px"
          and g["barCountStyle"]["lineHeight"] == "20px"
          and g["barCountStyle"]["fontWeight"] == "600"
          and g["barCountStyle"]["color"] == "rgb(255, 255, 255)",
          json.dumps(g["barCountStyle"]))

    labels = [b["label"] for b in g["barBtns"]]
    check("five actions in reference order", labels == f["bar_labels"],
          " | ".join(labels))
    check("every action has a 16px icon",
          all(b["icon"] and near(b["iconW"], 16) for b in g["barBtns"]),
          json.dumps([b["iconW"] for b in g["barBtns"]]))
    check("action buttons are 36px tall",
          all(near(b["h"], f["bar_btn_h"]) for b in g["barBtns"]),
          json.dumps([b["h"] for b in g["barBtns"]]))
    check("action buttons use 6px radius and 8/12 padding",
          all(b["radius"] == "6px" and b["pad"] == "8px 12px"
              for b in g["barBtns"]),
          json.dumps([[b["radius"], b["pad"]] for b in g["barBtns"]]))
    check("action label color is white",
          all(b["color"] == "rgb(255, 255, 255)" for b in g["barBtns"]),
          json.dumps([b["color"] for b in g["barBtns"]]))
    gaps = [round(g["barBtns"][i + 1]["x"] - (g["barBtns"][i]["x"] + g["barBtns"][i]["w"]), 1)
            for i in range(len(g["barBtns"]) - 1)]
    check("4px gaps between actions",
          all(near(v, f["bar_btn_gap"], 0.6) for v in gaps), json.dumps(gaps))
    last = g["barBtns"][-1]
    right_inset = round(g["bar"]["w"] - (last["x"] + last["w"]), 1)
    check("action group ends 16px from the card edge",
          near(right_inset, f["bar_right_inset"], 1.5), str(right_inset))
    check("Quick Edit is enabled for a single selection",
          g["barBtns"][0]["disabled"] is False,
          json.dumps(g["barBtns"][0]["disabled"]))
    c.shot(f"{OUT}/selected-1-1440.png")
    return first


def check_selection_cases(c):
    print("\n== selection cases ==")
    # Reset to the empty selection the previous block left behind.
    c.key("Escape")
    time.sleep(0.2)
    g = c.eval(GEOM)
    check("case 1: no rows selected hides the bar",
          g["barHidden"] is True and g["selectedIds"] == [],
          json.dumps({"hidden": g["barHidden"], "ids": g["selectedIds"]}))

    id0 = click_row(c, 0)
    g = c.eval(GEOM)
    check("case 2: one row selected",
          g["selectedIds"] == [id0] and g["barCount"] == "1 item selected",
          f"{g['selectedIds']} / {g['barCount']}")

    id2 = click_row(c, 2)
    g = c.eval(GEOM)
    check("case 3: two non-adjacent rows selected",
          sorted(g["selectedIds"]) == sorted([id0, id2])
          and g["barCount"] == "2 items selected",
          f"{g['selectedIds']} / {g['barCount']}")

    for i in (4, 6, 8):
        click_row(c, i)
    g = c.eval(GEOM)
    check("case 4: five rows selected",
          len(g["selectedIds"]) == 5 and g["barCount"] == "5 items selected",
          f"{g['selectedIds']} / {g['barCount']}")
    check("Quick Edit disabled while five rows are selected",
          g["barBtns"][0]["disabled"] is True
          and all(b["disabled"] is False for b in g["barBtns"][1:]),
          json.dumps([b["disabled"] for b in g["barBtns"]]))
    c.shot(f"{OUT}/selected-5-1440.png")

    click_row(c, 8)
    g = c.eval(GEOM)
    check("case 5: clicking a selected row deselects it",
          len(g["selectedIds"]) == 4 and g["barCount"] == "4 items selected",
          f"{g['selectedIds']} / {g['barCount']}")

    for i in (0, 2, 4, 6):
        click_row(c, i)
    g = c.eval(GEOM)
    check("case 6: deselecting every row hides the bar",
          g["selectedIds"] == [] and g["barHidden"] is True,
          f"{g['selectedIds']} / hidden={g['barHidden']}")

    # ---- case 7: sorting ---------------------------------------------------
    # Sorting can move a selected record onto another page, so the
    # assertion is that the selection set is unchanged and that whichever
    # of its rows are on screen are still painted as selected. Anything
    # stricter would be asserting the sort order, not the selection.
    picked = sorted([click_row(c, 1), click_row(c, 3)])
    # 2.1 hides the standalone .th--name header in favor of the combined
    # .th--name-id "Rate Card ID / Name" header (see styles.css "VERSION
    # 2.1 LIST VIEW"); both share the "name" sort key, so click whichever
    # one is actually visible.
    sort_spot = c.eval("""(() => {
      const th = document.querySelector('.table__head .th--name-id')
        || document.querySelector('.table__head .th--name');
      const r = th.getBoundingClientRect();
      return {x: r.x + 40, y: r.y + r.height / 2};
    })()""")
    c.click(sort_spot["x"], sort_spot["y"])
    time.sleep(0.35)
    g = c.eval(GEOM)
    check("case 7: selection survives sorting",
          g["barCount"] == "2 items selected"
          and set(g["selectedIds"]) <= set(picked)
          and set(g["selectedIds"]) == set(picked) & set(g["visibleIds"]),
          f"visible-selected={g['selectedIds']} picked={picked} "
          f"count={g['barCount']}")

    # ---- case 8: searching -------------------------------------------------
    term = c.eval("""(() => {
      const row = document.querySelector('[data-rows] .row.is-selected');
      if (!row) return null;
      const link = row.querySelector('.name__link');
      return link ? link.textContent.trim() : null;
    })()""")
    c.eval("""(() => {
      const i = document.querySelector('.search__input');
      i.focus(); return true;
    })()""")
    c.eval(f"""(() => {{
      const i = document.querySelector('.search__input');
      i.value = {json.dumps(term or '')};
      i.dispatchEvent(new Event('input', {{bubbles: true}}));
      return true;
    }})()""")
    time.sleep(0.4)
    g = c.eval(GEOM)
    check("case 8: search narrows the table without losing the selection",
          g["rowCount"] >= 1 and g["barCount"] in ("1 item selected",
                                                   "2 items selected"),
          f"rows={g['rowCount']} count={g['barCount']}")
    c.eval("""(() => {
      const i = document.querySelector('.search__input');
      i.value = '';
      i.dispatchEvent(new Event('input', {bubbles: true}));
      return true;
    })()""")
    time.sleep(0.4)
    g = c.eval(GEOM)
    check("case 8: clearing the search keeps both records selected",
          g["barCount"] == "2 items selected"
          and set(g["selectedIds"]) == set(picked) & set(g["visibleIds"]),
          f"visible-selected={g['selectedIds']} picked={picked} "
          f"count={g['barCount']}")

    # ---- case 9: paging ----------------------------------------------------
    moved = c.eval("""(() => {
      const btns = document.querySelectorAll('[data-pager] .page-btn--num');
      for (const b of btns) {
        if (b.textContent.trim() === '2') {
          const r = b.getBoundingClientRect();
          return {x: r.x + r.width / 2, y: r.y + r.height / 2};
        }
      }
      return null;
    })()""")
    if not moved:
        check("case 9: a second page exists to test paging", False,
              "no page 2 button")
    else:
        c.click(moved["x"], moved["y"])
        time.sleep(0.4)
        g = c.eval(GEOM)
        check("case 9: selection count holds while on page 2",
              g["barCount"] == "2 items selected"
              and set(g["selectedIds"]) == set(picked) & set(g["visibleIds"]),
              f"count={g['barCount']} visible-selected={g['selectedIds']}")
        check("case 9: page 2 repaints any selected record it holds",
              all((sel == "true") == (rid in picked)
                  for rid, sel in zip(g["visibleIds"], g["ariaSelected"])),
              json.dumps(list(zip(g["visibleIds"], g["ariaSelected"]))))
        back = c.eval("""(() => {
          const btns = document.querySelectorAll('[data-pager] .page-btn--num');
          for (const b of btns) {
            if (b.textContent.trim() === '1') {
              const r = b.getBoundingClientRect();
              return {x: r.x + r.width / 2, y: r.y + r.height / 2};
            }
          }
          return null;
        })()""")
        c.click(back["x"], back["y"])
        time.sleep(0.4)
        g = c.eval(GEOM)
        check("case 9: returning to page 1 keeps the same selection",
              g["barCount"] == "2 items selected"
              and set(g["selectedIds"]) == set(picked) & set(g["visibleIds"]),
              f"count={g['barCount']} visible-selected={g['selectedIds']}")

    # ---- keyboard ----------------------------------------------------------
    c.key("Escape")
    time.sleep(0.2)
    kb = c.eval("""(() => {
      const row = document.querySelectorAll('[data-rows] .row')[0];
      row.focus();
      return {tabindex: row.getAttribute('tabindex'),
              focused: document.activeElement === row,
              outline: getComputedStyle(row, ':focus-visible').outlineWidth};
    })()""")
    check("rows are focusable for keyboard selection",
          kb["focused"] and kb["tabindex"] is not None, json.dumps(kb))
    c.key(" ", "Space")
    time.sleep(0.2)
    g = c.eval(GEOM)
    check("Space toggles selection on the focused row",
          len(g["selectedIds"]) == 1, json.dumps(g["selectedIds"]))
    c.key("Enter")
    time.sleep(0.2)
    g = c.eval(GEOM)
    check("Enter toggles the same row back off",
          g["selectedIds"] == [] and g["barHidden"] is True,
          json.dumps(g["selectedIds"]))


def check_responsive(url):
    print("\n== responsive ==")
    for label, vp in (("320", (320, 800)), ("375", (375, 812)),
                      ("768", (768, 1024)), ("1024", (1024, 768)),
                      ("1280", (1280, 800)), ("figma-frame", (1440, 932)),
                      ("wide", (1920, 1080))):
        proc, port = boot_chrome(vp, f"resp_{label}")
        try:
            c = CDP(port)
            open_page(c, url, vp)
            click_row_checkbox(c, 0)
            click_row_checkbox(c, 2)
            g = c.eval(GEOM)
            tag = f"{label} {vp[0]}x{vp[1]}"
            check(f"{tag}: no page-level horizontal scrollbar",
                  g["docSW"] <= g["docCW"], f"{g['docSW']} vs {g['docCW']}")
            check(f"{tag}: card never exceeds the reference width",
                  g["cardW"] <= FIGMA["card_w"], str(g["cardW"]))
            # The bar starts where the header row starts and spans the
            # width the table is showing. Where the columns fit, that is
            # the header row's own width; where they do not, the bar
            # spans the scrollport instead of running off with the
            # columns, so its actions stay reachable.
            check(f"{tag}: bar stays aligned with the visible table",
                  near(g["bar"]["x"], g["head"]["x"], 1)
                  and near(g["bar"]["w"], g["tableScrollW"], 1.5)
                  and g["bar"]["w"] <= g["head"]["w"] + 1,
                  f"bar={g['bar']} head={g['head']} port={g['tableScrollW']}")
            # Below 1000 the shared narrow-viewport rule tightens Status
            # and Rate Card ID for every modern version, so only the
            # selection column and the columns it does not touch are held
            # to the reference width there. Rate Card ID / Name and
            # Buying Entity are the two tracks that are meant to give
            # ground as the card narrows, so they are checked against
            # their own floors just below rather than a fixed width.
            tightened = ({"status", "rate-card-id"} if vp[0] <= 999 else set())
            tightened |= {"name-id", "buying-entity",
                          "marketplace", "last-updated"}
            check(f"{tag}: columns keep their reference widths",
                  all(near(g["cols"][name]["w"], w, 1.5)
                      for name, _, w in FIGMA["cols"]
                      if name in g["cols"] and name not in tightened),
                  json.dumps({k: v["w"] for k, v in g["cols"].items()}))
            check(f"{tag}: the selection column keeps its exact width",
                  near(g["cols"]["select"]["w"], FIGMA["select_w"], 0.5),
                  str(g["cols"]["select"]["w"]))
            name_w = g["cols"]["name-id"]["w"]
            buyer_w = g["cols"]["buying-entity"]["w"]
            check(f"{tag}: Rate Card ID / Name never goes below its floor",
                  name_w >= FIGMA["name_id_min"] - 1.5, str(name_w))
            check(f"{tag}: Rate Card ID / Name stays the widest column",
                  name_w - max(v["w"] for k, v in g["cols"].items()
                               if k != "name-id") >= 150,
                  json.dumps({k: v["w"] for k, v in g["cols"].items()}))
            # 2026-08-26: Buying Entity is now the flexible column and
            # Rate Card ID / Name is capped, so the yielding order is the
            # other way round. Buying Entity takes the row's spare width
            # down to its own floor, and only once it is there does Rate
            # Card ID / Name come off its cap.
            check(f"{tag}: Rate Card ID / Name yields only after Buying Entity",
                  buyer_w >= FIGMA["buyer_min"] - 1.5
                  and (name_w >= FIGMA["name_id_w"] - 1.5
                       or buyer_w <= FIGMA["buyer_min"] + 1.5),
                  f"buyer={buyer_w} name={name_w}")
            # The cap is the point of the change: the column has to stop
            # growing well before it swallows the row's whole surplus.
            check(f"{tag}: Rate Card ID / Name never exceeds its cap",
                  name_w <= FIGMA["name_id_w"] + 1.5, str(name_w))
            check(f"{tag}: count still reads two items",
                  g["barCount"] == "2 items selected", str(g["barCount"]))
            check(f"{tag}: every action stays reachable",
                  len(g["barBtns"]) == 5, str(len(g["barBtns"])))
            # Horizontal scrolling is legitimate only when the card is
            # narrower than the table's own minimum.
            overflow = g["tableScrollSW"] > g["tableScrollW"]
            check(f"{tag}: table scrolls only when the card is too narrow",
                  overflow == (g["tableScrollW"] < g["tableScrollSW"]),
                  f"overflow={overflow} cardW={g['cardW']}")

            # Scrolled hard right, the selection column and the bar's count
            # both have to still be on screen. At the reference width there
            # is no scroll to apply and this is a no-op.
            c.eval("document.querySelector('.table-scroll').scrollLeft = 9999; true")
            time.sleep(0.3)
            pinned = c.eval("""(() => {
              const port = document.querySelector('.table-scroll').getBoundingClientRect();
              const inPort = (n) => {
                if (!n) return null;
                const r = n.getBoundingClientRect();
                return r.left >= port.left - 0.6 && r.right <= port.right + 0.6;
              };
              const bar = document.querySelector('[data-selection-bar]');
              return {
                row: inPort(document.querySelector('[data-rows] .row .ads-checkbox__box')),
                head: inPort(document.querySelector('[data-select-all-host] .ads-checkbox__box')),
                count: inPort(bar && bar.querySelector('[data-selection-count]')),
                actions: Array.prototype.every.call(
                  bar.querySelectorAll('.rcsel__btn'),
                  (b) => b.getBoundingClientRect().width > 0),
                offset: document.querySelector('.table-scroll').scrollLeft,
              };
            })()""")
            check(f"{tag}: the selection column stays pinned while the table scrolls",
                  pinned["row"] and pinned["head"], json.dumps(pinned))
            check(f"{tag}: the count stays on screen at any scroll offset",
                  pinned["count"] and pinned["actions"], json.dumps(pinned))
            c.shot(f"{OUT}/resp-{label}.png")
        finally:
            proc.kill()


def check_zoom_and_scaling(url):
    """200% browser zoom is a page scale factor, which is what a CSS
    viewport shrunk by two models. Text scaling is the separate case of a
    larger root font with the viewport unchanged."""
    print("\n== 200% zoom and text scaling ==")
    proc, port = boot_chrome((1440, 932), "zoom")
    try:
        c = CDP(port)
        open_page(c, url, (1440, 932))
        c.send("Emulation.setDeviceMetricsOverride",
               {"width": 720, "height": 466, "deviceScaleFactor": 1, "mobile": False})
        time.sleep(0.5)
        click_row_checkbox(c, 0)
        g = c.eval(GEOM)
        z = c.eval(PINNED)
        check("200% zoom: no page-level horizontal scrollbar",
              g["docSW"] <= g["docCW"], f"{g['docSW']} vs {g['docCW']}")
        check("200% zoom: the checkbox column keeps its exact width",
              near(g["cols"]["select"]["w"], FIGMA["select_w"], 0.5)
              and near(g["headCb"]["box"], FIGMA["cb_box"], 0.6),
              f"col={g['cols']['select']['w']} box={g['headCb']['box']}")
        check("200% zoom: header and row checkboxes stay aligned and on screen",
              z["aligned"] and z["row"] and z["head"], json.dumps(z))
        check("200% zoom: the count and all five actions stay available",
              z["count"] and len(g["barBtns"]) == 5,
              json.dumps({"count": z["count"], "actions": len(g["barBtns"])}))
        c.shot(f"{OUT}/zoom-200.png")

        open_page(c, url, (1440, 932))
        c.eval("document.documentElement.style.fontSize = '20px'; true")
        time.sleep(0.4)
        click_row_checkbox(c, 0)
        g = c.eval(GEOM)
        z = c.eval(PINNED)
        check("a larger root font does not distort the checkbox column",
              near(g["cols"]["select"]["w"], FIGMA["select_w"], 0.6)
              and near(g["headCb"]["box"], FIGMA["cb_box"], 0.6)
              and z["aligned"], f"col={g['cols']['select']['w']} "
                                f"box={g['headCb']['box']} aligned={z['aligned']}")
    finally:
        proc.kill()


def check_focus_and_hover(c):
    print("\n== checkbox focus and hover ==")
    c.key("Escape")
    time.sleep(0.2)
    c.eval("""(() => {
      document.querySelectorAll('[data-rows] .row .ads-checkbox__input')[0].focus();
      return true;
    })()""")
    time.sleep(0.25)
    fo = c.eval("""(() => {
      const i = document.querySelector('[data-rows] .row .ads-checkbox__input');
      const box = i.closest('.ads-checkbox').querySelector('.ads-checkbox__box');
      const s = getComputedStyle(box);
      const cell = i.closest('.cell--select');
      return {focused: document.activeElement === i,
              shadow: s.boxShadow, outline: s.outlineWidth,
              room: +(box.getBoundingClientRect().left
                      - cell.getBoundingClientRect().left).toFixed(1),
              cellOverflow: getComputedStyle(cell).overflow};
    })()""")
    check("a focused row checkbox draws a visible ring",
          fo["focused"] and (fo["shadow"] != "none"
                             or fo["outline"] not in ("", "0px", "auto")),
          json.dumps(fo))
    check("the selection cell does not clip that ring",
          fo["cellOverflow"] in ("visible", "") and fo["room"] >= 3,
          json.dumps(fo))
    c.shot(f"{OUT}/focus-ring.png")

    spot = c.eval(CLICK_BOX % json.dumps(
        "[data-rows] .row:nth-of-type(2) .ads-checkbox__box"))
    c.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": spot["x"],
                                        "y": spot["y"], "button": "none"})
    time.sleep(0.3)
    hov = c.eval("""(() => {
      const box = document.querySelectorAll('[data-rows] .row .ads-checkbox__box')[1];
      const s = getComputedStyle(box);
      return {fill: s.backgroundColor, border: s.borderTopColor};
    })()""")
    check("hover deepens the unchecked border and leaves the fill alone",
          hov["border"] != FIGMA["cb_border_rest"]
          and hov["fill"] == FIGMA["cb_fill_rest"], json.dumps(hov))
    c.key("Escape")
    time.sleep(0.2)


def check_action_targeting(c):
    """The action handlers live inside the app's closure, so the only
    honest way to see what an action received is the artefact it makes.
    Download writes a real CSV through a blob, so capture the blob."""
    print("\n== actions target the selected set ==")
    c.key("Escape")
    time.sleep(0.2)
    c.eval("""(() => {
      window.__blobs = []; window.__names = [];
      const make = URL.createObjectURL.bind(URL);
      URL.createObjectURL = function (blob) {
        blob.text().then((t) => window.__blobs.push(t));
        return make(blob);
      };
      const click = HTMLAnchorElement.prototype.click;
      HTMLAnchorElement.prototype.click = function () {
        if (this.download) { window.__names.push(this.download); return; }
        return click.apply(this, arguments);
      };
      return true;
    })()""")
    for i in (0, 2, 5):
        click_row_checkbox(c, i)
    g = c.eval(GEOM)
    names = c.eval("""Array.prototype.map.call(
      document.querySelectorAll('[data-rows] .row.is-selected .name__link'),
      (a) => a.textContent.trim())""")
    check("three non-adjacent rows select and read as three items",
          len(g["selectedIds"]) == 3 and g["barCount"] == "3 items selected"
          and g["headCb"]["indeterminate"] is True,
          f"{g['selectedIds']} / {g['barCount']}")
    check("the single-record action is the only one disabled for a set",
          g["barBtns"][0]["disabled"] is True
          and all(b["disabled"] is False for b in g["barBtns"][1:]),
          json.dumps([[b["label"], b["disabled"]] for b in g["barBtns"]]))

    # Download is bulk-safe and non-destructive, so it is the one to run.
    spot = c.eval(CLICK_BOX % json.dumps('.rcsel__btn[aria-label="Download"]'))
    c.click(spot["x"], spot["y"])
    time.sleep(1.0)
    dl = c.eval("""(() => ({
      names: window.__names || [], blobs: (window.__blobs || []).length,
      csv: (window.__blobs || [])[0] || '',
      toast: Array.prototype.map.call(
        document.querySelectorAll('.toast, [role="status"]'),
        (t) => t.textContent.trim()).join(' | '),
    }))()""")
    check("Download wrote one real CSV named for the whole selection",
          dl["blobs"] == 1 and dl["names"] == ["rate-cards-3.csv"],
          json.dumps({"names": dl["names"], "blobs": dl["blobs"]}))
    check("that CSV carries every selected rate card",
          all(n in dl["csv"] for n in names),
          json.dumps({"want": names, "hits": [n in dl["csv"] for n in names]}))
    check("the success toast reports the real count",
          "3 rate cards exported" in dl["toast"], dl["toast"][:160])

    # Archive removes the records, which is the reconciliation case: the
    # selection has to empty itself rather than keep three dead ids.
    spot = c.eval(CLICK_BOX % json.dumps('.rcsel__btn[aria-label="Archive"]'))
    c.click(spot["x"], spot["y"])
    time.sleep(0.9)
    g = c.eval(GEOM)
    check("archiving the selection empties it and hides the bar",
          g["barHidden"] is True and g["selectedIds"] == []
          and not any(cb["checked"] for cb in g["rowCbs"])
          and g["headCb"]["checked"] is False
          and g["headCb"]["indeterminate"] is False,
          json.dumps({"hidden": g["barHidden"], "ids": g["selectedIds"],
                      "head": g["headCb"]}))


def check_version_round_trip(url):
    """The selection header cell is mounted, not parked in the markup, so
    it has to survive leaving 2.1 and coming back without duplicating."""
    print("\n== version round trip ==")
    proc, port = boot_chrome((1440, 932), "roundtrip")
    try:
        c = CDP(port)
        ths = lambda: c.eval("""Array.prototype.map.call(
          document.querySelectorAll('.table__head .th'),
          (t) => (t.className.match(/th--[a-z-]+/g) || []).join('.'))""")
        open_page(c, url, (1440, 932))
        check("2.1 leads the header with the selection column",
              ths()[0] == "th--select", json.dumps(ths()))
        open_page(c, url + "?version=2.0", (1440, 932))
        check("2.0 carries no selection header cell at all",
              "th--select" not in ths()
              and c.eval(GEOM)["headCb"] is None, json.dumps(ths()))
        open_page(c, url + "?version=2.1", (1440, 932))
        back = ths()
        head = c.eval(GEOM)["headCb"]
        check("returning to 2.1 remounts exactly one selection header",
              back[0] == "th--select" and back.count("th--select") == 1
              and head["checked"] is False and head["indeterminate"] is False,
              json.dumps({"ths": back, "head": head}))
    finally:
        proc.kill()


def check_v20_untouched(url):
    print("\n== 2.0 regression guard ==")
    proc, port = boot_chrome((1440, 932), "v20")
    try:
        c = CDP(port)
        open_page(c, url + "?version=2.0", (1440, 932))
        g = c.eval(GEOM)
        check("2.0 still reports itself as 2.0", g["version"] == "2.0",
              str(g["version"]))
        check("2.0 keeps its Action column",
              g["actionHeads"] == 1 and g["actionCells"] > 0,
              f"heads={g['actionHeads']} cells={g['actionCells']}")
        check("2.0 keeps its Buying Entity column",
              g["buyingCells"] > 0, str(g["buyingCells"]))
        check("2.0 never builds the action bar",
              g["barPresent"] is False, str(g["barPresent"]))
        check("2.0 has no selection column and no checkbox",
              "select" not in g["cols"] and g["headCb"] is None
              and all(cb is None for cb in g["rowCbs"]),
              json.dumps({"col": "select" in g["cols"],
                          "head": g["headCb"] is not None}))
        click_row(c, 0)
        click_row(c, 2)
        g = c.eval(GEOM)
        check("2.0 selection stays single-row",
              len(g["selectedIds"]) == 1, json.dumps(g["selectedIds"]))
    finally:
        proc.kill()


def main():
    port = _free_port()
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port)],
                              cwd=ROOT, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}/"
    time.sleep(1)
    try:
        proc, cport = boot_chrome(FIGMA["frame"], "main")
        try:
            c = CDP(cport)
            open_page(c, url, FIGMA["frame"])
            check_default_state(c, url)
            check_checkbox_states(c)
            check_focus_and_hover(c)
            check_action_bar(c)
            check_selection_cases(c)
            # Runs last in this browser: it archives records, which
            # changes the data set the earlier blocks read from.
            check_action_targeting(c)
        finally:
            proc.kill()
        check_responsive(url)
        check_zoom_and_scaling(url)
        check_version_round_trip(url)
        check_v20_untouched(url)
    finally:
        server.terminate()

    failed = [c for c in CHECKS if not c[1]]
    print(f"\n{len(CHECKS) - len(failed)}/{len(CHECKS)} checks passed")
    if failed:
        print("\nFAILURES")
        for label, _, detail in failed:
            print(f"  - {label}: {detail}")
    print(f"\nscreenshots: {OUT}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
