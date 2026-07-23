# Compact Header Status Stack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put latency above a compact host-resource status beside the application information without consuming navigation space.

**Architecture:** `index.html` supplies a dedicated left-side status stack. CSS lays that stack out vertically on desktop and below application information on narrow screens. `renderResourceStatus` emits only three host percentages for the always-visible pill; the unchanged popover retains all host and backend diagnostics.

**Tech Stack:** Static HTML, CSS, browser JavaScript, Python `unittest` UI-integrity tests.

## Global Constraints

- Work only on the current `dev` branch; do not merge or write to `main`.
- Keep detailed backend and resource diagnostics in the existing resource popover.
- Preserve the existing accessible buttons, IDs and status-detail interactions.

---

### Task 1: Lock the header and compact-text contract

**Files:**
- Modify: `tests/test_web_ui_integrity.py:63-80`
- Test: `tests/test_web_ui_integrity.py`

**Interfaces:**
- Consumes: `#backendHealthStatus`, `#resourceStatus`, `#serverInfo` in `index.html`.
- Produces: a regression contract for a `header-status-stack` and `System: <cpu>/<ram>/<disk>` output.

- [ ] **Step 1: Write the failing test**

```python
def test_header_stacks_latency_above_compact_system_status(self) -> None:
    markup = INDEX_HTML.read_text(encoding="utf-8")
    source = APP_JS.read_text(encoding="utf-8")

    stack_start = markup.index('class="header-status-stack"')
    self.assertLess(markup.index('id="backendHealthStatus"'), markup.index('id="resourceStatus"'))
    self.assertLess(stack_start, markup.index('class="header-location"'))
    self.assertIn('`System: ${formatPercent(host.cpu_percent)}/${formatPercent(host.memory_percent)}/${formatPercent(host.disk_busy_percent)}`', source)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --python 3.13 --with-requirements requirements-web.txt --with pytest --with httpx2 pytest tests/test_web_ui_integrity.py -q -k "stacks_latency"`

Expected: FAIL because `header-status-stack` and compact rendering do not exist.

- [ ] **Step 3: Commit the regression test**

```powershell
git add tests/test_web_ui_integrity.py
git commit -m "test: cover compact header status stack"
```

### Task 2: Implement the compact status stack

**Files:**
- Modify: `picorgftp_sql/web/static/index.html:17-58`
- Modify: `picorgftp_sql/web/static/app.css:167-223,3620-3722`
- Modify: `picorgftp_sql/web/static/app.js:5731-5742`
- Test: `tests/test_web_ui_integrity.py`

**Interfaces:**
- Consumes: existing `backendHealthStatus`, `resourceStatus`, and their detail popovers.
- Produces: `header-status-stack` with the latency indicator before the resource indicator and compact host-only resource text.

- [ ] **Step 1: Move the existing controls into a stack**

```html
<div class="header-status-stack">
  <div class="backend-health-indicator">…</div>
  <div class="resource-status-indicator">…</div>
</div>
```

- [ ] **Step 2: Use a desktop vertical stack and a narrow-screen fallback**

```css
.header-status-stack {
  display: grid;
  justify-items: start;
  gap: 4px;
}

.resource-status {
  max-width: 220px;
}
```

Place the stack beside `.topbar-brand-info`; at the existing narrow breakpoint, place it below the application information rather than beside the navigation.

- [ ] **Step 3: Render only host CPU, RAM and disk values in the visible pill**

```js
resourceStatusText.textContent =
  `System: ${formatPercent(host.cpu_percent)}/${formatPercent(host.memory_percent)}/${formatPercent(host.disk_busy_percent)}`;
```

- [ ] **Step 4: Run the focused test to verify it passes**

Run: `uv run --python 3.13 --with-requirements requirements-web.txt --with pytest --with httpx2 pytest tests/test_web_ui_integrity.py -q -k "stacks_latency"`

Expected: PASS.

- [ ] **Step 5: Run related regression tests**

Run: `uv run --python 3.13 --with-requirements requirements-web.txt --with pytest --with httpx2 pytest tests/test_web_ui_integrity.py tests/test_source_integrity.py -q`

Expected: PASS.

- [ ] **Step 6: Commit implementation**

```powershell
git add picorgftp_sql/web/static/index.html picorgftp_sql/web/static/app.css picorgftp_sql/web/static/app.js tests/test_web_ui_integrity.py
git commit -m "fix: stack compact header statuses"
```
