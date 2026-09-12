"""Page image -> text, with a token probability behind every character. All OCR-model code lives here.

Model: Qwen3-VL-2B-Instruct, chosen by eval/model_selection/ocr_candidates.py over Tesseract,
GOT-OCR2, GLM-OCR, PaddleOCR-VL and the TrOCR prescription model (see README "Model selection").

Per-character confidence = the probability the model gave the token it emitted (greedy decoding),
copied to the characters that token produced. It measures the model's certainty, not correctness:
a generative OCR model can be confidently wrong (HbA1c read as HbAlc at p=0.999), which is why
every value still goes to human verification.
"""

from __future__ import annotations

import os
import re
import threading
from dataclasses import dataclass

from PIL import Image

MODEL_ID = "Qwen/Qwen3-VL-2B-Instruct"
PROMPT = (
    "Transcribe all text in this image exactly as written, line by line. Keep the original spelling, "
    "abbreviations, numbers and units. Do not correct, expand, translate or add anything. "
    "If there is no readable text, output nothing."
)
MAX_PIXELS = 1_400_000     # ~1000x1400: enough for A4 at readable size, bounded memory
MAX_NEW_TOKENS = 1536      # a dense page is ~600-900 tokens; hitting this means a loop or an unusual page


@dataclass
class PageText:
    text: str
    char_confidence: list[float]
    truncated: bool


_model = None
_processor = None
_logits_classes: tuple | None = None   # (LogitsProcessor, LogitsProcessorList), imported once under the load lock
_load_lock = threading.Lock()
_infer_lock = threading.Lock()  # one generation at a time: the model is not safe to share across threads


def _device() -> str:
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def load():
    """Load the model once per process (thread-safe). Returns (model, processor).

    Every heavy import happens here, under the lock: `transformers` is a lazy package, and importing a
    name from it while another thread is still importing it raises ImportError. That is exactly what a
    request arriving during start-up warm-up used to do.
    """
    global _model, _processor, _logits_classes
    with _load_lock:
        if _model is None:
            import torch
            from transformers import AutoModelForImageTextToText, AutoProcessor, LogitsProcessor, LogitsProcessorList

            device = _device()
            dtype = torch.float32 if device == "cpu" else torch.bfloat16
            processor = AutoProcessor.from_pretrained(MODEL_ID)
            model = AutoModelForImageTextToText.from_pretrained(MODEL_ID, dtype=dtype).to(device).eval()
            _logits_classes = (LogitsProcessor, LogitsProcessorList)
            _processor, _model = processor, model
    return _model, _processor


def is_loaded() -> bool:
    return _model is not None


def device_name() -> str:
    """Which device inference will use ("cuda" / "mps" / "cpu"). Does not load the model."""
    try:
        return _device()
    except Exception:  # torch missing or broken: report it instead of failing a health check
        return "unavailable"


def read_page(image: Image.Image) -> PageText:
    model, processor = load()          # completes every import before anything below touches them
    import torch                       # safe now: fully imported inside load()

    LogitsProcessor, LogitsProcessorList = _logits_classes
    image = _fit(image)
    messages = [{"role": "user", "content": [{"type": "image", "image": image}, {"type": "text", "text": PROMPT}]}]
    inputs = processor.apply_chat_template(
        messages, tokenize=True, add_generation_prompt=True, return_dict=True, return_tensors="pt"
    ).to(model.device)

    step_probs = []

    class RecordChosenProbability(LogitsProcessor):
        """Runs after the built-in processors: under greedy decoding the argmax of these scores is the
        emitted token, so the max softmax is that token's probability. Kept on the device (no per-token sync)."""

        def __call__(self, input_ids, scores):
            step_probs.append(torch.softmax(scores[0].float(), dim=-1).max())
            return scores

    try:
        with _infer_lock, torch.inference_mode():
            out = model.generate(
                **inputs,
                max_new_tokens=MAX_NEW_TOKENS,
                do_sample=False, temperature=None, top_p=None, top_k=None,
                logits_processor=LogitsProcessorList([RecordChosenProbability()]),
            )
            probs = torch.stack(step_probs).tolist() if step_probs else []
    except Exception:
        _release_cached_memory()  # e.g. after an out-of-memory error, so the next request can run
        raise
    new_ids = out[0, inputs["input_ids"].shape[-1]:].tolist()
    eos = set(_as_list(model.generation_config.eos_token_id))
    truncated = len(new_ids) >= MAX_NEW_TOKENS and not (new_ids and new_ids[-1] in eos)
    text, conf = _characters_with_confidence(processor.tokenizer, new_ids, probs)
    return PageText(*_strip_wrapping(text, conf), truncated=truncated)


def _release_cached_memory() -> None:
    import torch

    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    elif torch.backends.mps.is_available():
        torch.mps.empty_cache()


def _fit(image: Image.Image) -> Image.Image:
    pixels = image.width * image.height
    if pixels <= MAX_PIXELS:
        return image
    scale = (MAX_PIXELS / pixels) ** 0.5
    return image.resize((round(image.width * scale), round(image.height * scale)), Image.LANCZOS)


def _characters_with_confidence(tokenizer, ids: list[int], probs: list[float]) -> tuple[str, list[float]]:
    """Decode token by token so each character inherits the probability of the token that produced it.
    When a multi-byte character completes and rewrites the tail, the tail takes the lowest involved probability."""
    text, conf = "", []
    for i, p in enumerate(probs[: len(ids)]):
        current = tokenizer.decode(ids[: i + 1], skip_special_tokens=True)
        common = len(os.path.commonprefix([text, current]))
        tail = min([p, *conf[common:]])
        conf = conf[:common] + [tail] * (len(current) - common)
        text = current
    return text, conf


NO_TEXT_REPLY = re.compile(
    r"^\W*(?:there\s+is\s+|there's\s+|i\s+see\s+|the\s+image\s+(?:contains|has)\s+)?no\s+(?:readable|legible|visible|discernible)?\s*text"
    r"(?:\s+(?:in|on)\s+(?:the|this)\s+image)?\W*$",
    re.I,
)


def _strip_wrapping(text: str, conf: list[float]) -> tuple[str, list[float]]:
    """Remove surrounding whitespace and a ```markdown fence if the model added one, and turn a
    conversational "there is no readable text" reply into empty output. Content is never edited."""
    if NO_TEXT_REPLY.match(text.strip()):
        return "", []
    start, end = 0, len(text)
    stripped = text.strip()
    if stripped.startswith("```") and stripped.endswith("```") and len(stripped) >= 6:
        start = text.index("```")
        start = text.find("\n", start) + 1 if "\n" in text[start:] else start + 3
        end = text.rindex("```")
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return text[start:end], conf[start:end]


def _as_list(value) -> list:
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]
