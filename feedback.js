/* =====================================================================
   FEEDBACK  -  capture, annotate, submit to the Rate Card feedback doc
   ---------------------------------------------------------------------
   Self-contained apart from two siblings it reads and never writes:
   feedback-config.js for the destination, feedback-transport.js for the
   submission. Nothing here reaches into the prototype's own state.

   Three modes:
     closed   just the 32px "?" in the bottom-left corner
     live     the real running prototype, plus a small dock. Not a modal:
              the reviewer is inspecting the actual app, so the page stays
              interactive, scrollable, and focus is not trapped
     editor   a frozen screenshot in a dialog, with the annotation tools

   On capture. The screenshot is drawn from the page itself, in the page,
   with no permission prompt and nothing for the reviewer to pick. An
   earlier build asked the browser for the tab through getDisplayMedia;
   that call simply never settled in a managed or embedded browser, so the
   button sat on "Capturing..." and the canvas stayed empty. See the
   capture section for the details this rewrite depends on.

   On submission. Submit feedback posts the note and the annotated
   screenshot straight to the Rate Card feedback document. The reviewer
   copies nothing, downloads nothing, and opens no other form. Success is
   shown only after the document write has been confirmed by submission
   id, never on the strength of a dispatched request, because the response
   to that request is opaque and proves nothing. Copy and Download remain
   as emergency fallbacks for when submission cannot complete.
   ===================================================================== */
(function () {
  "use strict";

  var CONFIG = window.RCF_FEEDBACK_CONFIG;
  var TRANSPORT = window.RCFFeedbackTransport;

  var MAX_CHARS = (CONFIG && CONFIG.MAX_FEEDBACK_CHARS) || 300;
  var MAX_EXPORT_BYTES = 10 * 1024 * 1024;   /* the flatten's own ceiling */
  var MIN_MARK = 6;                          /* px, ignores stray taps */

  var COPY = {
    head: "The prototype may be fake. This feedback button is very real.",
    body: "Tell me what works, what feels confusing, or what you\u2019d change. " +
      "I genuinely read every note.",
    sign: "\u2014 Frances Sun",
    frozen: "Your screenshot is frozen so your annotations stay in place.",
    sendTogether: "Your note and marked-up screenshot will be sent together.",
    submitting: "Submitting feedback\u2026",
    confirming: "Confirming submission\u2026",
    successTitle: "Feedback submitted",
    successBody: "Got it, thank you! I really do read these.",
    authTitle: "Sign in to continue",
    authBody: "Open the sign-in page in a new tab, then come back and try again.",
    demoTitle: "Demo mode",
    demoBody: "This portfolio build runs offline, so feedback is not sent " +
      "anywhere. Use Copy feedback or Download screenshot to keep your notes.",
    errorTitle: "Feedback not submitted",
    keptSafe:
      "Your note, screenshot, and marks are all still here. You can try again, " +
      "or use Copy feedback and Download screenshot as a fallback."
  };

  /* The opening card has its own voice. It says what this is and who
   * reads it, and deliberately says nothing about how to work the tool:
   * the reviewer is one button away from finding that out, and a list of
   * steps here makes a thirty second errand sound like a chore. The
   * editor panel keeps its own wording because it is read later, while
   * the reviewer is already mid task. */
  var CARD_COPY = {
    head: "The prototype is fake. Your feedback isn\u2019t.",
    body: "Tell me what works, what feels unclear, and what could be better.",
    emphasis:
      "I\u2019ll actually see and read what you send \u2014 no feedback black hole.",
    reassurance: "Anything you send here comes straight to me."
  };

  /* One explicit phase. Nothing important is ever inferred from a CSS
   * class, and every phase names the status chip it puts on screen. */
  var PHASE_LABEL = {
    idle: "No screenshot",
    capturing: "Capturing\u2026",
    "capture-ready": "Screenshot ready",
    "capture-error": "Capture failed",
    editing: "Screenshot ready",
    preparing: "Preparing\u2026",
    submitting: "Submitting\u2026",
    confirming: "Confirming\u2026",
    submitted: "Submitted",
    "auth-required": "Sign in required",
    "demo-offline": "Demo mode",
    "submission-error": "Not submitted"
  };

  /* While a submission is in flight the dialog must not be closed, the
   * work must not be discarded, and Submit must not fire again.
   *
   * This is an explicit flag rather than a set of phase names because the
   * "preparing" phase has two causes: the background flatten that runs
   * after every mark, and the preparation step of a submission. Deriving
   * busy from the phase made a Submit press land during a background
   * flatten look like a duplicate press, and the click was swallowed with
   * no feedback at all. */
  function isBusy() {
    return state.submitInFlight;
  }

  var state = {
    mode: "closed",
    phase: "idle",
    shot: null,          /* { url, width, height, dpr } */
    marks: [],           /* normalised 0..1, in capture coordinates */
    tool: "pan",
    zoom: "fit",
    draft: "",
    source: null,
    exportBlob: null,
    exportName: "",
    /* Held across retries on purpose. A retry that reuses the id lets the
     * Web App drop it as a duplicate, so an uncertain retry can never
     * write a second entry into the document. */
    submissionId: null,
    submitInFlight: false,
    lastError: null,
    composing: false,
    lastFocus: null,
    prevOverflow: null,
    introSeen: false
  };

  var el = {};          /* built once, in build() */
  var drag = null;

  /* ------------------------------------------------------------ helpers */

  function make(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  function btn(label, cls, title) {
    var b = make("button", "rcf-btn" + (cls ? " " + cls : ""), label);
    b.type = "button";
    if (title) { b.title = title; b.setAttribute("aria-label", title); }
    return b;
  }

  function reducedMotion() {
    return typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  /* User-perceived characters. Intl.Segmenter counts a family emoji or a
   * combining sequence as the one character the reviewer sees; the split
   * fallback at least counts astral pairs once rather than twice. */
  var segmenter = (typeof Intl !== "undefined" && Intl.Segmenter)
    ? new Intl.Segmenter(undefined, { granularity: "grapheme" })
    : null;

  function graphemes(str) {
    if (!str) return [];
    if (segmenter) {
      var out = [];
      var it = segmenter.segment(str)[Symbol.iterator]();
      for (var r = it.next(); !r.done; r = it.next()) out.push(r.value.segment);
      return out;
    }
    return Array.from(str);
  }

  function clampGraphemes(str, max) {
    var g = graphemes(str);
    return g.length <= max ? str : g.slice(0, max).join("");
  }

  /* The single place the phase changes, so the status chip can never
   * disagree with what is actually on the canvas. */
  function setPhase(next) {
    if (!PHASE_LABEL[next]) return;
    state.phase = next;
    if (el.stateTag) {
      el.stateTag.textContent = PHASE_LABEL[next];
      el.stateTag.setAttribute("data-phase", next);
    }
    if (el.root) el.root.setAttribute("data-rcf-phase", next);
    syncButtons();
  }

  function status(msg, tone) {
    if (!el.status) return;
    el.status.textContent = msg || "";
    if (tone) el.status.setAttribute("data-tone", tone);
    else el.status.removeAttribute("data-tone");
  }

  function nextPaint() {
    return new Promise(function (resolve) {
      requestAnimationFrame(function () {
        requestAnimationFrame(function () { setTimeout(resolve, 40); });
      });
    });
  }

  /* ---------------------------------------------------- source reference */

  function readSource() {
    var route = document.body.getAttribute("data-route") || "list";
    /* The deck keeps an active slide in the DOM even when another route is
     * showing, so the slide only names the view when the deck is the view.
     * Otherwise a capture of the list reported itself as "list / cover". */
    var slide = route === "atlas"
      ? document.querySelector(".atlas-slide.is-active")
      : null;
    var id = slide ? slide.getAttribute("data-atlas-slide-id") : null;
    var heading = null;
    if (slide) {
      var h = slide.querySelector("h2, h1, .cov__title");
      if (h) heading = h.textContent.replace(/\s+/g, " ").trim();
    }
    if (!heading) {
      var main = document.querySelector(
        '.page-route:not([hidden]) h1, .page-route:not([hidden]) h2'
      );
      if (main) heading = main.textContent.replace(/\s+/g, " ").trim();
    }
    var VIEW = { list: "List", create: "Rate card details",
                 line: "Line pricing", atlas: "Presentation" };
    return {
      route: route,
      slideId: id,
      title: heading || document.title || "Rate Card prototype",
      viewLabel: VIEW[route] || route,
      /* The slide is the state within the presentation; other routes have
       * no second level worth naming. */
      stateLabel: id || null,
      /* Route and slide only. Never the raw query string: it can carry
       * ids or tokens that have no business in a feedback note. */
      label: id ? (route + " / " + id) : route
    };
  }

  /* The ?section= token, when the shared link carries one. Read straight
   * from the URL rather than inferred, and null when absent. */
  function readSection() {
    try {
      return new URLSearchParams(window.location.search).get("section") || null;
    } catch (err) {
      return null;
    }
  }

  function slugFor(src) {
    var base = (src && (src.slideId || src.route)) || "view";
    return String(base).toLowerCase().replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "").slice(0, 40) || "view";
  }

  function stamp() {
    var d = new Date();
    function p(n) { return String(n).padStart(2, "0"); }
    return d.getFullYear() + p(d.getMonth() + 1) + p(d.getDate()) +
      "-" + p(d.getHours()) + p(d.getMinutes()) + p(d.getSeconds());
  }

  /* ------------------------------------------------------------ launcher */

  function buildLauncher() {
    var b = make("button", "rcf-launch");
    b.type = "button";
    b.appendChild(make("span", null, "?"));
    b.title = "Share feedback";
    b.setAttribute("aria-label", "Open feedback");
    b.addEventListener("click", function (e) {
      /* The deck advances on a click anywhere in the stage wrap. This
       * button sits outside it, but stopping here as well means a future
       * layout change cannot turn the launcher into a slide advance. */
      e.preventDefault();
      e.stopPropagation();
      openLive();
    });
    return b;
  }

  /* The bottom-right corner is not always free. Rather than hard-code
   * what might be parked there on any given route, ask the document what
   * is actually under the corner.
   *
   * A small floating control is cleared by a short step upwards, which
   * keeps the button hard against the right edge where it belongs. A
   * full-height rail cannot be climbed past, so if lifting runs out of
   * room the button steps sideways instead, capped at a quarter of the
   * viewport so it can never wander towards the opposite corner. */
  var BASE = 24;

  function hitAt(x, y) {
    var prev = el.launch.style.pointerEvents;
    el.launch.style.pointerEvents = "none";
    var prevDock = el.dock ? el.dock.style.pointerEvents : null;
    if (el.dock) el.dock.style.pointerEvents = "none";
    var hit = document.elementFromPoint(x, y);
    el.launch.style.pointerEvents = prev;
    if (el.dock) el.dock.style.pointerEvents = prevDock;
    if (!hit || !hit.closest) return null;
    /* Only chrome counts. Something pinned to the viewport owns that
     * corner on every scroll position, so the button has to move; slide
     * artwork and page content underneath do not, and treating them as
     * obstacles sends the button wandering across the screen. */
    for (var n = hit; n && n !== document.body; n = n.parentElement) {
      if (el.root && el.root.contains(n)) return null;
      var pos = getComputedStyle(n).position;
      if (pos !== "fixed" && pos !== "sticky") continue;
      var r = n.getBoundingClientRect();
      /* A pinned surface that spans the viewport is the page, not a
       * control sitting in the corner. Only narrow chrome, a rail or a
       * small floating button, is something to move around. */
      if (r.width >= window.innerWidth * 0.5) continue;
      return n;
    }
    return null;
  }

  function placeLauncher() {
    if (!el.launch) return;
    var wasHidden = el.launch.hidden;
    if (wasHidden) el.launch.hidden = false;      /* must be laid out to probe */

    var right = BASE;
    var lift = 0;
    var maxShift = Math.max(BASE, Math.round(window.innerWidth * 0.25));

    function blockedAt(r, up) {
      var yy = window.innerHeight - (BASE + up + 16);
      var edge = window.innerWidth - r;
      return hitAt(edge - 2, yy) || hitAt(edge - 16, yy) || hitAt(edge - 30, yy);
    }

    if (blockedAt(right, 0)) {
      while (lift < 120 && blockedAt(right, lift)) lift += 40;
      if (blockedAt(right, lift)) {
        lift = 0;
        while (right + 48 <= maxShift + 48 && blockedAt(right, 0)) right += 8;
      }
    }

    var rcss = "calc(" + right + "px + env(safe-area-inset-right, 0px))";
    var bcss = "calc(" + (BASE + lift) + "px + env(safe-area-inset-bottom, 0px))";
    el.launch.style.right = rcss;
    el.launch.style.bottom = bcss;
    if (el.dock) { el.dock.style.right = rcss; el.dock.style.bottom = bcss; }
    if (wasHidden) el.launch.hidden = true;
  }

  /* --------------------------------------------------------- live inspect */

  function openLive() {
    if (state.mode === "editor") return;
    state.mode = "live";
    el.launch.hidden = true;
    /* First open shows the introduction; afterwards, straight to the
     * dock, because a reviewer reporting a second thing does not need to
     * be introduced again. */
    if (!state.introSeen) {
      state.introSeen = true;
      el.dock.hidden = true;
      el.intro.hidden = false;
      placeLauncher();
      el.introGo.focus();
    } else {
      el.intro.hidden = true;
      el.dock.hidden = false;
      placeLauncher();
      el.dockCapture.focus();
    }
    announce("Live view. Inspect the page, then capture this view.");
  }

  function closeLive() {
    state.mode = "closed";
    el.dock.hidden = true;
    if (el.intro) el.intro.hidden = true;
    el.launch.hidden = false;
    placeLauncher();
    el.launch.focus();
  }

  function announce(msg) {
    if (el.live) el.live.textContent = msg;
  }

  /* ------------------------------------------------------------- capture
     Deterministic and in-app. The reviewer presses one button and the
     screenshot appears; there is no operating-system picker and no
     permission prompt.

     How it works: the visible part of the page is cloned, every same-origin
     image is turned into a data URI, the page's own stylesheets are inlined,
     and the result is drawn into an SVG foreignObject which the browser
     rasterises onto a canvas.

     Three details are load-bearing, and each one was a failure before it was
     understood:

       1. The SVG must reach the Image as a data: URL. Chrome taints the
          canvas when an SVG containing a foreignObject arrives over blob:,
          so every read of the pixels threw SecurityError. The same markup
          over data: is clean.
       2. Comment nodes have to go. XML forbids "--" inside a comment and
          this markup is full of dashed comment banners, so the SVG failed
          to parse at the first one.
       3. No stylesheet may keep an off-origin url(). One un-inlined webfont
          is enough to taint the canvas again.
     ------------------------------------------------------------------- */

  var CAPTURE_MAX_SCALE = 2;      /* keep exports sharp without freezing */
  var cssCache = null;
  var imageCache = {};

  function blobToDataUri(blob) {
    return new Promise(function (resolve, reject) {
      var r = new FileReader();
      r.onload = function () { resolve(r.result); };
      r.onerror = function () { reject(new Error("read")); };
      r.readAsDataURL(blob);
    });
  }

  /* Google serves one @font-face per unicode subset, forty of them for this
   * family set. The latin subsets are what this UI renders. */
  function latinSubsetsOnly(text) {
    return text.split(/(?=\/\*)/).filter(function (block) {
      if (block.indexOf("@font-face") === -1) return true;
      return /\/\*\s*latin(-ext)?\s*\*\//.test(block);
    }).join("");
  }

  async function inlineCssUrls(text, base) {
    var wanted = [];
    text.replace(/url\((['"]?)([^)'"]+)\1\)/g, function (m, q, u) {
      if (u.indexOf("data:") !== 0) wanted.push(u);
      return m;
    });
    var map = {};
    await Promise.all(wanted.map(async function (u) {
      try {
        var res = await fetch(new URL(u, base).href, { mode: "cors" });
        if (res.ok) map[u] = await blobToDataUri(await res.blob());
      } catch (err) { /* the stripper below removes whatever is left */ }
    }));
    return text.replace(/url\((['"]?)([^)'"]+)\1\)/g, function (m, q, u) {
      return map[u] ? "url(" + map[u] + ")" : m;
    });
  }

  /* Anything still pointing off-origin taints the canvas the instant the SVG
   * is drawn, so it is removed rather than risked. Text falls through to the
   * next family in the stack. */
  function stripRemoteUrls(css) {
    return css.replace(/url\((['"]?)(https?:\/\/[^)'"]+)\1\)/g, function (m, q, u) {
      return u.indexOf(location.origin) === 0 ? m : "none";
    });
  }

  async function collectCss() {
    if (cssCache) return cssCache;
    var parts = [];
    for (var i = 0; i < document.styleSheets.length; i++) {
      var sheet = document.styleSheets[i];
      if (sheet.href) {
        /* The file itself is smaller than serialised cssRules and avoids the
         * shorthand expansion the CSSOM performs. */
        try {
          var res = await fetch(sheet.href, { mode: "cors" });
          if (res.ok) {
            parts.push(await inlineCssUrls(latinSubsetsOnly(await res.text()), sheet.href));
          }
        } catch (err) { /* a sheet we cannot read is simply not applied */ }
      } else {
        var rules = null;
        try { rules = sheet.cssRules; } catch (err) { rules = null; }
        if (!rules) continue;
        var text = "";
        for (var j = 0; j < rules.length; j++) text += rules[j].cssText + "\n";
        parts.push(text);
      }
    }
    cssCache = stripRemoteUrls(parts.join("\n"));
    return cssCache;
  }

  async function assetDataUri(url) {
    if (imageCache[url]) return imageCache[url];
    if (url.indexOf("data:") === 0) return url;
    try {
      var res = await fetch(url, { mode: "same-origin" });
      if (!res.ok) return null;
      var uri = await blobToDataUri(await res.blob());
      imageCache[url] = uri;
      return uri;
    } catch (err) { return null; }
  }

  /* Every picture has to travel inside the SVG. A relative src would resolve
   * against the data: URL and come back empty, and an off-origin one would
   * taint the canvas. */
  async function inlineImages(clone) {
    var jobs = [];
    var missed = [];
    Array.prototype.forEach.call(clone.querySelectorAll("img[src]"), function (n) {
      var src = n.src;
      jobs.push(assetDataUri(src).then(function (uri) {
        if (uri) n.setAttribute("src", uri);
        else { missed.push(src); n.removeAttribute("src"); }
      }));
    });
    Array.prototype.forEach.call(clone.querySelectorAll("image"), function (n) {
      var href = n.getAttribute("href") || n.getAttribute("xlink:href");
      if (!href) return;
      var abs = href.indexOf("data:") === 0 ? href : new URL(href, location.href).href;
      jobs.push(assetDataUri(abs).then(function (uri) {
        if (uri) { n.setAttribute("href", uri); n.removeAttribute("xlink:href"); }
        else { missed.push(abs); n.remove(); }
      }));
    });
    await Promise.all(jobs);
    return missed;
  }

  /* cloneNode copies attributes, not live form state, so a typed value or a
   * ticked box would vanish from the screenshot. */
  function freezeFormState(live, clone) {
    var a = live.querySelectorAll("input, textarea, select");
    var b = clone.querySelectorAll("input, textarea, select");
    for (var i = 0; i < a.length && i < b.length; i++) {
      var src = a[i], dst = b[i];
      if (src.tagName === "SELECT") {
        for (var j = 0; j < dst.options.length; j++) {
          if (j === src.selectedIndex) dst.options[j].setAttribute("selected", "");
          else dst.options[j].removeAttribute("selected");
        }
      } else if (src.type === "checkbox" || src.type === "radio") {
        if (src.checked) dst.setAttribute("checked", ""); else dst.removeAttribute("checked");
      } else if (src.tagName === "TEXTAREA") {
        dst.textContent = src.value;
      } else {
        dst.setAttribute("value", src.value);
      }
    }
  }

  /* A canvas is pixels, not markup, so it has to be swapped for a picture. */
  function freezeCanvases(live, clone) {
    var a = live.querySelectorAll("canvas");
    var b = clone.querySelectorAll("canvas");
    for (var i = 0; i < a.length && i < b.length; i++) {
      var uri = null;
      try { uri = a[i].toDataURL("image/png"); } catch (err) { uri = null; }
      if (!uri) continue;
      var img = document.createElement("img");
      img.setAttribute("src", uri);
      img.setAttribute("width", String(a[i].clientWidth || a[i].width));
      img.setAttribute("height", String(a[i].clientHeight || a[i].height));
      img.setAttribute("style", b[i].getAttribute("style") || "");
      b[i].parentNode.replaceChild(img, b[i]);
    }
  }

  function stripComments(node) {
    var walker = document.createTreeWalker(node, NodeFilter.SHOW_COMMENT, null);
    var doomed = [];
    while (walker.nextNode()) doomed.push(walker.currentNode);
    doomed.forEach(function (n) { if (n.parentNode) n.parentNode.removeChild(n); });
  }

  /* Everything the reviewer cannot see is dropped before the images are
   * inlined. Without this the clone carries all twelve slides and every
   * hidden route, which turned the SVG into megabytes of unused artwork. */
  var KEEP_FLAG = "data-rcf-keep";

  /* Marking has to happen on the live tree before it is cloned: the clone is
   * detached and cannot be measured, and marking afterwards leaves the clone
   * with no marks at all, which prunes the entire page away. */
  function markVisible(root, w, h) {
    var live = root.querySelectorAll("*");
    for (var i = 0; i < live.length; i++) {
      var n = live[i];
      var cs = window.getComputedStyle(n);
      if (cs.display === "none" || cs.visibility === "hidden") continue;
      var r = n.getBoundingClientRect();
      if (r.width <= 0 || r.height <= 0) continue;
      if (r.bottom < 0 || r.top > h || r.right < 0 || r.left > w) continue;
      n.setAttribute(KEEP_FLAG, "");
    }
    return live;
  }

  function unmark(nodes) {
    Array.prototype.forEach.call(nodes, function (n) { n.removeAttribute(KEEP_FLAG); });
  }

  function pruneUnmarked(clone) {
    var FLAG = KEEP_FLAG;
    (function walk(node) {
      var kids = Array.prototype.slice.call(node.children);
      for (var k = 0; k < kids.length; k++) {
        var elm = kids[k];
        if (!elm.hasAttribute(FLAG) && !elm.querySelector("[" + FLAG + "]")) {
          elm.remove();
          continue;
        }
        walk(elm);
      }
    })(clone);
    unmark(clone.querySelectorAll("[" + FLAG + "]"));
  }

  function rasterise(url, w, h, scale) {
    return new Promise(function (resolve, reject) {
      var img = new Image();
      img.onload = function () {
        var c = document.createElement("canvas");
        c.width = Math.round(w * scale);
        c.height = Math.round(h * scale);
        var ctx = c.getContext("2d");
        ctx.scale(scale, scale);
        ctx.drawImage(img, 0, 0, w, h);
        resolve(c);
      };
      img.onerror = function () { reject(new Error("The page could not be drawn.")); };
      img.src = url;
    });
  }

  function looksBlank(canvas) {
    /* A capture that never painted comes back one flat colour. Downscale and
     * read that back once: a grid of single-pixel reads costs a readback
     * each and makes the browser warn about it. */
    var n = 24;
    var t = document.createElement("canvas");
    t.width = n; t.height = n;
    var tc = t.getContext("2d", { willReadFrequently: true });
    tc.drawImage(canvas, 0, 0, n, n);
    var d = tc.getImageData(0, 0, n, n).data;
    for (var i = 4; i < d.length; i += 4) {
      if (d[i] !== d[0] || d[i + 1] !== d[1] || d[i + 2] !== d[2]) return false;
    }
    return true;
  }

  /* The application, and only the application.
   *
   * data-rcf-capture-root is the explicit opt in: if the app ever grows a
   * dedicated shell element it can name itself and the capture follows,
   * without this file having to know the markup. Until then the document
   * body is the application, which is what the prototype actually renders
   * into. */
  function resolveCaptureRoot() {
    return document.querySelector("[data-rcf-capture-root]") || document.body;
  }

  /* Anything that belongs to the reviewer's tooling rather than to the
   * product. Removed from the clone only, never from the live page, so
   * there is nothing to restore and no frame where the reviewer sees the
   * interface flicker.
   *   [data-rcf-root]     this feature: launcher, dock, dialog, backdrop
   *   [data-redline-ui]   the Redline QA inspector and its panels
   *   #ref-overlay        the Figma reference overlay
   *   .ads-toast          transient toasts, which would be stale by the
   *                       time anybody read the screenshot
   *   [data-rcf-exclude]  a general escape hatch for future chrome */
  var CAPTURE_EXCLUDE = [
    "[data-rcf-root]",
    "[data-redline-ui]",
    "#ref-overlay",
    ".ads-toast",
    "[data-rcf-exclude]"
  ].join(",");

  /* Draw the application exactly as it stands behind the workspace. */
  async function renderAppView() {
    /* The visual viewport, in CSS pixels, at the scroll position the
     * reviewer is actually looking at. Neither is modified here: the
     * capture reads the page, it never scrolls it. */
    var w = Math.max(1, Math.round(document.documentElement.clientWidth));
    var h = Math.max(1, Math.round(document.documentElement.clientHeight));
    var sx = window.scrollX || 0;
    var sy = window.scrollY || 0;

    if (document.fonts && document.fonts.ready) {
      try { await document.fonts.ready; } catch (err) { /* proceed */ }
    }
    /* Images already in the layout must have decoded, or a still loading
     * picture photographs as a blank box. decode() rejects for a broken
     * src, which is not a reason to abandon the capture. */
    await Promise.all(
      Array.prototype.slice
        .call(document.images)
        .filter(function (img) { return img.src && !img.complete; })
        .map(function (img) {
          return img.decode ? img.decode().catch(function () {}) : Promise.resolve();
        })
    );
    var css = await collectCss();

    var root = resolveCaptureRoot();
    var marked = markVisible(root, w, h);
    var clone;
    try {
      clone = root.cloneNode(true);
    } finally {
      unmark(marked);            /* the live page is never left altered */
    }
    /* The feature never photographs itself, or any other reviewer tooling
     * layered over the product. */
    Array.prototype.forEach.call(
      clone.querySelectorAll(CAPTURE_EXCLUDE), function (n) { n.remove(); });
    pruneUnmarked(clone);
    stripComments(clone);
    freezeFormState(root, clone);
    freezeCanvases(root, clone);
    var missed = await inlineImages(clone);

    /* The clone lays out from the top of the document, so the page's own
     * scroll has to be re-applied or a scrolled view photographs its header. */
    var shift = (sx || sy)
      ? ' style="margin:' + (-sy) + "px 0 0 " + (-sx) + 'px"'
      : "";
    var markup = new XMLSerializer().serializeToString(clone);
    var svg =
      '<svg xmlns="http://www.w3.org/2000/svg" width="' + w + '" height="' + h + '">' +
      '<foreignObject width="100%" height="100%">' +
      '<div xmlns="http://www.w3.org/1999/xhtml"' + shift + ">" +
      "<style>/*<![CDATA[*/" + css.replace(/<\/style>/gi, "") + "/*]]>*/</style>" +
      markup +
      "</div></foreignObject></svg>";

    var bytes = new TextEncoder().encode(svg);
    var bin = "";
    for (var b = 0; b < bytes.length; b += 0x8000) {
      bin += String.fromCharCode.apply(null, bytes.subarray(b, b + 0x8000));
    }
    var url = "data:image/svg+xml;base64," + btoa(bin);

    var scale = Math.min(CAPTURE_MAX_SCALE, window.devicePixelRatio || 1);
    var canvas = await rasterise(url, w, h, scale);
    if (looksBlank(canvas)) throw new Error("The capture came back empty.");
    return { canvas: canvas, missed: missed };
  }

  function setDockBusy(on) {
    el.dockCapture.disabled = on;
    el.dockCapture.textContent = on ? "Capturing\u2026" : "Capture this view";
    if (el.retake) el.retake.disabled = on || !state.shot;
  }

  /* One capture at a time, and a late one can never overwrite a newer shot. */
  var captureRun = 0;

  async function doCapture() {
    if (state.phase === "capturing") return;
    var mine = ++captureRun;
    setPhase("capturing");
    setDockBusy(true);
    status("Capturing\u2026", null);
    announce("Capturing the current view.");
    /* Hide only our own surfaces, and only for the moment of the draw. The
     * clone already excludes them; this also keeps them off the screen if a
     * browser ever paints during the rasterise. */
    var wasDock = el.dock.hidden, wasEditor = el.editor.hidden;
    var wasLaunch = el.launch.hidden, wasIntro = el.intro.hidden;
    el.launch.hidden = true; el.dock.hidden = true;
    el.intro.hidden = true; el.editor.hidden = true;
    try {
      await nextPaint();
      var out = await renderAppView();
      if (mine !== captureRun) return;            /* a newer capture won */
      await adoptCanvas(out.canvas);
      el.dock.hidden = true;
      openEditor();
      setPhase("capture-ready");
      if (out.missed && out.missed.length) {
        status("Screenshot ready, but " + out.missed.length +
               " image(s) could not be read and were left out. " + COPY.frozen, "error");
      } else {
        status("Screenshot ready. " + COPY.frozen, "ok");
      }
      announce("Screenshot ready.");
    } catch (err) {
      if (mine !== captureRun) return;
      el.launch.hidden = wasLaunch; el.dock.hidden = wasDock;
      el.intro.hidden = wasIntro; el.editor.hidden = wasEditor;
      captureFailed((err && err.message) || "The capture did not complete.");
    } finally {
      if (mine === captureRun) {
        setDockBusy(false);
        if (state.phase === "capturing") setPhase(state.shot ? "capture-ready" : "idle");
      }
    }
  }

  /* A failed capture keeps whatever the reviewer already had: the note, and
   * any screenshot from a previous attempt. */
  function captureFailed(why) {
    setPhase("capture-error");
    var tail = " Try again, import a screenshot, or carry on without one.";
    if (state.mode === "editor") {
      status(why + tail, "error");
    } else {
      state.mode = "editor";
      renderEditor();
      el.editor.hidden = false;
      status(why + tail, "error");
      focusEditor();
    }
    announce(why);
  }

  async function adoptCanvas(canvas) {
    if (state.shot && state.shot.url) URL.revokeObjectURL(state.shot.url);
    var blob = await new Promise(function (r) { canvas.toBlob(r, "image/png"); });
    var url = URL.createObjectURL(blob);
    /* The capture is in device pixels. Dividing by the CSS width of the
     * viewport gives the real ratio, which is not always devicePixelRatio:
     * the browser may hand back a downscaled surface. */
    var dpr = canvas.width / Math.max(1, window.innerWidth);
    if (!isFinite(dpr) || dpr <= 0) dpr = 1;
    state.shot = { url: url, width: canvas.width, height: canvas.height, dpr: dpr };
    state.marks = [];
    state.zoom = "fit";
    state.tool = "pan";
    state.source = readSource();
    scheduleExport();
    setPhase("capture-ready");
  }

  function importFile(file) {
    if (!file) return;
    var url = URL.createObjectURL(file);
    var img = new Image();
    img.onload = function () {
      var c = document.createElement("canvas");
      c.width = img.naturalWidth; c.height = img.naturalHeight;
      c.getContext("2d").drawImage(img, 0, 0);
      URL.revokeObjectURL(url);
      adoptCanvas(c).then(function () {
        if (state.mode !== "editor") openEditor(); else renderEditor();
        status("Imported screenshot. " + COPY.frozen, "ok");
        setPhase("capture-ready");
      });
    };
    img.onerror = function () {
      URL.revokeObjectURL(url);
      status("That file could not be read as an image. Try a PNG or JPEG.", "error");
    };
    img.src = url;
  }

  /* -------------------------------------------------------------- editor */

  function openEditor() {
    state.lastFocus = document.activeElement;
    state.mode = "editor";
    el.dock.hidden = true;
    if (el.intro) el.intro.hidden = true;
    el.launch.hidden = true;
    renderEditor();
    el.editor.hidden = false;
    if (state.prevOverflow === null) {
      state.prevOverflow = document.documentElement.style.overflow || "";
      document.documentElement.style.overflow = "hidden";
    }
    focusEditor();
  }

  function focusEditor() {
    setTimeout(function () {
      if (el.close) el.close.focus();
    }, 0);
  }

  function hasWork() {
    return !!(state.shot || state.marks.length || state.draft.trim());
  }

  /* Closing keeps the screenshot and the note. It used to ask "these will be
   * discarded" and then keep them anyway, which was both a lie and a reason
   * to hesitate. Discard is the button that throws work away, and it is the
   * one that asks. */
  function closeEditor() {
    /* A submission in flight owns the dialog. Closing here would leave the
     * confirmation poller running against an interface nobody can see, and
     * the reviewer would never learn what happened. */
    if (isBusy()) {
      status("Your feedback is being submitted. This will only take a moment.", null);
      announce("Your feedback is being submitted.");
      return;
    }
    state.mode = "closed";
    el.editor.hidden = true;
    if (state.prevOverflow !== null) {
      document.documentElement.style.overflow = state.prevOverflow;
      state.prevOverflow = null;
    }
    el.launch.hidden = false;
    placeLauncher();
    /* Whatever had focus when the editor opened is often the dock button,
     * which is hidden by the time we get back here; focusing a hidden node
     * silently does nothing and leaves the keyboard nowhere. */
    var back = state.lastFocus;
    var usable = back && document.contains(back) && back.offsetParent !== null;
    (usable ? back : el.launch).focus();
  }

  function resetAll() {
    if (isBusy()) return;
    if (hasWork() && !window.confirm(
      "Discard this screenshot, your marks, and your note?"
    )) return;
    if (state.shot && state.shot.url) URL.revokeObjectURL(state.shot.url);
    state.shot = null;
    state.marks = [];
    state.draft = "";
    state.exportBlob = null;
    /* A discarded draft is a different submission from here on. */
    state.submissionId = null;
    state.lastError = null;
    hideResult();
    renderEditor();
    setPhase("idle");
    status("Cleared.", null);
  }

  /* ------------------------------------------------------- preview layout */

  function scaleFor() {
    var s = state.shot;
    if (!s) return 1;
    var actual = 1 / s.dpr;                    /* natural px -> CSS px */
    if (state.zoom === "100") return actual;
    var box = el.preview.getBoundingClientRect();
    var padX = 24, padY = 24;
    var aw = Math.max(40, box.width - padX);
    var ah = Math.max(40, box.height - padY);
    return Math.min(aw / s.width, ah / s.height, actual);
  }

  function layoutStage() {
    var s = state.shot;
    if (!s || !el.stage) return;
    var scale = scaleFor();
    var w = Math.max(1, Math.round(s.width * scale));
    var h = Math.max(1, Math.round(s.height * scale));
    el.stage.style.width = w + "px";
    el.stage.style.height = h + "px";
    updateScrollHint();
  }

  function updateScrollHint() {
    if (!el.scrollhint || !el.preview) return;
    var over = el.preview.scrollWidth > el.preview.clientWidth + 2 ||
      el.preview.scrollHeight > el.preview.clientHeight + 2;
    el.scrollhint.hidden = !over;
  }

  /* ------------------------------------------------------------- marking */

  /* Pointer to capture coordinates. getBoundingClientRect is measured
   * after layout, after scrolling and after browser zoom, and clientX is
   * in the same units, so the ratio is correct in all three without ever
   * adding a scroll offset by hand. */
  function toImage(evt) {
    var s = state.shot;
    var r = el.svg.getBoundingClientRect();
    if (!s || !r.width || !r.height) return null;
    return {
      x: Math.min(1, Math.max(0, (evt.clientX - r.left) / r.width)),
      y: Math.min(1, Math.max(0, (evt.clientY - r.top) / r.height))
    };
  }

  function strokeWidth() {
    var s = state.shot;
    if (!s) return 3;
    return Math.max(2.5, Math.min(7, s.width * 0.0022));
  }

  function drawMarks(preview) {
    var s = state.shot;
    if (!s) return "";
    var sw = strokeWidth();
    var head = sw * 3.2;
    var parts = [];
    var list = state.marks.slice();
    if (preview && drag && drag.mark) list.push(drag.mark);
    list.forEach(function (m) {
      var x1 = m.x1 * s.width, y1 = m.y1 * s.height;
      var x2 = m.x2 * s.width, y2 = m.y2 * s.height;
      if (m.type === "rect") {
        var rx = Math.min(x1, x2), ry = Math.min(y1, y2);
        var rw = Math.abs(x2 - x1), rh = Math.abs(y2 - y1);
        parts.push('<rect x="' + rx + '" y="' + ry + '" width="' + rw +
          '" height="' + rh + '" fill="none" stroke="#FF4D4D" stroke-width="' +
          sw + '" />');
      } else {
        var dx = x2 - x1, dy = y2 - y1;
        var len = Math.sqrt(dx * dx + dy * dy) || 1;
        var ux = dx / len, uy = dy / len;
        var bx = x2 - ux * head, by = y2 - uy * head;
        var px = -uy * head * 0.42, py = ux * head * 0.42;
        parts.push('<line x1="' + x1 + '" y1="' + y1 + '" x2="' + bx +
          '" y2="' + by + '" stroke="#FF4D4D" stroke-width="' + sw +
          '" stroke-linecap="round" />');
        parts.push('<polygon points="' + x2 + ',' + y2 + ' ' +
          (bx + px) + ',' + (by + py) + ' ' + (bx - px) + ',' + (by - py) +
          '" fill="#FF4D4D" />');
      }
    });
    return parts.join("");
  }

  function paintOverlay() {
    if (!el.svg || !state.shot) return;
    el.svg.setAttribute("viewBox",
      "0 0 " + state.shot.width + " " + state.shot.height);
    el.svg.innerHTML = drawMarks(true);
  }

  function onPointerDown(e) {
    if (state.tool === "pan") return;          /* pan belongs to the browser */
    if (e.button != null && e.button !== 0) return;
    var p = toImage(e);
    if (!p) return;
    e.preventDefault();
    el.svg.setPointerCapture(e.pointerId);
    drag = {
      id: e.pointerId,
      mark: { type: state.tool === "rect" ? "rect" : "arrow",
              x1: p.x, y1: p.y, x2: p.x, y2: p.y }
    };
    paintOverlay();
  }

  function onPointerMove(e) {
    if (!drag || e.pointerId !== drag.id) return;
    var p = toImage(e);
    if (!p) return;
    drag.mark.x2 = p.x;
    drag.mark.y2 = p.y;
    paintOverlay();
  }

  function endDrag(e, cancelled) {
    if (!drag || (e && e.pointerId !== drag.id)) return;
    var m = drag.mark;
    var s = state.shot;
    drag = null;
    try { if (e) el.svg.releasePointerCapture(e.pointerId); } catch (_) {}
    if (!cancelled && s) {
      var dx = Math.abs(m.x2 - m.x1) * s.width;
      var dy = Math.abs(m.y2 - m.y1) * s.height;
      if (Math.sqrt(dx * dx + dy * dy) >= MIN_MARK) {
        state.marks.push(m);
        setPhase("editing");
        scheduleExport();
        announce(m.type === "rect" ? "Rectangle added." : "Arrow added.");
      }
    }
    paintOverlay();
    syncButtons();
  }

  /* ------------------------------------------------------------- exporting
     Built ahead of time and debounced, so the flatten is normally already
     finished by the time the reviewer presses Submit. settleExport()
     covers the case where it is not. */
  var exportTimer = 0;
  var exportWaiters = [];

  /* Resolves once the annotated flatten is available, or immediately if
   * there is nothing to flatten. Submission awaits this rather than
   * sending whatever happened to be ready, which is what stops a fast
   * Submit press from posting an unannotated screenshot. */
  function settleExport() {
    if (!state.shot) return Promise.resolve();
    if (state.exportBlob) return Promise.resolve();
    if (exportTimer) { clearTimeout(exportTimer); buildExport(); }
    return new Promise(function (resolve) {
      exportWaiters.push(resolve);
      /* A flatten that never completes must not hang the submission. */
      setTimeout(resolve, 8000);
    });
  }

  function flushExportWaiters() {
    var pending = exportWaiters;
    exportWaiters = [];
    pending.forEach(function (resolve) { resolve(); });
  }

  function scheduleExport() {
    if (exportTimer) clearTimeout(exportTimer);
    state.exportBlob = null;
    syncButtons();
    exportTimer = setTimeout(buildExport, 120);
  }

  function buildExport() {
    exportTimer = 0;
    var s = state.shot;
    if (!s) { state.exportBlob = null; flushExportWaiters(); syncButtons(); return; }
    if (state.phase === "capture-ready" || state.phase === "editing") setPhase("preparing");
    var img = new Image();
    img.onload = function () {
      var c = document.createElement("canvas");
      c.width = s.width; c.height = s.height;
      var ctx = c.getContext("2d");
      ctx.drawImage(img, 0, 0, s.width, s.height);
      /* The marks are drawn from the same normalised coordinates and the
       * same natural-pixel geometry the preview uses, over the whole
       * capture, so the export cannot differ from what was on screen and
       * cannot be cropped to the scrolled region. */
      var svg = '<svg xmlns="http://www.w3.org/2000/svg" width="' + s.width +
        '" height="' + s.height + '" viewBox="0 0 ' + s.width + ' ' +
        s.height + '">' + drawMarks(false) + "</svg>";
      var overlay = new Image();
      overlay.onload = function () {
        ctx.drawImage(overlay, 0, 0);
        c.toBlob(function (blob) {
          state.exportBlob = blob || null;
          state.exportName = "rate-card-feedback-" +
            slugFor(state.source) + "-" + stamp() + ".png";
          if (state.phase === "preparing") {
            setPhase(state.marks.length ? "editing" : "capture-ready");
          }
          if (blob && blob.size > MAX_EXPORT_BYTES) {
            status("The screenshot is " + (blob.size / 1048576).toFixed(1) +
              " MB. It will be resized before it is submitted.", null);
          }
          syncButtons();
          flushExportWaiters();
        }, "image/png");
      };
      overlay.onerror = function () {
        /* The annotations could not be flattened. Nothing is submitted in
         * that state: sending the plain capture would quietly drop the
         * marks the reviewer drew, which is worse than asking them to
         * try again. */
        state.exportBlob = null;
        setPhase("capture-error");
        status(
          "Your marks could not be flattened into the screenshot, so nothing " +
          "was prepared. Use Retake, or submit your note without a screenshot.",
          "error"
        );
        syncButtons();
        flushExportWaiters();
      };
      overlay.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);
    };
    img.onerror = function () {
      state.exportBlob = null;
      syncButtons();
      flushExportWaiters();
    };
    img.src = s.url;
  }

  function downloadExport() {
    if (!state.exportBlob) return false;
    var a = document.createElement("a");
    a.href = URL.createObjectURL(state.exportBlob);
    a.download = state.exportName;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    /* Give the download a tick to start before the URL goes away. */
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 60000);
    return true;
  }

  /* The emergency fallback text, used by Copy feedback when submission
   * cannot complete. Only the page they were looking at and what they
   * wrote: no query string, no ids, no local paths. */
  function feedbackText() {
    var s = state.source || readSource();
    var lines = ["Page: " + s.title];
    if (s.viewLabel) lines.push("View: " + s.viewLabel);
    if (s.stateLabel) lines.push("State: " + s.stateLabel);
    var note = (state.draft || "").trim();
    if (note) lines.push("Feedback: " + note);
    return lines.join("\n");
  }

  /* --------------------------------------------------------- submission
     One press, one POST, then confirmation by submission id. Every failure
     path leaves the note, the screenshot, and the marks exactly where they
     were, because the reviewer's work is the one thing this must never
     cost them. */

  function submissionFailed(title, message, kind) {
    state.lastError = message;
    if (kind === "demo") {
      /* Not a failure: the offline build has nowhere to send to, so the
       * chip and the status line stay neutral. */
      setPhase("demo-offline");
      showResult("auth", title, message);
      status(message, null);
      announce(message);
      return;
    }
    setPhase(kind === "auth" ? "auth-required" : "submission-error");
    showResult(kind === "auth" ? "auth" : "error", title, message);
    status(message, "error");
    announce(message);
  }

  /* The guard, the flag, and the safety net. Anything thrown below becomes
   * a reported failure rather than an unhandled rejection, and the flag is
   * always released so the interface can never be left stuck on Submitting.
   */
  async function submitFeedback() {
    if (state.submitInFlight || state.phase === "submitted") return;
    state.submitInFlight = true;
    syncButtons();
    try {
      await runSubmission();
    } catch (err) {
      submissionFailed(
        COPY.errorTitle,
        "Something went wrong while submitting. " + COPY.keptSafe,
        "error"
      );
      console.error("[feedback] submission failed", err);
    } finally {
      state.submitInFlight = false;
      syncButtons();
    }
  }

  async function runSubmission() {
    if (!CONFIG || !TRANSPORT) {
      submissionFailed(
        COPY.errorTitle,
        "The feedback submission module did not load. Reload the page and try again.",
        "error"
      );
      return;
    }
    if (!CONFIG.isConfigured) {
      /* Offline demo build: nothing is dispatched, so this is a normal
       * state rather than a failure. */
      submissionFailed(COPY.demoTitle, COPY.demoBody, "demo");
      return;
    }
    if (!state.draft.trim() && !state.shot) {
      status("Add a note or capture a screenshot before submitting.", "error");
      announce("Add a note or capture a screenshot before submitting.");
      return;
    }

    /* Reused across retries so the Web App can drop a duplicate. */
    if (!state.submissionId) state.submissionId = TRANSPORT.newSubmissionId();

    hideResult();
    setPhase("preparing");
    status("Preparing your feedback\u2026", null);
    announce("Preparing your feedback.");

    /* The flatten may still be debounced. Waiting here is what guarantees
     * the annotated version is the one that travels. */
    await settleExport();

    var shot = await TRANSPORT.prepareScreenshot(state.exportBlob);
    if (!shot.ok) {
      submissionFailed(COPY.errorTitle, shot.reason, "error");
      return;
    }

    var payload = TRANSPORT.buildPayload({
      submissionId: state.submissionId,
      feedback: state.draft,
      source: state.source || readSource(),
      section: readSection(),
      screenshotDataUrl: shot.dataUrl,
      screenshotFormat: shot.format,
      screenshotBytes: shot.bytes
    });

    setPhase("submitting");
    status(COPY.submitting, null);
    announce(COPY.submitting);

    var sent = await TRANSPORT.dispatch(payload);
    if (!sent.dispatched) {
      submissionFailed(
        COPY.errorTitle,
        "The submission could not be sent. " + (sent.reason || "") + " " + COPY.keptSafe,
        "error"
      );
      return;
    }

    setPhase("confirming");
    status(COPY.confirming, null);
    announce(COPY.confirming);

    /* The POST response is opaque, so the only way to learn whether the
     * request was even accepted is to ask over a channel we can read. If
     * that channel cannot reach the deployment either, the reviewer is
     * almost certainly not signed in, and saying so beats fifteen seconds
     * of waiting followed by a generic failure. */
    var auth = await TRANSPORT.probeAuth();
    if (!auth.authenticated) {
      submissionFailed(COPY.authTitle, COPY.authBody, "auth");
      return;
    }

    var confirmed = await TRANSPORT.confirm(state.submissionId, function (n, total) {
      status(COPY.confirming + " (" + n + " of " + total + ")", null);
    });

    if (confirmed.received) {
      submissionSucceeded();
      return;
    }
    if (confirmed.reason === "cancelled") return;
    if (!confirmed.everAnswered) {
      submissionFailed(COPY.authTitle, COPY.authBody, "auth");
      return;
    }
    submissionFailed(
      COPY.errorTitle,
      "The document did not confirm your submission in time. It may still " +
      "arrive. Try again in a moment, and your submission will not be " +
      "duplicated. " + COPY.keptSafe,
      "error"
    );
  }

  function submissionSucceeded() {
    state.lastError = null;
    setPhase("submitted");
    showResult("success", COPY.successTitle, COPY.successBody);
    status("", null);
    announce(COPY.successTitle + ". " + COPY.successBody);
  }

  /* Submit another keeps the screenshot, because the usual next comment is
   * about the same screen, and clears the note, the marks, and the
   * submission id so the next press is a genuinely new entry. */
  function submitAnother() {
    hideResult();
    state.draft = "";
    state.marks = [];
    state.submissionId = null;
    state.lastError = null;
    el.textarea.value = "";
    updateCount();
    if (state.shot) {
      paintOverlay();
      scheduleExport();
      setPhase("capture-ready");
    } else {
      setPhase("idle");
    }
    status("", null);
    renderResultVisibility();
    el.textarea.focus();
    announce("Ready for another submission.");
  }

  function retrySubmission() {
    /* Deliberately does not mint a new submission id. If the first POST
     * did land, the Web App drops this one as a duplicate and the document
     * keeps exactly one entry. */
    hideResult();
    submitFeedback();
  }

  function openSignIn() {
    if (!CONFIG.isConfigured) {
      status(CONFIG.configurationProblem, "error");
      return;
    }
    window.open(CONFIG.GOOGLE_FEEDBACK_WEB_APP_URL, "_blank", "noopener");
    status(
      "Complete sign in in the new tab, then select Try again. " +
      "Your note, screenshot, and marks are still here.",
      null
    );
  }

  /* ----------------------------------------------------------- result card
     One card carries all three terminal states. It replaces the draft and
     context cards rather than appearing beneath them, so the panel never
     grows and the dialog never shifts under the reviewer. */

  var RESULT_ICON = {
    success: "\u2713",
    auth: "\u21AA",
    error: "!"
  };

  function showResult(kind, title, message) {
    if (!el.result) return;
    el.result.setAttribute("data-kind", kind);
    el.resultIcon.textContent = RESULT_ICON[kind] || "";
    el.resultTitle.textContent = title;
    el.resultBody.textContent = message;
    /* No endpoint in the offline demo build, so there is nothing to sign
     * in to and the button stays out of the row. */
    el.resultSignIn.hidden = kind !== "auth" || !CONFIG.isConfigured;
    el.resultRetry.hidden = kind === "success" || !CONFIG.isConfigured;
    el.resultCopy.hidden = kind === "success";
    el.resultAnother.hidden = kind !== "success";
    renderResultVisibility();
    /* Focus the action the reviewer is most likely to want next, without
     * yanking them out of the dialog. */
    var next = kind === "success" ? el.resultAnother
      : (kind === "auth" && CONFIG.isConfigured) ? el.resultSignIn
        : !CONFIG.isConfigured ? el.resultCopy : el.resultRetry;
    if (next && !next.hidden) setTimeout(function () { next.focus(); }, 0);
  }

  function hideResult() {
    if (!el.result) return;
    el.result.removeAttribute("data-kind");
    renderResultVisibility();
  }

  /* The single place panel visibility is decided, driven by phase and
   * never by a stray class. */
  function renderResultVisibility() {
    if (!el.result) return;
    var showing = !!el.result.getAttribute("data-kind");
    el.result.hidden = !showing;
    var success = el.result.getAttribute("data-kind") === "success";
    /* On success the composer is put away so the confirmation is the only
     * thing in the panel. On a failure the note stays visible and editable,
     * because that is the reviewer's work and they may want to copy it. */
    el.draftCard.hidden = success;
    el.metaCard.hidden = success;
    el.submit.hidden = success;
    el.discard.hidden = success;
  }

  /* ------------------------------------------------------------ clipboard */

  function copyText(text, label) {
    if (!text) return;
    function ok() { status("Copied " + label + ".", "ok"); announce("Copied " + label); }
    function fail() {
      /* Never claim success. Put the text somewhere selectable instead. */
      el.fallback.value = text;
      el.fallbackWrap.hidden = false;
      el.fallback.focus();
      el.fallback.select();
      status("Clipboard is blocked. The text is selected above, copy it manually.",
        "error");
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(ok, fail);
    } else fail();
  }

  /* ----------------------------------------------------------------- build */

  function buildBackstageNote() {
    var note = make("p", "rcf-callout");
    var icon = make("span", "rcf-callout__icon", "\u2726");
    icon.setAttribute("aria-hidden", "true");
    var text = make("span", "rcf-callout__text");
    function say(s) { text.appendChild(document.createTextNode(s)); }
    if (!CONFIG.isConfigured) {
      say("Portfolio preview: mark up the screenshot and add your note. " +
        "Submission is disabled here, so use ");
      text.appendChild(make("strong", "rcf-callout__key", "Copy feedback"));
      say(" or ");
      text.appendChild(make("strong", "rcf-callout__key", "Download screenshot"));
      say(" to keep your notes.");
    } else {
      say("Mark up the screenshot, add your note, then hit ");
      text.appendChild(make("strong", "rcf-callout__key", "Submit feedback"));
      say(" in the bottom-right.");
    }
    note.appendChild(icon);
    note.appendChild(text);
    return note;
  }

  function build() {
    var root = make("div", "rcf-root");
    root.setAttribute("data-rcf-root", "");

    el.launch = buildLauncher();
    root.appendChild(el.launch);

    /* Ambient light behind the corner widget. It is a sibling rather than
     * a pseudo-element on the launcher or the card for two reasons: one
     * layer means one animation clock, so the breathing never restarts or
     * falls out of step when the card opens, and it cannot be clipped by
     * the card's own scroll container. Decorative only, so it is hidden
     * from assistive technology and takes no pointer events. */
    el.glow = make("div", "rcf-glow");
    el.glow.setAttribute("aria-hidden", "true");
    root.appendChild(el.glow);

    el.live = make("div", "rcf-sr");
    el.live.setAttribute("aria-live", "polite");
    root.appendChild(el.live);

    /* ---- live dock (non-modal on purpose) ---- */
    el.dock = make("div", "rcf-dock");
    el.dock.hidden = true;
    el.dock.setAttribute("role", "region");
    el.dock.setAttribute("aria-label", "Feedback, live view");
    var tag = make("span", "rcf-dock__tag", "Live view");
    el.dockCapture = btn("Capture this view", "rcf-btn--primary");
    el.dockCapture.addEventListener("click", function (e) {
      e.stopPropagation(); doCapture();
    });
    var dockImport = btn("Import", null, "Import an existing screenshot");
    dockImport.addEventListener("click", function (e) {
      e.stopPropagation(); el.file.click();
    });
    var dockNote = btn("Write note only", "rcf-btn--quiet");
    dockNote.addEventListener("click", function (e) {
      e.stopPropagation(); openEditor();
    });
    var dockClose = btn("\u2715", "rcf-btn--quiet rcf-btn--icon rcf-dock__close",
      "Close feedback");
    dockClose.addEventListener("click", function (e) {
      e.stopPropagation(); closeLive();
    });
    var hint = make("span", "rcf-dock__hint",
      "Scroll to the part you mean, then capture.");
    el.dock.appendChild(tag);
    el.dock.appendChild(hint);
    el.dock.appendChild(el.dockCapture);
    el.dock.appendChild(dockImport);
    el.dock.appendChild(dockNote);
    el.dock.appendChild(dockClose);
    root.appendChild(el.dock);

    /* The introduction belongs at the moment the feature opens, not
     * buried in the editor: the reviewer should know who is asking and
     * what for before they start hunting for something to report. It
     * collapses into the dock as soon as they begin, so it is never in
     * the way of the view they are trying to inspect. */
    el.intro = make("div", "rcf-intro-card");
    el.intro.hidden = true;
    el.intro.setAttribute("role", "dialog");
    el.intro.setAttribute("aria-label", "Share feedback");
    el.intro.appendChild(make("p", "rcf-intro__head", CARD_COPY.head));
    el.intro.appendChild(make("p", "rcf-intro__body", CARD_COPY.body));
    el.intro.appendChild(make("p", "rcf-intro__emphasis", CARD_COPY.emphasis));
    el.intro.appendChild(make("p", "rcf-intro__sign", COPY.sign));
    el.intro.appendChild(make("p", "rcf-intro__reassurance", CARD_COPY.reassurance));
    var introRow = make("div", "rcf-intro-card__row");
    el.introGo = btn("Start inspecting", "rcf-btn--primary");
    el.introGo.addEventListener("click", function (e) {
      e.stopPropagation();
      el.intro.hidden = true;
      el.dock.hidden = false;
      placeLauncher();
      el.dockCapture.focus();
    });
    var introClose = btn("Not now", "rcf-btn--quiet");
    introClose.addEventListener("click", function (e) {
      e.stopPropagation(); el.intro.hidden = true; closeLive();
    });
    introRow.appendChild(el.introGo);
    introRow.appendChild(introClose);
    el.intro.appendChild(introRow);
    el.intro.addEventListener("pointerdown", function (e) { e.stopPropagation(); });
    el.intro.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { e.stopPropagation(); el.intro.hidden = true; closeLive(); }
    });
    root.appendChild(el.intro);

    el.file = document.createElement("input");
    el.file.type = "file";
    el.file.accept = "image/*";
    el.file.className = "rcf-sr";
    el.file.addEventListener("change", function () {
      if (el.file.files && el.file.files[0]) importFile(el.file.files[0]);
      el.file.value = "";
    });
    root.appendChild(el.file);

    /* ---- editor ---- */
    el.editor = make("div", "rcf-editor");
    el.editor.hidden = true;

    el.dialog = make("div", "rcf-dialog");
    el.dialog.setAttribute("role", "dialog");
    el.dialog.setAttribute("aria-modal", "true");
    el.dialog.setAttribute("aria-label", "Feedback editor");

    var head = make("div", "rcf-head");
    el.stateTag = make("span", "rcf-state", PHASE_LABEL.idle);
    el.headTitle = make("h2", "rcf-head__title", "Share feedback");
    el.close = btn("\u2715", "rcf-btn--quiet rcf-btn--icon", "Close feedback");
    el.close.addEventListener("click", function () { closeEditor(); });
    head.appendChild(el.headTitle);
    head.appendChild(el.stateTag);
    head.appendChild(el.close);

    var body = make("div", "rcf-body");
    var main = make("div", "rcf-main");

    /* toolbar */
    var tb = make("div", "rcf-toolbar");
    el.toolPan = btn("Pan", null, "Pan and inspect");
    el.toolArrow = btn("Arrow", null, "Draw an arrow");
    el.toolRect = btn("Rectangle", null, "Draw an outline rectangle");
    [["pan", el.toolPan], ["arrow", el.toolArrow], ["rect", el.toolRect]]
      .forEach(function (pair) {
        pair[1].setAttribute("aria-pressed", "false");
        pair[1].addEventListener("click", function () {
          state.tool = pair[0];
          if (el.stage) el.stage.setAttribute("data-tool", pair[0]);
          syncButtons();
          announce(pair[0] === "pan" ? "Pan mode" : pair[0] + " tool");
        });
      });
    el.undo = btn("Undo", null, "Undo the last mark");
    el.undo.addEventListener("click", function () {
      if (!state.marks.length) return;
      state.marks.pop(); paintOverlay(); scheduleExport(); syncButtons();
      announce("Mark removed.");
    });
    el.clear = btn("Clear", null, "Clear all marks");
    el.clear.addEventListener("click", function () {
      if (!state.marks.length) return;
      if (!window.confirm("Remove all marks from this screenshot?")) return;
      state.marks = []; paintOverlay(); scheduleExport(); syncButtons();
      announce("All marks removed.");
    });
    el.zoomFit = btn("Fit", null, "Fit the whole screenshot");
    el.zoomFit.addEventListener("click", function () { setZoom("fit"); });
    el.zoom100 = btn("100%", null, "Show at actual size");
    el.zoom100.addEventListener("click", function () { setZoom("100"); });
    el.retake = btn("Retake", null, "Retake the screenshot");
    el.retake.addEventListener("click", function () {
      if (state.marks.length && !window.confirm(
        "Retake the screenshot? Your marks will be discarded. Your note is kept."
      )) return;
      state.marks = [];
      state.mode = "live";
      el.editor.hidden = true;
      if (state.prevOverflow !== null) {
        document.documentElement.style.overflow = state.prevOverflow;
        state.prevOverflow = null;
      }
      el.dock.hidden = false;
      placeLauncher();
      el.dockCapture.focus();
    });
    tb.appendChild(el.toolPan);
    tb.appendChild(el.toolArrow);
    tb.appendChild(el.toolRect);
    tb.appendChild(make("span", "rcf-toolbar__sep"));
    tb.appendChild(el.undo);
    tb.appendChild(el.clear);
    tb.appendChild(make("span", "rcf-toolbar__sep"));
    tb.appendChild(el.zoomFit);
    tb.appendChild(el.zoom100);
    tb.appendChild(make("span", "rcf-toolbar__spacer"));
    tb.appendChild(el.retake);
    main.appendChild(tb);

    el.scrollhint = make("div", "rcf-scrollhint",
      "Scroll to inspect \u2014 drag with Pan, or use the scrollbars.");
    el.scrollhint.hidden = true;
    main.appendChild(el.scrollhint);

    el.preview = make("div", "rcf-preview");
    el.preview.setAttribute("tabindex", "0");
    el.preview.setAttribute("role", "group");
    el.preview.setAttribute("aria-label", "Screenshot preview");
    main.appendChild(el.preview);
    body.appendChild(main);

    /* side panel */
    el.side = make("div", "rcf-side");

    var intro = make("div", "rcf-intro");
    intro.appendChild(make("p", "rcf-intro__head", COPY.head));
    intro.appendChild(make("p", "rcf-intro__body", COPY.body));
    intro.appendChild(make("p", "rcf-intro__sign", COPY.sign));
    intro.appendChild(buildBackstageNote());
    el.side.appendChild(intro);

    var draftCard = make("div", "rcf-card");
    el.draftCard = draftCard;
    var label = make("label", "rcf-field__label", "What could be better?");
    label.setAttribute("for", "rcf-draft");
    el.textarea = make("textarea", "rcf-textarea");
    el.textarea.id = "rcf-draft";
    el.textarea.placeholder = "Tell me what you noticed and how it could improve.";
    el.textarea.addEventListener("compositionstart", function () {
      state.composing = true;
    });
    el.textarea.addEventListener("compositionend", function () {
      state.composing = false;
      enforceLimit();
    });
    el.textarea.addEventListener("input", function () {
      /* Never cut a half-formed IME string: wait for compositionend. */
      if (state.composing) { updateCount(); return; }
      enforceLimit();
    });
    el.count = make("span", "rcf-count", "0 / " + MAX_CHARS);
    el.copyDraft = btn("Copy feedback", null, "Copy your note and page details");
    el.copyDraft.addEventListener("click", function () {
      copyText(feedbackText(), "your feedback");
    });
    draftCard.appendChild(label);
    draftCard.appendChild(el.textarea);
    draftCard.appendChild(el.count);
    draftCard.appendChild(make("p", "rcf-note", COPY.sendTogether));
    draftCard.appendChild(el.copyDraft);
    el.side.appendChild(draftCard);

    var metaCard = make("div", "rcf-card");
    el.metaCard = metaCard;
    el.meta = make("p", "rcf-meta", "");
    el.copyMeta = btn("Copy page details", null, "Copy the page details");
    el.copyMeta.addEventListener("click", function () {
      var s = state.source || readSource();
      var lines = ["Page: " + s.title];
      if (s.viewLabel) lines.push("View: " + s.viewLabel);
      if (s.stateLabel) lines.push("State: " + s.stateLabel);
      copyText(lines.join("\n"), "the page details");
    });
    metaCard.appendChild(el.meta);
    metaCard.appendChild(el.copyMeta);
    el.side.appendChild(metaCard);

    el.fallbackWrap = make("div", "rcf-card");
    el.fallbackWrap.hidden = true;
    el.fallbackWrap.appendChild(make("p", "rcf-note",
      "Clipboard access was refused. Select the text below and copy it."));
    el.fallback = make("textarea", "rcf-textarea");
    el.fallback.readOnly = true;
    el.fallbackWrap.appendChild(el.fallback);
    el.side.appendChild(el.fallbackWrap);

    /* The one card that reports the outcome. Hidden until there is one.
     * assertive rather than polite: a reviewer who has just pressed Submit
     * is waiting on precisely this sentence. */
    el.result = make("div", "rcf-card rcf-result");
    el.result.hidden = true;
    el.result.setAttribute("role", "alert");
    el.result.setAttribute("aria-live", "assertive");
    var resultHead = make("div", "rcf-result__head");
    el.resultIcon = make("span", "rcf-result__icon");
    el.resultIcon.setAttribute("aria-hidden", "true");
    el.resultTitle = make("p", "rcf-result__title", "");
    resultHead.appendChild(el.resultIcon);
    resultHead.appendChild(el.resultTitle);
    el.resultBody = make("p", "rcf-result__body", "");
    var resultRow = make("div", "rcf-result__row");
    el.resultAnother = btn("Submit another", "rcf-btn--primary");
    el.resultAnother.addEventListener("click", submitAnother);
    el.resultRetry = btn("Try again", "rcf-btn--primary");
    el.resultRetry.addEventListener("click", retrySubmission);
    el.resultSignIn = btn("Sign in", null,
      "Open the sign-in page for feedback submission");
    el.resultSignIn.addEventListener("click", openSignIn);
    el.resultCopy = btn("Copy feedback", null, "Copy your note and page details");
    el.resultCopy.addEventListener("click", function () {
      copyText(feedbackText(), "your feedback");
    });
    resultRow.appendChild(el.resultAnother);
    resultRow.appendChild(el.resultRetry);
    resultRow.appendChild(el.resultSignIn);
    resultRow.appendChild(el.resultCopy);
    el.result.appendChild(resultHead);
    el.result.appendChild(el.resultBody);
    el.result.appendChild(resultRow);
    el.side.appendChild(el.result);

    body.appendChild(el.side);

    /* foot */
    var foot = make("div", "rcf-foot");
    el.status = make("p", "rcf-status", "");
    el.status.setAttribute("role", "status");
    el.discard = btn("Discard", "rcf-btn--quiet", "Discard this feedback");
    el.discard.addEventListener("click", resetAll);
    el.download = btn("Download screenshot", null, "Download the annotated screenshot");
    el.download.addEventListener("click", function () {
      if (downloadExport()) status("Screenshot downloaded.", null);
    });
    /* The real submission. One press sends the note and the annotated
     * screenshot to the feedback document; nothing is handed off anywhere
     * else. A fixed minimum width keeps the label changing between
     * Submit, Submitting and Confirming without the footer twitching. */
    el.submit = btn("Submit feedback", "rcf-btn--primary rcf-btn--submit");
    el.submit.addEventListener("click", submitFeedback);
    foot.appendChild(el.status);
    foot.appendChild(el.discard);
    foot.appendChild(make("span", "rcf-foot__spacer"));
    foot.appendChild(el.download);
    foot.appendChild(el.submit);

    el.dialog.appendChild(head);
    el.dialog.appendChild(body);
    el.dialog.appendChild(foot);
    el.editor.appendChild(el.dialog);
    root.appendChild(el.editor);

    document.body.appendChild(root);
    el.root = root;

    /* Keys typed inside the editor must never reach the deck's document
     * handler, or Space and the arrows would move slides underneath. The
     * listener is on the editor, in the bubble phase, so the textarea and
     * the buttons still see everything first. */
    el.editor.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { e.stopPropagation(); closeEditor(); return; }
      if (e.key === "Tab") { trapTab(e); return; }
      var deckKeys = ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown",
        " ", "Spacebar", "PageUp", "PageDown", "Home", "End", "Enter"];
      if (deckKeys.indexOf(e.key) !== -1) e.stopPropagation();
    });
    el.dock.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { e.stopPropagation(); closeLive(); }
    });
    /* A click on the backdrop is a close request, same as the X. */
    el.editor.addEventListener("click", function (e) {
      if (e.target === el.editor) closeEditor();
    });
    el.editor.addEventListener("pointerdown", function (e) { e.stopPropagation(); });
    el.dock.addEventListener("pointerdown", function (e) { e.stopPropagation(); });
  }

  function trapTab(e) {
    var focusables = el.dialog.querySelectorAll(
      'button:not(:disabled), a[href], textarea, input, [tabindex]:not([tabindex="-1"])'
    );
    var list = Array.prototype.filter.call(focusables, function (n) {
      return n.offsetParent !== null || n === document.activeElement;
    });
    if (!list.length) return;
    var first = list[0], last = list[list.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault(); last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault(); first.focus();
    }
  }

  /* ------------------------------------------------------------- rendering */

  function enforceLimit() {
    var raw = el.textarea.value;
    var cut = clampGraphemes(raw, MAX_CHARS);
    if (cut !== raw) {
      var pos = el.textarea.selectionStart;
      el.textarea.value = cut;
      try { el.textarea.setSelectionRange(Math.min(pos, cut.length), Math.min(pos, cut.length)); }
      catch (_) {}
    }
    state.draft = el.textarea.value;
    updateCount();
    syncButtons();
  }

  function updateCount() {
    var n = graphemes(el.textarea.value).length;
    el.count.textContent = n + " / " + MAX_CHARS;
    el.count.setAttribute("data-over", n > MAX_CHARS ? "true" : "false");
  }

  function setZoom(z) {
    if (state.zoom === z) return;
    /* Keep the middle of the view roughly where it was so switching size
     * does not throw away the reviewer's place. Marks are normalised, so
     * nothing about them changes here. */
    var p = el.preview;
    var cx = (p.scrollLeft + p.clientWidth / 2) / Math.max(1, p.scrollWidth);
    var cy = (p.scrollTop + p.clientHeight / 2) / Math.max(1, p.scrollHeight);
    state.zoom = z;
    layoutStage();
    requestAnimationFrame(function () {
      p.scrollLeft = cx * p.scrollWidth - p.clientWidth / 2;
      p.scrollTop = cy * p.scrollHeight - p.clientHeight / 2;
      updateScrollHint();
    });
    syncButtons();
  }

  function syncButtons() {
    var hasShot = !!state.shot;
    el.toolPan.setAttribute("aria-pressed", String(state.tool === "pan"));
    el.toolArrow.setAttribute("aria-pressed", String(state.tool === "arrow"));
    el.toolRect.setAttribute("aria-pressed", String(state.tool === "rect"));
    el.zoomFit.setAttribute("aria-pressed", String(state.zoom === "fit"));
    el.zoom100.setAttribute("aria-pressed", String(state.zoom === "100"));
    [el.toolArrow, el.toolRect, el.zoomFit, el.zoom100, el.retake]
      .forEach(function (b) { b.disabled = !hasShot; });
    el.toolPan.disabled = !hasShot;
    el.undo.disabled = !state.marks.length;
    el.clear.disabled = !state.marks.length;
    el.download.disabled = !state.exportBlob;
    el.copyDraft.disabled = false;
    el.download.hidden = !hasShot;

    /* Submission is blocked only while it is already running, so a second
     * press cannot start a second attempt or a second document entry. */
    var busy = isBusy();
    el.submit.disabled = busy;
    el.submit.setAttribute("aria-busy", busy ? "true" : "false");
    el.submit.textContent =
      state.phase === "submitting" ? COPY.submitting
        : state.phase === "confirming" ? COPY.confirming
          : state.phase === "preparing" ? "Preparing\u2026"
            : "Submit feedback";
    /* Discarding or retaking mid-flight would strand a request that is
     * already on its way to the document. */
    el.discard.disabled = busy;
    el.retake.disabled = busy || !hasShot;
    el.toolPan.disabled = busy || !hasShot;
    [el.toolArrow, el.toolRect, el.zoomFit, el.zoom100]
      .forEach(function (b) { b.disabled = busy || !hasShot; });
    el.undo.disabled = busy || !state.marks.length;
    el.clear.disabled = busy || !state.marks.length;
    el.textarea.readOnly = busy;
  }

  function renderEditor() {
    var s = state.shot;
    el.preview.innerHTML = "";
    if (s) {
      el.stage = make("div", "rcf-stage");
      el.stage.setAttribute("data-tool", state.tool);
      var img = new Image();
      img.src = s.url;
      img.alt = "Captured screenshot of the prototype";
      el.svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      el.svg.setAttribute("viewBox", "0 0 " + s.width + " " + s.height);
      el.svg.setAttribute("preserveAspectRatio", "none");
      el.svg.addEventListener("pointerdown", onPointerDown);
      el.svg.addEventListener("pointermove", onPointerMove);
      el.svg.addEventListener("pointerup", function (e) { endDrag(e, false); });
      el.svg.addEventListener("pointercancel", function (e) { endDrag(e, true); });
      el.stage.appendChild(img);
      el.stage.appendChild(el.svg);
      el.preview.appendChild(el.stage);
      layoutStage();
      paintOverlay();
    } else {
      el.stage = null; el.svg = null;
      var empty = make("div", "rcf-empty");
      empty.appendChild(make("p", null,
        "No screenshot yet. Capture the view, import an image, or just write a note."));
      var cap = btn("Capture this view", "rcf-btn--primary");
      cap.addEventListener("click", function () {
        el.editor.hidden = true;
        state.mode = "live";
        doCapture();
      });
      var imp = btn("Import screenshot");
      imp.addEventListener("click", function () { el.file.click(); });
      var row = make("div");
      row.style.cssText = "display:flex;gap:8px;justify-content:center;margin-top:10px;flex-wrap:wrap";
      row.appendChild(cap); row.appendChild(imp);
      empty.appendChild(row);
      el.preview.appendChild(empty);
      el.scrollhint.hidden = true;
    }
    var src = state.source || readSource();
    el.meta.innerHTML = "";
    el.meta.appendChild(document.createTextNode("Captured from "));
    var strong = make("strong", null, src.title);
    el.meta.appendChild(strong);
    el.meta.appendChild(document.createTextNode(" (" + src.label + ")"));
    el.textarea.value = state.draft;
    updateCount();
    renderResultVisibility();
    syncButtons();
  }

  /* ------------------------------------------------------------ lifecycle */

  function onResize() {
    placeLauncher();
    if (state.mode === "editor" && state.shot) {
      layoutStage();
      paintOverlay();
    }
  }

  function start() {
    if (document.querySelector("[data-rcf-root]")) return;   /* exactly one */
    build();
    placeLauncher();

    window.addEventListener("resize", onResize);
    window.addEventListener("orientationchange", onResize);
    if (window.visualViewport) {
      window.visualViewport.addEventListener("resize", onResize);
    }
    if (typeof ResizeObserver === "function") {
      new ResizeObserver(function () {
        if (state.mode === "editor" && state.shot) { layoutStage(); paintOverlay(); }
      }).observe(el.preview);
    }
    /* The prototype swaps routes by flipping data-route rather than
     * reloading, so the corner can change owner without a resize. */
    new MutationObserver(function () { placeLauncher(); })
      .observe(document.body, { attributes: true, attributeFilter: ["data-route"] });

    /* If anything ever puts the app into element fullscreen, a body-level
     * fixed element stops being painted. Move the whole feature inside
     * the fullscreen element and put it back afterwards. */
    document.addEventListener("fullscreenchange", function () {
      var fs = document.fullscreenElement;
      if (fs && fs !== document.documentElement && !fs.contains(el.root)) {
        fs.appendChild(el.root);
      } else if (!fs && el.root.parentNode !== document.body) {
        document.body.appendChild(el.root);
      }
      placeLauncher();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
