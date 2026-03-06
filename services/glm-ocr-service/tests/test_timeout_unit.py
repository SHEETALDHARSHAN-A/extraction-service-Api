"""Unit tests for request timeout handling in FastAPI handlers."""

import asyncio
import base64
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from PIL import Image


def _image_b64() -> str:
    img = Image.new("RGB", (64, 64), color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


@pytest.mark.asyncio
async def test_extract_region_returns_504_on_timeout():
    from app.main import extract_region
    from app.models import RegionExtractionRequest

    mock_engine = MagicMock()
    mock_engine.is_ready.return_value = True
    mock_engine.device = "cuda"

    req = {
        "image": _image_b64(),
        "region_type": "text",
        "options": {"max_tokens": 1024},
    }

    request_model = RegionExtractionRequest(**req)
    request_ctx = SimpleNamespace(state=SimpleNamespace(request_id="unit-timeout", trace_id=""))

    with patch("app.main.settings.use_isolated_gpu_executor", False), patch("app.main.inference_engine", mock_engine), patch(
        "app.main._extract_with_timeout", new=AsyncMock(side_effect=asyncio.TimeoutError())
    ):
        with pytest.raises(HTTPException) as exc:
            await extract_region(request_model, request_ctx)

    assert exc.value.status_code == 504
    assert "timeout" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_extract_region_returns_503_on_cuda_oom():
    from app.main import extract_region
    from app.models import RegionExtractionRequest

    mock_engine = MagicMock()
    mock_engine.is_ready.return_value = True
    mock_engine.device = "cuda"

    req = {
        "image": _image_b64(),
        "region_type": "text",
        "options": {"max_tokens": 1024},
    }

    request_model = RegionExtractionRequest(**req)
    request_ctx = SimpleNamespace(state=SimpleNamespace(request_id="unit-oom", trace_id=""))

    with patch("app.main.settings.use_isolated_gpu_executor", False), patch("app.main.inference_engine", mock_engine), patch(
        "app.main._extract_with_timeout", new=AsyncMock(side_effect=RuntimeError("CUDA out of memory"))
    ), patch("torch.cuda.is_available", return_value=True):
        with pytest.raises(HTTPException) as exc:
            await extract_region(request_model, request_ctx)

    assert exc.value.status_code == 503
    assert "gpu memory" in str(exc.value.detail).lower()
