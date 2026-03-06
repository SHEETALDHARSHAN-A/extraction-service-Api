import io
import json
import logging
import os
import shutil
import subprocess
from concurrent import futures
from pathlib import Path

import grpc

from archive_extractor import extract_archive, is_archive
from image_enhancer import process_directory

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp", ".tif"}
_TEXT_EXTENSIONS = {".txt", ".csv"}
_OFFICE_EXTENSIONS = {".docx", ".xlsx", ".pptx"}


class PreprocessRequest:
    def __init__(self, file_path="", job_id="", deskew=True, denoise=True):
        self.file_path = file_path
        self.job_id = job_id
        self.deskew = deskew
        self.denoise = denoise


class PreprocessResponse:
    def __init__(self, image_paths=None, status="success", error=""):
        self.image_paths = image_paths or []
        self.status = status
        self.error = error

    def to_bytes(self):
        return json.dumps(
            {
                "image_paths": self.image_paths,
                "status": self.status,
                "error": self.error,
            }
        ).encode("utf-8")


def _deserialize_preprocess_request(payload: bytes) -> PreprocessRequest:
    data = json.loads(payload.decode("utf-8")) if payload else {}
    return PreprocessRequest(
        file_path=data.get("file_path", data.get("FilePath", "")),
        job_id=data.get("job_id", data.get("JobId", "")),
        deskew=bool(data.get("deskew", data.get("Deskew", True))),
        denoise=bool(data.get("denoise", data.get("Denoise", True))),
    )


def _serialize_preprocess_response(response: PreprocessResponse) -> bytes:
    return response.to_bytes()


def _copy_file(src: str, dst: str) -> None:
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _convert_pdf_to_images(pdf_path: str, output_dir: str) -> list[str]:
    output_dir_path = Path(output_dir)
    prefix = output_dir_path / f"pdf_{Path(pdf_path).name}"
    cmd = ["pdftoppm", "-png", "-r", "300", pdf_path, str(prefix)]
    process = subprocess.run(cmd, capture_output=True, text=True)
    if process.returncode != 0:
        raise RuntimeError(f"pdftoppm failed: {process.stderr.strip()}")

    matches = sorted(output_dir_path.glob(f"{prefix.name}-*.png"))
    if not matches:
        matches = sorted(output_dir_path.glob(f"{prefix.name}*.png"))
    logger.info("Rendered %d pages from PDF", len(matches))
    return [str(path) for path in matches]


def _convert_office_to_images(file_path: str, output_dir: str) -> list[str]:
    cmd = ["libreoffice", "--headless", "--convert-to", "pdf", "--outdir", output_dir, file_path]
    process = subprocess.run(cmd, capture_output=True, text=True)
    if process.returncode != 0:
        raise RuntimeError(f"libreoffice failed: {process.stderr.strip()}")

    file_name = Path(file_path).stem
    pdf_path = Path(output_dir) / f"{file_name}.pdf"
    if not pdf_path.exists():
        raise RuntimeError(f"expected PDF not found: {pdf_path}")
    return _convert_pdf_to_images(str(pdf_path), output_dir)


def _convert_doc_to_images(file_path: str, output_dir: str) -> list[str]:
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext == ".pdf":
        return _convert_pdf_to_images(file_path, output_dir)
    if ext in _IMAGE_EXTENSIONS:
        destination = Path(output_dir) / path.name
        _copy_file(file_path, str(destination))
        return [str(destination)]
    if ext in _OFFICE_EXTENSIONS:
        return _convert_office_to_images(file_path, output_dir)
    if ext in _TEXT_EXTENSIONS:
        return [file_path]

    raise RuntimeError(f"unsupported file type: {ext}")


def _enhance_images(image_paths: list[str], output_dir: str, deskew: bool, denoise: bool) -> list[str]:
    stage_dir = Path(output_dir) / "stage"
    enhanced_dir = Path(output_dir) / "enhanced"
    stage_dir.mkdir(parents=True, exist_ok=True)
    enhanced_dir.mkdir(parents=True, exist_ok=True)

    for image_path in image_paths:
        ext = Path(image_path).suffix.lower()
        if ext in _TEXT_EXTENSIONS:
            continue
        _copy_file(image_path, str(stage_dir / Path(image_path).name))

    results = process_directory(str(stage_dir), str(enhanced_dir), mode="glm", deskew=deskew, denoise=denoise)
    failures = [item for item in results if item.get("status") != "success"]
    if failures:
        logger.warning("Some image enhancements failed, falling back to original images for those files")

    enhanced_images = sorted(
        str(path)
        for path in enhanced_dir.iterdir()
        if path.is_file() and path.suffix.lower() in _IMAGE_EXTENSIONS
    )
    return enhanced_images if enhanced_images else image_paths


class PreprocessingServiceServicer:
    def Preprocess(self, request: PreprocessRequest, _context):
        logger.info("Preprocessing request file=%s job=%s", request.file_path, request.job_id)

        try:
            if not request.file_path:
                return PreprocessResponse(status="error", error="file_path is required")
            if not Path(request.file_path).exists():
                return PreprocessResponse(status="error", error=f"file not found: {request.file_path}")

            output_dir = Path("/tmp/idep") / request.job_id
            output_dir.mkdir(parents=True, exist_ok=True)

            if is_archive(request.file_path):
                docs = extract_archive(request.file_path, str(output_dir / "archive_contents"))
                all_images = []
                for doc in docs:
                    try:
                        all_images.extend(_convert_doc_to_images(doc, str(output_dir)))
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("Skipping extracted file %s: %s", doc, exc)

                if not all_images:
                    return PreprocessResponse(status="error", error="No processable documents found in archive")

                enhanced = _enhance_images(all_images, str(output_dir), request.deskew, request.denoise)
                return PreprocessResponse(image_paths=enhanced, status="success")

            image_paths = _convert_doc_to_images(request.file_path, str(output_dir))
            enhanced = _enhance_images(image_paths, str(output_dir), request.deskew, request.denoise)
            return PreprocessResponse(image_paths=enhanced, status="success")

        except Exception as exc:  # noqa: BLE001
            logger.exception("Preprocessing failed for job=%s", request.job_id)
            return PreprocessResponse(status="error", error=str(exc))


def serve() -> None:
    port = os.getenv("PORT", "50051")
    max_workers = int(os.getenv("GRPC_MAX_WORKERS", "8"))

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
    servicer = PreprocessingServiceServicer()

    rpc_method_handlers = {
        "Preprocess": grpc.unary_unary_rpc_method_handler(
            servicer.Preprocess,
            request_deserializer=_deserialize_preprocess_request,
            response_serializer=_serialize_preprocess_response,
        )
    }
    generic_handler = grpc.method_handlers_generic_handler("preprocessing.PreprocessingService", rpc_method_handlers)
    server.add_generic_rpc_handlers((generic_handler,))

    server.add_insecure_port(f"[::]:{port}")
    logger.info("Preprocessing gRPC service listening on %s", port)
    server.start()
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
