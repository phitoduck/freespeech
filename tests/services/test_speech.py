"""Contract tests for the SpeechSynthesizer implementations."""

from __future__ import annotations

import pytest
from reader.services.speech import FakeSynthesizer, KokoroSynthesizer, wav_duration


def test_wav_duration_is_positive_for_non_empty_text():
    wav_bytes = FakeSynthesizer().synthesize("hello world", voice="am_adam")

    assert wav_duration(wav_bytes) > 0


def test_wav_duration_is_deterministic_for_the_same_text():
    synth = FakeSynthesizer()

    first = wav_duration(synth.synthesize("hello world", voice="am_adam"))
    second = wav_duration(synth.synthesize("hello world", voice="am_adam"))

    assert first == second


@pytest.mark.kokoro
def test_kokoro_synthesizer_returns_a_wav_of_positive_duration():
    wav_bytes = KokoroSynthesizer().synthesize("Hello, this is a test.", voice="am_adam")

    assert wav_duration(wav_bytes) > 0
