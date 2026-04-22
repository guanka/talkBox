import logging
import select
import sys
import tempfile
import termios
import time
import tty
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

    def record_ptt(self, key: str = " ", max_duration: float = 30.0) -> str:
        stream = self._audio.open(
            format=pyaudio.paInt16,
            channels=self.channels,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=self.chunk,
        )
        frames = []
        max_chunks = int(self.sample_rate / self.chunk * max_duration)

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)

        try:
            tty.setraw(fd)
            key_display = key if key != " " else "空格"
            sys.stdout.write(f"\r按住 {key_display} 键说话，松开结束...\r\n")
            sys.stdout.flush()

            while True:
                if select.select([sys.stdin], [], [], 0.05)[0]:
                    ch = sys.stdin.read(1)
                    if ch == key or (key == " " and ch == " "):
                        break
                    if ch == "\x03":
                        raise KeyboardInterrupt

            sys.stdout.write("\r录音中...\r\n")
            sys.stdout.flush()

            last_key_time = time.time()
            while len(frames) < max_chunks:
                frames.append(stream.read(self.chunk, exception_on_overflow=False))

                if select.select([sys.stdin], [], [], 0.001)[0]:
                    ch = sys.stdin.read(1)
                    if ch == key or (key == " " and ch == " "):
                        last_key_time = time.time()
                    if ch == "\x03":
                        raise KeyboardInterrupt

                if time.time() - last_key_time > 0.3:
                    break
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
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
