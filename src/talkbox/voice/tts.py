import asyncio
import json
import logging
import queue
import threading
import wave

import websockets

try:
    import numpy as np
    import sounddevice as sd
    _HAS_AUDIO = True
except ImportError:
    _HAS_AUDIO = False

logger = logging.getLogger("talkbox.voice.tts")


class TTSClient:
    def __init__(self, ws_url: str = "ws://100.64.0.2:8765/ws/tts"):
        self.ws_url = ws_url

    async def synthesize(self, text: str, output_path: str | None = None) -> bytes:
        pcm_buffer = bytearray()

        async with websockets.connect(self.ws_url) as ws:
            msg = await ws.recv()
            data = json.loads(msg)
            logger.debug(f"TTS 连接: client_id={data.get('data', {}).get('client_id')}")

            await ws.send(json.dumps({"type": "text", "content": text}))

            while True:
                msg = await ws.recv()
                if isinstance(msg, bytes):
                    pcm_buffer.extend(msg)
                else:
                    data = json.loads(msg)
                    msg_type = data.get("type")
                    d = data.get("data", {})

                    if msg_type == "done":
                        break
                    elif msg_type == "error":
                        raise RuntimeError(f"TTS 错误: {d.get('message', '未知')}")

        if output_path:
            if output_path.endswith(".wav"):
                with wave.open(output_path, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(16000)
                    wf.writeframes(bytes(pcm_buffer))
            else:
                with open(output_path, "wb") as f:
                    f.write(bytes(pcm_buffer))
            logger.info(f"TTS 保存: {output_path} ({len(pcm_buffer)} bytes)")

        return bytes(pcm_buffer)

    async def synthesize_and_play(self, text: str) -> None:
        pcm = await self.synthesize(text)
        if not pcm:
            return

        if not _HAS_AUDIO:
            logger.warning("numpy/sounddevice 未安装，跳过播放")
            return

        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        sd.play(audio, samplerate=16000)
        sd.wait()

    async def synthesize_and_play_streaming(self, text: str) -> None:
        if not _HAS_AUDIO:
            await self.synthesize(text)
            return

        pcm_queue: queue.Queue[bytes | None] = queue.Queue()
        play_done = threading.Event()

        def _player():
            pcm_buffer = bytearray()
            while True:
                chunk = pcm_queue.get()
                if chunk is None:
                    if pcm_buffer:
                        audio = np.frombuffer(bytes(pcm_buffer), dtype=np.int16).astype(np.float32) / 32768.0
                        sd.play(audio, samplerate=16000)
                        sd.wait()
                    play_done.set()
                    return
                pcm_buffer.extend(chunk)
                if len(pcm_buffer) >= 16000 * 2 * 2:
                    audio = np.frombuffer(bytes(pcm_buffer), dtype=np.int16).astype(np.float32) / 32768.0
                    pcm_buffer.clear()
                    sd.play(audio, samplerate=16000)
                    sd.wait()

        player_thread = threading.Thread(target=_player, daemon=True)
        player_thread.start()

        try:
            async with websockets.connect(self.ws_url) as ws:
                msg = await ws.recv()
                data = json.loads(msg)
                logger.debug(f"TTS 流式连接: client_id={data.get('data', {}).get('client_id')}")

                await ws.send(json.dumps({"type": "text", "content": text}))

                while True:
                    msg = await ws.recv()
                    if isinstance(msg, bytes):
                        pcm_queue.put(msg)
                    else:
                        data = json.loads(msg)
                        msg_type = data.get("type")
                        if msg_type == "done":
                            break
                        elif msg_type == "error":
                            d = data.get("data", {})
                            raise RuntimeError(f"TTS 错误: {d.get('message', '未知')}")
        finally:
            pcm_queue.put(None)
            play_done.wait(timeout=30)
