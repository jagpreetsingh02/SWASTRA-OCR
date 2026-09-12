"""`read_page` plumbing, with a fake model instead of the 4 GB one.

Regression: the first upload after server start used to fail with
`ImportError: cannot import name 'LogitsProcessor' from 'transformers'`, because read_page imported
from the (lazy, still-initialising) transformers package while the warm-up thread was importing it.
All heavy imports now happen inside load(), under its lock, and read_page uses what load() cached.
"""

import torch
from PIL import Image

from medikiosk_ocr import ocr


class FakeInputs(dict):
    def to(self, _device):
        return self


class FakeProcessor:
    """Two tokens, spelled the way a real byte-level tokenizer does: ' Tab' then ' Dolo'."""
    pieces = {5: " Tab", 6: " Dolo"}

    class tokenizer:
        @staticmethod
        def decode(ids, skip_special_tokens=True):
            return "".join(FakeProcessor.pieces[i] for i in ids)

    def apply_chat_template(self, messages, **kwargs):
        self.seen = messages
        return FakeInputs(input_ids=torch.tensor([[1, 2, 3]]))


class FakeModel:
    device = "cpu"

    class generation_config:
        eos_token_id = 9

    def generate(self, input_ids=None, max_new_tokens=None, logits_processor=None, **kwargs):
        vocabulary = torch.full((1, 16), -10.0)
        for step, token in enumerate((5, 6)):
            vocabulary[0][token] = 10.0 - step  # a confident first token, a less confident second
            logits_processor(input_ids, vocabulary.clone())
        return torch.tensor([[1, 2, 3, 5, 6]])


def install_fake(monkeypatch):
    from transformers import LogitsProcessor, LogitsProcessorList

    monkeypatch.setattr(ocr, "_model", FakeModel())
    monkeypatch.setattr(ocr, "_processor", FakeProcessor())
    monkeypatch.setattr(ocr, "_logits_classes", (LogitsProcessor, LogitsProcessorList))


def test_read_page_uses_the_classes_cached_by_load(monkeypatch):
    install_fake(monkeypatch)
    page = ocr.read_page(Image.new("RGB", (400, 300), "white"))
    assert page.text == "Tab Dolo"                      # leading space stripped, nothing invented
    assert len(page.char_confidence) == len(page.text)
    assert page.char_confidence[0] > page.char_confidence[-1]  # per-token probability reached the characters
    assert page.truncated is False


def test_read_page_does_not_import_from_transformers_at_call_time(monkeypatch):
    """If it did, a request arriving while transformers is still importing would fail again."""
    install_fake(monkeypatch)
    import builtins

    real_import = builtins.__import__

    def refuse_transformers(name, *args, **kwargs):
        if name == "transformers" or name.startswith("transformers."):
            raise AssertionError(f"read_page must not import {name} at call time")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", refuse_transformers)
    assert ocr.read_page(Image.new("RGB", (400, 300), "white")).text == "Tab Dolo"


def test_load_is_only_called_once_per_process(monkeypatch):
    install_fake(monkeypatch)
    calls = []
    real_load = ocr.load
    monkeypatch.setattr(ocr, "load", lambda: calls.append(1) or real_load())
    ocr.read_page(Image.new("RGB", (400, 300), "white"))
    ocr.read_page(Image.new("RGB", (400, 300), "white"))
    assert len(calls) == 2 and ocr.is_loaded()  # load() is cheap after the first time: the model is cached
