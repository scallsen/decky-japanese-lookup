"""OCR backends.

- RapidOCRBackend: local/offline (default). Spawns ocr_worker.py under the
  venv python; nothing heavy is imported into the Decky process.
- GeminiBackend: optional cloud OCR via Gemini Vision, stdlib urllib only.

Both return an OCRResult; `regions` are per-line fragments, `text` is the
raw joined text in reading order (cleanup happens later, in cleanup.py).
"""

import asyncio
import base64
import json
import logging
import os
import urllib.error
import urllib.request

from .net import ssl_context

logger = logging.getLogger(__name__)

WORKER = os.path.join(os.path.dirname(__file__), "ocr_worker.py")
OCR_TIMEOUT = 120  # first run loads ONNX models; generous


class OCRError(Exception):
    """OCR failed entirely — surface to the user."""


class OCRResult:
    def __init__(self, regions, crop_path=None):
        # regions: [{text, rect, confidence}]
        self.regions = regions
        self.crop_path = crop_path

    @property
    def text(self) -> str:
        ordered = sorted(self.regions,
                         key=lambda r: (r["rect"]["top"], r["rect"]["left"]))
        return "\n".join(r["text"] for r in ordered)

    @property
    def mean_confidence(self) -> float:
        if not self.regions:
            return 0.0
        return sum(r["confidence"] for r in self.regions) / len(self.regions)

    def to_dict(self):
        return {
            "text": self.text,
            "regions": self.regions,
            "confidence": self.mean_confidence,
            "crop_path": self.crop_path,
        }


def _worker_env():
    # Clean env: Decky's LD_LIBRARY_PATH/PYTHONPATH must not leak into the
    # venv interpreter or the wrong shared libs get loaded.
    env = {k: v for k, v in os.environ.items()
           if k not in ("LD_LIBRARY_PATH", "LD_PRELOAD", "PYTHONPATH", "PYTHONHOME")}
    env["PYTHONNOUSERSITE"] = "1"
    return env


async def _run_worker(venv_python, args, stdin_bytes=None, timeout=OCR_TIMEOUT):
    # (no -S here: the venv's site-packages are resolved by the site module)
    proc = await asyncio.create_subprocess_exec(
        venv_python, WORKER, *args,
        stdin=asyncio.subprocess.PIPE if stdin_bytes is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=_worker_env(),
    )
    try:
        out, err = await asyncio.wait_for(
            proc.communicate(input=stdin_bytes), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        raise OCRError(f"OCR worker timed out after {timeout}s")
    if not out.strip():
        tail = err.decode(errors="replace").strip()[-400:]
        raise OCRError(f"OCR worker produced no output: {tail or 'no stderr'}")
    # onnxruntime/opencv sometimes print banners to stdout on load; the
    # worker's JSON is always the last line
    last_line = out.strip().splitlines()[-1]
    try:
        return json.loads(last_line)
    except json.JSONDecodeError:
        raise OCRError(f"OCR worker output not JSON: {last_line[:200]!r}")


class RapidOCRBackend:
    name = "rapidocr"

    def __init__(self, venv_python: str, models_dir: str):
        self.venv_python = venv_python
        self.models_dir = models_dir

    async def recognize(self, image_path, region=None, crop_out=None,
                        min_confidence=0.4) -> OCRResult:
        opts = {
            "image_path": image_path,
            "models_dir": self.models_dir,
            "min_confidence": min_confidence,
            "region": region,
            "crop_out": crop_out,
        }
        result = await _run_worker(self.venv_python, ["recognize", json.dumps(opts)])
        if result.get("error"):
            trace = result.get("trace", "")
            if trace:
                logger.error(f"worker trace: {trace}")
            raise OCRError(result["error"])
        return OCRResult(result.get("regions", []), result.get("crop_path"))

    async def encode_raw(self, raw: bytes, width: int, height: int, out_png: str) -> str:
        result = await _run_worker(
            self.venv_python,
            ["encode_raw", str(width), str(height), out_png],
            stdin_bytes=raw, timeout=30)
        if result.get("error"):
            raise OCRError(result["error"])
        return result["path"]

    async def crop(self, image_path, region, crop_out) -> str:
        opts = {"image_path": image_path, "region": region, "crop_out": crop_out}
        result = await _run_worker(self.venv_python, ["crop", json.dumps(opts)],
                                   timeout=30)
        if result.get("error"):
            raise OCRError(result["error"])
        return result["crop_path"]


GEMINI_PROMPT = (
    "This is a screenshot from a Japanese visual novel. Transcribe the "
    "dialogue/narration text shown in the text box exactly as written, "
    "including punctuation and quotes. Do not translate. Do not include "
    "UI labels, button prompts, or the speaker name. Return JSON: "
    '{"text": "<transcription>"} with an empty string if no text box is visible.'
)


class GeminiBackend:
    name = "gemini"

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash"):
        self.api_key = api_key
        self.model = model

    async def recognize(self, image_path, region=None, crop_out=None,
                        min_confidence=0.0) -> OCRResult:
        # region/crop handled by the caller (needs the venv); we OCR the
        # image we're given.
        if not self.api_key:
            raise OCRError("Gemini API key not set — add it in plugin settings")
        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()

        body = json.dumps({
            "contents": [{"parts": [
                {"text": GEMINI_PROMPT},
                {"inline_data": {"mime_type": "image/png", "data": img_b64}},
            ]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": {
                    "type": "OBJECT",
                    "properties": {"text": {"type": "STRING"}},
                    "required": ["text"],
                },
            },
        }).encode()

        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{self.model}:generateContent?key={self.api_key}")

        def _post():
            req = urllib.request.Request(
                url, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30,
                                        context=ssl_context()) as resp:
                return json.loads(resp.read())

        try:
            data = await asyncio.to_thread(_post)
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = json.loads(e.read()).get("error", {}).get("message", "")
            except Exception:
                pass
            if e.code in (401, 403):
                raise OCRError(f"Gemini API key rejected: {detail or e.code}")
            if e.code == 429:
                raise OCRError("Gemini rate limit hit — try again shortly")
            raise OCRError(f"Gemini API error {e.code}: {detail}")
        except urllib.error.URLError as e:
            raise OCRError(f"Network error reaching Gemini: {e.reason}")

        try:
            payload = data["candidates"][0]["content"]["parts"][0]["text"]
            text = json.loads(payload)["text"].strip()
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            raise OCRError(f"Unexpected Gemini response shape: {e}")

        regions = []
        if text:
            regions = [{"text": text,
                        "rect": {"left": 0, "top": 0, "right": 0, "bottom": 0},
                        "confidence": 1.0}]
        return OCRResult(regions, crop_out)
