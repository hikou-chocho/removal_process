### `docs/rules/codex_rules.md`


# Codex Rules (LLM 利用ルール)

> ★ このドキュメントは、removal_process / natural-language-to-feature-graph 系の  
>   カスタム GPT / LLM を運用する際のルールをまとめたものです。

## 1. 役割の整理

LLM（以下 "Codex"）の役割は **2 段階** に分かれる。

1. **自然言語 → L0 FeatureGraph JSON**  
   日本語 / 英語の加工指示から、L0 FeatureGraph JSON を生成する  
   生成結果は removal_process のバックエンドに渡される

2. **設計レビュー / スキーマレビュー**  
   `docs/` や `schemas/*.json` を読み、整合性チェックや改善案を出す

**重要:**  
Codex は **直接 STL / STEP / G-code を生成しない**。  
常に **L0 JSON → removal_process API → CadQuery** という流れを前提とする。

## 2. 出力フォーマット

### 2.1 FeatureGraph 生成モード

- 出力は **必ず JSON 単体** とし、前後に説明文を付けない
- JSON のトップレベルは FeatureGraph スキーマに準拠する

例:

```json
{
  "units": "mm",
  "origin": "world",
  "stock": {
    "type": "block",
    "params": { "w": 100, "h": 20, "d": 60 }
  },
  "csys_list": [
    {
      "name": "WCS",
      "role": "world",
      "origin": { "x": 0, "y": 0, "z": 0 },
      "rpy_deg": { "r": 0, "p": 0, "y": 0 }
    }
  ],
  "features": [
    {
      "feature_type": "planar_face_feature",
      "id": "F_TOP_DATUM",
      "csys_ref": "WCS",
      "selector": ">Z",
      "params": { "depth": 2.0 }
    },
    {
      "feature_type": "round_hole_feature",
      "id": "F_CENTER_HOLE",
      "csys_ref": "WCS",
      "selector": "<Z",
      "params": {
        "dia": 10.0,
        "depth": 20.0,
        "is_through": false,
        "center": { "x": 0.0, "y": 0.0 }
      }
    }
  ]
}
```

### 2.2 説明・レビュー・議論モード

- ユーザーが「説明して」「レビューして」と頼んだ場合のみ、文章で回答する
- その際も、実際に API に渡す JSON 例を一緒に提示できると望ましい

## 3. 自然言語入力の扱い

### 3.1 想定される入力スタイル

- 手順書スタイル
- 箇条書き
- 途中で条件変更が入る記述

例:

> 50×30×20 のブロックを用意する。  
> 上面を 2mm 荒取りして基準面を作る。  
> 次に、外周を 45×25 になるように 5mm 落とす。  
> 最後に、中心に直径 5mm 深さ 10mm の穴をあける。

Codex はこれを **複数フィーチャ** に分解する必要がある。

- `planar_face_feature`（基準面）
- `profile_outer_feature`（外周形状）
- `round_hole_feature`（穴）

### 3.2 禁止事項

- 自然言語の指示をそのまま `params.comment` に丸投げし、他のパラメータを埋めないまま返すこと
- スキーマに存在しない適当なフィールドを追加すること
- `TASK:` や `TODO:` といったメタ文言を JSON に含めること

以前のドキュメントで使用していた「TASK～」という見出し・書式は **すべて廃止** し、現在は **「自然言語 → L0 JSON」** という責務だけに集中させる。

## 4. スキーマ遵守ルール

### 4.1 スキーマが与えられている場合

ユーザーが `schema_*.json` を提示した場合:

1. まずスキーマをよく読み、`required` / `enum` / `oneOf` を理解する
2. 生成する JSON は、スキーマの制約を満たすようにする
3. 不明なパラメータは
   - むやみに推測せず、安全なデフォルト か
   - ユーザーに「どちらの意図か」を尋ねる

### 4.2 スキーマが与えられていない場合

- 既存の FeatureGraph 例を参考にしつつ、可能な範囲で一貫したフィールド名・構造を用いる
- とくに `feature_type` は **AP238 マッピングに合わせた名前** を選ぶ

## 5. CaseN / removal_process との関係

歴史的には:

- CaseN.json という「工程＋CadQuery 直結」スタイルの JSON が先にあり、
- 現在はそれを L0 FeatureGraph ベースの設計に再整理している

Codex が行うべきことは:

- **古い CaseN 形式の JSON が与えられた場合**  
  → 新しい FeatureGraph 形式に変換する提案を行う

- **新規の自然言語定義から**  
  → 直接 FeatureGraph を組み立てる

CaseN（直接 CadQuery 操作）に特化したロジックは、今後増やさない。  
あくまで **FeatureGraph を起点としたアーキテクチャ** を優先する。

## 6. 安全策・フォールバック

自然言語が曖昧で、複数解釈があり得る場合:

- 最も一般的な解釈（対称・中心・原点基準など）を採用しつつ、必要なら「ここは仮定に基づく」とコメントを添える

大規模な修正が必要な場合:

- 直接 JSON を書き換えるのではなく、「旧バージョン」と「提案バージョン」を並べて提示する

## 7. このルール文書の更新方針

- 実装側（Python / C#）の仕様変更に合わせて、ここも頻繁に更新する
- 「自然言語で何をどこまでやるか」の方針が変わった場合、
  1. まずこの `codex_rules.md` を更新し、
  2. その後にスキーマや README を追随させる

このファイルは、**「LLM をどう使うか」の真実となるドキュメント** として扱う。