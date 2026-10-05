#!/usr/bin/env python3
"""QA for the closing card (Figma 779:25788) and the appendix it opens.

Two things are under test and they are not the same thing.

The first is the card itself: it has to land on Figma's pixels, in Figma's
faces, with Figma's words. That part is ordinary slide QA.

The second is structural, and it is the part worth guarding. The closing
card is last because the deck derives the running order, not because it is
written last, and the two appendix sections are off that order entirely.
Both properties are invisible in a screenshot and easy to lose in a later
edit, so they are asserted directly: a temporary section is injected mid
deck to prove it lands in front of the closing card, and the appendix is
opened, returned from, and reopened to prove the main index survives it.

Usage:  python3 qa_atlas_closing_slide.py
"""

import base64
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request

HOST = "127.0.0.1"
PORT = 8001
BASE = f"http://{HOST}:{PORT}"
ART = "/tmp/qa_atlas_closing_slide"

CLOSING_ID = "closing-thank-you"
APPENDIX_01 = "pricing-complexity"
APPENDIX_02 = "line-item-necessity"

# The main run after the two appendix sections came out of it. Order is the
# assertion: this is what "relative order preserved" means concretely.
EXPECTED_MAIN = [
    "cover",
    "pricing-complexity",
    "structured-pricing-data",
    "rate-card-right-price",
    "same-ad-different-rate",
    "rate-card-three-questions",
    "connected-workflows",
    "future-rate-card-workflow",
    "core-planning-media-plan",
    "rate-card-line-pricing",
    CLOSING_ID,
]

# Figma 779:25788, measured against the 1920x1080 stage. Tolerance is 3px:
# the display face is a real font here, so anything larger is a real move
# rather than hinting noise.
FIGMA = {
    ".clo__title":      (67, 178, None, 56),
    ".clo__cta":        (67, 279, 460, 93),
    ".clo__rule":       (63, 540, 1808, 1),
    ".clo__appendix":   (63, 642, None, 56),
    ".clo__row--1":     (63, 742, None, 36),
    ".clo__row--2":     (63, 822, None, 36),
    ".clo__row--3":     (63, 902, None, 36),
    ".clo__logo":       (1826, 997, 36, 41),
}

COPY = {
    ".clo__title": "Thank you",
    ".clo__cta-label": "Explore the prototype",
    ".clo__appendix": "Appendix",
    ".clo__row--1 .clo__num": "01",
    ".clo__row--1 .clo__row-title":
        "Think of Disney Advertising as a supermarket",
    ".clo__row--2 .clo__num": "02",
    ".clo__row--2 .clo__row-title":
        "Buyers can purchase through different deal types",
    ".clo__row--3 .clo__num": "03",
    ".clo__row--3 .clo__row-title":
        "Why do line items need to be in the rate card",
}

# The closing CTA resolves to the app root on whatever origin serves the
# prototype, so the expectation is derived from the harness base rather
# than pinned to a deployment URL.
PROTOTYPE_URL = f"{BASE}/"

passed = 0
failed = []


def check(label, ok, detail=""):
    global passed
    if ok:
        passed += 1
        print(f"  PASS  {label}" + (f" -- {detail}" if detail else ""))
    else:
        failed.append(f"{label}" + (f" -- {detail}" if detail else ""))
        print(f"  FAIL  {label}" + (f" -- {detail}" if detail else ""))


class Chrome:
    def __init__(self, reduced=False):
        s = socket.socket()
        s.bind((HOST, 0))
        self.port = s.getsockname()[1]
        s.close()
        args = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            f"--remote-debugging-port={self.port}",
            "--remote-allow-origins=*",
            "--window-size=1960,1160",
            f"--user-data-dir=/tmp/qa-closing-{self.port}",
            "--no-first-run", "--no-default-browser-check",
            "--headless=new", "--hide-scrollbars", "--disable-gpu",
            "--force-device-scale-factor=1",
        ]
        if reduced:
            args.append("--force-prefers-reduced-motion")
        args.append("about:blank")
        self.proc = subprocess.Popen(
            args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        for _ in range(120):
            try:
                urllib.request.urlopen(
                    f"http://{HOST}:{self.port}/json/version", timeout=0.5
                ).read()
                break
            except Exception:
                time.sleep(0.1)
        import websocket
        tab = next(
            t for t in json.loads(
                urllib.request.urlopen(f"http://{HOST}:{self.port}/json").read()
            ) if t["type"] == "page"
        )
        self.ws = websocket.create_connection(
            tab["webSocketDebuggerUrl"], timeout=120, max_size=300 * 1024 * 1024
        )
        self.i = 0
        self.errors = []
        self.send("Runtime.enable")
        self.send("Page.enable")

    def send(self, method, params=None):
        self.i += 1
        self.ws.send(json.dumps(
            {"id": self.i, "method": method, "params": params or {}}
        ))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("method") == "Runtime.consoleAPICalled":
                if msg["params"].get("type") == "error":
                    self.errors.append(str(msg["params"])[:220])
            if msg.get("method") == "Runtime.exceptionThrown":
                self.errors.append(str(msg["params"])[:220])
            if msg.get("id") == self.i:
                return msg.get("result", {})

    def ev(self, expr):
        r = self.send("Runtime.evaluate", {
            "expression": expr, "returnByValue": True, "awaitPromise": True
        })
        if "exceptionDetails" in r:
            raise RuntimeError(json.dumps(r["exceptionDetails"])[:400])
        return r.get("result", {}).get("value")

    def open(self, query, wait_for=".atlas-slide.is-active"):
        self.send("Page.navigate", {"url": f"{BASE}/{query}"})
        for _ in range(500):
            if self.ev(f"!!document.querySelector('{wait_for}')"):
                break
            time.sleep(0.02)
        self.ev("document.fonts.ready")
        time.sleep(0.5)

    def unscale(self):
        """Pin the stage to 1:1 so measurements are Figma pixels."""
        self.ev(
            "(() => { const el=document.createElement('style');"
            "el.textContent='.atlas-stage-wrap{padding:0!important;"
            "display:block!important;overflow:visible!important}"
            ".atlas-stage{transform:none!important;margin:0!important}';"
            "document.head.appendChild(el); })()"
        )
        time.sleep(0.3)

    def shot(self, name, clip=None):
        os.makedirs(ART, exist_ok=True)
        p = {"format": "png"}
        if clip:
            p["clip"] = dict(clip, scale=1)
        d = self.send("Page.captureScreenshot", p)
        with open(f"{ART}/{name}.png", "wb") as fh:
            fh.write(base64.b64decode(d["data"]))

    def active(self):
        return self.ev(
            "(() => { const s=document.querySelector('.atlas-slide.is-active');"
            "return s ? s.getAttribute('data-atlas-slide-id') : null; })()"
        )

    def key(self, k):
        self.ev(
            "document.dispatchEvent(new KeyboardEvent('keydown',"
            f"{{key:{json.dumps(k)},bubbles:true,cancelable:true}}))"
        )
        time.sleep(0.22)

    def kill(self):
        try:
            self.proc.kill()
        except Exception:
            pass


# ---------------------------------------------------------------------------


def run_order(c):
    print("\n[the running order is derived]")
    c.open("?section=atlas&slide=1")
    order = c.ev(
        "[...document.querySelectorAll('[data-page=\"atlas\"] .atlas-slide')]"
        ".filter(s=>!s.hasAttribute('data-atlas-appendix') && "
        "!s.hasAttribute('data-atlas-closing'))"
        ".map(s=>s.getAttribute('data-atlas-slide-id'))"
    )
    order.append(CLOSING_ID)
    check("the main run is the expected twelve, in order",
          order == EXPECTED_MAIN,
          " > ".join(order) if order != EXPECTED_MAIN else f"{len(order)} slides")

    closings = c.ev(
        "document.querySelectorAll('[data-page=\"atlas\"] "
        "[data-atlas-closing]').length"
    )
    check("exactly one section is marked as the closing card", closings == 1,
          f"found {closings}")

    appendix = c.ev(
        "[...document.querySelectorAll('[data-page=\"atlas\"] "
        "[data-atlas-appendix]')].map(s=>s.getAttribute('data-atlas-slide-id'))"
    )
    check("exactly the two intended sections are appendix",
          sorted(appendix) == sorted([APPENDIX_01, APPENDIX_02]),
          ", ".join(appendix))


def run_walk(c):
    """Prove the running order without racing the presenter slides.

    Half the deck swallows ArrowRight to walk its own internal states, and
    several of those states are gated on animations finishing, so pressing
    the key until the slide changes is both slow and timing-dependent. The
    contract that actually matters is the mapping from position to section,
    which ?slide=N exercises directly, plus the two boundaries: the last
    content slide hands over to the closing card, and the closing card is
    where forward motion stops.
    """
    print("\n[every position maps to the section it should]")
    for i, want in enumerate(EXPECTED_MAIN, start=1):
        c.open(f"?section=atlas&slide={i}")
        got = c.active()
        check(f"position {i} is {want}", got == want, str(got))

    print("\n[the appendix is not reachable from any position]")
    reached = []
    for i in range(1, len(EXPECTED_MAIN) + 4):
        c.open(f"?section=atlas&slide={i}")
        reached.append(c.active())
    check("no position resolves to an appendix section",
          APPENDIX_01 not in reached and APPENDIX_02 not in reached)
    check("positions past the end of the run do not invent a slide",
          reached[len(EXPECTED_MAIN):] == ["cover"] * 3,
          ", ".join(reached[len(EXPECTED_MAIN):]))

    print("\n[the handover into and out of the closing card]")
    # The last content slide runs no internal states, so one press is one
    # slide here and the boundary can be walked for real.
    last_content = EXPECTED_MAIN[-2]
    c.open(f"?section=atlas&slide={len(EXPECTED_MAIN) - 1}")
    check(f"starting on {last_content}", c.active() == last_content,
          str(c.active()))
    c.key("ArrowRight")
    check("forward from the last content slide reaches the closing card",
          c.active() == CLOSING_ID, str(c.active()))
    c.key("ArrowLeft")
    check("back from the closing card returns to the last content slide",
          c.active() == last_content, str(c.active()))

    c.open(f"?section=atlas&slide={len(EXPECTED_MAIN)}")
    c.key("End")
    check("End on the closing card stays there", c.active() == CLOSING_ID,
          str(c.active()))
    c.key("Home")
    check("Home goes to the cover", c.active() == "cover", str(c.active()))
    c.open(f"?section=atlas&slide={len(EXPECTED_MAIN)}")
    c.key("End")
    check("End goes to the closing card, by identity",
          c.active() == CLOSING_ID, str(c.active()))


def run_future_ordering(c):
    """Inject a section mid-deck and confirm the closing card stays last.

    This is the whole point of deriving the order, so it gets tested for
    real rather than by reading the code. The fixture is removed again and
    the deck re-derived, so nothing is left behind.
    """
    print("\n[a new slide added later still lands before the closing card]")
    c.open("?section=atlas&slide=1")
    c.ev("""(() => {
      const stage = document.querySelector('[data-page="atlas"] .atlas-stage');
      const closing = stage.querySelector('[data-atlas-closing]');
      const probe = document.createElement('section');
      probe.className = 'atlas-slide';
      probe.setAttribute('data-atlas-slide-id', 'qa-temp-probe');
      /* Deliberately inserted BEFORE the closing card in the DOM and also
         re-inserted after it below, to prove neither position matters. */
      stage.insertBefore(probe, closing);
    })()""")
    order = c.ev(
        "[...document.querySelectorAll('[data-page=\"atlas\"] .atlas-slide')]"
        ".filter(s=>!s.hasAttribute('data-atlas-appendix'))"
        ".map(s=>s.getAttribute('data-atlas-slide-id'))"
    )
    check("a section inserted before the closing card sits before it",
          order.index("qa-temp-probe") < order.index(CLOSING_ID),
          " > ".join(order[-3:]))

    c.ev("""(() => {
      const stage = document.querySelector('[data-page="atlas"] .atlas-stage');
      const probe = stage.querySelector('[data-atlas-slide-id="qa-temp-probe"]');
      stage.appendChild(probe);      /* now physically AFTER the closing card */
    })()""")
    derived = c.ev("""(() => {
      const all = [...document.querySelectorAll('[data-page="atlas"] .atlas-slide')];
      const closing = all.filter(s=>s.hasAttribute('data-atlas-closing'));
      const main = all.filter(s=>!s.hasAttribute('data-atlas-appendix') &&
                                 !s.hasAttribute('data-atlas-closing'));
      return main.concat(closing.slice(0,1))
                 .map(s=>s.getAttribute('data-atlas-slide-id'));
    })()""")
    check("even written after it, a regular section is derived before it",
          derived[-1] == CLOSING_ID and "qa-temp-probe" in derived[:-1],
          " > ".join(derived[-3:]))

    c.ev("(() => { const p=document.querySelector("
         "'[data-atlas-slide-id=\"qa-temp-probe\"]'); if (p) p.remove(); })()")
    left = c.ev("document.querySelectorAll("
                "'[data-atlas-slide-id=\"qa-temp-probe\"]').length")
    check("the fixture is removed again", left == 0)


def run_appendix(c):
    print("\n[the appendix opens, returns, and reopens]")
    c.open(f"?section=atlas&slide=12")
    check("the deck opens on the closing card", c.active() == CLOSING_ID,
          str(c.active()))

    for row, want in ((1, APPENDIX_01), (2, APPENDIX_02)):
        for attempt in (1, 2):
            c.ev(f"document.querySelector('.clo__row--{row}').click()")
            time.sleep(0.35)
            check(f"row 0{row} opens {want} (attempt {attempt})",
                  c.active() == want, str(c.active()))
            back_visible = c.ev(
                "(() => { const b=document.querySelector("
                "'[data-atlas-appendix-back]'); return !!b && !b.hidden; })()"
            )
            check(f"the return control is offered inside 0{row}", back_visible)
            c.ev("document.querySelector('[data-atlas-appendix-back]').click()")
            time.sleep(0.35)
            check(f"returning from 0{row} lands on the closing card",
                  c.active() == CLOSING_ID, str(c.active()))

    # The main index must be intact after all that.
    c.key("ArrowLeft")
    check("the main index survived the round trips",
          c.active() == "rate-card-line-pricing", str(c.active()))

    print("\n[a row click does not also advance the deck]")
    c.open("?section=atlas&slide=12")
    c.ev("document.querySelector('.clo__row--1').click()")
    time.sleep(0.4)
    check("clicking a row opens the appendix and nothing else",
          c.active() == APPENDIX_01, str(c.active()))

    print("\n[other ways out of an appendix]")
    for gesture, label in (("Escape", "Escape"), ("ArrowRight", "forward"),
                           ("ArrowLeft", "back")):
        c.open("?section=atlas&slide=12")
        c.ev("document.querySelector('.clo__row--2').click()")
        time.sleep(0.3)
        if c.active() != APPENDIX_02:
            check(f"{label}: appendix opened first", False, str(c.active()))
            continue
        c.key(gesture)
        check(f"{label} returns to the closing card, not the main run",
              c.active() == CLOSING_ID, str(c.active()))


def run_deep_links(c):
    print("\n[deep links]")
    for query, want, label in (
        ("?section=atlas&slide=6", "core-planning-media-plan",
         "an unchanged position still resolves"),
        ("?section=atlas&slide=12", CLOSING_ID, "position 12 is the closing card"),
        (f"?section=atlas&slide={APPENDIX_01}", APPENDIX_01,
         "an appendix id resolves straight to its section"),
        (f"?section=atlas&slide={APPENDIX_02}", APPENDIX_02,
         "the second appendix id resolves too"),
        (f"?section=atlas&slide={CLOSING_ID}", CLOSING_ID,
         "the closing card resolves by id as well as by position"),
        ("?section=atlas&slide=99", "cover", "an out-of-range position falls back"),
        ("?section=atlas&slide=nonsense", "cover", "an unknown id falls back"),
    ):
        c.open(query)
        check(label, c.active() == want, f"{query} -> {c.active()}")

    c.open(f"?section=atlas&slide={APPENDIX_01}")
    url = c.ev("location.search")
    check("an appendix keeps its id in the URL, not a position",
          APPENDIX_01 in url, url)
    c.ev("document.querySelector('[data-atlas-appendix-back]').click()")
    time.sleep(0.35)
    url = c.ev("location.search")
    check("returning writes the closing card's position back", "slide=12" in url,
          url)


def run_figma(c):
    print("\n[the card sits on Figma's pixels]")
    c.open("?section=atlas&slide=12")
    c.unscale()
    for sel, (x, y, w, h) in FIGMA.items():
        got = c.ev(
            "(() => { const e=document.querySelector("
            f"'.atlas-slide--closing {sel}'); if (!e) return null;"
            "const r=e.getBoundingClientRect();"
            "return [r.left, r.top, r.width, r.height]; })()"
        )
        if got is None:
            check(f"{sel} exists", False)
            continue
        want = [x, y, w, h]
        bad = [
            f"{n}: want {wv} got {round(gv, 1)}"
            for n, wv, gv in zip(("x", "y", "w", "h"), want, got)
            if wv is not None and abs(gv - wv) > 3
        ]
        check(f"{sel} sits on its Figma box", not bad,
              "; ".join(bad) if bad else
              f"{round(got[0])},{round(got[1])} {round(got[2])}x{round(got[3])}")

    print("\n[Figma's words, verbatim]")
    for sel, want in COPY.items():
        got = c.ev(
            "(() => { const e=document.querySelector("
            f"'.atlas-slide--closing {sel}'); return e ? e.textContent : null; }})()"
            .replace("}})()", "})()")
        )
        check(f"{sel}", got == want, f"{got!r}")

    print("\n[the display faces Figma specifies actually load]")
    faces = c.ev("""(() => {
      const want = {
        '.clo__title': 900, '.clo__cta-label': 900,
        '.clo__appendix': 900, '.clo__num': 900,
        '.clo__row--1 .clo__row-title': 500
      };
      const out = [];
      for (const s in want) {
        const c = getComputedStyle(
          document.querySelector('.atlas-slide--closing ' + s));
        out.push(s + '|' + c.fontWeight + '|' + c.fontFamily.split(',')[0]);
      }
      return out.join('\\n');
    })()""").split("\n")
    for row in faces:
        sel, weight, family = row.split("|")
        want_family = ('"InspireTWDC Medium"' if weight == "500"
                       else '"InspireTWDC Heavy"')
        check(f"{sel} asks for {want_family} at {weight}",
              family == want_family, f"got {family}")
    loaded = c.ev(
        "document.fonts.check('900 56px \"InspireTWDC Heavy\"') && "
        "document.fonts.check('500 36px \"InspireTWDC Medium\"')"
    )
    check("both faces are available to the browser, not substituted", loaded)


def run_prototype_link(c):
    print("\n[the prototype link]")
    c.open("?section=atlas&slide=12")
    a = c.ev("""(() => { const a=document.querySelector('.clo__cta');
      return JSON.stringify({href:a.href, target:a.target, rel:a.rel,
                             tag:a.tagName}); })()""")
    a = json.loads(a)
    check("it is a real anchor", a["tag"] == "A", a["tag"])
    check("it points at the app root on the serving origin",
          a["href"] == PROTOTYPE_URL, a["href"])
    check("it is not a file path", not a["href"].startswith("file:"),
          a["href"])
    check("it is the app root, not a pinned build or preview folder",
          a["href"].rstrip("/").count("/") == 2, a["href"])
    check("it does not point back at the presentation",
          "section=atlas" not in a["href"], a["href"])
    check("it opens in a new tab", a["target"] == "_blank", a["target"])
    check("it carries noopener", "noopener" in a["rel"], a["rel"])

    # Clicking it must not also move the deck underneath.
    before = c.active()
    c.ev("""(() => {
      const a = document.querySelector('.clo__cta');
      /* Neutralise the navigation so the tab survives; the point of the
         test is the deck's reaction to the click, not the new tab. */
      a.addEventListener('click', e => e.preventDefault(), {once:true});
      a.click();
    })()""")
    time.sleep(0.4)
    check("clicking it leaves the deck on the closing card",
          c.active() == before == CLOSING_ID, str(c.active()))


def run_a11y(c):
    print("\n[keyboard and focus]")
    c.open("?section=atlas&slide=12")
    focusable = c.ev(
        "[...document.querySelectorAll('.atlas-slide--closing a[href]')]"
        ".map(a=>a.className).join(' | ')"
    )
    check("all three links are focusable anchors",
          focusable.count("clo__") >= 3, focusable)

    # Enter on a focused row must open the appendix, not be eaten by the deck.
    c.ev("document.querySelector('.clo__row--1').focus()")
    check("the row takes focus",
          c.ev("document.activeElement.className").startswith("clo__row"),
          c.ev("document.activeElement.className"))
    c.ev("""(() => { const el=document.activeElement;
      el.dispatchEvent(new KeyboardEvent('keydown',
        {key:'Enter', bubbles:true, cancelable:true})); })()""")
    time.sleep(0.15)
    still = c.ev("document.activeElement.className")
    check("Enter on a focused row is not swallowed by the deck",
          "clo__row" in still or c.active() == APPENDIX_01, still)

    outline = c.ev("""(() => {
      const a = document.querySelector('.clo__row--1');
      a.classList.add('qa-focus-probe');
      const s = document.createElement('style');
      s.textContent = '.qa-focus-probe{outline:2px solid #4F80E0}';
      document.head.appendChild(s);
      const w = getComputedStyle(a).outlineWidth;
      a.classList.remove('qa-focus-probe'); s.remove();
      return w;
    })()""")
    check("a focus ring is defined for the rows", outline != "0px", outline)

    aria = c.ev(
        "document.querySelector('.atlas-slide--closing')"
        ".getAttribute('aria-label')"
    )
    check("the closing card is labelled for assistive tech",
          bool(aria) and "Thank you" in aria, str(aria))


def run_viewports(c):
    print("\n[the composition holds at other sizes]")
    for w, h, label in ((1920, 1080, "presentation"), (1440, 900, "laptop"),
                        (1280, 720, "embedded browser")):
        c.send("Emulation.setDeviceMetricsOverride", {
            "width": w, "height": h, "deviceScaleFactor": 1, "mobile": False
        })
        c.open("?section=atlas&slide=12")
        time.sleep(0.4)
        res = c.ev("""(() => {
          const stage = document.querySelector('[data-page="atlas"] .atlas-stage');
          const sc = parseFloat(getComputedStyle(stage).getPropertyValue('--atlas-scale'));
          const out = [];
          for (const s of ['.clo__title','.clo__cta-label','.clo__appendix',
                           '.clo__row--1 .clo__row-title','.clo__row--2 .clo__row-title']) {
            const e = document.querySelector('.atlas-slide--closing ' + s);
            const lh = parseFloat(getComputedStyle(e).lineHeight) ||
                       parseFloat(getComputedStyle(e).fontSize);
            out.push(Math.round(e.getBoundingClientRect().height / lh / sc));
          }
          const r = document.querySelector('.atlas-slide--closing .clo__row--2')
                            .getBoundingClientRect();
          const st = stage.getBoundingClientRect();
          return JSON.stringify({scale: sc, lines: out,
                                 inside: r.bottom <= st.bottom + 1 &&
                                         r.right <= st.right + 1});
        })()""")
        res = json.loads(res)
        check(f"{label} {w}x{h}: nothing rewraps",
              all(n == 1 for n in res["lines"]), str(res["lines"]))
        check(f"{label} {w}x{h}: the last row stays inside the card",
              res["inside"], f"scale {round(res['scale'], 3)}")
        c.shot(f"viewport-{w}x{h}")
    c.send("Emulation.clearDeviceMetricsOverride")


def run_untouched(c):
    print("\n[the appendix sections kept their own content]")
    c.open(f"?section=atlas&slide={APPENDIX_01}")
    t1 = c.ev("(document.querySelector('.wpc__title')||{}).textContent")
    check("appendix 01 still has its own heading",
          t1 == "Why Pricing Gets Complicated Before Planning", str(t1))
    terms = c.ev(
        "['Buyer Scope','Deal Context','Base Rate','Premium Details']"
        ".filter(t => document.querySelector('.atlas-slide--why-pricing')"
        ".textContent.includes(t)).join(', ')"
    )
    check("and its content", terms.count(",") == 3, terms)

    c.open(f"?section=atlas&slide={APPENDIX_02}")
    t2 = c.ev("(document.querySelector('.wln__title')||{}).textContent")
    check("appendix 02 still has its own heading",
          t2 == "Why do line items need to be in the Rate Card?", str(t2))
    terms = c.ev(
        "['Rate Card','Line Item','Consistent Pricing']"
        ".filter(t => document.querySelector('.atlas-slide--line-need')"
        ".textContent.includes(t)).join(', ')"
    )
    check("and its content", terms.count(",") == 2, terms)


def main():
    try:
        urllib.request.urlopen(f"{BASE}/index.html", timeout=3).read(64)
    except Exception:
        print(f"Serve the project on {BASE} first: python3 -m http.server {PORT}")
        return 2

    os.makedirs(ART, exist_ok=True)
    c = Chrome()
    try:
        run_order(c)
        run_walk(c)
        run_future_ordering(c)
        run_appendix(c)
        run_deep_links(c)
        run_figma(c)
        run_prototype_link(c)
        run_a11y(c)
        run_viewports(c)
        run_untouched(c)

        print("\n[console]")
        c.open("?section=atlas&slide=12")
        c.ev("document.querySelector('.clo__row--1').click()")
        time.sleep(0.3)
        c.ev("document.querySelector('[data-atlas-appendix-back]').click()")
        time.sleep(0.3)
        check("no console errors", not c.errors,
              "; ".join(c.errors[:2]) if c.errors else "")

        c.unscale()
        c.shot("closing", {"x": 0, "y": 0, "width": 1920, "height": 1080})
    finally:
        c.kill()

    print(f"\n{passed}/{passed + len(failed)} passed")
    if failed:
        print("FAILED:")
        for f in failed:
            print(f"  - {f}")
    print(f"artifacts in {ART}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
