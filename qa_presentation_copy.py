"""Presentation narration says the approved copy and nothing internal.

Covers the three detail states and the list story: exact title, subtitle,
heading, explanation and three supporting facts; no CARD / LINE / PREM
terminology in anything the audience reads; the required live product
state for each slide.
"""

import json
import sys
import time

sys.path.insert(0, __file__.rsplit("/", 1)[0] + "/tmp")
from review import E, go, size  # noqa: E402

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


SLIDES = {
    1: {
        "title": "Edit Rate Card",
        "subtitle": "Update the details shared across the entire rate card.",
        "heading": "Who is this rate card for?",
        "explanation": "Shared details identify the buyer, market, and dates "
                       "for every price.",
        "facts": [("Buyer", "Who negotiated it"),
                  ("Market", "Where it applies"),
                  ("Timing", "When it applies")],
    },
    2: {
        "title": "Base Rate Details",
        "subtitle": "View existing base rates, or add and edit one price.",
        "heading": "What are we selling?",
        "explanation": "Each item connects a sellable product to its "
                       "negotiated base rate.",
        "facts": [("Advertiser", "Who the price is for"),
                  ("Product", "What is being sold"),
                  ("Price", "How it is charged")],
    },
    3: {
        "title": "Price Adjustments",
        "subtitle": "View existing adjustments, or add and edit one rule.",
        "heading": "What changes the base rate?",
        "explanation": "An adjustment changes the price only when its "
                       "condition applies.",
        "facts": [("Condition", "When it applies"),
                  ("Method", "How it changes"),
                  ("Value", "How much it changes")],
    },
}

# Row-type vocabulary and the retired slide names. A reader should not
# need the CSV model to follow the story.
BANNED = ["CARD sets", "Each LINE", "A PREM", "Rate Card Details",
          "Line Item Details", "Premium Adjustments"]

size(1440, 900)
go("version=2.1&section=create&mode=edit&cardId=RC-DAS-WPP-VIDEO-UF-2627",
   wait=2.9)
E("""window.RateCardPresentationView.open()""")
time.sleep(2.0)

for index, want in SLIDES.items():
    if index > 1:
        E("""document.querySelector('[data-rcle-slide-next]').click()""")
        time.sleep(1.4)

    got = E("""(() => {
      const o = document.querySelector('[data-rcle]');
      const panel = o.querySelector('[data-rcle-slide-panel]:not([hidden])');
      const norm = n => n ? n.textContent.replace(/\\s+/g, ' ').trim() : null;
      return {
        title: norm(o.querySelector('.rcle__title')),
        subtitle: norm(o.querySelector('.rcle__subtitle')),
        heading: norm(panel.querySelector('.rcle__slide-heading')),
        explanation: norm(panel.querySelector('.rcle__slide-copy')),
        facts: [...panel.querySelectorAll('.rcle__fact')].map(f => [
          norm(f.querySelector('dt')),
          norm(f.querySelector('dd'))]),
        narration: norm(o.querySelector('.rcle__header'))
                   + ' ' + norm(panel)
      };
    })()""")

    for field in ("title", "subtitle", "heading", "explanation"):
        check(f"slide {index} {field}", got[field] == want[field],
              f"want {want[field]!r} got {got[field]!r}")

    check(f"slide {index} has exactly three supporting facts",
          len(got["facts"]) == 3, json.dumps(got["facts"]))
    for i, (term, desc) in enumerate(want["facts"]):
        actual = got["facts"][i] if i < len(got["facts"]) else [None, None]
        check(f"slide {index} fact {i + 1} is {term}",
              actual[0] == term and actual[1] == desc,
              json.dumps(actual))

    leaked = [t for t in BANNED if t in got["narration"]]
    check(f"slide {index} narration avoids row-type terminology",
          not leaked, json.dumps(leaked))

    # Required live product state per slide.
    state = E("""(() => {
      const modal = document.querySelector('[data-rc-create-modal]');
      const root = document.querySelector('[data-v2-root]');
      const panelOpen = root.classList.contains('is-panel-open');
      const form = root.querySelector('[data-v2-form="line"], '
        + '[data-v2-form="premium"]');
      const filled = form ? [...form.querySelectorAll('input')]
        .filter(i => i.type !== 'checkbox' && i.value.trim()).length : 0;
      const selected = !!root.querySelector('tbody [data-v2-row-id].is-selected');
      return {
        modalOpen: !!(modal && !modal.hidden
          && modal.getBoundingClientRect().height > 0),
        panelOpen, filled, selected,
        tab: (root.querySelector('[data-v2-tab][aria-selected="true"]')
              || {}).getAttribute
          ? root.querySelector('[data-v2-tab][aria-selected="true"]')
              .getAttribute('data-v2-tab') : null
      };
    })()""")

    if index == 1:
        check("slide 1 shows the real Edit rate card modal open",
              state["modalOpen"], json.dumps(state))
        check("slide 1 has no details panel open behind the modal",
              not state["panelOpen"], json.dumps(state))
    else:
        check(f"slide {index} has no modal covering the product",
              not state["modalOpen"], json.dumps(state))
        check(f"slide {index} opens the details panel",
              state["panelOpen"], json.dumps(state))
        check(f"slide {index} panel holds a saved record, not a blank form",
              state["filled"] >= 3, json.dumps(state))
        check(f"slide {index} highlights the row the panel came from",
              state["selected"], json.dumps(state))

    if index == 2:
        check("slide 2 is on the Line items tab", state["tab"] == "lines",
              json.dumps(state))
    if index == 3:
        check("slide 3 is on the Premiums tab", state["tab"] == "premiums",
              json.dumps(state))

# Deal season reads as the stored YYYY-YYYY wherever it appears.
seasons = E("""(() => {
  const chip = [...document.querySelectorAll('.rcm-meta-chip, .rcm-meta-text')]
    .map(n => n.textContent).join(' ');
  const text = document.querySelector('[data-v2-root]').textContent;
  return {
    chip: chip.replace(/\\s+/g, ' ').trim(),
    fy: /FY\\d{2}/.test(chip),
    short: /\\b\\d{2}-\\d{2}\\b/.test(chip),
    enDash: text.indexOf('\\u2013') !== -1,
    full: /\\b20\\d{2}-20\\d{2}\\b/.test(chip)
  };
})()""")
check("deal season shows the normalized YYYY-YYYY form",
      seasons["full"] and not seasons["fy"] and not seasons["short"],
      json.dumps(seasons))
check("no en dash is rendered in the product view",
      not seasons["enDash"], json.dumps(seasons))

E("""document.querySelector('[data-rcle-close]').click()""")
time.sleep(0.6)

# --- list story -------------------------------------------------------
go("version=2.1&section=list", wait=2.5)
E("""window.RateCardPresentationView.open()""")
time.sleep(2.0)
rail = E("""(() => {
  const steps = [...document.querySelectorAll(
    '[data-rcle-list-rail] .rcle-list__step')];
  return steps.map(s => ({
    heading: (s.querySelector('h3, .rcle-list__step-title') || {})
      .textContent.replace(/\\s+/g, ' ').trim(),
    body: (s.querySelector('p') || {}).textContent
      .replace(/\\s+/g, ' ').trim()
  }));
})()""")
check("list story has the three approved steps", len(rail) == 3,
      json.dumps(rail))
for i, heading in enumerate(["Find the right rate card",
                             "Confirm the commercial context",
                             "Open the rate card"]):
    check(f"list step {i + 1} is {heading!r}",
          i < len(rail) and rail[i]["heading"] == heading,
          json.dumps(rail[i] if i < len(rail) else None))

# The rail must not promise a column the frame cuts off at this width.
claim = E("""(() => {
  const rail = document.querySelector('[data-rcle-list-rail]').textContent;
  const heads = [...document.querySelectorAll('thead .th, thead th')]
    .filter(t => t.getClientRects().length)
    .map(t => t.textContent.toLowerCase());
  return {mentionsVersion: /version/i.test(rail),
          showsVersion: heads.some(h => h.indexOf('version') !== -1)};
})()""")
check("list rail only cites columns the audience can see",
      not claim["mentionsVersion"] or claim["showsVersion"],
      json.dumps(claim))

print(json.dumps({"passes": PASSES, "failures": len(FAILURES)}))
sys.exit(1 if FAILURES else 0)
