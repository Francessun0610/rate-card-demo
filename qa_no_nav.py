#!/usr/bin/env python3
"""
qa_no_nav.py - Atlas slide viewer behavior QA.

Scope:

  - Verify the deck contains exactly the slides in EXPECTED_ORDER below,
    once each and in that order. The list is deliberately the only place
    the running order is written down in this file; the checks below read
    it rather than naming slides, so removing or moving a slide does not
    strand the walk part way through the deck.
  - Some slides own click / Space / Enter while they build. This suite
    crosses them with ArrowRight and spends their owned states first, per
    ARROW_OWNED_STATES. Their reveal behavior itself is covered by
    qa_right_price_slide.py, qa_supermarket_slide.py,
    qa_upfront_scatter_slide.py, qa_same_ad_rate_slide.py,
    qa_three_questions_slide.py and qa_media_plan_slide.py.
  - Verify no artifacts of an earlier, longer deck remain: no stale
    `of N` aria-labels, no duplicate ids, and data-atlas-slide indexes
    contiguous 1..TOTAL_SLIDES.
  - Verify every slide's typography floor (>= 14px) and non-clipping.
  - Verify navigation behavior:
      * ArrowRight / Space / click advances one slide.
      * ArrowLeft retreats one slide; no-op on slide 1.
      * Home / End jump to the first / last slide.
      * Click / ArrowRight / Space on the final slide navigates to
        the Rate Card Manager list route and does NOT loop back.
      * Hammering the advance keys on the last slide settles on /list once.
      * Keyboard listeners are silent once route is /list.
  - Verify each slide's locked title / subtitle copy, per SLIDE_COPY.

Slide geometry is verified per slide by the suites named above rather
than here.
"""
import base64
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request

ROOT  = "/Users/frances.sun/My Drive/Cursor and Code/Rate Card"
URL   = "http://127.0.0.1:8001/?section=atlas"
OUT   = "/tmp/qa_no_nav"
TOTAL_SLIDES = 11
FINAL_INDEX = TOTAL_SLIDES - 1
EXPECTED_ORDER = [
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
    "closing-thank-you",
]

# Most slides let arrow keys through untouched, which is what lets a
# presenter leave one mid-run. These two are presenter-driven: they own a
# forward gesture per grouped state before the deck gets it back, so
# crossing them takes that many extra presses. Entering either one resets
# it, so backward navigation is never held up.
ARROW_OWNED_STATES = {
    "advertising-supermarket": 3,   # store, shelf space, product
    "upfront-scatter": 2,           # the Upfront story, then the Scatter one
    "same-ad-different-rate": 3,    # the branch, Upfront, then Scatter
    "core-planning-media-plan": 5,  # the line item's five stops
}

# Most of those states are a class toggle and hand the next gesture back
# after the deck's usual 400ms guard. Three slides are different: each of
# their states runs a sequence and holds navigation until it settles, so a
# gesture sent too early is swallowed rather than queued. This walk waits
# out each run, so it reads settled states rather than catching one mid
# move. The waits track the holds those slides declare for themselves.
ARROW_STATE_WAIT = {"upfront-scatter": 4.6,
                    "same-ad-different-rate": 4.5,
                    "core-planning-media-plan": 2.2}

# Per-slide copy (2026-08-04 brief). Locking the title / subtitle wording
# so future edits cannot silently drift from the approved narrative. Each
# entry maps `data-atlas-slide-id` to the expected DOM copy at the two
# canonical selectors used across the deck.
SLIDE_COPY = {
    "core-planning-media-plan": {
        "title": (
            ".mpl__title",
            "Each line item is priced as the media plan is built.",
        ),
        "subtitle": (
            ".mpl__subtitle",
            "Core Planning uses ICM and TOM context. RCM returns the"
            " rate, and planning continues.",
        ),
    },
    "advertising-supermarket": {
        "title": (
            ".sup__title",
            "Think of Disney Advertising as a supermarket",
        ),
        "subtitle": (
            ".sup__subtitle",
            "Ad Inventory is the shelf space, and Offerings are the"
            " products planners can select.",
        ),
    },
    "rate-card-right-price": {
        "title": (
            ".rpx__title",
            "A Rate Card tells us the right price for each deal.",
        ),
        "subtitle": (
            ".rpx__subtitle",
            "It connects the buyer, the deal, the product, and anything"
            " that changes the price.",
        ),
    },
    "upfront-scatter": {
        "title": (
            ".usc__title",
            "Buyers can purchase through different deal types",
        ),
        "subtitle": (
            ".usc__subtitle",
            "The deal type helps determine which Rate Card applies.",
        ),
    },
    "same-ad-different-rate": {
        "title": (".sar__title", "Same product. Different applicable rate."),
        "subtitle": (
            ".sar__subtitle",
            "The price depends on the buyer and the deal,"
            " not only on the product.",
        ),
    },
    "cover": {
        "title": (".cov__title", "Rate Card Manager"),
        "presenter": (".cov__presenter", "Frances Sun"),
        "date": (".cov__date", "Sept 2026"),
    },
    "pricing-complexity": {
        "title": (
            ".wpcf__title",
            "Why pricing gets complicated before planning",
        ),
        "subtitle": (
            ".wpcf__subtitle",
            "Price changes with the buyer, deal, product, and adjustments.",
        ),
    },
    "rate-card-three-questions": {
        "title": (
            ".tq__title",
            "RCM organizes pricing into three connected sections",
        ),
        "subtitle": (
            ".tq__subtitle",
            "Together, they determine the applicable rate used in planning.",
        ),
    },
    "line-item-necessity": {
        "title": (
            ".wln__title",
            "Why do line items need to be in the Rate Card?",
        ),
        "subtitle": (
            ".wln__subtitle",
            "Because every price must be tied to a specific sellable item.",
        ),
    },
    "structured-pricing-data": {
        "title": (
            ".rcd__title",
            "Turning Rate Cards into Structured Pricing Data",
        ),
        "subtitle": (
            ".rcd__subtitle",
            "Existing rate-card workbooks are imported into a consistent"
            " structure for pricing and future Planning workflows.",
        ),
    },
    "future-rate-card-workflow": {
        "title": (
            ".frw__title",
            "Future Rate Card Workflow",
        ),
        "subtitle": (
            ".frw__subtitle",
            "Move from disconnected spreadsheets to structured rate-card"
            " data that supports automated pricing.",
        ),
    },
    "connected-workflows": {
        "title": (
            ".cw__title",
            "Pricing decisions change as the deal changes",
        ),
        "subtitle": (
            ".cw__subtitle",
            "Users need to revisit connected pricing sections without"
            " starting over.",
        ),
    },
    "rate-card-line-pricing": {
        "title": (
            ".rlp__title",
            "How Rate Cards Will Support Core Planning",
        ),
        "subtitle": (
            ".rlp__subtitle",
            "RCM manages negotiated rate-card data. Core Planning will use"
            " applicable rates in future planning workflows.",
        ),
    },
}
os.makedirs(OUT, exist_ok=True)


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def boot_chrome(viewport):
    w, h = viewport
    port = _free_port()
    proc = subprocess.Popen([
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        f"--remote-debugging-port={port}",
        "--remote-allow-origins=*",
        f"--window-size={w},{h}",
        "--user-data-dir=/tmp/qa_no_nav_profile",
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
            "expression": expr,
            "returnByValue": True,
            "awaitPromise": True,
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

    def key(self, key, code, vk):
        for t in ("keyDown", "keyUp"):
            self.send("Input.dispatchKeyEvent", {
                "type": t, "key": key, "code": code,
                "windowsVirtualKeyCode": vk, "nativeVirtualKeyCode": vk,
            })


def go(c, url):
    c.send("Page.enable")
    c.send("Runtime.enable")
    c.send("Network.enable")
    c.send("Network.setCacheDisabled", {"cacheDisabled": True})
    c.send("Page.navigate", {"url": url})
    for _ in range(80):
        if c.eval("!!document.querySelector('.atlas-slide.is-active')") or \
           c.eval("document.body?.getAttribute('data-route') === 'list'"):
            break
        time.sleep(0.1)
    time.sleep(0.4)


CHECKS = []


def check(label, ok, detail=""):
    tag = "PASS" if ok else "FAIL"
    print(f"  {tag}  {label}{(' -- ' + detail) if detail else ''}")
    CHECKS.append((label, ok, detail))


def slide_idx(c):
    """Position in the main run, which is what the deck counts.

    The appendix sections are still .atlas-slide elements sitting in the
    same container; they are simply not part of the run. Counting raw DOM
    position would put every slide after them two places out.
    """
    return c.eval(
        "(() => { var s = [...document.querySelectorAll('.atlas-slide')]"
        ".filter(x => !x.hasAttribute('data-atlas-appendix'));"
        " return s.findIndex(x => x.classList.contains('is-active')); })()"
    )


def slide_id(c):
    return c.eval(
        "document.querySelector('.atlas-slide.is-active')?.dataset.atlasSlideId"
        " || null"
    )


def mpl_state(c):
    """Slide 7's current state name.

    "0" is a real value here (the slide before the presenter starts the
    line item), so it is returned as-is; None means the media plan slide is
    not active.
    """
    return c.eval(
        "(() => { const m = document.querySelector("
        "'.atlas-slide.is-active [data-media-plan]');"
        " return m ? (m.getAttribute('data-mpl-step') || '0') : null; })()"
    )


def tq_state(c):
    """Slide 8's current state name, on the same terms as mpl_state()."""
    return c.eval(
        "(() => { const t = document.querySelector("
        "'.atlas-slide.is-active [data-three-questions]');"
        " return t ? (t.getAttribute('data-tq-state') || '') : null; })()"
    )


def route(c):
    return c.eval("document.body.getAttribute('data-route')")


def center_of_wrap(c):
    return c.eval("""(() => {
      var r = document.querySelector('.atlas-stage-wrap').getBoundingClientRect();
      return { x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2) };
    })()""")


def click_center(c):
    p = center_of_wrap(c)
    c.click(p["x"], p["y"])
    time.sleep(0.25)


def run_viewport(label, viewport):
    print(f"\n== {label} ({viewport[0]}x{viewport[1]}) ==")
    proc, port = boot_chrome(viewport)
    try:
        c = CDP(port)

        # ---- Structural: the main run, in the right order -------------------
        go(c, URL)
        slide_count = c.eval(
            "document.querySelectorAll('.atlas-slide:not([data-atlas-appendix])')"
            ".length"
        )
        check(
            f"the main run is exactly {TOTAL_SLIDES} slides",
            slide_count == TOTAL_SLIDES,
            f"slides={slide_count}",
        )
        actual_order = c.eval(
            "[...document.querySelectorAll('.atlas-slide')].filter(s => !s.hasAttribute('data-atlas-appendix'))"
            ".map(s => s.dataset.atlasSlideId || null)"
        )
        check(
            "slides appear in the new narrative order",
            actual_order == EXPECTED_ORDER,
            json.dumps(actual_order),
        )
        metadata = c.eval("""(() => {
          const slides = [...document.querySelectorAll('.atlas-slide')]
            .filter(s => !s.hasAttribute('data-atlas-appendix'));
          const ids = [...document.querySelectorAll(
            '[data-page="atlas"] [id]'
          )].map(el => el.id);
          return {
            indexes: slides.map(s => Number(s.dataset.atlasSlide)),
            aria: slides.map(s => s.getAttribute('aria-label')),
            hasSvgCover: !!document.querySelector(
              'img[src*="/atlas/slide-1.svg"]'
            ),
            legacyTotal: slides.filter(
              s => /of (?:8|9)/.test(s.getAttribute('aria-label') || '')
            ).length,
            duplicateIds: [...new Set(
              ids.filter((id, i) => ids.indexOf(id) !== i)
            )],
          };
        })()""")
        check(
            f"slide indexes are contiguous 1..{TOTAL_SLIDES} and every"
            f" aria-label says 'of {TOTAL_SLIDES}'",
            metadata["indexes"] == list(range(1, TOTAL_SLIDES + 1))
                and all(f"of {TOTAL_SLIDES}" in lbl for lbl in metadata["aria"])
                and metadata["legacyTotal"] == 0
                and not metadata["hasSvgCover"]
                and not metadata["duplicateIds"],
            json.dumps(metadata),
        )
        check(
            "starts on slide 1 (cover)",
            slide_idx(c) == 0 and slide_id(c) == "cover",
            f"index={slide_idx(c)} id={slide_id(c)}",
        )

        # ---- Presentation typefaces -----------------------------------------
        # Whether the deck has its faces is a property of the document, not of
        # any one slide, so it is asserted once here. Doing it per slide meant
        # re-requesting Open Sans from Google Fonts on every navigation with
        # the HTTP cache disabled, which the remote end starts refusing part
        # way through a run, failing a random slide for a reason that has
        # nothing to do with the deck.
        fonts = c.eval("""(async () => {
          const want = ['14px "Open Sans"', '14px "MultiplaneTWDC Display"'];
          const deadline = Date.now() + 10000;
          while (true) {
            try {
              await Promise.all(want.map(f => document.fonts.load(f)));
              await document.fonts.ready;
            } catch (_) {}
            if (want.every(f => document.fonts.check(f))) break;
            if (Date.now() > deadline) break;
            await new Promise(r => setTimeout(r, 250));
          }
          return {
            openSans: document.fonts.check('14px "Open Sans"'),
            multiplane: document.fonts.check('14px "MultiplaneTWDC Display"'),
          };
        })()""")
        check(
            "presentation fonts are available",
            all(fonts.values()),
            json.dumps(fonts),
        )

        # ---- Per-slide typography floor + screenshot ------------------------
        if label == "1920x1080":
            for slide_number in range(1, TOTAL_SLIDES + 1):
                go(c, URL + f"&slide={slide_number}")
                visual = c.eval("""(async () => {
                  /* Text metrics below are only meaningful once the faces the
                   * slide renders in have settled. Availability itself is
                   * asserted once per viewport, before this loop. */
                  try { await document.fonts.ready; } catch (_) {}
                  const slide = document.querySelector('.atlas-slide.is-active');
                  const undersized = [...slide.querySelectorAll('*')]
                    .filter(el => {
                      if (!el.getClientRects().length) return false;
                      const direct = [...el.childNodes].some(n =>
                        n.nodeType === Node.TEXT_NODE && n.textContent.trim()
                      );
                      return direct
                        && parseFloat(getComputedStyle(el).fontSize) < 14;
                    })
                    .map(el => ({
                      tag: el.tagName,
                      className: String(el.className || ''),
                      text: el.textContent.trim().slice(0, 80),
                      size: getComputedStyle(el).fontSize,
                    }));
                  const clipped = [...slide.querySelectorAll('*')]
                    .filter(el => {
                      if (!el.getClientRects().length) return false;
                      const direct = [...el.childNodes].some(n =>
                        n.nodeType === Node.TEXT_NODE && n.textContent.trim()
                      );
                      if (!direct) return false;
                      const st = getComputedStyle(el);
                      return st.overflow !== 'visible'
                        && (el.scrollWidth > el.clientWidth + 1
                            || el.scrollHeight > el.clientHeight + 1);
                    })
                    .map(el => ({
                      className: String(el.className || ''),
                      text: el.textContent.trim().slice(0, 80),
                    }));
                  return { undersized, clipped };
                })()""")
                check(
                    f"slide {slide_number} has no visible text below 14px",
                    not visual["undersized"],
                    json.dumps(visual["undersized"]),
                )
                check(
                    f"slide {slide_number} has no clipped HTML text",
                    not visual["clipped"],
                    json.dumps(visual["clipped"]),
                )
                # Copy assertion: title / subtitle for the active slide
                # must match the brief-locked text in SLIDE_COPY. Also
                # guard against em / en dashes anywhere on the slide
                # (.cursorrules bans them project-wide, including UX copy
                # and presentation text).
                current_id = slide_id(c)
                expected = SLIDE_COPY.get(current_id, {})
                selectors = json.dumps({
                    field: sel
                    for field, (sel, _) in expected.items()
                })
                copy_result = c.eval(f"""(() => {{
                  const slide = document.querySelector('.atlas-slide.is-active');
                  const map = {selectors};
                  const out = {{}};
                  for (const [field, sel] of Object.entries(map)) {{
                    const el = slide.querySelector(sel);
                    out[field] = el
                      ? el.textContent.replace(/\\s+/g, ' ').trim()
                      : null;
                  }}
                  out.__dashes = /[\\u2013\\u2014]/.test(slide.textContent)
                    ? slide.textContent.match(/[^.\\n]*[\\u2013\\u2014][^.\\n]*/g)
                    : null;
                  return out;
                }})()""")
                for field, (_, expected_text) in expected.items():
                    check(
                        f"slide {slide_number} ({current_id}) {field} matches brief",
                        copy_result.get(field) == expected_text,
                        json.dumps({
                            "got": copy_result.get(field),
                            "expected": expected_text,
                        }),
                    )
                check(
                    f"slide {slide_number} ({current_id}) contains no em or en dashes",
                    copy_result.get("__dashes") is None,
                    json.dumps(copy_result.get("__dashes")),
                )
                c.screenshot(f"{OUT}/{label}_full_slide_{slide_number}.png")
            go(c, URL + "&slide=1")

        # ---- Navigation: click / Space / ArrowRight advance ----------------
        click_center(c)
        check(
            "click on slide 1 advances to slide 2 (rate-card-right-price)",
            slide_idx(c) == 1 and slide_id(c) == "rate-card-right-price",
            f"index={slide_idx(c)} id={slide_id(c)}",
        )
        # Walk the rest on ArrowRight. Slides that run their own sequence on
        # click / Space still hand arrow keys straight to the deck, so one
        # press crosses them mid-run. The two presenter-driven slides own a
        # forward gesture per grouped state first, and the walk spends those
        # before expecting the deck to move.
        for target in range(2, 11):
            here = slide_id(c)
            owned = ARROW_OWNED_STATES.get(here, 0)
            if owned:
                # Let the slide's own intro finish first, so every press
                # below is spent on a grouped state rather than on skipping
                # a heading that was still arriving.
                time.sleep(1.0)
            beat = ARROW_STATE_WAIT.get(here, 0.55) if owned else 0.25
            for _ in range(owned + 1):
                c.key("ArrowRight", "ArrowRight", 39)
                time.sleep(beat)
            want = EXPECTED_ORDER[target]
            if owned:
                label = (f"ArrowRight spends {owned} state(s) on {here}, then"
                         f" advances to slide {target + 1} ({want})")
            else:
                label = (f"ArrowRight leaves {here} immediately, mid-run, to"
                         f" slide {target + 1} ({want})")
            check(
                label,
                slide_idx(c) == target and slide_id(c) == want,
                f"index={slide_idx(c)} id={slide_id(c)}",
            )

        # ---- Navigation: ArrowLeft retreats, no-op on slide 1 --------------
        # Walk back to the three questions slide one press at a time, taking
        # the slides to pass from the running order rather than naming them,
        # so this keeps working when the deck gains or loses a slide.
        back_to = EXPECTED_ORDER.index("rate-card-three-questions")
        for target in range(slide_idx(c) - 1, back_to, -1):
            c.key("ArrowLeft", "ArrowLeft", 37)
            time.sleep(0.2)
            want = EXPECTED_ORDER[target]
            check(
                f"ArrowLeft on slide {target + 2} retreats to slide"
                f" {target + 1} ({want})",
                slide_idx(c) == target and slide_id(c) == want,
                f"index={slide_idx(c)} id={slide_id(c)}",
            )
        c.key("ArrowLeft", "ArrowLeft", 37)
        time.sleep(0.3)
        check(
            "ArrowLeft into slide 7 restarts its run from the beginning "
            "(every slide change resets it, see initAtlasThreeQuestions)",
            slide_idx(c) == 6 and slide_id(c) == "rate-card-three-questions"
                and tq_state(c) in ("", "intro", "details-visible"),
            f"index={slide_idx(c)} state={tq_state(c)}",
        )
        c.key("ArrowLeft", "ArrowLeft", 37)
        time.sleep(0.3)
        check(
            "ArrowLeft leaves slide 7 immediately, mid-run, and retreats to "
            "slide 6 (the line item walkthrough, which re-enters on step 0 "
            "and so hands a further ArrowLeft straight to the deck)",
            slide_idx(c) == 5 and slide_id(c) == "core-planning-media-plan"
                and mpl_state(c) == "0",
            f"index={slide_idx(c)} id={slide_id(c)} step={mpl_state(c)}",
        )
        c.key("Home", "Home", 36)
        time.sleep(0.2)
        check("Home returns to slide 1", slide_idx(c) == 0)
        c.key("ArrowLeft", "ArrowLeft", 37)
        time.sleep(0.2)
        check("ArrowLeft on slide 1 is a no-op", slide_idx(c) == 0)

        # ---- Navigation: End jumps to final slide --------------------------
        c.key("End", "End", 35)
        time.sleep(0.2)
        check(
            f"End jumps to the closing card (slide {TOTAL_SLIDES})",
            slide_idx(c) == FINAL_INDEX
                and slide_id(c) == "closing-thank-you",
            f"index={slide_idx(c)} id={slide_id(c)}",
        )

        # ---- Core Planning copy check ---------------------------------------
        # No longer the last slide: the closing card is. Visit it directly so
        # this check does not silently start testing whatever ends the run.
        go(c, URL + f"&slide={TOTAL_SLIDES - 1}")
        check(
            "the slide before the closing card is Core Planning",
            slide_id(c) == "rate-card-line-pricing",
            f"id={slide_id(c)}",
        )
        cp = c.eval("""(() => {
          const slide = document.querySelector('.atlas-slide.is-active');
          const text = (sel) => slide.querySelector(sel)?.textContent
            .replace(/\\s+/g, ' ').trim() || null;
          const rows = (sel) => [...slide.querySelectorAll(sel)]
            .map(el => el.textContent.replace(/\\s+/g, ' ').trim());
          const statement = slide.querySelector('.rlp__statement');
          const statementHTML = statement
            ? statement.innerHTML.replace(/\\s+/g, ' ').trim()
            : null;
          // Guard: nothing on this slide extends past the 1920px stage
          // edge, so no visible copy can be clipped by overflow:hidden.
          const stageRect = document.querySelector('.atlas-stage')
            .getBoundingClientRect();
          const overflowing = [...slide.querySelectorAll('*')]
            .filter(el => {
              if (!el.getClientRects().length) return false;
              const direct = [...el.childNodes].some(n =>
                n.nodeType === Node.TEXT_NODE && n.textContent.trim()
              );
              if (!direct) return false;
              const r = el.getBoundingClientRect();
              return r.right > stageRect.right + 1;
            })
            .map(el => ({
              className: String(el.className || ''),
              text: el.textContent.trim().slice(0, 80),
            }));
          return {
            id: slide.dataset.atlasSlideId,
            aria: slide.getAttribute('aria-label'),
            title: text('.rlp__title'),
            subtitle: text('.rlp__subtitle'),
            rcmSupport: text('.rlp__card--rcm .rlp__card-support'),
            rcmRowCopy: rows('.rlp__card--rcm .rlp__row-copy'),
            connectorLabel: text('.rlp__connector-label'),
            connectorSublabel: text('.rlp__connector-sublabel'),
            planSupport: text('.rlp__card--planning .rlp__card-support'),
            planRowCopy: rows('.rlp__card--planning .rlp__row-copy'),
            statementHTML,
            forbidden: /manages the logic|Published rate card|Buyer Context/i
              .test(slide.textContent),
            overflowing,
          };
        })()""")
        cp_ok = (
            cp["id"] == "rate-card-line-pricing"
            and cp["aria"] == f"Slide {TOTAL_SLIDES - 1} of {TOTAL_SLIDES}:"
                              " How Rate Cards Will Support Core Planning"
            and cp["title"] == "How Rate Cards Will Support Core Planning"
            and cp["subtitle"] == (
                "RCM manages negotiated rate-card data. Core Planning will "
                "use applicable rates in future planning workflows."
            )
            and cp["rcmSupport"] == "Manage rate-card data"
            and cp["rcmRowCopy"] == [
                "Shared negotiation context",
                "Negotiated base rate",
                "Conditional adjustments",
            ]
            and cp["connectorLabel"] == "Applicable rate"
            and cp["connectorSublabel"] == "via shared pricing capabilities"
            and cp["planSupport"] == "Use applicable pricing"
            and cp["planRowCopy"] == [
                "Matches CARD",
                "Comes from LINE",
                "Comes from PREM",
            ]
            and cp["statementHTML"] == (
                "RCM manages the rate-card data.<br>Core Planning will use "
                "the applicable rate."
            )
            and not cp["forbidden"]
            and not cp["overflowing"]
        )
        check(
            "Core Planning copy matches the finalized brief",
            cp_ok,
            json.dumps(cp),
        )
        c.screenshot(f"{OUT}/{label}_core_planning.png")

        # ---- Navigation: final slide exits to /list, no loop back ----------
        go(c, URL + f"&slide={TOTAL_SLIDES}")
        click_center(c)
        check(
            "click on the closing card navigates to Rate Card Manager",
            route(c) == "list",
            f"route={route(c)}",
        )
        check(
            "no loop back to atlas after final forward",
            route(c) != "atlas",
        )

        # Re-open Atlas, verify ArrowRight on the final slide also exits.
        go(c, URL)
        c.key("End", "End", 35)
        time.sleep(0.2)
        check(
            "[re-open] End jumps to the closing card",
            slide_idx(c) == FINAL_INDEX,
        )
        c.key("ArrowRight", "ArrowRight", 39)
        time.sleep(0.35)
        check(
            "[re-open] ArrowRight on the closing card -> Rate Card Manager",
            route(c) == "list",
        )

        # Re-open Atlas, verify Space on the final slide also exits.
        go(c, URL)
        c.key("End", "End", 35)
        time.sleep(0.2)
        c.key(" ", "Space", 32)
        time.sleep(0.35)
        check(
            "[re-open] Space on the closing card -> Rate Card Manager",
            route(c) == "list",
        )

        # Hammer guard: multiple advance keys on the final slide still exit once.
        go(c, URL)
        c.key("End", "End", 35)
        time.sleep(0.2)
        for _ in range(6):
            c.key("ArrowRight", "ArrowRight", 39)
        time.sleep(0.4)
        check(
            "hammering ArrowRight on the closing card still settles on /list once",
            route(c) == "list",
        )

        # Keyboard listeners should be silent once route is /list.
        c.key("ArrowLeft", "ArrowLeft", 37)
        time.sleep(0.2)
        check(
            "ArrowLeft on /list does not re-enter atlas",
            route(c) == "list",
        )
    finally:
        proc.kill()


def main():
    # Boot the same static server the app already uses.
    if not os.path.exists(f"{ROOT}/index.html"):
        print("index.html missing", file=sys.stderr)
        sys.exit(1)
    server = subprocess.Popen(
        [sys.executable, "-m", "http.server", "8001"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Wait for the server to answer.
    for _ in range(30):
        try:
            urllib.request.urlopen(
                "http://127.0.0.1:8001/", timeout=0.5
            ).read()
            break
        except Exception:
            time.sleep(0.1)
    try:
        run_viewport("1920x1080", (1920, 1080))
        run_viewport("1440x900", (1440, 900))
        run_viewport("1280x800", (1280, 800))
    finally:
        server.terminate()

    total = len(CHECKS)
    failed = [c for c in CHECKS if not c[1]]
    print(f"\n{'FAIL' if failed else 'PASS'} - {total - len(failed)}/{total}")
    if failed:
        for label, _ok, detail in failed:
            print(f"  FAIL {label}{(' -- ' + detail) if detail else ''}")
        sys.exit(1)


if __name__ == "__main__":
    main()
