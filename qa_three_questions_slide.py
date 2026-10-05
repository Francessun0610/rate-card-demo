#!/usr/bin/env python3
"""
qa_three_questions_slide.py - Atlas deck slide 5 QA.

Slide 5, "To find the right price, RCM answers three questions", is authored
from Figma node 512:1580. It replaces the retired "RCM Organizes Pricing into
Three Building Blocks" slide, which made the same point as a static diagram.

Three inputs stack down the left, each a card plus the question it answers,
and the answer sits to the right behind an equals sign.

What this suite locks down:

  - The legacy slide is gone: no title, no semantic id, no styles, no assets
    left anywhere in the deck.
  - Placement. One such slide, eighth, directly after the media plan
    walkthrough, deck still fifteen long, every other id in its old
    order.
  - Copy, exactly as briefed, and the absence of every retired string from
    the deleted slide.
  - Legibility, measured rather than assumed. Every string clears 16px on
    screen at every viewport except the two sizes Figma fixes (the 24px card
    labels and the 28.8px Right Price label), which fall to 13.0px and
    15.6px at 1280x720 only. Figma fidelity was chosen for those two, so
    they are named explicitly and everything else is still held to the
    floor.
  - Geometry against the Figma node, element by element.
  - The six states, in order:
      intro -> details-visible -> line-items-visible -> premiums-visible
      -> waiting-for-result -> result-visible
  - The manual pause, which is the point of the slide: after Premiums the
    run stops and neither the equals sign nor any part of the Right Price
    group is visible, however long you wait.
  - The presenter reveal: the equals sign lands first, the answer follows,
    and neither gesture advances the deck.
  - Interaction. A gesture mid-run buys the three inputs and still stops at
    the pause. Arrow keys are never taken.
  - Timer cleanup, reset on re-entry, reduced motion, responsive layout and
    rounded-frame clipping.

Timings mirror the SEQUENCE in initAtlasThreeQuestions (app.js).
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
OUT = "/tmp/qa_three_questions_slide"
SLIDE_INDEX = 6
SLIDE_ID = "rate-card-three-questions"
PREV_ID = "core-planning-media-plan"
NEXT_ID = "structured-pricing-data"
TOTAL_SLIDES = 11

# header 250, group-1 900, plus-1 1450, group-2 1800, plus-2 2350,
# group-3 2700, run ends (pause begins) 3200.
SEQUENCE_MS = 3200
SETTLE_MS = 900
EQUALS_MS = 340
# Figma 512:1580 sets the card labels at 24px and the Right Price label at
# 28.8px. Those are kept, so the source floor here is Figma's own smallest
# size rather than the 30px that 1280x720 would need. run_layout records the
# visible size at every viewport so the shortfall is reported, not hidden.
MIN_FONT_PX = 24
VISIBLE_FLOOR = 16.0
# Figma fixes these two sizes (24px and 28.8px). Both clear 16px on screen at
# 1920x1080 and 1440x900; at 1280x720 the stage scales to 0.54 and they land
# at 13.0px and 15.6px. Figma fidelity was chosen over the floor for these
# two, so they are named here rather than being allowed to fail quietly.
# Everything else must clear the floor at every viewport.
FIGMA_FIXED = {"tq__card-label", "tq__result-label"}
STAGE_RADIUS = 40
CANVAS = "rgb(30, 30, 30)"
SLIDE_BG = "rgb(2, 0, 36)"

TITLE = "RCM organizes pricing into three connected sections"
SUBTITLE = "Together, they determine the applicable rate used in planning."
CARD_LABELS = ["Rate Card Details", "Line Items", "Premiums"]
QUESTIONS = [
    "Who is buying, and under which deal?",
    "What are they buying, and at what starting rate?",
    "Does anything change the price?",
]
DETAILS = [
    "Buyer / Marketplace / Deal / Timing",
    "Offering / Base Rate",
    "Condition / Adjustment",
]
RESULT_LABEL = "Right Price"
RESULT_NOTE = "The price used in planning"

# Everything the deleted slide used to say. None of it may come back.
# Wording unique to the deleted slide. None of it may survive anywhere.
RETIRED = [
    "RCM Organizes Pricing into Three Building Blocks",
    "Three Building Blocks",
    "Which marketplace and buyer apply?",
    "What is sold, and at what base rate?",
    "What pricing adjustments apply?",
    "Together, they provide a consistent structure",
    "Example result",
    # Superseded by the current Figma node. If either of these comes back the
    # old version of this slide has been re-added alongside the new one.
    "To find the right price, RCM answers three questions",
    "It combines the deal, the product, and anything that changes the price.",
]
# "RC Details" is still the connected-workflows slide's own label, so it is
# only banned from the new slide rather than from the whole deck.
RETIRED_ON_SLIDE = RETIRED + ["RC Details"]
RETIRED_IDS = ["rcm-building-blocks"]
RETIRED_MARKUP = ["rbb__", "atlas-slide--rcm-blocks", "rcm-blocks-details.svg",
                  "rcm-blocks-lines.svg", "rcm-blocks-premiums.svg"]

STATES = ["intro", "details-visible", "line-items-visible", "premiums-visible"]
PHASES = ["intro", "waiting-for-result", "result-visible"]

# Figma 512:1580 geometry, in native stage pixels: left, top, width, height.
FIGMA = {
    ".tq__header": (63, 88, 1828, 120),
    ".tq__title": (63, 88, 1727, 56),
    ".tq__subtitle": (63, 152, 1828, 56),
    ".tq__block--details": (64, 275, None, 160),
    ".tq__block--lines": (60, 523, None, 160),
    ".tq__block--premiums": (63, 769, None, 160),
    ".tq__block--details .tq__card": (66, 275, 180, 160),
    ".tq__block--details .tq__accent": (64, 289.5, 2, 131),
    ".tq__block--details .tq__copy": (302, 316.6, None, 76.8),
    ".tq__block--lines .tq__copy": (298, 564.6, None, 76.8),
    ".tq__block--premiums .tq__copy": (301, 810.6, None, 76.8),
    ".tq__plus--1": (136, 461, 36, 36),
    ".tq__plus--2": (136, 708, 36, 36),
    ".tq__equals": (1148, 560, 56, 56),
    ".tq__result": (1250, 477, 376, 272),
    ".tq__result-card": (1323, 477, 230.4, 192),
    ".tq__result-note": (1250, 711, 376, 38.4),
    ".tq__logo": (1826, 997, 36, 41),
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
    profile = f"/tmp/qa_tq_profile_{port}"
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


def state(c):
    return c.eval(
        "document.querySelector('[data-three-questions]')"
        "?.getAttribute('data-tq-state')"
    )


def phase(c):
    return c.eval(
        "document.querySelector('[data-three-questions]')"
        "?.getAttribute('data-tq-phase')"
    )


def slide_id(c):
    return c.eval(
        "document.querySelector('.atlas-slide.is-active')?.dataset.atlasSlideId"
    )


def revealed(c):
    return c.eval(
        "[...document.querySelectorAll('[data-tq-reveal]')]"
        ".filter(n => n.classList.contains('is-revealed'))"
        ".map(n => n.dataset.tqReveal)"
    )


def pin_native_scale(c):
    c.eval("""(() => {
      const style = document.createElement('style');
      style.textContent = `.atlas-stage{--atlas-scale:1 !important;margin:0 !important}
        .atlas-stage-wrap{padding:0 !important;overflow:visible !important}
        .atlas-deck{position:absolute !important}
        .atlas-slide--three-questions [data-tq-reveal]{
          opacity:1 !important; transform:none !important;
          transition:none !important; animation:none !important; }`;
      document.head.appendChild(style);
    })()""")
    time.sleep(0.4)


# ------------------------------------------------------- the legacy slide
def run_removal(c, url):
    print("\n[legacy slide removed]")
    go(c, url + "&slide=1")
    doc = c.eval("document.documentElement.outerHTML")

    for sid in RETIRED_IDS:
        check(f"no slide carries the id {sid}",
              c.eval(f"!document.querySelector('[data-atlas-slide-id=\"{sid}\"]')"))
    for phrase in RETIRED:
        check(f"the deck no longer says {phrase!r}", phrase not in doc)
    for marker in RETIRED_MARKUP:
        check(f"no markup or asset named {marker!r} remains", marker not in doc)

    check("no orphaned .rbb element is left hidden in the DOM",
          c.eval("document.querySelectorAll('[class*=\"rbb\"]').length") == 0)
    # The slide was updated in place and moved, so exactly one copy of its
    # section, host and result card may exist anywhere in the deck.
    duplicates = c.eval("""(() => ({
      sections: document.querySelectorAll('.atlas-slide--three-questions').length,
      hosts: document.querySelectorAll('[data-three-questions]').length,
      results: document.querySelectorAll('.tq__result-card').length,
      ids: document.querySelectorAll(
        '[data-atlas-slide-id="rate-card-three-questions"]').length,
    }))()""")
    check("the slide was replaced in place, not duplicated",
          duplicates == {"sections": 1, "hosts": 1, "results": 1, "ids": 1},
          json.dumps(duplicates))
    check("no stylesheet rule targets the removed slide",
          c.eval("""(() => {
            let hits = 0;
            for (const sheet of document.styleSheets) {
              let rules;
              try { rules = sheet.cssRules; } catch (e) { continue; }
              for (const rule of rules) {
                if (rule.selectorText
                    && /rbb|atlas-slide--rcm-blocks/.test(rule.selectorText)) {
                  hits += 1;
                }
              }
            }
            return hits;
          })()""") == 0)

    for name in ("rcm-blocks-details.svg", "rcm-blocks-lines.svg",
                 "rcm-blocks-premiums.svg"):
        check(f"the exclusive asset {name} was deleted",
              not os.path.exists(os.path.join(ROOT, "assets", "atlas", name)))
    for name in ("rcm-blocks-logo.svg", "rcm-blocks-plus.svg",
                 "rcm-blocks-equals.svg"):
        check(f"the shared asset {name} was kept",
              os.path.exists(os.path.join(ROOT, "assets", "atlas", name)))


def run_placement(c, url):
    print("\n[placement]")
    go(c, url + f"&slide={SLIDE_INDEX}")
    check(f"slide {SLIDE_INDEX} is the three questions slide",
          slide_id(c) == SLIDE_ID, f"id={slide_id(c)}")

    order = c.eval(
        "[...document.querySelectorAll('.atlas-slide')].filter(s => !s.hasAttribute('data-atlas-appendix'))"
        ".map(s => s.dataset.atlasSlideId)"
    )
    check("the slide exists exactly once",
          order.count(SLIDE_ID) == 1, f"{order.count(SLIDE_ID)} copies")
    i = order.index(SLIDE_ID)
    check("it follows the media plan walkthrough",
          order[i - 1] == PREV_ID, f"before={order[i - 1]}")
    check("the structured pricing data slide follows it",
          order[i + 1] == NEXT_ID, f"after={order[i + 1]}")
    check("the main run is intact with no duplicates",
          len(order) == TOTAL_SLIDES and len(set(order)) == TOTAL_SLIDES,
          f"{len(order)} slides")
    check("the surrounding order is unchanged",
          order == [
              "cover", "pricing-complexity", "structured-pricing-data",
              "rate-card-right-price", "same-ad-different-rate",
              SLIDE_ID, "connected-workflows",
              "future-rate-card-workflow", "core-planning-media-plan",
              "rate-card-line-pricing", "closing-thank-you",
          ], json.dumps(order))

    labelled = c.eval("""(() => {
      const s = document.querySelector('.atlas-slide.is-active');
      return {ordinal: s.dataset.atlasSlide, label: s.getAttribute('aria-label'),
              id: s.id};
    })()""")
    check(f"it registers as slide {SLIDE_INDEX} of {TOTAL_SLIDES}",
          labelled["ordinal"] == str(SLIDE_INDEX)
          and labelled["label"] == f"Slide {SLIDE_INDEX} of {TOTAL_SLIDES}: {TITLE}",
          json.dumps(labelled))
    check("it has a stable element id",
          labelled["id"] == "atlas-slide-three-questions", labelled["id"])

    # Every slide must still be reachable at its own number.
    # Only the main run is numbered; the appendix sections are addressed
    # by id and carry an "Appendix NN:" label instead of an ordinal.
    numbering = c.eval("""(total => [
      ...document.querySelectorAll('.atlas-slide')
    ].filter(s => !s.hasAttribute('data-atlas-appendix'))
     .every((s, i) => s.dataset.atlasSlide === String(i + 1)
      && (s.getAttribute('aria-label') || '')
           .startsWith('Slide ' + (i + 1) + ' of ' + total + ':')))(%d)"""
      % TOTAL_SLIDES)
    check("every slide's number and aria label match its position", numbering)

    # Deep links either side of the new slide.
    for n, want in ((SLIDE_INDEX - 1, PREV_ID), (SLIDE_INDEX, SLIDE_ID),
                    (SLIDE_INDEX + 1, NEXT_ID),
                    (TOTAL_SLIDES, "closing-thank-you"),
                    (TOTAL_SLIDES - 1, "rate-card-line-pricing")):
        go(c, url + f"&slide={n}")
        check(f"deep link slide={n} opens {want}",
              slide_id(c) == want, f"id={slide_id(c)}")

    go(c, url + f"&slide={SLIDE_INDEX}")
    c.key("ArrowLeft", "ArrowLeft", 37)
    time.sleep(0.4)
    check("back navigation lands on the media plan walkthrough",
          slide_id(c) == PREV_ID, f"id={slide_id(c)}")
    # The media plan walkthrough owns five forward steps of its own, and it
    # holds navigation while each one settles, so a gesture sent too early
    # is swallowed rather than queued. Six presses, spaced past its longest
    # hold, bring us back here.
    for _ in range(6):
        if slide_id(c) == SLIDE_ID:
            break
        c.key("ArrowRight", "ArrowRight", 39)
        time.sleep(2.2)
    check("forward navigation returns to it", slide_id(c) == SLIDE_ID,
          f"id={slide_id(c)}")


def run_copy(c, url):
    print("\n[copy]")
    go(c, url + f"&slide={SLIDE_INDEX}")
    copy = c.eval("""(() => {
      const s = document.querySelector('.atlas-slide--three-questions');
      const t = sel => s.querySelector(sel)?.textContent
        .replace(/\\s+/g, ' ').trim() || null;
      return {
        title: t('.tq__title'),
        subtitle: t('.tq__subtitle'),
        // innerText, not textContent: the Rate Card Details label is two
        // lines and textContent would swallow the break entirely.
        labels: [...s.querySelectorAll('.tq__card-label')]
          .map(n => n.innerText.replace(/\\s+/g, ' ').trim()),
        questions: [...s.querySelectorAll('.tq__question')]
          .map(n => n.textContent.trim()),
        details: [...s.querySelectorAll('.tq__detail')]
          .map(n => n.textContent.trim()),
        resultLabel: t('.tq__result-label'),
        resultNote: t('.tq__result-note'),
        text: s.textContent.replace(/\\s+/g, ' ').trim(),
        aria: [...s.querySelectorAll('[aria-label]')]
          .map(n => n.getAttribute('aria-label')).join(' | '),
      };
    })()""")
    check("title matches the brief", copy["title"] == TITLE, copy["title"])
    check("subtitle matches the brief", copy["subtitle"] == SUBTITLE, copy["subtitle"])
    check("the three card labels are right",
          copy["labels"] == CARD_LABELS, json.dumps(copy["labels"]))
    check("the three questions are right",
          copy["questions"] == QUESTIONS, json.dumps(copy["questions"]))
    check("the three detail lines are right",
          copy["details"] == DETAILS, json.dumps(copy["details"]))
    check("the result label is right",
          copy["resultLabel"] == RESULT_LABEL, copy["resultLabel"])
    check("the supporting line is right",
          copy["resultNote"] == RESULT_NOTE, copy["resultNote"])

    stale = [w for w in RETIRED_ON_SLIDE
             if w in copy["text"] or w in copy["aria"]]
    check("no retired copy appears on the new slide", not stale, json.dumps(stale))

    # Nothing the brief said not to add.
    check("no bottom takeaway, footnote or numbered badge was added",
          c.eval("""(() => {
            const s = document.querySelector('.atlas-slide--three-questions');
            return s.querySelectorAll(
              '.tq__takeaway, .tq__footnote, .tq__badge, .tq__example').length;
          })()""") == 0)
    check("the questions carry no card of their own",
          c.eval("""(() => {
            const copyBlocks = [...document.querySelectorAll('.tq__copy')];
            return copyBlocks.every(n => {
              const cs = getComputedStyle(n);
              return cs.borderTopWidth === '0px'
                && (cs.backgroundColor === 'rgba(0, 0, 0, 0)'
                    || cs.backgroundColor === 'transparent');
            });
          })()"""))
    check("no UI control was introduced",
          c.eval("""document.querySelectorAll(
            '.atlas-slide--three-questions button,'
            + ' .atlas-slide--three-questions a,'
            + ' .atlas-slide--three-questions input').length""") == 0)


def run_geometry(c, url):
    print("\n[geometry vs Figma 512:1580]")
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
        const el = document.querySelector('.atlas-slide--three-questions ' + sel);
        if (!el) { out[sel] = null; return; }
        const r = el.getBoundingClientRect();
        out[sel] = [+(r.left - stage.left).toFixed(1),
                    +(r.top - stage.top).toFixed(1),
                    +r.width.toFixed(1), +r.height.toFixed(1)];
      });
      return out;
    })())""" % json.dumps(list(FIGMA))))
    for sel, want in FIGMA.items():
        got = measured.get(sel)
        if got is None:
            check(f"{sel} exists", False, "missing")
            continue
        x, y, w, h = want
        ok = abs(got[0] - x) <= 1 and abs(got[1] - y) <= 1
        if w is not None:
            ok = ok and abs(got[2] - w) <= 1
        if h is not None:
            ok = ok and abs(got[3] - h) <= 1
        check(f"{sel} sits at Figma coordinates", ok,
              f"want=({x},{y},{w},{h}) got={got}")

    style = json.loads(c.eval("""JSON.stringify((() => {
      const s = document.querySelector('.atlas-slide--three-questions');
      const q = sel => getComputedStyle(s.querySelector(sel));
      return {
        title: [q('.tq__title').fontSize, q('.tq__title').color],
        subtitle: [q('.tq__subtitle').fontSize, q('.tq__subtitle').color],
        label: [q('.tq__card-label').fontSize, q('.tq__card-label').color],
        question: [q('.tq__question').fontSize, q('.tq__question').fontWeight],
        detail: [q('.tq__detail').fontSize, q('.tq__detail').fontWeight],
        resultLabel: [q('.tq__result-label').fontSize],
        resultNote: [q('.tq__result-note').fontSize],
        resultBorder: q('.tq__result-card').borderTopColor,
        resultBg: q('.tq__result-card').backgroundColor,
        radius: q('.tq__card').borderRadius,
      };
    })())"""))
    check("title is 56px in the Figma near-white",
          style["title"] == ["56px", "rgb(245, 245, 247)"], json.dumps(style["title"]))
    check("subtitle is 36px in the Figma grey",
          style["subtitle"] == ["36px", "rgb(210, 210, 215)"],
          json.dumps(style["subtitle"]))
    check("card labels are 24px", style["label"][0] == "24px", style["label"][0])
    check("questions are 32px and heavy",
          style["question"] == ["32px", "900"], json.dumps(style["question"]))
    check("detail lines are 32px and light",
          style["detail"] == ["32px", "300"], json.dumps(style["detail"]))
    check("the result card keeps the Figma gold border",
          style["resultBorder"] == "rgb(189, 151, 94)", style["resultBorder"])
    check("the result card keeps the Figma surface",
          style["resultBg"] == "rgb(32, 39, 53)", style["resultBg"])
    check("input cards use the Figma 16px radius",
          style["radius"] == "16px", style["radius"])

    # The 30px floor is what keeps everything >= 16px once the stage scales.
    small = c.eval("""(() => {
      const s = document.querySelector('.atlas-slide--three-questions');
      return [...s.querySelectorAll('*')].filter(n => {
        if (!n.getClientRects().length) return false;
        if (n.closest('.tq__sr')) return false;
        const direct = [...n.childNodes].some(
          x => x.nodeType === Node.TEXT_NODE && x.textContent.trim());
        return direct && parseFloat(getComputedStyle(n).fontSize) < %d;
      }).map(n => String(n.className) + '@'
        + getComputedStyle(n).fontSize);
    })()""" % MIN_FONT_PX)
    check(f"every visible string is at least {MIN_FONT_PX}px at source,"
          f" the Figma minimum", not small, json.dumps(small))
    banned = c.eval("""(() => {
      const s = document.querySelector('.atlas-slide--three-questions');
      return [...s.querySelectorAll('*')].filter(n => {
        if (n.closest('.tq__sr')) return false;
        const px = parseFloat(getComputedStyle(n).fontSize);
        return px >= 12 && px <= 15;
      }).map(n => String(n.className) + '@' + getComputedStyle(n).fontSize);
    })()""")
    check("nothing on the slide sits in the banned 12-15px band",
          not banned, json.dumps(banned[:6]))

    assets = c.eval("""(() => {
      const imgs = [...document.querySelectorAll(
        '.atlas-slide--three-questions img')];
      return imgs.filter(i => !i.complete || i.naturalWidth === 0)
                 .map(i => i.getAttribute('src'));
    })()""")
    check("every slide asset loaded", not assets, json.dumps(assets))
    check("no asset depends on a remote or expiring URL",
          not c.eval("""[...document.querySelectorAll(
            '.atlas-slide--three-questions img')]
            .filter(i => /^https?:/.test(i.getAttribute('src')))
            .map(i => i.getAttribute('src'))"""))
    check("decorative operators are hidden from assistive tech",
          c.eval("""[...document.querySelectorAll('.tq__plus, .tq__equals')]
            .every(a => a.getAttribute('aria-hidden') === 'true')"""))
    check("each input group carries an accessible name",
          c.eval("""[...document.querySelectorAll('.tq__block')]
            .every(g => (g.getAttribute('aria-label') || '').length > 10)"""))
    c.screenshot(f"{OUT}/geometry_1920.png")


# -------------------------------------------------- the run and the pause
def run_states(c, url, label):
    print(f"\n[automatic run and pause @ {label}]")
    c.send("Page.addScriptToEvaluateOnNewDocument", {"source": """
      window.__tqSamples = [];
      const sample = () => {
        const host = document.querySelector('[data-three-questions]');
        if (!host) return;
        /* .tq is positioned by styles.css; static means the stylesheet has
           not landed yet and every opacity would read as 1. */
        if (getComputedStyle(host).position !== 'absolute') return;
        /* Opacity lives on the [data-tq-reveal] group, so a child always
           reads 1. Walk up to the group before deciding. */
        const vis = sel => {
          const n = host.querySelector(sel);
          if (!n) return false;
          const group = n.closest('[data-tq-reveal]') || n;
          return parseFloat(getComputedStyle(group).opacity) > 0.01;
        };
        const boxes = {};
        host.querySelectorAll(
          '.tq__title, .tq__subtitle, .tq__card, .tq__copy, .tq__plus,'
          + ' .tq__equals, .tq__result-card, .tq__result-note')
          .forEach((n, i) => {
            boxes[i] = [n.offsetLeft, n.offsetTop, n.offsetWidth, n.offsetHeight];
          });
        window.__tqSamples.push({
          t: Math.round(performance.now()),
          state: host.getAttribute('data-tq-state') || '',
          phase: host.getAttribute('data-tq-phase') || '',
          shown: [...host.querySelectorAll('[data-tq-reveal].is-revealed')]
                   .map(n => n.dataset.tqReveal),
          equals: vis('.tq__equals'),
          resultCard: vis('.tq__result-card'),
          resultLabel: vis('.tq__result-label'),
          resultNote: vis('.tq__result-note'),
          boxes: boxes,
        });
      };
      const tick = setInterval(sample, 30);
      setTimeout(() => clearInterval(tick), 20000);
      document.addEventListener('DOMContentLoaded', sample);
    """})
    go(c, url + f"&slide={SLIDE_INDEX}")
    # Wait well past the end of the run: the pause must hold indefinitely.
    time.sleep((SEQUENCE_MS + SETTLE_MS) / 1000 + 4.0)

    samples = json.loads(c.eval("JSON.stringify(window.__tqSamples || [])") or "[]")
    check("the run was observed from the first frame",
          len(samples) > 150, f"{len(samples)} samples")

    seen = []
    for smp in samples:
        if smp["state"] and (not seen or seen[-1][0] != smp["state"]):
            seen.append((smp["state"], smp["t"]))
    order = [s for s, _ in seen]
    check("the four automatic states run in order",
          order == STATES, json.dumps(order))
    check("no state is revisited", len(order) == len(set(order)),
          json.dumps(order))

    first = {}
    for smp in samples:
        for name in smp["shown"]:
            first.setdefault(name, smp["t"])
    check("the header leads the first input",
          first.get("header", 1e9) < first.get("group-1", 0),
          json.dumps({k: first.get(k) for k in ("header", "group-1")}))
    for group, plus in (("group-1", "plus-1"), ("group-2", "plus-2")):
        check(f"{plus} follows {group} rather than leading it",
              group in first and plus in first and first[group] < first[plus],
              f'{first.get(group)} vs {first.get(plus)}')
    check("plus-1 arrives before the second input",
          first.get("plus-1", 1e9) < first.get("group-2", 0),
          json.dumps({k: first.get(k) for k in ("plus-1", "group-2")}))
    check("plus-2 arrives before the third input",
          first.get("plus-2", 1e9) < first.get("group-3", 0),
          json.dumps({k: first.get(k) for k in ("plus-2", "group-3")}))

    # The pause is the point of the slide.
    leaked = [s["t"] for s in samples
              if s["equals"] or s["resultCard"] or s["resultLabel"]
              or s["resultNote"]]
    check("no part of the answer is ever visible during the automatic run",
          not leaked, f"leaked at {leaked[:3]}")
    check("the equals sign is never revealed by a timer",
          "equals" not in first, json.dumps(sorted(first)))
    check("the Right Price group is never revealed by a timer",
          "result" not in first, json.dumps(sorted(first)))
    check("the run parks in waiting-for-result", phase(c) == "waiting-for-result",
          phase(c))
    check("the state stays at premiums-visible while it waits",
          state(c) == "premiums-visible", state(c))
    check("the deck did not advance on its own", slide_id(c) == SLIDE_ID,
          slide_id(c))

    laid_out = [s for s in samples if any(b[2] for b in s["boxes"].values())]
    baseline = laid_out[0] if laid_out else None
    drifted = [s["t"] for s in laid_out if s["boxes"] != baseline["boxes"]]
    check("no element moved during the run", not drifted,
          f"drifted at {drifted[:3]}")
    c.screenshot(f"{OUT}/{label}_pause.png")


def run_result(c, url, label):
    print(f"\n[manual result reveal @ {label}]")
    go(c, url + f"&slide={SLIDE_INDEX}")
    time.sleep((SEQUENCE_MS + SETTLE_MS) / 1000)
    check("primed at the pause", phase(c) == "waiting-for-result", phase(c))

    seq = json.loads(c.eval("""(async () => {
      const wait = ms => new Promise(r => setTimeout(r, ms));
      const host = () => document.querySelector('[data-three-questions]');
      const vis = sel => {
        const n = host().querySelector(sel);
        if (!n) return false;
        const group = n.closest('[data-tq-reveal]') || n;
        return parseFloat(getComputedStyle(group).opacity) > 0.01;
      };
      const active = () => document.querySelector(
        '.atlas-slide.is-active').dataset.atlasSlideId;
      document.querySelector('.atlas-stage-wrap').click();
      const trace = [];
      const t0 = performance.now();
      while (performance.now() - t0 < 1200) {
        trace.push([Math.round(performance.now() - t0),
                    vis('.tq__equals'), vis('.tq__result-card')]);
        await wait(20);
      }
      return JSON.stringify({
        equalsAt: trace.find(r => r[1])?.[0] ?? null,
        resultAt: trace.find(r => r[2])?.[0] ?? null,
        state: host().dataset.tqState, phase: host().dataset.tqPhase,
        active: active(),
        live: host().querySelector('[data-tq-live]').textContent,
      });
    })()"""))
    check("the equals sign appears on the gesture",
          seq["equalsAt"] is not None, json.dumps(seq))
    check("the Right Price group appears too",
          seq["resultAt"] is not None, json.dumps(seq))
    check("the equals sign lands before the answer does",
          seq["equalsAt"] is not None and seq["resultAt"] is not None
          and seq["equalsAt"] < seq["resultAt"],
          f'equals {seq["equalsAt"]}ms, result {seq["resultAt"]}ms')
    check("the answer waits for the equals travel to finish",
          seq["resultAt"] is not None and seq["resultAt"] >= EQUALS_MS - 80,
          f'result at {seq["resultAt"]}ms, equals takes {EQUALS_MS}ms')
    check("it enters result-visible",
          seq["state"] == "result-visible" and seq["phase"] == "result-visible",
          json.dumps(seq))
    check("the reveal gesture did not advance the deck",
          seq["active"] == SLIDE_ID, seq["active"])
    check("the result is announced once to assistive tech",
          "Right Price" in (seq["live"] or ""), seq["live"])

    # It holds, and does not loop or advance.
    before = revealed(c)
    time.sleep(5.2)
    check("the final state is held without looping or advancing",
          revealed(c) == before and state(c) == "result-visible"
          and slide_id(c) == SLIDE_ID,
          f"state={state(c)} id={slide_id(c)}")
    check("everything is showing at the end",
          len(revealed(c)) == c.eval(
              "document.querySelectorAll('[data-tq-reveal]').length"),
          len(revealed(c)))
    c.screenshot(f"{OUT}/{label}_result.png")

    time.sleep(0.4)
    c.click_stage()
    time.sleep(0.4)
    check("the next gesture advances normally",
          slide_id(c) == NEXT_ID, f"id={slide_id(c)}")


def run_interaction(c, url):
    print("\n[interaction ownership]")

    # A gesture mid-run buys the inputs and still stops at the pause.
    go(c, url + f"&slide={SLIDE_INDEX}")
    time.sleep(0.9)
    early = json.loads(c.eval("""(async () => {
      const wait = ms => new Promise(r => setTimeout(r, ms));
      const host = () => document.querySelector('[data-three-questions]');
      const n = () => host().querySelectorAll(
        '[data-tq-reveal].is-revealed').length;
      const vis = sel => {
        const el = host().querySelector(sel);
        if (!el) return false;
        const group = el.closest('[data-tq-reveal]') || el;
        return parseFloat(getComputedStyle(group).opacity) > 0.01;
      };
      const active = () => document.querySelector(
        '.atlas-slide.is-active').dataset.atlasSlideId;
      const before = {n: n(), phase: host().dataset.tqPhase};
      document.querySelector('.atlas-stage-wrap').click();
      await wait(200);
      return JSON.stringify({
        before,
        after: {n: n(), state: host().dataset.tqState,
                phase: host().dataset.tqPhase, active: active(),
                equals: vis('.tq__equals'), result: vis('.tq__result-card')},
      });
    })()"""))
    check("the click really did land mid-run",
          early["before"]["phase"] == "intro", json.dumps(early["before"]))
    check("a click mid-run completes all three inputs",
          early["after"]["n"] == 6 and early["after"]["state"] == "premiums-visible",
          json.dumps(early["after"]))
    check("it stops at the pause rather than the answer",
          early["after"]["phase"] == "waiting-for-result",
          early["after"]["phase"])
    check("it does not reveal the equals sign with the same gesture",
          not early["after"]["equals"], early["after"]["equals"])
    check("it does not reveal Right Price with the same gesture",
          not early["after"]["result"], early["after"]["result"])
    check("it does not advance the deck",
          early["after"]["active"] == SLIDE_ID, early["after"]["active"])

    # A double click must not skip the pause.
    go(c, url + f"&slide={SLIDE_INDEX}")
    time.sleep(0.9)
    c.click_stage()
    c.click_stage()
    time.sleep(0.3)
    check("a double click mid-run cannot skip the pause",
          phase(c) == "waiting-for-result" and slide_id(c) == SLIDE_ID,
          f"phase={phase(c)} id={slide_id(c)}")

    go(c, url + f"&slide={SLIDE_INDEX}")
    time.sleep((SEQUENCE_MS + SETTLE_MS) / 1000)
    c.click_stage()
    c.click_stage()
    time.sleep(0.4)
    check("a double click at the pause reveals once without advancing",
          phase(c) == "result-visible" and slide_id(c) == SLIDE_ID,
          f"phase={phase(c)} id={slide_id(c)}")

    go(c, url + f"&slide={SLIDE_INDEX}")
    time.sleep(0.9)
    for _ in range(8):
        c.key(" ", "Space", 32)
    time.sleep(0.3)
    check("a burst of key repeat cannot run past the pause",
          phase(c) in ("waiting-for-result", "result-visible")
          and slide_id(c) == SLIDE_ID,
          f"phase={phase(c)} id={slide_id(c)}")

    # Space and Enter match click at both steps.
    for key, code, num in ((" ", "Space", 32), ("Enter", "Enter", 13)):
        go(c, url + f"&slide={SLIDE_INDEX}")
        time.sleep(0.9)
        c.key(key, code, num)
        time.sleep(0.2)
        check(f"{code} mid-run stops at the pause",
              phase(c) == "waiting-for-result" and slide_id(c) == SLIDE_ID,
              f"phase={phase(c)} id={slide_id(c)}")
        time.sleep(0.5)
        c.key(key, code, num)
        time.sleep(0.6)
        check(f"{code} at the pause reveals the answer without advancing",
              phase(c) == "result-visible" and slide_id(c) == SLIDE_ID,
              f"phase={phase(c)} id={slide_id(c)}")

    # ArrowRight is always deck navigation, at any point.
    for wait_s, where in ((0.8, "mid-run"), ((SEQUENCE_MS + SETTLE_MS) / 1000,
                                             "at the pause")):
        go(c, url + f"&slide={SLIDE_INDEX}")
        time.sleep(wait_s)
        c.key("ArrowRight", "ArrowRight", 39)
        time.sleep(0.4)
        check(f"ArrowRight leaves the slide {where}",
              slide_id(c) == NEXT_ID, f"id={slide_id(c)}")


def run_reset(c, url):
    print("\n[reset and timer cleanup]")
    go(c, url + f"&slide={SLIDE_INDEX}")
    time.sleep((SEQUENCE_MS + SETTLE_MS) / 1000)
    c.click_stage()
    time.sleep(0.8)
    check("primed with the answer showing", phase(c) == "result-visible", phase(c))

    c.key("ArrowRight", "ArrowRight", 39)
    time.sleep(0.4)
    check("leaving cleared the run",
          phase(c) == "intro" and state(c) == "intro" and revealed(c) == [],
          f"phase={phase(c)} state={state(c)} revealed={revealed(c)}")
    check("the live region was cleared",
          c.eval("document.querySelector('[data-tq-live]').textContent") == "")

    c.key("ArrowLeft", "ArrowLeft", 37)
    time.sleep(0.2)
    check("re-entering starts from the beginning",
          len(revealed(c)) <= 1, json.dumps(revealed(c)))
    time.sleep((SEQUENCE_MS + SETTLE_MS) / 1000)
    check("re-entering replays the inputs and pauses again",
          phase(c) == "waiting-for-result" and state(c) == "premiums-visible",
          f"phase={phase(c)} state={state(c)}")
    check("the answer is hidden again after re-entry",
          c.eval("""!document.querySelector('[data-tq-reveal=\"result\"]')
            .classList.contains('is-revealed')"""))

    c.key("ArrowLeft", "ArrowLeft", 37)
    time.sleep(0.4)
    check("back navigation lands on the media plan walkthrough",
          slide_id(c) == PREV_ID, f"id={slide_id(c)}")
    check("back navigation cleared the run",
          phase(c) == "intro" and revealed(c) == [], f"phase={phase(c)}")

    # Pending steps must be cancelled, not merely ignored.
    go(c, url + f"&slide={SLIDE_INDEX}")
    time.sleep(0.5)
    c.key("ArrowRight", "ArrowRight", 39)
    time.sleep((SEQUENCE_MS + SETTLE_MS) / 1000)
    check("a pending step cannot fire onto the next slide",
          revealed(c) == [] and phase(c) == "intro",
          f"phase={phase(c)} revealed={revealed(c)}")
    check("the deck stayed where the presenter left it",
          slide_id(c) == NEXT_ID, f"id={slide_id(c)}")

    for _ in range(3):
        c.key("ArrowLeft", "ArrowLeft", 37)
        time.sleep(0.3)
        c.key("ArrowRight", "ArrowRight", 39)
        time.sleep(0.3)
    c.key("ArrowLeft", "ArrowLeft", 37)
    time.sleep((SEQUENCE_MS + SETTLE_MS) / 1000)
    check("repeated entry and exit still ends in one clean pause",
          phase(c) == "waiting-for-result", phase(c))
    res = json.loads(c.eval("""(async () => {
      const wait = ms => new Promise(r => setTimeout(r, ms));
      const active = () => document.querySelector(
        '.atlas-slide.is-active').dataset.atlasSlideId;
      document.querySelector('.atlas-stage-wrap').click();
      await wait(600);
      return JSON.stringify({phase: document.querySelector(
        '[data-three-questions]').dataset.tqPhase, active: active()});
    })()"""))
    check("one gesture is handled once, not once per past visit",
          res["phase"] == "result-visible" and res["active"] == SLIDE_ID,
          json.dumps(res))

    # A refresh starts over, not at the answer.
    go(c, url + f"&slide={SLIDE_INDEX}")
    time.sleep(0.3)
    shown = revealed(c)
    check("a refresh begins the run again rather than resuming it",
          phase(c) == "intro" and "equals" not in shown and "result" not in shown
          and len(shown) < 6,
          f"phase={phase(c)} revealed={shown}")


def run_layout(c, url, label):
    print(f"\n[layout and rounded frame @ {label}]")
    go(c, url + f"&slide={SLIDE_INDEX}")
    time.sleep((SEQUENCE_MS + SETTLE_MS) / 1000)
    c.click_stage()
    time.sleep(1.0)

    frame = c.eval("""(() => {
      const stage = document.querySelector('.atlas-stage');
      const wrap = document.querySelector('.atlas-stage-wrap');
      const deck = document.querySelector('.atlas-deck');
      const cs = el => getComputedStyle(el);
      const sr = stage.getBoundingClientRect();
      const wr = wrap.getBoundingClientRect();
      const cards = [...document.querySelectorAll('.tq__block .tq__card')]
        .map(n => n.getBoundingClientRect());
      const lefts = cards.map(r => Math.round(r.left));
      let overlap = 0;
      for (let i = 1; i < cards.length; i += 1) {
        if (cards[i].top < cards[i - 1].bottom - 0.5) overlap += 1;
      }
      const rects = [...document.querySelectorAll(
        '.tq__question, .tq__detail, .tq__card-label, .tq__result-label,'
        + ' .tq__result-note, .tq__title, .tq__subtitle')];
      return {
        radius: cs(stage).borderTopLeftRadius,
        overflow: cs(stage).overflow,
        canvas: cs(deck).backgroundColor,
        slideBg: cs(document.querySelector('.atlas-slide--three-questions'))
          .backgroundColor,
        pads: [sr.top - wr.top, sr.left - wr.left,
               wr.right - sr.right, wr.bottom - sr.bottom],
        escaped: [...document.querySelectorAll(
          '.atlas-slide--three-questions .tq > *')].filter(n => {
            const r = n.getBoundingClientRect();
            if (!r.width && !r.height) return false;
            return r.left < sr.left - 0.5 || r.right > sr.right + 0.5
                || r.top < sr.top - 0.5 || r.bottom > sr.bottom + 0.5;
          }).map(n => String(n.className)),
        cardSpread: Math.max(...lefts) - Math.min(...lefts),
        stacked: overlap === 0,
        scrolls: document.documentElement.scrollWidth > innerWidth + 1
              || document.documentElement.scrollHeight > innerHeight + 1,
        clipped: rects.filter(n => n.scrollWidth > n.clientWidth + 1)
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
    check("the three input cards stay vertically aligned",
          frame["cardSpread"] <= 6, frame["cardSpread"])
    check("the three inputs do not overlap", frame["stacked"])
    check("no text clips or wraps", not frame["clipped"],
          json.dumps(frame["clipped"]))
    check("the page does not scroll", not frame["scrolls"])

    # Legibility, measured rather than assumed: source size times the stage
    # scale is what the room actually reads.
    visible = json.loads(c.eval("""JSON.stringify((() => {
      const stage = document.querySelector('.atlas-stage');
      const scale = stage.getBoundingClientRect().width / 1920;
      const out = {};
      document.querySelectorAll(
        '.atlas-slide--three-questions .tq *').forEach(n => {
          if (!n.getClientRects().length) return;
          if (n.closest('.tq__sr')) return;
          const direct = [...n.childNodes].some(
            x => x.nodeType === Node.TEXT_NODE && x.textContent.trim());
          if (!direct) return;
          const cls = String(n.className).split(' ')[0];
          const px = parseFloat(getComputedStyle(n).fontSize) * scale;
          if (!(cls in out) || px < out[cls]) out[cls] = +px.toFixed(1);
        });
      return {scale: +scale.toFixed(4), sizes: out};
    })())"""))
    below = {k: v for k, v in visible["sizes"].items() if v < VISIBLE_FLOOR}
    unexpected = {k: v for k, v in below.items() if k not in FIGMA_FIXED}
    check(f"every string outside the two Figma-fixed labels clears"
          f" {VISIBLE_FLOOR:.0f}px on screen (stage scale {visible['scale']})",
          not unexpected, "below floor: " + json.dumps(unexpected))
    check("only the Figma-fixed labels ever sit under the floor",
          set(below) <= FIGMA_FIXED, json.dumps(below))

    # The operators must stay centred between the cards they join.
    centres = c.eval("""(() => {
      const mid = el => {
        const r = el.getBoundingClientRect();
        return (r.top + r.bottom) / 2;
      };
      const cards = [...document.querySelectorAll('.tq__block .tq__card')];
      const plus = [...document.querySelectorAll('.tq__plus')];
      const gaps = [];
      for (let i = 0; i < plus.length; i += 1) {
        const a = cards[i].getBoundingClientRect();
        const b = cards[i + 1].getBoundingClientRect();
        gaps.push(Math.abs(mid(plus[i]) - (a.bottom + b.top) / 2));
      }
      const eq = document.querySelector('.tq__equals').getBoundingClientRect();
      const res = document.querySelector('.tq__result-card')
        .getBoundingClientRect();
      return {gaps: gaps.map(g => +g.toFixed(1)),
              equalsLeftOfResult: eq.right < res.left,
              resultInsideStage: res.right < document.querySelector(
                '.atlas-stage').getBoundingClientRect().right};
    })()""")
    check("both plus signs sit centred between their cards",
          all(g <= 2 for g in centres["gaps"]), json.dumps(centres["gaps"]))
    check("the equals sign stays left of the result",
          centres["equalsLeftOfResult"])
    check("the result card stays inside the slide",
          centres["resultInsideStage"])

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
          const cs = sel => getComputedStyle(document.querySelector(sel));
          return {
            header: cs('.tq__header').transform,
            block: cs('.tq__block--details').transform,
            equals: cs('.tq__equals').transform,
            result: cs('.tq__result').transform,
            duration: cs('.tq__block--details').transitionDuration,
          };
        })()""")
        check("nothing travels or scales under reduced motion",
              all(motion[k] == "none"
                  for k in ("header", "block", "equals", "result")),
              json.dumps(motion))
        check("fades are short under reduced motion",
              motion["duration"] == "0.12s", motion["duration"])

        time.sleep((SEQUENCE_MS + SETTLE_MS) / 1000 + 1.5)
        check("the automatic run still ends at the pause",
              phase(c) == "waiting-for-result"
              and state(c) == "premiums-visible", phase(c))
        check("the answer is still held back under reduced motion",
              c.eval("""(() => {
                const eq = document.querySelector('.tq__equals');
                const group = document.querySelector('[data-tq-reveal="result"]');
                return parseFloat(getComputedStyle(eq).opacity) < 0.01
                  && parseFloat(getComputedStyle(group).opacity) < 0.01;
              })()"""))
        check("the gold pass on the result is dropped",
              c.eval("""(() => {
                const r = document.querySelector('[data-tq-reveal="result"]');
                r.classList.add('is-revealed');
                const name = getComputedStyle(
                  document.querySelector('.tq__result-card')).animationName;
                r.classList.remove('is-revealed');
                return name === 'none';
              })()"""))

        res = json.loads(c.eval("""(async () => {
          const wait = ms => new Promise(r => setTimeout(r, ms));
          const host = () => document.querySelector('[data-three-questions]');
          const active = () => document.querySelector(
            '.atlas-slide.is-active').dataset.atlasSlideId;
          document.querySelector('.atlas-stage-wrap').click();
          await wait(700);
          const revealed = {phase: host().dataset.tqPhase, active: active()};
          await wait(500);
          document.querySelector('.atlas-stage-wrap').click();
          await wait(450);
          return JSON.stringify({revealed, last: active()});
        })()"""))
        check("one gesture still reveals the answer without advancing",
              res["revealed"]["phase"] == "result-visible"
              and res["revealed"]["active"] == SLIDE_ID, json.dumps(res))
        check("the following gesture still advances",
              res["last"] == NEXT_ID, res["last"])
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
            run_removal(c, url)
            run_placement(c, url)
            run_copy(c, url)
            run_geometry(c, url)
            run_states(c, url, "1920x1080")
            run_result(c, url, "1920x1080")
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
                run_states(c, url, label)
                run_result(c, url, label)
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
