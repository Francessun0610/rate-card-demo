#!/usr/bin/env python3
"""
qa_upfront_scatter_slide.py - Atlas deck slide 5 QA.

Slide 5, "Buyers can purchase through different deal types", is authored
from Figma node 736:479. Two columns compare the two ways a buyer commits:
Upfront on the left, Scatter on the right, each an illustration with its
deal name, a blue one-line summary and a supporting line under it.

What this suite locks down:

  - Placement. Exactly one Upfront/Scatter slide, fifth, sitting between
    the supermarket metaphor and the media-plan walkthrough, with the deck
    fifteen long and reachable by deep link.
  - Copy, and the absence of everything the brief rules out: no takeaway,
    no OR label, no divider, no arrows, no cards around the columns.
  - Geometry against the Figma frame at the native 1920x1080 stage,
    including the two illustrations' own optical sizes, which are close to
    but deliberately not identical to each other.
  - Reveal. Three stages: the heading, then Upfront, then Scatter. The
    title and subtitle must arrive together, the two columns must not, and
    each column must arrive whole. No layout may shift while it runs.
  - Interaction. A gesture mid-run completes the slide and must not also
    advance; the next gesture advances. Arrow keys are never taken. Double
    clicks and key repeat cannot skip a slide.
  - Timer cleanup and reset, so a pending stage cannot paint onto the next
    slide and re-entry replays from the start.
  - Reduced motion, which keeps the three stages but drops the travel.
  - Rounded corners and the shared #1E1E1E canvas at three viewports.

Timings mirror the SEQUENCE in initAtlasUpfrontScatter (app.js).
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
OUT = "/tmp/qa_upfront_scatter_slide"
SLIDE_INDEX = 4
SLIDE_ID = "upfront-scatter"
TOTAL_SLIDES = 12

# header 250ms, upfront 1050ms, scatter 1430ms.
REVEAL_ORDER = ["header", "upfront", "scatter"]
SEQUENCE_MS = 1430
SETTLE_MS = 750
STAGE_RADIUS = 40
CANVAS = "rgb(30, 30, 30)"
SLIDE_BG = "rgb(2, 0, 36)"

TITLE = "Buyers can purchase through different deal types"
# A column the presenter has not opened yet is absent, not dimmed. Each
# stage then runs its own timeline, and app.js refuses the next gesture
# until that timeline is done, so a presenter beat has to outlast it.
HIDDEN = "0"
# One handling sequence per scene: reach, hold, set down, stand back.
STAGE_RUNTIME = {"upfront": 4.15, "scatter": 4.15}
STAGE_WAIT = 4.6
# Movable layers cut out of the approved original, per scene.
POSES = ["01-pickup", "02-handoff", "03-place", "04-release"]
# Each scene is the room, then the people. Everyone who never moves is lifted
# whole out of one drawing into a still plate; everyone who does gets their
# own cut-out per pose. Every layer is a straight lift from the artwork, so a
# person is painted once at full strength or not at all. Averaging poses
# together to make the plate is what previously left the counter pair
# standing at part opacity with doubled edges.
#
# Upfront's two warehouse workers pass a carton between them, so they share
# one timeline. Scatter's three staff split over two: the pair on the left
# aisle share a cut-out, the one on the right has their own and runs out of
# step with them. Only upfront has anybody standing still.
ACTOR_WINDOWS = {"upfront": 1, "scatter": 2}
STILL_PLATE = {"upfront": True, "scatter": False}
# Vertical compression applied to both scenes, in one place.
SQUASH = 0.82
SUBTITLE = "The deal type helps determine which Rate Card applies."
LINES = ["Upfront", "Reserve Early", "Agreed as an advance commitment",
         "Scatter", "Purchase Later", "Outside the earlier commitment"]

# Figma 736:479 geometry, in native stage pixels: left, top, width, height.
FIGMA = {
    ".usc__header": (63, 88, 1828, 120),
    ".usc__group--upfront": (240.6, 269.7, 542.3, None),
    ".usc__group--scatter": (1069.6, 269.7, 542.0, None),
    # 82% of the artwork's own height, so the columns are shorter and the
    # labels sit up under them.
    ".usc__art--upfront": (240.6, 269.7, 542.3, 488.3),
    ".usc__art--scatter": (1069.6, 269.7, 542.0, 487.5),
    ".usc__group--upfront .usc__copy": (311.2625, 786.0, 401, None),
    ".usc__group--scatter .usc__copy": (1114.1375, 785.26, 453, None),
    ".usc__logo": (1826, 997, 36, 41),
}

# The three copy lines are centred on their own illustration.
COLUMN_CENTRES = {"upfront": 511.7625, "scatter": 1340.6375}

CHECKS = []


def is_canvas(px):
    """True for the presentation canvas, allowing for the shared shadow.

    The corner probes sit inside the slide shadow's falloff, so the canvas
    reads a few levels darker right there. It stays a neutral grey either
    way, which is what tells it apart from the navy slide.
    """
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
    profile = f"/tmp/qa_usc_profile_{port}"
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
        "document.querySelector('[data-upfront-scatter]')"
        "?.getAttribute('data-usc-phase')"
    )


def slide_id(c):
    return c.eval(
        "document.querySelector('.atlas-slide.is-active')?.dataset.atlasSlideId"
    )


def revealed(c):
    return c.eval(
        "[...document.querySelectorAll('[data-usc-reveal]')]"
        ".filter(n => n.classList.contains('is-revealed'))"
        ".map(n => n.dataset.uscReveal)"
    )


def install_sampler(c):
    """Record the reveal timeline from before the document exists."""
    c.send("Page.addScriptToEvaluateOnNewDocument", {"source": """
      window.__uscSamples = [];
      const sample = () => {
        const host = document.querySelector('[data-upfront-scatter]');
        if (!host) return;
        const parts = [...host.querySelectorAll('[data-usc-reveal]')];
        const boxes = {};
        [...host.querySelectorAll(
          '.usc__title, .usc__subtitle, .usc__art, .usc__deal,'
          + ' .usc__lede, .usc__note')].forEach((n, i) => {
            boxes[n.className + i] =
              [n.offsetLeft, n.offsetTop, n.offsetWidth, n.offsetHeight];
          });
        window.__uscSamples.push({
          t: Math.round(performance.now()),
          shown: parts.filter(x => x.classList.contains('is-revealed'))
                      .map(x => x.dataset.uscReveal),
          phase: host.getAttribute('data-usc-phase'),
          boxes: boxes,
        });
      };
      const tick = setInterval(sample, 30);
      setTimeout(() => clearInterval(tick), 9000);
      document.addEventListener('DOMContentLoaded', sample);
    """})


def pin_native_scale(c):
    c.eval("""(() => {
      const style = document.createElement('style');
      style.textContent = `.atlas-stage{--atlas-scale:1 !important;margin:0 !important}
        .atlas-stage-wrap{padding:0 !important;overflow:visible !important}
        .atlas-deck{position:absolute !important}
        .atlas-slide--upfront-scatter [data-usc-reveal]{
          opacity:1 !important; transform:none !important;
          transition:none !important; }`;
      document.head.appendChild(style);
    })()""")
    time.sleep(0.4)


# ---------------------------------------------------------------- placement
def run_placement(c, url):
    print("\n[placement]")
    go(c, url + f"&slide={SLIDE_INDEX}")
    check("slide 5 is the Upfront and Scatter explainer",
          slide_id(c) == SLIDE_ID, f"id={slide_id(c)}")

    order = c.eval(
        "[...document.querySelectorAll('.atlas-slide')].filter(s => !s.hasAttribute('data-atlas-appendix'))"
        ".map(s => s.dataset.atlasSlideId)"
    )
    check("the slide exists exactly once",
          order.count(SLIDE_ID) == 1, f"{order.count(SLIDE_ID)} copies")
    i = order.index(SLIDE_ID)
    check("it follows the supermarket metaphor",
          order[i - 1] == "advertising-supermarket", f"before={order[i - 1]}")
    check("the next slide is the same-ad-different-rate explainer",
          order[i + 1] == "same-ad-different-rate", f"after={order[i + 1]}")
    check("no existing slide was dropped",
          len(order) == TOTAL_SLIDES and len(set(order)) == TOTAL_SLIDES,
          f"{len(order)} slides")
    check("the deck opens on the expected six-slide run-in",
          order[:6] == ["cover", "rate-card-right-price",
                        "advertising-supermarket", SLIDE_ID,
                        "same-ad-different-rate",
                        "core-planning-media-plan"],
          json.dumps(order[:6]))

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
          labelled["id"] == "atlas-slide-upfront-scatter", labelled["id"])

    copy = c.eval("""(() => {
      const s = document.querySelector('.atlas-slide.is-active');
      const t = sel => s.querySelector(sel)?.textContent
        .replace(/\\s+/g, ' ').trim() || null;
      return {
        title: t('.usc__title'),
        subtitle: t('.usc__subtitle'),
        lines: [...s.querySelectorAll('.usc__deal, .usc__lede, .usc__note')]
          .map(n => n.textContent.trim()),
        dashes: /[\\u2013\\u2014]/.test(s.textContent),
        text: s.textContent.replace(/\\s+/g, ' ').trim(),
      };
    })()""")
    check("title matches the brief", copy["title"] == TITLE, copy["title"])
    check("subtitle matches the brief", copy["subtitle"] == SUBTITLE, copy["subtitle"])
    check("both columns read in the Figma order",
          copy["lines"] == LINES, json.dumps(copy["lines"]))
    check("no em or en dashes", not copy["dashes"])
    # Nothing the brief rules out crept in.
    banned = [w for w in ("OR", "takeaway", "Takeaway") if
              (f" {w} " in f" {copy['text']} ")]
    check("no OR label or takeaway line", not banned, json.dumps(banned))
    extras = c.eval("""(() => {
      const s = document.querySelector('.atlas-slide--upfront-scatter');
      const cs = el => getComputedStyle(el);
      const framed = [...s.querySelectorAll('.usc__group')].filter(g => {
        const st = cs(g);
        return st.borderTopWidth !== '0px' || st.backgroundColor !== 'rgba(0, 0, 0, 0)'
            || st.boxShadow !== 'none';
      }).length;
      return {
        groups: s.querySelectorAll('.usc__group').length,
        scenes: s.querySelectorAll('[id$="-scene"]').length,
        sources: [...new Set([...s.querySelectorAll('image')]
          .map(i => i.getAttribute('href')))],
        framed: framed,
      };
    })()""")
    # One shared room, one still plate, four drawings for every person's
    # timeline, and the delivered carton. Every drawing is its own file: two
    # people sharing one would be two chances to paint the same body twice.
    want_sources = (1 + sum(STILL_PLATE.values())
                    + len(POSES) * sum(ACTOR_WINDOWS.values()) + 1)
    check("exactly two columns, two inline scenes, no cards or borders",
          extras["groups"] == 2 and extras["scenes"] == 2
          and len(extras["sources"]) == want_sources
          and extras["framed"] == 0,
          json.dumps(dict(extras, want_sources=want_sources)))


# ----------------------------------------------------------------- geometry
def run_geometry(c, url):
    print("\n[geometry vs Figma 736:479]")
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
        const el = document.querySelector('.atlas-slide--upfront-scatter ' + sel);
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

    check("the two illustrations keep their own optical sizes",
          abs(measured[".usc__art--upfront"][2]
              - measured[".usc__art--scatter"][2]) > 0.1,
          f'{measured[".usc__art--upfront"][2]}'
          f' vs {measured[".usc__art--scatter"][2]}')

    style = json.loads(c.eval("""JSON.stringify((() => {
      const s = document.querySelector('.atlas-slide--upfront-scatter');
      const cs = el => getComputedStyle(el);
      const q = sel => cs(s.querySelector(sel));
      return {
        title: [q('.usc__title').fontSize, q('.usc__title').lineHeight,
                q('.usc__title').color],
        subtitle: [q('.usc__subtitle').fontSize, q('.usc__subtitle').lineHeight,
                   q('.usc__subtitle').color],
        deal: [q('.usc__deal').fontSize, q('.usc__deal').lineHeight,
               q('.usc__deal').color, q('.usc__deal').fontWeight],
        lede: [q('.usc__lede').fontSize, q('.usc__lede').lineHeight,
               q('.usc__lede').color, q('.usc__lede').fontWeight],
        note: [q('.usc__note').fontSize, q('.usc__note').lineHeight,
               q('.usc__note').color, q('.usc__note').fontWeight],
        headerGap: cs(s.querySelector('.usc__header')).gap,
        groupGap: cs(s.querySelector('.usc__group')).gap,
        copyGap: cs(s.querySelector('.usc__copy')).gap,
      };
    })())"""))
    check("header type matches Figma",
          style["title"][:2] == ["56px", "56px"]
          and style["subtitle"][:2] == ["36px", "56px"]
          and style["title"][2] == "rgb(255, 255, 255)",
          json.dumps({"title": style["title"], "subtitle": style["subtitle"]}))
    check("the deal name is 40px white",
          style["deal"][:1] == ["40px"] and style["deal"][2] == "rgb(255, 255, 255)"
          and style["deal"][3] == "900", json.dumps(style["deal"]))
    check("the summary line is 32px Figma blue",
          style["lede"][0] == "32px" and style["lede"][2] == "rgb(108, 184, 255)"
          and style["lede"][3] == "900", json.dumps(style["lede"]))
    check("the supporting line is 32px white medium",
          style["note"][0] == "32px" and style["note"][2] == "rgb(255, 255, 255)"
          and style["note"][3] == "500", json.dumps(style["note"]))
    check("gaps match Figma (header 8, column 28, copy 12)",
          style["headerGap"] == "8px" and style["groupGap"] == "28px"
          and style["copyGap"] == "12px", json.dumps(style))
    check("no visible text drops below 14px",
          not c.eval("""[...document.querySelectorAll(
            '.atlas-slide--upfront-scatter *')].filter(n => {
              if (!n.getClientRects().length) return false;
              const direct = [...n.childNodes].some(
                x => x.nodeType === Node.TEXT_NODE && x.textContent.trim());
              return direct && parseFloat(getComputedStyle(n).fontSize) < 14;
            }).map(n => String(n.className))"""))

    assets = c.eval("""(() => {
      const imgs = [...document.querySelectorAll(
        '.atlas-slide--upfront-scatter img')];
      return imgs.filter(i => !i.complete || i.naturalWidth === 0)
                 .map(i => i.getAttribute('src'));
    })()""")
    check("every slide asset loaded", not assets, json.dumps(assets))
    check("no asset depends on a remote or expiring URL",
          not c.eval("""[...document.querySelectorAll(
            '.atlas-slide--upfront-scatter img')]
            .filter(i => /^https?:/.test(i.getAttribute('src')))
            .map(i => i.getAttribute('src'))"""))
    art = json.loads(c.eval("""JSON.stringify((() => {
      const s = document.querySelector('.atlas-slide--upfront-scatter');
      return [...s.querySelectorAll('[id$="-scene"]')].map(svg => {
        const r = svg.getBoundingClientRect();
        const vb = (svg.getAttribute('viewBox') || '').split(/\\s+/).map(Number);
        return {id: svg.id, drawn: r.width / r.height, art: vb[2] / vb[3],
                label: svg.getAttribute('aria-label') || ''};
      });
    })())"""))
    check("both scenes are inline so their layers can be driven",
          len(art) == 2, json.dumps([a["id"] for a in art]))
    # Both scenes are drawn at the column width and compressed to 82% of
    # their height, so the drawn shape is exactly that much wider than the
    # artwork's own. Anything else means the squash was applied twice, or
    # not at all.
    check("both scenes carry the intended 82% height compression, once",
          all(abs(a["drawn"] / a["art"] - 1 / SQUASH) < 0.02 for a in art),
          json.dumps([round(a["drawn"] / a["art"], 4) for a in art])
          + f" against {round(1 / SQUASH, 4)}")
    check("meaningful illustrations carry a description",
          all(len(a["label"]) > 20 for a in art),
          json.dumps([a["label"][:40] for a in art]))


# ------------------------------------------------------------------- reveal
def run_reveal(c, url, label):
    print(f"\n[reveal @ {label}]")
    install_sampler(c)
    go(c, url + f"&slide={SLIDE_INDEX}")
    time.sleep((SEQUENCE_MS + SETTLE_MS) / 1000 + 0.6)

    samples = json.loads(c.eval("JSON.stringify(window.__uscSamples || [])") or "[]")
    check("the reveal was observed from the first frame",
          len(samples) > 30, f"{len(samples)} samples")
    counts = [len(x["shown"]) for x in samples]
    check("the slide starts with nothing revealed",
          bool(counts) and counts[0] == 0, f"first samples {counts[:3]}")
    check("stages only ever arrive, never disappear",
          all(b >= a for a, b in zip(counts, counts[1:])),
          json.dumps(counts[:30]))

    first_seen = {}
    for smp in samples:
        for name in smp["shown"]:
            first_seen.setdefault(name, smp["t"])
    check("the heading is the only thing that arrives on its own",
          sorted(first_seen) == ["header"], json.dumps(sorted(first_seen)))

    # The title and subtitle share one reveal target, so they cannot split.
    check("title and subtitle reveal as one element",
          c.eval("""(() => {
            const s = document.querySelector('.atlas-slide--upfront-scatter');
            const header = s.querySelector('.usc__header[data-usc-reveal]');
            return !!header
              && header.querySelectorAll('.usc__title, .usc__subtitle').length === 2
              && s.querySelectorAll('[data-usc-reveal]').length === 3
              && s.querySelectorAll('[data-usc-reveal] [data-usc-reveal]').length === 0;
          })()"""))
    # Each column owns its illustration and all three lines.
    check("each column reveals as one whole group",
          c.eval("""(() => {
            return ['upfront', 'scatter'].every(name => {
              const g = document.querySelector(
                '.usc__group--' + name + '[data-usc-reveal]');
              return g && g.querySelectorAll('.usc__art').length === 1
                && g.querySelectorAll(
                  '.usc__deal, .usc__lede, .usc__note').length === 3;
            });
          })()"""))

    laid_out = [x for x in samples if any(b[2] for b in x["boxes"].values())]
    baseline = laid_out[0] if laid_out else None
    check("space is reserved before anything is revealed",
          baseline is not None and not baseline["shown"],
          f"first laid-out sample showed {baseline['shown'] if baseline else None}")
    drifted = [x["t"] for x in laid_out if x["boxes"] != baseline["boxes"]]
    check("no element moved during the reveal",
          not drifted, f"drifted at {drifted[:3]}")
    check("the entrance ends complete", phase(c) == "complete", phase(c))
    check("both columns are still absent, not dimmed",
          revealed(c) == ["header"]
          and c.eval("""(() => ['upfront', 'scatter'].every(
            n => getComputedStyle(document.querySelector(
              '.usc__group--' + n)).opacity === '0'))()"""),
          json.dumps(revealed(c)))
    c.screenshot(f"{OUT}/{label}_complete.png")


def stage(c):
    """The presenter stage count the slide is currently showing."""
    return c.eval("document.querySelector('[data-upfront-scatter]')"
                  "?.dataset.uscStage || null")


def scenes(c):
    """Both columns' emphasis and timeline state, read from the live page."""
    return c.eval("""(() => {
      const host = document.querySelector('[data-upfront-scatter]');
      const one = n => {
        const g = host.querySelector('[data-usc-scene="' + n + '"]');
        if (!g) return null;
        return {
          revealed: g.classList.contains('is-revealed'),
          run: g.dataset.uscRun || null,
          moving: g.dataset.uscRun === 'running' ? 1 : 0,
          rest: g.dataset.uscRun === 'settled' ? 1 : 0,
          pose: [...g.querySelectorAll('[data-usc-pose]')]
            .filter(n => +(n.getAttribute('opacity') || 0) > 0.99)
            .map(n => n.dataset.uscPose).join(),
          parts: g.querySelectorAll('[data-usc-pose]').length,
          opacity: getComputedStyle(g).opacity,
          copy: getComputedStyle(g.querySelector('.usc__copy')).opacity,
        };
      };
      return {
        stage: host.dataset.uscStage,
        phase: host.dataset.uscPhase,
        active: document.querySelector('.atlas-slide.is-active')
          .dataset.atlasSlideId,
        upfront: one('upfront'),
        scatter: one('scatter'),
      };
    })()""")


def settle(c, url):
    """Open the slide and let its entrance finish, stage still at zero."""
    go(c, url + f"&slide={SLIDE_INDEX}")
    time.sleep((SEQUENCE_MS + SETTLE_MS) / 1000 + 0.4)


def run_interaction(c, url):
    print("\n[presenter stages]")
    settle(c, url)

    opening = scenes(c)
    check("the slide opens on the heading alone",
          opening["stage"] == "0"
          and not opening["upfront"]["revealed"]
          and not opening["scatter"]["revealed"]
          and not opening["upfront"]["moving"]
          and not opening["scatter"]["moving"]
          and opening["upfront"]["opacity"] == HIDDEN
          and opening["scatter"]["opacity"] == HIDDEN,
          json.dumps(opening))
    check("the title and subtitle are up from the start",
          c.eval("""(() => getComputedStyle(document.querySelector(
            '.atlas-slide--upfront-scatter .usc__header')).opacity)()""") == "1")
    check("a column is genuinely absent, not dimmed",
          c.eval("""(() => ['upfront', 'scatter'].every(n => {
            const g = document.querySelector('.usc__group--' + n);
            return getComputedStyle(g).opacity === '0';
          }))()"""))
    check("nobody is working before the presenter opens a column",
          c.eval("""(() => {
            const s = document.querySelector('.atlas-slide--upfront-scatter');
            return [...s.querySelectorAll('[data-usc-scene]')].every(g =>
              g.dataset.uscRun === 'ready'
              && +(g.querySelector('[data-usc-pose="01-pickup"]')
                    .getAttribute('opacity')) === 1);
          })()"""))

    # Mouse, ArrowRight and Space must walk the identical two stages.
    for label, act in (
        ("a click", lambda: c.click_stage()),
        ("ArrowRight", lambda: c.key("ArrowRight", "ArrowRight", 39)),
        ("Space", lambda: c.key(" ", "Space", 32)),
    ):
        settle(c, url)
        act()
        time.sleep(0.45)
        inflight = scenes(c)
        check(f"{label} sets Upfront's people going",
              inflight["upfront"]["moving"] > 0
              and inflight["upfront"]["rest"] < 1,
              json.dumps(inflight["upfront"]))
        check(f"{label} leaves Scatter alone while Upfront runs",
              inflight["scatter"]["moving"] == 0
              and inflight["scatter"]["opacity"] == HIDDEN,
              json.dumps(inflight["scatter"]))
        time.sleep(STAGE_WAIT - 0.45)
        one = scenes(c)
        check(f"{label} reveals Upfront and only Upfront",
              one["stage"] == "1" and one["active"] == SLIDE_ID
              and one["upfront"]["revealed"]
              and one["upfront"]["moving"] == 1
              and one["upfront"]["opacity"] == "1"
              and not one["scatter"]["revealed"]
              and not one["scatter"]["moving"]
              and one["scatter"]["opacity"] == HIDDEN,
              json.dumps(one))

        # Nothing but a gesture may move the slide on.
        time.sleep(2.0)
        held = scenes(c)
        check(f"{label}: Upfront finishing does not reveal Scatter",
              held["stage"] == "1" and not held["scatter"]["revealed"]
              and held["active"] == SLIDE_ID, json.dumps(held))

        act()
        time.sleep(STAGE_WAIT)
        two = scenes(c)
        check(f"{label} then reveals Scatter, with Upfront still up",
              two["stage"] == "2" and two["active"] == SLIDE_ID
              and two["upfront"]["revealed"] and two["upfront"]["opacity"] == "1"
              and two["upfront"]["moving"] == 1
              and two["scatter"]["revealed"]
              and two["scatter"]["moving"] == 1
              and two["scatter"]["opacity"] == "1",
              json.dumps(two))

        act()
        time.sleep(0.6)
        check(f"{label} after both stages hands the deck back",
              slide_id(c) == "same-ad-different-rate", f"id={slide_id(c)}")

    check("the slide owns exactly two presenter stages",
          c.eval("""(() => document.querySelectorAll(
            '.atlas-slide--upfront-scatter [data-usc-scene]').length)()""") == 2)

    # A gesture arriving while a column is still telling its story has to be
    # swallowed, or one stray double click would skip Upfront onto Scatter.
    for label, script in (
        ("a double click",
         "const w = document.querySelector('.atlas-stage-wrap');"
         "w.click(); w.click();"),
        ("a triple click",
         "const w = document.querySelector('.atlas-stage-wrap');"
         "w.click(); w.click(); w.click();"),
    ):
        settle(c, url)
        c.eval(script + " true")
        time.sleep(0.5)
        mid = scenes(c)
        check(f"{label} mid-story does not reach Scatter",
              mid["stage"] == "1" and not mid["scatter"]["revealed"]
              and mid["active"] == SLIDE_ID, json.dumps(mid))
        time.sleep(STAGE_RUNTIME["upfront"])
        after = scenes(c)
        check(f"{label} still leaves the slide on Upfront once it settles",
              after["stage"] == "1" and not after["scatter"]["revealed"]
              and after["active"] == SLIDE_ID, json.dumps(after))

    # A presenter is allowed to move on while a column is still working, so
    # a run no longer blocks the next gesture. What must never happen is a
    # held key running away through the deck, or one press spending two
    # stages at once.
    settle(c, url)
    for _ in range(4):
        c.key("ArrowRight", "ArrowRight", 39)
        time.sleep(0.12)
    time.sleep(0.5)
    hammered = scenes(c)
    check("a held Arrow Right never runs past this slide",
          hammered["active"] == SLIDE_ID
          and int(hammered["stage"]) <= len(("upfront", "scatter")),
          json.dumps(hammered))

    # The tail of one press must still be swallowed: two events inside the
    # guard may only ever be worth a single stage.
    settle(c, url)
    twin = json.loads(c.eval("""(async () => {
      const wait = ms => new Promise(r => setTimeout(r, ms));
      const stage = () => +(document.querySelector('[data-upfront-scatter]')
        .dataset.uscStage || 0);
      const w = document.querySelector('.atlas-stage-wrap');
      w.click(); w.click(); w.click();
      await wait(120);
      return JSON.stringify({ after: stage() });
    })()"""))
    check("three events in one burst are still worth one stage",
          twin["after"] == 1, json.dumps(twin))

    # A gesture during the heading run buys the heading, not a stage. The
    # heading is only up for a moment now, so the click is fired the instant
    # the run is seen rather than after a fixed sleep.
    c.send("Page.navigate", {"url": url + f"&slide={SLIDE_INDEX}&qa=heading"})
    early = json.loads(c.eval("""(async () => {
      const wait = ms => new Promise(r => setTimeout(r, ms));
      const host = () => document.querySelector('[data-upfront-scatter]');
      // data-usc-stage is only written once the controller has run, so
      // waiting for it avoids clicking before the slide can hear it.
      for (let i = 0; i < 400; i += 1) {
        if (host() && host().dataset.uscStage !== undefined
            && host().dataset.uscPhase === 'revealing'
            && document.querySelector('.atlas-slide.is-active')) break;
        await wait(10);
      }
      const before = host().dataset.uscPhase;
      document.querySelector('.atlas-stage-wrap').click();
      await wait(140);
      return JSON.stringify({
        before,
        phase: host().dataset.uscPhase,
        stage: host().dataset.uscStage,
        shown: document.querySelectorAll('[data-usc-reveal].is-revealed').length,
        active: document.querySelector('.atlas-slide.is-active')
          .dataset.atlasSlideId,
      });
    })()"""))
    check("a gesture during the heading lands mid-heading",
          early["before"] == "revealing", json.dumps(early))
    check("it finishes the heading and spends no stage",
          early["phase"] == "complete" and early["stage"] == "0"
          and early["shown"] == 1 and early["active"] == SLIDE_ID,
          json.dumps(early))


def run_impatient(c, url):
    """A presenter who moves on mid-run must not be ignored."""
    print("\n[clicking on while a column is still moving]")
    settle(c, url)
    got = json.loads(c.eval("""(async () => {
      const wait = ms => new Promise(r => setTimeout(r, ms));
      const stage = () => +(document.querySelector('[data-upfront-scatter]')
        .dataset.uscStage || 0);
      const click = () => document.querySelector('.atlas-stage-wrap').click();
      const out = {};
      click(); await wait(400); out.first = stage();
      click(); await wait(400); out.midRun = stage();
      return JSON.stringify(out);
    })()"""))
    check("the first gesture opens Upfront", got["first"] == 1,
          json.dumps(got))
    check("a gesture during its run opens Scatter rather than being dropped",
          got["midRun"] == 2, json.dumps(got))

    # But one physical press must never spend two stages.
    settle(c, url)
    twice = json.loads(c.eval("""(async () => {
      const wait = ms => new Promise(r => setTimeout(r, ms));
      const stage = () => +(document.querySelector('[data-upfront-scatter]')
        .dataset.uscStage || 0);
      document.querySelector('.atlas-stage-wrap').click();
      await wait(60);
      return JSON.stringify({after: stage()});
    })()"""))
    check("one press spends exactly one stage", twice["after"] == 1,
          json.dumps(twice))


def run_reverse(c, url):
    print("\n[reverse]")
    settle(c, url)
    for _ in range(2):
        c.click_stage()
        time.sleep(STAGE_WAIT)
    check("primed with both columns up", stage(c) == "2", stage(c))

    c.key("ArrowLeft", "ArrowLeft", 37)
    time.sleep(0.6)
    back1 = scenes(c)
    check("back hides Scatter and leaves Upfront standing",
          back1["stage"] == "1" and back1["active"] == SLIDE_ID
          and back1["upfront"]["revealed"] and back1["upfront"]["opacity"] == "1"
          and not back1["scatter"]["revealed"]
          and not back1["scatter"]["moving"]
          and back1["scatter"]["opacity"] == HIDDEN, json.dumps(back1))
    check("Scatter is back on its first pose, ready to run again",
          c.eval("""(() => {
            const g = document.querySelector('.usc__group--scatter');
            return g.dataset.uscRun === 'ready'
              && +(g.querySelector('[data-usc-pose="01-pickup"]')
                    .getAttribute('opacity')) === 1
              && +(g.querySelector('[data-usc-pose="04-release"]')
                    .getAttribute('opacity')) === 0;
          })()"""))

    c.key("ArrowLeft", "ArrowLeft", 37)
    time.sleep(0.6)
    back2 = scenes(c)
    check("the next back returns the slide to the heading alone",
          back2["stage"] == "0" and back2["active"] == SLIDE_ID
          and not back2["upfront"]["revealed"]
          and not back2["upfront"]["moving"]
          and back2["upfront"]["opacity"] == HIDDEN, json.dumps(back2))
    check("Upfront is back on its first pose too",
          c.eval("""(() => {
            const g = document.querySelector('.usc__group--upfront');
            return g.dataset.uscRun === 'ready'
              && +(g.querySelector('[data-usc-pose="01-pickup"]')
                    .getAttribute('opacity')) === 1
              && +(g.querySelector('[data-usc-pose="04-release"]')
                    .getAttribute('opacity')) === 0;
          })()"""))

    c.key("ArrowLeft", "ArrowLeft", 37)
    time.sleep(0.6)
    check("back past the first stage leaves the slide",
          slide_id(c) == "advertising-supermarket", f"id={slide_id(c)}")


def run_reset(c, url):
    print("\n[reset and timer cleanup]")
    settle(c, url)
    check("primed with the heading finished", phase(c) == "complete", phase(c))
    for _ in range(2):
        c.click_stage()
        time.sleep(STAGE_WAIT)
    check("both columns up before leaving", stage(c) == "2", stage(c))

    c.key("ArrowRight", "ArrowRight", 39)
    time.sleep(0.6)
    check("the deck moves on once both stages are spent",
          slide_id(c) == "same-ad-different-rate", f"id={slide_id(c)}")
    check("leaving cleared the run and both stages",
          phase(c) == "revealing" and revealed(c) == [] and stage(c) == "0",
          f"phase={phase(c)} stage={stage(c)} revealed={revealed(c)}")

    c.key("ArrowLeft", "ArrowLeft", 37)
    time.sleep(0.15)
    check("re-entering starts from the initial state",
          len(revealed(c)) < len(REVEAL_ORDER), json.dumps(revealed(c)))
    time.sleep((SEQUENCE_MS + SETTLE_MS) / 1000 + 0.4)
    back = scenes(c)
    check("re-entering replays the heading and holds at stage zero",
          revealed(c) == ["header"]
          and back["phase"] == "complete" and back["stage"] == "0"
          and not back["upfront"]["revealed"]
          and not back["scatter"]["revealed"], json.dumps(back))

    # Backward off the slide resets it too.
    c.key("ArrowLeft", "ArrowLeft", 37)
    time.sleep(0.6)
    check("back navigation lands on the supermarket slide",
          slide_id(c) == "advertising-supermarket", f"id={slide_id(c)}")
    check("back navigation cleared the run",
          phase(c) == "revealing" and revealed(c) == [] and stage(c) == "0",
          f"phase={phase(c)} stage={stage(c)}")

    go(c, url + f"&slide={SLIDE_INDEX}")
    time.sleep(0.4)
    c.key("ArrowLeft", "ArrowLeft", 37)
    time.sleep((SEQUENCE_MS + SETTLE_MS) / 1000 + 0.4)
    check("a pending stage cannot fire onto another slide",
          revealed(c) == [] and phase(c) == "revealing",
          f"phase={phase(c)} revealed={revealed(c)}")
    check("the deck stayed where the presenter left it",
          slide_id(c) == "advertising-supermarket", f"id={slide_id(c)}")

    # Repeated entry must not stack duplicate listeners or timers.
    for _ in range(3):
        settle(c, url)
        c.click_stage()
        time.sleep(STAGE_WAIT)
        c.key("ArrowLeft", "ArrowLeft", 37)
        time.sleep(0.6)
    settle(c, url)
    c.click_stage()
    time.sleep(STAGE_WAIT)
    repeated = scenes(c)
    check("repeated entry and exit still opens exactly one stage",
          repeated["stage"] == "1" and repeated["upfront"]["revealed"]
          and not repeated["scatter"]["revealed"], json.dumps(repeated))


# Where the export already draws each person's hands, in illustration units.
# Every moving object has to start at one of these and finish nearby, which
# is what stops anything crossing the scene on its own.
HANDS = {
    "upfront": {
        "box-a": (234, 158), "box-b": (234, 158), "box-c": (234, 158),
        "van-box": (337, 162),
    },
    "scatter": {
        "prod-1": (122, 192), "prod-2": (205, 145), "prod-3": (348, 246),
    },
}
# A carried object may not begin further than this from the hands holding
# it, nor travel further than a person can reach without walking.
# Every beat has to be worth seeing at the size the room is actually drawn
# at, so these are measured against the rendered scene, not the source
# artwork.
#
# The floor is deliberately low. Each layer is now a cut-out of one
# timeline's people and nothing else, so a beat repaints only the body that
# moved: no dissolving shelves, no restated floor, none of the scenery churn
# that used to pad this number out. Upfront's pair swing a carton between
# them and run 2.3 to 5.7 percent a beat; Scatter's three restock from where
# they stand and run 0.7 to 1.1, the smallest being all three changing the
# reach of an arm. A beat where nobody moved repaints nothing at all, so a
# floor at half a percent still catches one while clearing honest work.
MIN_BEAT_CHANGE = 0.005
MAX_BEAT_CHANGE = 0.30


def run_handling(c, url):
    """The people pick the goods up, put them down, and let go."""
    print("\n[picking up, putting down, letting go]")
    settle(c, url)

    shape = json.loads(c.eval("""JSON.stringify((() => {
      const s = document.querySelector('.atlas-slide--upfront-scatter');
      const out = {};
      ['upfront', 'scatter'].forEach(scene => {
        const svg = s.querySelector('#' + scene + '-scene');
        const poses = [...svg.querySelectorAll('[data-usc-pose]')];
        out[scene] = {
          order: poses.map(n => n.dataset.uscPose),
          rooms: [...svg.querySelectorAll('.usc__room')].map(
            n => n.getAttribute('href')),
          animated: svg.getAnimations({subtree: true}).length,
          run: svg.closest('[data-usc-scene]').dataset.uscRun,
        };
      });
      return out;
    })())"""))

    for scene, got in sorted(shape.items()):
        check(f"{scene} carries the four handling poses, in order",
              got["order"] == POSES * ACTOR_WINDOWS[scene],
              json.dumps(got["order"]))
        plate = c.eval(
            "(document.querySelector('#%s-scene .usc__plate') || {})"
            ".getAttribute?.('href') || null" % scene)
        if STILL_PLATE[scene]:
            check(f"{scene} holds its still people on their own plate",
                  bool(plate) and plate.endswith(f"{scene}-plate.png"), str(plate))
        else:
            check(f"{scene} has no still plate, because everyone in it moves",
                  plate is None, str(plate))
        check(f"{scene} draws its room from one shared image",
              len(got["rooms"]) == 1
              and got["rooms"][0].endswith("upfront-scatter-room.png"),
              json.dumps(got["rooms"]))
        check(f"{scene} runs no CSS animation of its own",
              got["animated"] == 0, str(got["animated"]))
        check(f"{scene} waits on the first pose before anyone clicks",
              got["run"] == "ready", str(got["run"]))

    # The one rule the whole scene rests on: a person can only be drawn once.
    # Each timeline owns its own set of drawings, no drawing is shared with
    # another timeline, and nothing is cropped, so no pose can leave part of
    # a body behind or paint a second copy of somebody.
    for scene in ("upfront", "scatter"):
        lanes = json.loads(c.eval("""JSON.stringify((() => {
          const svg = document.querySelector('#%s-scene');
          return {
            lanes: [...svg.querySelectorAll('[data-usc-window]')].map(g =>
              [...g.querySelectorAll('[data-usc-pose]')].map(
                n => n.getAttribute('href'))),
            clipped: [...svg.querySelectorAll('[clip-path]')].length,
            defs: svg.querySelectorAll('clipPath').length,
          };
        })())""" % scene))
        flat = [src for lane in lanes["lanes"] for src in lane]
        check(f"{scene} runs {ACTOR_WINDOWS[scene]} timeline(s), one per person",
              len(lanes["lanes"]) == ACTOR_WINDOWS[scene], json.dumps(lanes["lanes"]))
        check(f"{scene} gives each timeline four drawings of its own",
              all(len(set(lane)) == len(POSES) for lane in lanes["lanes"]),
              json.dumps([len(set(x)) for x in lanes["lanes"]]))
        check(f"{scene} never shares a drawing between two timelines",
              len(set(flat)) == len(flat),
              f"{len(flat)} drawings, {len(set(flat))} unique")
        check(f"{scene} crops nothing, so no figure can be half drawn",
              lanes["clipped"] == 0 and lanes["defs"] == 0, json.dumps(lanes))

    # Nothing on screen may be partly see-through. Every layer is either the
    # drawing being shown or fully switched off, both dark and hidden, so a
    # previous pose cannot linger underneath the current one.
    lit = json.loads(c.eval("""JSON.stringify((() => {
      const bad = [];
      document.querySelectorAll('[data-usc-window]').forEach(g => {
        const poses = [...g.querySelectorAll('[data-usc-pose]')];
        const on = poses.filter(n => n.getAttribute('opacity') !== '0');
        if (on.length !== 1) bad.push('lit=' + on.map(n => n.dataset.uscPose).join('+'));
        poses.forEach(n => {
          const o = n.getAttribute('opacity');
          if (o !== '0' && o !== '1') bad.push('part opacity ' + o);
          const want = o === '1' ? 'visible' : 'hidden';
          if (n.style.visibility !== want) {
            bad.push(n.dataset.uscPose + ' is ' + n.style.visibility + ', wanted ' + want);
          }
        });
      });
      return bad;
    })())"""))
    check("exactly one drawing is painted per person, the rest fully off",
          lit == [], json.dumps(lit))

    # The goods must end up on a surface with nobody holding them, so the
    # last pose in the stack is the one that shows empty hands. Upfront also
    # carries a layer above the poses for the carton that has already been
    # delivered, which is what lets the worker walk back for the next one
    # without the last one blinking out.
    for scene in ("upfront", "scatter"):
        end = json.loads(c.eval("""JSON.stringify((() => {
          const g = document.querySelector('[data-usc-scene="%s"]');
          const svg = g.querySelector('svg');
          const poses = [...svg.querySelectorAll('[data-usc-pose]')];
          const placed = svg.querySelector('[data-usc-placed]');
          return {
            lastOnTop: poses.pop().dataset.uscPose,
            placed: !!placed,
            placedAbovePoses: placed
              ? [...placed.parentNode.children].indexOf(placed)
                > [...placed.parentNode.children].indexOf(
                    placed.parentNode.querySelector(
                      '[data-usc-pose="04-release"]'))
              : null,
          };
        })())""" % scene))
        check(f"{scene} finishes on the pose with empty hands",
              end["lastOnTop"] == "04-release", json.dumps(end))
        if scene == "upfront":
            check("the delivered carton sits above the poses that place it",
                  end["placed"] and end["placedAbovePoses"], json.dumps(end))

    # The place and release drawings already contain the carton standing on
    # the stack. Painting the separate carton layer over either of them would
    # lay two slightly different drawings of the same box on the same spot,
    # which reads as a doubled edge.
    doubled = json.loads(c.eval("""JSON.stringify((() => {
      const bad = [];
      document.querySelectorAll('[data-usc-placed]').forEach(carton => {
        if (carton.getAttribute('opacity') !== '1') return;
        const lit = [...carton.parentNode.querySelectorAll('[data-usc-pose]')]
          .filter(n => n.getAttribute('opacity') === '1')
          .map(n => n.dataset.uscPose);
        lit.forEach(p => {
          if (p === '03-place' || p === '04-release') bad.push('carton twice over ' + p);
        });
      });
      return bad;
    })())"""))
    check("the delivered carton is never drawn on top of itself",
          doubled == [], json.dumps(doubled))


def run_readable(c, url):
    """Each beat repaints enough of the scene to be seen from the back row."""
    print("\n[readable at presentation size]")
    settle(c, url)
    c.eval("document.querySelector('.atlas-stage-wrap').click()")
    time.sleep(STAGE_WAIT)
    c.eval("document.querySelector('.atlas-stage-wrap').click()")
    time.sleep(STAGE_WAIT)

    # Compare consecutive beats pixel by pixel, at the size the scene is
    # actually drawn at. A bounding box comparison would miss two poses that
    # occupy the same rectangle, which is exactly the case for the last two
    # Upfront beats.
    for scene in ("upfront", "scatter"):
        got = json.loads(c.eval("""(async () => {
          const svg = document.querySelector('#%s-scene');
          const box = svg.getBoundingClientRect();
          const vb = svg.viewBox.baseVal;
          const W = Math.round(box.width), H = Math.round(box.height);
          const load = src => new Promise(res => {
            const im = new Image();
            im.onload = () => res(im);
            im.src = src;
          });
          const paint = async node => {
            const cv = document.createElement('canvas');
            cv.width = W; cv.height = H;
            const g = cv.getContext('2d');
            const im = await load(node.getAttribute('href'));
            g.drawImage(im,
              (+node.getAttribute('x')) * W / vb.width,
              (+node.getAttribute('y')) * H / vb.height,
              (+node.getAttribute('width')) * W / vb.width,
              (+node.getAttribute('height')) * H / vb.height);
            return g.getImageData(0, 0, W, H).data;
          };
          const order = %s;
          const layers = {};
          svg.querySelectorAll('[data-usc-pose]').forEach(
            n => { layers[n.dataset.uscPose] = n; });
          const out = [];
          let prev = await paint(layers[order[0]]);
          for (let i = 1; i < order.length; i += 1) {
            const cur = await paint(layers[order[i]]);
            let changed = 0;
            for (let p = 0; p < cur.length; p += 4) {
              const da = Math.abs(cur[p + 3] - prev[p + 3]);
              const dc = Math.abs(cur[p] - prev[p])
                + Math.abs(cur[p + 1] - prev[p + 1])
                + Math.abs(cur[p + 2] - prev[p + 2]);
              if (da > 40 || (cur[p + 3] > 40 && prev[p + 3] > 40 && dc > 60)) {
                changed += 1;
              }
            }
            out.push({ from: order[i - 1], to: order[i], px: changed,
                       share: changed / (W * H) });
            prev = cur;
          }
          return JSON.stringify(out);
        })()""" % (scene, json.dumps(POSES))))
        for step in got:
            check(f"{scene} {step['from'][3:]} to {step['to'][3:]} "
                  "repaints a visible area",
                  step["share"] >= MIN_BEAT_CHANGE,
                  f"{step['px']:,} px, {step['share'] * 100:.2f}% of the scene")
            check(f"{scene} {step['from'][3:]} to {step['to'][3:]} "
                  "stays a movement, not a scene change",
                  step["share"] <= MAX_BEAT_CHANGE,
                  f"{step['share'] * 100:.2f}%")


def run_layout(c, url, label):
    print(f"\n[layout and rounded frame @ {label}]")
    go(c, url + f"&slide={SLIDE_INDEX}")
    time.sleep((SEQUENCE_MS + SETTLE_MS) / 1000 + 0.4)

    frame = c.eval("""(() => {
      const stage = document.querySelector('.atlas-stage');
      const wrap = document.querySelector('.atlas-stage-wrap');
      const deck = document.querySelector('.atlas-deck');
      const cs = el => getComputedStyle(el);
      const sr = stage.getBoundingClientRect();
      const wr = wrap.getBoundingClientRect();
      const up = document.querySelector('.usc__group--upfront')
                         .getBoundingClientRect();
      const sc = document.querySelector('.usc__group--scatter')
                         .getBoundingClientRect();
      return {
        radius: cs(stage).borderTopLeftRadius,
        overflow: cs(stage).overflow,
        canvas: cs(deck).backgroundColor,
        slideBg: cs(document.querySelector('.atlas-slide--upfront-scatter'))
          .backgroundColor,
        pads: [sr.top - wr.top, sr.left - wr.left,
               wr.right - sr.right, wr.bottom - sr.bottom],
        escaped: [...document.querySelectorAll(
          '.atlas-slide--upfront-scatter .usc > *')].filter(n => {
            const r = n.getBoundingClientRect();
            if (!r.width && !r.height) return false;
            return r.left < sr.left - 0.5 || r.right > sr.right + 0.5
                || r.top < sr.top - 0.5 || r.bottom > sr.bottom + 0.5;
          }).map(n => n.className),
        sideBySide: up.right <= sc.left + 0.5
          && Math.abs(up.top - sc.top) < 0.5,
        upfrontLeft: up.left < sc.left,
        scrolls: document.documentElement.scrollWidth > innerWidth + 1
              || document.documentElement.scrollHeight > innerHeight + 1,
        clipped: [...document.querySelectorAll(
          '.usc__title, .usc__subtitle, .usc__deal, .usc__lede, .usc__note')]
          .filter(n => n.scrollWidth > n.clientWidth + 1
                    || n.getClientRects().length !== 1)
          .map(n => String(n.className)),
      };
    })()""")
    check("the slide viewport carries the 40px radius",
          frame["radius"] == f"{STAGE_RADIUS}px", frame["radius"])
    check("the slide viewport clips its contents",
          frame["overflow"] == "hidden", frame["overflow"])
    check("the canvas is the shared presentation grey, the slide stays navy",
          frame["canvas"] == CANVAS and frame["slideBg"] == SLIDE_BG,
          f'canvas={frame["canvas"]} slide={frame["slideBg"]}')
    check("the slide is not flush to the browser edges",
          min(frame["pads"]) >= 24,
          json.dumps([round(p, 1) for p in frame["pads"]]))
    check("nothing paints outside the rounded frame",
          not frame["escaped"], json.dumps(frame["escaped"]))
    check("the two columns stay side by side without overlapping",
          frame["sideBySide"], frame["sideBySide"])
    check("Upfront stays on the left, Scatter on the right",
          frame["upfrontLeft"], frame["upfrontLeft"])
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
        """A point just inside a corner, in the slide's own coordinates.

        Anchored in native pixels so it stays in the slide's empty margin
        at every scale; a fixed screen offset lands on the title once the
        stage shrinks.
        """
        return (int(corners["l"] + nx * scale), int(corners["t"] + ny * scale))

    for name, (outside, inside_pt) in {
        "top-left": ((x0 + 3, y0 + 3), inset(36, 36)),
        "top-right": ((x1 - 3, y0 + 3), inset(1884, 36)),
        "bottom-left": ((x0 + 3, y1 - 3), inset(36, 1044)),
        "bottom-right": ((x1 - 3, y1 - 3), inset(1884, 1044)),
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
          return {
            header: cs(document.querySelector('.usc__header')).transform,
            group: cs(document.querySelector('.usc__group--upfront')).transform,
            duration: cs(document.querySelector('.usc__group--upfront'))
              .transitionDuration,
          };
        })()""")
        check("nothing travels or scales under reduced motion",
              motion["header"] == "none" and motion["group"] == "none",
              json.dumps(motion))
        check("fades are short under reduced motion",
              motion["duration"] == "0.12s", motion["duration"])

        time.sleep((SEQUENCE_MS + SETTLE_MS) / 1000 + 0.4)
        check("the heading still arrives on its own",
              revealed(c) == ["header"] and phase(c) == "complete", phase(c))
        check("both columns are still held back",
              stage(c) == "0"
              and c.eval("""(() => ['upfront', 'scatter'].every(
                n => getComputedStyle(document.querySelector(
                  '.usc__group--' + n)).opacity === '0'))()"""), stage(c))

        # Under reduced motion the scenes arrive on the approved drawing
        # and stay on it: the columns crossfade, the people never work.
        columns = c.eval("""(() => {
          const cs = getComputedStyle(document.querySelector(
            '.usc__group--upfront'));
          return {transition: cs.transitionProperty,
                  duration: cs.transitionDuration,
                  transform: cs.transform};
        })()""")
        check("the columns crossfade rather than travel",
              columns["transition"] == "opacity"
              and columns["transform"] == "none", json.dumps(columns))
        check("that crossfade is short",
              round(float(columns["duration"].rstrip("s")) * 1000) <= 250,
              columns["duration"])

        c.click_stage()
        time.sleep(0.6)
        one = scenes(c)
        check("the first action still reveals Upfront alone",
              one["stage"] == "1" and one["upfront"]["revealed"]
              and one["upfront"]["opacity"] == "1"
              and not one["scatter"]["revealed"]
              and one["scatter"]["opacity"] == HIDDEN
              and one["active"] == SLIDE_ID, json.dumps(one))
        check("Upfront holds the approved drawing, with nobody working",
              set(one["upfront"]["pose"].split(",")) == {"02-handoff"}
              and one["upfront"]["run"] == "settled"
              and one["upfront"]["moving"] == 0,
              json.dumps(one["upfront"]))

        c.click_stage()
        time.sleep(0.6)
        two = scenes(c)
        check("the second action reveals Scatter, one stage per action",
              two["stage"] == "2" and two["scatter"]["revealed"]
              and two["scatter"]["opacity"] == "1"
              and two["active"] == SLIDE_ID, json.dumps(two))
        check("Scatter holds the approved drawing too",
              set(two["scatter"]["pose"].split(",")) == {"02-handoff"}
              and two["scatter"]["run"] == "settled"
              and two["scatter"]["moving"] == 0,
              json.dumps(two["scatter"]))
        check("and no pose timeline ever ran",
              set(two["upfront"]["pose"].split(",")) == {"02-handoff"},
              json.dumps(two["upfront"]))

        c.click_stage()
        time.sleep(0.6)
        check("the following gesture still advances",
              slide_id(c) == "same-ad-different-rate", f"id={slide_id(c)}")
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
            run_reveal(c, url, "1920x1080")
            run_interaction(c, url)
            run_handling(c, url)
            run_readable(c, url)
            run_impatient(c, url)
            run_reverse(c, url)
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
                run_reveal(c, url, label)
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
