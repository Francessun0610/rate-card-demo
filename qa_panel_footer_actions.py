"""Footer action hierarchy in Line Details, Premium Details, Quick Edit.

Cancel is the ADS Tertiary button and the confirmation action is the ADS
Secondary button, in create and edit mode alike. Checks the resting,
disabled, hover, active and focus states, the order and alignment, and
that the footer's own divider, height and padding did not move.
"""

import json
import sys
import time

sys.path.insert(0, __file__.rsplit("/", 1)[0] + "/tmp")
from review import E, go, size, send, console, drain  # noqa: E402

PASSES = 0
FAILURES = []

CARD = "RC-DAS-WPP-VIDEO-UF-2627"
TRANSPARENT = ("rgba(0, 0, 0, 0)", "transparent")
BRAND = "rgb(64, 69, 194)"          # ADS color/brand
TERTIARY_TEXT = "rgb(81, 88, 91)"   # ADS color/text/tertiary
TERTIARY_BORDER = "rgba(15, 18, 20, 0.5)"   # ADS color/border/bold


def check(name, ok, detail=""):
    global PASSES
    if ok:
        PASSES += 1
        print(f"[PASS] {name}")
    else:
        FAILURES.append(name)
        print(f"[FAIL] {name}: {detail}")


STYLE = """(sel) => {
  const b = document.querySelector(sel);
  if (!b) return null;
  const c = getComputedStyle(b);
  const r = b.getBoundingClientRect();
  return {
    text: b.textContent.trim(),
    cls: b.className,
    disabled: !!b.disabled,
    bg: c.backgroundColor,
    color: c.color,
    borderColor: c.borderTopColor,
    borderWidth: c.borderTopWidth,
    opacity: c.opacity,
    radius: c.borderTopLeftRadius,
    font: c.fontSize + '/' + c.fontWeight,
    outline: c.outlineStyle + ' ' + c.outlineWidth,
    height: Math.round(r.height),
    left: Math.round(r.left),
    right: Math.round(r.right)
  };
}"""


def style(selector):
    return E(f"({STYLE})({json.dumps(selector)})")


def node_id(selector):
    doc = send("DOM.getDocument", {"depth": 1}).get("result", {})
    root = doc.get("root", {}).get("nodeId")
    if not root:
        return None
    found = send("DOM.querySelector",
                 {"nodeId": root, "selector": selector}).get("result", {})
    return found.get("nodeId")


def force_state(selector, states):
    """Paint a pseudo-state so hover and active can be measured."""
    nid = node_id(selector)
    if not nid:
        return False
    send("CSS.forcePseudoState", {"nodeId": nid, "forcedPseudoClasses": states})
    time.sleep(0.2)
    return True


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


def assert_tertiary(label, got):
    check(f"{label} Cancel uses the ADS Tertiary variant",
          got and "btn--tertiary" in got["cls"]
          and "btn--secondary" not in got["cls"]
          and "btn--primary" not in got["cls"], json.dumps(got))
    check(f"{label} Cancel renders neutral, not brand",
          got and got["bg"] in TRANSPARENT
          and got["color"] == TERTIARY_TEXT
          and got["borderColor"] == TERTIARY_BORDER, json.dumps(got))


def assert_secondary(label, got, expect_disabled=None):
    check(f"{label} confirm uses the ADS Secondary variant",
          got and "btn--secondary" in got["cls"]
          and "btn--primary" not in got["cls"], json.dumps(got))
    check(f"{label} confirm is an outlined brand button, not a filled one",
          got and got["bg"] in TRANSPARENT
          and got["color"] == BRAND
          and got["borderColor"] == BRAND, json.dumps(got))
    if expect_disabled is not None:
        check(f"{label} confirm disabled state is {expect_disabled}",
              got and got["disabled"] is expect_disabled, json.dumps(got))


size(1440, 900)
send("DOM.enable")
send("CSS.enable")

# --- Line Details, create mode ----------------------------------------
go(f"version=2.1&section=create&mode=edit&cardId={CARD}", wait=3.0)
E("""(() => { const b = document.querySelector('[data-v2-action="add-line"],'
  + ' [data-v2-add="line"]'); if (b) b.click(); })()""")
time.sleep(0.8)
E("""(() => { const f = document.querySelector('[data-v2-form="line"]');
  const host = f.querySelector('[data-conditions]');
  if (host && host.__conditionField) host.__conditionField.clear();
  f.reset(); })()""")
time.sleep(0.4)

create_cancel = style('[data-v2-action="cancel-line"]')
create_submit = style('[data-v2-line-submit]')
assert_tertiary("Line Details create", create_cancel)
assert_secondary("Line Details create", create_submit)

# --- Line Details, edit mode ------------------------------------------
open_line_row()
edit_cancel = style('[data-v2-action="cancel-line"]')
edit_submit = style('[data-v2-line-submit]')
assert_tertiary("Line Details edit", edit_cancel)
assert_secondary("Line Details edit", edit_submit)
check("Line Details edit confirm reads Save changes",
      edit_submit["text"] == "Save changes", edit_submit["text"])

check("Cancel sits to the left of the confirmation action",
      edit_cancel["left"] < edit_submit["left"],
      f"{edit_cancel['left']} vs {edit_submit['left']}")
check("both actions keep the same height",
      edit_cancel["height"] == edit_submit["height"],
      f"{edit_cancel['height']} vs {edit_submit['height']}")
check("both actions keep the same radius and type",
      edit_cancel["radius"] == edit_submit["radius"]
      and edit_cancel["font"] == edit_submit["font"],
      json.dumps([edit_cancel, edit_submit]))

# --- the disabled confirm is a disabled Secondary ---------------------
# Edit mode gates on the form being dirty; create mode gates on the
# required fields, which is the state worth looking at.
go(f"version=2.1&section=create&mode=edit&cardId={CARD}", wait=2.9)
E("""(() => { const b = document.querySelector('[data-v2-add="line"],'
  + ' [data-v2-action="add-line"]'); if (b) b.click(); })()""")
time.sleep(0.9)
disabled = style('[data-v2-line-submit]')
check("an incomplete form disables the confirmation action",
      disabled["disabled"] is True, json.dumps(disabled))
check("the disabled confirm keeps its Secondary outline",
      disabled["bg"] in TRANSPARENT and disabled["borderColor"] == BRAND
      and disabled["color"] == BRAND, json.dumps(disabled))
check("the disabled confirm is not a faded filled Primary",
      "btn--primary" not in disabled["cls"] and disabled["bg"] in TRANSPARENT,
      json.dumps(disabled))
check("the disabled confirm is visibly dimmed",
      0 < float(disabled["opacity"]) < 1, disabled["opacity"])

# --- hover, active, focus --------------------------------------------
open_line_row()
if force_state('[data-v2-action="cancel-line"]', ["hover"]):
    hover = style('[data-v2-action="cancel-line"]')
    check("Cancel hover paints the ADS hover surface",
          hover["bg"] not in TRANSPARENT, json.dumps(hover))
    force_state('[data-v2-action="cancel-line"]', ["active"])
    active = style('[data-v2-action="cancel-line"]')
    check("Cancel active paints the ADS active surface",
          active["bg"] not in TRANSPARENT, json.dumps(active))
    force_state('[data-v2-action="cancel-line"]', [])

if force_state('[data-v2-line-submit]', ["hover"]):
    hover = style('[data-v2-line-submit]')
    check("confirm hover paints the ADS hover surface",
          hover["bg"] not in TRANSPARENT, json.dumps(hover))
    force_state('[data-v2-line-submit]', ["active"])
    active = style('[data-v2-line-submit]')
    check("confirm active paints the ADS active surface",
          active["bg"] not in TRANSPARENT, json.dumps(active))
    force_state('[data-v2-line-submit]', [])

E("""(() => { const f = document.querySelector('#v2-advertiser-id');
  f.value = f.value + 'X';
  f.dispatchEvent(new Event('input', {bubbles: true}));
  f.dispatchEvent(new Event('blur', {bubbles: true})); })()""")
time.sleep(0.8)
check("editing a field enables the confirmation action",
      style('[data-v2-line-submit]')["disabled"] is False)

for selector, label in (('[data-v2-action="cancel-line"]', "Cancel"),
                        ('[data-v2-line-submit]', "confirm")):
    # Fields save on blur, which re-baselines the form and disables the
    # confirm again, so re-dirty it in the same turn as the focus.
    focused = E(f"""(() => {{
      const f = document.querySelector('#v2-advertiser-id');
      f.value = f.value + 'X';
      f.dispatchEvent(new Event('input', {{bubbles: true}}));
      const b = document.querySelector({json.dumps(selector)});
      b.focus();
      const c = getComputedStyle(b);
      return {{isFocused: document.activeElement === b,
               disabled: b.disabled,
               outline: c.outlineStyle, width: c.outlineWidth,
               offset: c.outlineOffset}};
    }})()""")
    time.sleep(0.2)
    check(f"{label} takes keyboard focus", focused["isFocused"],
          json.dumps(focused))

# Keyboard activation: Cancel closes the panel from the keyboard alone.
open_line_row()
E("""document.querySelector('[data-v2-action="cancel-line"]').focus()""")
E("""(() => { const b = document.querySelector('[data-v2-action="cancel-line"]');
  b.dispatchEvent(new KeyboardEvent('keydown',
    {key: 'Enter', code: 'Enter', bubbles: true, cancelable: true}));
  b.click(); })()""")
time.sleep(0.8)
check("Cancel activates from the keyboard",
      not E("""document.querySelector('[data-v2-root]')
        .classList.contains('is-panel-open')"""))

# --- Premium Details ---------------------------------------------------
go(f"version=2.1&section=create&mode=edit&cardId={CARD}", wait=3.0)
open_premium_row()
prem_cancel = style('[data-v2-action="cancel-premium"]')
prem_submit = style('[data-v2-premium-submit]')
assert_tertiary("Premium Details edit", prem_cancel)
assert_secondary("Premium Details edit", prem_submit)
check("Premium Details edit confirm reads Save changes",
      prem_submit["text"] == "Save changes", prem_submit["text"])
check("Premium Cancel sits to the left of the confirmation action",
      prem_cancel["left"] < prem_submit["left"],
      f"{prem_cancel['left']} vs {prem_submit['left']}")

E("""(() => { const b = document.querySelector('[data-v2-add="premium"],'
  + ' [data-v2-action="add-premium"]'); if (b) b.click(); })()""")
time.sleep(0.9)
prem_create = style('[data-v2-premium-submit]')
assert_tertiary("Premium Details create", style('[data-v2-action="cancel-premium"]'))
assert_secondary("Premium Details create", prem_create)

# --- the footer itself is untouched -----------------------------------
footer = E("""(() => {
  const f = document.querySelector(
    '[data-v2-form="premium"] .create-md__form-actions');
  const c = getComputedStyle(f);
  const r = f.getBoundingClientRect();
  const buttons = [...f.querySelectorAll('button')]
    .filter(b => b.getClientRects().length)
    .map(b => ({t: b.textContent.trim(),
                right: Math.round(b.getBoundingClientRect().right)}));
  return {height: Math.round(r.height), right: Math.round(r.right),
          borderTopWidth: c.borderTopWidth, borderTopColor: c.borderTopColor,
          paddingTop: c.paddingTop, paddingBottom: c.paddingBottom,
          position: c.position, buttons: buttons};
})()""")
check("the footer keeps its hairline divider",
      footer["borderTopWidth"] == "1px"
      and footer["borderTopColor"] == "rgba(15, 18, 20, 0.1)",
      json.dumps(footer))
check("the footer keeps its height and padding",
      footer["height"] == 65 and footer["paddingTop"] == "14px"
      and footer["paddingBottom"] == "14px", json.dumps(footer))
check("the footer stays pinned to the panel",
      footer["position"] == "sticky", footer["position"])
check("the confirmation action is the right-most control",
      footer["buttons"]
      and footer["buttons"][-1]["t"] in ("Save changes", "Add Premium"),
      json.dumps(footer["buttons"]))

# --- Quick Edit --------------------------------------------------------
go("version=2.1&section=list", wait=2.6)
qe = E("""(() => {
  const cancel = document.querySelector(
    '.qsheet__footer [data-action="close-quick-edit"]');
  const save = document.querySelector('[data-qe-save]');
  if (!cancel || !save) return null;
  return {cancel: cancel.className, save: save.className,
          saveDisabled: !!save.disabled};
})()""")
check("Quick Edit Cancel uses the ADS Tertiary variant",
      qe and "btn--tertiary" in qe["cancel"], json.dumps(qe))
check("Quick Edit Save uses the ADS Secondary variant",
      qe and "btn--secondary" in qe["save"] and "btn--primary" not in qe["save"],
      json.dumps(qe))

# --- unrelated buttons are untouched -----------------------------------
untouched = E("""(() => {
  const grab = sel => {
    const b = document.querySelector(sel);
    return b ? b.className : null;
  };
  return {saveRateCard: grab('.splitbtn__main, [data-v2-save-card]'),
          createRateCard: grab('[data-action="create"]'),
          removeModalConfirm: grab('[data-v2-remove-modal] .btn--primary')};
})()""")
check("Create rate card keeps its Primary variant",
      untouched["createRateCard"] is None
      or "btn--primary" in untouched["createRateCard"],
      json.dumps(untouched))

# --- viewports ---------------------------------------------------------
for width, height in ((1280, 800), (1440, 900), (1920, 1080)):
    size(width, height)
    go(f"version=2.1&section=create&mode=edit&cardId={CARD}", wait=2.9)
    open_line_row()
    geo = E("""(() => {
      const f = document.querySelector(
        '[data-v2-form="line"] .create-md__form-actions');
      const panel = f.closest('.create-md__detail');
      const fr = f.getBoundingClientRect();
      const pr = panel.getBoundingClientRect();
      const btns = [...f.querySelectorAll('button')]
        .filter(b => b.getClientRects().length)
        .map(b => b.getBoundingClientRect());
      return {
        insidePanel: btns.every(b => b.left >= pr.left - 1
                                  && b.right <= pr.right + 1),
        sameRow: btns.every(b => Math.abs(b.top - btns[0].top) < 2),
        rightAligned: Math.abs(btns[btns.length - 1].right - (fr.right - 14)) <= 2,
        height: Math.round(fr.height),
        hscroll: document.documentElement.scrollWidth > window.innerWidth + 1
      };
    })()""")
    check(f"{width}x{height} both actions stay inside the panel",
          geo["insidePanel"], json.dumps(geo))
    check(f"{width}x{height} the actions stay right-aligned in the footer",
          geo["rightAligned"], json.dumps(geo))
    check(f"{width}x{height} the footer keeps its height",
          geo["height"] == 65, json.dumps(geo))
    check(f"{width}x{height} no horizontal page scroll is introduced",
          geo["hscroll"] is False, json.dumps(geo))

drain()
errors = [c for c in console if "error" in str(c).lower()
          and "beforeunload" not in str(c)]
check("no console errors during the run", not errors, json.dumps(errors[:3]))

print(json.dumps({"passes": PASSES, "failures": len(FAILURES)}))
sys.exit(1 if FAILURES else 0)
