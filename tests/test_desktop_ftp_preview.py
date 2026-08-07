from __future__ import annotations

from dataclasses import dataclass

from picorgftp_sql.desktop_ftp_preview import DesktopFtpPreviewController


@dataclass(frozen=True)
class PreviewResult:
    ean: str
    files: tuple[str, ...]


def preview_result(ean: str) -> PreviewResult:
    return PreviewResult(ean=ean, files=(f"{ean}_01.jpg",))


class ControlledDownloader:
    def __init__(self) -> None:
        self.requests: dict[int, tuple[str, object, object]] = {}

    def __call__(self, request_id, ean, cancel_event, complete) -> None:
        self.requests[request_id] = (ean, cancel_event, complete)

    def finish(self, request_id: int, result: PreviewResult) -> None:
        self.requests[request_id][2](result)


class FakeTempManager:
    def __init__(self) -> None:
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1


def test_preview_controller_publishes_only_latest_request() -> None:
    scheduled = []
    results = []
    errors = []
    downloader = ControlledDownloader()
    controller = DesktopFtpPreviewController(
        downloader=downloader,
        temp_manager=FakeTempManager(),
        schedule=scheduled.append,
    )

    first = controller.request("5901", on_success=results.append, on_error=errors.append)
    second = controller.request("5902", on_success=results.append, on_error=errors.append)
    downloader.finish(first, preview_result("5901"))
    downloader.finish(second, preview_result("5902"))
    for callback in scheduled:
        callback()

    assert [item.ean for item in results] == ["5902"]
    assert errors == []


def test_preview_controller_close_cancels_request_and_closes_temp_manager_once() -> None:
    downloader = ControlledDownloader()
    temp_manager = FakeTempManager()
    controller = DesktopFtpPreviewController(
        downloader=downloader,
        temp_manager=temp_manager,
        schedule=lambda _callback: None,
    )

    request_id = controller.request("5901", on_success=lambda _result: None, on_error=lambda _error: None)
    controller.close()
    controller.close()

    assert downloader.requests[request_id][1].is_set()
    assert temp_manager.close_calls == 1


def test_preview_controller_schedules_stale_request_cleanup() -> None:
    scheduled = []
    discarded = []
    downloader = ControlledDownloader()
    controller = DesktopFtpPreviewController(
        downloader=downloader,
        temp_manager=FakeTempManager(),
        schedule=scheduled.append,
    )

    first = controller.request(
        "5901",
        on_success=lambda _result: None,
        on_error=lambda _error: None,
        on_discard=discarded.append,
    )
    controller.request(
        "5902",
        on_success=lambda _result: None,
        on_error=lambda _error: None,
    )
    downloader.finish(first, preview_result("5901"))
    for callback in scheduled:
        callback()

    assert [item.ean for item in discarded] == ["5901"]
