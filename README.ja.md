# Kunipy

**Kunipy** は、永続メモリ、人格、Telegram 連携、ツール、マルチモーダル機能、拡張可能なアプリケーションアーキテクチャを備えた Python ベースの AI キャラクタープラットフォームです。

このプロジェクトは当初、[Kuni](https://github.com/Alex2772/kuni) に着想を得て、関連するアイデアを Python で実装するところから始まりました。その後、コードとアーキテクチャは大幅に再設計・拡張されています。現在の Kunipy は独立した Python コードベースであり、元の Kuni の C++ ソースコードは含みません。

## プロジェクトの状態

| 領域 | 状態 |
|---|---|
| AI キャラクター / 人格 | ✅ 完成 |
| OpenAI-compatible LLM クライアント | ✅ 完成 |
| Tool calling | ✅ 完成 |
| Telegram | ✅ 完成 |
| 永続日記 | ✅ 完成 |
| 日記のセマンティック検索 / RAG | ✅ 完成 |
| ハイブリッド長期メモリ | ✅ 完成 |
| 自動メモリ形成 | ✅ 完成 |
| Working Memory | ✅ 完成 |
| Sleep / consolidation | ✅ 完成 |
| 自動日記 RAG 注入 | ✅ 完成 |
| 画像理解 | ✅ 完成* |
| 音声認識 | ✅ 完成* |
| TTS / 音声メッセージ | ✅ 完成* |
| 画像生成 | ✅ 完成* |
| Web search | ✅ 完成* |
| ステッカー / リアクション / メッセージ操作 | ✅ 完成 |
| グループ管理 | ✅ 完成* |
| OpenAI-compatible proxy | ✅ 完成 |
| Prometheus metrics | ✅ 完成 |
| テキスト文書抽出 | 🟡 部分的 |
| Desktop キャラクター | 🚧 開発中 |
| Live2D / desktop rendering | 🚧 開発中 |
| 動画メッセージのフレーム抽出 | 📋 計画中 |
| 追加の document/media extractors | 📋 計画中 |

\* 対応する外部 backend および/または設定が必要です。

詳細は [docs/status.md](docs/status.md) を参照してください。

## 主な機能

- 編集可能なキャラクター / 外見 prompt;
- TDLib ベースの Telegram userbot;
- embeddings とセマンティック検索を備えた永続日記;
- ChromaDB + SQLite のハイブリッドメモリ;
- 会話からの長期記憶の自動抽出;
- promise / plan / pending context 用の working memory;
- sleep/consolidation;
- マルチモーダルメッセージ処理;
- Stable Diffusion-compatible API による画像生成;
- TTS と音声メッセージ;
- Web search;
- OpenAI-compatible proxy;
- Prometheus metrics;
- dependency injection とレイヤードアーキテクチャ。

## クイックスタート

Python 3.11+、OpenAI-compatible LLM endpoint、そして Telegram を有効にする場合は Telegram API ID/hash が必要です。

```bash
git clone https://github.com/Dem0riaN/kunipy.git
cd kunipy

python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -e .

python run.py
```

完全な設定については `config.example.toml` を参照してください。実際の API キーやパスワードを Git にコミットしないでください。

## ドキュメント

- [プロジェクトの状態](docs/status.md)
- [インストール](docs/installation.md)
- [設定](docs/configuration.md)
- [アーキテクチャ](docs/architecture.md)
- [機能](docs/features.md)
- [メモリ](docs/memory.md)
- [Proxy](docs/proxy.md)
- [テスト](docs/testing.md)
- [プロジェクトの由来と帰属](docs/origins.md)
- [リポジトリ監査](docs/audit.md)

## 言語

- [English](README.md)
- [Русский](README.ru.md)
- [中文](README.zh-CN.md)

## ライセンス

Kunipy は [LICENSE](LICENSE) のカスタムライセンスで配布されます。

このライセンスは、条件の範囲内での無料使用・変更・再配布を認め、attribution の保持を要求し、対象となる Kunipy の素材の販売を禁止します。

サードパーティ製の依存関係、モデル、アセット、その他の外部素材には、それぞれのライセンスが適用されます。
