# Active Web Users Design

## Goal

Show currently active logged-in web users in the top navigation area, just to the left of the `Zdjecia WWW` button, when an administrator enables the feature. The setting is disabled by default so existing installations do not expose user presence until an admin opts in.

The visible user indicators must look like presence labels, not navigation buttons. They should be visually related to the top bar but clearly non-interactive.

## Existing Context

The FastAPI backend already records active web clients in memory and flushes a recent snapshot to `logs/web_active_clients.json`. The desktop web manager uses this data to show active users and TCP connections.

The web frontend currently exposes the active-client endpoint only to administrators at `/api/server/active-users`, and that payload includes operational details such as IP address, path, status code, and user agent. This feature must reuse the existing active-client tracking but expose a smaller privacy-safe payload to non-admin users only when enabled.

## Configuration

Add one web UI setting under the existing `security` configuration object:

```json
{
  "show_active_web_users": false
}
```

Normalization always returns a boolean value and defaults to `false`. Existing config files and SQLite config rows therefore keep the feature disabled until an administrator saves the setting.

The admin settings UI adds a checkbox in the `Bezpieczenstwo` tab:

- label: `Pokaz aktywnych uzytkownikow`;
- helper text: `Uzytkownicy zobacza nazwy kont obecnie aktywnych w panelu WWW.`;
- default unchecked.

Saving this option uses the existing `/api/settings` endpoint and the existing config persistence layer.

## Backend API

Add a user-accessible endpoint for sanitized presence:

```http
GET /api/server/presence
```

Behavior:

- requires a logged-in user;
- returns `{"enabled": false, "users": []}` when `show_active_web_users` is disabled;
- returns `{"enabled": true, "users": [...]}` when enabled;
- each user item contains only `username`, `last_seen`, and `last_seen_epoch`;
- omits unauthenticated entries and blank usernames;
- deduplicates by username, keeping the most recent `last_seen_epoch`;
- sorts newest first;
- limits output to 100 users.

The existing admin-only `/api/server/active-users` endpoint remains unchanged for diagnostics.

## Frontend Behavior

The top bar gains a non-button presence strip before `Zdjecia WWW`:

- hidden when the backend reports `enabled=false`;
- hidden when there are no active logged-in users;
- shows up to five user labels inline;
- each label contains a small status dot and the account name;
- labels do not use `<button>` styling and do not navigate;
- long account names truncate cleanly;
- if more than five users are active, a subtle `...` control appears.

Clicking `...` opens a small popover with the full sanitized user list. The popover shows account names and a compact "last seen" label. It closes when the user clicks outside it, presses Escape, or opens another modal.

The presence strip polls the new endpoint on the same background cadence used for light status polling. It must tolerate request failures silently so presence does not block normal work.

## Styling

Presence labels should fit the current top bar:

- use compact pill-like labels with a muted border or background;
- keep color lighter than `.nav-button` active states;
- avoid button cursor and button hover treatment;
- use `aria-label` text for the strip and popover;
- preserve responsive behavior on narrow screens by wrapping with the existing top nav.

The `...` element may be a small button for accessibility, but it must use a dedicated `presence-more-button` style so it does not look like a normal navigation button.

## Data Flow

1. Active-client middleware continues recording authenticated requests.
2. Admin saves `show_active_web_users` in the Security settings tab.
3. The frontend loads bootstrap/settings and starts the presence poller.
4. The poller calls `/api/server/presence`.
5. When enabled, the UI renders sanitized, deduplicated usernames next to `Zdjecia WWW`.
6. When disabled, the UI removes the presence strip and popover content.

## Error Handling

- Malformed or missing config defaults to disabled.
- Presence endpoint failures leave the previous UI state briefly, then clear the strip on the next failed refresh.
- Users with no valid username are excluded.
- Expired active clients are pruned by the existing active-client snapshot logic.
- The UI must not display IP addresses, paths, status codes, ports, or user agents outside the admin diagnostics endpoint.

## Testing

Automated coverage will include:

- config normalization defaults `show_active_web_users` to `false`;
- settings update persists the boolean in the security config;
- settings snapshot exposes the normalized value;
- `/api/server/presence` returns disabled payload by default for logged-in users;
- enabled presence returns only sanitized, deduplicated logged-in usernames;
- unauthenticated and blank entries are omitted;
- admin diagnostics endpoint keeps its existing detailed payload;
- static UI integrity verifies the presence container exists before `Zdjecia WWW`;
- frontend source includes rendering and polling paths for the disabled, inline, overflow, and failure states.

Focused tests will be written first and watched fail before implementation.
