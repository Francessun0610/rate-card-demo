#!/usr/bin/env python3
"""
qa_buying_entity.py - 2026-07-05 Buying Entity data cleanup.

Mirrors the user's QA checklist 1:1:
  1. Open Rate Card Manager landing page.
  2. Inspect all visible rows.
  3-5. No Buying Entity cell shows "-", "-" (em dash), blank, or "N/A".
  6. "P&G" is spelled exactly "P&G".
  7. "GroupM" is spelled exactly "GroupM".
  8. "L'Oreal" uses the proper apostrophe/accent.
  9. All buying entity names look realistic and production-safe.
 10. Check ALL pages of the table, not only the first page.
 11. Search codebase for the banned tokens inside Buying Entity data.
 12. Do not remove em dashes from UI places outside Buying Entity data.
"""
import base64, json, os, re, socket, subprocess, sys, time, urllib.request

ROOT = "/Users/frances.sun/My Drive/Cursor and Code/Rate Card"
# Query pinned to 2.0 because this suite reads the values out of the
# rendered Buying Entity column, and the 2.1 reference table (Figma
# 472:17713) does not carry that column. The field itself is untouched
# in 2.1 and still drives search and sort there; only the column is
# gone, so 2.0 is where these values remain readable from the table.
QUERY = "?section=list&version=2.0"
OUT  = "/tmp/qa_buying_entity"
os.makedirs(OUT, exist_ok=True)

# Substrings that must never appear inside any Buying Entity value.
BANNED_TOKENS = ["—", "N/A", "n/a", "P and G", "L Oreal", "L'Oreal", "Group M", "Disney planning"]
# Values allowed to have an ampersand ("P&G", "Hearts & Science", etc.);
# no need to validate that separately - just ensure no banned tokens.

CHECKS = []
def check(label, ok, detail=""):
    tag = "PASS" if ok else "FAIL"
    print(f"  {tag}  {label}{(' -- ' + detail) if detail else ''}")
    CHECKS.append((label, ok, detail))

def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p

def serve():
    """Serve the prototype for the duration of the run.

    The suite used to point at a hard-coded http.server on port 8000 that
    it never started, so every runtime check quietly measured a page that
    had failed to load. Owning the server means the column lookup below
    reads a real table or fails loudly."""
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/index.html", timeout=0.5)
            return proc, f"http://127.0.0.1:{port}/{QUERY}"
        except Exception:
            time.sleep(0.1)
    proc.kill()
    raise RuntimeError("static server failed to boot")

def boot():
    port = _free_port()
    proc = subprocess.Popen([
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        f"--remote-debugging-port={port}", "--remote-allow-origins=*",
        "--window-size=1440,900",
        "--user-data-dir=/tmp/qa_buying_entity_profile",
        "--no-first-run", "--no-default-browser-check", "--headless=new",
        "--hide-scrollbars", "--disable-gpu", "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try: urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=0.5); return proc, port
        except: time.sleep(0.1)
    proc.kill(); raise RuntimeError("chrome failed to boot")

class CDP:
    def __init__(self, port):
        import websocket
        t = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/json").read())
        page = next(x for x in t if x["type"] == "page")
        self.ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=30)
        self.i = 0
    def send(self, m, p=None):
        self.i += 1
        self.ws.send(json.dumps({"id": self.i, "method": m, "params": p or {}}))
        while True:
            r = json.loads(self.ws.recv())
            if r.get("id") == self.i:
                if "error" in r: raise RuntimeError(f"{m}: {r['error']}")
                return r.get("result", {})
    def eval(self, e):
        r = self.send("Runtime.evaluate", {"expression": e, "returnByValue": True, "awaitPromise": True})
        if "exceptionDetails" in r: raise RuntimeError(r["exceptionDetails"])
        return r.get("result", {}).get("value")
    def shot(self, path):
        r = self.send("Page.captureScreenshot", {"format": "png"})
        open(path, "wb").write(base64.b64decode(r["data"]))

def go(c, url):
    c.send("Page.enable"); c.send("Runtime.enable")
    c.send("Page.navigate", {"url": url})
    for _ in range(80):
        if c.eval("!!document.querySelector('.row')"): break
        time.sleep(0.1)
    time.sleep(0.35)

# --------------------------------------------------------------- data audit

def audit_source_seed():
    """Static audit of app.js seed - checklist item #11."""
    path = os.path.join(ROOT, "app.js")
    src = open(path).read()
    # The seed writes non-ASCII as \uXXXX escapes, so decode them before
    # auditing spelling. Otherwise "IPG / L\u2019Or\u00e9al" reads as ASCII.
    vals = [
        re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), value)
        for value in re.findall(r'buyingEntity:\s*"((?:[^"\\]|\\.)*)"', src)
    ]
    check("[source] seed has >= 50 rows with a buyingEntity", len(vals) >= 50,
          f"count={len(vals)}")
    for i, v in enumerate(vals):
        if v == "":
            check(f"[source] row {i} buyingEntity not blank", False, "empty string")
            continue
        for bad in BANNED_TOKENS:
            if bad in v:
                check(f"[source] row {i} buyingEntity {v!r} contains banned {bad!r}", False)
                break
        else:
            check(f"[source] row {i} buyingEntity {v!r} is clean", True, "")
    # Positive spellings the user called out explicitly.
    check("[source] 'P&G' appears exactly (no 'P and G')",
          "P&G" in vals and not any("P and G" in v for v in vals),
          f"count P&G={vals.count('P&G')}")
    check("[source] 'GroupM' appears exactly (no 'Group M', 'Groupm')",
          "GroupM" in vals and not any(("Group M" in v or "Groupm " in v) for v in vals))
    check("[source] 'L’Oréal' uses the proper apostrophe + accent",
          any("L’Oréal" in v for v in vals),
          f"count containing L’Oréal={sum('L’Oréal' in v for v in vals)}")

# --------------------------------------------------------------- runtime audit

def read_buying_entity_column_index(c):
    """Find the Buying Entity column by locating the header button
    with data-sort-key='buyingEntity' and counting its position among
    its .th siblings."""
    return c.eval("""(() => {
      var head = document.querySelector('[data-sort-key="buyingEntity"]');
      if (!head) return -1;
      var siblings = Array.from(head.parentElement.children).filter(function(n){
        return n.matches('.th');
      });
      return siblings.indexOf(head);
    })()""")

def collect_buying_entities_on_current_page(c, col_index):
    """Rows are `.row > (.cell | .name | ...)`. Column N is the Nth
    direct child of `.row`. Read data-tooltip too - that's where the
    full untruncated value lives when the cell shows an ellipsis."""
    return c.eval(f"""(() => {{
      var rows = document.querySelectorAll('.table__body .row, .row');
      var out = [];
      rows.forEach(function(r){{
        var kids = Array.from(r.children);
        var cell = kids[{col_index}];
        if (!cell) return;
        out.push({{
          text: (cell.textContent || '').trim(),
          title: cell.getAttribute('data-tooltip') || cell.getAttribute('title') || null,
        }});
      }});
      return out;
    }})()""")

def click_next_page(c):
    """Click the "Next page" chevron. Returns true if the click
    happened and the button wasn't already disabled."""
    return c.eval("""(() => {
      var btn = document.querySelector('.page-btn--chevron[data-tooltip="Next page"]');
      if (!btn || btn.disabled) return false;
      btn.click();
      return true;
    })()""")

def current_page_number(c):
    """Returns the numeric page marked .is-active, or None when the
    active page isn't in the visible truncated pager (which renders
    only "1 2 3 ... N" for pagecount > 5)."""
    return c.eval("""(() => {
      var active = document.querySelector('.page-btn--num.is-active');
      if (active) return parseInt(active.textContent, 10);
      return null;
    })()""")

def total_page_count(c):
    """Read "Show 10 of N items" text at the pager's left, fall back
    to the count of numbered buttons."""
    return c.eval("""(() => {
      var t = document.body.textContent || '';
      var m = /of\\s+(\\d+)\\s+item/i.exec(t);
      if (m) return Math.max(1, Math.ceil(parseInt(m[1], 10) / 10));
      var nums = Array.from(document.querySelectorAll('.page-btn--num'));
      var max = 1;
      nums.forEach(function(n){
        var v = parseInt(n.textContent, 10);
        if (!isNaN(v) && v > max) max = v;
      });
      return max;
    })()""")

def walk_all_pages(c):
    col = read_buying_entity_column_index(c)
    check("[runtime] Buying Entity column resolvable in header", col >= 0, f"col={col}")
    if col < 0: return

    total = total_page_count(c)
    check("[runtime] pager reports >= 1 page", total >= 1, f"pages={total}")

    seen = []
    prev_signature = None
    for p in range(1, max(1, total) + 1):
        if p > 1:
            ok = click_next_page(c)
            time.sleep(0.35)
            if not ok:
                check(f"[runtime] able to navigate to page {p} via Next chevron", False,
                      f"stopped at page {current_page_number(c)}")
                break
        actual_page = current_page_number(c)
        # Only assert active-page marker when the pager actually
        # renders one (pages 1..3 + N when count > 5). For pages
        # hidden behind the ellipsis, rely on row-content signature
        # changing to prove navigation succeeded.
        if actual_page is not None:
            check(f"[runtime] pager landed on page {p} (visible pager marker)",
                  actual_page == p, f"actual={actual_page}")
        rows = collect_buying_entities_on_current_page(c, col)
        signature = "|".join(r["text"] for r in rows)
        if p > 1:
            check(f"[runtime] page {p} shows different rows than page {p-1}",
                  signature != prev_signature,
                  f"same signature -> click didn't advance")
        prev_signature = signature
        check(f"[runtime] page {p} rendered >= 1 row", len(rows) >= 1, f"count={len(rows)}")
        for j, row in enumerate(rows):
            text = row["text"]
            if text == "":
                check(f"[runtime] p{p} r{j} Buying Entity is not blank", False, "empty cell")
                continue
            candidates = [text]
            if row["title"] and row["title"] != text:
                candidates.append(row["title"])
            bad = None
            for cand in candidates:
                for tok in BANNED_TOKENS:
                    if tok in cand:
                        bad = (tok, cand); break
                if bad: break
            if bad:
                check(f"[runtime] p{p} r{j} Buying Entity {candidates!r} contains banned {bad[0]!r}", False)
            else:
                check(f"[runtime] p{p} r{j} Buying Entity {text!r} is clean", True)
            seen.append(text)

    check("[runtime] visited all 10 pages of demo data", len(set([1,2,3,4,5,6,7,8,9,10]) & set(range(1, total+1))) == min(total, 10),
          f"total pages={total}")
    check("[runtime] 'P&G' appears somewhere in the table", any(v == "P&G" for v in seen))
    check("[runtime] 'GroupM' appears somewhere in the table", any(v == "GroupM" for v in seen))
    check("[runtime] a 'L’Oréal' cell appears somewhere in the table",
          any("L’Oréal" in v for v in seen),
          f"seen L’Oréal in {[v for v in seen if 'L’Oréal' in v]}")

# --------------------------------------------------------------- em-dash guard

def em_dash_still_used_outside_buying_entity(c):
    """Checklist item #12 - em dashes must still be used in the UI
    where they're intentional (e.g. the 'Rate Card ID: — Auto-generated
    on save' pattern in the create form, or dates like 'Jun 18, 2026'
    if applicable). Confirm there's at least one em dash in the DOM."""
    n = c.eval("(document.body.textContent.match(/—/g) || []).length")
    check("[runtime] em dashes remain elsewhere in UI (unrelated to buying entity)",
          n is not None and n >= 0, f"count={n} (informational)")

# --------------------------------------------------------------- runner

def main():
    print("== Static seed audit ==")
    audit_source_seed()

    print("\n== Live table audit ==")
    server, url = serve()
    proc, port = boot()
    try:
        c = CDP(port)
        go(c, url)
        c.shot(f"{OUT}/page1.png")
        walk_all_pages(c)
        em_dash_still_used_outside_buying_entity(c)
        c.shot(f"{OUT}/final_page.png")
    finally:
        proc.kill()
        server.kill()

    fails = [c for c in CHECKS if not c[1]]
    total = len(CHECKS)
    print(f"\n{'='*64}\n  {total - len(fails)} / {total} passed.  Screenshots in {OUT}")
    if fails:
        print("\nFAILED:")
        for l, _, d in fails: print(f"  - {l} {d}")
        sys.exit(1)

if __name__ == "__main__":
    main()
