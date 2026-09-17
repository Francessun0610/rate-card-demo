"""Manually entered Rate Card ID.

Covers the field itself in Add and Edit, trim / required / character /
case-insensitive uniqueness validation, when errors are allowed to
appear, submit gating, the confirmation dialog on an ID change, value
preservation after an unrelated error, keyboard and label wiring, and
that a changed ID re-keys the stored rate card file so imports still
match.
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


MODAL = "[data-rc-create-modal]"
ID_INPUT = "[data-rcm-card-id]"


def open_create():
    go("version=2.1&section=list", wait=2.4)
    E("""document.querySelector('[data-action="create"]').click()""")
    time.sleep(0.7)


def set_id(value, blur=True):
    E("""(() => { const i = document.querySelector('%s');
      i.value = %s; i.dispatchEvent(new Event('input', {bubbles: true}));
      %s })()""" % (ID_INPUT, json.dumps(value),
                    "i.dispatchEvent(new FocusEvent('blur'));" if blur else ""))
    time.sleep(0.2)


def set_name(value):
    E("""(() => { const i = document.querySelector('#rcm-name');
      i.value = %s; i.dispatchEvent(new Event('input', {bubbles: true})); })()"""
      % json.dumps(value))
    time.sleep(0.2)


def id_state():
    return E("""(() => {
      const m = document.querySelector('%s');
      const f = m.querySelector('[data-rcm-id-field]');
      const i = m.querySelector('%s');
      return {
        value: i.value,
        error: f.querySelector('.field__error').textContent,
        errorHidden: f.querySelector('.field__error').hidden,
        invalid: i.getAttribute('aria-invalid'),
        describedBy: i.getAttribute('aria-describedby'),
        confirmDisabled: m.querySelector('[data-action="confirm-rc-create"]').disabled
      };
    })()""" % (MODAL, ID_INPUT))


size(1440, 900)

# ------------------------------------------------------- field in Add
open_create()
field = E("""(() => {
  const m = document.querySelector('%s');
  const i = m.querySelector('%s');
  const label = m.querySelector('label[for="rcm-card-id"]');
  const helper = m.querySelector('[data-rcm-id-helper]');
  const name = m.querySelector('#rcm-name');
  const order = [...m.querySelectorAll('.modal__body > .field')]
    .map(f => (f.querySelector('label') || {}).textContent.trim());
  return {
    order,
    label: label.textContent.trim(),
    labelFor: label.getAttribute('for'),
    inputId: i.id,
    placeholder: i.placeholder,
    required: i.required,
    ariaRequired: i.getAttribute('aria-required'),
    helper: helper.textContent.trim(),
    helperId: helper.id,
    describedBy: i.getAttribute('aria-describedby'),
    prefilled: i.value,
    classesMatchOtherFields: i.className === name.className,
    tabbable: i.tabIndex >= 0
  };
})()""" % (MODAL, ID_INPUT))

check("Rate Card ID sits above Rate Card Name",
      field["order"][:2] == ["Rate Card ID", "Rate Card Name"], json.dumps(field["order"]))
check("label, placeholder and helper text match the spec",
      field["label"] == "Rate Card ID"
      and field["placeholder"] == "Enter rate card ID"
      and field["helper"] == "Enter the unique ID used to identify this rate card "
                             "and match future updates.", json.dumps(field))
check("field is marked required the standard way",
      field["required"] and field["ariaRequired"] == "true", json.dumps(field))
check("nothing is prepopulated or generated in Add",
      field["prefilled"] == "", repr(field["prefilled"]))
check("label and helper are associated with the input",
      field["labelFor"] == field["inputId"]
      and field["helperId"] in (field["describedBy"] or ""), json.dumps(field))
check("uses the same ADS input styling as the other modal fields",
      field["classesMatchOtherFields"], field["classesMatchOtherFields"])
check("input is keyboard reachable", field["tabbable"])

# ------------------------------------------ errors only after interaction
set_id("", blur=False)
early = id_state()
check("no error before the user has interacted with the field",
      early["errorHidden"], json.dumps(early))
check("Confirm is disabled while the ID is missing", early["confirmDisabled"])

# ------------------------------------------------------------ validation
cases = [
    ("", "Enter a rate card ID."),
    ("   ", "Enter a rate card ID."),
    ("has space", "Use only letters, numbers, hyphens, and underscores."),
    ("bad!chars", "Use only letters, numbers, hyphens, and underscores."),
    ("dots.not.allowed", "Use only letters, numbers, hyphens, and underscores."),
    ("RC-DAS-WPP-VIDEO-UF-2627", "This rate card ID is already in use."),
    ("rc-das-wpp-video-uf-2627", "This rate card ID is already in use."),
    ("Rc-DaS-WpP-ViDeO-uF-2627", "This rate card ID is already in use."),
    ("RC_NEW-001", ""),
    ("abc123", ""),
]
for value, expected in cases:
    set_id(value)
    state = id_state()
    label = "accepts" if expected == "" else "rejects"
    check(f"{label} {value!r}", state["error"] == expected,
          f"got {state['error']!r}, expected {expected!r}")

set_id("  RC_TRIM-001  ")
trimmed = id_state()
check("leading and trailing spaces are trimmed",
      trimmed["value"] == "RC_TRIM-001", repr(trimmed["value"]))

set_id("bad!chars")
aria = id_state()
check("an inline error sets aria-invalid and is announced",
      aria["invalid"] == "true"
      and "rcm-card-id-error" in (aria["describedBy"] or "")
      and E("""document.querySelector('#rcm-card-id-error')
        .getAttribute('role')""") == "alert", json.dumps(aria))
check("the helper stays associated while an error shows",
      "rcm-card-id-help" in (aria["describedBy"] or ""), aria["describedBy"])

# ---------------------------------------------- submit gating and focus
set_id("", blur=False)
set_name("Focus Probe Rate Card")
gated = id_state()
check("Confirm stays disabled while the ID is invalid", gated["confirmDisabled"])

E("""(() => { const c = document.querySelector(
  '[data-action="confirm-rc-create"]'); c.disabled = false; c.click(); })()""")
time.sleep(0.4)
check("a submit attempt with a bad ID shows the error",
      id_state()["error"] == "Enter a rate card ID.", id_state()["error"])
check("a failed submit moves focus to the Rate Card ID field",
      E("""document.activeElement.id""") == "rcm-card-id",
      E("""document.activeElement.id"""))
check("nothing was created by the blocked submit",
      E("""window.RATE_CARDS.some(r => r.name === 'Focus Probe Rate Card')""") is False)

# ------------------------------------- value survives an unrelated error
set_id("RC_KEEP-001")
set_name("")
E("""(() => { const c = document.querySelector(
  '[data-action="confirm-rc-create"]'); c.disabled = false; c.click(); })()""")
time.sleep(0.4)
kept = E("""(() => {
  const m = document.querySelector('%s');
  return {id: m.querySelector('%s').value,
          nameError: m.querySelector('#rcm-name').closest('.field')
            .querySelector('.field__error').textContent};
})()""" % (MODAL, ID_INPUT))
check("the entered ID survives a validation error on another field",
      kept["id"] == "RC_KEEP-001" and kept["nameError"] == "Enter a rate card name.",
      json.dumps(kept))

# ------------------------------------------------------------- creating
set_name("Manual ID Rate Card")
time.sleep(0.2)
check("Confirm enables once the ID and name are both valid",
      not id_state()["confirmDisabled"], json.dumps(id_state()))
E("""document.querySelector('[data-action="confirm-rc-create"]').click()""")
time.sleep(1.6)
created = E("""(() => {
  const row = window.RATE_CARDS.find(r => r.name === 'Manual ID Rate Card');
  return row ? {rateCardId: row.rateCardId, status: row.status} : null;
})()""")
check("the rate card is created with exactly the ID that was typed",
      created and created["rateCardId"] == "RC_KEEP-001", json.dumps(created))
check("the typed ID is not replaced by a generated one",
      created and not created["rateCardId"].startswith("RC-DAS-"),
      json.dumps(created))

# -------------------------------------------------------------- editing
go("version=2.1&section=create&mode=edit&cardId=RC_KEEP-001", wait=2.6)
E("""document.querySelector('[data-v2-action="edit-card-details"]').click()""")
time.sleep(0.8)
edit = E("""(() => {
  const m = document.querySelector('%s');
  const i = m.querySelector('%s');
  const helper = m.querySelector('[data-rcm-id-helper]');
  const order = [...m.querySelectorAll('.modal__body > .field')]
    .map(f => (f.querySelector('label') || {}).textContent.trim());
  return {title: m.querySelector('#rcm-create-title').textContent.trim(),
          value: i.value, readOnly: i.readOnly, disabled: i.disabled,
          helper: helper.textContent.trim(), order: order.slice(0, 2)};
})()""" % (MODAL, ID_INPUT))
check("Edit prepopulates the existing Rate Card ID in an editable input",
      edit["value"] == "RC_KEEP-001" and not edit["readOnly"] and not edit["disabled"],
      json.dumps(edit))
check("Edit shows its own helper text",
      edit["helper"] == "This ID is used to match imports and updates to this rate card.",
      edit["helper"])
check("Edit keeps the ID above the name",
      edit["order"] == ["Rate Card ID", "Rate Card Name"], json.dumps(edit["order"]))

# ------------------------- no confirmation when the ID is left unchanged
set_name("Manual ID Rate Card Renamed")
E("""document.querySelector('[data-action="confirm-rc-create"]').click()""")
time.sleep(0.7)
check("changing another field with the ID untouched shows no dialog",
      E("""document.querySelector('[data-ads-confirm]').hidden""") is True)
check("that edit saved",
      E("""!!window.RATE_CARDS.find(r => r.rateCardId === 'RC_KEEP-001'
        && r.name === 'Manual ID Rate Card Renamed')"""))

# ---------------------------------------- confirmation on an ID change
E("""document.querySelector('[data-v2-action="edit-card-details"]').click()""")
time.sleep(0.7)
set_id("RC_KEEP-002")
E("""document.querySelector('[data-action="confirm-rc-create"]').click()""")
time.sleep(0.6)
dialog = E("""(() => {
  const d = document.querySelector('[data-ads-confirm]');
  if (d.hidden) return {shown: false};
  const buttons = [...d.querySelectorAll('.modal__footer button')]
    .map(b => b.textContent.trim());
  return {shown: true,
          title: d.querySelector('.modal__title').textContent.trim(),
          body: d.querySelector('.modal__body').textContent.trim(),
          buttons};
})()""")
check("changing the ID raises the confirmation dialog", dialog.get("shown"), json.dumps(dialog))
check("dialog title matches the spec",
      dialog.get("title") == "Change rate card ID?", json.dumps(dialog))
check("dialog body matches the spec",
      dialog.get("body") == "This ID is used to match imports and updates. Changing it "
                            "may prevent files using the previous ID from matching this "
                            "rate card.", json.dumps(dialog))
check("dialog offers Cancel and Change ID",
      dialog.get("buttons") == ["Cancel", "Change ID"], json.dumps(dialog))

# Cancel leaves the ID alone.
E("""[...document.querySelectorAll('[data-ads-confirm] .modal__footer button')]
  .find(b => b.textContent.trim() === 'Cancel').click()""")
time.sleep(0.6)
check("cancelling the dialog leaves the saved ID unchanged",
      E("""!!window.RATE_CARDS.find(r => r.rateCardId === 'RC_KEEP-001')"""))

# Confirm actually renames.
E("""document.querySelector('[data-action="confirm-rc-create"]').click()""")
time.sleep(0.6)
E("""[...document.querySelectorAll('[data-ads-confirm] .modal__footer button')]
  .find(b => b.textContent.trim() === 'Change ID').click()""")
time.sleep(1.0)
renamed = E("""(() => {
  const files = JSON.parse(localStorage.getItem('rate-card-manager.v2.files') || '{}');
  return {
    listHasNew: !!window.RATE_CARDS.find(r => r.rateCardId === 'RC_KEEP-002'),
    listHasOld: !!window.RATE_CARDS.find(r => r.rateCardId === 'RC_KEEP-001'),
    fileUnderNewKey: !!files['RC_KEEP-002'],
    fileUnderOldKey: !!files['RC_KEEP-001'],
    cardIdInFile: files['RC_KEEP-002'] && files['RC_KEEP-002'].card.id,
    urlCardId: new URLSearchParams(location.search).get('cardId')
  };
})()""")
check("confirming the change updates the list row's ID",
      renamed["listHasNew"] and not renamed["listHasOld"], json.dumps(renamed))
check("the stored rate card file is re-keyed so imports still match",
      renamed["fileUnderNewKey"] and not renamed["fileUnderOldKey"]
      and renamed["cardIdInFile"] == "RC_KEEP-002", json.dumps(renamed))
check("the deep link follows the new ID",
      renamed["urlCardId"] == "RC_KEEP-002", json.dumps(renamed))

# ------------------------------- editing a card keeps its own ID valid
E("""document.querySelector('[data-v2-action="edit-card-details"]').click()""")
time.sleep(0.7)
set_id("RC_KEEP-002")
own = id_state()
check("a card's own ID is not reported as a duplicate of itself",
      own["error"] == "" and not own["confirmDisabled"], json.dumps(own))
set_id("RC-DAS-WPP-VIDEO-UF-2627")
check("another card's ID is still rejected while editing",
      id_state()["error"] == "This rate card ID is already in use.",
      id_state()["error"])

drain()
errors = [c for c in console if "error" in str(c).lower()]
check("no runtime exceptions", not errors, json.dumps(errors[:3]))

print(json.dumps({"passes": PASSES, "failures": len(FAILURES)}))
sys.exit(1 if FAILURES else 0)
