"""Model-specific output handling in ocr.py, without loading the model."""

import pytest

from medikiosk_ocr.ocr import _characters_with_confidence, _strip_wrapping


@pytest.mark.parametrize("reply", [
    "There is no readable text in the image.",
    "No text",
    "no legible text in this image",
    "  There's no visible text.  ",
])
def test_no_text_replies_become_empty_output(reply):
    assert _strip_wrapping(reply, [0.9] * len(reply)) == ("", [])


def test_real_text_mentioning_text_is_kept():
    text = "Adv: no text messages while driving\nTab Dolo 650 SOS"
    assert _strip_wrapping(text, [0.9] * len(text))[0] == text


def test_markdown_fence_and_whitespace_are_removed_with_confidence_kept_aligned():
    text = "```markdown\nTab Telma 40 OD\n```\n"
    conf = [0.5] * len(text)
    inner = text.index("Tab")
    conf[inner:inner + 3] = [0.1, 0.2, 0.3]
    out, out_conf = _strip_wrapping(text, conf)
    assert out == "Tab Telma 40 OD"
    assert out_conf[:3] == [0.1, 0.2, 0.3] and len(out_conf) == len(out)


class FakeTokenizer:
    """Token 3 is the second half of a multi-byte character: decoding 0..2 shows a placeholder."""
    pieces = {0: "Tab ", 1: "Dolo", 2: " 650", 3: "µ", 4: "g"}

    def decode(self, ids, skip_special_tokens=True):
        out = "".join(self.pieces[i] for i in ids if i != 9)
        return out.replace("µ", "µ")


def test_each_character_gets_the_probability_of_the_token_that_produced_it():
    text, conf = _characters_with_confidence(FakeTokenizer(), [0, 1, 2], [0.9, 0.4, 0.8])
    assert text == "Tab Dolo 650"
    assert conf == [0.9] * 4 + [0.4] * 4 + [0.8] * 4
