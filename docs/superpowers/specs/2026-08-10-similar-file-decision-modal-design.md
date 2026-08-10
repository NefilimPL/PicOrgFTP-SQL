# Similar File Decision Modal Design

## Goal

Make files suggested from similar products unmistakable and require an explicit, per-slot decision before a product update can be submitted.

## Scope

This design applies only to unaccepted candidates returned by the existing similar-file lookup. It does not change matching rules, slot settings, file persistence, or manual upload behavior.

## Slot state

Each slot with an unaccepted similar-file candidate is a **pending decision**. Its card must:

- show the candidate preview without requiring the `POD` source button;
- display a visible blue status label, `Wymaga decyzji · z podobnego`, near the slot heading;
- have a blue highlighted border with a restrained pulse animation;
- expose compact, always-visible green accept and red reject controls within that status label, with accessible labels and tooltips;
- retain the existing source selector (`POD`) for switching the preview when more than one source is present.

The status styling differentiates a pending candidate from both a manually selected file and an already accepted similar file. It must not rely only on image opacity.

## Update gate

When the user submits an update and one or more pending decisions exist, the normal submit request must not start. Instead, the application opens a modal.

Closing the modal leaves every pending decision unchanged and keeps submission blocked. Repeating the update action opens the modal again. The first unresolved slot is scrolled into view when the modal is opened and after closing it without completing decisions.

## Decision modal

The modal lists only pending candidates. Every row includes:

- slot ID and name;
- candidate filename and source product/color context;
- an image thumbnail or an embedded PDF preview;
- green `Zachowaj` and red `Odrzuć` controls.

Making a decision updates the row to its resulting state rather than immediately removing it. Accepted candidates become selected slot files through the current acceptance path; rejected candidates use the current dismissal path.

The modal footer includes:

- `Odrzuć wszystkie`, which explicitly rejects every pending candidate;
- `Zapisz i kontynuuj`, disabled until no pending candidates remain.

Once all decisions are made, `Zapisz i kontynuuj` resumes the originally requested update through the normal submit flow. No candidate is persisted before explicit acceptance.

## Error handling and accessibility

If a candidate preview cannot be loaded, the row shows its filename and the existing preview fallback; its accept/reject controls remain usable. Modal controls are keyboard reachable, provide accessible names, and do not rely on color alone.

## Verification

Tests will cover the submit gate, all-reject behavior, accept/reject state transitions, continuation only after every decision, default candidate preview, and the slot/modal state markers. Browser syntax and focused web UI tests will also run.
