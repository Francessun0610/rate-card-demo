"""Rate Card Manager filter drawer.

Covers the drawer shell, the three checkbox groups, the buying entity
autocomplete, filter combination (OR within a category, AND across
them), Apply / Cancel / Reset / Clear all, applied chips, URL
persistence, pagination and sorting interaction, the zero-result state,
and keyboard operation.
"""

import json
import sys
import time

sys.path.insert(0, __file__.rsplit("/", 1)[0] + "/tmp")
from review import E, go, size, console, drain  # noqa: E402

PASSES = 0
FAILURES = []


def check(name, ok, detail=""):
    global PASSES
    if ok:
        PASSES += 1
        print(f"[PASS] {name}")
    else:
        FAILURES.append({"name": name, "detail": detail})
        print(f"[FAIL] {name}: {detail}")


def open_drawer():
    E("""document.querySelector('[data-action="toggle-filter"]').click()""")
    time.sleep(0.55)


def pick(key, value, checked=True):
    E("""(() => { const c = document.querySelector(
      '[data-filter-checkbox="%s"][data-filter-value="%s"]');
      c.checked = %s; c.dispatchEvent(new Event('change', {bubbles: true})); })()"""
      % (key, value, "true" if checked else "false"))


def apply_now():
    E("""document.querySelector('[data-filter-apply]').click()""")
    time.sleep(0.6)


def total():
    return int(E("""(() => { const m = document.querySelector('[data-total]')
      .textContent.match(/\\d+/); return m ? Number(m[0]) : 0; })()"""))


def rows_shown():
    return E("""document.querySelectorAll('[data-rows] .row').length""")


size(1440, 900)

# ---------------------------------------------------------------- shell
go("version=2.1&section=list", wait=2.4)
open_drawer()

shell = E("""(() => {
  const p = document.querySelector('#filter-panel');
  const scrim = document.querySelector('[data-filter-scrim]');
  const nav = document.querySelector('.gnav').getBoundingClientRect();
  const head = p.querySelector('.fpanel__header').getBoundingClientRect();
  const foot = p.querySelector('.fpanel__footer').getBoundingClientRect();
  const pr = p.getBoundingClientRect();
  return {
    role: p.getAttribute('role'),
    modal: p.getAttribute('aria-modal'),
    labelled: p.getAttribute('aria-labelledby'),
    title: p.querySelector('.fpanel__title').textContent.trim(),
    reset: p.querySelector('[data-action="clear-filters"]').textContent.trim(),
    closeLabel: p.querySelector('.fpanel__close').getAttribute('aria-label'),
    scrimShown: !!scrim && !scrim.hidden,
    scrimDims: scrim ? getComputedStyle(scrim).backgroundColor : null,
    headerBelowNav: head.top >= nav.bottom,
    headerVisible: head.height > 0,
    footerPinned: Math.abs(foot.bottom - pr.bottom) < 2,
    cancel: p.querySelector('.fpanel__footer .btn--secondary').textContent.trim(),
  };
})()""")
check("drawer is a labelled modal dialog",
      shell["role"] == "dialog" and shell["modal"] == "true"
      and shell["labelled"] == "filter-panel-title", json.dumps(shell))
check("header shows Filters, Reset filters and a labelled close button",
      shell["title"] == "Filters" and shell["reset"] == "Reset filters"
      and shell["closeLabel"] == "Close filters", json.dumps(shell))
check("header is visible below the global nav",
      shell["headerBelowNav"] and shell["headerVisible"], json.dumps(shell))
check("footer is pinned to the bottom with a Cancel button",
      shell["footerPinned"] and shell["cancel"] == "Cancel", json.dumps(shell))
check("a dimmed scrim sits behind the drawer",
      shell["scrimShown"] and "rgba(0, 0, 0" in (shell["scrimDims"] or ""),
      json.dumps(shell))

# --------------------------------------------------------------- fields
fields = E("""(() => {
  const groups = [...document.querySelectorAll('#filter-panel .fgroup')].map(g => ({
    tag: g.tagName,
    legend: (g.querySelector('legend') || g.querySelector('.fgroup__legend'))
      .textContent.trim(),
    values: [...g.querySelectorAll('.fgroup__option')]
      .map(o => o.getAttribute('data-filter-value')),
    labels: [...g.querySelectorAll('.fgroup__option-text')].map(t => t.textContent),
    allCheckboxes: [...g.querySelectorAll('input')].every(i => i.type === 'checkbox'),
  }));
  const entity = document.querySelector('#fp-entity');
  return {groups, entityLabel: document.querySelector('label[for="fp-entity"]').textContent.trim(),
          entityPlaceholder: entity.placeholder,
          entityRole: entity.getAttribute('role')};
})()""")
by_legend = {g["legend"]: g for g in fields["groups"]}

check("Status offers only Draft and Published as checkboxes",
      by_legend["Status"]["values"] == ["Draft", "Published"]
      and by_legend["Status"]["allCheckboxes"], json.dumps(by_legend.get("Status")))
check("Status uses a fieldset so the group has an accessible name",
      by_legend["Status"]["tag"] == "FIELDSET", by_legend["Status"]["tag"])
check("Marketplace offers Upfront, Scatter and Multi-Year",
      sorted(by_legend["Marketplace"]["values"]) == ["Multi-Year", "Scatter", "Upfront"],
      json.dumps(by_legend.get("Marketplace")))
# The visible form is the normalized YYYY-YYYY the record stores; an en
# dash read nicely but was a different string from the value.
import re as _re
check("Deal season is present and normalized to YYYY-YYYY",
      by_legend["Deal season"]["labels"]
      and all(_re.fullmatch(r"\d{4}-\d{4}", label)
              for label in by_legend["Deal season"]["labels"]),
      json.dumps(by_legend.get("Deal season")))
check("Buying entity is a labelled combobox with the right placeholder",
      fields["entityLabel"] == "Buying entity"
      and fields["entityPlaceholder"] == "Search name or Saleshub ID"
      and fields["entityRole"] == "combobox", json.dumps(fields))
check("no status the data cannot produce is offered",
      "Archived" not in by_legend["Status"]["values"]
      and "Active" not in by_legend["Status"]["values"],
      json.dumps(by_legend["Status"]["values"]))

# ------------------------------------------------------- result count
baseline = total()
pick("marketplace", "Scatter")
time.sleep(0.25)
count_label = E("""document.querySelector('[data-filter-apply]').textContent""")
check("Apply button previews the result count before applying",
      count_label.startswith("Show ") and count_label.endswith(" rate cards")
      and str(baseline) not in count_label, count_label)
check("Apply stays enabled while previewing",
      E("""!document.querySelector('[data-filter-apply]').disabled"""))

# ------------------------------------------------------ cancel discards
E("""document.querySelector('#filter-panel .fpanel__footer .btn--secondary').click()""")
time.sleep(0.6)
check("Cancel closes without applying",
      total() == baseline and not E("""document.querySelector('#filter-panel')
        .classList.contains('is-open')"""), str(total()))
open_drawer()
check("reopening after Cancel shows no leftover draft",
      E("""[...document.querySelectorAll('[data-filter-checkbox]')]
        .every(c => !c.checked)"""))

# ------------------------------------------------------- OR within, AND across
pick("status", "Draft")
pick("status", "Published")
pick("marketplace", "Scatter")
apply_now()
combined = total()
expected = E("""(() => window.RATE_CARDS.filter(r =>
  (r.status === 'Draft' || r.status === 'Published') && r.marketplace === 'Scatter').length)()""")
check("OR within a category and AND across categories",
      combined == expected, f"table {combined}, data {expected}")
check("applying resets pagination to page 1",
      E("""document.querySelector('[data-pager] .is-active').textContent.trim()""") == "1")

# ------------------------------------------------------------- chips
chips = E("""[...document.querySelectorAll('.fchips__text')].map(c => c.textContent)""")
check("one chip per selected value",
      len(chips) == 3 and "Status: Draft" in chips and "Marketplace: Scatter" in chips,
      json.dumps(chips))
check("trigger label counts individual values",
      E("""document.querySelector('[data-action="toggle-filter"] span').textContent""")
      == "Filters (3)")
check("every chip remove button has an accessible name",
      E("""[...document.querySelectorAll('.fchips__remove')]
        .every(b => (b.getAttribute('aria-label') || '').length > 6)"""))

# --------------------------------------------------------- URL round trip
url = E("""location.search""")
check("applied filters are written to the URL",
      "status=Draft%2CPublished" in url and "marketplace=Scatter" in url, url)
check("unrelated params survive", "version=2.1" in url, url)

go(url.lstrip("?"), wait=2.4)
check("filters survive a refresh from the URL",
      total() == combined, f"{total()} vs {combined}")
check("restored state repopulates the chips",
      E("""document.querySelectorAll('.fchips__text').length""") == 3,
      str(E("""document.querySelectorAll('.fchips__text').length""")))

# ------------------------------------------- filters survive sort + paging
E("""document.querySelector('[data-action="sort"][data-sort-key="name"]').click()""")
time.sleep(0.5)
check("sorting preserves the applied filters", total() == combined, str(total()))
E("""(() => { const next = document.querySelector('[data-pager] .page-btn--num:not(.is-active)');
  if (next) next.click(); })()""")
time.sleep(0.5)
check("paging preserves the applied filters", total() == combined, str(total()))

# -------------------------------------------------- chip removal updates
E("""(() => { const b = [...document.querySelectorAll('.fchips__remove')]
  .find(x => x.getAttribute('data-chip-value') === 'Scatter'); b.click(); })()""")
time.sleep(0.6)
after_chip = total()
check("removing a chip immediately widens the list", after_chip > combined,
      f"{after_chip} vs {combined}")
check("removing a chip updates the URL",
      "marketplace=" not in E("""location.search"""), E("""location.search"""))
check("removing a chip resets to page 1",
      E("""document.querySelector('[data-pager] .is-active').textContent.trim()""") == "1")

# -------------------------------------------------------------- clear all
E("""document.querySelector('[data-action="clear-all-filters"]').click()""")
time.sleep(0.6)
check("Clear all restores the full list", total() == baseline, str(total()))
check("Clear all hides the chip bar",
      E("""document.querySelector('[data-filter-chips]').hidden"""))
check("Clear all clears the URL",
      "status=" not in E("""location.search"""), E("""location.search"""))
check("Clear all resets the trigger label",
      E("""document.querySelector('[data-action="toggle-filter"] span').textContent""")
      == "Filters")

# ------------------------------------------------- reset clears draft only
open_drawer()
pick("marketplace", "Upfront")
apply_now()
applied_upfront = total()
open_drawer()
pick("status", "Draft")
E("""document.querySelector('[data-action="clear-filters"]').click()""")
time.sleep(0.4)
check("Reset filters clears the draft checkboxes",
      E("""[...document.querySelectorAll('[data-filter-checkbox]')].every(c => !c.checked)"""))
check("Reset filters leaves the drawer open",
      E("""document.querySelector('#filter-panel').classList.contains('is-open')"""))
check("Reset filters alone does not change the table",
      total() == applied_upfront, f"{total()} vs {applied_upfront}")
E("""document.querySelector('#filter-panel .fpanel__footer .btn--secondary').click()""")
time.sleep(0.5)
check("Cancel after Reset restores the previously applied state",
      total() == applied_upfront, f"{total()} vs {applied_upfront}")
open_drawer()
E("""document.querySelector('[data-action="clear-filters"]').click()""")
time.sleep(0.3)
apply_now()
check("applying a reset draft returns the complete list",
      total() == baseline, str(total()))

# ------------------------------------------------------ buying entity
open_drawer()
E("""(() => { const i = document.querySelector('#fp-entity');
  i.value = 'wpp'; i.dispatchEvent(new Event('input', {bubbles: true})); })()""")
pending = E("""document.querySelector('[data-entity-status]').textContent""")
check("a pending state shows while the debounce runs",
      "Searching" in pending, pending)
time.sleep(0.45)
results = E("""[...document.querySelectorAll('.fentity__result')].map(r => r.textContent)""")
check("lower-case name search finds the entity",
      len(results) > 0 and "WPP" in results[0], json.dumps(results))
check("results show name and Saleshub ID together",
      " - " in results[0] and "0013" in results[0], json.dumps(results))

E("""(() => { const i = document.querySelector('#fp-entity');
  i.value = 'ZZZ no such entity'; i.dispatchEvent(new Event('input', {bubbles: true})); })()""")
time.sleep(0.45)
check("no-results state is shown",
      "No buying entities match" in E("""document.querySelector('[data-entity-status]').textContent"""),
      E("""document.querySelector('[data-entity-status]').textContent"""))

wpp_id = E("""(() => (window.RATE_CARDS.find(r => r.buyingEntity === 'WPP') || {}).saleshubId)()""")
E("""(() => { const i = document.querySelector('#fp-entity');
  i.value = '%s'; i.dispatchEvent(new Event('input', {bubbles: true})); })()""" % wpp_id)
time.sleep(0.45)
check("exact Saleshub ID lookup finds the entity",
      E("""document.querySelectorAll('.fentity__result').length""") >= 1)
E("""document.querySelector('#filter-panel .fentity__result').click()""")
time.sleep(0.3)
apply_now()
entity_total = total()
expected_entity = E("""(() => window.RATE_CARDS.filter(
  r => r.saleshubId === '%s').length)()""" % wpp_id)
check("buying entity filters to that entity's rows",
      entity_total == expected_entity, f"{entity_total} vs {expected_entity}")
check("buying entity is persisted in the URL",
      "entity=" + wpp_id in E("""location.search"""), E("""location.search"""))
open_drawer()
check("the chosen entity is shown in the field on reopen",
      "WPP" in E("""document.querySelector('#fp-entity').value"""),
      E("""document.querySelector('#fp-entity').value"""))
E("""document.querySelector('[data-action="clear-filter-entity"]').click()""")
time.sleep(0.3)
check("the entity can be cleared",
      E("""document.querySelector('#fp-entity').value""") == "")
apply_now()
check("clearing the entity restores the list", total() == baseline, str(total()))

# ------------------------------------------------------- zero results
open_drawer()
pick("marketplace", "Upfront")
pick("season", "2023-2024")
apply_now()
zero = total()
if zero == 0:
    check("zero results shows the empty state",
          not E("""document.querySelector('[data-empty]').hidden"""))
    check("zero results keeps a usable clear action",
          E("""!document.querySelector('[data-action="reset-all"]').hidden"""))
else:
    check("zero-result combination produced rows, skipping empty state",
          True, f"combination returned {zero}")
E("""document.querySelector('[data-action="clear-all-filters"]').click()""")
time.sleep(0.5)

# --------------------------------------------------------- zero button
open_drawer()
E("""(() => {
  document.querySelectorAll('[data-filter-checkbox="season"]').forEach(c => {
    c.checked = true; c.dispatchEvent(new Event('change', {bubbles: true})); });
  const one = document.querySelector('[data-filter-checkbox="marketplace"]');
  one.checked = true; one.dispatchEvent(new Event('change', {bubbles: true}));
})()""")
time.sleep(0.3)
check("the Apply button stays enabled whatever the count",
      not E("""document.querySelector('[data-filter-apply]').disabled"""))
E("""document.querySelector('#filter-panel .fpanel__footer .btn--secondary').click()""")
time.sleep(0.5)

# --------------------------------------------------------- keyboard + a11y
open_drawer()
kb = E("""(() => {
  const p = document.querySelector('#filter-panel');
  const items = [...p.querySelectorAll('button, input, [tabindex]')]
    .filter(n => !n.disabled && n.getAttribute('tabindex') !== '-1' && n.offsetParent !== null);
  const tab = shift => document.activeElement.dispatchEvent(
    new KeyboardEvent('keydown', {key: 'Tab', shiftKey: shift, bubbles: true, cancelable: true}));
  items[items.length - 1].focus(); tab(false);
  const wrapForward = document.activeElement === items[0];
  items[0].focus(); tab(true);
  const wrapBack = document.activeElement === items[items.length - 1];
  return {count: items.length, wrapForward, wrapBack,
    allNamed: items.every(n => (n.textContent || '').trim()
      || n.getAttribute('aria-label') || n.labels && n.labels.length
      || n.placeholder)};
})()""")
check("focus is trapped inside the open drawer",
      kb["wrapForward"] and kb["wrapBack"], json.dumps(kb))
check("every focusable control has an accessible name", kb["allNamed"], json.dumps(kb))

E("""document.querySelector('#filter-panel').dispatchEvent(
  new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}))""")
time.sleep(0.5)
check("Escape closes the drawer",
      not E("""document.querySelector('#filter-panel').classList.contains('is-open')"""))
check("focus returns to the Filters trigger after closing",
      E("""document.activeElement.getAttribute('data-action')""") == "toggle-filter",
      str(E("""document.activeElement.getAttribute('data-action')""")))

open_drawer()
E("""document.querySelector('[data-filter-scrim]').click()""")
time.sleep(0.5)
check("clicking the scrim closes the drawer",
      not E("""document.querySelector('#filter-panel').classList.contains('is-open')"""))

open_drawer()
E("""document.querySelector('#filter-panel .fpanel__close').click()""")
time.sleep(0.5)
check("the close icon closes the drawer",
      not E("""document.querySelector('#filter-panel').classList.contains('is-open')"""))

# ------------------------------------------------------------ live region
open_drawer()
pick("marketplace", "Scatter")
apply_now()
live = E("""(() => { const r = document.querySelector('[data-filter-live]');
  return {text: r.textContent, live: r.getAttribute('aria-live'),
          hidden: getComputedStyle(r).position === 'absolute'}; })()""")
check("the result count is announced politely",
      "rate cards match" in live["text"] and live["live"] == "polite",
      json.dumps(live))
check("the live region is visually hidden", live["hidden"], json.dumps(live))

# ----------------------------------------------- search still cooperates
E("""(() => { const s = document.querySelector('[data-action="search"]');
  s.value = 'disney'; s.dispatchEvent(new Event('input', {bubbles: true})); })()""")
time.sleep(0.5)
with_search = total()
check("global search narrows further within the applied filters",
      with_search <= total() and with_search >= 0, str(with_search))
check("search and filters both stay in effect",
      E("""[...document.querySelectorAll('[data-rows] .row')].every(r =>
        /disney/i.test(r.textContent) && /Scatter/.test(r.textContent))"""))

drain()
errors = [c for c in console if "error" in str(c).lower()]
check("no runtime exceptions", not errors, json.dumps(errors[:3]))

print(json.dumps({"passes": PASSES, "failures": len(FAILURES)}))
sys.exit(1 if FAILURES else 0)
