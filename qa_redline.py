"""Production Redline Mode browser QA.

Run with: python3 qa_redline.py
"""

import base64
import json
import os
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import urlopen

import websocket


ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = 8992
DEBUG_PORT = 9292
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
OUT = "/tmp/rate-card-redline-qa"
os.makedirs(OUT, exist_ok=True)


class StaticHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0] or "/index.html"
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
        }.get(os.path.splitext(filename)[1], "text/plain")
        with open(filename, "rb") as handle:
            payload = handle.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, *_args):
        return


server = ThreadingHTTPServer(("127.0.0.1", PORT), StaticHandler)
threading.Thread(target=server.serve_forever, daemon=True).start()
profile = "/tmp/rate_card_redline_qa_profile"
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
failures = []
passes = 0
console_messages = []


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
        if event.get("method") == "Runtime.consoleAPICalled":
            if event.get("params", {}).get("type") in ("error", "warning"):
                console_messages.append(event.get("params", {}).get("type", "console"))
        if event.get("id") == expected:
            return event


def evaluate(expression):
    result = send(
        "Runtime.evaluate",
        {"expression": expression, "returnByValue": True, "awaitPromise": True},
    )
    return result.get("result", {}).get("result", {}).get("value")


def check(name, condition, detail=""):
    global passes
    if condition:
        passes += 1
        print(f"[PASS] {name}")
    else:
        failures.append({"name": name, "detail": detail})
        print(f"[FAIL] {name}: {detail}")


def screenshot(name):
    payload = send("Page.captureScreenshot", {"format": "png"})
    data = payload.get("result", {}).get("data", "")
    with open(os.path.join(OUT, name + ".png"), "wb") as handle:
        handle.write(base64.b64decode(data))


def wait_for(expression, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if evaluate(expression):
            return True
        time.sleep(0.1)
    return False


try:
    send("Runtime.enable")
    send("Page.enable")
    send(
        "Page.navigate",
        {
            "url": (
                f"http://127.0.0.1:{PORT}/?version=2.0&section=create"
                "&mode=edit&cardId=RC-DAS-WPP-VIDEO-UF-2627"
            )
        },
    )
    # A cold profile can take longer than a fixed sleep to commit the new
    # document, and every probe below reads document.body.
    wait_for("!!document.body && !!document.body.getAttribute('data-route')", 15)
    time.sleep(1.3)

    hidden = evaluate(
        """(() => ({
          root: document.querySelectorAll('.redline').length,
          ui: document.querySelectorAll(
            '.redline__header,.redline__sidebar,.redline__grid,.redline__label,.redline__svg'
          ).length,
          bodyWidth: document.body.getBoundingClientRect().width,
          entry: document.querySelectorAll('[data-action="toggle-redline"]').length
        }))()"""
    )
    # bodyWidth is a sanity measurement, not a redline check: the table
    # header standardization (39px, matching the List View) makes this
    # tab's content ~7px taller, so at this fixed 1440x960 window the page
    # now grows a vertical scrollbar (by design, containers are min-height
    # and grow to fit content) which shaves the scrollbar's width off
    # body.getBoundingClientRect().width. window.innerWidth stays 1440.
    check(
        "Redline UI is absent before activation",
        hidden["root"] == 0
        and hidden["ui"] == 0
        and hidden["entry"] == 1
        and 1420 <= hidden["bodyWidth"] <= 1440,
        json.dumps(hidden),
    )
    menu_order = evaluate(
        """(() => {
          const menu = document.querySelector('#profile-menu');
          const theme = menu.querySelector('[data-submenu="theme"]');
          const redline = menu.querySelector('[data-action="toggle-redline"]');
          const divider = redline.nextElementSibling;
          return {
            afterTheme: theme.nextElementSibling === redline,
            divider: divider?.classList.contains('profile-menu__divider'),
            logout: divider?.nextElementSibling?.dataset.action,
            role: redline.getAttribute('role'),
            checked: redline.getAttribute('aria-checked'),
            iconCount: redline.querySelectorAll('img, svg').length,
            label: redline.firstElementChild?.textContent.trim(),
            noIconWrapper: !redline.querySelector('.profile-menu__item-label')
          };
        })()"""
    )
    check(
        "Profile menu order and toggle semantics are correct",
        menu_order
        == {
            "afterTheme": True,
            "divider": True,
            "logout": "logout",
            "role": "menuitemcheckbox",
            "checked": "false",
            "iconCount": 0,
            "label": "Redline",
            "noIconWrapper": True,
        },
        json.dumps(menu_order),
    )
    check(
        "Profile menu anchors four pixels below the avatar with aligned labels",
        evaluate(
            """(() => {
              const trigger = document.querySelector('[data-action="toggle-profile"]');
              const menu = document.querySelector('#profile-menu');
              trigger.click();
              const triggerRect = trigger.getBoundingClientRect();
              const menuRect = menu.getBoundingClientRect();
              const items = [...menu.querySelectorAll(
                ':scope > .profile-menu__item, :scope > .profile-menu__sub-wrap > .profile-menu__item'
              )];
              const labelLefts = items.map(item =>
                item.querySelector('span').getBoundingClientRect().left
              );
              const rowHeights = items.map(item =>
                Math.round(item.getBoundingClientRect().height)
              );
              trigger.click();
              return Math.round(menuRect.top - triggerRect.bottom) === 4
                && Math.round(menuRect.right - triggerRect.right) === 0
                && labelLefts.every(left => Math.abs(left - labelLefts[0]) < 0.5)
                && rowHeights.every(height => height === 40);
            })()"""
        ),
    )

    evaluate(
        """(() => {
          document.querySelector('[data-action="toggle-profile"]').click();
          document.querySelector('[data-action="toggle-redline"]').click();
        })()"""
    )
    check("Profile menu activates Redline", wait_for("window.RedlineMode.isActive()"))
    check(
        "Activation mounts one overlay without a breakpoint preview",
        wait_for(
            """document.querySelectorAll('.redline').length === 1
            && document.querySelector('.redline__preview')?.hidden
            && window.RedlineMode.debugState().breakpoint === ''"""
        ),
    )
    defaults = evaluate(
        """(() => ({
          clean: document.querySelector('[data-redline-action="mode:clean"]').getAttribute('aria-pressed'),
          grid: document.querySelector('[data-redline-action="mode:grid"]').getAttribute('aria-pressed'),
          type: document.querySelector('[data-redline-action="toggle:typography"]').getAttribute('aria-pressed'),
          color: document.querySelector('[data-redline-action="toggle:color"]').getAttribute('aria-pressed'),
          lines: document.querySelector('[data-redline-action="annotation:lines"]').checked,
          overlay: document.querySelector('[data-redline-action="annotation:grid-overlay"]').checked,
          route: document.body.dataset.route,
          frameHidden: document.querySelector('.redline__preview').hidden,
          selectedBreakpoints: document.querySelectorAll(
            '[data-redline-action^="breakpoint:"][aria-pressed="true"]'
          ).length,
          currentPressed: document.querySelector(
            '[data-redline-action="breakpoint:current"]'
          ).getAttribute('aria-pressed'),
          presentation: document.querySelector('.redline').dataset.breakpointActive
        }))()"""
    )
    check(
        "Defaults and same route are preserved",
        defaults
        == {
            "clean": "true",
            "grid": "false",
            "type": "false",
            "color": "false",
            "lines": True,
            "overlay": False,
            "route": "create",
            "frameHidden": True,
            "selectedBreakpoints": 1,
            "currentPressed": "true",
            "presentation": "false",
        },
        json.dumps(defaults),
    )
    shell = evaluate(
        """(() => {
          const q = s => document.querySelector(s);
          const rows = [...document.querySelectorAll('[data-redline-action^="breakpoint:"]')];
          const forbidden = /mobile|tablet|desktop|laptop|wide|ultrawide/i;
          return {
            noFloatingBars: document.querySelectorAll(
              '.redline__toolbar, [data-redline-color-panel]'
            ).length,
            headers: document.querySelectorAll('.redline__header').length,
            title: q('.redline__title')?.textContent,
            badge: q('[data-redline-version-badge]')?.textContent,
            hasClose: !!q('.redline__header [data-redline-action="close"]'),
            sections: [...document.querySelectorAll('[data-redline-section]')]
              .map(s => s.dataset.redlineSection),
            sectionLabels: [...document.querySelectorAll('.redline__section-label')]
              .map(l => l.textContent),
            names: rows.map(r => r.querySelector('.redline__breakpoint-name').textContent),
            sizes: rows.map(r => r.querySelector('.redline__breakpoint-size')?.textContent || ''),
            forbiddenNames: rows.some(r => forbidden.test(r.textContent)),
            segments: [...document.querySelectorAll('[data-redline-action^="mode:"]')]
              .map(b => b.textContent),
            inspection: [...document.querySelectorAll('[data-redline-action^="toggle:"]')]
              .map(b => b.textContent),
            annotations: [...document.querySelectorAll('.redline__checkbox-label')]
              .map(l => l.textContent),
            selection: q('[data-redline-selection]')?.textContent,
            inspectorEmpty: [...document.querySelectorAll('.redline__inspect-empty p')]
              .map(p => p.textContent),
            hint: q('[data-redline-mode-hint]')?.textContent
          };
        })()"""
    )
    check(
        "Redline shell replaces floating bars with a header and left control panel",
        shell["noFloatingBars"] == 0
        and shell["headers"] == 1
        and shell["title"] == "Redline Mode"
        and shell["badge"] == "Rate Card V2.0"
        and shell["hasClose"]
        and shell["sections"]
        == [
            "breakpoint",
            "measurement",
            "inspection",
            "annotations",
            "app-sidebar",
            "components",
            "overlays",
            "selection",
        ]
        and shell["sectionLabels"]
        == [
            "Breakpoint",
            "Measurement mode",
            "Inspection",
            "Annotations",
            "App sidebar",
            "Table components",
            "Overlays",
            "Selection",
        ],
        json.dumps(shell),
    )
    check(
        "Breakpoint sidebar lists the project's viewports with full dimensions",
        shell["names"]
        == ["Current", "320", "375", "768", "1024", "1280", "1440", "1920", "2560"]
        and shell["sizes"]
        == [
            "",
            "320 × 568",
            "375 × 667",
            "768 × 1024",
            "1024 × 760",
            "1280 × 800",
            "1440 × 900",
            "1920 × 1080",
            "2560 × 1440",
        ]
        and not shell["forbiddenNames"],
        json.dumps(shell),
    )
    check(
        "Measurement, inspection, annotation, and selection groups are present",
        shell["segments"] == ["Clean Spec", "8pt Grid"]
        and shell["inspection"] == ["Typography", "Color"]
        and shell["annotations"]
        == ["Show measurement lines", "Show 8pt grid overlay"]
        and shell["selection"] == "Nothing selected."
        and shell["hint"] == "Shows actual rounded values."
        and shell["inspectorEmpty"]
        == [
            "Hover or click a component in the preview to inspect it.",
            "Click again to clear the selection.",
        ],
        json.dumps(shell),
    )
    layout = evaluate(
        """(() => {
          const r = s => document.querySelector(s).getBoundingClientRect();
          const header = r('.redline__header');
          const left = r('.redline__sidebar--left');
          const right = r('.redline__sidebar--right');
          const canvas = r('.redline__canvas');
          return {
            headerFullWidth: Math.round(header.width) === Math.round(innerWidth),
            canvasBelowHeader: Math.round(canvas.top) === Math.round(header.bottom),
            canvasAfterLeft: canvas.left >= left.right - 0.5,
            canvasBeforeRight: canvas.right <= right.left + 0.5,
            canvasIsLargest: canvas.width > left.width + right.width,
            leftFirst: left.left < canvas.left && canvas.left < right.left,
            panelsBelowHeader: left.top >= header.bottom - 0.5
              && right.top >= header.bottom - 0.5
          };
        })()"""
    )
    check(
        "Workspace is a three-column layout with the preview canvas in the center",
        all(layout.values()),
        json.dumps(layout),
    )

    inspect = evaluate(
        """(() => {
          const api = window.RedlineMode.inspect('.gnav');
          const target = document.querySelector('.gnav');
          const rect = target.getBoundingClientRect();
          return {api, live:[Math.round(rect.width),Math.round(rect.height)]};
        })()"""
    )
    check(
        "Measurements come from live DOM geometry",
        inspect["api"]["width"] == inspect["live"][0]
        and inspect["api"]["height"] == inspect["live"][1],
        json.dumps(inspect),
    )

    evaluate(
        """(() => {
          const target = document.querySelector('.create-md__workspace');
          target.dispatchEvent(new PointerEvent('pointermove', {bubbles:true}));
          target.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true}));
        })()"""
    )
    time.sleep(0.2)
    annotation = evaluate(
        """(() => {
          const labels = [...document.querySelectorAll('.redline__label')];
          const boxes = labels.map(label => label.getBoundingClientRect());
          const chrome = [...document.querySelectorAll(
            '.redline__header, .redline__sidebar'
          )].map(node => node.getBoundingClientRect());
          const selected = document.querySelector('.create-md__workspace').getBoundingClientRect();
          const overlaps = (a, b) => !(
            a.right <= b.left || a.left >= b.right || a.bottom <= b.top || a.top >= b.bottom
          );
          return {
            labels: labels.map(n => n.textContent),
            boundary: document.querySelectorAll('.redline__boundary').length,
            dims: document.querySelectorAll('.redline__dim').length,
            selfMeasured: labels.some(n => /Redline controls/.test(n.textContent)),
            fontSizes: [...new Set(labels.map(n => getComputedStyle(n).fontSize))],
            redStroke: getComputedStyle(document.querySelector('.redline__dimension')).stroke,
            labelOverlap: boxes.some((box, index) =>
              boxes.slice(index + 1).some(other => overlaps(box, other))
            ),
            chromeOverlap: boxes.some(box => chrome.some(area => overlaps(box, area))),
            selectedOverlap: boxes.some(box => overlaps(box, selected)),
            selection: document.querySelector('[data-redline-selection]').textContent,
            inspectorGroups: [...document.querySelectorAll('.redline__inspect-title')]
              .map(node => node.textContent)
          };
        })()"""
    )
    check(
        "Hover and lock produce crisp integer annotations without self-measurement",
        annotation["boundary"] >= 1
        and annotation["dims"] == 4
        and annotation["labels"]
        and not any("." in label and any(char.isdigit() for char in label) for label in annotation["labels"])
        and not annotation["selfMeasured"],
        json.dumps(annotation),
    )
    check(
        "Red annotations use 14px collision-safe labels clear of the selection and shell chrome",
        annotation["fontSizes"] == ["14px"]
        and annotation["redStroke"] == "rgb(255, 59, 59)"
        and not annotation["labelOverlap"]
        and not annotation["chromeOverlap"]
        and not annotation["selectedOverlap"],
        json.dumps(annotation),
    )
    check(
        "Selection summary and inspector populate for the locked element",
        "create-md__workspace" in annotation["selection"]
        and annotation["selection"].startswith("section")
        and annotation["inspectorGroups"]
        == ["Component", "Dimensions", "Spacing", "Layout"],
        json.dumps(annotation),
    )
    inspector_rows = evaluate(
        """(() => {
          const rows = [...document.querySelectorAll('.redline__inspect-row')].map(row => [
            row.querySelector('.redline__inspect-label').textContent,
            row.querySelector('.redline__inspect-value').textContent
          ]);
          const target = document.querySelector('.create-md__workspace');
          const rect = target.getBoundingClientRect();
          const value = name => (rows.find(row => row[0] === name) || [])[1];
          return {
            labels: rows.map(row => row[0]),
            width: value('Width'),
            height: value('Height'),
            mapping: value('Mapping'),
            childCount: value('Child count'),
            liveWidth: Math.round(rect.width) + 'px',
            liveHeight: Math.round(rect.height) + 'px',
            liveChildren: String(target.children.length),
            heading: document.querySelector('.redline__inspect-heading').textContent
          };
        })()"""
    )
    required_inspector_rows = [
        "Element",
        "Class",
        "Mapping",
        "Width",
        "Height",
        "X",
        "Y",
        "Padding",
        "Margin",
        "Display",
        "Position",
        "Parent",
        "Child count",
    ]
    check(
        "Inspector reports identity, mapping, logical dimensions, spacing, and layout",
        # Radius, Gap, and Border rows are conditional, so the required rows
        # are asserted as an ordered subset.
        [row for row in inspector_rows["labels"] if row in required_inspector_rows]
        == required_inspector_rows
        and inspector_rows["width"] == inspector_rows["liveWidth"]
        and inspector_rows["height"] == inspector_rows["liveHeight"]
        and inspector_rows["childCount"] == inspector_rows["liveChildren"]
        and "Unmapped" in inspector_rows["mapping"]
        and "create-md__workspace" in inspector_rows["heading"],
        json.dumps(inspector_rows),
    )
    screenshot("redline-selected")
    evaluate(
        """document.body.dispatchEvent(
          new MouseEvent('click', {bubbles:true, cancelable:true})
        )"""
    )
    time.sleep(0.1)
    check(
        "Clicking preview empty space clears the locked selection",
        not evaluate("window.RedlineMode.debugState().hasLockedSelection"),
    )

    dynamic = evaluate(
        """(async () => {
          const target = document.querySelector('.create-md__workspace');
          const before = window.RedlineMode.inspect('.create-md__workspace');
          const renders = window.RedlineMode.debugState().renderCount;
          target.style.paddingLeft = '37px';
          target.style.width = '700px';
          await new Promise(resolve => setTimeout(resolve, 120));
          const after = window.RedlineMode.inspect('.create-md__workspace');
          target.style.paddingLeft = '';
          target.style.width = '';
          return {before, after, renders, next:window.RedlineMode.debugState().renderCount};
        })()"""
    )
    check(
        "Mutation and resize observers update changed geometry without refresh",
        dynamic["after"]["width"] == 700
        and dynamic["after"]["padding"][3] == 37
        and dynamic["next"] > dynamic["renders"],
        json.dumps(dynamic),
    )
    live_interaction = evaluate(
        """(async () => {
          const doc = document;
          const before = window.RedlineMode.debugState().renderCount;
          doc.querySelector('[data-v2-tab="premiums"]').click();
          await new Promise(resolve => setTimeout(resolve, 100));
          const premiumsOpen = !doc.querySelector('[data-v2-panel="premiums"]').hidden;
          doc.querySelector('[data-v2-tab="lines"]').click();
          return {
            premiumsOpen,
            renders:window.RedlineMode.debugState().renderCount - before
          };
        })()"""
    )
    check(
        "Inspection permits real tab interaction and automatically remeasures",
        live_interaction["premiumsOpen"] and live_interaction["renders"] > 0,
        json.dumps(live_interaction),
    )
    dropdown_scroll = evaluate(
        """(async () => {
          const doc = document;
          const trigger = doc.querySelector('[data-v2-form="card"] .ads-dd__trigger');
          const scroller = doc.querySelector('.create-md__table-scroll');
          const before = window.RedlineMode.debugState().renderCount;
          trigger.click();
          await new Promise(resolve => setTimeout(resolve, 80));
          const opened = trigger.getAttribute('aria-expanded') === 'true';
          trigger.click();
          scroller.scrollLeft = 20;
          scroller.dispatchEvent(new Event('scroll', {bubbles:false}));
          await new Promise(resolve => setTimeout(resolve, 80));
          return {
            opened,
            renders:window.RedlineMode.debugState().renderCount - before
          };
        })()"""
    )
    check(
        "Dropdown and nested scrolling remain interactive and remeasure automatically",
        dropdown_scroll["opened"] and dropdown_scroll["renders"] >= 2,
        json.dumps(dropdown_scroll),
    )
    recommendation = evaluate(
        """(async () => {
          const target = document.querySelector('[data-v2-action="add-line"]');
          target.style.width = '37.4px';
          target.dispatchEvent(new PointerEvent('pointermove', {bubbles:true}));
          target.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true}));
          await new Promise(resolve => setTimeout(resolve, 120));
          const cleanLabels = [...document.querySelectorAll('.redline__label')]
            .map(label => label.textContent);
          const cleanSelection = document.querySelector('[data-redline-selection]').textContent;
          document.querySelector('[data-redline-action="mode:grid"]').click();
          await new Promise(resolve => setTimeout(resolve, 120));
          const gridLabels = [...document.querySelectorAll('.redline__label')]
            .map(label => label.textContent);
          const gridSelection = document.querySelector('[data-redline-selection]').textContent;
          document.querySelector('[data-redline-action="toggle:typography"]').click();
          await new Promise(resolve => setTimeout(resolve, 120));
          const typographyRows = [...document.querySelectorAll('.redline__inspect-row')]
            .map(row => [
              row.querySelector('.redline__inspect-label').textContent,
              row.querySelector('.redline__inspect-value').textContent
            ]);
          // Captured while Typography is still active, before reverting.
          const typographyGroups = [...document.querySelectorAll('.redline__inspect-title')]
            .map(node => node.textContent);
          const gridHint = document.querySelector('[data-redline-mode-hint]').textContent;
          document.querySelector('[data-redline-action="toggle:typography"]').click();
          document.querySelector('[data-redline-action="mode:clean"]').click();
          target.style.width = '';
          return {
            cleanLabels, gridLabels, cleanSelection, gridSelection,
            typographyGroups, typographyRows, gridHint
          };
        })()"""
    )
    typography_values = dict(recommendation["typographyRows"])
    check(
        "Clean Spec reports actual rounded values and 8pt Grid reports the nearest 8pt value",
        any(label == "37" for label in recommendation["cleanLabels"])
        and any("40 (8pt)" in label for label in recommendation["gridLabels"])
        and not any("(8pt)" in label for label in recommendation["cleanLabels"]),
        json.dumps(recommendation),
    )
    check(
        "Switching measurement mode preserves the current selection",
        recommendation["cleanSelection"] == recommendation["gridSelection"]
        and recommendation["cleanSelection"] != "Nothing selected.",
        json.dumps(recommendation),
    )
    check(
        "8pt Grid hint explains the interpretation",
        recommendation["gridHint"] == "Shows the nearest 8pt grid value.",
        json.dumps(recommendation["gridHint"]),
    )
    check(
        "Typography inspection renders computed type detail in the inspector",
        "Typography" in recommendation["typographyGroups"]
        and typography_values.get("Font family") == "Open Sans"
        and typography_values.get("Font size", "").endswith("px")
        and "Font weight" in typography_values
        and "Line height" in typography_values
        and "Letter spacing" in typography_values
        and "Text color" in typography_values,
        json.dumps(recommendation["typographyRows"]),
    )

    modes = evaluate(
        """(async () => {
          const q = s => document.querySelector(s);
          const press = s => q(s).getAttribute('aria-pressed');
          const toggleCheck = name => {
            const box = q('[data-redline-action="annotation:' + name + '"]');
            box.click();
            box.dispatchEvent(new Event('change', {bubbles:true}));
          };
          const result = {};
          q('[data-redline-action="mode:grid"]').click();
          result.gridSelected = [press('[data-redline-action="mode:grid"]'),
            press('[data-redline-action="mode:clean"]')];
          q('[data-redline-action="mode:clean"]').click();
          result.cleanSelected = [press('[data-redline-action="mode:grid"]'),
            press('[data-redline-action="mode:clean"]')];

          q('[data-redline-action="toggle:typography"]').click();
          q('[data-redline-action="toggle:color"]').click();
          await new Promise(r => setTimeout(r, 80));
          result.colorExclusive = [press('[data-redline-action="toggle:color"]'),
            press('[data-redline-action="toggle:typography"]')];
          q('[data-redline-action="toggle:typography"]').click();
          await new Promise(r => setTimeout(r, 80));
          result.typographyExclusive = [press('[data-redline-action="toggle:color"]'),
            press('[data-redline-action="toggle:typography"]')];
          q('[data-redline-action="toggle:typography"]').click();

          // Annotations stay independent of the measurement mode.
          toggleCheck('grid-overlay');
          await new Promise(r => setTimeout(r, 80));
          const overlayOn = window.RedlineMode.debugState();
          result.overlayIndependent = [overlayOn.showGridOverlay,
            overlayOn.measurementMode, !q('[data-redline-grid]').hidden];
          toggleCheck('lines');
          await new Promise(r => setTimeout(r, 80));
          const linesOff = window.RedlineMode.debugState();
          result.linesIndependent = [linesOff.showLines, linesOff.showGridOverlay,
            document.querySelectorAll('.redline__label').length];
          toggleCheck('lines');
          toggleCheck('grid-overlay');
          await new Promise(r => setTimeout(r, 80));
          const restored = window.RedlineMode.debugState();
          result.restored = [restored.showLines, restored.showGridOverlay,
            q('[data-redline-grid]').hidden];
          return result;
        })()"""
    )
    check(
        "Measurement modes are mutually exclusive and inspection modes stay separate",
        modes["gridSelected"] == ["true", "false"]
        and modes["cleanSelected"] == ["false", "true"]
        and modes["colorExclusive"] == ["true", "false"]
        and modes["typographyExclusive"] == ["false", "true"],
        json.dumps(modes),
    )
    check(
        "Annotation toggles are independent and reversible",
        modes["overlayIndependent"] == [True, "clean", True]
        and modes["linesIndependent"] == [False, True, 0]
        and modes["restored"] == [True, False, True],
        json.dumps(modes),
    )

    for preset, width, height in (
        ("1024", 1024, 760),
        ("1280", 1280, 800),
        ("1440", 1440, 900),
        ("1920", 1920, 1080),
        ("2560", 2560, 1440),
    ):
        evaluate(
            f"document.querySelector('[data-redline-action=\"breakpoint:{preset}\"]').click()"
        )
        time.sleep(0.38)
        geometry = evaluate(
            """(() => {
              const frame = document.querySelector('.redline__preview');
              const shell = document.querySelector('.redline__preview-shell');
              const stage = document.querySelector('.redline__stage');
              const rect = frame.getBoundingClientRect();
              const shellRect = shell.getBoundingClientRect();
              const stageRect = stage.getBoundingClientRect();
              const headerRect = document.querySelector('.redline__header').getBoundingClientRect();
              const canvasRect = document.querySelector('.redline__canvas').getBoundingClientRect();
              const state = window.RedlineMode.debugState();
              const expectedScale = Math.min(
                1,
                stage.clientWidth / frame.clientWidth,
                stage.clientHeight / frame.clientHeight
              );
              return {
                displayWidth: rect.width,
                displayHeight: rect.height,
                shellMatches: Math.abs(rect.width - shellRect.width) < 0.02
                  && Math.abs(rect.height - shellRect.height) < 0.02,
                logicalWidth: frame.clientWidth,
                logicalHeight: frame.clientHeight,
                centered: Math.abs(
                  (rect.left + rect.width / 2) - (stageRect.left + stageRect.width / 2)
                ) <= 1,
                verticallyCentered: Math.abs(
                  (rect.top + rect.height / 2) - (stageRect.top + stageRect.height / 2)
                ) <= 1,
                viewport: frame.contentWindow.innerWidth,
                viewportHeight: frame.contentWindow.innerHeight,
                visible: !frame.hidden,
                headerBottom: Math.round(headerRect.bottom),
                frameTop: Math.round(rect.top),
                headerIsolated: rect.top >= headerRect.bottom,
                withinCanvas: rect.left >= canvasRect.left - 0.5
                  && rect.right <= canvasRect.right + 0.5,
                scale: state.previewScale,
                expectedScale,
                viewportInfo: document.querySelector('[data-redline-viewport-info]').textContent,
                presentation: document.querySelector('.redline').dataset.breakpointActive,
                canvasNeutral: getComputedStyle(
                  document.querySelector('.redline__canvas')
                ).backgroundColor,
                active: document.querySelector(
                  '[data-redline-action="breakpoint:' + window.RedlineMode.debugState().breakpoint + '"]'
                ).getAttribute('aria-pressed'),
                frameBoxSizing: getComputedStyle(frame).boxSizing,
                shellBoxSizing: getComputedStyle(shell).boxSizing
              };
            })()"""
        )
        check(
            f"{preset} preset keeps a logical {width}x{height} viewport",
            geometry["logicalWidth"] == width
            and geometry["logicalHeight"] == height
            and geometry["viewport"] == width
            and geometry["viewportHeight"] == height
            and abs(geometry["displayWidth"] - width * geometry["scale"]) < 0.1
            and abs(geometry["displayHeight"] - height * geometry["scale"]) < 0.1
            and abs(geometry["scale"] - geometry["expectedScale"]) < 0.0001
            and geometry["shellMatches"]
            and geometry["centered"]
            and geometry["verticallyCentered"]
            and geometry["visible"]
            and geometry["headerIsolated"]
            and geometry["withinCanvas"]
            and geometry["presentation"] == "true"
            and geometry["canvasNeutral"] == "rgb(220, 220, 223)"
            and geometry["active"] == "true"
            and geometry["frameBoxSizing"] == "border-box"
            and geometry["shellBoxSizing"] == "border-box",
            json.dumps(geometry),
        )
        check(
            f"{preset} header reports the logical viewport and applied scale",
            geometry["viewportInfo"]
            == f"{width} × {height} ({round(geometry['scale'] * 100)}%)",
            json.dumps(geometry),
        )
        screenshot(f"redline-{preset}")

    # Requirement: after a breakpoint change the selection survives, bounds
    # are recalculated, and the inspector refreshes to the new logical size.
    preserved = evaluate(
        """(async () => {
          const click = id => document.querySelector(
            '[data-redline-action="breakpoint:' + id + '"]'
          ).click();
          const inspectorValue = name => {
            const row = [...document.querySelectorAll('.redline__inspect-row')]
              .find(item => item.querySelector('.redline__inspect-label').textContent === name);
            return row ? row.querySelector('.redline__inspect-value').textContent : null;
          };
          const boundaryWidth = () => Number(document.querySelector(
            '.redline__boundary:not(.redline__alignment)'
          )?.getAttribute('width'));
          click('1440');
          await new Promise(r => setTimeout(r, 600));
          const frame = document.querySelector('.redline__preview');
          const target = frame.contentDocument.querySelector('nav.gnav');
          target.dispatchEvent(new frame.contentWindow.PointerEvent('pointermove', {bubbles:true}));
          target.dispatchEvent(new frame.contentWindow.MouseEvent(
            'click', {bubbles:true, cancelable:true}
          ));
          await new Promise(r => setTimeout(r, 300));
          const before = {
            selection: document.querySelector('[data-redline-selection]').textContent,
            width: inspectorValue('Width'),
            boundary: boundaryWidth(),
            labels: [...document.querySelectorAll('.redline__label')].map(l => l.textContent),
            renders: window.RedlineMode.debugState().renderCount
          };
          click('1920');
          await new Promise(r => setTimeout(r, 800));
          const scale = window.RedlineMode.debugState().previewScale;
          const liveRect = target.getBoundingClientRect();
          const after = {
            selection: document.querySelector('[data-redline-selection]').textContent,
            width: inspectorValue('Width'),
            boundary: boundaryWidth(),
            // The overlay must still trace the element's scaled geometry.
            expectedBoundary: liveRect.width * scale,
            labels: [...document.querySelectorAll('.redline__label')].map(l => l.textContent),
            renders: window.RedlineMode.debugState().renderCount,
            locked: window.RedlineMode.debugState().hasLockedSelection,
            route: frame.contentDocument.body.dataset.route,
            reloaded: frame.contentDocument.querySelector('nav.gnav') !== target
          };
          return {before, after};
        })()"""
    )
    check(
        "Breakpoint changes preserve the selection and recalculate measurements",
        preserved["after"]["selection"] == preserved["before"]["selection"]
        and preserved["after"]["locked"]
        and not preserved["after"]["reloaded"]
        and preserved["after"]["route"] == "create"
        and preserved["before"]["width"] == "1440px"
        and preserved["after"]["width"] == "1920px"
        and "1440" in preserved["before"]["labels"]
        and "1920" in preserved["after"]["labels"]
        and abs(
            preserved["after"]["boundary"] - preserved["after"]["expectedBoundary"]
        ) <= 1
        and preserved["after"]["renders"] > preserved["before"]["renders"],
        json.dumps(preserved),
    )
    evaluate(
        """document.body.dispatchEvent(
          new MouseEvent('click', {bubbles:true, cancelable:true})
        )"""
    )

    evaluate(
        "document.querySelector('[data-redline-action=\"breakpoint:1024\"]').click()"
    )
    send(
        "Emulation.setDeviceMetricsOverride",
        {"width": 900, "height": 700, "deviceScaleFactor": 1, "mobile": False},
    )
    time.sleep(0.4)
    compact = evaluate(
        """(() => {
          const frame = document.querySelector('.redline__preview');
          const rect = frame.getBoundingClientRect();
          const stage = document.querySelector('.redline__stage');
          const stageRect = stage.getBoundingClientRect();
          const state = window.RedlineMode.debugState();
          return {
            logical:[frame.contentWindow.innerWidth, frame.contentWindow.innerHeight],
            client:[frame.clientWidth, frame.clientHeight],
            display:[rect.width, rect.height],
            scale:state.previewScale,
            contained:rect.left >= stageRect.left - 0.5 && rect.top >= stageRect.top - 0.5
              && rect.right <= stageRect.right + 0.5 && rect.bottom <= stageRect.bottom + 0.5,
            hostScrollLocked:getComputedStyle(document.documentElement).overflow === 'hidden',
            stageOverflow:getComputedStyle(stage).overflow,
            rootOverflow:getComputedStyle(document.querySelector('.redline')).overflow,
            headerVisible:document.querySelector('.redline__header')
              .getBoundingClientRect().height > 0,
            size:document.querySelector(
              '[data-redline-action="breakpoint:1024"] .redline__breakpoint-size'
            ).textContent
          };
        })()"""
    )
    check(
        "1024 preset remains logically 1024x760 in a smaller host",
        compact["logical"] == [1024, 760]
        and compact["client"] == [1024, 760]
        and compact["scale"] < 1
        and compact["contained"]
        and compact["hostScrollLocked"]
        and compact["stageOverflow"] == "hidden"
        and compact["rootOverflow"] == "hidden"
        and compact["headerVisible"]
        and compact["size"] == "1024 × 760",
        json.dumps(compact),
    )
    evaluate(
        """(() => {
          const state = window.RedlineMode.debugState();
          if (state.typography) {
            document.querySelector('[data-redline-action="toggle:typography"]').click();
          }
          if (state.color) {
            document.querySelector('[data-redline-action="toggle:color"]').click();
          }
          if (state.measurementMode !== 'clean') {
            document.querySelector('[data-redline-action="mode:clean"]').click();
          }
          if (!state.showLines) {
            const box = document.querySelector('[data-redline-action="annotation:lines"]');
            box.click();
            box.dispatchEvent(new Event('change', {bubbles:true}));
          }
          if (state.showGridOverlay) {
            const box = document.querySelector('[data-redline-action="annotation:grid-overlay"]');
            box.click();
            box.dispatchEvent(new Event('change', {bubbles:true}));
          }
          const frame = document.querySelector('.redline__preview');
          const target = frame.contentDocument.querySelector('.gnav');
          target.dispatchEvent(new frame.contentWindow.PointerEvent(
            'pointermove', {bubbles:true}
          ));
        })()"""
    )
    time.sleep(0.15)
    scaled_measurement = evaluate(
        """(() => {
          const frame = document.querySelector('.redline__preview');
          const frameRect = frame.getBoundingClientRect();
          const targetRect = frame.contentDocument.querySelector('.gnav').getBoundingClientRect();
          const scale = window.RedlineMode.debugState().previewScale;
          const boundary = document.querySelector(
            '.redline__boundary:not(.redline__alignment)'
          );
          const labels = [...document.querySelectorAll('.redline__label')]
            .map(item => item.textContent.trim());
          return {
            labels,
            boundaryWidth:Number(boundary?.getAttribute('width')),
            boundaryLeft:Number(boundary?.getAttribute('x')),
            expectedWidth:targetRect.width * scale,
            expectedLeft:frameRect.left + targetRect.left * scale
          };
        })()"""
    )
    check(
        "Scaled annotations stay attached and report logical dimensions",
        "1024" in scaled_measurement["labels"]
        and abs(
            scaled_measurement["boundaryWidth"] - scaled_measurement["expectedWidth"]
        ) <= 1
        and abs(
            scaled_measurement["boundaryLeft"] - scaled_measurement["expectedLeft"]
        ) <= 1,
        json.dumps(scaled_measurement),
    )
    evaluate(
        "document.querySelector('[data-redline-action=\"breakpoint:1280\"]').click()"
    )
    time.sleep(0.4)
    compact_1280 = evaluate(
        """(() => {
          const frame = document.querySelector('.redline__preview');
          const rect = frame.getBoundingClientRect();
          const stage = document.querySelector('.redline__stage');
          const stageRect = stage.getBoundingClientRect();
          const state = window.RedlineMode.debugState();
          return {
            logical:[frame.contentWindow.innerWidth, frame.contentWindow.innerHeight],
            client:[frame.clientWidth, frame.clientHeight],
            display:[rect.width, rect.height],
            scale:state.previewScale,
            contained:rect.left >= stageRect.left - 0.5 && rect.top >= stageRect.top - 0.5
              && rect.right <= stageRect.right + 0.5 && rect.bottom <= stageRect.bottom + 0.5,
            hostScrollLocked:getComputedStyle(document.documentElement).overflow === 'hidden',
            stageOverflow:getComputedStyle(stage).overflow,
            rootOverflow:getComputedStyle(document.querySelector('.redline')).overflow,
            size:document.querySelector(
              '[data-redline-action="breakpoint:1280"] .redline__breakpoint-size'
            ).textContent
          };
        })()"""
    )
    check(
        "1280 preset remains logically 1280x800 in a smaller host",
        compact_1280["logical"] == [1280, 800]
        and compact_1280["client"] == [1280, 800]
        and compact_1280["scale"] < 1
        and compact_1280["contained"]
        and compact_1280["hostScrollLocked"]
        and compact_1280["stageOverflow"] == "hidden"
        and compact_1280["rootOverflow"] == "hidden"
        and compact_1280["size"] == "1280 × 800",
        json.dumps(compact_1280),
    )
    drawers = evaluate(
        """(async () => {
          const root = document.querySelector('.redline');
          const left = document.querySelector('.redline__sidebar--left');
          const right = document.querySelector('.redline__sidebar--right');
          const canvas = document.querySelector('.redline__canvas');
          const toggles = [...document.querySelectorAll('.redline__panel-toggle')];
          const logicalBefore = document.querySelector('.redline__preview').clientWidth;
          const collapsed = [left.getBoundingClientRect().right <= 1,
            right.getBoundingClientRect().left >= innerWidth - 1];
          document.querySelector('[data-redline-action="panel:left"]').click();
          document.querySelector('[data-redline-action="panel:right"]').click();
          await new Promise(r => setTimeout(r, 320));
          const opened = [left.getBoundingClientRect().right > 1,
            right.getBoundingClientRect().left < innerWidth - 1];
          const expanded = toggles.map(t => t.getAttribute('aria-expanded'));
          document.querySelector('[data-redline-action="panel:left"]').click();
          document.querySelector('[data-redline-action="panel:right"]').click();
          await new Promise(r => setTimeout(r, 320));
          return {
            togglesVisible: toggles.every(t => t.getBoundingClientRect().width > 0),
            collapsed, opened, expanded,
            canvasKeepsWidth: Math.round(canvas.getBoundingClientRect().width) === 900,
            headerVisible: document.querySelector('.redline__header')
              .getBoundingClientRect().height > 0,
            logicalUnchanged: document.querySelector('.redline__preview').clientWidth
              === logicalBefore,
            reclosed: [left.getBoundingClientRect().right <= 1,
              right.getBoundingClientRect().left >= innerWidth - 1]
          };
        })()"""
    )
    check(
        "Narrow hosts collapse the panels to reopenable drawers without changing the preview",
        drawers["togglesVisible"]
        and drawers["collapsed"] == [True, True]
        and drawers["opened"] == [True, True]
        and drawers["expanded"] == ["true", "true"]
        and drawers["reclosed"] == [True, True]
        and drawers["canvasKeepsWidth"]
        and drawers["headerVisible"]
        and drawers["logicalUnchanged"],
        json.dumps(drawers),
    )
    screenshot("redline-narrow-drawers")
    send("Emulation.clearDeviceMetricsOverride")
    time.sleep(0.2)
    evaluate(
        "document.querySelector('[data-redline-action=\"breakpoint:2560\"]').click()"
    )
    time.sleep(0.35)

    send(
        "Emulation.setEmulatedMedia",
        {"features": [{"name": "prefers-reduced-motion", "value": "reduce"}]},
    )
    reduced = evaluate(
        "getComputedStyle(document.querySelector('.redline__preview-shell')).transitionDuration"
    )
    check("Reduced motion disables breakpoint transition", reduced == "0s", reduced)
    send("Emulation.setEmulatedMedia", {"features": []})

    evaluate(
        "document.querySelector('[data-redline-action=\"breakpoint:2560\"]').click()"
    )
    time.sleep(0.1)
    cleared = evaluate(
        """(() => ({
          breakpoint:window.RedlineMode.debugState().breakpoint,
          hidden:document.querySelector('.redline__preview').hidden,
          selected:document.querySelectorAll(
            '[data-redline-action^="breakpoint:"][aria-pressed="true"]'
          ).length,
          currentPressed:document.querySelector(
            '[data-redline-action="breakpoint:current"]'
          ).getAttribute('aria-pressed'),
          presentation:document.querySelector('.redline').dataset.breakpointActive,
          canvas:getComputedStyle(document.querySelector('.redline__canvas')).backgroundColor
        }))()"""
    )
    check(
        "Clicking the active breakpoint restores Current inspection",
        cleared
        == {
            "breakpoint": "",
            "hidden": True,
            "selected": 1,
            "currentPressed": "true",
            "presentation": "false",
            "canvas": "rgba(0, 0, 0, 0)",
        },
        json.dumps(cleared),
    )
    screenshot("redline-current")

    focus_point = evaluate(
        """(() => {
          const rect = document.querySelector(
            '[data-redline-action="mode:clean"]'
          ).getBoundingClientRect();
          return {x:rect.left + rect.width / 2, y:rect.top + rect.height / 2};
        })()"""
    )
    send(
        "Input.dispatchMouseEvent",
        {"type": "mousePressed", "x": focus_point["x"], "y": focus_point["y"], "button": "left", "clickCount": 1},
    )
    send(
        "Input.dispatchMouseEvent",
        {"type": "mouseReleased", "x": focus_point["x"], "y": focus_point["y"], "button": "left", "clickCount": 1},
    )
    accessibility = evaluate(
        """(() => {
          const buttons = [...document.querySelectorAll(
            '.redline__breakpoint, .redline__segment, .redline__stack-button,'
            + ' .redline__close, .redline__panel-toggle'
          )];
          const stateful = [...document.querySelectorAll(
            '.redline__breakpoint, .redline__segment, .redline__stack-button'
          )];
          const checkboxes = [...document.querySelectorAll('.redline__checkbox-input')];
          const focused = document.querySelector('[data-redline-action="mode:clean"]');
          const style = getComputedStyle(focused);
          return {
            names:buttons.every(button =>
              button.getAttribute('aria-label') || button.textContent.trim()
            ),
            pressed:stateful.every(button => button.hasAttribute('aria-pressed')),
            labelledCheckboxes:checkboxes.every(box =>
              box.closest('label')?.textContent.trim()
            ),
            groups:[...document.querySelectorAll('.redline__sidebar--left [role="group"]')]
              .every(group => group.getAttribute('aria-label')),
            inspectorRegion:document.querySelector('.redline__sidebar--right')
              .getAttribute('aria-label'),
            focus:[style.outlineStyle, style.outlineWidth],
            decorative:document.querySelector('.redline__svg').getAttribute('aria-hidden'),
            labels:document.querySelector('[data-redline-labels]').getAttribute('aria-hidden')
          };
        })()"""
    )
    check(
        "Shell controls and decorative annotations expose accessible semantics",
        accessibility["names"]
        and accessibility["pressed"]
        and accessibility["labelledCheckboxes"]
        and accessibility["groups"]
        and accessibility["inspectorRegion"] == "Component inspector"
        and accessibility["focus"] == ["solid", "2px"]
        and accessibility["decorative"] == "true"
        and accessibility["labels"] == "true",
        json.dumps(accessibility),
    )

    route_update = evaluate(
        """(async () => {
          document.querySelector('[data-action="go-list"]').click();
          await new Promise(resolve => setTimeout(resolve, 350));
          const frame = document.querySelector('.redline__preview');
          const list = document.body.dataset.route === 'list' && frame.hidden;
          /* Create rate card now opens a dialog rather than routing, so
             the SPA navigation this checks for comes from opening a rate
             card, which is what takes the app to the create route. */
          document.querySelector('.name__link, .cell--name a').click();
          await new Promise(resolve => setTimeout(resolve, 350));
          return {
            list,
            create:document.body.dataset.route === 'create' && frame.hidden,
            overlays:document.querySelectorAll('.redline').length
          };
        })()"""
    )
    check(
        "Active Redline follows parent SPA navigation without stacking overlays",
        route_update == {"list": True, "create": True, "overlays": 1},
        json.dumps(route_update),
    )

    evaluate("window.RedlineMode.disable()")
    editable_guard = evaluate(
        """(() => {
          const host = document.createElement('div');
          host.innerHTML = [
            '<input>',
            '<textarea></textarea>',
            '<select><option>One</option></select>',
            '<div contenteditable="true" tabindex="0"></div>',
            '<div role="textbox" tabindex="0"></div>',
            '<div class="CodeMirror" tabindex="0"></div>'
          ].join('');
          document.body.appendChild(host);
          const results = [...host.children].map(control => {
            control.focus();
            const event = new KeyboardEvent('keydown', {
              key:'d', metaKey:true, bubbles:true, cancelable:true
            });
            control.dispatchEvent(event);
            return !window.RedlineMode.isActive() && !event.defaultPrevented;
          });
          host.remove();
          return results;
        })()"""
    )
    check(
        "Shortcut is ignored in every editable and code-editor context",
        editable_guard == [True, True, True, True, True, True],
        json.dumps(editable_guard),
    )
    shortcut = evaluate(
        """(() => {
          document.body.focus();
          const event = new KeyboardEvent('keydown', {
            key:'d', metaKey:true, bubbles:true, cancelable:true
          });
          document.dispatchEvent(event);
          return {active:window.RedlineMode.isActive(), prevented:event.defaultPrevented};
        })()"""
    )
    check(
        "Command or Control D activates and prevents bookmark behavior",
        shortcut == {"active": True, "prevented": True},
        json.dumps(shortcut),
    )
    evaluate(
        """document.dispatchEvent(new KeyboardEvent('keydown', {
          key:'d', ctrlKey:true, bubbles:true, cancelable:true
        }))"""
    )
    check("Repeated shortcut exits Redline", not evaluate("window.RedlineMode.isActive()"))

    evaluate("window.RedlineMode.enable('qa')")
    wait_for("document.querySelector('.redline__preview')?.contentDocument?.readyState === 'complete'")
    evaluate(
        "document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true}))"
    )
    check("Escape exits cleanly", not evaluate("window.RedlineMode.isActive()"))

    evaluate("window.RedlineMode.enable('qa')")
    evaluate("document.querySelector('[data-redline-action=\"close\"]').click()")
    check("Close button exits cleanly", not evaluate("window.RedlineMode.isActive()"))

    evaluate(
        """(() => {
          document.querySelector('[data-action="toggle-profile"]').click();
          document.querySelector('[data-action="toggle-redline"]').click();
        })()"""
    )
    wait_for("document.querySelector('.redline__preview')?.contentDocument?.readyState === 'complete'")
    active_menu_exit = evaluate(
        """(() => {
          const doc = document;
          doc.querySelector('[data-action="toggle-profile"]').click();
          doc.querySelector('[data-action="toggle-redline"]').click();
          return true;
        })()"""
    )
    time.sleep(0.1)
    exit_state = evaluate(
        """({
          active:window.RedlineMode.isActive(),
          focus:document.activeElement?.getAttribute('data-action') || document.activeElement?.tagName
        })"""
    )
    check(
        "Clicking the active Redline menu item exits and returns focus",
        active_menu_exit
        and exit_state == {"active": False, "focus": "toggle-profile"},
        json.dumps(exit_state),
    )

    stress = evaluate(
        """(async () => {
          for (let i = 0; i < 20; i += 1) {
            window.RedlineMode.enable('stress');
            await new Promise(resolve => setTimeout(resolve, 10));
            window.RedlineMode.disable();
          }
          window.RedlineMode.enable('stress-final');
          await new Promise(resolve => setTimeout(resolve, 80));
          const result = {
            overlays:document.querySelectorAll('.redline').length,
            headers:document.querySelectorAll('.redline__header').length,
            sidebars:document.querySelectorAll('.redline__sidebar').length
          };
          window.RedlineMode.disable();
          result.remaining = document.querySelectorAll('.redline').length;
          return result;
        })()"""
    )
    check(
        "Twenty activation cycles leave no duplicate or stale overlays",
        stress == {"overlays": 1, "headers": 1, "sidebars": 2, "remaining": 0},
        json.dumps(stress),
    )
    check("Browser console has no errors or warnings", not console_messages, json.dumps(console_messages))

finally:
    print(json.dumps({"passes": passes, "failures": len(failures)}, indent=2))
    ws.close()
    chrome.terminate()
    server.shutdown()

if failures:
    raise SystemExit(1)
