"""End-to-end smoke of the flows a PM will drive in the demo.

Filters, search, sort, pagination, the Edit rate card modal, Line and
Premium details, presentation navigation and keyboard control, and the
guarantee that presenting does not mutate the demo data.
"""

import json
import sys
import time

sys.path.insert(0, __file__.rsplit("/", 1)[0] + "/tmp")
from review import E, go, size, console, drain  # noqa: E402


def key(name):
    """Synthetic keydown on the document, which is where the app listens."""
    E(f"""(() => {{
      const ev = new KeyboardEvent('keydown', {{
        key: {name!r}, code: {name!r}, bubbles: true, cancelable: true}});
      (document.activeElement || document.body).dispatchEvent(ev);
    }})()""")

PASSES = 0
FAILURES = []


def check(name, ok, detail=""):
    global PASSES
    if ok:
        PASSES += 1
        print(f"[PASS] {name}")
    else:
        FAILURES.append(name)
        print(f"[FAIL] {name}: {detail}")


def total():
    """The pager's "of N items", which is the filtered result count."""
    label = E("""(document.querySelector('[data-total]') || {}).textContent""")
    digits = "".join(c for c in (label or "") if c.isdigit())
    return int(digits) if digits else 0


size(1440, 900)

# --- filter drawer ----------------------------------------------------
go("version=2.1&section=list", wait=2.7)
baseline = total()
check("list reports a total", baseline > 0, str(baseline))

E("""document.querySelector('[data-action="toggle-filter"]').click()""")
time.sleep(0.8)
check("filter drawer opens",
      E("""document.getElementById('filter-panel')
        .classList.contains('is-open')"""))

order = E("""(() => [...document.querySelectorAll('#filter-panel .fgroup,'
  + ' #filter-panel .fentity')].map(g => (g.querySelector('legend')
  || g.querySelector('.fgroup__legend')
  || g.querySelector('.ads-field__label')).textContent.trim()))()""")
check("filters read Marketplace, Deal season, Status, Buying entity",
      order == ["Marketplace", "Deal season", "Status", "Buying entity"],
      json.dumps(order))

E("""document.querySelector('[data-filter-checkbox="marketplace"]').click()""")
time.sleep(0.4)
count_label = E("""document.querySelector('[data-filter-apply]').textContent.trim()""")
check("footer previews the result count", "rate card" in count_label.lower(),
      count_label)

E("""document.querySelector('[data-filter-apply]').click()""")
time.sleep(0.9)
filtered = total()
check("apply filters narrows the table", filtered < baseline,
      f"{baseline} -> {filtered}")
check("applied filters surface as chips",
      E("""document.querySelectorAll('.fchips__list li').length""") >= 1)

E("""document.querySelector('[data-action="toggle-filter"]').click()""")
time.sleep(0.7)
E("""document.querySelector('#filter-panel [data-action="clear-filters"]').click()""")
time.sleep(0.4)
E("""document.querySelector('#filter-panel [data-action="close-filter"]').click()""")
time.sleep(0.7)
check("cancel leaves the applied filters alone", total() == filtered,
      f"{filtered} -> {total()}")

E("""document.querySelector('[data-action="toggle-filter"]').click()""")
time.sleep(0.7)
E("""document.querySelector('#filter-panel [data-action="clear-filters"]').click()""")
time.sleep(0.3)
E("""document.querySelector('[data-filter-apply]').click()""")
time.sleep(0.9)
check("reset then apply restores every row", total() == baseline,
      f"{baseline} vs {total()}")

E("""document.querySelector('[data-action="toggle-filter"]').click()""")
time.sleep(0.7)
key("Escape")
time.sleep(0.7)
check("Escape closes the filter drawer",
      not E("""document.getElementById('filter-panel')
        .classList.contains('is-open')"""),
      "drawer still open after Escape")

# --- search -----------------------------------------------------------
E("""(() => { const s = document.querySelector('[data-main-search] input');
  s.value = 'upfront'; s.dispatchEvent(new Event('input', {bubbles: true})); })()""")
time.sleep(0.8)
searched = total()
check("search narrows the table", 0 < searched < baseline, str(searched))
E("""(() => { const s = document.querySelector('[data-main-search] input');
  s.value = ''; s.dispatchEvent(new Event('input', {bubbles: true})); })()""")
time.sleep(0.8)
check("clearing search restores every row", total() == baseline, str(total()))

# --- sort + paginate --------------------------------------------------
first = E("""document.querySelector('.table__body .row a').textContent.trim()""")
E("""document.querySelector('.th--sortable').click()""")
time.sleep(0.7)
check("sorting reorders the table",
      E("""document.querySelector('.table__body .row a').textContent.trim()""")
      != first)
check("sorted header announces its direction",
      E("""document.querySelector('.th--sortable')
        .getAttribute('aria-sort')""") in ("ascending", "descending"))

E("""(() => { const b = [...document.querySelectorAll('[data-pager] .page-btn--num')]
  .find(x => x.textContent.trim() === '2'); if (b) b.click(); })()""")
time.sleep(0.9)
check("pagination moves to page 2",
      (E("""(document.querySelector('[data-pager] [aria-current="page"]')
        || {}).textContent""") or "").strip() == "2")

# --- edit rate card modal --------------------------------------------
go("version=2.1&section=create&mode=edit&cardId=RC-DAS-WPP-VIDEO-UF-2627",
   wait=2.9)
before_name = E("""(document.querySelector('[data-v2-card-title]') || {}).textContent""")
E("""document.querySelector('[data-v2-edit-card-link]').click()""")
time.sleep(0.9)
check("Edit rate card modal opens",
      E("""!document.querySelector('[data-rc-create-modal]').hidden"""),
      "modal stayed hidden")
check("modal prefills the rate card ID",
      bool(E("""(document.querySelector('[data-rc-create-modal] #rcm-card-id')
        || {}).value""")))
E("""(() => { const f = document.querySelector('[data-rc-create-modal] #rcm-name');
  f.value = 'Scratch edit that should not stick';
  f.dispatchEvent(new Event('input', {bubbles: true})); })()""")
E("""document.querySelector('[data-action="close-rc-create"]').click()""")
time.sleep(0.8)
check("cancelling the modal discards the edit",
      E("""(document.querySelector('[data-v2-card-title]') || {}).textContent""")
      == before_name)

# --- line details -----------------------------------------------------
E("""(() => { const r = document.querySelector(
  '[data-v2-table-region="lines"] tbody [data-v2-row-id]');
  [...r.children].find(c => String(c.className).indexOf('checkbox') === -1).click();
})()""")
time.sleep(1.0)
check("line details opens on a saved record",
      E("""!!document.querySelector('#v2-advertiser-id').value"""))

before_value = E("""document.querySelector('#v2-line-condition').value""")
E("""(() => { const i = document.querySelector('#v2-line-condition');
  i.blur(); i.focus(); })()""")
time.sleep(0.8)
E("""(() => { const i = document.querySelector('#v2-line-condition');
  i.value = 'NFL'; i.dispatchEvent(new Event('input', {bubbles: true})); })()""")
time.sleep(0.7)
suggestions = E("""document.querySelectorAll(
  '.ads-cond__menu:not([hidden]) .ads-cond__option').length""")
check("line conditions suggest matches as you type", suggestions > 0,
      str(suggestions))
E("""(() => { const o = document.querySelector(
  '.ads-cond__menu:not([hidden]) .ads-cond__option');
  if (o) o.dispatchEvent(new MouseEvent('mousedown', {bubbles: true})); })()""")
time.sleep(0.7)
picked = E("""document.querySelector('#v2-line-condition').value""")
check("choosing a suggestion fills the field",
      picked and picked != before_value, json.dumps([before_value, picked]))
check("choosing a suggestion closes the menu",
      E("""[...document.querySelectorAll('.ads-cond__menu')]
        .every(m => m.hidden)"""))
E("""document.querySelector(
  '[data-v2-form="line"] [data-cond-clear]').click()""")
time.sleep(0.6)
check("the clear control empties the condition",
      E("""document.querySelector('#v2-line-condition').value""") == "")
check("line conditions are not a single-select dropdown",
      E("""!document.querySelector('select#v2-line-condition')
        && !!document.querySelector('#v2-line-condition[role="combobox"]')"""))

E("""document.querySelector('[data-v2-action="close-panel"]').click()""")
time.sleep(0.7)
check("line details closes",
      not E("""document.querySelector('[data-v2-root]')
        .classList.contains('is-panel-open')"""))

# --- premiums ---------------------------------------------------------
E("""document.querySelector('[data-v2-tab="premiums"]').click()""")
time.sleep(0.9)
check("switching to Premiums shows its table",
      E("""document.querySelectorAll(
        '[data-v2-table-region="premiums"] tbody [data-v2-row-id]').length""") > 0)
E("""(() => { const r = document.querySelector(
  '[data-v2-table-region="premiums"] tbody [data-v2-row-id]');
  [...r.children].find(c => String(c.className).indexOf('checkbox') === -1).click();
})()""")
time.sleep(1.0)
method = E("""(document.querySelector('#v2-premium-calc') || {}).value""")
check("premium details opens with an approved calculation method",
      method in ("Additive CPM", "Flat Fee", "Percent Adjustment"), str(method))
E("""document.querySelector('[data-v2-action="close-panel"]').click()""")
time.sleep(0.6)

# --- presentation -----------------------------------------------------
snapshot = E("""localStorage.getItem('rate-card-manager.v2.files')""")
E("""window.RateCardPresentationView.open()""")
time.sleep(2.0)
check("presentation opens on slide 1",
      E("""document.querySelector('[data-rcle]')
        .getAttribute('data-rcle-slide')""") == "1")

key("ArrowRight")
time.sleep(1.3)
check("ArrowRight advances the presentation",
      E("""document.querySelector('[data-rcle]')
        .getAttribute('data-rcle-slide')""") == "2")
key("ArrowLeft")
time.sleep(1.3)
check("ArrowLeft steps back",
      E("""document.querySelector('[data-rcle]')
        .getAttribute('data-rcle-slide')""") == "1")

E("""document.querySelector('[data-rcle-view-toggle]').click()""")
time.sleep(1.2)
check("Previous design view is reachable",
      E("""document.querySelector('[data-rcle]')
        .getAttribute('data-rcle-view')""") == "previous")
E("""document.querySelector('[data-rcle-view-toggle]').click()""")
time.sleep(1.2)
check("returning restores the current design at the same slide",
      E("""document.querySelector('[data-rcle]')
        .getAttribute('data-rcle-slide')""") == "1")

key("Escape")
time.sleep(1.0)
check("Escape closes the presentation",
      E("""!document.querySelector('[data-rcle]')
        || document.querySelector('[data-rcle]').hidden"""))
check("presenting leaves the demo data untouched",
      E("""localStorage.getItem('rate-card-manager.v2.files')""") == snapshot)

drain()
errors = [c for c in console if "error" in str(c).lower()
          and "beforeunload" not in str(c)]
check("no console errors during the run", not errors, json.dumps(errors[:3]))

print(json.dumps({"passes": PASSES, "failures": len(FAILURES)}))
sys.exit(1 if FAILURES else 0)
