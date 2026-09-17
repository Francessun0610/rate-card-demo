# Rate Card Manager (RCM), Atlas prototype

A portfolio demo of a Rate Card Manager for an advertising sales workflow.
It implements the Rate Card list, the shared Create and Edit experience,
Quick Edit, and CSV import and export.

**Everything in this prototype is a demo.** All rate cards, advertisers,
agencies, rates, premiums, Saleshub style identifiers, user names, and
timestamps are fictional sample data created for this portfolio piece. There
is no backend, no account, and no live integration: the app runs entirely in
the browser and stores state locally. Brand names appear only as realistic
sample content for the advertising domain.

## Running it locally

No build step. Serve the folder with any static server:

```bash
python3 dev_server.py
```

Or:

```bash
python3 -m http.server 8080
```

Then open `http://localhost:8080/`.

## Deploying

Any static host works. For Vercel, import the repository, leave the
framework preset as **Other**, and leave the output directory at the
repository root. `vercel.json` and `.vercelignore` are set up for this, and
`.vercelignore` keeps the local QA suite and design notes out of the deploy.

## Demo mode behavior

- **Feedback panel**: capture, annotation, and drafting work as designed.
  Submission runs offline, so nothing is sent anywhere. Copy feedback and
  Download screenshot are the local fallbacks.
- **Finance and Admin nav items**: kept in the sidebar with their styling
  and tooltips. Selecting one shows a short "not available in this
  portfolio preview" notice instead of navigating to another product.
- **Redline**: the developer inspection overlay loads on localhost only.

## Features

- 100 synthetic Rate Cards using only Upfront, Scatter, and Multi-Year
- Shared Create and Edit experience for CARD, LINE, and PREM data
- Data-driven Line Item and Premium pagination, search, sorting, and counts
- CSV template download, partial CSV import, and full Rate Card export
- Quick Edit for LINE rows with persistent changes
- Responsive tables with sticky priority columns and accessible selection

## Headless QA coverage

The QA suites drive a headless Chrome against a local server. They are
development tooling and are not deployed.

    python3 qa_v2.py
    python3 qa_demo_dataset.py
    python3 qa_comprehensive_review.py
    python3 qa_ads_compliance.py

These cover the Rate Card workflows, design system treatments, responsive
behavior, synthetic data integrity, and browser console health.

## Project structure

| Path | Purpose |
|------|---------|
| `index.html` | App shell |
| `app.js`, `v2.js` | Application logic |
| `styles.css`, `v2.css` | Styling |
| `fixtures/` | Demo catalog data |
| `assets/` | Icons, illustrations, brand marks |
| `feedback*.js` | Feedback capture UI, offline in this build |
| `redline*` | Local design inspection tooling |
| `qa_*.py` | Headless QA suites, local only |
| `docs/` | Product and design notes |
