# Daily Change Summary and Mail Help Design

## Goal

Replace immediate informational e-mails with one readable daily change summary and explain every mail severity and Microsoft Entra credential field in the settings UI.

## Daily Summary

Mail settings gain `daily_summary_time`, normalized as `HH:MM`, defaulting to `16:00` in `Europe/Warsaw`. The notification worker sends at most one successful report per configured reporting interval. Each report covers the continuous interval from the prior successful report to the current scheduled run; therefore a change after 16:00 appears in the next report and no change is lost.

The report is sent only when the interval contains product-history changes. It uses recipients from the enabled `info` rule, does not add an actor, and uses the configured primary channel and fallback. The report groups all history records by EAN, with no maximum number of products. Each EAN is one compact line stating only: entry created, PIMcore data updated (changed field names), and/or photos updated (slot numbers). It contains no SQL, FTP, timing, internal log or raw JSON data. A durable SQLite report record prevents duplicates after restart; failed sends remain retryable.

All individual `info` events remain in operational logs but no longer create a notification outbox intent. Warning, error and critical delivery behavior is unchanged.

## Help Popovers

Reusable keyboard-accessible `?` controls open concise help popovers beside notification severity titles and Entra/SMTP fields. Help describes the audience and content for each severity. Entra text explicitly maps Tenant ID to `Identyfikator katalogu (dzierżawy)`, Client ID to `Identyfikator aplikacji (klienta)`, and Client Secret to `Certyfikaty i wpisy tajne → Wpisy tajne klienta → Wartość`, never Secret ID or Object ID.
