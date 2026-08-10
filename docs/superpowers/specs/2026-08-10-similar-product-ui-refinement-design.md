# Similar product UI refinement — design

## Goal

Make similar-file detection controls compact and slot-local, while making previews and opening suggested files reliable on mapped or resolved filesystem paths.

## Settings layout

The global `Wykrywaj pliki z podobnych produktow` checkbox remains above the slot list. Each slot row receives its own `Podobne` checkbox. It is checked when that prefix is in `similar_file_detection.slot_prefixes` and disabled while the global option is off. Saving continues to send the same settings payload; there is no configuration migration.

## Suggestion controls

The source badge is shortened from `PODOBNE` to `POD`. A pending candidate shows its colour and compact `✓` / `×` controls instead of the full-width accept button. `✓` accepts the candidate; `×` dismisses that slot's current candidate.

When a manual file occupies a candidate slot, the suggestion is dismissed for that occupied prefix and a fresh lookup uses the occupied slots. The existing discovery allocator then offers the candidate in the next permitted free slot. A later UI refresh preserves accepted similar candidates.

## Preview and open safety

The unaccepted image preview uses the candidate's signed thumbnail URL directly, rather than deriving it from the currently selected slot source. PDF candidates continue to use the signed file URL in the embedded object.

The token validator canonicalizes both the token path and each allowed root with `realpath(abspath(...))` before containment checking. This preserves the existing signed-token and allowed-root security boundary while treating a mapped path and its resolved physical target as the same local source.

## Verification

Regression tests cover: canonical allowed-root validation, direct candidate thumbnail rendering, manual-slot reallocation request, compact accept/reject controls, and slot-local settings serialization. The focused similar-file, web API, and UI suites must pass; Node syntax and Python compilation are also checked.
