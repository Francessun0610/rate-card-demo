/* Approved pricing conditions: one catalog, one eligibility rule, one
 * control, shared by Line Details, Premium Details and Quick Edit.
 *
 * The data comes from fixtures/condition-catalog.js, generated from the
 * Business Dictionary workbook. Nothing here holds a second list.
 */
window.RCMConditions = (function () {
  "use strict";

  function text(value, limit) {
    var out = value == null ? "" : String(value);
    return limit ? out.slice(0, limit) : out;
  }

  /* Stored as a comma separated list of labels, which is the shape the
   * records already used before conditions became a closed list. */
  function lineConditionList(value) {
    return text(value).split(",").map(function (part) {
      return part.trim();
    }).filter(Boolean);
  }

/* ---- Approved pricing conditions ----------------------------------
 * One catalog and one control serve both Line Details and Premium
 * Details. The workbook calls the grouping column "Premium Category"
 * even for line conditions, which reads as a mistake on a line item,
 * so the UI calls it Category throughout.
 *
 * Eligibility comes from the workbook's Pricing Condition Group: a
 * condition is offered on a line when the group contains Base Rate,
 * and on a premium when it contains Premium. Six carry both. The two
 * fields therefore differ only by that filter, never by their own
 * copy of the list. */

var CONDITION_SCOPES = { line: "L", premium: "P" };

function conditionNormalize(value) {
  return text(value).replace(/\s+/g, " ").trim();
}

/* Canonical identity. The workbook publishes a Systematic Identifier
 * column that is empty in every row today, so the key falls back to a
 * normalized category and name. Preferring the identifier the moment
 * it is populated means saved records keep resolving after a rename. */
function conditionKey(category, name, systematicId) {
  var sysId = conditionNormalize(systematicId);
  if (sysId) return "sys:" + sysId.toLowerCase();
  return conditionNormalize(category).toLowerCase()
    + "|" + conditionNormalize(name).toLowerCase();
}

function conditionLabel(category, name) {
  return conditionNormalize(category) + ": " + conditionNormalize(name);
}

var conditionIndex = null;

/* Built once. Collisions are recorded rather than merged: two rows
 * that normalize to one key are different records in the source and a
 * silent merge would drop one of them. */
function conditionCatalog() {
  if (conditionIndex) return conditionIndex;
  var source = window.RCMConditionCatalog;
  var rows = source && source.rows ? source.rows : [];
  var byKey = Object.create(null);
  var all = [];
  var collisions = [];
  rows.forEach(function (row, order) {
    var category = conditionNormalize(row[0]);
    var name = conditionNormalize(row[1]);
    if (!category || !name) return;
    var scope = text(row[3]).toUpperCase();
    var key = conditionKey(category, name, row[4]);
    if (byKey[key]) {
      if (byKey[key].name !== name || byKey[key].category !== category) {
        collisions.push(key);
      }
      return;
    }
    var entry = {
      key: key,
      category: category,
      name: name,
      description: conditionNormalize(row[2]),
      label: conditionLabel(category, name),
      line: scope.indexOf("L") !== -1,
      premium: scope.indexOf("P") !== -1,
      order: order
    };
    byKey[key] = entry;
    all.push(entry);
  });
  conditionIndex = {
    all: all,
    byKey: byKey,
    /* Labels resolve legacy rows saved before canonical keys existed. */
    byLabel: all.reduce(function (map, entry) {
      map[entry.label.toLowerCase()] = entry;
      return map;
    }, Object.create(null)),
    collisions: collisions,
    loaded: rows.length > 0
  };
  return conditionIndex;
}

function conditionsForScope(scope) {
  var flag = scope === "premium" ? "premium" : "line";
  return conditionCatalog().all.filter(function (entry) {
    return entry[flag];
  });
}

/* Resolve one stored value against the catalog. Anything that does not
 * resolve is kept as an unknown entry rather than dropped, so a record
 * saved before this list existed survives being opened. */
function resolveCondition(value, scope) {
  var index = conditionCatalog();
  if (value && typeof value === "object") {
    var stored = index.byKey[value.key]
      || index.byLabel[text(value.label).toLowerCase()];
    if (stored) return conditionAllowedInScope(stored, scope)
      ? stored
      : { key: stored.key, category: stored.category, name: stored.name,
          label: stored.label, unknown: true };
    return {
      key: text(value.key) || conditionKey(value.category, value.name),
      category: conditionNormalize(value.category),
      name: conditionNormalize(value.name),
      label: conditionNormalize(value.label)
        || conditionLabel(value.category, value.name),
      unknown: true
    };
  }
  var label = conditionNormalize(value);
  if (!label) return null;
  var match = index.byLabel[label.toLowerCase()];
  /* A real condition saved against the wrong record type is still
   * wrong here: a Base-Rate-only condition on a premium cannot be
   * offered, so it is preserved and flagged rather than shown as if
   * the catalog approved it for this field. */
  if (match) return conditionAllowedInScope(match, scope)
    ? match
    : { key: match.key, category: match.category, name: match.name,
        label: match.label, unknown: true };
  /* Older rows stored "Category: Name" as free text; split on the
   * first colon so a value that still names a real condition
   * resolves instead of being flagged. */
  var split = label.indexOf(":");
  if (split > 0) {
    var byParts = index.byKey[conditionKey(label.slice(0, split),
                                           label.slice(split + 1))];
    if (byParts) return conditionAllowedInScope(byParts, scope)
      ? byParts
      : { key: byParts.key, category: byParts.category, name: byParts.name,
          label: byParts.label, unknown: true };
  }
  return { key: "unknown:" + label.toLowerCase(), category: "",
           name: label, label: label, unknown: true };
}

/* Only entries the scope allows may be added. An unknown value that is
 * already saved is exempt: it is being preserved, not offered. */
function conditionAllowedInScope(entry, scope) {
  if (!entry) return false;
  if (entry.unknown) return false;
  return scope === "premium" ? !!entry.premium : !!entry.line;
}

function parseConditions(stored, json, scope) {
  var out = [];
  var seen = Object.create(null);
  var push = function (entry) {
    if (!entry || seen[entry.key]) return;
    seen[entry.key] = true;
    out.push(entry);
  };
  var parsed = null;
  if (text(json)) {
    try { parsed = JSON.parse(json); } catch (_) { parsed = null; }
  }
  if (Array.isArray(parsed)) {
    parsed.forEach(function (item) { push(resolveCondition(item, scope)); });
    return out;
  }
  lineConditionList(stored).forEach(function (label) {
    push(resolveCondition(label, scope));
  });
  return out;
}

/* ---- The shared condition control ---------------------------------
 * Instantiated once per [data-conditions] host. Each instance owns its
 * scope, its hidden inputs and its menu; nothing is shared between the
 * line and premium copies except the catalog itself. */
var conditionFields = [];

function createConditionField(host, options) {
  var scope = host.getAttribute("data-conditions-scope") === "premium"
    ? "premium" : "line";
  var input = host.querySelector(".ads-cond__input");
  var menu = host.querySelector(".ads-cond__menu");
  var list = host.querySelector("[data-cond-list]");
  var clearBtn = host.querySelector("[data-cond-clear]");
  var store = host.querySelector("[data-cond-value]");
  var json = host.querySelector("[data-cond-json]");
  var status = host.querySelector("[data-cond-status]");
  if (!input || !menu || !list || !store) return null;

  /* A record carries at most one condition, so this is one value or
   * none, held as the entry itself rather than a list. */
  var selected = null;
  /* What a legacy record held beyond the first value. Kept only so the
   * stored string survives untouched until the user replaces it. */
  var legacyExtras = [];
  var active = -1;
  var optionNodes = [];
  var editing = false;

  function announce(message) {
    if (status && message) status.textContent = message;
  }

  function persist() {
    /* Any write is a deliberate replacement, so a legacy record's extra
     * values go at the same moment the user chooses a new one. */
    legacyExtras = [];
    store.value = selected ? selected.label : "";
    if (json) {
      json.value = selected ? JSON.stringify({
        key: selected.key, category: selected.category,
        name: selected.name, label: selected.label,
        unknown: selected.unknown || undefined
      }) : "";
    }
    renderValue();
    store.dispatchEvent(new Event("input", { bubbles: true }));
    store.dispatchEvent(new Event("change", { bubbles: true }));
  }

  /* The value lives in the input itself rather than in a chip, so the
   * field reads like the single-value control it is. CSS ellipsizes it
   * when it does not fit; the tooltip only appears when that happens. */
  function renderValue() {
    if (!editing) input.value = selected ? selected.label : "";
    var label = selected ? selected.label : "";
    host.classList.toggle("has-value", !!selected);
    host.classList.toggle("is-unrecognized", !!(selected && selected.unknown));
    if (clearBtn) {
      clearBtn.hidden = !selected;
      if (selected) {
        clearBtn.setAttribute("aria-label", "Clear condition " + label);
      }
    }
    /* The accessible name always carries the whole value, truncated or
     * not, so a screen reader never hears a clipped label. */
    if (selected) {
      input.setAttribute("aria-label",
        (options && options.ariaLabel ? options.ariaLabel + ": " : "") + label
        + (selected.unknown ? " (unrecognized condition)" : ""));
    } else if (options && options.ariaLabel) {
      input.setAttribute("aria-label", options.ariaLabel);
    } else {
      input.removeAttribute("aria-label");
    }
    syncTruncationTooltip();
  }

  /* Only a clipped value gets a tooltip; one that already reads in full
   * would just repeat itself. Uses the shared ADS truncation tooltip,
   * never the native title. */
  function syncTruncationTooltip() {
    var clipped = input.scrollWidth > input.clientWidth + 1;
    if (selected && clipped) {
      input.setAttribute("data-tooltip", selected.label);
      input.setAttribute("data-tooltip-truncate", "auto");
    } else {
      input.removeAttribute("data-tooltip");
      input.removeAttribute("data-tooltip-truncate");
    }
    input.removeAttribute("title");
  }

  /* Exact name, then prefix, then anything else. A seller who knows
   * what the condition is called should not have to scroll past
   * description matches to reach it. */
  function rank(entry, query) {
    var name = entry.name.toLowerCase();
    var category = entry.category.toLowerCase();
    if (name === query) return 0;
    if (name.indexOf(query) === 0) return 1;
    if (category === query || category.indexOf(query) === 0) return 2;
    if (name.indexOf(query) !== -1) return 3;
    if (entry.label.toLowerCase().indexOf(query) !== -1) return 4;
    if (entry.description.toLowerCase().indexOf(query) !== -1) return 5;
    return -1;
  }

  /* The whole approved list, so the menu always shows what is on the
   * record with a checkmark rather than hiding it. */
  function search(query) {
    var typed = conditionNormalize(query).toLowerCase();
    var pool = conditionsForScope(scope);
    if (!typed) return pool;
    return pool.map(function (entry) {
      return { entry: entry, score: rank(entry, typed) };
    }).filter(function (hit) {
      return hit.score >= 0;
    }).sort(function (a, b) {
      return a.score - b.score || a.entry.order - b.entry.order;
    }).map(function (hit) { return hit.entry; });
  }

  function setActive(index) {
    active = index;
    optionNodes.forEach(function (node, at) {
      node.classList.toggle("is-active", at === index);
    });
    if (index < 0 || !optionNodes[index]) {
      input.removeAttribute("aria-activedescendant");
      return;
    }
    input.setAttribute("aria-activedescendant", optionNodes[index].id);
    var node = optionNodes[index];
    var top = node.offsetTop;
    var bottom = top + node.offsetHeight;
    if (top < menu.scrollTop) menu.scrollTop = top;
    else if (bottom > menu.scrollTop + menu.clientHeight) {
      menu.scrollTop = bottom - menu.clientHeight;
    }
  }

  function renderMenu(query) {
    list.replaceChildren();
    optionNodes = [];
    var catalog = conditionCatalog();
    if (!catalog.loaded) {
      /* The catalog is a deferred script. While the document is still
       * parsing it may simply not have run yet, which is a wait, not a
       * failure. Once parsing is done an absent catalog is a failure,
       * and the field stays closed rather than degrading into a text
       * box that would accept anything. */
      var pending = document.readyState === "loading";
      var notice = document.createElement("li");
      notice.className = "ads-cond__empty";
      notice.setAttribute("role", "presentation");
      notice.textContent = pending
        ? "Loading conditions\u2026"
        : "Conditions could not be loaded. Try again.";
      list.appendChild(notice);
      announce(notice.textContent);
      conditionIndex = null;
      return;
    }
    var matches = search(query);
    var currentCategory = null;
    var selectedKey = selected ? selected.key : null;
    matches.forEach(function (entry) {
      if (entry.category !== currentCategory) {
        currentCategory = entry.category;
        var heading = document.createElement("li");
        heading.className = "ads-cond__group";
        heading.setAttribute("role", "presentation");
        heading.textContent = entry.category;
        list.appendChild(heading);
      }
      var option = document.createElement("li");
      option.className = "ads-cond__option";
      option.id = input.id + "-opt-" + optionNodes.length;
      option.setAttribute("role", "option");
      option.setAttribute("aria-selected",
        entry.key === selectedKey ? "true" : "false");
      option.setAttribute("data-cond-key", entry.key);
      var check = document.createElement("span");
      check.className = "ads-cond__check";
      check.setAttribute("aria-hidden", "true");
      check.innerHTML = '<svg width="14" height="14" viewBox="0 0 16 16" '
        + 'fill="none"><path d="M3.5 8.5l3 3 6-6" stroke="currentColor" '
        + 'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>';
      option.appendChild(check);
      var body = document.createElement("span");
      body.className = "ads-cond__option-body";
      var name = document.createElement("span");
      name.className = "ads-cond__option-name";
      name.textContent = entry.name;
      body.appendChild(name);
      if (entry.description) {
        var desc = document.createElement("span");
        desc.className = "ads-cond__option-desc";
        desc.textContent = entry.description;
        body.appendChild(desc);
      }
      option.appendChild(body);
      list.appendChild(option);
      optionNodes.push(option);
    });
    if (!optionNodes.length) {
      var empty = document.createElement("li");
      empty.className = "ads-cond__empty";
      empty.setAttribute("role", "presentation");
      empty.textContent = "No matching conditions";
      list.appendChild(empty);
    }
    announce(optionNodes.length === 1
      ? "1 condition available"
      : optionNodes.length + " conditions available");
    /* Open on the current value so the list starts where the record is. */
    var at = optionNodes.findIndex(function (node) {
      return node.getAttribute("aria-selected") === "true";
    });
    setActive(optionNodes.length ? (at >= 0 ? at : 0) : -1);
  }

  /* The field sits near the bottom of a scrolling panel, so a menu that
   * always drops downward runs past the viewport and hides the footer
   * behind it. Flip above the control when there is more room there,
   * and cap the height to whatever room the chosen side has. */
  function placeMenu() {
    var control = host.querySelector("[data-cond-control]");
    if (!control || menu.hidden) return;
    var rect = control.getBoundingClientRect();
    var GAP = 4;
    var EDGE = 12;
    /* Whichever surface this control is on, keep clear of that
     * surface's own action footer: the panel's form actions or Quick
     * Edit's sheet footer. */
    var surface = host.closest(
      "form, .qsheet, [role='dialog'], .create-md__detail"
    ) || document;
    var footer = surface.querySelector(
      ".create-md__form-actions, .qsheet__footer"
    );
    var floor = window.innerHeight - EDGE;
    if (footer) {
      var footerRect = footer.getBoundingClientRect();
      if (footerRect.height > 0) floor = Math.min(floor, footerRect.top - GAP);
    }
    var below = floor - rect.bottom - GAP;
    var above = rect.top - GAP - EDGE;
    var flip = below < 200 && above > below;
    var room = Math.max(0, Math.min(300, flip ? above : below));
    menu.classList.toggle("ads-cond__menu--above", flip);
    menu.style.maxHeight = room + "px";
    /* Positioned against the viewport from the control's own box, not
     * inside the host. Quick Edit puts this control in a grid cell that
     * clips its overflow, so a menu laid out inside the host would be
     * cut off at the cell edge. The menu is at least as wide as the
     * control so a long option stays readable in a narrow column. */
    menu.style.left = Math.round(rect.left) + "px";
    menu.style.width = Math.round(rect.width) + "px";
    if (flip) {
      menu.style.top = "auto";
      menu.style.bottom = Math.round(window.innerHeight - rect.top + GAP) + "px";
    } else {
      menu.style.bottom = "auto";
      menu.style.top = Math.round(rect.bottom + GAP) + "px";
    }
    /* Whatever the arithmetic said, trust the box that was actually
     * laid out: a control that moved between measuring and painting
     * would otherwise push the menu off the bottom of the screen. */
    var painted = menu.getBoundingClientRect();
    var overflow = painted.bottom - (window.innerHeight - EDGE);
    if (overflow > 0) {
      menu.style.maxHeight = Math.max(120, painted.height - overflow) + "px";
    }
  }

  function openMenu(query) {
    renderMenu(query);
    /* Moved to the body while open. Quick Edit's sheet is transformed,
     * which would otherwise become the containing block for a fixed
     * menu and drop it well below its own field. */
    if (menu.parentElement !== document.body) document.body.appendChild(menu);
    menu.hidden = false;
    input.setAttribute("aria-expanded", "true");
    placeMenu();
    /* Focusing the field scrolls it into view, so the control is not
     * where it was when the menu was measured. Re-measure once the
     * scroll has settled; the observer below keeps up with anything
     * that moves it afterwards. */
    requestAnimationFrame(placeMenu);
    window.setTimeout(placeMenu, 120);
  }

  function closeMenu() {
    menu.hidden = true;
    if (menu.parentElement === document.body) host.appendChild(menu);
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
    active = -1;
  }

  /* One value: choosing replaces whatever was there and closes. */
  function choose(key) {
    var entry = conditionCatalog().byKey[key];
    if (!conditionAllowedInScope(entry, scope)) return;
    selected = entry;
    editing = false;
    persist();
    closeMenu();
    announce(entry.label + " selected");
  }

  function clearValue() {
    if (!selected) return;
    var gone = selected.label;
    selected = null;
    editing = false;
    persist();
    announce(gone + " cleared");
  }

  menu.addEventListener("mousedown", function (event) {
    var option = event.target.closest("[data-cond-key]");
    if (!option) return;
    /* Keep focus in the field rather than letting it fall to the menu. */
    event.preventDefault();
    choose(option.getAttribute("data-cond-key"));
    input.focus();
  });

  if (clearBtn) {
    clearBtn.addEventListener("mousedown", function (event) {
      /* Clearing must not also open the list. */
      event.preventDefault();
      event.stopPropagation();
    });
    clearBtn.addEventListener("click", function (event) {
      event.preventDefault();
      event.stopPropagation();
      clearValue();
      closeMenu();
      input.focus();
    });
  }

  host.addEventListener("click", function (event) {
    if (event.target.closest("[data-cond-clear]")) return;
    if (!event.target.closest("[data-cond-control]")) return;
    input.focus();
    if (menu.hidden) openMenu("");
  });

  input.addEventListener("input", function () {
    editing = true;
    openMenu(input.value);
  });

  input.addEventListener("focus", function () {
    /* Opening on the whole list rather than on the current value as a
     * query, and selecting the text, so typing replaces it. */
    editing = false;
    openMenu("");
    if (selected) input.select();
  });

  input.addEventListener("blur", function () {
    /* Whatever was typed is not a value, so the field goes back to what
     * the record holds. */
    editing = false;
    renderValue();
  });

  input.addEventListener("keydown", function (event) {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (menu.hidden) { openMenu(editing ? input.value : ""); return; }
      if (!optionNodes.length) return;
      var next = event.key === "ArrowDown" ? active + 1 : active - 1;
      if (next < 0) next = optionNodes.length - 1;
      if (next >= optionNodes.length) next = 0;
      setActive(next);
      return;
    }
    if (event.key === "Enter") {
      /* Only ever commits a highlighted approved option; typed text is
       * never a value. */
      event.preventDefault();
      if (!menu.hidden && active >= 0 && optionNodes[active]) {
        choose(optionNodes[active].getAttribute("data-cond-key"));
      }
      return;
    }
    if (event.key === " " && !editing && menu.hidden) {
      event.preventDefault();
      openMenu("");
      return;
    }
    if (event.key === "Escape") {
      if (!menu.hidden) {
        /* The panel's own Escape would otherwise close the whole
         * drawer and lose the edit in progress. */
        event.preventDefault();
        event.stopPropagation();
        closeMenu();
        renderValue();
      }
    }
  });

  document.addEventListener("click", function (event) {
    if (!host.contains(event.target) && !menu.contains(event.target)) {
      closeMenu();
    }
  }, true);
  document.addEventListener("scroll", placeMenu, true);
  window.addEventListener("resize", placeMenu);
  if (typeof ResizeObserver === "function") {
    /* A column that resizes moves the anchor and changes how much of
     * the value fits, and neither reports as a scroll or a resize. */
    new ResizeObserver(function () {
      placeMenu();
      syncTruncationTooltip();
    }).observe(host);
  }

  /* Hydrating from a record must not rewrite it: a legacy row holding
   * more than one condition keeps its stored string until the user
   * picks a replacement. */
  function hydrate(value, jsonValue) {
    var parsed = parseConditions(value, jsonValue, scope);
    selected = parsed.length ? parsed[0] : null;
    legacyExtras = parsed.slice(1);
    editing = false;
    /* The form serializes from the hidden inputs, so they have to carry
     * the record even though nothing changed. Written directly, without
     * the events persist() fires, so hydrating never marks the form
     * dirty. A legacy record keeps every value it arrived with until
     * the user picks a replacement. */
    store.value = parsed.map(function (e) { return e.label; }).join(", ");
    if (json) {
      /* One object, matching what a save writes. A record carries one
       * condition, so the canonical field describes that one; anything
       * extra a legacy row arrived with stays readable in the label
       * string above until the user replaces it. */
      json.value = selected ? JSON.stringify({
        key: selected.key, category: selected.category,
        name: selected.name, label: selected.label,
        unknown: selected.unknown || undefined
      }) : "";
    }
    renderValue();
    if (legacyExtras.length) {
      announce("This record holds more than one condition. "
        + "Choosing a condition replaces them.");
    }
  }

  var api = {
    host: host,
    scope: scope,
    sync: function () { hydrate(store.value, json && json.value); },
    set: function (value, jsonValue) { hydrate(value, jsonValue); },
    clear: function () {
      selected = null;
      legacyExtras = [];
      editing = false;
      input.value = "";
      closeMenu();
      store.value = "";
      if (json) json.value = "";
      renderValue();
    },
    /* A real selection: persists and notifies, the same as choosing from
     * the menu. set() deliberately does neither, because hydrating a
     * record must not mark its form dirty. */
    select: function (keyOrLabel) {
      var index = conditionCatalog();
      var entry = index.byKey[keyOrLabel]
        || index.byLabel[String(keyOrLabel).toLowerCase()];
      if (!entry) return false;
      choose(entry.key);
      return true;
    },
    value: function () { return selected; },
    /* Kept as a list for callers that predate single select. */
    values: function () { return selected ? [selected] : []; }
  };
  host.__conditionField = api;
  return api;
}

  var autoId = 0;

  /* Builds the control's markup for callers that have only an empty
   * host, which is how Quick Edit gets the same field inside a grid
   * cell that it renders per row. */
  function buildFieldMarkup(host, options) {
    var opts = options || {};
    var scope = host.getAttribute("data-conditions-scope") === "premium"
      ? "premium" : "line";
    autoId += 1;
    var id = opts.id || "cond-" + autoId;
    var placeholder = opts.placeholder || "Search conditions";
    var menuLabel = opts.menuLabel
      || (scope === "premium" ? "Premium condition" : "Line condition");
    host.classList.add("ads-cond");
    host.innerHTML =
      '<div class="ads-cond__control" data-cond-control>'
      + '<input type="text" id="' + id + '" class="ads-cond__input"'
      + ' role="combobox" aria-expanded="false" aria-autocomplete="list"'
      + ' aria-haspopup="listbox" aria-controls="' + id + '-menu"'
      + ' placeholder="' + placeholder + '" autocomplete="off" spellcheck="false">'
      + '<button type="button" class="ads-cond__clear" data-cond-clear'
      + ' tabindex="-1" aria-label="Clear condition" hidden>'
      + '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">'
      + '<path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="1.6"'
      + ' stroke-linecap="round"/></svg></button>'
      + '<span class="ads-cond__caret" aria-hidden="true">'
      + '<svg width="16" height="16" viewBox="0 0 16 16" fill="none">'
      + '<path d="M4 6l4 4 4-4" stroke="currentColor" stroke-width="1.5"'
      + ' stroke-linecap="round" stroke-linejoin="round"/></svg></span>'
      + '</div>'
      + '<div class="ads-cond__menu" id="' + id + '-menu" hidden>'
      + '<ul class="ads-cond__list" role="listbox"'
      + ' aria-label="' + menuLabel + '" data-cond-list></ul>'
      + '</div>'
      + '<p class="sr-only" role="status" aria-live="polite" data-cond-status></p>'
      + '<input type="hidden" data-cond-value>'
      + '<input type="hidden" data-cond-json>';
    if (opts.ariaLabel) {
      host.querySelector(".ads-cond__input")
        .setAttribute("aria-label", opts.ariaLabel);
    }
    return host;
  }

  function createField(host, options) {
    if (!host) return null;
    if (!host.querySelector("[data-cond-control]")) {
      buildFieldMarkup(host, options);
    }
    return createConditionField(host, options);
  }

  return {
    /* Every approved condition, in workbook order. */
    catalog: conditionCatalog,
    /* The approved conditions one editing context may use. */
    forScope: conditionsForScope,
    /* Resolve a stored value, flagging anything the catalog does not
     * recognise or that this context may not hold. */
    resolve: resolveCondition,
    parse: parseConditions,
    key: conditionKey,
    label: conditionLabel,
    allowed: conditionAllowedInScope,
    list: lineConditionList,
    createField: createField
  };
}());
