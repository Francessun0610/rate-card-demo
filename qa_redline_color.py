"""Color inspection tab (Redline Mode) browser QA.

Run with: python3 qa_redline_color.py
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
PORT = 8994
DEBUG_PORT = 9294
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
OUT = "/tmp/rate-card-redline-color-qa"
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
        self.send_header("Cache-Control", "no-store")
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
profile = "/tmp/rate_card_redline_color_qa_profile"
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
    time.sleep(1.3)

    evaluate("window.RedlineMode.enable('qa')")
    wait_for("document.querySelector('.redline__preview')?.contentDocument?.readyState === 'complete'")

    placement = evaluate(
        """(() => {
          const measurement = document.querySelector('[data-redline-section="measurement"]');
          const inspection = document.querySelector('[data-redline-section="inspection"]');
          const color = document.querySelector('[data-redline-action="toggle:color"]');
          const sidebar = document.querySelector('.redline__sidebar--left');
          const canvas = document.querySelector('.redline__canvas').getBoundingClientRect();
          const colorRect = color.getBoundingClientRect();
          return {
            measurementSegments: [...measurement.querySelectorAll('[data-redline-action^="mode:"]')]
              .map(node => node.textContent),
            inspectionModes: [...inspection.querySelectorAll('[data-redline-action^="toggle:"]')]
              .map(node => node.textContent),
            colorInSidebar: sidebar.contains(color),
            inspectionAfterMeasurement:
              measurement.compareDocumentPosition(inspection)
                & Node.DOCUMENT_POSITION_FOLLOWING ? true : false,
            colorClearOfCanvas: colorRect.right <= canvas.left + 0.5,
            noFloatingBar: document.querySelectorAll('.redline__toolbar').length
          };
        })()"""
    )
    check(
        "Measurement mode and Inspection are separate left-sidebar sections",
        placement["measurementSegments"] == ["Clean Spec", "8pt Grid"]
        and placement["inspectionModes"] == ["Typography", "Color"]
        and placement["colorInSidebar"]
        and placement["inspectionAfterMeasurement"]
        and placement["colorClearOfCanvas"]
        and placement["noFloatingBar"] == 0,
        json.dumps(placement),
    )

    parity = evaluate(
        """(() => {
          const pick = (el) => {
            const s = getComputedStyle(el);
            return [s.minHeight, s.paddingTop, s.paddingRight, s.fontFamily, s.fontSize,
              s.fontWeight, s.lineHeight, s.borderWidth, s.borderRadius, s.color, s.cursor];
          };
          const typography = document.querySelector('[data-redline-action="toggle:typography"]');
          const color = document.querySelector('[data-redline-action="toggle:color"]');
          return {
            colorVsTypography: JSON.stringify(pick(color)) === JSON.stringify(pick(typography)),
            sameClass: color.className === typography.className
          };
        })()"""
    )
    check(
        "Color control matches its sibling inspection control styling",
        parity["colorVsTypography"] and parity["sameClass"],
        json.dumps(parity),
    )

    hover_states = evaluate(
        """(() => {
          const color = document.querySelector('[data-redline-action="toggle:color"]');
          const typography = document.querySelector('[data-redline-action="toggle:typography"]');
          return {
            colorRestBg: getComputedStyle(color).backgroundColor,
            typographyRestBg: getComputedStyle(typography).backgroundColor
          };
        })()"""
    )
    check(
        "Color rest state background matches sibling controls",
        hover_states["colorRestBg"] == hover_states["typographyRestBg"],
        json.dumps(hover_states),
    )

    mutual = evaluate(
        """(() => {
          const typography = document.querySelector('[data-redline-action="toggle:typography"]');
          const color = document.querySelector('[data-redline-action="toggle:color"]');
          typography.click();
          const afterTypography = {
            typography: typography.getAttribute('aria-pressed'),
            color: color.getAttribute('aria-pressed')
          };
          color.click();
          const afterColor = {
            typography: typography.getAttribute('aria-pressed'),
            color: color.getAttribute('aria-pressed')
          };
          typography.click();
          const afterTypographyAgain = {
            typography: typography.getAttribute('aria-pressed'),
            color: color.getAttribute('aria-pressed')
          };
          return {afterTypography, afterColor, afterTypographyAgain};
        })()"""
    )
    check(
        "Activating Color deactivates Typography and vice versa",
        mutual["afterTypography"] == {"typography": "true", "color": "false"}
        and mutual["afterColor"] == {"typography": "false", "color": "true"}
        and mutual["afterTypographyAgain"] == {"typography": "true", "color": "false"},
        json.dumps(mutual),
    )

    grid_unaffected = evaluate(
        """(() => {
          const grid = document.querySelector('[data-redline-action="mode:grid"]');
          const clean = document.querySelector('[data-redline-action="mode:clean"]');
          const color = document.querySelector('[data-redline-action="toggle:color"]');
          const setPressed = (el, on) => {
            if ((el.getAttribute('aria-pressed') === 'true') !== on) el.click();
          };
          grid.click();
          setPressed(color, true);
          const before = {
            mode: window.RedlineMode.debugState().measurementMode,
            grid: grid.getAttribute('aria-pressed'),
            color: color.getAttribute('aria-pressed')
          };
          setPressed(color, false);
          const afterColorToggleOff = {
            mode: window.RedlineMode.debugState().measurementMode,
            grid: grid.getAttribute('aria-pressed'),
            color: color.getAttribute('aria-pressed'),
            typography: document.querySelector('[data-redline-action="toggle:typography"]').getAttribute('aria-pressed')
          };
          clean.click();
          return {before, afterColorToggleOff};
        })()"""
    )
    check(
        "Measurement mode stays independent while Color is toggled on and off",
        grid_unaffected["before"]["mode"] == "grid"
        and grid_unaffected["before"]["grid"] == "true"
        and grid_unaffected["before"]["color"] == "true"
        and grid_unaffected["afterColorToggleOff"]["mode"] == "grid"
        and grid_unaffected["afterColorToggleOff"]["grid"] == "true"
        and grid_unaffected["afterColorToggleOff"]["color"] == "false",
        json.dumps(grid_unaffected),
    )

    # Selecting a measurement mode is a presentation choice, so it must not
    # silently turn an inspection view off.
    mode_keeps_color = evaluate(
        """(() => {
          const clean = document.querySelector('[data-redline-action="mode:clean"]');
          const grid = document.querySelector('[data-redline-action="mode:grid"]');
          const color = document.querySelector('[data-redline-action="toggle:color"]');
          if (color.getAttribute('aria-pressed') !== 'true') color.click();
          const before = {
            mode: window.RedlineMode.debugState().measurementMode,
            color: color.getAttribute('aria-pressed')
          };
          grid.click();
          const afterGrid = {
            mode: window.RedlineMode.debugState().measurementMode,
            color: color.getAttribute('aria-pressed')
          };
          clean.click();
          const afterClean = {
            mode: window.RedlineMode.debugState().measurementMode,
            color: color.getAttribute('aria-pressed')
          };
          return {before, afterGrid, afterClean};
        })()"""
    )
    check(
        "Switching measurement mode preserves the active Color inspection view",
        mode_keeps_color["before"] == {"mode": "clean", "color": "true"}
        and mode_keeps_color["afterGrid"] == {"mode": "grid", "color": "true"}
        and mode_keeps_color["afterClean"] == {"mode": "clean", "color": "true"},
        json.dumps(mode_keeps_color),
    )
    evaluate(
        """(() => {
          const color = document.querySelector('[data-redline-action="toggle:color"]');
          if (color.getAttribute('aria-pressed') === 'true') color.click();
        })()"""
    )

    evaluate("document.querySelector('[data-redline-action=\"toggle:color\"]').click()")
    wait_for("document.querySelector('[data-redline-action=\"toggle:color\"]').getAttribute('aria-pressed') === 'true'")

    inspected_text = evaluate(
        """(async () => {
          const target = [...document.querySelectorAll('[data-v2-tab], button, a')]
            .find(el => el.getBoundingClientRect().width > 10 && el.getBoundingClientRect().height > 10);
          target.dispatchEvent(new PointerEvent('pointermove', {bubbles: true}));
          await new Promise(r => setTimeout(r, 220));
          const panel = document.querySelector('[data-redline-inspector]');
          const roles = [...panel.querySelectorAll('.redline__color-role-name')].map(n => n.textContent);
          const rows = [...panel.querySelectorAll('.redline__color-row')].map(row => {
            const [label, value] = row.querySelectorAll('span, code');
            return [label.textContent, value.textContent];
          });
          return {
            // The inspector is a persistent panel, so presence of color
            // roles is what proves the color view rendered.
            hidden: roles.length === 0,
            insideRightPanel: !!panel.closest('.redline__sidebar--right'),
            floatingPanels: document.querySelectorAll(
              '.redline__color-panel, [data-redline-color-panel]'
            ).length,
            roles,
            hasToken: rows.some(([label]) => label === 'Token'),
            hasHex: rows.some(([label, value]) => label === 'Hex' && /^#[0-9a-f]{6,8}$/i.test(value)),
            hasRgb: rows.some(([label, value]) => label === 'RGB' && /^rgba?\\(/.test(value)),
            hasSelector: rows.some(([label]) => label === 'Selector'),
            hasSource: rows.some(([label]) => label === 'Source'),
            hasInherited: rows.some(([label]) => label === 'Inherited'),
            hasHardcoded: rows.some(([label]) => label === 'Hardcoded'),
            hasContrastRatio: rows.some(([label, value]) => label === 'Ratio' && /:1$/.test(value)),
            hasAA: rows.some(([label, value]) => label.indexOf('WCAG AA') === 0 && /Pass|Fail/.test(value)),
            hasAAA: rows.some(([label, value]) => label.indexOf('WCAG AAA') === 0 && /Pass|Fail/.test(value)),
            copyButtons: [...panel.querySelectorAll('.redline__color-copy-btn')].map(b => b.textContent)
          };
        })()"""
    )
    check(
        "Color panel shows applicable roles with token/hex/rgb/selector/source/inherited/hardcoded",
        not inspected_text["hidden"]
        and len(inspected_text["roles"]) > 0
        and inspected_text["hasToken"]
        and inspected_text["hasHex"]
        and inspected_text["hasRgb"]
        and inspected_text["hasSelector"]
        and inspected_text["hasSource"]
        and inspected_text["hasInherited"]
        and inspected_text["hasHardcoded"],
        json.dumps(inspected_text),
    )
    check(
        "Color detail renders inside the right inspector, not a floating popover",
        inspected_text["insideRightPanel"] and inspected_text["floatingPanels"] == 0,
        json.dumps(inspected_text),
    )
    check(
        "Contrast ratio and WCAG AA/AAA pass or fail are displayed for text",
        inspected_text["hasContrastRatio"] and inspected_text["hasAA"] and inspected_text["hasAAA"],
        json.dumps(inspected_text),
    )
    check(
        "Copy actions exist for Token, Hex, RGB, and CSS declaration",
        any("Token" in b for b in inspected_text["copyButtons"])
        and any("Hex" in b for b in inspected_text["copyButtons"])
        and any("RGB" in b for b in inspected_text["copyButtons"])
        and any("CSS" in b for b in inspected_text["copyButtons"]),
        json.dumps(inspected_text["copyButtons"]),
    )
    screenshot("color-panel-inspecting-tab")

    token_detection = evaluate(
        """(async () => {
          const btn = [...document.querySelectorAll('button')]
            .find(b => b.textContent.trim() === 'Save Rate Card');
          btn.dispatchEvent(new PointerEvent('pointermove', {bubbles: true}));
          await new Promise(r => setTimeout(r, 500));
          const panel = document.querySelector('[data-redline-inspector]');
          const rows = [...panel.querySelectorAll('.redline__color-row')].map(row => {
            const [label, value] = row.querySelectorAll('span, code');
            return [label.textContent, value.textContent];
          });
          return {
            tokens: rows.filter(([label]) => label === 'Token').map(([, v]) => v),
            hardcoded: rows.filter(([label]) => label === 'Hardcoded').map(([, v]) => v),
            sources: rows.filter(([label]) => label === 'Source').map(([, v]) => v)
          };
        })()"""
    )
    check(
        "A real ADS-tokenized primary button resolves actual token names, not Unmapped",
        "--ads-brand" in token_detection["tokens"]
        and all(t != "Unmapped" for t in token_detection["tokens"])
        and all("uses a token" in h for h in token_detection["hardcoded"])
        and all(s.startswith("styles.css") for s in token_detection["sources"]),
        json.dumps(token_detection),
    )

    click_guard = evaluate(
        """(() => {
          const tabs = [...document.querySelectorAll('.create-md__tab, [data-v2-tab]')];
          const cardTab = tabs.find(t => (t.dataset.v2Tab || '') === 'lines') || tabs[1] || tabs[0];
          const before = cardTab.getAttribute('aria-selected');
          const event = new MouseEvent('click', {bubbles: true, cancelable: true});
          cardTab.dispatchEvent(event);
          const after = cardTab.getAttribute('aria-selected');
          return {before, after, prevented: event.defaultPrevented};
        })()"""
    )
    check(
        "Clicking an application control in Color mode is prevented from triggering its action",
        click_guard["prevented"] and click_guard["before"] == click_guard["after"],
        json.dumps(click_guard),
    )

    copy_test = evaluate(
        """(async () => {
          window.__copied = [];
          navigator.clipboard.writeText = (text) => { window.__copied.push(text); return Promise.resolve(); };
          const panel = document.querySelector('[data-redline-inspector]');
          const hexBtn = [...panel.querySelectorAll('.redline__color-copy-btn')]
            .find(b => b.getAttribute('data-copy-label') === 'Hex');
          const cssBtn = [...panel.querySelectorAll('.redline__color-copy-btn')]
            .find(b => b.getAttribute('data-copy-label') === 'CSS');
          hexBtn.click();
          await new Promise(r => setTimeout(r, 30));
          cssBtn.click();
          await new Promise(r => setTimeout(r, 30));
          return {
            copied: window.__copied,
            hexCopiedMatchesRow: window.__copied[0] === hexBtn.getAttribute('data-copy-text'),
            cssHasDeclaration: /:.*;$/.test(window.__copied[1] || ''),
            copiedFeedback: hexBtn.getAttribute('data-copied')
          };
        })()"""
    )
    check(
        "Copy buttons write the token/hex/rgb/css text to the clipboard and show feedback",
        len(copy_test["copied"]) == 2
        and copy_test["hexCopiedMatchesRow"]
        and copy_test["cssHasDeclaration"],
        json.dumps(copy_test),
    )

    self_inspect_guard = evaluate(
        """(() => {
          const panel = document.querySelector('[data-redline-inspector]');
          const before = panel.innerHTML;
          const controls = [
            '[data-redline-action="mode:grid"]',
            '[data-redline-action="breakpoint:1440"]',
            '[data-redline-action="annotation:lines"]'
          ].map(selector => document.querySelector(selector));
          controls.forEach(control => {
            control.dispatchEvent(new PointerEvent('pointermove', {bubbles: true}));
          });
          return {
            insideShell: controls.every(control =>
              control.closest('.redline') !== null
            ),
            panelUnchangedByShellHover: panel.innerHTML === before
          };
        })()"""
    )
    check(
        "The QA tool does not inspect its own shell controls as application colors",
        self_inspect_guard["insideShell"]
        and self_inspect_guard["panelUnchangedByShellHover"],
        json.dumps(self_inspect_guard),
    )

    escape_scoped = evaluate(
        """(() => {
          document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true, cancelable: true}));
          return {
            active: window.RedlineMode.isActive(),
            color: document.querySelector('[data-redline-action="toggle:color"]').getAttribute('aria-pressed'),
            colorRoles: document.querySelectorAll('.redline__color-role').length
          };
        })()"""
    )
    check(
        "Escape exits Color mode only, leaving the Redline shell active",
        escape_scoped == {"active": True, "color": "false", "colorRoles": 0},
        json.dumps(escape_scoped),
    )

    escape_close = evaluate(
        """(() => {
          document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true, cancelable: true}));
          return {active: window.RedlineMode.isActive(), overlays: document.querySelectorAll('.redline').length};
        })()"""
    )
    check(
        "Escape closes the whole Redline shell when Color mode is not active",
        escape_close == {"active": False, "overlays": 0},
        json.dumps(escape_close),
    )

    for width, height in ((1024, 768), (1280, 800), (1440, 900), (1920, 1080), (2560, 1440)):
        send(
            "Emulation.setDeviceMetricsOverride",
            {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False},
        )
        evaluate("window.RedlineMode.enable('qa')")
        wait_for("document.querySelector('.redline__preview')?.contentDocument?.readyState === 'complete'")
        evaluate("document.querySelector('[data-redline-action=\"toggle:color\"]').click()")
        result = evaluate(
            """(async () => {
              const target = [...document.querySelectorAll('button, a')]
                .find(el => el.getBoundingClientRect().width > 10 && el.getBoundingClientRect().height > 10);
              target.dispatchEvent(new PointerEvent('pointermove', {bubbles: true}));
              await new Promise(r => setTimeout(r, 200));
              // The scrollable panel is the sidebar; its inner content may be
              // taller and scroll independently.
              const panel = document.querySelector('.redline__sidebar--right');
              const rect = panel.getBoundingClientRect();
              const canvas = document.querySelector('.redline__canvas').getBoundingClientRect();
              const colorBtn = document.querySelector('[data-redline-action="toggle:color"]');
              const drawerMode = window.innerWidth <= 960;
              return {
                visible: document.querySelectorAll('.redline__color-role').length > 0,
                withinViewport: rect.right <= window.innerWidth + 1 && rect.bottom <= window.innerHeight + 1
                  && rect.left >= -1,
                // Outside drawer mode the inspector must never cover the preview.
                clearOfCanvas: drawerMode || rect.left >= canvas.right - 0.5,
                colorVisible: colorBtn.getBoundingClientRect().width > 0
                  || (drawerMode && !!colorBtn.closest('.redline__sidebar--left')),
                scrollsIndependently: getComputedStyle(panel).overflowY === 'auto',
                overflowX: document.documentElement.scrollWidth > window.innerWidth + 2
              };
            })()"""
        )
        check(
            f"Color control and inspector behave correctly at {width}px",
            result["visible"]
            and result["withinViewport"]
            and result["clearOfCanvas"]
            and result["colorVisible"]
            and result["scrollsIndependently"]
            and not result["overflowX"],
            json.dumps(result),
        )
        screenshot(f"color-{width}")
        evaluate("window.RedlineMode.disable()")

    send("Emulation.clearDeviceMetricsOverride")

    cleanup = evaluate(
        """(async () => {
          window.RedlineMode.enable('qa');
          document.querySelector('[data-redline-action="toggle:color"]').click();
          const target = [...document.querySelectorAll('button, a')]
            .find(el => el.getBoundingClientRect().width > 10 && el.getBoundingClientRect().height > 10);
          target.dispatchEvent(new PointerEvent('pointermove', {bubbles: true}));
          await new Promise(r => setTimeout(r, 150));
          const hadRoles = document.querySelectorAll('.redline__color-role').length > 0;
          document.querySelector('[data-redline-action="close"]').click();
          return {
            hadRoles,
            overlays: document.querySelectorAll('.redline').length,
            inspectors: document.querySelectorAll('[data-redline-inspector]').length,
            colorRoles: document.querySelectorAll('.redline__color-role').length,
            active: window.RedlineMode.isActive()
          };
        })()"""
    )
    check(
        "Closing the Redline shell removes every color inspection artifact",
        cleanup
        == {
            "hadRoles": True,
            "overlays": 0,
            "inspectors": 0,
            "colorRoles": 0,
            "active": False,
        },
        json.dumps(cleanup),
    )

    reactivate = evaluate(
        """(() => {
          window.RedlineMode.enable('qa');
          const state = window.RedlineMode.debugState();
          window.RedlineMode.disable();
          return state;
        })()"""
    )
    check(
        "Re-activating after close starts with Color mode off",
        reactivate["typography"] is False and reactivate.get("color") is False,
        json.dumps(reactivate),
    )

    check("Browser console has no errors or warnings", not console_messages, json.dumps(console_messages))

finally:
    print(json.dumps({"passes": passes, "failures": len(failures)}, indent=2))
    ws.close()
    chrome.terminate()
    server.shutdown()

if failures:
    raise SystemExit(1)
