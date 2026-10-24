"""The offline server: photo uploads from the ESP32, the ingest worker, the query API and the chat page.

Run: uv run --directory offline python -m whiteborag_offline.server
"""

from contextlib import asynccontextmanager
from datetime import UTC, datetime

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ingest.events import parse_key
from ingest.ulid import new_ulid

from whiteborag_offline.config import Config, load_config
from whiteborag_offline.deps import Runtime, open_runtime
from whiteborag_offline.jobs import JobQueue
from whiteborag_offline.worker import Worker

MAX_PHOTO_BYTES = 5 * 1024 * 1024  # a UXGA JPEG from the ESP32-CAM is well under 1 MB
JPEG_MAGIC = b"\xff\xd8"


def capture_key(device: str, at: datetime) -> tuple[str, str]:
    """A key in the shape ingest parses: captures/<device>/YYYY/MM/DD/<stamp>_<ulid>.jpg."""
    capture_id = new_ulid(int(at.timestamp() * 1000))
    return f"captures/{device}/{at:%Y/%m/%d}/{at:%Y%m%dT%H%M%SZ}_{capture_id}.jpg", capture_id


def create_app(cfg: Config, rt: Runtime | None = None, start_worker: bool = True) -> FastAPI:
    rt = rt or open_runtime(cfg)
    queue = JobQueue(rt.db_path)
    worker = Worker(rt, queue)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if start_worker:
            worker.start()
        yield
        if start_worker:
            worker.stop()

    app = FastAPI(title="WhiteBoRAG offline", lifespan=lifespan)
    app.state.rt, app.state.queue, app.state.worker = rt, queue, worker

    @app.post("/captures")
    async def post_capture(request: Request):
        device = cfg.devices.get(request.headers.get("x-device-key", ""))
        if device is None:
            return JSONResponse({"error": "forbidden"}, status_code=403)
        body = await request.body()
        if not body.startswith(JPEG_MAGIC):
            return JSONResponse({"error": "body must be a JPEG"}, status_code=400)
        if len(body) > MAX_PHOTO_BYTES:
            return JSONResponse({"error": "photo too large"}, status_code=400)
        key, capture_id = capture_key(device, datetime.now(UTC))
        if parse_key(key) is None:
            return JSONResponse({"error": f"device id {device!r} can't be used in a capture key"}, status_code=500)
        rt.blobs.put_bytes(key, body)
        job_id = queue.enqueue(key)
        print(f'{{"captured": "{key}", "trigger": "{request.headers.get("x-trigger", "")}", "job": {job_id}}}',
              flush=True)
        return JSONResponse({"capture_id": capture_id, "key": key, "job_id": job_id}, status_code=201)

    @app.get("/jobs")
    def jobs(limit: int = 50):
        return queue.recent(limit)

    @app.get("/health")
    def health():
        return {"ok": True}

    return app


def main() -> None:
    cfg = load_config()
    uvicorn.run(create_app(cfg), host=cfg.host, port=cfg.port)


if __name__ == "__main__":
    main()
