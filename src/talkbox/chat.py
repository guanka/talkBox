from __future__ import annotations

from typing import TYPE_CHECKING, Iterator

from talkbox.llm import Message, StreamingLLMClient

if TYPE_CHECKING:
    from talkbox.memory import Memory


class ChatManager:
    def __init__(
        self,
        llm: StreamingLLMClient,
        system_prompt: str = "你是一个有用的AI助手。",
        memory: Memory | None = None,
    ):
        self.llm = llm
        self.system_prompt = system_prompt
        self.memory = memory
        self.conversation_history: list[Message] = []

    def process(self, message: str) -> str:
        self.conversation_history.append(Message(role="user", content=message))
        messages = self._build_messages(message)
        response = self.llm.chat(messages)
        self.conversation_history.append(Message(role="assistant", content=response))
        self._store(message, response)
        return response

    def process_stream(self, message: str) -> Iterator[str]:
        self.conversation_history.append(Message(role="user", content=message))
        messages = self._build_messages(message)
        full_response = ""
        for chunk in self.llm.chat_stream(messages):
            full_response += chunk
            yield chunk
        self.conversation_history.append(Message(role="assistant", content=full_response))
        self._store(message, full_response)

    def _build_messages(self, current_message: str = "") -> list[Message]:
        memory_context = self._search_memory(current_message)
        if memory_context:
            system = f"{self.system_prompt}\n\n{memory_context}"
        else:
            system = self.system_prompt
        return [Message(role="system", content=system)] + self.conversation_history

    def _search_memory(self, query: str) -> str:
        if not self.memory or not query:
            return ""
        hits = self.memory.search(query)
        return self.memory.format_context(hits)

    def _store(self, user_msg: str, assistant_msg: str) -> None:
        if self.memory:
            self.memory.store(user_msg, assistant_msg)

    def clear(self) -> None:
        self.conversation_history.clear()
