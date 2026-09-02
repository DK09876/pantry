"""Tests for turning model output into something a speech engine reads well.

Both of these were written against a live failure during a demo, without
tests. Pinning them so the behaviour is deliberate rather than remembered.
"""

from pantry.tts import SENTENCE_END, for_speech


class TestThousandsSeparators:
    """Piper reads 29,031 as "twenty-nine thousand, oh three one"."""

    def test_a_comma_inside_a_number_is_removed(self):
        assert for_speech("It is 29,031 feet") == "It is 29031 feet"

    def test_several_in_one_sentence(self):
        assert for_speech("8,848 metres or 29,031 feet") == "8848 metres or 29031 feet"

    def test_a_comma_between_words_is_left_alone(self):
        assert for_speech("milk, eggs and bread") == "milk, eggs and bread"

    def test_a_comma_before_a_short_group_is_left_alone(self):
        # "1,2" is not a thousands separator; only a group of exactly three.
        assert for_speech("option 1,2 or 3") == "option 1,2 or 3"

    def test_a_comma_before_four_digits_is_left_alone(self):
        assert for_speech("ref 12,3456") == "ref 12,3456"


class TestMarkdown:
    def test_emphasis_is_stripped(self):
        assert for_speech("that is **really** important") == "that is really important"

    def test_backticks_and_headings_go_too(self):
        assert for_speech("# Title with `code`") == "Title with code"

    def test_ordinary_text_is_untouched(self):
        assert for_speech("Added buy milk to Health.") == "Added buy milk to Health."


def test_output_is_trimmed():
    assert for_speech("  padded  ") == "padded"


class TestSentenceSplitting:
    def test_splits_on_terminators(self):
        assert SENTENCE_END.split("One. Two! Three?") == ["One.", "Two!", "Three?"]

    def test_a_decimal_point_does_not_split(self):
        # No space after the point, so it is not a sentence end.
        assert SENTENCE_END.split("It costs 3.50 today") == ["It costs 3.50 today"]
