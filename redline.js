(function () {
  "use strict";

  var PREVIEW_PARAM = "redlinePreview";
  // The project's supported QA viewports. Labels are derived from these
  // values so the sidebar, header readout, and status can never disagree.
  var BREAKPOINTS = [
    { id: "320", width: 320, height: 568 },
    { id: "375", width: 375, height: 667 },
    { id: "768", width: 768, height: 1024 },
    { id: "1024", width: 1024, height: 760 },
    { id: "1280", width: 1280, height: 800 },
    { id: "1440", width: 1440, height: 900 },
    { id: "1920", width: 1920, height: 1080 },
    { id: "2560", width: 2560, height: 1440 }
  ];
  var MEASUREMENT_MODES = [
    {
      id: "clean",
      label: "Clean Spec",
      hint: "Shows actual rounded values."
    },
    {
      id: "grid",
      label: "8pt Grid",
      hint: "Shows the nearest 8pt grid value."
    }
  ];
  // Redline is in exactly one of these at a time. The galleries are extra
  // inspection modes layered on the same shell, not a separate tool.
  var PREVIEW_MODES = {
    CURRENT: "current-page",
    MODAL: "modal-gallery",
    TOAST: "toast-gallery",
    // A component specimen, not an overlay: the Action Bar is a piece of
    // the table, so it is staged in place rather than floated over a page.
    ACTION_BAR: "action-bar"
  };
  var GALLERY_ENTRY_ROWS = [
    { mode: PREVIEW_MODES.MODAL, label: "Modals", aria: "Open modal gallery" },
    { mode: PREVIEW_MODES.TOAST, label: "Toasts", aria: "Open toast gallery" }
  ];
  // Table components, listed apart from the overlay galleries because
  // they are permanent parts of a screen rather than things that appear
  // over one. Same entry behavior, same staging path.
  var COMPONENT_ENTRY_ROWS = [
    {
      mode: PREVIEW_MODES.ACTION_BAR,
      label: "Action Bar",
      aria: "Inspect the table Action Bar"
    }
  ];
  function entryRowFor(mode) {
    return GALLERY_ENTRY_ROWS.concat(COMPONENT_ENTRY_ROWS).find(function (row) {
      return row.mode === mode;
    }) || null;
  }
  var EMPTY_SELECTION = "Nothing selected.";
  var INSPECTOR_EMPTY = [
    "Hover or click a component in the preview to inspect it.",
    "Click again to clear the selection."
  ];
  var SVG_NS = "http://www.w3.org/2000/svg";
  var state = {
    active: false,
    root: null,
    frameShell: null,
    frame: null,
    frameDocument: null,
    aborter: null,
    resizeObserver: null,
    mutationObserver: null,
    parentObserver: null,
    frameLoadHandler: null,
    frameFontHandler: null,
    raf: 0,
    hovered: null,
    locked: null,
    lastFocus: null,
    breakpoint: "",
    previewScale: 1,
    // Measurement mode is a single choice (segmented control): "clean"
    // reports rounded actual CSS pixels, "grid" reports the nearest 8pt
    // recommendation. Kept separate from the annotation toggles below so
    // switching interpretation never changes what is drawn.
    measurementMode: "clean",
    // Annotation toggles are independent of the measurement mode.
    showLines: true,
    showGridOverlay: false,
    typography: false,
    color: false,
    renderCount: 0,
    storageSnapshot: null,
    // Serialized copy of the screen the user entered from, replayed into
    // the preview once it boots (see the UI state bridge in app.js).
    appSnapshot: null,
    appSnapshotApplied: false,
    previewPhase: "idle",
    previewToken: 0,
    previewTimer: 0,
    // Overlay gallery. previewMode is the active Redline mode; the entry
    // list is read from the product's own registry inside the preview.
    previewMode: PREVIEW_MODES.CURRENT,
    galleryEntries: [],
    galleryIndex: 0,
    galleryStaging: false,
    currentListenersAttached: false,
    frameListenersDoc: null,
    colorPanel: null,
    colorPanelTarget: undefined,
    colorSections: null,
    colorSheetCache: null,
    colorSheetCacheDoc: null,
    colorSheetTextCache: null,
    colorSheetWarming: null
  };

  function isPreview() {
    return new URLSearchParams(location.search).get(PREVIEW_PARAM) === "1";
  }

  function isEditable(target) {
    if (!target || target.nodeType !== 1) return false;
    return Boolean(target.closest(
      "input, textarea, select, [contenteditable]:not([contenteditable='false']), " +
      "[role='textbox'], .CodeMirror, .monaco-editor, .ace_editor"
    ));
  }

  function syncMenuState() {
    document.querySelectorAll('[data-action="toggle-redline"]').forEach(function (item) {
      item.setAttribute("aria-checked", state.active ? "true" : "false");
    });
  }

  function previewUrl() {
    var url = new URL(location.href);
    url.searchParams.set(PREVIEW_PARAM, "1");
    return url.toString();
  }

  // The badge mirrors the version the application itself is running
  // (body[data-version]); Redline never invents its own version label.
  function versionBadgeText() {
    var version = document.body && document.body.dataset
      ? document.body.dataset.version
      : "";
    return version ? "Rate Card V" + version : "Rate Card";
  }

  function measurementHint(mode) {
    var found = MEASUREMENT_MODES.find(function (item) {
      return item.id === mode;
    });
    return found ? found.hint : "";
  }

  function element(tag, className, attributes) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    Object.keys(attributes || {}).forEach(function (name) {
      node.setAttribute(name, attributes[name]);
    });
    node.setAttribute("data-redline-ui", "");
    return node;
  }

  function sectionLabel(text) {
    var node = element("h2", "redline__section-label");
    node.textContent = text;
    return node;
  }

  function section(name, labelText) {
    var node = element("section", "redline__section", {
      "data-redline-section": name
    });
    node.appendChild(sectionLabel(labelText));
    return node;
  }

  function divider() {
    return element("div", "redline__divider", { "aria-hidden": "true" });
  }

  function checkboxRow(labelText, action, checked) {
    var wrap = element("label", "redline__checkbox");
    var input = element("input", "redline__checkbox-input", {
      type: "checkbox",
      "data-redline-action": action
    });
    input.checked = Boolean(checked);
    var text = element("span", "redline__checkbox-label");
    text.textContent = labelText;
    wrap.appendChild(input);
    wrap.appendChild(text);
    return wrap;
  }

  /* One row per staged surface, shared by the overlay galleries and the
   * table components so both read and behave identically in the panel. */
  function entryList(rows, label) {
    var list = element("div", "redline__overlay-list", {
      role: "group",
      "aria-label": label
    });
    rows.forEach(function (entry) {
      var row = element("button", "redline__overlay-entry", {
        type: "button",
        "data-redline-action": "gallery:" + entry.mode,
        "aria-label": entry.aria,
        "aria-pressed": "false",
        title: entry.aria
      });
      var name = element("span", "redline__overlay-entry-name");
      name.textContent = entry.label;
      var chevron = element("span", "redline__overlay-entry-chevron", {
        "aria-hidden": "true"
      });
      chevron.textContent = "\u203a";
      row.appendChild(name);
      row.appendChild(chevron);
      list.appendChild(row);
    });
    return list;
  }

  function buildHeader() {
    var header = element("header", "redline__header");
    var left = element("div", "redline__header-side");
    // Only rendered at narrow host widths, where the panels become drawers.
    var leftToggle = element("button", "redline__panel-toggle", {
      type: "button",
      "data-redline-action": "panel:left",
      "aria-expanded": "false",
      "aria-label": "Show Redline controls",
      title: "Show Redline controls"
    });
    leftToggle.textContent = "\u2630";
    left.appendChild(leftToggle);
    var title = element("span", "redline__title");
    title.textContent = "Redline Mode";
    var badge = element("span", "redline__badge", {
      "data-redline-version-badge": ""
    });
    badge.textContent = versionBadgeText();
    left.appendChild(title);
    left.appendChild(badge);

    var right = element("div", "redline__header-side redline__header-side--end");
    var viewport = element("span", "redline__viewport-info", {
      "data-redline-viewport-info": ""
    });
    var close = element("button", "redline__close", {
      type: "button",
      "data-redline-action": "close",
      "aria-label": "Close Redline Mode",
      title: "Close Redline Mode"
    });
    close.textContent = "\u00d7";
    var rightToggle = element("button", "redline__panel-toggle", {
      type: "button",
      "data-redline-action": "panel:right",
      "aria-expanded": "false",
      "aria-label": "Show component inspector",
      title: "Show component inspector"
    });
    rightToggle.textContent = "\u2139";
    right.appendChild(viewport);
    right.appendChild(rightToggle);
    right.appendChild(close);

    header.appendChild(left);
    header.appendChild(right);
    return header;
  }

  function buildSidebar() {
    var sidebar = element("aside", "redline__sidebar redline__sidebar--left", {
      "data-redline-panel": "left",
      "aria-label": "Redline controls"
    });

    var breakpoints = section("breakpoint", "Breakpoint");
    var list = element("div", "redline__breakpoint-list", {
      role: "group",
      "aria-label": "Viewport sizes"
    });
    var current = element("button", "redline__breakpoint", {
      type: "button",
      "data-redline-action": "breakpoint:current",
      "aria-pressed": "true",
      title: "Inspect the current browser width"
    });
    var currentName = element("span", "redline__breakpoint-name");
    currentName.textContent = "Current";
    current.appendChild(currentName);
    list.appendChild(current);
    BREAKPOINTS.forEach(function (preset) {
      var row = element("button", "redline__breakpoint", {
        type: "button",
        "data-redline-action": "breakpoint:" + preset.id,
        "aria-pressed": "false",
        title: "Preview at " + preset.width + " \u00d7 " + preset.height
      });
      var name = element("span", "redline__breakpoint-name");
      name.textContent = preset.id;
      var size = element("span", "redline__breakpoint-size");
      size.textContent = preset.width + " \u00d7 " + preset.height;
      row.appendChild(name);
      row.appendChild(size);
      list.appendChild(row);
    });
    breakpoints.appendChild(list);
    sidebar.appendChild(breakpoints);
    sidebar.appendChild(divider());

    var measurement = section("measurement", "Measurement mode");
    var segmented = element("div", "redline__segmented", {
      role: "group",
      "aria-label": "Measurement mode"
    });
    MEASUREMENT_MODES.forEach(function (mode) {
      var item = element("button", "redline__segment", {
        type: "button",
        "data-redline-action": "mode:" + mode.id,
        "aria-pressed": mode.id === "clean" ? "true" : "false"
      });
      item.textContent = mode.label;
      segmented.appendChild(item);
    });
    measurement.appendChild(segmented);
    var hint = element("p", "redline__hint", { "data-redline-mode-hint": "" });
    hint.textContent = measurementHint("clean");
    measurement.appendChild(hint);
    sidebar.appendChild(measurement);
    sidebar.appendChild(divider());

    var inspection = section("inspection", "Inspection");
    var stack = element("div", "redline__stack", {
      role: "group",
      "aria-label": "Inspection modes"
    });
    [
      { id: "typography", label: "Typography" },
      { id: "color", label: "Color" }
    ].forEach(function (mode) {
      var item = element("button", "redline__stack-button", {
        type: "button",
        "data-redline-action": "toggle:" + mode.id,
        "aria-pressed": "false"
      });
      item.textContent = mode.label;
      stack.appendChild(item);
    });
    inspection.appendChild(stack);
    sidebar.appendChild(inspection);
    sidebar.appendChild(divider());

    var annotations = section("annotations", "Annotations");
    annotations.appendChild(
      checkboxRow("Show measurement lines", "annotation:lines", true)
    );
    annotations.appendChild(
      checkboxRow("Show 8pt grid overlay", "annotation:grid-overlay", false)
    );
    sidebar.appendChild(annotations);
    sidebar.appendChild(divider());

    var appSidebar = section("app-sidebar", "App sidebar");
    var sidebarModes = element("div", "redline__segmented", {
      role: "group",
      "aria-label": "App sidebar width"
    });
    [
      { id: "collapsed", label: "Collapsed" },
      { id: "expanded", label: "Expanded" }
    ].forEach(function (mode, index) {
      var item = element("button", "redline__segment", {
        type: "button",
        "data-redline-action": "sidebar:" + mode.id,
        "aria-pressed": index === 0 ? "true" : "false"
      });
      item.textContent = mode.label;
      sidebarModes.appendChild(item);
    });
    appSidebar.appendChild(sidebarModes);
    var sidebarHint = element("p", "redline__hint");
    sidebarHint.textContent = "Inspect .vnav in the preview. Rate cards stays selected on every Rate Card Manager route; entering Redline Mode does not change it.";
    appSidebar.appendChild(sidebarHint);
    sidebar.appendChild(appSidebar);
    sidebar.appendChild(divider());

    /* Table components. The Action Bar belongs here rather than under
     * Overlays: it is part of the table's own structure, between the
     * column header row and the first data row, not something that
     * appears over a screen and is dismissed. Selecting it stages the
     * real bar in the real table and reveals its states below. */
    var components = section("components", "Table components");
    components.appendChild(entryList(COMPONENT_ENTRY_ROWS, "Table components"));
    var states = element("div", "redline__state-list", {
      "data-redline-states": "",
      role: "group",
      "aria-label": "Component states",
      hidden: ""
    });
    components.appendChild(states);
    var componentHint = element("p", "redline__hint", {
      "data-redline-component-hint": "",
      hidden: ""
    });
    componentHint.textContent = "";
    components.appendChild(componentHint);
    sidebar.appendChild(components);
    sidebar.appendChild(divider());

    // Entry points only. The gallery's own contents are listed in the
    // toolbar above the preview, never here.
    var overlays = section("overlays", "Overlays");
    overlays.appendChild(entryList(GALLERY_ENTRY_ROWS, "Overlay galleries"));
    sidebar.appendChild(overlays);
    sidebar.appendChild(divider());

    var selection = section("selection", "Selection");
    var summary = element("p", "redline__selection", {
      "data-redline-selection": ""
    });
    summary.textContent = EMPTY_SELECTION;
    selection.appendChild(summary);
    sidebar.appendChild(selection);

    return sidebar;
  }

  function buildInspector() {
    var panel = element("aside", "redline__sidebar redline__sidebar--right", {
      "data-redline-panel": "right",
      role: "region",
      "aria-label": "Component inspector"
    });
    var body = element("div", "redline__inspector", {
      "data-redline-inspector": ""
    });
    panel.appendChild(body);
    return panel;
  }

  /* Covers the canvas while a preview is loading and replaces it with an
   * actionable explanation when the load fails, so a breakpoint can never
   * resolve to a featureless empty rectangle. */
  function buildPreviewStatus() {
    var overlay = element("div", "redline__preview-status", {
      "data-redline-preview-status": "idle",
      role: "status",
      "aria-live": "polite",
      hidden: ""
    });
    var card = element("div", "redline__preview-status-card");
    var title = element("p", "redline__preview-status-title", {
      "data-redline-preview-title": ""
    });
    var body = element("p", "redline__preview-status-body", {
      "data-redline-preview-body": ""
    });
    var diagnostics = element("p", "redline__preview-status-diagnostics", {
      "data-redline-preview-diagnostics": ""
    });
    var retry = element("button", "redline__preview-status-action", {
      type: "button",
      "data-redline-action": "preview:retry",
      hidden: ""
    });
    retry.textContent = "Retry preview";
    card.appendChild(title);
    card.appendChild(body);
    card.appendChild(diagnostics);
    card.appendChild(retry);
    overlay.appendChild(card);
    return overlay;
  }

  // Sits above the preview, inside the centre column but outside the canvas,
  // so it is never measured as product content and never covers the preview.
  function buildGalleryBar() {
    var bar = element("div", "redline__gallery", {
      "data-redline-gallery": "",
      role: "toolbar",
      "aria-label": "Overlay gallery navigation",
      hidden: ""
    });

    var back = element("button", "redline__gallery-back", {
      type: "button",
      "data-redline-action": "gallery:back",
      "aria-label": "Back to page"
    });
    back.textContent = "Back to page";

    var nav = element("div", "redline__gallery-nav");
    var previous = element("button", "redline__gallery-step", {
      type: "button",
      "data-redline-action": "gallery:previous",
      "aria-label": "Previous overlay",
      title: "Previous overlay"
    });
    previous.textContent = "\u2039";
    var label = element("p", "redline__gallery-label", {
      "data-redline-gallery-label": "",
      role: "status",
      "aria-live": "polite"
    });
    var next = element("button", "redline__gallery-step", {
      type: "button",
      "data-redline-action": "gallery:next",
      "aria-label": "Next overlay",
      title: "Next overlay"
    });
    next.textContent = "\u203a";
    nav.appendChild(previous);
    nav.appendChild(label);
    nav.appendChild(next);

    // Overlays remain interactive for inspection, so a designer can dismiss
    // one by accident. Reset puts the selected entry back on screen.
    var reset = element("button", "redline__gallery-reset", {
      type: "button",
      "data-redline-action": "gallery:reset",
      "aria-label": "Reopen the selected overlay"
    });
    reset.textContent = "Reset";

    bar.appendChild(back);
    bar.appendChild(nav);
    bar.appendChild(reset);
    return bar;
  }

  function buildRoot() {
    var root = element("div", "redline", {
      role: "application",
      "aria-label": "Redline inspection mode",
      "data-breakpoint-active": "false"
    });
    root.appendChild(buildHeader());
    var workspace = element("div", "redline__workspace");
    workspace.appendChild(buildSidebar());
    var canvas = element("div", "redline__canvas", { "data-redline-canvas": "" });
    var stage = element("div", "redline__stage");
    var frameShell = element("div", "redline__preview-shell", {
      hidden: ""
    });
    var frame = element("iframe", "redline__preview", {
      title: "Viewport QA preview",
      src: "about:blank",
      hidden: ""
    });
    frameShell.appendChild(frame);
    stage.appendChild(frameShell);
    stage.appendChild(buildPreviewStatus());
    canvas.appendChild(stage);

    // Overlays live inside the canvas column so tool chrome can never draw
    // on top of the sidebars or header.
    for (var index = 0; index < 4; index += 1) {
      canvas.appendChild(element("div", "redline__dim", {
        "data-redline-dim": String(index),
        "aria-hidden": "true"
      }));
    }
    canvas.appendChild(element("div", "redline__grid", {
      "data-redline-grid": "",
      "aria-hidden": "true",
      hidden: ""
    }));

    var svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("class", "redline__svg");
    svg.setAttribute("data-redline-ui", "");
    svg.setAttribute("data-redline-svg", "");
    svg.setAttribute("aria-hidden", "true");
    canvas.appendChild(svg);
    canvas.appendChild(element("div", "redline__labels", {
      "data-redline-labels": "",
      "aria-hidden": "true"
    }));

    // The centre column stacks the gallery toolbar above the canvas. The
    // canvas keeps its own positioning context, so every overlay coordinate
    // stays relative to the canvas and the toolbar simply shortens it.
    var center = element("div", "redline__center");
    center.appendChild(buildGalleryBar());
    center.appendChild(canvas);
    workspace.appendChild(center);
    workspace.appendChild(buildInspector());
    root.appendChild(workspace);
    root.appendChild(element("div", "redline__status", {
      role: "status",
      "aria-live": "polite",
      "data-redline-status": ""
    }));
    return { root: root, frameShell: frameShell, frame: frame };
  }

  function setStatus(message) {
    var status = state.root && state.root.querySelector("[data-redline-status]");
    if (status) status.textContent = message;
  }

  function activeBreakpoint() {
    return BREAKPOINTS.find(function (item) {
      return item.id === state.breakpoint;
    }) || null;
  }

  function inGallery() {
    return state.previewMode !== PREVIEW_MODES.CURRENT;
  }

  // A preset breakpoint needs the iframe to simulate the viewport. A gallery
  // needs it for a different reason: overlay fixtures must never touch the
  // page the user actually came from, so they are always staged in the
  // isolated preview copy, even while Current is the selected breakpoint.
  function usingFrame() {
    return Boolean(state.breakpoint) || inGallery();
  }

  // The viewport the product is laid out against. Under Current that is the
  // real window, which the gallery mirrors into the frame at 1:1 logical size.
  function logicalViewport() {
    var preset = activeBreakpoint();
    if (preset) return { width: preset.width, height: preset.height };
    return { width: window.innerWidth, height: window.innerHeight };
  }

  // The header always reports the logical viewport plus the scale actually
  // applied to fit it, never the scaled display size.
  function syncViewportInfo() {
    if (!state.root) return;
    var readout = state.root.querySelector("[data-redline-viewport-info]");
    if (!readout) return;
    var viewport = logicalViewport();
    var scale = usingFrame() ? state.previewScale : 1;
    readout.textContent = viewport.width + " \u00d7 " + viewport.height
      + " (" + Math.round(scale * 100) + "%)";
  }

  function syncVersionBadge() {
    if (!state.root) return;
    var badge = state.root.querySelector("[data-redline-version-badge]");
    if (badge) badge.textContent = versionBadgeText();
  }

  // The three-column shell is laid out in CSS, so the stage element already
  // reports exactly the space available between the sidebars and below the
  // header. No runtime chrome measurement is required.
  function fitBreakpointPreview() {
    if (!usingFrame() || !state.root || !state.frame || !state.frameShell) return;
    var viewport = logicalViewport();
    var stage = state.root.querySelector(".redline__stage");
    if (!stage) return;
    var availableWidth = stage.clientWidth;
    var availableHeight = stage.clientHeight;
    var scale = Math.min(
      1,
      availableWidth / viewport.width,
      availableHeight / viewport.height
    );
    if (!Number.isFinite(scale) || scale <= 0) scale = 1;
    var displayWidth = viewport.width * scale;
    var displayHeight = viewport.height * scale;
    state.previewScale = scale;
    state.frame.style.width = viewport.width + "px";
    state.frame.style.height = viewport.height + "px";
    state.frameShell.style.width = viewport.width + "px";
    state.frameShell.style.height = viewport.height + "px";
    state.frameShell.style.left = Math.max(0, (availableWidth - displayWidth) / 2) + "px";
    state.frameShell.style.top = Math.max(0, (availableHeight - displayHeight) / 2) + "px";
    state.frameShell.style.transform = "scale(" + scale + ")";
    syncViewportInfo();
  }

  function syncRenderedState() {
    if (!state.frameDocument || state.frameDocument === document) return;
    var sourceControls = document.querySelectorAll(
      "input, textarea, select, details, [aria-expanded], [aria-selected]"
    );
    sourceControls.forEach(function (source) {
      if (source.closest("[data-redline-ui]")) return;
      var target = source.id
        ? state.frameDocument.getElementById(source.id)
        : null;
      if (!target && source.getAttribute("name")) {
        try {
          target = state.frameDocument.querySelector(
            '[name="' + CSS.escape(source.getAttribute("name")) + '"]'
          );
        } catch (_) {}
      }
      if (!target) return;
      if ("value" in source && "value" in target) target.value = source.value;
      if ("checked" in source && "checked" in target) target.checked = source.checked;
      if (source.tagName === "DETAILS") target.open = source.open;
      ["aria-expanded", "aria-selected"].forEach(function (attribute) {
        if (source.hasAttribute(attribute)) {
          target.setAttribute(attribute, source.getAttribute(attribute));
        }
      });
    });
  }

  function schedule() {
    if (!state.active || state.raf) return;
    state.raf = requestAnimationFrame(function () {
      state.raf = 0;
      render();
    });
  }

  /* Under a preset breakpoint or a gallery the preview is the iframe, so the
   * page Redline was opened from sits behind the shell: visible to nobody, yet
   * still in the tab order and the accessibility tree. Marking it inert takes
   * it out of both. Under Current the live document IS the preview and has to
   * stay hoverable and clickable, so it is never marked. Only nodes Redline
   * marked are unmarked again. */
  function syncSourcePageInert() {
    setSourcePageInert(state.active && usingFrame());
  }

  function setSourcePageInert(inert) {
    var attribute = "data-redline-inert";
    if (!inert) {
      document.querySelectorAll("[" + attribute + "]").forEach(function (node) {
        node.removeAttribute(attribute);
        node.inert = false;
        node.removeAttribute("inert");
      });
      return;
    }
    Array.prototype.forEach.call(document.body.children, function (node) {
      if (node === state.root || node.hasAttribute("data-redline-ui")) return;
      if (node.inert || node.hasAttribute("inert")) return;
      node.setAttribute(attribute, "");
      node.inert = true;
    });
  }

  function disconnectFrame() {
    if (state.resizeObserver) state.resizeObserver.disconnect();
    if (state.mutationObserver) state.mutationObserver.disconnect();
    state.resizeObserver = null;
    state.mutationObserver = null;
    state.frameDocument = null;
    state.hovered = null;
    state.locked = null;
  }

  function observeInspectionDocument(doc, view, attachEvents) {
    disconnectFrame();
    if (!doc || !doc.documentElement) return;
    state.frameDocument = doc;
    syncRenderedState();

    var signal = state.aborter.signal;
    if (attachEvents) {
    doc.addEventListener("pointermove", onPreviewPointerMove, {
      capture: true,
      passive: true,
      signal: signal
    });
    doc.addEventListener("pointerleave", function () {
        if (state.frameDocument !== doc) return;
      state.hovered = null;
      schedule();
    }, { capture: true, signal: signal });
    doc.addEventListener("click", onPreviewClick, {
      capture: true,
      signal: signal
    });
    doc.addEventListener("transitionrun", schedule, { capture: true, signal: signal });
    doc.addEventListener("transitionend", schedule, { capture: true, signal: signal });
    doc.addEventListener("animationstart", schedule, { capture: true, signal: signal });
    doc.addEventListener("animationend", schedule, { capture: true, signal: signal });
      view.addEventListener("scroll", schedule, {
      capture: true,
      passive: true,
      signal: signal
    });
      view.addEventListener("resize", schedule, {
      passive: true,
      signal: signal
    });
    }

    if ("ResizeObserver" in window) {
      state.resizeObserver = new ResizeObserver(schedule);
      state.resizeObserver.observe(doc.documentElement);
      if (doc.body) state.resizeObserver.observe(doc.body);
    }
    state.mutationObserver = new MutationObserver(schedule);
    var mutationRoot = doc === document
      ? (doc.querySelector(".page") || doc.body)
      : doc.documentElement;
    state.mutationObserver.observe(mutationRoot, {
      attributes: true,
      childList: true,
      characterData: true,
      subtree: true
    });
    if (doc.fonts && doc.fonts.ready) {
      doc.fonts.ready.then(function () {
        if (state.active && state.frameDocument === doc) schedule();
      });
    }
    schedule();
  }

  function attachCurrent() {
    var attachEvents = !state.currentListenersAttached;
    observeInspectionDocument(document, window, attachEvents);
    state.currentListenersAttached = true;
  }

  function preserveLogicalPreviewWidth(doc) {
    if (!doc || !doc.head || doc.querySelector("[data-redline-preview-scroll]")) return;
    var style = doc.createElement("style");
    style.setAttribute("data-redline-preview-scroll", "");
    style.textContent = [
      "html { scrollbar-width: none !important; }",
      "html::-webkit-scrollbar, body::-webkit-scrollbar {",
      "  width: 0 !important;",
      "  height: 0 !important;",
      "}"
    ].join("\n");
    doc.head.appendChild(style);
  }

  // ----- Preview lifecycle --------------------------------------------------

  var PREVIEW_LOAD_TIMEOUT = 10000;

  function setPreviewPhase(phase, title, body, diagnostics, showRetry) {
    state.previewPhase = phase;
    if (!state.root) return;
    var overlay = state.root.querySelector("[data-redline-preview-status]");
    if (!overlay) return;
    overlay.setAttribute("data-redline-preview-status", phase);
    overlay.hidden = phase === "ready" || phase === "idle";
    var titleEl = overlay.querySelector("[data-redline-preview-title]");
    var bodyEl = overlay.querySelector("[data-redline-preview-body]");
    var diagEl = overlay.querySelector("[data-redline-preview-diagnostics]");
    var retryEl = overlay.querySelector("[data-redline-preview-action], [data-redline-action='preview:retry']");
    if (titleEl) titleEl.textContent = title || "";
    if (bodyEl) bodyEl.textContent = body || "";
    if (diagEl) {
      diagEl.textContent = diagnostics || "";
      diagEl.hidden = !diagnostics;
    }
    if (retryEl) retryEl.hidden = !showRetry;
  }

  function clearPreviewTimer() {
    if (state.previewTimer) {
      window.clearTimeout(state.previewTimer);
      state.previewTimer = 0;
    }
  }

  function previewLoading() {
    clearPreviewTimer();
    state.previewToken += 1;
    var token = state.previewToken;
    setPreviewPhase(
      "loading",
      "Loading preview",
      "Rendering the current page at the selected viewport.",
      "",
      false
    );
    clearOverlays();
    state.previewTimer = window.setTimeout(function () {
      if (token !== state.previewToken || state.previewPhase === "ready") return;
      classifyPreviewFailure(token, "The preview did not finish loading in time.");
    }, PREVIEW_LOAD_TIMEOUT);
    return token;
  }

  function previewReady() {
    clearPreviewTimer();
    setPreviewPhase("ready", "", "", "", false);
  }

  function previewError(title, body, diagnostics) {
    clearPreviewTimer();
    setPreviewPhase("error", title, body, diagnostics, true);
    // The failed document must not stay wired up for inspection.
    disconnectFrame();
    clearOverlays();
    setStatus(title + " " + body);
  }

  /* Distinguishes the failure modes a designer can act on: the dev server
   * being down, the route not existing, an auth wall, or markup that
   * loaded but never booted the app. */
  function classifyPreviewFailure(token, reason) {
    var url = previewUrl();
    var finish = function (title, body) {
      if (token !== state.previewToken) return;
      previewError(title, body, reason + " URL: " + url);
    };
    if (typeof window.fetch !== "function") {
      finish("Preview failed to render", "The preview page could not be inspected.");
      return;
    }
    window.fetch(url, { method: "GET", cache: "no-store" }).then(function (response) {
      if (response.status === 401 || response.status === 403) {
        finish("Authentication required", "The preview URL responded with " + response.status + ".");
      } else if (response.status === 404) {
        finish("Route not found", "The preview URL responded with 404.");
      } else if (!response.ok) {
        finish("Preview server error", "The preview URL responded with " + response.status + ".");
      } else {
        finish("Preview failed to render", "The page loaded but the application did not start.");
      }
    }).catch(function (error) {
      finish(
        "Preview server unavailable",
        "The preview URL could not be reached: " + (error && error.message ? error.message : error) + "."
      );
    });
  }

  /* Replays the captured entry state into the freshly booted preview. The
   * preview loads the same URL, but everything the app keeps in memory
   * (search, filters, sort, pagination, selection, unsaved values, scroll)
   * only survives because the bridge hands it across. */
  function captureAppSnapshot() {
    try {
      return window.RateCardStateBridge
        && typeof window.RateCardStateBridge.capture === "function"
        ? window.RateCardStateBridge.capture()
        : null;
    } catch (_) {
      return null;
    }
  }

  function restoreAppSnapshot() {
    state.appSnapshotApplied = false;
    if (!state.appSnapshot) return;
    var win;
    try {
      win = state.frame.contentWindow;
    } catch (_) {
      return;
    }
    if (!win || !win.RateCardStateBridge) return;
    try {
      state.appSnapshotApplied = Boolean(
        win.RateCardStateBridge.restore(state.appSnapshot)
      );
    } catch (_) {
      state.appSnapshotApplied = false;
    }
  }

  function attachFrame() {
    if (!usingFrame()) return;
    var doc;
    try {
      doc = state.frame.contentDocument;
    } catch (_) {
      previewError(
        "Preview failed to render",
        "The preview document could not be read from this origin.",
        "URL: " + previewUrl()
      );
      return;
    }
    if (!doc || !doc.body) {
      classifyPreviewFailure(state.previewToken, "The preview produced no document.");
      return;
    }
    if (!doc.body.getAttribute("data-route")) {
      classifyPreviewFailure(state.previewToken, "The preview document never set a route.");
      return;
    }
    preserveLogicalPreviewWidth(doc);
    restoreAppSnapshot();
    previewReady();
    // A preview document keeps its listeners until it is replaced, so a
    // re-attach after Current page must not bind a second set.
    var attachEvents = state.frameListenersDoc !== doc;
    observeInspectionDocument(doc, state.frame.contentWindow, attachEvents);
    state.frameListenersDoc = doc;
    if (inGallery()) {
      // The preview booted (or reloaded) while a gallery was open, so the
      // selected entry is restaged rather than dropping back to the page.
      if (loadGalleryEntries()) showGalleryEntry();
      else syncGalleryControls();
    }
    // Restored content reflows the page, so measurements are recomputed
    // once layout has settled rather than against the pre-restore layout.
    window.requestAnimationFrame(function () {
      window.requestAnimationFrame(schedule);
    });
  }

  function retryPreview() {
    if (!usingFrame() || !state.frame) return;
    var token = previewLoading();
    state.frame.src = "about:blank";
    window.setTimeout(function () {
      if (token !== state.previewToken) return;
      state.frame.src = previewUrl();
    }, 0);
  }

  function inspectedTarget(target) {
    if (!target || target.nodeType !== 1) return null;
    if (target.closest("[data-redline-ui], script, style, link, meta")) return null;
    if (target === state.frameDocument.documentElement || target === state.frameDocument.body) {
      return null;
    }
    return target;
  }

  function onPreviewPointerMove(event) {
    if (!event.target || event.target.ownerDocument !== state.frameDocument) return;
    if (event.target.closest && event.target.closest("[data-redline-ui]")) return;
    state.hovered = inspectedTarget(event.target);
    schedule();
  }

  function onPreviewClick(event) {
    // Staging an overlay drives the product's own controls, and those
    // synthetic clicks must not look like the user selecting a component.
    if (state.galleryStaging) return;
    var target = event.target && event.target.nodeType === 1 ? event.target : null;
    if (!target || target.ownerDocument !== state.frameDocument
        || target.closest("[data-redline-ui]")) return;
    if (target && target.closest('[data-action="toggle-profile"]')) return;
    if (target && target.closest('[data-action="toggle-theme"], [data-theme], [data-action="logout"]')) {
      return;
    }
    if (target && target.closest('[data-action="toggle-redline"]')) {
      event.preventDefault();
      event.stopImmediatePropagation();
      disable();
      return;
    }
    var inspected = inspectedTarget(target);
    if (state.color && inspected) {
      // Color mode pins the inspection result instead of letting the
      // click reach the underlying application control.
      event.preventDefault();
      event.stopPropagation();
    }
    state.locked = inspected;
    state.hovered = inspected;
    setStatus(inspected ? "Element locked for inspection." : "Locked selection cleared.");
    schedule();
  }

  function mapRect(rect) {
    var frameRect = usingFrame() && state.frame
      ? state.frame.getBoundingClientRect()
      : { left: 0, top: 0 };
    var scale = usingFrame() ? state.previewScale : 1;
    return {
      left: frameRect.left + rect.left * scale,
      top: frameRect.top + rect.top * scale,
      right: frameRect.left + rect.right * scale,
      bottom: frameRect.top + rect.bottom * scale,
      width: rect.width * scale,
      height: rect.height * scale,
      logicalWidth: rect.width,
      logicalHeight: rect.height
    };
  }

  // getBoundingClientRect() on an element inside the breakpoint iframe is
  // relative to that iframe's own scrollport, not clipped to it, so a target
  // taller than the simulated device (e.g. a content-heavy page inside a
  // short 1024x768 preview) produces a mapped rect that runs past the
  // frame's real bottom edge. Clamp every drawn rect to the frame's true
  // bounding box so boundary/measurement overlays never spill outside the
  // simulated viewport into the surrounding tool chrome.
  function clampRectToFrame(rect) {
    var bounds = inspectionViewportRect();
    var left = Math.max(rect.left, bounds.left);
    var top = Math.max(rect.top, bounds.top);
    var right = Math.min(rect.right, bounds.right);
    var bottom = Math.min(rect.bottom, bounds.bottom);
    right = Math.max(left, right);
    bottom = Math.max(top, bottom);
    return {
      left: left,
      top: top,
      right: right,
      bottom: bottom,
      width: right - left,
      height: bottom - top,
      logicalWidth: rect.logicalWidth,
      logicalHeight: rect.logicalHeight
    };
  }

  function logicalLength(value) {
    var scale = usingFrame() ? state.previewScale : 1;
    return scale > 0 ? value / scale : value;
  }

  function inspectionView() {
    return usingFrame() && state.frame ? state.frame.contentWindow : window;
  }

  function rounded(value) {
    return String(Math.round(Number(value) || 0));
  }

  function nearestEight(value) {
    return Math.round((Number(value) || 0) / 8) * 8;
  }

  function visible(node) {
    if (!node || node.nodeType !== 1) return false;
    var view = inspectionView();
    var style = view.getComputedStyle(node);
    var rect = node.getBoundingClientRect();
    var viewportWidth = usingFrame() ? state.frame.clientWidth : window.innerWidth;
    var viewportHeight = usingFrame() ? state.frame.clientHeight : window.innerHeight;
    return style.display !== "none" && style.visibility !== "hidden"
      && rect.width > 1 && rect.height > 1
      && rect.bottom > 0 && rect.right > 0
      && rect.top < viewportHeight && rect.left < viewportWidth;
  }

  function majorTargets() {
    if (!state.frameDocument) return [];
    var candidates = Array.prototype.slice.call(state.frameDocument.querySelectorAll(
      "header, nav, main, article, section, form, table, [role='dialog'], [role='tabpanel']"
    )).filter(visible);
    candidates.sort(function (a, b) {
      var ar = a.getBoundingClientRect();
      var br = b.getBoundingClientRect();
      return (br.width * br.height) - (ar.width * ar.height);
    });
    var selected = [];
    candidates.some(function (candidate) {
      if (selected.some(function (parent) { return parent.contains(candidate); })) return false;
      selected.push(candidate);
      return selected.length >= 4;
    });
    return selected;
  }

  function svgNode(tag, attrs) {
    var node = document.createElementNS(SVG_NS, tag);
    Object.keys(attrs || {}).forEach(function (name) {
      node.setAttribute(name, attrs[name]);
    });
    return node;
  }

  function prepareSvg(svg) {
    svg.replaceChildren();
    var defs = svgNode("defs");
    var marker = svgNode("marker", {
      id: "redline-arrow",
      markerWidth: "8",
      markerHeight: "8",
      refX: "4",
      refY: "4",
      orient: "auto-start-reverse"
    });
    marker.appendChild(svgNode("path", {
      d: "M 8 0 L 1 4 L 8 8",
      fill: "none",
      stroke: "var(--redline-clean)",
      "stroke-width": "1",
      "stroke-linecap": "square",
      "stroke-linejoin": "miter"
    }));
    defs.appendChild(marker);
    svg.appendChild(defs);
  }

  function line(svg, x1, y1, x2, y2, className, arrows) {
    var attrs = {
      x1: rounded(x1),
      y1: rounded(y1),
      x2: rounded(x2),
      y2: rounded(y2),
      "class": className || "redline__dimension"
    };
    if (arrows) {
      attrs["marker-start"] = "url(#redline-arrow)";
      attrs["marker-end"] = "url(#redline-arrow)";
    }
    svg.appendChild(svgNode("line", attrs));
  }

  function boundary(svg, rect, extraClass) {
    svg.appendChild(svgNode("rect", {
      x: rounded(rect.left),
      y: rounded(rect.top),
      width: rounded(rect.width),
      height: rounded(rect.height),
      rx: "0",
      "class": "redline__boundary" + (extraClass ? " " + extraClass : "")
    }));
  }

  // The canvas column is the only region overlays may draw in, so tool
  // chrome (header, sidebars, inspector) can never be annotated or covered.
  function canvasRect() {
    var canvas = state.root && state.root.querySelector("[data-redline-canvas]");
    if (!canvas) {
      return { left: 0, top: 0, right: window.innerWidth, bottom: window.innerHeight };
    }
    var rect = canvas.getBoundingClientRect();
    return {
      left: rect.left,
      top: rect.top,
      right: rect.right,
      bottom: rect.bottom
    };
  }

  function inspectionBounds() {
    var canvas = canvasRect();
    if (usingFrame() && state.frame) {
      var frameRect = state.frame.getBoundingClientRect();
      return {
        left: Math.max(canvas.left, frameRect.left),
        top: Math.max(canvas.top, frameRect.top),
        right: Math.min(canvas.right, frameRect.right),
        bottom: Math.min(canvas.bottom, frameRect.bottom)
      };
    }
    return canvas;
  }

  // Retained for the label placer's collision API. The redesigned shell has
  // no floating control bars over the preview, so nothing is reserved.
  function toolbarBoxes() {
    return [];
  }

  function boxesOverlap(a, b, clearance) {
    var gap = Number(clearance) || 0;
    return !(a.right + gap <= b.left || a.left >= b.right + gap
      || a.bottom + gap <= b.top || a.top >= b.bottom + gap);
  }

  function labelPlacer(host, svg) {
    var occupied = toolbarBoxes();
    var keys = new Set();
    var bounds = inspectionBounds();
    var inset = 6;

    function clampPosition(position, width, height) {
      return {
        x: Math.max(
          bounds.left + inset,
          Math.min(position.x, bounds.right - width - inset)
        ),
        y: Math.max(
          bounds.top + inset,
          Math.min(position.y, bounds.bottom - height - inset)
        ),
        leader: Boolean(position.leader)
      };
    }

    function candidatesFor(x, y, width, height, options) {
      var offset = 10;
      var shifts = [0, 36, -36, 72, -72];
      var positions = [];
      if (options.axis === "horizontal") {
        shifts.forEach(function (shift) {
          positions.push({ x: x - width / 2 + shift, y: y - height - offset });
        });
        shifts.forEach(function (shift) {
          positions.push({ x: x - width / 2 + shift, y: y + offset });
        });
      } else if (options.axis === "vertical") {
        shifts.forEach(function (shift) {
          positions.push({ x: x - width - offset, y: y - height / 2 + shift });
        });
        shifts.forEach(function (shift) {
          positions.push({ x: x + offset, y: y - height / 2 + shift });
        });
      } else {
        positions = [
          { x: x - width / 2, y: y + offset },
          { x: x - width / 2, y: y - height - offset },
          { x: x + offset, y: y - height / 2 },
          { x: x - width - offset, y: y - height / 2 }
        ];
      }
      positions.push(
        { x: x - width / 2, y: bounds.top + inset, leader: true },
        { x: x - width / 2, y: bounds.bottom - height - inset, leader: true },
        { x: bounds.left + inset, y: y - height / 2, leader: true },
        { x: bounds.right - width - inset, y: y - height / 2, leader: true }
      );
      return positions;
    }

    return function (text, x, y, kind, title, options) {
      options = options || {};
      var key = options.dedupeKey || (kind || "measure") + ":" + text;
      if (keys.has(key)) return null;
      keys.add(key);
      var node = element("span", "redline__label" + (kind ? " redline__label--" + kind : ""));
      node.textContent = text;
      if (title) node.title = title;
      node.style.visibility = "hidden";
      host.appendChild(node);
      var width = node.offsetWidth;
      var height = node.offsetHeight;
      var positions = candidatesFor(x, y, width, height, options);
      var chosen = null;
      for (var i = 0; i < positions.length; i += 1) {
        var position = clampPosition(positions[i], width, height);
        var candidate = {
          left: position.x,
          top: position.y,
          right: position.x + width,
          bottom: position.y + height
        };
        var collides = occupied.some(function (box) {
          return boxesOverlap(candidate, box, 4);
        });
        if (!collides && options.avoid && boxesOverlap(candidate, options.avoid, 6)) {
          collides = true;
        }
        if (!collides) {
          chosen = { position: position, box: candidate };
          break;
        }
      }
      if (!chosen) {
        node.remove();
        return null;
      }
      occupied.push(chosen.box);
      node.style.left = Math.round(chosen.position.x) + "px";
      node.style.top = Math.round(chosen.position.y) + "px";
      node.style.visibility = "visible";
      if (chosen.position.leader && svg) {
        var endX = Math.max(chosen.box.left, Math.min(x, chosen.box.right));
        var endY = Math.max(chosen.box.top, Math.min(y, chosen.box.bottom));
        line(svg, x, y, endX, endY, "redline__leader", false);
      }
      return chosen.box;
    };
  }

  // Draws the width/height dimension lines anchored to the preview. The
  // active measurement mode only changes how the numbers are interpreted:
  // "clean" reports rounded actual CSS pixels, "grid" reports the nearest
  // 8pt value. Detailed padding/margin/layout values live in the inspector.
  function drawMeasurementLines(svg, addLabel, rect) {
    var bounds = inspectionBounds();
    var isGrid = state.measurementMode === "grid";
    var lineClass = isGrid
      ? "redline__dimension redline__recommendation"
      : "redline__dimension redline__dimension--selected";
    var logicalWidth = Number.isFinite(rect.logicalWidth)
      ? rect.logicalWidth
      : logicalLength(rect.width);
    var logicalHeight = Number.isFinite(rect.logicalHeight)
      ? rect.logicalHeight
      : logicalLength(rect.height);
    var horizontalY = Math.max(bounds.top + 6, rect.top - 12);
    if (horizontalY <= bounds.top + 6 && rect.bottom + 12 <= bounds.bottom - 6) {
      horizontalY = rect.bottom + 12;
    }
    var verticalX = Math.max(bounds.left + 6, rect.left - 12);
    if (verticalX <= bounds.left + 6 && rect.right + 12 <= bounds.right - 6) {
      verticalX = rect.right + 12;
    }
    line(svg, rect.left, horizontalY, rect.right, horizontalY, lineClass, !isGrid);
    line(svg, verticalX, rect.top, verticalX, rect.bottom, lineClass, !isGrid);
    var widthText = isGrid
      ? nearestEight(logicalWidth) + " (8pt)"
      : rounded(logicalWidth);
    var heightText = isGrid
      ? nearestEight(logicalHeight) + " (8pt)"
      : rounded(logicalHeight);
      addLabel(
      widthText,
      rect.left + rect.width / 2,
      horizontalY,
      isGrid ? "grid" : "",
      isGrid ? "Actual: " + rounded(logicalWidth) + " pixels." : "",
      { axis: "horizontal", avoid: rect, dedupeKey: "width:" + widthText }
    );
    addLabel(
      heightText,
      verticalX,
      rect.top + rect.height / 2,
      isGrid ? "grid" : "",
      isGrid ? "Actual: " + rounded(logicalHeight) + " pixels." : "",
      { axis: "vertical", avoid: rect, dedupeKey: "height:" + heightText }
    );
  }

  // ---------------------------------------------------------------------
  // Color inspection mode
  //
  // Resolves, for a hovered/locked element, the browser-computed color for
  // each applicable role (text, background, border, SVG fill/stroke,
  // outline, placeholder), then attempts to attribute that computed value
  // to the CSS declaration that produced it (selector, source file, best
  // effort line number, and whether the declaration references a design
  // token via var(--x) or is a hardcoded literal). Contrast is computed
  // against an effective background resolved through ancestor layers.
  // ---------------------------------------------------------------------

  function hasOwnText(el) {
    return Array.prototype.some.call(el.childNodes, function (node) {
      return node.nodeType === 3 && node.textContent.trim().length > 0;
    });
  }

  function camelize(prop) {
    return prop.replace(/-([a-z])/g, function (_, c) { return c.toUpperCase(); });
  }

  function parseColorToRgba(value) {
    if (!value) return null;
    var v = value.trim().toLowerCase();
    if (v === "transparent") return { r: 0, g: 0, b: 0, a: 0 };
    var m = v.match(/^rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)(?:[\s,/]+([\d.]+%?))?\s*\)$/);
    if (m) {
      var a = m[4] !== undefined
        ? (m[4].indexOf("%") !== -1 ? parseFloat(m[4]) / 100 : parseFloat(m[4]))
        : 1;
      return {
        r: Math.round(parseFloat(m[1])),
        g: Math.round(parseFloat(m[2])),
        b: Math.round(parseFloat(m[3])),
        a: Number.isFinite(a) ? a : 1
      };
    }
    var hexMatch = v.match(/^#([0-9a-f]{3,8})$/);
    if (hexMatch) {
      var hex = hexMatch[1];
      if (hex.length === 3 || hex.length === 4) {
        hex = hex.split("").map(function (ch) { return ch + ch; }).join("");
      }
      return {
        r: parseInt(hex.slice(0, 2), 16),
        g: parseInt(hex.slice(2, 4), 16),
        b: parseInt(hex.slice(4, 6), 16),
        a: hex.length === 8 ? parseInt(hex.slice(6, 8), 16) / 255 : 1
      };
    }
    return null;
  }

  function rgbaToHex(rgba) {
    function channel(n) {
      return Math.max(0, Math.min(255, Math.round(n))).toString(16).padStart(2, "0");
    }
    var hex = "#" + channel(rgba.r) + channel(rgba.g) + channel(rgba.b);
    if (rgba.a < 1) hex += channel(rgba.a * 255);
    return hex;
  }

  function rgbaToText(rgba) {
    return rgba.a < 1
      ? "rgba(" + rgba.r + ", " + rgba.g + ", " + rgba.b + ", " + (Math.round(rgba.a * 100) / 100) + ")"
      : "rgb(" + rgba.r + ", " + rgba.g + ", " + rgba.b + ")";
  }

  function compositeOver(fg, bg) {
    var a = fg.a;
    return {
      r: fg.r * a + bg.r * (1 - a),
      g: fg.g * a + bg.g * (1 - a),
      b: fg.b * a + bg.b * (1 - a),
      a: 1
    };
  }

  function relativeLuminance(rgb) {
    function channel(c) {
      var v = c / 255;
      return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    }
    return 0.2126 * channel(rgb.r) + 0.7152 * channel(rgb.g) + 0.0722 * channel(rgb.b);
  }

  function contrastRatio(rgbA, rgbB) {
    var lA = relativeLuminance(rgbA) + 0.05;
    var lB = relativeLuminance(rgbB) + 0.05;
    return lA > lB ? lA / lB : lB / lA;
  }

  function isLargeText(cs) {
    var size = parseFloat(cs.fontSize) || 0;
    var weight = parseInt(cs.fontWeight, 10) || 400;
    return size >= 24 || (size >= 18.66 && weight >= 700);
  }

  function effectiveBackgroundChain(target) {
    var view = inspectionView();
    var doc = state.frameDocument;
    var node = target;
    var chain = [];
    var guard = 0;
    while (node && guard < 64) {
      guard += 1;
      var cs = view.getComputedStyle(node);
      chain.push({ node: node, rgba: parseColorToRgba(cs.backgroundColor) });
      if (node === doc.documentElement) break;
      node = node.parentElement;
    }
    var composite = { r: 255, g: 255, b: 255, a: 1 };
    var sourceNode = null;
    for (var i = chain.length - 1; i >= 0; i -= 1) {
      var layer = chain[i].rgba;
      if (!layer || layer.a === 0) continue;
      composite = layer.a >= 1 ? { r: layer.r, g: layer.g, b: layer.b, a: 1 } : compositeOver(layer, composite);
      sourceNode = chain[i].node;
    }
    return { rgba: composite, sourceNode: sourceNode, isOwn: sourceNode === target };
  }

  function splitSelectorList(selectorText) {
    var parts = [];
    var depth = 0;
    var start = 0;
    for (var i = 0; i < selectorText.length; i += 1) {
      var ch = selectorText[i];
      if (ch === "(" || ch === "[") depth += 1;
      else if (ch === ")" || ch === "]") depth -= 1;
      else if (ch === "," && depth === 0) {
        parts.push(selectorText.slice(start, i).trim());
        start = i + 1;
      }
    }
    parts.push(selectorText.slice(start).trim());
    return parts.filter(Boolean);
  }

  function computeSpecificity(selector) {
    try {
      var work = String(selector);
      var pseudoElements = (work.match(/::[\w-]+/g) || []).length;
      work = work.replace(/::[\w-]+/g, " ");
      var ids = (work.match(/#[\w-]+/g) || []).length;
      work = work.replace(/#[\w-]+/g, " ");
      var classAttrPseudoPattern = /\.[\w-]+|\[[^\]]*\]|:[\w-]+(?:\([^()]*(?:\([^()]*\)[^()]*)*\))?/g;
      var classAttrPseudo = (work.match(classAttrPseudoPattern) || []).length;
      work = work.replace(classAttrPseudoPattern, " ");
      var types = (work.match(/[a-zA-Z][\w-]*/g) || []).length;
      return ids * 100 + classAttrPseudo * 10 + (types + pseudoElements);
    } catch (_) {
      return 0;
    }
  }

  function buildRuleCache() {
    var rules = [];
    var order = 0;
    var doc = state.frameDocument;
    var sheets = [];
    try { sheets = Array.prototype.slice.call(doc.styleSheets); } catch (_) { sheets = []; }
    function walk(list, sheet) {
      var items;
      try { items = Array.prototype.slice.call(list); } catch (_) { return; }
      items.forEach(function (rule) {
        // A plain CSSStyleRule now also exposes (usually empty) `.cssRules`
        // because browsers support native CSS nesting, so container
        // detection must not rely on that property alone or every style
        // rule with a selector gets treated as a container and skipped.
        if (rule.selectorText && rule.style) {
          order += 1;
          splitSelectorList(rule.selectorText).forEach(function (branch) {
            rules.push({
              selectorText: branch,
              fullSelectorText: rule.selectorText,
              style: rule.style,
              specificity: computeSpecificity(branch),
              order: order,
              sheetHref: sheet && sheet.href,
              cssText: rule.cssText
            });
          });
        }
        if (rule.cssRules && rule.cssRules.length) {
          walk(rule.cssRules, sheet);
        }
      });
    }
    sheets.forEach(function (sheet) {
      var cssRules;
      try { cssRules = sheet.cssRules; } catch (_) { return; }
      if (!cssRules) return;
      walk(cssRules, sheet);
    });
    return rules;
  }

  function getRuleCache() {
    if (!state.colorSheetCache || state.colorSheetCacheDoc !== state.frameDocument) {
      state.colorSheetCache = buildRuleCache();
      state.colorSheetCacheDoc = state.frameDocument;
    }
    return state.colorSheetCache;
  }

  var PLACEHOLDER_PSEUDO_RE = /::?(placeholder|-webkit-input-placeholder|-moz-placeholder|-ms-input-placeholder)\s*$/i;

  function findWinningDeclaration(el, props, pseudo) {
    var cache = getRuleCache();
    var best = null;
    cache.forEach(function (entry) {
      var selector = entry.selectorText;
      var hasPlaceholderPseudo = PLACEHOLDER_PSEUDO_RE.test(selector);
      if (pseudo && !hasPlaceholderPseudo) return;
      if (!pseudo && hasPlaceholderPseudo) return;
      var matchSelector = hasPlaceholderPseudo ? selector.replace(PLACEHOLDER_PSEUDO_RE, "").trim() : selector;
      if (!matchSelector || /::[\w-]+$/.test(matchSelector)) return;
      var matched;
      try { matched = el.matches(matchSelector); } catch (_) { matched = false; }
      if (!matched) return;
      var propHit = null;
      for (var i = 0; i < props.length; i += 1) {
        var raw = entry.style.getPropertyValue(props[i]);
        if (raw) { propHit = { prop: props[i], raw: raw.trim() }; break; }
      }
      if (!propHit) return;
      var candidate = {
        selectorText: entry.fullSelectorText,
        matchedBranch: entry.selectorText,
        prop: propHit.prop,
        raw: propHit.raw,
        important: entry.style.getPropertyPriority(propHit.prop) === "important",
        specificity: entry.specificity,
        order: entry.order,
        sheetHref: entry.sheetHref,
        cssText: entry.cssText
      };
      if (!best) { best = candidate; return; }
      if (candidate.important !== best.important) {
        if (candidate.important) best = candidate;
        return;
      }
      if (candidate.specificity !== best.specificity) {
        if (candidate.specificity > best.specificity) best = candidate;
        return;
      }
      if (candidate.order >= best.order) best = candidate;
    });
    if (!pseudo && el.style) {
      for (var i = 0; i < props.length; i += 1) {
        var inlineRaw = el.style.getPropertyValue(props[i]);
        if (inlineRaw) {
          best = {
            selectorText: "element.style (inline)",
            prop: props[i],
            raw: inlineRaw.trim(),
            important: el.style.getPropertyPriority(props[i]) === "important",
            specificity: Infinity,
            order: Infinity,
            sheetHref: null,
            cssText: null,
            inline: true
          };
          break;
        }
      }
    }
    return best;
  }

  function looksLikeColor(value) {
    if (!value) return false;
    var v = value.trim().toLowerCase();
    return /^#([0-9a-f]{3,8})$/.test(v) || /^rgba?\(/.test(v) || /^hsla?\(/.test(v)
      || v === "transparent" || v === "currentcolor";
  }

  function extractColorSource(rawValue, contextEl) {
    if (!rawValue) return null;
    var matches = [];
    var re = /var\(\s*(--[\w-]+)\s*(?:,\s*([^)]+))?\)/g;
    var m;
    while ((m = re.exec(rawValue))) {
      matches.push({ token: m[1], fallback: m[2] ? m[2].trim() : null });
    }
    if (!matches.length) {
      return { token: null, hardcoded: true, raw: rawValue };
    }
    var view = inspectionView();
    var resolved = matches.map(function (entry) {
      var value = "";
      try { value = view.getComputedStyle(contextEl).getPropertyValue(entry.token).trim(); } catch (_) {}
      return { token: entry.token, value: value, fallback: entry.fallback, looksColor: looksLikeColor(value) };
    });
    var pick = null;
    for (var i = resolved.length - 1; i >= 0; i -= 1) {
      if (resolved[i].looksColor) { pick = resolved[i]; break; }
    }
    if (!pick) pick = resolved[resolved.length - 1];
    return { token: pick.token, hardcoded: false, raw: rawValue, resolvedValue: pick.value || pick.fallback || null };
  }

  function sheetLabel(href) {
    if (!href) return "inline style";
    try {
      var url = new URL(href, location.href);
      var parts = url.pathname.split("/");
      return parts[parts.length - 1] || href;
    } catch (_) {
      return href;
    }
  }

  function warmStylesheetText() {
    if (state.colorSheetWarming) return state.colorSheetWarming;
    var doc = state.frameDocument;
    var hrefs = [];
    try {
      Array.prototype.forEach.call(doc.styleSheets, function (sheet) {
        if (sheet.href && hrefs.indexOf(sheet.href) === -1) hrefs.push(sheet.href);
      });
    } catch (_) {}
    state.colorSheetTextCache = state.colorSheetTextCache || {};
    var cache = state.colorSheetTextCache;
    var pending = hrefs.filter(function (href) { return !(href in cache); });
    if (!pending.length) {
      state.colorSheetWarming = Promise.resolve();
      return state.colorSheetWarming;
    }
    state.colorSheetWarming = Promise.all(pending.map(function (href) {
      return fetch(href)
        .then(function (res) { return res.ok ? res.text() : null; })
        .catch(function () { return null; })
        .then(function (text) { cache[href] = text; });
    })).then(function () {
      if (state.active && state.color && state.colorSheetTextCache === cache) {
        state.colorPanelTarget = undefined;
        state.colorSections = null;
        schedule();
      }
    });
    return state.colorSheetWarming;
  }

  function lineNumberFor(sheetHref, selectorText, cssText, matchedBranch) {
    if (!sheetHref || !state.colorSheetTextCache) return null;
    var text = state.colorSheetTextCache[sheetHref];
    if (!text) return null;
    var idx = -1;
    if (cssText) {
      var declStart = cssText.indexOf("{");
      var head = (declStart > -1 ? cssText.slice(0, declStart) : cssText).trim();
      if (head) idx = text.indexOf(head);
    }
    // Multi-selector rules are frequently authored one selector per line, so
    // the canonical (single-line) cssText/selectorText from the CSSOM often
    // will not appear verbatim in the source. Fall back to the individual
    // matched branch, which is more likely to appear on its own line.
    if (idx === -1 && matchedBranch) idx = text.indexOf(matchedBranch);
    if (idx === -1 && selectorText) idx = text.indexOf(selectorText);
    if (idx === -1) return null;
    return text.slice(0, idx).split("\n").length;
  }

  function borderColorAndSide(cs) {
    var sides = ["Top", "Right", "Bottom", "Left"];
    for (var i = 0; i < sides.length; i += 1) {
      var width = parseFloat(cs["border" + sides[i] + "Width"]) || 0;
      var style = cs["border" + sides[i] + "Style"];
      if (width > 0 && style !== "none" && style !== "hidden") {
        return { color: cs["border" + sides[i] + "Color"], side: sides[i].toLowerCase() };
      }
    }
    return null;
  }

  function collectColorRoles(target) {
    var view = inspectionView();
    var cs = view.getComputedStyle(target);
    var roles = [];
    var isSvgShape = target.namespaceURI === "http://www.w3.org/2000/svg" && target.localName !== "svg";

    if (hasOwnText(target)
        || ["INPUT", "TEXTAREA", "BUTTON", "SELECT", "A", "LABEL", "OPTION"].indexOf(target.tagName) !== -1) {
      roles.push({ key: "text", label: "Text color", computed: cs.color, props: ["color"], inheritable: true, cs: cs });
    }
    roles.push({
      key: "background",
      label: "Background color",
      computed: cs.backgroundColor,
      props: ["background-color", "background"],
      inheritable: false,
      cs: cs,
      isBackground: true
    });
    var border = borderColorAndSide(cs);
    if (border) {
      roles.push({
        key: "border",
        label: "Border color (" + border.side + ")",
        computed: border.color,
        props: ["border-" + border.side + "-color", "border-color", "border", "border-" + border.side],
        inheritable: false,
        cs: cs
      });
    }
    if (isSvgShape) {
      if (cs.fill && cs.fill !== "none") {
        roles.push({ key: "fill", label: "SVG fill", computed: cs.fill, props: ["fill"], inheritable: true, cs: cs });
      }
      if (cs.stroke && cs.stroke !== "none") {
        roles.push({ key: "stroke", label: "SVG stroke", computed: cs.stroke, props: ["stroke"], inheritable: true, cs: cs });
      }
    }
    if (state.frameDocument.activeElement === target
        && cs.outlineStyle !== "none" && (parseFloat(cs.outlineWidth) || 0) > 0) {
      roles.push({
        key: "outline",
        label: "Outline / focus color",
        computed: cs.outlineColor,
        props: ["outline-color", "outline"],
        inheritable: false,
        cs: cs
      });
    }
    if ((target.tagName === "INPUT" || target.tagName === "TEXTAREA") && target.hasAttribute("placeholder")) {
      var placeholderCs = view.getComputedStyle(target, "::placeholder");
      roles.push({
        key: "placeholder",
        label: "Placeholder color",
        computed: placeholderCs.color,
        props: ["color"],
        inheritable: false,
        cs: placeholderCs,
        pseudo: true
      });
    }
    return roles;
  }

  function describeElement(el) {
    var id = el.id ? "#" + el.id : "";
    var cls = el.classList && el.classList.length
      ? "." + Array.prototype.slice.call(el.classList).slice(0, 2).join(".")
      : "";
    return el.tagName.toLowerCase() + id + cls;
  }

  // Color detail now renders inside the persistent right inspector instead
  // of a floating popover over the product UI.
  function inspectorEl() {
    if (!state.colorPanel && state.root) {
      state.colorPanel = state.root.querySelector("[data-redline-inspector]");
    }
    return state.colorPanel;
  }

  function copyButton(label, value) {
    var btn = element("button", "redline__color-copy-btn", {
      type: "button",
      "data-redline-action": "copy"
    });
    btn.textContent = "Copy " + label;
    btn.setAttribute("data-copy-label", label);
    if (value === null || value === undefined || value === "") {
      btn.disabled = true;
    } else {
      btn.setAttribute("data-copy-text", String(value));
    }
    return btn;
  }

  function colorRow(labelText, valueText, extraClass) {
    var row = element("div", "redline__color-row" + (extraClass ? " " + extraClass : ""));
    var label = element("span", "");
    label.textContent = labelText;
    var value = element("code", "");
    value.textContent = valueText;
    row.appendChild(label);
    row.appendChild(value);
    return row;
  }

  function buildRoleSection(target, role) {
    var rgba = parseColorToRgba(role.computed) || { r: 0, g: 0, b: 0, a: 1 };
    var hex = rgbaToHex(rgba);
    var rgbText = rgbaToText(rgba);
    var winning = findWinningDeclaration(target, role.props, role.pseudo);
    var source = winning ? extractColorSource(winning.raw, target) : null;
    var tokenDisplay = source && source.token ? source.token : "Unmapped";

    var inherited = Boolean(role.inheritable && !winning && target.parentElement);

    var sourceLabel = "Not detected";
    if (winning) {
      sourceLabel = winning.inline
        ? "Inline style attribute"
        : sheetLabel(winning.sheetHref) + (function () {
          var line = winning.sheetHref
            ? lineNumberFor(winning.sheetHref, winning.selectorText, winning.cssText, winning.matchedBranch)
            : null;
          return line ? ":" + line : "";
        }());
    } else if (inherited) {
      sourceLabel = "Inherited (no rule on this element)";
    }

    var hardcodedText = "Not detected";
    if (source) hardcodedText = source.hardcoded ? "Yes (literal value)" : "No (uses a token)";

    var section = element("div", "redline__color-role");
    var head = element("div", "redline__color-role-head");
    var swatch = element("span", "redline__color-swatch");
    swatch.style.background = rgbText;
    var name = element("span", "redline__color-role-name");
    name.textContent = role.label;
    head.appendChild(swatch);
    head.appendChild(name);
    section.appendChild(head);

    section.appendChild(colorRow("Token", tokenDisplay));
    section.appendChild(colorRow("Hex", hex));
    section.appendChild(colorRow("RGB", rgbText));
    section.appendChild(colorRow("Selector", winning ? winning.selectorText : (inherited ? "Inherited from ancestor" : "Not detected")));
    section.appendChild(colorRow("Source", sourceLabel));
    section.appendChild(colorRow("Inherited", inherited ? "Yes" : "No"));
    section.appendChild(colorRow("Hardcoded", hardcodedText));

    if (role.isBackground) {
      var effective = effectiveBackgroundChain(target);
      if (!effective.isOwn) {
        var effHex = rgbaToHex(effective.rgba);
        section.appendChild(colorRow(
          "Effective (rendered)",
          effHex + " from " + (effective.sourceNode ? describeElement(effective.sourceNode) : "page canvas")
        ));
      }
    }

    var primaryProp = role.props[0];
    var cssDeclaration = primaryProp + ": " + (source && source.token ? ("var(" + source.token + ", " + hex + ")") : hex) + ";";
    var copyRow = element("div", "redline__color-copy-row");
    copyRow.appendChild(copyButton("Token", source && source.token ? source.token : null));
    copyRow.appendChild(copyButton("Hex", hex));
    copyRow.appendChild(copyButton("RGB", rgbText));
    copyRow.appendChild(copyButton("CSS", cssDeclaration));
    section.appendChild(copyRow);

    if (role.key === "text") {
      var bg = effectiveBackgroundChain(target);
      var ratio = contrastRatio(rgba.a < 1 ? compositeOver(rgba, bg.rgba) : rgba, bg.rgba);
      var large = isLargeText(role.cs);
      var aaPass = ratio >= (large ? 3 : 4.5);
      var aaaPass = ratio >= (large ? 4.5 : 7);
      var contrastSection = element("div", "redline__color-role redline__color-role--contrast");
      var contrastHead = element("div", "redline__color-role-head");
      var contrastName = element("span", "redline__color-role-name");
      contrastName.textContent = "Contrast (vs. effective background)";
      contrastHead.appendChild(contrastName);
      contrastSection.appendChild(contrastHead);
      contrastSection.appendChild(colorRow("Ratio", ratio.toFixed(2) + ":1"));
      contrastSection.appendChild(colorRow(
        "WCAG AA" + (large ? " (large text)" : ""),
        aaPass ? "Pass" : "Fail",
        aaPass ? "redline__color-contrast--pass" : "redline__color-contrast--fail"
      ));
      contrastSection.appendChild(colorRow(
        "WCAG AAA" + (large ? " (large text)" : ""),
        aaaPass ? "Pass" : "Fail",
        aaaPass ? "redline__color-contrast--pass" : "redline__color-contrast--fail"
      ));
      section.appendChild(contrastSection);
    }

    return section;
  }

  function inspectorSection(titleText) {
    var node = element("div", "redline__inspect-group");
    var title = element("div", "redline__inspect-title");
    title.textContent = titleText;
    node.appendChild(title);
    return node;
  }

  // A labelled value row, matching the inspector's compact presentation.
  function inspectRow(labelText, valueText) {
    var row = element("div", "redline__inspect-row");
    var label = element("span", "redline__inspect-label");
    label.textContent = labelText;
    var value = element("code", "redline__inspect-value");
    value.textContent = valueText;
    row.appendChild(label);
    row.appendChild(value);
    return row;
  }

  // Reports a design-system mapping only when one is actually detectable.
  // Anything else is explicitly labelled unmapped rather than guessed at.
  function mappingStatus(el) {
    var classes = Array.prototype.slice.call(el.classList || []);
    var adsClass = classes.find(function (name) {
      return name.indexOf("ads-") === 0;
    });
    if (adsClass) return "ADS component class (." + adsClass + ")";
    var componentAttr = Array.prototype.find.call(el.attributes, function (attr) {
      return attr.name.indexOf("data-v2-") === 0
        || attr.name.indexOf("data-lc-") === 0;
    });
    if (componentAttr) return "Application component (" + componentAttr.name + ")";
    return "Unmapped, no design-system class detected";
  }

  function sideValues(style, prefix) {
    return ["Top", "Right", "Bottom", "Left"].map(function (side) {
      return rounded(parseFloat(style[prefix + side]) || 0);
    }).join(" ");
  }

  function buildIdentitySection(target) {
    var group = inspectorSection("Component");
    group.appendChild(inspectRow("Element", target.tagName.toLowerCase()));
    if (target.id) group.appendChild(inspectRow("Id", "#" + target.id));
    if (target.classList && target.classList.length) {
      group.appendChild(inspectRow(
        "Class",
        "." + Array.prototype.slice.call(target.classList).join(" .")
      ));
    }
    group.appendChild(inspectRow("Mapping", mappingStatus(target)));
    return group;
  }

  // All values are reported in logical CSS pixels, never scaled display px.
  function buildDimensionSection(target) {
    var raw = target.getBoundingClientRect();
    var group = inspectorSection("Dimensions");
    group.appendChild(inspectRow("Width", rounded(raw.width) + "px"));
    group.appendChild(inspectRow("Height", rounded(raw.height) + "px"));
    group.appendChild(inspectRow("X", rounded(raw.left) + "px"));
    group.appendChild(inspectRow("Y", rounded(raw.top) + "px"));
    return group;
  }

  function buildSpacingSection(target) {
    var style = inspectionView().getComputedStyle(target);
    var group = inspectorSection("Spacing");
    group.appendChild(inspectRow("Padding", sideValues(style, "padding")));
    group.appendChild(inspectRow("Margin", sideValues(style, "margin")));
    var gap = parseFloat(style.gap);
    if (Number.isFinite(gap) && gap > 0) {
      group.appendChild(inspectRow("Gap", rounded(gap) + "px"));
    }
    var radius = parseFloat(style.borderRadius);
    if (Number.isFinite(radius) && radius > 0) {
      group.appendChild(inspectRow("Radius", rounded(radius) + "px"));
    }
    return group;
  }

  function buildLayoutSection(target) {
    var style = inspectionView().getComputedStyle(target);
    var parent = target.parentElement;
    var group = inspectorSection("Layout");
    group.appendChild(inspectRow("Display", style.display));
    group.appendChild(inspectRow("Position", style.position));
    group.appendChild(inspectRow(
      "Parent",
      parent ? describeElement(parent) : "none"
    ));
    group.appendChild(inspectRow("Child count", String(target.children.length)));
    return group;
  }

  function buildTypographySection(target) {
    var group = inspectorSection("Typography");
    var style = inspectionView().getComputedStyle(target);
    if (!hasOwnText(target)
        && ["INPUT", "TEXTAREA", "BUTTON", "SELECT", "A", "LABEL", "OPTION"]
          .indexOf(target.tagName) === -1) {
      group.appendChild(inspectRow("Text", "No text on this element"));
      return group;
    }
    var lineHeight = parseFloat(style.lineHeight);
    var winning = findWinningDeclaration(target, ["color"], false);
    var source = winning ? extractColorSource(winning.raw, target) : null;
    group.appendChild(inspectRow(
      "Font family",
      style.fontFamily.split(",")[0].replace(/["']/g, "")
    ));
    group.appendChild(inspectRow(
      "Font size",
      rounded(parseFloat(style.fontSize)) + "px"
    ));
    group.appendChild(inspectRow("Font weight", style.fontWeight));
    group.appendChild(inspectRow(
      "Line height",
      Number.isFinite(lineHeight) ? rounded(lineHeight) + "px" : style.lineHeight
    ));
    group.appendChild(inspectRow(
      "Letter spacing",
      style.letterSpacing === "normal"
        ? "normal"
        : rounded(parseFloat(style.letterSpacing)) + "px"
    ));
    group.appendChild(inspectRow("Text color", style.color));
    group.appendChild(inspectRow(
      "Color token",
      source && source.token ? source.token : "Unmapped"
    ));
    group.appendChild(inspectRow("Text align", style.textAlign));
    return group;
  }

  // Color role resolution walks stylesheet rules, so it is cached per
  // target. The cheap geometry sections are always rebuilt so the inspector
  // never reports stale values after a reflow or breakpoint change.
  function colorSectionsFor(target) {
    if (target === state.colorPanelTarget && state.colorSections) {
      return state.colorSections;
    }
    warmStylesheetText();
    var roles = collectColorRoles(target);
    var sections;
    if (!roles.length) {
      var none = inspectorSection("Color");
      none.appendChild(inspectRow("Color", "No inspectable colors"));
      sections = [none];
    } else {
      sections = roles.map(function (role) {
        return buildRoleSection(target, role);
      });
    }
    state.colorPanelTarget = target;
    state.colorSections = sections;
    return sections;
  }

  function renderInspector(target) {
    var panel = inspectorEl();
    if (!panel) return;
    if (target !== state.colorPanelTarget) {
      state.colorPanelTarget = target;
      state.colorSections = null;
    }
    panel.replaceChildren();

    if (!target) {
      var empty = element("div", "redline__inspect-empty");
      INSPECTOR_EMPTY.forEach(function (copy) {
        var paragraph = element("p", "");
        paragraph.textContent = copy;
        empty.appendChild(paragraph);
      });
      panel.appendChild(empty);
      return;
    }

    var heading = element("div", "redline__inspect-heading");
    heading.textContent = describeElement(target);
    panel.appendChild(heading);

    panel.appendChild(buildIdentitySection(target));
    panel.appendChild(buildDimensionSection(target));
    panel.appendChild(buildSpacingSection(target));
    panel.appendChild(buildLayoutSection(target));
    if (state.typography) panel.appendChild(buildTypographySection(target));
    if (state.color) {
      colorSectionsFor(target).forEach(function (node) {
        panel.appendChild(node);
      });
    }
  }

  function refreshInspector() {
    state.colorPanelTarget = undefined;
    state.colorSections = null;
    renderInspector(state.locked || state.hovered || null);
  }

  function updateSelectionSummary(target) {
    if (!state.root) return;
    var summary = state.root.querySelector("[data-redline-selection]");
    if (!summary) return;
    summary.textContent = target ? describeElement(target) : EMPTY_SELECTION;
    summary.setAttribute("data-empty", target ? "false" : "true");
  }

  function copyColorValue(control) {
    var text = control.getAttribute("data-copy-text") || "";
    if (!text) return;
    function done(ok) {
      control.setAttribute("data-copied", ok ? "true" : "false");
      setStatus(ok
        ? "Copied " + (control.getAttribute("data-copy-label") || "value") + " to clipboard."
        : "Copy failed.");
      window.setTimeout(function () {
        if (control.isConnected) control.removeAttribute("data-copied");
      }, 1200);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () { done(true); }, function () { done(false); });
      return;
    }
    try {
      var scratch = document.createElement("textarea");
      scratch.value = text;
      scratch.style.position = "fixed";
      scratch.style.opacity = "0";
      document.body.appendChild(scratch);
      scratch.select();
      document.execCommand("copy");
      scratch.remove();
      done(true);
    } catch (_) {
      done(false);
    }
  }

  function inspectionViewportRect() {
    if (usingFrame() && state.frame) return state.frame.getBoundingClientRect();
    var canvas = canvasRect();
    return {
      left: canvas.left,
      top: canvas.top,
      right: canvas.right,
      bottom: canvas.bottom,
      width: canvas.right - canvas.left,
      height: canvas.bottom - canvas.top
    };
  }

  function updateDimming(activeRect) {
    var frameRect = inspectionViewportRect();
    var panes = state.root.querySelectorAll("[data-redline-dim]");
    var hole = activeRect || {
      left: frameRect.left,
      top: frameRect.top,
      right: frameRect.left,
      bottom: frameRect.top
    };
    // Dimming exists to spotlight a selected element. With nothing selected
    // the panes collapse so the product preview renders unchanged.
    var boxes = activeRect ? [
      [frameRect.left, frameRect.top, frameRect.width, Math.max(0, hole.top - frameRect.top)],
      [frameRect.left, hole.bottom, frameRect.width, Math.max(0, frameRect.bottom - hole.bottom)],
      [frameRect.left, hole.top, Math.max(0, hole.left - frameRect.left), Math.max(0, hole.height)],
      [hole.right, hole.top, Math.max(0, frameRect.right - hole.right), Math.max(0, hole.height)]
    ] : [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]];
    panes.forEach(function (pane, index) {
      var box = boxes[index];
      pane.style.left = rounded(box[0]) + "px";
      pane.style.top = rounded(box[1]) + "px";
      pane.style.width = rounded(box[2]) + "px";
      pane.style.height = rounded(box[3]) + "px";
    });
  }

  /* Wipes every drawn annotation. Used whenever there is nothing valid to
   * measure, so a failed or still-loading preview can never leave the
   * previous document's overlays on screen. */
  function clearOverlays() {
    if (!state.root) return;
    var svg = state.root.querySelector("[data-redline-svg]");
    var labels = state.root.querySelector("[data-redline-labels]");
    var grid = state.root.querySelector("[data-redline-grid]");
    if (svg) svg.replaceChildren();
    if (labels) labels.replaceChildren();
    if (grid) grid.hidden = true;
    state.root.querySelectorAll("[data-redline-dim]").forEach(function (pane) {
      pane.style.width = "0px";
      pane.style.height = "0px";
    });
    updateSelectionSummary(null);
    renderInspector(null);
  }

  function render() {
    if (!state.active) return;
    // A preset breakpoint measures the preview document. While that preview
    // is loading or has failed there is nothing to measure, and drawing
    // against the parent page instead would put overlays on the wrong
    // geometry entirely.
    if (usingFrame() && state.previewPhase !== "ready") {
      clearOverlays();
      return;
    }
    if (!state.frameDocument) return;
    state.renderCount += 1;
    var svg = state.root.querySelector("[data-redline-svg]");
    var labels = state.root.querySelector("[data-redline-labels]");
    var grid = state.root.querySelector("[data-redline-grid]");
    var frameRect = inspectionViewportRect();
    prepareSvg(svg);
    labels.replaceChildren();
    var addLabel = labelPlacer(labels, svg);
    grid.hidden = !state.showGridOverlay;
    grid.style.left = rounded(frameRect.left) + "px";
    grid.style.top = rounded(frameRect.top) + "px";
    grid.style.width = rounded(frameRect.width) + "px";
    grid.style.height = rounded(frameRect.height) + "px";
    var gridStep = 8 * (usingFrame() ? state.previewScale : 1);
    grid.style.backgroundSize = gridStep + "px " + gridStep + "px";

    var target = state.locked || state.hovered;
    if (target && !target.isConnected) {
      if (state.locked === target) state.locked = null;
      if (state.hovered === target) state.hovered = null;
      target = null;
    }
    var activeRect = target && visible(target)
      ? clampRectToFrame(mapRect(target.getBoundingClientRect()))
      : null;
    updateDimming(activeRect);
    // Summary and inspector always describe the same target, so an element
    // that cannot be measured is never reported as selected.
    var inspected = activeRect ? target : null;
    updateSelectionSummary(inspected);

    if (activeRect) {
      boundary(svg, activeRect);
      if (state.showLines) drawMeasurementLines(svg, addLabel, activeRect);
    } else if (!target) {
      // Idle overview: outline the major landmarks so the inspectable
      // regions are discoverable before the first hover.
      majorTargets().forEach(function (item) {
        boundary(
          svg,
          clampRectToFrame(mapRect(item.getBoundingClientRect())),
          "redline__alignment"
        );
      });
    }

    renderInspector(inspected);
  }

  /* =====================================================================
   *  STAGED SURFACES: OVERLAY GALLERIES AND TABLE COMPONENTS
   *
   *  Redline never builds product markup itself. It asks a registry
   *  inside the preview to stage each entry using the application's own
   *  components and copy, then inspects the result exactly like any
   *  other page content. Two registries, both defined in app.js and both
   *  the same shape, so everything below is written once:
   *
   *    RateCardOverlayGallery    modals and toasts, staged over a page
   *    RateCardComponentGallery  parts of a screen, staged in place
   * ===================================================================== */

  function isComponentMode(mode) {
    return COMPONENT_ENTRY_ROWS.some(function (row) { return row.mode === mode; });
  }

  function galleryApi() {
    if (!state.frame) return null;
    try {
      var win = state.frame.contentWindow;
      var api = win && (isComponentMode(state.previewMode)
        ? win.RateCardComponentGallery
        : win.RateCardOverlayGallery);
      return api && typeof api.open === "function" ? api : null;
    } catch (_) {
      return null;
    }
  }

  function galleryKind() {
    if (state.previewMode === PREVIEW_MODES.TOAST) return "toast";
    if (state.previewMode === PREVIEW_MODES.ACTION_BAR) return "action-bar";
    return "modal";
  }

  function currentGalleryEntry() {
    return state.galleryEntries[state.galleryIndex] || null;
  }

  /* A component's states are listed in the panel next to the entry that
   * opened it, so a selection count can be picked directly instead of
   * stepped through. The list is built from whatever the preview's
   * registry reports, so a state added in app.js appears here. */
  function syncComponentStates() {
    if (!state.root) return;
    var list = state.root.querySelector("[data-redline-states]");
    var hint = state.root.querySelector("[data-redline-component-hint]");
    if (!list) return;
    var active = isComponentMode(state.previewMode);
    list.hidden = !active || state.galleryEntries.length === 0;
    if (hint) hint.hidden = !active;
    if (!active) {
      list.replaceChildren();
      return;
    }
    list.replaceChildren();
    state.galleryEntries.forEach(function (entry, index) {
      var item = element("button", "redline__state-button", {
        type: "button",
        "data-redline-action": "state:" + index,
        "aria-pressed": index === state.galleryIndex ? "true" : "false",
        title: entry.description || entry.stateName || entry.name
      });
      item.textContent = entry.stateName || entry.name;
      list.appendChild(item);
    });
    if (hint) {
      var entry = currentGalleryEntry();
      hint.textContent = entry && entry.description
        ? entry.description
        : "Preview only. Nothing pressed here reaches a rate card.";
    }
  }

  function syncGalleryControls() {
    if (!state.root) return;
    state.root.setAttribute("data-preview-mode", state.previewMode);
    state.root.querySelectorAll('[data-redline-action^="gallery:"]').forEach(function (item) {
      var action = item.getAttribute("data-redline-action").slice("gallery:".length);
      if (action === state.previewMode) item.setAttribute("aria-pressed", "true");
      else if (entryRowFor(action)) item.setAttribute("aria-pressed", "false");
    });
    syncComponentStates();

    var bar = state.root.querySelector("[data-redline-gallery]");
    if (!bar) return;
    bar.hidden = !inGallery();
    if (!inGallery()) return;

    var label = bar.querySelector("[data-redline-gallery-label]");
    var total = state.galleryEntries.length;
    var entry = currentGalleryEntry();
    if (label) {
      label.textContent = entry
        ? entry.name + (entry.stateName ? ", " + entry.stateName : "")
          + " \u00b7 " + (state.galleryIndex + 1) + " of " + total
        : (isComponentMode(state.previewMode)
          ? "No states registered"
          : "No overlays registered");
      // The label truncates, so the full name stays readable on hover.
      label.title = label.textContent;
    }
    // Boundaries are disabled rather than wrapped, so the index readout is
    // always an honest position in the list.
    var previous = bar.querySelector('[data-redline-action="gallery:previous"]');
    var next = bar.querySelector('[data-redline-action="gallery:next"]');
    if (previous) previous.disabled = state.galleryIndex <= 0;
    if (next) next.disabled = state.galleryIndex >= total - 1;
    var reset = bar.querySelector('[data-redline-action="gallery:reset"]');
    if (reset) reset.disabled = !entry;
  }

  function loadGalleryEntries() {
    var api = galleryApi();
    if (!api) {
      state.galleryEntries = [];
      return false;
    }
    try {
      state.galleryEntries = api.entries(galleryKind()) || [];
    } catch (_) {
      state.galleryEntries = [];
    }
    if (state.galleryIndex >= state.galleryEntries.length) state.galleryIndex = 0;
    return state.galleryEntries.length > 0;
  }

  // Switching entries always tears the previous overlay down first, so no
  // two fixtures are ever on screen at once and stale selections are dropped
  // before the next overlay mounts.
  function showGalleryEntry() {
    var api = galleryApi();
    var entry = currentGalleryEntry();
    if (!api || !entry) {
      syncGalleryControls();
      return;
    }
    state.hovered = null;
    state.locked = null;
    var opened = false;
    state.galleryStaging = true;
    try {
      opened = api.open(entry.id);
    } catch (_) {
      opened = false;
    } finally {
      state.galleryStaging = false;
    }
    syncGalleryControls();
    setStatus(opened
      ? entry.name + (entry.stateName ? ", " + entry.stateName : "") + " shown."
      : (state.previewMode === PREVIEW_MODES.ACTION_BAR
        ? "The Action Bar could not be staged. It is a 2.1 table component, "
          + "so the preview has to be running version 2.1."
        : "This overlay could not be staged in the preview."));
    // Fixtures, fonts and icons settle over a couple of frames, so geometry
    // is recalculated after layout rather than against the mount frame.
    window.requestAnimationFrame(function () {
      window.requestAnimationFrame(function () {
        schedule();
        window.setTimeout(schedule, 160);
      });
    });
  }

  function stepGallery(delta) {
    if (!inGallery() || !state.galleryEntries.length) return;
    selectGalleryEntry(state.galleryIndex + delta);
  }

  function selectGalleryEntry(index) {
    if (!inGallery() || !state.galleryEntries.length) return;
    if (!Number.isInteger(index)) return;
    if (index < 0 || index >= state.galleryEntries.length) return;
    state.galleryIndex = index;
    showGalleryEntry();
  }

  function closeGalleryOverlays() {
    var api = galleryApi();
    if (!api) return;
    state.galleryStaging = true;
    try { api.close(); } catch (_) {} finally { state.galleryStaging = false; }
  }

  function setPreviewMode(mode) {
    if (state.previewMode === mode) return;
    var leavingGallery = inGallery();
    if (leavingGallery) closeGalleryOverlays();
    state.previewMode = mode;
    state.hovered = null;
    state.locked = null;
    syncSourcePageInert();

    if (mode === PREVIEW_MODES.CURRENT) {
      state.galleryEntries = [];
      state.galleryIndex = 0;
      syncGalleryControls();
      // Returning to the page restores the screen the user entered from,
      // including any route the gallery had to visit to reach an overlay.
      state.appSnapshotApplied = false;
      restoreAppSnapshot();
      if (!state.breakpoint) {
        // Current breakpoint inspects the live document again, so the frame
        // that only existed to isolate gallery fixtures is stood down.
        state.frame.hidden = true;
        state.frameShell.hidden = true;
        state.frame.style.width = "";
        state.frame.style.height = "";
        state.frameShell.removeAttribute("style");
        state.previewScale = 1;
        previewReady();
        attachCurrent();
      }
      syncViewportInfo();
      setStatus("Back to the current page.");
      schedule();
      return;
    }

    state.galleryIndex = 0;
    syncGalleryControls();

    if (!state.breakpoint) {
      // Stage the isolated preview at the real window size so opening a
      // gallery never silently changes the selected breakpoint.
      state.frame.hidden = false;
      state.frameShell.hidden = false;
      fitBreakpointPreview();
    }
    syncViewportInfo();

    var nextUrl = previewUrl();
    if (state.frame.src !== nextUrl) {
      previewLoading();
      state.frame.src = nextUrl;
      return;
    }
    if (state.frameDocument !== state.frame.contentDocument) {
      // Current page inspects the live document, so the frame it left
      // behind is still loaded but no longer observed. Re-attaching points
      // inspection back at the preview and stages the entry from there.
      attachFrame();
      return;
    }
    if (!loadGalleryEntries()) {
      setStatus(isComponentMode(mode)
        ? "The component registry is not available in this preview."
        : "The overlay registry is not available in this preview.");
      syncGalleryControls();
      return;
    }
    showGalleryEntry();
  }

  function setBreakpoint(id) {
    if (id === "current" || id === state.breakpoint) {
      state.breakpoint = "";
      syncSourcePageInert();
      state.previewScale = 1;
      document.documentElement.classList.remove("redline-breakpoint-preview");
      state.root.setAttribute("data-breakpoint-active", "false");
      state.root.querySelectorAll('[data-redline-action^="breakpoint:"]').forEach(function (item) {
        item.setAttribute(
          "aria-pressed",
          item.getAttribute("data-redline-action") === "breakpoint:current"
            ? "true"
            : "false"
        );
      });
      if (inGallery()) {
        // A gallery always needs the isolated preview, so Current only
        // changes the logical viewport it is sized to.
        fitBreakpointPreview();
        syncViewportInfo();
        setStatus("Current browser width selected.");
        schedule();
        return;
      }
      state.frame.hidden = true;
      state.frameShell.hidden = true;
      state.frame.style.width = "";
      state.frame.style.height = "";
      state.frameShell.removeAttribute("style");
      // The live document is always available, so any pending preview
      // load state stops applying the moment Current is selected.
      state.previewToken += 1;
      previewReady();
      attachCurrent();
      syncViewportInfo();
      setStatus("Current browser width selected.");
      schedule();
      return;
    }
    var preset = BREAKPOINTS.find(function (item) { return item.id === id; });
    if (!preset || !state.frame) return;
    state.breakpoint = id;
    syncSourcePageInert();
    document.documentElement.classList.add("redline-breakpoint-preview");
    state.root.setAttribute("data-breakpoint-active", "true");
    state.root.querySelectorAll('[data-redline-action^="breakpoint:"]').forEach(function (item) {
      item.setAttribute(
        "aria-pressed",
        item.getAttribute("data-redline-action") === "breakpoint:" + id ? "true" : "false"
      );
    });
    state.frame.hidden = false;
    state.frameShell.hidden = false;
    fitBreakpointPreview();
    var nextUrl = previewUrl();
    if (state.frame.src !== nextUrl) {
      // First preset of the session: the preview boots once here. Later
      // preset changes only resize this same instance, so the product is
      // never remounted and nothing it holds in memory is lost.
      previewLoading();
      state.frame.src = nextUrl;
    } else if (state.frameDocument !== state.frame.contentDocument) {
      attachFrame();
    } else {
      previewReady();
      schedule();
    }
    syncViewportInfo();
    setStatus(preset.width + " \u00d7 " + preset.height + " preview selected.");
    schedule();
    window.setTimeout(schedule, window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 320);
  }

  function setControlPressed(name) {
    var control = state.root.querySelector('[data-redline-action="toggle:' + name + '"]');
    if (control) control.setAttribute("aria-pressed", state[name] ? "true" : "false");
  }

  // Measurement mode is a single choice, so selecting one always deselects
  // the other. It changes interpretation only, never the selection or the
  // annotations that are drawn.
  function setMeasurementMode(mode) {
    if (!MEASUREMENT_MODES.some(function (item) { return item.id === mode; })) return;
    state.measurementMode = mode;
    state.root.querySelectorAll('[data-redline-action^="mode:"]').forEach(function (item) {
      item.setAttribute(
        "aria-pressed",
        item.getAttribute("data-redline-action") === "mode:" + mode ? "true" : "false"
      );
    });
    var hint = state.root.querySelector("[data-redline-mode-hint]");
    if (hint) hint.textContent = measurementHint(mode);
    setStatus(
      (mode === "grid" ? "8pt Grid" : "Clean Spec") + " measurement mode selected."
    );
    schedule();
  }

  // Annotation toggles are independent of each other and of the mode.
  function setAnnotation(name, checked) {
    if (name === "lines") state.showLines = checked;
    if (name === "grid-overlay") state.showGridOverlay = checked;
    schedule();
  }

  function setLayer(name) {
    state[name] = !state[name];
    // Typography and Color are alternate inspection views, so only one may
    // be active at a time (preserved from the previous behavior).
    if (name === "typography" && state.typography && state.color) {
      state.color = false;
      setControlPressed("color");
    }
    if (name === "color" && state.color && state.typography) {
      state.typography = false;
      setControlPressed("typography");
    }
    setControlPressed(name);
    refreshInspector();
    schedule();
  }

  // Drawer state only affects the Redline shell, never the logical preview
  // viewport, so the product breakpoint is untouched here.
  function togglePanel(side) {
    var attribute = side === "left" ? "data-panel-left" : "data-panel-right";
    var open = state.root.getAttribute(attribute) === "open";
    state.root.setAttribute(attribute, open ? "closed" : "open");
    var control = state.root.querySelector(
      '[data-redline-action="panel:' + side + '"]'
    );
    if (control) control.setAttribute("aria-expanded", open ? "false" : "true");
    schedule();
  }

  function setPreviewSidebar(mode) {
    var doc = state.frameDocument || document;
    if (!doc) return;
    var shell = doc.defaultView && doc.defaultView.RateCardShell;
    var pinned = mode === "expanded";
    if (shell && typeof shell.setVnavPinned === "function") {
      shell.setVnavPinned(pinned);
    } else {
      var vnav = doc.querySelector(".vnav");
      if (vnav) vnav.classList.toggle("vnav--pinned", pinned);
      if (pinned) doc.body.setAttribute("data-vnav-pinned", "1");
      else doc.body.removeAttribute("data-vnav-pinned");
    }
    if (state.root) {
      state.root.querySelectorAll('[data-redline-action^="sidebar:"]').forEach(function (item) {
        var id = item.getAttribute("data-redline-action").split(":")[1];
        item.setAttribute("aria-pressed", id === mode ? "true" : "false");
      });
    }
    schedule();
  }

  function onWorkspaceClick(event) {
    var control = event.target.closest("[data-redline-action]");
    if (!control) return;
    var action = control.getAttribute("data-redline-action");
    if (action === "close") {
      disable();
    } else if (action.indexOf("panel:") === 0) {
      togglePanel(action.split(":")[1]);
    } else if (action.indexOf("breakpoint:") === 0) {
      setBreakpoint(action.split(":")[1]);
    } else if (action.indexOf("mode:") === 0) {
      setMeasurementMode(action.split(":")[1]);
    } else if (action.indexOf("toggle:") === 0) {
      setLayer(action.split(":")[1]);
    } else if (action === "gallery:back") {
      setPreviewMode(PREVIEW_MODES.CURRENT);
    } else if (action === "gallery:previous") {
      stepGallery(-1);
    } else if (action === "gallery:next") {
      stepGallery(1);
    } else if (action === "gallery:reset") {
      showGalleryEntry();
    } else if (action.indexOf("gallery:") === 0) {
      var requested = action.slice("gallery:".length);
      // The entry rows are navigation, not a toggle. Pressing the row for
      // the gallery that is already open restages its entry rather than
      // dropping the user back to the page; Back to page is the way out.
      if (state.previewMode === requested) showGalleryEntry();
      else setPreviewMode(requested);
    } else if (action.indexOf("state:") === 0) {
      selectGalleryEntry(Number(action.split(":")[1]));
    } else if (action.indexOf("sidebar:") === 0) {
      setPreviewSidebar(action.split(":")[1]);
    } else if (action === "preview:retry") {
      retryPreview();
    } else if (action === "copy") {
      copyColorValue(control);
    }
  }

  function onWorkspaceChange(event) {
    var control = event.target.closest("[data-redline-action]");
    if (!control) return;
    var action = control.getAttribute("data-redline-action");
    if (action.indexOf("annotation:") === 0) {
      setAnnotation(action.split(":")[1], control.checked);
    }
  }

  function portfolioPresentation() {
    return document.body.getAttribute("data-deck-variant") === "portfolio"
      && document.body.getAttribute("data-route") === "atlas";
  }

  function enable(source) {
    if (state.active || isPreview() || portfolioPresentation()) return;
    state.active = true;
    state.lastFocus = document.activeElement;
    state.measurementMode = "clean";
    state.showLines = true;
    state.showGridOverlay = false;
    state.typography = false;
    state.color = false;
    state.breakpoint = "";
    state.previewScale = 1;
    state.renderCount = 0;
    state.currentListenersAttached = false;
    state.colorPanel = null;
    state.colorPanelTarget = undefined;
    state.colorSections = null;
    state.colorSheetCache = null;
    state.colorSheetCacheDoc = null;
    state.colorSheetTextCache = null;
    state.colorSheetWarming = null;
    state.previewPhase = "idle";
    state.previewToken = 0;
    state.appSnapshotApplied = false;
    // Redline always opens on the page the user was looking at.
    state.previewMode = PREVIEW_MODES.CURRENT;
    state.galleryEntries = [];
    state.galleryIndex = 0;
    // Taken before any Redline chrome mounts, so the snapshot describes
    // the screen exactly as the user was looking at it.
    state.appSnapshot = captureAppSnapshot();
    state.storageSnapshot = {};
    try {
      for (var storageIndex = 0; storageIndex < localStorage.length; storageIndex += 1) {
        var storageKey = localStorage.key(storageIndex);
        state.storageSnapshot[storageKey] = localStorage.getItem(storageKey);
      }
    } catch (_) {
      state.storageSnapshot = null;
    }
    state.aborter = new AbortController();
    var built = buildRoot();
    state.root = built.root;
    state.frameShell = built.frameShell;
    state.frame = built.frame;
    document.body.appendChild(state.root);
    syncSourcePageInert();
    syncMenuState();
    state.frame.addEventListener("load", attachFrame, {
      signal: state.aborter.signal
    });
    state.frame.addEventListener("error", function () {
      classifyPreviewFailure(state.previewToken, "The preview frame reported a load error.");
    }, { signal: state.aborter.signal });
    state.root.addEventListener("click", onWorkspaceClick, {
      signal: state.aborter.signal
    });
    state.root.addEventListener("change", onWorkspaceChange, {
      signal: state.aborter.signal
    });
    state.root.querySelector(".redline__stage").addEventListener("scroll", schedule, {
      passive: true,
      signal: state.aborter.signal
    });
    window.addEventListener("resize", function () {
      fitBreakpointPreview();
      syncViewportInfo();
      schedule();
    }, {
      passive: true,
      signal: state.aborter.signal
    });
    state.parentObserver = new MutationObserver(function (records) {
      var routeChanged = records.some(function (record) {
        return record.target === document.body
          && ["data-route", "data-version", "data-mode"].indexOf(record.attributeName) >= 0;
      });
      syncVersionBadge();
      if (routeChanged && state.frame) {
        // A gallery drives the preview's own route to reach overlays, so a
        // reload here would tear down the entry that is being inspected.
        if (inGallery()) schedule();
        else if (state.breakpoint) state.frame.src = previewUrl();
        else schedule();
      }
    });
    state.parentObserver.observe(document.body, {
      attributes: true,
      attributeFilter: ["data-route", "data-version", "data-mode"]
    });
    syncViewportInfo();
    renderInspector(null);
    updateSelectionSummary(null);
    attachCurrent();
    setStatus("Redline Mode active" + (source ? " from " + source + "." : "."));
  }

  function disable() {
    if (!state.active) return;
    var focusTarget = state.lastFocus;
    // Overlay fixtures are disposed through the product's own close paths
    // before the preview goes away, so no timers or portal nodes survive.
    if (inGallery()) closeGalleryOverlays();
    state.previewMode = PREVIEW_MODES.CURRENT;
    state.galleryEntries = [];
    state.galleryIndex = 0;
    state.galleryStaging = false;
    state.active = false;
    if (state.raf) cancelAnimationFrame(state.raf);
    state.raf = 0;
    clearPreviewTimer();
    state.previewToken += 1;
    state.previewPhase = "idle";
    state.appSnapshot = null;
    state.appSnapshotApplied = false;
    disconnectFrame();
    if (state.parentObserver) state.parentObserver.disconnect();
    state.parentObserver = null;
    if (state.aborter) state.aborter.abort();
    state.aborter = null;
    setSourcePageInert(false);
    if (state.root) state.root.remove();
    state.root = null;
    state.frameShell = null;
    state.frame = null;
    state.previewScale = 1;
    document.documentElement.classList.remove("redline-breakpoint-preview");
    state.currentListenersAttached = false;
    state.frameListenersDoc = null;
    state.hovered = null;
    state.locked = null;
    state.colorPanel = null;
    state.colorPanelTarget = undefined;
    state.colorSections = null;
    state.colorSheetCache = null;
    state.colorSheetCacheDoc = null;
    state.colorSheetTextCache = null;
    state.colorSheetWarming = null;
    if (state.storageSnapshot) {
      try {
        var currentKeys = [];
        for (var keyIndex = 0; keyIndex < localStorage.length; keyIndex += 1) {
          currentKeys.push(localStorage.key(keyIndex));
        }
        currentKeys.forEach(function (key) {
          if (!Object.prototype.hasOwnProperty.call(state.storageSnapshot, key)) {
            localStorage.removeItem(key);
          }
        });
        Object.keys(state.storageSnapshot).forEach(function (key) {
          localStorage.setItem(key, state.storageSnapshot[key]);
        });
      } catch (_) {}
    }
    state.storageSnapshot = null;
    syncMenuState();
    var fallback = document.querySelector('[data-action="toggle-profile"]');
    var focusIsInteractive = focusTarget && focusTarget.matches
      && focusTarget.matches("button, a[href], input, textarea, select, [tabindex]");
    var nextFocus = focusIsInteractive && focusTarget.isConnected && !focusTarget.closest("[hidden]")
      ? focusTarget
      : fallback;
    if (nextFocus && typeof nextFocus.focus === "function") {
      window.setTimeout(function () {
        window.focus();
        if (nextFocus.isConnected) nextFocus.focus({ preventScroll: true });
      }, 0);
    }
  }

  function toggle(source) {
    if (state.active) disable();
    else enable(source);
  }

  function onGlobalKeydown(event) {
    var shortcut = event.key.toLocaleLowerCase() === "d"
      && (event.metaKey || event.ctrlKey)
      && !event.altKey && !event.shiftKey;
    if (shortcut && !isEditable(event.target)) {
      event.preventDefault();
      event.stopImmediatePropagation();
      toggle("keyboard");
      return;
    }
    // Arrow shortcuts only apply while a gallery is open, and never while
    // focus sits in a field, so a modal's own form keeps normal key handling.
    if (state.active && inGallery() && !isEditable(event.target)
      && !event.metaKey && !event.ctrlKey && !event.altKey && !event.shiftKey
      && (event.key === "ArrowLeft" || event.key === "ArrowRight")) {
      event.preventDefault();
      event.stopImmediatePropagation();
      stepGallery(event.key === "ArrowRight" ? 1 : -1);
      return;
    }
    if (state.active && event.key === "Escape") {
      event.preventDefault();
      event.stopImmediatePropagation();
      if (state.color) {
        setLayer("color");
        setStatus("Color inspection closed.");
      } else if (inGallery()) {
        // Escape steps out of the gallery before it closes Redline, so the
        // page the user entered from is never skipped over.
        setPreviewMode(PREVIEW_MODES.CURRENT);
      } else {
      disable();
      }
    }
  }

  function inspect(selector) {
    if (!state.frameDocument) return null;
    var target = state.frameDocument.querySelector(selector);
    if (!target) return null;
    var rect = target.getBoundingClientRect();
    var style = inspectionView().getComputedStyle(target);
    return {
      width: Math.round(rect.width),
      height: Math.round(rect.height),
      padding: [
        Math.round(parseFloat(style.paddingTop) || 0),
        Math.round(parseFloat(style.paddingRight) || 0),
        Math.round(parseFloat(style.paddingBottom) || 0),
        Math.round(parseFloat(style.paddingLeft) || 0)
      ],
      gap: Math.round(parseFloat(style.gap) || 0)
    };
  }

  function debugState() {
    return {
      active: state.active,
      breakpoint: state.breakpoint,
      previewScale: state.previewScale,
      measurementMode: state.measurementMode,
      showLines: state.showLines,
      showGridOverlay: state.showGridOverlay,
      typography: state.typography,
      color: state.color,
      renderCount: state.renderCount,
      overlays: document.querySelectorAll(".redline").length,
      previewPhase: state.previewPhase,
      hasAppSnapshot: Boolean(state.appSnapshot),
      appSnapshotApplied: state.appSnapshotApplied,
      hasLockedSelection: Boolean(state.locked),
      hasHoveredSelection: Boolean(state.hovered),
      previewMode: state.previewMode,
      galleryIndex: state.galleryIndex,
      galleryTotal: state.galleryEntries.length,
      galleryEntryId: (currentGalleryEntry() || {}).id || "",
      selectionSummary: state.root
        ? (state.root.querySelector("[data-redline-selection]") || {}).textContent
        : ""
    };
  }

  window.RedlineMode = {
    enable: enable,
    disable: disable,
    toggle: toggle,
    isActive: function () { return state.active; },
    inspect: inspect,
    debugState: debugState,
    breakpoints: BREAKPOINTS.slice(),
    previewMode: function () { return state.previewMode; }
  };

  if (isPreview()) {
    document.addEventListener("keydown", function (event) {
      var shortcut = event.key.toLocaleLowerCase() === "d"
        && (event.metaKey || event.ctrlKey)
        && !event.altKey && !event.shiftKey;
      if (shortcut && !isEditable(event.target)) {
        event.preventDefault();
        if (window.parent.RedlineMode) window.parent.RedlineMode.toggle("keyboard");
      } else if (event.key === "Escape" && window.parent.RedlineMode) {
        // While a gallery is showing an overlay, Escape belongs to that
        // overlay's own dismiss behavior, not to closing Redline.
        var inOverlayGallery = false;
        try {
          inOverlayGallery = window.parent.RedlineMode.previewMode() !== "current-page";
        } catch (_) {}
        if (inOverlayGallery) return;
        event.preventDefault();
        window.parent.RedlineMode.disable();
      }
    }, true);
    return;
  }
  document.addEventListener("keydown", onGlobalKeydown, true);
  syncMenuState();
  new MutationObserver(function () {
    if (portfolioPresentation() && state.active) disable();
  }).observe(document.body, { attributes: true, attributeFilter: ["data-route"] });
})();
