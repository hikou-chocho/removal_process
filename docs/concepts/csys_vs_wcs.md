### `docs/concepts/csys_vs_wcs.md`

# CSYS vs WCS

## 1. 用語

- **WCS (World Coordinate System)**  
  ワールド座標系。機械原点に近い概念  
  `origin: "world"` のベースとなる座標系

- **CSYS (Coordinate System for Setup)**  
  各セットアップ（割り出し角度・チャック基準など）での作業座標系  
  ワーク側から見た「加工基準座標」

removal_process では、WCS/CSYS と CAD 内の Workplane を **明示的に区別して扱う**。

## 2. JSON 定義例

```json
"csys_list": [
  {
    "name": "WCS",
    "role": "world",
    "origin": { "x": 0, "y": 0, "z": 0 },
    "rpy_deg": { "r": 0, "p": 0, "y": 0 }
  },
  {
    "name": "SETUP_A90C0_FRONT",
    "role": "setup",
    "origin": { "x": 0, "y": 0, "z": 0 },
    "rpy_deg": { "r": 90, "p": 0, "y": 0 }
  }
]
```

- **role**  
  - `"world"`: 基準 WCS
  - `"setup"`: 割り出しなど、追加セットアップ

- **rpy_deg**  
  WCS に対する回転角（Roll, Pitch, Yaw）

## 3. フィーチャからの参照

各フィーチャは `csys_ref` で、どの CSYS を基準に寸法を解釈するかを指定する。

```json
{
  "feature_type": "pocket_rectangular_feature",
  "id": "F_P1",
  "csys_ref": "SETUP_A90C0_FRONT",
  "selector": ">Z",
  "params": {
    "w": 40,
    "d": 20,
    "depth": 10,
    "center": { "x": 0, "y": 0 }
  }
}
```

ここで:

- `selector: ">Z"` は `SETUP_A90C0_FRONT` の Z+ 方向を意味する
- CadQuery 実装では
  1. WCS → CSYS への変換
  2. CSYS 上での Workplane 定義
  3. その上でのスケッチ／押し込み
  
  を行う。

## 4. 割り出し 5 軸と同時 5 軸

### 割り出し 5 軸 (3+2)

- CSYS を「離散的に切り替える」イメージ
- `csys_list` に A0C0, A90C0, A90C90 などのセットアップを列挙
- 各フィーチャはどのセットアップで加工されるかを `csys_ref` で指定

### 同時 5 軸

- 工具姿勢が連続的に変化
- L0 では「代表となる CSYS + 面の法線」までにとどめ、実際の姿勢変化は L2 以降のテーマとする

現状の removal_process では **3+2 割り出し** を対象とし、同時 5 軸は今後の拡張を前提とした設計にとどめる。

## 5. CSYS / WCS / 面法線の関係

典型的な設定では:

- **WCS** は機械原点・ワーク中心など
- **CSYS** は
  - ワーク上の基準面（例: 上面）に対して Z+ が外側になるように設定
  - フィーチャの `selector` は CSYS 基準で解釈し、
    - `">Z"`: 基準面から外側へ加工（フェイスミルなど）
    - `"<Z"`: 内側へ掘り込む（穴・ポケットなど）

自由曲面の場合は:

- `csys_ref`: 代表となるワーク基準 CSYS
- `params.face_ref`: 実際の B-Rep 面（局所法線は UV で変化）
- 実装側で「代表法線 ≒ CSYS の Z」になるような CSYS を選ぶ

という運用を想定している。
