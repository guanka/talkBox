import asyncio
import json
import logging
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
