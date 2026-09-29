/**
 * Portfolio-only helpers. Loaded only by portfolio.html.
 * Do not import from index.html. Keep behavior gated to the portfolio deck.
 */
(function initPortfolioDeckHelpers() {
  function ready(fn) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", fn, { once: true });
    } else {
      fn();
    }
  }

  ready(function () {
    if (document.body.getAttribute("data-deck-variant") !== "portfolio") return;
    mountPreviousDesignPreview();
  });

  /**
   * Slide A embeds the real Create Rate Card step-wizard prototype
   * (the same node the product "Previous design" toggle clones from).
   * One source of truth; no invented screenshot.
   */
  function mountPreviousDesignPreview() {
    var mount = document.querySelector("[data-pf-prev-mount]");
    var source = document.querySelector("[data-rcle-previous-prototype]");
    if (!mount || !source || mount.childElementCount) return;

    var copy = source.cloneNode(true);
    while (copy.firstChild) mount.appendChild(copy.firstChild);

    mount.querySelectorAll(
      "a, button, input, select, textarea, [tabindex]"
    ).forEach(function (node) {
      node.setAttribute("tabindex", "-1");
    });
  }
})();
