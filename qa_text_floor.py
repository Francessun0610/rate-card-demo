"""No visible user-facing text renders below 14px.

Walks every rendered element that carries its own text on each major
surface and in every presentation state. Decorative marks with no
semantic content are exempt.
"""

import json
import sys
import time

sys.path.insert(0, __file__.rsplit("/", 1)[0] + "/tmp")
from review import E, go, size, console, drain  # noqa: E402

PASSES = 0
FAILURES = []
FLOOR = 14


def check(name, ok, detail=""):
    global PASSES
    if ok:
        PASSES += 1
        print(f"[PASS] {name}")
    else:
        FAILURES.append(name)
        print(f"[FAIL] {name}: {detail}")


# Decorative-only marks: an em dash placeholder, a bullet separator, and
# the chevron glyphs. None carry meaning a reader needs.
SCAN = """(root) => {
  const host = root ? document.querySelector(root) : document.body;
  if (!host) return {missing: true};
  const decorative = node =>
    node.getAttribute('aria-hidden') === 'true'
    || node.closest('[aria-hidden="true"]')
    || node.closest('svg');
  const out = [];
  const walk = host.querySelectorAll('*');
  [...walk].concat(host).forEach(node => {
    if (!node.getClientRects || !node.getClientRects().length) return;
    if (node.closest('[hidden]')) return;
    if (decorative(node)) return;
    const own = [...node.childNodes].some(
      c => c.nodeType === 3 && c.textContent.trim());
    const control = node.matches('input, textarea, select')
      && !node.matches('[type="checkbox"], [type="radio"]')
      && (node.value || node.placeholder);
    if (!own && !control) return;
    const size = parseFloat(getComputedStyle(node).fontSize);
    if (size >= 14) return;
    out.push({
      tag: node.tagName,
      cls: String(node.className || '').slice(0, 44),
      size: size,
      text: (node.textContent || node.value || node.placeholder || '')
        .trim().slice(0, 40)
    });
  });
  // One row per distinct class + size, so a table of 100 cells reports once.
  const seen = {};
  return out.filter(item => {
    const key = item.cls + '|' + item.size;
    if (seen[key]) return false;
    seen[key] = true;
    return true;
  });
}"""


def scan(root=None):
    return E(f"({SCAN})({json.dumps(root)})")


for w, h in [(1280, 800), (1440, 900), (1920, 1080)]:
    size(w, h)

    # --- Rate Card list, filter drawer, create modal ------------------
    go("version=2.1&section=list", wait=2.6)
    small = scan()
    check(f"{w}x{h} rate card list text is at least {FLOOR}px",
          not small, json.dumps(small[:6]))

    E("""document.querySelector('[data-action="toggle-filter"]').click()""")
    time.sleep(0.8)
    small = scan("#filter-panel")
    check(f"{w}x{h} filter drawer text is at least {FLOOR}px",
          not small, json.dumps(small[:6]))
    E("""document.querySelector('#filter-panel [data-action="close-filter"]').click()""")
    time.sleep(0.5)

    E("""document.querySelector('[data-action="create"]').click()""")
    time.sleep(0.8)
    small = scan("[data-rc-create-modal]")
    check(f"{w}x{h} create rate card modal text is at least {FLOOR}px",
          not small, json.dumps(small[:6]))
    E("""document.querySelector('[data-action="close-rc-create"]').click()""")
    time.sleep(0.5)

    # --- Rate card detail, line details, premium details --------------
    go("version=2.1&section=create&mode=edit&cardId=RC-DAS-WPP-VIDEO-UF-2627",
       wait=2.8)
    small = scan("[data-v2-root]")
    check(f"{w}x{h} rate card detail text is at least {FLOOR}px",
          not small, json.dumps(small[:6]))

    E("""(() => { const r = document.querySelector(
      '[data-v2-table-region="lines"] tbody [data-v2-row-id]');
      const cell = r && (r.querySelector('.create-md__td-advertiser')
        || [...r.children].find(c => !String(c.className).includes('checkbox')));
      if (cell) cell.click(); })()""")
    time.sleep(0.9)
    small = scan("[data-v2-form=\"line\"]")
    check(f"{w}x{h} line details text is at least {FLOOR}px",
          not small, json.dumps(small[:6]))

    E("""(() => { const t = document.querySelector('[data-v2-tab="premiums"]');
      if (t) t.click(); })()""")
    time.sleep(0.9)
    E("""(() => { const r = document.querySelector(
      '[data-v2-table-region="premiums"] tbody [data-v2-row-id]');
      const cell = r && [...r.children].find(
        c => !String(c.className).includes('checkbox'));
      if (cell) cell.click(); })()""")
    time.sleep(0.9)
    small = scan("[data-v2-form=\"premium\"]")
    check(f"{w}x{h} premium details text is at least {FLOOR}px",
          not small, json.dumps(small[:6]))

    # --- every presentation state -------------------------------------
    go("version=2.1&section=create&mode=edit&cardId=RC-DAS-WPP-VIDEO-UF-2627",
       wait=2.8)
    E("""window.RateCardPresentationView.open()""")
    time.sleep(1.8)
    for slide in (1, 2, 3):
        if slide > 1:
            E("""document.querySelector('[data-rcle-slide-next]').click()""")
            time.sleep(1.0)
        narration = E("""(() => {
          const o = document.querySelector('[data-rcle]');
          const parts = [o.querySelector('.rcle__title'),
                         o.querySelector('.rcle__subtitle'),
                         o.querySelector('[data-rcle-slide-panel]:not([hidden])'),
                         o.querySelector('[data-rcle-carousel-nav]')];
          const out = [];
          parts.forEach(part => {
            if (!part) return;
            [...part.querySelectorAll('*')].concat(part).forEach(node => {
              if (!node.getClientRects().length) return;
              if (node.closest('svg') || node.getAttribute('aria-hidden') === 'true') return;
              const own = [...node.childNodes].some(
                c => c.nodeType === 3 && c.textContent.trim());
              if (!own) return;
              const size = parseFloat(getComputedStyle(node).fontSize);
              if (size < 14) out.push({cls: String(node.className), size,
                                       text: node.textContent.trim().slice(0, 32)});
            });
          });
          return out;
        })()""")
        check(f"{w}x{h} presentation state {slide} narration is at least {FLOOR}px",
              not narration, json.dumps(narration[:5]))

    E("""document.querySelector('[data-rcle-view-toggle]').click()""")
    time.sleep(1.0)
    prev_small = E("""(() => {
      const o = document.querySelector('[data-rcle]');
      const parts = [o.querySelector('.rcle__title'), o.querySelector('.rcle__subtitle')];
      const out = [];
      parts.forEach(part => {
        if (!part || !part.getClientRects().length) return;
        const size = parseFloat(getComputedStyle(part).fontSize);
        if (size < 14) out.push({cls: String(part.className), size});
      });
      return out;
    })()""")
    check(f"{w}x{h} previous design header text is at least {FLOOR}px",
          not prev_small, json.dumps(prev_small))
    E("""document.querySelector('[data-rcle-close]').click()""")
    time.sleep(0.6)

    # --- rate card list presentation ----------------------------------
    go("version=2.1&section=list", wait=2.6)
    E("""window.RateCardPresentationView.open()""")
    time.sleep(1.8)
    rail = E("""(() => {
      const rail = document.querySelector('[data-rcle-list-rail]');
      const out = [];
      [...rail.querySelectorAll('*')].concat(rail).forEach(node => {
        if (!node.getClientRects().length) return;
        const own = [...node.childNodes].some(
          c => c.nodeType === 3 && c.textContent.trim());
        if (!own) return;
        const size = parseFloat(getComputedStyle(node).fontSize);
        if (size < 14) out.push({cls: String(node.className), size,
                                 text: node.textContent.trim().slice(0, 32)});
      });
      return out;
    })()""")
    check(f"{w}x{h} list presentation rail text is at least {FLOOR}px",
          not rail, json.dumps(rail[:5]))
    E("""document.querySelector('[data-rcle-close]').click()""")
    time.sleep(0.5)

drain()
errors = [c for c in console if "error" in str(c).lower()
          and "beforeunload" not in str(c)]
check("no console errors", not errors, json.dumps(errors[:3]))

print(json.dumps({"passes": PASSES, "failures": len(FAILURES)}))
sys.exit(1 if FAILURES else 0)
