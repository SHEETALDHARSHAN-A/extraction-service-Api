"""Unit tests for chunking and merge behavior in GLM inference engine."""

from PIL import Image

from app.glm_inference import GLMInferenceEngine
from app.config import settings


def _engine_without_model(device: str = "cuda") -> GLMInferenceEngine:
    engine = GLMInferenceEngine.__new__(GLMInferenceEngine)
    engine.device = device
    return engine


def test_split_into_vertical_segments_count_and_overlap():
    engine = _engine_without_model()
    image = Image.new("RGB", (1000, 3000), color="white")

    segments = engine._split_into_vertical_segments(image, segment_count=3, overlap_px=120)

    assert len(segments) == 3
    heights = [seg.size[1] for seg in segments]
    assert all(h > 1000 for h in heights)  # overlap increases segment size


def test_merge_chunk_contents_deduplicates_overlap_lines():
    engine = _engine_without_model()

    merged = engine._merge_chunk_contents([
        "Header\nLine A\nLine B",
        "Header\nLine B\nLine C",
        "Line C\nLine D",
    ])

    lines = merged.splitlines()
    assert lines.count("Header") == 1
    assert lines.count("Line B") == 1
    assert lines.count("Line C") == 1
    assert "Line D" in lines


def test_should_chunk_image_when_large_and_cuda(monkeypatch):
    engine = _engine_without_model(device="cuda")
    image = Image.new("RGB", (1200, 1800), color="white")

    monkeypatch.setattr(settings, "chunk_large_pages", True)
    monkeypatch.setattr(settings, "chunk_trigger_max_edge", 1400)

    assert engine._should_chunk_image(image) is True


def test_should_not_chunk_when_cpu(monkeypatch):
    engine = _engine_without_model(device="cpu")
    image = Image.new("RGB", (2000, 2000), color="white")

    monkeypatch.setattr(settings, "chunk_large_pages", True)
    monkeypatch.setattr(settings, "chunk_trigger_max_edge", 1400)

    assert engine._should_chunk_image(image) is False
