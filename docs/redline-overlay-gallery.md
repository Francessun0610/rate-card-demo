# Redline Overlay Gallery

Redline Mode has two extra inspection modes alongside the current page:
a **modal gallery** and a **toast gallery**, reached from the `OVERLAYS`
section of the Redline sidebar.

The point of the gallery is that a designer can measure any overlay in the
product without having to reproduce the workflow that raises it. Deleting a
rate card to inspect the delete confirmation is not a reasonable ask, and an
error toast that only appears when a CSV import fails is close to
unmeasurable in practice.

## How it is put together

There are two halves.

**The registry** lives in `app.js` as `window.RateCardOverlayGallery`. It
knows every overlay the product can show and how to put each one on screen.
It runs inside the application, so it can call the application's own
functions.

**The shell** lives in `redline.js`. It renders the sidebar entry rows and
the navigation toolbar above the preview, and asks the registry to stage
entries. It knows nothing about rate cards.

```
redline.js                     app.js
  sidebar OVERLAYS rows          window.RateCardOverlayGallery
  gallery toolbar        ──────▶   .entries("modal" | "toast")
  preview mode switching           .open(id)
  inspection + measurement         .close()
```

### Why the overlays are real

Every entry drives the application's own markup through its own open
function. `modal.delete.default` calls `openDeleteModal()` with a real rate
card id; the dialog that appears is the same node, with the same classes,
copy and ARIA, that a user sees after clicking Delete. There are no replicas,
no screenshots and no gallery-only styling, so a measurement taken in the
gallery is a measurement of production.

Toasts work the same way: entries call the production `toast()` with the
exact copy from the flow they belong to, passing `duration: 0` so
auto-dismiss is frozen for as long as the inspection takes.

### Why nothing gets written

Galleries only ever run inside the Redline preview, which is an isolated
same-origin copy of the app in an iframe. On top of that isolation, opening
an entry installs a capture-phase guard that blocks the confirm actions that
would write data (`confirm-delete`, `save-quick-edit`, `confirm-remove-line`,
`apply-filters` and the rest). Clicking "Delete rate card" in the gallery
does nothing. Leaving the gallery closes every overlay through the product's
real close path, so inert backgrounds, body classes and focus all unwind
normally.

### The preview is the overlay root

The brief for this work assumed a React app where overlays portal into a
`#redline-preview-overlay-root` node. This codebase does not portal: overlay
markup is static in `index.html` and lives in the preview document. The
iframe boundary gives the same guarantee more strongly, because a backdrop
inside the preview physically cannot paint over the Redline header, sidebar,
toolbar or inspector. `qa_redline_overlays.py` asserts this rather than
taking it on trust.

## Adding a modal

Add an entry to `GALLERY_MODALS` in `app.js`:

```js
{
  id: "modal.publish.confirm",        // stable, unique, dot-namespaced
  group: "Publish",                    // groups related entries in the list
  name: "Publish rate card",           // the overlay's name
  stateName: "Confirmation",           // which state of it this entry is
  description: "Shown before a draft is published.",
  route: "list",                       // background page for the overlay
  source: "index.html [data-publish-modal], app.js openPublishModal()",
  ads: "Modal (ADS Modal, primary footer)",
  open: function () {
    galleryRoute("list");
    var row = galleryRow(function (item) { return item.status === "Draft"; });
    if (!row) return false;
    openPublishModal(row.id);         // the product's own function
    return true;
  },
}
```

`open()` returns `true` when it staged something and `false` when it could
not. Never build markup in `open()`. If the only way to show a state is to
hand-write its DOM, that state does not exist in the product yet and does not
belong in the gallery.

Entries render in array order, so put related states next to each other.

After `open()` returns, the registry puts focus back inside the staged surface
if the route change moved it elsewhere, so every entry can be inspected from
the keyboard. That only corrects for staging; it does not paper over an
overlay that fails to take focus in the product. If an entry lands focus
nowhere, fix the product's open path.

## Adding a modal state

A state is worth registering when it renders differently. Loading, validation
errors, empty, long content and destructive variants all qualify. Internal
states that look identical do not.

Reach the state the way the product does. `modal.quick-edit.dirty` opens the
sheet and then writes a base rate through real `input`/`change`/`blur`
events, which is what enables Save. It does not reach in and flip the
disabled attribute.

When a state genuinely has no reachable trigger in the prototype (the
submitting state of the remove-line dialog only exists for the duration of a
synchronous call), set the same attributes the product sets and say so in a
comment.

## Adding a toast

Add an entry to `GALLERY_TOASTS`:

```js
{
  id: "toast.publish.published",
  group: "Publish",
  name: "Rate card published",
  variant: "success",                  // success | error | warning | info
  route: "list",                       // page the toast is staged over
  source: "app.js publishRateCard()",
  config: { message: "Rate card published.", variant: "success" },
}
```

`route` is the page the flow runs on, so the toast is inspected over the
screen it really appears on. It defaults to `list`; use `create` for toasts
raised from Create or Edit Rate Card.

`config` is passed straight to the production `toast()`. Copy the message
string from the call site verbatim, including punctuation. If the flow shows
a title and a supporting message, register both:

```js
config: {
  title: "Unable to publish rate card",
  message: "Try again.",
  variant: "error",
}
```

Do not add `duration`; the gallery freezes it.

## Adding a stack

Use `stack` instead of `config`, listing toasts oldest first (the production
`toast()` prepends, so this matches a real sequence of events):

```js
{
  id: "toast.stack.publish-mixed",
  group: "Stacks",
  name: "Publish and warning",
  stateName: "Stack of 2",
  variant: "warning",
  source: "app.js toast() stack container",
  stack: [
    { message: "Rate card published.", variant: "success" },
    { message: "Complete required fields before continuing.", variant: "warning" },
  ],
}
```

The stack container has no hard maximum, so do not register a stack larger
than a real workflow could produce.

## Using production copy

Copy in this codebase is inline at the call site, not centralised. When you
register an overlay, open the call site and copy the string exactly. Do not
improve the wording on the way past. If the copy is wrong, fix it at the call
site so the product and the gallery change together.

Two long import summaries (`IMPORT_SUMMARY_CORRECTIONS`,
`IMPORT_SUMMARY_LONG`) are assembled in the registry from the real row-error
templates in `importRateCardCsv()`, because those messages are built at
runtime from the file being imported.

## Providing isolated fixtures

Prefer real catalog data. `galleryRow()`, `galleryLongNameRow()` and
`galleryQuickEditRow()` pick a representative rate card out of the live
catalog, which keeps the gallery honest as the fixtures change.

Where a state needs data the catalog cannot supply (a file that failed
validation, for instance), keep the fixture in the registry as a plain
string or object. Never read from disk, never upload, never call a service.

## Preventing mutations

If you register an overlay with a new confirm action, add that action to
`GALLERY_BLOCKED_ACTIONS` (for `data-action`) or `GALLERY_BLOCKED_V2_ACTIONS`
(for `data-v2-action`). Then check it: open the entry, click the confirm
button, leave the gallery, and confirm the list is unchanged.
`qa_redline_overlays.py` does exactly this for the delete dialog.

## Testing breakpoints

Every Redline breakpoint applies to galleries, including Current. Switching
breakpoints keeps the selected entry, because the preview is resized rather
than reloaded.

Check a new overlay at 1024 and at 2560. At the small end look for clipping,
a body that should scroll but does not, and footer buttons that collide. At
the large end look for a modal that stretches when it should stay fixed
width. Measurements are always reported in logical CSS pixels, so a value in
the inspector should match the value in the stylesheet regardless of the
scale shown in the header.

## Confirming ADS compliance

Record the ADS component and variant in the entry's `ads` field. If the
production overlay does not match ADS, record what it actually is, not what
it should be, and raise the discrepancy separately. Making the gallery look
compliant while production is not defeats the purpose of the tool.

## Adding automated coverage

`qa_redline_overlays.py` walks the registry, so a new entry is covered by the
inventory, render, cleanup and isolation checks the moment you add it. A new
entry that cannot be staged fails the suite rather than being silently
skipped, which is what stops overlays from quietly rotting.

It also works the other way around: the suite scans `index.html` for every
`role="dialog"` and `role="alertdialog"` surface and fails if one of them is
missing from the registry, so a new product dialog cannot ship uninspectable.
If a surface genuinely does not belong in the gallery, exclude it in that
check with a reason, the way ADS Popover date pickers are excluded.

Two surfaces are excluded today because they are presentation, not product:
the Cmd+P rate card explainer (`[data-rcle]`) and the pricing complexity
dialog (`#wpc-modal`). Both explain the product to an audience rather than
being screens a user works in, so they are not pages a designer redlines. A
paired check fails if anything matching those markers is registered again.

Add a targeted check of your own when an entry has behavior the generic walk
cannot see, such as a specific stack order or a particular ARIA relationship.
