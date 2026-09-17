# Line Items Table Figma State Matrix

The linked Rate Card nodes are regions of the same populated desktop frame (`450:7895`, 1440 by 960). They define one coherent table rather than sixteen separate screen states. Missing states use ADS v2.1 and existing Rate Card behavior.

| Node | Region or state | Key implementation details |
|---|---|---|
| `455:15032` | Sortable header | Seven columns, 32px header, opaque white surface, bottom divider |
| `455:13937` | Data row 1 | Default row, 48px height |
| `455:13959` | Data row 2 | Default row, 48px height |
| `455:13981` | Data row 3 | Default row, 48px height |
| `455:14003` | Data row 4 | Default row, 48px height |
| `455:14025` | Data row 5 | Default row, 48px height |
| `455:14047` | Data row 6 | Default row, 48px height |
| `455:14069` | Data row 7 | Default row, 48px height |
| `455:14091` | Data row 8 | Default row, 48px height |
| `455:14113` | Data row 9 | Default row, 48px height |
| `457:15192` | Data row 10 | Default row, 48px height |
| `455:14157` | Pagination footer | Page size, real filtered total, generated page range, page jumper |
| `457:15187` | Compact tabs | Active Line items tab with dynamic count, inactive Premiums tab |
| `455:13884` | Heading | New Rate Card title and CARD, LINE, PREM description |
| `455:13732` | Header actions | Back link, Save as Draft, primary Save Rate Card |
| `455:13730` | Workspace surface | 868 by 800 desktop card, white surface, subtle border, 12px radius |

## Derived application states

- Empty account: no rows, no pagination numbers.
- Populated: real LINE rows, total count badge, generated pagination.
- Search results: case-insensitive trimmed search across advertiser and card context.
- No results: distinct message with a clear-search action.
- Loading: ADS skeleton rows, no empty-state message.
- Error: load failure message and functional retry.
- Sorted: active header exposes ascending or descending `aria-sort`.
- First, middle, and last pages: generated ranges and correct boundary controls.
- Row hover, keyboard focus, and editing: row activation opens the existing LINE editor.
- Removal: edit-mode Remove action opens an ADS confirmation modal.
- Narrow viewport: the table keeps readable column widths inside its own horizontal scroller.

ADS Pagination node `35:36` supplies the page-item anatomy and state styling. Its numbers are examples only.
