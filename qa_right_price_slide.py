#!/usr/bin/env python3
"""
qa_right_price_slide.py - Atlas deck slide 2 QA.

Slide 2, "A Rate Card tells us the right price for each deal", is authored
from Figma node 736:248. It is the deck's only slide that withholds part of
its own content: the formula assembles itself, then the slide stops and
waits for the presenter before showing the gold Right Price card.

What this suite locks down:

  - Deck placement. Slide 2 of 14, sitting between the cover and
    the supermarket metaphor, with no existing slide dropped or renamed.
  - Geometry against the Figma frame, at the native 1920x1080 stage.
  - The reveal sequence: nothing visible on entry, terms and operators
    arriving in order, and the run ending in `waiting-for-result` with the
    result still hidden.
  - No layout shift. Every animated element occupies its final box from
    the first frame, so its rect must not move while it fades in.
  - Interaction ownership. Click / Space / Enter belong to the slide until
    the result is up; ArrowRight never does. The gesture that reveals the
    result must not also advance the deck, and a double click or a held
    key must not skip a slide.
  - Reset. Leaving the slide clears the run, and coming back replays it.
  - Reduced motion, which keeps the staging but drops the travel.
  - Rounded corners: the stage clips at 40px and the canvas behind it is
    darker than the slide, so all four corners are actually visible.

Timings mirror the constants in initAtlasRightPrice (app.js).
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
OUT = "/tmp/qa_right_price_slide"
SLIDE_INDEX = 2
SLIDE_ID = "rate-card-right-price"
TOTAL_SLIDES = 12

# The whole automatic run, in ms, from entry to `waiting-for-result`:
# LEAD_IN 260 + 3 * (TERM_TO_OP 180 + OP_TO_TERM 200) + TERM_TO_OP 180.
SEQUENCE_MS = 1580
SETTLE_MS = 900          # longest transition (result) plus a margin
STAGE_RADIUS = 40
CANVAS = "rgb(30, 30, 30)"
SLIDE_BG = "rgb(2, 0, 36)"

# Figma 736:248 geometry, in native stage pixels.
FIGMA = {
    ".rpx__header": (63, 88, None, None),
    ".rpx__group--buyer": (63, 392, 230.4, None),
    ".rpx__group--deal": (384, 392, 230.4, None),
    ".rpx__group--product": (700, 392, 241, None),
    ".rpx__group--price-change": (1026, 392, 261, None),
    ".rpx__group--result": (1391, 392, 230.4, None),
    ".rpx__operator--plus-1": (314, 471, 50, 50),
    ".rpx__operator--plus-2": (635, 471, 45, 45),
    ".rpx__operator--plus-3": (961, 471, 45, 45),
    ".rpx__operator--equals": (1307, 470, 45, 45),
    ".rpx__logo": (1826, 997, 36, 41),
}

REVEAL_ORDER = [
    "term-1", "op-1", "term-2", "op-2",
    "term-3", "op-3", "term-4", "op-4",
]

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

    def eval(self, expression, await_promise=False):
        out = self.send("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": await_promise,
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
        """Click the slide canvas the way a presenter does."""
        self.eval("document.querySelector('.atlas-stage-wrap').click()")

    def screenshot(self, path):
        data = self.send("Page.captureScreenshot", {"format": "png"})
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(base64.b64decode(data["data"]))


def boot_chrome(viewport, reduced=False, port_http=None, slide=SLIDE_INDEX):
    port = free_port()
    profile = f"/tmp/qa_rpx_profile_{port}"
    subprocess.run(["rm", "-rf", profile], check=False)
    args = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile}",
        "--headless=new",
        "--remote-allow-origins=*",
        "--no-first-run",
        "--hide-scrollbars",
        "--force-device-scale-factor=1",
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
    time.sleep(1.3)


def phase(c):
    return c.eval(
        "document.querySelector('[data-right-price]')"
        "?.getAttribute('data-rpx-phase')"
    )


def slide_id(c):
    return c.eval(
        "document.querySelector('.atlas-slide.is-active')?.dataset.atlasSlideId"
    )


def revealed(c):
    return c.eval(
        "[...document.querySelectorAll('[data-rpx-reveal]')]"
        ".filter(n => n.classList.contains('is-revealed'))"
        ".map(n => n.dataset.rpxReveal)"
    )


def result_opacity(c):
    return float(c.eval(
        "getComputedStyle(document.querySelector('.rpx__group--result')).opacity"
    ))


def boxes(c):
    """Layout boxes in native stage pixels.

    Deliberately offset* and not getBoundingClientRect: the reveal moves
    elements with transforms, which a client rect would report as
    movement. Layout position is what must not shift.
    """
    return c.eval("""JSON.stringify((() => {
      const out = {};
      document.querySelectorAll('[data-rpx-reveal], .rpx__group--result')
        .forEach(node => {
          const key = node.dataset.rpxReveal || 'result';
          out[key] = [node.offsetLeft, node.offsetTop,
                      node.offsetWidth, node.offsetHeight];
        });
      return out;
    })())""")


def pin_native_scale(c):
    """Freeze the stage at 1:1 so geometry can be read in Figma pixels."""
    c.eval("""(() => {
      const style = document.createElement('style');
      style.textContent = `.atlas-stage{--atlas-scale:1 !important;margin:0 !important}
        .atlas-stage-wrap{padding:0 !important;overflow:visible !important}
        .atlas-deck{position:absolute !important}`;
      document.head.appendChild(style);
    })()""")
    time.sleep(0.4)


# ---------------------------------------------------------------- placement
def run_placement(c, url):
    print("\n[placement]")
    go(c, url + f"&slide={SLIDE_INDEX}")
    check("slide 2 is the Right Price explainer",
          slide_id(c) == SLIDE_ID, f"id={slide_id(c)}")

    order = c.eval(
        "[...document.querySelectorAll('.atlas-slide')].filter(s => !s.hasAttribute('data-atlas-appendix'))"
        ".map(s => s.dataset.atlasSlideId)"
    )
    i = order.index(SLIDE_ID)
    check("it follows the cover", order[i - 1] == "cover", f"before={order[i - 1]}")
    check("the next slide is the supermarket metaphor",
          order[i + 1] == "advertising-supermarket", f"after={order[i + 1]}")
    check("no existing slide was dropped",
          len(order) == TOTAL_SLIDES and len(set(order)) == TOTAL_SLIDES,
          f"{len(order)} slides")

    labelled = c.eval("""(() => {
      const s = document.querySelector('.atlas-slide.is-active');
      return {ordinal: s.dataset.atlasSlide, label: s.getAttribute('aria-label')};
    })()""")
    check(f"it registers as slide {SLIDE_INDEX} of {TOTAL_SLIDES}",
          labelled["ordinal"] == str(SLIDE_INDEX)
          and labelled["label"] == f"Slide {SLIDE_INDEX} of {TOTAL_SLIDES}:"
                                   " A Rate Card tells us the right price"
                                   " for each deal",
          json.dumps(labelled))

    copy = c.eval("""(() => {
      const s = document.querySelector('.atlas-slide.is-active');
      const t = sel => s.querySelector(sel)?.textContent
        .replace(/\\s+/g, ' ').trim() || null;
      return {
        title: t('.rpx__title'),
        subtitle: t('.rpx__subtitle'),
        labels: [...s.querySelectorAll('.rpx__card-label')].map(n => n.textContent.trim()),
        questions: [...s.querySelectorAll('.rpx__question')].map(n => n.textContent.trim()),
        dashes: /[\\u2013\\u2014]/.test(s.textContent),
      };
    })()""")
    check("title matches the brief",
          copy["title"] == "A Rate Card tells us the right price for each deal.",
          copy["title"])
    check("subtitle matches the brief",
          copy["subtitle"] == "It connects the buyer, the deal, the product,"
                              " and anything that changes the price.",
          copy["subtitle"])
    check("card labels read as the formula",
          copy["labels"] == ["Buyer", "Deal", "Product", "Price Change", "Right Price"],
          json.dumps(copy["labels"]))
    check("each card keeps its own question",
          copy["questions"] == ["Who is buying?", "Which deal applies?",
                                "What are they buying?", "What changes the price?"],
          json.dumps(copy["questions"]))
    check("no em or en dashes", not copy["dashes"])


# ----------------------------------------------------------------- geometry
def run_geometry(c, url):
    print("\n[geometry vs Figma 736:248]")
    go(c, url + f"&slide={SLIDE_INDEX}")
    pin_native_scale(c)
    time.sleep(SEQUENCE_MS / 1000 + 0.6)

    stage = c.eval("""(() => {
      const r = document.querySelector('.atlas-stage').getBoundingClientRect();
      return {w: r.width, h: r.height};
    })()""")
    check("stage renders at the native 1920x1080",
          abs(stage["w"] - 1920) < 1 and abs(stage["h"] - 1080) < 1,
          json.dumps(stage))

    # offset* rather than client rects: the result card rests at
    # scale(0.96) until the presenter asks for it, and a client rect would
    # report the animation instead of the Figma layout.
    measured = json.loads(c.eval("""JSON.stringify((() => {
      const out = {};
      %s.forEach(sel => {
        const el = document.querySelector('.atlas-slide--right-price ' + sel);
        if (!el) { out[sel] = null; return; }
        out[sel] = [el.offsetLeft, el.offsetTop,
                    +el.offsetWidth.toFixed(1), +el.offsetHeight.toFixed(1)];
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
        check(f"{sel} sits at Figma coordinates",
              ok, f"want=({x},{y},{w},{h}) got={got}")

    cards = json.loads(c.eval("""JSON.stringify((() => {
      const s = document.querySelector('.atlas-slide--right-price');
      const card = s.querySelector('.rpx__group--buyer .rpx__card');
      const result = s.querySelector('.rpx__card--result');
      const cs = el => getComputedStyle(el);
      return {
        cardW: +card.offsetWidth.toFixed(1), cardH: +card.offsetHeight.toFixed(1),
        radius: cs(card).borderTopLeftRadius,
        borderW: parseFloat(cs(card).borderTopWidth),
        borderC: cs(card).borderTopColor,
        surface: cs(card).backgroundColor,
        resultBorderW: parseFloat(cs(result).borderTopWidth),
        resultBorderC: cs(result).borderTopColor,
        icon: +s.querySelector('.rpx__icon').offsetWidth.toFixed(1),
        label: cs(s.querySelector('.rpx__card-label')).fontSize,
        question: cs(s.querySelector('.rpx__question')).fontSize,
        title: cs(s.querySelector('.rpx__title')).fontSize,
        subtitle: cs(s.querySelector('.rpx__subtitle')).fontSize,
      };
    })())"""))
    check("cards are 230.4 x 192 with a 19.2px radius",
          abs(cards["cardW"] - 230.4) < 0.6 and abs(cards["cardH"] - 192) < 0.6
          and cards["radius"] == "19.2px", json.dumps(cards))
    # Chrome floors sub-pixel borders to whole device pixels, so Figma's
    # 1.2 and 1.5 both come back as 1. The colours still have to be exact.
    check("input cards use the Figma surface and border",
          cards["surface"] == "rgb(32, 39, 53)"
          and cards["borderC"] == "rgb(56, 66, 82)"
          and abs(cards["borderW"] - 1.2) <= 0.5,
          f'{cards["borderW"]} {cards["borderC"]}')
    check("the result card is the gold-bordered one",
          cards["resultBorderC"] == "rgb(189, 151, 94)"
          and abs(cards["resultBorderW"] - 1.5) <= 0.5,
          f'{cards["resultBorderW"]} {cards["resultBorderC"]}')
    check("icons render at 86.4px", abs(cards["icon"] - 86.4) < 0.6, cards["icon"])
    check("type scale matches Figma",
          cards["title"] == "56px" and cards["subtitle"] == "36px"
          and cards["label"] == "28.8px" and cards["question"] == "24px",
          json.dumps(cards))

    assets = c.eval("""(() => {
      const imgs = [...document.querySelectorAll('.atlas-slide--right-price img')];
      return imgs.filter(i => !i.complete || i.naturalWidth === 0)
                 .map(i => i.getAttribute('src'));
    })()""")
    check("every slide asset loaded", not assets, json.dumps(assets))
    check("no asset depends on a remote or expiring URL",
          not c.eval("""[...document.querySelectorAll(
            '.atlas-slide--right-price img')]
            .filter(i => /^https?:/.test(i.getAttribute('src')))
            .map(i => i.getAttribute('src'))"""))
    c.screenshot(f"{OUT}/geometry_1920.png")


# ------------------------------------------------------------------- reveal
def run_reveal(c, url, label):
    print(f"\n[reveal sequence @ {label}]")
    # The run starts on load, so the opening frames can only be caught by a
    # sampler installed before the document exists. It records how many
    # parts are showing, plus the layout box of every animated element, so
    # both the ordering and the absence of layout shift come from the same
    # timeline rather than from a lucky poll.
    c.send("Page.addScriptToEvaluateOnNewDocument", {"source": """
      window.__rpxSamples = [];
      const sample = () => {
        const parts = [...document.querySelectorAll('[data-rpx-reveal]')];
        if (!parts.length) return;
        const host = document.querySelector('[data-right-price]');
        const boxes = {};
        [...parts, document.querySelector('.rpx__group--result')]
          .forEach(n => {
            if (!n) return;
            boxes[n.dataset.rpxReveal || 'result'] =
              [n.offsetLeft, n.offsetTop, n.offsetWidth, n.offsetHeight];
          });
        window.__rpxSamples.push({
          t: Math.round(performance.now()),
          n: parts.filter(p => p.classList.contains('is-revealed')).length,
          phase: host ? host.getAttribute('data-rpx-phase') : null,
          boxes: boxes,
        });
      };
      const tick = setInterval(sample, 40);
      setTimeout(() => clearInterval(tick), 6000);
      document.addEventListener('DOMContentLoaded', sample);
    """})
    go(c, url + f"&slide={SLIDE_INDEX}")
    time.sleep(SEQUENCE_MS / 1000 + SETTLE_MS / 1000)

    samples = c.eval("JSON.stringify(window.__rpxSamples || [])")
    samples = json.loads(samples) if samples else []
    counts = [s["n"] for s in samples]
    check("the reveal was observed from the first frame",
          len(samples) > 10, f"{len(samples)} samples")
    check("the formula starts empty",
          bool(counts) and counts[0] == 0, f"first sample showed {counts[:3]}")
    check("terms and operators only ever arrive, never disappear",
          all(b >= a for a, b in zip(counts, counts[1:])), json.dumps(counts))
    check("all eight parts arrive one at a time",
          sorted(set(counts)) == list(range(0, 9)), json.dumps(sorted(set(counts))))
    check("the phase never skips ahead of the parts",
          all(s["phase"] == "revealing-inputs" for s in samples if s["n"] < 8),
          json.dumps([s["phase"] for s in samples[:6]]))

    # Every element must hold its final box from the moment it has one, so
    # nothing can reflow while the formula assembles. The baseline is the
    # first laid-out sample; earlier frames are the document before the
    # stylesheet has applied and report nothing at all.
    laid_out = [s for s in samples if any(b[2] for b in s["boxes"].values())]
    baseline = laid_out[0] if laid_out else None
    check("space is reserved before anything is revealed",
          baseline is not None and baseline["n"] == 0,
          f"first laid-out sample showed {baseline['n'] if baseline else None}")
    drifted = [s["t"] for s in laid_out if s["boxes"] != baseline["boxes"]]
    check("no element moved while the formula assembled",
          not drifted,
          f"baseline={baseline['boxes'] if baseline else None}"
          f" drifted at {drifted[:3]}")

    header = c.eval(
        "getComputedStyle(document.querySelector('.rpx__header')).opacity"
    )
    check("title and subtitle are visible from the first frame",
          header == "1", header)

    check("every term and operator is showing once the run ends",
          revealed(c) == REVEAL_ORDER, json.dumps(revealed(c)))
    check("the run parks in waiting-for-result",
          phase(c) == "waiting-for-result", phase(c))
    check("the result is still hidden after the automatic run",
          result_opacity(c) == 0.0)
    c.screenshot(f"{OUT}/{label}_waiting.png")

    # The reveal click must not also move the deck.
    c.click_stage()
    time.sleep(SETTLE_MS / 1000)
    check("a click reveals the result", phase(c) == "result-visible", phase(c))
    check("the result is fully visible", result_opacity(c) == 1.0)
    check("the reveal click did not advance the deck",
          slide_id(c) == SLIDE_ID, f"id={slide_id(c)}")
    check("the result is announced to assistive tech",
          c.eval("document.querySelector('[data-rpx-live]').textContent")
          == "Right Price revealed.")
    check("the result leaves the a11y tree only while hidden",
          c.eval("document.querySelector('[data-rpx-result]')"
                 ".getAttribute('aria-hidden')") == "false")
    c.screenshot(f"{OUT}/{label}_result.png")

    # Past the guard window, the deck takes the gesture back.
    time.sleep(0.5)
    c.click_stage()
    time.sleep(0.4)
    check("the next click advances to slide 3",
          slide_id(c) == "advertising-supermarket", f"id={slide_id(c)}")


def run_interaction(c, url):
    print("\n[interaction ownership]")

    # A click mid-sequence buys the rest of the formula, not the answer.
    #
    # Re-entry and the click are driven from inside the page: the run is
    # only 1580ms long, so a CDP round trip between navigating and
    # clicking is enough to miss it and test nothing.
    go(c, url + f"&slide={SLIDE_INDEX}")
    early = json.loads(c.eval("""(async () => {
      const wait = ms => new Promise(r => setTimeout(r, ms));
      const host = () => document.querySelector('[data-right-price]');
      const shown = () => [...document.querySelectorAll(
        '[data-rpx-reveal].is-revealed')].length;
      const active = () => document.querySelector(
        '.atlas-slide.is-active').dataset.atlasSlideId;
      const key = k => document.dispatchEvent(
        new KeyboardEvent('keydown', {key: k, bubbles: true}));
      key('ArrowLeft');
      await wait(400);
      key('ArrowRight');
      await wait(500);
      const before = {phase: host().dataset.rpxPhase, shown: shown()};
      document.querySelector('.atlas-stage-wrap').click();
      await wait(120);
      return JSON.stringify({
        before: before,
        phase: host().dataset.rpxPhase,
        shown: shown(),
        resultOpacity: getComputedStyle(
          document.querySelector('.rpx__group--result')).opacity,
        active: active(),
      });
    })()""", await_promise=True))
    check("the click really did land mid-sequence",
          early["before"]["phase"] == "revealing-inputs"
          and 0 < early["before"]["shown"] < len(REVEAL_ORDER),
          json.dumps(early["before"]))
    check("an early click finishes the formula at once",
          early["shown"] == len(REVEAL_ORDER), early["shown"])
    check("an early click stops at waiting-for-result",
          early["phase"] == "waiting-for-result", early["phase"])
    check("an early click does not reveal the result",
          float(early["resultOpacity"]) == 0.0, early["resultOpacity"])
    check("an early click does not advance the deck",
          early["active"] == SLIDE_ID, early["active"])

    # Space and Enter match click for the internal reveal.
    for key, code, num in ((" ", "Space", 32), ("Enter", "Enter", 13)):
        go(c, url + f"&slide={SLIDE_INDEX}")
        time.sleep(SEQUENCE_MS / 1000 + 0.4)
        c.key(key, code, num)
        time.sleep(SETTLE_MS / 1000)
        check(f"{code} reveals the result", phase(c) == "result-visible", phase(c))
        check(f"{code} keeps the presenter on the slide",
              slide_id(c) == SLIDE_ID, f"id={slide_id(c)}")

    # A double click must not skip past the slide.
    go(c, url + f"&slide={SLIDE_INDEX}")
    time.sleep(SEQUENCE_MS / 1000 + 0.4)
    c.click_stage()
    c.click_stage()
    time.sleep(0.3)
    check("a double click reveals without advancing",
          phase(c) == "result-visible" and slide_id(c) == SLIDE_ID,
          f"phase={phase(c)} id={slide_id(c)}")

    # A held key must not skip past the slide either.
    go(c, url + f"&slide={SLIDE_INDEX}")
    time.sleep(SEQUENCE_MS / 1000 + 0.4)
    for _ in range(6):
        c.key(" ", "Space", 32)
    time.sleep(0.3)
    check("key repeat reveals without advancing",
          phase(c) == "result-visible" and slide_id(c) == SLIDE_ID,
          f"phase={phase(c)} id={slide_id(c)}")

    # ArrowRight is always deck navigation, at any phase.
    go(c, url + f"&slide={SLIDE_INDEX}")
    time.sleep(0.3)
    c.key("ArrowRight", "ArrowRight", 39)
    time.sleep(0.35)
    check("ArrowRight leaves the slide even mid-sequence",
          slide_id(c) == "advertising-supermarket", f"id={slide_id(c)}")


def run_reset(c, url):
    print("\n[reset and replay]")
    go(c, url + f"&slide={SLIDE_INDEX}")
    time.sleep(SEQUENCE_MS / 1000 + 0.4)
    c.click_stage()
    time.sleep(SETTLE_MS / 1000)
    check("primed with the result showing", phase(c) == "result-visible", phase(c))

    # Forward off the slide, then back onto it.
    c.key("ArrowRight", "ArrowRight", 39)
    time.sleep(0.4)
    check("left the slide", slide_id(c) == "advertising-supermarket", f"id={slide_id(c)}")
    check("leaving cleared the run",
          phase(c) == "revealing-inputs" and result_opacity(c) == 0.0
          and revealed(c) == [], f"phase={phase(c)} revealed={revealed(c)}")

    c.key("ArrowLeft", "ArrowLeft", 37)
    time.sleep(0.15)
    check("re-entering starts from an empty formula",
          len(revealed(c)) < len(REVEAL_ORDER), json.dumps(revealed(c)))
    time.sleep(SEQUENCE_MS / 1000 + SETTLE_MS / 1000)
    check("re-entering replays the whole sequence",
          revealed(c) == REVEAL_ORDER and phase(c) == "waiting-for-result",
          f"phase={phase(c)} revealed={len(revealed(c))}")
    check("the result stays hidden on the replay", result_opacity(c) == 0.0)

    # Backward navigation off the slide resets it too.
    c.key("ArrowLeft", "ArrowLeft", 37)
    time.sleep(0.4)
    check("back navigation lands on the cover",
          slide_id(c) == "cover", f"id={slide_id(c)}")
    check("back navigation cleared the run",
          phase(c) == "revealing-inputs" and revealed(c) == [],
          f"phase={phase(c)} revealed={revealed(c)}")

    # A pending step must never paint onto whatever slide is up next.
    go(c, url + f"&slide={SLIDE_INDEX}")
    time.sleep(0.2)
    c.key("ArrowRight", "ArrowRight", 39)
    time.sleep(SEQUENCE_MS / 1000 + SETTLE_MS / 1000)
    check("a pending step cannot fire onto the next slide",
          revealed(c) == [] and phase(c) == "revealing-inputs",
          f"phase={phase(c)} revealed={revealed(c)}")

    # Repeated entries must not stack duplicate work.
    for _ in range(3):
        c.key("ArrowLeft", "ArrowLeft", 37)
        time.sleep(0.25)
        c.key("ArrowRight", "ArrowRight", 39)
        time.sleep(0.25)
    c.key("ArrowLeft", "ArrowLeft", 37)
    time.sleep(SEQUENCE_MS / 1000 + SETTLE_MS / 1000)
    check("repeated entry and exit still ends in one clean run",
          revealed(c) == REVEAL_ORDER and phase(c) == "waiting-for-result",
          f"phase={phase(c)} revealed={json.dumps(revealed(c))}")


def run_corners(c, url, label, viewport):
    print(f"\n[rounded corners @ {label}]")
    go(c, url + f"&slide={SLIDE_INDEX}")
    time.sleep(SEQUENCE_MS / 1000 + 0.4)

    frame = c.eval("""(() => {
      const stage = document.querySelector('.atlas-stage');
      const wrap = document.querySelector('.atlas-stage-wrap');
      const deck = document.querySelector('.atlas-deck');
      const cs = el => getComputedStyle(el);
      const sr = stage.getBoundingClientRect();
      const wr = wrap.getBoundingClientRect();
      return {
        radius: cs(stage).borderTopLeftRadius,
        overflow: cs(stage).overflow,
        canvas: cs(deck).backgroundColor,
        slideBg: cs(document.querySelector('.atlas-slide--right-price'))
          .backgroundColor,
        padTop: sr.top - wr.top,
        padLeft: sr.left - wr.left,
        padRight: wr.right - sr.right,
        padBottom: wr.bottom - sr.bottom,
        insideStage: [...document.querySelectorAll(
          '.atlas-slide--right-price .rpx > *')]
          .filter(n => {
            const r = n.getBoundingClientRect();
            if (!r.width && !r.height) return false;
            return r.left < sr.left - 0.5 || r.right > sr.right + 0.5
                || r.top < sr.top - 0.5 || r.bottom > sr.bottom + 0.5;
          })
          .map(n => n.className),
      };
    })()""")
    check("the slide viewport carries the 40px radius",
          frame["radius"] == f"{STAGE_RADIUS}px", frame["radius"])
    check("the slide viewport clips its contents",
          frame["overflow"] == "hidden", frame["overflow"])
    check("the canvas is darker than the slide, so corners read",
          frame["canvas"] == CANVAS and frame["slideBg"] == SLIDE_BG,
          f"canvas={frame['canvas']} slide={frame['slideBg']}")
    check("the slide is not flush to the browser edges",
          min(frame["padTop"], frame["padLeft"],
              frame["padRight"], frame["padBottom"]) >= 24,
          json.dumps({k: round(frame[k], 1) for k in
                      ("padTop", "padLeft", "padRight", "padBottom")}))
    check("nothing paints outside the rounded frame",
          not frame["insideStage"], json.dumps(frame["insideStage"]))

    # Sample the actual pixels: a corner must be canvas, its inset slide.
    # The corner probes ask whether the slide's radius lets the canvas show
    # through. The feedback launcher is a floating app control that sits in
    # the lower-left corner by design, so it has to be out of the frame for
    # that question to be about the frame. It is put back straight after.
    c.eval("""(() => { const b = document.querySelector('.rcf-launch');
      if (b) b.style.visibility = 'hidden'; })()""")
    c.screenshot(f"{OUT}/{label}_corners.png")
    c.eval("""(() => { const b = document.querySelector('.rcf-launch');
      if (b) b.style.visibility = ''; })()""")
    corners = c.eval("""(() => {
      const r = document.querySelector('.atlas-stage').getBoundingClientRect();
      return {l: r.left, t: r.top, w: r.width, h: r.height};
    })()""")
    from PIL import Image
    im = Image.open(f"{OUT}/{label}_corners.png").convert("RGB")
    slide_rgb = tuple(int(v) for v in SLIDE_BG[4:-1].split(","))
    x0, y0 = int(corners["l"]), int(corners["t"])
    x1, y1 = int(corners["l"] + corners["w"]) - 1, int(corners["t"] + corners["h"]) - 1
    probes = {
        "top-left": ((x0 + 3, y0 + 3), (x0 + 60, y0 + 60)),
        "top-right": ((x1 - 3, y0 + 3), (x1 - 60, y0 + 60)),
        "bottom-left": ((x0 + 3, y1 - 3), (x0 + 60, y1 - 60)),
        "bottom-right": ((x1 - 3, y1 - 3), (x1 - 60, y1 - 60)),
    }
    for name, (outside, inside) in probes.items():
        got_out = im.getpixel(outside)
        got_in = im.getpixel(inside)
        check(f"{name} corner is rounded away to the canvas",
              is_canvas(got_out) and got_in == slide_rgb,
              f"corner={got_out} inset={got_in}")

    formula = c.eval("""(() => {
      const s = document.querySelector('.atlas-slide--right-price');
      const tops = [...s.querySelectorAll('.rpx__group')].map(n => n.offsetTop);
      return {sameRow: new Set(tops).size === 1, tops};
    })()""")
    check("the formula stays on one line", formula["sameRow"],
          json.dumps(formula["tops"]))

    aligned = c.eval("""(() => {
      const s = document.querySelector('.atlas-slide--right-price');
      return [...s.querySelectorAll('.rpx__group:not(.rpx__group--result)')]
        .filter(g => {
          const card = g.querySelector('.rpx__card').getBoundingClientRect();
          const q = g.querySelector('.rpx__question').getBoundingClientRect();
          return q.top < card.bottom || Math.abs(q.left - g.getBoundingClientRect().left) > 1;
        }).length;
    })()""")
    check("each question sits directly under its own card", aligned == 0, aligned)


def run_reduced_motion(url, port_http):
    print("\n[reduced motion]")
    proc, port = boot_chrome((1440, 900), reduced=True, port_http=port_http)
    try:
        c = CDP(port)
        go(c, url + f"&slide={SLIDE_INDEX}")
        check("reduced motion is in effect",
              c.eval("matchMedia('(prefers-reduced-motion: reduce)').matches"))
        motion = c.eval("""(() => {
          const g = document.querySelector('.rpx__group--buyer');
          const r = document.querySelector('.rpx__group--result');
          const cs = el => getComputedStyle(el);
          return {
            groupTransform: cs(g).transform,
            groupTransition: cs(g).transitionDuration,
            resultTransform: cs(r).transform,
            resultAnimation: cs(
              document.querySelector('.rpx__card--result')).animationName,
          };
        })()""")
        check("terms do not travel under reduced motion",
              motion["groupTransform"] == "none", motion["groupTransform"])
        check("fades are short under reduced motion",
              motion["groupTransition"] == "0.12s", motion["groupTransition"])
        check("the result does not scale under reduced motion",
              motion["resultTransform"] == "none", motion["resultTransform"])

        time.sleep(SEQUENCE_MS / 1000 + 0.6)
        check("the staged sequence still runs in order",
              revealed(c) == REVEAL_ORDER and phase(c) == "waiting-for-result",
              f"phase={phase(c)} revealed={len(revealed(c))}")
        check("the result still waits for the presenter",
              result_opacity(c) == 0.0)
        c.click_stage()
        time.sleep(0.4)
        check("the manual reveal still works under reduced motion",
              phase(c) == "result-visible" and result_opacity(c) == 1.0,
              phase(c))
        check("the gold emphasis is dropped under reduced motion",
              c.eval("getComputedStyle(document.querySelector("
                     "'.rpx__card--result')).animationName") == "none")
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
        proc, port = boot_chrome((1920, 1080), port_http=port_http)
        try:
            c = CDP(port)
            run_placement(c, url)
            run_geometry(c, url)
            run_reveal(c, url, "1920x1080")
            run_interaction(c, url)
            run_reset(c, url)
            run_corners(c, url, "1920x1080", (1920, 1080))
            print("\n[console]")
            check("no console errors or warnings", not c.logs, json.dumps(c.logs))
        finally:
            proc.kill()

        for label, viewport in (("1440x900", (1440, 900)), ("1280x720", (1280, 720))):
            proc, port = boot_chrome(viewport, port_http=port_http)
            try:
                c = CDP(port)
                run_reveal(c, url, label)
                run_corners(c, url, label, viewport)
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
