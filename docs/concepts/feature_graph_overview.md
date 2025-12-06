### `docs/concepts/feature_graph_overview.md`

# L0 FeatureGraph Overview

## 1. 目的

L0 FeatureGraph は、除去加工プロセスにおける「フィーチャ定義」のレイヤであり、

- **設計意図（どの面を、どれだけ、どのように削るか）** を
- **中立な JSON 構造** で表現し、
- 後段の幾何生成・プロセス計画・ツールパス生成の基準

となることを目的とする。

ここでは CAM やツールパスまでは扱わず、**形状フィーチャの定義** にフォーカスする。

## 2. 位置づけ（レイヤモデル）

プロジェクト全体は、以下のようなレイヤ構造を想定している。

- **L0: Feature Definition & Feature Model Layer**
  - 本ドキュメントの対象
  - AP238 / ISO 14649 ベースのフィーチャ定義
- **L1: Product Geometry & Source CAD Layer**
  - L0 に基づき CadQuery や B-Rep 形状を構築
  - STEP / STL などの幾何データ
- **L2: Feature-Based Process Planning Layer**
  - L0 フィーチャから加工戦略・工具候補などを選定
  - 本プロジェクトではスコープ外（将来拡張）
- **L3 〜 L5: Toolpath / NC / Machine Layer**
  - 既存 CAM や外部システムに委譲

removal_process リポジトリは、現状 **L0 → L1** にフォーカスしている。

## 3. FeatureGraph の基本構造

### 3.1 ルート構造（例）

```json
{
  "units": "mm",
  "origin": "world",
  "stock": {
    "type": "block",
    "params": { "w": 120, "h": 40, "d": 60 }
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
      "id": "F1_TOP_DATUM",
      "csys_ref": "WCS",
      "selector": ">Z",
      "params": { "depth": 2.0 }
    },
    {
      "feature_type": "pocket_rectangular_feature",
      "id": "F2_RECT_POCKET",
      "csys_ref": "WCS",
      "selector": ">Z",
      "params": {
        "w": 40.0,
        "d": 30.0,
        "depth": 10.0,
        "corner_r": 4.0,
        "center": { "x": 0, "y": 0 }
      }
    }
  ]
}
```
ポイント:

stock … 初期素材（ブロック / シリンダ等）

csys_list … World / 各セットアップの CSYS 定義

features[] … 加工フィーチャの列（順序は加工順に近いが、厳密なプロセスではない）

### 3.2 Feature オブジェクト共通項目

各 feature は、少なくとも以下を持つ。

- **feature_type**  
  AP238 / ISO 14649 に対応するフィーチャ種別  
  例: `planar_face_feature`, `round_hole_feature`, `pocket_rectangular_feature`,  
  `turning_outer_diameter_feature`, `swarf_surface_feature` など

- **id**  
  JSON 内で一意な識別子

- **csys_ref**  
  加工基準となる CSYS 名（`csys_list` の `name` と対応）

- **selector**  
  CSYS 上での方向指定や面集合を簡易に表現  
  例: `">Z"`（+Z 向きの外側面）、`"<Z"`（-Z 向き）、`"|X"`（±X 側面など）

- **params**  
  フィーチャ固有パラメータ  
  寸法・位置・オフセット・トリム範囲などを含む

## 4. 主なフィーチャカテゴリ

### 4.1 ミーリング系

- **planar_face_feature**  
  基準面のフェイスミル

- **round_hole_feature**  
  直円穴（貫通 / 止まり）

- **pocket_rectangular_feature**  
  直方形ポケット（角 R 指定）

- **profile_outer_feature**  
  外形プロファイル（外周エンドミル）

AP238 / AP224 のフィーチャ名と 1 対 1 対応させる方針。  
詳細は `ap238_mapping.md` を参照。

### 4.2 旋削系

- **turning_face_feature**
- **turning_outer_diameter_feature**
- **turning_inner_diameter_feature**
- **turning_groove_feature**

回転対称形状の場合、Z–D プロファイルで定義するフィーチャが中心になる。

### 4.3 自由曲面・ブレード系

- **swarf_surface_feature**  
  自由曲面をスワーフ加工するための面  
  通常は既存 B-Rep Face への参照 + トリム範囲（UV）で定義

- **blade_surface_feature**  
  タービン等の翼形状

これらは L0 では「どの面をどの厚みで残すか」までを対象とし、  
工具姿勢やパス分割は L2 以降で扱う。

## 5. 自然言語との関係

自然言語での指示は、主に次のようなスタイルを想定する。

> 100×60×20 mm のブロックを用意し、  
> 上面を 2mm 荒取りして基準面を作る。  
> その面から、中心 40×30 mm の R4 ポケットを深さ 10mm 掘る。

LLM（"Codex"）の役割は:

- この自然言語を解析し
- 適切な `feature_type` と `params` を持つ FeatureGraph JSON を組み立て
- `removal_process` API に渡せる形に整える

**自然言語から直接 STL / STEP を生成しない** 点が重要である。  
常に L0 FeatureGraph を経由し、設計意図を明示的に残す。