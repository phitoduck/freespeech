"""Invariants of split_sentences() not already expressed in features/*.feature."""

from __future__ import annotations

from hypothesis import given
from reader.domain.sentences import split_sentences

from tests.properties.strategies import word_lists


@given(word_lists())
def test_concatenating_sentence_words_reproduces_the_input(words):
    sentences = split_sentences(words)
    reconstructed = [word for sentence in sentences for word in sentence.words]
    assert reconstructed == words


@given(word_lists())
def test_sentence_start_and_stop_index_correctly_into_the_input(words):
    sentences = split_sentences(words)

    # start/stop must cover the input exactly once, in order, with no gaps.
    assert sentences[0].start == 0
    assert sentences[-1].stop == len(words)
    for earlier, later in zip(sentences, sentences[1:], strict=False):
        assert earlier.stop == later.start

    for sentence in sentences:
        assert words[sentence.start : sentence.stop] == list(sentence.words)
