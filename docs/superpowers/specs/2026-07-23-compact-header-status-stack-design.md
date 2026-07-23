# Compact header status stack

## Goal

Keep the web-panel header compact without allowing operational indicators to
consume the navigation area.

## Layout

On desktop, the left header cluster contains the GitHub button, application
name, version and photo location. Immediately beside that information is a
vertical status stack:

1. Backend latency, for example `Wolno · 203 ms`.
2. Compact host-resource summary, for example `System: 35%/91%/3%` for CPU,
   RAM and disk activity.

The status stack is not in the same horizontal row as the location. On narrow
screens it moves below the application information before navigation can be
compressed or obscured.

## Resource information

The compact header summary contains host values only. Detailed host and
backend metrics remain unchanged in the existing resource-details popover,
opened by the compact status control. This preserves diagnostics while keeping
the always-visible header small.

## Verification

Static UI tests verify the status-stack order, the location placement and the
compact `System: CPU/RAM/DISK` rendering. Existing interaction and resource
detail tests remain valid.
