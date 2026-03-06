"""Single-flight isolated GPU inference executor.

Runs model inference inside a dedicated child process so a timed-out request can
be truly cancelled by terminating and restarting that worker process.
"""

from __future__ import annotations

import logging
import multiprocessing as mp
import queue
import time
import uuid
from dataclasses import dataclass
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class InferenceTask:
    task_id: str
    image_base64: str
    prompt: str
    max_tokens: int
    output_format: str


class SingleFlightGPUExecutor:
    """Queue-based single-flight GPU executor with hard-kill timeout recovery."""

    def __init__(self, model_path: str, precision_mode: str) -> None:
        self.model_path = model_path
        self.precision_mode = precision_mode
        self.ctx = mp.get_context("spawn")
        self.request_q: mp.Queue = self.ctx.Queue(maxsize=8)
        self.result_q: mp.Queue = self.ctx.Queue(maxsize=8)
        self.proc: Optional[mp.Process] = None

    @staticmethod
    def _worker_loop(request_q: mp.Queue, result_q: mp.Queue, model_path: str, precision_mode: str) -> None:
        from .glm_inference import GLMInferenceEngine

        engine = GLMInferenceEngine(model_path=model_path, precision_mode=precision_mode)
        while True:
            task = request_q.get()
            if task is None:
                break

            task_id = task["task_id"]
            try:
                content, confidence, prompt_tokens, completion_tokens = engine.extract_content(
                    image_base64=task["image_base64"],
                    prompt=task["prompt"],
                    max_tokens=task["max_tokens"],
                    output_format=task["output_format"],
                )
                result_q.put({
                    "task_id": task_id,
                    "ok": True,
                    "content": content,
                    "confidence": confidence,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                })
            except Exception as exc:  # pragma: no cover - exercised via parent handling
                result_q.put({
                    "task_id": task_id,
                    "ok": False,
                    "error": str(exc),
                })

        try:
            engine.cleanup()
        except Exception:
            pass

    def start(self) -> None:
        if self.proc and self.proc.is_alive():
            return

        self.proc = self.ctx.Process(
            target=self._worker_loop,
            args=(self.request_q, self.result_q, self.model_path, self.precision_mode),
            daemon=True,
        )
        self.proc.start()
        logger.info("Isolated GPU executor started (pid=%s)", self.proc.pid)

    def stop(self) -> None:
        if not self.proc:
            return
        if self.proc.is_alive():
            try:
                self.request_q.put_nowait(None)
            except Exception:
                pass
            self.proc.join(timeout=2)
        if self.proc.is_alive():
            self.proc.terminate()
            self.proc.join(timeout=2)
        logger.info("Isolated GPU executor stopped")
        self.proc = None

    def restart(self) -> None:
        self.stop()
        self.start()

    def is_ready(self) -> bool:
        return self.proc is not None and self.proc.is_alive()

    def execute(
        self,
        image_base64: str,
        prompt: str,
        max_tokens: int,
        output_format: str,
        timeout_seconds: float,
    ) -> Tuple[str, float, int, int]:
        if not self.is_ready():
            self.start()

        task_id = str(uuid.uuid4())
        self.request_q.put({
            "task_id": task_id,
            "image_base64": image_base64,
            "prompt": prompt,
            "max_tokens": int(max_tokens),
            "output_format": output_format,
        })

        deadline = time.time() + float(timeout_seconds)
        stash = []
        while time.time() < deadline:
            remaining = max(0.1, deadline - time.time())
            try:
                msg = self.result_q.get(timeout=remaining)
            except queue.Empty:
                continue

            if msg.get("task_id") != task_id:
                stash.append(msg)
                continue

            # push back unrelated messages in order
            for item in stash:
                self.result_q.put(item)

            if not msg.get("ok"):
                raise RuntimeError(msg.get("error", "inference worker error"))

            return (
                msg["content"],
                float(msg["confidence"]),
                int(msg["prompt_tokens"]),
                int(msg["completion_tokens"]),
            )

        # Timeout: enforce true cancellation by killing worker process.
        logger.error("Isolated GPU executor timed out; restarting worker process")
        self.restart()
        raise TimeoutError(f"Inference timed out after {timeout_seconds}s")
