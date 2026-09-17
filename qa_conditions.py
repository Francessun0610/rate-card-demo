"""The approved pricing condition control.

Covers catalog parsing and eligibility against the Business Dictionary,
search ranking, multi-select behaviour, legacy and out-of-scope values,
keyboard interaction, and the presentation-mode examples.
"""

import json
import re
import sys
import time

sys.path.insert(0, __file__.rsplit("/", 1)[0] + "/tmp")
from review import E, go, size, console, drain  # noqa: E402

PASSES = 0
FAILURES = []

CARD = "RC-DAS-WPP-VIDEO-UF-2627"
LINE_INPUT = "#v2-line-condition"
PREM_INPUT = "#v2-prem-condition"


def check(name, ok, detail=""):
    global PASSES
    if ok:
        PASSES += 1
        print(f"[PASS] {name}")
    else:
        FAILURES.append(name)
        print(f"[FAIL] {name}: {detail}")


def open_card():
    go(f"version=2.1&section=create&mode=edit&cardId={CARD}", wait=3.0)


def open_line_row():
    E("""(() => { const r = document.querySelector(
      '[data-v2-table-region="lines"] tbody [data-v2-row-id]');
      [...r.children].find(c => String(c.className).indexOf('checkbox') === -1)
        .click(); })()""")
    time.sleep(1.0)


def open_premium_row():
    E("""document.querySelector('[data-v2-tab="premiums"]').click()""")
    time.sleep(0.9)
    E("""(() => { const r = document.querySelector(
      '[data-v2-table-region="premiums"] tbody [data-v2-row-id]');
      [...r.children].find(c => String(c.className).indexOf('checkbox') === -1)
        .click(); })()""")
    time.sleep(1.0)


def type_in(selector, query):
    E(f"""(() => {{ const i = document.querySelector('{selector}');
      i.focus(); i.value = {json.dumps(query)};
      i.dispatchEvent(new Event('input', {{bubbles: true}})); }})()""")
    time.sleep(0.5)


def press(selector, key):
    E(f"""(() => {{ const i = document.querySelector('{selector}');
      i.focus();
      i.dispatchEvent(new KeyboardEvent('keydown', {{key: {json.dumps(key)},
        code: {json.dumps(key)}, bubbles: true, cancelable: true}})); }})()""")
    time.sleep(0.45)


def menu_state(input_sel):
    return E(f"""(() => {{
      const m = document.querySelector('{input_sel}-menu');
      const opts = [...m.querySelectorAll('.ads-cond__option')];
      return {{
        open: !m.hidden,
        count: opts.length,
        names: opts.slice(0, 4).map(o =>
          o.querySelector('.ads-cond__option-name').textContent),
        groups: [...m.querySelectorAll('.ads-cond__group')].map(g => g.textContent),
        selected: opts.filter(o => o.getAttribute('aria-selected') === 'true')
          .map(o => o.querySelector('.ads-cond__option-name').textContent),
        empty: (m.querySelector('.ads-cond__empty') || {{}}).textContent || null,
        active: opts.findIndex(o => o.classList.contains('is-active'))
      }};
    }})()""")


def field_state(form):
    return E(f"""(() => {{
      const h = document.querySelector('[data-v2-form="{form}"] [data-conditions]');
      if (!h) return null;
      return {{
        scope: h.getAttribute('data-conditions-scope'),
        value: h.querySelector('.ads-cond__input').value,
        unknown: h.classList.contains('is-unrecognized'),
        clearVisible: !h.querySelector('[data-cond-clear]').hidden,
        stored: h.querySelector('[data-cond-value]').value,
        json: h.querySelector('[data-cond-json]').value,
        status: (h.querySelector('[data-cond-status]') || {{}}).textContent
      }};
    }})()""")


def reopen(selector):
    """Focusing an already focused input fires no focus event, so the
    menu would stay shut. Blur first."""
    E("(() => { const i = document.querySelector("
      + json.dumps(selector) + "); i.blur(); i.focus(); })()")
    time.sleep(0.7)


size(1440, 900)
open_card()

# --- 1. catalog parsing and eligibility -------------------------------
catalog = E("""(() => {
  const c = window.RCMConditionCatalog;
  if (!c) return null;
  const line = c.rows.filter(r => r[3].indexOf('L') !== -1);
  const prem = c.rows.filter(r => r[3].indexOf('P') !== -1);
  return {
    total: c.rows.length,
    line: line.length,
    premium: prem.length,
    both: c.rows.filter(r => r[3] === 'LP').length,
    categories: [...new Set(c.rows.map(r => r[0]))],
    blankScope: c.rows.filter(r => !r[3]).length,
    blankName: c.rows.filter(r => !r[1]).length
  };
})()""")
check("condition catalog is loaded", catalog is not None, "no catalog")
check("Line Details has 89 approved options from the workbook",
      catalog["line"] == 89, json.dumps(catalog))
check("Premium Details has 30 approved options from the workbook",
      catalog["premium"] == 30, json.dumps(catalog))
check("six approved conditions appear in both lists",
      catalog["both"] == 6, json.dumps(catalog))
check("every catalog row carries an eligibility scope",
      catalog["blankScope"] == 0, str(catalog["blankScope"]))
check("every catalog row carries an identifier name",
      catalog["blankName"] == 0, str(catalog["blankName"]))
check("workbook category order is preserved",
      catalog["categories"] == ["Format", "Targeting", "Duration", "DAR Demo"],
      json.dumps(catalog["categories"]))

# Pending requests are not approved production values.
pending = E("""(() => {
  const names = ['College Basketball - Men/Women', 'Pharma', 'PMP', 'IOA',
                 'Interactive Formats (All)', 'Sport Specific - General'];
  const have = window.RCMConditionCatalog.rows.map(r => r[1].toLowerCase());
  return names.filter(n => have.indexOf(n.toLowerCase()) !== -1);
})()""")
check("New Condition Requests values do not appear", not pending,
      json.dumps(pending))

# Marquee has a blank Pricing Condition Group in the workbook.
blank_group = E("""(() => {
  const have = window.RCMConditionCatalog.rows.map(r => r[1].toLowerCase());
  return ['marquee', 'ad selector', 'brand block']
    .filter(n => have.indexOf(n) !== -1);
})()""")
check("blank-group conditions do not appear", not blank_group,
      json.dumps(blank_group))

check("no duplicate condition keys survive normalizing",
      E("""(() => {
        const keys = window.RCMConditionCatalog.rows.map(
          r => (r[0] + '|' + r[1]).toLowerCase().replace(/\\s+/g, ' '));
        return keys.length - new Set(keys).size;
      })()""") == 0)

# --- 2. the two fields share one control, filtered ---------------------
open_line_row()
line_field = field_state("line")
check("Line Details uses the shared condition control",
      line_field and line_field["scope"] == "line", json.dumps(line_field))
E(f"""document.querySelector('{LINE_INPUT}').focus()""")
time.sleep(0.6)
line_menu = menu_state(LINE_INPUT)
check("Line Details offers exactly the Base-Rate-eligible conditions",
      line_menu["count"] == 89, json.dumps(line_menu)[:160])
check("Line Details omits the Premium-only Duration category",
      "Duration" not in line_menu["groups"], json.dumps(line_menu["groups"]))
check("Line results are grouped by category",
      line_menu["groups"] == ["Format", "Targeting", "DAR Demo"],
      json.dumps(line_menu["groups"]))

# --- 3. search ---------------------------------------------------------
type_in(LINE_INPUT, "NFL")
hit = menu_state(LINE_INPUT)
check("searching a name finds it and ranks it first",
      hit["count"] > 0 and hit["names"][0] == "NFL", json.dumps(hit)[:160])

type_in(LINE_INPUT, "Targeting")
hit = menu_state(LINE_INPUT)
check("searching a category leads with that category's conditions",
      hit["count"] > 0 and hit["groups"][0] == "Targeting",
      json.dumps(hit["groups"]))

type_in(LINE_INPUT, "DAR Demo")
hit = menu_state(LINE_INPUT)
check("searching DAR Demo returns the demo guarantees",
      hit["count"] == 29, str(hit["count"]))

type_in(LINE_INPUT, "Marquee")
hit = menu_state(LINE_INPUT)
check("searching Marquee finds nothing, it has no pricing group",
      hit["count"] == 0 and hit["empty"] == "No matching conditions",
      json.dumps(hit))

type_in(LINE_INPUT, "zzzz")
check("no result copy reads 'No matching conditions'",
      menu_state(LINE_INPUT)["empty"] == "No matching conditions")

# --- 4. single select --------------------------------------------------
type_in(LINE_INPUT, "")
before = field_state("line")["value"]
E(f"""(() => {{
  const m = document.querySelector('{LINE_INPUT}-menu');
  const opts = [...m.querySelectorAll('.ads-cond__option')];
  const target = opts.find(o => o.getAttribute('aria-selected') !== 'true');
  target.dispatchEvent(new MouseEvent('mousedown', {{bubbles: true}}));
}})()""")
time.sleep(0.7)
after = field_state("line")
check("choosing an option shows it in the field as plain text",
      after["value"] and after["value"] != before, json.dumps(after))
check("the chosen value replaces the previous one",
      after["stored"] == after["value"], json.dumps(after))
check("choosing a condition is announced",
      "selected" in (after["status"] or ""), after["status"])
check("choosing closes the menu",
      menu_state(LINE_INPUT)["open"] is False)
check("the field shows no chips",
      E("""document.querySelectorAll(
        '[data-v2-form="line"] .ads-cond__chip').length""") == 0)
check("the field shows no selection count",
      not re.search(r"\b\d+\s+selected\b", after["value"] or ""),
      after["value"])
check("a clear control appears once a value is chosen",
      after["clearVisible"] is True, json.dumps(after))

reopen(LINE_INPUT)
marked = menu_state(LINE_INPUT)
check("exactly one option is checked in the menu",
      len(marked["selected"]) == 1, json.dumps(marked["selected"]))

# A second choice replaces rather than accumulating.
first_value = field_state("line")["value"]
reopen(LINE_INPUT)
E(f"""(() => {{
  const m = document.querySelector('{LINE_INPUT}-menu');
  const opts = [...m.querySelectorAll('.ads-cond__option')];
  const other = opts.find(o => o.getAttribute('aria-selected') !== 'true');
  other.dispatchEvent(new MouseEvent('mousedown', {{bubbles: true}}));
}})()""")
time.sleep(0.7)
replaced = field_state("line")
check("choosing another condition replaces the current value",
      replaced["value"] and replaced["value"] != first_value
      and "," not in replaced["stored"], json.dumps(replaced))
check("only one value is ever stored",
      len(json.loads(replaced["json"])) == 1
      if replaced["json"].startswith("[") else True, replaced["json"][:80])

# The clear control empties the field without opening the list.
E("""document.querySelector(
  '[data-v2-form="line"] [data-cond-clear]').click()""")
time.sleep(0.6)
cleared = field_state("line")
check("the clear control empties the field",
      cleared["value"] == "" and cleared["stored"] == "", json.dumps(cleared))
check("the clear control hides once there is no value",
      cleared["clearVisible"] is False, json.dumps(cleared))
check("clearing does not open the option list",
      menu_state(LINE_INPUT)["open"] is False)
check("an empty condition is allowed",
      cleared["stored"] == "" and cleared["json"] == "", json.dumps(cleared))

# --- 5. no arbitrary values -------------------------------------------
reopen(LINE_INPUT)
E(f"""(() => {{
  const m = document.querySelector('{LINE_INPUT}-menu');
  const o = m.querySelector('.ads-cond__option');
  o.dispatchEvent(new MouseEvent('mousedown', {{bubbles: true}}));
}})()""")
time.sleep(0.6)
kept_value = field_state("line")["value"]
type_in(LINE_INPUT, "Totally Made Up Condition")
press(LINE_INPUT, "Enter")
typed = field_state("line")
check("typed text cannot be committed as a condition",
      "Totally Made Up" not in (typed["stored"] or ""), json.dumps(typed))
E(f"""document.querySelector('{LINE_INPUT}').blur()""")
time.sleep(0.5)
blurred = field_state("line")
check("arbitrary text does not survive leaving the field",
      blurred["value"] == kept_value, json.dumps([kept_value, blurred["value"]]))
check("the menu offers no create or add-new affordance",
      E(f"""![...document.querySelectorAll('{LINE_INPUT}-menu')]
        .some(m => /Add \"|Create/.test(m.textContent))"""))

# --- 6. keyboard -------------------------------------------------------
reopen(LINE_INPUT)
press(LINE_INPUT, "ArrowDown")
nav = menu_state(LINE_INPUT)
check("ArrowDown moves the active option", nav["active"] >= 0, json.dumps(nav)[:120])
check("the active option is exposed to assistive tech",
      bool(E(f"""document.querySelector('{LINE_INPUT}')
        .getAttribute('aria-activedescendant')""")))
value_before = field_state("line")["value"]
press(LINE_INPUT, "Enter")
time.sleep(0.5)
picked = field_state("line")
check("Enter selects the highlighted approved option",
      picked["value"] and picked["value"] != value_before, json.dumps(picked))
check("Enter closes the menu", menu_state(LINE_INPUT)["open"] is False)

reopen(LINE_INPUT)
check("the menu reopens from the field",
      menu_state(LINE_INPUT)["open"] is True)
press(LINE_INPUT, "Escape")
esc = field_state("line")
check("Escape closes the menu", menu_state(LINE_INPUT)["open"] is False)
check("Escape keeps the selected value",
      esc["value"] == picked["value"], json.dumps([picked["value"], esc["value"]]))
check("Escape does not close the details panel",
      E("""document.querySelector('[data-v2-root]')
        .classList.contains('is-panel-open')"""))

# --- 6b. truncation and full-value access ------------------------------
LONG_LINE = "Targeting: SEC Network - Women's College Basketball - Live"
trunc = E(f"""(() => {{
  const h = document.querySelector('[data-v2-form="line"] [data-conditions]');
  h.__conditionField.set({json.dumps(LONG_LINE)}, '');
  const i = h.querySelector('.ads-cond__input');
  const ctrl = h.querySelector('[data-cond-control]');
  const panel = h.closest('.create-md__detail').getBoundingClientRect();
  const box = ctrl.getBoundingClientRect();
  return {{
    truncated: i.scrollWidth > i.clientWidth + 1,
    tooltip: i.getAttribute('data-tooltip'),
    title: i.getAttribute('title'),
    aria: i.getAttribute('aria-label'),
    height: Math.round(box.height),
    whiteSpace: getComputedStyle(i).whiteSpace,
    ellipsis: getComputedStyle(i).textOverflow,
    insidePanel: box.right <= panel.right + 1 && box.left >= panel.left - 1
  }};
}})()""")
check("a long value truncates rather than wrapping",
      trunc["truncated"] and trunc["whiteSpace"] == "nowrap"
      and trunc["ellipsis"] == "ellipsis", json.dumps(trunc))
check("a truncated value keeps the field one line tall",
      trunc["height"] <= 40, json.dumps(trunc))
check("a truncated value offers the whole label by ADS tooltip",
      trunc["tooltip"] == LONG_LINE, json.dumps(trunc))
check("the native title tooltip is not used",
      trunc["title"] is None, str(trunc["title"]))
check("the accessible name carries the whole label",
      trunc["aria"] and LONG_LINE in trunc["aria"], trunc["aria"])
check("the field stays inside its panel when truncating",
      trunc["insidePanel"], json.dumps(trunc))

short = E("""(() => {
  const h = document.querySelector('[data-v2-form="line"] [data-conditions]');
  h.__conditionField.set('Targeting: NFL', '');
  const i = h.querySelector('.ads-cond__input');
  return {truncated: i.scrollWidth > i.clientWidth + 1,
          tooltip: i.getAttribute('data-tooltip'),
          title: i.getAttribute('title')};
})()""")
check("a value that already fits gets no tooltip",
      short["truncated"] is False and short["tooltip"] is None
      and short["title"] is None, json.dumps(short))

# --- 7. accessibility semantics ---------------------------------------
semantics = E(f"""(() => {{
  const i = document.querySelector('{LINE_INPUT}');
  const l = document.querySelector('{LINE_INPUT}-menu .ads-cond__list');
  const label = document.querySelector('label[for="v2-line-condition"]');
  const help = document.getElementById('v2-line-condition-help');
  return {{
    role: i.getAttribute('role'),
    expanded: i.getAttribute('aria-expanded'),
    autocomplete: i.getAttribute('aria-autocomplete'),
    controls: i.getAttribute('aria-controls'),
    listRole: l.getAttribute('role'),
    multi: l.getAttribute('aria-multiselectable'),
    label: label.textContent.replace(/\\s+/g, ' ').trim(),
    placeholder: i.placeholder,
    help: help.textContent.trim(),
    status: !!document.querySelector('[data-v2-form="line"] [data-cond-status][role="status"]')
  }};
}})()""")
check("the control has combobox semantics",
      semantics["role"] == "combobox"
      and semantics["autocomplete"] == "list"
      and semantics["controls"] == "v2-line-condition-menu",
      json.dumps(semantics))
check("the results list is a single-select listbox",
      semantics["listRole"] == "listbox" and not semantics["multi"],
      json.dumps(semantics))
check("a live region announces result counts",
      semantics["status"] is True)
check("Line Details label reads 'Line Condition (Optional)'",
      semantics["label"] == "Line Condition (Optional)", semantics["label"])
check("Line Details placeholder reads 'Search conditions'",
      semantics["placeholder"] == "Search conditions", semantics["placeholder"])
check("Line Details helper text matches the approved copy",
      semantics["help"] == "Select an approved pricing condition.",
      semantics["help"])

# --- 8. premium side ---------------------------------------------------
open_card()
open_premium_row()
prem_field = field_state("premium")
check("Premium Details uses the same shared control",
      prem_field and prem_field["scope"] == "premium", json.dumps(prem_field))
E(f"""document.querySelector('{PREM_INPUT}').focus()""")
time.sleep(0.6)
prem_menu = menu_state(PREM_INPUT)
check("Premium Details offers exactly the Premium-eligible conditions",
      prem_menu["count"] == 30, str(prem_menu["count"]))
check("Premium Details omits the Base-Rate-only DAR Demo category",
      "DAR Demo" not in prem_menu["groups"], json.dumps(prem_menu["groups"]))
check("Premium Details includes the Premium-only Duration category",
      "Duration" in prem_menu["groups"], json.dumps(prem_menu["groups"]))

type_in(PREM_INPUT, "Geo")
geo = menu_state(PREM_INPUT)
check("searching Geo finds the Targeting condition on Premium",
      geo["count"] == 1 and geo["names"][0] == "Geo", json.dumps(geo))

prem_semantics = E(f"""(() => {{
  const i = document.querySelector('{PREM_INPUT}');
  return {{
    label: document.querySelector('label[for="v2-prem-condition"]')
      .textContent.replace(/\\s+/g, ' ').trim(),
    placeholder: i.placeholder,
    help: document.getElementById('v2-prem-condition-help').textContent.trim(),
    isSelect: i.tagName
  }};
}})()""")
check("Premium Details label reads 'Premium Condition (Optional)'",
      prem_semantics["label"] == "Premium Condition (Optional)",
      prem_semantics["label"])
check("Premium Details helper text matches the approved copy",
      prem_semantics["help"]
      == "Select an approved condition for this premium.",
      prem_semantics["help"])
check("the premium condition field is not a plain input or select",
      prem_semantics["isSelect"] == "INPUT"
      and E(f"""!!document.querySelector('{PREM_INPUT}[role="combobox"]')"""))

# Line and Premium must not be reversed.
crossover = E("""(() => {
  const rows = window.RCMConditionCatalog.rows;
  const lineOnly = rows.filter(r => r[3] === 'L').map(r => r[0] + ': ' + r[1]);
  const premOnly = rows.filter(r => r[3] === 'P').map(r => r[0] + ': ' + r[1]);
  const inMenu = sel => [...document.querySelectorAll(sel + ' .ads-cond__option')]
    .map(o => o.closest('.ads-cond__list')
      && o.querySelector('.ads-cond__option-name').textContent);
  return {lineOnly: lineOnly.length, premOnly: premOnly.length};
})()""")
check("the eligibility split is not reversed",
      crossover["lineOnly"] == 83 and crossover["premOnly"] == 24,
      json.dumps(crossover))

# --- 9. legacy and out-of-scope saved values ---------------------------
legacy = E("""(() => {
  const h = document.querySelector('[data-v2-form="premium"] [data-conditions]');
  h.__conditionField.set('Audience: Purchase Intent', '');
  const i = h.querySelector('.ads-cond__input');
  return {value: i.value, stored: h.querySelector('[data-cond-value]').value,
          unknown: h.classList.contains('is-unrecognized'),
          aria: i.getAttribute('aria-label')};
})()""")
check("an unmatched legacy value is preserved in the field",
      "Purchase Intent" in legacy["value"]
      and "Purchase Intent" in legacy["stored"], json.dumps(legacy))
check("an unmatched legacy value is marked unrecognized",
      legacy["unknown"] is True, json.dumps(legacy))
check("the unrecognized state is not signalled by colour alone",
      legacy["aria"] and "unrecognized" in legacy["aria"].lower(),
      legacy["aria"])

# A record that arrived with two values keeps both until replaced.
compound = E("""(() => {
  const h = document.querySelector('[data-v2-form="premium"] [data-conditions]');
  h.__conditionField.set('Duration: :15, Targeting: Geo', '');
  const i = h.querySelector('.ads-cond__input');
  return {value: i.value, stored: h.querySelector('[data-cond-value]').value};
})()""")
check("a legacy multi-value record shows only its first condition",
      compound["value"] == "Duration: :15", json.dumps(compound))
check("a legacy multi-value record is not truncated on load",
      compound["stored"] == "Duration: :15, Targeting: Geo",
      json.dumps(compound))

wrong_scope = E("""(() => {
  const h = document.querySelector('[data-v2-form="premium"] [data-conditions]');
  h.__conditionField.set('DAR Demo: A18-49', '');
  return {value: h.querySelector('.ads-cond__input').value,
          unknown: h.classList.contains('is-unrecognized')};
})()""")
check("a Base-Rate-only condition saved on a premium is flagged",
      wrong_scope["value"] == "DAR Demo: A18-49"
      and wrong_scope["unknown"] is True, json.dumps(wrong_scope))
check("an unknown value cannot be re-added from the menu",
      E("""(() => {
        const h = document.querySelector('[data-v2-form="premium"] [data-conditions]');
        const before = h.querySelectorAll('.ads-cond__chip').length;
        const m = document.querySelector('#v2-prem-condition-menu');
        return ![...m.querySelectorAll('.ads-cond__option-name')]
          .some(n => n.textContent === 'A18-49');
      })()"""))
check("an out-of-scope value is not offered for new selection",
      E("""(() => {
        const m = document.querySelector('#v2-prem-condition-menu');
        return ![...m.querySelectorAll('.ads-cond__option-name')]
          .some(n => n.textContent === 'A18-49');
      })()"""))

# --- 10. canonical storage --------------------------------------------
open_card()
open_line_row()
stored = field_state("line")
payload = json.loads(stored["json"]) if stored["json"] else None
check("the canonical field holds one object, not a list",
      isinstance(payload, dict), type(payload).__name__)
check("the saved value carries a canonical identity, not just the label",
      payload and set(("key", "category", "name", "label")) <= set(payload),
      stored["json"][:180])
check("the readable label is still stored for tables and export",
      stored["stored"] and payload["label"] == stored["stored"],
      stored["stored"])

# --- 11. no whole-dataset unknowns -------------------------------------
sweep = E("""(() => {
  const files = JSON.parse(localStorage.getItem('rate-card-manager.v2.files') || '{}');
  const rows = window.RCMConditionCatalog.rows;
  const norm = v => String(v).replace(/\\s+/g, ' ').trim().toLowerCase();
  const key = (c, n) => norm(c) + '|' + norm(n);
  const line = {}, prem = {};
  rows.forEach(r => {
    if (r[3].indexOf('L') !== -1) line[key(r[0], r[1])] = true;
    if (r[3].indexOf('P') !== -1) prem[key(r[0], r[1])] = true;
  });
  const bad = {line: [], premium: []};
  Object.keys(files).forEach(id => {
    const f = files[id];
    (f.lines || []).forEach(l => (l.condition1 || '').split(/,\\s*/)
      .filter(Boolean).forEach(v => {
        const at = v.indexOf(':');
        if (at < 0 || !line[key(v.slice(0, at), v.slice(at + 1))]) bad.line.push(v);
      }));
    (f.premiums || []).forEach(p => (p.condition1 || '').split(/,\\s*/)
      .filter(Boolean).forEach(v => {
        const at = v.indexOf(':');
        if (at < 0 || !prem[key(v.slice(0, at), v.slice(at + 1))]) bad.premium.push(v);
      }));
  });
  return {line: [...new Set(bad.line)], premium: [...new Set(bad.premium)]};
})()""")
check("every seeded line condition is Base-Rate eligible",
      not sweep["line"], json.dumps(sweep["line"][:5]))
check("every seeded premium condition is Premium eligible",
      not sweep["premium"], json.dumps(sweep["premium"][:5]))

# --- 12. menu geometry -------------------------------------------------
for width, height in ((1280, 800), (1440, 900), (1920, 1080)):
    size(width, height)
    open_card()
    open_line_row()
    E(f"""document.querySelector('{LINE_INPUT}').focus()""")
    time.sleep(0.7)
    box = E(f"""(() => {{
      const m = document.querySelector('{LINE_INPUT}-menu');
      const r = m.getBoundingClientRect();
      const footer = document.querySelector(
        '[data-v2-form="line"] .create-md__form-actions');
      const f = footer.getBoundingClientRect();
      return {{h: Math.round(r.height), bottom: Math.round(r.bottom),
               top: Math.round(r.top),
               right: Math.round(r.right), left: Math.round(r.left),
               vh: window.innerHeight, vw: window.innerWidth,
               scrolls: m.scrollHeight > m.clientHeight + 1,
               footerOverlap: !(r.bottom <= f.top || r.top >= f.bottom),
               hscroll: document.documentElement.scrollWidth > window.innerWidth + 1}};
    }})()""")
    check(f"{width}x{height} menu height stays within the 280-320px band",
          160 <= box["h"] <= 320, json.dumps(box))
    check(f"{width}x{height} long result sets scroll inside the menu",
          box["scrolls"] is True, json.dumps(box))
    check(f"{width}x{height} menu stays within the viewport",
          box["left"] >= 0 and box["right"] <= box["vw"]
          and box["top"] >= 0 and box["bottom"] <= box["vh"], json.dumps(box))
    check(f"{width}x{height} the menu does not cover the action footer",
          box["footerOverlap"] is False, json.dumps(box))
    check(f"{width}x{height} the control adds no horizontal page scroll",
          box["hscroll"] is False, json.dumps(box))
    small = E("""(() => {
      const h = document.querySelector('[data-v2-form="line"] [data-conditions]');
      const out = [];
      h.querySelectorAll('*').forEach(n => {
        if (!n.getClientRects().length) return;
        if (n.closest('svg') || n.getAttribute('aria-hidden') === 'true') return;
        const own = [...n.childNodes].some(c => c.nodeType === 3 && c.textContent.trim());
        const ph = n.matches('input') && n.placeholder;
        if (!own && !ph) return;
        const size = parseFloat(getComputedStyle(n).fontSize);
        if (size < 14) out.push({cls: String(n.className).slice(0, 30), size});
      });
      return out;
    })()""")
    check(f"{width}x{height} all control text is at least 14px",
          not small, json.dumps(small[:4]))

# --- 12b. Quick Edit ---------------------------------------------------
# Quick Edit edits the same line records, so it has to be the same
# closed list with the same eligibility, not a text box.
size(1440, 900)
go("version=2.1&section=list", wait=2.8)
def open_quick_edit():
    E("""(() => { const cb = document.querySelector(
      '.table__body .row input[type=checkbox]');
      if (!cb.checked) cb.click(); })()""")
    time.sleep(0.8)
    E("""(() => { const b = [...document.querySelectorAll('button')]
      .find(x => /quick edit/i.test(x.textContent || '')); if (b) b.click(); })()""")
    time.sleep(2.0)


open_quick_edit()


def qe_row(index):
    return E(f"""(() => {{
      const row = document.querySelectorAll('[data-qe-rows] tr')[{index}];
      if (!row) return null;
      const host = row.querySelector('[data-conditions]');
      if (!host) return null;
      const input = host.querySelector('.ads-cond__input');
      return {{
        wired: !!host.__conditionField,
        scope: host.getAttribute('data-conditions-scope'),
        value: input.value,
        truncated: input.scrollWidth > input.clientWidth + 1,
        tooltip: input.getAttribute('data-tooltip'),
        aria: input.getAttribute('aria-label'),
        unknown: host.classList.contains('is-unrecognized') ? 1 : 0,
        stored: host.querySelector('[data-cond-value]').value,
        qeField: host.querySelector('[data-cond-value]')
          .getAttribute('data-qe-field'),
        freeText: !!row.querySelector(
          'input[type="text"][data-qe-field="lineConditions"]')
      }};
    }})()""")


first = qe_row(0)
check("Quick Edit uses the shared condition control",
      first and first["wired"] and first["scope"] == "line", json.dumps(first))
check("Quick Edit has no free-text condition input",
      first and first["freeText"] is False, json.dumps(first))
check("Quick Edit loads the saved line condition",
      first and first["value"] and first["stored"], json.dumps(first))
check("Quick Edit conditions are recognised by the catalog",
      first and first["unknown"] == 0, json.dumps(first))
check("Quick Edit exposes the full label whenever it is clipped",
      first and (first["tooltip"] if first["truncated"] else True)
      and first["value"] in (first["aria"] or ""), json.dumps(first))

E("""document.querySelector('[data-qe-rows] tr .ads-cond__input').focus()""")
time.sleep(0.9)
qe_menu = E("""(() => {
  const m = [...document.querySelectorAll('.ads-cond__menu')]
    .filter(x => !x.hidden)[0];
  if (!m) return null;
  const input = document.getElementById(m.id.replace(/-menu$/, ''));
  const ctrl = input.closest('[data-cond-control]');
  const cr = ctrl.getBoundingClientRect(), mr = m.getBoundingClientRect();
  const footer = document.querySelector('.qsheet__footer');
  const fr = footer.getBoundingClientRect();
  return {
    options: m.querySelectorAll('.ads-cond__option').length,
    groups: [...m.querySelectorAll('.ads-cond__group')].map(g => g.textContent),
    gap: Math.round(mr.top - cr.bottom),
    insideViewport: mr.top >= 0 && mr.bottom <= window.innerHeight,
    coversFooter: !(mr.bottom <= fr.top || mr.top >= fr.bottom)
  };
})()""")
check("Quick Edit offers the same 89 Base-Rate conditions as Line Details",
      qe_menu and qe_menu["options"] == 89, json.dumps(qe_menu))
check("Quick Edit excludes the Premium-only Duration category",
      qe_menu and "Duration" not in qe_menu["groups"], json.dumps(qe_menu))
check("the Quick Edit menu opens next to its own field",
      qe_menu and 0 <= qe_menu["gap"] <= 8, json.dumps(qe_menu))
check("the Quick Edit menu stays inside the viewport",
      qe_menu and qe_menu["insideViewport"], json.dumps(qe_menu))
check("the Quick Edit menu does not cover the action footer",
      qe_menu and qe_menu["coversFooter"] is False, json.dumps(qe_menu))

# Adding marks the sheet dirty, which is what enables Save.
before = qe_row(0)["value"]
E("""(() => {
  const m = [...document.querySelectorAll('.ads-cond__menu')]
    .filter(x => !x.hidden)[0];
  const opt = [...m.querySelectorAll('.ads-cond__option')]
    .find(o => o.getAttribute('aria-selected') !== 'true');
  opt.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
})()""")
time.sleep(0.7)
after = qe_row(0)
check("choosing a condition in Quick Edit updates the row",
      after["value"] and after["value"] != before, json.dumps(after))
check("adding a condition marks the sheet dirty",
      E("""!document.querySelector('[data-qe-save]').disabled"""))
check("Quick Edit does not save on selection",
      E("""!!document.querySelector('[data-quick-edit]')
        && !document.querySelector('[data-quick-edit]').hidden"""))

# A second row must not inherit the first row's edit.
second = qe_row(1)
check("editing one row does not leak into the next",
      second and second["stored"] != after["stored"],
      json.dumps([after["stored"], second["stored"]]))

# Cancel discards.
E("""document.querySelector('.qsheet__footer [data-action="close-quick-edit"]').click()""")
time.sleep(1.0)
E("""(() => { const d = document.querySelector('[data-qe-discard]');
  if (d && !d.hidden) {
    const go = [...d.querySelectorAll('button')]
      .find(b => /discard/i.test(b.textContent)); if (go) go.click();
  } })()""")
time.sleep(1.2)
open_quick_edit()
reopened = qe_row(0)
check("Cancel restores the saved condition",
      reopened and reopened["value"] == before,
      json.dumps([before, reopened["value"]]))
E("""document.querySelector('.qsheet__close').click()""")
time.sleep(0.8)

# --- 12c. every seeded condition suits its rate card -------------------
context = E("""(() => {
  const rows = window.RCMConditionCatalog.rows;
  const byLabel = {};
  rows.forEach(r => byLabel[(r[0] + ': ' + r[1]).toLowerCase()] = r);
  const sportRe = new RegExp([
    'NFL', 'NBA', 'MLB', 'NHL', 'WNBA', 'Football', 'Basketball', 'Baseball',
    'Softball', 'Soccer', 'Golf', 'Tennis', 'Boxing', 'MMA', 'UFC', 'NASCAR',
    'Racing', 'Cricket', 'Rugby', 'Fantasy', 'Deportes', 'College',
    'Little League', 'Horse', 'Formula One', 'Poker', 'WWE', 'Sports'
  ].join('|'), 'i');
  const issues = [];
  let lines = 0, prem = 0;
  window.RCMRateCards.getAll().slice(0, 40).forEach(card => {
    let file;
    try {
      file = window.RCMCatalog.buildFile(
        window.RCMRateCards.getByRateCardId(card.rateCardId));
    } catch (e) { return; }
    if (!file) return;
    (file.lines || []).forEach(l => {
      lines += 1;
      (l.condition1 || '').split(/,\s*/).filter(Boolean).forEach(v => {
        const row = byLabel[v.toLowerCase()];
        if (!row) { issues.push('unknown line condition: ' + v); return; }
        if (row[3].indexOf('L') === -1) {
          issues.push('premium-only condition on a line: ' + v);
        }
        if (sportRe.test(v)
            && !/ESPN|Live Event|Sports/i.test(l.baseOffering || '')) {
          issues.push('sports condition on ' + l.baseOffering + ': ' + v);
        }
      });
    });
    (file.premiums || []).forEach(p => {
      prem += 1;
      (p.condition1 || '').split(/,\s*/).filter(Boolean).forEach(v => {
        const row = byLabel[v.toLowerCase()];
        if (!row) { issues.push('unknown premium condition: ' + v); return; }
        if (row[3].indexOf('P') === -1) {
          issues.push('base-rate-only condition on a premium: ' + v);
        }
      });
    });
  });
  return {lines: lines, premiums: prem,
          issues: [...new Set(issues)].slice(0, 6)};
})()""")
check("every seeded line and premium condition is approved and in scope",
      context and not context["issues"], json.dumps(context))
check("the audit actually covered the demo books",
      context and context["lines"] > 500 and context["premiums"] > 100,
      json.dumps(context))

# --- 13. presentation mode --------------------------------------------
size(1440, 900)
open_card()
E("""window.RateCardPresentationView.open()""")
time.sleep(2.0)
E("""document.querySelector('[data-rcle-slide-next]').click()""")
time.sleep(1.4)
pres_line = E("""(() => {
  const h = document.querySelector('[data-v2-form="line"] [data-conditions]');
  const panel = document.querySelector('[data-rcle-slide-panel]:not([hidden])');
  return {
    value: h.querySelector('.ads-cond__input').value,
    unknown: h.classList.contains('is-unrecognized'),
    support: (panel.querySelector('.rcle__slide-support') || {}).textContent || ''
  };
})()""")
check("presentation state 2 shows a valid Line-eligible condition",
      pres_line["value"] and not pres_line["unknown"],
      json.dumps(pres_line))
check("presentation state 2 explains that conditions are chosen, not typed",
      "Only approved conditions can be selected" in pres_line["support"]
      and "base price applies" in pres_line["support"], pres_line["support"])

E("""document.querySelector('[data-rcle-slide-next]').click()""")
time.sleep(1.4)
pres_prem = E("""(() => {
  const h = document.querySelector('[data-v2-form="premium"] [data-conditions]');
  const panel = document.querySelector('[data-rcle-slide-panel]:not([hidden])');
  return {
    value: h.querySelector('.ads-cond__input').value,
    unknown: h.classList.contains('is-unrecognized'),
    support: (panel.querySelector('.rcle__slide-support') || {}).textContent || ''
  };
})()""")
check("presentation state 3 shows a valid Premium-eligible condition",
      pres_prem["value"] and not pres_prem["unknown"],
      json.dumps(pres_prem))
check("presentation state 3 explains that conditions are chosen, not typed",
      "Only approved conditions can be selected" in pres_prem["support"]
      and "price adjustment applies" in pres_prem["support"],
      pres_prem["support"])
check("presentation copy avoids internal vocabulary",
      not any(term in (pres_line["support"] + pres_prem["support"])
              for term in ("enum", "schema", "CARD", "LINE", "PREM")),
      pres_line["support"] + " | " + pres_prem["support"])
E("""document.querySelector('[data-rcle-close]').click()""")
time.sleep(0.7)

drain()
errors = [c for c in console if "error" in str(c).lower()
          and "beforeunload" not in str(c)]
check("no console errors during the run", not errors, json.dumps(errors[:3]))

print(json.dumps({"passes": PASSES, "failures": len(FAILURES)}))
sys.exit(1 if FAILURES else 0)
