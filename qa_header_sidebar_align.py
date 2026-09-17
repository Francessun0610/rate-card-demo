#!/usr/bin/env python3
"""
qa_header_sidebar_align.py - Ad-hoc QA for the 2026-08-12 header/sidebar brief.

Verifies:
  1. Header brand name reads "Ad Console" and stays vertically centered
     with the logomark.
  2. Every sidebar nav icon shares one consistent horizontal axis in both
     collapsed and expanded states. In the collapsed rail that axis is the
     exact Figma 595:6631 geometry - a 68px rail with a symmetric 14px
     inset, which centers the 40px NavItem (and its 20px icon) on x=34.
     The header brand lockup's visible Disney "D" is centered on that same
     x=34 axis (2026-08-15 alignment brief, superseding the 2026-08-13
     brief that instead cleared the rail by one nav gap).
  3. Selected "Rate cards" row still renders its active background/bar.
  4. The collapse button stays anchored near the bottom-right of the
     sidebar at multiple viewport heights, remains visible while page
     content scrolls, and never overlaps nav items or the viewport edge.
"""
import base64
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = "/Users/frances.sun/My Drive/Cursor and Code/Rate Card"
URL = "http://127.0.0.1:8001/"
OUT = "/tmp/qa_header_sidebar_align"
os.makedirs(OUT, exist_ok=True)

CHECKS = []


def check(label, ok, detail=""):
    tag = "PASS" if ok else "FAIL"
    print(f"  {tag}  {label}{(' -- ' + detail) if detail else ''}")
    CHECKS.append((label, ok, detail))


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def boot_chrome(viewport, label):
    w, h = viewport
    port = _free_port()
    # Isolated profile per run - the app persists sidebar pin state to
    # localStorage, so a shared profile across viewports would leak the
    # "expanded" choice from one run's assertions into the next run's
    # supposedly-fresh "collapsed" measurement.
    profile_dir = f"/tmp/qa_header_sidebar_align_profile_{label}"
    proc = subprocess.Popen([
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        f"--remote-debugging-port={port}",
        "--remote-allow-origins=*",
        f"--window-size={w},{h}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run", "--no-default-browser-check", "--headless=new",
        "--hide-scrollbars", "--disable-gpu",
        "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen(
                f"http://127.0.0.1:{port}/json/version", timeout=0.5
            ).read()
            return proc, port
        except Exception:
            time.sleep(0.1)
    proc.kill()
    raise RuntimeError("chrome failed to boot")


class CDP:
    def __init__(self, port):
        import websocket
        targets = json.loads(
            urllib.request.urlopen(f"http://127.0.0.1:{port}/json").read()
        )
        target = next(t for t in targets if t["type"] == "page")
        self.ws = websocket.create_connection(
            target["webSocketDebuggerUrl"], timeout=30
        )
        self.i = 0

    def send(self, method, params=None):
        self.i += 1
        self.ws.send(json.dumps(
            {"id": self.i, "method": method, "params": params or {}}
        ))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.i:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    def eval(self, expr):
        r = self.send("Runtime.evaluate", {
            "expression": expr, "returnByValue": True, "awaitPromise": True,
        })
        if "exceptionDetails" in r:
            raise RuntimeError(r["exceptionDetails"])
        return r.get("result", {}).get("value")

    def screenshot(self, path):
        r = self.send("Page.captureScreenshot", {"format": "png"})
        open(path, "wb").write(base64.b64decode(r["data"]))

    def click(self, x, y):
        for t in ("mousePressed", "mouseReleased"):
            self.send("Input.dispatchMouseEvent", {
                "type": t, "x": x, "y": y, "button": "left", "clickCount": 1,
            })


def go(c, url):
    c.send("Page.enable")
    c.send("Runtime.enable")
    c.send("Network.enable")
    c.send("Network.setCacheDisabled", {"cacheDisabled": True})
    c.send("Page.navigate", {"url": url})
    for _ in range(80):
        if c.eval("!!document.querySelector('.vnav')"):
            break
        time.sleep(0.1)
    time.sleep(0.4)
    # Reused profile dirs across separate script invocations can carry a
    # stale "rate-card-nav-pinned" localStorage entry into what's supposed
    # to be a fresh, collapsed-by-default load. Force a clean slate.
    c.eval("localStorage.clear(); true")
    c.send("Page.navigate", {"url": url})
    for _ in range(80):
        if c.eval("!!document.querySelector('.vnav')"):
            break
        time.sleep(0.1)
    time.sleep(0.4)


def run_viewport(label, viewport):
    print(f"\n== {label} ({viewport[0]}x{viewport[1]}) ==")
    proc, port = boot_chrome(viewport, label)
    try:
        c = CDP(port)
        go(c, URL)

        # ---- 1. Header brand name -----------------------------------------
        brand = c.eval("""(() => {
          const name = document.querySelector('.gnav__brand-name--v2');
          const logo = document.querySelector('.gnav__brand-icon--v2');
          if (!name || !logo) return null;
          const nameRect = name.getBoundingClientRect();
          const logoRect = logo.getBoundingClientRect();
          return {
            text: name.textContent.trim(),
            nameCenterY: nameRect.top + nameRect.height / 2,
            logoCenterY: logoRect.top + logoRect.height / 2,
            headerHeight: document.querySelector('.gnav').getBoundingClientRect().height,
          };
        })()""")
        check(
            "header brand name reads 'Ad Console'",
            brand and brand["text"] == "Ad Console",
            json.dumps(brand),
        )
        check(
            "logo + brand name stay vertically centered with each other",
            brand and abs(brand["nameCenterY"] - brand["logoCenterY"]) <= 1,
            json.dumps(brand),
        )

        # ---- 2. Sidebar icon alignment (collapsed) -------------------------
        collapsed = c.eval("""(() => {
          const logo = document.querySelector('.gnav__brand-icon--v2').getBoundingClientRect();
          const lockup = document.querySelector('.gnav__logomark').getBoundingClientRect();
          const name = document.querySelector('.gnav__brand-name--v2').getBoundingClientRect();
          const rail = document.querySelector('.vnav').getBoundingClientRect();
          const icons = [...document.querySelectorAll('.vnav__link')].map(l => {
            const icon = l.querySelector('.vnav__icon');
            const r = icon.getBoundingClientRect();
            return Math.round(r.left);
          });
          const centers = [...document.querySelectorAll('.vnav__icon')].map(i => {
            const r = i.getBoundingClientRect();
            return +(r.left + r.width / 2).toFixed(2);
          });
          const rows = [...document.querySelectorAll('.vnav__link')].map(l => {
            const r = l.getBoundingClientRect();
            return {left: +r.left.toFixed(2), w: +r.width.toFixed(2)};
          });
          return {
            railWidth: +rail.width.toFixed(2),
            railRight: +rail.right.toFixed(2),
            logoLeft: Math.round(logo.left),
            logoCenter: +(logo.left + logo.width / 2).toFixed(2),
            lockupLeft: +lockup.left.toFixed(2),
            lockupWidth: +lockup.width.toFixed(2),
            nameGap: +(name.left - logo.right).toFixed(2),
            iconLefts: icons,
            uniqueLefts: [...new Set(icons)],
            iconCenters: centers,
            uniqueCenters: [...new Set(centers)],
            rowLefts: [...new Set(rows.map(r => r.left))],
            rowWidths: [...new Set(rows.map(r => r.w))],
          };
        })()""")
        check(
            "collapsed: every nav icon shares one horizontal axis",
            len(collapsed["uniqueLefts"]) == 1,
            json.dumps(collapsed["uniqueLefts"]),
        )
        # Figma 595:6631 is a 68px rail with a symmetric 14px inset, so the
        # 40px NavItem lands at x=14..54 and centers on x=34, the rail's own
        # midline.
        check(
            "collapsed: rail width matches Figma 595:6631 (68px)",
            collapsed["railWidth"] == 68,
            f"railWidth={collapsed['railWidth']}",
        )
        check(
            "collapsed: NavItem is 40px wide at the Figma 14px inset",
            collapsed["rowLefts"] == [14.0] and collapsed["rowWidths"] == [40.0],
            f"lefts={collapsed['rowLefts']} widths={collapsed['rowWidths']}",
        )
        check(
            "collapsed: every icon centers on one axis",
            len(collapsed["uniqueCenters"]) == 1,
            f"iconCenters={collapsed['uniqueCenters']}",
        )
        # 2026-08-15 brief: the brand lockup's visible Disney "D" centers on
        # the same x=34 axis as the collapsed rail's nav icons, reversing
        # the 2026-08-13 "clear the rail by one nav gap" decision (which
        # traded that shared axis for clearance from an edge that only
        # exists one row down, on the rail, not in the header itself).
        # "Ad Console" keeps its usual gap to the right of the mark; only
        # the group's shared inline-start padding moved.
        check(
            "collapsed: brand logo's visible centre matches the rail's icon axis",
            collapsed["logoCenter"] == collapsed["iconCenters"][0],
            f"logoCenter={collapsed['logoCenter']} iconAxis={collapsed['iconCenters'][0]}",
        )
        check(
            "collapsed: brand name keeps its existing gap to the right of the logo",
            collapsed["nameGap"] == 8,
            f"nameGap={collapsed['nameGap']}",
        )
        c.screenshot(f"{OUT}/{label}_collapsed.png")

        # ---- 2b. Sidebar icon + label alignment (expanded) -----------------
        c.eval("window.RateCardShell.setVnavPinned(true)")
        time.sleep(0.3)
        expanded = c.eval("""(() => {
          const logo = document.querySelector('.gnav__brand-icon--v2').getBoundingClientRect();
          const rows = [...document.querySelectorAll('.vnav__link')].map(l => {
            const icon = l.querySelector('.vnav__icon').getBoundingClientRect();
            const label = l.querySelector('.vnav__label').getBoundingClientRect();
            return {
              route: l.closest('.vnav__item').dataset.route,
              iconLeft: Math.round(icon.left),
              labelLeft: Math.round(label.left),
              gap: Math.round(label.left - icon.right),
            };
          });
          const active = document.querySelector('.vnav__item--active');
          const activeLink = active.querySelector('.vnav__link');
          const activeBg = getComputedStyle(activeLink).backgroundColor;
          const activeBar = active.querySelector('.vnav__active-bar');
          return {
            logoLeft: Math.round(logo.left),
            rows,
            uniqueIconLefts: [...new Set(rows.map(r => r.iconLeft))],
            uniqueGaps: [...new Set(rows.map(r => r.gap))],
            activeRoute: active.dataset.route,
            activeBg,
            activeBarVisible: getComputedStyle(activeBar).display !== 'none'
              && getComputedStyle(activeBar).backgroundColor !== 'rgba(0, 0, 0, 0)',
          };
        })()""")
        check(
            "expanded: every icon shares one horizontal axis",
            len(expanded["uniqueIconLefts"]) == 1,
            json.dumps(expanded["rows"]),
        )
        check(
            "expanded: icon-to-label gap is identical for every row (spacing preserved)",
            len(expanded["uniqueGaps"]) == 1,
            json.dumps(expanded["rows"]),
        )
        # Figma 595:6574 expanded rail: 14px rail inset, rows 172px wide, and
        # on the active row (595:6592) the icon sits at x=23 and the label at
        # x=51 within the row - i.e. x=37 and x=65 against the viewport.
        check(
            "expanded: icon + label sit on the Figma 595:6574 active-row axis",
            expanded["uniqueIconLefts"] == [37]
            and [r["labelLeft"] for r in expanded["rows"]] == [65] * len(expanded["rows"]),
            f"iconLefts={expanded['uniqueIconLefts']} "
            f"labelLefts={sorted({r['labelLeft'] for r in expanded['rows']})}",
        )
        # NOTE: collapsed and expanded icon axes are NOT expected to be
        # pixel-identical, and this is unchanged by the 595:6631 rail work.
        # Figma 595:6574 (expanded) puts the ACTIVE row's icon at x=37
        # (row inset 12 + a 3px active indicator + the 8px gap) and every
        # other row's icon at x=26. This implementation lays the indicator
        # span out in every expanded row and only paints it on the active
        # one, so all expanded icons sit on the active row's x=37 axis.
        # That trades Figma's per-row inset for a rail where the icon
        # column never jumps as the active row changes. It is a deliberate,
        # pre-existing choice; revisit it only with a new design decision.
        print(
            f"  INFO  collapsed icon axis={collapsed['iconLefts'][0]}px "
            f"(center {collapsed['uniqueCenters'][0]}px), "
            f"expanded icon axis={expanded['uniqueIconLefts'][0]}px "
            "(offset is expected - active-bar spacer only exists when expanded)"
        )
        check(
            "expanded: Rate cards is the active/selected row with a visible background + bar",
            expanded["activeRoute"] == "pricing"
                and expanded["activeBg"] != "rgba(0, 0, 0, 0)"
                and expanded["activeBarVisible"],
            json.dumps(expanded),
        )
        c.screenshot(f"{OUT}/{label}_expanded.png")

        # ---- 3. Collapse button anchored near bottom-right -----------------
        footer = c.eval("""(() => {
          const vnav = document.querySelector('.vnav').getBoundingClientRect();
          const btn = document.querySelector('.vnav__close').getBoundingClientRect();
          const lastItem = [...document.querySelectorAll('.vnav__item')].pop()
            .getBoundingClientRect();
          return {
            viewportHeight: window.innerHeight,
            vnavBottom: Math.round(vnav.bottom),
            vnavRight: Math.round(vnav.right),
            btnBottom: Math.round(btn.bottom),
            btnRight: Math.round(btn.right),
            btnTop: Math.round(btn.top),
            distanceFromViewportBottom: Math.round(window.innerHeight - btn.bottom),
            distanceFromRailRight: Math.round(vnav.right - btn.right),
            lastItemBottom: Math.round(lastItem.bottom),
            overlapsLastItem: btn.top < lastItem.bottom,
            withinViewport: btn.bottom <= window.innerHeight && btn.top >= 0,
          };
        })()""")
        check(
            "collapse button sits ~16px from the viewport bottom (allow 0-24px)",
            0 <= footer["distanceFromViewportBottom"] <= 24,
            json.dumps(footer),
        )
        check(
            "collapse button is attached to the sidebar's right edge",
            footer["distanceFromRailRight"] <= 20,
            json.dumps(footer),
        )
        check(
            "collapse button does not overlap the last nav item",
            not footer["overlapsLastItem"],
            json.dumps(footer),
        )
        check(
            "collapse button stays fully within the viewport",
            footer["withinViewport"],
            json.dumps(footer),
        )

        # ---- 4. Button stays visible while page content scrolls -----------
        c.eval("document.querySelector('.page').scrollTop = 500")
        c.eval("window.scrollTo(0, 500)")
        time.sleep(0.2)
        after_scroll = c.eval("""(() => {
          const btn = document.querySelector('.vnav__close').getBoundingClientRect();
          return {
            visible: btn.width > 0 && btn.height > 0
              && btn.top >= 0 && btn.bottom <= window.innerHeight,
            top: Math.round(btn.top),
            bottom: Math.round(btn.bottom),
          };
        })()""")
        check(
            "collapse button remains visible after scrolling page content",
            after_scroll["visible"],
            json.dumps(after_scroll),
        )
        c.screenshot(f"{OUT}/{label}_after_scroll.png")
    finally:
        proc.kill()


def main():
    server = subprocess.Popen(
        [sys.executable, "-m", "http.server", "8001"],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(30):
        try:
            urllib.request.urlopen("http://127.0.0.1:8001/", timeout=0.5).read()
            break
        except Exception:
            time.sleep(0.1)
    try:
        run_viewport("short_1280x760", (1280, 760))
        run_viewport("tall_1440x1200", (1440, 1200))
        run_viewport("standard_1920x1080", (1920, 1080))
    finally:
        server.terminate()

    total = len(CHECKS)
    failed = [x for x in CHECKS if not x[1]]
    print(f"\n{'FAIL' if failed else 'PASS'} - {total - len(failed)}/{total}")
    if failed:
        for label, _ok, detail in failed:
            print(f"  FAIL {label}{(' -- ' + detail) if detail else ''}")
        sys.exit(1)


if __name__ == "__main__":
    main()
