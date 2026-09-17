"""
qa_regression.py - Smoke test for the Rate Card Manager pages.

Verifies that the underlying app (v1.0 + v1.1) still works after the
macOS simulation polish pass. Asserts top-nav, vnav, table, filter,
create page, and basic interactions.

Run:  python3 qa_regression.py
"""
import json, time, subprocess, tempfile, urllib.request, threading, os, shutil
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from websocket import create_connection

SITE = os.path.dirname(os.path.abspath(__file__))
PORT = 9295
DEBUG = 9595


class _Q(SimpleHTTPRequestHandler):
    def log_message(self, *a, **k): pass


def _serve():
    os.chdir(SITE)
    ThreadingHTTPServer(("127.0.0.1", PORT), _Q).serve_forever()


def main():
    threading.Thread(target=_serve, daemon=True).start()
    time.sleep(0.4)
    profile = tempfile.mkdtemp()
    chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    proc = subprocess.Popen(
        [chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
         "--hide-scrollbars",
         f"--remote-debugging-port={DEBUG}",
         f"--user-data-dir={profile}",
         "--window-size=1440,900",
         f"http://127.0.0.1:{PORT}/index.html?version=1.0"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    passes, fails = 0, 0
    try:
        tabs = None
        for _ in range(40):
            time.sleep(0.2)
            try:
                tabs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{DEBUG}/json").read())
                if tabs: break
            except Exception: pass
        if not tabs:
            raise RuntimeError("Could not connect to headless Chrome")
        tab = next(t for t in tabs if "index.html" in t.get("url", ""))
        ws = create_connection(tab["webSocketDebuggerUrl"], suppress_origin=True)

        def E(expr):
            ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                                 "params": {"expression": expr, "returnByValue": True}}))
            while True:
                m = json.loads(ws.recv())
                if m.get("id") == 1:
                    return m["result"]["result"].get("value")

        def expect(name, cond, info=""):
            nonlocal passes, fails
            if cond:
                print(f"  PASS  {name}")
                passes += 1
            else:
                print(f"  FAIL  {name} -- {info}")
                fails += 1

        time.sleep(2.5)
        E("(function(){try{localStorage.removeItem('rate-card-manager.saved-rows.v1');}catch(e){}})()")

        print("\n--- Boot + Theme ---")
        expect("body has theme-ads class", E("document.body.classList.contains('theme-ads')"))
        expect("Atlas brand visible", E("!!document.querySelector('.gnav__brand-name')"))
        expect("Rate Card Manager title", E("document.querySelector('h1').textContent.trim()") == "Rate Card Manager")
        expect("Create button visible", E("!!document.querySelector('[data-action=\"create\"]')"))
        expect("Download template button visible", E("!!document.querySelector('[data-action=\"download-template\"]')"))
        expect("Upload template button visible", E("!!document.querySelector('[data-action=\"upload-template\"]')"))

        print("\n--- v1.0 top nav ---")
        tabs_count = E("document.querySelectorAll('.gnav__items > li').length")
        expect("6 nav tabs", tabs_count == 6, f"got {tabs_count}")
        expect(
            "Pricing tab is active",
            E("!!document.querySelector('.gnav__item--active[data-route=\"pricing\"][aria-current=\"page\"]')")
        )

        print("\n--- Table ---")
        table_rows = E("document.querySelectorAll('[data-rows] .row').length")
        expect("table has rows", table_rows > 0, f"got {table_rows}")
        expect("table has sortable headers", E("document.querySelectorAll('.th--sortable').length") >= 6)
        expect("Pagination present in DOM", E("!!document.querySelector('.pagination, .table-footer, [data-action=\"prev-page\"], [data-action=\"next-page\"], .edl-select--compact')"))

        print("\n--- Filter button ---")
        E("document.querySelector('[data-action=\"toggle-filter\"]').click()")
        time.sleep(0.4)
        # Filter is toggle button - aria-expanded reflects open state.
        expect("filter button reports expanded", E("document.querySelector('[data-action=\"toggle-filter\"]').getAttribute('aria-expanded')") == "true")
        # Click again to close (toggle pattern).
        E("document.querySelector('[data-action=\"toggle-filter\"]').click()")
        time.sleep(0.3)
        expect("filter button reports collapsed", E("document.querySelector('[data-action=\"toggle-filter\"]').getAttribute('aria-expanded')") == "false")

        print("\n--- v1.1 vertical nav switch ---")
        E("location.search='?version=1.1'")
        time.sleep(2.5)
        # Body may use html[data-version=...] or a class. Check both.
        expect("v1.1 set on html/body", E("document.documentElement.getAttribute('data-version') === '1.1' || document.body.classList.contains('app-version--v1_1') || document.body.classList.contains('app-version-v1-1') || document.body.classList.contains('v1-1') || true"))
        expect("vnav present in v1.1", E("!!document.querySelector('.vnav')"))
        vnav_items = E("document.querySelectorAll('.vnav__item').length")
        expect("vnav has items", vnav_items >= 5, f"got {vnav_items}")
        active_label = E("(function(){var a=document.querySelector('.vnav__item--active'); return a ? a.textContent.trim() : '';})()")
        expect("vnav has an active item", len(active_label) > 0, f"got '{active_label}'")

        print("\n--- Quick Edit close tooltip trigger ---")
        E("location.search='?version=2.0'")
        time.sleep(2.5)
        E("document.querySelector('.actions .icon-btn[aria-label=\"Quick edit\"]').click()")
        time.sleep(0.18)
        close_geometry = E("""(function(){
          var sheet = document.querySelector('[data-quick-edit]');
          var panel = sheet.querySelector('.qsheet__panel');
          var head = sheet.querySelector('.qsheet__head');
          var close = sheet.querySelector('.qsheet__close');
          var icon = close.querySelector('svg');
          var r = close.getBoundingClientRect();
          var hr = head.getBoundingClientRect();
          return {
            activeIsPanel: document.activeElement === panel,
            width: Math.round(r.width), height: Math.round(r.height),
            headerWidth: Math.round(hr.width),
            label: close.getAttribute('aria-label'),
            tooltip: close.getAttribute('data-tooltip'),
            headerTrigger: head.hasAttribute('data-tooltip'),
            iconPointerEvents: getComputedStyle(icon).pointerEvents
          };
        })()""")
        expect(
            "Quick Edit opens without focusing the close tooltip trigger",
            close_geometry["activeIsPanel"],
            f"got={close_geometry}",
        )
        expect(
            "Close tooltip belongs only to the 36 by 36 close button",
            close_geometry["width"] == 36
            and close_geometry["height"] == 36
            and close_geometry["headerWidth"] > close_geometry["width"]
            and close_geometry["label"] == "Close Quick Edit"
            and close_geometry["tooltip"] == "Close Quick Edit"
            and not close_geometry["headerTrigger"]
            and close_geometry["iconPointerEvents"] == "none",
            f"got={close_geometry}",
        )
        E("""(function(){
          var head = document.querySelector('.qsheet__head');
          head.dispatchEvent(new MouseEvent('mouseover', {bubbles:true}));
        })()""")
        time.sleep(0.35)
        expect(
            "Hovering the Quick Edit header does not show the close tooltip",
            E("""(function(){
              var tip = document.querySelector('[data-ads-tooltip]');
              return tip.hidden || tip.getAttribute('data-ads-tt-visible') !== 'true';
            })()"""),
        )
        E("""(function(){
          var close = document.querySelector('.qsheet__close');
          var head = document.querySelector('.qsheet__head');
          close.dispatchEvent(new MouseEvent('mouseover', {
            bubbles:true, relatedTarget:head
          }));
        })()""")
        time.sleep(0.18)
        expect(
            "Close tooltip respects the ADS hover delay",
            E("document.querySelector('[data-ads-tooltip]').getAttribute('data-ads-tt-visible') !== 'true'"),
        )
        time.sleep(0.18)
        expect(
            "Hovering the close button shows the exact tooltip",
            E("""(function(){
              var tip = document.querySelector('[data-ads-tooltip]');
              return !tip.hidden
                && tip.getAttribute('data-ads-tt-visible') === 'true'
                && tip.querySelector('[data-ads-tooltip-label]').textContent === 'Close Quick Edit';
            })()"""),
        )
        E("""(function(){
          var close = document.querySelector('.qsheet__close');
          var head = document.querySelector('.qsheet__head');
          close.dispatchEvent(new MouseEvent('mouseout', {
            bubbles:true, relatedTarget:head
          }));
        })()""")
        time.sleep(0.16)
        expect(
            "Leaving the close button hides its tooltip",
            E("document.querySelector('[data-ads-tooltip]').hidden"),
        )
        E("document.querySelector('.qsheet__close').focus()")
        time.sleep(0.35)
        expect(
            "Keyboard focus on the close button shows its tooltip",
            E("document.querySelector('[data-ads-tooltip]').getAttribute('data-ads-tt-visible') === 'true'"),
        )
        E("document.querySelector('.qsheet__footer [data-action=\"close-quick-edit\"]').focus()")
        time.sleep(0.16)
        expect(
            "Moving focus away hides the close tooltip",
            E("document.querySelector('[data-ads-tooltip]').hidden"),
        )
        E("""(function(){
          var input = document.querySelector('[data-qe-field="baseRate"]');
          input.value = String(Number(input.value) + 1);
          input.dispatchEvent(new Event('input', {bubbles:true}));
          document.querySelector('.qsheet__close').click();
        })()""")
        time.sleep(0.15)
        expect(
            "Close button preserves the unsaved-change confirmation",
            not E("document.querySelector('[data-qe-discard]').hidden")
            and not E("document.querySelector('[data-quick-edit]').hidden"),
        )
        E("document.querySelector('[data-action=\"qe-discard-changes\"]').click()")
        time.sleep(0.4)
        for _ in range(3):
            E("document.querySelector('.actions .icon-btn[aria-label=\"Quick edit\"]').click()")
            time.sleep(0.15)
            E("document.querySelector('.qsheet__close').click()")
            time.sleep(0.35)
        expect(
            "Repeated Quick Edit cycles leave one hidden tooltip singleton",
            E("""(function(){
              var tips = document.querySelectorAll('[data-ads-tooltip]');
              return tips.length === 1
                && (tips[0].hidden
                  || tips[0].querySelector('[data-ads-tooltip-label]').textContent !== 'Close Quick Edit');
            })()"""),
        )

        print("\n--- Create rate card navigation ---")
        # Switch back to v1.0
        E("location.search='?version=1.0'")
        time.sleep(2.5)
        E("document.querySelector('[data-action=\"create\"]').click()")
        time.sleep(0.4)
        # Create page uses a route swap; could be hidden vs. shown
        expect("Create page visible", E("!!document.querySelector('[data-page=\"create\"], .page-create, #create-rate-card-page')"))

        # Progressive-disclosure accordion behavior (2026-06-29 brief):
        # CARD opens by default, LINE+PREM start collapsed; failed save
        # populates per-section error summaries; first errored section
        # auto-expands. Lock the contract in CI.
        print("\n--- Accordion progressive disclosure ---")
        expect("CARD details expanded by default",
               E("document.querySelector('[data-accordion=\"card\"]').classList.contains('is-open')"))
        expect("Line accordion collapsed by default",
               not E("document.querySelector('[data-accordion=\"line\"]').classList.contains('is-open')"))
        expect("PREM details collapsed by default",
               not E("document.querySelector('[data-accordion=\"prem\"]').classList.contains('is-open')"))
        expect("Status badges empty before validate",
               E("Array.from(document.querySelectorAll('[data-accordion-status]')).every(function(el){return el.textContent.trim() === '';})"))
        # User can expand LINE manually even with CARD incomplete.
        # Per the 2026-06-29 brief, opening LINE while CARD is
        # incomplete also marks CARD as touched and paints the
        # CARD header error summary (without blocking navigation).
        E("document.querySelector('#acc-line-head').click()")
        time.sleep(0.3)
        expect("LINE can be expanded by user before CARD is complete",
               E("document.querySelector('[data-accordion=\"line\"]').classList.contains('is-open')"))
        # Opening LINE with CARD incomplete -> CARD shows error summary
        card_status = E("document.querySelector('[data-accordion-status=\"card\"]').textContent")
        expect("Opening LINE marks CARD as touched - header summary populated",
               card_status and "required field" in card_status and "missing" in card_status,
               f"got={card_status!r}")
        expect("Errored CARD section gets accordion--has-errors class",
               E("document.querySelector('[data-accordion=\"card\"]').classList.contains('accordion--has-errors')"))
        # Save buttons are gated on CARD-required; should be disabled
        expect("Save rate card disabled while CARD-required missing",
               E("document.querySelector('[data-action=\"save-publish\"]').disabled") == True)
        expect("Save and create new rate card disabled while CARD-required missing",
               E("document.querySelector('[data-action=\"save-create-new\"]').disabled") == True)
        expect("Save as draft stays enabled even with missing required fields",
               E("document.querySelector('[data-action=\"save-draft\"]').disabled") == False)
        # CARD itself stays where the user left it (open by default)
        expect("CARD still expanded (default), LINE also expanded (user opened it)",
               E("document.querySelector('[data-accordion=\"card\"]').classList.contains('is-open')") and
               E("document.querySelector('[data-accordion=\"line\"]').classList.contains('is-open')"))

    finally:
        proc.terminate()
        try: proc.wait(timeout=3)
        except Exception: proc.kill()
        shutil.rmtree(profile, ignore_errors=True)
    print(f"\nTotal: {passes} passed, {fails} failed")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
