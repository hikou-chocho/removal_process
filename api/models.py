# api/models.py
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Literal, Optional, Dict, List, Union, Any

Num = Union[float, int]

class Operation(BaseModel):
    op: str
    name: Optional[str] = None
    selector: Optional[str] = None                # CadQuery selector (e.g. ">Z", "<X", "|Y")
    workplane: Optional[Literal["XY", "YZ", "ZX"]] = None
    csys: Optional[Dict[str, List[float]]] = None # 予約（STEP2で回転・平行移動対応）
    params: Dict[str, Any] = Field(default_factory=dict)

class Stock(BaseModel):
    type: Literal["block", "cylinder", "mesh"]
    params: Dict[str, Num | str]

class PipelineRequest(BaseModel):
    units: Literal["mm","inch"] = "mm"
    origin: Literal["world","center","stock_min"] = "world"
    stock: Stock
    operations: List[Operation]
    output_mode: Literal["stl","show","none"] = "stl"
    file_template_solid: str = "case_{step:02d}_{name}_solid.stl"
    file_template_removed: str = "case_{step:02d}_{name}_removed.stl"
    dry_run: bool = False

class StepResult(BaseModel):
    step: int
    name: str
    solid: Optional[str] = None
    removed: Optional[str] = None

class PipelineResponse(BaseModel):
    status: Literal["ok","error"]
    message: Optional[str] = None
    steps: List[StepResult] = Field(default_factory=list)
