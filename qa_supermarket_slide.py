#!/usr/bin/env python3
"""
qa_supermarket_slide.py - Atlas deck slide 3 QA.

Slide 3, "Think of Disney Advertising as a supermarket", is authored from
Figma node 620:20510 at the deck's native 1920 x 1080 coordinate space.
Three columns run left to right: the store, the shelf space in it, and the
product on the shelf. Each carries a small grey category label (Store /
Shelf space / Product) above its white business label (Disney Advertising /
Ad Inventory / Ad Offerings). This suite verifies it four ways:

  1. Geometry. Every element's box is read out of the live DOM in stage
     coordinates and compared against the coordinates Figma reports for the
     node. This is the authoritative check, because it compares numbers to
     numbers instead of pixels to pixels.

  2. Small/main label alignment. Both label rows are read straight out of
     getBoundingClientRect() and cross-checked against each other (not just
     against Figma numbers), because the real requirement is that the three
     columns can never drift apart from one another: shared top edges,
     shared bottom edges, an identical small-to-main gap, and each small
     label centred over its own main label and its own illustration.

  3. Pixel diff. The slide is rendered at 1:1 and differenced against the
     Figma PNG export, region by region. The illustration regions must match
     closely. The text regions are expected to differ: Figma sets this slide
     in InspireTWDC, a licensed face the deck does not ship, so the browser
     substitutes a fallback and the glyphs are simply not the same shapes.
     Reporting the regions separately keeps that substitution visible instead
     of letting it hide inside one whole-slide average.

The Figma export lives at tmp/figma-ref/figma-620-20510.png. tmp/ is
gitignored working scratch, so on a fresh clone the pixel stage is skipped
with a note and the geometry stage still runs. To restore it, re-export node
620:20510 as PNG at scale 1.

  4. Reveal. The heading arrives a line at a time on its own, then the
     presenter brings in one whole column per gesture, left to right. A
     column is one reveal target holding its drawing and both of its
     captions, so no piece of a column can arrive without the rest of it,
     one gesture can never spend two columns, backward navigation gives
     the columns back in reverse, and the slide draws no arrows or other
     extra graphics.

Also checks deck placement: slide 3 sits between the Right Price explainer
and the three-questions slide, and is reachable with the normal
next/previous controls. Deck-wide navigation is covered by qa_no_nav.py.
"""
import base64
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request

import numpy as np
from PIL import Image

# Resolved from this file so the suite runs from any checkout.
ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = "/tmp/qa_supermarket_slide"
REF = os.path.join(ROOT, "tmp/figma-ref/figma-620-20510.png")
STAGE_W, STAGE_H = 1920, 1080

# Figma node 620:20510 geometry, in stage coordinates.
#
# The three drawings use the intrinsic size of their SVG export rather than
# the fractional frame width Figma reports (371.05 / 369.96 / 303.79). Figma
# rounds an export viewport up to whole pixels from the frame origin, so the
# drawing keeps its Figma position and scale inside the slightly larger box
# and the slack lands on the trailing edge. Tolerance below absorbs that.
FIGMA = {
    "title": {
        "sel": ".sup__title",
        "text": "Think of Disney Advertising as a supermarket",
        "left": 63, "top": 88, "height": 56,
        "font_size": 56, "line_height": 56,
    },
    "subtitle": {
        "sel": ".sup__subtitle",
        "text": "Ad Inventory is the shelf space, and Offerings are the"
                " products planners can select.",
        # 88 title top + 56 title height + 8 header gap.
        "left": 63, "top": 152, "height": 56,
        "font_size": 36, "line_height": 56,
    },
    "art_store": {
        "sel": ".sup__art--store",
        "left": 87, "top": 343, "width": 369.957, "height": 296,
        "src": "supermarket-store.svg",
    },
    "art_shelves": {
        "sel": ".sup__art--shelves",
        "left": 704, "top": 343, "width": 309.4005, "height": 312.8754,
        "src": "supermarket-shelves.svg",
    },
    "art_produce": {
        "sel": ".sup__art--produce",
        "left": 1296, "top": 343, "width": 333.7107, "height": 299,
        "src": "supermarket-produce.png",
    },
    # Business labels, Figma 638:59442/59441/59443. center_x is the midpoint
    # of the drawing above, which is also where Figma centres its text box.
    "label_store": {
        "sel": ".sup__label--store",
        "text": "Disney Advertising",
        "center_x": 271.9785, "top": 798, "height": 40,
        "font_size": 40, "line_height": 40,
    },
    "label_shelves": {
        "sel": ".sup__label--shelves",
        "text": "Ad Inventory",
        "center_x": 858.7003, "top": 798, "height": 40,
        "font_size": 40, "line_height": 40,
    },
    "label_produce": {
        "sel": ".sup__label--produce",
        "text": "Ad Offerings",
        "center_x": 1462.8554, "top": 798, "height": 40,
        "font_size": 40, "line_height": 40,
    },
    # Small grey category labels, Figma 639:61399/61397/61401.
    "label_small_store": {
        "sel": ".sup__label-small--store",
        "text": "Store",
        "center_x": 271.9785, "top": 747,
        "font_size": 32, "line_height": 38.4,
    },
    "label_small_shelves": {
        "sel": ".sup__label-small--shelves",
        "text": "Shelf space",
        "center_x": 858.7003, "top": 747,
        "font_size": 32, "line_height": 38.4,
    },
    "label_small_produce": {
        "sel": ".sup__label-small--produce",
        "text": "Product",
        "center_x": 1462.8554, "top": 747,
        "font_size": 32, "line_height": 38.4,
    },
    "logo": {
        "sel": ".sup__logo",
        "left": 1826, "top": 997, "width": 36, "height": 41,
    },
}

# Deck placement. DOM order is the running order, and ?slide=N is 1-based
# into it, so these travel together.
SLIDE_INDEX = 3
SLIDE_ID = "advertising-supermarket"
PREV_ID = "rate-card-right-price"
NEXT_ID = "upfront-scatter"
TOTAL_SLIDES = 11
SLIDE_QS = f"&slide={SLIDE_ID}"   # appendix: addressed by stable id

# Reveal contract, mirroring the constants in initAtlasSupermarket (app.js).
# The heading runs itself (title at 120ms, subtitle at 300ms); the three
# columns are presenter owned, one gesture each, left to right.
GROUP_ORDER = ["group-store", "group-shelves", "group-produce"]
REVEAL_ORDER = ["title", "subtitle"] + GROUP_ORDER
SEQUENCE_MS = 300
SETTLE_MS = 700

# One wait per presenter action. app.js swallows repeat gestures for
# ADVANCE_GUARD (400ms) after a step, so a real presenter beat is longer.
STEP_WAIT = 0.55

# A column arrives whole, so these three move as one and are never seen
# apart. Keys match the data-sup-reveal name of the column that owns them.
GROUP_MEMBERS = {
    "group-store": [
        ".sup__art--store", ".sup__label-small--store", ".sup__label--store",
    ],
    "group-shelves": [
        ".sup__art--shelves", ".sup__label-small--shelves",
        ".sup__label--shelves",
    ],
    "group-produce": [
        ".sup__art--produce", ".sup__label-small--produce",
        ".sup__label--produce",
    ],
}

# A column arrives with a fade and a small lift, in the brief's 350-450ms
# band, on the deck's shared ease-out curve. The lift lives on the column
# wrapper so the whole column moves as one.
FADE_MIN_MS, FADE_MAX_MS = 350, 450
LIFT = "matrix(1, 0, 0, 1, 0, 8)"

# The only artwork this slide is allowed to draw. Anything else (an arrow,
# a connector, a new badge) is a regression, so the list is exhaustive.
SLIDE_IMAGES = sorted([
    "atlas-brand-mark.svg",
    "supermarket-produce.png",
    "supermarket-shelves.svg",
    "supermarket-store.svg",
])

# Pixel-diff regions. "art" regions must match the export closely; "text"
# regions carry the substituted typeface and are reported, not asserted.
DIFF_REGIONS = [
    ("art: store",     "art",  (87, 343, 457, 639)),
    ("art: shelves",   "art",  (704, 343, 1014, 656)),
    ("art: produce",   "art",  (1296, 343, 1630, 642)),
    ("brand mark",     "art",  (1826, 997, 1862, 1038)),
    ("title",          "text", (63, 88, 1790, 144)),
    ("subtitle",       "text", (63, 152, 1810, 208)),
    ("small labels row", "text", (87, 745, 1630, 787)),
    ("labels row",     "text", (87, 795, 1630, 840)),
]
# Mean absolute per-channel error, 0..255. The illustrations are the same
# vector art rendered by two engines, so anti-aliasing along edges differs by
# a few levels; 3.0 catches a wrong, shifted, or missing asset while allowing
# that. Empty navy regions score near 0.
ART_MAE_LIMIT = 3.0

os.makedirs(OUT, exist_ok=True)
CHECKS = []


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}"
          f"{(' -- ' + detail) if detail else ''}")
    CHECKS.append((label, ok, detail))


def note(label, detail=""):
    print(f"  NOTE  {label}{(' -- ' + detail) if detail else ''}")


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def boot_chrome(port_http):
    port = _free_port()
    proc = subprocess.Popen([
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        f"--remote-debugging-port={port}",
        "--remote-allow-origins=*",
        f"--window-size={STAGE_W},{STAGE_H}",
        f"--user-data-dir={OUT}/profile",
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
        self.console = []

    def send(self, method, params=None):
        self.i += 1
        self.ws.send(json.dumps(
            {"id": self.i, "method": method, "params": params or {}}
        ))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("method") == "Log.entryAdded":
                e = msg["params"]["entry"]
                if e.get("level") in ("error", "warning"):
                    self.console.append(f"{e['level']}: {e.get('text', '')}")
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

    def key(self, key, code, vk):
        for t in ("keyDown", "keyUp"):
            self.send("Input.dispatchKeyEvent", {
                "type": t, "key": key, "code": code,
                "windowsVirtualKeyCode": vk, "nativeVirtualKeyCode": vk,
            })

    def click_stage(self):
        """One presenter click on the slide canvas."""
        self.eval("document.querySelector('.atlas-stage-wrap').click()")

    def shot_stage(self, path):
        """Render the stage at 1:1 and clip the capture to its 1920x1080 box."""
        box = self.eval("""(() => {
          const s = document.querySelector('.atlas-stage');
          const r = s.getBoundingClientRect();
          return {x: r.x + window.scrollX, y: r.y + window.scrollY,
                  w: r.width, h: r.height};
        })()""")
        r = self.send("Page.captureScreenshot", {
            "format": "png", "captureBeyondViewport": True,
            "clip": {"x": box["x"], "y": box["y"],
                     "width": box["w"], "height": box["h"], "scale": 1},
        })
        open(path, "wb").write(base64.b64decode(r["data"]))
        return box


def go(c, url):
    c.send("Page.enable")
    c.send("Runtime.enable")
    c.send("Log.enable")
    c.send("Network.enable")
    c.send("Network.setCacheDisabled", {"cacheDisabled": True})
    c.send("Page.navigate", {"url": url})
    for _ in range(80):
        if c.eval("!!document.querySelector('.atlas-slide.is-active')"):
            break
        time.sleep(0.1)
    c.eval("""(async () => {
      try { await document.fonts.ready; } catch (e) {}
      return true;
    })()""")
    time.sleep(0.5)


def sampled_replay(c):
    """Leave the slide, come back, and return the samples of that replay.

    A cold load competes with the document's own fonts and artwork for the
    main thread, which starves a 30ms sampler. Replaying on a warm page
    reads the run the audience actually sees, and it exercises the
    leave-and-return reset at the same time. The presenter's three columns
    are spent again on the way back, so the caller gets a full run.
    """
    # Leave first, then start sampling, so the first sample is the reset
    # state rather than whatever the presenter had already spent.
    for _ in range(len(GROUP_ORDER) + 2):
        if slide_id(c) != SLIDE_ID:
            break
        c.key("ArrowRight", "ArrowRight", 39)
        time.sleep(STEP_WAIT)
    c.eval("""(() => {
      window.__supSamples = [];
      clearInterval(window.__supTick);
      const tick = setInterval(window.__supSample, 30);
      window.__supTick = tick;
      setTimeout(() => clearInterval(tick), 8000);
      return true;
    })()""")
    c.key("ArrowLeft", "ArrowLeft", 37)
    time.sleep((SEQUENCE_MS + SETTLE_MS) / 1000 + 0.4)
    for _ in GROUP_ORDER:
        c.click_stage()
        time.sleep(STEP_WAIT)
    return json.loads(
        c.eval("JSON.stringify(window.__supSamples || [])") or "[]")


def first_seen_of(samples):
    """First timestamp at which each reveal target was seen revealed."""
    out = {}
    for smp in samples:
        for name in smp["shown"]:
            out.setdefault(name, smp["t"])
    return out


def pin_native_scale(c):
    """Defeat fit-to-viewport so the stage renders at exactly 1920x1080.

    fitStage() scales the stage to whatever the window can show. For a pixel
    comparison the stage has to be 1:1, so this neutralises the transform and
    the centring margins for the duration of the capture.
    """
    c.eval("""(() => {
      let el = document.getElementById('qa-native-scale');
      if (!el) {
        el = document.createElement('style');
        el.id = 'qa-native-scale';
        document.head.appendChild(el);
      }
      el.textContent = `
        .atlas-stage-wrap { padding: 0 !important; display: block !important;
                            overflow: visible !important; }
        .atlas-stage { transform: none !important; margin: 0 !important; }
        /* Settle the entrance so geometry is read from the final state,
           not from part-way through the reveal's translateY. */
        .atlas-slide--supermarket [data-sup-reveal] {
          opacity: 1 !important;
          transform: none !important;
          transition: none !important;
        }
      `;
      return true;
    })()""")
    time.sleep(0.3)


def slide_id(c):
    return c.eval(
        "document.querySelector('.atlas-slide.is-active')"
        "?.dataset.atlasSlideId || null"
    )


def measure(c):
    """Read every tracked box in stage coordinates."""
    spec = {k: v["sel"] for k, v in FIGMA.items()}
    return c.eval(f"""(() => {{
      const spec = {json.dumps(spec)};
      const stage = document.querySelector('.atlas-stage')
                            .getBoundingClientRect();
      const out = {{}};
      for (const [key, sel] of Object.entries(spec)) {{
        const el = document.querySelector(
          '.atlas-slide--supermarket ' + sel
        );
        if (!el) {{ out[key] = null; continue; }}
        const r = el.getBoundingClientRect();
        const cs = getComputedStyle(el);
        out[key] = {{
          left: r.left - stage.left, top: r.top - stage.top,
          width: r.width, height: r.height,
          centerX: r.left - stage.left + r.width / 2,
          text: (el.textContent || '').trim(),
          fontSize: parseFloat(cs.fontSize),
          lineHeight: parseFloat(cs.lineHeight),
          color: cs.color,
          fontWeight: cs.fontWeight,
          src: el.getAttribute('src'),
          naturalW: el.naturalWidth || null,
          naturalH: el.naturalHeight || null,
          complete: el.complete === undefined ? null : el.complete,
        }};
      }}
      return out;
    }})()""")


def mae(a, b):
    return float(np.mean(np.abs(a.astype(np.int16) - b.astype(np.int16))))


def main():
    port_http = _free_port()
    server = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port_http)],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(60):
        try:
            urllib.request.urlopen(
                f"http://127.0.0.1:{port_http}/", timeout=0.5
            ).read()
            break
        except Exception:
            time.sleep(0.1)
    else:
        server.terminate()
        raise RuntimeError("static server failed to boot")

    url = f"http://127.0.0.1:{port_http}/?section=atlas"
    proc, port = boot_chrome(port_http)
    try:
        c = CDP(port)

        # ---- Deck placement ------------------------------------------------
        print("\n[placement]")
        go(c, url + SLIDE_QS)
        check("?slide=advertising-supermarket opens the supermarket slide",
              slide_id(c) == SLIDE_ID, f"id={slide_id(c)}")

        # 2026-09-22: this section moved to the appendix. It is no longer part
        # of the numbered main run, so placement is now asserted as "off the
        # run but still reachable by its stable id" rather than "third slide".
        order = c.eval(
            "[...document.querySelectorAll('.atlas-slide')].filter(s => !s.hasAttribute('data-atlas-appendix'))"
            ".map(s => s.dataset.atlasSlideId)"
        )
        check("it is held out of the main run",
              SLIDE_ID not in order, json.dumps(order))
        check("the main run is the expected eleven slides",
              len(order) == TOTAL_SLIDES and len(set(order)) == TOTAL_SLIDES,
              f"{len(order)} slides")
        check("it is marked as an appendix section",
              c.eval(f"""(() => {{
                const s = document.querySelector('[data-atlas-slide-id="{SLIDE_ID}"]');
                return s.hasAttribute('data-atlas-appendix')
                  && !s.hasAttribute('data-atlas-slide');
              }})()"""))
        check("it carries an appendix label rather than a slide number",
              c.eval(f"""(() => {{
                const s = document.querySelector('[data-atlas-slide-id="{SLIDE_ID}"]');
                return (s.getAttribute('aria-label') || '').startsWith('Appendix');
              }})()"""))

        # Reachable with the deck's own controls, not just a deep link. The
        # two slides before it own no presenter gestures, so it is two
        # ArrowRights from the cover.
        go(c, url)
        for _ in range(2):
            c.key("ArrowRight", "ArrowRight", 39)
            time.sleep(0.5)
        check("two ArrowRights from the cover land on it",
              slide_id(c) == SLIDE_ID, f"id={slide_id(c)}")
        # Forward off the slide takes its three columns first.
        for _ in range(4):
            c.key("ArrowRight", "ArrowRight", 39)
            time.sleep(STEP_WAIT)
        check("forward off the last column reaches the next slide",
              slide_id(c) == NEXT_ID, f"id={slide_id(c)}")
        c.key("ArrowLeft", "ArrowLeft", 37)
        time.sleep(0.5)
        check("ArrowLeft from the next slide comes back to it",
              slide_id(c) == SLIDE_ID, f"id={slide_id(c)}")

        # ---- Geometry ------------------------------------------------------
        print("\n[geometry vs Figma 620:20510]")
        go(c, url + SLIDE_QS)
        pin_native_scale(c)

        stage = c.eval("""(() => {
          const r = document.querySelector('.atlas-stage')
                            .getBoundingClientRect();
          return {w: r.width, h: r.height};
        })()""")
        check("stage renders at the native 1920x1080",
              abs(stage["w"] - STAGE_W) < 0.5 and abs(stage["h"] - STAGE_H) < 0.5,
              f"{stage['w']}x{stage['h']}")

        m = measure(c)
        missing = [k for k, v in m.items() if v is None]
        check("every element is present", not missing, json.dumps(missing))
        if missing:
            return

        for key, want in FIGMA.items():
            got = m[key]
            probs = []
            # 1px absorbs the export's whole-pixel rounding and subpixel
            # text layout; anything larger is a real placement error.
            tol = 1.0
            for prop, gk in (("left", "left"), ("top", "top"),
                             ("width", "width"), ("height", "height"),
                             ("center_x", "centerX")):
                if prop in want:
                    d = got[gk] - want[prop]
                    if abs(d) > tol:
                        probs.append(f"{prop} {got[gk]:.2f} vs {want[prop]}"
                                     f" (off {d:+.2f})")
            for prop, gk in (("font_size", "fontSize"),
                             ("line_height", "lineHeight")):
                if prop in want and abs(got[gk] - want[prop]) > 0.5:
                    probs.append(f"{prop} {got[gk]} vs {want[prop]}")
            if "text" in want and got["text"] != want["text"]:
                probs.append(f"copy {got['text']!r}")
            if "src" in want:
                if want["src"] not in (got["src"] or ""):
                    probs.append(f"src {got['src']!r}")
                if not got["complete"] or not got["naturalW"]:
                    probs.append("asset did not load")
                # An <img> whose box differs from the file's own aspect
                # ratio is being stretched.
                elif got["naturalW"] and got["naturalH"]:
                    want_ar = got["naturalW"] / got["naturalH"]
                    got_ar = got["width"] / got["height"]
                    if abs(want_ar - got_ar) > 0.01:
                        probs.append(
                            f"stretched: box AR {got_ar:.4f} vs file"
                            f" {want_ar:.4f}")
            check(f"{key} matches Figma", not probs, "; ".join(probs))

        colors = {k: m[k]["color"] for k in
                  ("title", "subtitle", "label_store", "label_shelves",
                   "label_produce")}
        check("title, subtitle, and business labels are Figma white",
              all(v == "rgb(255, 255, 255)" for v in colors.values()),
              json.dumps(colors))

        small_colors = {k: m[k]["color"] for k in
                        ("label_small_store", "label_small_shelves",
                         "label_small_produce")}
        check("small category labels render in the Figma gray"
              " (color/gray/100, #51585B)",
              all(v == "rgb(81, 88, 91)" for v in small_colors.values()),
              json.dumps(small_colors))

        weights = {k: m[k]["fontWeight"] for k in
                   ("title", "subtitle", "label_store",
                    "label_small_store", "label_small_shelves",
                    "label_small_produce")}
        check("text renders at the Figma heavy weight",
              all(v == "900" for v in weights.values()), json.dumps(weights))

        panel = c.eval("""(() => {
          const s = document.querySelector('.atlas-slide--supermarket');
          const d = document.querySelector('.atlas-deck');
          const cs = getComputedStyle(s);
          return {bg: cs.backgroundColor, radius: cs.borderTopLeftRadius,
                  canvas: getComputedStyle(d).backgroundColor};
        })()""")
        # The shared presentation canvas sits behind every slide so the
        # stage's 40px radius has something to be a corner against.
        check("navy panel, 40px radius, presentation canvas behind it",
              panel["bg"] == "rgb(2, 0, 36)"
              and panel["radius"] == "40px"
              and panel["canvas"] == "rgb(30, 30, 30)",
              json.dumps(panel))

        overflow = c.eval("""(() => {
          const root = document.querySelector('.atlas-slide--supermarket');
          const r = root.getBoundingClientRect();
          const bad = [];
          for (const el of root.querySelectorAll('.sup *')) {
            const b = el.getBoundingClientRect();
            if (!b.width && !b.height) continue;
            if (b.left < r.left - 0.5 || b.top < r.top - 0.5 ||
                b.right > r.right + 0.5 || b.bottom > r.bottom + 0.5) {
              bad.push(el.className + ' ' + JSON.stringify({
                l: Math.round(b.left - r.left), t: Math.round(b.top - r.top),
                r: Math.round(b.right - r.left), b: Math.round(b.bottom - r.top),
              }));
            }
          }
          return bad;
        })()""")
        check("nothing overflows the slide", not overflow,
              json.dumps(overflow))

        clipped = c.eval("""(() => {
          const bad = [];
          for (const sel of ['.sup__title', '.sup__subtitle', '.sup__label',
                              '.sup__label-small']) {
            for (const el of document.querySelectorAll(
              '.atlas-slide--supermarket ' + sel
            )) {
              if (el.scrollWidth > Math.ceil(el.clientWidth) + 1) {
                bad.push(sel + ' ' + el.scrollWidth + '>' + el.clientWidth);
              }
            }
          }
          return bad;
        })()""")
        check("no text is clipped", not clipped, json.dumps(clipped))

        one_line = c.eval("""(() => {
          const out = {};
          const sels = [
            ['title', '.sup__title'], ['subtitle', '.sup__subtitle'],
            ['label_store', '.sup__label--store'],
            ['label_shelves', '.sup__label--shelves'],
            ['label_produce', '.sup__label--produce'],
            ['label_small_store', '.sup__label-small--store'],
            ['label_small_shelves', '.sup__label-small--shelves'],
            ['label_small_produce', '.sup__label-small--produce'],
          ];
          for (const [k, sel] of sels) {
            const el = document.querySelector(
              '.atlas-slide--supermarket ' + sel
            );
            out[k] = el.getClientRects().length;
          }
          return out;
        })()""")
        check("title, subtitle, and all six labels stay on one line each"
              " at the native viewport (Disney Advertising in particular)",
              all(v == 1 for v in one_line.values()), json.dumps(one_line))

        # ---- Small/main label baseline + centring geometry -----------------
        # Every assertion here reads getBoundingClientRect() directly rather
        # than trusting the FIGMA dict, because the requirement is internal
        # consistency ("these three columns must never drift apart"), not
        # just an individual match to Figma.
        print("\n[small + main label alignment]")
        label_geo = c.eval("""(() => {
          const stage = document.querySelector('.atlas-stage')
                                .getBoundingClientRect();
          const mainSel = ['.sup__label--store', '.sup__label--shelves',
                            '.sup__label--produce'];
          const smallSel = ['.sup__label-small--store',
                             '.sup__label-small--shelves',
                             '.sup__label-small--produce'];
          const artSel = ['.sup__art--store', '.sup__art--shelves',
                           '.sup__art--produce'];
          const countOf = sel => document.querySelectorAll(
            '.atlas-slide--supermarket ' + sel
          ).length;
          const rectOf = sel => {
            const el = document.querySelector(
              '.atlas-slide--supermarket ' + sel
            );
            if (!el) return null;
            const r = el.getBoundingClientRect();
            return {
              top: r.top - stage.top, bottom: r.bottom - stage.top,
              left: r.left - stage.left, right: r.right - stage.left,
              centerX: r.left - stage.left + r.width / 2,
            };
          };
          return {
            mainCounts: mainSel.map(countOf),
            smallCounts: smallSel.map(countOf),
            main: mainSel.map(rectOf),
            small: smallSel.map(rectOf),
            art: artSel.map(rectOf),
          };
        })()""")

        check("each business label (Disney Advertising / Ad Inventory /"
              " Ad Offerings) exists exactly once",
              label_geo["mainCounts"] == [1, 1, 1],
              json.dumps(label_geo["mainCounts"]))
        check("each category label (Store / Shelf space / Product)"
              " exists exactly once",
              label_geo["smallCounts"] == [1, 1, 1],
              json.dumps(label_geo["smallCounts"]))

        main_tops = [r["top"] for r in label_geo["main"]]
        main_bottoms = [r["bottom"] for r in label_geo["main"]]
        small_tops = [r["top"] for r in label_geo["small"]]
        small_bottoms = [r["bottom"] for r in label_geo["small"]]
        check("the three main-label top edges match within 1px"
              " (one shared horizontal baseline)",
              max(main_tops) - min(main_tops) <= 1.0,
              json.dumps(main_tops))
        check("the three main-label bottom edges match within 1px",
              max(main_bottoms) - min(main_bottoms) <= 1.0,
              json.dumps(main_bottoms))
        check("the three small-label top edges match within 1px"
              " (one shared horizontal baseline)",
              max(small_tops) - min(small_tops) <= 1.0,
              json.dumps(small_tops))
        check("the three small-label bottom edges match within 1px",
              max(small_bottoms) - min(small_bottoms) <= 1.0,
              json.dumps(small_bottoms))

        gaps = [m["top"] - s["top"] for m, s in
                zip(label_geo["main"], label_geo["small"])]
        check("the small-to-main vertical gap is identical across all"
              " three columns (top-edge to top-edge, immune to descenders)",
              max(gaps) - min(gaps) <= 1.0, json.dumps(gaps))

        center_offsets = [abs(m["centerX"] - s["centerX"]) for m, s in
                           zip(label_geo["main"], label_geo["small"])]
        check("each small label is horizontally centred over its main"
              " label within 1px",
              max(center_offsets) <= 1.0, json.dumps(center_offsets))

        group_offsets = [abs(m["centerX"] - a["centerX"]) for m, a in
                          zip(label_geo["main"], label_geo["art"])]
        check("each label group is centred beneath its illustration"
              " (left = the Figma drawing's own midpoint)",
              max(group_offsets) <= 1.0, json.dumps(group_offsets))

        column_bounds = [
            (87, 457), (704, 1014), (1296, 1630),
        ]
        overflow_cols = []
        for (lo, hi), m_, s_ in zip(column_bounds, label_geo["main"],
                                     label_geo["small"]):
            pad = 40  # labels are visually wider than their own illustration
            if (m_["left"] < lo - pad or m_["right"] > hi + pad
                    or s_["left"] < lo - pad or s_["right"] > hi + pad):
                overflow_cols.append({"col": [lo, hi], "main": m_, "small": s_})
        check("no label overflows its illustration column",
              not overflow_cols, json.dumps(overflow_cols))

        # ---- Uniform scaling ----------------------------------------------
        # Reload first: the geometry stage pins the stage to 1:1, and this
        # stage has to read the real fit-to-viewport transform.
        print("\n[uniform scaling]")
        go(c, url + SLIDE_QS)
        for w, h in ((1920, 1080), (1440, 900), (1280, 720), (2560, 1440)):
            c.send("Emulation.setDeviceMetricsOverride", {
                "width": w, "height": h, "deviceScaleFactor": 1,
                "mobile": False,
            })
            time.sleep(0.4)
            geo = c.eval("""(() => {
              const st = document.querySelector('.atlas-stage');
              const cs = getComputedStyle(st);
              const scale = parseFloat(
                st.style.getPropertyValue('--atlas-scale')
              );
              const sr = st.getBoundingClientRect();
              const rect = sel => {
                const r = document.querySelector(
                  '.atlas-slide--supermarket ' + sel
                ).getBoundingClientRect();
                return {x: (r.left - sr.left) / sr.width,
                        y: (r.top - sr.top) / sr.height,
                        w: r.width / sr.width};
              };
              return {scale, matrix: cs.transform,
                      ar: sr.width / sr.height,
                      arts: ['--store', '--shelves', '--produce']
                        .map(s => rect('.sup__art' + s)),
                      rows: new Set(
                        ['--store', '--shelves', '--produce'].map(
                          s => Math.round(rect('.sup__art' + s).y * 1000)
                        )
                      ).size};
            })()""")
            m2 = geo["matrix"]
            # matrix(a, b, c, d, e, f): uniform when a == d and b == c == 0.
            nums = [float(x) for x in
                    m2[m2.find("(") + 1:m2.find(")")].split(",")] \
                if m2.startswith("matrix(") else []
            uniform = (len(nums) == 6 and abs(nums[0] - nums[3]) < 1e-6
                       and abs(nums[1]) < 1e-6 and abs(nums[2]) < 1e-6)
            check(f"{w}x{h}: scales uniformly, keeps 16:9",
                  uniform and abs(geo["ar"] - 16 / 9) < 0.001,
                  f"scale={geo['scale']:.4f} ar={geo['ar']:.4f} {m2}")
            rel = geo["arts"]
            check(f"{w}x{h}: illustrations hold relative position and stay"
                  " in one row",
                  all(abs(r["x"] - e) < 0.0015 for r, e in
                      zip(rel, (87 / STAGE_W, 704 / STAGE_W, 1296 / STAGE_W)))
                  and all(abs(r["w"] - e) < 0.0015 for r, e in
                          zip(rel, (369.957 / STAGE_W, 309.4005 / STAGE_W,
                                    333.7107 / STAGE_W))),
                  json.dumps(rel))
        c.send("Emulation.clearDeviceMetricsOverride")
        time.sleep(0.3)

        # ---- Pixel diff ----------------------------------------------------
        print("\n[pixel diff vs Figma export]")
        go(c, url + SLIDE_QS)
        pin_native_scale(c)
        shot = os.path.join(OUT, "rendered-1920x1080.png")
        c.shot_stage(shot)
        img = Image.open(shot).convert("RGB")
        check("capture is a native 1920x1080 frame",
              img.size == (STAGE_W, STAGE_H), f"{img.size}")

        if not os.path.exists(REF):
            note("Figma export missing, pixel stage skipped",
                 f"re-export node 620:20510 as PNG scale 1 to {REF}")
        elif img.size != (STAGE_W, STAGE_H):
            note("capture is the wrong size, pixel stage skipped")
        else:
            ref = Image.open(REF).convert("RGB")
            check("Figma export is 1920x1080", ref.size == (STAGE_W, STAGE_H),
                  f"{ref.size}")
            a = np.asarray(img)
            b = np.asarray(ref.resize(img.size)) if ref.size != img.size \
                else np.asarray(ref)

            d = np.abs(a.astype(np.int16) - b.astype(np.int16))
            Image.fromarray(
                np.clip(d.sum(axis=2) * 3, 0, 255).astype(np.uint8)
            ).save(os.path.join(OUT, "diff-heatmap.png"))
            sbs = Image.new("RGB", (STAGE_W, STAGE_H * 2))
            sbs.paste(ref, (0, 0))
            sbs.paste(img, (0, STAGE_H))
            sbs.save(os.path.join(OUT, "figma-over-rendered.png"))

            print(f"  whole slide MAE {mae(a, b):.2f}/255")
            for name, kind, (x0, y0, x1, y1) in DIFF_REGIONS:
                e = mae(a[y0:y1, x0:x1], b[y0:y1, x0:x1])
                if kind == "art":
                    check(f"{name} matches the export"
                          f" (MAE {e:.2f} <= {ART_MAE_LIMIT})",
                          e <= ART_MAE_LIMIT, f"MAE={e:.2f}")
                else:
                    note(f"{name} MAE {e:.2f}",
                         "expected: Figma sets InspireTWDC, deck substitutes")

        # ---- Reveal, interaction and reset ---------------------------------
        # The heading runs itself; the three columns are the presenter's.
        # A column must never be caught arriving a piece at a time, and one
        # gesture must never spend two of them. Members are read with
        # checkVisibility({opacityProperty}), which accounts for the column
        # wrapper's opacity, so this is the drawing's and the captions' real
        # on-screen state rather than their own declared style. The sampler
        # is installed before the document exists because the heading run
        # starts on load.
        print("\n[reveal]")
        c.send("Emulation.clearDeviceMetricsOverride")
        c.send("Page.addScriptToEvaluateOnNewDocument", {"source": """
          window.__supMembers = %s;
          window.__supSamples = [];
          const sample = () => {
            const host = document.querySelector('[data-supermarket]');
            if (!host) return;
            const parts = [...host.querySelectorAll('[data-sup-reveal]')];
            const boxes = {};
            [...host.querySelectorAll('.sup__art, .sup__label, .sup__label-small')]
              .forEach((n, i) => {
                boxes[n.className + i] =
                  [n.offsetLeft, n.offsetTop, n.offsetWidth, n.offsetHeight];
              });
            const groups = {};
            for (const [name, sels] of Object.entries(window.__supMembers)) {
              const g = host.querySelector('[data-sup-reveal="' + name + '"]');
              if (!g) continue;
              const cs = getComputedStyle(g);
              groups[name] = {
                opacity: cs.opacity,
                transform: cs.transform,
                duration: cs.transitionDuration,
                delay: cs.transitionDelay,
                timing: cs.transitionTimingFunction,
                animation: cs.animationName,
                seen: sels.map(sel => {
                  const m = host.querySelector(sel);
                  return !!m && m.checkVisibility({
                    opacityProperty: true, visibilityProperty: true,
                  });
                }),
              };
            }
            window.__supSamples.push({
              t: Math.round(performance.now()),
              shown: parts.filter(x => x.classList.contains('is-revealed'))
                          .map(x => x.dataset.supReveal),
              phase: host.getAttribute('data-sup-phase'),
              boxes: boxes,
              groups: groups,
            });
          };
          window.__supSample = sample;
          /* Each run's stop timer holds its own interval id, so re-arming
             the sampler for a replay cannot be cancelled by the timer the
             page load set up. */
          const tick = setInterval(sample, 30);
          window.__supTick = tick;
          setTimeout(() => clearInterval(tick), 8000);
          document.addEventListener('DOMContentLoaded', sample);
        """ % json.dumps(GROUP_MEMBERS)})
        go(c, url + SLIDE_QS)
        time.sleep((SEQUENCE_MS + SETTLE_MS) / 1000 + 0.6)

        # The heading is up and the metaphor is not: this is the state the
        # room sees while the presenter introduces the slide.
        opening = c.eval("""(() => {
          const host = document.querySelector('[data-supermarket]');
          const vis = sel => {
            const n = host.querySelector(sel);
            return !!n && n.checkVisibility({
              opacityProperty: true, visibilityProperty: true});
          };
          return {
            phase: host.dataset.supPhase,
            step: host.dataset.supGroupStep,
            heading: [vis('.sup__title'), vis('.sup__subtitle')],
            columns: [...host.querySelectorAll('.sup__group')].map(
              g => [g.dataset.supReveal,
                    g.classList.contains('is-revealed'),
                    getComputedStyle(g).opacity]),
          };
        })()""")
        check("the slide opens on the heading with no columns spent",
              opening["phase"] == "complete" and opening["step"] == "0"
              and opening["heading"] == [True, True]
              and all(row[1] is False and row[2] == "0"
                      for row in opening["columns"]),
              json.dumps(opening))

        # Spend the three columns the way a presenter would.
        for _ in GROUP_ORDER:
            c.click_stage()
            time.sleep(STEP_WAIT)

        samples = c.eval("JSON.stringify(window.__supSamples || [])")
        samples = json.loads(samples) if samples else []
        check("the reveal was observed from the first frame",
              len(samples) > 20, f"{len(samples)} samples")
        counts = [len(x["shown"]) for x in samples]
        check("the slide starts with nothing revealed",
              bool(counts) and counts[0] == 0, f"first samples {counts[:3]}")
        check("stages only ever arrive, never disappear",
              all(b >= a for a, b in zip(counts, counts[1:])),
              json.dumps(counts[:24]))
        check("no gesture ever spends two columns at once",
              all(b - a <= 1 for a, b in zip(counts, counts[1:])),
              json.dumps(counts[:40]))

        first_seen = first_seen_of(samples)
        arrival = sorted(first_seen, key=lambda n: first_seen[n])
        check("heading first, then the three columns left to right",
              arrival == REVEAL_ORDER, json.dumps(arrival))

        structure = c.eval("""(() => {
          const host = document.querySelector('[data-supermarket]');
          const groups = [...host.querySelectorAll('.sup__group')];
          return {
            targets: [...host.querySelectorAll('[data-sup-reveal]')]
              .map(n => n.dataset.supReveal),
            nested: host.querySelectorAll(
              '[data-sup-reveal] [data-sup-reveal]').length,
            loose: host.querySelectorAll(
              '.sup__visual > .sup__art, .sup__visual > .sup__label,'
              + ' .sup__visual > .sup__label-small').length,
            contents: groups.map(g => [
              g.dataset.supReveal,
              g.querySelectorAll('.sup__art').length,
              g.querySelectorAll('.sup__label-small').length,
              g.querySelectorAll('.sup__label').length,
            ]),
          };
        })()""")
        check("each column is one reveal group holding its own drawing,"
              " category label and business label",
              structure["targets"] == REVEAL_ORDER
              and structure["nested"] == 0
              and structure["loose"] == 0
              and [row[0] for row in structure["contents"]] == GROUP_ORDER
              and all(row[1:] == [1, 1, 1] for row in structure["contents"]),
              json.dumps(structure))

        graphics = c.eval("""(() => {
          const slide = document.querySelector('.atlas-slide--supermarket');
          return {
            svg: slide.querySelectorAll('svg').length,
            arrowish: slide.querySelectorAll(
              '[class*="arrow"], [data-sup-arrow], [src*="arrow"]').length,
            imgs: [...slide.querySelectorAll('img')]
              .map(n => n.getAttribute('src').split('/').pop()).sort(),
          };
        })()""")
        check("the slide draws no arrow and no other new graphic",
              graphics["svg"] == 0 and graphics["arrowish"] == 0
              and graphics["imgs"] == SLIDE_IMAGES, json.dumps(graphics))

        if all(name in first_seen for name in REVEAL_ORDER):
            check("the heading leads the first column",
                  first_seen["title"] < first_seen["subtitle"]
                  < first_seen["group-store"], json.dumps(first_seen))

        laid_out = [x for x in samples
                    if any(b[2] for b in x["boxes"].values())]
        baseline = laid_out[0] if laid_out else None
        check("space is reserved before anything is revealed",
              baseline is not None and not baseline["shown"],
              f"first laid-out sample showed {baseline['shown'] if baseline else None}")
        drifted = [x["t"] for x in laid_out if x["boxes"] != baseline["boxes"]]
        check("no element moved during the reveal",
              not drifted, f"drifted at {drifted[:3]}")

        # The drawing and both captions of a column are read out of the live
        # render, so this fails if a column is dimmed-but-present at load, if
        # one member leads the others, or if a member is left behind.
        check("member visibility is read from the live render",
              c.eval("typeof Element.prototype.checkVisibility === 'function'"))
        split = [(x["t"], name, g["seen"]) for x in laid_out
                 for name, g in x["groups"].items() if len(set(g["seen"])) != 1]
        check("no piece of a column is ever on screen without the rest of it",
              not split, json.dumps(split[:3]))
        early_show = [(x["t"], name, g["seen"], x["shown"]) for x in laid_out
                      for name, g in x["groups"].items()
                      if any(g["seen"]) and name not in x["shown"]]
        check("a column's drawing and captions stay hidden until its own step",
              not early_show, json.dumps(early_show[:3]))
        settled = [x for x in laid_out
                   if x["t"] >= first_seen.get(GROUP_ORDER[-1], 0) + 200]
        unfinished = [(x["t"], name, g["seen"]) for x in settled
                      for name, g in x["groups"].items() if not all(g["seen"])]
        check("every column's drawing and captions are on screen once its"
              " fade has run",
              bool(settled) and not unfinished, json.dumps(unfinished[:3]))

        # The only movement allowed is the column's own 8px lift resolving
        # to none. Anything else is a scale, a slide or a bounce.
        strange = [(x["t"], name, g["transform"]) for x in laid_out
                   for name, g in x["groups"].items()
                   if g["transform"] != "none"
                   and not g["transform"].startswith("matrix(1, 0, 0, 1, 0, ")]
        check("a column only ever lifts straight up, never scales or slides",
              not strange, json.dumps(strange[:3]))
        # The resting offset is read from a throwaway column rather than a
        # live one: taking the class off a real column starts its transition
        # back, so an instant read would catch a mid-flight value.
        check("a column rests 8px low and settles at its final position",
              c.eval(f"""(() => {{
                const host = document.querySelector('[data-supermarket]');
                const settled = [...host.querySelectorAll('.sup__group')]
                  .every(g => getComputedStyle(g).transform === 'none');
                const probe = document.createElement('div');
                probe.className = 'sup__group';
                probe.setAttribute('data-sup-reveal', 'probe');
                host.querySelector('.sup__visual').appendChild(probe);
                const rest = getComputedStyle(probe).transform;
                const hidden = getComputedStyle(probe).opacity;
                probe.remove();
                return settled && rest === '{LIFT}' && hidden === '0';
              }})()"""))

        fades = c.eval("""(() => {
          const host = document.querySelector('[data-supermarket]');
          return Object.fromEntries(
            [...host.querySelectorAll('.sup__group')].map(g => {
              const cs = getComputedStyle(g);
              return [g.dataset.supReveal, {
                property: cs.transitionProperty,
                duration: cs.transitionDuration,
                delay: cs.transitionDelay,
                timing: cs.transitionTimingFunction,
                animation: cs.animationName,
              }];
            }));
        })()""")
        def ms_band(value):
            """Every leg of a transition shorthand, in milliseconds."""
            return [round(float(part.strip().rstrip("s")) * 1000)
                    for part in value.split(",")]

        check("every column fades and lifts on one clock, for"
              f" {FADE_MIN_MS}-{FADE_MAX_MS}ms, no delay and no keyframes",
              len(fades) == len(GROUP_ORDER)
              and all(sorted(p.strip() for p in v["property"].split(","))
                      == ["opacity", "transform"]
                      and set(ms_band(v["delay"])) == {0}
                      and v["animation"] == "none"
                      and len(set(ms_band(v["duration"]))) == 1
                      and all(FADE_MIN_MS <= d <= FADE_MAX_MS
                              for d in ms_band(v["duration"]))
                      for v in fades.values()), json.dumps(fades))
        check("the columns share the deck's ease-out curve",
              len(set(v["timing"] for v in fades.values())) == 1
              and all(v["timing"].startswith("cubic-bezier")
                      for v in fades.values()), json.dumps(fades))

        check("the run ends complete",
              c.eval("document.querySelector('[data-supermarket]')"
                     ".dataset.supPhase") == "complete")
        check("every column is on screen when the run ends",
              c.eval("""(() => {
                const host = document.querySelector('[data-supermarket]');
                return [...host.querySelectorAll('.sup__group')].every(
                  g => g.classList.contains('is-revealed')
                    && getComputedStyle(g).opacity === '1');
              })()"""))

        print("\n[interaction]")

        def column_state(c):
            return c.eval("""(() => {
              const host = document.querySelector('[data-supermarket]');
              const vis = sel => {
                const n = host.querySelector(sel);
                return !!n && n.checkVisibility({
                  opacityProperty: true, visibilityProperty: true});
              };
              return {
                active: document.querySelector(
                  '.atlas-slide.is-active').dataset.atlasSlideId,
                step: host.dataset.supGroupStep,
                shown: [...host.querySelectorAll('.sup__group.is-revealed')]
                  .map(g => g.dataset.supReveal),
                store: vis('.sup__art--store') && vis('.sup__label--store'),
                shelves: vis('.sup__art--shelves')
                  && vis('.sup__label--shelves'),
                produce: vis('.sup__art--produce')
                  && vis('.sup__label--produce'),
              };
            })()""")

        # Mouse, ArrowRight and Space have to walk the identical sequence.
        for label, step in (
            ("a click", lambda: c.click_stage()),
            ("ArrowRight", lambda: c.key("ArrowRight", "ArrowRight", 39)),
            ("Space", lambda: c.key(" ", "Space", 32)),
        ):
            go(c, url + SLIDE_QS)
            time.sleep((SEQUENCE_MS + SETTLE_MS) / 1000 + 0.4)
            seen = [column_state(c)]
            for _ in GROUP_ORDER:
                step()
                time.sleep(STEP_WAIT)
                seen.append(column_state(c))
            check(f"{label} opens with the three columns hidden",
                  seen[0]["step"] == "0" and seen[0]["shown"] == []
                  and not any(seen[0][k]
                              for k in ("store", "shelves", "produce")),
                  json.dumps(seen[0]))
            check(f"{label} reveals the store column first, whole and alone",
                  seen[1]["step"] == "1"
                  and seen[1]["shown"] == ["group-store"]
                  and (seen[1]["store"], seen[1]["shelves"],
                       seen[1]["produce"]) == (True, False, False),
                  json.dumps(seen[1]))
            check(f"{label} adds only the shelf space column next",
                  seen[2]["step"] == "2"
                  and seen[2]["shown"] == GROUP_ORDER[:2]
                  and (seen[2]["store"], seen[2]["shelves"],
                       seen[2]["produce"]) == (True, True, False),
                  json.dumps(seen[2]))
            check(f"{label} adds only the product column last",
                  seen[3]["step"] == "3" and seen[3]["shown"] == GROUP_ORDER
                  and all(seen[3][k]
                          for k in ("store", "shelves", "produce")),
                  json.dumps(seen[3]))
            check(f"{label} keeps the presenter on the slide throughout",
                  all(s["active"] == SLIDE_ID for s in seen),
                  json.dumps([s["active"] for s in seen]))

        # The slide gives the deck its gesture back once it has nothing left.
        c.click_stage()
        time.sleep(STEP_WAIT)
        check("the gesture after the last column advances the deck",
              slide_id(c) == NEXT_ID, f"id={slide_id(c)}")

        go(c, url + SLIDE_QS)
        time.sleep((SEQUENCE_MS + SETTLE_MS) / 1000 + 0.4)
        rapid = json.loads(c.eval("""(async () => {
          const wait = ms => new Promise(r => setTimeout(r, ms));
          const host = () => document.querySelector('[data-supermarket]');
          const wrap = document.querySelector('.atlas-stage-wrap');
          wrap.click();
          wrap.click();
          wrap.click();
          await wait(250);
          return JSON.stringify({
            step: host().dataset.supGroupStep,
            active: document.querySelector(
              '.atlas-slide.is-active').dataset.atlasSlideId,
          });
        })()"""))
        check("rapid clicking cannot skip or double-spend a column",
              rapid["step"] == "1" and rapid["active"] == SLIDE_ID,
              json.dumps(rapid))

        # A gesture during the heading run buys the heading, not a column.
        c.send("Page.navigate", {"url": url + SLIDE_QS + "&qa=mid-run"})
        time.sleep(0.25)
        early = json.loads(c.eval("""(async () => {
          const wait = ms => new Promise(r => setTimeout(r, ms));
          const host = () => document.querySelector('[data-supermarket]');
          const before = host().dataset.supPhase;
          document.querySelector('.atlas-stage-wrap').click();
          await wait(120);
          return JSON.stringify({
            before,
            phase: host().dataset.supPhase,
            step: host().dataset.supGroupStep,
            heading: [...host().querySelectorAll(
              '.sup__title.is-revealed, .sup__subtitle.is-revealed')].length,
            active: document.querySelector(
              '.atlas-slide.is-active').dataset.atlasSlideId,
          });
        })()"""))
        check("the click really did land during the heading run",
              early["before"] == "revealing", json.dumps(early))
        check("a click mid-heading finishes the heading and spends no column",
              early["phase"] == "complete" and early["heading"] == 2
              and early["step"] == "0" and early["active"] == SLIDE_ID,
              json.dumps(early))

        print("\n[reverse]")
        go(c, url + SLIDE_QS)
        time.sleep((SEQUENCE_MS + SETTLE_MS) / 1000 + 0.4)
        for _ in GROUP_ORDER:
            c.click_stage()
            time.sleep(STEP_WAIT)
        for want_step, want_shown in (
            ("2", GROUP_ORDER[:2]),
            ("1", GROUP_ORDER[:1]),
            ("0", []),
        ):
            c.key("ArrowLeft", "ArrowLeft", 37)
            time.sleep(STEP_WAIT)
            state = column_state(c)
            check(f"backward navigation gives back a whole column to step"
                  f" {want_step}",
                  state["active"] == SLIDE_ID and state["step"] == want_step
                  and state["shown"] == want_shown
                  and state["store"] == ("group-store" in want_shown)
                  and state["shelves"] == ("group-shelves" in want_shown)
                  and state["produce"] == ("group-produce" in want_shown),
                  json.dumps(state))
        c.key("ArrowLeft", "ArrowLeft", 37)
        time.sleep(0.5)
        check("backward past the first column leaves the slide",
              slide_id(c) == PREV_ID, f"id={slide_id(c)}")

        print("\n[reset]")
        go(c, url + SLIDE_QS)
        time.sleep((SEQUENCE_MS + SETTLE_MS) / 1000 + 0.4)
        for _ in GROUP_ORDER:
            c.click_stage()
            time.sleep(STEP_WAIT)
        c.key("ArrowRight", "ArrowRight", 39)
        time.sleep(0.5)
        state = c.eval("""(() => {
          const host = document.querySelector('[data-supermarket]');
          return {phase: host.dataset.supPhase,
                  step: host.dataset.supGroupStep,
                  shown: [...document.querySelectorAll(
                    '[data-sup-reveal].is-revealed')].length,
                  active: document.querySelector(
                    '.atlas-slide.is-active').dataset.atlasSlideId};
        })()""")
        check("leaving the slide clears the run",
              state["active"] == NEXT_ID and state["phase"] == "revealing"
              and state["step"] == "0" and state["shown"] == 0,
              json.dumps(state))
        c.key("ArrowLeft", "ArrowLeft", 37)
        time.sleep((SEQUENCE_MS + SETTLE_MS) / 1000 + 0.4)
        check("returning replays the heading and re-hides the columns",
              c.eval("""(() => {
                const host = document.querySelector('[data-supermarket]');
                return host.dataset.supPhase === 'complete'
                  && host.dataset.supGroupStep === '0'
                  && document.querySelectorAll(
                       '.sup__group.is-revealed').length === 0;
              })()"""))
        replay = sampled_replay(c)
        replay_first = first_seen_of(replay)
        check("the sequence replays in order when the presenter returns",
              sorted(replay_first, key=lambda n: replay_first[n])
              == REVEAL_ORDER, json.dumps(replay_first))
        check("nothing is on screen at the start of the replay",
              bool(replay) and not replay[0]["shown"],
              json.dumps(replay[0]["shown"] if replay else None))

        # A pending heading line must not paint onto another slide. Going
        # backward is the way out mid-heading: a forward gesture would be
        # claimed by the slide to finish the heading instead of leaving.
        # The page is already warm here, so stepping off and back on is a
        # reliable way to catch the heading run in flight.
        left = json.loads(c.eval("""(async () => {
          const wait = ms => new Promise(r => setTimeout(r, ms));
          const host = () => document.querySelector('[data-supermarket]');
          const active = () => document.querySelector(
            '.atlas-slide.is-active').dataset.atlasSlideId;
          const key = k => document.dispatchEvent(
            new KeyboardEvent('keydown', {key: k, bubbles: true}));
          /* Any columns still spent are given back before the slide is,
             so step back until the deck has actually moved off it. */
          for (let i = 0; i < 6 && active() === 'advertising-supermarket';
               i += 1) {
            key('ArrowLeft');
            await wait(450);
          }
          key('ArrowRight');
          await wait(150);
          const midRun = document.querySelectorAll(
            '[data-sup-reveal].is-revealed').length;
          const phase = host().dataset.supPhase;
          key('ArrowLeft');
          await wait(250);
          return JSON.stringify({midRun, phase, active: active()});
        })()"""))
        check("the deck leaves while the heading is still arriving",
              left["phase"] == "revealing" and left["midRun"] < 2
              and left["active"] == PREV_ID, json.dumps(left))
        time.sleep((SEQUENCE_MS + SETTLE_MS) / 1000 + 0.4)
        check("a pending heading line cannot fire onto another slide",
              c.eval("[...document.querySelectorAll("
                     "'[data-sup-reveal].is-revealed')].length") == 0
              and c.eval("document.querySelector('[data-supermarket]')"
                         ".dataset.supPhase") == "revealing")

        print("\n[reduced motion]")
        c.send("Emulation.setEmulatedMedia", {"features": [
            {"name": "prefers-reduced-motion", "value": "reduce"}]})
        go(c, url + SLIDE_QS)
        time.sleep((SEQUENCE_MS + SETTLE_MS) / 1000 + 0.6)
        check("reduced motion is in effect",
              c.eval("matchMedia('(prefers-reduced-motion: reduce)').matches"))
        rm_fades = c.eval("""(() => {
          const host = document.querySelector('[data-supermarket]');
          return Object.fromEntries(
            [...host.querySelectorAll('.sup__group')].map(g => {
              const cs = getComputedStyle(g);
              return [g.dataset.supReveal, {
                property: cs.transitionProperty,
                duration: cs.transitionDuration,
                delay: cs.transitionDelay,
                timing: cs.transitionTimingFunction,
                transform: cs.transform,
              }];
            }));
        })()""")
        check("reduced motion drops the lift and keeps a short opacity fade",
              all(v["property"] == "opacity" and v["duration"] == "0.12s"
                  and v["timing"] == "linear" and v["delay"] in ("0s", "0ms")
                  and v["transform"] == "none"
                  for v in rm_fades.values()), json.dumps(rm_fades))
        rm_samples = sampled_replay(c)
        rm_first = first_seen_of(rm_samples)
        check("reduced motion still brings the columns in one at a time,"
              " left to right",
              sorted(rm_first, key=lambda n: rm_first[n]) == REVEAL_ORDER,
              json.dumps(rm_first))
        rm_counts = [len(x["shown"]) for x in rm_samples]
        check("reduced motion still spends one column per gesture",
              all(b - a <= 1 for a, b in zip(rm_counts, rm_counts[1:])),
              json.dumps(rm_counts[:40]))
        rm_laid_out = [x for x in rm_samples
                       if any(b[2] for b in x["boxes"].values())]
        rm_split = [(x["t"], name, g["seen"]) for x in rm_laid_out
                    for name, g in x["groups"].items()
                    if len(set(g["seen"])) != 1]
        check("reduced motion still brings each column in whole",
              not rm_split, json.dumps(rm_split[:3]))
        rm_early = [(x["t"], name, g["seen"], x["shown"]) for x in rm_laid_out
                    for name, g in x["groups"].items()
                    if any(g["seen"]) and name not in x["shown"]]
        check("reduced motion keeps each column hidden until its own step",
              not rm_early, json.dumps(rm_early[:3]))
        c.send("Emulation.setEmulatedMedia", {"features": []})

        # ---- Console -------------------------------------------------------
        print("\n[console]")
        assets = c.eval("""(() => {
          const bad = [];
          for (const im of document.querySelectorAll(
            '.atlas-slide--supermarket img'
          )) {
            if (!im.complete || !im.naturalWidth) bad.push(im.src);
          }
          return bad;
        })()""")
        check("every slide asset loaded", not assets, json.dumps(assets))
        errs = [e for e in c.console if "favicon" not in e.lower()]
        check("no console errors or warnings", not errs,
              " | ".join(errs[:5]))

    finally:
        proc.kill()
        server.terminate()

    failed = [c_ for c_ in CHECKS if not c_[1]]
    print(f"\n{len(CHECKS) - len(failed)}/{len(CHECKS)} passed")
    print(f"artifacts in {OUT}")
    if failed:
        print("\nFAILED:")
        for label, _, detail in failed:
            print(f"  - {label}{(' -- ' + detail) if detail else ''}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
