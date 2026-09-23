# Kunipy

**Kunipy 是一个基于 Python 的 AI 角色运行时，提供 Telegram 集成、长期记忆、
可编辑角色人格、后台服务以及 OpenAI-compatible 接口。**

项目最初基于 [Alex2772/kuni](https://github.com/Alex2772/kuni) 的思路和部分
代码开始，但之后进行了大量重构和扩展。因此现在更适合将 Kunipy 视为一个
独立的 Python 项目，而不是简单的 Python 移植版。

> **状态：** 持续开发中。本文档基于 **2026-09-23** 对仓库当前状态的检查。

## 语言

- [English](README.md)
- [Русский](README.ru.md)
- [简体中文](README.zh-CN.md)
- [日本語](README.ja.md)

## 主要功能

当前代码库包含：

- 基于 TDLib / `aiotdlib` 的 Telegram 集成；
- OpenAI-compatible LLM 与 embedding 客户端；
- 以 Markdown 文件保存和编辑的角色人格；
- ChromaDB + SQLite 长期记忆；
- 从近期对话中自动提取记忆；
- 保存承诺、计划和短期上下文的 working memory；
- Markdown diary 以及语义检索；
- Diary Auto-RAG；
- 后台 worker、sleep 和 proactive 服务；
- 在配置外部 backend 后使用 vision、STT、TTS、图像生成和 web search；
- OpenAI-compatible proxy；
- Prometheus LLM 使用量指标；
- 可选的 desktop-character 基础设施。

部分功能默认关闭，部分功能依赖外部服务。

## 快速开始

需要 Python **3.11+**。

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp config.example.toml config.toml
python run.py
```

然后编辑 `config.toml`。启用 Telegram 时，需要 Telegram API ID/hash。

详细说明：

- [`docs/installation.md`](docs/installation.md)
- [`docs/configuration.md`](docs/configuration.md)

## 文档

| 主题 | 文档 |
|---|---|
| 文档索引 | [`docs/README.md`](docs/README.md) |
| 安装 | [`docs/installation.md`](docs/installation.md) |
| 配置 | [`docs/configuration.md`](docs/configuration.md) |
| 架构 | [`docs/architecture.md`](docs/architecture.md) |
| 功能 | [`docs/features.md`](docs/features.md) |
| 记忆与 diary | [`docs/memory.md`](docs/memory.md) |
| Proxy | [`docs/proxy.md`](docs/proxy.md) |
| 测试 | [`docs/testing.md`](docs/testing.md) |
| 项目来源 | [`docs/origins.md`](docs/origins.md) |
| 审计 | [`docs/audit.md`](docs/audit.md) |

## 来源

Kunipy 最初基于
[Alex2772/kuni](https://github.com/Alex2772/kuni)。

现在的 Kunipy 已经经过大量重新设计和扩展，包括 Python 架构、记忆系统、
角色系统、diary、worker、proxy 以及 desktop 方向。

## 许可证

请参阅 [`LICENSE`](LICENSE)。

项目许可证允许免费使用、修改和再分发，但禁止出售软件或修改版本，并要求
保留项目来源和原始 `kuni` 项目的署名信息。

由于开始 Kunipy 工作时 upstream `kuni` 仓库没有提供许可证，本许可证不会
声称替其他版权所有者授予相关代码的权利。
