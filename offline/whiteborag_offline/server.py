"""The offline server: photo uploads from the ESP32, the ingest worker, the query API and the chat page.

Run: uv run --directory offline python -m whiteborag_offline.server
"""

import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from ingest.events import CAPTURE_PREFIX, LOCAL_TZ, parse_key
from ingest.ulid import new_ulid
from query.handler import handle

from whiteborag_offline import REPO_DIR
from whiteborag_offline.config import DEFAULT_CONFIG, Config, load_config
from whiteborag_offline.deps import QUERY_KEY_ID, Runtime, open_runtime, query_deps
from whiteborag_offline.jobs import JobQueue
from whiteborag_offline.worker import Worker

MAX_PHOTO_BYTES = 5 * 1024 * 1024  # a UXGA JPEG from the ESP32-CAM is well under 1 MB
JPEG_MAGIC = b"\xff\xd8"
FRONTEND_DIR = REPO_DIR / "aws" / "frontend"
CONFIG_JS = f'window.WHITEBORAG = {{apiUrl: location.origin, apiKey: "{QUERY_KEY_ID}"}};\n'


def _today() -> str:
    return datetime.now(LOCAL_TZ).strftime("%Y-%m-%d")


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
        declared = request.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > MAX_PHOTO_BYTES:  # refuse before reading it all in
            return JSONResponse({"error": "photo too large"}, status_code=400)
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
        print(json.dumps({"captured": key, "trigger": request.headers.get("x-trigger", ""), "job": job_id}),
              flush=True)
        return JSONResponse({"capture_id": capture_id, "key": key, "job_id": job_id}, status_code=201)

    @app.get("/jobs")
    def jobs(limit: int = 50):
        return queue.recent(limit)

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.post("/query")
    async def post_query(request: Request):
        # Same origin only: requiring JSON makes a cross-site browser send a preflight, and the CORS headers
        # the shared handler adds are dropped below, so no other website can run a query or read the answer.
        if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
            return JSONResponse({"error": "send the question as application/json"}, status_code=415)
        # The shared handler takes an API Gateway proxy event and returns a proxy response.
        event = {"body": (await request.body()).decode("utf-8", "replace"),
                 "requestContext": {"identity": {"apiKeyId": QUERY_KEY_ID}}}
        deps = query_deps(rt, str(request.base_url))
        resp = await run_in_threadpool(handle, event, deps, _today)  # model calls are slow and blocking
        headers = {k: v for k, v in resp["headers"].items() if not k.lower().startswith("access-control-")}
        return Response(resp["body"], status_code=resp["statusCode"], headers=headers)

    @app.get("/photos/{key:path}")
    def photo(key: str):
        if not key.startswith(CAPTURE_PREFIX):
            raise HTTPException(404)
        try:
            path = rt.blobs.path_for(key)
        except ValueError:
            raise HTTPException(404)
        if not path.is_file():
            raise HTTPException(404)
        return FileResponse(path, media_type="image/jpeg")

    @app.get("/config.js")
    def config_js():
        return Response(CONFIG_JS, media_type="application/javascript")

    # Registered last so the routes above win; the chat page itself is the AWS one, unchanged.
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
    return app


def main(config_path: Path = DEFAULT_CONFIG, example: Path | None = None) -> None:
    cfg = load_config(config_path, example) if example else load_config(config_path)
    uvicorn.run(create_app(cfg), host=cfg.host, port=cfg.port)


if __name__ == "__main__":
    main()
