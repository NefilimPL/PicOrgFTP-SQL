# Parcel template functions design

## Goal

Allow a Pimcore template to derive a numeric package count from entered parcel
fields without relying on a numeric dimension value.

## Scope

Add four placeholder functions to the existing template grammar.  Each
function is appended to a normal placeholder and therefore works in the
current template editor, preview, and runtime renderer without introducing a
second expression syntax.

* `filled` accepts no arguments and returns `1` for a non-blank source value,
  otherwise `0`.
* `any_filled` returns `1` when its source or any quoted source supplied as an
  argument is non-blank, otherwise `0`.
* `count_filled` returns the number of non-blank values among its source and
  quoted source arguments.
* `if_filled:"present","empty"` returns its first literal argument for a
  non-blank source value and its second argument otherwise.

Source arguments are resolved with the same catalog and aliases as ordinary
placeholders.  For example, a package count based on widths can use:

```text
{PIMCORE:parcel_1_width|filled}+{PIMCORE:parcel_2_width|filled}
```

For a package identified by any dimension, use its first field as the
placeholder and list the remaining sources as arguments:

```text
{PIMCORE:parcel_1_depth|any_filled:"PIMCORE:parcel_1_height","PIMCORE:parcel_1_weight","PIMCORE:parcel_1_width"}
```

## Error handling

`filled` rejects arguments. `any_filled` and `count_filled` accept any number
of additional source arguments. `if_filled` requires exactly two arguments.
Unknown source arguments use the existing `unknown_source` template error.

## User interface and verification

The template builder lists all four functions with copyable syntax. Unit tests
cover blank values, whitespace, multiple source arguments, conditional text,
argument validation, source-catalog resolution, and the eleven-width package
formula. UI integrity tests assert the newly exposed builder tokens.
