# CodeQL Regex Removal Design

## Goal

Remove the two CodeQL `polynomial-regex` findings without changing which mailboxes are accepted or how secret-bearing text is redacted.

## Design

`email_settings.py` will replace the local-part regular expression with a small ASCII character predicate. The existing checks for length, dots, whitespace and domain labels stay unchanged.

`redaction.py` will replace the structured-field regular expression with a forward-only parser. It accepts the existing grammar: an ASCII identifier starting with a letter or underscore, followed by letters, digits, dot, underscore or hyphen, optional spaces/tabs, then `:` or `=`. It remains used only to decide whether a comma or closing parenthesis ends a sensitive value.

## Safety and Tests

Both parsers are linear and contain no backtracking regular expression. Tests will prove the accepted/rejected e-mail character set, structured-field boundary behavior, and very long hostile-looking input. No new dependency or configuration is needed. GitHub CodeQL remains the authoritative post-push scanner because it is not installed locally.
