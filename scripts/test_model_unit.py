#!/usr/bin/env python3
"""
Unit test for services/triton-models/glm_ocr/1/model.py

Runs entirely in-process with IDEP_MOCK_INFERENCE=true — no GPU, no Docker,
no model download.  Validates the new GLM-OCR output schema:
  pages[].elements[].bbox_2d   [x1, y1, x2, y2]
  markdown                     aggregated markdown string
  extract_fields / fields      selective field extraction
  precision_mode               "high" adds .words[] to elements
"""
from __future__ import annotations
import sys, os, json, types, traceback

# ─── Redirect to repo root ────────────────────────────────────────────────────
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

# ─── Force mock mode before import ───────────────────────────────────────────
os.environ["IDEP_MOCK_INFERENCE"] = "true"
os.environ["IDEP_STRICT_REAL"]    = "false"
os.environ["GLM_MODEL_PATH"]      = "zai-org/GLM-OCR"

# ─── Stub triton_python_backend_utils so model.py loads without Triton ───────
_pb = types.ModuleType("triton_python_backend_utils")

class _FakeTensor:
    def __init__(self, name, data): self._name = name; self._data = data
    def as_numpy(self): import numpy as np; return np.array(self._data, dtype=object)

class _FakeRequest:
    def __init__(self, **tensors): self._t = tensors
    def get_input_tensor_by_name(self, name): return self._t.get(name)

def _get_input_tensor_by_name(req, name): return req._t.get(name)

_pb.get_input_tensor_by_name = _get_input_tensor_by_name
_pb.Tensor                   = lambda name, arr: (name, arr)
_pb.TritonError               = Exception

class _FakeResp:
    def __init__(self, output_tensors=None, error=None):
        self.output_tensors = output_tensors or []
        self.error = error

_pb.InferenceResponse = _FakeResp
sys.modules["triton_python_backend_utils"] = _pb

# ─── Load model.py ────────────────────────────────────────────────────────────
MODEL_PY = os.path.join(ROOT, "services", "triton-models", "glm_ocr", "1", "model.py")
import importlib.util
spec = importlib.util.spec_from_file_location("model", MODEL_PY)
model_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model_mod)

# ─── Helpers ──────────────────────────────────────────────────────────────────
_pass = 0
_fail = 0
_results: list[tuple] = []

def check(name: str, expr: bool, detail: str = ""):
    global _pass, _fail
    ok = bool(expr)
    mark = "✅ PASS" if ok else "❌ FAIL"
    suffix = f"  ({detail})" if detail and not ok else ""
    print(f"  {mark}  {name}{suffix}")
    _results.append((ok, name))
    if ok: _pass += 1
    else:  _fail += 1

def section(title: str):
    print(f"\n{'─'*62}\n  {title}\n{'─'*62}")

# ─── Bootstrap TritonPythonModel ──────────────────────────────────────────────
m = model_mod.TritonPythonModel()
m.initialize({"model_instance_name": "glm_ocr_0",
               "model_repository": "/models",
               "model_version":    "1"})

def infer(output_format="text", options: dict | None = None, precision_mode=""):
    """Helper: build a minimal fake Triton request and call execute()."""
    import numpy as np
    opts = {"output_format": output_format, **(options or {})}
    tensors = {
        "images":  _FakeTensor("images",  [b"/tmp/idep/test.png"]),
        "prompt":  _FakeTensor("prompt",  [b"Text Recognition:"]),
        "options": _FakeTensor("options", [json.dumps(opts).encode()]),
    }
    if precision_mode:
        tensors["precision_mode"] = _FakeTensor("precision_mode", [precision_mode.encode()])

    req = _FakeRequest(**tensors)
    resp = m.execute([req])[0]
    # resp.output_tensors is a list of (name, np.array) tuples
    raw_json = None
    for (name, arr) in resp.output_tensors:
        if name == "generated_text":
            raw_json = arr.flat[0]
            if isinstance(raw_json, bytes):
                raw_json = raw_json.decode()
            break
    assert raw_json, "No generated_text in response"
    return json.loads(raw_json)

# ══════════════════════════════════════════════════════════════════════════════
# TEST SUITE
# ══════════════════════════════════════════════════════════════════════════════

section("1 · Text extraction — base schema")
r = infer("text", {"include_coordinates": True})
check("top-level 'pages' present",           "pages"      in r)
check("top-level 'model' is zai-org/GLM-OCR", r.get("model") == "zai-org/GLM-OCR")
check("mode is 'mock'",                       r.get("mode") == "mock")
check("pages is non-empty list",              isinstance(r.get("pages"), list) and len(r["pages"]) > 0)
page0 = r["pages"][0] if r.get("pages") else {}
check("page[0] has 'elements'",               "elements" in page0)
els = page0.get("elements", [])
check("at least one element",                 len(els) > 0)
el0 = els[0] if els else {}
check("element has 'bbox_2d'",                "bbox_2d"  in el0)
check("bbox_2d has 4 values",                 len(el0.get("bbox_2d", [])) == 4)
check("bbox_2d x2 > x1  (absolute coords)",  el0.get("bbox_2d", [0,0,0,0])[2] > el0.get("bbox_2d", [0,0,1,0])[0])
check("element has 'label'",                  "label"   in el0)
check("element has 'content'",                "content" in el0)
check("confidence in [0,1]",                  0 <= r.get("confidence", -1) <= 1)

section("2 · Markdown output format")
r = infer("markdown")
check("'markdown' key present",               "markdown" in r)
check("markdown is non-empty string",         isinstance(r.get("markdown"), str) and len(r["markdown"]) > 10)
check("markdown contains heading",            "#" in r.get("markdown", ""))

section("3 · Table recognition")
r = infer("table", {"include_coordinates": True})
table_els = [e for e in r.get("pages", [{}])[0].get("elements", []) if e.get("label") == "table"]
check("at least one 'table' element",         len(table_els) > 0)
check("table element has 'bbox_2d'",           "bbox_2d" in (table_els[0] if table_els else {}))

section("4 · Formula recognition")
r = infer("formula")
check("pages present for formula",            "pages" in r)
form_els = [e for e in r.get("pages", [{}])[0].get("elements", []) if e.get("label") in ("formula", "text")]
check("formula/text elements returned",       len(form_els) > 0)

section("5 · Precision mode = high  (word-level bbox enrichment)")
r = infer("text", {"include_coordinates": True, "include_word_confidence": True}, precision_mode="high")
check("precision field is 'high'",            r.get("precision") == "high")
els_with_words = [e for e in r.get("pages", [{}])[0].get("elements", []) if e.get("words")]
check("at least one element has 'words'",     len(els_with_words) > 0)
if els_with_words:
    w0 = els_with_words[0]["words"][0]
    check("word entry has 'bbox_2d'",         "bbox_2d"    in w0)
    check("word entry has 'word' field",      "word"       in w0)
    check("word entry has 'confidence'",      "confidence" in w0)

section("6 · extract_fields filter (date, amount)")
r = infer("text", {"include_coordinates": True, "extract_fields": ["date", "amount"]})
check("'extract_fields' echoed in response",  "extract_fields" in r)
check("extract_fields echoes 'date'",         "date"   in (r.get("extract_fields") or []))
check("extract_fields echoes 'amount'",       "amount" in (r.get("extract_fields") or []))
check("pages still present after filter",     "pages" in r and len(r.get("pages", [])) > 0)

section("7 · Usage metadata")
r = infer("text")
u = r.get("usage", {})
check("usage.prompt_tokens present",      "prompt_tokens"     in u)
check("usage.completion_tokens present",  "completion_tokens" in u)
check("prompt_tokens > 0",                u.get("prompt_tokens", 0) > 0)

section("8 · finalize() cleans up without error")
try:
    m.finalize()
    check("finalize() ran without exception", True)
except Exception as e:
    check("finalize() ran without exception", False, str(e))

# ─── Summary ──────────────────────────────────────────────────────────────────
total = _pass + _fail
print(f"\n{'═'*62}")
print(f"  Passed {_pass} / {total}")
if _fail:
    print(f"  {_fail} FAILED:")
    for ok, name in _results:
        if not ok: print(f"    ✗ {name}")
    sys.exit(1)
else:
    print("  All tests passed 🎉")
    sys.exit(0)
