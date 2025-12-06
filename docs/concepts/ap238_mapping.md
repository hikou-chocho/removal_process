### `docs/concepts/ap238_mapping.md`

# AP238 / ISO 14649 Mapping

## 1. 目的

本ドキュメントは、L0 FeatureGraph の各 `feature_type` を STEP AP238 / ISO 14649 / AP224 のフィーチャ定義にマッピングする。

- **目標**: 既存規格との互換性を確保しつつ、実装しやすい JSON スキーマを設計すること
- **範囲**: 幾何フィーチャ（加工条件やツール情報は対象外）

## 2. マッピングポリシー

1. **AP238 を優先**  
   可能な限り AP238 のフィーチャ名 / 構造をベースに命名・設計する

2. **不足部分は AP224 / ISO 14649 を参照**  
   旋削や自由曲面など、AP238 に明示が薄い部分は他プロファイルも参考にする

3. **実装上のシンプルさを重視**  
   CadQuery で実装しやすいパラメータ構造にする  
   ただし表現力が不足しないよう配慮する

## 3. ミーリングフィーチャ

| FeatureGraph `feature_type`         | 規格側の対応フィーチャ                        | 備考                           |
|------------------------------------|-----------------------------------------------|--------------------------------|
| `planar_face_feature`              | planar_face (AP224)                           | フェイスミル／基準面          |
| `round_hole_feature`              | round_hole (ISO 14649-11 / AP224)            | 貫通／止まりフラグを params に持つ |
| `pocket_rectangular_feature`      | pocket (rectangular, AP224)                  | corner_radius を持つ           |
| `profile_outer_feature`           | profile feature (open/closed profile)        | 外形輪郭。selector と組合せ     |

### 3.1 `round_hole_feature` 例

```json
{
  "feature_type": "round_hole_feature",
  "id": "F_H1",
  "csys_ref": "WCS",
  "selector": ">Z",
  "params": {
    "dia": 10.0,
    "depth": 20.0,
    "is_through": false,
    "center": { "x": 0.0, "y": 0.0 }
  }
}
```

AP224 の `round_hole` に該当しつつ、実装上扱いやすい `is_through` ブール値を設けている。

## 4. 旋削フィーチャ

| FeatureGraph `feature_type`            | 規格側の対応フィーチャ            | 備考       |
|---------------------------------------|----------------------------------|-----------|
| `turning_face_feature`                | facing (ISO 14649-12)            | 端面加工   |
| `turning_outer_diameter_feature`      | outer_diameter (ISO 14649-12)    | OD 形状    |
| `turning_inner_diameter_feature`      | inner_diameter (ISO 14649-12)    | ID 形状    |
| `turning_groove_feature`              | groove / recess (ISO 14649-12)   | 溝・逃げ   |

Z–D プロファイルで形状を記述するのが基本となる。

### 4.1 例

```json
{
  "feature_type": "turning_outer_diameter_feature",
  "id": "F_OD1",
  "csys_ref": "WCS",
  "selector": ">Z",
  "params": {
    "profile": [
      { "z": 0.0,  "d": 50.0 },
      { "z": 20.0, "d": 50.0 },
      { "z": 20.0, "d": 40.0 },
      { "z": 40.0, "d": 40.0 },
      { "z": 40.0, "d": 30.0 },
      { "z": 80.0, "d": 30.0 }
    ]
  }
}
```

## 5. 自由曲面 / スワーフ / ブレード

| FeatureGraph `feature_type`  | 規格側の対応フィーチャ／概念              | 備考                           |
|-----------------------------|------------------------------------------|-------------------------------|
| `swarf_surface_feature`     | swarf milling feature (STEP-NC 拡張等)    | 面＋トリム範囲＋厚み          |
| `blade_surface_feature`     | blade / impeller feature                 | 羽根面。ルート／チップなどの区分 |

`swarf_surface_feature` は、基本的に「既存 B-Rep 面の切り出し」として扱う:

### 5.1 例

```json
{
  "feature_type": "swarf_surface_feature",
  "id": "F_SW1",
  "csys_ref": "SETUP_A90C0",
  "selector": ">Z",
  "params": {
    "face_ref": "STEP_FACE_123",
    "trim_uv": {
      "umin": 0.1, "umax": 0.9,
      "vmin": 0.0, "vmax": 1.0
    },
    "thickness": 2.0
  }
}
```

- **face_ref**: 元の STEP / B-Rep の Face ID
- **trim_uv**: UV パラメトリック座標でトリム領域を指定
- **thickness**: 片側厚み（残す／削る方向は CSYS / selector で解釈）

## 6. L0 で決めること / 決めないこと

### L0 で決めること（必須）

- どの CSYS 基準で見るか (`csys_ref`)
- どの方向から見た面か (`selector`)
- 幾何パラメータ（寸法・位置・厚み・トリム範囲）
- フィーチャ同士の関係（ID を通じた参照など）

### L0 では決めないこと（上位レイヤで扱う）

- 工具の種類・番手（エンドミル φ10 など）
- 加工条件（回転数・送り・切込み）
- 実際のツールパス（CL データ）
- 機械ごとの NC コード

これにより、L0 FeatureGraph は **設計意図を失わない最小限のフィーチャ定義** を目指す。