# Cross-Platform Rate Card Demo Fixture

The synthetic demo fixture lives in `fixtures/demo-cross-platform-rate-card.js`.

## Enable

Open the application with:

`?version=2.0&demoData=cross-platform-2026-27`

The Rate Card list will include `Disney Advertising 2026-27 Cross-Platform Rate Card`. Select its name to open the shared Edit page.

The fixture is disabled when the `demoData` query parameter is absent. It does not add records to the normal list or storage in that state.

## Reset

Run this in the browser console:

`window.RCMDemoRateCard.reset()`

Then refresh the page. This removes saved edits for the fixture and restores the deterministic source records.

To remove the demo completely, remove the fixture script tag from `index.html` and delete the fixture file.

## Dataset

- 100 unique LINE records, `LI-0001` through `LI-0100`
- 44 unique PREM records, `PREM-0001` through `PREM-0044`
- 20 fictional advertiser accounts across major advertising categories
- USD pricing using the approved CPM, Flat Rate, and Unit Price values
- Premium-to-LINE relationships stored in `lineItemIds`
- Dates within the 2026-10-01 through 2027-09-30 Rate Card effective period

The application currently supports four Ad Type values and four Base Offering values. The fixture intentionally uses only those approved enums, even though the original demo request targeted at least six of each.

All names and rates are synthetic demonstration data. They do not represent confidential customer information or real negotiated prices.
