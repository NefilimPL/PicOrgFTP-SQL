# FTP preview refresh design

## Goal

Ensure that a selected FTP source is refreshed from the authoritative FTP service before it is shown or opened, so a stale local preview-cache token cannot open `/api/file` with a 404 response. Move the three preview actions closer to their corners.

## Scope

- Keep SQL as a presence/value indicator only. SQL URLs continue to open directly, and availability of the remote URL is not checked by PicOrgFTP-SQL.
- When the user selects the FTP badge, request a fresh FTP preview even if the browser already has a token cached for that EAN and filename.
- When the user opens an active FTP source, refresh it first and open only the URL returned by that refresh.
- Preserve the existing FTP cache for passive/background previews; forcing a refresh is limited to explicit user actions.
- Position FIT at top-left, Usuń at top-right, and Otwórz at bottom-left with a 3px inset from the preview frame.

## Data flow and error handling

`loadFtpPreview` gains a `forceRefresh` option. It bypasses the browser's `ftpPreviewCache`, calls `/api/ftp-preview`, then replaces the slot's FTP token, file URL, thumbnail URL, and cache entry with the server response. `openSlotFile` awaits this path for the active FTP source before calling `window.open`.

If the remote FTP file is unavailable, `/api/ftp-preview` supplies its existing readable error response; no stale `/api/file` URL is opened. SQL remains unchanged: a SQL value is displayed and HTTP(S) values are opened directly.

## Tests

- UI contract regression: forced FTP refresh must bypass a stale browser cache and the open path must await it for FTP.
- UI contract regression: action overlays use 3px insets.
- Existing web/UI suites, JS syntax, Python compilation, and whitespace diff checks must pass.
