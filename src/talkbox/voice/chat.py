from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

from talkbox.llm import Message, StreamingLLMClient
from talkbox.voice.asr import ASRClient
from talkbox.voice.recorder import AudioRecorder
from talkbox.voice.tts import TTSClient

if TYPE_CHECKING:
    from talkbox.memory import Memory

logger = logging.getLogger("talkbox.voice.chat")

_SENTENCE_ENDINGS = re.compile(r"([。！？；\n.!?;]+)")


def _split_sentences(text: str) -> list[str]:
    if not text.strip():
        return []
    parts = _SENTENCE_ENDINGS.split(text)
    sentences = []
    current = ""
    for part in parts:
        current += part
        if _SENTENCE_ENDINGS.fullmatch(part):
            stripped = current.strip()
            if stripped:
                sentences.append(stripped)
            current = ""
    if current.strip():
        sentences.append(current.strip())
    return sentences


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
                    full_response = await self._stream_llm_to_tts(messages)
                    print()

                    self.conversation_history.append(Message(role="assistant", content=full_response))

                    if self.memory:
                        self.memory.store(text, full_response)

                except KeyboardInterrupt:
                    print("\n再见!")
                    break
                except Exception as e:
                    logger.error(f"语音聊天错误: {e}")
                    print(f"\n错误: {e}")
        finally:
            self.recorder.cleanup()

    async def _stream_llm_to_tts(self, messages: list[Message]) -> str:
        buffer = ""
        full_response = ""
        tts_tasks: list[asyncio.Task] = []

        async for chunk in self.llm.chat_stream_async(messages):
            print(chunk, end="", flush=True)
            buffer += chunk

            sentences = _split_sentences(buffer)
            if len(sentences) > 1:
                for sentence in sentences[:-1]:
                    full_response += sentence
                    tts_tasks.append(asyncio.create_task(
                        self.tts.synthesize_and_play_streaming(sentence)
                    ))
                buffer = sentences[-1] if not _SENTENCE_ENDINGS.search(buffer) else buffer
                if _SENTENCE_ENDINGS.search(buffer):
                    full_response += buffer
                    tts_tasks.append(asyncio.create_task(
                        self.tts.synthesize_and_play_streaming(buffer)
                    ))
                    buffer = ""

        if buffer.strip():
            full_response += buffer
            print(buffer, end="", flush=True)
            tts_tasks.append(asyncio.create_task(
                self.tts.synthesize_and_play_streaming(buffer)
            ))

        if tts_tasks:
            await asyncio.gather(*tts_tasks, return_exceptions=True)

        return full_response

    def _build_messages(self, system_prompt: str, current_message: str) -> list[Message]:
        memory_context = ""
        if self.memory:
            hits = self.memory.search(current_message)
            memory_context = self.memory.format_context(hits)
        system = f"{system_prompt}\n\n{memory_context}" if memory_context else system_prompt
        return [Message(role="system", content=system)] + self.conversation_history
