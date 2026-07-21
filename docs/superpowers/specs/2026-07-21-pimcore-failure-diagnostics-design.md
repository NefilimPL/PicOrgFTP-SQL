# Pimcore Failure Diagnostics Design

## Goal

Make a failed manual Pimcore create or update explainable from its incident
mail without placing a raw exception in the mail body or public API.

## Chosen approach

Carry the caught exception from the Pimcore operation boundary into the
existing observability event. The existing event pipeline records a redacted
exception type and traceback, and the existing notification pipeline creates
the bounded, redacted text attachment for qualifying error events.

This is preferable to changing only the mail template, because the current
final Pimcore event discards the exception before the mail layer can see it.
It is also preferable to rendering a raw error in the mail body, which would
increase the risk of exposing credentials.

## Flow

1. The manual create/update wrappers initialize an optional failure exception.
2. If the Pimcore client raises, the wrapper retains that exception while
   preserving current re-raise, audit, submission-history, and status
   behavior.
3. The final integration event receives the optional exception.
4. Failed integrations emit severity error, an explicit recommended action,
   and the exception through observability.
5. Observability redacts and bounds the traceback; the mail service adds its
   safe diagnostic attachment. Normal HTML and text mail bodies remain free
   of exception text.

The recommended action for a failed Pimcore integration directs the operator
to the Pimcore operation history for the EAN and to the redacted diagnostic
attachment. It must not promise a specific root cause before the error is
known.

## Scope

- Update the shared Pimcore integration-event helper and the manual create and
  update wrappers in picorgftp_sql/web_data.py.
- Add tests for failed PIMcore operations proving exception propagation,
  recommended action, and safe mail-facing event fields.
- Reuse the existing sanitization, attachment, recipient, API projection, and
  incident behavior. Do not change the generic connection-test mail feature.

## Acceptance criteria

- A failed manual Pimcore operation emits an error event with exception_type,
  redacted traceback_text, and a non-empty recommended_action.
- Error mail receives the existing bounded/redacted diagnostic attachment.
- Raw traceback text stays out of normal mail text/HTML bodies and public API
  responses.
- Successful and conflict behavior is unchanged.
- Tests cover the failure path and existing relevant suites remain green.
