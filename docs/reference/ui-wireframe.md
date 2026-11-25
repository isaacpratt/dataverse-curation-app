---
page_type: reference
tgdp_template: Reference
audience: developer
---
# UI wireframe reference

Numbered map of the painted app. Each `[NN]` badge in [the SVG](../assets/ui-wireframe.svg) names one box; the legend below gives its Qt class, `objectName` (the QSS selector and `findChild` key), layout manager, size policy and measured bounds. Tags sit in a gutter beside the boxes so the labels never distort the proportions they describe. For the rules behind the layout, see [UI conventions](../explanation/ui-conventions.md).

<!-- BEGIN GENERATED UI WIREFRAME -->

| Tag | Screen | Element | Qt class | objectName | Layout | Size policy | Bounds (x,y w,h) | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [01] | Main window / dashboard | Top nav bar | QFrame | `TopNav` | QHBoxLayout | Preferred | 0,0 1280,48 | fixed 48 px high chrome; sits above the page stack |
| [02] | Main window / dashboard | Active nav button | AppButton | `NavActive` | — | Minimum/Fixed | 10,6 82,32 | selected state; 32 px high |
| [03] | Main window / dashboard | Nav button | AppButton | `NavItem` | — | Minimum/Fixed | 105,6 32,32 | one per pane; same 32 px height |
| [04] | Main window / dashboard | Chip row | QWidget | `ChipsWrap` | QHBoxLayout | Expanding/Preferred | 302,0 826,48 | Expanding/Preferred; wraps chips |
| [05] | Main window / dashboard | Window controls | QWidget | `WinControls` | QHBoxLayout | Preferred | 1134,0 144,48 | fixed-width right edge of the nav bar |
| [06] | Main window / dashboard | Dashboard page | DashboardView | `DashboardView` | QVBoxLayout | Preferred | 0,0 1280,812 | background of the stacked page |
| [07] | Main window / dashboard | Metric card | QFrame | `MetricCard` | QHBoxLayout | Preferred | 22,22 400,52 | three across; one per queue metric |
| [08] | Main window / dashboard | Queue card | QFrame | `Card` | QVBoxLayout | Preferred | 22,94 1232,641 | contains the header and the table |
| [09] | Main window / dashboard | Queue header | QFrame | `QueueHeaderBar` | QVBoxLayout | Preferred | 0,0 1230,92 | headline plus filter row |
| [10] | Main window / dashboard | Queue table | QWidget | `QueueStack` | QGridLayout | Preferred | 0,91 1230,547 | grid layout; one row per dataset |
| [11] | Main window / dashboard | Status pill | QFrame | `StatusPill` | QHBoxLayout | Preferred | 22,755 1204,31 | bottom status strip |
| [12] | Main window / dashboard | Progress ring | — | `RingProgress` | — | — | not present in this screen | busy indicator inside the status pill |
| [13] | Main window / dashboard | Docent mark | QLabel | `DocentMark` | — | Preferred | 1238,762 16,16 | watermark at the bottom-right |
| [14] | Dataset detail | Detail page | DatasetDetailView | `DetailView` | QVBoxLayout | Preferred | 0,0 1280,900 | root of the detail view |
| [15] | Dataset detail | Detail header | QWidget | `DetailTopBar` | QVBoxLayout | Preferred | 0,0 1280,163 | fixed 170 px; scrolls away with the main column |
| [16] | Dataset detail | Workflow rail | WorkflowRail | `WorkflowRail` | QHBoxLayout | Preferred | 22,14 1232,36 | step buttons; fixed 36 px high |
| [17] | Dataset detail | Workflow step | QPushButton | `WorkflowStep` | — | Fixed | 170,0 125,36 | done/active/blocked states |
| [18] | Dataset detail | Filter chip | AppButton | `FilterChip` | — | Minimum/Fixed | 22,58 201,36 | chip family; 36 px high |
| [19] | Dataset detail | Review state pill | QLabel | `PillInReview` | — | Preferred | 231,58 48,36 | conditional: IN REVIEW only |
| [20] | Dataset detail | Draft state pill | — | `PillDraft` | — | — | not present in this screen | conditional: DRAFT only |
| [21] | Dataset detail | Primary action button | AppButton | `PrimaryButton` | — | Minimum/Fixed | 1026,58 172,36 | commit / approve |
| [22] | Dataset detail | Secondary action button | AppButton | `SecondaryButton` | — | Minimum/Fixed | 899,58 121,36 | download, export, back |
| [23] | Dataset detail | Dataset title | QLabel | `HeadlineLG` | — | Preferred | 22,104 723,30 | large headline |
| [24] | Dataset detail | Dataset subtitle | QLabel | `BodyMD` | — | Preferred | 22,136 723,17 | PID and owner line |
| [25] | Dataset detail | Status widget | StatusWidget | `StatusWidget` | QHBoxLayout | Preferred | 761,104 493,49 | info/success/error states |
| [26] | Dataset detail | Page stack | QStackedWidget | `DetailPages` | QStackedLayout | Preferred | 0,161 1280,737 | review page and response page |
| [27] | Dataset detail | Review page | QWidget | `DetailReviewPage` | QHBoxLayout | Preferred | 0,0 1280,737 | main column plus sidebar |
| [28] | Dataset detail | Main column | QWidget | `DetailMainContainer` | QVBoxLayout | Preferred | 22,10 870,1959 | scroll canvas for cards |
| [29] | Dataset detail | Sidebar | QWidget | `DetailSideContainer` | QVBoxLayout | Preferred | 0,0 358,789 | 280-400 px; horizontal scrollbar off |
| [30] | Dataset detail | Detail card | QFrame | `Card` | QVBoxLayout | Preferred | 0,76 870,1472 | metadata, files, checks, sensitivity |
| [31] | Settings | Settings pane | SettingsPane | `SettingsDialog` | QVBoxLayout | Preferred | 0,0 1272,951 | root of the settings form |
| [32] | Settings | Settings heading | QLabel | `HeadlineLG` | — | Preferred | 24,24 1224,30 | large headline |
| [33] | Settings | Settings help text | QLabel | `BodyMD` | — | Preferred | 24,70 1224,17 | body copy |
| [34] | Settings | Settings card | QFrame | `Card` | QVBoxLayout | Preferred | 24,103 1224,765 | grouped form controls |
| [35] | Settings | Search field | QLineEdit | `SearchField` | — | Expanding/Fixed | 122,64 1052,36 | line edit with a search icon |
| [36] | Settings | Field label | QLabel | `LabelStrongSM` | — | Preferred | 16,16 94,26 | small strong label |
| [37] | Settings | Cancel button | AppButton | `SecondaryButton` | — | Minimum/Fixed | 1095,11 64,32 | discard path |
| [38] | Settings | Save button | AppButton | `PrimaryButton` | — | Minimum/Fixed | 1167,11 57,32 | commit path |
| [39] | Settings | Pane footer | PaneFooter | `PaneFooter` | QHBoxLayout | Preferred | 24,884 1224,43 | fixed action strip |
| [40] | About | About pane | AboutPane | `AboutPane` | QVBoxLayout | Preferred | 0,0 1280,812 | root of the About page |
| [41] | About | About heading | QLabel | `HeadlineLG` | — | Preferred | 24,24 1232,30 | large headline |
| [42] | About | About card | QFrame | `Card` | QVBoxLayout | Preferred | 24,70 1232,452 | version and attribution |
| [43] | About | Docent mark | QLabel | `DocentMark` | — | Preferred | 21,21 64,64 | brand glyph |
| [44] | About | Updates card | QFrame | `UpdatesCard` | QVBoxLayout | Preferred | 21,312 1190,119 | last-checked state is conditional |
| [45] | About | Updates divider | QFrame | `UpdatesDivider` | — | Preferred | 0,12 1190,1 | separates actions |
| [46] | About | Check for updates | AppButton | `SecondaryButton` | — | Minimum/Fixed | 743,266 468,36 | disabled while a check runs |
| [47] | Log | Log page | LogPage | `LogPage` | QVBoxLayout | Preferred | 0,0 1280,812 | root of the app request log |
| [48] | Log | Log heading | QLabel | `HeadlineLG` | — | Preferred | 24,24 1232,30 | large headline |
| [49] | Log | Log search | QLineEdit | `SearchField` | — | Expanding/Fixed | 818,70 180,36 | filters request lines |
| [50] | Log | Log action | AppButton | `SecondaryButton` | — | Minimum/Fixed | 1006,70 71,36 | clear / export controls |
| [51] | Review configuration | Review config page | ReviewConfigView | `ReviewConfigView` | QVBoxLayout | Preferred | 0,0 1280,812 | root of the ruleset editor |
| [52] | Review configuration | Config heading | QLabel | `HeadlineLG` | — | Preferred | 24,24 1232,30 | large headline |
| [53] | Review configuration | Ruleset card | QFrame | `Card` | QVBoxLayout | Preferred | 24,70 1232,151 | one per configured ruleset |
| [54] | Review configuration | Card top bar | QFrame | `CardTopBar` | QHBoxLayout | Preferred | 1,1 1230,45 | title plus row actions |
| [55] | Review configuration | Card title | QLabel | `CardTitle` | — | Preferred | 16,12 50,20 | ruleset name |
| [56] | Review configuration | Card body | QWidget | `CardBodyWrap` | QVBoxLayout | Preferred | 1,46 1230,104 | parameter controls |
| [57] | Review configuration | Config search | QLineEdit | `SearchField` | — | Expanding/Fixed | 146,56 889,36 | line edit |
| [58] | Review configuration | Config action | AppButton | `SecondaryButton` | — | Minimum/Fixed | 990,14 63,32 | run / edit controls |
| [59] | Component gallery | Gallery window | GalleryWindow | `GalleryWindow` | QVBoxLayout | Preferred | 0,0 960,900 | root of the component gallery |
| [60] | Component gallery | Gallery heading | QLabel | `HeadlineLG` | — | Preferred | 22,18 190,36 | large headline |
| [61] | Component gallery | Gallery subtitle | QLabel | `BodyMD` | — | Preferred | 22,70 912,17 | body copy |
| [62] | Component gallery | Gallery content | QWidget | `GalleryContent` | QVBoxLayout | Preferred | 0,0 912,744 | scrollable body |
| [63] | Component gallery | Dual-theme view | QWidget | `GalleryDualTheme` | QHBoxLayout | Preferred | 0,0 912,455 | light and dark side by side |
| [64] | Component gallery | Theme column | QWidget | `GalleryThemeColumn` | QVBoxLayout | Preferred | 0,0 448,455 | one per rendered theme |

<!-- END GENERATED UI WIREFRAME -->

## Non-visible states

A static image cannot show a state that is not active while it is captured. These are the conditional states to check when a screenshot looks right but behaviour is wrong; the object names are the same ones in the legend.

| Family | objectName / QSS selector | Loading | Empty | Error | Disabled | Hover / focus |
| --- | --- | --- | --- | --- | --- | --- |
| Buttons | `#PrimaryButton`, `#SecondaryButton`, `#NavActive`, `#NavItem` | `setEnabled(False)` while a worker runs; `AppButton` keeps its height (32/36/40 px) | n/a — a button always renders | status text moves to `#StatusWidget`; the button itself is not an error surface | `setEnabled(False)`; QSS dims the face but keeps the outline | `#AppButton:hover` raises the surface; focus draws the accent ring |
| Chips | `#FilterChip`, `#ChipsWrap`, `#StatusWidget` | chip text is replaced with the phase message; `Expanding/Preferred` wrap keeps its row | placeholder text in the status widget | `#StatusWidget.set_error` paints the error tone and keeps the detail in the tooltip | no dedicated disabled chip; hide the chip instead | chip buttons follow the same `:hover` / `:focus` rules as buttons |
| Cards | `#Card`, `#MetricCard`, `#UpdatesCard` | card body shows a placeholder until its worker finishes | `#Card` keeps its frame and shows the empty-state label instead of rows | the card stays and the status widget carries the error; no card is deleted | controls inside the card are disabled individually | cards themselves do not take hover; only their controls do |
| Workflow rail | `#WorkflowRail`, `#WorkflowStep` | current step keeps its badge; later steps stay dimmed | n/a | a blocked step wears the lock mark (state is not colour-only) | unavailable steps are non-clickable | hover reveals the step tooltip; focus ring follows the button rules |

## Bounding-box constraints

These are the constraints that cause clipping and overlap. They are read from the running widgets (geometry, size policies and scroll areas), not inferred from the picture.

| Container | Fixed dimensions | Size policy | Overflow rule | Stacking (z-order) |
| --- | --- | --- | --- | --- |
| `#TopNav` | 48 px high (`setFixedHeight(48)`); nav buttons 32 px | `Preferred/Preferred`, `#ChipsWrap` `Expanding/Preferred` | chip row wraps; window controls keep a fixed 144 px edge | nav bar paints above the page stack |
| `#DetailTopBar` | 170 px tall in the captured layout; headline and status share the row | `Preferred/Preferred` | text elides (`#LabelMD`, `ElidedLabel`); status detail lines clip rather than wrap the header | header scrolls with the main column, below any popup |
| `#WorkflowRail` | steps fixed 36 px high (`BUTTON_HEIGHTS["md"]`) | `Fixed/Fixed` per step | horizontal rail; a long workflow scrolls, it does not wrap | rail sits above the page body inside the header |
| `#DetailSideContainer` | side scroll area min 280 px, max 400 px wide | `Preferred/Preferred` | horizontal scrollbar always off; vertical scrollbar owns overflow | sidebar is a sibling of the main column, never overlaps it |
| `#Card`, `#MetricCard` | metric cards 52 px high; chip/button heights 36 px | `Preferred/Preferred` | long labels elide; the card frame is not resized by its text | cards are painted in document order inside their scroll canvas |
| `#StatusWidget` | status detail fixed to the right edge of the strip | `Expanding/Fixed` on the caption | caption elides; error detail stays in the tooltip | strip is at the bottom of the page, below dialogs |

## Regenerate

```bash
uv run python tools/docs/gen_ui_wireframe.py --write   # regenerate SVG + legend
uv run python tools/docs/gen_ui_wireframe.py --check   # fail if stale
```

The generator boots the app offscreen against a throwaway workspace (never the configured instance), walks the real widget tree, and writes text-only SVG and Markdown. It assigns tags in registry order, so a published tag keeps its number across runs. `tools/tests/test_ui_wireframe.py` checks that every badge in the SVG has exactly one legend row, that no number is reused, and that the state and constraint tables are present — without needing Qt.
