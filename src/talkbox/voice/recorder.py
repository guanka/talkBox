import logging
import tempfile
import wave
from pathlib import Path

import pyaudio

logger = logging.getLogger("talkbox.voice.recorder")


class AudioRecorder:
    def __init__(self, sample_rate: int = 16000, channels: int = 1, chunk: int = 1024):
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk = chunk
        self._audio = pyaudio.PyAudio()

    def record(self, duration: float) -> str:
        stream = self._audio.open(
            format=pyaudio.paInt16,
            channels=self.channels,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=self.chunk,
        )
        frames = []
        n_chunks = int(self.sample_rate / self.chunk * duration)
        logger.info(f"录音 {duration}s ({n_chunks} 帧)...")

        try:
            for _ in range(n_chunks):
                frames.append(stream.read(self.chunk, exception_on_overflow=False))
        finally:
            stream.stop_stream()
            stream.close()

        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        self._save_wav(tmp.name, frames)
        return tmp.name

    def record_until_silence(
        self,
        max_duration: float = 30.0,
        silence_threshold: float = 500,
        silence_chunks: int = 30,
    ) -> str:
        import array

        stream = self._audio.open(
            format=pyaudio.paInt16,
            channels=self.channels,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=self.chunk,
        )
        frames = []
        silent_count = 0
        max_chunks = int(self.sample_rate / self.chunk * max_duration)

        logger.info("录音中 (静音自动停止)...")

        try:
            for _ in range(max_chunks):
                data = stream.read(self.chunk, exception_on_overflow=False)
                frames.append(data)

                samples = array.array("h", data)
                rms = (sum(s * s for s in samples) // len(samples)) ** 0.5 if samples else 0

                if rms < silence_threshold:
                    silent_count += 1
                    if silent_count >= silence_chunks:
                        logger.info("检测到静音，停止录音")
                        break
                else:
                    silent_count = 0
        finally:
            stream.stop_stream()
            stream.close()

        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        self._save_wav(tmp.name, frames)
        return tmp.name

    def _save_wav(self, path: str, frames: list[bytes]) -> None:
        with wave.open(path, "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(self._audio.get_sample_size(pyaudio.paInt16))
            wf.setframerate(self.sample_rate)
            wf.writeframes(b"".join(frames))
        logger.info(f"录音保存: {path}")

    def cleanup(self) -> None:
        self._audio.terminate()
