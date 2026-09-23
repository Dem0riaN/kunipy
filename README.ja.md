# Kunipy

**Kunipy は、Telegram 統合、長期メモリ、編集可能なキャラクター人格、
バックグラウンドサービス、OpenAI-compatible API を備えた Python 製 AI
キャラクターランタイムです。**

このプロジェクトは当初、
[Alex2772/kuni](https://github.com/Alex2772/kuni) のアイデアと一部コードを
基に始まりました。しかし、その後大幅な再設計と拡張が行われています。
現在の Kunipy は単純な Python ポートや `kuni` の drop-in replacement と
いうより、独立した Python プロジェクトとして扱う方が正確です。

> **状態:** 開発継続中。以下の文書は **2026-09-23** 時点のリポジトリを確認
> した結果に基づいています。

## 言語

- [English](README.md)
- [Русский](README.ru.md)
- [简体中文](README.zh-CN.md)
- [日本語](README.ja.md)

## 主な機能

- TDLib / `aiotdlib` による Telegram 統合
- OpenAI-compatible LLM / embedding クライアント
- Markdown ファイルで編集できるキャラクター人格
- ChromaDB + SQLite による長期メモリ
- 会話からの自動メモリ抽出
- 約束・計画・短期コンテキストを保持する working memory
- Markdown diary とセマンティック検索
- Diary Auto-RAG
- worker / sleep / proactive バックグラウンドサービス
- 外部 backend を設定した場合の vision / STT / TTS / 画像生成 / web search
- OpenAI-compatible proxy
- Prometheus 形式の LLM 使用量メトリクス
- オプションの desktop-character 基盤

一部の機能はデフォルトで無効であり、外部サービスや追加コンポーネントを
必要とします。

## クイックスタート

Python **3.11+** が必要です。

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp config.example.toml config.toml
python run.py
```

その後 `config.toml` を設定してください。Telegram を有効にする場合は
Telegram API ID/hash が必要です。

詳細:

- [`docs/installation.md`](docs/installation.md)
- [`docs/configuration.md`](docs/configuration.md)

## ドキュメント

| トピック | ドキュメント |
|---|---|
| インデックス | [`docs/README.md`](docs/README.md) |
| インストール | [`docs/installation.md`](docs/installation.md) |
| 設定 | [`docs/configuration.md`](docs/configuration.md) |
| アーキテクチャ | [`docs/architecture.md`](docs/architecture.md) |
| 機能 | [`docs/features.md`](docs/features.md) |
| メモリと diary | [`docs/memory.md`](docs/memory.md) |
| Proxy | [`docs/proxy.md`](docs/proxy.md) |
| テスト | [`docs/testing.md`](docs/testing.md) |
| プロジェクトの由来 | [`docs/origins.md`](docs/origins.md) |
| 監査 | [`docs/audit.md`](docs/audit.md) |

## 由来

Kunipy は当初
[Alex2772/kuni](https://github.com/Alex2772/kuni) をベースとして始まりました。

現在は Python アーキテクチャ、メモリ、persona、diary、worker、proxy、
desktop などが大幅に変更・拡張されています。

## ライセンス

[`LICENSE`](LICENSE) を参照してください。

このプロジェクト固有のライセンスでは、無料での使用・変更・再配布を認める
一方、ソフトウェアや変更版の販売を禁止し、Kunipy および元となった
`kuni` の帰属表示を要求します。

なお、Kunipy の作業開始時点で upstream の `kuni` リポジトリにはライセンス
がありませんでした。そのため、このライセンスは他の著作権者が所有する
コードについて権利を新たに付与するものではありません。
