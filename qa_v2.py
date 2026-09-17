"""Rate Card Manager Version 2.x functional and regression QA.

Covers 2.0 and its 2.1 fork. The boot-time checks assert that 2.1 is
VERSION_LATEST (bare URL, refresh, and incognito land there) and that 2.0
stays selectable; the feature checks below stay pinned to ?version=2.0 on
purpose, so this suite keeps proving the preserved 2.0 experience works.

Run with: python3 qa_v2.py
Writes a JSON report and desktop/narrow screenshots under /tmp/rate-card-v2-qa.
"""

import base64
import json
import os
import shutil
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import urlopen

import websocket


ROOT = "/Users/frances.sun/My Drive/Cursor and Code/Rate Card"
PORT = 8990
DEBUG_PORT = 9290
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
OUT = "/tmp/rate-card-v2-qa"
os.makedirs(OUT, exist_ok=True)


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


server = ThreadingHTTPServer(("127.0.0.1", PORT), StaticHandler)
threading.Thread(target=server.serve_forever, daemon=True).start()
profile = "/tmp/rate_card_v2_qa_profile"
# Start from an empty profile. The suite selects other versions as it runs
# and the app persists that choice, so a reused profile carries the last
# run's selection into the checks that assert what a first-time visitor
# lands on.
shutil.rmtree(profile, ignore_errors=True)
os.makedirs(profile, exist_ok=True)
chrome = subprocess.Popen(
    [
        CHROME,
        f"--remote-debugging-port={DEBUG_PORT}",
        f"--user-data-dir={profile}",
        "--headless=new",
        "--remote-allow-origins=*",
        "--no-first-run",
        "--window-size=1440,960",
        "about:blank",
    ],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
time.sleep(1.2)
tabs = json.loads(urlopen(f"http://127.0.0.1:{DEBUG_PORT}/json").read())
ws_url = next(tab["webSocketDebuggerUrl"] for tab in tabs if tab.get("type") == "page")
ws = websocket.create_connection(ws_url)
message_id = 0
console_messages = []
results = []


def send(method, params=None):
    global message_id
    message_id += 1
    expected = message_id
    ws.send(json.dumps({"id": expected, "method": method, "params": params or {}}))
    while True:
        event = json.loads(ws.recv())
        if event.get("method") == "Runtime.exceptionThrown":
            details = event.get("params", {}).get("exceptionDetails", {})
            console_messages.append(
                (details.get("exception") or {}).get("description", details.get("text", ""))
            )
        if event.get("id") == expected:
            return event


def evaluate(expression):
    response = send(
        "Runtime.evaluate",
        {"expression": expression, "returnByValue": True, "awaitPromise": True},
    )
    return response.get("result", {}).get("result", {}).get("value")


def navigate(query, pause=1.0):
    """Load a page and wait until the app has actually booted on it.

    The cache is disabled for this run, so a cold first load can take
    longer than the fixed pause and the checks then measure a page whose
    scripts have not run. Wait for app.js to stamp the resolved version
    on the body before returning, and keep `pause` as the floor for the
    layout and font work that follows it."""
    send("Page.navigate", {"url": f"http://127.0.0.1:{PORT}/{query}"})
    time.sleep(pause)
    for _ in range(40):
        if evaluate("!!document.body && !!document.body.dataset.version"):
            return
        time.sleep(0.1)


def viewport(width, height=960):
    send(
        "Emulation.setDeviceMetricsOverride",
        {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False},
    )
    time.sleep(0.25)


def screenshot(name):
    send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": 1, "y": 1})
    time.sleep(0.05)
    payload = send("Page.captureScreenshot", {"format": "png"})
    data = payload.get("result", {}).get("data", "")
    filename = os.path.join(OUT, name + ".png")
    with open(filename, "wb") as handle:
        handle.write(base64.b64decode(data))


def screenshot_clip(name, clip):
    payload = send(
        "Page.captureScreenshot",
        {"format": "png", "clip": {**clip, "scale": 1}},
    )
    data = payload.get("result", {}).get("data", "")
    filename = os.path.join(OUT, name + ".png")
    with open(filename, "wb") as handle:
        handle.write(base64.b64decode(data))


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results.append({"name": name, "status": status, "detail": detail})
    print(f"[{status}] {name}" + (f": {detail}" if detail and not condition else ""))


try:
    send("Page.enable")
    send("Runtime.enable")
    send("Network.enable")
    send("Network.setCacheDisabled", {"cacheDisabled": True})

    navigate("")
    check("Bare URL defaults to 2.1", evaluate("document.body.dataset.version") == "2.1")
    check(
        "Latest-version navigation matches Figma geometry",
        evaluate(
            """(() => {
              const nav = document.querySelector('.gnav').getBoundingClientRect();
              const mark = document.querySelector('.gnav__brand-icon--v2').getBoundingClientRect();
              const avatar = document.querySelector('.gnav__avatar').getBoundingClientRect();
              const title = document.querySelector('.gnav__brand-name--v2');
              const titleStyle = getComputedStyle(title);
              return nav.height === 56 && mark.width === 32 && mark.height === 28
                && avatar.width === 32 && avatar.height === 32
                && title.textContent === 'Ad Console'
                && titleStyle.fontSize === '18px' && titleStyle.lineHeight === '24px';
            })()"""
        ),
    )
    check(
        "Version 2.0 uses exact exported navigation assets",
        evaluate(
            """(() => {
              const mark = document.querySelector('.gnav__brand-icon--v2');
              const bell = document.querySelector('.gnav__utility-icon--bell');
              const sparkle = document.querySelector('.gnav__utility-icon--sparkle');
              return mark.currentSrc.endsWith('/assets/figma-navigation/disney-mark.svg')
                && bell.currentSrc.endsWith('/assets/figma-navigation/bell.svg')
                && sparkle.currentSrc.endsWith('/assets/figma-navigation/sparkle.svg')
                && bell.getBoundingClientRect().width > 14
                && sparkle.getBoundingClientRect().width > 18;
            })()"""
        ),
    )
    check(
        "2.1 menu option is active (VERSION_LATEST)",
        evaluate(
            """(() => {
              const item = document.querySelector('.version-submenu__item[data-version="2.1"]');
              return !!item && item.getAttribute('aria-checked') === 'true';
            })()"""
        ),
    )
    check(
        "2.0 remains selectable in the version menu",
        evaluate(
            """(() => {
              const item = document.querySelector('.version-submenu__item[data-version="2.0"]');
              return !!item && !item.disabled && item.getAttribute('aria-checked') === 'false';
            })()"""
        ),
    )

    # 2.1 was forked from 2.0 on 2026-08-12 as an exact duplicate, so both
    # tokens mount the v2 master-detail experience and neither hides it.
    V2_FAMILY = ["2.0", "2.1"]
    for version in ["1.0", "1.1", "1.2", "2.0", "2.1"]:
        navigate(f"?version={version}")
        check(
            f"Explicit Version {version} restores",
            evaluate("document.body.dataset.version") == version,
        )
        if version not in V2_FAMILY:
            check(
                f"Version {version} keeps V2 hidden",
                evaluate("document.querySelector('[data-v2-root]').hidden") is True,
            )
        else:
            check(
                f"Version {version} mounts the V2 experience",
                evaluate("document.querySelector('[data-v2-root]').hidden") is False,
            )
        if version == "1.2":
            check(
                "Version 1.2 keeps its frozen navigation",
                evaluate(
                    """document.querySelector('.gnav').getBoundingClientRect().height === 56
                    && getComputedStyle(document.querySelector('.gnav__brand-name--legacy')).display !== 'none'
                    && document.querySelector('.gnav__brand-name--legacy').textContent === 'Disney Advertising'"""
                ),
            )

    # The list filter drawer no longer uses single-select ADS Dropdowns.
    # Status, Marketplace and Deal season are ADS checkbox groups so each
    # one can hold several values at once, and Buying entity is an
    # autocomplete. This checks the controls that actually ship.
    filter_controls = evaluate(
        """(() => {
          document.querySelector('[data-action="toggle-filter"]').click();
          const panel = document.querySelector('#filter-panel');
          const groups = [...panel.querySelectorAll('.fgroup')];
          const entity = panel.querySelector('#fp-entity');
          const state = {
            groupCount: groups.length,
            legends: groups.map(g => g.querySelector('legend').textContent.trim()),
            allFieldsets: groups.every(g => g.tagName === 'FIELDSET'),
            allAdsCheckboxes: groups.every(g =>
              [...g.querySelectorAll('input')].every(input =>
                input.type === 'checkbox'
                && input.classList.contains('ads-checkbox__input')
                && input.closest('.ads-checkbox'))),
            multiSelectable: (() => {
              const boxes = [...panel.querySelectorAll('[data-filter-checkbox="marketplace"]')];
              boxes.slice(0, 2).forEach(box => {
                box.checked = true;
                box.dispatchEvent(new Event('change', {bubbles: true}));
              });
              const held = boxes.filter(box => box.checked).length;
              boxes.forEach(box => {
                box.checked = false;
                box.dispatchEvent(new Event('change', {bubbles: true}));
              });
              return held === 2;
            })(),
            entityIsCombobox: entity.getAttribute('role') === 'combobox'
              && entity.getAttribute('aria-autocomplete') === 'list',
            closeLabel: panel.querySelector('.fpanel__close').getAttribute('aria-label'),
            scrimDims: (() => {
              const scrim = document.querySelector('[data-filter-scrim]');
              return Boolean(scrim) && !scrim.hidden;
            })()
          };
          panel.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));
          state.closedOnEscape = !panel.classList.contains('is-open');
          return state;
        })()"""
    )
    check(
        "List filters use ADS checkbox groups and an entity autocomplete",
        filter_controls["groupCount"] == 3
        and filter_controls["legends"] == ["Status", "Marketplace", "Deal season"]
        and filter_controls["allFieldsets"]
        and filter_controls["allAdsCheckboxes"]
        and filter_controls["multiSelectable"]
        and filter_controls["entityIsCombobox"]
        and filter_controls["closeLabel"] == "Close filters"
        and filter_controls["scrimDims"]
        and filter_controls["closedOnEscape"],
        json.dumps(filter_controls),
    )
    check(
        "Profile action menus support arrow navigation and Escape focus return",
        evaluate(
            """(() => {
              // Profile menu order (2026-08-04):
              //   1. Presentation view   [data-action="open-presentation-view"]
              //   2. divider
              //   3. Version              [data-action="toggle-version"]
              //   4. Theme                [data-action="toggle-theme"]
              //   5. Redline              [data-action="toggle-redline"]
              //   6. Log out              [data-action="logout"]
              // ArrowDown from the trigger opens the menu and lands on the
              // first menuitem (Presentation view). The Version submenu keyboard
              // contract is exercised by focusing that submenu trigger
              // explicitly, so this test is resilient to future menu inserts
              // above / between the top rows.
              const trigger = document.querySelector('[data-action="toggle-profile"]');
              trigger.focus();
              trigger.dispatchEvent(new KeyboardEvent('keydown', {key:'ArrowDown', bubbles:true}));
              const first = document.activeElement;
              const versionTrigger = document.querySelector('[data-action="toggle-version"]');
              versionTrigger.focus();
              versionTrigger.dispatchEvent(new KeyboardEvent('keydown', {key:'ArrowRight', bubbles:true}));
              const enteredSubmenu = document.activeElement.matches('.version-submenu__item');
              document.activeElement.dispatchEvent(new KeyboardEvent('keydown', {
                key:'Escape', bubbles:true
              }));
              return first.matches('[data-action="open-presentation-view"]')
                && enteredSubmenu
                && document.querySelector('#profile-menu').hidden
                && document.activeElement === trigger;
            })()"""
        ),
    )

    navigate("?version=1.2&section=create")
    check(
        "Legacy selection hosts use the ADS compatibility wrapper and combobox semantics",
        evaluate(
            """(() => {
              const roots = [...document.querySelectorAll(
                '.edl-select:not(.edl-select--rcle)'
              )];
              const marketplace = document.querySelector(
                '.edl-select[data-field="marketplace"]'
              );
              const trigger = marketplace.querySelector('.edl-select__trigger');
              return roots.length > 0 && roots.every(root => {
                const button = root.querySelector('.edl-select__trigger');
                const menu = root.querySelector('.edl-select__menu');
                return root.classList.contains('ads-select')
                  && root.dataset.selectWired === 'true'
                  && button.getAttribute('role') === 'combobox'
                  && button.getAttribute('aria-controls') === menu.id;
              }) && trigger.getBoundingClientRect().height === 42
                && getComputedStyle(trigger).fontFamily.includes('Open Sans');
            })()"""
        ),
    )
    evaluate("document.querySelector('[data-accordion=\"line\"] .accordion__header').click()")
    evaluate(
        """(() => {
          const input = document.querySelector('[data-lineitems-search-input]');
          input.value = 'WPP';
          input.dispatchEvent(new Event('input', {bubbles:true}));
        })()"""
    )
    check(
        "Legacy LINE Search uses shared filled and clear behavior",
        evaluate(
            """(() => {
              const input = document.querySelector('[data-lineitems-search-input]');
              const wrap = input.closest('.ads-search');
              const clear = wrap.querySelector('[data-lineitems-search-clear]');
              const filled = wrap.dataset.filled === 'true' && !clear.hidden;
              clear.click();
              return filled && input.value === '' && clear.hidden
                && document.activeElement === input
                && input.getAttribute('aria-expanded') === 'false';
            })()"""
        ),
    )
    evaluate("document.querySelector('[data-accordion=\"prem\"] .accordion__header').click()")
    evaluate(
        """(() => {
          const input = document.querySelector('[data-premitems-search-input]');
          input.value = 'CPM';
          input.dispatchEvent(new Event('input', {bubbles:true}));
        })()"""
    )
    check(
        "Legacy PREM Search uses shared filled and clear behavior",
        evaluate(
            """(() => {
              const input = document.querySelector('[data-premitems-search-input]');
              const wrap = input.closest('.ads-search');
              const clear = wrap.querySelector('[data-premitems-search-clear]');
              const filled = wrap.dataset.filled === 'true' && !clear.hidden;
              clear.click();
              return filled && input.value === '' && clear.hidden
                && document.activeElement === input
                && input.getAttribute('aria-expanded') === 'false';
            })()"""
        ),
    )

    navigate("?version=2.0&section=create&mode=edit&cardId=RC-QUERY-CHECK&qaMarker=kept")
    evaluate("document.querySelector('.version-submenu__item[data-version=\"1.2\"]').click()")
    time.sleep(0.15)
    check(
        "Version selection preserves unrelated query parameters",
        evaluate(
            """(() => {
              const p = new URL(location.href).searchParams;
              return p.get('version') === '1.2' && p.get('section') === 'create'
                && p.get('mode') === 'edit' && p.get('cardId') === 'RC-QUERY-CHECK'
                && p.get('qaMarker') === 'kept';
            })()"""
        ),
    )

    navigate("?version=2.0&section=create")
    evaluate("localStorage.removeItem('rate-card-manager.v2.files'); location.reload()")
    time.sleep(1.0)
    viewport(1440, 960)
    screenshot("figma-initial")
    check("Create master-detail renders", evaluate("!document.querySelector('[data-v2-root]').hidden"))
    check(
        "Initial content hierarchy matches Figma",
        evaluate(
            """(() => {
              const items = [
                document.querySelector('.create-md__back'),
                document.querySelector('[data-v2-title]'),
                document.querySelector('[data-v2-helper]'),
                document.querySelector('.create-md__tabs'),
                document.querySelector('[data-v2-empty="lines"]')
              ];
              const text = items.map(el => el.textContent.replace(/\\s+/g, ' ').trim());
              const tops = items.map(el => el.getBoundingClientRect().top);
              window.__qaEmptyTabsTop = items[3].getBoundingClientRect().top;
              const tabLabels = [...document.querySelectorAll('[data-v2-tab]')]
                .map(tab => tab.querySelector('.create-md__tab-label').textContent.trim());
              return text[0] === 'Back to list view'
                && text[1] === 'Create New Rate Card'
                && text[2] === 'Enter the rate card details, then add line items and premium adjustments.'
                && tabLabels.join('|') === 'Line items|Premiums'
                && text[4] === 'No line items yet Add your first line item to start building this rate card. Add Line Item'
                && tops.every((top, index) => index === 0 || top > tops[index - 1]);
            })()"""
        ),
    )
    # Both columns are direct children of one content-driven grid row.
    initial_figma_geometry = evaluate(
        """(() => {
          const rect = selector => {
            const value = document.querySelector(selector).getBoundingClientRect();
            return [value.x, value.y, value.width, value.height].map(Math.round);
          };
          return {
            workspace: rect('.create-md__workspace'),
            detail: rect('.create-md__detail'),
            card: rect('[data-v2-accordion="card"]'),
            line: rect('[data-v2-accordion="line"]'),
            premium: rect('[data-v2-accordion="premium"]')
          };
        })()"""
    )
    check(
        "Initial master-detail geometry shares exact outer edges",
        initial_figma_geometry["workspace"] == [76, 75, 878, 712]
        and initial_figma_geometry["detail"] == [966, 75, 462, 712]
        and initial_figma_geometry["card"] == [982, 91, 430, 568]
        and initial_figma_geometry["line"] == [982, 667, 430, 48]
        and initial_figma_geometry["premium"] == [982, 723, 430, 48],
        json.dumps(initial_figma_geometry),
    )
    check(
        "Create page layered fills match Figma 457:15236",
        evaluate(
            """(() => {
              const background = selector =>
                getComputedStyle(document.querySelector(selector)).backgroundColor;
              return background('[data-page="create"] > .page__content') === 'rgb(243, 243, 243)'
                && background('.create-md__workspace') === 'rgb(255, 255, 255)'
                && background('.create-md__detail') === 'rgb(236, 238, 238)'
                && background('[data-v2-accordion="card"]') === 'rgb(255, 255, 255)'
                && background('[data-v2-accordion="line"]') === 'rgb(255, 255, 255)'
                && background('[data-v2-form="card"] .field__input') === 'rgb(255, 255, 255)'
                && background('.gnav') === 'rgb(64, 69, 194)'
                && background('.vnav') === 'rgb(255, 255, 255)';
            })()"""
        ),
    )
    check(
        "Right rail accordion titles share Figma body semibold xl",
        evaluate(
            """(() => [...document.querySelectorAll(
              '.create-md__detail .create-md__accordion-trigger'
            )].every(trigger => {
              const label = trigger.querySelector(':scope > .create-md__accordion-title');
              const icon = trigger.querySelector(':scope > svg');
              const style = getComputedStyle(label);
              const triggerStyle = getComputedStyle(trigger);
              const labelRect = label.getBoundingClientRect();
              const iconRect = icon.getBoundingClientRect();
              return style.fontFamily.includes('Open Sans')
                && style.fontSize === '18px'
                && style.fontWeight === '600'
                && style.lineHeight === '24px'
                && ['0px', 'normal'].includes(style.letterSpacing)
                && style.color === 'rgb(22, 28, 30)'
                && style.textTransform === 'none'
                && style.whiteSpace === 'nowrap'
                && style.wordBreak === 'break-word'
                && Math.round(iconRect.width) === 24
                && Math.round(iconRect.height) === 24
                && Math.round(labelRect.left - iconRect.right) === 8
                && Math.round(labelRect.height) === 24
                && triggerStyle.alignItems === 'center';
            }))()"""
        ),
    )
    check(
        "Right rail accordion titles use exact visible and accessible copy",
        evaluate(
            """(() => {
              const triggers = [...document.querySelectorAll(
                '.create-md__detail .create-md__accordion-trigger'
              )];
              return triggers.map(trigger =>
                trigger.querySelector('.create-md__accordion-title').textContent.trim()
              ).join('|') === 'Rate Card details|Line details|Premium adjustments'
                && triggers.every(trigger => trigger.getAttribute('aria-label') === null)
                && triggers.map(trigger => trigger.textContent.trim()).join('|')
                  === 'Rate Card details|Line details|Premium adjustments';
            })()"""
        ),
    )
    check(
        "Incorrect pricing rows heading is absent",
        not evaluate(
            """[...document.querySelectorAll('h1,h2,h3,h4,h5,h6')]
              .some(el => /rate card pricing rows/i.test(el.textContent))"""
        ),
    )
    check(
        "Create begins with empty row collections",
        evaluate(
            """document.querySelector('[data-v2-empty="lines"]').hidden === false
            && document.querySelector('[data-v2-empty="premiums"]').hidden === false
            && document.querySelector('[data-v2-total="lines"]').textContent === '0'
            && document.querySelector('[data-v2-total="premiums"]').textContent === '0'"""
        ),
    )
    toast_geometry = evaluate(
        """(async () => {
          const workspace = document.querySelector('.create-md__workspace').getBoundingClientRect();
          window.toast({title:'Line item added', variant:'info', duration:0});
          await new Promise(resolve => setTimeout(resolve, 260));
          const stack = document.querySelector('[data-toast-stack]');
          const toast = stack.firstElementChild;
          const card = toast.getBoundingClientRect();
          const stackRect = stack.getBoundingClientRect();
          const style = getComputedStyle(toast);
          const iconBox = toast.querySelector('.ads-toast__icon').getBoundingClientRect();
          const icon = toast.querySelector('.ads-toast__icon img').getBoundingClientRect();
          const close = toast.querySelector('.ads-toast__close').getBoundingClientRect();
          const closeLeaf = toast.querySelector('.ads-toast__close-icon').getBoundingClientRect();
          const workspaceAfter = document.querySelector('.create-md__workspace').getBoundingClientRect();
          // Round the outer rect values so sub-pixel artifacts from the
          // CSS transform matrix (identity after enter animation ends)
          // don't produce fractional widths like 399.99993... that would
          // flake the equality assertions below.
          return {
            top: Math.round(card.top),
            right: Math.round(innerWidth - card.right),
            width: Math.round(card.width),
            padding: style.padding,
            borderLeft: style.borderLeftWidth,
            borderColor: style.borderLeftColor,
            radius: style.borderRadius,
            titleColor: getComputedStyle(toast.querySelector('.ads-toast__title')).color,
            iconBox: [iconBox.width, iconBox.height],
            icon: [icon.width, icon.height],
            iconAsset: toast.querySelector('.ads-toast__icon img').currentSrc,
            close: [close.width, close.height],
            closeLeaf: [closeLeaf.width, closeLeaf.height],
            role: toast.getAttribute('role'),
            live: toast.getAttribute('aria-live'),
            noInlineStatus: !document.querySelector('[data-v2-save-status]'),
            noShift: workspace.x === workspaceAfter.x
              && workspace.y === workspaceAfter.y
              && workspace.width === workspaceAfter.width
              && workspace.height === workspaceAfter.height
              && getComputedStyle(stack).position === 'fixed'
          };
        })()"""
    )
    check(
        "V2 operation feedback uses the ADS blue Toast without layout shift",
        # Per the 2026-08-04 toast placement brief, the stack anchors the
        # toast's TOP edge halfway into the bottom of the blue nav bar
        # (nav is 56px, so top == 28). See v2.css --ads-toast-stack.
        toast_geometry.get("top") == 28
        and toast_geometry.get("right") == 24
        and toast_geometry.get("width") == 400
        and toast_geometry.get("padding") == "16px"
        and toast_geometry.get("borderLeft") == "5px"
        and toast_geometry.get("borderColor") == "rgb(64, 69, 194)"
        and toast_geometry.get("radius") == "6px"
        and toast_geometry.get("titleColor") == "rgb(64, 69, 194)"
        and toast_geometry.get("iconBox") == [24, 24]
        and toast_geometry.get("icon") == [19.5, 19.5]
        and toast_geometry.get("iconAsset").endswith("/assets/ads-toast-info.svg")
        and toast_geometry.get("close") == [16, 16]
        and toast_geometry.get("closeLeaf") == [10, 10]
        and toast_geometry.get("role") == "status"
        and toast_geometry.get("live") == "polite"
        and toast_geometry.get("noInlineStatus")
        and toast_geometry.get("noShift"),
        json.dumps(toast_geometry),
    )
    toast_lifecycle = evaluate(
        """(async () => {
          while (document.querySelector('[data-toast]')) {
            window.dismissToast(document.querySelector('[data-toast]'));
            await new Promise(resolve => setTimeout(resolve, 200));
          }
          const first = window.toast({title:'Line item added', variant:'info', duration:0});
          const second = window.toast({title:'Premium adjustment added', variant:'info', duration:0});
          await new Promise(resolve => setTimeout(resolve, 260));
          const live = [...document.querySelectorAll('[data-toast]')];
          const gap = live[1].getBoundingClientRect().top - live[0].getBoundingClientRect().bottom;
          const newestFirst = live[0].querySelector('[data-toast-title]').textContent
            === 'Premium adjustment added';
          second.querySelector('[data-action="close-toast"]').click();
          // Exit animation is 260ms per v2.css ads-toast-exit-right;
          // wait comfortably past that before asserting removal so the
          // animationend handler has time to detach the node.
          await new Promise(resolve => setTimeout(resolve, 340));
          const manualRemoved = !document.body.contains(second);
          const paused = window.toast({title:'Paused toast', variant:'info', duration:120});
          paused.dispatchEvent(new PointerEvent('pointerenter'));
          await new Promise(resolve => setTimeout(resolve, 220));
          const remainedWhileHovered = document.body.contains(paused);
          paused.dispatchEvent(new PointerEvent('pointerleave'));
          // The hover now banks the whole 120ms rather than letting it
          // burn down underneath the pointer, so the countdown only
          // starts here. Removal therefore lands a full duration plus a
          // 260ms exit animation after the leave, where it used to be
          // mid-exit by this point.
          await new Promise(resolve => setTimeout(resolve, 700));
          const removedAfterLeave = !document.body.contains(paused);
          while (document.querySelector('[data-toast]')) {
            window.dismissToast(document.querySelector('[data-toast]'));
            await new Promise(resolve => setTimeout(resolve, 200));
          }
          return {count:live.length, gap, newestFirst, manualRemoved,
            remainedWhileHovered, removedAfterLeave};
        })()"""
    )
    check(
        "ADS Toast stacks, dismisses, and pauses its timer",
        toast_lifecycle == {
            "count": 2,
            "gap": 24,
            "newestFirst": True,
            "manualRemoved": True,
            "remainedWhileHovered": True,
            "removedAfterLeave": True,
        },
        json.dumps(toast_lifecycle),
    )
    check(
        "Rate Card details is the only open section",
        evaluate(
            """(() => {
              const open = [...document.querySelectorAll('[data-v2-accordion]')]
                .filter(x => x.querySelector('button').getAttribute('aria-expanded') === 'true');
              return open.length === 1 && open[0].dataset.v2Accordion === 'card';
            })()"""
        ),
    )
    check(
        "Create title and unsaved ID are correct",
        evaluate(
            """document.querySelector('[data-v2-title]').textContent === 'Create New Rate Card'
            && document.querySelector('[data-v2-card-id]').textContent === 'Auto-generated on Save'"""
        ),
    )
    check(
        "Figma field components and placeholders are exact",
        evaluate(
            """(() => {
              const form = document.querySelector('[data-v2-form="card"]');
              const start = form.querySelector('[data-field="v2-effective-start"]');
              const end = form.querySelector('[data-field="v2-effective-end"]');
              const order = [...form.children]
                .filter(element => element.dataset.v2CardField)
                .map(element => element.dataset.v2CardField)
                .join('|');
              return order === 'id|name|buying-id|buying-name|market-season|dates|rule-order'
                && form.elements.name.placeholder === 'e.g. WPP – Disney+ Upfront 2026–2027'
                && form.elements.buyingEntityId.placeholder === 'e.g. SH-BE-102384'
                && form.elements.buyingEntityName.placeholder === 'e.g. The Wonderful Company'
                && form.elements.marketplace.tagName === 'SELECT'
                && form.elements.dealSeason.tagName === 'SELECT'
                && form.elements.dealSeason.value === '2025-2026'
                && !form.elements.dealSeason.required
                && !form.elements.buyingEntityId.required
                && !form.elements.buyingEntityName.required
                && form.elements.dcmRuleOrder.tagName === 'INPUT'
                && form.elements.dcmRuleOrder.type === 'text'
                && form.elements.dcmRuleOrder.inputMode === 'numeric'
                && form.elements.dcmRuleOrder.value === ''
                && form.elements.dcmRuleOrder.placeholder === 'e.g. 10'
                && !form.elements.dcmRuleOrder.closest('.create-md__select')
                && start.querySelector('.ads-datepicker__value').textContent === 'Select start date'
                && end.querySelector('.ads-datepicker__value').textContent === 'Select end date';
            })()"""
        ),
    )
    check(
        "All v2 native enums delegate to the shared ADS Dropdown Small wrapper",
        evaluate(
            """(() => {
              const root = document.querySelector('[data-v2-root]');
              const selects = [...root.querySelectorAll('select')];
              return selects.length === 12 && selects.every(select => {
                const dropdown = select.closest('.ads-dd');
                const trigger = dropdown?.querySelector('.ads-dd__trigger');
                const menu = dropdown?.querySelector('.ads-dd__menu');
                return select.hidden && select.dataset.adsEnhanced === 'true'
                  && dropdown.classList.contains('ads-dd--small')
                  && trigger?.getAttribute('role') === 'combobox'
                  && trigger?.getAttribute('aria-controls') === menu?.id
                  && menu?.getAttribute('role') === 'listbox'
                  && menu.hidden
                  && menu.querySelectorAll('.ads-dd__option').length === select.options.length;
              });
            })()"""
        ),
    )
    generic_dropdown = evaluate(
        """(() => {
          const select = document.querySelector('[data-v2-form="card"]').elements.marketplace;
          const dropdown = select.closest('.ads-dd');
          const trigger = dropdown.querySelector('.ads-dd__trigger');
          const before = dropdown.getBoundingClientRect().height;
          trigger.click();
          const menu = dropdown.querySelector('.ads-dd__menu');
          const style = getComputedStyle(trigger);
          const open = {
            expanded: trigger.getAttribute('aria-expanded'),
            hidden: menu.hidden,
            optionCount: menu.querySelectorAll('.ads-dd__option').length,
            followingBefore: before,
            followingAfter: dropdown.getBoundingClientRect().height,
            height: trigger.getBoundingClientRect().height,
            fontSize: style.fontSize
          };
          menu.querySelector('[data-value="Upfront"]').click();
          const selected = {
            value: select.value,
            text: dropdown.querySelector('.ads-dd__value').textContent,
            expanded: trigger.getAttribute('aria-expanded'),
            focused: document.activeElement === trigger
          };
          select.value = '';
          select.dispatchEvent(new Event('input', {bubbles: true}));
          select.dispatchEvent(new Event('change', {bubbles: true}));
          return {open, selected};
        })()"""
    )
    check(
        "Shared v2 Dropdown opens as a Small overlay and persists selection",
        generic_dropdown == {
            "open": {
                "expanded": "true",
                "hidden": False,
                "optionCount": 4,
                "followingBefore": generic_dropdown["open"]["followingAfter"],
                "followingAfter": generic_dropdown["open"]["followingAfter"],
                "height": 32,
                "fontSize": "13px",
            },
            "selected": {
                "value": "Upfront",
                "text": "Upfront",
                "expanded": "false",
                "focused": True,
            },
        },
        json.dumps(generic_dropdown),
    )
    check(
        "ADS Input and Date Picker geometry uses shared tokens",
        evaluate(
            """(() => {
              const form = document.querySelector('[data-v2-form="card"]');
              const input = form.elements.name;
              const inputStyle = getComputedStyle(input);
              const labelStyle = getComputedStyle(form.querySelector('label[for="v2-card-name"]'));
              const dates = [...form.querySelectorAll('.ads-datepicker__trigger')];
              return input.getBoundingClientRect().height === 36
                && inputStyle.borderRadius === '6px'
                && inputStyle.fontSize === '14px' && inputStyle.lineHeight === '20px'
                && labelStyle.fontSize === '12px' && labelStyle.lineHeight === '18px'
                && labelStyle.fontWeight === '600'
                && dates.length === 2
                && dates.every(trigger => trigger.getBoundingClientRect().height === 36);
            })()"""
        ),
    )
    evaluate("document.querySelector('[data-v2-form=\"card\"]').elements.name.focus()")
    time.sleep(0.15)
    input_states = {
        "focus": evaluate(
            """(() => {
              const style = getComputedStyle(document.querySelector('[data-v2-form="card"]').elements.name);
              const input = document.querySelector('[data-v2-form="card"]').elements.name;
              return {
                active: document.activeElement === input,
                borderWidth: style.borderTopWidth,
                borderColor: style.borderTopColor
              };
            })()"""
        )
    }
    evaluate(
        """(() => {
          const input = document.querySelector('[data-v2-form="card"]').elements.name;
          input.blur();
          input.closest('.field').classList.remove('is-invalid');
          input.removeAttribute('aria-invalid');
          input.disabled = true;
        })()"""
    )
    time.sleep(0.15)
    input_states["disabled"] = evaluate(
        """(() => {
          const style = getComputedStyle(document.querySelector('[data-v2-form="card"]').elements.name);
          return {borderColor: style.borderTopColor, color: style.color};
        })()"""
    )
    evaluate(
        """(() => {
          const input = document.querySelector('[data-v2-form="card"]').elements.name;
          input.disabled = false;
          input.readOnly = true;
        })()"""
    )
    time.sleep(0.15)
    input_states["readonly"] = evaluate(
        """(() => {
          const style = getComputedStyle(document.querySelector('[data-v2-form="card"]').elements.name);
          return {borderColor: style.borderTopColor, color: style.color};
        })()"""
    )
    evaluate("document.querySelector('[data-v2-form=\"card\"]').elements.name.readOnly = false")
    check(
        "ADS Input focus, disabled, and read-only states are tokenized",
        input_states == {
            "focus": {
                "active": True,
                "borderWidth": "2px",
                "borderColor": "rgb(64, 69, 194)",
            },
            "disabled": {
                "borderColor": "rgba(15, 18, 20, 0.05)",
                "color": "rgba(15, 18, 20, 0.3)",
            },
            "readonly": {
                "borderColor": "rgba(15, 18, 20, 0.2)",
                "color": "rgb(30, 37, 40)",
            },
        },
        json.dumps(input_states),
    )
    evaluate(
        "document.querySelector('[data-field=\"v2-effective-start\"] button').setAttribute('aria-disabled', 'true')"
    )
    time.sleep(0.15)
    date_states = {
        "disabled": evaluate(
            """(() => {
              const trigger = document.querySelector('[data-field="v2-effective-start"] button');
              return {
                borderColor: getComputedStyle(trigger).borderTopColor,
                color: getComputedStyle(trigger.querySelector('.ads-datepicker__value')).color
              };
            })()"""
        )
    }
    evaluate(
        """(() => {
          const trigger = document.querySelector('[data-field="v2-effective-start"] button');
          trigger.removeAttribute('aria-disabled');
          trigger.setAttribute('aria-readonly', 'true');
        })()"""
    )
    time.sleep(0.15)
    date_states["readonly"] = evaluate(
        """(() => {
          const trigger = document.querySelector('[data-field="v2-effective-start"] button');
          return {
            borderColor: getComputedStyle(trigger).borderTopColor,
            color: getComputedStyle(trigger.querySelector('.ads-datepicker__value')).color
          };
        })()"""
    )
    evaluate(
        "document.querySelector('[data-field=\"v2-effective-start\"] button').removeAttribute('aria-readonly')"
    )
    check(
        "ADS Date Picker disabled and read-only states are tokenized",
        date_states == {
            "disabled": {
                "borderColor": "rgba(15, 18, 20, 0.05)",
                "color": "rgba(15, 18, 20, 0.3)",
            },
            "readonly": {
                "borderColor": "rgba(15, 18, 20, 0.2)",
                "color": "rgb(30, 37, 40)",
            },
        },
        json.dumps(date_states),
    )
    initial_geometry = evaluate(
        """(() => {
          const left = document.querySelector('.create-md__workspace').getBoundingClientRect();
          const right = document.querySelector('.create-md__detail').getBoundingClientRect();
          return {
            left: [left.x, left.y, left.width, left.height, left.bottom],
            right: [right.x, right.y, right.width, right.height, right.bottom],
            overflow: getComputedStyle(document.querySelector('.create-md__detail')).overflowY,
            documentWidth: document.documentElement.scrollWidth
          };
        })()"""
    )
    check(
        "Initial geometry preserves columns with shared outer height",
        initial_geometry["left"][:4] == [76, 75, 878, 736]
        and initial_geometry["right"][:4] == [966, 75, 462, 736]
        and initial_geometry["left"][4] == initial_geometry["right"][4]
        and initial_geometry["overflow"] == "hidden"
        and initial_geometry["documentWidth"] == 1440,
        json.dumps(initial_geometry),
    )
    create_spacing = evaluate(
        """(() => {
          const title = document.querySelector('[data-v2-title]').getBoundingClientRect();
          const helper = document.querySelector('[data-v2-helper]').getBoundingClientRect();
          const tab = document.querySelector('[data-v2-tab="lines"]').getBoundingClientRect();
          const tabs = document.querySelector('.create-md__tabs').getBoundingClientRect();
          return {
            title: [Math.round(title.left), Math.round(title.top), Math.round(title.height)],
            helper: [Math.round(helper.left), Math.round(helper.top), Math.round(helper.height)],
            tab: [Math.round(tab.left), Math.round(tab.top), Math.round(tab.height)],
            tabsTop: Math.round(tabs.top),
            titleToHelper: Math.round(helper.top - title.bottom),
            helperToTab: Math.round(tab.top - helper.bottom)
          };
        })()"""
    )
    check(
        "Create heading and ADS Tabs match Figma 450:7895 vertical rhythm",
        create_spacing["title"] == [98, 139, 38]
        and create_spacing["helper"] == [98, 181, 22]
        and create_spacing["tab"] == [87, 214, 31]
        and create_spacing["tabsTop"] == 203
        and create_spacing["titleToHelper"] == 4
        and create_spacing["helperToTab"] == 11,
        json.dumps(create_spacing),
    )
    check(
        "CARD rows use equal two-column ADS grids and full-width fields",
        evaluate(
            """(() => {
              const form = document.querySelector('[data-v2-form="card"]');
              const rect = name => {
                const control = form.elements[name];
                const trigger = control.closest('.ads-dd')?.querySelector('.ads-dd__trigger');
                return (trigger || control).getBoundingClientRect();
              };
              const start = form.querySelector('[data-field="v2-effective-start"] button').getBoundingClientRect();
              const end = form.querySelector('[data-field="v2-effective-end"] button').getBoundingClientRect();
              const full = ['name','buyingEntityId','buyingEntityName','dcmRuleOrder'].map(rect);
              const market = rect('marketplace');
              const season = rect('dealSeason');
              const focusables = [...form.querySelectorAll(
                'input:not([type="hidden"]), select:not([hidden]), button'
              )].map(control => {
                const dropdown = control.closest('.ads-dd[data-dropdown-control]');
                const native = dropdown && form.elements[dropdown.dataset.dropdownControl];
                return control.name || native?.name || control.closest('[data-field]')?.dataset.field;
              });
              return full.every(control => control.width === full[0].width)
                && market.width === season.width && market.y === season.y
                && start.width === end.width && start.y === end.y
                && market.width < full[0].width && start.width < full[0].width
                && focusables.join('|') === [
                  'name','buyingEntityId','buyingEntityName','marketplace','dealSeason',
                  'v2-effective-start','v2-effective-end','dcmRuleOrder'
                ].join('|');
            })()"""
        ),
    )
    check(
        "Tabs, accordions, and CARD fields expose accessible semantics",
        evaluate(
            """(() => {
              const tabs = [...document.querySelectorAll('[data-v2-tab]')];
              const accordions = [...document.querySelectorAll('[data-v2-accordion]')];
              const form = document.querySelector('[data-v2-form="card"]');
              const named = ['name','marketplace','dealSeason','buyingEntityId','buyingEntityName'];
              return tabs.length === 2
                && tabs.every(tab => tab.getAttribute('role') === 'tab'
                  && tab.hasAttribute('aria-selected') && tab.hasAttribute('aria-controls'))
                && accordions.every(item => {
                  const button = item.querySelector('button');
                  return button.hasAttribute('aria-expanded') && button.hasAttribute('aria-controls');
                })
                && named.every(name => {
                  const control = form.elements[name];
                  return control.id && !!document.querySelector('label[for="' + control.id + '"]');
                })
                && ['v2-effective-start','v2-effective-end'].every(field => {
                  const trigger = document.querySelector('[data-field="' + field + '"] button');
                  return trigger.getAttribute('aria-haspopup') === 'dialog'
                    && !!trigger.getAttribute('aria-labelledby');
                });
            })()"""
        ),
    )
    check(
        "Save Rate Card begins disabled",
        evaluate("document.querySelector('[data-v2-action=\"save-card\"]').disabled"),
    )
    evaluate(
        """(() => {
          window.__qaLineBeforeValidation =
            document.querySelector('[data-v2-accordion="line"]').getBoundingClientRect().top;
          document.querySelector('[data-v2-form="card"]').elements.effectiveStart.value = '';
          const trigger = document.querySelector('[data-field="v2-effective-start"] button');
          trigger.focus();
          window.__qaDateTriggerFocused = document.activeElement === trigger;
        })()"""
    )
    time.sleep(0.05)
    evaluate(
        """(() => {
          const form = document.querySelector('[data-v2-form="card"]');
          const trigger = document.querySelector('[data-field="v2-effective-start"] button');
          trigger.dispatchEvent(new FocusEvent('blur', {
            bubbles: false,
            relatedTarget: form.elements.name
          }));
          form.elements.name.focus();
        })()"""
    )
    time.sleep(0.1)
    date_alignment = evaluate(
        """(() => {
              const form = document.querySelector('[data-v2-form="card"]');
              const startField = form.querySelector('[data-field="v2-effective-start"]').closest('.field');
              const endField = form.querySelector('[data-field="v2-effective-end"]').closest('.field');
              const startTrigger = startField.querySelector('button').getBoundingClientRect();
              const endTrigger = endField.querySelector('button').getBoundingClientRect();
              const slots = [startField, endField].map(field =>
                field.querySelector('.create-md__validation-slot').getBoundingClientRect());
              return {
                errorVisible: !form.querySelector('[data-v2-error="effectiveStart"]').hidden,
                startY: startTrigger.y, endY: endTrigger.y,
                startWidth: startTrigger.width, endWidth: endTrigger.width,
                startSlotHeight: slots[0].height, endSlotHeight: slots[1].height,
                startValue: form.elements.effectiveStart.value,
                activeId: document.activeElement.id,
                triggerInvalid: startField.querySelector('button').getAttribute('aria-invalid'),
                triggerWasFocused: window.__qaDateTriggerFocused,
                lineBefore: window.__qaLineBeforeValidation,
                lineAfter: document.querySelector('[data-v2-accordion="line"]').getBoundingClientRect().top
              };
            })()"""
    )
    check(
        "Effective Start validation preserves two-column row alignment",
        date_alignment
        and date_alignment["errorVisible"]
        and date_alignment["startY"] == date_alignment["endY"]
        and date_alignment["startWidth"] == date_alignment["endWidth"]
        and date_alignment["startSlotHeight"] > date_alignment["endSlotHeight"]
        and date_alignment["lineBefore"] == date_alignment["lineAfter"],
        json.dumps(date_alignment),
    )
    evaluate("document.querySelector('[data-field=\"v2-effective-start\"] button').click()")
    time.sleep(0.15)
    initial_calendar_focus = evaluate(
        """(() => {
          const trigger = document.querySelector('[data-field="v2-effective-start"] button');
          const pop = document.querySelector('body > .ads-datepicker__popover:not([hidden])');
          const day = document.activeElement.closest && document.activeElement.closest('.ads-cal__day');
          return {
            expanded: trigger.getAttribute('aria-expanded'),
            portaled: Boolean(pop),
            focusedIso: day && day.dataset.iso
          };
        })()"""
    )
    check(
        "Date Picker opens in a portal and focuses the day grid",
        initial_calendar_focus
        and initial_calendar_focus["expanded"] == "true"
        and initial_calendar_focus["portaled"]
        and bool(initial_calendar_focus["focusedIso"]),
        json.dumps(initial_calendar_focus),
    )
    screenshot("date-picker-open")
    evaluate(
        """(() => {
          const day = document.activeElement;
          day.dispatchEvent(new KeyboardEvent('keydown', {key:'ArrowRight', bubbles:true}));
        })()"""
    )
    moved_calendar_focus = evaluate(
        "document.activeElement.closest('.ads-cal__day')?.dataset.iso"
    )
    check(
        "Date Picker arrow-key navigation moves one day",
        initial_calendar_focus
        and moved_calendar_focus
        and moved_calendar_focus != initial_calendar_focus["focusedIso"],
        f"before={initial_calendar_focus and initial_calendar_focus['focusedIso']} after={moved_calendar_focus}",
    )
    evaluate(
        "document.activeElement.dispatchEvent(new KeyboardEvent('keydown', {key:'Escape', bubbles:true}))"
    )
    check(
        "Date Picker Escape closes and returns focus",
        evaluate(
            """(() => {
              const trigger = document.querySelector('[data-field="v2-effective-start"] button');
              return trigger.getAttribute('aria-expanded') === 'false'
                && document.activeElement === trigger;
            })()"""
        ),
    )
    evaluate("document.querySelector('[data-field=\"v2-effective-start\"] button').click()")
    month_before = evaluate(
        "document.querySelector('body > .ads-datepicker__popover .ads-cal__title').textContent"
    )
    evaluate(
        "document.querySelector('body > .ads-datepicker__popover [data-cal-nav=\"next\"]').click()"
    )
    time.sleep(0.1)
    month_after = evaluate(
        "document.querySelector('body > .ads-datepicker__popover .ads-cal__title').textContent"
    )
    check(
        "Date Picker month navigation updates the grid and retains focus",
        month_before != month_after
        and evaluate(
            "document.activeElement.getAttribute('data-cal-nav') === 'next'"
        ),
        f"before={month_before} after={month_after}",
    )
    selected_iso = evaluate(
        """(() => {
          const day = document.querySelector('body > .ads-datepicker__popover .ads-cal__day:not(.is-out-of-month)');
          const iso = day.dataset.iso;
          day.click();
          return iso;
        })()"""
    )
    check(
        "Date Picker selection stores ISO, formats display, and returns focus",
        evaluate(
            f"""(() => {{
              const picker = document.querySelector('[data-field="v2-effective-start"]');
              const trigger = picker.querySelector('button');
              const iso = {json.dumps(selected_iso)};
              const expectedDisplay = iso.slice(5, 7) + '/' + iso.slice(8, 10) + '/' + iso.slice(0, 4);
              return picker.querySelector('input[type="hidden"]').value === {json.dumps(selected_iso)}
                && picker.querySelector('.ads-datepicker__value').textContent === expectedDisplay
                && document.activeElement === trigger;
            }})()"""
        ),
    )

    evaluate(
        """(() => {
          const name = document.querySelector('[data-v2-form="card"]').elements.name;
          name.value = ' \\t ';
          name.dispatchEvent(new Event('input', {bubbles:true}));
        })()"""
    )
    check(
        "Whitespace-only name keeps initial state",
        evaluate(
            """document.querySelector('[data-v2-root]').dataset.workspaceState === 'initial'
            && document.querySelector('[data-v2-title]').textContent === 'Create New Rate Card'
            && !document.querySelector('[data-v2-helper]').hidden"""
        ),
    )
    evaluate(
        """(() => {
          const name = document.querySelector('[data-v2-form="card"]').elements.name;
          name.value = 'F';
          name.dispatchEvent(new Event('input', {bubbles:true}));
        })()"""
    )
    check(
        "First character updates the heading and removes helper layout space",
        evaluate(
            """(() => {
              const helper = document.querySelector('[data-v2-helper]');
              const tabs = document.querySelector('.create-md__tabs');
              return document.querySelector('[data-v2-root]').dataset.workspaceState === 'named'
                && document.querySelector('[data-v2-title]').textContent === 'F'
                && helper.hidden && helper.getClientRects().length === 0
                && tabs.getBoundingClientRect().top < window.__qaEmptyTabsTop;
            })()"""
        ),
    )
    evaluate(
        """(() => {
          const name = document.querySelector('[data-v2-form="card"]').elements.name;
          name.value = '  WPP Upfront  ';
          name.dispatchEvent(new Event('input', {bubbles:true}));
        })()"""
    )
    check(
        "Named heading trims display whitespace without changing the input",
        evaluate(
            """document.querySelector('[data-v2-title]').textContent === 'WPP Upfront'
            && document.querySelector('[data-v2-form="card"]').elements.name.value === '  WPP Upfront  '
            && document.querySelector('[data-v2-helper]').hidden"""
        ),
    )
    evaluate(
        """(() => {
          const name = document.querySelector('[data-v2-form="card"]').elements.name;
          name.value = 'WPP Upfront Revised';
          name.dispatchEvent(new Event('input', {bubbles:true}));
        })()"""
    )
    check(
        "Editing the name updates the Create heading live",
        evaluate(
            """document.querySelector('[data-v2-title]').textContent === 'WPP Upfront Revised'
            && document.querySelector('[data-v2-helper]').hidden"""
        ),
    )
    evaluate(
        """(() => {
          const name = document.querySelector('[data-v2-form="card"]').elements.name;
          name.value = '';
          name.dispatchEvent(new Event('input', {bubbles:true}));
        })()"""
    )
    check(
        "Clearing name restores initial state",
        evaluate(
            """document.querySelector('[data-v2-root]').dataset.workspaceState === 'initial'
            && document.querySelector('[data-v2-title]').textContent === 'Create New Rate Card'
            && !document.querySelector('[data-v2-helper]').hidden"""
        ),
    )

    evaluate(
        """(() => {
          const values = {
            name: 'WPP Disney+ Upfront 2025-2026',
            marketplace: 'Upfront',
            dealSeason: '2025-2026',
            buyingEntityId: '0014100000c4mPnAAI',
            buyingEntityName: 'WPP',
            dcmRuleOrder: '17',
            effectiveStart: '2025-10-01'
          };
          const form = document.querySelector('[data-v2-form="card"]');
          Object.entries(values).forEach(([name, value]) => {
            const el = form.elements[name];
            el.value = value;
            el.dispatchEvent(new Event('input', {bubbles:true}));
            el.dispatchEvent(new Event('change', {bubbles:true}));
          });
          form.querySelector('[data-field="v2-effective-start"] button').focus();
          form.elements.name.focus();
          form.elements.name.dispatchEvent(new FocusEvent('focusout', {bubbles:true}));
        })()"""
    )
    time.sleep(0.35)
    check(
        "Complete Rate Card name remains the live heading",
        evaluate(
            """document.querySelector('[data-v2-title]').textContent === 'WPP Disney+ Upfront 2025-2026'
            && document.querySelector('[data-v2-helper]').hidden
            && document.querySelector('[data-v2-title-caption]').hidden
            && document.querySelector('[data-v2-form="card"]').elements.name.value === 'WPP Disney+ Upfront 2025-2026'"""
        ),
    )
    check(
        "Missing Effective End keeps save actions disabled",
        evaluate("document.querySelector('[data-v2-action=\"save-card\"]').disabled"),
    )
    evaluate(
        """(() => {
          const end = document.querySelector('[data-v2-form="card"]').elements.effectiveEnd;
          end.value = '2026-09-30';
          end.dispatchEvent(new Event('input', {bubbles:true}));
          end.dispatchEvent(new Event('change', {bubbles:true}));
        })()"""
    )
    check(
        "Complete CARD enables Save Rate Card",
        evaluate(
            """!document.querySelector('[data-v2-action="save-card"]').disabled
            && !document.querySelector('[data-v2-action="save-draft"]').disabled"""
        ),
    )
    check(
        "Effective End is required by the approved inventory",
        evaluate(
            """document.querySelector('[data-v2-form="card"]').elements.effectiveEnd.value === '2026-09-30'
            && !document.querySelector('#v2-effective-end-label .field__optional')
            && document.querySelector('[data-field="v2-effective-end"] button').getAttribute('aria-required') === 'true'
            && !document.querySelector('[data-v2-action="save-card"]').disabled"""
        ),
    )
    evaluate(
        """(() => {
          const end = document.querySelector('[data-v2-form="card"]').elements.effectiveEnd;
          end.value = '2025-09-30';
          end.dispatchEvent(new Event('input', {bubbles:true}));
          end.dispatchEvent(new Event('change', {bubbles:true}));
        })()"""
    )
    check(
        "CARD date ordering disables publish when end precedes start",
        evaluate("document.querySelector('[data-v2-action=\"save-card\"]').disabled"),
    )
    evaluate(
        """(() => {
          const end = document.querySelector('[data-v2-form="card"]').elements.effectiveEnd;
          end.value = '2026-09-30';
          end.dispatchEvent(new Event('input', {bubbles:true}));
          end.dispatchEvent(new Event('change', {bubbles:true}));
        })()"""
    )

    evaluate("document.querySelector('[data-v2-empty=\"lines\"] [data-v2-action=\"add-line\"]').click()")
    time.sleep(0.15)
    check(
        "Left Add Line Item opens the shared editor",
        evaluate(
            """document.querySelector('[data-v2-accordion="line"] button').getAttribute('aria-expanded') === 'true'
            && document.querySelectorAll('[data-v2-accordion] button[aria-expanded="true"]').length === 1
            && document.activeElement === document.querySelector('[data-v2-form="line"]').elements.advertiserId"""
        ),
    )
    check(
        "Line uses the approved copy and compact field set",
        evaluate(
            """(() => {
              const form = document.querySelector('[data-v2-form="line"]');
              return !form.elements.namedItem('useBuyingEntity')
                && !form.elements.namedItem('upfrontId')
                && !form.previousElementSibling
                && form.elements.advertiserId.placeholder === 'e.g. ADV-1172-01'
                && form.elements.advertiserName.tagName === 'SELECT'
                && form.elements.advertiserName.options[0].textContent === 'e.g. Ford Motor Company'
                && !form.elements.advertiserName.required
                && form.querySelector('label[for="v2-advertiser-name"] .field__optional').textContent === '(Optional)'
                && form.querySelector('label[for="v2-advertiser-id"] .field__help')
                && form.elements.baseRate.type === 'text'
                && form.elements.baseRate.inputMode === 'decimal'
                && form.elements.baseRate.placeholder === 'e.g. 28.00'
                // Line Conditions is a multi-value chip combobox: a hidden
                // condition1 value plus a search input, so the field can
                // hold several conditions without the rest of the app
                // learning a new shape.
                && form.elements.condition1.type === 'hidden'
                && form.querySelector('[data-line-conditions] input[role="combobox"]')
                && form.querySelector('label[for="v2-line-condition"]')
                  .textContent.replace(/\s+/g, ' ').trim() === 'Line Conditions (Optional)'
                && form.querySelectorAll('[name^="condition"]').length === 1
                && form.querySelector('label[for="v2-rate-type"]').textContent.trim() === 'Cost Method'
                && form.elements.rateType.value === 'CPM'
                && form.elements.rateType.closest('.ads-dd').querySelector('.ads-dd__value').textContent === 'CPM'
                && [...form.elements.baseOffering.options].map(option => option.textContent).join('|')
                  === 'Select Base offering|Disney+ Select|Hulu Select|Disney Streaming Bundle'
                    + '|ESPN Streaming Sports|Disney Streaming Live Events|ABC|FX|Freeform|National Geographic'
                && form.elements.attachToCard.type === 'hidden'
                && form.elements.attachToCard.value.length > 0
                && !form.querySelector('label[for="v2-line-attach"]')
                && document.querySelector('[data-v2-panel="lines"] .create-md__toolbar [data-v2-action="add-line"]').textContent === 'Add Line Item';
            })()"""
        ),
    )
    rate_currency_geometry = evaluate(
        """(() => {
          const form = document.querySelector('[data-v2-form="line"]');
          const rate = form.elements.baseRate.getBoundingClientRect();
          const currency = form.elements.currency.closest('.ads-dd').querySelector('.ads-dd__trigger').getBoundingClientRect();
          return {
            rateTop: rate.top, currencyTop: currency.top,
            rateWidth: rate.width, currencyWidth: currency.width,
            rateHeight: rate.height, currencyHeight: currency.height
          };
        })()"""
    )
    check(
        "Base Rate and Currency use equal ADS paired-field geometry",
        abs(rate_currency_geometry["rateTop"] - rate_currency_geometry["currencyTop"]) <= 0.5
        and abs(rate_currency_geometry["rateWidth"] - rate_currency_geometry["currencyWidth"]) <= 0.5
        and abs(rate_currency_geometry["rateHeight"] - rate_currency_geometry["currencyHeight"]) <= 0.5,
        json.dumps(rate_currency_geometry),
    )
    check(
        "Base Rate accepts decimal text without native spinner controls",
        evaluate(
            """(() => {
              const input = document.querySelector('[data-v2-form="line"] [name="baseRate"]');
              return ['12', '12.5', '25.0000'].every(value => {
                input.value = value;
                input.dispatchEvent(new Event('input', {bubbles:true}));
                return input.value === value;
              }) && input.type === 'text' && input.inputMode === 'decimal';
            })()"""
        ),
    )
    screenshot("line-base-rate")
    check(
        "Ad Type Dropdown begins closed with the ADS placeholder",
        evaluate(
            """(() => {
              const root = document.querySelector('[data-dropdown-control="v2-ad-product"]');
              const trigger = root.querySelector('.ads-dd__trigger');
              const menu = root.querySelector('.ads-dd__menu');
              return trigger.getAttribute('role') === 'combobox'
                && trigger.getAttribute('aria-expanded') === 'false'
                && trigger.getAttribute('aria-controls') === menu.id
                && root.querySelector('.ads-dd__label').textContent === 'Ad Type'
                && root.querySelector('.ads-dd__value').textContent === 'Select Ad Type'
                && menu.hidden
                && root.querySelector('[name="adProduct"]').value === '';
            })()"""
        ),
    )
    dropdown_geometry = evaluate(
        """(() => {
          const root = document.querySelector('[data-dropdown-control="v2-ad-product"]');
          const following = document.querySelector('#v2-base-offering').getBoundingClientRect();
          root.querySelector('.ads-dd__trigger').click();
          const menu = root.querySelector('.ads-dd__menu');
          const trigger = root.querySelector('.ads-dd__trigger');
          const label = root.querySelector('.ads-dd__label');
          const value = root.querySelector('.ads-dd__value');
          const caret = root.querySelector('.ads-dd__caret');
          const caretImage = caret.querySelector('img');
          const after = document.querySelector('#v2-base-offering').getBoundingClientRect();
          const style = getComputedStyle(menu);
          return {
            optionLabels: [...menu.querySelectorAll('[role="option"]')].map(option => option.textContent.trim()),
            expanded: trigger.getAttribute('aria-expanded'),
            hidden: menu.hidden,
            menuPosition: style.position,
            menuWidth: Math.round(menu.getBoundingClientRect().width),
            triggerWidth: Math.round(trigger.getBoundingClientRect().width),
            triggerHeight: Math.round(trigger.getBoundingClientRect().height),
            labelFontSize: getComputedStyle(label).fontSize,
            valueFontSize: getComputedStyle(value).fontSize,
            caretWidth: Math.round(caret.getBoundingClientRect().width),
            caretHeight: Math.round(caret.getBoundingClientRect().height),
            caretLeafWidth: Math.round(caretImage.getBoundingClientRect().width),
            caretLeafHeight: Math.round(caretImage.getBoundingClientRect().height),
            followingBefore: Math.round(following.top),
            followingAfter: Math.round(after.top)
          };
        })()"""
    )
    check(
        # Ad Type stays on the format axis per the 2026-08-04 taxonomy
        # correction (see docs/rcm-base-offering-audit.md): platform and
        # property values live under Base Offering, delivery mechanisms
        # under Line Condition. The sales dataset sells five formats.
        "Ad Type opens as an overlay with all five approved format options",
        dropdown_geometry.get("expanded") == "true"
        and not dropdown_geometry.get("hidden")
        and dropdown_geometry.get("menuPosition") == "absolute"
        and dropdown_geometry.get("menuWidth") == dropdown_geometry.get("triggerWidth")
        and dropdown_geometry.get("followingBefore") == dropdown_geometry.get("followingAfter")
        and dropdown_geometry.get("optionLabels") == [
            "Standard Video",
            "Connected TV Video",
            "Live Event Video",
            "Sports Video",
            "Pause Ad",
        ],
        json.dumps(dropdown_geometry),
    )
    check(
        "Ad Type uses ADS Dropdown Small geometry and typography",
        dropdown_geometry.get("triggerHeight") == 32
        and dropdown_geometry.get("labelFontSize") == "12px"
        and dropdown_geometry.get("valueFontSize") == "13px"
        and dropdown_geometry.get("caretWidth") == 16
        and dropdown_geometry.get("caretHeight") == 16
        and dropdown_geometry.get("caretLeafWidth") == 11
        and dropdown_geometry.get("caretLeafHeight") == 6,
        json.dumps(dropdown_geometry),
    )
    screenshot("ad-product-dropdown-open")
    selected_values = evaluate(
        """(() => {
          const root = document.querySelector('[data-dropdown-control="v2-ad-product"]');
          const trigger = root.querySelector('.ads-dd__trigger');
          const control = root.querySelector('[name="adProduct"]');
          return [...root.querySelectorAll('.ads-dd__option')].map(option => {
            if (trigger.getAttribute('aria-expanded') !== 'true') trigger.click();
            option.click();
            return {
              stored: control.value,
              displayed: root.querySelector('.ads-dd__value').textContent,
              expanded: trigger.getAttribute('aria-expanded'),
              focused: document.activeElement === trigger
            };
          });
        })()"""
    )
    check(
        "Each Ad Type option closes, displays, stores, and returns focus",
        all(
            state.get("stored") == label
            and state.get("displayed") == label
            and state.get("expanded") == "false"
            and state.get("focused")
            for state, label in zip(
                selected_values,
                [
                    "Standard Video",
                    "Connected TV Video",
                    "Live Event Video",
                    "Sports Video",
                    "Pause Ad",
                ],
            )
        ),
        json.dumps(selected_values),
    )
    evaluate(
        """(() => {
          const root = document.querySelector('[data-dropdown-control="v2-ad-product"]');
          root.querySelector('.ads-dd__trigger').click();
          document.querySelector('#v2-advertiser-id').click();
        })()"""
    )
    check(
        "Ad Type closes on outside click",
        evaluate(
            """document.querySelector('#v2-ad-product-trigger').getAttribute('aria-expanded') === 'false'
            && document.querySelector('#v2-ad-product-menu').hidden"""
        ),
    )
    evaluate(
        """(() => {
          const control = document.querySelector('[name="adProduct"]');
          control.value = '';
          window.syncAdsDropdown(control);
          document.querySelector('#v2-ad-product-trigger').focus();
        })()"""
    )
    send("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13})
    send("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13})
    time.sleep(0.05)
    send("Input.dispatchKeyEvent", {"type": "keyDown", "key": "ArrowDown", "code": "ArrowDown", "windowsVirtualKeyCode": 40})
    send("Input.dispatchKeyEvent", {"type": "keyUp", "key": "ArrowDown", "code": "ArrowDown", "windowsVirtualKeyCode": 40})
    send("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13})
    send("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13})
    check(
        "Ad Type supports keyboard opening, navigation, and selection",
        # Enter opens the menu, ArrowDown advances one option, Enter
        # selects. The second option is "Connected TV Video" per the
        # sourced Ad Type taxonomy.
        evaluate(
            """document.querySelector('[name="adProduct"]').value === 'Connected TV Video'
            && document.querySelector('#v2-ad-product-trigger').getAttribute('aria-expanded') === 'false'
            && document.activeElement === document.querySelector('#v2-ad-product-trigger')"""
        ),
    )
    send("Input.dispatchKeyEvent", {"type": "keyDown", "key": " ", "code": "Space", "windowsVirtualKeyCode": 32, "text": " "})
    send("Input.dispatchKeyEvent", {"type": "keyUp", "key": " ", "code": "Space", "windowsVirtualKeyCode": 32})
    time.sleep(0.05)
    space_opened = evaluate("document.querySelector('#v2-ad-product-trigger').getAttribute('aria-expanded') === 'true'")
    send("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27})
    send("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27})
    check(
        "Ad Type supports Space, Escape, and focus restoration",
        space_opened
        and evaluate(
            """document.querySelector('#v2-ad-product-trigger').getAttribute('aria-expanded') === 'false'
            && document.querySelector('#v2-ad-product-menu').hidden
            && document.activeElement === document.querySelector('#v2-ad-product-trigger')
            && document.querySelector('#v2-acc-line-trigger').getAttribute('aria-expanded') === 'true'"""
        ),
    )
    evaluate(
        """(() => {
          const control = document.querySelector('[name="adProduct"]');
          control.value = '';
          window.syncAdsDropdown(control);
        })()"""
    )
    evaluate("document.querySelector('[data-v2-action=\"cancel-line\"]').click()")
    check(
        "Left editor cancel returns focus and adds no row",
        evaluate(
            """document.activeElement === document.querySelector('[data-v2-empty="lines"] [data-v2-action="add-line"]')
            && document.querySelectorAll('[data-v2-tbody="lines"] tr').length === 0"""
        ),
    )
    evaluate("document.querySelector('#v2-acc-line-trigger').click()")
    time.sleep(0.15)
    check(
        "Right LINE box opens the same shared editor",
        evaluate(
            """document.querySelector('[data-v2-accordion="line"] button').getAttribute('aria-expanded') === 'true'
            && document.querySelector('[data-v2-form="line"]').elements.id.value === ''
            && document.activeElement === document.querySelector('[data-v2-form="line"]').elements.advertiserId"""
        ),
    )
    evaluate("document.querySelector('[data-v2-action=\"cancel-line\"]').click()")
    check(
        "Right editor cancel returns focus and adds no row",
        evaluate(
            """document.activeElement === document.querySelector('#v2-acc-line-trigger')
            && document.querySelectorAll('[data-v2-tbody="lines"] tr').length === 0"""
        ),
    )
    evaluate("document.querySelector('[data-v2-empty=\"lines\"] [data-v2-action=\"add-line\"]').click()")
    evaluate(
        """(() => {
          const form = document.querySelector('[data-v2-form="line"]');
          const values = {
            advertiserId:'ADV-1048-01', advertiserName:'The Coca-Cola Company',
            baseOffering:'Disney+ Select', rateType:'CPM', baseRate:'0', currency:'USD'
          };
          Object.entries(values).forEach(([name,value]) => form.elements[name].value = value);
          form.elements.adProduct.value = 'Standard Video';
          form.requestSubmit();
        })()"""
    )
    time.sleep(0.2)
    check(
        "First valid LINE save creates exactly one selected row",
        evaluate(
            """document.querySelectorAll('[data-v2-tbody="lines"] tr').length === 1
            && document.querySelector('[data-v2-tbody="lines"] tr').getAttribute('aria-selected') === 'true'
            && document.querySelector('[data-v2-total="lines"]').textContent === '1'"""
        ),
    )
    check(
        "Selected LINE row uses one continuous ADS background",
        evaluate(
            """(() => {
              const row = document.querySelector('[data-v2-tbody="lines"] tr[aria-selected="true"]');
              const backgrounds = [...row.cells].map(cell => getComputedStyle(cell).backgroundColor);
              return new Set(backgrounds).size === 1
                && backgrounds[0] !== 'rgb(255, 255, 255)'
                && backgrounds[0] !== 'rgba(0, 0, 0, 0)';
            })()"""
        ),
    )
    check(
        "Adding a LINE shows one blue operation toast",
        evaluate(
            """document.querySelector('[data-toast-stack]').firstElementChild
              ?.querySelector('[data-toast-title]').textContent === 'Line item added'
            && document.querySelector('[data-toast-stack]').firstElementChild
              ?.dataset.variant === 'info'"""
        ),
    )
    evaluate("document.querySelector('[data-v2-form=\"line\"]').requestSubmit()")
    time.sleep(0.2)
    check(
        "Editing a LINE shows the updated operation toast",
        evaluate(
            """document.querySelector('[data-toast-stack]').firstElementChild
              ?.querySelector('[data-toast-title]').textContent === 'Line item updated'
            && document.querySelectorAll('[data-v2-tbody="lines"] tr').length === 1"""
        ),
    )
    evaluate(
        """(() => {
          document.querySelector('[data-v2-action="cancel-line"]').click();
          document.querySelector('#v2-acc-line-trigger').click();
          const form = document.querySelector('[data-v2-form="line"]');
          form.elements.advertiserId.value = 'ADV-1172-01';
          form.elements.advertiserName.value = 'Ford Motor Company';
          form.elements.baseOffering.value = 'Hulu Select';
          form.elements.rateType.value = 'CPM';
          form.elements.baseRate.value = '12';
          form.elements.currency.value = 'USD';
          form.elements.adProduct.value = 'Pause Ad';
          form.requestSubmit();
        })()"""
    )
    time.sleep(0.2)
    check(
        "Second valid LINE save creates exactly two rows",
        evaluate("document.querySelectorAll('[data-v2-tbody=\"lines\"] tr').length === 2"),
    )
    evaluate(
        """(() => {
          document.querySelector('[data-v2-action="cancel-line"]').click();
          document.querySelector('[data-v2-panel="lines"] .create-md__toolbar [data-v2-action="add-line"]').click();
          const form = document.querySelector('[data-v2-form="line"]');
          form.elements.advertiserId.value = 'ADV-1459-01';
          form.elements.advertiserName.value = 'Capital One';
          form.elements.baseOffering.value = 'ESPN Streaming Sports';
          form.elements.rateType.value = 'CPM';
          form.elements.baseRate.value = '12.5';
          form.elements.currency.value = 'USD';
          form.elements.adProduct.value = 'Sports Video';
          form.requestSubmit();
        })()"""
    )
    time.sleep(0.2)
    check(
        "Third valid LINE save creates exactly three stable rows",
        evaluate(
            """(() => {
              const rows = [...document.querySelectorAll('[data-v2-tbody="lines"] tr')];
              const ids = rows.map(row => row.dataset.v2RowId);
              return rows.length === 3 && new Set(ids).size === 3 && ids.every(Boolean);
            })()"""
        ),
    )
    evaluate(
        """(() => {
          document.querySelector('[data-v2-action="cancel-line"]').click();
          document.querySelector('[data-v2-panel="lines"] .create-md__toolbar [data-v2-action="add-line"]').click();
          document.querySelector('[data-v2-action="cancel-line"]').click();
        })()"""
    )
    check(
        "Canceling a fourth LINE adds no row",
        evaluate("document.querySelectorAll('[data-v2-tbody=\"lines\"] tr').length === 3"),
    )
    evaluate(
        """(() => {
          document.querySelector('#v2-acc-line-trigger').click();
          document.querySelector('[data-v2-form="line"]').requestSubmit();
        })()"""
    )
    check(
        "Invalid LINE submission adds no row and associates an error",
        evaluate(
            """document.querySelectorAll('[data-v2-tbody="lines"] tr').length === 3
            && document.activeElement.getAttribute('aria-invalid') === 'true'
            && !!document.activeElement.getAttribute('aria-describedby')"""
        ),
    )
    evaluate("document.querySelector('[data-v2-action=\"cancel-line\"]').click()")
    evaluate(
        """(() => {
          document.querySelector('[data-v2-panel="lines"] .create-md__toolbar [data-v2-action="add-line"]').click();
          const form = document.querySelector('[data-v2-form="line"]');
          form.elements.advertiserId.value = 'ADV-1195-01';
          form.elements.advertiserName.value = 'Target';
          form.elements.baseOffering.value = 'Disney+ Select';
          form.elements.rateType.value = 'CPM';
          form.elements.baseRate.value = '25.0000';
          form.elements.currency.value = 'USD';
          form.elements.adProduct.value = 'Standard Video';
          form.requestSubmit();
          form.requestSubmit();
        })()"""
    )
    time.sleep(0.2)
    check(
        "Repeated submit creates one LINE without duplication",
        evaluate("document.querySelectorAll('[data-v2-tbody=\"lines\"] tr').length === 4"),
    )
    remove_line_ghost = evaluate(
        """(() => {
          document.querySelector('[data-v2-tbody="lines"] tr').click();
          const remove = document.querySelector('[data-v2-action="request-remove-line"]');
          const cancel = document.querySelector('[data-v2-action="cancel-line"]');
          const save = document.querySelector('[data-v2-line-submit]');
          const rect = remove.getBoundingClientRect();
          const cancelRect = cancel.getBoundingClientRect();
          const saveRect = save.getBoundingClientRect();
          const style = getComputedStyle(remove);
          return {
            text: remove.textContent.trim(),
            ghost: remove.classList.contains('btn--ghost'),
            danger: remove.classList.contains('btn--danger'),
            hidden: remove.hidden,
            geometry: [
              Math.round(rect.height),
              style.paddingTop,
              style.paddingRight,
              style.borderRadius
            ],
            typography: [
              style.fontFamily,
              style.fontSize,
              style.fontWeight,
              style.lineHeight
            ],
            rest: [style.color, style.backgroundColor, style.borderWidth],
            alignment: [
              rect.left < cancelRect.left,
              Math.round(saveRect.left - cancelRect.right)
            ]
          };
        })()"""
    )
    check(
        "Remove Line Item reuses the default-size ADS Ghost Button",
        remove_line_ghost["text"] == "Remove Line Item"
        and remove_line_ghost["ghost"]
        and not remove_line_ghost["danger"]
        and not remove_line_ghost["hidden"]
        and remove_line_ghost["geometry"] == [36, "8px", "12px", "6px"]
        and remove_line_ghost["typography"]
        == ['"Open Sans", sans-serif', "14px", "600", "20px"]
        and remove_line_ghost["rest"]
        == ["rgb(81, 88, 91)", "rgba(0, 0, 0, 0)", "0px"]
        and remove_line_ghost["alignment"] == [True, 8],
        json.dumps(remove_line_ghost),
    )
    remove_modal = evaluate(
        """(() => {
          const trigger = document.querySelector('[data-v2-action="request-remove-line"]');
          const modal = document.querySelector('[data-v2-remove-modal]');
          const open = () => trigger.click();
          open();
          const panel = modal.querySelector('.modal__panel');
          const header = modal.querySelector('.modal__header');
          const body = modal.querySelector('.modal__body');
          const footer = modal.querySelector('.modal__footer');
          const title = modal.querySelector('.modal__title');
          const close = modal.querySelector('.modal__close');
          const closeIcon = modal.querySelector('.modal__close-icon');
          const cancel = footer.querySelector('[data-v2-action="cancel-remove-line"]');
          const confirm = footer.querySelector('[data-v2-action="confirm-remove-line"]');
          const panelStyle = getComputedStyle(panel);
          const headerStyle = getComputedStyle(header);
          const bodyStyle = getComputedStyle(body);
          const footerStyle = getComputedStyle(footer);
          const titleStyle = getComputedStyle(title);
          const closeStyle = getComputedStyle(close);
          const closeIconStyle = getComputedStyle(closeIcon);
          const lineForm = document.querySelector('[data-v2-form="line"]');
          const initial = {
            semantics: [
              modal.getAttribute('role'),
              modal.getAttribute('aria-modal'),
              modal.getAttribute('aria-labelledby'),
              modal.getAttribute('aria-describedby')
            ],
            copy: [
              title.textContent.trim(),
              modal.querySelector('.modal__body-text').textContent.trim(),
              modal.querySelector('.modal__summary-label').textContent.trim(),
              modal.querySelector('[data-v2-remove-target]').textContent.trim()
            ],
            selectedAdvertiser:
              lineForm.elements.advertiserName.value
              || lineForm.elements.advertiserId.value,
            panel: [
              Math.round(panel.getBoundingClientRect().width),
              panelStyle.borderRadius,
              panelStyle.backgroundColor,
              panelStyle.borderColor,
              panelStyle.boxShadow
            ],
            padding: [
              headerStyle.padding,
              bodyStyle.padding,
              footerStyle.padding,
              footerStyle.gap
            ],
            titleType: [
              titleStyle.fontFamily,
              titleStyle.fontSize,
              titleStyle.fontWeight,
              titleStyle.lineHeight,
              titleStyle.letterSpacing
            ],
            close: [
              Math.round(close.getBoundingClientRect().width),
              Math.round(closeIcon.getBoundingClientRect().width),
              closeStyle.borderRadius,
              closeIconStyle.maskImage.includes('ads-modal-close.svg')
            ],
            scrim: getComputedStyle(modal.querySelector('.modal__scrim')).backgroundColor,
            warningIcons: modal.querySelectorAll('.modal__warning-icon').length,
            buttons: [
              cancel.className,
              confirm.className,
              cancel.textContent.trim(),
              confirm.textContent.trim()
            ],
            // Every confirmation in the app opens on its Cancel button, so
            // Enter on arrival never destroys anything.
            focused: document.activeElement === cancel,
            backgroundInert: document.querySelector('.create-md__workspace').inert
              && document.querySelector('.create-md__detail').inert
          };
          confirm.focus();
          confirm.dispatchEvent(new KeyboardEvent('keydown', {
            key: 'Tab', bubbles: true, cancelable: true
          }));
          const forwardTrap = document.activeElement === close;
          close.dispatchEvent(new KeyboardEvent('keydown', {
            key: 'Tab', shiftKey: true, bubbles: true, cancelable: true
          }));
          const backwardTrap = document.activeElement === confirm;
          confirm.dispatchEvent(new KeyboardEvent('keydown', {
            key: 'Escape', bubbles: true, cancelable: true
          }));
          const escape = modal.hidden
            && document.activeElement === trigger
            && !document.querySelector('[inert]');
          open();
          modal.querySelector('.modal__scrim').click();
          const backdrop = modal.hidden && document.activeElement === trigger;
          open();
          close.click();
          const closeButton = modal.hidden && document.activeElement === trigger;
          open();
          cancel.click();
          const cancelButton = modal.hidden && document.activeElement === trigger;
          return {
            initial,
            trap: [forwardTrap, backwardTrap],
            dismiss: [escape, backdrop, closeButton, cancelButton]
          };
        })()"""
    )
    check(
        "Remove confirmation uses the official ADS Default Modal anatomy",
        remove_modal["initial"]["semantics"]
        == ["alertdialog", "true", "v2-remove-title", "v2-remove-body"]
        and remove_modal["initial"]["copy"][:3]
        == [
            "Remove this line item?",
            "This line item will be removed from the rate card. This action cannot be undone.",
            "Advertiser",
        ]
        and remove_modal["initial"]["copy"][3]
        == remove_modal["initial"]["selectedAdvertiser"]
        and remove_modal["initial"]["panel"]
        == [480, "12px", "rgb(255, 255, 255)", "rgba(15, 18, 20, 0.1)", "none"]
        and remove_modal["initial"]["padding"]
        == ["20px 24px", "16px 24px", "16px 24px", "12px"]
        and remove_modal["initial"]["titleType"]
        == ['"Open Sans", -apple-system, "system-ui", sans-serif',
            "18px", "600", "24px", "normal"]
        and remove_modal["initial"]["close"] == [24, 15, "3px", True]
        and remove_modal["initial"]["scrim"] == "rgba(0, 0, 0, 0.5)"
        and remove_modal["initial"]["warningIcons"] == 0
        and remove_modal["initial"]["buttons"]
        == [
            "btn btn--secondary",
            "btn btn--primary",
            "Cancel",
            "Remove line item",
        ],
        json.dumps(remove_modal),
    )
    check(
        "ADS remove modal traps focus, inerts the page, and restores focus on dismiss",
        remove_modal["initial"]["focused"]
        and remove_modal["initial"]["backgroundInert"]
        and remove_modal["trap"] == [True, True]
        and remove_modal["dismiss"] == [True, True, True, True],
        json.dumps(remove_modal),
    )
    viewport(768, 1024)
    compact_modal = evaluate(
        """(() => {
          document.querySelector('[data-v2-action="request-remove-line"]').click();
          const modal = document.querySelector('[data-v2-remove-modal]');
          const panel = modal.querySelector('.modal__panel');
          const body = modal.querySelector('.modal__body');
          const rect = panel.getBoundingClientRect();
          return {
            open: !modal.hidden,
            withinViewport:
              rect.left >= 0 && rect.top >= 0
              && rect.right <= document.documentElement.clientWidth + 1
              && rect.bottom <= document.documentElement.clientHeight + 1,
            bodyScrollOwner: getComputedStyle(body).overflowY === 'auto',
            pageHorizontalOverflow:
              document.documentElement.scrollWidth
                > document.documentElement.clientWidth,
          };
        })()"""
    )
    check(
        "ADS remove modal fits the tablet portrait viewport",
        compact_modal["open"]
        and compact_modal["withinViewport"]
        and compact_modal["bodyScrollOwner"]
        and not compact_modal["pageHorizontalOverflow"],
        json.dumps(compact_modal),
    )
    evaluate(
        """document.querySelector(
          '[data-v2-remove-modal] [data-v2-action="cancel-remove-line"]'
        ).click()"""
    )
    viewport(1440, 900)
    removed = evaluate(
        """(() => {
          const row = document.querySelector('[data-v2-tbody="lines"] tr');
          const id = row.dataset.v2RowId;
          const before = Number(document.querySelector('[data-v2-total="lines"]').textContent);
          row.click();
          document.querySelector('[data-v2-action="request-remove-line"]').click();
          const confirm = document.querySelector('[data-v2-action="confirm-remove-line"]');
          confirm.click();
          confirm.click();
          return {
            id,
            before,
            after: Number(document.querySelector('[data-v2-total="lines"]').textContent),
            confirmDisabled: confirm.disabled
          };
        })()"""
    )
    check(
        "Remove line item confirms once and deletes exactly the selected row",
        evaluate(
            f"""document.querySelectorAll('[data-v2-tbody="lines"] tr').length === 3
            && !document.querySelector('[data-v2-row-id="{removed["id"]}"]')"""
        )
        and removed["after"] == removed["before"] - 1
        and removed["confirmDisabled"],
        json.dumps(removed),
    )
    check(
        "Removing a LINE shows the blue operation toast",
        evaluate(
            """document.querySelector('[data-toast-stack]').firstElementChild
              ?.querySelector('[data-toast-title]').textContent === 'Line item removed'"""
        ),
    )
    evaluate(
        """(() => {
          document.querySelector('[data-v2-panel="lines"] .create-md__toolbar [data-v2-action="add-line"]').click();
          const form = document.querySelector('[data-v2-form="line"]');
          form.elements.advertiserId.value = 'ADV-1512-01';
          form.elements.baseOffering.value = 'Disney+ Select';
          form.elements.rateType.value = 'CPM';
          form.elements.baseRate.value = '30';
          form.elements.currency.value = 'USD';
          form.elements.adProduct.value = 'Standard Video';
          form.requestSubmit();
        })()"""
    )
    time.sleep(0.2)
    check(
        "Replacement LINE restores the expected persisted row count",
        evaluate("document.querySelectorAll('[data-v2-tbody=\"lines\"] tr').length === 4"),
    )
    viewport(1440, 960)
    screenshot("new-rate-card-populated")

    evaluate(
        """(() => {
          document.querySelector('[data-v2-tab="premiums"]').click();
          document.querySelector('[data-v2-action="add-premium"]').click();
        })()"""
    )
    time.sleep(0.1)
    check(
        "Premium form follows the approved field order, copy, and paired geometry",
        evaluate(
            """(() => {
              const form = document.querySelector('[data-v2-form="premium"]');
              const labels = [...form.querySelectorAll('.field__label')]
                .map(label => label.textContent.replace(/\\s+/g, ' ').trim());
              const value = form.elements.value.getBoundingClientRect();
              const stack = form.elements.stackOrder.getBoundingClientRect();
              const start = form.querySelector('[data-field="v2-premium-effective-start"] button').getBoundingClientRect();
              const end = form.querySelector('[data-field="v2-premium-effective-end"] button').getBoundingClientRect();
              const calculationTrigger = form.elements.calculationMethod.closest('.ads-dd')
                .querySelector('.ads-dd__trigger').getBoundingClientRect();
              const categoryTrigger = form.elements.category.closest('.ads-dd')
                .querySelector('.ads-dd__trigger').getBoundingClientRect();
              const accordion = form.closest('[data-v2-accordion="premium"]');
              const panelStyle = getComputedStyle(form.closest('.create-md__accordion-panel'));
              return labels.join('|') === [
                  'Calculation Method',
                  'Premium Category',
                  'Premium Display Name (Optional)',
                  'Value',
                  'Application Order (Optional)',
                  'Condition',
                  'Effective Start',
                  'Effective End'
                ].join('|')
                && form.elements.attachToCard.type === 'hidden'
                && !form.querySelector('label[for="v2-premium-attach-card"]')
                && form.elements.category.tagName === 'SELECT'
                && form.elements.category.options[0].textContent === 'Select Category'
                && form.elements.calculationMethod.tagName === 'SELECT'
                && form.elements.calculationMethod.options[0].textContent === 'Select Method'
                && Boolean(
                  form.elements.calculationMethod.compareDocumentPosition(form.elements.category)
                    & Node.DOCUMENT_POSITION_FOLLOWING
                )
                && form.elements.displayName.placeholder === 'e.g. 31-60s'
                && form.querySelector('label[for="v2-premium-name"] .field__label-icon')
                && form.elements.value.type === 'text'
                && form.elements.value.inputMode === 'decimal'
                && form.elements.value.placeholder === 'e.g. 5.0000'
                && form.elements.stackOrder.type === 'text'
                && form.elements.stackOrder.inputMode === 'numeric'
                && form.elements.stackOrder.placeholder === 'e.g. 10'
                && form.elements.condition1.placeholder === 'e.g. Device: Connected TV'
                && !form.elements.condition2 && !form.elements.condition3
                && !form.elements.advertiserName
                && value.top === stack.top && value.width === stack.width && value.height === stack.height
                && start.top === end.top && start.width === end.width && start.height === end.height
                && form.querySelectorAll('.field__helper').length === 0
                && form.querySelector('[data-field="v2-premium-effective-start"] .ads-datepicker__value').textContent === 'Select start date'
                && form.querySelector('[data-field="v2-premium-effective-end"] .ads-datepicker__value').textContent === 'Select end date'
                && calculationTrigger.height === 36
                && categoryTrigger.height === 36
                && start.height === 40 && end.height === 40
                && getComputedStyle(accordion).borderRadius === '8px'
                && panelStyle.padding === '16px 24px'
                && getComputedStyle(form).gap === '16px'
                && [...form.querySelectorAll('.create-md__form-actions button:not([hidden])')]
                  .map(button => button.textContent.trim()).join('|') === 'Cancel|Add Premium';
            })()"""
        ),
    )
    screenshot("premium-form")
    evaluate(
        """(() => {
          const form = document.querySelector('[data-v2-form="premium"]');
          form.elements.displayName.value = 'Unsaved premium';
          form.elements.condition1.value = 'Demographic: Age → Adults 18–49';
          document.querySelector('[data-v2-accordion="card"] button').click();
          document.querySelector('[data-v2-accordion="premium"] button').click();
        })()"""
    )
    check(
        "Premium draft values survive accordion switching",
        evaluate(
            """(() => {
              const form = document.querySelector('[data-v2-form="premium"]');
              return form.elements.displayName.value === 'Unsaved premium'
                && form.elements.condition1.value === 'Demographic: Age → Adults 18–49'
                && document.querySelector('[data-v2-accordion="premium"] button')
                  .getAttribute('aria-expanded') === 'true';
            })()"""
        ),
    )
    evaluate(
        """(() => {
          const form = document.querySelector('[data-v2-form="premium"]');
          form.elements.calculationMethod.value = 'Percent Adjustment';
          form.elements.value.value = '5';
          form.elements.effectiveStart.value = '2024-10-01';
          form.elements.effectiveEnd.value = '2024-09-30';
          form.requestSubmit();
        })()"""
    )
    check(
        "Premium dates outside the CARD range fail without creating a record",
        evaluate(
            """document.querySelectorAll('[data-v2-tbody="premiums"] tr').length === 0
            && document.querySelector('[data-field="v2-premium-effective-start"] button')
              .getAttribute('aria-invalid') === 'true'
            && document.querySelector('[data-field="v2-premium-effective-end"] button')
              .getAttribute('aria-invalid') === 'true'"""
        ),
    )
    evaluate(
        """(() => {
          const form = document.querySelector('[data-v2-form="premium"]');
          form.elements.category.value = 'Duration';
          form.elements.displayName.value = 'Demographic Guarantee Premium';
          form.elements.calculationMethod.value = 'Percent Adjustment';
          form.elements.value.value = '-5';
          form.elements.stackOrder.value = '10';
          form.elements.condition1.value = 'Demographic: Age → Adults 18–49';
          form.elements.effectiveStart.value = '2025-10-01';
          form.elements.effectiveEnd.value = '2026-09-30';
          form.requestSubmit();
        })()"""
    )
    time.sleep(0.2)
    check(
        "Premium allows negatives and creates one selected row",
        evaluate(
            """document.querySelectorAll('[data-v2-tbody="premiums"] tr').length === 1
            && document.querySelector('[data-v2-tbody="premiums"] tr').getAttribute('aria-selected') === 'true'
            && document.querySelector('[data-v2-form="premium"] [name="effectiveStart"]').value === '2025-10-01'
            && document.querySelector('[data-field="v2-premium-effective-start"] .ads-datepicker__value').textContent === '10/01/2025'
            && document.querySelector('[data-field="v2-premium-effective-end"] .ads-datepicker__value').textContent === '09/30/2026'"""
        ),
    )
    check(
        "Adding and editing a Premium adjustment use blue operation toasts",
        evaluate(
            """document.querySelector('[data-toast-stack]').firstElementChild
              ?.querySelector('[data-toast-title]').textContent === 'Premium adjustment added'"""
        ),
    )
    evaluate("document.querySelector('[data-v2-form=\"premium\"]').requestSubmit()")
    time.sleep(0.2)
    check(
        "Editing a Premium adjustment shows the updated operation toast",
        evaluate(
            """document.querySelector('[data-toast-stack]').firstElementChild
              ?.querySelector('[data-toast-title]').textContent === 'Premium adjustment updated'
            && document.querySelectorAll('[data-v2-tbody="premiums"] tr').length === 1"""
        ),
    )
    evaluate(
        "document.querySelector('[data-v2-action=\"request-remove-premium\"]').click()"
    )
    time.sleep(0.2)
    check(
        "Remove Premium asks for confirmation before deleting anything",
        evaluate(
            """(() => {
              const modal = document.querySelector('[data-v2-remove-modal]');
              return !modal.hidden
                && modal.querySelector('#v2-remove-title').textContent
                  === 'Remove this premium adjustment?'
                && document.querySelectorAll('[data-v2-tbody="premiums"] tr').length === 1;
            })()"""
        ),
    )
    evaluate(
        "document.querySelector('[data-v2-action=\"confirm-remove-line\"]').click()"
    )
    time.sleep(0.2)
    check(
        "Removing a Premium adjustment updates state and shows a blue toast",
        evaluate(
            """document.querySelectorAll('[data-v2-tbody="premiums"] tr').length === 0
            && document.querySelector('[data-toast-stack]').firstElementChild
              ?.querySelector('[data-toast-title]').textContent === 'Premium adjustment removed'"""
        ),
    )
    evaluate(
        """(() => {
          document.querySelector('[data-v2-tab="premiums"]').click();
          document.querySelector('[data-v2-action="add-premium"]').click();
          const form = document.querySelector('[data-v2-form="premium"]');
          form.elements.category.value = 'Duration';
          form.elements.displayName.value = 'Demographic Guarantee Premium';
          form.elements.calculationMethod.value = 'Percent Adjustment';
          form.elements.value.value = '-5';
          form.elements.stackOrder.value = '10';
          form.elements.condition1.value = 'Demographic: Age → Adults 18–49';
          form.elements.effectiveStart.value = '2025-10-01';
          form.elements.effectiveEnd.value = '2026-09-30';
          form.requestSubmit();
        })()"""
    )
    time.sleep(0.2)

    evaluate("document.querySelector('[data-v2-action=\"save-draft\"]').click()")
    time.sleep(0.2)
    saved_id = evaluate("document.querySelector('[data-v2-card-id]').textContent")
    check(
        "Draft save generates a Rate Card ID on the seeded RC-DAS-<entity>-<marketplace>-<season> convention",
        saved_id.startswith("RC-DAS-WPP-UF-2526-"),
        saved_id,
    )
    check(
        "Save as Draft shows the blue operation toast after persistence",
        evaluate(
            """document.querySelector('[data-toast-stack]').firstElementChild
              ?.querySelector('[data-toast-title]').textContent === 'Rate card saved as draft'"""
        ),
    )
    check(
        "Draft save updates deep link",
        evaluate(
            """new URL(location.href).searchParams.get('mode') === 'edit'
            && new URL(location.href).searchParams.get('cardId') === document.querySelector('[data-v2-card-id]').textContent"""
        ),
    )
    check(
        "Edit heading loads, renames live, keeps approved context, and preserves ID",
        evaluate(
            r"""(() => {
              const form = document.querySelector('[data-v2-form="card"]');
              const input = form.elements.name;
              const helper = document.querySelector('[data-v2-helper]');
              const title = document.querySelector('[data-v2-title]');
              const idBefore = document.querySelector('[data-v2-card-id]').textContent;
              const original = input.value;
              const displayOriginal = original.replace(/\((\d{2})-(\d{2})\)/g, '($1–$2)');
              const approvedHelper = 'Enter the rate card details, then add line items and premium adjustments.';
              const loaded = title.textContent === displayOriginal
                && helper.hidden && helper.textContent.trim() === approvedHelper;
              input.value = 'Renamed WPP Rate Card';
              input.dispatchEvent(new Event('input', {bubbles:true}));
              const renamed = title.textContent === 'Renamed WPP Rate Card'
                && helper.hidden && helper.textContent.trim() === approvedHelper
                && !title.textContent.includes('New Rate Card');
              input.value = '   ';
              input.dispatchEvent(new Event('input', {bubbles:true}));
              const cleared = title.textContent === displayOriginal
                && !helper.hidden && helper.textContent.trim() === approvedHelper;
              input.value = original;
              input.dispatchEvent(new Event('input', {bubbles:true}));
              const result = loaded && renamed && cleared
                && helper.hidden
                && document.querySelector('[data-v2-card-id]').textContent === idBefore
                && document.querySelector('[data-v2-root]').querySelectorAll('h1').length === 1;
              document.querySelector('[data-v2-action="save-draft"]').click();
              return result;
            })()"""
        ),
    )
    check(
        "Complete file persists to isolated storage",
        evaluate(
            """(() => {
              const files = JSON.parse(localStorage.getItem('rate-card-manager.v2.files'));
              const id = document.querySelector('[data-v2-card-id]').textContent;
              const rates = files[id].lines.map(line => line.baseRate);
              return files[id].lines.length === 4 && files[id].premiums.length === 1
                && files[id].card.dealSeason === '2025-2026'
                && files[id].card.dcmRuleOrder === 17
                // The rows were typed at 0, 12, 12.5 and 25, one was
                // removed, and the replacement was typed at 30. Which one
                // the remove took depends on the Updated date sort, so
                // assert the surviving rates come from what was typed.
                && rates.includes(30)
                && rates.every(rate => [0, 12, 12.5, 25, 30].includes(rate))
                && files[id].lines.every(line => line.attachToCard === id)
                && files[id].lines.every(line => !('upfrontId' in line)
                  && !('condition2' in line) && !('condition3' in line) && !('condition4' in line))
                && files[id].premiums.every(premium => premium.attachToCard === id)
                && files[id].premiums.every(premium => !('advertiserName' in premium)
                  && !('condition2' in premium) && !('condition3' in premium))
                && files[id].premiums[0].category === 'Duration'
                && files[id].premiums[0].stackOrder === 10
                && files[id].premiums[0].effectiveStart === '2025-10-01'
                && files[id].premiums[0].effectiveEnd === '2026-09-30';
            })()"""
        ),
    )
    evaluate(
        """(() => {
          const files = JSON.parse(localStorage.getItem('rate-card-manager.v2.files'));
          const id = document.querySelector('[data-v2-card-id]').textContent;
          files[id].lines[0].upfrontId = 'LEGACY-UPFRONT';
          files[id].lines[0].condition2 = 'Legacy device';
          files[id].lines[0].condition3 = 'Legacy format';
          files[id].premiums[0].advertiserName = 'Legacy advertiser';
          files[id].premiums[0].condition2 = 'Legacy premium device';
          files[id].premiums[0].condition3 = 'Legacy premium format';
          localStorage.setItem('rate-card-manager.v2.files', JSON.stringify(files));
        })()"""
    )
    evaluate("location.reload()")
    time.sleep(1.0)
    check(
        "Deep-link refresh restores CARD, LINE, and PREM",
        evaluate(
            """document.querySelector('[data-v2-form="card"]').elements.name.value === 'WPP Disney+ Upfront 2025-2026'
            && document.querySelector('[data-v2-total="lines"]').textContent === '4'
            && document.querySelector('[data-v2-total="premiums"]').textContent === '1'"""
        ),
    )
    evaluate(
        """(() => {
          const files = JSON.parse(localStorage.getItem('rate-card-manager.v2.files'));
          const cardId = document.querySelector('[data-v2-card-id]').textContent;
          const legacy = files[cardId].lines.find(line => line.upfrontId === 'LEGACY-UPFRONT');
          const row = [...document.querySelectorAll('[data-v2-tbody="lines"] tr')]
            .find(candidate => candidate.dataset.v2RowId === legacy.id);
          row.querySelector('[data-v2-action="edit-row"]').click();
          const form = document.querySelector('[data-v2-form="line"]');
          form.elements.baseRate.value = String(Number(form.elements.baseRate.value) + 1);
          form.requestSubmit();
          document.querySelector('[data-v2-action="save-draft"]').click();
        })()"""
    )
    time.sleep(0.15)
    check(
        "Editing a legacy LINE preserves deleted legacy properties without restoring their fields",
        evaluate(
            """(() => {
              const files = JSON.parse(localStorage.getItem('rate-card-manager.v2.files'));
              const id = document.querySelector('[data-v2-card-id]').textContent;
              const legacy = files[id].lines.find(line => line.upfrontId === 'LEGACY-UPFRONT');
              const form = document.querySelector('[data-v2-form="line"]');
              return legacy && legacy.condition2 === 'Legacy device'
                && legacy.condition3 === 'Legacy format'
                && !form.elements.upfrontId && !form.elements.condition2 && !form.elements.condition3;
            })()"""
        ),
    )
    evaluate(
        """(() => {
          document.querySelector('[data-v2-tab="premiums"]').click();
          document.querySelector('[data-v2-tbody="premiums"] [data-v2-action="edit-row"]').click();
          const form = document.querySelector('[data-v2-form="premium"]');
          form.elements.value.value = String(Number(form.elements.value.value) + 1);
          form.requestSubmit();
          document.querySelector('[data-v2-action="save-draft"]').click();
        })()"""
    )
    time.sleep(0.15)
    check(
        "Editing a legacy PREM preserves removed legacy properties without restoring their fields",
        evaluate(
            """(() => {
              const files = JSON.parse(localStorage.getItem('rate-card-manager.v2.files'));
              const id = document.querySelector('[data-v2-card-id]').textContent;
              const legacy = files[id].premiums[0];
              const form = document.querySelector('[data-v2-form="premium"]');
              return legacy.advertiserName === 'Legacy advertiser'
                && legacy.condition2 === 'Legacy premium device'
                && legacy.condition3 === 'Legacy premium format'
                && !form.elements.advertiserName && !form.elements.condition2 && !form.elements.condition3;
            })()"""
        ),
    )
    evaluate("document.querySelector('[data-v2-action=\"save-card\"]').click()")
    time.sleep(0.15)
    check(
        "Save Rate Card publishes the complete file",
        evaluate(
            """(() => {
              const files = JSON.parse(localStorage.getItem('rate-card-manager.v2.files'));
              const id = document.querySelector('[data-v2-card-id]').textContent;
              return files[id].status === 'Published';
            })()"""
        ),
    )
    check(
        "Save Rate Card shows the blue operation toast after persistence",
        evaluate(
            """document.querySelector('[data-toast-stack]').firstElementChild
              ?.querySelector('[data-toast-title]').textContent === 'Rate card saved'"""
        ),
    )
    failed_save_toast = evaluate(
        """(async () => {
          while (document.querySelector('[data-toast]')) {
            window.dismissToast(document.querySelector('[data-toast]'));
            await new Promise(resolve => setTimeout(resolve, 200));
          }
          const original = Storage.prototype.setItem;
          Storage.prototype.setItem = function () { throw new Error('QA storage failure'); };
          document.querySelector('[data-v2-action="save-draft"]').click();
          Storage.prototype.setItem = original;
          await new Promise(resolve => setTimeout(resolve, 260));
          return [...document.querySelectorAll('[data-toast]')].map(toast => ({
            title: toast.querySelector('[data-toast-title]').textContent,
            variant: toast.dataset.variant
          }));
        })()"""
    )
    check(
        "A failed save shows only the ADS error toast",
        failed_save_toast == [
            {"title": "Unable to save rate card", "variant": "error"}
        ],
        json.dumps(failed_save_toast),
    )
    close_operation_stack = evaluate(
        """(async () => {
          while (document.querySelector('[data-toast]')) {
            window.dismissToast(document.querySelector('[data-toast]'));
            await new Promise(resolve => setTimeout(resolve, 200));
          }
          document.querySelector('[data-v2-action="save-draft"]').click();
          document.querySelector('[data-v2-action="save-card"]').click();
          await new Promise(resolve => setTimeout(resolve, 260));
          const toasts = [...document.querySelectorAll('[data-toast]')];
          return {
            titles: toasts.map(toast => toast.querySelector('[data-toast-title]').textContent),
            gap: toasts[1].getBoundingClientRect().top - toasts[0].getBoundingClientRect().bottom
          };
        })()"""
    )
    check(
        "Two successful operations stack once each from the top-right",
        close_operation_stack == {
            "titles": ["Rate card saved", "Rate card saved as draft"],
            "gap": 24,
        },
        json.dumps(close_operation_stack),
    )
    evaluate(
        """(() => {
          document.querySelector('[data-v2-tab="lines"]').click();
          document.querySelector('[data-v2-action="add-line"]').click();
          const form = document.querySelector('[data-v2-form="line"]');
          form.elements.baseRate.value = '12.5.2';
          form.requestSubmit();
        })()"""
    )
    time.sleep(0.1)
    check(
        "Invalid LINE does not create a row and focuses an error",
        evaluate(
            """document.querySelectorAll('[data-v2-tbody="lines"] tr').length === 4
            && document.activeElement.getAttribute('aria-invalid') === 'true'
            && document.querySelector('[data-v2-form="line"] [name="baseRate"]').getAttribute('aria-invalid') === 'true'
            && document.querySelector('[data-v2-error="baseRate"]').textContent === 'Enter a valid decimal value'"""
        ),
    )
    evaluate("document.querySelector('[data-v2-action=\"cancel-line\"]').click()")

    stored_files_backup = evaluate(
        "localStorage.getItem('rate-card-manager.v2.files')"
    )
    evaluate(
        """localStorage.setItem('rate-card-manager.v2.files', '{invalid');
        location.reload()"""
    )
    time.sleep(0.8)
    check(
        "Corrupt persisted data renders the accessible LINE load-error state",
        evaluate(
            """!document.querySelector('[data-v2-load-error="lines"]').hidden
            && document.querySelector('[data-v2-load-error="lines"]').getAttribute('role') === 'alert'
            && document.querySelector('[data-v2-table-region="lines"]').hidden"""
        ),
    )
    evaluate("document.querySelector('[data-v2-tab=\"premiums\"]').click()")
    check(
        "Premiums expose the same accessible load-error state",
        evaluate(
            """!document.querySelector('[data-v2-load-error="premiums"]').hidden
            && document.querySelector('[data-v2-load-error="premiums"]').getAttribute('role') === 'alert'"""
        ),
    )
    evaluate(
        f"""localStorage.setItem(
          'rate-card-manager.v2.files',
          {json.dumps(stored_files_backup)}
        );
        document.querySelector('[data-v2-load-error="premiums"] [data-v2-action="retry-load"]').click()"""
    )
    time.sleep(0.2)
    check(
        "Retry restores the Rate Card after the persisted-data error is corrected",
        evaluate(
            """document.querySelector('[data-v2-load-error="premiums"]').hidden
            && document.querySelector('[data-v2-total="lines"]').textContent === '4'
            && document.querySelector('[data-v2-total="premiums"]').textContent === '1'"""
        ),
    )

    navigate("?version=2.0&section=create&mode=edit&cardId=RC-DAS-WPP-VIDEO-UF-2627")
    check(
        "Compatibility edit adapter hydrates populated tables",
        evaluate(
            """Number(document.querySelector('[data-v2-total="lines"]').textContent) > 10
            && Number(document.querySelector('[data-v2-total="premiums"]').textContent) > 0"""
        ),
    )
    tab_component = evaluate(
        """(() => {
          const tablist = document.querySelector('.create-md__tabs');
          const lines = document.querySelector('[data-v2-tab="lines"]');
          const premiums = document.querySelector('[data-v2-tab="premiums"]');
          const activeStyle = getComputedStyle(lines);
          const restStyle = getComputedStyle(premiums);
          const indicator = getComputedStyle(lines, '::after');
          const widths = () => [lines, premiums]
            .map(tab => Math.round(tab.getBoundingClientRect().width));
          /* Each label sits centered in its own tab: the space left of the
           * label matches the space right of it, on both tabs. */
          const centering = [lines, premiums].map(tab => {
            const box = tab.getBoundingClientRect();
            const label = tab.querySelector('.create-md__tab-label').getBoundingClientRect();
            return Math.round(label.left - box.left) === Math.round(box.right - label.right);
          });
          const linesActiveWidths = widths();
          premiums.focus();
          premiums.dispatchEvent(new KeyboardEvent('keydown', {key:'Home', bubbles:true}));
          const homeFocus = document.activeElement === lines;
          lines.dispatchEvent(new KeyboardEvent('keydown', {key:'End', bubbles:true}));
          const endFocus = document.activeElement === premiums;
          const premiumsActiveWidths = widths();
          premiums.dispatchEvent(new KeyboardEvent('keydown', {key:'ArrowRight', bubbles:true}));
          const wrappedFocus = document.activeElement === lines;
          return {
            tablist: [tablist.getAttribute('role'), tablist.getAttribute('aria-orientation')],
            activeType: [activeStyle.fontSize, activeStyle.lineHeight, activeStyle.fontWeight],
            restType: [restStyle.fontSize, restStyle.lineHeight, restStyle.fontWeight],
            gap: getComputedStyle(tablist).gap,
            tabText: [lines.innerText.trim(), premiums.innerText.trim()],
            chips: document.querySelectorAll('.create-md__tab-count').length,
            digitsInTabs: /\\d/.test(tablist.innerText),
            centering: centering,
            widthsBySelection: [linesActiveWidths, premiumsActiveWidths],
            indicator: [indicator.height, indicator.backgroundColor],
            labels: [lines.getAttribute('aria-label'), premiums.getAttribute('aria-label')],
            keyboard: [homeFocus, endFocus, wrappedFocus]
          };
        })()"""
    )
    check(
        "Shared tabs use ADS compact anatomy, dynamic labels, and keyboard behavior",
        tab_component["tablist"] == ["tablist", "horizontal"]
        and tab_component["activeType"] == ["14px", "20px", "600"]
        and tab_component["restType"] == ["14px", "20px", "400"]
        and tab_component["gap"] == "8px"
        and tab_component["indicator"] == ["3px", "rgb(64, 69, 194)"]
        and "line items" in tab_component["labels"][0].lower()
        and "premiums" in tab_component["labels"][1].lower()
        and tab_component["keyboard"] == [True, True, True],
        json.dumps(tab_component),
    )
    check(
        "Tabs read as text alone: no count chip, no digits, no leftover chip gap",
        tab_component["tabText"] == ["Line items", "Premiums"]
        and tab_component["chips"] == 0
        and not tab_component["digitsInTabs"],
        json.dumps(tab_component),
    )
    check(
        "Each tab label stays centered and the control keeps its width across tabs",
        tab_component["centering"] == [True, True]
        and tab_component["widthsBySelection"][0] == tab_component["widthsBySelection"][1],
        json.dumps(tab_component),
    )
    check(
        "Pagination appears for populated LINE table",
        evaluate("document.querySelectorAll('[data-v2-pagination=\"lines\"] button').length >= 4"),
    )
    pagination_geometry = evaluate(
        """(() => {
              const host = document.querySelector('[data-v2-pagination="lines"]');
              const item = host.querySelector('button');
              const itemStyle = getComputedStyle(item);
              return {
                gap: getComputedStyle(host).gap,
                width: itemStyle.width,
                height: itemStyle.height,
                radius: itemStyle.borderRadius
              };
            })()"""
    )
    check(
        "V2 Pagination matches ADS 35:36 item geometry",
        pagination_geometry
        == {"gap": "4px", "width": "36px", "height": "36px", "radius": "8px"},
        json.dumps(pagination_geometry),
    )
    line_header_anatomy = evaluate(
        """(() => {
          const tabs = document.querySelector('.create-md__tabs').getBoundingClientRect();
          const toolbar = document.querySelector(
            '[data-v2-panel="lines"] .create-md__toolbar'
          );
          const add = toolbar.querySelector('[data-v2-action="add-line"]')
            .getBoundingClientRect();
          const search = toolbar.querySelector('.create-md__search')
            .getBoundingClientRect();
          const table = document.querySelector(
            '[data-v2-panel="lines"] .create-md__table'
          ).getBoundingClientRect();
          // Every version keeps all the <th>s in the DOM and hides the
          // ones it does not show (2.0 has no Line condition column, 2.1
          // no standalone Advertiser ID), so a hidden header has no icon
          // box to align and is not part of this claim.
          const headers = [...document.querySelectorAll(
            '[data-v2-sort-header^="lines:"]'
          )].filter(header => header.offsetParent !== null);
          return {
            tabToControls: Math.round(add.top - tabs.bottom),
            controlGap: Math.round(add.left - search.right),
            searchAlignsTableLeft: Math.abs(search.left - table.left) <= 1,
            addAlignsTableRight: Math.abs(add.right - table.right) <= 1,
            searchBeforeAdd: search.left < add.left,
            centered: Math.abs(
              (search.top + search.height / 2) - (add.top + add.height / 2)
            ) <= 1,
            toolbarPadding: [
              getComputedStyle(toolbar).paddingTop,
              getComputedStyle(toolbar).paddingBottom
            ],
            activeSortHeader: (headers.find(header =>
              header.getAttribute('aria-sort') !== 'none'
            ) || {}).dataset?.v2SortHeader,
            activeSortDirection: (headers.find(header =>
              header.getAttribute('aria-sort') !== 'none'
            ) || {}).getAttribute?.('aria-sort'),
            inactiveSorts: headers.filter(header =>
              header.getAttribute('aria-sort') === 'none'
            ).length,
            headerKeys: headers.map(header => header.dataset.v2SortHeader),
            icons: headers.map(header => {
              const button = header.querySelector('button');
              const icon = button.querySelector('.th__sort');
              const iconRect = icon.getBoundingClientRect();
              const paths = [...icon.querySelectorAll('.th__sort-direction')];
              const range = document.createRange();
              range.setStart(button.firstChild, 0);
              range.setEnd(button.firstChild, button.firstChild.textContent.length);
              const labelRect = range.getBoundingClientRect();
              return {
                count: button.querySelectorAll('.th__sort').length,
                size: [Math.round(iconRect.width), Math.round(iconRect.height)],
                top: Math.round(iconRect.top),
                gap: Math.round(iconRect.left - labelRect.right),
                centered: Math.round(iconRect.top + iconRect.height / 2)
                  === Math.round(labelRect.top + labelRect.height / 2),
                paths: paths.map(path => ({
                  direction: path.classList.contains('th__sort-direction--ascending')
                    ? 'ascending'
                    : 'descending',
                  geometry: path.getAttribute('d'),
                  color: getComputedStyle(path).color
                })),
                nowrap: getComputedStyle(button).whiteSpace,
                wrapped: button.scrollHeight > button.clientHeight,
                label: button.getAttribute('aria-label')
              };
            })
          };
        })()"""
    )
    check(
        "Tabs and LINE controls use the increased shared spacing token",
        line_header_anatomy["tabToControls"] == 20
        and line_header_anatomy["toolbarPadding"] == ["20px", "16px"],
        json.dumps(line_header_anatomy),
    )
    check(
        "LINE toolbar matches Figma 455:13900: search left, Add Line Item "
        "right, both edge-aligned with the table and vertically centered",
        line_header_anatomy["searchBeforeAdd"]
        and line_header_anatomy["searchAlignsTableLeft"]
        and line_header_anatomy["addAlignsTableRight"]
        and line_header_anatomy["centered"]
        and line_header_anatomy["controlGap"] >= 16,
        json.dumps(line_header_anatomy),
    )
    check(
        # The book opens on the most recently maintained pricing rules,
        # so Updated date owns the initial sort and every other header
        # reports no sort.
        "Every LINE sort header uses one aligned shared icon and accessible state",
        line_header_anatomy["activeSortHeader"] == "lines:updatedAt"
        and line_header_anatomy["activeSortDirection"] == "descending"
        and line_header_anatomy["inactiveSorts"] == 6
        and all(icon["count"] == 1
                and icon["size"] == [12, 12]
                and icon["top"] == line_header_anatomy["icons"][0]["top"]
                and icon["gap"] == line_header_anatomy["icons"][0]["gap"]
                and icon["centered"]
                and len(icon["paths"]) == 2
                and [path["geometry"] for path in icon["paths"]]
                == [path["geometry"] for path in line_header_anatomy["icons"][0]["paths"]]
                and icon["nowrap"] == "nowrap"
                and not icon["wrapped"]
                and "Current sort:" in icon["label"]
                for icon in line_header_anatomy["icons"]),
        json.dumps(line_header_anatomy),
    )
    active_sort_icon = line_header_anatomy["icons"][
        line_header_anatomy["headerKeys"].index(line_header_anatomy["activeSortHeader"])
    ]
    inactive_sort_icon = line_header_anatomy["icons"][0]
    active_descending = next(
        path for path in active_sort_icon["paths"] if path["direction"] == "descending"
    )
    active_ascending = next(
        path for path in active_sort_icon["paths"] if path["direction"] == "ascending"
    )
    inactive_paths = {path["direction"]: path["color"] for path in inactive_sort_icon["paths"]}
    check(
        # Updated date owns the opening sort, so only its descending arrow
        # is emphasized. Every unsorted header keeps both arrows neutral.
        "Updated date emphasizes only descending while unsorted icons stay neutral",
        active_descending["color"] != inactive_paths["descending"]
        and active_ascending["color"] == inactive_paths["ascending"]
        and inactive_paths["ascending"] == inactive_paths["descending"],
        json.dumps([active_sort_icon, inactive_sort_icon]),
    )
    moved_sort_state = evaluate(
        """(() => {
          const advertiser = document.querySelector(
            '[data-v2-sort-header="lines:advertiserName"]'
          );
          const advertiserId = document.querySelector(
            '[data-v2-sort-header="lines:advertiserId"]'
          );
          advertiserId.querySelector('button').click();
          const moved = {
            advertiser: advertiser.getAttribute('aria-sort'),
            advertiserId: advertiserId.getAttribute('aria-sort'),
            advertiserClass: advertiser.querySelector('button').className,
            advertiserIdClass: advertiserId.querySelector('button').className,
            advertiserAscendingColor: getComputedStyle(
              advertiser.querySelector('.th__sort-direction--ascending')
            ).color,
            advertiserIdAscendingColor: getComputedStyle(
              advertiserId.querySelector('.th__sort-direction--ascending')
            ).color
          };
          advertiserId.querySelector('button').click();
          moved.descending = advertiserId.getAttribute('aria-sort');
          moved.advertiserIdDescendingColor = getComputedStyle(
            advertiserId.querySelector('.th__sort-direction--descending')
          ).color;
          moved.advertiserIdInactiveAscendingColor = getComputedStyle(
            advertiserId.querySelector('.th__sort-direction--ascending')
          ).color;
          advertiser.querySelector('button').click();
          return moved;
        })()"""
    )
    check(
        "Changing columns moves the active ascending sort state and color",
        moved_sort_state["advertiser"] == "none"
        and moved_sort_state["advertiserId"] == "ascending"
        and moved_sort_state["advertiserClass"] == ""
        and moved_sort_state["advertiserIdClass"] == "th--sort-asc"
        and moved_sort_state["advertiserAscendingColor"]
        != moved_sort_state["advertiserIdAscendingColor"]
        and moved_sort_state["descending"] == "descending"
        and moved_sort_state["advertiserIdDescendingColor"]
        != moved_sort_state["advertiserIdInactiveAscendingColor"],
        json.dumps(moved_sort_state),
    )
    line_sort_matrix = evaluate(
        """(() => {
          // Cell 0 is the bulk-selection checkbox column, which every 2.x
          // version renders so the body keeps lining up with the <thead>.
          // key, cell index, value type. Line condition sits after the
          // pricing fields and before Updated date, which moved to 8.
          const keys = [
            ['advertiserName', 1, 'text'],
            ['advertiserId', 2, 'text'],
            ['baseOffering', 3, 'text'],
            ['rateType', 4, 'text'],
            ['baseRate', 5, 'number'],
            ['currency', 6, 'text'],
            ['condition1', 7, 'condition'],
            ['updatedAt', 8, 'date']
          ];
          const normalize = (value, type) => {
            if (type === 'number') return Number(value.replace(/[^0-9.+-]/g, ''));
            if (type === 'date') return Date.parse(value);
            // An unset Line condition is drawn as an em dash followed by
            // screen-reader-only words. It sorts as the empty value it
            // stands for, not as the punctuation it is drawn with.
            if (type === 'condition') {
              const shown = value.trim();
              return shown.indexOf('\u2014') === 0 ? '' : shown.toLowerCase();
            }
            return value.trim().toLowerCase();
          };
          const ordered = (values, direction) => values.every((value, index) => {
            if (!index) return true;
            return direction === 'ascending'
              ? values[index - 1] <= value
              : values[index - 1] >= value;
          });
          return keys.every(([key, cellIndex, type]) => {
            const header = document.querySelector('[data-v2-sort-header="lines:' + key + '"]');
            const button = document.querySelector('[data-v2-sort="lines:' + key + '"]');
            if (header.getAttribute('aria-sort') !== 'ascending') button.click();
            const ascending = [...document.querySelectorAll('[data-v2-tbody="lines"] tr')]
              .map(row => normalize(row.cells[cellIndex].textContent, type));
            const ascendingPass = header.getAttribute('aria-sort') === 'ascending'
              && ordered(ascending, 'ascending');
            button.click();
            const descending = [...document.querySelectorAll('[data-v2-tbody="lines"] tr')]
              .map(row => normalize(row.cells[cellIndex].textContent, type));
            return ascendingPass
              && header.getAttribute('aria-sort') === 'descending'
              && ordered(descending, 'descending');
          });
        })()"""
    )
    check("Every approved LINE column sorts real rows in both directions", line_sort_matrix)
    evaluate(
        """(() => {
          document.querySelector('[data-v2-tab="premiums"]').click();
        })()"""
    )
    premium_sort_matrix = evaluate(
        """(() => {
          // Figma 697:3617 order after the checkbox column: Premium, Base
          // offering, Category, Value, Calculation method.
          const keys = [['displayName', 1, 'text'], ['baseOffering', 2, 'text'], ['value', 4, 'number']];
          const normalize = (value, type) => type === 'number'
            ? Number(value.replace(/[^0-9.+-]/g, ''))
            : value.trim().toLowerCase();
          const ordered = (values, direction) => values.every((value, index) => {
            if (!index) return true;
            return direction === 'ascending'
              ? values[index - 1] <= value
              : values[index - 1] >= value;
          });
          return keys.every(([key, cellIndex, type]) => {
            const header = document.querySelector('[data-v2-sort-header="premiums:' + key + '"]');
            const button = document.querySelector('[data-v2-sort="premiums:' + key + '"]');
            if (header.getAttribute('aria-sort') !== 'ascending') button.click();
            const ascending = [...document.querySelectorAll('[data-v2-tbody="premiums"] tr')]
              .map(row => normalize(row.cells[cellIndex].textContent, type));
            const ascendingPass = header.getAttribute('aria-sort') === 'ascending'
              && ordered(ascending, 'ascending');
            button.click();
            const descending = [...document.querySelectorAll('[data-v2-tbody="premiums"] tr')]
              .map(row => normalize(row.cells[cellIndex].textContent, type));
            return ascendingPass
              && header.getAttribute('aria-sort') === 'descending'
              && ordered(descending, 'descending');
          });
        })()"""
    )
    check("Every approved Premium column exposes aria-sort and sorts both ways", premium_sort_matrix)
    evaluate(
        """(() => {
          const search = document.querySelector('[data-v2-search="premiums"]');
          search.value = 'no matching premium value';
          search.dispatchEvent(new Event('input', {bubbles:true}));
        })()"""
    )
    check(
        "Premium search renders its dedicated no-results state",
        evaluate(
            """!document.querySelector('[data-v2-no-results="premiums"]').hidden
            && document.querySelector('[data-v2-table-region="premiums"]').hidden
            && document.querySelector('[data-v2-total="premiums"]').textContent === '0'"""
        ),
    )
    evaluate(
        """document.querySelector(
          '[data-v2-no-results="premiums"] [data-v2-action="clear-premium-refinements"]'
        ).click()"""
    )
    check(
        "Clearing Premium refinements restores data, pagination, and search focus",
        evaluate(
            """document.activeElement === document.querySelector('[data-v2-search="premiums"]')
            && document.querySelector('[data-v2-search="premiums"]').value === ''
            && !document.querySelector('[data-v2-table-region="premiums"]').hidden
            && document.querySelectorAll('[data-v2-go-page="premiums"] option').length >= 1"""
        ),
    )
    evaluate("document.querySelector('[data-v2-tab=\"lines\"]').click()")
    evaluate("document.querySelector('[data-v2-action=\"save-draft\"]').click()")
    time.sleep(0.1)
    pagination_card_id = evaluate("document.querySelector('[data-v2-card-id]').textContent")
    pagination_template = evaluate(
        """(() => {
          const files = JSON.parse(localStorage.getItem('rate-card-manager.v2.files'));
          return files[document.querySelector('[data-v2-card-id]').textContent].lines[0];
        })()"""
    )
    pagination_original_lines = evaluate(
        """(() => {
          const files = JSON.parse(localStorage.getItem('rate-card-manager.v2.files'));
          return files[document.querySelector('[data-v2-card-id]').textContent].lines;
        })()"""
    )

    def seed_pagination_lines(count):
        written_count = evaluate(
            f"""(() => {{
              const files = JSON.parse(localStorage.getItem('rate-card-manager.v2.files'));
              const template = {json.dumps(pagination_template)};
              files[{json.dumps(pagination_card_id)}].lines = Array.from({{length:{count}}}, (_, index) => ({{
                ...template,
                id: 'qa-page-' + index,
                advertiserId: 'ADV-' + String(index + 1).padStart(4, '0'),
                advertiserName: index === 0 ? 'Pagination Match' : 'Advertiser ' + (index + 1),
                baseRate: index + 1,
                updatedAt: new Date(2026, 0, index % 28 + 1).toISOString()
              }}));
              localStorage.setItem('rate-card-manager.v2.files', JSON.stringify(files));
              return files[{json.dumps(pagination_card_id)}].lines.length;
            }})()"""
        )
        if written_count != count:
            check(f"Pagination fixture writes {count} item(s)", False, f"wrote={written_count}")
        # Route to a neutral URL before re-navigating so the router always
        # sees a real navigation, not a no-op when the target URL matches the
        # current one (go_to_line_page above mutates in-app state, not URL).
        # Without this, the CDP Page.navigate to the same URL becomes a
        # same-document reload race and the fresh localStorage seed can be
        # read before the router re-renders, leaving total counts at 0.
        navigate("?version=2.0", pause=0.2)
        navigate(
            f"?version=2.0&section=create&mode=edit&cardId={pagination_card_id}",
            pause=0.6,
        )

    def pagination_snapshot():
        return evaluate(
            """(() => {
              const host = document.querySelector('[data-v2-pagination="lines"]');
              const pages = [...host.querySelectorAll('.create-md__pagination-item--page')]
                .map(button => Number(button.textContent));
              return {
                total: document.querySelector('[data-v2-total="lines"]').textContent,
                pages,
                ellipses: host.querySelectorAll('.create-md__pagination-ellipsis').length,
                current: Number(host.querySelector('[aria-current="page"]')?.textContent || 0),
                previousDisabled: host.querySelector('.create-md__pagination-item--previous')?.disabled ?? true,
                nextDisabled: host.querySelector('.create-md__pagination-item--next')?.disabled ?? true,
                goTo: [...document.querySelector('[data-v2-go-page="lines"]').options].map(option => Number(option.value)),
                visibleRows: document.querySelectorAll('[data-v2-tbody="lines"] tr').length,
                paginationButtons: host.querySelectorAll('button').length
              };
            })()"""
        )

    for count, expected_pages in ((0, 0), (1, 1), (10, 1), (11, 2), (50, 5)):
        seed_pagination_lines(count)
        snapshot = pagination_snapshot()
        check(
            f"Pagination derives {expected_pages} page(s) from {count} item(s)",
            snapshot["total"] == str(count)
            and len(snapshot["goTo"]) == expected_pages
            and snapshot["paginationButtons"] == (0 if count == 0 else expected_pages + 2)
            and snapshot["visibleRows"] == min(count, 10),
            json.dumps(snapshot),
        )

    seed_pagination_lines(100)
    evaluate(
        """(() => {
          const select = document.querySelector('[data-v2-page-size="lines"]');
          select.value = '10';
          select.dispatchEvent(new Event('change', {bubbles:true}));
        })()"""
    )
    exact_ten_pages = pagination_snapshot()
    check(
        "Page size ten creates exactly ten valid pages",
        exact_ten_pages["goTo"] == list(range(1, 11))
        and exact_ten_pages["pages"] == [1, 2, 3, 4, 5, 10]
        and exact_ten_pages["ellipses"] == 1,
        json.dumps(exact_ten_pages),
    )

    seed_pagination_lines(101)
    over_ten_pages = pagination_snapshot()
    check(
        "More than ten pages uses generated ellipsis and the real final page",
        over_ten_pages["pages"] == [1, 2, 3, 4, 5, 11]
        and over_ten_pages["ellipses"] == 1
        and over_ten_pages["goTo"] == list(range(1, 12)),
        json.dumps(over_ten_pages),
    )

    def go_to_line_page(page_number):
        evaluate(
            f"""(() => {{
              const select = document.querySelector('[data-v2-go-page="lines"]');
              select.value = '{page_number}';
              select.dispatchEvent(new Event('change', {{bubbles:true}}));
            }})()"""
        )

    # Figma 455:14159. Window rules: near-beginning shows 1-5, ellipsis,
    # last. Middle shows 1, ellipsis, current-1..current+1, ellipsis, last.
    # Near-end mirrors near-beginning from the other edge.
    go_to_line_page(1)
    near_start = pagination_snapshot()
    check(
        "Ellipsis window: page near the beginning (11 pages)",
        near_start["pages"] == [1, 2, 3, 4, 5, 11] and near_start["ellipses"] == 1,
        json.dumps(near_start),
    )
    go_to_line_page(6)
    middle_page = pagination_snapshot()
    check(
        "Ellipsis window: middle page shows both ellipses around current",
        middle_page["pages"] == [1, 5, 6, 7, 11]
        and middle_page["ellipses"] == 2
        and middle_page["current"] == 6,
        json.dumps(middle_page),
    )
    go_to_line_page(11)
    near_end = pagination_snapshot()
    check(
        "Ellipsis window: final page mirrors the near-beginning window",
        near_end["pages"] == [1, 7, 8, 9, 10, 11]
        and near_end["ellipses"] == 1
        and near_end["current"] == 11
        and near_end["nextDisabled"],
        json.dumps(near_end),
    )

    seed_pagination_lines(70)
    small_total = pagination_snapshot()
    check(
        "Ellipsis window: small total-page count (7 pages) renders every page, no ellipsis",
        small_total["pages"] == [1, 2, 3, 4, 5, 6, 7] and small_total["ellipses"] == 0,
        json.dumps(small_total),
    )

    seed_pagination_lines(500)
    huge_total = pagination_snapshot()
    check(
        "Ellipsis window: large total-page count (50 pages) still windows to 7 controls",
        huge_total["pages"] == [1, 2, 3, 4, 5, 50] and huge_total["ellipses"] == 1,
        json.dumps(huge_total),
    )

    seed_pagination_lines(101)
    pagination_a11y = evaluate(
        """(() => {
          const host = document.querySelector('[data-v2-pagination="lines"]');
          const prev = host.querySelector('.create-md__pagination-item--previous');
          const next = host.querySelector('.create-md__pagination-item--next');
          const ellipsis = host.querySelector('.create-md__pagination-ellipsis');
          const page2 = [...host.querySelectorAll('.create-md__pagination-item--page')]
            .find(button => button.textContent === '2');
          const current = host.querySelector('[aria-current="page"]');
          return {
            prevLabel: prev.getAttribute('aria-label'),
            nextLabel: next.getAttribute('aria-label'),
            page2Label: page2 ? page2.getAttribute('aria-label') : null,
            currentHasAriaCurrent: current.getAttribute('aria-current') === 'page',
            ellipsisAriaHidden: ellipsis.getAttribute('aria-hidden'),
            ellipsisIsButton: ellipsis.tagName === 'BUTTON',
            prevUsesIcon: prev.querySelector('svg') !== null && !prev.textContent.includes('<'),
            nextUsesIcon: next.querySelector('svg') !== null && !next.textContent.includes('>')
          };
        })()"""
    )
    check(
        "Pagination controls expose the required accessible names and are not raw text glyphs",
        pagination_a11y["prevLabel"] == "Previous page"
        and pagination_a11y["nextLabel"] == "Next page"
        and pagination_a11y["page2Label"] == "Go to page 2"
        and pagination_a11y["currentHasAriaCurrent"]
        and pagination_a11y["ellipsisAriaHidden"] == "true"
        and pagination_a11y["ellipsisIsButton"] is False
        and pagination_a11y["prevUsesIcon"]
        and pagination_a11y["nextUsesIcon"],
        json.dumps(pagination_a11y),
    )

    viewport(1440, 900)
    seed_pagination_lines(80)
    pagination_geometry = evaluate(
        """(() => {
          const cs = el => getComputedStyle(el);
          const rect = el => el.getBoundingClientRect();
          const pageSizeTrigger = document.querySelector(
            '[data-v2-panel="lines"] .create-md__page-size .ads-dd__trigger'
          );
          const goTrigger = document.querySelector(
            '[data-v2-panel="lines"] .create-md__page-jump .ads-dd__trigger'
          );
          const item = document.querySelector(
            '[data-v2-pagination="lines"] .create-md__pagination-item--page'
          );
          const footer = document.querySelector('[data-v2-panel="lines"] .create-md__table-footer');
          const pagination = document.querySelector('[data-v2-pagination="lines"]');
          const table = document.querySelector('[data-v2-panel="lines"] .create-md__table-scroll');
          const pageSize = footer.querySelector('.create-md__page-size');
          const pageJump = footer.querySelector('.create-md__page-jump');
          const tableRect = rect(table);
          const footerRect = rect(footer);
          const paginationRect = rect(pagination);
          return {
            pageSizeTriggerHeight: Math.round(rect(pageSizeTrigger).height),
            pageSizeTriggerWidth: Math.round(rect(pageSizeTrigger).width),
            pageSizeTriggerRadius: cs(pageSizeTrigger).borderRadius,
            pageSizeTriggerPadding: cs(pageSizeTrigger).padding,
            goTriggerHeight: Math.round(rect(goTrigger).height),
            goTriggerWidth: Math.round(rect(goTrigger).width),
            goTriggerRadius: cs(goTrigger).borderRadius,
            itemSize: Math.round(rect(item).width) + 'x' + Math.round(rect(item).height),
            itemRadius: cs(item).borderRadius,
            paginationGap: cs(pagination).gap,
            paginationDisplay: cs(pagination).display,
            footerGridDisplay: cs(footer).display,
            footerColumns: cs(footer).gridTemplateColumns.split(' ').length,
            footerPadding: cs(footer).padding,
            footerHeight: Math.round(footerRect.height),
            edgeDiffs: [
              Math.abs(rect(pageSize).left - tableRect.left),
              Math.abs(tableRect.right - rect(pageJump).right)
            ],
            centerDiff: Math.abs(
              (paginationRect.left + paginationRect.width / 2)
              - (footerRect.left + footerRect.width / 2)
            ),
            noOverflow: document.documentElement.scrollWidth <= document.documentElement.clientWidth
          };
        })()"""
    )
    check(
        "Figma 455:14158/455:14160. Compact selectors match Show/Go-to-page geometry, not a full-width field",
        pagination_geometry["pageSizeTriggerHeight"] == 32
        and pagination_geometry["pageSizeTriggerWidth"] <= 64
        and pagination_geometry["pageSizeTriggerRadius"] == "8px"
        and pagination_geometry["pageSizeTriggerPadding"] == "8px"
        and pagination_geometry["goTriggerHeight"] == 32
        and pagination_geometry["goTriggerWidth"] <= 64
        and pagination_geometry["goTriggerRadius"] == "8px",
        json.dumps(pagination_geometry),
    )
    check(
        "Pagination footer groups align to table edges while page controls remain centered",
        pagination_geometry["footerPadding"] == "8px 0px"
        and pagination_geometry["footerHeight"] == 52
        and max(pagination_geometry["edgeDiffs"]) <= 1
        and pagination_geometry["centerDiff"] <= 1,
        json.dumps(pagination_geometry),
    )
    check(
        "Figma 455:14159. Numbered page buttons are 36 by 36 with 8px radius on a flex pagination row",
        pagination_geometry["itemSize"] == "36x36"
        and pagination_geometry["itemRadius"] == "8px"
        and pagination_geometry["paginationGap"] == "4px"
        and pagination_geometry["paginationDisplay"] == "flex"
        and pagination_geometry["footerGridDisplay"] == "grid"
        and pagination_geometry["footerColumns"] == 3
        and pagination_geometry["noOverflow"],
        json.dumps(pagination_geometry),
    )

    pagination_edges_by_width = {}
    for width in [1024, 1280, 1440, 1920]:
        viewport(width, 900)
        pagination_edges_by_width[str(width)] = evaluate(
            """(() => {
              const panel = document.querySelector('[data-v2-panel="lines"]');
              const table = panel.querySelector('.create-md__table-scroll').getBoundingClientRect();
              const footer = panel.querySelector('.create-md__table-footer');
              const footerRect = footer.getBoundingClientRect();
              const left = footer.querySelector('.create-md__page-size').getBoundingClientRect();
              const center = footer.querySelector('.create-md__pagination').getBoundingClientRect();
              const right = footer.querySelector('.create-md__page-jump').getBoundingClientRect();
              return {
                edges: [
                  Math.abs(left.left - table.left),
                  Math.abs(table.right - right.right)
                ],
                center: Math.abs(
                  (center.left + center.width / 2)
                  - (footerRect.left + footerRect.width / 2)
                ),
                height: Math.round(footerRect.height)
              };
            })()"""
        )
    viewport(1440, 900)
    check(
        "Pagination edge alignment remains exact across supported desktop widths",
        all(
            max(result["edges"]) <= 1
            and result["center"] <= 1
            and result["height"] == (92 if int(width) <= 1280 else 52)
            for width, result in pagination_edges_by_width.items()
        ),
        json.dumps(pagination_edges_by_width),
    )

    pagination_states = evaluate(
        """(() => {
          const cs = el => getComputedStyle(el);
          const active = document.querySelector('[data-v2-pagination="lines"] [aria-current="page"]');
          const rest = [...document.querySelectorAll(
            '[data-v2-pagination="lines"] .create-md__pagination-item--page'
          )].find(btn => btn.getAttribute('aria-current') !== 'page');
          const prev = document.querySelector('[data-v2-pagination="lines"] .create-md__pagination-item--previous');
          return {
            activeBackground: cs(active).backgroundColor,
            activeColor: cs(active).color,
            restBackground: cs(rest).backgroundColor,
            restBorder: cs(rest).borderColor,
            prevDisabled: prev.disabled,
            prevVisible: cs(prev).display !== 'none' && cs(prev).visibility !== 'hidden'
          };
        })()"""
    )
    check(
        "Figma 455:14159. Active page uses the ADS brand fill and white text; rest state is a white outline chip",
        pagination_states["activeBackground"] == "rgb(64, 69, 194)"
        and pagination_states["activeColor"] == "rgb(255, 255, 255)"
        and pagination_states["restBackground"] == "rgb(255, 255, 255)"
        and pagination_states["prevDisabled"]
        and pagination_states["prevVisible"],
        json.dumps(pagination_states),
    )

    premiums_share_component = evaluate(
        """(() => {
          document.querySelector('[data-v2-tab="premiums"]').click();
          const pagination = document.querySelector('[data-v2-pagination="premiums"]');
          const pageSize = document.querySelector('[data-v2-panel="premiums"] .create-md__page-size .ads-dd__trigger');
          return {
            usesSharedItemClass: pagination
              ? pagination.querySelectorAll('.create-md__pagination-item').length > 0
              : false,
            pageSizeIsCompact: pageSize ? Math.round(pageSize.getBoundingClientRect().width) <= 64 : false
          };
        })()"""
    )
    check(
        "Premiums table reuses the same pagination component classes and compact selector styling as Line items",
        premiums_share_component["usesSharedItemClass"]
        and premiums_share_component["pageSizeIsCompact"],
        json.dumps(premiums_share_component),
    )
    evaluate(
        """(() => { document.querySelector('[data-v2-tab="lines"]').click(); })()"""
    )

    evaluate(
        """(() => {
          const input = document.querySelector('[data-v2-search="lines"]');
          input.value = '  pagination match  ';
          input.dispatchEvent(new Event('input', {bubbles:true}));
        })()"""
    )
    one_search_page = pagination_snapshot()
    check(
        "Search trims whitespace and recalculates one result page",
        one_search_page["total"] == "1"
        and one_search_page["pages"] == [1]
        and one_search_page["previousDisabled"]
        and one_search_page["nextDisabled"],
        json.dumps(one_search_page),
    )

    seed_pagination_lines(11)
    evaluate(
        """(() => {
          document.querySelector('[data-v2-page="lines:2"]').click();
          const row = document.querySelector('[data-v2-tbody="lines"] tr');
          row.click();
          document.querySelector('[data-v2-action="request-remove-line"]').click();
          document.querySelector('[data-v2-action="confirm-remove-line"]').click();
        })()"""
    )
    delete_last_page_item = pagination_snapshot()
    check(
        "Deleting the final item on the last page clamps to the final valid page",
        delete_last_page_item["total"] == "10"
        and delete_last_page_item["current"] == 1
        and delete_last_page_item["pages"] == [1]
        and delete_last_page_item["visibleRows"] == 10,
        json.dumps(delete_last_page_item),
    )

    evaluate(
        f"""(() => {{
          const files = JSON.parse(localStorage.getItem('rate-card-manager.v2.files'));
          files[{json.dumps(pagination_card_id)}].lines = {json.dumps(pagination_original_lines)};
          localStorage.setItem('rate-card-manager.v2.files', JSON.stringify(files));
        }})()"""
    )
    navigate(f"?version=2.0&section=create&mode=edit&cardId={pagination_card_id}", pause=0.35)
    evaluate(
        """(() => {
          const lineSearch = document.querySelector('[data-v2-search="lines"]');
          const files = JSON.parse(localStorage.getItem('rate-card-manager.v2.files'));
          const cardId = document.querySelector('[data-v2-card-id]').textContent;
          window.__qaLineTabQuery = files[cardId].lines[0].advertiserName;
          lineSearch.value = window.__qaLineTabQuery;
          lineSearch.dispatchEvent(new Event('input', {bubbles:true}));
          document.querySelector('[data-v2-tab="premiums"]').click();
          const premiumSearch = document.querySelector('[data-v2-search="premiums"]');
          premiumSearch.value = 'Sports';
          premiumSearch.dispatchEvent(new Event('input', {bubbles:true}));
          document.querySelector('[data-v2-tab="lines"]').click();
        })()"""
    )
    tabs_independent_debug = evaluate(
        """(() => ({
          lineValue: document.querySelector('[data-v2-search="lines"]').value,
          expectedLineValue: window.__qaLineTabQuery,
          premiumValue: document.querySelector('[data-v2-search="premiums"]').value,
          lineRows: document.querySelectorAll('[data-v2-tbody="lines"] tr').length,
          // First data cell, skipping the bulk-selection checkbox column
          // that every 2.x version renders ahead of it.
          firstCells: [...document.querySelectorAll('[data-v2-tbody="lines"] tr')]
            .map(row => row.cells[1].textContent)
        }))()"""
    )
    check(
        "Tabs preserve independent search state",
        tabs_independent_debug["lineValue"] == tabs_independent_debug["expectedLineValue"]
        and tabs_independent_debug["premiumValue"] == "Sports"
        and tabs_independent_debug["lineRows"] > 0
        and all(
            tabs_independent_debug["expectedLineValue"] in cell
            for cell in tabs_independent_debug["firstCells"]
        ),
        json.dumps(tabs_independent_debug),
    )
    search_component = evaluate(
        """(async () => {
          const searches = [...document.querySelectorAll('.create-md__search.ads-search')];
          const anatomy = searches.map(search => {
            const style = getComputedStyle(search);
            const input = search.querySelector('.ads-search__input');
            const inputStyle = getComputedStyle(input);
            const icon = search.querySelector('.ads-search__icon');
            const iconLeaf = icon.querySelector('img');
            const clear = search.querySelector('.ads-search__clear');
            const clearLeaf = clear.querySelector('img');
            return {
              geometry: [
                style.height,
                style.padding,
                style.gap,
                style.borderWidth,
                style.borderRadius
              ],
              surface: [
                style.backgroundColor,
                style.borderColor,
                getComputedStyle(input, '::placeholder').color
              ],
              type: [
                inputStyle.fontFamily,
                inputStyle.fontSize,
                inputStyle.fontWeight,
                inputStyle.lineHeight
              ],
              icon: [
                Math.round(parseFloat(getComputedStyle(icon).width)),
                Math.round(parseFloat(getComputedStyle(iconLeaf).width)),
                iconLeaf.getAttribute('src'),
                icon.getAttribute('aria-hidden')
              ],
              clear: [
                Math.round(parseFloat(getComputedStyle(clear).width)),
                Math.round(parseFloat(getComputedStyle(clearLeaf).width)),
                clearLeaf.getAttribute('src'),
                clear.getAttribute('aria-label'),
                clear.hidden
              ],
              label: input.labels[0]?.textContent.trim(),
              filled: search.dataset.filled
            };
          });
          const lineInput = document.querySelector('[data-v2-search="lines"]');
          const lineSearch = lineInput.closest('.ads-search');
          lineInput.focus();
          await new Promise(resolve => setTimeout(resolve, 150));
          const focusBorder = getComputedStyle(lineSearch).borderColor;
          lineInput.blur();
          lineInput.disabled = true;
          await new Promise(resolve => setTimeout(resolve, 150));
          const disabledStyle = getComputedStyle(lineSearch);
          const disabled = [
            disabledStyle.backgroundColor,
            disabledStyle.borderColor,
            disabledStyle.opacity,
            getComputedStyle(lineSearch.querySelector('.ads-search__clear')).display
          ];
          lineInput.disabled = false;
          return {anatomy, focusBorder, disabled};
        })()"""
    )
    check(
        "V2 Search Fields reuse the official ADS Search anatomy and assets",
        len(search_component["anatomy"]) == 2
        and all(
            search["geometry"] == ["36px", "8px 12px", "8px", "1px", "100px"]
            and search["surface"]
            == ["rgb(255, 255, 255)", "rgba(15, 18, 20, 0.2)", "rgb(81, 88, 91)"]
            and search["type"]
            == ['"Open Sans", system-ui, sans-serif', "14px", "400", "20px"]
            and search["icon"] == [20, 16, "./assets/ads-search.svg", "true"]
            and search["clear"][:4]
            == [16, 10, "./assets/ads-search-clear.svg", "Clear search"]
            and search["label"] in ["Search line items", "Search premiums"]
            and search["filled"] == "true"
            and not search["clear"][4]
            for search in search_component["anatomy"]
        )
        and search_component["focusBorder"] == "rgba(15, 18, 20, 0.5)"
        # Disabled border uses the lighter --ads-input-border-disabled token
        # (rgba(15,18,20,0.05)) so search matches every other ADS input in
        # the disabled state. qa_ads_compliance.py enforces the same value
        # on the list view search.
        and search_component["disabled"]
        == ["rgba(15, 18, 20, 0.05)", "rgba(15, 18, 20, 0.05)", "0.6", "none"],
        json.dumps(search_component),
    )
    evaluate("document.querySelector('[data-v2-clear-search=\"lines\"]').click()")
    check(
        "V2 Search clear restores rows, focus, and independent premium query",
        evaluate(
            """document.querySelector('[data-v2-search="lines"]').value === ''
            && document.activeElement === document.querySelector('[data-v2-search="lines"]')
            && document.querySelectorAll('[data-v2-tbody="lines"] tr').length > 1
            && document.querySelector('[data-v2-search="premiums"]').value === 'Sports'"""
        ),
    )
    check(
        "Line search matches the Figma copy and broader rate card context",
        evaluate(
            """(() => {
              const input = document.querySelector('[data-v2-search="lines"]');
              const cardId = document.querySelector('[data-v2-card-id]').textContent;
              const marketplace = document.querySelector('[data-v2-form="card"]').elements.marketplace.value;
              const files = JSON.parse(localStorage.getItem('rate-card-manager.v2.files'));
              const expected = String(files[cardId].lines.length);
              const search = value => {
                input.value = value;
                input.dispatchEvent(new Event('input', {bubbles:true}));
                return document.querySelector('[data-v2-total="lines"]').textContent;
              };
              const marketplaceTotal = search('  ' + marketplace.toLowerCase() + '  ');
              const cardTotal = search(cardId.toLowerCase());
              input.value = '';
              input.dispatchEvent(new Event('input', {bubbles:true}));
              return input.placeholder === 'Search line items'
                && marketplaceTotal === expected
                && cardTotal === expected;
            })()"""
        ),
    )
    evaluate(
        """(() => {
          const row = document.querySelector('[data-v2-tbody="lines"] tr');
          row.click();
          document.querySelector('[data-v2-action="cancel-line"]').click();
        })()"""
    )
    check(
        "Cancel returns focus to the selected row",
        evaluate(
            """document.activeElement.matches('[data-v2-row-type="lines"]')
            && document.activeElement.getAttribute('aria-selected') === 'true'"""
        ),
    )

    def column_metrics():
        return evaluate(
            """(() => {
              const workspace = document.querySelector('.create-md__workspace');
              const detail = document.querySelector('.create-md__detail');
              const workspaceRect = workspace.getBoundingClientRect();
              const detailRect = detail.getBoundingClientRect();
              const cards = [...detail.querySelectorAll('.create-md__accordion')];
              const lastCardRect = cards[cards.length - 1].getBoundingClientRect();
              const tableFooter = [...workspace.querySelectorAll('.create-md__table-footer')]
                .find(footer => footer.offsetParent !== null);
              const tableFooterRect = tableFooter && tableFooter.getBoundingClientRect();
              const openCard = cards.find(card => card.classList.contains('is-open'));
              const openPanel = openCard && openCard.querySelector('.create-md__accordion-panel');
              const triggers = cards.map(card => card.querySelector('.create-md__accordion-trigger'));
              return {
                workspaceTop: Math.round(workspaceRect.top),
                workspaceBottom: Math.round(workspaceRect.bottom),
                workspaceHeight: Math.round(workspaceRect.height),
                detailTop: Math.round(detailRect.top),
                detailBottom: Math.round(detailRect.bottom),
                detailHeight: Math.round(detailRect.height),
                lastCardBottom: Math.round(lastCardRect.bottom),
                detailTrailingSpace: Math.round(detailRect.bottom - lastCardRect.bottom),
                workspaceTrailingSpace: tableFooterRect
                  ? Math.round(workspaceRect.bottom - tableFooterRect.bottom) : null,
                openSections: cards.filter(card => card.classList.contains('is-open'))
                  .map(card => card.dataset.v2Accordion),
                accordionAllocation: cards.map(card => ({
                  section: card.dataset.v2Accordion,
                  grow: getComputedStyle(card).flexGrow,
                  shrink: getComputedStyle(card).flexShrink
                })),
                headersVisible: triggers.every(trigger => {
                  const rect = trigger.getBoundingClientRect();
                  return rect.top >= detailRect.top && rect.bottom <= detailRect.bottom;
                }),
                openPanelOverflow: openPanel ? getComputedStyle(openPanel).overflowY : null,
                openPanelMinHeight: openPanel ? getComputedStyle(openPanel).minHeight : null,
                openPanelClientHeight: openPanel ? openPanel.clientHeight : null,
                openPanelScrollHeight: openPanel ? openPanel.scrollHeight : null,
                detailOverflow: getComputedStyle(detail).overflowY,
                detailClientHeight: detail.clientHeight,
                detailScrollHeight: detail.scrollHeight,
                pageClientHeight: document.documentElement.clientHeight,
                pageScrollHeight: document.documentElement.scrollHeight,
                gridColumns: getComputedStyle(document.querySelector('[data-v2-root]')).gridTemplateColumns,
                gridAlignItems: getComputedStyle(document.querySelector('.create-md')).alignItems
              };
            })()"""
        )

    viewport(1440, 900)
    card_columns = column_metrics()
    check(
        "Rate Card details and table share aligned outer edges",
        card_columns["openSections"] == ["card"]
        and all(card["grow"] == "0" for card in card_columns["accordionAllocation"])
        and card_columns["headersVisible"]
        and card_columns["openPanelOverflow"] == "auto"
        and card_columns["openPanelMinHeight"] == "0px"
        and card_columns["workspaceTop"] == card_columns["detailTop"]
        and card_columns["workspaceBottom"] == card_columns["detailBottom"]
        and card_columns["workspaceTrailingSpace"] <= 1
        and card_columns["detailTrailingSpace"] >= 16
        and card_columns["gridAlignItems"] == "stretch"
        and card_columns["detailOverflow"] == "hidden",
        json.dumps(card_columns),
    )
    evaluate("document.querySelector('#v2-acc-line-trigger').click()")
    time.sleep(0.1)
    line_columns = column_metrics()
    check(
        "Line details and table share aligned outer edges",
        line_columns["openSections"] == ["line"]
        and all(card["grow"] == "0" for card in line_columns["accordionAllocation"])
        and line_columns["headersVisible"]
        and line_columns["openPanelOverflow"] == "auto"
        and line_columns["openPanelMinHeight"] == "0px"
        and line_columns["workspaceTop"] == line_columns["detailTop"]
        and line_columns["workspaceBottom"] == line_columns["detailBottom"]
        and line_columns["detailTrailingSpace"] == 16
        and line_columns["gridAlignItems"] == "stretch"
        and line_columns["detailOverflow"] == "hidden",
        json.dumps(line_columns),
    )
    evaluate("document.querySelector('#v2-acc-premium-trigger').click()")
    time.sleep(0.1)
    premium_columns = column_metrics()
    check(
        "Premium adjustments and table share aligned outer edges",
        premium_columns["openSections"] == ["premium"]
        and all(card["grow"] == "0" for card in premium_columns["accordionAllocation"])
        and premium_columns["headersVisible"]
        and premium_columns["openPanelOverflow"] == "auto"
        and premium_columns["openPanelMinHeight"] == "0px"
        and premium_columns["workspaceTop"] == premium_columns["detailTop"]
        and premium_columns["workspaceBottom"] == premium_columns["detailBottom"]
        and premium_columns["detailTrailingSpace"] == 16
        and premium_columns["gridAlignItems"] == "stretch"
        and premium_columns["detailOverflow"] == "hidden",
        json.dumps(premium_columns),
    )
    evaluate("document.querySelector('#v2-acc-premium-trigger').click()")
    collapsed_columns = column_metrics()
    check(
        "All collapsed accordions remain top-anchored inside the aligned rail",
        collapsed_columns["openSections"] == []
        and all(card["grow"] == "0" for card in collapsed_columns["accordionAllocation"])
        and collapsed_columns["headersVisible"]
        and collapsed_columns["workspaceTop"] == collapsed_columns["detailTop"]
        and collapsed_columns["workspaceBottom"] == collapsed_columns["detailBottom"]
        and collapsed_columns["detailTrailingSpace"] >= 16
        and collapsed_columns["gridAlignItems"] == "stretch",
        json.dumps(collapsed_columns),
    )
    viewport(1440, 480)
    evaluate("document.querySelector('#v2-acc-line-trigger').click()")
    time.sleep(0.1)
    short_columns = column_metrics()
    check(
        "Short viewport grows the page without nested rail scrolling",
        short_columns["pageScrollHeight"] > short_columns["pageClientHeight"]
        and short_columns["detailScrollHeight"] <= short_columns["detailClientHeight"]
        and short_columns["headersVisible"]
        and short_columns["openPanelScrollHeight"] <= short_columns["openPanelClientHeight"]
        and short_columns["openPanelOverflow"] == "auto"
        and short_columns["workspaceTop"] == short_columns["detailTop"]
        and short_columns["workspaceBottom"] == short_columns["detailBottom"]
        and short_columns["detailTrailingSpace"] == 16
        and short_columns["detailOverflow"] == "hidden",
        json.dumps(short_columns),
    )
    viewport(1024, 768)
    compact_desktop = column_metrics()
    check(
        "1024 compact desktop preserves the complete two-column workspace",
        len(compact_desktop["gridColumns"].split(" ")) == 2
        and compact_desktop["workspaceTop"] == compact_desktop["detailTop"]
        and compact_desktop["workspaceBottom"] == compact_desktop["detailBottom"]
        and compact_desktop["headersVisible"]
        and compact_desktop["openPanelScrollHeight"] <= compact_desktop["openPanelClientHeight"]
        and compact_desktop["openPanelOverflow"] == "auto"
        and compact_desktop["detailOverflow"] == "hidden"
        and evaluate(
            """document.querySelector('.create-md__detail').getBoundingClientRect().right
              <= document.documentElement.clientWidth
            && document.documentElement.scrollWidth
              <= document.documentElement.clientWidth"""
        ),
        json.dumps(compact_desktop),
    )
    viewport(700, 800)
    unsupported_desktop = column_metrics()
    check(
        "Below 1024 stacks panels without page-level horizontal overflow",
        len(unsupported_desktop["gridColumns"].split(" ")) == 1
        and unsupported_desktop["detailTop"] >= unsupported_desktop["workspaceBottom"]
        and unsupported_desktop["headersVisible"]
        and unsupported_desktop["detailOverflow"] == "hidden"
        and evaluate(
            """(() => {
              const lineFields = document.querySelectorAll(
                '[data-v2-form="line"] .create-md__rate-currency > .field'
              );
              const premiumPairs = document.querySelectorAll(
                '[data-v2-form="premium"] .create-md__paired-fields'
              );
              return document.documentElement.scrollWidth
                  <= document.documentElement.clientWidth
                && lineFields.length === 2
                && lineFields[0].getBoundingClientRect().top
                  === lineFields[1].getBoundingClientRect().top
                && [...premiumPairs].every(pair => {
                  const fields = pair.querySelectorAll(':scope > .field');
                  return fields.length === 2
                    && fields[0].getBoundingClientRect().top
                      === fields[1].getBoundingClientRect().top;
                });
            })()"""
        ),
        json.dumps(unsupported_desktop),
    )
    evaluate("document.querySelector('#v2-acc-card-trigger').click()")

    viewport(1440)
    screenshot("desktop")
    check(
        "Desktop uses two-column master-detail",
        evaluate("getComputedStyle(document.querySelector('[data-v2-root]')).gridTemplateColumns.split(' ').length >= 2"),
    )
    viewport(1280, 800)
    screenshot("viewport-1280")
    check(
        "1280 viewport preserves the rail and wraps pagination without collision",
        evaluate(
            """(() => {
              const root = document.querySelector('[data-v2-root]');
              const workspace = document.querySelector('.create-md__workspace').getBoundingClientRect();
              const rail = document.querySelector('.create-md__detail').getBoundingClientRect();
              const tableScroll = document.querySelector(
                '[data-v2-panel="lines"] .create-md__table-scroll'
              );
              const table = tableScroll.querySelector('.create-md__table').getBoundingClientRect();
              const footer = document.querySelector('[data-v2-panel="lines"] .create-md__table-footer');
              const pageSize = footer.querySelector('.create-md__page-size').getBoundingClientRect();
              const pagination = footer.querySelector('.create-md__pagination').getBoundingClientRect();
              const pageJump = footer.querySelector('.create-md__page-jump').getBoundingClientRect();
              return getComputedStyle(root).gridTemplateColumns.split(' ').length >= 2
                && Math.round(rail.width) === 422
                && Math.round(rail.left - workspace.right) === 12
                && rail.right <= document.documentElement.clientWidth
                && Math.abs(table.width - tableScroll.clientWidth) <= 1
                && Math.abs(tableScroll.scrollWidth - tableScroll.clientWidth) <= 1
                && Math.abs(pageSize.top - pageJump.top) <= 1
                && pagination.top > pageSize.bottom
                && document.documentElement.scrollWidth <= document.documentElement.clientWidth;
            })()"""
        ),
    )
    viewport(1600, 1000)
    check(
        "1600 viewport grows fluidly beyond the Figma baseline",
        evaluate(
            """(() => {
              const root = document.querySelector('[data-v2-root]').getBoundingClientRect();
              const workspace = document.querySelector('.create-md__workspace').getBoundingClientRect();
              const rail = document.querySelector('.create-md__detail').getBoundingClientRect();
              return root.width > 1342
                && workspace.width > 868
                && rail.width > 462 && rail.width <= 520
                && rail.left - workspace.right > 12
                && document.documentElement.scrollWidth <= document.documentElement.clientWidth;
            })()"""
        ),
    )
    viewport(1800, 1000)
    screenshot("viewport-1800")
    check(
        "1800 viewport continues fluid growth without overflow",
        evaluate(
            """(() => {
              const root = document.querySelector('[data-v2-root]');
              const workspace = document.querySelector('.create-md__workspace').getBoundingClientRect();
              const rail = document.querySelector('.create-md__detail').getBoundingClientRect();
              const rootRect = root.getBoundingClientRect();
              return getComputedStyle(root).gridTemplateColumns.split(' ').length >= 2
                && rootRect.width > 1500
                && workspace.width > 1000
                && Math.round(rail.width) === 520
                && rail.left - workspace.right > 12
                && document.documentElement.scrollWidth <= document.documentElement.clientWidth;
            })()"""
        ),
    )
    viewport(1920, 1080)
    screenshot("viewport-1920")
    check(
        "1920 viewport uses nearly all available shell width",
        evaluate(
            """(() => {
              const root = document.querySelector('[data-v2-root]').getBoundingClientRect();
              const workspace = document.querySelector('.create-md__workspace').getBoundingClientRect();
              const rail = document.querySelector('.create-md__detail').getBoundingClientRect();
              return Math.round(root.width) === 1808
                && Math.round(workspace.width) === 1271
                && Math.round(rail.width) === 520
                && Math.round(rail.left - workspace.right) === 17
                && Math.round(root.left - 64) === 24
                && Math.round(innerWidth - root.right) === 24
                && document.documentElement.scrollWidth <= document.documentElement.clientWidth;
            })()"""
        ),
    )
    viewport(2560, 1440)
    screenshot("viewport-2560")
    check(
        "2560 viewport fills the shell without shifting the left edge inward",
        evaluate(
            """(() => {
              const root = document.querySelector('[data-v2-root]').getBoundingClientRect();
              const workspace = document.querySelector('.create-md__workspace').getBoundingClientRect();
              const rail = document.querySelector('.create-md__detail').getBoundingClientRect();
              return Math.round(root.width) === 2432
                && Math.round(workspace.width) === 1892
                && Math.round(rail.width) === 520
                && Math.round(rail.left - workspace.right) === 20
                && Math.round(root.left - 64) === 32
                && Math.round(innerWidth - root.right) === 32
                && document.documentElement.scrollWidth <= document.documentElement.clientWidth;
            })()"""
        ),
    )
    responsive_matrix = {}
    for width, height in [
        (1024, 760),
        (1280, 800),
        (1366, 768),
        (1440, 900),
        (1512, 982),
        (1920, 1080),
        (2560, 1440),
        (768, 1024),
        (1024, 768),
    ]:
        viewport(width, height)
        responsive_matrix[f"{width}x{height}"] = evaluate(
            """(() => {
              const viewportWidth = document.documentElement.clientWidth;
              const viewportHeight = document.documentElement.clientHeight;
              const root = document.querySelector('[data-v2-root]');
              const workspace = document.querySelector('.create-md__workspace');
              const detail = document.querySelector('.create-md__detail');
              const tableScroll = document.querySelector(
                '[data-v2-panel="lines"] .create-md__table-scroll'
              );
              const rect = element => {
                const value = element.getBoundingClientRect();
                return {
                  left: value.left,
                  top: value.top,
                  right: value.right,
                  bottom: value.bottom,
                  width: value.width,
                  height: value.height,
                };
              };
              const rootRect = rect(root);
              const workspaceRect = rect(workspace);
              const detailRect = rect(detail);
              const columns = getComputedStyle(root).gridTemplateColumns
                .split(' ').length;
              const controls = [...document.querySelectorAll(
                '.create-md__workspace-header button:not([hidden]),'
                + '.create-md__toolbar button:not([hidden]),'
                + '.create-md__toolbar input:not([hidden])'
              )];
              return {
                columns,
                pageHorizontalOverflow:
                  document.documentElement.scrollWidth > viewportWidth,
                rootWithinViewport:
                  rootRect.left >= 0 && rootRect.right <= viewportWidth + 1,
                panelsWithinViewport:
                  workspaceRect.left >= 0
                  && workspaceRect.right <= viewportWidth + 1
                  && detailRect.left >= 0
                  && detailRect.right <= viewportWidth + 1,
                panelFlow:
                  columns === 1
                    ? detailRect.top >= workspaceRect.bottom
                    : Math.abs(detailRect.top - workspaceRect.top) <= 1,
                controlsWithinViewport: controls.every(control => {
                  const value = control.getBoundingClientRect();
                  return value.left >= 0 && value.right <= viewportWidth + 1;
                }),
                tableOverflowOwner:
                  getComputedStyle(tableScroll).overflowX === 'auto'
                  && tableScroll.clientWidth <= workspace.clientWidth,
                viewportHeight,
                pageScrollHeight: document.documentElement.scrollHeight,
              };
            })()"""
        )
    check(
        "Create/Edit fit-to-viewport matrix keeps overflow component-owned",
        all(
            not metrics["pageHorizontalOverflow"]
            and metrics["rootWithinViewport"]
            and metrics["panelsWithinViewport"]
            and metrics["panelFlow"]
            and metrics["controlsWithinViewport"]
            and metrics["tableOverflowOwner"]
            for metrics in responsive_matrix.values()
        ),
        json.dumps(responsive_matrix),
    )
    evaluate(
        """(() => {
          const key = 'rate-card-manager.v2.files';
          const files = JSON.parse(localStorage.getItem(key) || '{}');
          delete files['RC-DAS-WPP-VIDEO-UF-2627'];
          localStorage.setItem(key, JSON.stringify(files));
        })()"""
    )
    navigate("?version=2.0&section=create&mode=edit&cardId=RC-DAS-WPP-VIDEO-UF-2627")
    viewport(1030, 914)
    screenshot("primary-edit-1030x914")
    primary_fidelity = evaluate(
        """(() => {
          const rect = selector => {
            const r = document.querySelector(selector).getBoundingClientRect();
            return [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)];
          };
          const rail = document.querySelector('.create-md__detail');
          const rows = document.querySelectorAll('[data-v2-tbody="lines"] tr');
          const tableScroll = document.querySelector(
            '[data-v2-panel="lines"] .create-md__table-scroll'
          );
          const pagination = [...document.querySelectorAll(
            '[data-v2-pagination="lines"] > *'
          )].map(item => item.getAttribute('aria-label') || item.textContent.trim());
          const footer = document.querySelector(
            '[data-v2-panel="lines"] .create-md__table-footer'
          );
          const pageSize = footer.querySelector('.create-md__page-size').getBoundingClientRect();
          const pager = footer.querySelector('.create-md__pagination').getBoundingClientRect();
          const pageJump = footer.querySelector('.create-md__page-jump').getBoundingClientRect();
          return {
            topbar: rect('.gnav'),
            sidenav: rect('.vnav'),
            workspace: rect('.create-md__workspace'),
            headerRow: rect('.create-md__workspace-header-row'),
            title: document.querySelector('[data-v2-title]').textContent,
            helper: document.querySelector('[data-v2-helper]').textContent.trim(),
            helperVisible: !document.querySelector('[data-v2-helper]').hidden,
            tabs: [...document.querySelectorAll('[data-v2-tab]')]
              .map(tab => tab.innerText.trim()),
            totals: [
              document.querySelector('[data-v2-total="lines"]').textContent,
              document.querySelector('[data-v2-total="premiums"]').textContent
            ],
            add: rect('[data-v2-action="add-line"]'),
            addPadding: (() => {
              const cs = getComputedStyle(document.querySelector('[data-v2-action="add-line"]'));
              return [cs.paddingLeft, cs.paddingRight];
            })(),
            search: rect('.create-md__toolbar .ads-search'),
            searchRadius: getComputedStyle(
              document.querySelector('.create-md__toolbar .ads-search')
            ).borderRadius,
            table: rect('[data-v2-panel="lines"] .create-md__table'),
            headerHeight: Math.round(
              document.querySelector('[data-v2-panel="lines"] thead tr')
                .getBoundingClientRect().height
            ),
            rowHeights: [...rows].map(row => Math.round(row.getBoundingClientRect().height)),
            rows: rows.length,
            footer: rect('[data-v2-panel="lines"] .create-md__table-footer'),
            footerAligned: Math.abs(pageSize.top - pager.top) <= 2
              && Math.abs(pageJump.top - pager.top) <= 2,
            pagination,
            railDisplay: getComputedStyle(rail).display,
            railCollapseDisplay: getComputedStyle(
              document.querySelector('.vnav__close')
            ).display,
            tableScroll: [
              tableScroll.clientWidth,
              tableScroll.scrollWidth,
              getComputedStyle(tableScroll).overflowX
            ],
            overflow: document.documentElement.scrollWidth
              <= document.documentElement.clientWidth
          };
        })()"""
    )
    check(
        "Primary 1030 viewport keeps the complete rail and constrained workspace visible",
        primary_fidelity["topbar"][:2] == [0, 0]
        and primary_fidelity["topbar"][2] in [1015, 1030]
        and primary_fidelity["topbar"][3] == 56
        and primary_fidelity["sidenav"][:3] == [0, 56, 64]
        and primary_fidelity["workspace"][:2] == [76, 75]
        and primary_fidelity["workspace"][2] >= 520
        and primary_fidelity["headerRow"][:2] == [98, 92]
        and primary_fidelity["headerRow"][2] == primary_fidelity["workspace"][2] - 44
        and primary_fidelity["headerRow"][3] == 36
        and primary_fidelity["railDisplay"] == "flex"
        and primary_fidelity["railCollapseDisplay"] == "none"
        and primary_fidelity["tableScroll"][0] == primary_fidelity["workspace"][2] - 43
        and primary_fidelity["tableScroll"][1:] == [825, "auto"]
        and primary_fidelity["overflow"],
        json.dumps(primary_fidelity),
    )
    check(
        "Primary WPP page preserves title, context, counts, table density, and pagination",
        primary_fidelity["title"] == "WPP – Streaming Video Upfront 2026–2027"
        and not primary_fidelity["helperVisible"]
        and primary_fidelity["helper"]
        == "Enter the rate card details, then add line items and premium adjustments."
        and primary_fidelity["tabs"] == ["Line items", "Premiums"]
        and primary_fidelity["totals"] == ["80", "4"]
        and primary_fidelity["add"][3] == 36
        and primary_fidelity["addPadding"] == ["16px", "16px"]
        and 118 < primary_fidelity["add"][2] < 150
        and 340 <= primary_fidelity["search"][2] <= 388
        and primary_fidelity["search"][3] == 36
        and primary_fidelity["searchRadius"] == "100px"
        and primary_fidelity["table"][2] == 825
        and primary_fidelity["headerHeight"] == 39
        and primary_fidelity["rows"] == 10
        and all(height == 48 for height in primary_fidelity["rowHeights"])
        and primary_fidelity["footer"][2] == primary_fidelity["workspace"][2] - 43
        and primary_fidelity["footer"][3] == 92
        and not primary_fidelity["footerAligned"]
        and primary_fidelity["pagination"]
        == [
            "Previous page", "Page 1, current page", "Go to page 2",
            "Go to page 3", "Go to page 4", "Go to page 5", "...",
            "Go to page 8", "Next page"
        ],
        json.dumps(primary_fidelity),
    )
    pagination_behavior = evaluate(
        """(() => {
          const pageSize = document.querySelector('[data-v2-page-size="lines"]');
          pageSize.value = '20';
          pageSize.dispatchEvent(new Event('change', {bubbles:true}));
          const firstCount = document.querySelectorAll('[data-v2-tbody="lines"] tr').length;
          const pageCount = document.querySelectorAll(
            '[data-v2-pagination="lines"] [data-v2-page]'
          ).length;
          const goTo = document.querySelector('[data-v2-go-page="lines"]');
          goTo.value = '3';
          goTo.dispatchEvent(new Event('change', {bubbles:true}));
          const current = document.querySelector(
            '[data-v2-pagination="lines"] [aria-current="page"]'
          )?.textContent.trim();
          const thirdCount = document.querySelectorAll('[data-v2-tbody="lines"] tr').length;
          pageSize.value = '10';
          pageSize.dispatchEvent(new Event('change', {bubbles:true}));
          return {firstCount, pageCount, current, thirdCount};
        })()"""
    )
    check(
        "Primary pagination page-size and go-to controls update real rows",
        pagination_behavior
        == {"firstCount": 20, "pageCount": 6, "current": "3", "thirdCount": 20},
        json.dumps(pagination_behavior),
    )
    viewport(1440, 960)
    screenshot("primary-edit-1440x960")
    check(
        "Figma desktop keeps the fluid main column and 462 pixel details rail",
        evaluate(
            """(() => {
              const workspace = document.querySelector('.create-md__workspace').getBoundingClientRect();
              const rail = document.querySelector('.create-md__detail').getBoundingClientRect();
              const tableScroll = document.querySelector(
                '[data-v2-panel="lines"] .create-md__table-scroll'
              );
              return Math.round(workspace.width) === 878
                && Math.round(rail.width) === 462
                && Math.abs(workspace.top - rail.top) <= 1
                && Math.abs(workspace.bottom - rail.bottom) <= 1
                && getComputedStyle(document.querySelector('.create-md__detail')).display === 'flex'
                && Math.abs(tableScroll.clientWidth - tableScroll.scrollWidth) <= 1
                && getComputedStyle(tableScroll).overflowX === 'auto'
                && document.documentElement.scrollWidth <= document.documentElement.clientWidth;
            })()"""
        ),
    )
    viewport(1030, 914)
    top_row_geometry = evaluate(
        """(() => {
              const row = document.querySelector('.create-md__workspace-header-row').getBoundingClientRect();
              const workspace = document.querySelector('.create-md__workspace').getBoundingClientRect();
              const header = document.querySelector('.create-md__workspace-header');
              const headerRect = header.getBoundingClientRect();
              const headerStyle = getComputedStyle(header);
              const title = document.querySelector('[data-v2-title]').getBoundingClientRect();
              const back = document.querySelector('.create-md__back');
              const backRect = back.getBoundingClientRect();
              const iconBox = back.querySelector('.create-md__back-icon').getBoundingClientRect();
              const iconElement = back.querySelector('img');
              const icon = iconElement.getBoundingClientRect();
              const draft = document.querySelector('[data-v2-action="save-draft"]');
              const save = document.querySelector('[data-v2-action="save-card"]');
              const draftDisabled = draft.disabled;
              const saveDisabled = save.disabled;
              draft.disabled = true;
              save.disabled = true;
              const draftRect = draft.getBoundingClientRect();
              const saveRect = save.getBoundingClientRect();
              const backStyle = getComputedStyle(back);
              const draftStyle = getComputedStyle(draft);
              const result = {
                rowWidth: Math.round(row.width),
                rowHeight: Math.round(row.height),
                rowLeft: Math.round(row.left),
                rowRight: Math.round(row.right),
                expectedLeft: Math.round(workspace.left + parseFloat(headerStyle.paddingLeft)),
                expectedRight: Math.round(headerRect.right - parseFloat(headerStyle.paddingRight)),
                titleLeft: Math.round(title.left),
                backLeft: Math.round(backRect.left),
                backTopOffset: Math.round(backRect.top - row.top),
                backWidth: Math.round(backRect.width),
                backHeight: Math.round(backRect.height),
                iconBox: [Math.round(iconBox.width), Math.round(iconBox.height)],
                icon: [Math.round(icon.width), Math.round(icon.height)],
                backType: [backStyle.fontSize, backStyle.lineHeight, backStyle.fontWeight],
                backFont: backStyle.fontFamily,
                backColor: backStyle.color,
                backLetterSpacing: backStyle.letterSpacing,
                backGap: backStyle.gap,
                backPadding: [backStyle.paddingTop, backStyle.paddingRight, backStyle.paddingBottom, backStyle.paddingLeft],
                backCursor: backStyle.cursor,
                backTag: back.tagName,
                backName: back.getAttribute('aria-label'),
                iconSource: iconElement.currentSrc,
                buttonHeights: [Math.round(draftRect.height), Math.round(saveRect.height)],
                saveRight: Math.round(saveRect.right),
                actionGap: Math.round(saveRect.left - draftRect.right),
                buttonType: [draftStyle.fontSize, draftStyle.lineHeight, draftStyle.fontWeight],
                disabledColor: draftStyle.color
              };
              draft.disabled = draftDisabled;
              save.disabled = saveDisabled;
              return result;
            })()"""
    )
    check(
        "Top action row matches Figma 457:15595 geometry and typography",
        top_row_geometry.get("rowHeight") == 36
        and abs(top_row_geometry.get("rowLeft") - top_row_geometry.get("expectedLeft")) <= 1
        and abs(top_row_geometry.get("rowRight") - top_row_geometry.get("expectedRight")) <= 1
        and top_row_geometry.get("rowLeft") == top_row_geometry.get("titleLeft")
        and top_row_geometry.get("backLeft") == top_row_geometry.get("titleLeft")
        and top_row_geometry.get("backTopOffset") == 9
        and top_row_geometry.get("backWidth") == 121
        and top_row_geometry.get("backHeight") == 18
        and top_row_geometry.get("iconBox") == [16, 16]
        and top_row_geometry.get("icon") == [12, 10]
        and top_row_geometry.get("backType") == ["12px", "18px", "700"]
        and '"Open Sans"' in top_row_geometry.get("backFont")
        and top_row_geometry.get("backColor") == "rgb(84, 88, 201)"
        and top_row_geometry.get("backLetterSpacing") == "normal"
        and top_row_geometry.get("backGap") == "8px"
        and top_row_geometry.get("backPadding") == ["0px", "0px", "0px", "0px"]
        and top_row_geometry.get("backCursor") == "pointer"
        and top_row_geometry.get("backTag") == "A"
        and top_row_geometry.get("backName") == "Back to list view"
        and top_row_geometry.get("iconSource").endswith("/assets/ads-arrow-left.svg")
        and top_row_geometry.get("buttonHeights") == [36, 36]
        and top_row_geometry.get("saveRight") == top_row_geometry.get("rowRight")
        and top_row_geometry.get("actionGap") == 13
        and top_row_geometry.get("buttonType") == ["14px", "20px", "600"]
        and top_row_geometry.get("disabledColor") == "rgba(15, 18, 20, 0.3)",
        json.dumps(top_row_geometry),
    )
    back_clip = evaluate(
        """(() => {
          const rect = document.querySelector('.create-md__back').getBoundingClientRect();
          return {
            x: rect.left + scrollX - 4,
            y: rect.top + scrollY - 4,
            width: rect.width + 8,
            height: rect.height + 8
          };
        })()"""
    )
    screenshot_clip("back-control-rest", back_clip)
    back_center = evaluate(
        """(() => {
          const rect = document.querySelector('.create-md__back').getBoundingClientRect();
          return {x: rect.left + rect.width / 2, y: rect.top + rect.height / 2};
        })()"""
    )
    send(
        "Input.dispatchMouseEvent",
        {"type": "mouseMoved", "x": back_center["x"], "y": back_center["y"]},
    )
    time.sleep(0.05)
    check(
        "Back control hover keeps the Figma foreground and unified target",
        evaluate(
            """(() => {
              const back = document.querySelector('.create-md__back');
              const style = getComputedStyle(back);
              return back.matches(':hover')
                && style.color === 'rgb(84, 88, 201)'
                && style.textDecorationLine === 'underline'
                && [...back.children].every(child => getComputedStyle(child).pointerEvents === 'none');
            })()"""
        ),
    )
    screenshot_clip("back-control-hover", back_clip)
    send(
        "Input.dispatchMouseEvent",
        {
            "type": "mousePressed",
            "x": back_center["x"],
            "y": back_center["y"],
            "button": "left",
            "clickCount": 1,
        },
    )
    check(
        "Back control active state preserves the approved foreground",
        evaluate(
            """(() => {
              const back = document.querySelector('.create-md__back');
              return back.matches(':active')
                && getComputedStyle(back).color === 'rgb(84, 88, 201)';
            })()"""
        ),
    )
    screenshot_clip("back-control-active", back_clip)
    send(
        "Input.dispatchMouseEvent",
        {"type": "mouseReleased", "x": 1, "y": 1, "button": "left", "clickCount": 1},
    )
    send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": 1, "y": 1})
    send("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Tab", "code": "Tab"})
    send("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Tab", "code": "Tab"})
    evaluate("document.querySelector('.create-md__back').focus()")
    check(
        "Back control keyboard focus uses the visible ADS focus ring",
        evaluate(
            """(() => {
              const back = document.querySelector('.create-md__back');
              const style = getComputedStyle(back);
              return back.matches(':focus-visible')
                && style.outlineStyle === 'solid'
                && style.outlineWidth === '2px'
                && style.outlineColor === 'rgb(64, 69, 194)'
                && style.outlineOffset === '2px';
            })()"""
        ),
    )
    screenshot_clip("back-control-focus", back_clip)
    evaluate("document.querySelector('.create-md__back').blur()")
    navigate("?version=2.0&section=create")
    check(
        "Create and Edit share the constrained right-aligned save action group",
        evaluate(
            """(() => {
              const header = document.querySelector('.create-md__workspace-header');
              const headerRect = header.getBoundingClientRect();
              const style = getComputedStyle(header);
              const row = header.querySelector('.create-md__workspace-header-row').getBoundingClientRect();
              const actions = header.querySelector('.create-md__workspace-actions').getBoundingClientRect();
              const back = header.querySelector('.create-md__back');
              const backRect = back.getBoundingClientRect();
              const backStyle = getComputedStyle(back);
              return Math.abs(row.right - (headerRect.right - parseFloat(style.paddingRight))) <= 1
                && Math.abs(actions.right - row.right) <= 1
                && getComputedStyle(header.querySelector('.create-md__workspace-actions')).justifySelf === 'end'
                && Math.round(backRect.height) === 18
                && Math.round(backRect.width) === 121
                && backStyle.color === 'rgb(84, 88, 201)'
                && backStyle.fontSize === '12px'
                && backStyle.fontWeight === '700';
            })()"""
        ),
    )
    check(
        "LINE empty state uses approved button copy, centered grouping, and ADS spacing",
        evaluate(
            """(() => {
              const empty = document.querySelector('[data-v2-empty="lines"]');
              const description = empty.querySelector('p').getBoundingClientRect();
              const button = empty.querySelector('[data-v2-action="add-line"]');
              const buttonRect = button.getBoundingClientRect();
              const style = getComputedStyle(empty);
              return button.textContent.trim() === 'Add Line Item'
                && buttonRect.top - description.bottom >= 16
                && style.justifyItems === 'center'
                && style.textAlign === 'center'
                && Math.abs(
                  (buttonRect.left + buttonRect.width / 2)
                  - (empty.getBoundingClientRect().left + empty.getBoundingClientRect().width / 2)
                ) <= 1;
            })()"""
        ),
    )
    viewport(700)
    screenshot("unsupported-width-desktop-fallback")
    check(
        "Compact widths retain paired CARD fields without page overflow",
        evaluate(
            """(() => {
              const form = document.querySelector('[data-v2-form="card"]');
              const market = form.elements.marketplace.closest('.ads-dd')
                .querySelector('.ads-dd__trigger').getBoundingClientRect();
              const season = form.elements.dealSeason.closest('.ads-dd')
                .querySelector('.ads-dd__trigger').getBoundingClientRect();
              const start = form.querySelector('[data-field="v2-effective-start"] button').getBoundingClientRect();
              const end = form.querySelector('[data-field="v2-effective-end"] button').getBoundingClientRect();
              return season.y === market.y && end.y === start.y
                && market.width === season.width && start.width === end.width
                && document.documentElement.scrollWidth
                  <= document.documentElement.clientWidth;
            })()"""
        ),
    )
    viewport(1024, 900)
    navigate("?version=2.0&section=create&mode=edit&cardId=RC-DAS-WPP-VIDEO-UF-2627")
    # The guard is asked in the shared ADS confirmation dialog rather than
    # the browser's confirm(), so the answer is a click on one of its two
    # buttons instead of a stubbed return value.
    unsaved_navigation = evaluate(
        """(() => {
          const input = document.querySelector('[data-v2-form="card"]').elements.name;
          const originalUrl = location.href;
          const dialog = document.querySelector('[data-ads-confirm]');
          input.value += ' QA';
          input.dispatchEvent(new Event('input', {bubbles:true}));
          document.querySelector('.create-md__back').click();
          const asked = !dialog.hidden
            && dialog.querySelector('.modal__title').textContent.trim()
              === 'Leave without saving?';
          dialog.querySelector('[data-ads-confirm-action="cancel"].btn').click();
          const stayed = location.href === originalUrl
            && document.body.dataset.route === 'create'
            && input.value.endsWith(' QA');
          document.querySelector('.create-md__back').click();
          dialog.querySelector('[data-ads-confirm-action="confirm"]').click();
          const left = document.body.dataset.route === 'list'
            && !new URL(location.href).searchParams.has('mode')
            && !new URL(location.href).searchParams.has('cardId');
          return {asked, stayed, left};
        })()"""
    )
    check(
        "Back navigation preserves the unsaved-change confirmation flow",
        unsaved_navigation == {"asked": True, "stayed": True, "left": True},
        json.dumps(unsaved_navigation),
    )
    # --- Shared edit row alignment. Both direct grid children stretch to the
    # taller column, while the grid itself remains content-driven. ---
    navigate("?version=2.0&section=create&mode=edit&cardId=RC-DAS-WPP-VIDEO-UF-2627")
    workspace_geometry_js = """(() => {
      const ws = document.querySelector('.create-md__workspace');
      const detail = document.querySelector('.create-md__detail');
      const grid = document.querySelector('.create-md');
      const content = grid.parentElement;
      const footer = ws.querySelector('.create-md__table-footer');
      const lastCard = detail.querySelector('.create-md__accordion:last-child');
      const wsRect = ws.getBoundingClientRect();
      const detailRect = detail.getBoundingClientRect();
      const gridRect = grid.getBoundingClientRect();
      const contentRect = content.getBoundingClientRect();
      const footerRect = footer && footer.getBoundingClientRect();
      const lastCardRect = lastCard.getBoundingClientRect();
      return {
        top: Math.round(wsRect.top),
        height: Math.round(wsRect.height),
        bottom: Math.round(wsRect.bottom),
        gridHeight: Math.round(gridRect.height),
        workspaceTrailingSpace: footerRect
          ? Math.round(wsRect.bottom - footerRect.bottom) : null,
        detailBottom: Math.round(detailRect.bottom),
        detailHeight: Math.round(detailRect.height),
        detailTrailingSpace: Math.round(detailRect.bottom - lastCardRect.bottom),
        gridAlignItems: getComputedStyle(grid).alignItems,
        gridMaxWidth: getComputedStyle(grid).maxWidth,
        gridWidth: Math.round(gridRect.width),
        leftEdge: Math.round(wsRect.left),
        rightEdge: Math.round(detailRect.right),
        leftGutter: Math.round(gridRect.left - contentRect.left),
        rightGutter: Math.round(contentRect.right - gridRect.right),
        directChildren: ws.parentElement === grid && detail.parentElement === grid,
        topDifference: Math.abs(wsRect.top - detailRect.top),
        bottomDifference: Math.abs(wsRect.bottom - detailRect.bottom),
        horizontalOverflow: document.documentElement.scrollWidth
          > document.documentElement.clientWidth,
      };
    })()"""
    heights_by_vh = {}
    for test_height in (768, 900, 1080, 1200, 1440):
        viewport(1440, test_height)
        send("Runtime.evaluate", {"expression": "window.dispatchEvent(new Event('resize'))"})
        time.sleep(0.2)
        heights_by_vh[test_height] = evaluate(workspace_geometry_js)

    check(
        "Edit workspace and details rail are direct children of one stretching grid",
        all(g["directChildren"] and g["gridAlignItems"] == "stretch"
            for g in heights_by_vh.values()),
        json.dumps({h: {
            "direct": g["directChildren"], "align": g["gridAlignItems"]
        } for h, g in heights_by_vh.items()}),
    )
    check(
        "Edit workspace and details rail share exact top and bottom edges",
        all(g["topDifference"] <= 1 and g["bottomDifference"] <= 1
            and g["height"] == g["detailHeight"] for g in heights_by_vh.values()),
        json.dumps({h: {
            "top": g["topDifference"], "bottom": g["bottomDifference"],
            "leftHeight": g["height"], "rightHeight": g["detailHeight"]
        } for h, g in heights_by_vh.items()}),
    )
    check(
        "Shared edit row remains content-driven instead of viewport-capped",
        len({g["gridHeight"] for g in heights_by_vh.values()}) == 1
        and all(g["gridMaxWidth"] == "none" for g in heights_by_vh.values()),
        json.dumps({h: {
            "grid": g["gridHeight"], "maxWidth": g["gridMaxWidth"]
        } for h, g in heights_by_vh.items()}),
    )
    check(
        "Shared row introduces no horizontal overflow or left-table trailing gap",
        all(not g["horizontalOverflow"] and g["workspaceTrailingSpace"] <= 1
            and g["detailTrailingSpace"] >= 16 for g in heights_by_vh.values()),
        json.dumps({h: {
            "workspace": g["workspaceTrailingSpace"], "detail": g["detailTrailingSpace"]
        } for h, g in heights_by_vh.items()}),
    )

    width_geometry = {}
    for test_width in (1280, 1440, 1920, 2560):
        viewport(test_width, 1440)
        send("Runtime.evaluate", {"expression": "window.dispatchEvent(new Event('resize'))"})
        time.sleep(0.2)
        width_geometry[test_width] = evaluate(workspace_geometry_js)
    check(
        "Wider viewports preserve shared alignment without a fixed overall width",
        all(g["topDifference"] <= 1 and g["bottomDifference"] <= 1
            and g["gridMaxWidth"] == "none" and not g["horizontalOverflow"]
            for g in width_geometry.values())
        and all(g["workspaceTrailingSpace"] <= 1 for g in width_geometry.values())
        and all(g["leftGutter"] == g["rightGutter"] for g in width_geometry.values())
        and width_geometry[2560]["gridWidth"] > width_geometry[1920]["gridWidth"]
        and width_geometry[2560]["leftEdge"] - width_geometry[1920]["leftEdge"] <= 8
        and width_geometry[1280]["height"] >= width_geometry[1440]["height"]
        and width_geometry[1440]["height"] == width_geometry[1920]["height"],
        json.dumps({w: {
            "grid": g["gridHeight"], "workspace": g["height"]
        } for w, g in width_geometry.items()}),
    )

    viewport(1440, 900)
    navigate("?version=2.0&section=create")
    empty_state_height = evaluate(workspace_geometry_js)
    check(
        "New Rate Card uses the same shared-row alignment architecture",
        empty_state_height["topDifference"] <= 1
        and empty_state_height["bottomDifference"] <= 1
        and empty_state_height["height"] == empty_state_height["detailHeight"]
        and empty_state_height["gridAlignItems"] == "stretch"
        and not empty_state_height["horizontalOverflow"],
        json.dumps(empty_state_height),
    )

    # --- Shared-row behavior across desktop sizes and accordion states. The
    # outer rail stretches with the table while its accordion cards stay
    # naturally sized at the top. ---
    sidebar_viewports = (
        (1024, 768), (1024, 800), (1280, 720), (1280, 768),
        (1280, 800), (1280, 900), (1440, 900), (1920, 1080),
    )
    sidebar_states = ("card", "line", "premium", "collapsed")
    sidebar_modes = {
        "create": "?version=2.0&section=create",
        "edit": "?version=2.0&section=create&mode=edit&cardId=RC-DAS-WPP-VIDEO-UF-2627",
    }

    def set_sidebar_state(section):
        evaluate(
            """(() => {
              const section = %s;
              document.querySelectorAll('[data-v2-accordion]').forEach(card => {
                const open = card.dataset.v2Accordion === section;
                card.classList.toggle('is-open', open);
                const trigger = card.querySelector('.create-md__accordion-trigger');
                const panel = card.querySelector('.create-md__accordion-panel');
                trigger.setAttribute('aria-expanded', open ? 'true' : 'false');
                panel.hidden = !open;
              });
            })()""" % json.dumps("" if section == "collapsed" else section)
        )
        time.sleep(0.05)

    sidebar_metrics_js = """(() => {
      const detail = document.querySelector('.create-md__detail');
      const workspace = document.querySelector('.create-md__workspace');
      const grid = document.querySelector('.create-md');
      const page = document.querySelector('[data-page="create"]');
      const content = page.querySelector(':scope > .page__content');
      const cards = [...detail.querySelectorAll('.create-md__accordion')];
      const openCard = cards.find(card => card.classList.contains('is-open'));
      const panel = openCard && openCard.querySelector('.create-md__accordion-panel');
      const triggers = cards.map(card => card.querySelector('.create-md__accordion-trigger'));
      const detailRect = detail.getBoundingClientRect();
      const workspaceRect = workspace.getBoundingClientRect();
      const lastRect = cards[cards.length - 1].getBoundingClientRect();
      const snapshot = element => {
        const rect = element.getBoundingClientRect();
        const style = getComputedStyle(element);
        return {
          top: Math.round(rect.top), bottom: Math.round(rect.bottom),
          height: Math.round(rect.height), minHeight: style.minHeight,
          maxHeight: style.maxHeight, overflow: style.overflow,
          display: style.display, flex: style.flex, alignItems: style.alignItems
        };
      };
      return {
        viewport: {width: innerWidth, height: innerHeight},
        html: snapshot(document.documentElement),
        body: snapshot(document.body),
        page: snapshot(page),
        content: snapshot(content),
        grid: snapshot(grid),
        workspace: snapshot(workspace),
        detail: snapshot(detail),
        cards: cards.map(snapshot),
        panel: panel ? {
          ...snapshot(panel),
          clientHeight: panel.clientHeight,
          scrollHeight: panel.scrollHeight,
          scrollTop: panel.scrollTop,
          gutter: getComputedStyle(panel).scrollbarGutter
        } : null,
        headersVisible: triggers.every(trigger => {
          const rect = trigger.getBoundingClientRect();
          return rect.top >= detailRect.top
            && rect.bottom <= detailRect.bottom;
        }),
        finalBoundaryVisible: lastRect.bottom <= detailRect.bottom
          && parseFloat(getComputedStyle(cards[cards.length - 1]).borderBottomRightRadius) > 0,
        aligned: Math.abs(workspaceRect.top - detailRect.top) <= 1
          && Math.abs(workspaceRect.bottom - detailRect.bottom) <= 1,
        horizontalOverflow: document.documentElement.scrollWidth
          > document.documentElement.clientWidth,
        pageScrollHeight: document.documentElement.scrollHeight,
        pageClientHeight: document.documentElement.clientHeight
      };
    })()"""

    sidebar_matrix = {}
    for mode, query in sidebar_modes.items():
        navigate(query)
        for test_width, test_height in sidebar_viewports:
            viewport(test_width, test_height)
            state_metrics = {}
            for section in sidebar_states:
                set_sidebar_state(section)
                metrics = evaluate(sidebar_metrics_js)
                state_metrics[section] = metrics
                open_panel_ok = section == "collapsed" or (
                    metrics["panel"]["overflow"] in ("auto", "scroll")
                    and metrics["panel"]["minHeight"] == "0px"
                    and metrics["panel"]["gutter"].startswith("stable")
                )
                open_card_ok = section == "collapsed" or (
                    metrics["cards"][sidebar_states.index(section)]["flex"].startswith("0 0")
                )
                check(
                    f"{mode} {test_width}x{test_height} {section}: shared row stays aligned",
                    metrics["headersVisible"]
                    and metrics["finalBoundaryVisible"]
                    and metrics["aligned"]
                    and metrics["detail"]["overflow"] == "hidden"
                    and not metrics["horizontalOverflow"]
                    and open_panel_ok
                    and open_card_ok,
                    json.dumps(metrics),
                )
                if (mode == "edit" and test_width in (1024, 1280)
                        and test_height == (768 if test_width == 1024 else 800)
                        and section != "collapsed"):
                    screenshot(f"sidebar-{test_width}x{test_height}-{section}")
            sidebar_matrix[(mode, test_width, test_height)] = state_metrics
            page_heights = [metrics["pageScrollHeight"] for metrics in state_metrics.values()]
            check(
                f"{mode} {test_width}x{test_height}: accordion states preserve shared-row alignment",
                all(metrics["aligned"] for metrics in state_metrics.values())
                and all(not metrics["horizontalOverflow"] for metrics in state_metrics.values()),
                json.dumps(dict(zip(sidebar_states, page_heights))),
            )

    viewport(1024, 768)
    navigate(sidebar_modes["edit"])
    set_sidebar_state("card")
    constrained_dropdown = evaluate(
        """(() => {
          const trigger = document.querySelector('#v2-marketplace-trigger');
          const panel = trigger.closest('.create-md__accordion-panel');
          trigger.scrollIntoView({block:'center'});
          trigger.click();
          const menu = document.querySelector('#v2-marketplace-menu');
          const panelRect = panel.getBoundingClientRect();
          const menuRect = menu.getBoundingClientRect();
          return {
            expanded: trigger.getAttribute('aria-expanded'),
            menuVisible: !menu.hidden,
            insidePanel: menuRect.top >= panelRect.top && menuRect.bottom <= panelRect.bottom,
            panelOverflow: getComputedStyle(panel).overflowY
          };
        })()"""
    )
    check(
        "Constrained sidebar keeps ADS Dropdown menus inside the visible expanded panel",
        constrained_dropdown == {
            "expanded": "true",
            "menuVisible": True,
            "insidePanel": True,
            "panelOverflow": "auto",
        },
        json.dumps(constrained_dropdown),
    )
    evaluate("document.querySelector('#v2-marketplace-trigger').click()")
    constrained_date_picker = evaluate(
        """(() => {
          const trigger = document.querySelector(
            '[data-field="v2-effective-start"] button'
          );
          trigger.scrollIntoView({block:'center'});
          trigger.click();
          const popover = document.querySelector(
            'body > .ads-datepicker__popover:not([hidden])'
          );
          const rect = popover && popover.getBoundingClientRect();
          return {
            portaled: Boolean(popover),
            visible: Boolean(rect && rect.top >= 0 && rect.bottom <= innerHeight),
            outsidePanel: Boolean(popover
              && !popover.closest('.create-md__accordion-panel'))
          };
        })()"""
    )
    check(
        "Constrained sidebar keeps the portaled Date Picker visible",
        constrained_date_picker == {
            "portaled": True,
            "visible": True,
            "outsidePanel": True,
        },
        json.dumps(constrained_date_picker),
    )
    send("Input.dispatchKeyEvent", {
        "type": "keyDown", "key": "Escape", "code": "Escape",
        "windowsVirtualKeyCode": 27
    })
    set_sidebar_state("line")
    natural_growth = evaluate(
        """(() => {
          const grid = document.querySelector('.create-md');
          const workspace = document.querySelector('.create-md__workspace');
          const detail = document.querySelector('.create-md__detail');
          const panel = detail.querySelector(
            '[data-v2-accordion="line"] .create-md__accordion-panel'
          );
          const before = grid.getBoundingClientRect().height;
          const probe = document.createElement('div');
          probe.dataset.qaNaturalGrowth = '';
          probe.style.height = '200px';
          panel.appendChild(probe);
          const gridRect = grid.getBoundingClientRect();
          const workspaceRect = workspace.getBoundingClientRect();
          const detailRect = detail.getBoundingClientRect();
          probe.remove();
          return {
            grew: gridRect.height > before,
            aligned: Math.abs(workspaceRect.top - detailRect.top) <= 1
              && Math.abs(workspaceRect.bottom - detailRect.bottom) <= 1
          };
        })()"""
    )
    check(
        "Taller accordion content grows the shared row and preserves alignment",
        natural_growth == {"grew": True, "aligned": True},
        json.dumps(natural_growth),
    )

    # Page scale does not alter the shared-row allocation.
    viewport(1280, 800)
    navigate(sidebar_modes["edit"])
    zoom_metrics = {}
    for zoom in (1, 1.25, 1.5):
        send("Emulation.setPageScaleFactor", {"pageScaleFactor": zoom})
        set_sidebar_state("card")
        zoom_metrics[str(zoom)] = evaluate(sidebar_metrics_js)
    send("Emulation.setPageScaleFactor", {"pageScaleFactor": 1})
    check(
        "Right rail stays aligned at 100%, 125%, and 150% page scale",
        all(metrics["headersVisible"]
            and metrics["finalBoundaryVisible"]
            and metrics["aligned"]
            and metrics["detail"]["overflow"] == "hidden"
            for metrics in zoom_metrics.values()),
        json.dumps(zoom_metrics),
    )
    with open(os.path.join(OUT, "sidebar-layout-report.json"), "w", encoding="utf-8") as report_file:
        json.dump(
            {
                "1024x768": sidebar_matrix[("edit", 1024, 768)],
                "1280x800": sidebar_matrix[("edit", 1280, 800)],
                "zoom": zoom_metrics,
            },
            report_file,
            indent=2,
        )

    # --- Scoped Rate Card title typography and single-line truncation. ---
    title_viewports = (1024, 1280, 1440, 1920, 2560)
    short_title = "WPP – Upfront 2025–2026"
    # Long enough to overflow the scoped title column even at 2560px.
    long_title = (
        "Publicis Media Investment – National Streaming and Live Sports "
        "Sponsorship Multi-Year 2025–2026"
    )

    def set_rate_card_name(value):
        evaluate(
            """(() => {
              const input = document.querySelector('[data-v2-form="card"] [name="name"]');
              input.value = %s;
              input.dispatchEvent(new Event('input', {bubbles:true}));
            })()""" % json.dumps(value)
        )
        time.sleep(0.3)

    title_metrics_js = """(() => {
      const title = document.querySelector('[data-v2-title]');
      const helper = document.querySelector('[data-v2-helper]');
      const header = document.querySelector('.create-md__workspace-header');
      const actions = document.querySelector('.create-md__workspace-actions');
      const accordionTitle = document.querySelector('.create-md__accordion-title');
      const style = getComputedStyle(title);
      const rect = title.getBoundingClientRect();
      const helperRect = helper.getBoundingClientRect();
      const tabsRect = document.querySelector('.create-md__tabs').getBoundingClientRect();
      const headerRect = header.getBoundingClientRect();
      const actionsRect = actions.getBoundingClientRect();
      const range = document.createRange();
      range.selectNodeContents(title);
      const textRect = range.getBoundingClientRect();
      const accordionStyle = getComputedStyle(accordionTitle);
      return {
        text: title.textContent,
        ariaLabel: title.getAttribute('aria-label'),
        tooltip: title.getAttribute('data-tooltip'),
        rect: [rect.left, rect.top, rect.width, rect.height],
        titleBottom: rect.bottom,
        helperHidden: helper.hidden,
        helperRects: helper.getClientRects().length,
        helperTop: helperRect.top,
        helperBottom: helperRect.bottom,
        tabsTop: tabsRect.top,
        headerHeight: headerRect.height,
        actions: [actionsRect.left, actionsRect.top, actionsRect.width, actionsRect.height],
        textWidth: textRect.width,
        clientWidth: title.clientWidth,
        scrollWidth: title.scrollWidth,
        fontFamily: style.fontFamily,
        fontSize: style.fontSize,
        fontStyle: style.fontStyle,
        fontWeight: style.fontWeight,
        lineHeight: style.lineHeight,
        letterSpacing: style.letterSpacing,
        color: style.color,
        display: style.display,
        minWidth: style.minWidth,
        maxWidth: style.maxWidth,
        overflow: style.overflow,
        textOverflow: style.textOverflow,
        whiteSpace: style.whiteSpace,
        accordionTypography: [
          accordionStyle.fontFamily,
          accordionStyle.fontSize,
          accordionStyle.fontWeight,
          accordionStyle.lineHeight
        ]
      };
    })()"""

    title_results = {}
    for test_width in title_viewports:
        viewport(test_width, 900)
        navigate("?version=2.0&section=create")
        empty_metrics = evaluate(title_metrics_js)
        if test_width == 1024:
            screenshot("rate-card-create-empty-name")
        evaluate(
            """document.querySelector(
              '[data-v2-form="card"] [name="name"]'
            ).focus()"""
        )
        set_rate_card_name(short_title)
        short_metrics = evaluate(title_metrics_js)
        set_rate_card_name(long_title)
        long_metrics = evaluate(title_metrics_js)
        title_results[str(test_width)] = {
            "empty": empty_metrics,
            "short": short_metrics,
            "long": long_metrics,
        }
        check(
            f"Rate Card title uses heading/lg typography at {test_width}px",
            long_metrics["fontFamily"] == '"MultiplaneTWDC Display"'
            and long_metrics["fontSize"] == "24px"
            and long_metrics["fontStyle"] == "normal"
            and long_metrics["fontWeight"] == "500"
            and long_metrics["lineHeight"] == "28px"
            and long_metrics["letterSpacing"] in ("0px", "normal")
            and long_metrics["color"] == "rgb(22, 28, 30)",
            json.dumps(long_metrics),
        )
        check(
            f"Rate Card title truncates only overflowing text at {test_width}px",
            short_metrics["scrollWidth"] <= short_metrics["clientWidth"] + 1
            and long_metrics["scrollWidth"] > long_metrics["clientWidth"] + 1
            and long_metrics["textWidth"] > long_metrics["clientWidth"]
            and long_metrics["display"] == "block"
            and long_metrics["minWidth"] == "0px"
            and long_metrics["overflow"] == "hidden"
            and long_metrics["textOverflow"] == "ellipsis"
            and long_metrics["whiteSpace"] == "nowrap"
            and long_metrics["text"] == long_title
            and long_metrics["ariaLabel"] == long_title
            and long_metrics["tooltip"] == long_title,
            json.dumps({"short": short_metrics, "long": long_metrics}),
        )
        check(
            f"Rate Card title leaves header, helper, and Save actions unchanged at {test_width}px",
            short_metrics["rect"] == long_metrics["rect"]
            and short_metrics["helperTop"] == long_metrics["helperTop"]
            and short_metrics["headerHeight"] == long_metrics["headerHeight"]
            and short_metrics["actions"] == long_metrics["actions"]
            and long_metrics["accordionTypography"]
              == ['"Open Sans"', "18px", "600", "24px"],
            json.dumps({"short": short_metrics, "long": long_metrics}),
        )
        check(
            f"Rate Card description follows the trimmed Card Name at {test_width}px",
            not empty_metrics["helperHidden"]
            and empty_metrics["helperRects"] == 1
            and empty_metrics["tabsTop"] > empty_metrics["titleBottom"]
            and short_metrics["helperHidden"]
            and short_metrics["helperRects"] == 0
            and short_metrics["tabsTop"] < empty_metrics["tabsTop"]
            and long_metrics["helperHidden"]
            and long_metrics["helperRects"] == 0,
            json.dumps({
                "empty": empty_metrics,
                "short": short_metrics,
                "long": long_metrics,
            }),
        )

    viewport(1280, 900)
    navigate("?version=2.0&section=create&mode=edit&cardId=RC-DAS-WPP-VIDEO-UF-2627")
    edit_title_metrics = evaluate(title_metrics_js)
    screenshot("rate-card-edit-named")
    check(
        "Create, Edit, populated, and empty Rate Card states share the scoped title style",
        edit_title_metrics["fontFamily"] == '"MultiplaneTWDC Display"'
        and edit_title_metrics["fontSize"] == "24px"
        and edit_title_metrics["fontWeight"] == "500"
        and edit_title_metrics["lineHeight"] == "28px"
        and edit_title_metrics["color"] == "rgb(22, 28, 30)"
        and edit_title_metrics["helperHidden"]
        and edit_title_metrics["helperRects"] == 0
        and edit_title_metrics["ariaLabel"] == edit_title_metrics["text"]
        and all(
            result["short"]["fontSize"] == edit_title_metrics["fontSize"]
            and result["short"]["fontWeight"] == edit_title_metrics["fontWeight"]
            and result["short"]["lineHeight"] == edit_title_metrics["lineHeight"]
            for result in title_results.values()
        ),
        json.dumps(edit_title_metrics),
    )
    with open(os.path.join(OUT, "rate-card-title-report.json"), "w", encoding="utf-8") as report_file:
        json.dump(
            {
                "viewports": title_results,
                "edit": edit_title_metrics,
            },
            report_file,
            indent=2,
        )
    viewport(1440, 960)

    # --- DCM Rule Order: plain text input, no native stepper, digits-only
    # via JS filter (mirrors the v1.1/v1.2 #dcm-rule pattern in app.js) ---
    navigate("?version=2.0&section=create&mode=edit&cardId=RC-DAS-WPP-VIDEO-UF-2627")
    dcm_geometry = evaluate(
        """(() => {
          const input = document.getElementById('v2-rule-order');
          const cs = getComputedStyle(input);
          const rect = input.getBoundingClientRect();
          return {
            type: input.type,
            inputMode: input.inputMode,
            pattern: input.getAttribute('pattern'),
            hasStep: input.hasAttribute('step'),
            hasMin: input.hasAttribute('min'),
            placeholder: input.placeholder,
            width: Math.round(rect.width),
            height: Math.round(rect.height),
            padding: [cs.paddingTop, cs.paddingRight, cs.paddingBottom, cs.paddingLeft],
            border: cs.borderTopWidth + ' ' + cs.borderTopStyle,
            radius: cs.borderRadius,
          };
        })()"""
    )
    check(
        "DCM Rule Order is a plain text input with no native number stepper (type, inputmode, no step/min)",
        dcm_geometry["type"] == "text" and dcm_geometry["inputMode"] == "numeric"
        and not dcm_geometry["hasStep"] and not dcm_geometry["hasMin"]
        and dcm_geometry["placeholder"] == "e.g. 10",
        json.dumps(dcm_geometry),
    )
    dcm_reference_geometry = evaluate(
        """(() => {
          const reference = document.querySelector('[data-v2-card-field="buying-id"] .field__input');
          const cs = getComputedStyle(reference);
          const rect = reference.getBoundingClientRect();
          return {
            width: Math.round(rect.width),
            height: Math.round(rect.height),
            padding: [cs.paddingTop, cs.paddingRight, cs.paddingBottom, cs.paddingLeft],
            border: cs.borderTopWidth + ' ' + cs.borderTopStyle,
            radius: cs.borderRadius,
          };
        })()"""
    )
    check(
        "DCM Rule Order keeps the same width, height, padding, border, and radius as sibling text fields",
        dcm_geometry["height"] == dcm_reference_geometry["height"]
        and dcm_geometry["padding"] == dcm_reference_geometry["padding"]
        and dcm_geometry["border"] == dcm_reference_geometry["border"]
        and dcm_geometry["radius"] == dcm_reference_geometry["radius"],
        json.dumps({"dcm": dcm_geometry, "reference": dcm_reference_geometry}),
    )
    dcm_typing = evaluate(
        """(() => {
          const input = document.getElementById('v2-rule-order');
          input.focus();
          input.value = '';
          document.execCommand && void 0;
          function setValue(v) {
            input.value = v;
            input.dispatchEvent(new Event('input', {bubbles: true}));
          }
          setValue('1a2b3');
          const afterLetters = input.value;
          setValue('');
          setValue('-7');
          const afterDash = input.value;
          setValue('');
          setValue('12.5');
          const afterDecimal = input.value;
          setValue('');
          setValue('42');
          const afterDigitsOnly = input.value;
          return {afterLetters, afterDash, afterDecimal, afterDigitsOnly};
        })()"""
    )
    check(
        "DCM Rule Order strips non-digit characters as the user types (letters, minus sign, decimal point)",
        dcm_typing == {"afterLetters": "123", "afterDash": "7", "afterDecimal": "125", "afterDigitsOnly": "42"},
        json.dumps(dcm_typing),
    )
    dcm_save = evaluate(
        """(() => {
          const input = document.getElementById('v2-rule-order');
          input.value = '';
          input.dispatchEvent(new Event('input', {bubbles: true}));
          input.value = '250';
          input.dispatchEvent(new Event('input', {bubbles: true}));
          input.dispatchEvent(new Event('change', {bubbles: true}));
          input.dispatchEvent(new Event('focusout', {bubbles: true}));
          return {fieldValue: input.value};
        })()"""
    )
    check(
        "DCM Rule Order accepts a typed numeric value without native validation blocking it "
        "(existing app validation, not a browser number-input constraint, governs it)",
        dcm_save["fieldValue"] == "250",
        json.dumps(dcm_save),
    )
    evaluate(
        "document.getElementById('v2-rule-order').value = ''; "
        "document.getElementById('v2-rule-order').dispatchEvent(new Event('input', {bubbles: true}));"
    )

    # --- Premiums table: the Figma 697:3617 column order, with Base
    # offering second. Cell indexes below count DOM position, and cell 0 is
    # always the bulk-selection checkbox column (hidden here on 2.0). ---
    evaluate("document.querySelector('[data-v2-tab=\"premiums\"]').click()")
    premium_base_offering_headers = evaluate(
        """[...document.querySelectorAll('[data-v2-table-region="premiums"] thead th')]
          .map(th => th.textContent.trim())"""
    )
    check(
        "Premiums table header follows the Figma order, Base offering right after Premium",
        premium_base_offering_headers == [
            "", "Premium", "Base offering", "Category", "Value",
            "Calculation method", "Advertiser"
        ],
        json.dumps(premium_base_offering_headers),
    )
    premium_base_offering_rows = evaluate(
        """(() => {
          const rows = [...document.querySelectorAll('[data-v2-tbody="premiums"] tr')];
          return Object.fromEntries(rows.map(row => [row.cells[1].textContent.trim(), row.cells[2].textContent.trim()]));
        })()"""
    )
    # Every WPP premium prices a named set of offerings, so no row may fall
    # back to a blank cell or to anything outside the card's vocabulary.
    catalog_offerings = {
        "Disney+ Select", "Hulu Select", "Disney Streaming Bundle",
        "ESPN Streaming Sports", "Disney Streaming Live Events",
    }
    offering_problems = [
        f"{name}: {offering!r}"
        for name, offering in premium_base_offering_rows.items()
        if not offering
        or any(part.strip() not in catalog_offerings for part in offering.split(","))
    ]
    check(
        "Every WPP Premium row names the offerings it prices, from the card's own vocabulary",
        len(premium_base_offering_rows) == 10 and not offering_problems,
        json.dumps({"rows": premium_base_offering_rows, "problems": offering_problems}),
    )
    premium_table_scroll = evaluate(
        """(() => {
          const scroll = document.querySelector('[data-v2-table-region="premiums"] .create-md__table-scroll');
          return {scrollWidth: scroll.scrollWidth, clientWidth: scroll.clientWidth};
        })()"""
    )
    check(
        "All Premiums columns, including Base offering, fit without horizontal scroll at the reference desktop width",
        premium_table_scroll["scrollWidth"] <= premium_table_scroll["clientWidth"] + 1,
        json.dumps(premium_table_scroll),
    )
    premium_base_offering_tooltip = evaluate(
        """(() => {
          const row = [...document.querySelectorAll('[data-v2-tbody="premiums"] tr')]
            .find(tr => tr.cells[1].textContent.trim() === 'Authenticated Streaming Household Premium');
          if (!row) return null;
          const cell = row.cells[2];
          return {
            text: cell.textContent.trim(),
            tooltip: cell.getAttribute('data-tooltip'),
            truncate: cell.getAttribute('data-tooltip-truncate')
          };
        })()"""
    )
    check(
        "Base offering cells expose the shared truncation tooltip like the rest of the row",
        premium_base_offering_tooltip is not None
        and premium_base_offering_tooltip["tooltip"]
        == "Disney+ Select, Hulu Select, Disney Streaming Bundle"
        and premium_base_offering_tooltip["truncate"] == "auto",
        json.dumps(premium_base_offering_tooltip),
    )
    evaluate(
        """(() => {
          const search = document.querySelector('[data-v2-search="premiums"]');
          search.value = 'bundle';
          search.dispatchEvent(new Event('input', {bubbles:true}));
        })()"""
    )
    premium_base_offering_search = evaluate(
        """[...document.querySelectorAll('[data-v2-tbody="premiums"] tr')]
          .map(row => ({name: row.cells[1].textContent.trim(), offering: row.cells[2].textContent.trim()}))"""
    )
    check(
        # "bundle" appears only in Base offering text on this card, never in a
        # Premium name, so every hit proves the column itself is searchable.
        "Premium search matches Base offering text, so 'bundle' finds only Streaming Bundle premiums",
        premium_base_offering_search
        and all("Bundle" in row["offering"] and "bundle" not in row["name"].lower()
                for row in premium_base_offering_search),
        json.dumps(premium_base_offering_search),
    )
    evaluate(
        """(() => {
          const search = document.querySelector('[data-v2-search="premiums"]');
          search.value = '';
          search.dispatchEvent(new Event('input', {bubbles:true}));
        })()"""
    )
    evaluate("document.querySelector('[data-v2-sort=\"premiums:baseOffering\"]').click()")
    premium_base_offering_sort_asc = evaluate(
        """[...document.querySelectorAll('[data-v2-tbody="premiums"] tr')].map(row => row.cells[2].textContent.trim())"""
    )
    check(
        "Base offering column sorts ascending across its real values",
        premium_base_offering_sort_asc == sorted(premium_base_offering_sort_asc, key=str.lower),
        json.dumps(premium_base_offering_sort_asc),
    )

    navigate("?version=2.0&section=create")
    dcm_create_type = evaluate(
        """(() => {
          const input = document.getElementById('v2-rule-order');
          return input ? input.type : 'missing';
        })()"""
    )
    check(
        "New Rate Card uses the same DCM Rule Order text input as Edit Rate Card (single shared element)",
        dcm_create_type == "text",
        dcm_create_type,
    )

    check("No runtime exceptions", len(console_messages) == 0, "\n".join(console_messages[:3]))

finally:
    report = {
        "passes": sum(item["status"] == "PASS" for item in results),
        "failures": sum(item["status"] == "FAIL" for item in results),
        "results": results,
        "console": console_messages,
    }
    with open(os.path.join(OUT, "report.json"), "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print(json.dumps({"passes": report["passes"], "failures": report["failures"]}))
    ws.close()
    chrome.terminate()
    server.shutdown()
