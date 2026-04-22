import asyncio
import json
import logging
import subprocess
import tempfile
from pathlib import Path

import websockets

SUPPORTED_FORMATS = {".mp3", ".wav", ".webm", ".ogg", ".pcm", ".opus", ".flac", ".m4a", ".aac"}

logger = logging.getLogger("talkbox.voice.asr")


def _convert_to_webm(audio_path: str) -> str:
    tmp = tempfile.NamedTemporaryFile(suffix=".webm", delete=False)
    tmp.close()
    result = subprocess.run(
        [
            "ffmpeg", "-y", "-i", audio_path,
            "-c:a", "libopus", "-b:a", "32k", "-ar", "16000", "-ac", "1", tmp.name,
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        Path(tmp.name).unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg 转码失败: {result.stderr}")
    return tmp.name


class ASRClient:
    def __init__(self, ws_url: str = "ws://100.64.0.2:8765/ws"):
        self.ws_url = ws_url

    async def recognize(self, audio_path: str) -> str:
        path = Path(audio_path)
        if not path.exists():
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")

        suffix = path.suffix.lower()
        if suffix not in SUPPORTED_FORMATS:
            raise ValueError(f"不支持的音频格式 '{suffix}'，支持: {', '.join(sorted(SUPPORTED_FORMATS))}")

        send_path = audio_path
        need_cleanup = False

        if suffix != ".webm":
            logger.info(f"转码 {suffix} → webm: {audio_path}")
            send_path = _convert_to_webm(audio_path)
            need_cleanup = True

        try:
            async with websockets.connect(self.ws_url) as ws:
                greeting = json.loads(await ws.recv())
                logger.debug(f"ASR 服务端: {greeting.get('data', {}).get('text', '')}")

                with open(send_path, "rb") as f:
                    await ws.send(f.read())

                last_text = ""
                while True:
                    try:
                        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=60.0))
                        msg_type = msg.get("type")
                        data = msg.get("data", {})

                        if msg_type == "partial":
                            last_text = data.get("text", last_text)
                        elif msg_type == "final":
                            return data.get("text", last_text)
                        elif msg_type == "error":
                            raise RuntimeError(f"ASR 错误: {data.get('message', '未知错误')}")
                    except asyncio.TimeoutError:
                        return last_text
        finally:
            if need_cleanup:
                Path(send_path).unlink(missing_ok=True)
