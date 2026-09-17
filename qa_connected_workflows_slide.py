#!/usr/bin/env python3
"""
qa_connected_workflows_slide.py - Atlas deck slide 15 QA.

Slide 15, "Pricing decisions change as the deal changes", carries two
internal views inside one deck slide:

  current-design   Figma node 741:13577
  previous-design  Figma node 741:19209 (the Create Rate Card step wizard)

They are a design comparison, not two deck slides. The whole point of this
suite is that the toggle never leaks into deck navigation: no slide index
change, no URL change, no history entry, and the back control returns to
the current design rather than to slide 14.

Also locked down here:

  - The slide exists once, keeps its id and position, and the deck is
    still fifteen long.
  - Both Figma nodes, measured element by element.
  - "Rate Card Details", not "RC Details", and two-way links rather than
    plus signs: the slide is about revisiting sections, not summing them.
  - Both controls are real buttons with accessible names, 44px targets
    and visible focus.
  - Focus moves between the two controls on each swap.
  - The inactive view is hidden outright, so it is neither focusable nor
    read out as duplicate content.
  - Reset on leave, and current-design on entry, refresh and deep link.
  - Double clicks, key repeat and Escape.
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
OUT = "/tmp/qa_connected_workflows_slide"
SLIDE_INDEX = 10
SLIDE_ID = "connected-workflows"
PREV_SLIDE_ID = "future-rate-card-workflow"
NEXT_SLIDE_ID = "rate-card-line-pricing"
TOTAL_SLIDES = 12

CURRENT = "current-design"
PREVIOUS = "previous-design"

TITLE = "Pricing decisions change as the deal changes"
SUBTITLE = "Users need to revisit connected pricing sections without starting over."
WIZARD_LABEL = "Step Wizard"
WIZARD_SUPPORT = "Assumes each decision is made once."
CONNECTED_LABEL = "Connected sections"
CONNECTED_SUPPORT = "Details, line items, and premiums can be updated anytime."
STEP_LABELS = ["Step 1", "Step 2", "Step 3"]
CARD_LABELS = ["Rate Card Details", "Line Items", "Premiums"]
TOGGLE_TEXT = "Previous design"
BACK_TEXT = "\u2190 Back to current design"

STAGE_RADIUS = 40
CANVAS = "rgb(30, 30, 30)"
SLIDE_BG = "rgb(2, 0, 36)"
MIN_TARGET = 44
CHROME_FLOOR = 16.0
# Figma 741:13577 fixes the step and card labels at 24px and the two
# supporting lines at 28px. They clear 16px on screen at 1920x1080 and
# 1440x900; at 1280x720 the stage scales to 0.54 and they land at 13.0
# and 15.2. Figma fidelity was chosen for those, so they are named here
# rather than failing quietly. The slide's own controls are not Figma
# composition and are held to the floor at every viewport.
FIGMA_FIXED = {"cw__step-label", "cw__struct-label", "cw__section-support"}

# Figma 741:13577 geometry, in native stage pixels: left, top, width, height.
FIGMA_CURRENT = {
    ".cw__header": (63, 88, 1828, 120),
    ".cw__section--wizard": (88, 358, 409, 58),
    ".cw__section-support--wizard": (88, 416, 720, None),
    ".cw__section--structured": (960, 358, 335, 58),
    ".cw__section-support--structured": (960, 420, 900, None),
    ".cw__step-card--1": (88, 546, 160, 137),
    ".cw__step-card--2": (276, 546, 160, 137),
    ".cw__step-card--3": (464, 546, 160, 137),
    ".cw__arrow": (697, 603, 255, 19),
    ".cw__struct-card--rc-details": (955, 537, 182, 160),
    ".cw__struct-card--line-items": (1277, 537, 182, 160),
    ".cw__struct-card--premiums": (1607, 537, 182, 160),
    ".cw__link--1": (1146, 611.2, 121, 11.5),
    ".cw__link--2": (1462, 611.2, 121, 11.5),
    ".cw__brand": (1826, 997, 36, 41),
}

CHECKS = []


def is_canvas(px):
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
            target["webSocketDebuggerUrl"], max_size=200 * 1024 * 1024,
            timeout=30,
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
                    self.logs.append(entry.get("text", "")[:160])
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

    def screenshot(self, path):
        data = self.send("Page.captureScreenshot", {"format": "png"})
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(base64.b64decode(data["data"]))


def boot_chrome(viewport, port_http, slide=SLIDE_INDEX):
    port = free_port()
    profile = f"/tmp/qa_cw_profile_{port}"
    subprocess.run(["rm", "-rf", profile], check=False)
    proc = subprocess.Popen([
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile}",
        "--headless=new", "--remote-allow-origins=*", "--no-first-run",
        "--hide-scrollbars", "--force-device-scale-factor=1",
        f"--window-size={viewport[0]},{viewport[1]}",
        f"http://127.0.0.1:{port_http}/?section=atlas&slide={slide}",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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


def view(c):
    return c.eval(
        "document.querySelector('[data-connected-workflows]')"
        "?.getAttribute('data-cw-view')"
    )


def slide_id(c):
    return c.eval(
        "document.querySelector('.atlas-slide.is-active')?.dataset.atlasSlideId"
    )


def url_slide(c):
    return c.eval("new URLSearchParams(location.search).get('slide')")


def pin_native_scale(c):
    c.eval("""(() => {
      const style = document.createElement('style');
      style.textContent = `.atlas-stage{--atlas-scale:1 !important;margin:0 !important}
        .atlas-stage-wrap{padding:0 !important;overflow:visible !important}
        .atlas-deck{position:absolute !important}
        .atlas-slide--connected-workflows .cw__view{transition:none !important}`;
      document.head.appendChild(style);
    })()""")
    time.sleep(0.4)


def show_previous(c):
    c.eval("document.querySelector('.cw__toggle').click()")
    time.sleep(0.6)


# --------------------------------------------------------------- placement
def run_placement(c, url):
    print("\n[placement]")
    go(c, url + f"&slide={SLIDE_INDEX}")
    check(f"slide {SLIDE_INDEX} is the connected workflows slide",
          slide_id(c) == SLIDE_ID, f"id={slide_id(c)}")

    order = c.eval(
        "[...document.querySelectorAll('.atlas-slide')].filter(s => !s.hasAttribute('data-atlas-appendix'))"
        ".map(s => s.dataset.atlasSlideId)"
    )
    check("the slide exists exactly once",
          order.count(SLIDE_ID) == 1, f"{order.count(SLIDE_ID)} copies")
    check("the deck is still fifteen long",
          len(order) == TOTAL_SLIDES and len(set(order)) == TOTAL_SLIDES,
          f"{len(order)} slides")
    i = order.index(SLIDE_ID)
    check("its neighbours are unchanged",
          order[i - 1] == PREV_SLIDE_ID and order[i + 1] == NEXT_SLIDE_ID,
          f"{order[i - 1]} .. {order[i + 1]}")
    check("no second deck slide was created for the previous design",
          not any("previous" in s for s in order), json.dumps(order))

    labelled = c.eval("""(() => {
      const s = document.querySelector('.atlas-slide.is-active');
      return {ordinal: s.dataset.atlasSlide, label: s.getAttribute('aria-label')};
    })()""")
    check(f"it registers as slide {SLIDE_INDEX} of {TOTAL_SLIDES}",
          labelled["ordinal"] == str(SLIDE_INDEX)
          and labelled["label"] == f"Slide {SLIDE_INDEX} of {TOTAL_SLIDES}: {TITLE}",
          json.dumps(labelled))

    check("a deep link opens the current design",
          view(c) == CURRENT, view(c))
    go(c, url + f"&slide={SLIDE_INDEX}")
    check("a refresh also opens the current design",
          view(c) == CURRENT, view(c))


def run_current_design(c, url):
    print("\n[current design: Figma 741:13577]")
    go(c, url + f"&slide={SLIDE_INDEX}")
    pin_native_scale(c)

    copy = c.eval("""(() => {
      const s = document.querySelector('.atlas-slide--connected-workflows');
      const t = sel => s.querySelector(sel)?.textContent
        .replace(/\\s+/g, ' ').trim() || null;
      return {
        title: t('.cw__title'), subtitle: t('.cw__subtitle'),
        wizard: t('.cw__section-title--wizard'),
        wizardSupport: t('.cw__section-support--wizard'),
        connected: t('.cw__section-title--structured'),
        connectedSupport: t('.cw__section-support--structured'),
        steps: [...s.querySelectorAll('.cw__step-label')].map(n => n.textContent.trim()),
        cards: [...s.querySelectorAll('.cw__struct-label')]
          .map(n => n.innerText.replace(/\\s+/g, ' ').trim()),
        html: s.innerHTML,
      };
    })()""")
    check("title matches the node", copy["title"] == TITLE, copy["title"])
    check("subtitle matches the node", copy["subtitle"] == SUBTITLE, copy["subtitle"])
    check("the left label is Step Wizard",
          copy["wizard"] == WIZARD_LABEL, copy["wizard"])
    check("the left supporting line matches",
          copy["wizardSupport"] == WIZARD_SUPPORT, copy["wizardSupport"])
    check("the right label is Connected sections",
          copy["connected"] == CONNECTED_LABEL, copy["connected"])
    check("the right supporting line matches",
          copy["connectedSupport"] == CONNECTED_SUPPORT, copy["connectedSupport"])
    check("the three step cards are right",
          copy["steps"] == STEP_LABELS, json.dumps(copy["steps"]))
    check("the three connected cards say Rate Card Details, not RC Details",
          copy["cards"] == CARD_LABELS, json.dumps(copy["cards"]))
    check("the retired RC Details label is gone from this slide",
          "RC Details" not in copy["html"])
    check("the plus signs are gone",
          "cw__plus" not in copy["html"] and "cw-plus.svg" not in copy["html"])
    check("two-way links join the connected cards",
          copy["html"].count("cw-arrow-bidirectional.svg") == 2,
          copy["html"].count("cw-arrow-bidirectional.svg"))

    measured = json.loads(c.eval("""JSON.stringify((() => {
      const stage = document.querySelector('.atlas-stage').getBoundingClientRect();
      const out = {};
      %s.forEach(sel => {
        const el = document.querySelector('.atlas-slide--connected-workflows ' + sel);
        if (!el) { out[sel] = null; return; }
        const r = el.getBoundingClientRect();
        out[sel] = [+(r.left - stage.left).toFixed(1), +(r.top - stage.top).toFixed(1),
                    +r.width.toFixed(1), +r.height.toFixed(1)];
      });
      return out;
    })())""" % json.dumps(list(FIGMA_CURRENT))))
    for sel, want in FIGMA_CURRENT.items():
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

    assets = c.eval("""[...document.querySelectorAll(
      '.atlas-slide--connected-workflows img')]
      .filter(i => !i.complete || i.naturalWidth === 0)
      .map(i => i.getAttribute('src'))""")
    check("every current-design asset loaded", not assets, json.dumps(assets))
    c.screenshot(f"{OUT}/current_1920.png")


def run_controls(c, url):
    print("\n[the two controls]")
    go(c, url + f"&slide={SLIDE_INDEX}")
    pin_native_scale(c)

    toggle = c.eval("""(() => {
      const b = document.querySelector('.cw__toggle');
      const stage = document.querySelector('.atlas-stage').getBoundingClientRect();
      const r = b.getBoundingClientRect();
      const cs = getComputedStyle(b);
      return {tag: b.tagName, type: b.getAttribute('type'),
              name: b.getAttribute('aria-label'),
              text: b.textContent.trim(),
              box: [+(r.left - stage.left).toFixed(1), +(r.top - stage.top).toFixed(1),
                    +r.width.toFixed(1), +r.height.toFixed(1)],
              font: parseFloat(cs.fontSize), radius: cs.borderTopLeftRadius,
              border: cs.borderTopColor};
    })()""")
    check("the toggle is a real button",
          toggle["tag"] == "BUTTON" and toggle["type"] == "button",
          f'{toggle["tag"]} type={toggle["type"]}')
    check("its accessible name is 'View previous design'",
          toggle["name"] == "View previous design", toggle["name"])
    check("its visible label is 'Previous design'",
          toggle["text"] == TOGGLE_TEXT, toggle["text"])
    check("it sits at the Figma lower-left anchor (88, 766)",
          abs(toggle["box"][0] - 88) <= 1 and abs(toggle["box"][1] - 766) <= 1,
          json.dumps(toggle["box"]))
    check(f"its target is at least {MIN_TARGET}x{MIN_TARGET}",
          toggle["box"][2] >= MIN_TARGET and toggle["box"][3] >= MIN_TARGET,
          json.dumps(toggle["box"][2:]))
    check("it keeps the node's white border and rounded corner",
          toggle["border"] == "rgb(255, 255, 255)"
          and toggle["radius"].endswith("px"),
          f'{toggle["border"]} {toggle["radius"]}')

    show_previous(c)
    back = c.eval("""(() => {
      const b = document.querySelector('.cw__back');
      const stage = document.querySelector('.atlas-stage').getBoundingClientRect();
      const r = b.getBoundingClientRect();
      const frame = document.querySelector('.cw__prev-frame')
        .getBoundingClientRect();
      return {tag: b.tagName, type: b.getAttribute('type'),
              name: b.getAttribute('aria-label'),
              text: b.textContent.replace(/\\s+/g, ' ').trim(),
              box: [+(r.left - stage.left).toFixed(1), +(r.top - stage.top).toFixed(1),
                    +r.width.toFixed(1), +r.height.toFixed(1)],
              font: parseFloat(getComputedStyle(b).fontSize),
              insideStage: r.left >= stage.left && r.top >= stage.top
                        && r.right <= stage.right && r.bottom <= stage.bottom,
              clearsFrame: r.bottom <= frame.top + 0.5};
    })()""")
    check("the back control is a real button",
          back["tag"] == "BUTTON" and back["type"] == "button",
          f'{back["tag"]} type={back["type"]}')
    check("its accessible name is 'Back to current design'",
          back["name"] == "Back to current design", back["name"])
    check("its visible label carries the arrow",
          back["text"] == BACK_TEXT, repr(back["text"]))
    check("it sits in the upper left of the slide",
          back["box"][0] < 200 and back["box"][1] < 200, json.dumps(back["box"]))
    check(f"its target is at least {MIN_TARGET}x{MIN_TARGET}",
          back["box"][2] >= MIN_TARGET and back["box"][3] >= MIN_TARGET,
          json.dumps(back["box"][2:]))
    check("it stays inside the rounded slide viewport", back["insideStage"])
    check("it does not overlap the previous design", back["clearsFrame"])

    focus = c.eval("""(() => {
      const style = getComputedStyle(document.querySelector('.cw__back'), ':focus-visible');
      document.querySelector('.cw__back').focus();
      const cs = getComputedStyle(document.querySelector('.cw__back'));
      return {outlineWidth: cs.outlineWidth, outlineStyle: cs.outlineStyle};
    })()""")
    check("the back control has a visible focus ring",
          focus["outlineStyle"] != "none" and focus["outlineWidth"] != "0px",
          json.dumps(focus))


def run_previous_design(c, url):
    print("\n[previous design: Figma 741:19209]")
    go(c, url + f"&slide={SLIDE_INDEX}")
    pin_native_scale(c)
    show_previous(c)

    proto = c.eval("""(() => {
      const mount = document.querySelector('[data-cw-prev-mount]');
      const text = mount.innerText.replace(/\\s+/g, ' ');
      return {children: mount.childElementCount, text: text,
              width: getComputedStyle(mount).width,
              focusable: mount.querySelectorAll(
                'a, button, input, select, textarea,'
                + ' [tabindex]:not([tabindex="-1"])').length,
              hidden: mount.getAttribute('aria-hidden')};
    })()""")
    check("the Create Rate Card prototype was mounted",
          proto["children"] > 0, proto["children"])
    check("it renders at the node's natural 1440 width",
          abs(float(proto["width"].rstrip("px")) - 1440) < 1, proto["width"])
    for phrase in ("Create Rate Card", "CARD details", "LINE details",
                   "CARD", "LINE", "PREM", "Rate Card Name", "Marketplace",
                   "Deal Season", "Base Rate", "Currency"):
        check(f"the previous design shows {phrase!r}", phrase in proto["text"])
    check("nothing inside the prototype is focusable",
          proto["focusable"] == 0, proto["focusable"])
    check("the prototype is not read out as duplicate content",
          proto["hidden"] == "true", proto["hidden"])
    check("no Figma chrome, watermark or editor label came along",
          not any(w in proto["text"] for w in
                  ("Figma", "Hello World", "node-id", "Frame 2134")),
          proto["text"][:100])

    frame = c.eval("""(() => {
      const stage = document.querySelector('.atlas-stage').getBoundingClientRect();
      const f = document.querySelector('.cw__prev-frame').getBoundingClientRect();
      const mount = document.querySelector('[data-cw-prev-mount]')
        .getBoundingClientRect();
      return {inside: f.left >= stage.left - 0.5 && f.top >= stage.top - 0.5
                   && f.right <= stage.right + 0.5 && f.bottom <= stage.bottom + 0.5,
              contained: mount.right <= f.right + 1,
              cropped: mount.bottom > f.bottom,
              overflow: getComputedStyle(
                document.querySelector('.cw__prev-frame')).overflow};
    })()""")
    check("the previous design stays inside the slide", frame["inside"])
    check("it fits the frame horizontally",
          frame["contained"], json.dumps(frame))
    check("the taller page is cropped by the frame, as the node is",
          frame["overflow"] == "hidden" and frame["cropped"], json.dumps(frame))
    c.screenshot(f"{OUT}/previous_1920.png")


def run_toggle(c, url):
    print("\n[toggle and deck isolation]")
    go(c, url + f"&slide={SLIDE_INDEX}")
    check("the default view is the current design", view(c) == CURRENT, view(c))

    before_url = c.eval("location.href")
    res = json.loads(c.eval("""(async () => {
      const wait = ms => new Promise(r => setTimeout(r, ms));
      const cw = () => document.querySelector('[data-connected-workflows]');
      const active = () => document.querySelector(
        '.atlas-slide.is-active').dataset.atlasSlideId;
      const historyBefore = history.length;
      document.querySelector('.cw__toggle').click();
      await wait(500);
      const opened = {view: cw().dataset.cwView, slide: active(),
                      href: location.href, history: history.length,
                      focus: document.activeElement.className,
                      live: cw().querySelector('[data-cw-live]').textContent,
                      curHidden: document.querySelector(
                        '[data-cw-panel="current-design"]').hidden,
                      prevHidden: document.querySelector(
                        '[data-cw-panel="previous-design"]').hidden};
      document.querySelector('.cw__back').click();
      await wait(500);
      const closed = {view: cw().dataset.cwView, slide: active(),
                      href: location.href, history: history.length,
                      focus: document.activeElement.className,
                      live: cw().querySelector('[data-cw-live]').textContent};
      return JSON.stringify({historyBefore, opened, closed});
    })()"""))
    op, cl = res["opened"], res["closed"]
    check("the toggle opens the previous design", op["view"] == PREVIOUS, op["view"])
    check("it does not advance the deck", op["slide"] == SLIDE_ID, op["slide"])
    check("the URL does not change", op["href"] == before_url, op["href"][-40:])
    check("no history entry is pushed",
          op["history"] == res["historyBefore"], op["history"])
    check("focus moves to the back control",
          "cw__back" in (op["focus"] or ""), op["focus"])
    check("the swap is announced once",
          op["live"] == "Previous design displayed", op["live"])
    check("only the previous panel is present",
          op["curHidden"] is True and op["prevHidden"] is False,
          json.dumps({"current": op["curHidden"], "previous": op["prevHidden"]}))

    check("the back control returns to the current design",
          cl["view"] == CURRENT, cl["view"])
    check("it does NOT navigate to the preceding deck slide",
          cl["slide"] == SLIDE_ID, cl["slide"])
    check("the URL is still unchanged", cl["href"] == before_url, cl["href"][-40:])
    check("still no history entry",
          cl["history"] == res["historyBefore"], cl["history"])
    check("focus returns to the Previous design button",
          "cw__toggle" in (cl["focus"] or ""), cl["focus"])
    check("the return is announced once",
          cl["live"] == "Current design displayed", cl["live"])

    # Keyboard. Both controls are real buttons, so Space and Enter
    # activate them natively; what this slide has to guarantee is that
    # the keystroke never also reaches the deck.
    for key, code in ((" ", "Space"), ("Enter", "Enter")):
        for sel, target, expect in ((".cw__toggle", PREVIOUS, "opens"),
                                    (".cw__back", CURRENT, "returns")):
            go(c, url + f"&slide={SLIDE_INDEX}")
            if sel == ".cw__back":
                show_previous(c)
            res = json.loads(c.eval("""(async () => {
              const wait = ms => new Promise(r => setTimeout(r, ms));
              const cw = () => document.querySelector('[data-connected-workflows]');
              const active = () => document.querySelector(
                '.atlas-slide.is-active').dataset.atlasSlideId;
              const button = document.querySelector('%s');
              button.focus();
              const focused = document.activeElement === button;
              /* A real keystroke first: if the deck can see it, the slide
                 changes here and the assertion below catches it. */
              button.dispatchEvent(new KeyboardEvent('keydown',
                {key: %s, bubbles: true, cancelable: true}));
              await wait(250);
              const afterKey = {view: cw().dataset.cwView, slide: active()};
              /* Then the activation the browser would perform itself. */
              button.click();
              await wait(500);
              return JSON.stringify({focused, afterKey,
                view: cw().dataset.cwView, slide: active()});
            })()""" % (sel, json.dumps(key))))
            check(f"{code} can focus {sel}", res["focused"], json.dumps(res))
            check(f"{code} on {sel} never reaches deck navigation",
                  res["afterKey"]["slide"] == SLIDE_ID,
                  json.dumps(res["afterKey"]))
            check(f"activating {sel} {expect} the view without advancing",
                  res["view"] == target and res["slide"] == SLIDE_ID,
                  json.dumps(res))

    # Escape backs out of the comparison.
    go(c, url + f"&slide={SLIDE_INDEX}")
    show_previous(c)
    c.key("Escape", "Escape", 27)
    time.sleep(0.6)
    route = c.eval("document.body.getAttribute('data-route')")
    check("Escape did not leave the presentation", route == "atlas", route)
    if route == "atlas":
        check("Escape returns to the current design", view(c) == CURRENT, view(c))
        check("Escape kept the deck on this slide",
              slide_id(c) == SLIDE_ID, slide_id(c))
    else:
        check("Escape returns to the current design", False, "deck exited")
        check("Escape kept the deck on this slide", False, "deck exited")
        go(c, url + f"&slide={SLIDE_INDEX}")

    # One activation, one state change.
    go(c, url + f"&slide={SLIDE_INDEX}")
    c.eval("""(() => {
      const b = document.querySelector('.cw__toggle');
      b.click(); b.click(); b.click();
    })()""")
    time.sleep(0.6)
    check("rapid clicks change the state only once",
          view(c) == PREVIOUS and slide_id(c) == SLIDE_ID,
          f"view={view(c)} slide={slide_id(c)}")

    go(c, url + f"&slide={SLIDE_INDEX}")
    repeat = json.loads(c.eval("""(async () => {
      const wait = ms => new Promise(r => setTimeout(r, ms));
      const cw = () => document.querySelector('[data-connected-workflows]');
      const active = () => document.querySelector(
        '.atlas-slide.is-active').dataset.atlasSlideId;
      const button = document.querySelector('.cw__toggle');
      button.focus();
      /* A held key: one real press, then auto-repeat. The repeats must
         neither re-toggle nor reach the deck. */
      button.dispatchEvent(new KeyboardEvent('keydown',
        {key: ' ', bubbles: true, cancelable: true}));
      button.click();
      for (let i = 0; i < 6; i += 1) {
        button.dispatchEvent(new KeyboardEvent('keydown',
          {key: ' ', repeat: true, bubbles: true, cancelable: true}));
      }
      await wait(600);
      return JSON.stringify({view: cw().dataset.cwView, slide: active()});
    })()"""))
    check("key repeat cannot toggle back or advance",
          repeat["view"] == PREVIOUS and repeat["slide"] == SLIDE_ID,
          json.dumps(repeat))

    # Clicking the slide itself still belongs to the deck.
    go(c, url + f"&slide={SLIDE_INDEX}")
    c.eval("document.querySelector('.atlas-stage-wrap').click()")
    time.sleep(0.5)
    check("a click elsewhere still advances the deck",
          slide_id(c) == NEXT_SLIDE_ID, slide_id(c))

    # Arrow navigation stays available from either view.
    go(c, url + f"&slide={SLIDE_INDEX}")
    c.key("ArrowRight", "ArrowRight", 39)
    time.sleep(0.4)
    check("ArrowRight advances from the current design",
          slide_id(c) == NEXT_SLIDE_ID, slide_id(c))
    go(c, url + f"&slide={SLIDE_INDEX}")
    show_previous(c)
    c.key("ArrowRight", "ArrowRight", 39)
    time.sleep(0.4)
    check("ArrowRight advances from the previous design too",
          slide_id(c) == NEXT_SLIDE_ID, slide_id(c))


def run_reset(c, url):
    print("\n[reset]")
    go(c, url + f"&slide={SLIDE_INDEX}")
    show_previous(c)
    check("primed on the previous design", view(c) == PREVIOUS, view(c))

    c.key("ArrowRight", "ArrowRight", 39)
    time.sleep(0.5)
    check("leaving the slide resets the view",
          view(c) == CURRENT, view(c))
    check("the live region was cleared",
          c.eval("document.querySelector('[data-cw-live]').textContent") == "")

    c.key("ArrowLeft", "ArrowLeft", 37)
    time.sleep(0.5)
    check("returning lands back on the slide",
          slide_id(c) == SLIDE_ID, slide_id(c))
    check("it opens the current design, not the comparison",
          view(c) == CURRENT, view(c))
    check("the previous panel is hidden again",
          c.eval("document.querySelector('[data-cw-panel=\"previous-design\"]').hidden"))

    c.key("ArrowLeft", "ArrowLeft", 37)
    time.sleep(0.4)
    check("back navigation reaches the preceding slide",
          slide_id(c) == PREV_SLIDE_ID, slide_id(c))

    for _ in range(3):
        c.key("ArrowRight", "ArrowRight", 39)
        time.sleep(0.25)
        c.key("ArrowLeft", "ArrowLeft", 37)
        time.sleep(0.25)
    c.key("ArrowRight", "ArrowRight", 39)
    time.sleep(0.5)
    check("repeated entry and exit still opens the current design",
          slide_id(c) == SLIDE_ID and view(c) == CURRENT,
          f"slide={slide_id(c)} view={view(c)}")
    c.eval("document.querySelector('.cw__toggle').click()")
    time.sleep(0.5)
    check("one gesture is still handled once after repeated visits",
          view(c) == PREVIOUS and slide_id(c) == SLIDE_ID,
          f"view={view(c)} slide={slide_id(c)}")


def run_layout(c, url, label):
    print(f"\n[layout @ {label}]")
    for state, opener in ((CURRENT, None), (PREVIOUS, show_previous)):
        go(c, url + f"&slide={SLIDE_INDEX}")
        if opener:
            opener(c)
        frame = c.eval("""(() => {
          const stage = document.querySelector('.atlas-stage');
          const wrap = document.querySelector('.atlas-stage-wrap');
          const deck = document.querySelector('.atlas-deck');
          const cs = el => getComputedStyle(el);
          const sr = stage.getBoundingClientRect();
          const wr = wrap.getBoundingClientRect();
          const panel = document.querySelector(
            '.cw__view:not([hidden])');
          return {
            radius: cs(stage).borderTopLeftRadius,
            overflow: cs(stage).overflow,
            canvas: cs(deck).backgroundColor,
            slideBg: cs(document.querySelector(
              '.atlas-slide--connected-workflows')).backgroundColor,
            stageBox: [+sr.width.toFixed(1), +sr.height.toFixed(1)],
            pads: [sr.top - wr.top, sr.left - wr.left,
                   wr.right - sr.right, wr.bottom - sr.bottom],
            escaped: [...panel.querySelectorAll(':scope > *')].filter(n => {
              const r = n.getBoundingClientRect();
              if (!r.width && !r.height) return false;
              return r.left < sr.left - 0.5 || r.right > sr.right + 0.5
                  || r.top < sr.top - 0.5 || r.bottom > sr.bottom + 0.5;
            }).map(n => String(n.className)),
            scrolls: document.documentElement.scrollWidth > innerWidth + 1
                  || document.documentElement.scrollHeight > innerHeight + 1,
          };
        })()""")
        check(f"[{state}] the viewport keeps the 40px radius",
              frame["radius"] == f"{STAGE_RADIUS}px", frame["radius"])
        check(f"[{state}] the viewport clips its contents",
              frame["overflow"] == "hidden", frame["overflow"])
        check(f"[{state}] the canvas is grey and the slide stays navy",
              frame["canvas"] == CANVAS and frame["slideBg"] == SLIDE_BG,
              f'{frame["canvas"]} / {frame["slideBg"]}')
        check(f"[{state}] the slide is not flush to the browser edges",
              min(frame["pads"]) >= 24,
              json.dumps([round(p, 1) for p in frame["pads"]]))
        check(f"[{state}] nothing paints outside the rounded frame",
              not frame["escaped"], json.dumps(frame["escaped"]))
        check(f"[{state}] the page does not scroll", not frame["scrolls"])

        if state == CURRENT:
            first_box = frame["stageBox"]
        else:
            check("switching views does not resize the slide",
                  frame["stageBox"] == first_box,
                  f'{first_box} vs {frame["stageBox"]}')

    # The slide's own chrome must clear the floor on screen.
    go(c, url + f"&slide={SLIDE_INDEX}")
    visible = json.loads(c.eval("""JSON.stringify((() => {
      const stage = document.querySelector('.atlas-stage');
      const scale = stage.getBoundingClientRect().width / 1920;
      const out = {};
      document.querySelectorAll(
        '.atlas-slide--connected-workflows .cw__view--current *').forEach(n => {
          if (!n.getClientRects().length) return;
          const direct = [...n.childNodes].some(
            x => x.nodeType === Node.TEXT_NODE && x.textContent.trim());
          if (!direct) return;
          const cls = String(n.className).split(' ')[0] || n.tagName;
          const px = +(parseFloat(getComputedStyle(n).fontSize) * scale).toFixed(1);
          if (!(cls in out) || px < out[cls]) out[cls] = px;
        });
      return {scale: +scale.toFixed(4), sizes: out};
    })())"""))
    below = {k: v for k, v in visible["sizes"].items() if v < CHROME_FLOOR}
    unexpected = {k: v for k, v in below.items() if k not in FIGMA_FIXED}
    check(f"[current] every string outside the Figma-fixed labels clears"
          f" {CHROME_FLOOR:.0f}px on screen (stage scale {visible['scale']})",
          not unexpected, json.dumps(unexpected))
    check("[current] only the Figma-fixed labels ever sit under the floor",
          set(below) <= FIGMA_FIXED, json.dumps(below))

    back_size = c.eval("""(() => {
      const stage = document.querySelector('.atlas-stage');
      const scale = stage.getBoundingClientRect().width / 1920;
      document.querySelector('.cw__toggle').click();
      const px = parseFloat(getComputedStyle(
        document.querySelector('.cw__back')).fontSize) * scale;
      return +px.toFixed(1);
    })()""")
    time.sleep(0.5)
    check(f"[previous] the back control clears {CHROME_FLOOR:.0f}px on screen",
          back_size >= CHROME_FLOOR, back_size)

    # The corner probes ask whether the slide's radius lets the canvas show
    # through. The feedback launcher is a floating app control that sits in
    # the lower-left corner by design, so it has to be out of the frame for
    # that question to be about the frame. It is put back straight after.
    c.eval("""(() => { const b = document.querySelector('.rcf-launch');
      if (b) b.style.visibility = 'hidden'; })()""")
    c.screenshot(f"{OUT}/{label}_previous.png")
    c.eval("""(() => { const b = document.querySelector('.rcf-launch');
      if (b) b.style.visibility = ''; })()""")
    corners = c.eval("""(() => {
      const r = document.querySelector('.atlas-stage').getBoundingClientRect();
      return {l: r.left, t: r.top, w: r.width, h: r.height};
    })()""")
    from PIL import Image
    im = Image.open(f"{OUT}/{label}_previous.png").convert("RGB")
    slide_rgb = tuple(int(v) for v in SLIDE_BG[4:-1].split(","))
    scale = corners["w"] / 1920
    x0, y0 = int(corners["l"]), int(corners["t"])
    x1 = int(corners["l"] + corners["w"]) - 1
    y1 = int(corners["t"] + corners["h"]) - 1

    def inset(nx, ny):
        return (int(corners["l"] + nx * scale), int(corners["t"] + ny * scale))

    for name, (outside, inside_pt) in {
        "top-left": ((x0 + 3, y0 + 3), inset(1500, 40)),
        "top-right": ((x1 - 3, y0 + 3), inset(1884, 40)),
        "bottom-left": ((x0 + 3, y1 - 3), inset(36, 1044)),
        "bottom-right": ((x1 - 3, y1 - 3), inset(1884, 1044)),
    }.items():
        check(f"[previous] {name} corner is rounded away to the canvas",
              is_canvas(im.getpixel(outside))
              and im.getpixel(inside_pt) == slide_rgb,
              f"corner={im.getpixel(outside)} inset={im.getpixel(inside_pt)}")


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
            run_current_design(c, url)
            run_controls(c, url)
            run_previous_design(c, url)
            run_toggle(c, url)
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
                run_layout(c, url, label)
                check(f"no console errors at {label}", not c.logs, json.dumps(c.logs))
            finally:
                proc.kill()
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
