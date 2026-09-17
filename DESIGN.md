# DESIGN.md

## Purpose

This project must follow the Disney Ads Design System v2.1 as the source of truth for UI implementation, component usage, styling, content quality, and migration decisions.

Every implementation, refactor, audit, or prompt should be checked against this file before changes are considered complete.

When a prompt ends with:
```
follow design md
```

Cursor must use this document as required context and verify the work against the rules below.

---

## Design System Source of Truth

Use the Disney Ads Design System v2.1.

Required grounding files:

- DESIGN.md
- .cursorrules
- ads-components.json
- ADS-v2.1-Migration-Guide.md if migration work is involved

The component knowledge base is `ads-components.json`.

The project should use ADS v2.1 components, tokens, state names, and interaction patterns. Do not rely on old EDL components, old ADS v1 vocabulary, or hand-built replacements when an ADS component exists.

---

## Global Implementation Rules

### 1. Use real ADS components

Use real ADS v2.1 components from the package.

Do not hand-build children inside compound components when real ADS instances exist.

Pay special attention to:

- Sheet
- Pagination
- Toggle Group
- Accordion
- Date Picker
- Select
- Multi-Select
- Popover-family components

Do not import from internal ADS paths. Import from the ADS package root unless the design system explicitly says otherwise.

---

### 2. Use ADS tokens only

Every color, spacing, radius, shadow, typography, and surface treatment must be bound to ADS v2.1 tokens.

Do not use:

- Hardcoded hex values
- Hardcoded pixel spacing
- Hardcoded rem spacing
- Hardcoded border radius
- Hardcoded shadows
- One-off CSS values that bypass ADS tokens

If a new token appears necessary, stop and flag it for review. Do not invent tokens.

---

### 3. Typography

Use ADS typography rules.

- Body text: Open Sans
- Display text: MultiplaneTWDC

Do not introduce unrelated fonts.

---

### 4. State naming

Use ADS v2.1 state names.

Approved state names:

- rest
- hover
- active
- disabled
- focus

Do not use old or inconsistent names such as:

- default
- pressed
- focused

---

### 5. Close buttons

Close buttons must always be neutral.

Do not tint close buttons based on status, alert type, error state, warning state, or semantic color.

---

### 6. Tables

Tables must follow ADS v2.1 patterns.

Table rows should be opaque and use ADS surface tokens, especially:

- `color/surface/default`

Do not use transparent table rows unless ADS explicitly allows it.

Tables should be readable, aligned, and not visually cramped.

---

### 7. Popover rules

Use the unified ADS Popover where appropriate.

Components that should consume Popover:

- Date Picker
- Multi-Select
- Select

Components that should not consume Popover:

- Tooltip
- Dropdown.Menu

Do not create bespoke floating panels if ADS already provides the correct component pattern.

---

### 8. No em dashes

Do not use em dashes in:

- String literals
- JSX text
- Comments
- UX copy
- Mock data
- Documentation generated for this project

Use commas, periods, parentheses, or shorter sentences instead.

---

## Migration Rules: EDL or ADS v1 to ADS v2.1

This project is moving from EDL and older ADS patterns to the Disney Ads Design System v2.1.

Every new change must check for old EDL components or styling and replace them with ADS v2.1 equivalents.

### Always check for old EDL usage

Before completing any UI task, inspect the touched files for:

- EDL component imports
- EDL class names
- EDL theme references
- EDL color tokens
- EDL table styles
- EDL dropdown styles
- EDL modal or sheet patterns
- Any copied EDL visual pattern that no longer matches ADS v2.1

If old EDL usage remains, flag it and replace it with ADS v2.1 if the equivalent is clear.

If the mapping is ambiguous, flag it for human review instead of guessing.

---

### ADS v1 to ADS v2.1 vocabulary changes

Apply these renames where relevant:

- violet to indigo
- neutral to gray
- steel to blue when used for information states
- teal: removed, replace only with a valid ADS v2.1 token
- mint: removed, replace only with a valid ADS v2.1 token
- old pink: removed, replace only with a valid ADS v2.1 token
- warning yellow to orange
- info steel to blue
- whitespace/* to spacing/*
- SegmentedControl to ToggleGroup
- Tooltip Tooth to Tooltip Arrow
- Tooltip Icon to Tooltip Small
- Tooltip Definition to Tooltip Large

---

### Structural migration rules

Apply these refactors when old structures appear:

1. **Sheet.** Use `<Sheet>` with real `<SheetHeader>` and `<SheetFooter>` instances.
2. **Pagination.** Replace old `<PaginationNav>` and `<PaginationCell>` patterns with `<PaginationItem variant="...">`.
3. **Toggle Group.** Wrap segments in `<ToggleGroupItem>`.
4. **Date Picker.** Use the ADS v2.1 Date Picker family, including Date Cell atoms and correct composites where needed.
5. **Popover.** Refactor bespoke floating panels to consume ADS Popover, except Tooltip and Dropdown.Menu.

---

## Content Rules

This project is for Disney Advertising work. UI content must be realistic, clear, and understandable to ADS Sales, Finance, Ops, and cross-functional business users.

### Replace fake Figma content

Figma links may include placeholder, fake, generic, or unrealistic content.

When implementing from Figma:

- Use the Figma layout and interaction intent.
- Replace fake content with realistic Disney Advertising business content.
- Do not blindly copy placeholder labels, sample names, or lorem ipsum.
- Use language that ADS Sales, Finance, Ops, and business stakeholders can understand.

---

### Content should be business-realistic

Use content related to Disney Advertising workflows, such as:

- Campaigns
- Advertisers
- Agencies
- Orders
- Deals
- Inventory
- Forecasting
- Delivery
- Billing
- Revenue
- Pacing
- Approvals
- Sales teams
- Finance review
- Ops handoff
- Platform setup
- Demand channels
- Regions
- Categories
- Product lines

The content should feel credible for Disney Advertising internal tools.

---

### Do not make the product feel like Linear

This project should not sound or feel like Linear, Jira, or a generic engineering task tracker.

Avoid content that is too software-project-management focused, such as:

- Issues
- Tickets
- Sprints
- Backlog grooming
- Bug queues
- Engineering-only workflows
- Linear-style project statuses
- Generic task-board language

Use Advertising, Sales, Finance, and Operations language instead.

---

### UX copy principles

UX copy should be:

- Clear
- Specific
- Business-friendly
- Reusable where possible
- Short enough for enterprise UI
- Helpful without overexplaining

Avoid:

- Placeholder text
- Internal jokes
- Overly casual language
- Engineering jargon for business users
- Fake user names unless the screen specifically requires people data
- Linear-style issue language
- Em dashes

---

## Prompt Behavior Rules

Whenever a user asks Cursor to implement, update, refactor, audit, QA, or generate code, Cursor must:

1. Read this DESIGN.md.
2. Check the relevant files against ADS v2.1.
3. Use `ads-components.json` as the component source of truth.
4. Avoid hand-built components when ADS components exist.
5. Replace fake Figma content with realistic Disney Advertising content.
6. Check for old EDL components or styling.
7. Check for ADS v1 names, states, tokens, and component references.
8. Use ADS tokens instead of hardcoded values.
9. Verify typography, spacing, table density, dropdowns, modals, sheets, and popovers.
10. Report anything ambiguous instead of guessing.

---

## Required Final QA Checklist

Before considering any task complete, verify:

- [ ] ADS v2.1 components are used correctly.
- [ ] No old EDL component remains in touched files.
- [ ] No ADS v1 component or token remains unless intentionally preserved and explained.
- [ ] No hardcoded color, spacing, radius, or shadow values were introduced.
- [ ] Typography follows ADS rules.
- [ ] State names use rest, hover, active, disabled, and focus.
- [ ] Close buttons are neutral.
- [ ] Table rows are opaque and readable.
- [ ] Popover usage follows ADS v2.1 rules.
- [ ] Figma placeholder content has been replaced with realistic Disney Advertising content.
- [ ] Copy is understandable to ADS Sales, Finance, Ops, and cross-functional business users.
- [ ] The UI does not feel like Linear, Jira, or an engineering task tracker.
- [ ] No em dashes appear in code, comments, UX copy, or mock data.
- [ ] The changed UI visually aligns with ADS v2.1, not EDL.
ADS Figma Reference

The ADS Figma file is a required visual reference for ADS v2.1 implementation:https://www.figma.com/design/DJb3yM8aOQjIAbTQ9Cd8Mi/Ads-Design-System?m=auto&node-id=2898-18&t=HYjRklsMpUncwa7N-1When implementing, auditing, migrating, or QA checking UI work, carefully reference the ADS Figma file whenever possible.

Cursor must use the ADS Figma file to verify:

* Component anatomy
* Component variants
* Spacing
* Density
* Table treatment
* Dropdown treatment
* Modal and sheet layout
* Popover behavior
* Tooltip behavior
* Form field styling
* Button hierarchy
* Navigation styling
* Empty states
* Error states
* Focus states
* Hover states
* Disabled states
* Typography scale
* Color usage
* Surface treatment
* Border radius
* Dividers
* Icon sizing and placement

The ADS Figma file should be treated as the visual source of truth, while ads-components.json, .cursorrules, and this DESIGN.md define the implementation rules.

If there is a conflict:

1. ads-components.json is the source of truth for available components and implementation names.
2. DESIGN.md is the source of truth for project-specific rules.
3. .cursorrules is the source of truth for Cursor behavior.
4. The ADS Figma file is the source of truth for visual alignment and design intent.

Do not copy fake placeholder content from the ADS Figma file into the product. Use the ADS Figma file for visual and component guidance only, then replace example content with realistic Disney Advertising content.

If the Figma file shows an ADS pattern that does not appear to exist in the current codebase, flag it for review instead of inventing a custom component.

If implementation differs from the ADS Figma reference, Cursor must explain why in the final compliance report.