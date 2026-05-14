<div align="center">

```
       📬
   ┌─────────┐
   │ paperboy│
   └─────────┘
```

# Paperboy

**Your AI paperboy — turns newsletter chaos into a 30-second morning briefing.**

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![GitHub Actions](https://img.shields.io/badge/runs_on-GitHub_Actions-2088FF.svg)](https://github.com/features/actions)
[![LLM](https://img.shields.io/badge/LLM-Qwen_|_OpenAI_|_DeepSeek-orange.svg)](#llm-配置)

*Subscribe to 50 newsletters. Read zero. Get one beautiful briefing every morning.*

</div>

---

## The Problem

You subscribe to newsletters because they're valuable. But they pile up, create anxiety, and you never actually read them. Sound familiar?

## The Solution

Paperboy is a **tiny, self-hosted AI agent** that:

1. 📥 Pulls your newsletter emails from Gmail every morning
2. 🧠 Uses AI to distill them into a structured briefing
3. 📬 Sends you ONE beautiful email with everything that matters

**Zero infrastructure cost** — runs free on GitHub Actions.

---

## 📸 What You Get

Every morning at 8:00 AM, you receive an email like this:

```
📬 每日简报 · 2026-05-14
共处理 12 封订阅邮件

⭐ Top 3 必读
1. GPT-5 发布：多模态推理能力大幅提升
   OpenAI 正式发布 GPT-5，推理成本降低 60%。
   来源: AI Weekly · [原文]

2. Rust 在后端开发的采用率突破 30%
   Stack Overflow 调查显示 Rust 后端使用率首次超 30%。
   来源: The Pragmatic Engineer · [原文]

3. 一个人如何用 AI Agent 管理 10 个开源项目
   独立开发者分享 AI Agent 自动化 issue/PR/changelog 工作流。
   来源: Indie Hacker Weekly · [原文]

📰 其他速览
- [JavaScript Weekly] TypeScript 6.0: pattern matching + 改进类型推断
- [Data Engineering] DuckDB 1.2 内置向量搜索
- ...

🔖 关键词雷达
AI Agent / GPT-5 / Rust / TypeScript / 向量搜索
```

HTML version is even prettier — with colors, badges, and links. ✨

---

## ⚡ Quick Start

### Option 1: Try it now (demo mode, zero config)

```bash
git clone https://github.com/guduzhixing/hello_world.git paperboy
cd paperboy
pip install -e .
python -m src.main --demo
```

This shows a sample briefing with no Gmail or API key needed.

### Option 2: Full setup (5 minutes)

**1. Gmail setup:**
- Enable 2-Step Verification in your Google Account
- Generate an [App Password](https://myaccount.google.com/apppasswords)
- Create a Gmail label called `Newsletters`
- Set up a filter to auto-label your newsletter subscriptions

**2. Get your LLM API key:**
- [DashScope Console](https://dashscope.console.aliyun.com/) → Create API Key (starts with `sk-`)

**3. Configure:**

```bash
cp .env.example .env
# Edit .env with your credentials
```

**4. Run:**

```bash
python -m src.main
```

---

## 🤖 Deploy on GitHub Actions (Recommended)

Run Paperboy for **free** on GitHub Actions — no server needed.

1. Fork this repository
2. Go to **Settings → Secrets → Actions** and add:

| Secret | Value |
|--------|-------|
| `GMAIL_ADDRESS` | your-email@gmail.com |
| `GMAIL_APP_PASSWORD` | your 16-char app password |
| `QWEN_API_KEY` | sk-your-dashscope-key |

3. Done! Paperboy runs automatically every day at 8:00 AM (Beijing time).

To test immediately: **Actions → Daily Briefing → Run workflow**

---

## 🔧 LLM 配置

Paperboy supports multiple LLM providers through a unified interface. Switch by changing one env var:

```env
LLM_PROVIDER=qwen    # Options: qwen / openai / deepseek / ollama
```

| Provider | Model | Cost | Best For |
|----------|-------|------|----------|
| **Qwen** (default) | qwen-plus | ~¥0.01/briefing | Chinese content, best value |
| OpenAI | gpt-4o-mini | ~$0.01/briefing | English content |
| DeepSeek | deepseek-chat | ~¥0.005/briefing | Cheapest |
| Ollama | qwen2.5 | Free (local) | Privacy, offline |

### Using Ollama (fully local, free)

```bash
# Install Ollama, then:
ollama pull qwen2.5
LLM_PROVIDER=ollama python -m src.main
```

---

## 🏗️ Architecture

```
Gmail IMAP ──→ Agent (LLM + tools) ──→ HTML Email ──→ Gmail SMTP
                     │
                     ├── expand_email tool (on-demand full text)
                     └── structured JSON output
```

### Plugin System

Paperboy uses a simple plugin protocol for extensibility:

```python
# Add a new source (e.g., RSS, Twitter)
class MySource:
    def fetch(self) -> list[EmailItem]: ...

# Add a new sink (e.g., Telegram, Feishu)
class MySink:
    def send(self, briefing, html, text) -> None: ...
```

---

## 📁 Project Structure

```
├── src/
│   ├── main.py              # Entry point + CLI
│   ├── config.py            # Configuration (pydantic-settings)
│   ├── models.py            # Data models
│   ├── agent.py             # Minimal agent loop (LLM + tools)
│   ├── summarizer.py        # Prompts + rendering
│   ├── llm/                 # LLM abstraction (multi-provider)
│   ├── sources/             # Source plugins (Gmail, ...)
│   ├── sinks/               # Sink plugins (Email, ...)
│   └── templates/           # HTML & text email templates
├── examples/
│   └── demo_output.json     # Sample data for --demo mode
├── .github/workflows/
│   └── daily.yml            # GitHub Actions schedule
└── .env.example             # Configuration template
```

---

## 🆚 Why Paperboy?

| Feature | Paperboy | Newsletter Glue | Manual Reading |
|---------|----------|-----------------|----------------|
| AI summarization | ✅ | ❌ | ❌ |
| Multi-LLM (Qwen/OpenAI/Local) | ✅ | ❌ | — |
| Self-hosted & free | ✅ | ❌ (paid) | — |
| Plugin system | ✅ | ❌ | — |
| Setup time | 5 min | 30 min | — |
| Daily time cost | 30 sec | 5 min | 30+ min |
| Privacy | ✅ Your data stays yours | ❌ | ✅ |

---

## 🗺️ Roadmap

- [x] v1.0 — Gmail → LLM → Email briefing
- [ ] v1.1 — RSS source plugin
- [ ] v1.2 — Telegram / Feishu sink
- [ ] v2.0 — `paperboy podcast` — briefing as audio (TTS)
- [ ] v2.1 — `paperboy chat` — ask questions about today's briefing
- [ ] v3.0 — Web config panel + multi-user

---

## 🤝 Contributing

Contributions are welcome! Some good first issues:

- Add RSS source plugin
- Add Telegram sink
- Improve HTML email template design
- Add weekly summary mode
- Support more LLM providers

---

## 📄 License

[MIT](LICENSE) — Use it however you want.

---

<div align="center">

**If Paperboy saves you time, give it a ⭐**

Made with ☕ by [guduzhixing](https://github.com/guduzhixing)

</div>
