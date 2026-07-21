# Pimcore Failure Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Include a safe, actionable diagnostic attachment in failed manual Pimcore create/update incident mail without exposing tracebacks in normal mail bodies or public API.

**Architecture:** The manual PIMcore wrappers retain a caught exception until their finally block and pass it to the existing integration-event helper. The helper adds the existing observability exception fields and a fixed recommendation only for status failed. Observability and NotificationService continue to perform redaction, bounding, persistence, and attachment delivery.

**Tech Stack:** Python 3.14, existing observability event pipeline, NotificationService, pytest.

## Global Constraints

- The ordinary send_test_message connection test and the five-scenario mail test suite remain unchanged.
- Only failed manual Pimcore create/update events receive the exception object and a recommended action.
- The normal subject, text body, HTML body, and public API never contain raw traceback text.
- The existing 24 KiB bounded/redacted attachment path remains the only mail diagnostic surface.
- PimcoreConflictError behavior remains unchanged: status conflict, no exception attachment, and re-raise.
- No new persistence schema, API response field, or mail transport behavior is introduced.

---

### Task 1: Propagate manual-update failures to observability

**Files:**
- Modify: picorgftp_sql/web_data.py:2382-2416,2554-2636
- Modify: tests/test_pimcore_web.py:740-900

**Interfaces:**
- Produces: _emit_pimcore_integration_event(..., failure: BaseException | None = None) -> None.
- Consumes: the caught RuntimeError from update_pimcore_product.
- Produces: emit_event keyword arguments exception and recommended_action only when status equals failed.

- [ ] **Step 1: Write the failing update test**

Add this test beside test_update_adapter_persists_manual_update_audit:

    def test_failed_manual_update_emits_actionable_exception_event() -> None:
        cfg = json.loads(json.dumps(web_data.config.DEFAULT_CONFIG))
        cfg["pimcore"].update({"enabled": True, "setup_complete": True})
        failure = RuntimeError("Pimcore rejected the update")
        with (
            patch.object(web_data.config, "CONFIG", cfg),
            patch.object(web_data, "update_product", side_effect=failure),
            patch.object(web_data, "_persist_pimcore_operation") as persist,
            patch.object(web_data, "_persist_pimcore_submission"),
            patch.object(web_data, "emit_event") as emit_event,
        ):
            with pytest.raises(RuntimeError, match="rejected"):
                web_data.update_pimcore_product(
                    91, "100", {"EAN": "5904804578169"}, "operator"
                )

        report = persist.call_args.args[0]
        pimcore_call = next(
            call
            for call in emit_event.call_args_list
            if call.kwargs["event_type"] == "integration.pimcore.completed"
        )
        assert report["status"] == "failed"
        assert pimcore_call.kwargs["severity"] == "error"
        assert pimcore_call.kwargs["exception"] is failure
        assert pimcore_call.kwargs["recommended_action"] == (
            "Otworz historie operacji Pimcore dla tego EAN i sprawdz "
            "zredagowany zalacznik diagnostyczny."
        )

- [ ] **Step 2: Verify RED**

Run:

    python -m pytest tests/test_pimcore_web.py::test_failed_manual_update_emits_actionable_exception_event -q --basetemp=pytest-pimcore-diagnostics-red-update

Expected: FAIL because the existing helper does not accept or forward exception and recommended_action.

- [ ] **Step 3: Implement the minimal update path**

In picorgftp_sql/web_data.py extend the helper signature and its emit_event call:

    def _emit_pimcore_integration_event(
        result: dict[str, object],
        *,
        status: str,
        operation_type: str,
        username: str,
        job_id: str,
        ean: object,
        elapsed_ms: int,
        failure: BaseException | None = None,
    ) -> None:
        ...
        recommended_action = (
            "Otworz historie operacji Pimcore dla tego EAN i sprawdz "
            "zredagowany zalacznik diagnostyczny."
            if status == "failed"
            else ""
        )
        emit_event(
            severity="error" if status == "failed" else "info",
            event_type="integration.pimcore.completed",
            ...
            recommended_action=recommended_action,
            details={...},
            exception=failure if status == "failed" else None,
        )

In update_pimcore_product initialize failure: BaseException | None = None before try. In the generic exception handler assign failure = exc before emit and re-raise. Pass failure=failure from the finally-block helper call. Do not set failure in the PimcoreConflictError branch.

- [ ] **Step 4: Verify GREEN**

Run:

    python -m pytest tests/test_pimcore_web.py::test_failed_manual_update_emits_actionable_exception_event tests/test_observability.py::test_emit_event_captures_exception_with_bounded_traceback -q --basetemp=pytest-pimcore-diagnostics-green-update

Expected: PASS.

- [ ] **Step 5: Commit**

    git add picorgftp_sql/web_data.py tests/test_pimcore_web.py
    git commit -m "feat: add Pimcore update failure diagnostics"

### Task 2: Cover manual-create parity and the safe mail boundary

**Files:**
- Modify: picorgftp_sql/web_data.py:2418-2489
- Modify: tests/test_pimcore_web.py
- Verify: tests/test_notification_service.py
- Verify: tests/test_observability.py

**Interfaces:**
- Consumes: the optional failure parameter from _emit_pimcore_integration_event.
- Produces: identical failed-event diagnostics for create_pimcore_product and update_pimcore_product.
- Preserves: conflict behavior and normal mail-body redaction.

- [ ] **Step 1: Write the failing create test**

Add a create counterpart that patches create_product to raise a RuntimeError with an Authorization Bearer sentinel:

    def test_failed_manual_create_emits_redacted_attachment_eligible_event() -> None:
        cfg = json.loads(json.dumps(web_data.config.DEFAULT_CONFIG))
        cfg["pimcore"].update({"enabled": True, "setup_complete": True})
        failure = RuntimeError("Authorization: Bearer PIMCORE_CREATE_SENTINEL")
        with (
            patch.object(web_data.config, "CONFIG", cfg),
            patch.object(web_data, "create_product", side_effect=failure),
            patch.object(web_data, "_persist_pimcore_operation"),
            patch.object(web_data, "_persist_pimcore_submission"),
            patch.object(web_data, "emit_event") as emit_event,
        ):
            with pytest.raises(RuntimeError, match="Authorization"):
                web_data.create_pimcore_product(
                    {"EAN": "5904804578169"}, "operator"
                )

        pimcore_call = next(
            call
            for call in emit_event.call_args_list
            if call.kwargs["event_type"] == "integration.pimcore.completed"
        )
        assert pimcore_call.kwargs["exception"] is failure
        assert pimcore_call.kwargs["recommended_action"]
        assert pimcore_call.kwargs["severity"] == "error"

- [ ] **Step 2: Verify RED**

Run:

    python -m pytest tests/test_pimcore_web.py::test_failed_manual_create_emits_redacted_attachment_eligible_event -q --basetemp=pytest-pimcore-diagnostics-red-create

Expected: FAIL because create_pimcore_product still drops the caught exception before its final integration event.

- [ ] **Step 3: Implement create parity**

In create_pimcore_product initialize failure: BaseException | None = None before try. In its existing generic exception block assign failure = exc before recording the finish event and re-raising. Pass failure=failure in the existing final _emit_pimcore_integration_event call. Do not add exception text to result, report summary, mail subject, text body, or HTML body.

- [ ] **Step 4: Verify GREEN and the boundary**

Run:

    python -m pytest tests/test_pimcore_web.py::test_failed_manual_create_emits_redacted_attachment_eligible_event tests/test_pimcore_web.py::test_failed_manual_update_emits_actionable_exception_event tests/test_observability.py::test_emit_event_captures_exception_with_bounded_traceback tests/test_notification_service.py::test_error_exception_is_sent_as_bounded_redacted_text_attachment -q --basetemp=pytest-pimcore-diagnostics-green-boundary

Expected: PASS. The existing notification test proves a qualifying event yields a bounded/redacted attachment and keeps exception text out of normal mail bodies.

- [ ] **Step 5: Commit**

    git add picorgftp_sql/web_data.py tests/test_pimcore_web.py
    git commit -m "feat: add Pimcore create failure diagnostics"

### Task 3: Run regressions and verify no API/mail regression

**Files:**
- Verify: picorgftp_sql/web_data.py
- Verify: picorgftp_sql/observability.py
- Verify: picorgftp_sql/notification_service.py
- Verify: tests/test_pimcore_web.py
- Verify: tests/test_observability.py
- Verify: tests/test_notification_service.py
- Verify: tests/test_observability_api.py
- Verify: tests/test_web_smoke_ci.py

- [ ] **Step 1: Run focused regressions**

Run:

    python -m pytest tests/test_pimcore_web.py tests/test_observability.py tests/test_notification_service.py tests/test_observability_api.py tests/test_web_smoke_ci.py -q --basetemp=pytest-pimcore-diagnostics-focused

Expected: PASS. This proves the failure event, redacted traceback handling, attachment boundary, and public API projection remain compatible.

- [ ] **Step 2: Run static checks**

Run:

    python -m compileall -q picorgftp_sql
    git diff --check

Expected: both commands exit 0.

- [ ] **Step 3: Run full suite**

Run:

    python -m pytest -q --basetemp=pytest-pimcore-diagnostics-full

Expected: PASS.

- [ ] **Step 4: Inspect state and clean generated directories**

Resolve and inspect the exact absolute paths for pytest-pimcore-diagnostics-red-update, pytest-pimcore-diagnostics-green-update, pytest-pimcore-diagnostics-red-create, pytest-pimcore-diagnostics-green-boundary, pytest-pimcore-diagnostics-focused, and pytest-pimcore-diagnostics-full. Remove only those directories after verification. Do not remove picorgftp_sql.sqlite, any broad pytest parent, user data, or files outside the workspace.

Run:

    git status --short
    git log --oneline -6

Expected: only intended commits plus any pre-existing preserved local database file. Do not push, merge, reset, or discard work.
