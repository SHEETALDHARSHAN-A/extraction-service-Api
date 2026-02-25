from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os

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

@app.post("/jobs/upload")
async def upload_document(file: UploadFile = File(...)):
    # Placeholder for document ingestion logic
    return {
        "job_id": "placeholder-id",
        "filename": file.filename,
        "status": "received"
    }

@app.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    # Placeholder for status checking logic
    return {
        "job_id": job_id,
        "status": "processing",
        "progress": 50
    }

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
