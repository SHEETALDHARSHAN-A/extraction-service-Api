from __future__ import annotations

import json
import random
from flask import Flask, jsonify, request

app = Flask(__name__)


def _find_input(inputs, name: str):
    for entry in inputs or []:
        if entry.get("name") == name:
            data = entry.get("data") or []
            return data[0] if data else ""
    return ""


def _mock_elements(include_coordinates: bool, include_word_confidence: bool, extract_fields: list[str]):
    elements = [
        {
            "index": 1,
            "label": "text",
            "content": "Invoice Date: 2026-02-25",
            "bbox_2d": [96, 102, 332, 128] if include_coordinates else None,
            "confidence": 0.97,
        },
        {
            "index": 2,
            "label": "text",
            "content": "Total Amount: $1,358.02",
            "bbox_2d": [96, 134, 386, 160] if include_coordinates else None,
            "confidence": 0.96,
        },
        {
            "index": 3,
            "label": "table",
            "content": "| Item | Qty | Price |",
            "bbox_2d": [80, 300, 540, 420] if include_coordinates else None,
            "confidence": 0.95,
        },
    ]

    if include_word_confidence:
        for el in elements:
            if el.get("bbox_2d"):
                x1, y1, x2, y2 = el["bbox_2d"]
                el["words"] = [
                    {"word": "sample", "bbox_2d": [x1, y1, x1 + 30, y2], "confidence": 0.94}
                ]

    if extract_fields:
        fset = {f.lower().strip() for f in extract_fields if f}
        keep = []
        for el in elements:
            text = (el.get("content") or "").lower()
            if ("date" in fset and "date" in text) or ("amount" in fset and "amount" in text):
                keep.append(el)
        elements = keep

    return elements


@app.get("/v2/health/ready")
def ready():
    return "OK", 200


@app.get("/v2/models/glm_ocr")
def model_meta():
    return jsonify(
        {
            "name": "glm_ocr",
            "platform": "mock-triton-python",
            "outputs": [{"name": "generated_text"}, {"name": "confidence"}],
        }
    )


@app.post("/v2/models/glm_ocr/infer")
def infer():
    payload = request.get_json(force=True, silent=True) or {}
    inputs = payload.get("inputs", [])

    prompt = str(_find_input(inputs, "prompt") or "Text Recognition:")
    options_raw = _find_input(inputs, "options") or "{}"
    precision_mode = str(_find_input(inputs, "precision_mode") or "normal").lower()

    try:
        options = json.loads(options_raw) if isinstance(options_raw, str) else {}
    except json.JSONDecodeError:
        options = {}

    output_format = str(options.get("output_format") or "text").lower().strip()
    include_coordinates = bool(options.get("include_coordinates"))
    include_word_confidence = bool(options.get("include_word_confidence"))
    extract_fields = options.get("extract_fields") or []
    if isinstance(extract_fields, str):
        extract_fields = [s.strip() for s in extract_fields.split(",") if s.strip()]

    elements = _mock_elements(
        include_coordinates=include_coordinates,
        include_word_confidence=(include_word_confidence or precision_mode == "high"),
        extract_fields=extract_fields,
    )

    markdown = "# Mock OCR\n\n- Invoice Date: 2026-02-25\n- Total Amount: $1,358.02\n"
    result = {
        "model": "zai-org/GLM-OCR",
        "mode": "mock",
        "precision": precision_mode,
        "prompt": prompt,
        "extract_fields": extract_fields,
        "pages": [
            {
                "page": 1,
                "width": 612,
                "height": 792,
                "elements": elements,
            }
        ],
        "markdown": markdown if output_format == "markdown" else markdown,
        "fields": {
            "date": "2026-02-25",
            "amount": "$1,358.02",
        } if extract_fields else {},
        "confidence": round(random.uniform(0.92, 0.98), 3),
        "usage": {"prompt_tokens": 42, "completion_tokens": 220},
    }

    out = {
        "model_name": "glm_ocr",
        "model_version": "1",
        "outputs": [
            {"name": "generated_text", "datatype": "BYTES", "shape": [1], "data": [json.dumps(result)]},
            {"name": "confidence", "datatype": "FP32", "shape": [1], "data": [result["confidence"]]},
        ],
    }
    return jsonify(out)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
