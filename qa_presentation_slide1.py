"""Presentation slide 1 demonstrates the live Edit rate card modal.

Asserts the required DOM state rather than only that a panel closed:
the heading and subtitle copy, the real modal being visible and titled,
no Line or Premium details panel, no empty product-side column holding
layout width, the background page still visible, the whole modal inside
the live product viewport, and the absence of the retired copy.
"""

import json
import sys
import time

sys.path.insert(0, __file__.rsplit("/", 1)[0] + "/tmp")
from review import E, go, shot, size, console, drain  # noqa: E402

PASSES = 0
FAILURES = []

# Retired audience-facing terminology. The live product keeps its own
# labels; this list is only checked against the narration slots.
RETIRED_COPY = [
    "Rate Card Details",
    "Line Item Details",
    "Premium Adjustments",
    "CARD sets the commercial context",
    "Each LINE",
    "A PREM",
    "Negotiated base rates",
    "Additional pricing adjustments",
]


def check(name, ok, detail=""):
    global PASSES
    if ok:
        PASSES += 1
        print(f"[PASS] {name}")
    else:
        FAILURES.append(name)
        print(f"[FAIL] {name}: {detail}")


PROBE = """(() => {
  const o = document.querySelector('[data-rcle]');
  const modal = document.querySelector('[data-rc-create-modal]');
  const frame = o.querySelector('[data-rcle-product-frame]');
  const viewport = o.querySelector('[data-rcle-product-viewport]');
  const copy = o.querySelector('[data-rcle-slide-panel]:not([hidden])');
  const detail = o.querySelector('.rcle__live-slot .create-md__detail');
  const ring = o.querySelector('[data-rcle-callout-target]');
  const line = o.querySelector('[data-rcle-callout-line]');
  const table = o.querySelector('.rcle__live-slot [data-v2-table-region="lines"]');
  const title = o.querySelector('.rcle__live-slot [data-v2-title]');
  const fr = frame.getBoundingClientRect();
  const panel = modal && !modal.hidden ? modal.querySelector('.modal__panel') : null;
  const mr = panel ? panel.getBoundingClientRect() : null;
  const rr = ring.getBoundingClientRect();
  const lr = line.getBoundingClientRect();
  const cr = copy.getBoundingClientRect();
  const detailRect = detail ? detail.getBoundingClientRect() : null;
  return {
    slide: o.getAttribute('data-rcle-slide'),
    headerTitle: o.querySelector('.rcle__title').textContent.trim(),
    headerSubtitle: o.querySelector('.rcle__subtitle').textContent.trim(),
    heading: copy.querySelector('.rcle__slide-heading').textContent.trim(),
    copyText: copy.querySelector('.rcle__slide-copy').textContent.replace(/\\s+/g,' ').trim(),
    facts: [...copy.querySelectorAll('.rcle__fact')]
      .map(f => f.querySelector('dt').textContent.trim() + ' | '
             + f.querySelector('dd').textContent.trim()),
    modalVisible: !!panel,
    modalTitle: panel ? modal.querySelector('.modal__title').textContent.trim() : null,
    modalInViewport: mr ? (mr.left >= fr.left - 2 && mr.right <= fr.right + 2
      && mr.top >= fr.top - 2 && mr.bottom <= fr.bottom + 2) : false,
    modalHasFooter: !!(panel && panel.querySelector('.modal__footer')),
    modalActions: panel ? [...panel.querySelectorAll('.modal__footer button')]
      .map(b => b.textContent.trim()) : [],
    modalMountedInFrame: !!(panel && frame.contains(modal)),
    linePanelOpen: !!o.querySelector('.rcle__live-slot .create-md.is-panel-open'),
    detailColumnWidth: detailRect ? Math.round(detailRect.width) : 0,
    backgroundVisible: !!(table && table.getBoundingClientRect().width > 0)
      && !!(title && title.getBoundingClientRect().width > 0),
    // The annotation must sit on the modal, not on an empty column.
    ringOnModal: mr ? (Math.abs(rr.left - mr.left) < 24
      && Math.abs(rr.width - mr.width) < 48) : false,
    leaderClearOfCopy: line.hasAttribute('hidden') || lr.right <= cr.left + 1,
    narrationText: [o.querySelector('.rcle__title'),
                    o.querySelector('.rcle__subtitle'),
                    ...o.querySelectorAll('[data-rcle-slide-panel]')]
      .map(n => n ? n.textContent : '').join(' ')
  };
})()"""

size(1440, 900)

for version, card in [("2.0", "RC-2026-UPFRONT-001"),
                      ("2.1", "RC-DAS-WPP-VIDEO-UF-2627")]:
    for w, h in [(1280, 800), (1440, 900), (1920, 1080)]:
        size(w, h)
        go(f"section=create&mode=edit&cardId={card}&version={version}", wait=3.0)
        E("""window.RateCardPresentationView.open()""")
        time.sleep(2.0)
        st = E(PROBE)
        tag = f"v{version} {w}x{h}"

        check(f"{tag} presentation heading is Edit Rate Card",
              st["headerTitle"] == "Edit Rate Card", st["headerTitle"])
        check(f"{tag} subtitle matches the new copy",
              st["headerSubtitle"] == "Update the details shared across the "
                                      "entire rate card.", st["headerSubtitle"])
        check(f"{tag} the Edit rate card modal is visible",
              st["modalVisible"], json.dumps(st["modalVisible"]))
        check(f"{tag} the modal title is Edit rate card",
              st["modalTitle"] == "Edit rate card", str(st["modalTitle"]))
        check(f"{tag} the modal is the live component mounted in the frame",
              st["modalMountedInFrame"])
        check(f"{tag} no Line or Premium details panel is visible",
              not st["linePanelOpen"])
        check(f"{tag} no empty product-side column holds layout width",
              st["detailColumnWidth"] == 0, str(st["detailColumnWidth"]))
        check(f"{tag} the Rate Card background page is still visible",
              st["backgroundVisible"])
        check(f"{tag} the complete modal is inside the live product viewport",
              st["modalInViewport"] and st["modalHasFooter"]
              and st["modalActions"] == ["Cancel", "Confirm"],
              json.dumps([st["modalInViewport"], st["modalActions"]]))
        check(f"{tag} the explanation carries the new copy",
              st["heading"] == "Who is this rate card for?"
              and st["copyText"] == "Shared details identify the buyer, market, "
                                    "and dates for every price."
              and st["facts"] == ["Buyer | Who negotiated it",
                                  "Market | Where it applies",
                                  "Timing | When it applies"],
              json.dumps([st["heading"], st["facts"]]))
        retired = [phrase for phrase in RETIRED_COPY if phrase in st["narrationText"]]
        check(f"{tag} the retired copy is absent", not retired, json.dumps(retired))
        check(f"{tag} the annotation is on the modal, not an empty panel",
              st["ringOnModal"] and st["leaderClearOfCopy"],
              json.dumps([st["ringOnModal"], st["leaderClearOfCopy"]]))

        if version == "2.1":
            shot(f"slide1-{w}x{h}")

        # --- lifecycle: every route back into slide 1 reopens the modal
        for label, action in [
            ("navigating back from slide 2", """(() => {
               document.querySelector('[data-rcle-slide-next]').click(); })()"""),
            ("returning from Previous design", """(() => {
               document.querySelector('[data-rcle-view-toggle]').click(); })()"""),
        ]:
            E(action)
            time.sleep(1.0)
            E("""(() => {
              const o = document.querySelector('[data-rcle]');
              if (o.getAttribute('data-rcle-view') === 'previous') {
                document.querySelector('[data-rcle-view-toggle]').click();
              } else {
                document.querySelector('[data-rcle-slide-prev]').click();
              }
            })()""")
            time.sleep(1.2)
            check(f"{tag} the modal reopens after {label}",
                  not E("""document.querySelector('[data-rc-create-modal]').hidden"""))

        # Reopening presentation mode.
        E("""document.querySelector('[data-rcle-close]').click()""")
        time.sleep(0.8)
        check(f"{tag} leaving presentation closes the modal",
              E("""document.querySelector('[data-rc-create-modal]').hidden"""))
        E("""window.RateCardPresentationView.open()""")
        time.sleep(1.8)
        check(f"{tag} reopening presentation reopens the modal",
              not E("""document.querySelector('[data-rc-create-modal]').hidden"""))
        E("""document.querySelector('[data-rcle-close]').click()""")
        time.sleep(0.6)

drain()
errors = [c for c in console if "error" in str(c).lower()
          and "beforeunload" not in str(c)]
check("no console errors", not errors, json.dumps(errors[:3]))

print(json.dumps({"passes": PASSES, "failures": len(FAILURES)}))
sys.exit(1 if FAILURES else 0)
