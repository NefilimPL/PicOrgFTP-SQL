"""Process-job query routes with explicit application dependencies."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, HTTPException, Request


@dataclass(frozen=True)
class ProcessApiDependencies:
    current_user: Callable[[Request], str]
    jobs_for_user: Callable[[str, int], list[dict[str, Any]]]
    active_jobs: Callable[[], dict[str, Any]]
    job_for_user: Callable[[str, str], dict[str, Any] | None]
    cancel_job: Callable[[str, str], dict[str, Any] | None]


def build_process_router(dependencies: ProcessApiDependencies) -> APIRouter:
    router = APIRouter()

    @router.get("/api/process-jobs")
    def process_jobs(request: Request, limit: int = 20) -> dict[str, Any]:
        return {"jobs": dependencies.jobs_for_user(dependencies.current_user(request), limit)}

    @router.get("/api/process-jobs/active")
    def active_process_jobs(request: Request) -> dict[str, Any]:
        dependencies.current_user(request)
        return dependencies.active_jobs()

    @router.get("/api/process-jobs/{job_id}")
    def process_job(request: Request, job_id: str) -> dict[str, Any]:
        job = dependencies.job_for_user(job_id, dependencies.current_user(request))
        if not job:
            raise HTTPException(status_code=404, detail="Nie znaleziono zadania.")
        return job

    @router.delete("/api/process-jobs/{job_id}")
    def cancel_process_job(request: Request, job_id: str) -> dict[str, Any]:
        job = dependencies.cancel_job(job_id, dependencies.current_user(request))
        if not job:
            raise HTTPException(
                status_code=409,
                detail="Zadanie nie oczekuje juz w kolejce ani nie jest uruchomione.",
            )
        return {"cancelled": True, "job": job}

    return router
