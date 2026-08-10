# Slot Source Overlay Controls Design

## Goal

Move slot actions onto the preview, make every source badge select a visible source state, and make the SQL state useful without pretending it is a file.

## Slot overlay controls

The existing action row below the source badges is removed. For every slot with a current file or source, controls are rendered inside the preview:

- FIT is in the top-left corner;
- Usun is in the top-right corner;
- Otworz is in the bottom-left corner.

Controls retain their existing actions. Otworz opens the file or URL from the currently active source. It is hidden or disabled when that source has no openable value.

## Source switching

LOCAL, FTP, SQL, and POD are source selectors.

- LOCAL, FTP and POD show their respective file preview using their current signed/local source.
- SQL shows a text card containing the SQL value and a copy control.
- If the SQL value is an HTTP(S) URL, the overlay Otworz opens that URL in a new tab. Otherwise it is unavailable in the SQL state.
- SQL remains selectable whenever a SQL value exists.

## Decision modal

The per-row decisions are visibly filled buttons:

- Zachowaj: green background with white text;
- Odrzuc: red background with white text.

Their contrast does not depend on hover state.

## Verification

Tests cover source badge selection, SQL text/copy state, overlay positions and source-aware open behavior. Existing similar-file UI tests, JavaScript syntax checks, and focused web test suites must continue to pass.
