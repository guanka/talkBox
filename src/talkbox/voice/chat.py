from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from talkbox.llm import Message, StreamingLLMClient
from talkbox.voice.asr import ASRClient
from talkbox.voice.recorder import AudioRecorder
from talkbox.voice.tts import TTSClient

if TYPE_CHECKING:
    from talkbox.memory import Memory

logger = logging.getLogger("talkbox.voice.chat")


class VoiceChat:
    def __init__(
        self,
        llm_client: StreamingLLMClient,
        asr_client: ASRClient,
        tts_client: TTSClient,
        recorder: AudioRecorder,
        memory: Memory | None = None,
    ):
        self.llm = llm_client
        self.asr = asr_client
        self.tts = tts_client
        self.recorder = recorder
        self.memory = memory
        self.conversation_history: list[Message] = []

    async def run(self, system_prompt: str = "你是一个有用的AI助手。") -> None:
        print("[TalkBox] 语音聊天模式 (按 Ctrl+C 退出)")
        print("-" * 40)

        try:
            while True:
                try:
                    print("\n按住 GPIO 按钮说话，松开结束...")
                    audio_path = self.recorder.record_gpio()

                    print("识别中...")
                    text = await self.asr.recognize(audio_path)
                    Path(audio_path).unlink(missing_ok=True)

                    print(f"你> {text}")

                    if not text.strip():
                        print("(未识别到语音)")
                        continue

                    self.conversation_history.append(Message(role="user", content=text))
                    messages = self._build_messages(system_prompt, text)

                    print("[TalkBox] ", end="", flush=True)
                    full_response = ""
                    for chunk in self.llm.chat_stream(messages):
                        print(chunk, end="", flush=True)
                        full_response += chunk
                    print()

                    self.conversation_history.append(Message(role="assistant", content=full_response))

                    if self.memory:
                        self.memory.store(text, full_response)

                    if full_response.strip():
                        print("播放中...")
                        await self.tts.synthesize_and_play(full_response)

                except KeyboardInterrupt:
                    print("\n再见!")
                    break
                except Exception as e:
                    logger.error(f"语音聊天错误: {e}")
                    print(f"\n错误: {e}")
        finally:
            self.recorder.cleanup()

    def _build_messages(self, system_prompt: str, current_message: str) -> list[Message]:
        memory_context = ""
        if self.memory:
            hits = self.memory.search(current_message)
            memory_context = self.memory.format_context(hits)
        system = f"{system_prompt}\n\n{memory_context}" if memory_context else system_prompt
        return [Message(role="system", content=system)] + self.conversation_history
