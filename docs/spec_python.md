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
