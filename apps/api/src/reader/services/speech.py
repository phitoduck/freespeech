"""Text-to-speech: turn words into WAV audio, deterministically for tests.

>>> synth = FakeSynthesizer()
>>> wav_duration(synth.synthesize("hello", voice="am_adam"))
0.4
"""

from __future__ import annotations

import io
import wave
from typing import Any, Protocol


class SpeechSynthesizer(Protocol):
    """Anything that turns text into WAV bytes. The seam that keeps the model out of tests.

    >>> def narrate(synth: "SpeechSynthesizer") -> float:
    ...     return wav_duration(synth.synthesize("hello", voice="am_adam"))
    >>> narrate(FakeSynthesizer())          # tests: silent, instant, deterministic
    0.4
    >>> narrate(KokoroSynthesizer())        # the running app: real speech  # doctest: +SKIP
    0.65
    """

    def synthesize(self, text: str, *, voice: str) -> bytes: ...


def wav_duration(wav_bytes: bytes) -> float:
    """Return a WAV's duration in seconds, from its frame count and frame rate.

    >>> wav_duration(FakeSynthesizer().synthesize("hi", voice="am_adam"))
    0.16
    """
    with wave.open(io.BytesIO(wav_bytes), "rb") as wav:
        return wav.getnframes() / wav.getframerate()


def concat_wavs(wavs: list[bytes]) -> bytes:
    """Join same-format WAVs (24kHz mono 16-bit) into one, frames end to end.

    >>> synth = FakeSynthesizer()
    >>> one, two = synth.synthesize("hi", voice="am_adam"), synth.synthesize("bye", voice="am_adam")
    >>> wav_duration(concat_wavs([one, two])) == wav_duration(one) + wav_duration(two)
    True
    """
    buf = io.BytesIO()
    with wave.open(buf, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(24000)
        for wav_bytes in wavs:
            with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
                out.writeframes(wav_file.readframes(wav_file.getnframes()))
    return buf.getvalue()


class FakeSynthesizer:
    """Silent WAV whose length is a function of the text, so tests never load a model.

    >>> wav_duration(FakeSynthesizer().synthesize("hello", voice="am_adam"))
    0.4
    """

    def synthesize(self, text: str, *, voice: str) -> bytes:
        """Return silent 24kHz mono 16-bit WAV bytes, 0.08s per character of `text`.

        >>> len(FakeSynthesizer().synthesize("hi", voice="am_adam")) > 44
        True
        """
        duration = max(0.08 * len(text), 0.05)
        frame_count = int(duration * 24000)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(24000)
            wav.writeframes(b"\x00\x00" * frame_count)
        return buf.getvalue()


_engine: Any = None


class KokoroSynthesizer:
    """Real Kokoro speech via fastkokoro; the 82M model loads on first use, not on import.

    # -> wav_duration(KokoroSynthesizer().synthesize("Hello", voice="am_adam")) -> 0.65
    """

    def synthesize(self, text: str, *, voice: str = "am_adam") -> bytes:
        """Synthesize speech with the real Kokoro model, loaded into memory on first use.

        # -> KokoroSynthesizer().synthesize("Hi", voice="am_adam") -> b"RIFF..."
        """
        global _engine
        if _engine is None:
            from fastkokoro import FastKokoro

            _engine = FastKokoro()
        return _engine.create(text, voice=voice, lang="en-us", response_format="wav")
