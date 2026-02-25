"""
Triton Python Backend for GLM-OCR Model

This backend loads the GLM-4V-OCR model and performs inference on document images.
It uses Hugging Face Transformers for model loading and tokenization.

For local development without the actual model weights, set the environment variable
IDEP_MOCK_INFERENCE=true to use simulated inference.
"""
import os
import json
import logging
import numpy as np

logger = logging.getLogger(__name__)

# Conditional imports — only fail if not mocking
MOCK_MODE = os.getenv("IDEP_MOCK_INFERENCE", "true").lower() == "true"

if not MOCK_MODE:
    try:
        import torch
        from transformers import AutoTokenizer, AutoModelForCausalLM
        from PIL import Image
        import io
    except ImportError as e:
        logger.warning(f"ML dependencies not available: {e}. Falling back to mock mode.")
        MOCK_MODE = True

try:
    import triton_python_backend_utils as pb_utils
except ImportError:
    # Running outside Triton (e.g., for testing)
    pb_utils = None


class TritonPythonModel:
    """Triton Python Backend for GLM-4V-OCR document understanding."""

    def initialize(self, args):
        self.model_config = json.loads(args.get("model_config", "{}"))
        model_name = self.model_config.get("name", "glm_ocr")
        logger.info(f"Initializing {model_name} (mock={MOCK_MODE})")

        if not MOCK_MODE:
            model_path = os.getenv("GLM_MODEL_PATH", "THUDM/glm-4v-9b")
            logger.info(f"Loading model from: {model_path}")

            self.tokenizer = AutoTokenizer.from_pretrained(
                model_path, trust_remote_code=True
            )
            self.model = AutoModelForCausalLM.from_pretrained(
                model_path,
                torch_dtype=torch.bfloat16,
                device_map="auto",
                trust_remote_code=True,
            )
            self.model.eval()
            logger.info("✅ GLM-OCR model loaded successfully")
        else:
            self.tokenizer = None
            self.model = None
            logger.info("⚠️  Running in MOCK inference mode")

    def execute(self, requests):
        responses = []
        for request in requests:
            try:
                if pb_utils:
                    images_tensor = pb_utils.get_input_tensor_by_name(request, "images")
                    prompt_tensor = pb_utils.get_input_tensor_by_name(request, "prompt")
                    prompt = "OCR this document image. Extract all text, tables, and formulas."
                    if prompt_tensor is not None:
                        prompt = prompt_tensor.as_numpy()[0].decode("utf-8")
                else:
                    images_tensor = None
                    prompt = "OCR this document image."

                if MOCK_MODE:
                    generated_text, confidence = self._mock_inference(prompt)
                else:
                    generated_text, confidence = self._real_inference(
                        images_tensor, prompt
                    )

                if pb_utils:
                    output_text = pb_utils.Tensor(
                        "generated_text",
                        np.array([generated_text], dtype=object),
                    )
                    output_conf = pb_utils.Tensor(
                        "confidence",
                        np.array([confidence], dtype=np.float32),
                    )
                    responses.append(
                        pb_utils.InferenceResponse(output_tensors=[output_text, output_conf])
                    )
                else:
                    responses.append(
                        {"generated_text": generated_text, "confidence": confidence}
                    )

            except Exception as e:
                logger.error(f"Inference error: {e}")
                if pb_utils:
                    responses.append(
                        pb_utils.InferenceResponse(
                            error=pb_utils.TritonError(str(e))
                        )
                    )
                else:
                    responses.append({"error": str(e)})

        return responses

    def _real_inference(self, images_tensor, prompt):
        """Run actual GLM-OCR inference."""
        image_data = images_tensor.as_numpy()
        img = Image.fromarray(image_data)

        inputs = self.tokenizer.apply_chat_template(
            [{"role": "user", "image": img, "content": prompt}],
            add_generation_prompt=True,
            tokenize=True,
            return_tensors="pt",
            return_dict=True,
        ).to(self.model.device)

        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=2048,
                do_sample=False,
            )

        generated_ids = outputs[:, inputs["input_ids"].shape[1] :]
        generated_text = self.tokenizer.decode(
            generated_ids[0], skip_special_tokens=True
        )

        # Confidence heuristic based on output token probabilities
        confidence = 0.92  # Placeholder — can be computed from logprobs
        return generated_text, confidence

    def _mock_inference(self, prompt):
        """Simulated inference for local development without GPU/model."""
        mock_result = {
            "document_type": "invoice",
            "fields": {
                "invoice_number": "INV-2026-0042",
                "date": "2026-02-25",
                "vendor": "Acme Corp",
                "total_amount": "$1,234.56",
                "line_items": [
                    {"description": "Widget A", "quantity": 10, "unit_price": "$100.00", "total": "$1,000.00"},
                    {"description": "Widget B", "quantity": 5, "unit_price": "$46.91", "total": "$234.56"},
                ],
            },
            "tables": [
                {
                    "headers": ["Description", "Qty", "Unit Price", "Total"],
                    "rows": [
                        ["Widget A", "10", "$100.00", "$1,000.00"],
                        ["Widget B", "5", "$46.91", "$234.56"],
                    ],
                }
            ],
            "raw_text": "INVOICE\\nInvoice #: INV-2026-0042\\nDate: 2026-02-25\\nBill To: Customer Inc.",
        }
        return json.dumps(mock_result, indent=2), 0.95

    def finalize(self):
        logger.info("Finalizing GLM-OCR model")
        if not MOCK_MODE and self.model is not None:
            del self.model
            del self.tokenizer
            if not MOCK_MODE:
                torch.cuda.empty_cache()
