# Slot open overlay correction

## Goal

Keep the Open button present for every slot while restoring the pre-existing
slot card layout exactly.

## Layout

- FIT remains in the preview's upper-left overlay position.
- Usun remains in the preview's upper-right overlay position.
- Otworz remains in the preview's lower-left overlay position.
- No controls are appended to slot metadata and no CSS change may alter card
  or preview dimensions.

## Behavior

The Otworz button is always created in the preview overlay. It is disabled
until the selected source is ready and is enabled in place after a LOCAL, FTP,
or SQL source update. Existing readiness behavior is unchanged.

## Regression checks

- FIT, Usun, and Otworz are appended to the existing preview overlay.
- The Open button is not conditionally omitted while a source is loading.
- The old grid and preview CSS rules remain responsible for card dimensions.
