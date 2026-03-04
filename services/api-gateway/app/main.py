from datetime import datetime
from threading import Lock, Thread
from typing import Dict, Any
import uuid

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn


jobs: Dict[str, Dict[str, Any]] = {}
jobs_lock = Lock()

app = FastAPI(
    title="Intelligent Document Extraction Platform (IDEP) API",
    description="Enterprise-scale document content extraction using GLM-OCR and Temporal.io",
    version="1.0.0"
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "api-gateway"}


def _process_job(job_id: str, filename: str, content_type: str, file_bytes: bytes):
    with jobs_lock:
        if job_id not in jobs:
            return
        jobs[job_id]["status"] = "PROCESSING"
        jobs[job_id]["progress"] = 10

    try:
        extracted_text = ""

        lowered_name = filename.lower()
        if (
            content_type.startswith("text/")
            or lowered_name.endswith(".log")
            or lowered_name.endswith(".txt")
        ):
            extracted_text = file_bytes.decode("utf-8", errors="replace")
        else:
            raise ValueError(
                "Unsupported file type for Python fallback gateway. "
                "Use the Go API gateway for PDF/image OCR pipeline."
            )

        line_count = len(extracted_text.splitlines()) if extracted_text else 0
        word_count = len(extracted_text.split()) if extracted_text else 0

        result_payload = {
            "job_id": job_id,
            "filename": filename,
            "status": "COMPLETED",
            "model": "python-fallback-text-extractor",
            "processing_time_ms": 1,
            "document_confidence": 1.0,
            "page_count": 1,
            "result": {
                "raw_text": extracted_text,
                "line_count": line_count,
                "word_count": word_count,
                "document_type": "log_document" if lowered_name.endswith(".log") else "text_document",
            },
            "completed_at": datetime.utcnow().isoformat() + "Z",
        }

        with jobs_lock:
            if job_id in jobs:
                jobs[job_id]["status"] = "COMPLETED"
                jobs[job_id]["progress"] = 100
                jobs[job_id]["result"] = result_payload

    except Exception as exc:
        with jobs_lock:
            if job_id in jobs:
                jobs[job_id]["status"] = "FAILED"
                jobs[job_id]["progress"] = 100
                jobs[job_id]["error"] = str(exc)


@app.post("/jobs/upload")
async def upload_document(file: UploadFile = File(...)):
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Empty file uploaded")

    job_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat() + "Z"

    with jobs_lock:
        jobs[job_id] = {
            "job_id": job_id,
            "filename": file.filename,
            "status": "QUEUED",
            "progress": 0,
            "created_at": now,
            "result": None,
            "error": None,
        }

    worker = Thread(
        target=_process_job,
        args=(job_id, file.filename, file.content_type or "application/octet-stream", file_bytes),
        daemon=True,
    )
    worker.start()

    return {
        "job_id": job_id,
        "filename": file.filename,
        "status": "QUEUED",
        "result_url": f"/jobs/{job_id}/result",
        "status_url": f"/jobs/{job_id}",
    }


@app.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    response = {
        "job_id": job["job_id"],
        "filename": job["filename"],
        "status": job["status"],
        "progress": job["progress"],
        "created_at": job["created_at"],
    }
    if job.get("error"):
        response["error"] = job["error"]

    return response


@app.get("/jobs/{job_id}/result")
async def get_job_result(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["status"] != "COMPLETED":
        raise HTTPException(status_code=409, detail=f"Job not yet completed (status={job['status']})")

    return job["result"]

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
