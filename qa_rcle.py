#!/usr/bin/env python3
"""Focused QA for the live Rate Card pricing explainer."""

import base64
import json
import os
import socket
import subprocess
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import websocket


ROOT = "/Users/frances.sun/My Drive/Cursor and Code/Rate Card"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
OUT = "/tmp/rate-card-live-explainer-qa"
VIEWPORTS = [
    (1024, 768),
    (1280, 720),
    (1280, 800),
    (1366, 768),
    (1440, 900),
    (1920, 1080),
]
os.makedirs(OUT, exist_ok=True)


def free_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class StaticHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            path = "/index.html"
        filename = os.path.join(ROOT, path.lstrip("/"))
        if not os.path.isfile(filename):
            self.send_response(404)
            self.end_headers()
            return
        content_type = {
            ".html": "text/html",
            ".css": "text/css",
            ".js": "application/javascript",
            ".svg": "image/svg+xml",
            ".png": "image/png",
            ".json": "application/json",
        }.get(os.path.splitext(filename)[1], "text/plain")
        with open(filename, "rb") as handle:
            payload = handle.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_args):
        return


class CDP:
    def __init__(self, port):
        targets = json.loads(
            urllib.request.urlopen(f"http://127.0.0.1:{port}/json").read()
        )
        target = next(item for item in targets if item["type"] == "page")
        self.ws = websocket.create_connection(
            target["webSocketDebuggerUrl"], timeout=30
        )
        self.message_id = 0

    def send(self, method, params=None):
        self.message_id += 1
        expected = self.message_id
        self.ws.send(json.dumps({
            "id": expected,
            "method": method,
            "params": params or {},
        }))
        while True:
            message = json.loads(self.ws.recv())
            if message.get("id") == expected:
                if "error" in message:
                    raise RuntimeError(f"{method}: {message['error']}")
                return message.get("result", {})

    def eval(self, expression):
        result = self.send("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": True,
        })
        if "exceptionDetails" in result:
            raise RuntimeError(result["exceptionDetails"])
        return result.get("result", {}).get("value")

    def key(self, key, code, virtual_key, modifiers=0):
        for event_type in ("keyDown", "keyUp"):
            self.send("Input.dispatchKeyEvent", {
                "type": event_type,
                "key": key,
                "code": code,
                "windowsVirtualKeyCode": virtual_key,
                "nativeVirtualKeyCode": virtual_key,
                "modifiers": modifiers,
            })

    def screenshot(self, filename):
        result = self.send("Page.captureScreenshot", {"format": "png"})
        with open(filename, "wb") as handle:
            handle.write(base64.b64decode(result["data"]))


RESULTS = []


def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    RESULTS.append({"name": label, "status": status, "detail": detail})
    suffix = f": {detail}" if detail and not condition else ""
    print(f"[{status}] {label}{suffix}")


def wait_for(client, expression, timeout=4):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if client.eval(expression):
            return True
        time.sleep(0.05)
    return False


STATE_EXPRESSION = r"""(() => {
  const root = document.querySelector('[data-v2-root]');
  const activeTab = root.querySelector('[data-v2-tab][aria-selected="true"]');
  const selectedRow = root.querySelector('[data-v2-row-id].is-selected');
  const openAccordion = root.querySelector('[data-v2-accordion].is-open');
  const controls = [...root.querySelectorAll('input, select, textarea')].map(
    (control, index) => ({
      key: `${control.form?.getAttribute('data-v2-form') || 'none'}:${control.name || control.id}:${index}`,
      value: control.value,
      checked: control.checked,
      selectedIndex: control.selectedIndex,
    })
  );
  const scroll = [root, ...root.querySelectorAll('*')]
    .filter(element => element.scrollTop || element.scrollLeft)
    .map(element => ({
      key: element.getAttribute('data-v2-table-region')
        || element.getAttribute('data-v2-accordion')
        || element.className,
      top: element.scrollTop,
      left: element.scrollLeft,
    }));
  return {
    url: location.href,
    activeTab: activeTab?.getAttribute('data-v2-tab') || '',
    selectedRow: selectedRow?.getAttribute('data-v2-row-id') || '',
    openAccordion: openAccordion?.getAttribute('data-v2-accordion') || '',
    controls,
    scroll,
  };
})()"""

LIST_STATE_EXPRESSION = r"""(() => {
  const root = document.querySelector('[data-page="list"]');
  const tableScroll = root.querySelector('.table-scroll');
  return {
    url: location.href,
    search: root.querySelector('[data-action="search"]')?.value || '',
    filters: [...document.querySelectorAll(
      '#filter-panel [data-filter]'
    )].map(element => ({
      key: element.getAttribute('data-filter'),
      value: element.getAttribute('data-value')
        || element.querySelector('input')?.value
        || '',
    })),
    sort: [...root.querySelectorAll('[aria-sort]')].map(element => ({
      key: element.getAttribute('data-sort-key'),
      value: element.getAttribute('aria-sort'),
    })),
    page: root.querySelector('[data-pager] [aria-current="page"]')
      ?.textContent.trim() || '',
    rows: [...root.querySelectorAll('[data-rows] .row')]
      .map(row => row.textContent.replace(/\s+/g, ' ').trim()),
    tableScrollLeft: tableScroll?.scrollLeft || 0,
    windowScroll: [scrollX, scrollY],
  };
})()"""


SLIDE_EXPECTATIONS = [
    {
        # Slide 1 demonstrates the real Edit rate card modal, so no
        # accordion is open behind it: the modal is the editing surface.
        "title": "Edit Rate Card",
        "subtitle": "Update the details shared across the entire rate card.",
        "heading": "Who is this rate card for?",
        "copy": (
            "Shared details identify the buyer, market, and dates for "
            "every price."
        ),
        "badge": "01",
        "accordion": "",
        "tab": "lines",
        "expects_modal": True,
        "field_pairs": [
            ("Buyer", "Who negotiated it"),
            ("Market", "Where it applies"),
            ("Timing", "When it applies"),
        ],
    },
    {
        "title": "Base Rate Details",
        "subtitle": "View existing base rates, or add and edit one price.",
        "heading": "What are we selling?",
        "copy": "Each item connects a sellable product to its negotiated base rate.",
        "badge": "02",
        "accordion": "line",
        "tab": "lines",
        "field_pairs": [
            ("Advertiser", "Who the price is for"),
            ("Product", "What is being sold"),
            ("Price", "How it is charged"),
        ],
    },
    {
        "title": "Price Adjustments",
        "subtitle": "View existing adjustments, or add and edit one rule.",
        "heading": "What changes the base rate?",
        "copy": "An adjustment changes the price only when its condition applies.",
        "badge": "03",
        "accordion": "premium",
        "tab": "premiums",
        "field_pairs": [
            ("Condition", "When it applies"),
            ("Method", "How it changes"),
            ("Value", "How much it changes"),
        ],
    },
]


def snapshot_carousel(client):
    """Read the current slide, indicator, connector, and typography state."""
    return client.eval(r"""(() => {
      const overlay = document.querySelector('[data-rcle]');
      const frame = overlay.querySelector('[data-rcle-product-frame]');
      const panels = [...overlay.querySelectorAll('[data-rcle-slide-panel]')];
      const active = panels.find(panel => !panel.hidden) || null;
      const indicator = overlay.querySelector('[data-rcle-slide-indicator]');
      const prev = overlay.querySelector('[data-rcle-slide-prev]');
      const next = overlay.querySelector('[data-rcle-slide-next]');
      const svg = overlay.querySelector('[data-rcle-callouts]');
      const group = svg.querySelector('[data-rcle-callout="active"]');
      const ring = group?.querySelector('[data-rcle-callout-target]');
      const path = group?.querySelector('[data-rcle-callout-line]');
      const ringSecondary = group?.querySelector(
        '[data-rcle-slide-callout-target-secondary]'
      );
      const pathSecondary = group?.querySelector(
        '[data-rcle-slide-callout-line-secondary]'
      );
      const marker = group?.querySelector('[data-rcle-callout-marker]');
      const number = group?.querySelector('[data-rcle-callout-number]');
      const openAccordion = document.querySelector(
        '[data-v2-accordion].is-open'
      );
      const activeV2Tab = document.querySelector(
        '[data-v2-tab][aria-selected="true"]'
      );
      const rect = element => {
        if (!element) return null;
        const value = element.getBoundingClientRect();
        return {
          left: value.left, top: value.top, right: value.right,
          bottom: value.bottom, width: value.width, height: value.height,
        };
      };
      /* Copy in the HTML source is wrapped across multiple indented
       * lines for readability, so browser textContent contains the
       * source newlines + indent. Normalize whitespace so QA can
       * compare against single-line expected strings. */
      const normalize = value =>
        (value || '').replace(/\s+/g, ' ').trim();
      const fieldPairs = active
        ? [...active.querySelectorAll('.rcle__facts > .rcle__fact')]
          .map(row => [
            normalize(row.querySelector('dt')?.textContent),
            normalize(row.querySelector('dd')?.textContent),
          ])
        : [];
      const partPairs = active
        ? [...active.querySelectorAll('.rcle__slide-parts > div')]
          .map(row => [
            normalize(row.querySelector('dt')?.textContent),
            normalize(row.querySelector('dd')?.textContent),
          ])
        : [];
      const noteTexts = active
        ? [...active.querySelectorAll('.rcle__slide-note')]
          .map(node => normalize(node.textContent))
        : [];
      return {
        title: normalize(overlay.querySelector('#rcle-title').textContent),
        subtitle: normalize(
          overlay.querySelector('#rcle-subtitle').textContent
        ),
        activeIndex: active
          ? Number(active.getAttribute('data-rcle-slide-panel'))
          : 0,
        visiblePanels: panels.filter(panel => !panel.hidden).length,
        panelHiddenFlags: panels.map(panel =>
          panel.hidden || panel.getAttribute('aria-hidden') === 'true'
        ),
        badge: normalize(
          active?.querySelector('.rcle__step')?.textContent
        ),
        heading: normalize(
          active?.querySelector('.rcle__slide-heading')?.textContent
        ),
        copy: normalize(
          active?.querySelector('.rcle__slide-copy')?.textContent
        ),
        fieldPairs,
        partPairs,
        noteTexts,
        indicatorText: indicator?.textContent.trim() || '',
        prevDisabled: !!prev?.disabled,
        nextDisabled: !!next?.disabled,
        activeSlideRect: rect(active),
        frameRect: rect(frame),
        markerRect: rect(marker),
        ringDim: {
          width: Number(ring?.getAttribute('width') || 0),
          height: Number(ring?.getAttribute('height') || 0),
        },
        connectorPath: path?.getAttribute('d') || '',
        connectorNumber: number?.textContent.trim() || '',
        connectorHidden: !!group?.hidden,
        // SVG hidden semantics differ from HTML: check the attribute
        // directly instead of the DOM property so we detect the actual
        // paint state.
        secondaryHidden: !!ringSecondary?.hasAttribute('hidden'),
        secondaryDim: {
          width: Number(ringSecondary?.getAttribute('width') || 0),
          height: Number(ringSecondary?.getAttribute('height') || 0),
        },
        secondaryPath: pathSecondary?.getAttribute('d') || '',
        secondaryRect: rect(ringSecondary),
        activeTabName: activeV2Tab?.getAttribute('data-v2-tab') || '',
        openAccordion: openAccordion?.getAttribute('data-v2-accordion') || '',
        undersized: [...overlay.querySelectorAll('*')]
          .filter(element => {
            if (element.closest('[hidden]')
                || !element.getClientRects().length) return false;
            const directText = [...element.childNodes].some(node =>
              node.nodeType === Node.TEXT_NODE
              && node.textContent.trim()
            );
            const textControl = element.matches(
              'input, textarea, select, option'
            );
            return (directText || textControl)
              && parseFloat(getComputedStyle(element).fontSize) < 14;
          })
          .map(element => ({
            tag: element.tagName,
            className: String(element.className || ''),
            text: element.textContent.trim().slice(0, 80),
            size: getComputedStyle(element).fontSize,
          })),
        cardModalOpen: (() => {
          const m = document.querySelector('[data-rc-create-modal]');
          return !!(m && !m.hidden);
        })(),
        cardModalTitle: (() => {
          const m = document.querySelector('[data-rc-create-modal]');
          return m && !m.hidden
            ? m.querySelector('.modal__title').textContent.trim() : null;
        })(),
        // The modal has to be inside the live product frame, not the
        // body-level position it takes outside presentation mode.
        cardModalInFrame: (() => {
          const m = document.querySelector('[data-rc-create-modal]');
          const frame = document.querySelector('[data-rcle-product-frame]');
          if (!m || m.hidden || !frame) return false;
          const panel = m.querySelector('.modal__panel');
          const p = panel.getBoundingClientRect();
          const f = frame.getBoundingClientRect();
          return frame.contains(m)
            && p.left >= f.left - 2 && p.right <= f.right + 2
            && p.top >= f.top - 2 && p.bottom <= f.bottom + 2;
        })(),
        slideUndersized: (() => {
          if (!active) return [];
          const isCallout = element =>
            element.closest('[data-rcle-callouts]');
          const isStepNumeral = element =>
            element.classList.contains('rcle__step');
          return [...active.querySelectorAll('*')]
            .concat(active)
            .filter(element => {
              if (element.closest('[hidden]')
                  || !element.getClientRects().length
                  || isCallout(element)
                  || isStepNumeral(element)) return false;
              const directText = [...element.childNodes].some(node =>
                node.nodeType === Node.TEXT_NODE
                && node.textContent.trim()
              );
              if (!directText) return false;
              return parseFloat(getComputedStyle(element).fontSize) < 16;
            })
            .map(element => ({
              tag: element.tagName,
              className: String(element.className || ''),
              text: element.textContent.trim().slice(0, 80),
              size: getComputedStyle(element).fontSize,
            }));
        })(),
        indicatorFontSize: indicator
          ? parseFloat(getComputedStyle(indicator).fontSize)
          : 0,
        titleFontSize: parseFloat(
          getComputedStyle(overlay.querySelector('#rcle-title')).fontSize
        ),
        subtitleFontSize: parseFloat(
          getComputedStyle(overlay.querySelector('#rcle-subtitle')).fontSize
        ),
        removedElements: overlay.querySelectorAll(
          '.rcle__closing, [data-rcle-layer-card], [data-rcle-callout="1"], '
          + '[data-rcle-callout="2"], [data-rcle-callout="3"]'
        ).length,
      };
    })()""")


def run_exploded_checks(client, label, width, height, baseline):
    time.sleep(0.25)
    shell = client.eval(r"""(() => {
      const overlay = document.querySelector('[data-rcle]');
      const frame = overlay.querySelector('[data-rcle-product-frame]');
      const source = overlay.querySelector('.rcle__product-source');
      const carousel = overlay.querySelector('[data-rcle-carousel]');
      const root = document.querySelector('[data-v2-root]');
      const rect = element => {
        const value = element.getBoundingClientRect();
        return {
          left: value.left, top: value.top, right: value.right,
          bottom: value.bottom, width: value.width, height: value.height,
        };
      };
      return {
        overlay: rect(overlay),
        frame: rect(frame),
        source: rect(source),
        carousel: rect(carousel),
        rootInSlot: root.parentElement.matches('[data-rcle-live-slot]'),
        sameRoot: root === window.__rcleQaRoot,
        rootInert: root.inert,
scrimHasHole: (() => {
          const scrim = document.querySelector('[data-rcle-scrim]');
          if (!scrim) return false;
          const d = scrim.getAttribute('d') || '';
          return (d.match(/M /g) || []).length === 2;
        })(),
                rootOpacity: Number(getComputedStyle(root).opacity),
        pageOverflow:
          document.documentElement.scrollWidth > innerWidth + 1
          || document.documentElement.scrollHeight > innerHeight + 1,
        duplicateIds: (() => {
          const ids = [...overlay.querySelectorAll('[id]')]
            .map(element => element.id);
          return [...new Set(
            ids.filter((id, index) => ids.indexOf(id) !== index)
          )];
        })(),
        productScrollOwned:
          getComputedStyle(
            overlay.querySelector('[data-rcle-product-viewport]')
          ).overflow === 'auto',
      };
    })()""")
    frame_rect = shell["frame"]
    carousel_rect = shell["carousel"]
    check(
        f"{label} full-screen carousel shell fits",
        shell["overlay"]["width"] == width
        and shell["overlay"]["height"] == height
        and frame_rect["left"] >= 0
        and frame_rect["top"] >= 0
        and frame_rect["right"] <= width + 1
        and frame_rect["bottom"] <= height + 1
        and carousel_rect["left"] >= 0
        and carousel_rect["right"] <= width + 1
        and carousel_rect["width"] > 0,
        str(shell),
    )
    check(
        f"{label} product keeps ~2/3 of the diagram width",
        shell["source"]["width"] > shell["carousel"]["width"] * 1.55
        and shell["source"]["right"] < shell["carousel"]["left"],
        str({
            "source": shell["source"],
            "carousel": shell["carousel"],
        }),
    )
    # The product root is no longer dimmed as a whole. A spotlight scrim
    # painted over the frame de-emphasises everything except the region
    # being explained, which is what lets that region stay at full
    # opacity: CSS opacity on the root would cap its children with it.
    check(
        f"{label} same live root is reparented and spotlit",
        shell["sameRoot"]
        and shell["rootInSlot"]
        and shell["rootInert"]
        and shell["rootOpacity"] == 1
        and shell["scrimHasHole"],
        str(shell),
    )
    check(
        f"{label} shell has no page overflow",
        not shell["pageOverflow"]
        and shell["productScrollOwned"]
        and not shell["duplicateIds"],
        str(shell),
    )

    def press(key, code, virtual_key):
        client.key(key, code, virtual_key)
        time.sleep(0.25)

    def click_selector(selector):
        client.eval(f"document.querySelector({selector!r}).click()")
        time.sleep(0.25)

    def verify_slide(state, slide_number, method):
        expected = SLIDE_EXPECTATIONS[slide_number - 1]
        pairs_ok = state["fieldPairs"] == [
            list(pair) for pair in expected["field_pairs"]
        ]
        parts_ok = state["partPairs"] == []
        indicator_ok = state["indicatorText"] == f"{slide_number} of 3"
        prev_ok = state["prevDisabled"] == (slide_number == 1)
        next_ok = state["nextDisabled"] == (slide_number == 3)
        connector_measured = (
            not state["connectorHidden"]
            and state["ringDim"]["width"] > 0
            and state["ringDim"]["height"] > 0
            and state["connectorPath"].startswith("M ")
        )
        # The numbered circle that used to float in the gutter is gone:
        # the step number lives in the copy, and a second numeral beside
        # it only competed for the same job.
        marker = state["markerRect"]
        marker_hidden = not marker or marker["width"] == 0
        text_at_16 = not state["slideUndersized"]
        check(
            f"{label} slide {slide_number} via {method} shows only itself",
            state["activeIndex"] == slide_number
            and state["visiblePanels"] == 1
            and state["title"] == expected["title"]
            and state["subtitle"] == expected["subtitle"]
            and state["badge"] == expected["badge"]
            and state["heading"] == expected["heading"]
            and state["copy"] == expected["copy"]
            and pairs_ok
            and parts_ok,
            str(state),
        )
        check(
            f"{label} slide {slide_number} carousel controls in sync",
            indicator_ok and prev_ok and next_ok,
            str({
                "indicator": state["indicatorText"],
                "prevDisabled": state["prevDisabled"],
                "nextDisabled": state["nextDisabled"],
            }),
        )
        if expected.get("expects_modal"):
            check(
                f"{label} slide {slide_number} opens the live Edit rate card modal",
                state["cardModalOpen"]
                and state["cardModalTitle"] == "Edit rate card"
                and state["cardModalInFrame"]
                and not state["openAccordion"],
                str(state),
            )
        else:
            check(
                f"{label} slide {slide_number} live accordion matches",
                state["openAccordion"] == expected["accordion"],
                str(state),
            )
        check(
            f"{label} slide {slide_number} live tab matches",
            state["activeTabName"] == expected["tab"],
            str({
                "activeTabName": state["activeTabName"],
                "expected": expected["tab"],
            }),
        )
        check(
            f"{label} slide {slide_number} primary red callout is measured",
            connector_measured and marker_hidden,
            str(state),
        )
        # Every slide annotates exactly one region. Ringing the table as
        # well as the form pointed at two things at once and buried the
        # single idea each slide is supposed to carry.
        check(
            f"{label} slide {slide_number} has no secondary callout",
            state["secondaryHidden"],
            str(state),
        )
        check(
            f"{label} slide {slide_number} explanation text is at least 16px",
            text_at_16,
            str(state["slideUndersized"]),
        )

    # Slide 1: default state after open().
    state1 = snapshot_carousel(client)
    check(
        f"{label} title and subtitle sizes meet the presentation floor",
        state1["titleFontSize"] >= 28
        and state1["subtitleFontSize"] >= 16
        and state1["indicatorFontSize"] >= 16,
        str(state1),
    )
    check(
        f"{label} old three-card artifacts are removed",
        state1["removedElements"] == 0,
        str(state1),
    )
    check(
        f"{label} all visible explainer text is at least 14px",
        not state1["undersized"],
        str(state1["undersized"]),
    )
    verify_slide(state1, 1, "initial")
    if width in (1024, 1920):
        client.screenshot(
            os.path.join(OUT, f"rcle-carousel-slide1-{label}.png")
        )

    # Slide 2: press Right arrow to advance.
    press("ArrowRight", "ArrowRight", 39)
    state2 = snapshot_carousel(client)
    verify_slide(state2, 2, "ArrowRight")
    if width in (1024, 1920):
        client.screenshot(
            os.path.join(OUT, f"rcle-carousel-slide2-{label}.png")
        )

    # Slide 3: click the next button.
    click_selector("[data-rcle-slide-next]")
    state3 = snapshot_carousel(client)
    verify_slide(state3, 3, "next-button")
    if width in (1024, 1920):
        client.screenshot(
            os.path.join(OUT, f"rcle-carousel-slide3-{label}.png")
        )

    # Attempt to over-advance: next button must stay disabled.
    over_advance = client.eval(r"""(() => {
      const btn = document.querySelector('[data-rcle-slide-next]');
      btn.click();
      const active = document.querySelector(
        '[data-rcle-slide-panel]:not([hidden])'
      );
      return {
        disabled: !!btn.disabled,
        stillOnLast: active?.getAttribute('data-rcle-slide-panel') === '3',
      };
    })()""")
    check(
        f"{label} next arrow is inert on the last slide",
        over_advance["disabled"] and over_advance["stillOnLast"],
        str(over_advance),
    )

    # Back to slide 2 via Left arrow, then to slide 1 via prev button.
    press("ArrowLeft", "ArrowLeft", 37)
    state_back2 = snapshot_carousel(client)
    verify_slide(state_back2, 2, "ArrowLeft")
    click_selector("[data-rcle-slide-prev]")
    state_back1 = snapshot_carousel(client)
    verify_slide(state_back1, 1, "prev-button")

    over_reverse = client.eval(r"""(() => {
      const btn = document.querySelector('[data-rcle-slide-prev]');
      btn.click();
      const active = document.querySelector(
        '[data-rcle-slide-panel]:not([hidden])'
      );
      return {
        disabled: !!btn.disabled,
        stillOnFirst: active?.getAttribute('data-rcle-slide-panel') === '1',
      };
    })()""")
    check(
        f"{label} prev arrow is inert on the first slide",
        over_reverse["disabled"] and over_reverse["stillOnFirst"],
        str(over_reverse),
    )

    # 2026-08-04 previous-design view. Navigate to slide 2 first so we
    # can prove the carousel returns to the same slide after the swap.
    press("ArrowRight", "ArrowRight", 39)
    press("ArrowRight", "ArrowRight", 39)
    prep = snapshot_carousel(client)
    check(
        f"{label} carousel parked on slide 3 before opening previous design",
        prep["activeIndex"] == 3,
        str(prep),
    )

    toggle_baseline = client.eval(r"""(() => {
      const overlay = document.querySelector('[data-rcle]');
      const toggle = overlay.querySelector('[data-rcle-view-toggle]');
      const previous = overlay.querySelector('[data-rcle-previous-view]');
      const current = overlay.querySelector('.rcle__diagram');
      const nav = overlay.querySelector('[data-rcle-carousel-nav]');
      const style = toggle && getComputedStyle(toggle);
      const close = overlay.querySelector('[data-rcle-close]');
      const toggleRect = toggle && toggle.getBoundingClientRect();
      const closeRect = close && close.getBoundingClientRect();
      return {
        toggleExists: !!toggle,
        toggleLabel: toggle && toggle.textContent.trim(),
        toggleVisible:
          !!toggle && toggle.getClientRects().length > 0 && !toggle.hidden,
        toggleFontSize: style ? parseFloat(style.fontSize) : 0,
        toggleAriaPressed: toggle && toggle.getAttribute('aria-pressed'),
        gapToClose:
          toggleRect && closeRect ? closeRect.left - toggleRect.right : 0,
        previousHidden: previous ? previous.hidden : true,
        currentHidden: current ? current.hidden : false,
        navHidden: nav ? nav.hidden : false,
      };
    })()""")
    check(
        f"{label} 'Previous design' toggle present, quiet, min-16px label",
        (
            toggle_baseline["toggleExists"]
            and toggle_baseline["toggleVisible"]
            and toggle_baseline["toggleLabel"] == "Previous design"
            and toggle_baseline["toggleFontSize"] >= 16
            and toggle_baseline["toggleAriaPressed"] == "false"
            and 12 <= toggle_baseline["gapToClose"] <= 20
            and toggle_baseline["previousHidden"]
            and not toggle_baseline["currentHidden"]
        ),
        json.dumps(toggle_baseline),
    )

    click_selector("[data-rcle-view-toggle]")
    time.sleep(0.35)

    previous_state = client.eval(r"""(() => {
      const overlay = document.querySelector('[data-rcle]');
      const toggle = overlay.querySelector('[data-rcle-view-toggle]');
      const title = overlay.querySelector('#rcle-title');
      const subtitle = overlay.querySelector('#rcle-subtitle');
      const previous = overlay.querySelector('[data-rcle-previous-view]');
      const current = overlay.querySelector('.rcle__diagram');
      const nav = overlay.querySelector('[data-rcle-carousel-nav]');
      const prototype = overlay.querySelector('[data-rcle-previous-prototype]');
      const frame = overlay.querySelector('[data-rcle-previous-frame]');
      const norm = (text) => (text || '')
        .replace(/\s+/g, ' ')
        .trim();
      const titleStyle = getComputedStyle(title);
      const subtitleStyle = getComputedStyle(subtitle);
      const cards = prototype
        ? Array.from(prototype.querySelectorAll('.prev-card__title'))
            .map((h) => norm(h.textContent))
        : [];
      const stepChips = prototype
        ? Array.from(prototype.querySelectorAll('.prev-step__label'))
            .map((s) => norm(s.textContent))
        : [];
      const buttons = prototype
        ? Array.from(prototype.querySelectorAll('.prev-btn'))
            .map((b) => norm(b.textContent))
        : [];
      const scale = prototype
        ? parseFloat(
            prototype.style.getPropertyValue('--rcle-prev-scale') || '1'
          )
        : 0;
      const frameRect = frame ? frame.getBoundingClientRect() : null;
      const prototypeRect = prototype ? prototype.getBoundingClientRect() : null;
      return {
        overlayView: overlay.getAttribute('data-rcle-view'),
        previousHidden: previous.hidden,
        currentHidden: current.hidden,
        navHidden: nav.hidden,
        toggleLabel: norm(toggle.textContent),
        toggleAriaPressed: toggle.getAttribute('aria-pressed'),
        toggleTarget: toggle.getAttribute('data-rcle-target-view'),
        title: norm(title.textContent),
        titleFontSize: parseFloat(titleStyle.fontSize),
        subtitle: norm(subtitle.textContent),
        subtitleFontSize: parseFloat(subtitleStyle.fontSize),
        cards,
        stepChips,
        buttons,
        scale,
        prototypeFitsFrame:
          !!frameRect && !!prototypeRect
          && prototypeRect.left >= frameRect.left - 1
          && prototypeRect.right <= frameRect.right + 1,
      };
    })()""")

    expected_supporting = (
        "The original concept used a fixed three-step flow, but rate-card"
        " work is not always linear. Users need to move back and forth"
        " between the shared rate-card context, individual base rates,"
        " and premiums to confirm how the negotiated rate applies."
    )
    check(
        f"{label} previous view swaps in with correct header and toggle",
        (
            previous_state["overlayView"] == "previous"
            and not previous_state["previousHidden"]
            and previous_state["currentHidden"]
            and previous_state["navHidden"]
            and previous_state["title"] == "Previous Design"
            and 28 <= previous_state["titleFontSize"] <= 34
            and previous_state["subtitle"] == expected_supporting
            and previous_state["subtitleFontSize"] >= 16
            and previous_state["toggleLabel"] == "Current design"
            and previous_state["toggleAriaPressed"] == "true"
            and previous_state["toggleTarget"] == "current"
        ),
        json.dumps(previous_state),
    )
    check(
        f"{label} previous prototype renders CARD/LINE/PREM sections",
        (
            previous_state["cards"] == ["CARD details", "LINE details", "PREM details"]
            and previous_state["stepChips"] == ["CARD", "LINE", "PREM"]
            and "Save as Draft" in previous_state["buttons"]
            and "Save and Create New LINE" in previous_state["buttons"]
            and "Save and Continue to PREM" in previous_state["buttons"]
        ),
        json.dumps(previous_state),
    )
    check(
        f"{label} previous prototype is proportionally scaled to fit",
        previous_state["scale"] > 0
        and previous_state["scale"] <= 1.001
        and previous_state["prototypeFitsFrame"],
        json.dumps(previous_state),
    )

    # Figma-fidelity checks on the rebuilt prototype: exact copy, exact
    # asset loading, exact stepper state, and no scrollbar overlap with
    # the profile control. These prevent silent regressions when the
    # historical previous-design prototype is edited in the future.
    figma_state = client.eval(r"""(() => {
      const overlay = document.querySelector('[data-rcle]');
      const proto = overlay.querySelector('[data-rcle-previous-prototype]');
      const frame = overlay.querySelector('[data-rcle-previous-frame]');
      if (!proto || !frame) return null;
      const norm = (text) => (text || '').replace(/\s+/g, ' ').trim();
      const logo = proto.querySelector('.prev-nav__logo');
      const avatar = proto.querySelector('.prev-nav__avatar img');
      const bell = proto.querySelector('.prev-nav__bell img');
      const navItems = Array.from(
        proto.querySelectorAll('.prev-nav__item')
      ).map((n) => norm(n.textContent));
      const currentNav = norm(
        (proto.querySelector('.prev-nav__item--current') || {}).textContent
      );
      const activeStepNum = proto.querySelector('.prev-step__num--active');
      const activeChip = proto.querySelector('.prev-step__chip--active');
      const dealSeason = norm(
        (proto.querySelectorAll('.prev-input__value')[0] || {}).textContent
      );
      const values = Array.from(
        proto.querySelectorAll('.prev-input__value')
      ).map((v) => norm(v.textContent));
      const fieldLabels = Array.from(
        proto.querySelectorAll('.prev-field__label')
      ).map((l) => norm(l.textContent));
      const avatarRect = avatar ? avatar.getBoundingClientRect() : null;
      const frameRect = frame.getBoundingClientRect();
      const avatarClearOfScrollbar = avatarRect
        ? avatarRect.right <= frameRect.right - 8
        : false;
      return {
        logoLoaded: !!logo && logo.complete && logo.naturalWidth > 0,
        avatarLoaded: !!avatar && avatar.complete && avatar.naturalWidth > 0,
        bellLoaded: !!bell && bell.complete && bell.naturalWidth > 0,
        navItems,
        currentNav,
        activeStepIsOne: !!activeStepNum &&
          activeStepNum.textContent.trim() === '1',
        activeChipLabel: activeChip ? norm(activeChip.textContent) : null,
        dealSeason,
        seededValues: values,
        rateCardNameLabel: fieldLabels[0] || null,
        marketplacePlaceholder: norm(
          (proto.querySelectorAll('.prev-input__placeholder')[3] || {})
            .textContent
        ),
        avatarClearOfScrollbar,
      };
    })()""")
    check(
        f"{label} previous prototype loads Figma nav assets (logo, avatar, bell)",
        figma_state
        and figma_state["logoLoaded"]
        and figma_state["avatarLoaded"]
        and figma_state["bellLoaded"],
        json.dumps(figma_state),
    )
    check(
        f"{label} previous prototype nav shows Sales/Planning/Ad Ops/Billing/Admin (Admin current)",
        figma_state
        and figma_state["navItems"] == [
            "Sales", "Planning", "Ad Ops", "Billing", "Admin",
        ]
        and figma_state["currentNav"] == "Admin",
        json.dumps(figma_state),
    )
    check(
        f"{label} previous prototype stepper is on step 1 (CARD active, 1 CARD chip)",
        figma_state
        and figma_state["activeStepIsOne"]
        and figma_state["activeChipLabel"] == "1 CARD",
        json.dumps(figma_state),
    )
    check(
        f"{label} previous prototype preserves seeded Figma values (25-26, CPM, USD)",
        figma_state
        and figma_state["seededValues"] == ["25-26", "CPM", "USD"],
        json.dumps(figma_state),
    )
    check(
        f"{label} previous prototype scrollbar does not overlap the profile control",
        figma_state and figma_state["avatarClearOfScrollbar"],
        json.dumps(figma_state),
    )

    if width in (1440, 1920):
        client.screenshot(
            os.path.join(OUT, f"rcle-previous-design-{label}.png")
        )

    # Swap back to current -> should land on the same slide (3) that we
    # parked on before opening the previous view.
    click_selector("[data-rcle-view-toggle]")
    time.sleep(0.35)
    back_state = snapshot_carousel(client)
    check(
        f"{label} 'Current design' returns to the last-viewed carousel slide",
        (
            back_state["activeIndex"] == 3
            and back_state["title"] == "Price Adjustments"
            and back_state["visiblePanels"] == 1
        ),
        json.dumps({
            "activeIndex": back_state["activeIndex"],
            "title": back_state["title"],
            "visiblePanels": back_state["visiblePanels"],
        }),
    )

    # Reset back to slide 1 so the Escape/restore checks match the
    # baseline the state expression captured at open time.
    click_selector("[data-rcle-slide-prev]")
    time.sleep(0.2)
    click_selector("[data-rcle-slide-prev]")
    time.sleep(0.2)

    client.key("Escape", "Escape", 27)
    closed = wait_for(client, "document.querySelector('[data-rcle]').hidden")
    restored = client.eval(STATE_EXPRESSION)
    root_restored = client.eval(r"""(() => {
      const root = document.querySelector('[data-v2-root]');
      return root === window.__rcleQaRoot
        && root.parentNode === window.__rcleQaParent
        && root.previousSibling === window.__rcleQaPrevious
        && document.activeElement === window.__rcleQaFocus
        && !document.body.classList.contains('rcle-open')
        && !root.inert
        && !root.querySelector('[id^="rcle-"]');
    })()""")
    check(f"{label} Escape closes explainer", closed)
    check(
        f"{label} route, tab, row, accordion, fields, and scroll restore",
        restored == baseline,
        json.dumps({"before": baseline, "after": restored}),
    )
    check(f"{label} root position and focus restore", root_restored)


def run_viewport(client, base_url, width, height):
    label = f"{width}x{height}"
    print(f"\n== {label} ==")
    client.send("Emulation.setDeviceMetricsOverride", {
        "width": width,
        "height": height,
        "deviceScaleFactor": 1,
        "mobile": False,
    })
    client.send("Page.navigate", {
        "url": (
            f"{base_url}/?section=create&mode=edit"
            "&cardId=RC-2026-UPFRONT-001&version=2.0"
        )
    })
    loaded = wait_for(
        client,
        "document.body?.dataset.route === 'create' && "
        "!document.querySelector('[data-v2-root]')?.hidden",
    )
    check(f"{label} edit route loads", loaded)
    time.sleep(0.25)

    client.eval("""(() => {
      const root = document.querySelector('[data-v2-root]');
      const tableScroll = root.querySelector('.create-md__table-scroll');
      const detail = root.querySelector('.create-md__detail');
      if (tableScroll) tableScroll.scrollLeft = Math.min(36, tableScroll.scrollWidth);
      if (detail) detail.scrollTop = Math.min(18, detail.scrollHeight);
      window.__rcleQaRoot = root;
      window.__rcleQaParent = root.parentNode;
      window.__rcleQaPrevious = root.previousSibling;
      window.__rcleQaFocus = root.querySelector('[data-v2-tab="lines"]');
      window.__rcleQaFocus?.focus();
    })()""")
    baseline = client.eval(STATE_EXPRESSION)
    client.key("p", "KeyP", 80, modifiers=4)
    opened = wait_for(client, "!document.querySelector('[data-rcle]').hidden")
    check(f"{label} Cmd+P opens explainer", opened)
    time.sleep(0.2)

    if client.eval(
        "document.querySelector('[data-rcle]')"
        ".hasAttribute('data-rcle-exploded')"
    ):
        run_exploded_checks(client, label, width, height, baseline)
        return

    geometry = client.eval("""(() => {
      const overlay = document.querySelector('[data-rcle]');
      const panel = overlay.querySelector('.rcle__panel');
      const frame = overlay.querySelector('[data-rcle-product-frame]');
      const explanation = overlay.querySelector('.rcle__explanation');
      const root = document.querySelector('[data-v2-root]');
      const rect = element => {
        const value = element.getBoundingClientRect();
        return {
          left: value.left, top: value.top, right: value.right,
          bottom: value.bottom, width: value.width, height: value.height,
        };
      };
      return {
        overlay: rect(overlay),
        panel: rect(panel),
        frame: rect(frame),
        explanation: rect(explanation),
        rootInSlot: root.parentElement.matches('[data-rcle-live-slot]'),
        sameRoot: root === window.__rcleQaRoot,
        pageOverflow:
          document.documentElement.scrollWidth > innerWidth + 1
          || document.documentElement.scrollHeight > innerHeight + 1,
        duplicateIds: (() => {
          const ids = [...overlay.querySelectorAll('[id]')]
            .map(element => element.id);
          return [...new Set(
            ids.filter((id, index) => ids.indexOf(id) !== index)
          )];
        })(),
        productScrollOwned:
          getComputedStyle(
            overlay.querySelector('[data-rcle-product-viewport]')
          ).overflow === 'auto',
        title: overlay.querySelector('#rcle-title').textContent,
        subtitle: overlay.querySelector('#rcle-subtitle').textContent,
      };
    })()""")
    frame = geometry["frame"]
    fits = (
        geometry["overlay"]["width"] == width
        and geometry["overlay"]["height"] == height
        and frame["left"] >= 0
        and frame["top"] >= 0
        and frame["right"] <= width + 1
        and frame["bottom"] <= height + 1
        and frame["width"] >= 620
        and frame["height"] >= 430
    )
    check(f"{label} full-screen shell and product frame fit", fits, str(geometry))
    check(
        f"{label} same live root is reparented",
        geometry["sameRoot"] and geometry["rootInSlot"],
    )
    check(
        f"{label} shell has no page overflow",
        not geometry["pageOverflow"] and geometry["productScrollOwned"],
    )
    check(
        f"{label} global explainer copy is exact",
        geometry["title"] == "Rate Card Pricing Layers"
        and geometry["subtitle"]
        == "RCM organizes negotiated pricing into three connected layers.",
    )

    client.eval(
        "document.querySelector('[data-rcle-layer-option=\"line\"]').click()"
    )
    wait_for(
        client,
        "document.querySelector('[data-rcle]').dataset.rcleLayer === 'line'",
    )
    time.sleep(0.2)
    line = client.eval("""(() => {
      const overlay = document.querySelector('[data-rcle]');
      const panelRect = overlay.querySelector('.rcle__panel').getBoundingClientRect();
      const frameRect = overlay.querySelector('[data-rcle-product-frame]').getBoundingClientRect();
      const svg = overlay.querySelector('[data-rcle-callouts]');
      const groups = [...svg.querySelectorAll('[data-rcle-callout]')];
      const labels = [...overlay.querySelectorAll('[data-rcle-callout-label]')];
      const firstRow = document.querySelector(
        '[data-v2-tbody="lines"] [data-v2-row-id]'
      );
      firstRow?.click();
      const labelOutsideProduct = labels.every(label => {
        const rect = label.getBoundingClientRect();
        return rect.right <= frameRect.left;
      });
      return {
        layer: overlay.dataset.rcleLayer,
        tab: document.querySelector(
          '[data-v2-tab][aria-selected="true"]'
        )?.dataset.v2Tab,
        copy: overlay.querySelector('[data-rcle-section-title]').textContent,
        legendVisible: !overlay.querySelector(
          '[data-rcle-callout-legend]'
        ).hidden,
        svgVisible: !svg.hidden,
        visibleGroups: groups.filter(group => !group.hidden).length,
        targets: groups.map(group => {
          const rect = group.querySelector('[data-rcle-callout-target]');
          return {
            width: Number(rect.getAttribute('width') || 0),
            height: Number(rect.getAttribute('height') || 0),
          };
        }),
        labelOutsideProduct,
        svgMatchesPanel:
          Number(svg.getAttribute('width')) === Math.round(panelRect.width)
          && Number(svg.getAttribute('height')) === Math.round(panelRect.height),
      };
    })()""")
    time.sleep(0.2)
    line_after_layout = client.eval("""(() => {
      const svg = document.querySelector('[data-rcle-callouts]');
      const groups = [...svg.querySelectorAll('[data-rcle-callout]')];
      return {
        visibleGroups: groups.filter(group => !group.hidden).length,
        targets: groups.map(group => {
          const rect = group.querySelector('[data-rcle-callout-target]');
          return Number(rect.getAttribute('width') || 0) > 0
            && Number(rect.getAttribute('height') || 0) > 0;
        }),
        selected: !!document.querySelector(
          '[data-v2-tbody="lines"] [data-v2-row-id].is-selected'
        ),
        lineAccordion: document.querySelector(
          '[data-v2-accordion="line"]'
        ).classList.contains('is-open'),
        sortIconsCompact: [...document.querySelectorAll(
          '.create-md__table .th__sort'
        )].every(icon => {
          const rect = icon.getBoundingClientRect();
          return rect.width <= 17 && rect.height <= 17;
        }),
        markersAvoidControls: (() => {
          const controls = [...document.querySelectorAll(
            '[data-v2-root] button, [data-v2-root] input, '
            + '[data-v2-root] select, [data-v2-root] textarea, '
            + '[data-v2-root] td, [data-v2-root] th'
          )].map(element => element.getBoundingClientRect());
          return [...svg.querySelectorAll('[data-rcle-callout-marker]')]
            .filter(marker => !marker.closest('[data-rcle-callout]').hidden)
            .every(marker => {
              const rect = marker.getBoundingClientRect();
              return controls.every(control =>
                rect.right <= control.left
                || rect.left >= control.right
                || rect.bottom <= control.top
                || rect.top >= control.bottom
              );
            });
        })(),
      };
    })()""")
    check(
        f"{label} Line Items selector drives live UI and copy",
        line["layer"] == "line"
        and line["tab"] == "lines"
        and line["copy"] == "Line Items"
        and line["legendVisible"],
        str(line),
    )
    check(
        f"{label} LINE callouts are measured and labels avoid product data",
        line["svgVisible"]
        and line["labelOutsideProduct"]
        and line["svgMatchesPanel"]
        and line_after_layout["visibleGroups"] == 3
        and all(line_after_layout["targets"]),
        str(line_after_layout),
    )
    check(
        f"{label} live table sort icons remain compact",
        line_after_layout["sortIconsCompact"],
    )
    check(
        f"{label} callout markers avoid data and controls",
        line_after_layout["markersAvoidControls"],
        str(line_after_layout),
    )
    check(
        f"{label} selected row synchronizes Line details",
        line_after_layout["selected"] and line_after_layout["lineAccordion"],
    )
    if width in (1024, 1920):
        client.screenshot(os.path.join(OUT, f"rcle-open-line-{label}.png"))

    client.eval(
        "document.querySelector('[data-rcle-layer-option=\"premium\"]').click()"
    )
    time.sleep(0.2)
    premium = client.eval("""(() => {
      const overlay = document.querySelector('[data-rcle]');
      return {
        layer: overlay.dataset.rcleLayer,
        tab: document.querySelector(
          '[data-v2-tab][aria-selected="true"]'
        )?.dataset.v2Tab,
        copy: overlay.querySelector('[data-rcle-section-title]').textContent,
        calloutsHidden: overlay.querySelector('[data-rcle-callouts]').hidden,
      };
    })()""")
    check(
        f"{label} Premium selector synchronizes and removes LINE callouts",
        premium["layer"] == "premium"
        and premium["tab"] == "premiums"
        and premium["copy"] == "Premium Adjustments"
        and premium["calloutsHidden"],
        str(premium),
    )

    client.eval(
        "document.querySelector('[data-v2-tab=\"lines\"]').click()"
    )
    time.sleep(0.15)
    check(
        f"{label} direct live tab updates explanation",
        client.eval(
            "document.querySelector('[data-rcle]').dataset.rcleLayer === 'line'"
        ),
    )

    client.key("Escape", "Escape", 27)
    closed = wait_for(client, "document.querySelector('[data-rcle]').hidden")
    restored = client.eval(STATE_EXPRESSION)
    root_restored = client.eval("""(() => {
      const root = document.querySelector('[data-v2-root]');
      return root === window.__rcleQaRoot
        && root.parentNode === window.__rcleQaParent
        && root.previousSibling === window.__rcleQaPrevious
        && document.activeElement === window.__rcleQaFocus
        && !document.body.classList.contains('rcle-open')
        && !root.querySelector('[id^="rcle-"]');
    })()""")
    check(f"{label} Escape closes explainer", closed)
    check(
        f"{label} route, tab, row, accordion, fields, and scroll restore",
        restored == baseline,
        json.dumps({"before": baseline, "after": restored}),
    )
    check(f"{label} root position and focus restore", root_restored)

    if width in (1024, 1920):
        client.screenshot(os.path.join(OUT, f"rcle-closed-{label}.png"))


def run_list_viewport(client, base_url, width, height):
    label = f"list-{width}x{height}"
    print(f"\n== {label} ==")
    client.send("Emulation.setDeviceMetricsOverride", {
        "width": width,
        "height": height,
        "deviceScaleFactor": 1,
        "mobile": False,
    })
    client.send("Page.navigate", {
        "url": f"{base_url}/?section=list&version=2.0"
    })
    loaded = wait_for(
        client,
        "document.body?.dataset.route === 'list' && "
        "Boolean(document.querySelector("
        "'[data-page=\"list\"] .table__body .row'))",
    )
    check(f"{label} list route loads", loaded)
    time.sleep(0.2)

    client.eval("""(() => {
      const root = document.querySelector('[data-page="list"]');
      const search = root.querySelector('[data-action="search"]');
      // 'rate' matches nothing in this dataset, which emptied the table
      // and made the "rows are readable" and "action names" assertions
      // below impossible to satisfy. Any term with results proves the
      // same thing about state restoring.
      search.value = 'upfront';
      search.dispatchEvent(new Event('input', { bubbles: true }));
      (root.querySelector('.th--name-id') || root.querySelector('.th--name'))?.click();
      root.querySelector('[aria-label="Page 2"]')?.click();
      const tableScroll = root.querySelector('.table-scroll');
      if (tableScroll) tableScroll.scrollLeft = Math.min(
        72,
        Math.max(0, tableScroll.scrollWidth - tableScroll.clientWidth)
      );
      window.__rcleListQaRoot = root;
      window.__rcleListQaParent = root.parentNode;
      window.__rcleListQaPrevious = root.previousSibling;
      window.__rcleListQaFocus = root.querySelector(
        '[data-action="toggle-filter"]'
      );
      window.__rcleListQaFocus?.focus();
    })()""")
    time.sleep(0.2)
    baseline = client.eval(LIST_STATE_EXPRESSION)

    client.key("p", "KeyP", 80, modifiers=4)
    opened = wait_for(
        client,
        "!document.querySelector('[data-rcle]').hidden && "
        "document.querySelector('[data-rcle]').dataset.rcleMode === 'list'",
    )
    check(f"{label} Cmd+P opens list explainer", opened)
    time.sleep(0.35)

    result = client.eval("""(() => {
      const overlay = document.querySelector('[data-rcle]');
      const view = overlay.querySelector('[data-rcle-list-view]');
      const frame = overlay.querySelector('[data-rcle-list-frame]');
      const root = document.querySelector('[data-page="list"]');
      const cards = [...overlay.querySelectorAll('[data-rcle-list-step]')];
      const groups = [...overlay.querySelectorAll(
        '[data-rcle-list-callout]'
      )];
      const rect = element => {
        const value = element.getBoundingClientRect();
        return {
          left: value.left, top: value.top, right: value.right,
          bottom: value.bottom, width: value.width, height: value.height,
        };
      };
      const frameRect = frame.getBoundingClientRect();
      const cardsAvoidFrame = cards.every(card => {
        const value = card.getBoundingClientRect();
        return value.right <= frameRect.left + 1
          || value.left >= frameRect.right - 1
          || value.bottom <= frameRect.top + 1
          || value.top >= frameRect.bottom - 1;
      });
      const viewRect = view.getBoundingClientRect();
      // 2026-08-05: the red source-ring outline and leader-line
      // connector were removed entirely, so badge placement is
      // re-derived here directly from the same live elements app.js
      // targets (independent of any app-reported rect), instead of
      // reading back a ring's x/y/width/height attributes.
      const targetRectsById = {
        '1': [
          root.querySelector('[aria-label="Filter rate cards"]'),
          root.querySelector('[data-main-search]') || root.querySelector('.search'),
        ].filter(Boolean).map(rect),
        '2': [...root.querySelectorAll('.th--marketplace, .th--buying-entity')]
          .map(rect),
        // 2026-08-15: 2.1 hides the standalone .th--name header in
        // favor of the combined .th--name-id "Rate Card ID / Name"
        // header (see app.js's own nameHeaderCandidates fallback), so
        // prefer whichever of the two is actually visible.
        '3': [
          [root.querySelector('.th--name-id'), root.querySelector('.th--name')]
            .find(el => el && el.getBoundingClientRect().width > 0),
        ].filter(Boolean).map(rect),
        '4': [root.querySelector('.th--saleshub')].filter(Boolean).map(rect),
        '5': [
          root.querySelector('.th--action'),
          ...root.querySelectorAll('.table__body .row .actions'),
        ].filter(Boolean).map(rect),
      };
      const unionOf = rects => rects.reduce((acc, value) => {
        if (!acc) return value;
        return {
          left: Math.min(acc.left, value.left),
          top: Math.min(acc.top, value.top),
          right: Math.max(acc.right, value.right),
          bottom: Math.max(acc.bottom, value.bottom),
        };
      }, null);
      const badgeMetrics = [];
      // Each badge sits centered above the same live UI area it
      // annotates: above its target's top edge, and horizontally
      // overlapping (or centered within a small tolerance of) that
      // target, with no drawn line connecting the two.
      // One ring and one leader, for the active step only, so two lines
      // can never cross and nothing is drawn over a label or a value.
      const ring = overlay.querySelector('[data-rcle-list-ring]');
      const leader = overlay.querySelector('[data-rcle-list-line]');
      const scrim = overlay.querySelector('[data-rcle-list-scrim]');
      const ringRect = ring.getBoundingClientRect();
      const leaderRect = leader.getBoundingClientRect();
      const railRect = overlay
        .querySelector('[data-rcle-list-rail]').getBoundingClientRect();
      const annotation = {
        ringVisible: !ring.hasAttribute('hidden')
          && ringRect.width > 0 && ringRect.height > 0,
        ringInsideFrame: ringRect.left >= frame.getBoundingClientRect().left - 2
          && ringRect.right <= frame.getBoundingClientRect().right + 2,
        ringIsRed: /rgb\(199,\s*57,\s*69\)/.test(getComputedStyle(ring).stroke),
        leaderStopsBeforeCopy: leader.hasAttribute('hidden')
          || leaderRect.right <= railRect.left + 1,
        scrimHasHole:
          ((scrim.getAttribute('d') || '').match(/M /g) || []).length === 2,
      };
      return {
        overlay: rect(overlay),
        view: rect(view),
        frame: rect(frame),
        cards: cards.map(rect),
        annotation,
        activeStep: overlay.getAttribute('data-rcle-list-step'),
        activeStepCount: overlay
          .querySelectorAll('[data-rcle-list-step].is-active').length,
        stepsAreNotCards: [...overlay.querySelectorAll('[data-rcle-list-step]')]
          .every(step => {
            const cs = getComputedStyle(step);
            return cs.backgroundColor === 'rgba(0, 0, 0, 0)'
              && cs.borderTopWidth === '0px'
              && cs.boxShadow === 'none';
          }),
        cardsAvoidFrame,
        cardContentFits: cards.every(card =>
          card.scrollWidth <= card.clientWidth + 1
          && card.scrollHeight <= card.clientHeight + 1
        ),
        rootInSlot: root.parentElement.matches(
          '[data-rcle-list-live-slot]'
        ),
        sameRoot: root === window.__rcleListQaRoot,
        rootInert: root.inert,
        modeClass: document.body.classList.contains('rcle-list-open'),
        pageOverflow:
          document.documentElement.scrollWidth > innerWidth + 1
          || document.documentElement.scrollHeight > innerHeight + 1,
        duplicateIds: (() => {
          const ids = [...overlay.querySelectorAll('[id]')]
            .map(element => element.id);
          return [...new Set(
            ids.filter((id, index) => ids.indexOf(id) !== index)
          )];
        })(),
        title: overlay.querySelector('#rcle-title').textContent.trim(),
        subtitle: overlay.querySelector('#rcle-subtitle').textContent.trim(),
        detailHidden: overlay.querySelector(
          '[data-rcle-detail-view]'
        ).hidden,
        listVisible: !view.hidden,
        cardCopy: cards.map(card => ({
          number: card.querySelector('.rcle-list__step-num').textContent.trim(),
          heading: card.querySelector('h3').textContent.trim(),
          description: card.querySelector('h3 + p').textContent.trim(),
          note: '',
        })),
        takeaway: (overlay.querySelector('.rcle-list__takeaway')
          || {}).textContent
          ? overlay.querySelector('.rcle-list__takeaway').textContent.trim()
          : '',
        paginationNoteRemoved: !overlay.querySelector(
          '[data-rcle-list-pagination-note]'
        ) && !overlay.querySelector(
          '[data-rcle-list-pagination-callout]'
        ),
        ui: {
          filter: !!root.querySelector('[aria-label="Filter rate cards"]'),
          search: !!root.querySelector('[aria-label="Search rate cards"]'),
          table: !!root.querySelector('[role="table"][aria-label="Rate cards"]'),
          status: !!root.querySelector('.th--status'),
          rateCardId: !!root.querySelector('.th--rate-card-id'),
          name: !!root.querySelector('.th--name'),
          marketplace: !!root.querySelector('.th--marketplace'),
          buyingEntity: !!root.querySelector('.th--buying-entity'),
          salesHubId: !!root.querySelector('.th--saleshub'),
          lastUpdated: !!root.querySelector('.th--last-updated'),
          version: !!root.querySelector('.th--ver'),
          actions: !!root.querySelector('.th--action'),
          pagination: !!root.querySelector('[data-pager]'),
        },
        actionNames: [...root.querySelectorAll(
          '.table__body .row:first-child .actions button'
        )].map(button => ({
          aria: button.getAttribute('aria-label'),
          tooltip: button.getAttribute('data-tooltip'),
        })),
        undersizedText: [...overlay.querySelectorAll('*')]
          .filter(element => {
            if (element.closest('[hidden]') || !element.getClientRects().length) {
              return false;
            }
            const directText = [...element.childNodes].some(node =>
              node.nodeType === Node.TEXT_NODE && node.textContent.trim()
            );
            const textControl = element.matches(
              'input, textarea, select, option'
            );
            return (directText || textControl)
              && parseFloat(getComputedStyle(element).fontSize) < 14;
          })
          .map(element => ({
            tag: element.tagName,
            className: String(element.className || ''),
            text: element.textContent.trim().slice(0, 80),
            size: getComputedStyle(element).fontSize,
          })),
        headingsAt18: cards.every(card => (
          parseFloat(getComputedStyle(card.querySelector('h3')).fontSize) >= 16
        )),
        bodyAt16: cards.every(card => (
          parseFloat(
            getComputedStyle(card.querySelector('h3 + p')).fontSize
          ) >= 14
        )),
        rowsReadable: [...root.querySelectorAll('.table__body .row')]
          .some(row => {
            const value = row.getBoundingClientRect();
            return value.width > 0 && value.height > 0;
          }),
      };
    })()""")

    expected_copy = [
        {
            "number": "01",
            "heading": "Find the right rate card",
            "description": (
                "Search or filter by name, ID, marketplace, or buying entity."
            ),
            "note": "",
        },
        {
            "number": "02",
            "heading": "Confirm the commercial context",
            "description": (
                "Check the marketplace, buying entity, and status."
            ),
            "note": "",
        },
        {
            "number": "03",
            "heading": "Open the rate card",
            "description": (
                "Select its name to manage its base rates and premium "
                "adjustments."
            ),
            "note": "",
        },
    ]
    check(
        f"{label} shell fits without page overflow",
        result["overlay"]["width"] == width
        and result["overlay"]["height"] == height
        and result["frame"]["left"] >= 0
        and result["frame"]["right"] <= width + 1
        and result["frame"]["top"] >= 0
        and result["frame"]["bottom"] <= height + 1
        and not result["pageOverflow"]
        and not result["duplicateIds"],
        str(result),
    )
    check(
        f"{label} live table is dominant and unobstructed",
        result["frame"]["width"] > result["view"]["width"] * 0.5
        and result["cardsAvoidFrame"]
        and result["cardContentFits"]
        and result["rowsReadable"],
        str(result),
    )
    check(
        f"{label} same live list is inert and reparented",
        result["sameRoot"]
        and result["rootInSlot"]
        and result["rootInert"]
        and result["modeClass"],
        str(result),
    )
    check(
        f"{label} exact list explainer copy and mode are visible",
        result["title"] == "Rate Card List"
        and result["subtitle"] == (
            "Find the right rate card, confirm its context, "
            "and open it for management."
        )
        and result["detailHidden"]
        and result["listVisible"]
        and result["cardCopy"] == expected_copy
        and result["paginationNoteRemoved"],
        str(result),
    )
    check(
        f"{label} real list interface remains complete",
        all(result["ui"].values()),
        str(result["ui"]),
    )
    # The five cards that used to surround the product are gone. The
    # story is three steps in one rail, and only the active step is
    # annotated, so no two leader lines can cross.
    check(
        f"{label} exactly one step is active and annotated",
        result["activeStepCount"] == 1
        and result["annotation"]["ringVisible"]
        and result["annotation"]["ringInsideFrame"]
        and result["annotation"]["ringIsRed"]
        and result["annotation"]["scrimHasHole"],
        json.dumps(result["annotation"]),
    )
    check(
        f"{label} the leader stops before the copy",
        result["annotation"]["leaderStopsBeforeCopy"],
        json.dumps(result["annotation"]),
    )
    check(
        f"{label} the explanation is text, not cards",
        result["stepsAreNotCards"] and len(result["cards"]) == 3,
        json.dumps({"steps": len(result["cards"]),
                    "notCards": result["stepsAreNotCards"]}),
    )
    check(
        f"{label} the takeaway line is present",
        result["takeaway"] == "One list to find, verify, and manage every "
                              "rate card.",
        result["takeaway"],
    )
    check(
        f"{label} card typography meets the presentation floor",
        result["headingsAt18"] and result["bodyAt16"],
        json.dumps({
            "headingsAt18": result["headingsAt18"],
            "bodyAt16": result["bodyAt16"],
        }),
    )
    expected_actions = [
        "Quick edit",
        "Duplicate rate card",
        "Export rate card",
        "Archive rate card",
        "Delete rate card",
    ]
    check(
        f"{label} action names are confirmed by labels and tooltips",
        [item["aria"] for item in result["actionNames"]] == expected_actions
        and all(
            item["aria"] == item["tooltip"]
            for item in result["actionNames"]
        ),
        str(result["actionNames"]),
    )
    check(
        f"{label} all visible explainer text is at least 14px",
        not result["undersizedText"],
        str(result["undersizedText"]),
    )

    client.screenshot(os.path.join(OUT, f"rcle-{label}.png"))

    if width == 1440:
        client.key("p", "KeyP", 80, modifiers=4)
    else:
        client.key("Escape", "Escape", 27)
    closed = wait_for(client, "document.querySelector('[data-rcle]').hidden")
    restored = client.eval(LIST_STATE_EXPRESSION)
    root_restored = client.eval("""(() => {
      const root = document.querySelector('[data-page="list"]');
      return root === window.__rcleListQaRoot
        && root.parentNode === window.__rcleListQaParent
        && root.previousSibling === window.__rcleListQaPrevious
        && document.activeElement === window.__rcleListQaFocus
        && !document.body.classList.contains('rcle-open')
        && !document.body.classList.contains('rcle-list-open')
        && !root.inert
        && !root.querySelector('[id^="rcle-"]');
    })()""")
    check(f"{label} presentation shortcut or Escape closes", closed)
    check(
        f"{label} search, filters, sort, page, rows, and scroll restore",
        restored == baseline,
        json.dumps({"before": baseline, "after": restored}),
    )
    check(f"{label} list position and focus restore", root_restored)
    if width == 1440:
        client.key("p", "KeyP", 80, modifiers=2)
        ctrl_opened = wait_for(
            client,
            "!document.querySelector('[data-rcle]').hidden && "
            "document.querySelector('[data-rcle]').dataset.rcleMode === 'list'",
        )
        client.eval(
            "document.querySelector('[data-rcle-close]').click()"
        )
        close_button_closed = wait_for(
            client,
            "document.querySelector('[data-rcle]').hidden",
        )
        check(f"{label} Ctrl+P opens list explainer", ctrl_opened)
        check(f"{label} neutral close control exits", close_button_closed)


def main():
    app_port = free_port()
    debug_port = free_port()
    server = ThreadingHTTPServer(("127.0.0.1", app_port), StaticHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    profile = f"/tmp/rate_card_rcle_profile_{debug_port}"
    os.makedirs(profile, exist_ok=True)
    # SECURITY-REVIEW: Launches local headless Chrome with fixed arguments.
    chrome = subprocess.Popen(
        [
            CHROME,
            f"--remote-debugging-port={debug_port}",
            f"--user-data-dir={profile}",
            "--headless=new",
            "--remote-allow-origins=*",
            "--no-first-run",
            "--window-size=1920,1080",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(
                    f"http://127.0.0.1:{debug_port}/json/version", timeout=0.5
                ).read()
                break
            except Exception:
                time.sleep(0.1)
        client = CDP(debug_port)
        client.send("Page.enable")
        client.send("Runtime.enable")
        client.send("Network.enable")
        client.send("Network.setCacheDisabled", {"cacheDisabled": True})
        client.send("Page.addScriptToEvaluateOnNewDocument", {"source": """
          window.__rcleQaIssues = [];
          addEventListener('error', event => {
            window.__rcleQaIssues.push('error: ' + event.message);
          });
          addEventListener('unhandledrejection', event => {
            window.__rcleQaIssues.push(
              'unhandledrejection: ' + String(event.reason)
            );
          });
          ['error', 'warn'].forEach(level => {
            const original = console[level].bind(console);
            console[level] = (...args) => {
              window.__rcleQaIssues.push(
                level + ': ' + args.map(String).join(' ')
              );
              original(...args);
            };
          });
        """})
        base_url = f"http://127.0.0.1:{app_port}"
        for width, height in VIEWPORTS:
            run_viewport(client, base_url, width, height)
        for width, height in ((1024, 768), (1440, 900), (1920, 1080)):
            run_list_viewport(client, base_url, width, height)

        issues = client.eval("window.__rcleQaIssues || []")
        check("No console errors or warnings", not issues, str(issues))
        client.key("d", "KeyD", 68, modifiers=4)
        time.sleep(0.2)
        redline_active = client.eval(
            "Boolean(window.RedlineMode && window.RedlineMode.isActive())"
        )
        check("Cmd+D Redline Mode remains available", redline_active)
        if redline_active:
            client.key("Escape", "Escape", 27)
    finally:
        server.shutdown()
        chrome.terminate()
        try:
            chrome.wait(timeout=3)
        except subprocess.TimeoutExpired:
            chrome.kill()

    report = {
        "results": RESULTS,
        "passed": sum(item["status"] == "PASS" for item in RESULTS),
        "failed": sum(item["status"] == "FAIL" for item in RESULTS),
    }
    with open(os.path.join(OUT, "report.json"), "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print(
        f"\nSummary: {report['passed']} passed, {report['failed']} failed. "
        f"Artifacts: {OUT}"
    )
    raise SystemExit(1 if report["failed"] else 0)


if __name__ == "__main__":
    main()
