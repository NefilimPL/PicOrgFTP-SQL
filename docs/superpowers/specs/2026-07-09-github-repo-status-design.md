# GitHub Repo Status Design

## Scope

Add a GitHub status button to the web panel header next to the application name. The button opens repository information for the fixed repository `NefilimPL/PicOrgFTP-SQL`.

This feature does not add auto-update behavior, one-click updates, editable repository settings, or editable GitHub tokens.

## Security

The application will not store, request, or expose a GitHub token. It will call public GitHub REST API endpoints without authentication.

GitHub repository secrets are not used by the runtime application. They are only available to GitHub Actions workflows and should not be embedded into the built application.

If GitHub reports the repository as unavailable, the UI will state that the repository is private or unavailable.

## User Experience

The header gets a compact GitHub icon button near `PicOrgFTP-SQL Web`, `versionInfo`, and `serverInfo`.

Clicking the button opens a modal with:

- repository link,
- visibility or private/unavailable notice,
- latest release tag and release date,
- license,
- owner,
- contributors listed separately from the owner.

The GitHub icon pulses when a newer public release is available.

For local version `dev`, the latest public release is always treated as newer. This makes the update indicator visible during development.

For release versions, version comparison uses semantic tags such as `v1.2.3` or `1.2.3`. If either value cannot be compared safely, the UI shows the release details but does not claim an update is available.

## Architecture

Backend:

- Add a small GitHub metadata helper in the web backend boundary.
- Add `GET /api/github/repository`.
- Fetch public GitHub API data server-side so the browser stays same-origin under the existing Content Security Policy.
- Cache successful and unavailable responses for a short interval to reduce anonymous API rate-limit pressure.
- Return a normalized JSON payload with `available`, `private`, `repository`, `latest_release`, `license`, `owner`, `contributors`, `current_version`, and `update_available`.

Frontend:

- Add static HTML for the icon button and modal.
- Add CSS for the compact icon button, modal details, and pulse animation.
- Add JS that loads GitHub status during bootstrap or shortly after, applies the pulse class, and refreshes details when the user clicks the button.

## Error Handling

Network failure, rate limiting, and non-JSON GitHub responses become a friendly UI message. The backend must not log or return secrets because no secret is involved.

`404` from GitHub is treated as private or unavailable. Other GitHub errors are treated as temporarily unavailable.

## Testing

Backend tests cover:

- public repository payload normalization,
- private or unavailable repository response,
- latest release newer than `dev`,
- semantic version comparison for released versions,
- GitHub failures returning a safe unavailable payload.

UI integrity tests cover:

- GitHub button and modal IDs exist,
- JS selectors match static HTML,
- CSS includes pulse styling,
- static JS references the GitHub endpoint and renders update state.
