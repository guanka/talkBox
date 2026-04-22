# TalkBox 使用文档

流式 LLM 聊天盒，支持文字对话与语音对话。

## 安装

```bash
cd /home/guanka/code/talkbox
pip3 install -e .
```

需要语音模式时，先装系统依赖再安装可选包：

```bash
# Ubuntu/Debian
sudo apt install python3-dev portaudio19-dev

# 然后安装语音依赖
pip3 install -e ".[voice]"
```

## 配置

```bash
cp config.yaml.example config.yaml
```

编辑 `config.yaml`：

```yaml
llm:
  provider: minimax              # glm 或 minimax
  model: MiniMax-Text-01         # 模型名称
  api_key: "你的API密钥"          # 必填
  base_url: null                 # 留空按 provider 自动选择
  system_prompt: "你是一个有用的AI助手。"
```

### 支持的 LLM 服务商

| provider | base_url（自动） | 推荐模型 |
|----------|-----------------|---------|
| `glm` | `https://open.bigmodel.cn/api/paas/v4` | glm-4 |
| `minimax` | `https://api.minimaxi.com/v1/text/chatcompletion_v2` | MiniMax-Text-01 |

`base_url` 留空时按 `provider` 自动填充。填了值则优先使用填的值。

### 记忆系统（可选）

基于 MemPalace 的语义记忆，跨对话保留上下文：

```yaml
memory:
  enabled: true
  palace_path: null    # 存储路径，留空用默认
  wing: "talkbox"      # 命名空间，区分不同用途
```

启用后每次对话自动检索相关历史注入上下文，并在对话结束后存储。

### 语音服务（仅语音模式需要）

```yaml
voice:
  asr_ws_url: "ws://100.64.0.2:8765/ws"       # ASR WebSocket 地址
  tts_ws_url: "ws://100.64.0.2:8765/ws/tts"   # TTS WebSocket 地址
  sample_rate: 16000                            # 采样率
```

需要本地运行 ASR/TTS WebSocket 服务。

## 运行

### 文字聊天（默认）

```bash
talkbox
# 或
talkbox --tui
# 或
python3 -m talkbox
```

进入终端交互界面，流式输出回复：

```
[TalkBox] TUI 模式启动 (输入 quit 退出)
----------------------------------------
你> 你好
[TalkBox] 你好！有什么我可以帮助你的吗？
你> quit
再见!
```

输入 `quit`、`exit`、`退出`、`q` 任一即可退出。

### 语音聊天

```bash
talkbox --voice
```

流程循环：录音5秒 → 语音转文字 → LLM流式回复 → 语音合成播放 → 下一轮。

按 `Ctrl+C` 退出。

## 项目结构

```
talkbox/
├── config.yaml.example    # 配置模板
├── pyproject.toml         # 项目定义
└── src/talkbox/
    ├── __main__.py        # 入口
    ├── llm.py             # 流式 LLM 客户端（SSE）
    ├── chat.py            # 对话管理器（历史 + 记忆）
    ├── memory.py          # MemPalace 记忆集成
    ├── tui.py             # 终端文字聊天界面
    └── voice/
        ├── asr.py         # ASR 客户端（WebSocket）
        ├── tts.py         # TTS 客户端（WebSocket + 播放）
        ├── recorder.py    # 录音器（PyAudio）
        └── chat.py        # 语音聊天编排
```

## 依赖说明

| 包 | 必需 | 用途 |
|---|---|---|
| pyyaml | 是 | 读取 config.yaml |
| requests | 是 | LLM API 调用（含流式） |
| prompt-toolkit | 是 | 终端输入 |
| websockets | 是 | ASR/TTS WebSocket 通信 |
| mempalace | 是 | 语义记忆 |
| numpy | 语音 | TTS 音频处理 |
| sounddevice | 语音 | TTS 音频播放 |
| pyaudio | 语音 | 麦克风录音 |
