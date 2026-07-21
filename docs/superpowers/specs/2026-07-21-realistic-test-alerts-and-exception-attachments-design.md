# Realistic Test Alerts and Redacted Exception Attachments Design

## Goal

Keep the ordinary mail-test button as a narrow connection test. Make the
separate "test all notification types" action send realistic-looking,
harmless `[TEST][SYMULACJA]` messages. Error and critical alerts may carry a
small, redacted exception attachment when the source is an actual or simulated
exception; ordinary validation and non-exception failures must never attach a
diagnostic file.

## Scope and Scenarios

The connection-test button keeps its current generic message and recipient
entry. It proves that the selected transport can deliver one message; it does
not impersonate an incident.

The test-suite action remains a five-message, direct-send workflow. It does
not create operational events, incidents, outbox records, history rows, or
application-side effects. Every subject and visible mail body begins with
`[TEST][SYMULACJA]`.

The five scenarios are:

1. PIMcore rejected the submitted data (`warning`): a believable validation
   problem, with no attachment.
2. FTP transfer failed (`error`): a simulated transport exception, with an
   attachment.
3. The configured photo location is unavailable (`error`): an operational,
   non-exception failure, with no attachment.
4. An unhandled backend exception stopped a task (`critical`): a simulated
   traceback, with an attachment.
5. The Entra Client Secret expires in seven days (`critical`): a configuration
   alert, with no attachment.

There is intentionally no immediate informational test message. Informational
product changes are represented by the daily summary, rather than a separate
incident-style e-mail, so the test suite preserves the anti-spam policy.

## Transport-Neutral Attachment Model

`MailMessage` gains an immutable sequence of small `MailAttachment` values.
Each attachment has a fixed safe filename, a MIME type, and UTF-8 content. The
normal mail path produces no attachments unless the notification payload has a
prebuilt safe exception attachment.

The two transports consume that same model:

- SMTP adds a `text/plain; charset=utf-8` MIME attachment through
  `EmailMessage`.
- Microsoft Graph adds a `fileAttachment` object with a base64-encoded
  `contentBytes` field.

No transport-specific formatting or exception selection is placed in
`NotificationService`; it only supplies an attachment-ready message.

## Exception Attachment Construction

`NotificationService` creates the attachment only when all conditions hold:

- severity is `error` or `critical`; and
- the event/test scenario contains an exception type or traceback text.

The filename is fixed to `picorgftp-sql-exception.txt`. Its text begins with a
short explanation that the content was redacted, then contains only the safe
exception type and/or sanitized traceback. It is capped at 24 KiB after
UTF-8-safe truncation. The same redaction pass removes passwords, tokens,
Client Secrets, and key IDs before any text is stored or delivered. Raw
tracebacks stay out of normal HTML and plain-text mail bodies.

Validation errors, forbidden file or slot errors, incorrect input, unavailable
photo locations without an exception, and Entra expiry alerts do not satisfy
these conditions and therefore have no attachment.

For durable incident delivery, the notification payload persists only this
already-redacted, bounded attachment representation. It never persists a raw
traceback or unredacted credentials in delivery JSON.

## Flow and Failure Handling

For a real notification, event data is converted into the existing mail
payload plus an optional safe attachment representation. `_mail_message`
converts it into `MailAttachment` values immediately before delivery. A retry
therefore sends the same bounded, redacted diagnostic.

For the test suite, scenario templates define their harmless user-facing
content and optional synthetic exception text. The FTP and backend-exception
templates use the same attachment builder as real events, so transport output
matches a real alert while remaining explicitly marked as a simulation.

Delivery, fallback, recipient resolution, and the redacted API result remain
unchanged. The API never returns attachment content, filenames, message IDs,
or recipients.

## Tests

Tests cover:

- Graph and SMTP serialization of a text attachment and the absence of an
  attachment when none is supplied.
- All five test-suite scenarios, the `[TEST][SYMULACJA]` marker, and direct
  delivery without store writes.
- Attachments only for simulated FTP and backend exceptions.
- Real `error`/`critical` exception events receiving an attachment, while
  validation, forbidden-file/slot, bad-input, photo-location, and Entra
  scenarios do not.
- Redaction of password, token, Client Secret, and key-ID values plus the
  24 KiB bound in both payload and serialized transport output.
- The API's public projection continuing to omit private mail and attachment
  data.
