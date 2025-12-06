# removal_process / docs

このフォルダは、除去加工可視化プロジェクトのドキュメント集です。  
実装コード（`api/` / `csharp_client/`）とは独立した「概念」「ルール」「LLM 利用方針」をまとめます。

## 構成

```text
docs/
  README.md
  concepts/
    feature_graph_overview.md
    ap238_mapping.md
    csys_vs_wcs.md
  rules/
    codex_rules.md
```

- **concepts/**  
  実装に依存しないコンセプト文書  
  L0 FeatureGraph、AP238/STEP-NC のマッピング、CSYS / WCS の扱いなど

- **rules/**  
  LLM（"Codex" 的なアシスタント）を使う際のルール  
  プロンプトや出力フォーマット、禁止事項など

## 自然言語と FeatureGraph の位置づけ

本プロジェクトは **「自然言語 → L0 FeatureGraph → removal_process API」** を想定しているが、バックエンド API は常に **構造化 JSON（CaseN / FeatureGraph）** を入力として受け取る。

- **自然言語**は「入力 UI / データセット」のレイヤ
- **L0 FeatureGraph** は「設計の真実（ソース・オブ・トゥルース）」
- **removal_process API** は「L0 から幾何（CadQuery）を生成する層」

自然言語だけで直接 CadQuery や STL を生成することは想定していない。  
あくまで **L0 JSON を経由する** 前提で設計する。

詳細は:

- `concepts/feature_graph_overview.md`
- `rules/codex_rules.md`

を参照。