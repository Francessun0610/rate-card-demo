#!/usr/bin/env python3
"""
qa_same_ad_rate_slide.py - Atlas deck slide 6 QA.

Slide 6, "Same product. Different applicable rate.", is authored from Figma
node 739:6035. One ad on the left, a connector that splits in the middle,
and the same ad priced two ways on the right.

What this suite locks down:

  - Placement. Exactly one such slide, sixth, sitting between the deal-type
    explainer and the media-plan walkthrough, deck fifteen long.
  - Copy, including the left label reading "Ad", and the absence
    of the takeaway, OR label, cards and divider the brief rules out.
  - Geometry against the Figma frame at the native 1920x1080 stage.
  - The connector. It has to be real vector segments, not the flat export,
    and they have to arrive in the order that makes the split legible: the
    first line reaches the junction, then the spine opens, then both
    branches run out together, then both arrowheads.
  - Both results arriving together, each as one whole group, so a shelf is
    never up without its rate.
  - No layout shift, at any point in a four-second run.
  - Interaction. A gesture mid-run completes the slide without advancing;
    the next one advances. Arrow keys are never taken. Double clicks and
    key repeat cannot skip a slide.
  - Timer cleanup and reset on re-entry.
  - Reduced motion, which keeps the order but drops drawing and travel.
  - Rounded corners and the shared #1E1E1E canvas at three viewports.

Timings mirror the SEQUENCE in initAtlasSameAdRate (app.js).
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
OUT = "/tmp/qa_same_ad_rate_slide"
SLIDE_INDEX = 5
SLIDE_ID = "same-ad-different-rate"
TOTAL_SLIDES = 12

# The slide opens on the question and answers it in three presenter clicks.
STAGES = ["branch", "upfront", "scatter"]
# What each click's own timeline costs, matched to app.js and styles.css.
RUNTIME_MS = {"branch": 615, "upfront": 450, "scatter": 2935}
RUNTIME_REDUCED_MS = {"branch": 200, "upfront": 200, "scatter": 1370}
SETTLE_MS = 400

# Inside click 3: the shelf takes 450ms, then it holds empty, then the
# pumpkins run, then the rate takes a beat 150ms after the last one lands.
FILL_HOLD_MS = 1050
FILL_DURATION_MS = 360
FILL_STAGGER_MS = 125
FILL_RATE_MS = 2685
PUMPKINS = 10
# Bottom of the shelf upward, reordered wherever a strictly bottom-up run
# would send a pumpkin across one already placed.
ENTRY_ORDER = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
# Where each one belongs, in the shelf's own units.
HOMES = {
    1: (58.25, 257.55), 2: (173.65, 195.70), 3: (135.55, 213.75),
    4: (176.65, 143.45), 5: (99.15, 188.95), 6: (53.95, 212.65),
    7: (166.95, 106.15), 8: (127.65, 125.45), 9: (124.75, 79.95),
    10: (88.95, 101.25),
}
ORIGIN_X = -50.81
STAGE_RADIUS = 40
CANVAS = "rgb(30, 30, 30)"

SLIDE_BG = "rgb(2, 0, 36)"

TITLE = "Same product. Different applicable rate."
SUBTITLE = ("The price depends on the buyer and the deal,"
            " not only on the product.")
COPY = ["Same product. Different applicable rate.",
        "The price depends on the buyer and the deal, not only on the product.",
        "Ad", "$20 CPM", "FY27 Upfront", "Reserved placement",
        "$28 CPM", "Scatter", "Available placement",
        "*Rates shown are illustrative."]

# Figma 739:6035 geometry, in native stage pixels: left, top, width, height.
FIGMA = {
    ".sar__header": (63, 88, 1828, 120),
    ".sar__pumpkin": (285.696, 531.792, 162.02, 134.805),
    ".sar__wire": (492.288, 443.88, 362.161, 417.228),
    ".sar__shelf--upfront": (909.49, 267, 211.964, 305.184),
    ".sar__shelf--scatter": (905.26, 676.82, 211.964, 305.184),
    ".sar__copy--upfront .sar__rate": (1190, 341, None, 48),
    ".sar__copy--upfront .sar__deal": (1190, 393, None, None),
    ".sar__copy--upfront .sar__placement": (1190, 437.66, None, None),
    ".sar__copy--scatter .sar__rate": (1184, 759, None, 48),
    ".sar__copy--scatter .sar__deal": (1190, 808, None, None),
    ".sar__copy--scatter .sar__placement": (1190, 850, None, None),
    ".sar__footnote": (63, 982, None, None),
    ".sar__logo": (1826, 997, 36, 41),
}

CHECKS = []


def is_canvas(px):
    """True for the presentation canvas, allowing for the shared shadow."""
    r, g, b = px
    return r == g == b and abs(r - 30) <= 8


def check(label, ok, detail=""):
    CHECKS.append((label, bool(ok), detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f" -- {detail}" if detail else ""))
    return bool(ok)


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class CDP:
    def __init__(self, port):
        import websocket
        tabs = json.loads(
            urllib.request.urlopen(f"http://127.0.0.1:{port}/json").read()
        )
        target = next(t for t in tabs if t.get("type") == "page")
        self.ws = websocket.create_connection(
            target["webSocketDebuggerUrl"], max_size=200 * 1024 * 1024
        )
        self.id = 0
        self.logs = []
        self.send("Runtime.enable")
        self.send("Page.enable")
        self.send("Log.enable")

    def send(self, method, params=None):
        self.id += 1
        self.ws.send(json.dumps({
            "id": self.id, "method": method, "params": params or {},
        }))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("method") == "Log.entryAdded":
                entry = msg["params"]["entry"]
                if entry.get("level") in ("error", "warning"):
                    self.logs.append(entry.get("text", ""))
            if msg.get("method") == "Runtime.exceptionThrown":
                self.logs.append("exception")
            if msg.get("id") == self.id:
                return msg.get("result", {})

    def eval(self, expression):
        out = self.send("Runtime.evaluate", {
            "expression": expression, "returnByValue": True,
            "awaitPromise": True,
        })
        return out.get("result", {}).get("value")

    def key(self, key, code, code_num):
        for kind in ("keyDown", "keyUp"):
            self.send("Input.dispatchKeyEvent", {
                "type": kind, "key": key, "code": code,
                "windowsVirtualKeyCode": code_num,
                "nativeVirtualKeyCode": code_num,
            })

    def click_stage(self):
        self.eval("document.querySelector('.atlas-stage-wrap').click()")

    def screenshot(self, path):
        data = self.send("Page.captureScreenshot", {"format": "png"})
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(base64.b64decode(data["data"]))


def boot_chrome(viewport, port_http, reduced=False, slide=SLIDE_INDEX):
    port = free_port()
    profile = f"/tmp/qa_sar_profile_{port}"
    subprocess.run(["rm", "-rf", profile], check=False)
    args = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile}",
        "--headless=new", "--remote-allow-origins=*", "--no-first-run",
        "--hide-scrollbars", "--force-device-scale-factor=1",
        f"--window-size={viewport[0]},{viewport[1]}",
    ]
    if reduced:
        args.append("--force-prefers-reduced-motion")
    args.append(f"http://127.0.0.1:{port_http}/?section=atlas&slide={slide}")
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=0.5)
            break
        except Exception:
            time.sleep(0.1)
    time.sleep(1.4)
    return proc, port


def go(c, url):
    c.send("Page.navigate", {"url": url})
    time.sleep(1.2)


def phase(c):
    return c.eval(
        "document.querySelector('[data-same-ad-rate]')"
        "?.getAttribute('data-sar-phase')"
    )


def slide_id(c):
    return c.eval(
        "document.querySelector('.atlas-slide.is-active')?.dataset.atlasSlideId"
    )


def stage_index(c):
    return int(c.eval("document.querySelector('[data-same-ad-rate]')"
                      "?.getAttribute('data-sar-stage') || 0"))


def click_through(c, upto=3, reduced=False):
    """Click the slide forward and let each stage finish."""
    runtime = RUNTIME_REDUCED_MS if reduced else RUNTIME_MS
    for name in STAGES[:upto]:
        c.click_stage()
        time.sleep(runtime[name] / 1000 + 0.25)


def stages(c):
    """Distinct stage names currently revealed, in document order."""
    return c.eval("""(() => {
      const seen = [];
      document.querySelectorAll('[data-sar-reveal].is-revealed')
        .forEach(n => {
          if (!seen.includes(n.dataset.sarReveal)) seen.push(n.dataset.sarReveal);
        });
      return seen;
    })()""")


def install_sampler(c):
    """Record the reveal timeline from before the document exists."""
    c.send("Page.addScriptToEvaluateOnNewDocument", {"source": """
      window.__sarSamples = [];
      const sample = () => {
        const host = document.querySelector('[data-same-ad-rate]');
        if (!host) return;
        const shown = [];
        host.querySelectorAll('[data-sar-reveal].is-revealed').forEach(n => {
          if (!shown.includes(n.dataset.sarReveal)) shown.push(n.dataset.sarReveal);
        });
        const boxes = {};
        host.querySelectorAll(
          '.sar__title, .sar__subtitle, .sar__pumpkin, .sar__source-label,'
          + ' .sar__wire, .sar__shelf, .sar__rate, .sar__deal,'
          + ' .sar__placement, .sar__footnote').forEach((n, i) => {
            boxes[i] = [n.offsetLeft, n.offsetTop, n.offsetWidth, n.offsetHeight];
          });
        window.__sarSamples.push({
          t: Math.round(performance.now()),
          shown: shown,
          phase: host.getAttribute('data-sar-phase'),
          boxes: boxes,
        });
      };
      const tick = setInterval(sample, 30);
      setTimeout(() => clearInterval(tick), 12000);
      document.addEventListener('DOMContentLoaded', sample);
    """})


def pin_stage_scale(c):
    """Draw the deck at 1:1 so measurements are in the slide's own units.

    This only fixes the scale. Anything being revealed still reveals, which
    is what the timing tests need.
    """
    c.eval("""(() => {
      const style = document.createElement('style');
      style.textContent = `.atlas-stage{--atlas-scale:1 !important;margin:0 !important}
        .atlas-stage-wrap{padding:0 !important;overflow:visible !important}
        .atlas-deck{position:absolute !important}`;
      document.head.appendChild(style);
    })()""")
    time.sleep(0.4)


def pin_native_scale(c):
    """As above, but also force the slide to its finished state.

    Used by the geometry pass, which measures where everything ends up and
    so must not wait on, or be moved by, the reveal.
    """
    pin_stage_scale(c)
    c.eval("""(() => {
      const style = document.createElement('style');
      style.textContent = `.atlas-slide--same-ad-rate [data-sar-reveal]{
          opacity:1 !important; transform:none !important;
          stroke-dashoffset:0 !important; transition:none !important;
          animation:none !important; }`;
      document.head.appendChild(style);
    })()""")
    time.sleep(0.4)


# ---------------------------------------------------------------- placement
def run_placement(c, url):
    print("\n[placement]")
    go(c, url + f"&slide={SLIDE_INDEX}")
    check("slide 6 is the same-ad-different-rate slide",
          slide_id(c) == SLIDE_ID, f"id={slide_id(c)}")

    order = c.eval(
        "[...document.querySelectorAll('.atlas-slide')].filter(s => !s.hasAttribute('data-atlas-appendix'))"
        ".map(s => s.dataset.atlasSlideId)"
    )
    check("the slide exists exactly once",
          order.count(SLIDE_ID) == 1, f"{order.count(SLIDE_ID)} copies")
    i = order.index(SLIDE_ID)
    check("it follows the deal-type explainer",
          order[i - 1] == "upfront-scatter", f"before={order[i - 1]}")
    check("the next slide is the media plan explainer",
          order[i + 1] == "core-planning-media-plan",
          f"after={order[i + 1]}")
    check("no existing slide was dropped",
          len(order) == TOTAL_SLIDES and len(set(order)) == TOTAL_SLIDES,
          f"{len(order)} slides")

    labelled = c.eval("""(() => {
      const s = document.querySelector('.atlas-slide.is-active');
      return {ordinal: s.dataset.atlasSlide, label: s.getAttribute('aria-label'),
              id: s.id};
    })()""")
    check(f"it registers as slide {SLIDE_INDEX} of {TOTAL_SLIDES}",
          labelled["ordinal"] == str(SLIDE_INDEX)
          and labelled["label"] == f"Slide {SLIDE_INDEX} of {TOTAL_SLIDES}: {TITLE}",
          json.dumps(labelled))
    check("it keeps a stable semantic element id",
          labelled["id"] == "atlas-slide-same-ad-different-rate", labelled["id"])

    copy = c.eval("""(() => {
      const s = document.querySelector('.atlas-slide.is-active');
      return {
        lines: [...s.querySelectorAll('.sar__title, .sar__subtitle,'
          + ' .sar__source-label, .sar__rate-value, .sar__deal,'
          + ' .sar__placement, .sar__footnote')]
          .map(n => n.textContent.replace(/\\s+/g, ' ').trim()),
        dashes: /[\\u2013\\u2014]/.test(s.textContent),
        text: s.textContent.replace(/\\s+/g, ' ').trim(),
      };
    })()""")
    check("every line matches the brief", copy["lines"] == COPY,
          json.dumps(copy["lines"]))
    # "Ad" on its own would match inside other words, so read the label.
    check("the left label reads exactly Ad",
          c.eval("""document.querySelector('.sar__source-label')
            .textContent.trim()""") == "Ad")
    check("no earlier wording of that label survives",
          "Same Ad" not in copy["text"]
          and "Same Offering" not in copy["text"]
          and "Same offering" not in copy["text"])
    check("no em or en dashes", not copy["dashes"])
    banned = [w for w in ("OR", "Takeaway", "takeaway")
              if f" {w} " in f" {copy['text']} "]
    check("no OR label or takeaway line", not banned, json.dumps(banned))
    check("no cards, borders or dividers around the groups",
          c.eval("""(() => {
            const s = document.querySelector('.atlas-slide--same-ad-rate');
            const cs = el => getComputedStyle(el);
            return [...s.querySelectorAll(
              '.sar__result, .sar__source, .sar__copy')].every(g => {
                const st = cs(g);
                return st.borderTopWidth === '0px'
                  && st.backgroundColor === 'rgba(0, 0, 0, 0)'
                  && st.boxShadow === 'none';
              });
          })()"""))


# ----------------------------------------------------------------- geometry
def run_geometry(c, url):
    print("\n[geometry vs Figma 739:6035]")
    go(c, url + f"&slide={SLIDE_INDEX}")
    pin_native_scale(c)

    stage = c.eval("""(() => {
      const r = document.querySelector('.atlas-stage').getBoundingClientRect();
      return {w: r.width, h: r.height};
    })()""")
    check("stage renders at the native 1920x1080",
          abs(stage["w"] - 1920) < 1 and abs(stage["h"] - 1080) < 1,
          json.dumps(stage))

    measured = json.loads(c.eval("""JSON.stringify((() => {
      const stage = document.querySelector('.atlas-stage')
                            .getBoundingClientRect();
      const out = {};
      %s.forEach(sel => {
        const el = document.querySelector('.atlas-slide--same-ad-rate ' + sel);
        if (!el) { out[sel] = null; return; }
        const r = el.getBoundingClientRect();
        out[sel] = [+(r.left - stage.left).toFixed(2),
                    +(r.top - stage.top).toFixed(2),
                    +r.width.toFixed(2), +r.height.toFixed(2)];
      });
      return out;
    })())""" % json.dumps(list(FIGMA))))

    for sel, (x, y, w, h) in FIGMA.items():
        got = measured.get(sel)
        if got is None:
            check(f"{sel} exists", False, "missing")
            continue
        ok = abs(got[0] - x) <= 1 and abs(got[1] - y) <= 1
        if w is not None:
            ok = ok and abs(got[2] - w) <= 1
        if h is not None:
            ok = ok and abs(got[3] - h) <= 1
        check(f"{sel} sits at Figma coordinates", ok,
              f"want=({x},{y},{w},{h}) got={got}")

    # Upfront is a plain image. Scatter is inline, because its pumpkins are
    # animated one at a time, so the two are checked differently.
    upfront = json.loads(c.eval("""JSON.stringify((() => {
      const img = document.querySelector(
        '.atlas-slide--same-ad-rate img.sar__shelf--upfront');
      if (!img) return null;
      const r = img.getBoundingClientRect();
      return {
        src: img.getAttribute('src'),
        loaded: img.complete && img.naturalWidth > 0,
        intrinsic: img.naturalWidth / img.naturalHeight,
        drawn: r.width / r.height,
      };
    })())"""))
    check("the Upfront shelf is still a plain image", upfront is not None)
    if upfront:
        check("the Upfront shelf asset resolves and decodes",
              upfront["loaded"], f"{upfront['src']} loaded={upfront['loaded']}")
        # A swap that keeps the CSS box but changes the artwork's own
        # proportions would silently squash it. Guard the aspect, not the
        # pixel size: naturalWidth rounds to whole pixels on a fractional SVG.
        check("the Upfront shelf is drawn at its own aspect, not stretched",
              abs(upfront["intrinsic"] - upfront["drawn"]) < 0.01,
              f"intrinsic={upfront['intrinsic']:.5f} "
              f"drawn={upfront['drawn']:.5f}")

    scatter = json.loads(c.eval("""JSON.stringify((() => {
      const s = document.querySelector('.atlas-slide--same-ad-rate');
      const svg = s.querySelector('svg[data-sar-scatter-shelf]');
      if (!svg) return null;
      const r = svg.getBoundingClientRect();
      const box = (svg.getAttribute('viewBox') || '')
        .trim().split(/[\\s,]+/).map(Number);
      // A full-bleed filled rect would be a background baked in by a Figma
      // group export, and would paint an opaque panel over the slide.
      const bled = [...svg.querySelectorAll('rect')].filter(rect => {
        const fill = rect.getAttribute('fill');
        if (!fill || fill === 'none' || fill === 'transparent') return false;
        const x = parseFloat(rect.getAttribute('x') || '0');
        const y = parseFloat(rect.getAttribute('y') || '0');
        const rw = parseFloat(rect.getAttribute('width') || '0');
        const rh = parseFloat(rect.getAttribute('height') || '0');
        return x <= 0.5 && y <= 0.5
          && x + rw >= box[2] - 0.5 && y + rh >= box[3] - 0.5;
      }).map(rect => rect.getAttribute('fill'));
      return {
        viewBox: [box[2], box[3]],
        drawn: r.width / r.height,
        overflow: getComputedStyle(svg).overflow,
        rest: svg.querySelectorAll('[data-sar-role="rest"]').length,
        fliers: svg.querySelectorAll('[data-sar-role="flier"]').length,
        defs: svg.querySelectorAll('defs > [id^="sar-pumpkin-"]').length,
        label: svg.getAttribute('aria-label') || '',
        bled: bled,
      };
    })())"""))
    check("the Scatter shelf is inline so its pumpkins can be animated",
          scatter is not None)
    if scatter:
        check("the Scatter shelf is drawn at its own aspect, not stretched",
              abs(scatter["viewBox"][0] / scatter["viewBox"][1]
                  - scatter["drawn"]) < 0.01,
              f"viewBox={scatter['viewBox']} drawn={scatter['drawn']:.5f}")
        # The pumpkins fly in from beside the connector, well outside the
        # shelf's own box, so the shelf must not crop them.
        check("the Scatter shelf does not crop its arriving pumpkins",
              scatter["overflow"] == "visible", scatter["overflow"])
        check("ten pumpkins are defined once and drawn twice",
              scatter["defs"] == PUMPKINS and scatter["rest"] == PUMPKINS
              and scatter["fliers"] == PUMPKINS,
              f"defs={scatter['defs']} rest={scatter['rest']} "
              f"fliers={scatter['fliers']}")
        check("the Scatter shelf carries no baked-in background",
              not scatter["bled"], f"full-bleed fills={scatter['bled']}")
        check("the inline Scatter shelf still describes itself",
              "shelf" in scatter["label"].lower(), scatter["label"])

    label = json.loads(c.eval("""JSON.stringify((() => {
      const stage = document.querySelector('.atlas-stage')
                            .getBoundingClientRect();
      const p = document.querySelector('.sar__pumpkin')
                        .getBoundingClientRect();
      const l = document.querySelector('.sar__source-label')
                        .getBoundingClientRect();
      const cs = getComputedStyle(document.querySelector('.sar__source-label'));
      return {
        offCentre: +Math.abs((p.left + p.right) / 2
                           - (l.left + l.right) / 2).toFixed(2),
        top: +(l.top - stage.top).toFixed(2),
        gap: +(l.top - p.bottom).toFixed(2),
        size: cs.fontSize,
        weight: cs.fontWeight,
        colour: cs.color,
      };
    })())"""))
    check("the Ad label is centred under the pumpkin",
          label["offCentre"] < 1, f"{label['offCentre']}px off centre")
    # Figma 739:12632 puts the label at y 686, 19.4 below the pumpkin's box.
    check("the Ad label keeps Figma's spacing below the pumpkin",
          abs(label["top"] - 686) <= 1, f"top={label['top']}")
    check("the Ad label keeps Figma's type",
          label["size"] == "33.887px" and label["weight"] == "500"
          and label["colour"] == "rgb(255, 255, 255)", json.dumps(label))

    style = json.loads(c.eval("""JSON.stringify((() => {
      const s = document.querySelector('.atlas-slide--same-ad-rate');
      const q = sel => getComputedStyle(s.querySelector(sel));
      return {
        title: [q('.sar__title').fontSize, q('.sar__title').lineHeight],
        subtitle: [q('.sar__subtitle').fontSize, q('.sar__subtitle').lineHeight],
        rate: [q('.sar__rate-value').fontSize, q('.sar__rate-value').color,
               q('.sar__rate-value').fontWeight],
        deal: [q('.sar__deal').fontSize, q('.sar__deal').color,
               q('.sar__deal').fontWeight],
        place: [q('.sar__placement').fontSize, q('.sar__placement').color],
        source: [q('.sar__source-label').fontSize, q('.sar__source-label').color],
        footnote: [q('.sar__footnote').fontSize, q('.sar__footnote').fontStyle],
      };
    })())"""))
    check("header type matches Figma",
          style["title"] == ["56px", "56px"]
          and style["subtitle"] == ["36px", "56px"], json.dumps(style))
    check("both rates are Figma gold",
          style["rate"][0] == "32px" and style["rate"][1] == "rgb(255, 187, 0)"
          and style["rate"][2] == "900", json.dumps(style["rate"]))
    check("deal type is bright enough to project",
          style["deal"][1] == "rgb(236, 238, 238)"
          and style["deal"][2] == "900", json.dumps(style["deal"]))
    check("placement copy uses the same near-white",
          style["place"][1] == "rgb(236, 238, 238)", json.dumps(style["place"]))
    check("the footnote is italic",
          style["footnote"] == ["24px", "italic"], json.dumps(style["footnote"]))
    check("no visible text drops below 14px",
          not c.eval("""[...document.querySelectorAll(
            '.atlas-slide--same-ad-rate *')].filter(n => {
              if (!n.getClientRects().length) return false;
              const direct = [...n.childNodes].some(
                x => x.nodeType === Node.TEXT_NODE && x.textContent.trim());
              return direct && parseFloat(getComputedStyle(n).fontSize) < 14;
            }).map(n => String(n.className))"""))

    # The connector has to be real geometry, not the flat export.
    wire = json.loads(c.eval("""JSON.stringify((() => {
      const svg = document.querySelector('.sar__wire');
      const seg = [...svg.querySelectorAll('.sar__seg')];
      return {
        isSvg: svg instanceof SVGElement,
        segments: seg.length,
        arrows: svg.querySelectorAll('.sar__arrow').length,
        joints: svg.querySelectorAll('.sar__joint').length,
        images: svg.querySelectorAll('image, img').length,
        decorative: svg.getAttribute('aria-hidden') === 'true'
                 && svg.getAttribute('focusable') === 'false',
        stroke: seg.map(p => p.getAttribute('stroke'))
                   .every(s => s === '#6CB8FF'),
        widths: seg.map(p => p.getAttribute('stroke-width'))
                   .every(w => w === '2'),
        lengths: seg.map(p => +p.getTotalLength().toFixed(1)),
        names: seg.map(p => p.dataset.sarReveal),
      };
    })())"""))
    check("the connector is inline vector, not an image",
          wire["isSvg"] and wire["images"] == 0, json.dumps(wire["images"]))
    check("it is built from five separate animatable segments",
          wire["segments"] == 5, wire["segments"])
    check("both arrowheads and both corner joints are present",
          wire["arrows"] == 2 and wire["joints"] == 2,
          f'arrows={wire["arrows"]} joints={wire["joints"]}')
    check("segments use the Figma stroke and weight",
          wire["stroke"] and wire["widths"])
    check("the connector is decorative to assistive tech", wire["decorative"])
    check("the branch is built from halves so it can open outward",
          c.eval("""(() => {
            const s = document.querySelector('.atlas-slide--same-ad-rate');
            const named = cls => s.querySelector('.sar__seg--' + cls);
            return ['spine-up', 'spine-down', 'branch-up', 'branch-down']
              .every(cls => named(cls)
                && named(cls).dataset.sarReveal === 'branch')
              && s.querySelectorAll('[data-sar-reveal="branch"]').length === 8;
          })()"""))
    check("segment lengths match the Figma run",
          wire["lengths"] == [177.9, 199.0, 200.2, 177.9, 177.9],
          json.dumps(wire["lengths"]))

    # The branches have to actually reach the shelves they point at.
    aim = json.loads(c.eval("""JSON.stringify((() => {
      const stage = document.querySelector('.atlas-stage')
                            .getBoundingClientRect();
      const r = sel => {
        const b = document.querySelector(sel).getBoundingClientRect();
        return {l: b.left - stage.left, r: b.right - stage.left,
                t: b.top - stage.top, b: b.bottom - stage.top};
      };
      const wire = r('.sar__wire');
      return {
        wire, up: r('.sar__shelf--upfront'), down: r('.sar__shelf--scatter'),
        source: r('.sar__source'),
      };
    })())"""))
    check("the first line starts clear of the Ad group",
          aim["wire"]["l"] >= aim["source"]["r"] - 1,
          f'wire {aim["wire"]["l"]:.1f} vs source {aim["source"]["r"]:.1f}')
    check("the arrow tips reach the two shelves",
          abs(aim["wire"]["r"] - aim["up"]["l"]) < 60
          and abs(aim["wire"]["r"] - aim["down"]["l"]) < 60,
          f'wire right {aim["wire"]["r"]:.1f}, shelves'
          f' {aim["up"]["l"]:.1f} / {aim["down"]["l"]:.1f}')
    check("the connector spans between the two results vertically",
          aim["wire"]["t"] > aim["up"]["t"] and aim["wire"]["b"] < aim["down"]["b"],
          json.dumps({k: round(v, 1) for k, v in aim["wire"].items()}))

    assets = c.eval("""(() => {
      const imgs = [...document.querySelectorAll(
        '.atlas-slide--same-ad-rate img')];
      return imgs.filter(i => !i.complete || i.naturalWidth === 0)
                 .map(i => i.getAttribute('src'));
    })()""")
    check("every slide asset loaded", not assets, json.dumps(assets))
    check("no asset depends on a remote or expiring URL",
          not c.eval("""[...document.querySelectorAll(
            '.atlas-slide--same-ad-rate img')]
            .filter(i => /^https?:/.test(i.getAttribute('src')))
            .map(i => i.getAttribute('src'))"""))
    check("meaningful illustrations carry a description",
          c.eval("""[...document.querySelectorAll(
            '.sar__pumpkin, .sar__shelf')]
            .every(i => ((i.getAttribute('alt')
                       || i.getAttribute('aria-label') || '').length > 10))"""))
    c.screenshot(f"{OUT}/geometry_1920.png")


# ------------------------------------------------------------------- reveal
def run_stages(c, url, label):
    """The slide opens on the question and answers it in three clicks."""
    print(f"\n[three clicks @ {label}]")
    go(c, url + f"&slide={SLIDE_INDEX}")
    time.sleep(0.8)

    def look():
        return json.loads(c.eval("""JSON.stringify((() => {
          const s = document.querySelector('.atlas-slide--same-ad-rate');
          const host = s.querySelector('[data-same-ad-rate]');
          const op = sel => +(+getComputedStyle(
            s.querySelector(sel)).opacity).toFixed(2);
          const drawn = cls => {
            const cs = getComputedStyle(s.querySelector('.sar__seg--' + cls));
            return +(parseFloat(cs.strokeDashoffset) || 0).toFixed(1);
          };
          const lit = sel => [...s.querySelectorAll(sel)]
            .filter(n => +getComputedStyle(n).opacity > 0.02).length;
          return {
            stage: +(host.dataset.sarStage || 0),
            phase: host.dataset.sarPhase,
            header: op('.sar__header'),
            ad: op('.sar__source'),
            footnote: op('.sar__footnote'),
            logo: op('.sar__logo'),
            line: drawn('line'),
            spine: drawn('spine-up'),
            branch: drawn('branch-up'),
            arrows: lit('.sar__arrow'),
            joints: lit('.sar__joint'),
            upfront: op('.sar__result--upfront'),
            scatter: op('.sar__result--scatter'),
            pumpkins: lit('[data-sar-role="rest"]'),
          };
        })())"""))

    # ---- the slide as it opens -------------------------------------------
    open_ = look()
    check("the slide opens on stage zero",
          open_["stage"] == 0 and open_["phase"] == "revealing",
          json.dumps(open_))
    check("the question is on screen from the first frame",
          open_["header"] == 1 and open_["ad"] == 1
          and open_["footnote"] == 1 and open_["logo"] == 1,
          json.dumps({k: open_[k] for k in
                      ("header", "ad", "footnote", "logo")}))
    check("the short line beside the Ad is already drawn",
          open_["line"] == 0, f"dash offset {open_['line']}")
    check("the branch has not been drawn yet",
          open_["spine"] > 100 and open_["branch"] > 100
          and open_["arrows"] == 0 and open_["joints"] == 0,
          json.dumps({k: open_[k] for k in
                      ("spine", "branch", "arrows", "joints")}))
    check("neither shelf is on screen yet",
          open_["upfront"] == 0 and open_["scatter"] == 0,
          json.dumps({"upfront": open_["upfront"],
                      "scatter": open_["scatter"]}))
    check("no pumpkin is on the Scatter shelf yet",
          open_["pumpkins"] == 0, str(open_["pumpkins"]))
    c.screenshot(f"{OUT}/{label}_click0.png")

    # ---- click 1: the branch, both sides at once -------------------------
    order = json.loads(c.eval("""(async () => {
      const s = document.querySelector('.atlas-slide--same-ad-rate');
      const dash = cls => {
        const cs = getComputedStyle(s.querySelector('.sar__seg--' + cls));
        return parseFloat(cs.strokeDashoffset) || 0;
      };
      const seen = {};
      const t0 = performance.now();
      document.querySelector('.atlas-stage-wrap').click();
      await new Promise(done => {
        (function tick() {
          const t = Math.round(performance.now() - t0);
          if (!seen.spineUp && dash('spine-up') < 190) seen.spineUp = t;
          if (!seen.spineDown && dash('spine-down') < 190) seen.spineDown = t;
          if (!seen.branchUp && dash('branch-up') < 170) seen.branchUp = t;
          if (!seen.branchDown && dash('branch-down') < 170) seen.branchDown = t;
          if (!seen.arrow && [...s.querySelectorAll('.sar__arrow')]
                .every(a => +getComputedStyle(a).opacity > 0.5)) seen.arrow = t;
          if (performance.now() - t0 > 1000) done();
          else requestAnimationFrame(tick);
        })();
      });
      return JSON.stringify(seen);
    })()"""))
    time.sleep(0.3)
    after1 = look()
    check("one click draws the whole branch",
          after1["stage"] == 1 and after1["spine"] == 0
          and after1["branch"] == 0 and after1["arrows"] == 2
          and after1["joints"] == 2, json.dumps(after1))
    check("both sides of the branch are the same click",
          "spineUp" in order and "spineDown" in order
          and "branchUp" in order and "branchDown" in order
          and abs(order["branchUp"] - order["branchDown"]) <= 60,
          json.dumps(order))
    check("the upright opens before the arms run out",
          order.get("spineUp", 9999) <= order.get("branchUp", 0),
          json.dumps(order))
    check("the heads wait for the arms to reach them",
          order.get("arrow", 0) >= order.get("branchUp", 9999),
          json.dumps(order))
    check("the branch is done inside two thirds of a second",
          order.get("arrow", 9999) <= 700, f"{order.get('arrow')}ms")
    check("neither shelf came with the branch",
          after1["upfront"] == 0 and after1["scatter"] == 0
          and after1["pumpkins"] == 0, json.dumps(after1))
    c.screenshot(f"{OUT}/{label}_click1.png")

    # ---- click 2: Upfront, and only Upfront ------------------------------
    c.click_stage()
    time.sleep(RUNTIME_MS["upfront"] / 1000 + 0.3)
    after2 = look()
    check("the second click brings Upfront up whole",
          after2["stage"] == 2 and after2["upfront"] == 1, json.dumps(after2))
    check("Scatter stayed away for its own click",
          after2["scatter"] == 0 and after2["pumpkins"] == 0,
          json.dumps({"scatter": after2["scatter"],
                      "pumpkins": after2["pumpkins"]}))
    check("the branch is still there behind it",
          after2["arrows"] == 2 and after2["spine"] == 0, json.dumps(after2))
    check("the Upfront shelf arrives stocked, not filling",
          c.eval("""(() => {
            const img = document.querySelector('img.sar__shelf--upfront');
            return img.complete && img.naturalWidth > 0
              && !document.querySelector(
                   '.sar__result--upfront [data-sar-pumpkin]');
          })()"""))
    c.screenshot(f"{OUT}/{label}_click2.png")

    # ---- click 3: Scatter, then the shelf fills itself -------------------
    c.click_stage()
    time.sleep(0.75)
    holding = look()
    check("the third click brings the Scatter shelf up",
          holding["stage"] == 3 and holding["scatter"] == 1,
          json.dumps(holding))
    check("it arrives holding only the other produce",
          holding["pumpkins"] == 0,
          f"{holding['pumpkins']} pumpkins during the hold")
    check("every non-pumpkin product is already in place during the hold",
          c.eval("""(() => {
            const shelf = document.querySelector('[data-sar-scatter-shelf]');
            const g = shelf.querySelector('.sar__apples');
            return !!g && g.querySelectorAll('path').length === 14
              && +getComputedStyle(g).opacity === 1
              && shelf.querySelectorAll('ellipse[id^="Ellipse 4"]').length >= 10;
          })()"""))
    c.screenshot(f"{OUT}/{label}_click3_hold.png")

    time.sleep((RUNTIME_MS["scatter"] - 750) / 1000 + 0.4)
    done = look()
    check("all ten pumpkins end up on the shelf",
          done["pumpkins"] == PUMPKINS, str(done["pumpkins"]))
    check("the slide finishes complete, with everything on screen",
          done["phase"] == "complete" and done["stage"] == 3
          and done["upfront"] == 1 and done["scatter"] == 1
          and done["arrows"] == 2 and done["header"] == 1,
          json.dumps(done))
    c.screenshot(f"{OUT}/{label}_click3_done.png")


def run_fill(c, url):
    """Inside click 3: the hold, then ten pumpkins, then the rate."""
    print("\n[the Scatter shelf filling]")
    go(c, url + f"&slide={SLIDE_INDEX}")
    pin_stage_scale(c)
    click_through(c, upto=2)

    frames = json.loads(c.eval("""(async () => {
      const slide = document.querySelector('.atlas-slide--same-ad-rate');
      const shelf = slide.querySelector('[data-sar-scatter-shelf]');
      const out = [];
      document.querySelector('.atlas-stage-wrap').click();
      const t0 = performance.now();
      await new Promise(done => {
        (function tick() {
          const box = shelf.getBoundingClientRect();
          const row = {t: Math.round(performance.now() - t0), p: []};
          shelf.querySelectorAll('[data-sar-pumpkin]').forEach(u => {
            const o = +getComputedStyle(u).opacity;
            if (o <= 0.02) return;
            const r = u.getBoundingClientRect();
            row.p.push({
              n: +u.dataset.sarPumpkin, role: u.dataset.sarRole,
              o: +o.toFixed(3),
              x: +(r.left + r.width / 2 - box.left).toFixed(1),
              y: +(r.top + r.height / 2 - box.top).toFixed(1),
              w: +r.width.toFixed(1), h: +r.height.toFixed(1),
            });
          });
          out.push(row);
          if (performance.now() - t0 > %d) done();
          else requestAnimationFrame(tick);
        })();
      });
      return JSON.stringify(out);
    })()""" % (RUNTIME_MS["scatter"] + 500)))
    check("the fill was watched frame by frame", len(frames) > 150,
          f"{len(frames)} frames")

    def lit(row, n):
        return max((q["o"] for q in row["p"] if q["n"] == n), default=0)

    # 1. The shelf is on screen well before anything lands on it.
    quiet = [r for r in frames if r["t"] < FILL_HOLD_MS - 150]
    check("the shelf holds empty before the pumpkins come",
          bool(quiet) and all(lit(r, n) == 0 for r in quiet for n in HOMES),
          f"nothing for the first {quiet[-1]['t'] if quiet else 0}ms")

    seen = {}
    for row in frames:
        for n in HOMES:
            if n not in seen and lit(row, n) > 0.05:
                seen[n] = row["t"]
    check("every one of the ten arrives", sorted(seen) == sorted(HOMES),
          json.dumps(sorted(seen)))
    if sorted(seen) == sorted(HOMES):
        check("the first waits out the hold",
              seen[ENTRY_ORDER[0]] >= FILL_HOLD_MS - 250,
              f"first at {seen[ENTRY_ORDER[0]]}ms")
        arrived = sorted(seen, key=lambda n: seen[n])
        check("they arrive one at a time, never together",
              len(set(seen.values())) == len(seen),
              json.dumps([seen[n] for n in arrived]))
        check("they arrive in the order that keeps their paths clear",
              arrived == ENTRY_ORDER, json.dumps(arrived))
        gaps = [seen[b] - seen[a]
                for a, b in zip(ENTRY_ORDER, ENTRY_ORDER[1:])]
        check("the stagger between them stays even",
              all(80 <= g <= 200 for g in gaps), json.dumps(gaps))
        run = seen[ENTRY_ORDER[-1]] + FILL_DURATION_MS - seen[ENTRY_ORDER[0]]
        check("the ten of them take between one and two seconds",
              1250 <= run <= 1750, f"{run}ms")

    # 2. Each one is travelling, not fading in where it lands.
    starts = {}
    for row in frames:
        for q in row["p"]:
            if q["role"] == "flier" and q["o"] > 0.05 and q["n"] not in starts:
                starts[q["n"]] = q["x"]
    check("each is still short of its shelf when it appears",
          len(starts) == PUMPKINS
          and all(HOMES[n][0] - x > 25 for n, x in starts.items()),
          json.dumps({n: round(HOMES[n][0] - x, 1)
                      for n, x in sorted(starts.items())}))
    check("they set off from the connector, not from thin air",
          all(ORIGIN_X - 1 < x < HOMES[n][0] for n, x in starts.items()),
          json.dumps({n: round(x, 1) for n, x in sorted(starts.items())}))

    # 3. None is seen crossing another on the way in. Some of them rest
    #    close enough for their boxes to touch, so that much is the artwork
    #    and the flight is only allowed to match it.
    def span(q):
        return (q["x"] - q["w"] / 2, q["y"] - q["h"] / 2,
                q["x"] + q["w"] / 2, q["y"] + q["h"] / 2)

    def overlap(a, b):
        w = min(a[2], b[2]) - max(a[0], b[0])
        h = min(a[3], b[3]) - max(a[1], b[1])
        return w * h if w > 0 and h > 0 else 0.0

    resting = json.loads(c.eval("""JSON.stringify((() => {
      const shelf = document.querySelector('[data-sar-scatter-shelf]');
      return [...shelf.querySelectorAll('[data-sar-role="rest"]')].map(u => {
        const r = u.getBoundingClientRect();
        return {l: r.left, t: r.top, r: r.right, b: r.bottom};
      });
    })())"""))
    settled = 0.0
    for i, a in enumerate(resting):
        for b in resting[i + 1:]:
            box = overlap((a["l"], a["t"], a["r"], a["b"]),
                          (b["l"], b["t"], b["r"], b["b"]))
            smaller = min((a["r"] - a["l"]) * (a["b"] - a["t"]),
                          (b["r"] - b["l"]) * (b["b"] - b["t"]))
            settled = max(settled, box / smaller * 100)
    crossing, when = 0.0, None
    for row in frames:
        vis = [q for q in row["p"] if q["o"] > 0.05]
        for i, a in enumerate(vis):
            for b in vis[i + 1:]:
                if a["n"] == b["n"]:
                    continue
                box = overlap(span(a), span(b))
                if not box:
                    continue
                pct = box / min(a["w"] * a["h"], b["w"] * b["h"]) * 100
                if pct > crossing:
                    crossing, when = pct, row["t"]
    check("no pumpkin is seen crossing another on its way in",
          crossing <= settled + 2,
          f"worst {crossing:.1f}% at {when}ms, against {settled:.1f}% "
          f"where they rest side by side")

    clip = json.loads(c.eval("""JSON.stringify((() => {
      const shelf = document.querySelector('[data-sar-scatter-shelf]');
      const layer = shelf.querySelector('[data-sar-fliers]');
      const ref = (layer && layer.getAttribute('clip-path') || '')
        .replace(/^url\\(#|\\)$/g, '');
      const path = ref && shelf.querySelector(
        'clipPath#' + CSS.escape(ref) + ' > path');
      return {ref, rule: path && path.getAttribute('clip-rule'),
              holes: path ? (path.getAttribute('d').match(/M/g) || []).length - 1
                          : 0};
    })())"""))
    check("the flying layer is cut around the produce it passes",
          clip["ref"] == "sar-behind-produce" and clip["rule"] == "evenodd"
          and clip["holes"] == 4, json.dumps(clip))

    moving = json.loads(c.eval("""JSON.stringify((() => {
      const shelf = document.querySelector('[data-sar-scatter-shelf]');
      return shelf.getAnimations({subtree: true})
        .filter(a => !(a.effect.target.dataset || {}).sarRole)
        .map(a => a.animationName + ' on ' + a.effect.target.tagName);
    })())"""))
    check("only the pumpkins are animated, the other produce is left alone",
          not moving, json.dumps(moving))

    # The two apples are part of the shelf the presenter is shown first,
    # not something that arrives. In Figma they are drawn after the shelf,
    # so they have to sit above the flying layer too.
    cabbage = json.loads(c.eval("""JSON.stringify((() => {
      const shelf = document.querySelector('[data-sar-scatter-shelf]');
      const g = shelf.querySelector('.sar__apples');
      if (!g) return null;
      const kids = [...shelf.children];
      const fliers = shelf.querySelector('[data-sar-fliers]');
      return {
        paths: g.querySelectorAll('path').length,
        animated: g.getAnimations({subtree: true}).length,
        aboveFliers: kids.indexOf(g) > kids.indexOf(fliers),
        opacity: +(+getComputedStyle(g).opacity).toFixed(2),
      };
    })())"""))
    check("the Scatter shelf carries both apples from Figma",
          cabbage is not None and cabbage["paths"] == 14,
          json.dumps(cabbage))
    if cabbage:
        check("the apples never move",
              cabbage["animated"] == 0 and cabbage["opacity"] == 1,
              json.dumps(cabbage))
        check("they sit above the arriving pumpkins, as Figma draws them",
              cabbage["aboveFliers"], json.dumps(cabbage))

    # 4. The shelf ends stocked, nothing in the air, nothing drawn twice.
    time.sleep(0.8)
    end = json.loads(c.eval("""JSON.stringify((() => {
      const shelf = document.querySelector('[data-sar-scatter-shelf]');
      const box = shelf.getBoundingClientRect();
      const read = role => [...shelf.querySelectorAll(
        '[data-sar-role="' + role + '"]')].map(u => {
          const r = u.getBoundingClientRect();
          return {n: +u.dataset.sarPumpkin,
                  o: +(+getComputedStyle(u).opacity).toFixed(3),
                  tf: getComputedStyle(u).transform,
                  x: +(r.left + r.width / 2 - box.left).toFixed(1),
                  y: +(r.top + r.height / 2 - box.top).toFixed(1)};
        });
      return {rest: read('rest'), flier: read('flier')};
    })())"""))
    check("all ten end on the shelf",
          len(end["rest"]) == PUMPKINS
          and all(p["o"] == 1 for p in end["rest"]),
          json.dumps([p["o"] for p in end["rest"]]))
    check("none is left hanging in the air",
          all(p["o"] == 0 for p in end["flier"]),
          json.dumps([p["o"] for p in end["flier"]]))
    identity = ("none", "matrix(1, 0, 0, 1, 0, 0)")
    check("nothing is left mid-flight once the shelf is stocked",
          all(p["tf"] in identity for p in end["rest"]),
          json.dumps(sorted({p["tf"] for p in end["rest"]})))
    off = {p["n"]: [round(p["x"] - HOMES[p["n"]][0], 1),
                    round(p["y"] - HOMES[p["n"]][1], 1)]
           for p in end["rest"] if p["n"] in HOMES}
    check("each lands exactly in its own place",
          all(abs(dx) <= 1.5 and abs(dy) <= 1.5 for dx, dy in off.values()),
          json.dumps(off))

    rate = json.loads(c.eval("""JSON.stringify((() => {
      const p = document.querySelector(
        '.atlas-slide--same-ad-rate .sar__copy--scatter .sar__rate');
      const cs = getComputedStyle(p);
      return {name: cs.animationName, count: cs.animationIterationCount,
              delay: cs.animationDelay, duration: cs.animationDuration,
              opacity: +(+cs.opacity).toFixed(3)};
    })())"""))
    check("the $28 rate takes its beat after the last pumpkin settles",
          rate["name"] == "sar-rate-arrive"
          and rate["delay"] in ("2.685s", "2685ms"), json.dumps(rate))
    check("that beat happens once and does not loop",
          rate["count"] == "1" and rate["opacity"] == 1, json.dumps(rate))


def run_interaction(c, url):
    print("\n[interaction]")
    go(c, url + f"&slide={SLIDE_INDEX}")
    time.sleep(0.6)

    # A gesture arriving mid-stage is dropped, not banked.
    guarded = json.loads(c.eval("""(async () => {
      const wait = ms => new Promise(r => setTimeout(r, ms));
      const host = () => document.querySelector('[data-same-ad-rate]');
      const stage = () => +(host().dataset.sarStage || 0);
      const click = () => document.querySelector('.atlas-stage-wrap').click();
      const before = stage();
      click();
      await wait(120);
      const mid = stage();
      click(); click();
      await wait(120);
      const hammered = stage();
      await wait(700);
      const settled = stage();
      return JSON.stringify({before, mid, hammered, settled,
        active: document.querySelector('.atlas-slide.is-active')
                        .dataset.atlasSlideId});
    })()"""))
    check("one click is one stage", guarded["mid"] == 1, json.dumps(guarded))
    check("clicks during a running stage are dropped, not banked",
          guarded["hammered"] == 1 and guarded["settled"] == 1,
          json.dumps(guarded))
    check("and none of them escaped to the deck",
          guarded["active"] == SLIDE_ID, guarded["active"])

    # Keyboard and space walk the same three stages.
    for code, key_js in (("Space", " "), ("ArrowRight", "ArrowRight")):
        go(c, url + f"&slide={SLIDE_INDEX}")
        time.sleep(0.6)
        seq = []
        for name in STAGES:
            c.eval("document.dispatchEvent(new KeyboardEvent('keydown', "
                   "{key: %s, bubbles: true}))" % json.dumps(key_js))
            time.sleep(RUNTIME_MS[name] / 1000 + 0.3)
            seq.append(stage_index(c))
        check(f"{code} walks the same three stages", seq == [1, 2, 3],
              json.dumps(seq))
        check(f"{code} did not leave the slide early",
              slide_id(c) == SLIDE_ID, slide_id(c))

    # The fourth gesture, once the third stage is done, belongs to the deck.
    go(c, url + f"&slide={SLIDE_INDEX}")
    time.sleep(0.6)
    click_through(c)
    check("the slide reports itself complete", phase(c) == "complete",
          phase(c))
    check("it has not advanced on its own", slide_id(c) == SLIDE_ID,
          slide_id(c))
    c.click_stage()
    time.sleep(0.5)
    check("the next click advances the deck",
          slide_id(c) == "core-planning-media-plan", slide_id(c))

    # ArrowRight still leaves the slide once the sequence is done, and
    # ArrowLeft is deck navigation throughout.
    go(c, url + f"&slide={SLIDE_INDEX}")
    time.sleep(0.6)
    c.key("ArrowLeft", "ArrowLeft", 37)
    time.sleep(0.5)
    check("ArrowLeft is deck navigation, not a step back through the stages",
          slide_id(c) == "upfront-scatter", slide_id(c))


def run_reset(c, url):
    print("\n[reset]")
    go(c, url + f"&slide={SLIDE_INDEX}")
    time.sleep(0.6)
    click_through(c)
    check("primed with the whole slide showing",
          stage_index(c) == 3 and phase(c) == "complete",
          f"stage={stage_index(c)} phase={phase(c)}")

    c.key("ArrowRight", "ArrowRight", 39)
    time.sleep(0.5)
    check("leaving cleared the slide",
          stage_index(c) == 0 and stages(c) == [],
          f"stage={stage_index(c)} stages={stages(c)}")

    c.key("ArrowLeft", "ArrowLeft", 37)
    time.sleep(0.6)
    back = json.loads(c.eval("""JSON.stringify((() => {
      const s = document.querySelector('.atlas-slide--same-ad-rate');
      const host = s.querySelector('[data-same-ad-rate]');
      const lit = sel => [...s.querySelectorAll(sel)]
        .filter(n => +getComputedStyle(n).opacity > 0.02).length;
      return {
        stage: +(host.dataset.sarStage || 0),
        arrows: lit('.sar__arrow'),
        pumpkins: lit('[data-sar-role="rest"]'),
        upfront: +(+getComputedStyle(
          s.querySelector('.sar__result--upfront')).opacity).toFixed(2),
        scatter: +(+getComputedStyle(
          s.querySelector('.sar__result--scatter')).opacity).toFixed(2),
      };
    })())"""))
    check("coming back puts the opening state up again",
          back["stage"] == 0 and back["arrows"] == 0
          and back["pumpkins"] == 0 and back["upfront"] == 0
          and back["scatter"] == 0, json.dumps(back))

    click_through(c)
    again = json.loads(c.eval("""JSON.stringify((() => {
      const shelf = document.querySelector('[data-sar-scatter-shelf]');
      return {
        stage: +(document.querySelector('[data-same-ad-rate]')
                         .dataset.sarStage || 0),
        rest: shelf.querySelectorAll('[data-sar-role="rest"]').length,
        lit: [...shelf.querySelectorAll('[data-sar-role="rest"]')]
               .filter(u => +getComputedStyle(u).opacity === 1).length,
        fliers: [...shelf.querySelectorAll('[data-sar-role="flier"]')]
               .filter(u => +getComputedStyle(u).opacity > 0.02).length,
      };
    })())"""))
    check("the whole three-click run replays cleanly",
          again["stage"] == 3 and again["rest"] == PUMPKINS
          and again["lit"] == PUMPKINS and again["fliers"] == 0,
          json.dumps(again))

    # Nothing may fire onto a slide the presenter has already left.
    go(c, url + f"&slide={SLIDE_INDEX}")
    time.sleep(0.5)
    click_through(c, upto=2)
    c.click_stage()          # start the long Scatter stage
    time.sleep(0.3)          # and leave while its shelf is still holding
    go(c, url + f"&slide={SLIDE_INDEX - 1}")
    time.sleep(RUNTIME_MS["scatter"] / 1000)
    check("the deck stayed where the presenter left it",
          slide_id(c) == "upfront-scatter", slide_id(c))
    check("a stage cut short cannot paint onto the slide behind it",
          c.eval("""(() => {
            const s = document.querySelector('.atlas-slide--same-ad-rate');
            const host = s.querySelector('[data-same-ad-rate]');
            return +(host.dataset.sarStage || 0) === 0
              && s.querySelectorAll('[data-sar-reveal].is-revealed').length === 0
              && [...s.querySelectorAll('[data-sar-pumpkin]')]
                   .every(u => +getComputedStyle(u).opacity === 0);
          })()"""))


def run_layout(c, url, label):
    print(f"\n[layout and rounded frame @ {label}]")
    go(c, url + f"&slide={SLIDE_INDEX}")
    click_through(c)
    time.sleep(SETTLE_MS / 1000)

    frame = c.eval("""(() => {
      const stage = document.querySelector('.atlas-stage');
      const wrap = document.querySelector('.atlas-stage-wrap');
      const deck = document.querySelector('.atlas-deck');
      const cs = el => getComputedStyle(el);
      const sr = stage.getBoundingClientRect();
      const wr = wrap.getBoundingClientRect();
      const up = document.querySelector('.sar__result--upfront')
                         .getBoundingClientRect();
      const dn = document.querySelector('.sar__result--scatter')
                         .getBoundingClientRect();
      const src = document.querySelector('.sar__source').getBoundingClientRect();
      const wire = document.querySelector('.sar__wire').getBoundingClientRect();
      return {
        radius: cs(stage).borderTopLeftRadius,
        overflow: cs(stage).overflow,
        canvas: cs(deck).backgroundColor,
        slideBg: cs(document.querySelector('.atlas-slide--same-ad-rate'))
          .backgroundColor,
        pads: [sr.top - wr.top, sr.left - wr.left,
               wr.right - sr.right, wr.bottom - sr.bottom],
        escaped: [...document.querySelectorAll(
          '.atlas-slide--same-ad-rate .sar > *')].filter(n => {
            const r = n.getBoundingClientRect();
            if (!r.width && !r.height) return false;
            return r.left < sr.left - 0.5 || r.right > sr.right + 0.5
                || r.top < sr.top - 0.5 || r.bottom > sr.bottom + 0.5;
          }).map(n => String(n.className)),
        resultsApart: up.bottom <= dn.top + 0.5,
        wireClearsSource: wire.left >= src.right - 1,
        wireClearsShelves: wire.right <= up.left + 1 && wire.right <= dn.left + 1,
        scrolls: document.documentElement.scrollWidth > innerWidth + 1
              || document.documentElement.scrollHeight > innerHeight + 1,
        clipped: [...document.querySelectorAll(
          '.sar__title, .sar__subtitle, .sar__source-label, .sar__rate-value,'
          + ' .sar__deal, .sar__placement, .sar__footnote')]
          .filter(n => n.scrollWidth > n.clientWidth + 1
                    || n.getClientRects().length !== 1)
          .map(n => String(n.className)),
      };
    })()""")
    check("the slide viewport carries the 40px radius",
          frame["radius"] == f"{STAGE_RADIUS}px", frame["radius"])
    check("the slide viewport clips its contents",
          frame["overflow"] == "hidden", frame["overflow"])
    check("the canvas is the shared grey, the slide stays navy",
          frame["canvas"] == CANVAS and frame["slideBg"] == SLIDE_BG,
          f'canvas={frame["canvas"]} slide={frame["slideBg"]}')
    check("the slide is not flush to the browser edges",
          min(frame["pads"]) >= 24,
          json.dumps([round(p, 1) for p in frame["pads"]]))
    check("nothing paints outside the rounded frame",
          not frame["escaped"], json.dumps(frame["escaped"]))
    check("the two results do not overlap each other",
          frame["resultsApart"], frame["resultsApart"])
    check("the connector overlaps neither the source nor the shelves",
          frame["wireClearsSource"] and frame["wireClearsShelves"],
          json.dumps({k: frame[k] for k in
                      ("wireClearsSource", "wireClearsShelves")}))
    check("no text clips or wraps", not frame["clipped"],
          json.dumps(frame["clipped"]))
    check("the page does not scroll", not frame["scrolls"])

    # The corner probes ask whether the slide's radius lets the canvas show
    # through. The feedback launcher is a floating app control that sits in
    # the lower-left corner by design, so it has to be out of the frame for
    # that question to be about the frame. It is put back straight after.
    c.eval("""(() => { const b = document.querySelector('.rcf-launch');
      if (b) b.style.visibility = 'hidden'; })()""")
    c.screenshot(f"{OUT}/{label}_frame.png")
    c.eval("""(() => { const b = document.querySelector('.rcf-launch');
      if (b) b.style.visibility = ''; })()""")
    corners = c.eval("""(() => {
      const r = document.querySelector('.atlas-stage').getBoundingClientRect();
      return {l: r.left, t: r.top, w: r.width, h: r.height};
    })()""")
    from PIL import Image
    im = Image.open(f"{OUT}/{label}_frame.png").convert("RGB")
    slide_rgb = tuple(int(v) for v in SLIDE_BG[4:-1].split(","))
    scale = corners["w"] / 1920
    x0, y0 = int(corners["l"]), int(corners["t"])
    x1, y1 = int(corners["l"] + corners["w"]) - 1, int(corners["t"] + corners["h"]) - 1

    def inset(nx, ny):
        """A point just inside a corner, in the slide's own coordinates."""
        return (int(corners["l"] + nx * scale), int(corners["t"] + ny * scale))

    for name, (outside, inside_pt) in {
        "top-left": ((x0 + 3, y0 + 3), inset(36, 36)),
        "top-right": ((x1 - 3, y0 + 3), inset(1884, 36)),
        "bottom-left": ((x0 + 3, y1 - 3), inset(1500, 1044)),
        "bottom-right": ((x1 - 3, y1 - 3), inset(1700, 1044)),
    }.items():
        check(f"{name} corner is rounded away to the canvas",
              is_canvas(im.getpixel(outside))
              and im.getpixel(inside_pt) == slide_rgb,
              f"corner={im.getpixel(outside)} inset={im.getpixel(inside_pt)}")


def run_reduced_motion(url, port_http):
    print("\n[reduced motion]")
    proc, port = boot_chrome((1440, 900), port_http, reduced=True)
    try:
        c = CDP(port)
        go(c, url + f"&slide={SLIDE_INDEX}")
        check("reduced motion is in effect",
              c.eval("matchMedia('(prefers-reduced-motion: reduce)').matches"))
        motion = c.eval("""(() => {
          const cs = el => getComputedStyle(el);
          const line = cs(document.querySelector('.sar__seg--line'));
          return {
            result: cs(document.querySelector('.sar__result--upfront')).transform,
            dash: line.strokeDasharray,
            offset: line.strokeDashoffset,
            lineOpacity: +(+line.opacity).toFixed(2),
            duration: cs(document.querySelector(
              '.sar__result--upfront')).transitionDuration,
          };
        })()""")
        check("nothing travels under reduced motion",
              motion["result"] == "none", json.dumps(motion))
        check("the connector is not drawn, only faded",
              motion["dash"] in ("none", "") and motion["offset"] == "0px",
              json.dumps({"dash": motion["dash"], "offset": motion["offset"]}))
        check("the short line beside the Ad is still on screen",
              motion["lineOpacity"] == 1, str(motion["lineOpacity"]))
        check("fades are short under reduced motion",
              motion["duration"] == "0.12s", motion["duration"])

        click_through(c, reduced=True)
        time.sleep(0.4)
        check("the same three clicks still walk the slide",
              stage_index(c) == 3 and phase(c) == "complete",
              f"stage={stage_index(c)} phase={phase(c)}")
        check("the gold pass is dropped under reduced motion",
              c.eval("getComputedStyle(document.querySelector("
                     "'.sar__rate-value')).animationName") == "none")

        # The shelf still fills, but nothing crosses the slide to do it.
        fill = json.loads(c.eval("""JSON.stringify((() => {
          const s = document.querySelector('.atlas-slide--same-ad-rate');
          const read = role => [...s.querySelectorAll(
            '[data-sar-role="' + role + '"]')].map(u => {
              const cs = getComputedStyle(u);
              return {op: +(+cs.opacity).toFixed(3),
                      anim: cs.animationName, tf: cs.transform};
            });
          const rate = getComputedStyle(
            s.querySelector('.sar__copy--scatter .sar__rate'));
          return {rest: read('rest'), flier: read('flier'),
                  rateAnim: rate.animationName, rateTf: rate.transform,
                  rateOp: +(+rate.opacity).toFixed(3)};
        })())"""))
        check("every pumpkin is on the shelf under reduced motion",
              all(p["op"] == 1 for p in fill["rest"])
              and len(fill["rest"]) == PUMPKINS,
              json.dumps([p["op"] for p in fill["rest"]]))
        check("no pumpkin travels under reduced motion",
              all(p["anim"] == "sar-pumpkin-appear" for p in fill["rest"])
              and all(p["tf"] in ("none", "matrix(1, 0, 0, 1, 0, 0)")
                      for p in fill["rest"]),
              json.dumps([[p["anim"], p["tf"]] for p in fill["rest"]]))
        check("the flying copies are never used under reduced motion",
              all(p["op"] == 0 for p in fill["flier"]),
              json.dumps([p["op"] for p in fill["flier"]]))
        check("the rate beat is opacity only under reduced motion",
              fill["rateAnim"] == "sar-rate-appear"
              and fill["rateTf"] in ("none", "matrix(1, 0, 0, 1, 0, 0)")
              and fill["rateOp"] == 1,
              json.dumps([fill["rateAnim"], fill["rateTf"], fill["rateOp"]]))

        # The three clicks are still three clicks, and the deck only takes
        # the slide back once the third has run.
        go(c, url + f"&slide={SLIDE_INDEX}")
        time.sleep(0.4)
        walked = []
        for name in STAGES:
            c.click_stage()
            time.sleep(RUNTIME_REDUCED_MS[name] / 1000 + 0.25)
            walked.append([stage_index(c), slide_id(c)])
        check("each stage is still its own gesture under reduced motion",
              [w[0] for w in walked] == [1, 2, 3]
              and all(w[1] == SLIDE_ID for w in walked),
              json.dumps(walked))
        c.click_stage()
        time.sleep(0.4)
        check("and the gesture after the last one advances",
              slide_id(c) == "core-planning-media-plan", slide_id(c))
        check("no console errors under reduced motion", not c.logs,
              json.dumps(c.logs))
    finally:
        proc.kill()


def main():
    if not os.path.exists(f"{ROOT}/index.html"):
        print("index.html missing", file=sys.stderr)
        sys.exit(1)
    port_http = free_port()
    server = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port_http)],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(40):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port_http}/", timeout=0.5).read()
            break
        except Exception:
            time.sleep(0.1)

    url = f"http://127.0.0.1:{port_http}/?section=atlas"
    try:
        proc, port = boot_chrome((1920, 1080), port_http)
        try:
            c = CDP(port)
            run_placement(c, url)
            run_geometry(c, url)
            run_stages(c, url, "1920x1080")
            run_fill(c, url)
            run_interaction(c, url)
            run_reset(c, url)
            run_layout(c, url, "1920x1080")
            print("\n[console]")
            check("no console errors or warnings", not c.logs, json.dumps(c.logs))
        finally:
            proc.kill()

        for label, viewport in (("1440x900", (1440, 900)), ("1280x720", (1280, 720))):
            proc, port = boot_chrome(viewport, port_http)
            try:
                c = CDP(port)
                run_stages(c, url, label)
                run_layout(c, url, label)
                check(f"no console errors at {label}", not c.logs, json.dumps(c.logs))
            finally:
                proc.kill()

        run_reduced_motion(url, port_http)
    finally:
        server.terminate()

    total = len(CHECKS)
    bad = [x for x in CHECKS if not x[1]]
    print(f"\n{total - len(bad)}/{total} passed")
    print(f"artifacts in {OUT}")
    if bad:
        print("\nFAILED:")
        for label, _ok, detail in bad:
            print(f"  - {label}" + (f" -- {detail}" if detail else ""))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
