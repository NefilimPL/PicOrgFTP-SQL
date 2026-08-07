from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_process_router_delegates_job_queries_and_cancellation() -> None:
    from picorgftp_sql.web.process_api import ProcessApiDependencies, build_process_router

    app = FastAPI()
    app.include_router(
        build_process_router(
            ProcessApiDependencies(
                current_user=lambda _request: "alice",
                jobs_for_user=lambda username, limit: [{"id": "one", "owner": username, "limit": limit}],
                active_jobs=lambda: {"jobs": [{"id": "one"}]},
                job_for_user=lambda job_id, username: {"id": job_id, "owner": username},
                cancel_job=lambda job_id, username: {"id": job_id, "owner": username},
            )
        )
    )
    client = TestClient(app)

    assert client.get("/api/process-jobs?limit=5").json() == {
        "jobs": [{"id": "one", "owner": "alice", "limit": 5}]
    }
    assert client.get("/api/process-jobs/active").json() == {"jobs": [{"id": "one"}]}
    assert client.get("/api/process-jobs/one").json() == {"id": "one", "owner": "alice"}
    assert client.delete("/api/process-jobs/one").json() == {
        "cancelled": True,
        "job": {"id": "one", "owner": "alice"},
    }
