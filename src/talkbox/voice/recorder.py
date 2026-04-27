import logging
import tempfile
import time
import wave

import pyaudio

try:
    import RPi.GPIO as GPIO
    _HAS_GPIO = True
except ImportError:
    _HAS_GPIO = False

logger = logging.getLogger("talkbox.voice.recorder")


class AudioRecorder:
    def __init__(self, sample_rate: int = 48000, channels: int = 1, chunk: int = 1024, gpio_pin: int = 4):
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk = chunk
        self.gpio_pin = gpio_pin
        self._audio = pyaudio.PyAudio()
        self._gpio_initialized = False

    def _init_gpio(self) -> None:
        if not _HAS_GPIO or self._gpio_initialized:
            return
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.gpio_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        self._gpio_initialized = True
        logger.info(f"GPIO{self.gpio_pin} 已初始化 (BCM, PULL_UP)")

    def _gpio_pressed(self) -> bool:
        return GPIO.input(self.gpio_pin) != GPIO.LOW

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

    def record_gpio(
        self,
        gpio_pin: int | None = None,
        max_duration: float = 30.0,
    ) -> str:
        pin = gpio_pin or self.gpio_pin
        self._init_gpio()

        stream = self._audio.open(
            format=pyaudio.paInt16,
            channels=self.channels,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=self.chunk,
        )
        frames = []
        max_chunks = int(self.sample_rate / self.chunk * max_duration)

        print(f"按住 GPIO{pin} 按钮说话，松开结束...")
        logger.info(f"等待 GPIO{pin} 触发 (PULL_UP, LOW=按下)")

        try:
            while not self._gpio_pressed():
                time.sleep(0.05)

            print("录音中... (松开停止)")
            while len(frames) < max_chunks:
                frames.append(stream.read(self.chunk, exception_on_overflow=False))
                if not self._gpio_pressed():
                    break
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
        if self._gpio_initialized:
            GPIO.cleanup()
            self._gpio_initialized = False
