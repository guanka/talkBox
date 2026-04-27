import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Iterator

import requests


@dataclass
class Message:
    role: str
    content: str


class StreamingLLMClient:
    MAX_RETRIES = 3
    RETRY_BACKOFF = (2, 5, 10)

    def __init__(
        self,
        api_key: str,
        model: str = "glm-4",
        base_url: str = "https://open.bigmodel.cn/api/paas/v4",
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self._is_minimax = "minimax" in base_url
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {api_key}"})
        self.logger = logging.getLogger("talkbox.llm")

    def _url(self) -> str:
        if self.base_url.endswith(("/completions", "/chatcompletion_v2")):
            return self.base_url
        return f"{self.base_url}/chat/completions"

    def _post(self, payload: dict) -> dict:
        url = self._url()
        if self._is_minimax:
            payload["reasoning_split"] = False
        for attempt in range(self.MAX_RETRIES + 1):
            response = self.session.post(url, json=payload)
            if response.status_code in (429, 529) and attempt < self.MAX_RETRIES:
                wait = self.RETRY_BACKOFF[attempt]
                self.logger.warning(f"限流 {response.status_code}，{wait}s 后重试 ({attempt + 1}/{self.MAX_RETRIES})")
                time.sleep(wait)
                continue
            if not response.ok:
                self.logger.error(f"LLM API 错误 {response.status_code}: {response.text[:500]}")
            response.raise_for_status()
            text = response.text.strip()
            data = json.loads(text.split("\n", 1)[0])
            if data.get("type") == "error":
                err = data.get("error", {})
                msg = err.get("message", "")
                if "2064" in msg and attempt < self.MAX_RETRIES:
                    wait = self.RETRY_BACKOFF[attempt]
                    self.logger.warning(f"MiniMax 过载，{wait}s 后重试 ({attempt + 1}/{self.MAX_RETRIES})")
                    time.sleep(wait)
                    continue
                raise RuntimeError(f"LLM API 错误: {msg or text[:200]}")
            self._log_usage(data)
            return data
        raise RuntimeError("LLM API 重试次数耗尽")

    def _base_payload(self, messages: list[Message]) -> dict[str, Any]:
        return {
            "model": self.model,
            "messages": [self._serialize(m) for m in messages],
            "thinking": False,
            "reasoning_split": False,
        }

    def chat(self, messages: list[Message]) -> str:
        payload = self._base_payload(messages)
        data = self._post(payload)
        return data["choices"][0]["message"]["content"]

    def chat_stream(self, messages: list[Message]) -> Iterator[str]:
        payload = self._base_payload(messages)
        payload["stream"] = True
        url = self._url()
        response = self.session.post(url, json=payload, stream=True)
        response.raise_for_status()

        in_thinking = False
        for line in response.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str.strip() == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
                delta = chunk["choices"][0].get("delta", {})
                content = delta.get("content", "")
                if not content:
                    continue
                # 过滤 <think ...>...</think > 块（MiniMax 推理模型）
                if in_thinking:
                    if "</think" in content:
                        in_thinking = False
                        content = content.split(">", 1)[-1] if ">" in content else ""
                    else:
                        continue
                if "<think" in content:
                    in_thinking = True
                    before = content.split("<think", 1)[0]
                    if before.strip():
                        yield before
                    continue
                if content:
                    yield content
            except (json.JSONDecodeError, KeyError, IndexError):
                continue

    def _serialize(self, m: Message) -> dict[str, Any]:
        return {"role": m.role, "content": m.content}

    def _log_usage(self, data: dict[str, Any]) -> None:
        usage = data.get("usage", {})
        if usage:
            self.logger.info(
                f"token用量 prompt={usage.get('prompt_tokens', '?')} "
                f"completion={usage.get('completion_tokens', '?')} "
                f"total={usage.get('total_tokens', '?')}"
            )
