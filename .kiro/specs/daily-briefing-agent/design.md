# Paperboy 📬 · 设计文档

> **Your AI paperboy — turns newsletter chaos into a 30-second morning briefing.**

---

## 1. 品牌与定位

- **项目名**：Paperboy
- **Tagline**：`📬 Your AI paperboy — turns newsletter chaos into a 30-second morning briefing.`
- **定位**：小而美的自托管 AI 邮件简报 Agent，支持插件化扩展
- **License**：MIT
- **GitHub Topics**：`agent` `llm` `gmail` `newsletter` `productivity` `qwen` `python` `automation`

---

## 2. 架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                   GitHub Actions（每日定时 / 手动）               │
│                              │                                   │
│                              ▼                                   │
│                          main.py                                 │
│   ┌──────────┐      ┌──────────┐      ┌──────────┐   ┌────────┐│
│   │ Sources  │  →   │  Agent   │  →   │Summarizer│ → │ Sinks  ││
│   │(插件协议)│      │(LLM循环) │      │ (渲染)   │   │(插件)  ││
│   └──────────┘      └──────────┘      └──────────┘   └────────┘│
│        │                 │                                       │
│        ▼                 ▼                                       │
│   GmailSource       LLM Provider                                 │
│   RSSSource(v2)     (Qwen/OpenAI/DeepSeek/Ollama)               │
└─────────────────────────────────────────────────────────────────┘
```

### 插件协议

```python
class Source(Protocol):
    """数据来源插件"""
    def fetch(self) -> list[EmailItem]: ...

class Sink(Protocol):
    """推送渠道插件"""
    def send(self, briefing: DailyBriefing) -> None: ...
```

内置实现：
- **Sources**: `GmailSource`（v1）, `RSSSource`（v2 预留）
- **Sinks**: `EmailSink`（v1）, `TelegramSink`（v2 预留）

---

## 3. 项目结构

```
paperboy/  (hello_world repo)
├── README.md                        # 爆款 README
├── pyproject.toml                   # 依赖与元数据
├── .env.example                     # 环境变量模板
├── .gitignore                       # Python + .env
├── LICENSE                          # MIT
├── .github/workflows/
│   └── daily.yml                    # 定时触发
├── src/
│   ├── __init__.py
│   ├── main.py                      # 入口 + --demo 模式
│   ├── config.py                    # pydantic-settings 配置
│   ├── models.py                    # 数据模型
│   ├── agent.py                     # 最小 agent 循环
│   ├── summarizer.py                # 提示词 + JSON 解析
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── base.py                  # LLMClient Protocol
│   │   └── openai_compatible.py     # 统一实现
│   ├── sources/
│   │   ├── __init__.py
│   │   ├── base.py                  # Source Protocol
│   │   └── gmail.py                 # GmailSource
│   ├── sinks/
│   │   ├── __init__.py
│   │   ├── base.py                  # Sink Protocol
│   │   └── email.py                 # EmailSink (SMTP)
│   └── templates/
│       ├── briefing.html            # HTML 邮件模板
│       └── briefing.txt             # 纯文本模板
├── examples/
│   └── demo_output.json             # demo 模式的示例数据
└── tests/
    └── test_smoke.py
```

---

## 4. 关键设计

### 4.1 LLM 多 Provider（一份代码）

所有 Provider 兼容 OpenAI Chat Completions 协议：

| Provider   | base_url                                                 | 默认 model      |
|------------|----------------------------------------------------------|-----------------|
| `qwen`     | `https://dashscope.aliyuncs.com/compatible-mode/v1`      | `qwen-plus`     |
| `openai`   | `https://api.openai.com/v1`                              | `gpt-4o-mini`   |
| `deepseek` | `https://api.deepseek.com/v1`                            | `deepseek-chat` |
| `ollama`   | `http://localhost:11434/v1`                              | `qwen2.5`       |

### 4.2 最小 Agent

```python
def run(emails) -> DailyBriefing:
    messages = [system_prompt, user_prompt(emails_preview)]
    tools = [expand_email]
    for _ in range(MAX_TURNS=3):
        resp = llm.chat(messages, tools)
        if resp.tool_calls:
            execute & append results
            continue
        return parse_json(resp.content)
```

### 4.3 Demo 模式

`python -m src.main --demo`：
- 不连 Gmail、不调 LLM
- 使用 `examples/demo_output.json` 硬编码数据
- 渲染简报并输出到终端 + 保存为 HTML 文件
- 让用户**零配置**看到产品效果

### 4.4 简报格式

LLM 返回 JSON → 渲染为 HTML + 纯文本：

```
📬 每日简报 · 2026-05-14
共处理 12 封订阅邮件

⭐ Top 3 必读
1. [标题] · 一句话总结
   来源：xxx · 原文链接

📰 其他速览
- [来源] 标题：要点

🔖 关键词雷达
AI Agent / RAG / Rust async
```

---

## 5. 配置

```env
GMAIL_ADDRESS=you@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
GMAIL_LABEL=Newsletters
LOOKBACK_HOURS=24
LLM_PROVIDER=qwen
QWEN_API_KEY=sk-xxx
QWEN_MODEL=qwen-plus
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=deepseek-chat
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=qwen2.5
MAX_AGENT_TURNS=3
MAX_EMAIL_PREVIEW_CHARS=500
```

---

## 6. 运行方式

- **GitHub Actions**：UTC 0:00 (北京 8:00) 定时 + workflow_dispatch
- **本地**：`python -m src.main`（需 `.env`）
- **Demo**：`python -m src.main --demo`（零配置）

---

## 7. 依赖（精简）

```
imap-tools>=1.6
openai>=1.40
pydantic>=2.7
pydantic-settings>=2.3
python-dotenv>=1.0
```

---

## 8. Roadmap

| 版本 | 内容 |
|------|------|
| **v1.0** | Gmail → Qwen → 邮件简报（本次） |
| v1.1 | RSS Source 插件 |
| v1.2 | Telegram Sink |
| v2.0 | `paperboy podcast` — 简报转 TTS |
| v2.1 | `paperboy chat` — 对简报提问 |
| v3.0 | Web 配置面板 + 多用户 |
