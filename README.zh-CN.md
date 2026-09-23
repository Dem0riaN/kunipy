# Kunipy

**Kunipy** 是一个基于 Python 的 AI 角色平台，提供持久记忆、人格、Telegram 交互、工具、多模态能力以及可扩展的应用架构。

项目最初受到 [Kuni](https://github.com/Alex2772/kuni) 的启发，并尝试以 Python 实现相关思路。之后代码和架构经过大幅重构与扩展。目前 Kunipy 是独立的 Python 代码库，不包含原 Kuni 的 C++ 源代码。

## 项目状态

| 模块 | 状态 |
|---|---|
| AI 角色 / 人格 | ✅ 已完成 |
| OpenAI-compatible LLM 客户端 | ✅ 已完成 |
| Tool calling | ✅ 已完成 |
| Telegram | ✅ 已完成 |
| 持久日记 | ✅ 已完成 |
| 日记语义搜索 / RAG | ✅ 已完成 |
| 混合长期记忆 | ✅ 已完成 |
| 自动记忆形成 | ✅ 已完成 |
| Working Memory | ✅ 已完成 |
| Sleep / consolidation | ✅ 已完成 |
| 自动日记 RAG 注入 | ✅ 已完成 |
| 图像理解 | ✅ 已完成* |
| 语音识别 | ✅ 已完成* |
| TTS / 语音消息 | ✅ 已完成* |
| 图像生成 | ✅ 已完成* |
| Web search | ✅ 已完成* |
| 贴纸 / 反应 / 消息操作 | ✅ 已完成 |
| 群组管理 | ✅ 已完成* |
| OpenAI-compatible proxy | ✅ 已完成 |
| Prometheus metrics | ✅ 已完成 |
| 文本文档提取 | 🟡 部分完成 |
| Desktop 角色 | 🚧 开发中 |
| Live2D / desktop rendering | 🚧 开发中 |
| 视频消息帧提取 | 📋 计划中 |
| 更多 document/media extractors | 📋 计划中 |

\* 需要相应的外部 backend 和/或配置。

详细状态说明请参阅 [docs/status.md](docs/status.md)。

## 主要功能

- 可编辑的角色与外观 prompt；
- 基于 TDLib 的 Telegram userbot；
- 带 embeddings 和语义搜索的持久日记；
- ChromaDB + SQLite 混合记忆；
- 从对话中自动提取长期记忆；
- 用于承诺、计划和待处理上下文的 working memory；
- sleep/consolidation；
- 多模态消息处理；
- Stable Diffusion-compatible API 图像生成；
- TTS 和语音消息；
- Web search；
- OpenAI-compatible proxy；
- Prometheus metrics；
- dependency injection 和分层架构。

## 快速开始

需要 Python 3.11+、OpenAI-compatible LLM endpoint，以及 Telegram（如启用）所需的 API ID/hash。

```bash
git clone https://github.com/Dem0riaN/kunipy.git
cd kunipy

python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -e .

python run.py
```

完整配置请参考 `config.example.toml`。不要将真实密钥提交到 Git。

## 文档

- [项目状态](docs/status.md)
- [安装](docs/installation.md)
- [配置](docs/configuration.md)
- [架构](docs/architecture.md)
- [功能](docs/features.md)
- [记忆](docs/memory.md)
- [Proxy](docs/proxy.md)
- [测试](docs/testing.md)
- [项目来源与署名](docs/origins.md)
- [仓库审计](docs/audit.md)

## 语言

- [English](README.md)
- [Русский](README.ru.md)
- [日本語](README.ja.md)

## 许可证

Kunipy 使用 [LICENSE](LICENSE) 中的自定义许可证。

该许可证允许在其规定条件下免费使用、修改和再发布，要求保留 attribution，并禁止出售受该许可证覆盖的 Kunipy 材料。

第三方依赖、模型、资源和其他外部材料仍受其各自许可证约束。
