import argparse
import logging
import sys
from pathlib import Path

import yaml

from talkbox.chat import ChatManager
from talkbox.llm import StreamingLLMClient
from talkbox.tui import ChatTUI

_LLM_BASE_URLS = {
    "glm": "https://open.bigmodel.cn/api/paas/v4",
    "minimax": "https://api.minimaxi.com/v1/text/chatcompletion_v2",
}


def find_project_root() -> Path:
    package_path = Path(__file__).resolve().parent
    current = package_path
    while current != current.parent:
        if (current / "config.yaml").exists() or (current / "pyproject.toml").exists():
            return current
        current = current.parent
    return Path.cwd()


def main() -> None:
    parser = argparse.ArgumentParser(description="TalkBox - 流式LLM聊天盒")
    parser.add_argument("--voice", action="store_true", help="语音聊天模式")
    parser.add_argument("--tui", action="store_true", help="文字聊天模式 (默认)")
    args = parser.parse_args()

    root = find_project_root()
    config_path = root / "config.yaml"

    if not config_path.exists():
        print(f"错误: 配置文件不存在: {config_path}")
        print("请复制 config.yaml.example 为 config.yaml 并填入配置")
        sys.exit(1)

    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    logging.basicConfig(
        level=config.get("logging", {}).get("level", "INFO"),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    llm_cfg = config.get("llm", {})
    api_key = llm_cfg.get("api_key", "")
    if not api_key or api_key == "YOUR_API_KEY_HERE":
        print("错误: 请在 config.yaml 中配置 llm.api_key")
        sys.exit(1)

    provider = llm_cfg.get("provider", "glm")
    base_url = llm_cfg.get("base_url") or _LLM_BASE_URLS.get(provider, _LLM_BASE_URLS["glm"])
    logger = logging.getLogger("talkbox")
    logger.info(f"LLM: {provider}/{llm_cfg.get('model', 'glm-4')}")

    llm_client = StreamingLLMClient(
        api_key=api_key,
        model=llm_cfg.get("model", "glm-4"),
        base_url=base_url,
    )

    memory = None
    memory_cfg = config.get("memory", {})
    if memory_cfg.get("enabled", False):
        from talkbox.memory import Memory
        palace_path = memory_cfg.get("palace_path") or str(root / ".palace")
        memory = Memory(
            palace_path=palace_path,
            wing=memory_cfg.get("wing", "talkbox"),
        )
        logger.info(f"记忆系统已启用: {memory.palace_path}")

    system_prompt = llm_cfg.get("system_prompt", "你是一个有用的AI助手。")
    chat_manager = ChatManager(llm=llm_client, system_prompt=system_prompt, memory=memory)

    try:
        if args.voice:
            from talkbox.voice.chat import VoiceChat
            from talkbox.voice.asr import ASRClient
            from talkbox.voice.tts import TTSClient
            from talkbox.voice.recorder import AudioRecorder

            voice_cfg = config.get("voice", {})
            asr_client = ASRClient(ws_url=voice_cfg.get("asr_ws_url", "ws://100.64.0.2:8765/ws"))
            tts_client = TTSClient(ws_url=voice_cfg.get("tts_ws_url", "ws://100.64.0.2:8765/ws/tts"))
            recorder = AudioRecorder(sample_rate=voice_cfg.get("sample_rate", 48000))

            voice_chat = VoiceChat(
                llm_client=llm_client,
                asr_client=asr_client,
                tts_client=tts_client,
                recorder=recorder,
                memory=memory,
                gpio_chip=voice_cfg.get("gpio_chip", 0),
                gpio_line=voice_cfg.get("gpio_line", 4),
            )
            import asyncio
            asyncio.run(voice_chat.run(system_prompt=system_prompt))
        else:
            tui = ChatTUI(chat_manager=chat_manager)
            tui.start()
    finally:
        pass


if __name__ == "__main__":
    main()
