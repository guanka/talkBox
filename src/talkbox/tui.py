from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory


class ChatTUI:
    def __init__(self, chat_manager, agent_name: str = "TalkBox"):
        self.chat_manager = chat_manager
        self.agent_name = agent_name
        self.running = False

    def start(self) -> None:
        self.running = True
        session = PromptSession(history=InMemoryHistory())

        print(f"[{self.agent_name}] TUI 模式启动 (输入 quit 退出)")
        print("-" * 40)

        while self.running:
            try:
                user_input = session.prompt("你> ")
            except KeyboardInterrupt:
                print("\n再见!")
                break

            if not user_input.strip():
                continue

            if user_input.lower() in ("quit", "exit", "退出", "q"):
                print("再见!")
                self.running = False
                break

            print(f"[{self.agent_name}] ", end="", flush=True)
            for chunk in self.chat_manager.process_stream(user_input):
                print(chunk, end="", flush=True)
            print()

    def stop(self) -> None:
        self.running = False
