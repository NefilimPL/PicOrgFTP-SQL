"""Tests for asynchronous desktop data loading."""

from dataclasses import FrozenInstanceError
import threading

import pytest

from picorgftp_sql import desktop_data_loader
from picorgftp_sql.desktop_data_loader import (
    DesktopDataLoader,
    DesktopDataSnapshot,
    load_desktop_data,
)


def test_loader_posts_result_through_scheduler():
    scheduled = []
    received = []
    errors = []
    loader = DesktopDataLoader(
        load=lambda: DesktopDataSnapshot(lists={"NAZWY": ["ALFA"]}, entries=()),
        schedule=lambda callback: scheduled.append(callback),
    )

    assert loader.start(
        on_success=lambda snapshot: received.append(snapshot),
        on_error=errors.append,
    )
    loader.join_for_test(timeout=1.0)

    assert received == []
    scheduled[0]()
    assert received[0].lists["NAZWY"] == ["ALFA"]


def test_loader_posts_error_through_scheduler():
    scheduled = []
    received = []
    failure = RuntimeError("data unavailable")

    def fail_load():
        raise failure

    loader = DesktopDataLoader(load=fail_load, schedule=scheduled.append)

    assert loader.start(on_success=received.append, on_error=received.append)
    loader.join_for_test(timeout=1.0)

    assert received == []
    assert len(scheduled) == 1
    scheduled[0]()
    assert received == [failure]


def test_loader_rejects_second_start_while_load_is_running():
    release_load = threading.Event()
    load_started = threading.Event()
    scheduled = []

    def slow_load():
        load_started.set()
        release_load.wait(timeout=1.0)
        return DesktopDataSnapshot(lists={}, entries=())

    loader = DesktopDataLoader(load=slow_load, schedule=scheduled.append)

    assert loader.start(on_success=lambda _snapshot: None, on_error=lambda _error: None)
    assert load_started.wait(timeout=1.0)
    assert not loader.start(
        on_success=lambda _snapshot: None,
        on_error=lambda _error: None,
    )

    release_load.set()
    loader.join_for_test(timeout=1.0)
    assert loader.start(on_success=lambda _snapshot: None, on_error=lambda _error: None)
    loader.join_for_test(timeout=1.0)


def test_load_desktop_data_returns_frozen_complete_snapshot(monkeypatch):
    payload = {
        "NAZWY": ["ALFA"],
        "ENTRIES": {"590": {"NAZWA": "ALFA"}},
        "__ENTRY_RECORDS__": [{"EAN": "590", "NAZWA": "ALFA"}],
    }
    monkeypatch.setattr(desktop_data_loader, "prepare_excel_lists", lambda: payload)

    snapshot = load_desktop_data()

    assert snapshot.lists is payload
    assert snapshot.entries == ({"EAN": "590", "NAZWA": "ALFA"},)
    with pytest.raises(FrozenInstanceError):
        snapshot.entries = ()
