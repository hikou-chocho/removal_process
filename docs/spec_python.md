# Python側仕様書（FastAPI + CadQuery） v3.1 完全版

## 1. 概要
FastAPI を用いて除去加工パイプラインを API で実行します。
CadQuery による形状生成と差分計算を行い、各工程ステップで STL 出力します。

### 構成ファイル
| ファイル | 内容 |
|----------|------|
| `main.py` | FastAPI エントリポイント |
| `models.py` | Pydantic モデル定義 |
| `cad_ops.py` | 加工操作（op）のディスパッチ処理 |
| `utils/geometry.py` | 差分計算など補助関数（予定） |

## 2. モデル定義
```python
# models.py
from pydantic import BaseModel, Field
from typing import Literal, Optional, Dict, List

class Operation(BaseModel):
    op: str
    name: Optional[str] = None
    selector: Optional[str] = None
    workplane: Optional[Literal["XY", "YZ", "ZX"]] = None
    csys: Optional[Dict[str, List[float]]] = None
    params: Dict[str, float | int | str] = Field(default_factory=dict)

class Stock(BaseModel):
    type: Literal["block","cylinder","mesh"]
    params: Dict[str, float | int | str]

class PipelineRequest(BaseModel):
    units: Literal["mm","inch"] = "mm"
    origin: Literal["world","center","stock_min"] = "world"
    stock: Stock
    operations: List[Operation]
    output_mode: Literal["stl","show","none"] = "stl"
    file_template_solid: str = "case_{step:02d}_{name}_solid.stl"
    file_template_removed: str = "case_{step:02d}_{name}_removed.stl"
    dry_run: bool = False
```

## 3. 操作仕様
| 操作名 | 概要 |
|--------|------|
| `stock:block` | 直方体素材を生成 |
| `stock:cylinder` | 円柱素材を生成 |
| `stock:mesh` | 外部STL読込 |
| `mill:face` | フェイスミル削り |
| `mill:profile` | 外周削り |
| `drill:hole` | 穴加工 |
| `lathe:face_cut` | 正面削り |
| `lathe:turn_od` | 外径加工 |
| `lathe:bore_id` | 内径加工 |
| `xform:transform` | 平行移動/スケール |

## 4. 差分出力
```python
def apply_op(work, op):
    before = work
    after = work
    if op.op == "mill:face":
        depth = float(op.params.get("depth", 1.0))
        after = before.faces(op.selector or ">Z").workplane().cutBlind(-depth)
    removed = before.cut(after)
    return after, removed
```
- `solid` = after
- `removed` = before - after

## 5. 出力形式
- ファイル命名：`file_template_solid`, `file_template_removed`
- 出力ディレクトリ：`data/output/`
- `output_mode:"show"` の場合は最終形状を `show()`

## 6. 任意輪郭プロファイル加工（lathe:turn_od_profile / lathe:bore_id_profile）

### 目的と位置づけ

- 旋盤用の任意外径 / 内径形状を、**Z–D（軸方向 Z・直径 D）プロファイルの折れ線**として定義し、
- そのプロファイルに沿って外径／内径を削るための Operation 群。
- Phase 1 では **「すべて polyline（折れ線）」のみ**対応し、  
  将来 `corner_c` / `corner_r` などで C 面・R 面処理を追加できる余地を残す。

対象 op:

- `lathe:turn_od_profile` … 外径（Outer Diameter）プロファイル切削
- `lathe:bore_id_profile` … 内径（Inner Diameter）プロファイル切削

---

### 共通座標系と基本ルール

- ワークは Z 軸回りの回転体（`stock.type = "cylinder"`）を想定する。
  - 例: `cq.Workplane("XY").circle(dia/2).extrude(h)`
- **心押し側端面を z=0 としてプロファイル Z を定義する。**
  - `z_profile = 0` … 心押し側端面
  - `z_profile > 0` … チャック側方向へ進む
- ワールド座標系への変換は:
  - `z_world = zmin + z_profile`
    - `zmin` は現ワークの BoundingBox から取得した Z 最小値
- プロファイルで指定した **Z 範囲内だけを加工対象とし、それ以外の Z には手を出さない。**
  - `z_min_profile = min(profile[].z)`
  - `z_max_profile = max(profile[].z)`
  - 実際の加工 Z 範囲は `[zmin + z_min_profile, zmin + z_max_profile]`
- プロファイルは **Z の昇順に限定しない**。
  - `z` が前後に行き来する「戻り形状」（えぐり・切り上げ）も許可する。
  - ただし `z` が完全に同じ点が連続する（長さ 0 のエッジ）はエラーとすることを推奨。

---

### 共通パラメータ `profile`

両 op 共通で、`params.profile` に Z–D プロファイルを定義する。

```jsonc
"params": {
  "profile": [
    { "z": 0.0,  "d": 50.0 },
    { "z": 10.0, "d": 48.0 },
    { "z": 20.0, "d": 45.0 },
    { "z": 30.0, "d": 45.0 }
  ]
}
```

**パラメータ説明:**
- `profile` : list[dict]
  - 各要素: `{ "z": float, "d": float }`
  - `z` : プロファイル座標系での Z 位置（心押し側端面が 0）
  - `d` : その Z での直径（外径 / 内径）

---

### `lathe:turn_od_profile` — 外径プロファイル切削

**概要**: ワークの外径を Z–D プロファイルに沿って切削する。

**パラメータ:**
- `profile` (必須) : list[dict] … Z–D プロファイルの折れ線
  - `z`: Z 座標（プロファイル系）
  - `d`: その Z での目標外径

**動作:**
1. 入力ワークの BoundingBox から `zmin` を取得
2. プロファイルの Z 範囲を確認（`z_min`, `z_max`）
3. プロファイルに沿い、ワールド Z = `zmin + z_profile` で回転体を生成
4. ワーク と差分演算により、目標プロファイル内側を切削

**制約:**
- プロファイルの `d` は現ワーク外径より小さく、かつ `> 0`
- プロファイルに重複する Z（同じ Z で複数の D）があればエラー

---

### `lathe:bore_id_profile` — 内径プロファイル切削

**概要**: ワークの内径を Z–D プロファイルに沿って削る。

**パラメータ:**
- `profile` (必須) : list[dict] … Z–D プロファイルの折れ線
  - `z`: Z 座標（プロファイル系）
  - `d`: その Z での目標内径

**動作:**
1. 入力ワークの BoundingBox から `zmin` を取得
2. プロファイルの Z 範囲を確認（`z_min`, `z_max`）
3. プロファイルに沿い、内径半径の回転体を生成
4. ワーク と差分演算により、目標プロファイル内側を削除

**制約:**
- プロファイルの `d` は現ワーク外径より小さく、かつ `> 0`
- プロファイルに重複する Z（同じ Z で複数の D）があればエラー

---

### 実装ハイレベルイメージ

```python
def _op_lathe_turn_od_profile(before: cq.Workplane, op: Operation) -> cq.Workplane:
    """
    外径プロファイル切削
    """
    profile = _validate_profile(op.params.get("profile"))
    
    bb = before.val().BoundingBox()
    zmin = bb.zmin
    
    # プロファイルに沿い、回転体を生成
    cut_solid = _create_profile_solid(profile, zmin, mode="od")
    
    after = before.cut(cut_solid)
    return after


def _op_lathe_bore_id_profile(before: cq.Workplane, op: Operation) -> cq.Workplane:
    """
    内径プロファイル切削
    """
    profile = _validate_profile(op.params.get("profile"))
    
    bb = before.val().BoundingBox()
    zmin = bb.zmin
    
    # プロファイルに沿い、回転体を生成
    cut_solid = _create_profile_solid(profile, zmin, mode="id")
    
    after = before.cut(cut_solid)
    return after
```
