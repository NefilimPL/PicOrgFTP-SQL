# Email Notification Test Suite Design

## Goal

Allow an administrator to verify every configured notification severity without creating real incidents: information, warning, error, critical error, and a simulated Entra Client Secret expiry alert.

## Behavior

The existing one-recipient transport test remains unchanged. A second action, "Testuj wszystkie typy powiadomień", sends five independent direct test messages using the selected channel and optional fallback. Each message contains a randomly selected harmless Polish scenario description and a visible `[TEST]` marker.

Each scenario resolves recipients from its actual saved severity rule. The related-user option is intentionally excluded because a test has no real task actor. A disabled rule or a rule without valid recipients is reported as skipped, not treated as a transport error. The Entra-expiry scenario uses `critical` routing and plainly says that it simulates an expiring Client Secret.

## Safety and Feedback

The suite does not persist an event, incident, intent, or delivery. It reuses the existing direct transport and fallback handling. The API returns a redacted result per scenario; the UI presents sent, fallback, error, or skipped status for all five cases. Tests cover recipient routing, skipped rules, fallback, safe response projection, and source integrity.
