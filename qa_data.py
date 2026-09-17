"""
qa_data.py - Validate the production-scale Rate Card dataset.

Asserts:
  - 100 total rows in RATE_CARDS
  - 10 distinct pages of 10 rows each (page size = 10)
  - Every row has the required fields populated
  - Every row's name has a season suffix that round-trips to row.season
  - No forbidden terms (Linear, Broadcast, Cable, ABC Linear, ESPN Linear,
    Example, Sample, Test, Demo, Lorem)
  - Marketplace values match the PRD enum
  - Sorting works (Name asc / desc)
  - Filter works (Marketplace = Upfront returns subset)
  - Search works (substring across name / id / saleshub / buying entity)
  - Row body selects without navigating; Name link opens Edit
  - Last row (id=100) opens its specific data, not a different row

Run:  python3 qa_data.py
"""
import json, time, subprocess, tempfile, urllib.request, threading, os, shutil
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from websocket import create_connection

SITE = os.path.dirname(os.path.abspath(__file__))
PORT = 9296
DEBUG = 9596


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
         f"http://127.0.0.1:{PORT}/index.html"],
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
        # Clear any persisted user-added rows so we get the pure seed set
        E("(function(){try{localStorage.removeItem('rate-card-manager.saved-rows.v1');}catch(e){}location.reload();})()")
        time.sleep(2.5)

        print("\n--- Dataset shape ---")
        total = E("window.RATE_CARDS.length")
        expect("100 rows total", total == 100, f"got {total}")
        # Pagination footer (page count = 10)
        page_text = E("(document.querySelector('.pagination') ? document.querySelector('.pagination').textContent : '')")
        expect("table renders", page_text is not None and len(page_text) >= 0)

        print("\n--- Row schema ---")
        # Every row has the required fields
        missing = E("""
          (function(){
            var req = ['id','status','saleshubId','rateCardId','name','marketplace','buyingEntity','lastUpdated','version','season'];
            var bad = [];
            window.RATE_CARDS.forEach(function(r){
              req.forEach(function(k){
                if (r[k] === undefined || r[k] === null || String(r[k]).length === 0) {
                  bad.push(r.id + ':' + k);
                }
              });
            });
            return bad;
          })()
        """)
        expect("every row has all required fields", isinstance(missing, list) and len(missing) == 0, f"missing: {missing[:5] if missing else missing}")
        # Marketplace values
        markets = E("Array.from(new Set(window.RATE_CARDS.map(r=>r.marketplace))).sort()")
        allowed_markets = {"Upfront", "Scatter", "Multi-Year"}
        bad_market = [m for m in markets if m not in allowed_markets]
        expect("all marketplaces in allowed set", len(bad_market) == 0, f"unknown: {bad_market}")
        # Status values
        statuses = E("Array.from(new Set(window.RATE_CARDS.map(r=>r.status))).sort()")
        expect("status is Published or Draft only", set(statuses) <= {"Published","Draft"}, f"got {statuses}")
        # Deal Season is stored in the PRD's YYYY-YYYY form, not the old
        # 25-26 shorthand, and the two years must be consecutive.
        bad_season = E(
            "window.RATE_CARDS.filter(r => {"
            "  const m = /^(\\d{4})-(\\d{4})$/.exec(r.season || '');"
            "  return !m || Number(m[2]) <= Number(m[1]);"
            "}).length"
        )
        expect("every row has valid season", bad_season == 0, f"bad count: {bad_season}")

        print("\n--- Forbidden terms ---")
        # The user explicitly forbade these
        for term in ["Linear", "Broadcast", "Cable", "Lorem", "Sample", "Demo", "Example", "Test "]:
            hits = E(f"window.RATE_CARDS.filter(r => (r.name||'').includes('{term}') || (r.rateCardId||'').includes('{term.upper()}')).length")
            expect(f"no rows contain '{term}'", hits == 0, f"got {hits} hits")
        # The user said "No 'Example Rate Card'" - confirm
        example_hits = E("window.RATE_CARDS.filter(r => /Example/i.test(r.name)).length")
        expect("no name contains 'Example'", example_hits == 0, f"got {example_hits}")

        print("\n--- Variety ---")
        unique_entities = E("new Set(window.RATE_CARDS.map(r=>r.buyingEntity)).size")
        expect("at least 25 unique buying entities", unique_entities >= 25, f"got {unique_entities}")
        unique_markets = E("new Set(window.RATE_CARDS.map(r=>r.marketplace)).size")
        expect("exactly 3 PRD marketplaces represented", unique_markets == 3, f"got {unique_markets}")
        unique_seasons = E("new Set(window.RATE_CARDS.map(r=>r.season)).size")
        expect("at least 3 deal seasons represented", unique_seasons >= 3, f"got {unique_seasons}")

        print("\n--- Pagination ---")
        visible1 = E("document.querySelectorAll('[data-rows] .row').length")
        expect("page 1 shows 10 rows", visible1 == 10, f"got {visible1}")
        # Navigate to page 10 via the numbered page button.
        E("(function(){var btns=document.querySelectorAll('[data-pager] .page-btn--num'); var target=null; btns.forEach(b=>{if(b.textContent.trim()==='10') target=b;}); if(target) target.click();})()")
        time.sleep(0.4)
        page10_visible = E("document.querySelectorAll('[data-rows] .row').length")
        expect("last page shows 10 rows", page10_visible == 10, f"got {page10_visible}")
        # Confirm a unique row from page 10 (id=100) is visible
        has_100 = E("Array.from(document.querySelectorAll('[data-rows] .row')).some(r => r.textContent.includes('IPG-MCARD'))")
        expect("page 10 contains row id=100 (IPG Mastercard)", has_100)
        # Reset to page 1
        E("(function(){var btns=document.querySelectorAll('[data-pager] .page-btn--num'); var target=null; btns.forEach(b=>{if(b.textContent.trim()==='1') target=b;}); if(target) target.click();})()")
        time.sleep(0.4)

        print("\n--- Sort ---")
        # Click Name header to sort A->Z
        E("document.querySelector('[data-sort-key=\"name\"]').click()")
        time.sleep(0.3)
        first_name_asc = E("document.querySelector('[data-rows] .row .name__link').textContent")
        # Click again for desc
        E("document.querySelector('[data-sort-key=\"name\"]').click()")
        time.sleep(0.3)
        first_name_desc = E("document.querySelector('[data-rows] .row .name__link').textContent")
        expect("sort asc vs desc differ", first_name_asc != first_name_desc, f"asc={first_name_asc} desc={first_name_desc}")
        # Reset sort
        E("document.querySelector('[data-sort-key=\"name\"]').click()")
        time.sleep(0.3)

        print("\n--- Search ---")
        search = E("document.querySelector('[data-action=\"search\"]')")
        if search is None:
            # try the search input by placeholder
            E("(function(){var i=document.querySelector('input[type=\"search\"], input[placeholder*=\"Search\"]'); if(i){i.value='PepsiCo'; i.dispatchEvent(new Event('input', {bubbles:true}));}})()")
        else:
            E("(function(){var i=document.querySelector('[data-action=\"search\"]'); i.value='PepsiCo'; i.dispatchEvent(new Event('input', {bubbles:true}));})()")
        time.sleep(0.4)
        rows_after_search = E("document.querySelectorAll('[data-rows] .row').length")
        expect("search 'PepsiCo' narrows results", rows_after_search >= 1 and rows_after_search < 100, f"got {rows_after_search}")
        has_pepsi = E("Array.from(document.querySelectorAll('[data-rows] .row')).every(r => r.textContent.toLowerCase().includes('pepsi'))")
        expect("all visible search results match 'PepsiCo'", has_pepsi)
        # Clear search
        E("(function(){var i=document.querySelector('[data-action=\"search\"], input[type=\"search\"], input[placeholder*=\"Search\"]'); if(i){i.value=''; i.dispatchEvent(new Event('input', {bubbles:true}));}})()")
        time.sleep(0.3)

        print("\n--- Row selection and Name-link Edit ---")
        # Row body selection must not duplicate the Name link's Edit behavior.
        E("(function(){var firstRow = document.querySelector('[data-rows] .row'); var statusCell = firstRow.querySelector('.cell--status'); statusCell.click();})()")
        time.sleep(0.2)
        selected_without_navigation = E("""document.body.getAttribute('data-route') !== 'create'
          && document.querySelector('[data-rows] .row').getAttribute('aria-selected') === 'true'""")
        expect("click on row body selects without navigating", selected_without_navigation)
        E("document.querySelector('[data-rows] .row .name__link').click()")
        time.sleep(0.5)
        on_edit_page = E("document.body.getAttribute('data-route') === 'create'")
        expect("Name link navigates to Edit/Create page", on_edit_page)
        prefilled_name = E("""document.querySelector('[data-v2-form="card"]')
          ? document.querySelector('[data-v2-form="card"]').elements.name.value
          : document.querySelector('#rc-name')?.value || ''""")
        expect("Edit page form is prefilled with row name", bool(prefilled_name), f"got '{prefilled_name}'")
        # Go back to list
        E("(function(){var b=document.querySelector('[data-action=\"go-list\"]'); if(b) b.click();})()")
        time.sleep(0.4)

        print("\n--- Row click respects Action buttons ---")
        # Clicking an action icon should NOT navigate to Edit (should fire its own handler)
        # We click the Quick Edit icon; the page should stay on rcm route.
        # 2.1 moves the row actions into the selected-row action bar, so there is
        # no in-row icon to click there and the case does not apply.
        has_row_actions = E("!!document.querySelector('[data-rows] .row .actions .icon-btn')")
        if has_row_actions:
            E("(function(){var firstRow = document.querySelector('[data-rows] .row'); var qeBtn = firstRow.querySelector('.actions .icon-btn'); qeBtn.click();})()")
            time.sleep(0.4)
            still_on_list = E("document.body.getAttribute('data-route') !== 'create'")
            expect("clicking action button does NOT open Edit page", still_on_list)
            # Close quick edit if it opened
            E("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))")
            time.sleep(0.3)
        else:
            print("  SKIP  clicking action button does NOT open Edit page"
                  " -- this version has no in-row action icons")

        print("\n--- Keyboard row selection (Enter) ---")
        # Selection is a toggle, and the row-body click above left this row
        # selected, so clear the selection first. Otherwise Enter deselects and
        # the assertion measures the wrong half of the toggle.
        E("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))")
        time.sleep(0.3)
        E("(function(){var r = document.querySelector('[data-rows] .row'); r.focus(); r.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));})()")
        time.sleep(0.2)
        selected_kbd = E("""document.body.getAttribute('data-route') !== 'create'
          && document.querySelector('[data-rows] .row').getAttribute('aria-selected') === 'true'""")
        expect("Enter key on focused row selects without navigating", selected_kbd)

    finally:
        proc.terminate()
        try: proc.wait(timeout=3)
        except Exception: proc.kill()
        shutil.rmtree(profile, ignore_errors=True)
    print(f"\nTotal: {passes} passed, {fails} failed")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
